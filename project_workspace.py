import project_archive
import project_notifications
import time
"""Project read model. Explicit source paths, never a customer-stage writer."""
import hashlib
import json
import re
import threading
from functools import lru_cache
from datetime import datetime, date, timedelta
from pathlib import Path
from public_signal_hub import identity_aliases, name_key

PLAN_LOCK = threading.Lock()
ROLES = (
    ("交付", ("迁移", "切换", "验收", "实施", "排期"), "确认资源、实施边界与验收结果"),
    ("技术 TO", ("接口", "研发", "人天", "架构", "数据字典"), "确认技术可行性、依赖与工作量"),
    ("销售助理", ("文件", "资质", "盖章", "招投标", "标书"), "整理材料、预检查与流程跟踪"),
    ("售前", ("需求", "方案", "演示", "Demo", "功能"), "澄清需求并形成可验证方案"),
)

def identity(value):
    return hashlib.sha256(value.encode()).hexdigest()[:20]

def clean(value):
    value = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m[2] or m[1], value)
    return re.sub(r"^\s*[-*]\s*(?:\[[ xX]\]\s*)?", "", value).replace("**", "").strip()

def section(text, words):
    for match in re.finditer(r"^##\s+(.+)\n([\s\S]*?)(?=^##\s|\Z)", text, re.M):
        if any(word in match[1] for word in words):
            return match[2].strip()
    return ""

def read_plan(root, project_id):
    path = root / "project_plans" / f"{project_id}.json"
    return json.loads(path.read_text()) if path.exists() else {"revision": 0, "actions": {}}

def explicit_link_index(knowledge_root):
    index = {}
    for directory in ('raw', 'tracking', 'queries', 'projects', 'moc', 'comparisons'):
        for path in (knowledge_root / directory).rglob('*'):
            if path.is_file() and path.suffix.lower() in ('.md', '.txt'):
                index.setdefault(path.stem, []).append(str(path.relative_to(knowledge_root)))
    return index

REVIEW_MARKERS = r'归档|核验|归整|复核|回读|补录|转写|转译|重校|重新识别'

def _dates(text):
    values = re.findall(r'(?<!\d)(20\d{2})[-年/_](\d{1,2})[-月/_](\d{1,2})(?!\d)', text)
    values += re.findall(r'(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)', text)
    valid = []
    for year, month, day in values:
        try:
            value = date(int(year), int(month), int(day))
            if value <= date.today(): valid.append(value.isoformat())
        except ValueError: pass
    return valid

def _date_value(text):
    # The adjacent date/range belongs to the label; later dates may be promises.
    token=r'(?:20\d{2}[-年/_]\d{1,2}[-月/_]\d{1,2}日?|20\d{6})(?!\d)'
    match=re.match(r'''\s*[`"']?(?:(?:PHONE|VM)[-_]\d+\s*[，,]\s*)?('''+token+r'(?:\s*(?:至|到|~|～|—|–|--|-)\s*'+token+r')?)',text)
    return _dates(match[1]) if match else []

def source_dates(path, body):
    return _source_dates(str(path), body, date.today())

@lru_cache(maxsize=512)
def _source_dates(path, body, today):
    # Prefer explicit occurrence metadata. A filename may contain both the
    # original recording date and a later review date; they are not equivalent.
    explicit, headings = [], []
    for line in body.splitlines():
        plain = re.sub(r'^\s*[-*]\s+', '', line).replace('**', '').strip()
        occurrence=re.match(r'^(?:occurred_at|event_date|沟通日期|录音日期|会议日期|业务日期|发生日期|录音)\s*[:：]', plain)
        if occurrence:
            explicit += _date_value(plain[occurrence.end():])
        elif not re.search(r'计划|预计|截止|排期', plain) and (
                not re.search(REVIEW_MARKERS, plain) or re.search(
                    r'客户回复\s*[:：].*(?:复核|核验)|客户.*(?:已复核|已核验|复核了|核验了)|客户.*(?:人天|人日|工作量|需求).*复核', plain)):
            if re.match(r'^(?:date|日期)\s*[:：]', plain): explicit += _date_value(re.split(r'[:：]',plain,maxsplit=1)[1])
            elif re.match(r'^#{1,6}\s', plain) and re.search(r'沟通|会议|录音|拜访|反馈|客户回复|电话|访谈', plain): headings += _dates(plain)
    if explicit: return max(explicit + headings)
    # Dated archive directories are ignored. In a reviewed recording filename,
    # only a leading original date is eligible; a review suffix is never used.
    values = list(headings)
    for part in Path(path).parts:
        if re.search(REVIEW_MARKERS, part):
            if part == Path(path).name and re.search(r'PHONE[-_]|VM[-_]|原始录音', part) and re.match(r'^20\d{2}(?:[-_]\d{2}[-_]\d{2}|\d{4})', part):
                values += _dates(re.split(REVIEW_MARKERS, part, maxsplit=1)[0])
        else: values += _dates(part)
    return max(values, default='')

