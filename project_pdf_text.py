"""Read PDF text layers locally; never infer image or signature contents."""
import json
import sys
import hashlib
from io import BytesIO
from pathlib import Path
from pypdf import PdfReader


def extract(path,expected_digest):
    data=Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest()!=expected_digest:raise ValueError('PDF在读取前已变化，须重新读取')
    reader=PdfReader(BytesIO(data))
    if len(reader.pages)>300:raise ValueError('PDF页数超过本轮读取容量')
    lines=[];missing=[];total=0
    for number,page in enumerate(reader.pages,1):
        text=page.extract_text() or ''
        total+=len(text)
        if total>3_000_000:raise ValueError('PDF文字层超过本轮读取容量')
        if not text.strip():missing.append(number)
        lines.append(f'PDF第{number}页\n'+(text if text.strip() else '【本页无可读文字层，图像内容未读取】'))
    if len(missing)==len(reader.pages):raise ValueError('PDF没有可读文字层，扫描页待识别')
    return {'text':'\n\n'.join(lines),'missing_pages':missing,'pages':len(reader.pages)}


if __name__=='__main__':
    try:print(json.dumps(extract(sys.argv[1],sys.argv[2]),ensure_ascii=False))
    except Exception:
        print(json.dumps({'error':'PDF文字层无法完整读取，扫描页或受保护内容待核对'},ensure_ascii=False))
        sys.exit(1)
