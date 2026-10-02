"""One bounded, local-only key bootstrap. Restores verified official app in finally.

Run only with explicit authorization for temporary ad-hoc signing and login.
Never logs key material or changes SIP; never installs a background service.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT / "private"
OFFICIAL = Path("/Applications/WeChat.app")
APP = PRIVATE / "runtime/WeChat.app"
SQLCIPHER = "/opt/homebrew/bin/sqlcipher"

def save_private(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".write-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)

def status(state, **extra):
    result = {"state": state, "updated_at": time.time(), **extra}
    save_private(PRIVATE / "bootstrap-status.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)

def checked(args):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
    if p.returncode:
        raise RuntimeError(Path(args[0]).name + " failed")

def databases():
    base = Path.home()/"Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"
    return sorted(base.glob("*/db_storage/**/*.db"))

def validates(raw_hex, path):
    if not re.fullmatch(r"[0-9a-f]{64}", raw_hex): return False
    with path.open("rb") as f: salt=f.read(16)
    derived=hashlib.pbkdf2_hmac("sha512",bytes.fromhex(raw_hex),salt,256000,dklen=32).hex()
    sql=(f"PRAGMA key = \"x'{derived}'\";\nPRAGMA kdf_iter=1;\n"
         "PRAGMA cipher_compatibility=4;\nPRAGMA cipher_page_size=4096;\n"
         "PRAGMA query_only=ON;\nSELECT count(*) FROM sqlite_master;\n")
    p=subprocess.run([SQLCIPHER,"-readonly",str(path)],input=sql,text=True,
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=8)
    return p.returncode==0 and any(x.strip().isdigit() and int(x)>0 for x in p.stdout.splitlines())

def restore(backup):
    # Only the private disposable copy is signed. The installed app must remain intact.
    checked(["codesign","--verify","--deep","--strict",str(OFFICIAL)])
    expected=hashlib.sha256((backup/"Contents/MacOS/WeChat").read_bytes()).digest()
    actual=hashlib.sha256((OFFICIAL/"Contents/MacOS/WeChat").read_bytes()).digest()
    if expected!=actual: raise RuntimeError("official executable mismatch")

def execute(seconds):
    import frida
    meta=json.loads((PRIVATE/"backup.json").read_text())
    backup=Path(meta["backup"])
    checked(["codesign","--verify","--deep","--strict",str(backup)])
    if not APP.is_dir() or not os.access(APP/"Contents/MacOS/WeChat",os.W_OK):
        status("temporary_copy_not_ready",chat_messages_read=0); return 2
    if subprocess.run(["pgrep","-x","WeChat"],capture_output=True).returncode==0:
        status("needs_wechat_closed",chat_messages_read=0); return 2
    dbs=databases()
    targets=[p for p in dbs if re.fullmatch(r"message_\d+\.db",p.name)]
    if not targets: raise RuntimeError("no message database")
    salts=[]
    for p in dbs:
        with p.open("rb") as f: salts.append(f.read(16).hex())
    js="""
const salts=new Set(SALTS);
const hex=p=>Array.from(new Uint8Array(p.readByteArray(32))).map(b=>b.toString(16).padStart(2,'0')).join('');
const seen=new Set();
const fn=Module.findGlobalExportByName('CCKeyDerivationPBKDF');
if (!fn) { send({kind:'unavailable'}); }
else {
  Interceptor.attach(fn, {
    onEnter(a) {
      if (a[2].toInt32()!==32 || a[4].toInt32()!==16 || a[6].toInt32()!==256000 || a[8].toInt32()!==32) return;
      const salt=Array.from(new Uint8Array(a[3].readByteArray(16))).map(b=>b.toString(16).padStart(2,'0')).join('');
      if (!salts.has(salt)) return;
      const key=hex(a[1]);
      if (!seen.has(key)) { seen.add(key); send({kind:'candidate',key:key,salt:salt}); }
    }
  });
  send({kind:'ready'});
}
""".replace("SALTS",json.dumps(salts))
    messages=queue.Queue(); session=None; device=None; pid=None; modified=False; success=False; restore_failed=False
    def receive(message,data):
        if message.get("type")=="send": messages.put(message.get("payload",{}))
        elif message.get("type")=="error": messages.put({"kind":"hook_error"})
    try:
        status("temporarily_signing_private_copy",chat_messages_read=0)
        modified=True
        checked(["codesign","--force","--deep","--sign","-",str(APP)])
        device=frida.get_local_device()
        pid=device.spawn([str(APP/"Contents/MacOS/WeChat")],stdio='pipe')
        session=device.attach(pid)
        script=session.create_script(js); script.on("message",receive); script.load()
        device.resume(pid)
        status("waiting_for_login",timeout_seconds=seconds,chat_messages_read=0)
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            try: event=messages.get(timeout=1)
            except queue.Empty: continue
            kind=event.get("kind")
            if kind in {"hook_error","unavailable"}:
                raise RuntimeError("key capture unavailable")
            if kind!="candidate": continue
            key=event.get("key","")
            candidate_targets=[]
            for p in targets:
                with p.open("rb") as f: salt=f.read(16).hex()
                if salt==event.get("salt"): candidate_targets.insert(0,p)
                else: candidate_targets.append(p)
            verified=next((p for p in candidate_targets if validates(key,p)),None)
            if verified:
                save_private(PRIVATE/"key.json",{"raw_key":key,"account_directory":str(verified.parents[2]),"validated_at":time.time()})
                success=True
                status("key_verified",chat_messages_read=0)
                break
        if not success: status("capture_timeout",chat_messages_read=0)
    except (Exception, KeyboardInterrupt) as exc:
        # Exception messages may contain arbitrary application output. Never print them.
        status("capture_failed",error_type=type(exc).__name__,chat_messages_read=0)
    finally:
        # Native Frida detach/kill may hang after TransportError. Terminate only
        # our exact temporary executable before releasing the instrumentation.
        if pid:
            process=subprocess.run(['ps','-p',str(pid),'-o','comm='],capture_output=True,text=True,timeout=5)
            if process.stdout.strip()==str(APP/'Contents/MacOS/WeChat'):
                try:os.kill(pid,signal.SIGTERM)
                except ProcessLookupError:pass
            for _ in range(30):
                try: os.kill(pid,0)
                except ProcessLookupError: break
                time.sleep(.1)
            else:
                process=subprocess.run(['ps','-p',str(pid),'-o','comm='],capture_output=True,text=True,timeout=5)
                if process.stdout.strip()==str(APP/'Contents/MacOS/WeChat'):
                    try:os.kill(pid,signal.SIGKILL)
                    except ProcessLookupError:pass
        if modified:
            status("verifying_official_app",key_verified=success,chat_messages_read=0)
            try: restore(backup)
            except Exception as exc:
                status("restoration_failed",error_type=type(exc).__name__,key_verified=success)
                restore_failed=True
        if not restore_failed:
            status("official_app_verified",key_verified=success,chat_messages_read=0)
    if restore_failed: return 3
    return 0 if success else 1

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--execute",action="store_true",required=True)
    parser.add_argument("--timeout",type=int,default=180)
    args=parser.parse_args()
    signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    raise SystemExit(execute(max(30,min(args.timeout,300))))