def review_dates(path, body):
    return _review_dates(str(path), body, date.today())

@lru_cache(maxsize=512)
def _review_dates(path, body, today):
    values = []
    for part in Path(path).parts:
        match = re.search(REVIEW_MARKERS, part)
        if match: values += _dates(part[match.start():])
    for line in body.splitlines():
        marker = re.search(r'(?:复核日期|核验日期|归档核验|归档日期|(?:资料)?回读(?:日期|日)|reviewed_at)\s*[:：]', line)
        if marker: values += _dates(line[marker.end():])
        if re.match(r'^#{1,6}\s|^\s*(?:复核日期|归档日期|reviewed_at)\s*[:：]', line) and re.search(REVIEW_MARKERS + '|reviewed_at', line):
            values += _dates(line)
    return max(values, default='')

def linked_sources(body, front, knowledge_root, source, link_index=None):
    paths = re.findall(r"(?:^\s*-\s+|[\"'])(?P<path>(?:raw|tracking|queries)/[^\n\"']+)", front, re.M)
    paths += re.findall(r"\^\[((?:raw|tracking|queries)/[^\]]+)\]", body)
    paths += re.findall(r"`((?:raw|tracking|queries)/[^`]+)`", section(body, ("来源",)))
    for target in re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', body):
        target = target.split('#', 1)[0].strip()
        if target.startswith(('raw/', 'tracking/', 'queries/', 'projects/', 'moc/', 'comparisons/')):
            paths.append(target if Path(target).suffix else target + '.md')
        elif '/' not in target:
            matches = (link_index or {}).get(Path(target).stem, [])
            if len(matches) == 1: paths.append(matches[0])
    output = [{"path": source, "label": "项目判断原文", "exists": True, "readable": True, "relation": "project_source"}]
    for rel in dict.fromkeys(paths):
        rel = rel.strip().strip('"\'`')
        target = (knowledge_root / rel).resolve()
        if knowledge_root.resolve() not in target.parents or rel == source:
            continue
        output.append({"path": rel, "label": "明确引用的来源", "exists": target.is_file(), "readable": target.suffix.lower() in (".md", ".txt"), "relation": "background_reference" if rel.startswith(("projects/", "moc/", "comparisons/")) else "explicit_evidence"})
    return output

def read_source(project_id, source, knowledge_root, state_root):
    project = next((p for p in build_projects(knowledge_root, state_root) if p["id"] == project_id), None)
    item = next((s for s in project["sources"] if s["path"] == source), None) if project else None
    if not item or not item.get("readable") or not item["exists"]:
        raise ValueError("该材料不在本项目可读取的来源中")
    path = (knowledge_root / source).resolve()
    if knowledge_root.resolve() not in path.parents:
        raise ValueError("来源路径超出知识库")
    content = path.read_text(encoding="utf-8")
    return {"ok": True, "project_id": project_id, "path": source, "content": content[:300000], "truncated": len(content) > 300000}

def known_customer_names(knowledge_root, project_documents):
    """Only registered customers and explicit project customer fields are identity anchors."""
    names=set()
    registry=knowledge_root/'tracking/client_registry.md'
    try:
        for line in registry.read_text(encoding='utf-8').splitlines():
            if not line.startswith('|'):continue
            cells=[v.strip() for v in line.strip('|').split('|') if v.strip()]
            if cells and cells[0]!='客户' and not re.fullmatch(r'[- :]+',cells[0]):names.add(name_key(clean(cells[0])))
    except OSError:pass
    for body in project_documents:
        names.update(name_key(value) for value in re.findall(r'\*?\*?客户\*?\*?\s*[：:]\s*\[\[([^\]|]+)',body))
    return {name_key(alias) for name in names for alias in identity_aliases(name)}

