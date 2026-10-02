"""Local project-linked commercial drafts. No CRM writes and no mail sending."""
import json
import project_rounds
import quote_versions
import hashlib
import os
import tempfile
import threading
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from project_workspace import build_projects

LOCK = threading.Lock()
BUDGET_FIELDS = (
    ("own_labor", "自有人力预算金额"), ("pco", "PCO预算金额"),
    ("formal", "正式预算金额"), ("travel", "差旅预算金额"),
    ("procurement", "代采预算金额"), ("token", "Token预算金额"),
    ("presales", "售前预算金额"), ("other", "其他预算金额"),
)


class DraftConflict(ValueError):
    status = 409


def _text(value, limit=2000):
    if not isinstance(value, str):
        raise ValueError("文字字段格式不正确")
    return value.strip()[:limit]


def _decimal(value, label, places=2):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{label}需要填写非负数字")
    try:
        number = Decimal(str(value).strip() or "0")
    except InvalidOperation:
        raise ValueError(f"{label}需要填写非负数字") from None
    if not number.is_finite() or number < 0 or number > Decimal("100000000000"):
        raise ValueError(f"{label}需要填写合理的非负数字")
    precision = Decimal(1).scaleb(-places)
    if number != number.quantize(precision):
        raise ValueError(f"{label}最多保留{places}位小数")
    return number


def _number(value):
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else str(value)


def _money(value):
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _project(project_id, knowledge_root, state_root):
    project = next((p for p in build_projects(Path(knowledge_root), Path(state_root)) if p["id"] == project_id), None)
    if not project:
        raise ValueError("项目不存在或来源已变化，请重新选择项目")
    return project


def _path(state_root, project):
    return Path(state_root) / "commercial_drafts" / f"{project['id']}.json"


def _read(state_root, project):
    path = _path(state_root, project)
    if not path.exists():
        return {"project_id": project["id"], "project_source": project["source_path"], "revision": 0,
                "requirement": "", "effort": "", "rate": "", "budget": {},
                "customer_confirmed": False, "budget_verified": False,
                "confirmation_source": "", "confirmation_excerpt": "", "version": "", "sample": False}
    draft = json.loads(path.read_text(encoding="utf-8"))
    if draft.get("project_id") != project["id"] or draft.get("project_source") != project["source_path"]:
        raise ValueError("草稿与项目来源不一致，未加载或覆盖原记录")
    return draft


