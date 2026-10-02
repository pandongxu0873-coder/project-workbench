"""Read exact named attachments into inference without changing originals."""
from functools import lru_cache
from pathlib import Path
import time
import re
import json
import hashlib
import subprocess
import zipfile
from project_document_text import reviewed_pdf_text
import xml.etree.ElementTree as ET

SUPPORTED={'.docx','.xlsx','.pdf','.json'}

@lru_cache(maxsize=32)
def _pdf_text(path,content_digest):
    reviewed=reviewed_pdf_text(content_digest)
    if reviewed is not None:return reviewed
    runtime=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
    if not runtime.is_file():raise ValueError('本机PDF文字层读取组件不可用')
    try:
        result=subprocess.run([str(runtime),str(Path(__file__).with_name('project_pdf_text.py')),path,content_digest],capture_output=True,text=True,timeout=30)
        payload=json.loads(result.stdout)
        if result.returncode or payload.get('error'):raise ValueError('PDF文字层未能读取，扫描页或受保护内容待核对')
        return payload
    except (OSError,subprocess.TimeoutExpired,json.JSONDecodeError):raise ValueError('PDF文字层未能读取')

def pdf_limitations(path):
    value=_pdf_text(str(path),hashlib.sha256(path.read_bytes()).hexdigest())
    if value.get('method')=='reviewed_local_ocr':return value['limitations']
    missing=value['missing_pages']
    return 'PDF仅读取文字层；图像、图表及签章未核验'+('；无文字层页：'+','.join(map(str,missing)) if missing else '')

def has_original_quote(source, quote):
    if not isinstance(quote,str) or not quote.strip():return False
    return any(quote in text for text in source.get('original_quotes',[])) if source.get('extracted') else quote in source['content']