def linked_customer_fallback(body, intro, known):
    # Never infer identity from the project title, free text, or contact/entity order.
    candidates={}
    for scope in (intro,section(body,('关联',))):
        for target in re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]',scope):
            if '/' in target and not target.startswith('entities/') and target not in known:continue
            name=name_key(target.split('#',1)[0])
            if name in known:candidates[name]=target
    if len(candidates)!=1:return None
    name,target=next(iter(candidates.items()))
    return {'name':name,'link':target}

def explicit_related_customers(body, known, source, primary_customer):
    """资料明示关联客户: display references, never identity or business relationships."""
    primary={name_key(value) for value in identity_aliases(primary_customer)}
    reference_only=set()
    for statement in re.split(r'[\n。；]',body):
        if re.search(r'对照|对标|类比|借鉴|参考案例|行业案例|仅供参考',statement):
            reference_only.update(name_key(target.split('#',1)[0]) for target in re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]',statement))
    related={}
    for scope in re.finditer(r'^##\s+(?:关联|关联客户)\s*\n([\s\S]*?)(?=^##\s|\Z)',body,re.M):
        references={}
        for target in re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]',scope[1]):
            target=target.split('#',1)[0].strip()
            if '/' in target and not target.startswith('entities/'):continue
            name=name_key(target)
            if name in known or name in primary:references.setdefault(name,target)
        # Require the declared primary party in the same section. Even then,
        # explicitly described comparisons/cases are not public-signal edges.
        if not primary.intersection(references):continue
        for name,target in references.items():
            if name not in primary and name not in reference_only:
                related.setdefault(name,{'customer':name,'path':source,'link':target})
    return list(related.values())

