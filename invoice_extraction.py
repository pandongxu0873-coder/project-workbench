"""Bounded offline document worker; no network access."""
import json,sys,io
from pathlib import Path

def inspect(path,ext):
 if ext in {'png','jpg','webp'}:
  from PIL import Image
  Image.MAX_IMAGE_PIXELS=20_000_000
  with Image.open(path) as im:
   if im.width*im.height>20_000_000:raise ValueError('图片像素超限')
   im.verify()
  return {'file_state':'unrecognized','extraction_note':'原件已保存；未启用本地OCR，请手工填写','fields':{},'field_sources':{}}
 if ext=='ofd':return {'file_state':'unrecognized','extraction_note':'原件已保存，暂不支持OFD预览/识别','fields':{},'field_sources':{}}
 import fitz,re
 with fitz.open(path) as doc:
  if doc.needs_pass:return {'file_state':'unrecognized','extraction_note':'密码保护文件已保存，请下载解锁后重新上传','fields':{},'field_sources':{}}
  if len(doc)>100:raise ValueError('超过100页解析限制，原件仍保留')
  pages=[page.get_text()[:20000] for page in doc]
  fields={};sources={}
  patterns={'number':r'发票号码[：:\s]*([0-9]{8,30})','code':r'发票代码[：:\s]*([0-9]{8,20})','issued_on':r'开票日期[：:\s]*(\d{4}年\d{1,2}月\d{1,2}日)'}
  for key,pat in patterns.items():
   found=[(i,m) for i,text in enumerate(pages,1) for m in re.finditer(pat,text)]
   if len(found)==1:
    i,m=found[0];v=m.group(1)
    if key=='issued_on':
     nums=re.findall(r'\d+',v);v=f'{int(nums[0]):04}-{int(nums[1]):02}-{int(nums[2]):02}'
    fields[key]=v;sources[key]={'source':'native_pdf_text','page':i,'excerpt':m.group(0)[:100]}
  return {'file_state':'read' if any(t.strip() for t in pages) else 'unrecognized','extraction_note':'已读取原生文本，提取字段仍待人工核对；不自动判断多票和金额' if any(t.strip() for t in pages) else '扫描件已保存；未启用OCR，请手工填写','fields':fields,'field_sources':sources,'page_count':len(pages)}
if __name__=='__main__':
 if sys.argv[1]=='--validate-image':
  from PIL import Image
  Image.MAX_IMAGE_PIXELS=20_000_000
  raw=sys.stdin.buffer.read(20*1024*1024+1)
  if len(raw)>20*1024*1024:raise ValueError('limit')
  with Image.open(io.BytesIO(raw)) as im:
   if im.format not in {'PNG','JPEG','WEBP'} or im.width*im.height>20_000_000:raise ValueError('format or pixels')
   im.verify()
  sys.exit(0)
 try:print(json.dumps(inspect(Path(sys.argv[1]),sys.argv[2]),ensure_ascii=False))
 except Exception:print(json.dumps({'file_state':'unrecognized','extraction_note':'原件已保存，文件损坏、格式或本地解析能力受限；可下载及手工填写','fields':{},'field_sources':{}}))