def covered_excerpts(documents, budget=160000, per_source=24000):
    """Water-fill the context budget so recent long files cannot erase history."""
    lengths=[min(len(s['content']),per_source) for s in documents]
    lo,hi=0,per_source
    while lo<hi:
        cap=(lo+hi+1)//2
        if sum(min(n,cap) for n in lengths)<=budget:lo=cap
        else:hi=cap-1
    result=[]
    marker='\n【中间内容省略；本来源仅提供节选】\n'
    for source in documents:
        content=source['content'];limit=min(lo,per_source)
        if not limit:continue
        truncated=len(content)>limit
        if truncated:
            half=max(0,(limit-len(marker))//2)
            content=content[:half]+marker+content[-half:] if half else content[:limit]
        result.append({**source,'content':content,'truncated':truncated})
    return result

def attachment_text(path):
    """Deterministic, read-only extraction; values retain sheet/cell addresses."""
    if path.stat().st_size>60_000_000:raise ValueError('附件超过可读大小')
    if path.suffix.lower()=='.json':
        text=path.read_text(encoding='utf-8-sig')
        json.loads(text)  # Validate structure, retaining exact source text for citations.
        return text
    if path.suffix.lower()=='.pdf':
        value=_pdf_text(str(path),hashlib.sha256(path.read_bytes()).hexdigest())
        return '【'+pdf_limitations(path)+'】\n'+value['text']
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist())>60_000_000:raise ValueError('附件解压后超过可读大小')
        if path.suffix.lower()=='.docx':
            root=ET.fromstring(z.read('word/document.xml'))
            ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            return '\n'.join(''.join(p.itertext()) for p in root.findall('.//w:p',ns))
        ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            shared=[''.join(t.text or '' for t in e.findall('.//m:t',ns)) for e in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',ns)]
        rels={e.attrib['Id']:e.attrib['Target'] for e in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        lines=[]
        for sheet in ET.fromstring(z.read('xl/workbook.xml')).findall('m:sheets/m:sheet',ns):
            target=rels[sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
            target=target.lstrip('/') if target.startswith('/') else 'xl/'+target
            lines.append('工作表：'+sheet.attrib['name'])
            for row in ET.fromstring(z.read(target)).findall('.//m:row',ns):
                cells=[]
                for c in row.findall('m:c',ns):
                    v=c.find('m:v',ns);value=v.text or '' if v is not None else ''
                    if c.get('t')=='s':value=shared[int(value)] if value else ''
                    elif c.get('t')=='inlineStr':value=''.join(t.text or '' for t in c.findall('.//m:t',ns))
                    if value:cells.append(c.attrib.get('r','')+'='+value)
                if cells:lines.append(' | '.join(cells))
        return '\n'.join(lines)

@lru_cache(maxsize=2)
def _asset_index(root, epoch):
    index={}
    for path in (Path(root)/'raw').rglob('*'):
        if path.is_file() and path.suffix.lower() in SUPPORTED|{'.txt'}:index.setdefault(path.name,[]).append(str(path.relative_to(root)))
    return index

@lru_cache(maxsize=2)
def _asset_trie(root,epoch):
    trie={}
    for name in _asset_index(root,epoch):
        node=trie
        for char in reversed(name):node=node.setdefault(char,{})
        node[None]=name
    return trie

def mentioned_names(body,trie):
    """Scan extensions once, then resolve exact basenames backwards."""
    found=set()
    for match in re.finditer(r'\.(?:docx|xlsx|pdf|txt)(?![\w.\-])',body,re.IGNORECASE):
        node=trie;position=match.end()
        while position and body[position-1] in node:
            position-=1;node=node[body[position]]
            if None in node and (not position or not re.match(r'[\w.\-]',body[position-1])):found.add(node[None])
    return found

def discovery_snapshot(root):
    # One exact directory observation per request; never reuse a timed snapshot
    # for another request (a second same-named attachment changes identity).
    epoch=time.monotonic_ns()
    return _asset_index(str(root),epoch),_asset_trie(str(root),epoch)


def supplement_sources(project, root, discovery=None):
    """Only exact unique filenames in explicit project evidence, no keyword join."""
    existing={s['path'] for s in project['sources']}
    bodies=[]
    for source in project['sources']:
        if source.get('readable') and source.get('exists') and source.get('relation')!='background_reference':
            path=(root/source['path']).resolve()
            if root.resolve() in path.parents:bodies.append((source['path'],path.read_text(encoding='utf-8')))
    found=[]
    # Resolve only an explicitly linked exact path with its omitted .md suffix.
    for source in project['sources']:
        if not source.get('exists') and not Path(source['path']).suffix:
            relative=source['path']+'.md';path=(root/relative).resolve()
            if relative not in existing and root.resolve() in path.parents and path.is_file():
                found.append({**source,'path':relative,'exists':True,'readable':True})
                existing.add(relative)
    index,trie = discovery if discovery is not None else discovery_snapshot(root)
    references={};explicit={}
    for path,body in bodies:
        # Missing explicitly named files must remain visible even when their
        # basename has no entry anywhere in the local file index.
        for match in re.finditer(r'(?<![\w/])raw/[^\n\r`"\'\[\]<>|]*?\.(?:docx|xlsx|pdf|txt)(?![\w.\-])',body,re.IGNORECASE):
            relative=match.group()
            explicit.setdefault(Path(relative).name,{}).setdefault(relative,path)
        for name in mentioned_names(body,trie):
            references.setdefault(name,path)
            # A complete path is authoritative, including when it is broken.
            # A Markdown label must not fall back to another client's file.
            pattern=r'raw/[^\n\r`"\'\[\]<>|]*?'+re.escape(name)+r'(?![\w.\-])'
            for match in re.finditer(pattern,body):
                declared='raw/'+match.group().rsplit('raw/',1)[-1]
                explicit.setdefault(name,{}).setdefault(declared,path)
    for name in dict.fromkeys([*index,*explicit]):
        paths=index.get(name,[])
        if name in explicit:
            candidates=explicit[name]
        elif len(paths)==1 and name in references:
            candidates={paths[0]:references[name]}
        else:continue
        # A suffix of another attachment name must never join two projects.
        # Paths, wiki links and Markdown labels delimit the complete basename.
        for relative,referring in candidates.items():
            path=(root/relative).resolve()
            if relative in existing or root.resolve() not in path.parents:continue
            exists=path.is_file()
            found.append({'path':relative,'exists':exists,'readable':exists and path.suffix.lower()=='.txt','relation':'cited_attachment','cited_by':referring,'evidence_date':''})
            existing.add(relative)
    customer=project.get('customer','')
    if customer and '/' not in customer and '\\' not in customer and customer not in ('.','..','客户关联待核实'):
        relative='entities/'+customer+'.md';path=(root/relative).resolve()
        if relative not in existing and root.resolve() in path.parents and path.is_file():
            found.append({'path':relative,'exists':True,'readable':True,'relation':'customer_background','evidence_date':''})
            existing.add(relative)
    # Preserve explicitly mutual entity links as related background. They do
    # not assert that the linked entity is the project's contracting customer.
    main=next((body for path,body in bodies if path==project.get('source_path')),'')
    project_link=str(Path(project['source_path']).with_suffix('')) if project.get('source_path') else ''
    if main and project_link:
        for entity in re.findall(r'\[\[(entities/[^\]\|#]+)(?:[|#][^\]]*)?\]\]',main):
            relative=entity if entity.endswith('.md') else entity+'.md';path=(root/relative).resolve()
            if relative in existing or root.resolve() not in path.parents or not path.is_file():continue
            body=path.read_text(encoding='utf-8')
            if re.search(r'\[\['+re.escape(project_link)+r'(?:\.md)?(?:[|#][^\]]*)?\]\]',body):
                found.append({'path':relative,'exists':True,'readable':True,'relation':'background_reference','evidence_date':''})
                existing.add(relative)
    return found