def build_projects(knowledge_root, state_root):
    observed = time.time_ns()
    projects = []
    link_index = explicit_link_index(knowledge_root)
    documents=[(path,path.read_text(encoding='utf-8')) for path in (knowledge_root/'projects').glob('*.md')]
    known_customers=known_customer_names(knowledge_root,[body for _,body in documents])
    for path,body in documents:
        if not re.search(r"客户|项目", body):
            continue
        source = str(path.relative_to(knowledge_root))
        project_id = identity(source)
        title = re.search(r"^#\s+(.+)$", body, re.M)
        customer = re.search(r"\*?\*?客户\*?\*?\s*[：:]\s*\[\[([^\]|]+)", body)
        # Only frontmatter paths are direct source edges. Mere mentions stay in the document.
        front = body.split("---", 2)[1] if body.startswith("---") else ""
        sources = linked_sources(body, front, knowledge_root, source, link_index)
        intro = re.split(r"^#{2,}\s", body.split("---", 2)[-1] if body.startswith("---") else body, maxsplit=1, flags=re.M)[0]
        intro_entity = re.search(r"\[\[entities/([^\]|]+)", intro)
        linked_customer=linked_customer_fallback(body,intro,known_customers) if not customer and not intro_entity else None
        primary_customer=customer[1] if customer else intro_entity[1] if intro_entity else linked_customer['name'] if linked_customer else "客户关联待核实"
        plan = read_plan(state_root, project_id)
        actions = []
        action_body = section(body, ("下一步", "后续动作", "行动建议", "当前待办", "关键行动", "销售动作"))
        action_lines = action_body.splitlines()
        has_list = any(re.match(r"^\s*(?:[-*]|\d+[.)、])\s", line) for line in action_lines)
        for line in action_lines:
            if (has_list and not re.match(r"^\s*(?:[-*]|\d+[.)、])\s", line)) or re.match(r"^\s*[-*]\s+\[[xX]\]", line):
                continue
            task = re.sub(r"\^\[[^\]]+\]", "", re.sub(r"^\d+[.)、]\s*", "", clean(line))).strip()
            if not task:
                continue
            action_id = identity(source + ":" + task)
            role, deliverable = "销售本人", "获得客户或内部的明确答复与下一节点"
            suggested_roles = []
            for suggested, markers, outcome in ROLES:
                if any(marker in task for marker in markers):
                    suggested_roles.append(suggested)
                    if len(suggested_roles) == 1:
                        role, deliverable = suggested, outcome
            actions.append({"id": action_id, "task": task, "source_path": source,
                            "suggested_role": role, "deliverable": deliverable,
                            "support_roles": suggested_roles[1:],
                            "record": plan.get("actions", {}).get(action_id, {})})
        updated = re.search(r"^updated:\s*(.+)$", front, re.M)
        summary = clean(section(body, ("一句话判断", "当前判断", "当前重点", "销售判断", "核心判断")))
        if not summary:
            dated = list(re.finditer(r"^###\s+(20\d{2}-\d{2}-\d{2}[^\n]*)\n([\s\S]*?)(?=^#{1,3}\s|\Z)", body, re.M))
            if dated:
                latest = max(dated, key=lambda m: m[1][:10])
                summary = clean(latest[2].split("\n\n")[0])
                summary = f"材料摘录（{latest[1][:10]}）：{summary}"
        summary = re.sub(r"\^\[[^\]]+\]", "", summary).strip()
        risks = [clean(line) for line in section(body, ("主要风险", "风险", "待确认")).splitlines() if line.strip()][:5]
        evidence_dates, reviewed_dates = [], []
        for evidence in sources:
            if evidence['exists'] and evidence['readable']:
                try:
                    text = (knowledge_root / evidence['path']).read_text(encoding='utf-8')
                    evidence['content_sha256'] = hashlib.sha256(text.encode('utf-8')).hexdigest()
                    source_front = text.split('\n---', 1)[0] if text.startswith('---\n') else ''
                    source_title = re.search(r'^title:\s*([^\n]+)', source_front, re.M)
                    source_heading = re.search(r'^#\s+(.+)$', text, re.M)
                    caption = source_title or source_heading
                    if caption:
                        evidence['title'] = clean(caption[1].strip().strip('"\''))[:160]
                    evidence['evidence_date'] = source_dates(evidence['path'], text)
                    evidence['reviewed_date'] = review_dates(evidence['path'], text)
                    if evidence['evidence_date'] and evidence.get('relation')!='background_reference': evidence_dates.append(evidence['evidence_date'])
                    if evidence['reviewed_date'] and evidence.get('relation')!='background_reference': reviewed_dates.append(evidence['reviewed_date'])
                except (OSError, UnicodeError): evidence['evidence_date'] = ''
        from project_rounds import _read as read_local_round
        try:
            local = read_local_round(state_root / 'project_rounds' / f'{project_id}.json', project_id)
            # Entering/correcting old facts today does not mean a new conversation today.
            substantive = [h['record'] for h in local['history'] if h['record'].get('facts') or h['record'].get('feedback')]
            previous_content = None
            for record in substantive:
                content = (record.get('facts'), record.get('feedback'))
                if content != previous_content:
                    occurrence = source_dates('', '\n'.join(content))
                    if occurrence: evidence_dates.append(occurrence)
                previous_content = content
            current_round = local['record'] or {}
        except (ValueError, OSError): current_round = None
        analysis_cache = None
        try:
            from project_analysis import read_cache as read_analysis_cache
            analysis_cache = read_analysis_cache(state_root, project_id)
            if analysis_cache.get('correction') and analysis_cache.get('correction_history'):
                reviewed_dates.append(analysis_cache['correction_history'][-1]['date'])
        except (ValueError, OSError): pass
        analysis_value=((analysis_cache or {}).get('result') or {}).get('analysis') or {}
        notification_state = {
            'decision': {**{k:(analysis_value.get('brief') or {}).get(k,'') for k in ('stage','attention')}, **{k:analysis_value.get(k,'') for k in ('contact_boundary','execution_signal')}},
            'round': project_notifications.digest({k:v for k,v in current_round.items() if k not in ('saved_at', 'revision', 'request_id')}) if current_round is not None else None,
            'plan': project_notifications.digest({aid:{k:v for k,v in record.items() if k!='updated_at'} for aid,record in plan.get('actions', {}).items()}),
            'analysis': project_notifications.digest((analysis_cache.get('result') or {}).get('analysis', {})) if analysis_cache is not None else None,
            'correction': project_notifications.digest(analysis_cache.get('correction', '')) if analysis_cache is not None else None,
        }
        current_round = current_round or {}
        latest_evidence = max(evidence_dates, default='')
        future_commitment = bool(current_round.get('due') and current_round['due'] >= date.today().isoformat() and current_round.get('status') not in ('本轮完成', '暂停跟进') and current_round.get('action'))
        future_commitment = future_commitment or any(a['record'].get('due', '') >= date.today().isoformat() and a['record'].get('status') != '已完成' for a in actions)
        current = bool(latest_evidence and latest_evidence >= (date.today() - timedelta(days=30)).isoformat()) or future_commitment
        projects.append({"id": project_id, "title": title[1] if title else path.stem,
                         "customer": primary_customer,
                         "customer_link_evidence": {"path":source,"link":linked_customer['link']} if linked_customer else None,
                         "related_customers": explicit_related_customers(body,known_customers,source,primary_customer),
                         "updated_at": updated[1] if updated else "", "source_path": source,
                         "latest_evidence_date": latest_evidence, "is_current": current, "future_commitment": future_commitment,
                         "latest_review_date": max(reviewed_dates, default=''), "latest_recorded_at": current_round.get('saved_at', ''),
                         "freshness_reason": "保留未来明确节点" if future_commitment else "近30天有材料依据" if current else "历史材料待核实" if latest_evidence else "依据日期待核实",
                         "judgement": summary or "材料中尚未形成明确判断，请查看项目原文。",
                         "risks": risks, "sources": sources, "actions": actions,
                         "plan_revision": plan.get("revision", 0), "notification_state": notification_state,
                         "formal_status": "沿用客户登记事实；此页不自动认定商机阶段"})
    import project_archive
    result = project_archive.overlay(sorted(projects, key=lambda p: p["latest_evidence_date"], reverse=True), state_root, knowledge_root)
    if (state_root / "project_notifications" / "inbox.sqlite3").exists():
        project_notifications.observe_safely(result, state_root, observed)
    for project in result:
        project.pop("notification_state", None)
    return result

