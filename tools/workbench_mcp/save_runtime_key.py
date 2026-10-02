import getpass, os, tempfile
from pathlib import Path
os.umask(0o077)
root=Path(__file__).resolve().parent/'private'
root.mkdir(mode=0o700,exist_ok=True)
print('请粘贴刚在 OpenAI 官方页面创建的连接凭证。输入不会显示，按回车保存。')
print('凭证仅保存在本机受保护文件，不发送到聊天，不会调用模型。')
key=getpass.getpass('连接凭证：').strip()
if not key.startswith('sk-') or len(key)<20 or any(c.isspace() for c in key):
    print('格式不正确，未保存。');raise SystemExit(1)
fd,name=tempfile.mkstemp(dir=root,prefix='.runtime-')
with os.fdopen(fd,'w') as f:f.write(key+'\n')
os.chmod(name,0o600);os.replace(name,root/'runtime-key')
key=''
print('已保存在本机。请回到聊天告诉我：凭证已保存。')
input('按回车关闭。')