def _render(payload, project, knowledge_root, state_root, allow_stale_quote=False):
    working = project_rounds.read_round(project["id"], knowledge_root, state_root)["record"]
    contact_blocked = bool(working and working["relationship"] == "no_contact")
    effort = _decimal(payload.get("effort", ""), "客户人日", 6)
    rate = _decimal(payload.get("rate", ""), "对客单价")
    raw_budget = payload.get("budget", {})
    if not isinstance(raw_budget, dict) or set(raw_budget) - {key for key, _ in BUDGET_FIELDS}:
        raise ValueError("请使用模板中的八项预算成本")
    budget = {key: _decimal(raw_budget.get(key, ""), label) for key, label in BUDGET_FIELDS}
    draft = {key: _text(payload.get(key, "")) for key in (
        "requirement", "confirmation_source", "confirmation_excerpt", "version", "confirmation_fingerprint")}
    for key in ("customer_confirmed", "budget_verified", "sample", "self_cost_enabled"):
        if not isinstance(payload.get(key, False), bool):
            raise ValueError("确认标记格式不正确")
        draft[key] = payload.get(key, False)
    draft.update(project_id=project["id"], project_source=project["source_path"], effort=_number(effort),
                 rate=_number(rate), budget={key: _number(value) for key, value in budget.items()})
    revenue = (effort * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    base_cost = sum(budget.values(), Decimal("0"))
    self_cost = (revenue / 10).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) if draft['self_cost_enabled'] else Decimal(0)
    cost = base_cost + self_cost
    stale_quote = False
    latest_quote = None
    quote_id = payload.get('quote_id', '')
    if quote_id:
        try: quote = quote_versions.current(state_root, quote_id, payload.get('quote_revision'))
        except quote_versions.QuoteConflict as exc:
            if not allow_stale_quote: raise DraftConflict(str(exc)) from exc
            history = quote_versions.read(state_root, quote_id)
            revision = payload.get('quote_revision')
            if type(revision) is not int or not 1 <= revision <= history['revision']:
                raise DraftConflict(str(exc)) from exc
            quote = history['versions'][revision - 1]
            latest_quote = {**history['versions'][-1], 'quote_id': quote_id}
            stale_quote = True
        values = quote['values']
        if not quote_versions.customer_matches(values['customer'], project.get('customer', '')):
            raise ValueError('报价客户与所选项目不一致，请选择该客户项目或先核对报价客户名称')
        if (effort != Decimal(values['effort']) or rate != Decimal(values['rate']) or any(budget[k] != Decimal(values['costs'][k]) for k in budget)
                or draft['self_cost_enabled'] != values['selfCostEnabled'] or (values['requirement'] and draft['requirement'] != values['requirement'])
                or (values['version'] and draft['version'] != values['version'])):
            raise ValueError('本页金额或范围与关联报价不一致，请从计算器保存并带入新版报价')
        draft.update(quote_id=quote_id, quote_revision=payload['quote_revision'], quote_requirement=values['requirement'], quote_version_label=values['version'])
    profit = revenue - cost
    margin = (profit / revenue * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if revenue else None
    sources = {s["path"] for s in project.get("sources", []) if s.get("exists") and s["path"] != project["source_path"]}
    reasons = []
    if stale_quote:
        draft['customer_confirmed'] = False
        reasons.append('关联报价已有新版，请带入新版后核对；本页保留的是旧版输入')
    if draft["confirmation_source"] in sources:
        digest = hashlib.sha256()
        with (Path(knowledge_root) / draft["confirmation_source"]).open("rb") as handle:
            for block in iter(lambda: handle.read(65536), b""):
                digest.update(block)
        fingerprint = digest.hexdigest()
        if draft["confirmation_fingerprint"] and draft["confirmation_fingerprint"] != fingerprint:
            draft["customer_confirmed"] = False
            reasons.append("确认来源内容已变化，需重新核对客户确认")
        draft["confirmation_fingerprint"] = fingerprint
    if not draft["requirement"] or effort <= 0 or rate <= 0:
        reasons.append("需求名称、客户人日和对客单价待补齐")
    if not draft["customer_confirmed"]:
        reasons.append("尚未核实客户已完整确认本次需求和人日")
    if draft["confirmation_source"] not in sources or not draft["confirmation_excerpt"] or not draft["version"]:
        reasons.append("需要本项目真实关联的客户回复来源、确认原文和对应版本")
    if not draft["budget_verified"]:
        reasons.append("预算成本待核实；空白按0计算不代表已确认无成本")
    if draft["sample"]:
        reasons.append("当前为历史样例，仅供核对模板，不可用作新申请")
    ready = not reasons
    name = draft["requirement"] or "【需求名称待填写】"
    customer = "星海汽车" if "星海汽车" in project.get("customer", "") or "星海汽车" in project["title"] else project.get("customer", "客户")
    opening = "客户已完成工作量复核确认，最终工作量为" if ready else "本材料为待核实草稿，拟确认工作量为"
    internal = (f"@审批负责人，{customer}新增定制需求“{name}”，{opening}{_number(effort)}人日，"
                f"按{_money(rate)}元/人日计算，对客报价金额为{_money(revenue)}元。\n\n"
                f"项目预算成本：{_money(cost)}元\n毛利：{_money(profit)}元\n"
                f"毛利率：{str(margin) + '%' if margin is not None else '待计算'}\n\n成本明细：\n")
    if self_cost: internal += f"另计成交额10%自成本：{_money(self_cost)}元（已计入总成本，未计入下列八项预算）\n"
    internal += "\n".join(f"{label}：{_money(budget[key])}元" for key, label in BUDGET_FIELDS)
    internal += ("\n\n客户已确认人天，辛苦审批负责人审批报价申请、合同工单及提前启动工单～\n\n【随附本次客户邮件回复确认截图】"
                 if ready else "\n\n待核实草稿，暂不可作为已确认审批申请提交。\n待补齐：" + "；".join(reasons))
    # Construct independently: never reuse internal approval text or budget fields in customer mail.
    external = (f"您好，\n\n关于“{name}”，本次拟确认工作量为{_number(effort)}人日，"
                f"按{_money(rate)}元/人日计算，对客报价金额为{_money(revenue)}元。\n\n"
                "请核对本次需求范围及对应的工作量评估附件；如一致，烦请回复确认需求范围、人日及报价。"
                "如有调整，请在回复中说明，以便同步修订。\n\n谢谢。")
    return {"draft": draft, "calculation": {"revenue": _number(revenue), "budget_total": _number(cost),
            "gross_profit": _number(profit), "margin_percent": str(margin) if margin is not None else None},
            "approval_ready": ready, "blocking_reasons": reasons, "internal_approval": internal,
            "contact_blocked": contact_blocked,
            "stale_quote": stale_quote, "latest_quote": latest_quote,
            "customer_email": None if contact_blocked or stale_quote else {"subject": f"请确认：{name}工作量及报价", "body": external},
            "delivery_status": "仅本机草稿，未发送、未审批、未录入CRM"}


def preview_draft(payload, knowledge_root, state_root):
    if not isinstance(payload, dict):
        raise ValueError("草稿格式不正确")
    project = _project(payload.get("project_id"), knowledge_root, state_root)
    saved = _read(state_root, project)
    if 'revision' in payload and (type(payload['revision']) is not int or payload['revision'] != saved.get('revision', 0)):
        raise DraftConflict("已有更新的报价草稿；当前输入已保留，请重新加载后核对版本")
    return {"ok": True, **_render(payload, project, knowledge_root, state_root)}


def get_draft(project_id, knowledge_root, state_root):
    project = _project(project_id, knowledge_root, state_root)
    saved = _read(state_root, project)
    result = _render(saved, project, knowledge_root, state_root, allow_stale_quote=True)
    result["draft"].update(revision=saved.get("revision", 0), updated_at=saved.get("updated_at", ""))
    return {"ok": True, **result}


def save_draft(payload, knowledge_root, state_root):
    if not isinstance(payload, dict):
        raise ValueError("草稿格式不正确")
    with LOCK:
        project = _project(payload.get("project_id"), knowledge_root, state_root)
        current = _read(state_root, project)
        if type(payload.get("revision")) is not int or payload["revision"] != current.get("revision", 0):
            raise DraftConflict("草稿已被更新，请重新加载后再保存，避免覆盖新内容")
        result = _render(payload, project, knowledge_root, state_root)
        draft = result["draft"]
        draft.update(revision=current.get("revision", 0) + 1,
                     updated_at=datetime.now().astimezone().isoformat(timespec="seconds"))
        destination = _path(state_root, project)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            previous = destination.with_name(f"{project['id']}.r{current.get('revision', 0)}.json")
            if not previous.exists():
                with previous.open("x", encoding="utf-8") as archive:
                    json.dump(current, archive, ensure_ascii=False, indent=2)
                previous.chmod(0o600)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                             prefix=f".{project['id']}-", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(draft, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
        return {"ok": True, **result}