@project_archive.sales_write
def save_plan(payload, knowledge_root, state_root):
    with PLAN_LOCK:
        project = next((p for p in build_projects(knowledge_root, state_root) if p["id"] == payload.get("project_id")), None)
        if not project:
            raise ValueError("项目不存在，请刷新后重新选择")
        action = next((a for a in project["actions"] if a["id"] == payload.get("action_id")), None)
        if not action:
            raise ValueError("行动来源已变化，请刷新后重新确认")
        plan = read_plan(state_root, project["id"])
        if payload.get("revision") != plan.get("revision", 0):
            raise ValueError("计划已被更新，请刷新后重试，避免覆盖新记录")
        record = {key: str(payload.get(key, "")).strip()[:2000] for key in ("owner", "due", "status", "result")}
        if record["status"] not in ("待安排", "已联系待接受", "执行中", "等待反馈", "已完成"):
            raise ValueError("请选择有效的推进状态")
        if record["status"] == "已完成" and not record["result"]:
            raise ValueError("完成需要填写实际结果或确认依据，不能仅凭已发送标记完成")
        if record["due"]:
            datetime.strptime(record["due"], "%Y-%m-%d")
        record["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        plan.setdefault("actions", {})[action["id"]] = record
        plan["revision"] = plan.get("revision", 0) + 1
        folder = state_root / "project_plans"
        folder.mkdir(parents=True, exist_ok=True)
        # Keep append-only revisions as recovery evidence; atomically replace only current view.
        serialized = json.dumps(plan, ensure_ascii=False, indent=2)
        (folder / f"{project['id']}.r{plan['revision']}.json").write_text(serialized)
        temporary = folder / f"{project['id']}.tmp"
        temporary.write_text(serialized)
        temporary.replace(folder / f"{project['id']}.json")
        return {"ok": True, "revision": plan["revision"], "record": record}
