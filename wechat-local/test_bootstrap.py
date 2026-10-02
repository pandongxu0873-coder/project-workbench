import json
from types import SimpleNamespace
from unittest.mock import patch
import bootstrap

def test_private_save(tmp_path):
    target=tmp_path/'key.json'
    bootstrap.save_private(target,{'test':'synthetic'})
    assert target.stat().st_mode & 0o777 == 0o600

def fixture(tmp_path, monkeypatch):
    app=tmp_path/"WeChat.app"
    (app/"Contents/MacOS").mkdir(parents=True)
    (app/"Contents/MacOS/WeChat").write_bytes(b"synthetic")
    monkeypatch.setattr(bootstrap,"APP",app)
    backup=tmp_path/'backup';backup.mkdir()
    (tmp_path/'backup.json').write_text(json.dumps({'backup':str(backup)}))
    db=tmp_path/'message_0.db';db.write_bytes(b'0'*4096)
    return backup,db

def test_running_wechat_prevents_mutation(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch);commands=[]
    with patch.object(bootstrap,'PRIVATE',tmp_path), patch.object(bootstrap,'status'), patch.object(bootstrap,'checked',side_effect=lambda c:commands.append(c)), patch.object(bootstrap.subprocess,'run',return_value=SimpleNamespace(returncode=0)):
        assert bootstrap.execute(30)==2
    assert not any('--sign' in command for command in commands)

def test_signing_failure_restores_official_app(tmp_path, monkeypatch):
    backup,db=fixture(tmp_path, monkeypatch)
    def checked(cmd):
        if '--sign' in cmd: raise RuntimeError('synthetic failure')
    with patch.object(bootstrap,'PRIVATE',tmp_path),patch.object(bootstrap,'databases',return_value=[db]),patch.object(bootstrap,'status') as status,patch.object(bootstrap,'checked',side_effect=checked),patch.object(bootstrap,'restore') as restore,patch.object(bootstrap.subprocess,'run',return_value=SimpleNamespace(returncode=1)):
        assert bootstrap.execute(30)==1
        restore.assert_called_once_with(backup)
        assert status.call_args.args[0]=='official_app_verified'
        assert status.call_args.kwargs['key_verified'] is False

def test_failed_restoration_never_claims_restored(tmp_path, monkeypatch):
    _,db=fixture(tmp_path, monkeypatch)
    def checked(cmd):
        if '--sign' in cmd: raise RuntimeError('synthetic failure')
    with patch.object(bootstrap,'PRIVATE',tmp_path),patch.object(bootstrap,'databases',return_value=[db]),patch.object(bootstrap,'status') as status,patch.object(bootstrap,'checked',side_effect=checked),patch.object(bootstrap,'restore',side_effect=RuntimeError('synthetic')),patch.object(bootstrap.subprocess,'run',return_value=SimpleNamespace(returncode=1)):
        assert bootstrap.execute(30)==3
        assert status.call_args.args[0]=='restoration_failed'
