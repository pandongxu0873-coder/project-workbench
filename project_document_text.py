"""Read reviewed OCR derivatives only for the identical original PDF bytes."""
import json
from pathlib import Path


def reviewed_pdf_text(source_digest, directory=None):
    if len(source_digest) != 64 or any(c not in '0123456789abcdef' for c in source_digest):
        raise ValueError('无效原文件校验值')
    root = Path(directory) if directory else Path(__file__).with_name('project_document_text')
    path = root / (source_digest + '.json')
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('source_sha256') != source_digest or value.get('schema_version') != 1:
        raise ValueError('识别文本与原件不匹配')
    pages = value.get('pages', [])
    if not pages or [p.get('page') for p in pages] != list(range(1, len(pages) + 1)):
        raise ValueError('识别页码不完整')
    if value.get('reviewed_pages') != list(range(1, len(pages) + 1)):
        raise ValueError('识别结果尚未逐页核对')
    if any(not isinstance(p.get('text'), str) or not p['text'].strip() for p in pages):
        raise ValueError('识别页缺少正文')
    limitations = value.get('limitations')
    if not isinstance(limitations, str) or not limitations.strip():
        raise ValueError('识别结果缺少局限说明')
    text = '\n\n'.join('PDF第%d页【本地OCR识别】\n%s' % (p['page'], p['text']) for p in pages)
    return {'text': text, 'pages': len(pages), 'missing_pages': [],
            'method': 'reviewed_local_ocr', 'limitations': limitations}
