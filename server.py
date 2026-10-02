#!/usr/bin/env python3
from __future__ import annotations

import project_notifications
import argparse
import html
import json
import os
import re
import shutil
import sqlite3
import ssl
import subprocess
import sys
import signal
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from zoneinfo import ZoneInfo
from project_workspace import build_projects, save_plan, read_source
from calendar_project_links import link_project_calendar_items
import quote_versions
import project_activity
import project_rounds
import k100_sync
import project_analysis
import legacy_crm_snapshot
import commercial
import discovery_handoff
import discovery_workspace
import material_library
import material_files
import public_signal_hub
import background_operations
import communication_jobs
import ai_hot
import project_crm
import project_archive
import local_resources
import workbench_agent


WORKSPACE_ROOT = Path(__file__).resolve().parent
# Captured at process import, so runtime verification cannot mistake edited disk files for loaded code.
import hashlib as _release_hash
RUNTIME_VERSION = {'release':'agent-workspace-20261001','loaded_at':datetime.now().astimezone().isoformat(),
                   'sources':{name:_release_hash.sha256((WORKSPACE_ROOT/name).read_bytes()).hexdigest()
                              for name in ('server.py','project_analysis.py','project_workspace.py','project_notifications.py','workbench_agent.py','material_library.py','material_files.py','material_receipts.py','communication_jobs.py','tools/communication_pipeline.py','tools/wechat_source.py','wechat-local/reader.py','wechat-local/file_originals.py','k100_sync.py','macos_keychain.py','legacy_crm_snapshot.py','background_operations.py')}}
HOME_ROOT = Path.home()
DEFAULT_OPEN_DESIGN_PROJECT_ROOT = (
    HOME_ROOT / "Library" / "Application Support" / "Open Design" / "namespaces" / "release-stable" / "data" / "projects"
)
DEFAULT_WORKBENCH_ROOT = Path(__file__).resolve().parent
DEFAULT_STATE_ROOT = HOME_ROOT / "Library" / "Application Support" / "SalesWorkbenchPublic"
CANONICAL_WORKBENCH_URL = "http://127.0.0.1:8766/"


def env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    return Path(raw).expanduser() if raw else default


def resolve_knowledge_root() -> Path:
    configured = os.environ.get("SALES_WORKBENCH_KNOWLEDGE_ROOT", "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            HOME_ROOT / "工作台用户销售知识库",
            HOME_ROOT / "工作台用户知识库",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


WORKBENCH_ROOT = env_path("SALES_WORKBENCH_WORKBENCH_ROOT", DEFAULT_WORKBENCH_ROOT)
STATE_ROOT = env_path("SALES_WORKBENCH_WORKBENCH_STATE_ROOT", DEFAULT_STATE_ROOT)
SALES_WORKBENCH_KNOWLEDGE_ROOT = resolve_knowledge_root()
CLIENT_REGISTRY = SALES_WORKBENCH_KNOWLEDGE_ROOT / "tracking" / "client_registry.md"
TODO_LOG = SALES_WORKBENCH_KNOWLEDGE_ROOT / "tracking" / "todo_log.md"
INTAKE_ROOT = SALES_WORKBENCH_KNOWLEDGE_ROOT / "tracking" / "intake"
REPORT_ROOT = SALES_WORKBENCH_KNOWLEDGE_ROOT / "tracking" / "reports"
WORKBENCH_DATA_ROOT = STATE_ROOT / "workbench_data"
RISK_RESOLUTION_ROOT = SALES_WORKBENCH_KNOWLEDGE_ROOT / "tracking" / "risk_resolutions"
RISK_EVIDENCE_ASSET_ROOT = SALES_WORKBENCH_KNOWLEDGE_ROOT / "raw" / "assets" / "risk_evidence"
RISK_TODO_FILE = WORKBENCH_DATA_ROOT / "risk_todos.json"
RISK_TODO_LOG = WORKBENCH_DATA_ROOT / "risk_todo_log.md"
WORKFLOW_RECEIPT_ROOT = WORKBENCH_DATA_ROOT / "workflow_receipts"
WORKFLOW_EVIDENCE_ASSET_ROOT = WORKBENCH_DATA_ROOT / "workflow_assets"
WORKFLOW_EVENT_ROOT = WORKBENCH_DATA_ROOT / "workflow_events"
WORKFLOW_RECEIPT_LOG = WORKBENCH_DATA_ROOT / "workflow_receipt_log.md"
TRANSCRIPT_ROOT = SALES_WORKBENCH_KNOWLEDGE_ROOT / "raw" / "transcripts"
STRUCTURED_ARTICLE_SOURCES = [
    (SALES_WORKBENCH_KNOWLEDGE_ROOT / "raw" / "articles" / "星海汽车权益平台" / "财经沟通", "星海汽车权益平台"),
    (SALES_WORKBENCH_KNOWLEDGE_ROOT / "raw" / "articles" / "星海汽车权益平台" / "权益中台", "星海汽车权益平台"),
    (SALES_WORKBENCH_KNOWLEDGE_ROOT / "raw" / "articles" / "星海汽车权益平台" / "商城", "星海汽车商城"),
    (SALES_WORKBENCH_KNOWLEDGE_ROOT / "raw" / "articles", None),
]
PM_DAILY_ROOT = WORKBENCH_DATA_ROOT / "pm_daily_reports"
PM_DAILY_RESOLUTION_ROOT = WORKBENCH_DATA_ROOT / "pm_daily_resolutions"
PM_DAILY_EVIDENCE_ASSET_ROOT = WORKBENCH_DATA_ROOT / "pm_daily_assets"
PM_DAILY_TODO_FILE = WORKBENCH_DATA_ROOT / "pm_daily_todos.json"
PM_DAILY_TODO_LOG = WORKBENCH_DATA_ROOT / "pm_daily_todo_log.md"
WORKFLOW_STATE_FILE = WORKBENCH_DATA_ROOT / "workflow_state.json"
FEISHU_CALENDAR_CACHE = WORKBENCH_DATA_ROOT / "feishu_calendar_cache.json"
EXTERNAL_SYNC_OUTBOX_FILE = WORKBENCH_DATA_ROOT / "external_sync_outbox.json"
FEISHU_REMINDER_DELIVERY_FILE = WORKBENCH_DATA_ROOT / "feishu_reminder_delivery.json"
LEGACY_PM_DAILY_ROOT = REPORT_ROOT / "pm_daily"
RAW_MESSAGE_CACHE_ROOT = WORKBENCH_DATA_ROOT / "raw_feishu_messages"
LEGACY_MESSAGE_ROOT = SALES_WORKBENCH_KNOWLEDGE_ROOT / "raw" / "feishu" / "messages"
MESSAGE_ROOT = RAW_MESSAGE_CACHE_ROOT
RULES_FILE = STATE_ROOT / "xiaowu_config" / "WORK_RULES.md"
RULE_OBS_FILE = STATE_ROOT / "xiaowu_memory" / "work_rule_observations.json"
FEISHU_API_ROOT = Path(os.environ.get("WORKBENCH_FEISHU_API_ROOT", str(HOME_ROOT / ".sales-workbench" / "feishu-api")))
LARK_CLI_BIN = os.environ.get("LARK_CLI_BIN") or "/opt/homebrew/bin/lark-cli"
FEISHU_REMINDER_CHAT_ID = os.environ.get(
    "FEISHU_REMINDER_CHAT_ID",
    "",
).strip()
# User confirmed opt-in, explicitly scheduled reminders on 2026-09-06.
# Eligibility is checked separately; overdue digests remain disabled even when forced.
FEISHU_REMINDER_ENABLED = os.environ.get("FEISHU_REMINDER_ENABLED", "0").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
FEISHU_OVERDUE_REMINDER_HOUR = max(
    0,
    min(23, int(os.environ.get("FEISHU_OVERDUE_REMINDER_HOUR", "9"))),
)
FEISHU_REMINDER_SCAN_SECONDS = max(
    30,
    int(os.environ.get("FEISHU_REMINDER_SCAN_SECONDS", "60")),
)
LARK_AUTH_ROOT = WORKBENCH_ROOT / "auth"
LARK_AUTH_STATE_FILE = STATE_ROOT / "lark_auth_state.json"
FXIAOKE_API_BASE = os.environ.get("FXIAOKE_API_BASE", "https://open.fxiaoke.com").rstrip("/")
FXIAOKE_MODE = os.environ.get("FXIAOKE_MODE", "page_snapshot").strip() or "page_snapshot"
FXIAOKE_TOKEN_CACHE = WORKBENCH_DATA_ROOT / ".fxiaoke_token_cache.json"
FXIAOKE_SYNC_CACHE = WORKBENCH_DATA_ROOT / "fxiaoke_sync_preview.json"
FXIAOKE_PAGE_SNAPSHOT_CACHE = WORKBENCH_DATA_ROOT / "fxiaoke_page_snapshot.json"
PROSPECTING_STATE_FILE = WORKBENCH_DATA_ROOT / "prospecting_automation.json"
PROSPECTING_REVENUE_CACHE_FILE = WORKBENCH_DATA_ROOT / "prospecting_revenue_cache.json"
CUSTOMER_INTEL_STATE_FILE = WORKBENCH_DATA_ROOT / "customer_intel_signals.json"
ACCOUNT_ADVANCEMENT_CACHE_FILE = WORKBENCH_DATA_ROOT / "account_advancement_cache.json"
ACCOUNT_STORE_FILE = WORKBENCH_DATA_ROOT / "sales_workbench.sqlite3"
UI_DIST_ROOT = WORKSPACE_ROOT / "dist"
ACCOUNT_ADVANCEMENT_BASE_TOKEN = os.environ.get("ACCOUNT_ADVANCEMENT_BASE_TOKEN", "")
ACCOUNT_ADVANCEMENT_CUSTOMER_TABLE_ID = os.environ.get("ACCOUNT_ADVANCEMENT_CUSTOMER_TABLE_ID", "")
ACCOUNT_ADVANCEMENT_CHANNEL_TABLE_ID = os.environ.get("ACCOUNT_ADVANCEMENT_CHANNEL_TABLE_ID", "")
ACCOUNT_ADVANCEMENT_CHANNEL_VIEW_ID = os.environ.get("ACCOUNT_ADVANCEMENT_CHANNEL_VIEW_ID", "")
PROSPECTING_QUERY_GROUPS = [
    {
        "id": "strategic_retail",
        "label": "战略零售",
        "reason": "业务平台适配场景：大型零售/消费/连锁集团的会员、私域、商城、门店和全渠道经营",
        "queries": [
            "连锁零售 会员 私域 O2O 门店 数字化",
            "上市公司 连锁门店 会员运营 小程序商城 私域",
        ],
    },
    {
        "id": "private_domain_growth",
        "label": "私域增长",
        "reason": "业务平台适配场景：消费品牌、车主运营、本地生活和会员复购体系",
        "queries": [
            "消费品牌 私域 会员运营 小程序商城 复购",
            "消费品牌 DTC 私域复购 全渠道 会员系统 上市",
        ],
    },
    {
        "id": "o2o_member_operation",
        "label": "O2O会员",
        "reason": "业务平台适配场景：线上线下一体化、门店核销、导购带客、会员权益和复购闭环",
        "queries": [
            "连锁门店 O2O 会员系统 小程序 招标 采购 报名截止 开标",
            "门店 导购 带客下单 企微 会员 小程序商城",
        ],
    },
    {
        "id": "ai_customer_operation",
        "label": "智能运营",
        "reason": "业务平台适配场景：企微助手、智能客服、AI 导购、内容营销和客户运营",
        "queries": [
            "零售品牌 AI导购 智能客服 会员运营 私域",
            "连锁门店 企业微信 智能客服 私域 会员运营",
        ],
    },
    {
        "id": "youzan_procurement",
        "label": "招采采购",
        "reason": "业务平台适配场景：CRM、SCRM、会员、商城、私域、智能客服、企微助手或营销系统采购",
        "queries": [
            "CRM SCRM 会员系统 私域 招标 采购 连锁 响应截止",
            "小程序商城 会员运营 智能客服 供应商征集 采购公告 开标",
        ],
    },
    {
        "id": "supplier_entry",
        "label": "供应商路径",
        "reason": "破局场景：查客户现有软件厂商、系统集成商、营销服务商和竞品服务商，判断合作带入或替换切口",
        "queries": [
            "零售 消费品牌 会员系统 中标 供应商 客户运营",
            "连锁品牌 数字化 服务商 SCRM CDP 企微 中标",
        ],
    },
]
PROSPECTING_QUERIES = [query for group in PROSPECTING_QUERY_GROUPS for query in group["queries"]]
PROSPECTING_KEYWORDS = (
    "上市",
    "招采",
    "采购",
    "招标",
    "中标",
    "采购公告",
    "供应商征集",
    "系统替换",
    "CRM",
    "SCRM",
    "CDP",
    "私域",
    "会员",
    "会员系统",
    "积分",
    "权益",
    "权益兑换",
    "积分商城",
    "订单履约",
    "数字化",
    "AI",
    "智能客服",
    "企微",
    "企业微信",
    "导购",
    "O2O",
    "零售",
    "连锁",
    "门店",
    "电商",
    "本地生活",
    "小程序",
    "小程序商城",
)
YOUZAN_FIT_KEYWORDS = (
    "CRM",
    "SCRM",
    "CDP",
    "新零售",
    "零售",
    "连锁",
    "门店",
    "导购",
    "私域",
    "会员",
    "会员系统",
    "会员运营",
    "积分",
    "积分商城",
    "权益",
    "权益兑换",
    "兑换",
    "履约",
    "订单履约",
    "车主权益",
    "客户运营",
    "营销自动化",
    "企业微信",
    "企微",
    "社交电商",
    "小程序",
    "小程序商城",
    "商城",
    "O2O",
    "全渠道",
    "复购",
    "电商",
    "DTC",
    "品牌",
    "本地生活",
    "餐饮",
    "茶饮",
    "美业",
    "医美",
    "宠物",
    "教育",
    "文旅",
    "酒店",
    "运动场馆",
    "健身",
    "母婴",
    "服饰",
    "美妆",
    "食品",
    "白酒",
    "商超",
    "百货",
    "购物中心",
    "AI导购",
    "AI客服",
    "智能客服",
    "内容营销",
)
PROSPECTING_MISMATCH_KEYWORDS = (
    "基金",
    "期货",
    "证券",
    "银行",
    "保险",
    "信托",
    "政府",
    "委员会",
    "事业单位",
    "政务",
    "高校",
    "研究院",
    "医院信息化",
    "纯ERP",
    "业务平台产品中心",
    "产品中心",
    "帮助中心",
    "腾讯企点官网",
    "企点营销云",
    "企业营销平台",
    "美团智能掌柜",
    "每个商家",
)
PROSPECTING_YOUZAN_EXISTING_CASE_MARKERS = (
    "业务平台新零售",
    "业务平台案例",
    "业务平台商家",
    "与业务平台合作",
    "和业务平台合作",
    "业务平台战略合作",
    "业务平台赋能",
    "使用业务平台",
    "携手业务平台",
    "找业务平台",
    "业务平台美业",
    "业务平台微商城",
)
PROSPECTING_EXISTING_CUSTOMER_FILTER_BUCKETS = {"active", "reference", "excluded"}
PROSPECTING_EXISTING_CUSTOMER_EXCEPTION_KEYWORDS = (
    "断约",
    "解约",
    "停止合作",
    "终止合作",
    "重新合作",
    "重启合作",
    "恢复合作",
    "复签",
    "更换系统",
    "替换系统",
    "换供应商",
    "重新招标",
    "重启项目",
)
KNOWN_YOUZAN_PROSPECT_BRANDS = (
    "星巴克",
    "无印良品",
    "美团",
    "饿了么",
    "瑞幸",
    "Kappa",
    "爱乐活",
    "柠季",
    "毛戈平",
    "袁记",
    "伊利",
    "丝域养发",
    "鸣鸣很忙",
    "示例食品集团",
    "青岳酒业",
    "丽雅",
    "恩施荟",
    "昆明供销",
    "蜜雪冰城",
    "茶百道",
    "奈雪",
    "绝味",
    "周黑鸭",
    "老乡鸡",
    "锅圈",
    "百果园",
    "美宜佳",
    "天虹",
    "蒙牛",
    "自然堂",
    "彭世修脚",
    "吉乐屋",
    "东阿阿胶",
    "良品铺子",
    "来伊份",
    "三只松鼠",
    "孩子王",
    "都市丽人",
    "名创优品",
    "屈臣氏",
    "永辉",
    "大润发",
    "红旗连锁",
    "云杉百货",
    "王府井",
    "周大福",
    "老凤祥",
    "珀莱雅",
    "上海家化",
    "贝泰妮",
    "安踏",
    "李宁",
    "特步",
    "海澜之家",
    "太平鸟",
    "森马",
    "大参林",
    "老百姓",
    "益丰",
    "一心堂",
    "松果宠物",
    "松叶",
    "宠物家",
    "小麦公社",
    "泡泡玛特",
    "百胜中国",
    "易宠科技",
    "海底捞",
    "霸王茶姬",
    "古茗",
    "沪上阿姨",
)
PROSPECTING_RECENT_SIGNAL_DAYS = 21
PROSPECTING_STALE_SIGNAL_DAYS = 30
PROSPECTING_PREP_WINDOW_MIN_DAYS = 14
PROSPECTING_PREP_WINDOW_MAX_DAYS = 30
PROSPECTING_VISIBLE_CANDIDATE_LIMIT = 3
PROSPECTING_VISIBLE_WATCH_LIMIT = 20
ZLBX_API_BASE = "https://mcp-server.zhiliaobiaoxun.com/api_v2"
ZLBX_CONFIG_FILE = HOME_ROOT / ".zlbx" / "config.json"
ZLBX_RECENT_SEARCH_DAYS = 21
ZLBX_DETAIL_LIMIT = 4
ZLBX_MANUAL_COOLDOWN_MINUTES = 10
ZLBX_TENDER_KEYWORDS = (
    "会员系统",
    "会员平台",
    "CRM",
    "SCRM",
    "CDP",
    "私域",
    "小程序商城",
    "企业微信",
    "客户运营",
    "数字营销",
    "即时零售",
)
ZLBX_EXCLUDE_KEYWORDS = ("物业", "保安", "食堂", "维修", "耗材", "制服", "印刷")
ZLBX_HARD_MISMATCH_MARKERS = (
    "医院",
    "学校",
    "学院",
    "大学",
    "政府",
    "公安",
    "法院",
    "检察院",
    "研究所",
    "银行",
    "证券",
    "基金",
    "期货",
    "保险",
    "信托",
    "电信",
    "联通",
    "移动",
    "军工",
)
ZLBX_CLOSED_NOTICE_MARKERS = (
    "中标结果",
    "成交结果",
    "中选结果",
    "成交公告",
    "中标公告",
    "候选人公示",
    "结果公示",
)
PROSPECTING_SCAN_LOCK = threading.Lock()
PROSPECTING_EXCLUDED_COMPANIES = {
    "美团",
    "饿了么",
    "阿里",
    "腾讯",
    "京东",
    "抖音",
}

PROJECT_CHATS = json.loads(os.environ.get("WORKBENCH_PROJECT_CHATS_JSON", "[]"))
SYNC_STATE_FILE = WORKBENCH_DATA_ROOT / "raw_feishu_sync_state.json"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
ACTIONABLE_SCHEDULE_WINDOW_MINUTES = 60
ACCOUNT_STORE_LOCK = threading.RLock()
ACCOUNT_STORE_INITIALIZED = False
EVIDENCE_SUBMISSION_LOCK = threading.RLock()
STATE_FILE_LOCK = threading.RLock()
PROSPECTING_STATE_LOCK = threading.RLock()
MESSAGE_SYNC_LOCK = threading.RLock()
LARK_AUTH_LOCK = threading.RLock()
FEISHU_REMINDER_DELIVERY_LOCK = threading.RLock()
FEISHU_CALENDAR_READ_LOCK = threading.RLock()
FEISHU_CALENDAR_READ_JOBS = {}
FEISHU_CALENDAR_READ_RETRY_SECONDS = 30
WORKBENCH_OUTCOME_STATUSES = {"已处理", "待客户反馈", "待内部支持", "推进中"}


@dataclass
class CustomerRecord:
    bucket: str
    name: str
    status: str
    owner: str
    note: str


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    except OSError:
        return ""


def write_private_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    os.replace(temporary, path)


def write_private_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(value, encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    os.replace(temporary, path)


def read_json_file(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError:
        return fallback


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def safe_filename(value: str, fallback: str = "untitled") -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", value.strip(), flags=re.UNICODE).strip("-._")
    return cleaned[:80] or fallback


def parse_markdown_table(section_text: str, bucket: str) -> list[CustomerRecord]:
    records: list[CustomerRecord] = []
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        if "---" in line or ("客户" in line and "备注" in line):
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if parts and not parts[0] and len(parts) > 1 and parts[1]:
            parts = parts[1:]
        if not parts or not parts[0] or parts[0] == "客户":
            continue
        if bucket == "active":
            name, status, owner, note = (parts + ["", "", "", ""])[:4]
        else:
            name = parts[0]
            status = parts[1] if len(parts) > 1 else ""
            owner = ""
            note = parts[2] if len(parts) > 2 else ""
        records.append(CustomerRecord(bucket=bucket, name=name, status=status, owner=owner, note=note))
    return records


def parse_client_registry() -> dict[str, list[dict]]:
    text = read_text(CLIENT_REGISTRY)
    sections = {
        "active": "## 🟢 活跃跟进",
        "potential": "## 🟡 潜在目标",
        "reference": "## 🔵 参考案例",
        "excluded": "## ⛔ 已排除",
    }
    parsed: dict[str, list[dict]] = {key: [] for key in sections}
    ordered = list(sections.items())
    for index, (key, marker) in enumerate(ordered):
        start = text.find(marker)
        if start == -1:
            continue
        end = len(text)
        for _, next_marker in ordered[index + 1 :]:
            next_pos = text.find(next_marker, start + len(marker))
            if next_pos != -1:
                end = min(end, next_pos)
        parsed[key] = [asdict(item) for item in parse_markdown_table(text[start:end], key)]
    return parsed


def fxiaoke_config_status() -> dict:
    config = {
        "api_base": FXIAOKE_API_BASE,
        "app_id": os.environ.get("FXIAOKE_APP_ID", "").strip(),
        "app_secret": os.environ.get("FXIAOKE_APP_SECRET", "").strip(),
        "permanent_code": os.environ.get("FXIAOKE_PERMANENT_CODE", "").strip(),
        "current_open_user_id": os.environ.get("FXIAOKE_CURRENT_OPEN_USER_ID", "").strip(),
        "user_mobile": os.environ.get("FXIAOKE_USER_MOBILE", "").strip(),
    }
    missing = []
    for key, label in (
        ("app_id", "FXIAOKE_APP_ID"),
        ("app_secret", "FXIAOKE_APP_SECRET"),
        ("permanent_code", "FXIAOKE_PERMANENT_CODE"),
    ):
        if not config[key]:
            missing.append(label)
    if not config["current_open_user_id"] and not config["user_mobile"]:
        missing.append("FXIAOKE_CURRENT_OPEN_USER_ID 或 FXIAOKE_USER_MOBILE")
    return {
        "configured": not missing,
        "missing": missing,
        "api_base": config["api_base"],
        "has_app_id": bool(config["app_id"]),
        "has_app_secret": bool(config["app_secret"]),
        "has_permanent_code": bool(config["permanent_code"]),
        "has_current_open_user_id": bool(config["current_open_user_id"]),
        "has_user_mobile": bool(config["user_mobile"]),
    }


def fxiaoke_post(path: str, payload: dict, timeout: int = 20) -> dict:
    url = f"{FXIAOKE_API_BASE}{path}"
    if "thirdTraceId=" not in url:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}thirdTraceId={uuid.uuid4().hex}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"分享销客接口 HTTP {exc.code}：{detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"分享销客接口连接失败：{exc.reason}") from exc
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"分享销客接口返回不是 JSON：{raw[:160]}") from exc
    if result.get("errorCode") not in (0, "0", None):
        message = result.get("errorMessage") or result.get("errorDescription") or "未知错误"
        raise RuntimeError(f"分享销客接口失败：{message}")
    return result


def fxiaoke_access_context() -> dict:
    status = fxiaoke_config_status()
    if not status["configured"]:
        raise RuntimeError("分享销客 API 未配置：" + "、".join(status["missing"]))

    now = int(time.time())
    cache = read_json_file(FXIAOKE_TOKEN_CACHE, {})
    env_app_id = os.environ.get("FXIAOKE_APP_ID", "").strip()
    current_open_user_id = os.environ.get("FXIAOKE_CURRENT_OPEN_USER_ID", "").strip() or cache.get("currentOpenUserId", "")
    if (
        cache.get("appId") == env_app_id
        and cache.get("corpAccessToken")
        and cache.get("corpId")
        and cache.get("expiresAt", 0) > now + 180
    ):
        if current_open_user_id:
            return {
                "corpAccessToken": cache["corpAccessToken"],
                "corpId": cache["corpId"],
                "currentOpenUserId": current_open_user_id,
                "expiresAt": cache["expiresAt"],
                "fromCache": True,
            }

    token_result = fxiaoke_post(
        "/cgi/corpAccessToken/get/V2",
        {
            "appId": env_app_id,
            "appSecret": os.environ.get("FXIAOKE_APP_SECRET", "").strip(),
            "permanentCode": os.environ.get("FXIAOKE_PERMANENT_CODE", "").strip(),
        },
    )
    corp_token = token_result.get("corpAccessToken", "")
    corp_id = token_result.get("corpId", "")
    expires_at = now + int(token_result.get("expiresIn") or 7200)
    if not corp_token or not corp_id:
        raise RuntimeError("分享销客授权成功但未返回 corpAccessToken/corpId")

    if not current_open_user_id:
        mobile = os.environ.get("FXIAOKE_USER_MOBILE", "").strip()
        user_result = fxiaoke_post(
            "/cgi/user/getByMobile",
            {"corpAccessToken": corp_token, "corpId": corp_id, "mobile": mobile},
        )
        employees = user_result.get("empList") or []
        if not employees:
            raise RuntimeError("未通过手机号找到分享销客员工 openUserId")
        current_open_user_id = employees[0].get("openUserId", "")
    if not current_open_user_id:
        raise RuntimeError("分享销客 currentOpenUserId 为空")

    write_private_json(
        FXIAOKE_TOKEN_CACHE,
        {
            "appId": env_app_id,
            "corpAccessToken": corp_token,
            "corpId": corp_id,
            "currentOpenUserId": current_open_user_id,
            "expiresAt": expires_at,
            "updatedAt": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
        },
    )
    return {
        "corpAccessToken": corp_token,
        "corpId": corp_id,
        "currentOpenUserId": current_open_user_id,
        "expiresAt": expires_at,
        "fromCache": False,
    }


def fxiaoke_query_object(api_name: str, field_projection: list[str], limit: int = 20, offset: int = 0) -> dict:
    context = fxiaoke_access_context()
    return fxiaoke_post(
        "/cgi/crm/v2/data/query",
        {
            "corpAccessToken": context["corpAccessToken"],
            "corpId": context["corpId"],
            "currentOpenUserId": context["currentOpenUserId"],
            "includeNull": True,
            "data": {
                "dataObjectApiName": api_name,
                "find_explicit_total_num": True,
                "search_query_info": {
                    "offset": offset,
                    "limit": min(max(limit, 1), 100),
                    "orders": [{"fieldName": "create_time", "isAsc": False}],
                    "filters": [],
                    "fieldProjection": field_projection,
                },
            },
        },
    )


def normalize_fxiaoke_records(result: dict, limit: int = 20) -> list[dict]:
    data = result.get("data")
    if isinstance(data, dict):
        candidates = data.get("dataList") or data.get("list") or data.get("records") or data.get("objects")
    else:
        candidates = data
    if isinstance(candidates, dict):
        candidates = list(candidates.values())
    if not isinstance(candidates, list):
        candidates = []
    normalized = []
    for item in candidates[:limit]:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "id": item.get("_id") or item.get("id") or "",
                "name": item.get("name") or item.get("account_name") or item.get("opportunity_name") or "",
                "create_time": item.get("create_time"),
                "last_modified_time": item.get("last_modified_time"),
            }
        )
    return normalized


def fxiaoke_page_snapshot_payload(refresh: bool = False) -> dict:
    cache = read_json_file(FXIAOKE_PAGE_SNAPSHOT_CACHE, {})
    registry = parse_client_registry()
    cached_quarter = cache.get("quarter") or {}
    cached_preview = cache.get("preview") or {}
    has_quarter_snapshot = any(
        str(cached_quarter.get(field, "")).strip() not in {"", "--", "待读取"}
        for field in ("target_amount", "achieved_amount", "attainment_rate", "gap_amount")
    )
    has_preview_snapshot = bool((cached_preview.get("accounts") or []) or (cached_preview.get("opportunities") or []))
    capture_status = "captured" if cache.get("synced_at") and (has_quarter_snapshot or has_preview_snapshot) else "waiting_for_visible_page"
    fallback_accounts = [
        {
            "name": item.get("name", ""),
            "status": item.get("status", ""),
            "create_time": "",
        }
        for item in registry.get("active", [])
        if item.get("name")
    ][:20]
    payload = {
        "ok": True,
        "mode": "page_snapshot",
        "configured": True,
        "capture_status": capture_status,
        "source_label": cache.get("source_label", "分享销客页面快照"),
        "dashboard": cache.get("dashboard", "销售数据统计"),
        "last_sync": cache.get("synced_at", ""),
        "quarter": cache.get(
            "quarter",
            {
                "target_amount": "待读取",
                "achieved_amount": "待读取",
                "attainment_rate": "--",
                "period": "本季度",
                "gap_amount": "待读取",
            },
        ),
        "pipeline": cache.get("pipeline", {}),
        "counts": cache.get("counts", {"accounts": len(fallback_accounts), "opportunities": 0}),
        "preview": cache.get(
            "preview",
            {
                "accounts": fallback_accounts,
                "opportunities": [],
            },
        ),
        "snapshot_note": cache.get(
            "snapshot_note",
            (
                "当前采用页面快照模式：只读取分享销客「销售数据统计」里的季度目标、签约额和完成率；"
                "客户签约明细需要穿透后单独补充，不使用 CRM 阶段还原过程管理。"
            ),
        ),
        "operator_hint": "打开纷享销客数据驾驶舱或签约订单页后，由小吴读取 Chrome 可见页面并写入快照；如果目标完成驾驶舱被隐藏，不用 0 值覆盖上次可见目标。",
        "refresh_requested_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds") if refresh else "",
    }
    return payload


def fxiaoke_status_payload() -> dict:
    if FXIAOKE_MODE != "api":
        return fxiaoke_page_snapshot_payload()
    status = fxiaoke_config_status()
    cache = read_json_file(FXIAOKE_SYNC_CACHE, {})
    token_cache = read_json_file(FXIAOKE_TOKEN_CACHE, {})
    return {
        "ok": True,
        "configured": status["configured"],
        "missing": status["missing"],
        "api_base": status["api_base"],
        "credential_state": {
            "app_id": "已配置" if status["has_app_id"] else "未配置",
            "app_secret": "已配置" if status["has_app_secret"] else "未配置",
            "permanent_code": "已配置" if status["has_permanent_code"] else "未配置",
            "open_user": "已配置" if status["has_current_open_user_id"] or status["has_user_mobile"] else "未配置",
        },
        "token_cached": bool(token_cache.get("corpAccessToken") and token_cache.get("expiresAt", 0) > int(time.time())),
        "last_sync": cache.get("synced_at", ""),
        "counts": cache.get("counts", {"accounts": 0, "opportunities": 0}),
        "preview": cache.get("preview", {"accounts": [], "opportunities": []}),
    }


def fxiaoke_sync_preview() -> dict:
    if FXIAOKE_MODE != "api":
        return fxiaoke_page_snapshot_payload(refresh=True)
    accounts = fxiaoke_query_object("AccountObj", ["_id", "name", "create_time"], limit=20)
    opportunities = fxiaoke_query_object("OpportunityObj", ["_id", "name", "create_time"], limit=20)
    preview = {
        "accounts": normalize_fxiaoke_records(accounts),
        "opportunities": normalize_fxiaoke_records(opportunities),
    }
    payload = {
        "synced_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
        "counts": {key: len(value) for key, value in preview.items()},
        "preview": preview,
        "sources": [
            "https://developer.fxiaoke.com/openapi_v2/object/CustomersAndContacts/AccountObj/query-acc.html",
            "https://developer.fxiaoke.com/openapi_v2/object/OpportunitiesAndLeads/OpportunityObj/query.html",
            "https://open.fxiaoke.com/cgi/corpAccessToken/get/V2",
        ],
    }
    write_private_json(FXIAOKE_SYNC_CACHE, payload)
    return {"ok": True, **payload}


def parse_todo_log() -> dict[str, list[str]]:
    text = read_text(TODO_LOG)
    pending: list[str] = []
    completed: list[str] = []
    target: list[str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("### 待进行"):
            target = pending
            continue
        if line.startswith("### 已完成"):
            target = completed
            continue
        if line.startswith("### "):
            target = None
            continue
        if target is not None and line.startswith("- "):
            target.append(line[2:].strip())
    return {"pending": pending, "completed": completed}


def list_recent_notes(root: Path, limit: int = 8) -> list[dict]:
    if not root.exists():
        return []
    items = sorted(
        [path for path in root.rglob("*.md") if path.is_file()],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    results = []
    for path in items[:limit]:
        rel = path.relative_to(SALES_WORKBENCH_KNOWLEDGE_ROOT)
        results.append(
            {
                "name": path.stem,
                "path": str(rel),
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                "preview": read_text(path)[:260].strip(),
            }
        )
    return results


PROJECT_PATTERNS = [
    ("星海汽车权益平台", ("权益平台", "权益中台", "数字资产中台", "财经中台", "积分抵现", "积分", "抵现", "权益")),
    (
        "星海汽车商城",
        (
            "星海汽车商城",
            "示例汽车集团商城",
            "APP原生商城",
            "分享裂变",
            "人群包",
            "抽奖",
            "一期合同内",
            "一期合同范围",
            "一期范围",
            "一期变更",
            "一期新增",
            "二期营销",
            "二期新增",
            "营销线上化",
            "剩余人天",
            "采购单价",
            "框架报价",
            "框架合同",
            "O2O",
            "三期",
            "新增需求SOW",
            "盖章流程",
        ),
    ),
    ("山岚酒业", ("山岚酒业",)),
    ("清源健康健康", ("清源健康", "清源健康健康", "清源健康制药", "清源皮肤")),
    ("云杉百货", ("云杉百货", "云杉")),
    ("远航汽车", ("远航汽车",)),
    ("松果宠物", ("松果宠物", "松叶", "松叶宠物")),
    ("晨曦机车", ("晨曦机车", "晨曦", "DEMO_MOTO")),
    ("晴川乳业", ("晴川乳业", "晴川")),
    ("示例新能源汽车", ("示例新能源", "示例新能源汽车")),
]


NON_WENJIE_PROJECT_PATTERNS = [
    ("示例酒品牌", ("示例酒品牌",)),
    ("青岳酒业", ("青岳酒业",)),
    ("橙田食品", ("橙田食品",)),
    ("示例美妆", ("示例美妆",)),
    ("麦田食品", ("麦田", "麦穗百万餐饮")),
    ("山岚酒业", ("山岚酒业",)),
    ("清源健康健康", ("清源健康", "清源健康健康", "清源健康制药", "清源皮肤")),
    ("云杉百货", ("云杉百货", "云杉")),
    ("远航汽车", ("远航汽车",)),
    ("松果宠物", ("松果宠物", "松叶", "松叶宠物")),
    ("晨曦机车", ("晨曦机车", "晨曦", "DEMO_MOTO")),
    ("晴川乳业", ("晴川乳业", "晴川")),
    ("示例新能源汽车", ("示例新能源", "示例新能源汽车")),
]


WENJIE_CONTEXT_KEYWORDS = (
    "星海汽车",
    "示例汽车集团",
    "DEMO_AUTO",
    "星海汽车商城",
    "示例汽车集团商城",
    "星海汽车录音",
    "星海汽车项目",
)


PROJECT_LINK_LABELS = {
    "星海汽车商城": "星海汽车商城",
    "星海汽车商城一期交付": "星海汽车商城",
    "星海汽车商城二期营销升级": "星海汽车商城",
    "星海汽车商城APP原生适配": "星海汽车商城",
    "星海汽车商城压测限流": "星海汽车商城",
    "星海汽车权益平台": "星海汽车权益平台",
    "星海汽车数字资产中台": "星海汽车权益平台",
    "示例汽车集团": "星海汽车商城",
    "示例汽车集团汽车": "星海汽车商城",
    "松果宠物": "松果宠物",
    "松果宠物宠物": "松果宠物",
    "清源健康健康": "清源健康健康",
    "云杉百货": "云杉百货",
    "远航汽车": "远航汽车",
    "晨曦机车": "晨曦机车",
    "山岚酒业": "山岚酒业",
}


def project_labels_from_wikilinks(text: str) -> list[str]:
    labels: list[str] = []
    for match in re.findall(r"\[\[([^\]|#]+)", text):
        name = Path(match.strip()).name
        label = PROJECT_LINK_LABELS.get(name)
        if not label:
            explicit = explicit_non_wenjie_labels(name)
            label = explicit[0] if len(explicit) == 1 else None
        if label:
            labels.append(label)
    return list(dict.fromkeys(labels))


def project_name_from_wikilink(value: str) -> str:
    name = Path(value.strip()).name
    return name


def transcript_direction_index() -> dict[str, dict]:
    if not TRANSCRIPT_ROOT.exists():
        return {}
    index: dict[str, dict] = {}
    for path in TRANSCRIPT_ROOT.rglob("00_*索引.md"):
        text = read_text(path)
        if "结构化整理" not in text or "合并判断" not in text:
            continue
        index_title = markdown_display_title(text, path.stem)
        direction_summary = clean_markdown_line(section_body(text, ("合并判断",)))
        sections = list(re.finditer(r"^###\s+(.+)$", text, flags=re.MULTILINE))
        for section_index, match in enumerate(sections):
            section_title = clean_markdown_line(match.group(1))
            start = match.end()
            end = sections[section_index + 1].start() if section_index + 1 < len(sections) else len(text)
            section = text[start:end]
            structured = re.search(r"结构化整理：`([^`]+)`", section)
            if not structured:
                continue
            project_match = re.search(r"归属项目：\[\[([^\]]+)\]\]", section)
            project_title = project_name_from_wikilink(project_match.group(1)) if project_match else ""
            rel_path = structured.group(1).strip()
            topic = re.sub(r"^\d{1,2}:\d{2}\s+", "", section_title).strip()
            index[rel_path] = {
                "knowledge_direction": project_title or clean_markdown_line(index_title),
                "knowledge_direction_title": project_title or clean_markdown_line(index_title),
                "knowledge_direction_summary": direction_summary,
                "knowledge_topic": topic,
                "knowledge_index_path": str(path.relative_to(SALES_WORKBENCH_KNOWLEDGE_ROOT)),
            }
    return index


def has_wenjie_context(text: str) -> bool:
    return any(keyword in text for keyword in WENJIE_CONTEXT_KEYWORDS)


def explicit_non_wenjie_labels(text: str) -> list[str]:
    labels = []
    for project, keywords in NON_WENJIE_PROJECT_PATTERNS:
        if any(keyword in text for keyword in keywords):
            labels.append(project)
    return list(dict.fromkeys(labels))


def infer_project_label(*parts: str) -> str:
    titleish = " ".join(part for part in parts[:2] if part)
    haystack = " ".join(part for part in parts if part)
    for project, keywords in NON_WENJIE_PROJECT_PATTERNS:
        if any(keyword in titleish for keyword in keywords):
            return project
    if has_wenjie_context(haystack) and any(keyword in titleish for keyword in ("权益平台", "权益中台", "积分抵现", "权益", "数字资产中台", "财经中台", "示例协调人")):
        return "星海汽车权益平台"
    if has_wenjie_context(haystack) and any(
        keyword in titleish
        for keyword in (
            "星海汽车商城",
            "示例汽车集团商城",
            "商城APP",
            "APP改造",
            "APP原生商城",
            "一期合同内",
            "一期合同范围",
            "一期范围",
            "一期变更",
            "一期新增",
            "二期营销",
            "二期新增",
            "营销线上化",
            "采购单价",
            "框架报价",
            "框架合同",
            "O2O",
            "三期",
            "新增需求SOW",
        )
    ):
        return "星海汽车商城"
    for project, keywords in PROJECT_PATTERNS:
        if project.startswith("星海汽车") and not has_wenjie_context(haystack):
            continue
        if any(keyword in haystack for keyword in keywords):
            return project
    if any(keyword in haystack for keyword in ("示例联系人", "项目经理", "需求池", "合同范围", "二期")) and has_wenjie_context(haystack):
        return "星海汽车商城"
    if any(keyword in haystack for keyword in ("示例汽车集团", "星海汽车")):
        return "星海汽车商城"
    return "未归类"


def infer_project_labels(*parts: str) -> list[str]:
    titleish = " ".join(part for part in parts[:3] if part)
    haystack = " ".join(part for part in parts if part)
    title_labels = explicit_non_wenjie_labels(titleish)
    if title_labels and not has_wenjie_context(titleish):
        return title_labels
    labels = []
    for project, keywords in PROJECT_PATTERNS:
        if project.startswith("星海汽车") and not has_wenjie_context(haystack):
            continue
        if any(keyword in haystack for keyword in keywords):
            labels.append(project)
    if any(keyword in haystack for keyword in ("示例联系人", "项目经理", "需求池", "合同范围", "二期")) and has_wenjie_context(haystack):
        labels.append("星海汽车商城")
    if any(keyword in haystack for keyword in ("示例汽车集团", "星海汽车")) and not any(label.startswith("星海汽车") for label in labels):
        labels.append("星海汽车商城")
    return list(dict.fromkeys(labels)) or ["未归类"]


def is_structured_transcript(text: str) -> bool:
    if "发生了什么" not in text:
        return False
    return any(
        marker in text
        for marker in (
            "按时间戳整理",
            "时间戳整理",
            "后续待办/待确认",
            "后续待办",
            "建议动作",
            "下一步",
            "关键结论",
            "商务判断",
        )
    )


def extract_named_section(text: str, start_marker: str, end_markers: tuple[str, ...]) -> str:
    start = text.find(start_marker)
    if start == -1:
        return ""
    start += len(start_marker)
    end = len(text)
    for marker in end_markers:
        pos = text.find(marker, start)
        if pos != -1:
            end = min(end, pos)
    return text[start:end].strip()


def extract_bullets(section: str, limit: int = 6) -> list[str]:
    bullets = []
    for line in section.splitlines():
        clean = line.strip()
        if clean.startswith("- "):
            bullets.append(clean[2:].strip())
        elif clean.startswith(("1. ", "2. ", "3. ", "4. ", "5. ")):
            bullets.append(clean[3:].strip())
    return bullets[:limit]


def extract_metadata_field(text: str, field_name: str) -> str:
    match = re.search(rf"^{re.escape(field_name)}：(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def parse_recorded_timestamp(text: str) -> float | None:
    recorded_at = extract_metadata_field(text, "录制时间")
    if not recorded_at:
        return None
    match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", recorded_at)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return None


def transcript_business_title(text: str, fallback: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("#").strip()
        if not line:
            continue
        if line.startswith(("原始录音", "录制时间", "录音时长", "知识库路径", "整理说明", "转写质量")):
            continue
        return compact_text(line, 48)
    return fallback


def build_note_preview(text: str, limit: int = 220) -> str:
    lines: list[str] = []
    in_frontmatter = False
    saw_content = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "---" and not saw_content:
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue
        saw_content = True
        if line.startswith(("#", "> 来源", "> 抓取时间", "原始录音", "录制时间", "录音时长", "知识库路径")):
            continue
        lines.append(clean_markdown_line(line))
        if len(" ".join(lines)) >= limit:
            break
    return compact_text(" ".join(lines), limit)


def markdown_display_title(text: str, fallback: str) -> str:
    frontmatter_title = re.search(r"^title:\s*[\"']?(.+?)[\"']?\s*$", text, flags=re.MULTILINE)
    if frontmatter_title:
        return compact_text(frontmatter_title.group(1).strip(), 52)
    heading = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    if heading:
        return compact_text(heading.group(1).strip(), 52)
    clean = re.sub(r"^\d{8}_?", "", fallback)
    clean = clean.replace("_", " ").replace("+", " + ")
    return compact_text(clean, 52)


def parse_knowledge_timestamp(path: Path, text: str, type_label: str) -> float:
    if type_label == "录音整理":
        recorded = parse_recorded_timestamp(text)
        if recorded:
            return recorded
    if type_label == "推进记录":
        file_stamp = re.search(r"_(\d{8})-(\d{6})$", path.stem)
        if file_stamp:
            try:
                return datetime.strptime(f"{file_stamp.group(1)}-{file_stamp.group(2)}", "%Y%m%d-%H%M%S").timestamp()
            except ValueError:
                pass
        body_stamp = re.search(r"发生时间\*\*[:：]\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})", text)
        if body_stamp:
            try:
                return datetime.fromisoformat(f"{body_stamp.group(1)}T{body_stamp.group(2)}").timestamp()
            except ValueError:
                pass
    for value in (
        re.search(r"(\d{4})(\d{2})(\d{2})", path.stem),
        re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", text),
    ):
        if not value:
            continue
        try:
            return datetime(int(value.group(1)), int(value.group(2)), int(value.group(3)), 9, 0).timestamp()
        except ValueError:
            continue
    return path.stat().st_mtime


def section_body(text: str, keywords: tuple[str, ...]) -> str:
    lines = text.splitlines()
    capture = False
    capture_level = 0
    captured: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            if capture and level <= capture_level:
                break
            if not capture and any(keyword in heading.group(2) for keyword in keywords):
                capture = True
                capture_level = level
                continue
            if capture:
                captured.append(raw_line)
            continue
        if capture:
            captured.append(raw_line)
    return "\n".join(captured).strip()


def first_section_body(text: str, keyword_groups: tuple[tuple[str, ...], ...]) -> str:
    for keywords in keyword_groups:
        section = section_body(text, keywords)
        if section:
            return section
    return ""


def digest_points(section: str, limit: int = 4) -> list[str]:
    bullets = extract_bullets(section, limit=limit)
    if bullets:
        cleaned_bullets = [clean_markdown_line(item) for item in bullets]
        return [
            item
            for item in cleaned_bullets
            if item and item not in {"业务平台侧", "客户侧", "云杉百货侧", "华为侧", "星海汽车侧", "参与人列表（去重）"}
        ][:limit]
    points: list[str] = []
    for raw_line in section.splitlines():
        line = clean_markdown_line(raw_line)
        if not line or line.startswith(("|", "---", "来源", "原始文件")):
            continue
        if line in {"业务平台侧", "客户侧", "云杉百货侧", "华为侧", "星海汽车侧", "参与人列表（去重）"}:
            continue
        if len(line) < 8:
            continue
        points.append(line)
        if len(points) >= limit:
            break
    return points


def clean_markdown_block(text: str) -> str:
    blocks: list[str] = []
    current: list[str] = []
    for raw_line in text.splitlines():
        line = clean_markdown_line(raw_line)
        if not line or line in {"业务平台侧", "客户侧", "云杉百货侧", "华为侧", "星海汽车侧", "参与人列表（去重）"}:
            if current:
                blocks.append(" ".join(current).strip())
                current = []
            continue
        if line.startswith("|") or line == "---":
            continue
        current.append(line)
    if current:
        blocks.append(" ".join(current).strip())
    return "\n\n".join(block for block in blocks if block).strip()


def full_content_from_markdown(text: str) -> str:
    skip_headings = ("基本信息", "来源", "关联", "原始", "元数据")
    lines: list[str] = []
    capture = True
    in_frontmatter = False
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            title = heading.group(2).strip()
            capture = not any(keyword in title for keyword in skip_headings)
            if capture:
                clean_heading = clean_markdown_line(title)
                if clean_heading:
                    lines.append("")
                    lines.append(clean_heading)
            continue
        if not capture:
            continue
        clean = clean_markdown_line(raw_line)
        if not clean:
            lines.append("")
            continue
        if clean.startswith(("项目线：", "沟通主题：", "沟通日期：", "原始转写：", "知识库路径：", "录音时长：", "录制时间：")):
            continue
        lines.append(clean)
    return "\n".join(lines).strip()


def clean_markdown_line(text: str) -> str:
    clean = re.sub(r"\^\[[^\]]+\]", "", text)
    clean = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda match: match.group(2) or match.group(1).split("/")[-1], clean)
    clean = re.sub(r"`([^`]+)`", r"\1", clean)
    clean = re.sub(r"^\s*[-*>#]+\s*", "", clean.strip())
    clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", clean)
    clean = clean.replace("**", "")
    return " ".join(clean.split())


def build_structured_digest(text: str) -> dict:
    summary_section = first_section_body(
        text,
        (
            ("当前判断", "当前销售判断", "核心判断", "核心结论", "沟通结论", "达成的决策", "核心事件", "客户核心需求", "项目背景"),
            ("总结", "会议概述", "决策结论", "AI建设全景概览"),
            ("最新进展", "沟通路径", "这次沟通", "项目路径", "定位", "当前金额"),
            ("沟通脉络", "核心主题", "关键要点"),
        ),
    )
    signal_section = section_body(
        text,
        (
            "关键信号",
            "关键信息",
            "当前销售判断",
            "核心发现",
            "关键局势",
            "已确认事实",
            "双方共识",
            "关键升级",
            "关注点",
            "重点大项",
            "关键讨论点",
            "关键要点",
            "业务平台方展示内容",
        ),
    )
    risk_section = section_body(text, ("风险", "卡点", "关键矛盾", "主要矛盾", "待验证", "客户疑虑", "客户核心痛点"))
    action_section = section_body(text, ("下一步", "建议动作", "待办", "后续安排", "使用建议", "应对策略", "承诺的后续动作"))
    summary = ""
    candidates = digest_points(summary_section, limit=3)
    useful_candidates = [
        candidate
        for candidate in candidates
        if "raw/" not in candidate
        and "原始" not in candidate
        and not candidate.startswith(("来源", "时长", "截图路径", "会议时间", "会议主题", "参与人", "日期范围"))
    ]
    preferred = [
        candidate
        for candidate in useful_candidates
        if any(keyword in candidate for keyword in ("判断", "客户", "项目", "本次", "核心", "机会", "风险", "推进", "阶段", "需求", "沟通"))
    ]
    for candidate in preferred or useful_candidates:
        summary = candidate
        break
    if not summary and candidates:
        summary = next((candidate for candidate in candidates if "raw/" not in candidate), candidates[0])
    return {
        "summary": summary,
        "full_summary": full_content_from_markdown(text) or clean_markdown_block(summary_section),
        "signals": digest_points(signal_section, limit=12),
        "risks": digest_points(risk_section, limit=12),
        "actions": digest_points(action_section, limit=16),
    }


def is_workbench_article(path: Path) -> bool:
    if path.suffix.lower() not in {".md", ".txt"}:
        return False
    name = path.name
    excluded = (
        "_文本",
        "对比稿",
        "Wiki.json",
        "产品方案集合",
        "方案集合",
        "投标文件",
        "合同SOW文件",
        "需求建议书",
        "招标文件",
        "原始转写",
        "feishu_docx",
        "pipeline_",
    )
    if any(marker in name for marker in excluded):
        return False
    text = read_text(path)
    structured_markers = (
        "## 总结",
        "## 会议概述",
        "## 核心主题",
        "## 核心结论",
        "## 核心判断",
        "## 客户核心需求",
        "## 关键信息",
        "## 沟通结论",
        "## 核心发现",
        "## 关键讨论点",
        "## 关键要点",
        "## 决策结论",
        "## AI建设全景概览",
        "## 风险",
        "## 风险与卡点",
        "## 下一步",
        "## 工作台用户承诺的后续动作",
        "## 建议动作",
        "## 待办",
        "## 定位",
    )
    return any(marker in text for marker in structured_markers)


def build_transcript_digest(text: str) -> dict:
    summary = first_section_body(
        text,
        (
            ("发生了什么", "会议概述", "本次沟通"),
            ("商务判断", "关键结论"),
        ),
    )
    judgement = first_section_body(
        text,
        (
            ("当前销售判断", "商务判断", "关键结论", "核心判断"),
            ("O2O 闭环核心判断", "客户明确提出的三大挑战", "新需求与产品能力方向"),
        ),
    )
    timeline_section = section_body(text, ("按时间戳整理", "时间戳整理", "时间线"))
    action_section = section_body(text, ("后续待办/待确认", "后续待办", "建议动作", "下一步"))
    risk_section = section_body(text, ("风险", "待确认", "风险与待确认", "风险与卡点"))
    timeline = extract_bullets(timeline_section, limit=5)
    actions = extract_bullets(action_section, limit=5)
    risks = extract_bullets(risk_section, limit=12) or [
        item
        for item in [*timeline, *actions]
        if any(keyword in item for keyword in ("风险", "超出", "待确认", "不明确", "不能", "无法", "影响", "资源", "人天", "排期"))
    ][:4]
    full_summary = full_content_from_markdown(text)
    return {
        "summary": compact_text(summary, 180) if summary else "",
        "full_summary": full_summary,
        "timeline": timeline,
        "actions": actions,
        "risks": risks,
        "duration": extract_metadata_field(text, "录音时长"),
    }


def knowledge_item(
    path: Path,
    type_label: str,
    title: str | None = None,
    project_override: str | None = None,
    direction_map: dict[str, dict] | None = None,
) -> dict:
    stat = path.stat()
    rel = path.relative_to(SALES_WORKBENCH_KNOWLEDGE_ROOT)
    text = read_text(path)
    preview = build_note_preview(text)
    item_title = title or path.stem
    is_transcript = type_label == "录音整理"
    display_type = "沟通沉淀" if is_transcript else type_label
    transcript_digest = build_transcript_digest(text) if is_transcript else {}
    structured_digest = build_structured_digest(text) if not is_transcript else {}
    display_title = transcript_business_title(text, item_title) if is_transcript else markdown_display_title(text, item_title)
    timestamp = parse_knowledge_timestamp(path, text, type_label)
    if transcript_digest.get("summary"):
        preview = transcript_digest["summary"]
    if structured_digest.get("summary"):
        preview = structured_digest["summary"]
    linked_projects = project_labels_from_wikilinks(text)
    project = project_override or (linked_projects[0] if linked_projects else infer_project_label(display_title, item_title, str(rel), preview))
    projects = [project_override] if project_override else (linked_projects or infer_project_labels(display_title, item_title, str(rel), preview))
    direction = (direction_map or {}).get(str(rel), {})
    return {
        "type": display_type,
        "title": display_title,
        "raw_title": item_title,
        "project": project,
        "projects": projects,
        "path": str(rel),
        "updated_at": datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M"),
        "timestamp": timestamp,
        "preview": preview or "暂无预览",
        "source_note": "已整理沉淀 / 工作台用户知识库",
        **transcript_digest,
        **structured_digest,
        **direction,
    }


def dated_project_section_items(path: Path) -> list[dict]:
    text = read_text(path)
    rel = path.relative_to(SALES_WORKBENCH_KNOWLEDGE_ROOT)
    project_title = markdown_display_title(text, path.stem)
    headings = list(re.finditer(r"^#{2,4}\s+(.+?(20\d{2}-\d{2}-\d{2}).*)$", text, flags=re.MULTILINE))
    items: list[dict] = []
    for index, match in enumerate(headings):
        heading = clean_markdown_line(match.group(1))
        start = match.start()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section_text = text[start:end].strip()
        digest = build_structured_digest(section_text)
        preview = digest.get("summary") or build_note_preview(section_text, 220)
        try:
            timestamp = datetime.fromisoformat(f"{match.group(2)}T09:00:00").timestamp()
        except ValueError:
            timestamp = path.stat().st_mtime
        title = f"{project_title} · {heading}"
        project = infer_project_label(title, path.stem, str(rel), preview, section_text)
        items.append(
            {
                "type": "项目沉淀",
                "title": compact_text(title, 64),
                "raw_title": path.stem,
                "project": project,
                "projects": infer_project_labels(title, path.stem, str(rel), preview, section_text),
                "path": str(rel),
                "updated_at": datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M"),
                "timestamp": timestamp,
                "preview": preview or "暂无预览",
                "source_note": "项目页日期沉淀 / 工作台用户知识库",
                **digest,
            }
        )
    return items


def build_knowledge_timeline(limit: int = 160) -> list[dict]:
    items: list[dict] = []
    seen_article_paths: set[Path] = set()
    raw_articles_root = SALES_WORKBENCH_KNOWLEDGE_ROOT / "raw" / "articles"
    direction_map = transcript_direction_index()
    sources = [
        (SALES_WORKBENCH_KNOWLEDGE_ROOT / "projects", "项目沉淀", None),
        (INTAKE_ROOT, "沟通入库", None),
        (REPORT_ROOT, "分析报告", None),
        (TRANSCRIPT_ROOT, "录音整理", None),
    ]
    sources.extend((root, "沟通沉淀", project) for root, project in STRUCTURED_ARTICLE_SOURCES)
    for root, type_label, project_override in sources:
        if not root.exists():
            continue
        source_paths = [root] if root.is_file() else root.rglob("*")
        for path in source_paths:
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".json"}:
                continue
            resolved_path = path.resolve()
            if type_label == "沟通沉淀":
                if resolved_path in seen_article_paths:
                    continue
                seen_article_paths.add(resolved_path)
            if type_label == "沟通沉淀" and not is_workbench_article(path):
                continue
            if root == TRANSCRIPT_ROOT and (path.suffix.lower() == ".json" or "_whisper_json" in path.parts):
                continue
            if root == TRANSCRIPT_ROOT and path.name.startswith("00_"):
                continue
            if root == TRANSCRIPT_ROOT:
                transcript_text = read_text(path)
                if not is_structured_transcript(transcript_text):
                    continue
            if (PM_DAILY_ROOT in path.parents or LEGACY_PM_DAILY_ROOT in path.parents) and type_label == "分析报告":
                continue
            if type_label == "分析报告" and "客户追踪周报" in path.name:
                continue
            title = path.stem
            if root == SALES_WORKBENCH_KNOWLEDGE_ROOT / "projects":
                section_items = dated_project_section_items(path)
                if section_items:
                    items.extend(section_items)
                    continue
            item = knowledge_item(path, type_label, title, project_override, direction_map)
            if type_label == "沟通沉淀" and project_override is None and raw_articles_root == root and item.get("project") == "未归类":
                continue
            if type_label == "PM日报":
                date_match = re.match(r"(\d{4}-\d{2}-\d{2})_PM日报", path.stem)
                if date_match:
                    report_dt = datetime.fromisoformat(f"{date_match.group(1)}T23:59:00")
                    item["updated_at"] = report_dt.strftime("%Y-%m-%d %H:%M")
                    item["timestamp"] = report_dt.timestamp()
            items.append(item)

    items.sort(key=lambda item: item["timestamp"], reverse=True)
    return [{key: value for key, value in item.items() if key != "timestamp"} for item in items[:limit]]


def parse_work_rules() -> dict[str, list[str]]:
    text = read_text(RULES_FILE)
    low: list[str] = []
    high: list[str] = []
    target: list[str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## 低风险习惯"):
            target = low
            continue
        if line.startswith("## 高风险业务规则"):
            target = high
            continue
        if line.startswith("## "):
            target = None
            continue
        if target is not None and line.startswith("- "):
            target.append(line[2:].strip())
    return {"low": low, "high": high}


def get_rule_candidates(threshold: int = 2) -> list[dict]:
    payload = read_json_file(RULE_OBS_FILE, {})
    if not isinstance(payload, dict):
        return []
    items = []
    for obs in payload.get("observations", {}).values():
        if obs.get("approved") or obs.get("count", 0) < threshold:
            continue
        items.append(
            {
                "rule_key": obs.get("rule_key"),
                "count": obs.get("count"),
                "risk": obs.get("risk"),
                "scope": obs.get("scope"),
                "text": obs.get("candidate_text"),
                "candidate_text": obs.get("candidate_text"),
            }
        )
    items.sort(key=lambda item: (-item["count"], item["rule_key"]))
    return items


def customer_aliases(customer_name: str) -> list[str]:
    if customer_name == "星海汽车商城":
        return [
            "星海汽车商城",
            "示例汽车集团商城",
            "APP原生商城",
            "二期营销",
            "营销线上化",
            "分享裂变",
        ]
    if customer_name == "星海汽车权益平台":
        return [
            "星海汽车权益平台",
            "权益平台",
            "财经",
            "权益中台",
            "数字资产中台",
            "积分",
            "抵现",
        ]
    aliases = [part.strip(" ）)(") for part in re.split(r"[/（(]", customer_name) if part.strip(" ）)(")]
    aliases.append(customer_name)
    alias_map = {
        "示例汽车集团": ["星海汽车", "权益平台", "APP原生商城"],
        "星海汽车": ["示例汽车集团", "权益平台", "APP原生商城"],
        "清源健康": ["清源健康健康", "清源健康制药", "清源皮肤皮肤", "清源皮肤"],
        "云杉百货": ["云杉", "云杉集团"],
        "晨曦机车": ["晨曦", "DEMO_MOTO"],
        "松果宠物": ["松果宠物宠物", "松叶", "松叶宠物", "松叶宠物（独立体系）"],
        "松果宠物宠物": ["松果宠物", "松叶", "松叶宠物", "松叶宠物（独立体系）"],
        "松叶宠物": ["松果宠物", "松果宠物宠物", "松叶"],
    }
    base_text = " ".join(aliases)
    for key, extra_aliases in alias_map.items():
        if key in base_text:
            aliases.extend(extra_aliases)
    for suffix in ("健康", "制药", "集团", "汽车", "宠物"):
        for alias in list(aliases):
            if alias.endswith(suffix) and len(alias) > len(suffix):
                aliases.append(alias[: -len(suffix)])
    return list(dict.fromkeys(aliases))


def display_customer_name(value: str) -> str:
    text = str(value or "").strip()
    if text in {"松果宠物", "松叶", "松叶宠物", "松叶宠物（独立体系）"}:
        return "松果宠物宠物"
    return text


def display_customer_text(value: str) -> str:
    text = str(value or "")
    replacements = (
        ("松叶宠物（独立体系）", "松果宠物宠物"),
        ("松叶宠物", "松果宠物宠物"),
        ("松果宠物 ·", "松果宠物宠物 ·"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


DISPLAY_TEXT_KEYS = {
    "customer",
    "customer_label",
    "name",
    "title",
    "action",
    "next_step",
    "risk",
    "signal",
    "task",
    "recommendation",
    "stage",
    "label",
}


def normalize_display_names(value):
    if isinstance(value, list):
        return [normalize_display_names(item) for item in value]
    if isinstance(value, dict):
        normalized = {}
        for key, item in value.items():
            if key in {"customer", "name"}:
                normalized[key] = display_customer_name(str(item))
            elif key in DISPLAY_TEXT_KEYS and isinstance(item, str):
                normalized[key] = display_customer_text(item)
            else:
                normalized[key] = normalize_display_names(item)
        return normalized
    return value


def customer_todos(customer_name: str, todos: dict[str, list[str]]) -> list[str]:
    aliases = customer_aliases(customer_name)
    return [item for item in todos.get("pending", []) if any(alias in item for alias in aliases)]


def infer_customer_strategy(record: dict, todos: dict[str, list[str]]) -> dict:
    actions = customer_todos(record.get("name", ""), todos)
    return {"priority": "P2", "stage": record.get("status") or "待判断", "next_action": actions[0] if actions else "核对最新沟通，确认下一步", "risk": "以已关联材料为准，未确认信息保持待核验", "signal": record.get("note") or "尚无已核验信息", "amount": "", "source": "local records"}


def split_wenjie_projects(record: dict, todos: dict[str, list[str]]) -> list[dict]:
    # Public distribution never seeds customer-specific project facts.
    return [{**record, **infer_customer_strategy(record, todos), "todos": customer_todos(record.get("name", ""), todos)}]


def build_deal_board(customers: dict[str, list[dict]], todos: dict[str, list[str]]) -> list[dict]:
    board = []
    for bucket in ("active", "potential"):
        for record in customers.get(bucket, []):
            if bucket == "active" and record.get("name") == "示例汽车集团/星海汽车":
                board.extend(split_wenjie_projects(record, todos))
                continue
            board.append({**record, **infer_customer_strategy(record, todos), "todos": customer_todos(record["name"], todos)})
    priority_rank = {"P0": 0, "P1": 1, "P2": 2}
    board.sort(key=lambda item: (priority_rank.get(item.get("priority"), 9), item.get("name", "")))
    return board


def customers_for_workbench(customers: dict[str, list[dict]], todos: dict[str, list[str]]) -> dict[str, list[dict]]:
    ui_customers = {key: list(value) for key, value in customers.items()}
    active: list[dict] = []
    for record in customers.get("active", []):
        if record.get("name") == "示例汽车集团/星海汽车":
            for project in split_wenjie_projects(record, todos):
                active.append(
                    {
                        "bucket": "active",
                        "name": project["name"],
                        "status": project["status"],
                        "owner": project["owner"],
                        "note": project["note"],
                    }
                )
            continue
        active.append(record)
    ui_customers["active"] = active
    return ui_customers


def build_battle_actions(deal_board: list[dict], todos: dict[str, list[str]], schedule_items: list[dict] | None = None) -> list[dict]:
    due_followups = build_due_followup_actions(schedule_items or [])
    actions = [
        {
            "account_id": item.get("account_id") or "",
            "customer": item["name"],
            "bucket": item.get("bucket", "active"),
            "priority": item["priority"],
            "stage": item["stage"],
            "action": item["next_action"],
            "risk": item["risk"],
            "signal": item["signal"],
        }
        for item in deal_board
        if item.get("bucket") == "active"
    ]
    actions = [action for action in actions if not should_suppress_battle_action(action)]
    generic_todos = []
    for todo in todos.get("pending", []):
        if not any(any(alias in todo for alias in customer_aliases(action["customer"])) for action in actions):
            generic_todos.append(todo)
    for todo in generic_todos[:3]:
        actions.append(
            {
                "customer": "通用待办",
                "priority": "P2",
                "stage": "待处理",
                "action": todo,
                "risk": "来自 todo_log，尚未绑定到客户",
                "signal": "手工待办",
            }
        )
    actions = [action for action in actions if not should_suppress_battle_action(action)]
    return [*due_followups, *actions][:10]


def sales_brain_public_signals_for_customer(customer_name: str, intel_state: dict | None = None) -> list[dict]:
    state = intel_state or load_customer_intel_state()
    customers = state.get("customers") if isinstance(state.get("customers"), dict) else {}
    matched_name = customer_intel_match_name(customer_name)
    record = customers.get(matched_name) or customers.get(customer_name)
    if not record:
        record = next((candidate for name, candidate in customers.items()
                       if public_signal_hub.same_customer(customer_name, name, public_signal_hub.identity_aliases)), None)
    signals = record.get("signals", []) if isinstance(record, dict) and isinstance(record.get("signals"), list) else []
    return signals[:5]


def sales_brain_item_reason(item: dict) -> str:
    priority = item.get("priority") or "P2"
    stage = item.get("stage") or "待处理"
    signal = item.get("signal") or item.get("risk") or "来自客户推进状态"
    if str(item.get("action", "")).startswith("到点跟进") or "超时" in str(item.get("risk", "")):
        return "时间已到或已超时，需要先确认本轮是否继续推进。"
    if priority == "P0":
        return "P0 客户事项，直接影响当前交付、回款或增购窗口。"
    if "待反馈" in stage or "反馈" in signal:
        return "上一轮已经推进，现在需要检查客户或内部反馈。"
    return compact_text(signal, 92)


def sales_brain_exit_hint(item: dict) -> str:
    action = str(item.get("action") or item.get("next_step") or "")
    if "客户反馈" in action:
        return "提交反馈结果；未反馈则顺延 Deadline"
    if "内部支持" in action:
        return "提交内部进展；未完成则顺延 Deadline"
    if "沟通提取" in action:
        return "确认是否变成正式待办"
    return "提交回执：闭环 / 待客户反馈 / 待内部支持 / 继续推进"


def build_sales_brain_payload(
    deal_board: list[dict],
    battle_actions: list[dict],
    calendar_status: dict,
    fxiaoke_status: dict,
    prospecting: dict,
    message_digest: dict,
    knowledge_timeline: list[dict],
) -> dict:
    intel_state = load_customer_intel_state()
    public_signal_count = sum(
        len(record.get("signals", []))
        for record in (intel_state.get("customers") or {}).values()
        if isinstance(record, dict)
    )
    prospecting_summary = prospecting.get("summary") or {}
    prospecting_pending = int(prospecting_summary.get("pending_count", 0) or 0) + int(prospecting_summary.get("verify_count", 0) or 0)
    latest_report = (message_digest.get("days") or [{}])[0] if message_digest.get("days") else {}
    quarter = fxiaoke_status.get("quarter") or {}
    calendar_items = calendar_status.get("items") if isinstance(calendar_status.get("items"), list) else []

    today_queue = []
    for item in battle_actions[:6]:
        today_queue.append({
            "customer": item.get("customer") or "待匹配事项",
            "action": item.get("action") or item.get("next_step") or "待处理",
            "why_today": sales_brain_item_reason(item),
            "target": item.get("risk") or item.get("signal") or "完成本轮判断并提交回执",
            "source": item.get("source_label") or item.get("signal") or item.get("stage") or "客户推进状态",
            "exit": sales_brain_exit_hint(item),
            "destination": "客户作战室 -> 回执 -> Deadline/经营地图",
        })

    operating_maps = []
    for item in deal_board[:8]:
        signals = sales_brain_public_signals_for_customer(item.get("name", ""), intel_state)
        supplier_signals = [
            signal for signal in signals
            if "供应商" in str(signal.get("signal_type", "")) or "供应商" in str(signal.get("impact_judgment", ""))
        ]
        operating_maps.append({
            "customer": item.get("name"),
            "project_lines": [item.get("stage") or item.get("status") or "当前项目线"],
            "budget": item.get("amount") or "预算待确认",
            "key_people": item.get("owner") or "关键人待补齐",
            "supplier_path": supplier_signals[0].get("impact_judgment") if supplier_signals else "供应商/竞品路径待补齐",
            "next_play": item.get("next_action") or "等待下一步动作",
            "public_signal_count": len(signals),
        })

    tomorrow_plan = []
    for item in calendar_items:
        if len(tomorrow_plan) >= 3:
            break
        bucket = str(item.get("schedule_bucket") or "")
        if bucket in {"tomorrow", "upcoming", "future"} or item.get("deadline"):
            tomorrow_plan.append({
                "title": item.get("title") or item.get("next_step") or "检查下一次跟进",
                "customer": item.get("customer") or "待匹配事项",
                "prepare": item.get("next_step") or "提前准备沟通目标、现状证据和下一步选项",
                "trigger": item.get("deadline") or item.get("time_label") or item.get("countdown_label") or "下一次提醒",
            })
    for item in battle_actions:
        if len(tomorrow_plan) >= 3:
            break
        tomorrow_plan.append({
            "title": item.get("action") or "客户推进",
            "customer": item.get("customer") or "待匹配事项",
            "prepare": "如果今天未闭环，明天先检查反馈并补证据。",
            "trigger": "今天回执结果",
        })
    judgment_buckets = [
        {
            "type": "今日动作",
            "count": len(battle_actions),
            "meaning": "需要今天处理、到点或超时的事项。",
            "destination": "首页队列 -> 客户作战室",
        },
        {
            "type": "客户经营地图更新",
            "count": sum(item.get("public_signal_count", 0) for item in operating_maps) + len(knowledge_timeline[:8]),
            "meaning": "改变客户长期判断，但不一定今天处理。",
            "destination": "客户作战室 -> 经营地图",
        },
        {
            "type": "情报观察",
            "count": int(prospecting_pending or 0) + public_signal_count,
            "meaning": "值得看，但没有直接变成待办。",
            "destination": "战略雷达 / 客户新闻",
        },
        {
            "type": "经营判断",
            "count": 1 if quarter else 0,
            "meaning": f"目标 {quarter.get('target_amount', '待读取')} / 已签约 {quarter.get('achieved_amount', '待读取')} / 缺口 {quarter.get('gap_amount', '待读取')}",
            "destination": "业绩快照",
        },
        {
            "type": "只读背景",
            "count": len(latest_report.get("items", [])) if latest_report else 0,
            "meaning": "项目群日报只读，不自动生成待办。",
            "destination": "项目群日报",
        },
    ]

    ten_steps = [
        {"step": "1 收集信号", "status": "已接入", "detail": "录音/TXT、手动捕捉、CRM、日程、公开新闻、招投标、知识库。"},
        {"step": "2 过滤边界", "status": "已接入", "detail": "日报只读；业绩只经营判断；新闻和战略雷达不自动进待办。"},
        {"step": "3 识别对象", "status": "已接入", "detail": "信号会绑定到客户、项目线或新客户候选。"},
        {"step": "4 判断价值", "status": "本次补齐", "detail": "统一判为今日动作、经营地图更新、情报观察、经营判断、只读背景。"},
        {"step": "5 今日队列", "status": "本次补齐", "detail": "每条今日动作补充为什么今天处理、目标、出口和去向。"},
        {"step": "6 客户作战室", "status": "已接入", "detail": "核心点击进入客户作战室；全局模块独立显示。"},
        {"step": "7 提交回执", "status": "已接入", "detail": "处理后写回执，区分闭环、待反馈、待内部支持、继续推进。"},
        {"step": "8 下次触发", "status": "已接入", "detail": "未闭环进入 Deadline，到点后回到今日队列。"},
        {"step": "9 经营地图", "status": "本次补齐", "detail": "客户项目线、预算、关键人、供应商路径和下一步打法聚合到客户地图。"},
        {"step": "10 明日预案", "status": "本次补齐", "detail": "只按 Deadline 和今日未闭环动作生成准备项；AI 候选及升级替换机会不进入执行预案。"},
    ]

    return {
        "ten_steps": ten_steps,
        "judgment_buckets": judgment_buckets,
        "today_queue": today_queue,
        "customer_maps": operating_maps,
        "tomorrow_plan": tomorrow_plan[:3],
    }


def build_due_followup_actions(schedule_items: list[dict]) -> list[dict]:
    output: list[dict] = []
    for item in schedule_items:
        if item.get("sales_suppressed"): continue
        source_type = str(item.get("source_type") or item.get("source_scope") or "")
        if source_type == "feishu_calendar" and not item.get("matched_customer"):
            continue
        bucket = str(item.get("schedule_bucket", ""))
        minutes_left = item.get("minutes_left")
        try:
            minutes_left_value = int(minutes_left) if minutes_left is not None else None
        except (TypeError, ValueError):
            minutes_left_value = None
        status = str(item.get("status", ""))
        transcript_candidate = source_type == "transcript_intake" and status == "待确认"
        actionable_now = transcript_candidate or bucket == "overdue" or (
            bucket == "today"
            and minutes_left_value is not None
            and minutes_left_value <= ACTIONABLE_SCHEDULE_WINDOW_MINUTES
        )
        if not actionable_now:
            continue
        if status in {"已闭环", "已处理", "已回填", "已忽略"}:
            continue
        customer = str(item.get("customer") or "待匹配事项")
        title = str(item.get("title") or item.get("next_step") or "待跟进")
        next_step = str(item.get("next_step") or title)
        if status == "待客户反馈":
            action_label = f"检查客户反馈：{title}"
            risk_label = "上次已推进，现在需要确认客户是否反馈；若仍未反馈，提交继续等待的证据并顺延下一次检查。"
        elif status == "待内部支持":
            action_label = f"检查内部支持：{title}"
            risk_label = "上次需要内部支持，现在需要确认内部是否已推进；未完成则提交当前进展并顺延下一次检查。"
        elif source_type == "feishu_calendar" and status == "待会后回填":
            action_label = f"会后回填：{title}"
            risk_label = "这是已匹配客户的飞书会议，会议已结束；需要回填结论，并决定是否生成下一步 Deadline。"
        elif source_type == "feishu_calendar" and bucket == "overdue":
            action_label = f"进行中确认：{title}"
            risk_label = "这是已匹配客户且已经开始的飞书日程；确认当前进展，并在结束后回填结论。"
        elif source_type == "feishu_calendar":
            action_label = f"会前确认：{title}"
            risk_label = "这是已匹配客户的飞书会议；会前确认目标、风险和会后需要锁定的下一步。"
        else:
            action_label = f"到点跟进：{title}"
            risk_label = f"这条提醒已到点，当前状态：{status or '待跟进'}。"
        if source_type == "transcript_intake":
            candidate_count = item.get("transcript_candidate_count")
            action_label = f"确认录音候选：{title}"
            risk_label = (
                "来自近期录音/TXT整理的一条候选动作；确认是否进入正式行动、安排下次，或只保留为知识背景。"
            ) if candidate_count else "来自近期录音/TXT整理的候选动作，先由你确认是否推进。"
        output.append(
            {
                **item,
                "account_id": item.get("account_id") or "",
                "customer": customer,
                "priority": "P1" if transcript_candidate else ("P0" if bucket == "overdue" else "P1"),
                "stage": "待判断" if transcript_candidate else (item.get("countdown_label") or ("已超期" if bucket == "overdue" else "今天到期")),
                "action": action_label,
                "risk": risk_label,
                "signal": "录音/TXT 提取候选" if source_type == "transcript_intake" else "日程 / Deadline",
                "context_type": "schedule",
                "workflow_key": item.get("id") or "",
                "todo_id": item.get("id") or "",
                "status": status,
                "deadline": item.get("deadline") or "",
                "next_step": next_step,
                "calendar": item.get("calendar") or {},
                "source_type": source_type or "workbench_deadline",
                "schedule_bucket": bucket,
                "countdown_label": item.get("countdown_label") or "",
                "minutes_left": item.get("minutes_left"),
            }
        )
    return output


def normalize_work_text(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", strip_html(value or "").lower())


def work_text_overlaps(left: str, right: str) -> bool:
    left_text = normalize_work_text(left)
    right_text = normalize_work_text(right)
    if not left_text or not right_text:
        return False
    if left_text in right_text or right_text in left_text:
        return True
    short, long = sorted([left_text, right_text], key=len)
    if len(short) < 18:
        return False
    return short[:18] in long or short[-18:] in long


def workflow_action_key_for_item(item: dict) -> str:
    return "action:" + ":".join(
        safe_filename(str(part), "")
        for part in [item.get("customer", ""), item.get("action") or item.get("title") or item.get("task") or ""]
        if str(part or "").strip()
    )


def is_open_followup_status(status: str) -> bool:
    return status in {"待客户反馈", "待内部支持", "推进中", "待确认时间", "需继续跟进", "已同步", "同步失败"}


def same_customer(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right or left in right or right in left:
        return True
    left_aliases = set(customer_aliases(left))
    right_aliases = set(customer_aliases(right))
    return bool(left_aliases & right_aliases)


def action_belongs_to_customer(action_customer: str, action_title: str, target_customer: str) -> bool:
    if same_customer(action_customer, target_customer):
        return True
    if action_customer == "通用待办":
        return any(alias and alias in action_title for alias in customer_aliases(target_customer))
    return False


def should_suppress_battle_action(action: dict) -> bool:
    if action.get("context_type") == "schedule":
        return False
    customer = str(action.get("customer", ""))
    title = str(action.get("action") or action.get("title") or action.get("task") or "")
    state = load_workflow_state()
    exact_record = state.get("action_status", {}).get(workflow_action_key_for_item(action), {})
    if exact_record.get("hidden") or exact_record.get("status") in {"已闭环", "已处理", "已转日程", "已忽略"}:
        return True
    for bucket in ("action_status", "risk_status", "schedule_status"):
        for record in state.get(bucket, {}).values():
            if not isinstance(record, dict):
                continue
            if not action_belongs_to_customer(customer, title, str(record.get("customer", ""))):
                continue
            record_title = str(record.get("title") or record.get("next_step") or record.get("item", {}).get("action", ""))
            if not work_text_overlaps(title, record_title):
                continue
            if record.get("hidden") or str(record.get("status", "")) in {"已闭环", "已处理", "已回填", "风险解除", "已忽略"} or is_open_followup_status(str(record.get("status", ""))):
                return True
    for todo in load_risk_todos():
        if not action_belongs_to_customer(customer, title, str(todo.get("customer", ""))):
            continue
        todo_title = str(todo.get("title") or todo.get("next_step") or todo.get("action", ""))
        if work_text_overlaps(title, todo_title) and is_open_followup_status(str(todo.get("status", ""))):
            return True
    return False


def parse_due_date(text: str) -> date | None:
    match = re.search(r"(?P<month>\d{1,2})/(?P<day>\d{1,2})", text)
    if not match:
        return None
    try:
        return date(datetime.now().year, int(match.group("month")), int(match.group("day")))
    except ValueError:
        return None


def risk_level_label(item_date: date | None) -> tuple[str, str]:
    today = date.today()
    if item_date is None:
        return "watch", "待确认时间"
    delta = (item_date - today).days
    if delta < 0:
        return "overdue", f"已超期 {abs(delta)} 天"
    if delta == 0:
        return "today", "今天到期"
    if delta <= 2:
        return "soon", f"{delta} 天内到期"
    return "planned", f"{delta} 天后到期"


def project_line_for_customer(customer: str) -> str:
    if customer == "星海汽车权益平台":
        return "财经权益线"
    if customer == "星海汽车商城":
        return "商城二期线"
    if customer == "星海汽车企微助手":
        return "企微助手线"
    if customer == "云杉百货":
        return "云杉百货线"
    if customer == "清源健康健康":
        return "清源健康健康线"
    return "客户项目线"


def risk_status_for_level(level: str) -> str:
    if level in {"overdue", "today", "soon", "planned"}:
        return "未闭环"
    if level == "message":
        return "风险观察"
    return "待确认"


def recommendation_for_todo(todo: str, customer: str | None, board_item: dict | None) -> str:
    if "APP原生" in todo or "原生商城" in todo:
        return "补齐 APP 原生商城方案和对齐会材料，确认原生化范围、人天、排期与二期主线关系；不要带入后续采购金额口径"
    if "汇报" in todo:
        return "先补汇报材料、参会人和预期结论，再确认会议是否仍有效"
    if "预约" in todo or "约" in todo:
        return "今天先发确认消息，拿到具体时间；若无回复，补第二联系人"
    if "方案" in todo or "demo" in todo.lower():
        return "拆成资料准备、内部预演、对外确认三个动作，避免继续堆积"
    if customer:
        return f"围绕 {customer} 补最新沟通，再明确下一步推进动作"
    return "先确认责任人、截止时间和阻塞点"


def find_board_item_for_text(text: str, deal_board: list[dict]) -> dict | None:
    for item in deal_board:
        if item["name"].startswith("星海汽车"):
            continue
        if any(alias and alias in text for alias in customer_aliases(item["name"])):
            return item
    if any(keyword in text for keyword in ("权益平台", "财经", "积分", "抵现", "权益中台", "数字资产中台")):
        return next((item for item in deal_board if item["name"] == "星海汽车权益平台"), None)
    if has_wenjie_context(text) and any(keyword in text for keyword in ("商城", "人群包", "抽奖", "分享裂变", "APP", "采购", "框架单价", "示例联系人", "项目经理")):
        return next((item for item in deal_board if item["name"] == "星海汽车商城"), None)
    for item in deal_board:
        if any(alias and alias in text for alias in customer_aliases(item["name"])):
            return item
    if any(keyword in text for keyword in ("星海汽车", "示例汽车集团", "新哥", "超哥")):
        return next((item for item in deal_board if item["name"] == "星海汽车商城"), None)
    return None


def build_message_alerts(deal_board: list[dict], message_digest: dict) -> list[dict]:
    return []


def build_risk_alerts(deal_board: list[dict], todos: dict[str, list[str]], message_digest: dict | None = None) -> list[dict]:
    alerts = []
    matched_todos = set()
    for item in deal_board:
        for todo in item.get("todos", []):
            due = parse_due_date(todo)
            level, label = risk_level_label(due)
            matched_todos.add(todo)
            alerts.append(
                {
                    "customer": item["name"],
                    "projectLine": project_line_for_customer(item["name"]),
                    "priority": item["priority"],
                    "level": level,
                    "label": label,
                    "date": due.isoformat() if due else "",
                    "status": risk_status_for_level(level),
                    "task": todo,
                    "risk": item["risk"],
                    "recommendation": recommendation_for_todo(todo, item["name"], item),
                    "source": "todo_log",
                }
            )
    for todo in todos.get("pending", []):
        if todo in matched_todos:
            continue
        due = parse_due_date(todo)
        level, label = risk_level_label(due)
        alerts.append(
            {
                "customer": "通用待办",
                "projectLine": "通用待办",
                "priority": "P2",
                "level": level,
                "label": label,
                "date": due.isoformat() if due else "",
                "status": risk_status_for_level(level),
                "task": todo,
                "risk": "未绑定到客户，容易被遗漏",
                "recommendation": recommendation_for_todo(todo, None, None),
                "source": "todo_log",
            }
        )
    if message_digest:
        alerts.extend(build_message_alerts(deal_board, message_digest))
    rank = {"overdue": 0, "today": 1, "soon": 2, "message": 3, "watch": 4, "planned": 5}
    priority_rank = {"P0": 0, "P1": 1, "P2": 2}
    alerts.sort(
        key=lambda item: (
            rank.get(item["level"], 9),
            priority_rank.get(item.get("priority"), 9),
            item.get("date") or "9999-12-31",
            item["customer"],
        )
    )
    return alerts[:14]


def parse_message_date(path: Path) -> str:
    match = re.match(r"(\d{4}-\d{2}-\d{2})_", path.name)
    return match.group(1) if match else ""


def extract_message_texts(path: Path) -> list[str]:
    texts: list[str] = []
    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        bullet_match = re.match(r"- \*\*.*?\*\* \(\d{2}:\d{2}:\d{2}\):\s*(.*)", line)
        if bullet_match:
            text = bullet_match.group(1).strip()
            if text:
                texts.append(text)
            continue
        if line.startswith(("# ", "## ", "> ", "- message_id:", "- type:", "- sender:", "```")):
            continue
        if line.startswith("{") and line.endswith("}"):
            continue
        texts.append(line)
    return texts


def compact_text(text: str, limit: int = 72) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else f"{clean[: limit - 1]}…"


def extract_message_entries(path: Path) -> list[dict]:
    entries: list[dict] = []
    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        match = re.match(r"- \*\*(?P<sender>.*?)\*\* \((?P<time>\d{2}:\d{2}:\d{2})\):\s*(?P<text>.*)", line)
        if not match:
            continue
        text = match.group("text").strip()
        if text:
            entries.append({"sender": match.group("sender").strip(), "time": match.group("time"), "text": text})
    return entries


def unique_limited(items: list[str], limit: int = 5) -> list[str]:
    cleaned = [item for item in (compact_text(item, 96) for item in items) if item]
    return list(dict.fromkeys(cleaned))[:limit]


def infer_message_owners(text: str, sender: str = "") -> list[str]:
    owners = []
    owners.extend(re.findall(r"@([\w\u4e00-\u9fff_-]{2,12})", text))
    owners.extend(re.findall(r"([\u4e00-\u9fff]{1,4}(?:哥|姐|总|老师|同学))", text))
    if sender and not sender.startswith("_") and sender != "unknown":
        owners.append(sender)
    ignored = {"所有人", "all", "大家", "用户"}
    return [
        owner
        for owner in dict.fromkeys(owners)
        if owner not in ignored and not owner.startswith("_user") and not owner.startswith("ou_")
    ][:4]


def sanitize_pm_text(text: str, limit: int = 110) -> str:
    clean = re.sub(r"@_user_\d+\s*", "", text)
    clean = re.sub(r"\bou_[a-zA-Z0-9_]+\b", "同事", clean)
    return compact_text(clean, limit)


def combined_pm_text(report: dict) -> str:
    chunks = [report.get("summary", "")]
    chunks.extend(str(item) for item in report.get("risks", []))
    chunks.extend(str(item) for item in report.get("decisions_needed", []))
    for action in report.get("actions", []):
        if isinstance(action, dict):
            chunks.append(action.get("task", ""))
            chunks.append(action.get("group", ""))
        else:
            chunks.append(str(action))
    for item in report.get("items", []):
        chunks.append(item.get("name", ""))
        chunks.append(item.get("summary", ""))
    return " ".join(chunks)


def normalize_pm_daily_report(report: dict) -> dict:
    report = {**report}

    def group_digest_text(value: str) -> str:
        text = str(value or "")
        text = text.replace("PM 日报", "项目群日报").replace("PM日报", "项目群日报")
        text = text.replace("项目日报", "项目群日报")
        text = text.replace("会话", "项目群")
        text = re.sub(r"\s*当前首要(?:风险|动作)：.*$", "", text)
        text = re.sub(r"\s*管理动作应[^。]*[。]?", "", text)
        text = re.sub(r"\s*主要风险：[^。；]*[。；]?", "", text)
        text = re.sub(r"\s*下一步：[^。；]*[。；]?", "", text)
        return compact_text(text, 220)

    items = report.get("items", [])
    normalized_items = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        normalized_items.append(
            {
                "name": item.get("name") or "未命名项目群",
                "message_count": int(item.get("message_count") or 0),
                "health": item.get("health") or "灰",
                "summary": group_digest_text(item.get("summary") or "今天暂无有效摘要。"),
                "topics": item.get("topics") or [],
                "progress": item.get("progress") or [],
                "discussion_points": [group_digest_text(value) for value in (item.get("discussion_points") or item.get("highlights") or [])],
                "open_points": [group_digest_text(value) for value in (item.get("open_points") or [])],
                "mentions": [group_digest_text(value) for value in (item.get("mentions") or [])],
                "actions": [],
                "risks": [],
                "owners": [],
                "decisions_needed": [],
            }
        )
    if not report.get("summary"):
        topic_desc = "、".join(list(dict.fromkeys(topic for item in normalized_items for topic in item.get("topics", [])))[:5]) or "日常沟通"
        report["summary"] = f"{report.get('date', '')} 共覆盖 {len(normalized_items)} 个项目群，主要沟通集中在 {topic_desc}。"
    else:
        report["summary"] = group_digest_text(report["summary"])
    for key in ("overview_points", "issue_points", "plan_points", "coordination_points", "highlight_points"):
        report[key] = [group_digest_text(value) for value in (report.get(key) or []) if group_digest_text(value)][:8]
    report["items"] = normalized_items
    report["actions"] = []
    report["risks"] = []
    report["owners"] = []
    report["decisions_needed"] = []
    return report


def infer_pm_topic(text: str) -> str:
    topics = [
        ("交付排期", ("上线", "发布", "排期", "延期", "预计", "今天", "明天", "周五", "周六")),
        ("技术对接", ("接口", "SSO", "白名单", "密钥", "配置", "登录", "联调", "环境")),
        ("会议沟通", ("会议", "调研", "汇报", "现场", "线下", "线上", "预约", "时间")),
        ("客户支持", ("培训", "答疑", "支持", "协助", "处理", "反馈")),
        ("商务报价", ("预算", "报价", "成本", "人天", "毛利", "采购", "框架单价", "付款")),
    ]
    for title, keywords in topics:
        if any(keyword in text for keyword in keywords):
            return title
    return "日常沟通"


def synthesize_group_report_sections(chat_name: str, texts: list[str], topics: list[str]) -> dict[str, list[str]]:
    joined = " ".join(texts)
    progress: list[str] = []
    discussion: list[str] = []
    open_points: list[str] = []
    coordination: list[str] = []
    highlights: list[str] = []

    def has(*keywords: str) -> bool:
        return any(keyword in joined for keyword in keywords)

    def add(bucket: list[str], value: str) -> None:
        if value and value not in bucket:
            bucket.append(value)

    if has("测试环境", "私服", "jar", "服务器", "环境"):
        add(discussion, "测试环境、依赖包和私服配置是当天主要对齐内容。")
        add(open_points, "测试环境交付状态、依赖包准备情况和客户 IT 配合需要继续收口。")
        add(coordination, "需要技术侧与客户 IT/运维侧保持环境和依赖项同步。")

    if has("登录", "OA", "oa", "SSO", "静默登录", "代客下单", "解锁"):
        add(discussion, "登录链路、静默登录方案或账号解锁问题在群内持续推进。")
        if has("解锁", "好了", "已经", "定稿"):
            add(progress, "部分登录或方案问题已有明确处理结果，后续等待验证或实现支持。")
            add(highlights, "登录或方案类问题已有明确反馈，推进状态比单纯排查更清晰。")
        add(open_points, "登录方案的实现支持、验证结果和后续发版节奏仍需群内继续同步。")

    if has("发版", "发布", "周四", "上线", "排期"):
        add(discussion, "发版窗口、上线节奏和验证时间在群内被反复确认。")
        add(open_points, "具体发版时间、验证结果和相关影响范围仍需要群内对齐。")
        if has("计划", "同步"):
            add(progress, "发版计划已开始在群内同步，等待具体时间和验证结果落地。")

    if has("退款", "流水", "对账", "智融", "分账", "中台"):
        add(discussion, "退款流水、对账字段、分账数据来源等财务/技术口径在群内对齐。")
        add(open_points, "退款流水取值、对账字段和分账数据展示链路仍需技术侧确认。")
        add(coordination, "需要商城侧、中台侧和对账相关同学统一字段口径。")

    if has("ES", "商品", "脚本", "前置执行"):
        add(discussion, "商品 ES 测试环境和前置脚本是技术群内的重点同步内容。")
        add(progress, "相关脚本和测试环境材料已经在群内流转。")

    if has("网络", "反馈"):
        add(progress, "网络类问题已被识别并反馈给相关同学继续处理。")
        add(highlights, "已有问题被定位到网络或环境侧，减少了业务链路误判。")

    if has("安装", "经销", "店铺模块", "模块变更"):
        add(discussion, "安装类经销线上化的店铺模块变更在群内进行说明和对齐。")
        add(open_points, "模块变更范围、讲解时间和后续影响需要继续确认。")

    if has("方案", "评审", "定稿", "UI", "需求"):
        add(discussion, "方案评审、UI 支持和需求实现边界是产品群内的重点。")
        if has("定稿"):
            add(progress, "方案已推进到定稿阶段，下一步重点是技术实现支持。")
            add(highlights, "方案从讨论推进到定稿，具备继续落地的基础。")
        add(open_points, "方案落地需要继续明确技术支持人、实现方式和交付节奏。")

    if has("成本", "预算", "报价", "采购", "付款", "人天"):
        add(discussion, "商务预算、采购口径和人天成本信息在群内被提及或同步。")
        add(open_points, "预算、采购和人天口径仍需要保持一致，避免后续交付口径偏差。")

    if not discussion:
        add(discussion, f"群内主要围绕{'、'.join(topics) or '日常沟通'}进行同步。")
    if not open_points:
        add(open_points, "当天没有形成明确待对齐问题，后续按正常群内同步观察。")
    if not coordination:
        add(coordination, "当前未识别到需要额外跨部门协调的事项。")
    if not progress:
        add(progress, "当天以信息同步和问题确认为主，未形成明确完成节点。")
    if not highlights:
        add(highlights, "群内沟通保持连续，关键事项已被纳入同步范围。")

    return {
        "progress": progress[:4],
        "discussion_points": discussion[:4],
        "open_points": open_points[:4],
        "mentions": coordination[:4],
        "highlights": highlights[:4],
    }


def build_group_pm_report(chat_name: str, entries: list[dict]) -> dict:
    texts = [entry["text"] for entry in entries]
    if not texts:
        return {
            "name": chat_name,
            "message_count": 0,
            "health": "灰",
            "summary": "当天没有有效文本消息。",
            "topics": [],
            "progress": [],
            "discussion_points": [],
            "open_points": [],
            "mentions": [],
            "risks": [],
            "actions": [],
            "owners": [],
            "decisions_needed": [],
        }

    topic_keywords = [
        ("交付排期", ("上线", "发布", "周五", "周六", "排期", "预计", "延期")),
        ("技术对接", ("接口", "SSO", "白名单", "密钥", "配置", "登录", "联调", "环境")),
        ("会议沟通", ("会议", "调研", "汇报", "现场", "线下", "线上", "预约")),
        ("客户支持", ("培训", "答疑", "支持", "协助", "反馈", "处理")),
        ("商务报价", ("预算", "报价", "成本", "人天", "毛利", "采购", "框架单价", "付款")),
    ]
    topic_hits: list[tuple[int, str]] = []
    for title, keywords in topic_keywords:
        count = sum(1 for text in texts if any(keyword in text for keyword in keywords))
        if count:
            topic_hits.append((count, title))
    topic_hits.sort(reverse=True)

    topics = [title for _, title in topic_hits[:3]] or ["日常沟通"]
    if len(texts) >= 40:
        health = "红"
    elif len(texts) >= 12:
        health = "黄"
    else:
        health = "绿"

    topic_desc = "、".join(topics)
    time_range = ""
    if entries:
        first_time = entries[0].get("time", "")
        last_time = entries[-1].get("time", "")
        if first_time and last_time:
            time_range = f"沟通时段 {first_time[:5]}-{last_time[:5]}。"
    sections = synthesize_group_report_sections(chat_name, texts, topics)
    summary_parts = sections["discussion_points"][:2]
    summary = f"{chat_name} 今日主题为 {topic_desc}，共 {len(texts)} 条有效消息。{time_range}".strip()
    if summary_parts:
        summary += f" 结构化判断：{'；'.join(summary_parts)}"

    return {
        "name": chat_name,
        "message_count": len(texts),
        "health": health,
        "summary": summary,
        "topics": topics,
        "progress": sections["progress"],
        "discussion_points": sections["discussion_points"],
        "open_points": sections["open_points"],
        "mentions": sections["mentions"],
        "highlight_points": [],
        "risks": [],
        "actions": [],
        "owners": [],
        "decisions_needed": [],
    }


def build_pm_daily_report(day: str, group_reports: list[dict]) -> dict:
    all_topics = []
    total_messages = 0
    for group in group_reports:
        total_messages += group["message_count"]
        all_topics.extend(group.get("topics", []))

    active_groups = sum(1 for group in group_reports if group.get("message_count", 0) > 0)
    heavy_groups = sum(1 for group in group_reports if group.get("health") == "红")
    medium_groups = sum(1 for group in group_reports if group.get("health") == "黄")
    health = "红" if heavy_groups else "黄" if medium_groups else "绿"
    topic_desc = "、".join(list(dict.fromkeys(all_topics))[:5]) or "日常沟通"
    active_names = "、".join(group["name"] for group in group_reports if group.get("message_count", 0) > 0) or "暂无活跃群"
    executive_summary = f"{day} 共覆盖 {len(group_reports)} 个项目群，其中 {active_groups} 个有有效沟通，合计 {total_messages} 条消息。今日主题集中在 {topic_desc}。活跃群：{compact_text(active_names, 120)}。"
    active_reports = [group for group in group_reports if group.get("message_count", 0) > 0]
    overview_points = [
        f"{group['name']}：围绕{'、'.join(group.get('topics', []) or ['日常沟通'])}推进，群内产生 {group.get('message_count', 0)} 条有效消息。"
        for group in active_reports
    ]
    issue_points = [
        f"{group['name']}：{point}"
        for group in active_reports
        for point in group.get("open_points", [])[:2]
    ]
    def plan_from_group_point(group_name: str, point: str) -> str:
        clean = point
        for old, new in (
            ("需要继续", ""),
            ("仍需", ""),
            ("还需", ""),
            ("需要", ""),
            ("继续收口", "确认"),
            ("群内继续同步", "同步"),
            ("继续同步", "同步"),
            ("收口", "确认"),
        ):
            clean = clean.replace(old, new)
        clean = clean.strip("。； ")
        clean = re.sub(r"(确认|同步)$", "", clean).strip("。； ")
        return f"{group_name}：明日继续确认{clean}。"

    plan_points = [
        plan_from_group_point(group["name"], point)
        for group in active_reports
        for point in (group.get("open_points", [])[:1] or group.get("discussion_points", [])[:1])
    ]
    coordination_points = [
        f"{group['name']}：{point}"
        for group in active_reports
        for point in group.get("mentions", [])[:2]
    ]
    return normalize_pm_daily_report({
        "date": day,
        "health": health,
        "file_count": len(group_reports),
        "message_count": total_messages,
        "summary": executive_summary,
        "overview_points": overview_points or [executive_summary],
        "issue_points": unique_limited(issue_points, 8) or ["群内没有形成需要单独提示的问题，按正常项目沟通推进。"],
        "plan_points": unique_limited(plan_points, 8) or ["明日继续观察各项目群是否出现明确 @ 或需跟进事项。"],
        "coordination_points": unique_limited(coordination_points, 8) or ["当前没有需要额外关注的项目背景。"],
        "highlight_points": [],
        "actions": [],
        "risks": [],
        "owners": [],
        "decisions_needed": [],
        "items": group_reports,
    })


def pm_report_markdown(report: dict) -> str:
    def append_numbered_section(lines: list[str], title: str, points: list[str]) -> None:
        lines.extend(["", f"## {title}"])
        if points:
            lines.extend([f"{index}. {point}" for index, point in enumerate(points, 1)])
        else:
            lines.append("暂无。")

    lines = [
        f"# 项目群日报 - {report['date']}",
        "",
        f"- 活跃度：{report['health']}",
        f"- 覆盖项目群：{report['file_count']} 个",
        f"- 原始沟通：{report['message_count']} 条（仅作证据，不在工作台逐条展示）",
    ]
    append_numbered_section(lines, "一、今日进展概述", report.get("overview_points", []))
    append_numbered_section(lines, "二、群内问题与待对齐点", report.get("issue_points", []))
    append_numbered_section(lines, "三、后续计划", report.get("plan_points", []))
    append_numbered_section(lines, "四、需要关注事项", report.get("coordination_points", []))
    lines.extend(["", "## 五、项目群明细"])
    for item in report.get("items", []):
        lines.extend(
            [
                "",
                f"### {item['name']}",
                f"- 活跃度：{item['health']}",
                f"- 消息数：{item.get('message_count', 0)}",
                f"- 摘要：{item['summary']}",
                f"- 主题：{'、'.join(item.get('topics', [])) or '日常沟通'}",
            ]
        )
        if item.get("discussion_points"):
            lines.append("- 关键讨论：")
            lines.extend([f"  - {point}" for point in item.get("discussion_points", [])])
        if item.get("progress"):
            lines.append("- 项目进展：")
            lines.extend([f"  - {point}" for point in item.get("progress", [])])
        if item.get("open_points"):
            lines.append("- 群内待对齐点：")
            lines.extend([f"  - {point}" for point in item.get("open_points", [])])
        if item.get("mentions"):
            lines.append("- 需要关注事项：")
            lines.extend([f"  - {point}" for point in item.get("mentions", [])])
    lines.extend(["", "## 来源", "- 飞书项目群消息汇总；历史日报保留。合并消息数采用保守累计口径，不重复相加重叠快照。"])
    return "\n".join(lines).strip() + "\n"


def parse_pm_report_file(path: Path) -> dict | None:
    text = read_text(path)
    match = re.match(r"(\d{4}-\d{2}-\d{2})_(?:PM日报|项目群日报)\.md", path.name)
    if not match:
        return None
    date_str = match.group(1)
    health_match = re.search(r"- (?:健康度|活跃度)：(.+)", text)
    sessions_match = re.search(r"- 覆盖(?:会话|项目群)：(\d+) 个", text)
    messages_match = re.search(r"- 原始沟通：(\d+) 条", text)
    summary_match = re.search(r"## (?:今日结论|今日群聊概览|一、今日进展概述)\n(?P<body>.*?)(?:\n\n## |$)", text, re.S)

    def section_lines(title: str) -> list[str]:
        section_match = re.search(rf"## {re.escape(title)}\n(?P<body>.*?)(?:\n\n## |$)", text, re.S)
        if not section_match:
            return []
        rows = []
        for line in section_match.group("body").splitlines():
            line = line.strip()
            if "暂无" in line:
                continue
            match_line = re.match(r"(?:-\s+|\d+\.\s+)(.+)", line)
            if match_line:
                rows.append(match_line.group(1).strip())
        return rows

    groups = []
    group_section = re.search(r"## (?:项目群摘要|分群摘要|五、项目群明细|六、项目群明细)\n(?P<body>.*?)(?:\n\n## |$)", text, re.S)
    group_body = group_section.group("body") if group_section else text
    for block in re.split(r"\n(?=### )", group_body):
        header = re.match(r"### (?P<name>.+)", block.strip())
        if not header:
            continue
        name = header.group("name").strip()
        health = re.search(r"- (?:健康度|活跃度)：(?P<value>.*)", block)
        count = re.search(r"- 消息数：(?P<value>\d+)", block)
        summary = re.search(r"- 摘要：(?P<value>.*)", block)
        topics = re.search(r"- 主题：(?P<value>.*)", block)
        discussion = re.search(r"- 讨论点：\n(?P<body>(?:  - .*\n?)*)", block)
        if not discussion:
            discussion = re.search(r"- 关键讨论：\n(?P<body>(?:  - .*\n?)*)", block)
        progress = re.search(r"- 已有进展：\n(?P<body>(?:  - .*\n?)*)", block)
        if not progress:
            progress = re.search(r"- 项目进展：\n(?P<body>(?:  - .*\n?)*)", block)
        open_points = re.search(r"- 待群内对齐：\n(?P<body>(?:  - .*\n?)*)", block)
        mentions = re.search(r"- 群内 @：\n(?P<body>(?:  - .*\n?)*)", block)

        def nested_lines(match_obj: re.Match | None) -> list[str]:
            if not match_obj:
                return []
            return [
                line.strip()[2:].strip()
                for line in match_obj.group("body").splitlines()
                if line.strip().startswith("- ")
            ]

        groups.append(
            {
                "name": name,
                "health": health.group("value").strip() if health else "灰",
                "summary": " ".join(summary.group("value").split()) if summary else "",
                "topics": [item for item in (topics.group("value") if topics else "").split("、") if item],
                "message_count": int(count.group("value")) if count else 0,
                "progress": nested_lines(progress),
                "discussion_points": nested_lines(discussion),
                "open_points": nested_lines(open_points),
                "mentions": nested_lines(mentions),
                "risks": [],
                "actions": [],
                "owners": [],
                "decisions_needed": [],
            }
        )

    return normalize_pm_daily_report({
        "date": date_str,
        "health": health_match.group(1).strip() if health_match else "灰",
        "file_count": int(sessions_match.group(1)) if sessions_match else len(groups),
        "message_count": int(messages_match.group(1)) if messages_match else 0,
        "summary": " ".join(summary_match.group("body").strip().split()) if summary_match else compact_text(text, 180),
        "overview_points": section_lines("一、今日进展概述"),
        "issue_points": section_lines("二、群内问题与待对齐点"),
        "plan_points": section_lines("三、后续计划") or section_lines("三、后续计划与待办"),
        "coordination_points": section_lines("四、需要关注事项") or section_lines("四、需要协调的事项"),
        "highlight_points": [],
        "actions": [],
        "risks": [],
        "owners": [],
        "decisions_needed": [],
        "items": groups,
    })


def load_persisted_pm_reports(limit_days: int = 5) -> list[dict]:
    reports = []
    by_name = {path.name: path for root in (LEGACY_PM_DAILY_ROOT, PM_DAILY_ROOT) for path in root.glob("*_PM日报.md")}
    for name in sorted(by_name, reverse=True):
        path = by_name[name]
        report = parse_pm_report_file(path)
        if report:
            reports.append(report)
        if len(reports) >= limit_days:
            break
    return reports


def migrate_legacy_pm_reports() -> int:
    if not LEGACY_PM_DAILY_ROOT.exists():
        return 0
    PM_DAILY_ROOT.mkdir(parents=True, exist_ok=True)
    moved = 0
    for source in LEGACY_PM_DAILY_ROOT.glob("*_PM日报.md"):
        target = PM_DAILY_ROOT / source.name
        if not target.exists():
            target.write_text(read_text(source), encoding="utf-8")
        source.unlink()
        moved += 1
    try:
        if not any(LEGACY_PM_DAILY_ROOT.iterdir()):
            LEGACY_PM_DAILY_ROOT.rmdir()
    except OSError:
        pass
    return moved


def merge_unique_by_key(items: list[dict], key_fields: tuple[str, ...], limit: int) -> list[dict]:
    merged = []
    seen = set()
    for item in items:
        token = tuple(str(item.get(field, "")).strip() for field in key_fields)
        if token in seen:
            continue
        seen.add(token)
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged


def merge_pm_daily_reports(existing: dict, incoming: dict) -> dict:
    if not existing or existing.get("date") != incoming.get("date"):
        return incoming

    health_rank = {"绿": 0, "黄": 1, "红": 2}
    health = max(
        [existing.get("health", "绿"), incoming.get("health", "绿")],
        key=lambda value: health_rank.get(value, -1),
    )
    actions = merge_unique_by_key(
        [*incoming.get("actions", []), *existing.get("actions", [])],
        ("topic", "task", "owner", "group"),
        10,
    )
    by_group: dict[str, dict] = {}
    for item in [*existing.get("items", []), *incoming.get("items", [])]:
        name = item.get("name") or "项目群日报"
        current = by_group.get(name)
        if not current:
            by_group[name] = dict(item)
            continue
        current["health"] = max(
            [current.get("health", "绿"), item.get("health", "绿")],
            key=lambda value: health_rank.get(value, -1),
        )
        # Group snapshots overlap: use conservative cumulative count, never sum repeats.
        current["message_count"] = max(current.get("message_count", 0), item.get("message_count", 0))
        current["summary"] = "；".join(unique_limited([current.get("summary", ""), item.get("summary", "")], 2))
        current["topics"] = unique_limited([*current.get("topics", []), *item.get("topics", [])], 6)
        current["discussion_points"] = unique_limited([*current.get("discussion_points", []), *item.get("discussion_points", [])], 6)
        current["progress"] = unique_limited([*current.get("progress", []), *item.get("progress", [])], 6)
        current["open_points"] = unique_limited([*current.get("open_points", []), *item.get("open_points", [])], 6)
        current["mentions"] = unique_limited([*current.get("mentions", []), *item.get("mentions", [])], 6)

    return normalize_pm_daily_report({
        "date": incoming["date"],
        "health": health,
        "file_count": len(by_group) or max(existing.get("file_count", 0), incoming.get("file_count", 0)),
        "message_count": max(sum(item.get("message_count", 0) for item in by_group.values()), existing.get("message_count", 0), incoming.get("message_count", 0)),
        "summary": "；".join(unique_limited([incoming.get("summary", ""), existing.get("summary", "")], 2)),
        "actions": [],
        "risks": [],
        "owners": [],
        "decisions_needed": [],
        "items": list(by_group.values()),
        **{key: unique_limited([*incoming.get(key, []), *existing.get(key, [])], 8) for key in ("overview_points", "issue_points", "plan_points", "coordination_points")},
    })


def persist_pm_daily_report(report: dict) -> None:
    PM_DAILY_ROOT.mkdir(parents=True, exist_ok=True)
    path = PM_DAILY_ROOT / f"{report['date']}_PM日报.md"
    existing = parse_pm_report_file(path) if path.exists() else None
    if existing:
        report = merge_pm_daily_reports(existing, report)
    content = pm_report_markdown(report)
    if read_text(path) != content:
        path.write_text(content, encoding="utf-8")


def cleanup_raw_message_cache(date_str: str | None = None) -> int:
    removed = 0
    pattern = f"{date_str}_*.md" if date_str else "*.md"
    for root in (RAW_MESSAGE_CACHE_ROOT, LEGACY_MESSAGE_ROOT):
        if not root.exists():
            continue
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            try:
                path.unlink()
                removed += 1
            except FileNotFoundError:
                continue
    return removed


def build_message_digest(limit_days: int = 5, persist_reports: bool = False) -> dict:
    expected_date = datetime.now().strftime("%Y-%m-%d")
    if not persist_reports:
        persisted = load_persisted_pm_reports(limit_days)
        if persisted:
            latest_date = persisted[0]["date"]
            return {
                "latest_date": latest_date,
                "expected_date": expected_date,
                "is_stale": latest_date != expected_date,
                "groups_synced": sum(day["file_count"] for day in persisted),
                "total_messages": sum(day["message_count"] for day in persisted),
                "days": persisted,
            }

    message_roots = [root for root in (MESSAGE_ROOT, LEGACY_MESSAGE_ROOT) if root.exists()]
    if not message_roots:
        return {
            "latest_date": "",
            "expected_date": expected_date,
            "is_stale": True,
            "groups_synced": 0,
            "total_messages": 0,
            "days": [],
        }
    files = sorted(
        [path for root in message_roots for path in root.glob("*.md")],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    by_day: dict[str, list[Path]] = {}
    for path in files:
        day = parse_message_date(path)
        if day:
            by_day.setdefault(day, []).append(path)
    days = []
    for day in sorted(by_day.keys(), reverse=True)[:limit_days]:
        day_files = by_day[day]
        group_reports = []
        for path in sorted(day_files):
            group_reports.append(build_group_pm_report(path.stem.split("_", 1)[-1], extract_message_entries(path)))
        report = build_pm_daily_report(day, group_reports)
        if persist_reports:
            persist_pm_daily_report(report)
        days.append(report)
    latest_date = days[0]["date"] if days else ""
    return {
        "latest_date": latest_date,
        "expected_date": expected_date,
        "is_stale": latest_date != expected_date,
        "groups_synced": sum(day["file_count"] for day in days),
        "total_messages": sum(day["message_count"] for day in days),
        "days": days,
    }


def snippet_for_match(text: str, needle: str, width: int = 84) -> str:
    idx = text.find(needle)
    if idx == -1:
        return compact_text(text[:width], width)
    start = max(0, idx - width // 2)
    end = min(len(text), idx + width // 2)
    return compact_text(text[start:end], width)


def collect_local_customer_intel(query: str, limit: int = 6) -> list[dict]:
    aliases = customer_aliases(query)
    candidates = []
    for root in (REPORT_ROOT, INTAKE_ROOT, SALES_WORKBENCH_KNOWLEDGE_ROOT / "raw" / "articles"):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".json"}:
                continue
            text = read_text(path)
            matched_alias = next((alias for alias in aliases if alias and (alias in path.name or alias in text)), None)
            if not matched_alias:
                continue
            stat = path.stat()
            candidates.append(
                {
                    "source": str(path.relative_to(SALES_WORKBENCH_KNOWLEDGE_ROOT)),
                    "updated_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "snippet": snippet_for_match(text, matched_alias),
                    "score": stat.st_mtime,
                }
            )
    unique = []
    seen = set()
    for item in sorted(candidates, key=lambda row: row["score"], reverse=True):
        if item["source"] in seen:
            continue
        seen.add(item["source"])
        unique.append({key: value for key, value in item.items() if key != "score"})
        if len(unique) >= limit:
            break
    return unique


def collect_customer_message_signals(query: str, limit: int = 8) -> list[dict]:
    if not MESSAGE_ROOT.exists():
        return []
    min_day = date.today().toordinal() - 6
    aliases = customer_aliases(query)
    if any(alias in ("示例汽车集团", "星海汽车") for alias in aliases):
        aliases.extend(["采购", "框架单价", "产品沟通", "技术沟通"])
    aliases = list(dict.fromkeys(alias for alias in aliases if alias))
    candidates = []
    for path in MESSAGE_ROOT.glob("*.md"):
        day = parse_message_date(path)
        if not day:
            continue
        try:
            if date.fromisoformat(day).toordinal() < min_day:
                continue
        except ValueError:
            continue
        source_name = path.stem.split("_", 1)[-1]
        texts = extract_message_texts(path)
        matched_by_source = any(alias in source_name for alias in aliases)
        for text in texts:
            matched_alias = next((alias for alias in aliases if alias in text), None)
            if not matched_alias and not matched_by_source:
                continue
            kind = "消息"
            if any(word in text for word in ("风险", "失败", "问题", "不满", "挑战", "延期", "未")):
                kind = "风险"
            elif any(word in text for word in ("需要", "请", "协助", "跟进", "确认", "支持", "安排", "推进", "约", "发邮件", "开整")):
                kind = "动作"
            candidates.append(
                {
                    "date": day,
                    "source": source_name,
                    "kind": kind,
                    "snippet": compact_text(text, 110),
                }
            )
    candidates.sort(key=lambda item: item["date"], reverse=True)
    unique = []
    seen = set()
    for item in candidates:
        key = (item["date"], item["source"], item["snippet"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def customer_intel_target_names(limit: int = 40) -> list[str]:
    customers = parse_client_registry()
    names = []
    for bucket in ("active", "potential"):
        for item in customers.get(bucket, []):
            name = str(item.get("name", "")).strip()
            if name:
                names.append(name)
    return list(dict.fromkeys(names))[:limit]


def customer_intel_task_defaults() -> dict:
    now = datetime.now(LOCAL_TZ)
    return {
        "enabled": True,
        "schedule": "每天 06:00",
        "timezone": "Asia/Shanghai",
        "rule": "现有客户新闻由 Codex 自动搜索回传；只做客户情报和判断依据，不自动生成待办。",
        "last_run_at": "",
        "last_run_status": "waiting",
        "last_run_error": "",
        "next_run_at": prospecting_next_run_at(now, ""),
        "target_customers": customer_intel_target_names(),
    }


def default_customer_intel_state() -> dict:
    return {
        "ok": True,
        "task": customer_intel_task_defaults(),
        "customers": {},
        "runs": [],
    }


def load_customer_intel_state() -> dict:
    state = read_json_file(CUSTOMER_INTEL_STATE_FILE, default_customer_intel_state())
    if not isinstance(state, dict):
        state = default_customer_intel_state()
    defaults = default_customer_intel_state()
    state.setdefault("ok", True)
    state["task"] = {**defaults["task"], **(state.get("task") or {})}
    state["task"]["rule"] = defaults["task"]["rule"]
    state["task"]["target_customers"] = defaults["task"]["target_customers"]
    state.setdefault("customers", {})
    state.setdefault("runs", [])
    return state


def save_customer_intel_state(state: dict) -> None:
    write_private_json(CUSTOMER_INTEL_STATE_FILE, state)


def customer_intel_match_name(value: str) -> str:
    text = str(value or '').strip()
    if not text:return ''
    return next((name for name in customer_intel_target_names()
                 if public_signal_hub.same_customer(text,name,public_signal_hub.identity_aliases)),text)


def customer_intel_signal_type(row: dict, title: str) -> str:
    raw = str(row.get("signal_type") or row.get("type") or "").strip()
    if raw:
        return raw
    if any(marker in title for marker in ("招标", "采购", "中标", "供应商征集", "比选", "商务谈判", "成交公告")):
        return "招投标/采购"
    if any(marker in title for marker in ("财报", "业绩", "营收", "利润", "增长")):
        return "经营动态"
    if any(marker in title for marker in ("数字化", "私域", "会员", "小程序", "商城", "企微", "智能客服")):
        return "业务触发"
    return "公开新闻"


def normalize_customer_intel_signal(row: dict, customer: str, rank: int) -> dict:
    title = str(row.get("title") or row.get("headline") or "公开新闻").strip()
    url = str(row.get("source_url") or row.get("url") or "").strip()
    summary = str(row.get("summary") or row.get("snippet") or row.get("source_text") or "").strip()
    signal_type = customer_intel_signal_type(row, title)
    published_at = str(row.get("published_at") or row.get("date") or "").strip()
    signal_id = str(row.get("id") or uuid.uuid5(uuid.NAMESPACE_URL, url or f"{customer}:{title}").hex[:12])
    return {
        "id": signal_id,
        "rank": rank,
        "customer": customer,
        "title": title,
        "url": url,
        "source_url": url,
        "published_at": published_at,
        "signal_type": signal_type,
        "summary": summary,
        "relevance": row.get("relevance") or row.get("why_matched") or "与客户经营/项目推进相关，先作为情报判断。",
        "impact_judgment": row.get("impact_judgment") or row.get("judgment") or "只读情报：不自动变成待办，等进入客户作战室后再判断是否需要动作。",
        "recommended_action": row.get("recommended_action") or row.get("next_step") or "先读来源，判断是否影响当前客户推进或需要补充到下一次沟通。",
        "should_create_todo": False,
        "source": row.get("source") or row.get("publisher") or "Codex 搜索",
    }


def import_customer_intel_payload(payload: dict) -> dict:
    with PROSPECTING_STATE_LOCK:
        return import_customer_intel_payload_impl(payload)

def import_customer_intel_payload_impl(payload: dict) -> dict:
    state = load_customer_intel_state()
    run_id = str(payload.get('run_id') or '')
    if run_id:
        receipt = next((r for r in state.get('runs',[]) if r.get('run_id') == run_id),None)
        if receipt:
            return {'ok':True,'replayed':True,'customer_count':receipt.get('customer_count',0),'signal_count':receipt.get('signal_count',0),'intel':state}
    now = datetime.now(LOCAL_TZ)
    customer_rows: dict[str, list[dict]] = {}

    for group in payload.get("customers", []) if isinstance(payload.get("customers"), list) else []:
        if not isinstance(group, dict):
            continue
        customer = customer_intel_match_name(str(group.get("customer") or group.get("name") or ""))
        if not customer:
            continue
        signals = group.get("signals") or group.get("items") or []
        if isinstance(signals, list):
            customer_rows.setdefault(customer, []).extend([row for row in signals if isinstance(row, dict)])

    flat_signals = payload.get("signals") or payload.get("items") or []
    if isinstance(flat_signals, list):
        for row in flat_signals:
            if not isinstance(row, dict):
                continue
            customer = customer_intel_match_name(str(row.get("customer") or row.get("company") or ""))
            if not customer:
                continue
            customer_rows.setdefault(customer, []).append(row)

    updated_count = 0
    signal_count = 0
    new_count = 0
    updated_signal_count = 0
    customers = state.get("customers") if isinstance(state.get("customers"), dict) else {}
    for customer, rows in customer_rows.items():
        seen = set()
        signals = []
        for row in rows:
            title = str(row.get("title") or row.get("headline") or "").strip()
            url = str(row.get("source_url") or row.get("url") or "").strip()
            if not title and not url:
                continue
            key = url or title
            if key in seen:
                continue
            seen.add(key)
            signals.append(normalize_customer_intel_signal(row, customer, len(signals) + 1))
            if len(signals) >= 12:
                break
        if not signals:
            continue
        old_record = customers.get(customer, {})
        old_signals = old_record.get('signals', [])
        old_by_key = {public_signal_hub.signal_key(x): x for x in old_signals}
        for item in signals:
            previous = old_by_key.get(public_signal_hub.signal_key(item))
            if previous is None: new_count += 1
            elif any(item.get(k) != previous.get(k) for k in ('title','summary','impact_judgment','recommended_action','published_at')): updated_signal_count += 1
        merged_signals = public_signal_hub.merge_signals(old_signals, signals, now.isoformat(timespec='seconds'))
        customers[customer] = {
            "customer": customer,
            "updated_at": now.isoformat(timespec="seconds"),
            "source": payload.get("source") or "codex_agent_search",
            "signals": merged_signals,
        }
        updated_count += 1
        signal_count += len(signals)

    state["customers"] = customers
    task = state.get("task") or {}
    task.update({
        "enabled": True,
        "schedule": "每天 06:00",
        "timezone": "Asia/Shanghai",
        "rule": customer_intel_task_defaults()["rule"],
        "last_run_at": now.isoformat(timespec="seconds"),
        "last_run_status": "failed" if payload.get("status") == "failed" else "ok" if signal_count else "no_change" if payload.get("checked_customers") else "no_import",
        "last_run_error": str(payload.get("error") or "搜索未完成")[:500] if payload.get("status") == "failed" else "" if signal_count or payload.get("checked_customers") else "没有搜索覆盖回执，不能认定无新增",
        "checked_customers": payload.get("checked_customers", []),
        "next_run_at": prospecting_next_run_at(now, now.isoformat(timespec="seconds")),
        "target_customers": customer_intel_target_names(),
    })
    state["task"] = task
    state["runs"] = [{
        "at": now.isoformat(timespec="seconds"),
        "run_id": str(payload.get('run_id') or ''),
        "run_date": str(payload.get('run_date') or now.date().isoformat()),
        "new_count": new_count,
        "updated_count": updated_signal_count,
        "checked_customers": payload.get('checked_customers', []),
        "checked_queries": payload.get('checked_queries', []) if isinstance(payload.get('checked_queries'), list) else [],
        "coverage_notes": payload.get('coverage_notes', []) if isinstance(payload.get('coverage_notes'), list) else [],
        "source": payload.get("source") or "codex_agent_search",
        "status": task["last_run_status"],
        "customer_count": updated_count,
        "signal_count": signal_count,
    }, *[item for item in state.get("runs", []) if isinstance(item, dict)]][:10]
    save_customer_intel_state(state)
    return {"ok": True, "customer_count": updated_count, "signal_count": signal_count, "intel": state}


def public_customer_intel_signals(query: str, state: dict | None = None) -> tuple[list[dict], dict]:
    intel_state = state or load_customer_intel_state()
    customers = intel_state.get("customers") if isinstance(intel_state.get("customers"), dict) else {}
    customer = customer_intel_match_name(query)
    record = customers.get(customer)
    if not record:
        for name, candidate in customers.items():
            if public_signal_hub.same_customer(query, name, public_signal_hub.identity_aliases):
                record, customer = candidate, name
                break
    signals = record.get("signals", []) if isinstance(record, dict) and isinstance(record.get("signals"), list) else []
    return signals, {"customer": customer, "record": record or {}, "task": intel_state.get("task") or {}}


def get_public_signal_hub():
    projects = build_projects(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT)
    intel=load_customer_intel_state()
    prospecting = load_prospecting_state()
    for name,record in prospecting.get('customer_evidence',{}).items():
        prior=intel.setdefault('customers',{}).setdefault(name,{'customer':name,'signals':[]})
        prior['signals']=public_signal_hub.merge_signals(prior.get('signals',[]),record.get('signals',[]),'')
    for lead in prospecting.get('leads',[]):
        if lead.get('decision')!='accepted' or not lead.get('additional_signals'):continue
        name=lead.get('added_customer_name') or lead.get('company')
        prior=intel.setdefault('customers',{}).setdefault(name,{'customer':name,'signals':[]})
        signals=[{**x,'impact_judgment':x.get('impact_judgment') or x.get('entry_strategy'),'recommended_action':x.get('recommended_action') or x.get('next_step')} for x in lead['additional_signals']]
        prior['signals']=public_signal_hub.merge_signals(prior.get('signals',[]),signals,'')
    result = public_signal_hub.build_hub(intel, projects, public_signal_hub.identity_aliases)
    result['opportunity_task'] = public_signal_hub.run_status(prospecting.get('public_task', {}), [r for r in prospecting.get('runs', []) if r.get('trigger') == 'codex_agent_search'])
    result['opportunity_receipt'] = prospecting.get('public_receipt', {})
    result['tender_receipt'] = public_signal_hub.tender_receipt(prospecting)
    result['operations'] = background_operations.read_status(WORKBENCH_DATA_ROOT)
    return result


def get_customer_intel_payload(query: str) -> dict:
    public_signals, public_meta = public_customer_intel_signals(query)
    return {
        "query": query,
        "customer": public_meta.get("customer") or query,
        "public_task": public_meta.get("task") or {},
        "public_updated_at": (public_meta.get("record") or {}).get("updated_at", ""),
        "message_signals": collect_customer_message_signals(query),
        "local_signals": collect_local_customer_intel(query),
        "public_signals": public_signals,
    }


def prospecting_today_six(now: datetime | None = None) -> datetime:
    current = now or datetime.now(LOCAL_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=LOCAL_TZ)
    return current.astimezone(LOCAL_TZ).replace(hour=6, minute=0, second=0, microsecond=0)


def parse_optional_local_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TZ)
    return parsed.astimezone(LOCAL_TZ)


def parse_prospecting_date(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text or any(marker in text for marker in ("待核验", "未知", "暂无", "无")):
        return None
    normalized = (
        text.replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
        .replace("/", "-")
        .replace(".", "-")
    )
    match = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", normalized)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def prospecting_first_date(lead: dict, keys: tuple[str, ...]) -> date | None:
    for key in keys:
        parsed = parse_prospecting_date(str(lead.get(key) or ""))
        if parsed:
            return parsed
    return None


def prospecting_earliest_date(lead: dict, keys: tuple[str, ...]) -> date | None:
    dates = [parsed for key in keys if (parsed := parse_prospecting_date(str(lead.get(key) or "")))]
    return min(dates) if dates else None


def prospecting_time_window(lead: dict, now: date | None = None) -> dict:
    today = now or datetime.now(LOCAL_TZ).date()
    published = prospecting_first_date(lead, ("published_at", "publish_date", "date", "updated_at"))
    deadline = prospecting_earliest_date(
        lead,
        (
            "bid_deadline",
            "response_deadline",
            "submission_deadline",
            "registration_deadline",
            "application_deadline",
            "document_acquisition_deadline",
            "question_deadline",
            "deadline",
            "close_at",
            "end_at",
            "opening_at",
        ),
    )
    base = {
        "published_at": published.isoformat() if published else "",
        "deadline": deadline.isoformat() if deadline else "",
        "published_age_days": None,
        "prep_days": None,
        "status": "needs_time_evidence",
        "label": "缺少公告/截止时间",
        "note": "先补公告发布时间、报名/响应/开标截止日，再判断是否值得列明。",
        "actionability": "needs_time_evidence",
    }
    if lead.get("background_only") or lead.get("notice_state") in {"closed_result", "closed_contract"}:
        base.update({
            "status": "closed_result",
            "label": lead.get("notice_state_label") or "已成交 / 中标",
            "note": "采购窗口已经闭合，只用于识别供应商和复盘项目范围，不进入客户准入或今日行动。",
            "actionability": "stale",
        })
        return base
    if deadline:
        prep_days = (deadline - today).days
        base["prep_days"] = prep_days
        if prep_days < 0:
            base.update({
                "status": "stale_deadline",
                "label": f"截止已过 {abs(prep_days)} 天",
                "note": "采购窗口已经关闭，只能作为历史背景或供应商路径复盘，不进入今日判断。",
                "actionability": "stale",
            })
        elif PROSPECTING_PREP_WINDOW_MIN_DAYS <= prep_days <= PROSPECTING_PREP_WINDOW_MAX_DAYS:
            base.update({
                "status": "prep_window",
                "label": f"准备窗口 {prep_days} 天",
                "note": "还有一到四周准备时间，优先补关键人、供应商路径和切入材料。",
                "actionability": "actionable",
            })
        elif 0 <= prep_days < PROSPECTING_PREP_WINDOW_MIN_DAYS:
            base.update({
                "status": "near_deadline",
                "label": f"窗口只剩 {prep_days} 天",
                "note": "时间过近，除非已有渠道或供应商路径，否则不建议冷启动主攻。",
                "actionability": "limited",
            })
        else:
            base.update({
                "status": "future_window",
                "label": f"远期窗口 {prep_days} 天",
                "note": "还偏早，先放观察，等窗口接近再推动具体动作。",
                "actionability": "watch",
            })
        return base
    if published:
        age_days = (today - published).days
        base["published_age_days"] = age_days
        if age_days < 0:
            base.update({
                "status": "future_signal",
                "label": "未来公告",
                "note": "发布时间异常在未来，先补信源时间。",
                "actionability": "needs_time_evidence",
            })
        elif age_days <= PROSPECTING_RECENT_SIGNAL_DAYS:
            base.update({
                "status": "recent_signal",
                "label": f"近期发布 {age_days} 天 · 待补截止日",
                "note": "近期触发，但还缺截止日；先补报名/响应/开标时间。",
                "actionability": "needs_time_evidence",
            })
        elif age_days <= PROSPECTING_STALE_SIGNAL_DAYS:
            base.update({
                "status": "aging_signal",
                "label": f"发布 {age_days} 天",
                "note": "信号开始变旧，需要先查是否已截止或已中标。",
                "actionability": "limited",
            })
        else:
            base.update({
                "status": "stale_signal",
                "label": f"发布已过 {age_days} 天",
                "note": "公告已经滞后，只保留为历史背景，不进入今日判断。",
                "actionability": "stale",
            })
    return base


def prospecting_user_surface(lead: dict) -> str:
    decision = str(lead.get("decision") or "pending")
    actionability = str(lead.get("actionability") or "needs_time_evidence")
    if decision in {"accepted", "watch", "ignored"}:
        return decision
    if decision in {"pending", "verify"} and actionability == "actionable":
        return "candidate"
    if decision == "stale" or actionability in {"stale", "limited"}:
        return "history"
    return "internal_review"


def prospecting_watch_profile(lead: dict) -> dict:
    title = str(lead.get("title") or "")
    actionability = str(lead.get("actionability") or "")
    background_only = bool(lead.get("background_only")) or any(
        marker in title for marker in ("中标结果", "成交结果", "采购结果", "中标公告", "成交公告")
    )
    if background_only:
        watch_type = "供应商替换"
        reason = "历史结果证明客户购买过相关能力，继续识别现有供应商、合同周期和替换风险。"
        next_trigger = "新一轮招采、合同续约、二期扩容或现有供应商交付问题"
    elif actionability == "limited":
        watch_type = "近窗转长期"
        reason = "本轮窗口不适合冷启动，但当前招采已经验证客户的真实采购意图。"
        next_trigger = "本轮中标结果、实施供应商、二期建设或下一次采购窗口"
    elif "咨询" in title:
        watch_type = "升级孵化"
        reason = "客户已启动相关咨询，后续可能进入系统建设、运营陪跑或能力升级。"
        next_trigger = "咨询中标结果、系统建设立项、实施采购或组织负责人变化"
    else:
        watch_type = "升级与替换"
        reason = "历史采购证明客户具备相关需求，等待新的升级、增购或替换触发。"
        next_trigger = "新招采、二期扩容、合同到期或供应商替换信号"
    return {
        "watch_type": str(lead.get("watch_type") or watch_type),
        "watch_reason": str(lead.get("watch_reason") or reason),
        "next_trigger": str(lead.get("next_trigger") or next_trigger),
        "maintenance_mode": "ai_background",
        "execution_boundary": "AI后台维护，不进入今日行动、下次提醒或飞书任务；出现新触发后再回到准入判断。",
        "watch_since": str(lead.get("watch_since") or lead.get("decided_at") or datetime.now(LOCAL_TZ).isoformat(timespec="seconds")),
    }


def apply_prospecting_historical_watch(lead: dict) -> dict:
    decision = str(lead.get("decision") or "pending")
    title = str(lead.get("title") or "")
    historical = bool(lead.get("background_only")) or str(lead.get("notice_state") or "") in {
        "closed_result",
        "closed_contract",
    } or any(marker in title for marker in ("中标结果", "成交结果", "采购结果", "中标公告", "成交公告"))
    if historical and decision not in {"accepted", "ignored"}:
        now = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
        lead["decision"] = "watch"
        lead["status"] = "AI 后台维护"
        lead["decided_at"] = str(lead.get("decided_at") or now)
        lead["decision_note"] = str(lead.get("decision_note") or "历史采购只作为客户意图和供应商证据")
        lead.update(prospecting_watch_profile(lead))
        lead["user_surface"] = "watch"
    return lead


def apply_prospecting_surface_limits(state: dict) -> dict:
    leads = [item for item in state.get("leads", []) if isinstance(item, dict)]
    for lead in leads:
        lead["user_surface"] = prospecting_user_surface(lead)
        lead.pop("surface_rank", None)

    candidates = [lead for lead in leads if lead.get("user_surface") == "candidate"]
    candidates.sort(
        key=lambda lead: (
            -int(lead.get("search_score") or 0),
            int((lead.get("time_window") or {}).get("prep_days") or 10**6),
            int(lead.get("rank") or 10**6),
        )
    )
    for index, lead in enumerate(candidates):
        lead["surface_rank"] = index + 1
        if index >= PROSPECTING_VISIBLE_CANDIDATE_LIMIT:
            lead["user_surface"] = "candidate_backlog"

    watches = [lead for lead in leads if lead.get("decision") == "watch"]
    for lead in watches:
        lead.update(prospecting_watch_profile(lead))
    watches.sort(
        key=lambda lead: (
            str(lead.get("published_at") or ""),
            str(lead.get("decided_at") or ""),
        ),
        reverse=True,
    )
    for index, lead in enumerate(watches):
        lead["surface_rank"] = index + 1
        lead["user_surface"] = "watch" if index < PROSPECTING_VISIBLE_WATCH_LIMIT else "watch_backlog"

    state["surface_limits"] = {
        "daily_candidate_limit": PROSPECTING_VISIBLE_CANDIDATE_LIMIT,
        "long_term_limit": PROSPECTING_VISIBLE_WATCH_LIMIT,
        "candidate_backlog_count": sum(1 for lead in leads if lead.get("user_surface") == "candidate_backlog"),
        "watch_backlog_count": sum(1 for lead in leads if lead.get("user_surface") == "watch_backlog"),
    }
    state["leads"] = leads
    return state


def apply_prospecting_time_window(lead: dict, *, preserve_user_decision: bool = True) -> dict:
    window = prospecting_time_window(lead)
    lead["time_window"] = window
    lead["time_window_label"] = window["label"]
    lead["actionability"] = window["actionability"]
    if window.get("deadline") and not lead.get("deadline"):
        lead["deadline"] = window["deadline"]
    decision = lead.get("decision") or "pending"
    user_decided = decision in {"accepted", "watch", "ignored"}
    if preserve_user_decision and user_decided:
        lead["user_surface"] = prospecting_user_surface(lead)
        return lead
    if window["actionability"] == "stale":
        lead["decision"] = "stale"
        lead["status"] = "已成交，仅作供应商背景" if lead.get("background_only") else "已滞后"
    elif decision in {"pending", "verify"} and window["actionability"] == "needs_time_evidence":
        lead["decision"] = "verify"
        lead["status"] = "待补时间窗口"
    elif decision in {"pending", "verify"} and window["actionability"] == "limited":
        lead["decision"] = "stale"
        lead["status"] = "准备时间不足，仅作历史背景"
    elif decision == "pending" and window["actionability"] == "watch":
        lead["status"] = "远期观察"
    lead["user_surface"] = prospecting_user_surface(lead)
    return lead


def prospecting_next_run_at(now: datetime | None = None, last_run_at: str | None = None) -> str:
    current = now or datetime.now(LOCAL_TZ)
    today_six = prospecting_today_six(current)
    last_run = parse_optional_local_datetime(last_run_at)
    if last_run and last_run.date() == current.date() and last_run >= today_six:
        return (today_six + timedelta(days=1)).isoformat(timespec="seconds")
    return today_six.isoformat(timespec="seconds")


def default_prospecting_state() -> dict:
    now = datetime.now(LOCAL_TZ)
    return {
        "ok": True,
        "task": {
            "enabled": True,
            "schedule": "每天 06:00",
            "timezone": "Asia/Shanghai",
            "rule": "知了标讯负责发现公开招采，AI 负责客户适配和进入路径判断；只有核到最早有效截止节点且仍有 14-30 天准备窗口的项目进入待判断，缺截止日、准备不足、已成交或已截止项目不进入用户候选池。",
            "last_run_at": "",
            "last_run_status": "waiting",
            "next_run_at": prospecting_next_run_at(now, ""),
            "searched_queries": [],
            "source": "zhiliao_tender_search",
            "source_label": "知了标讯",
            "query_groups": [
                {"id": group["id"], "label": group["label"], "reason": group["reason"]}
                for group in PROSPECTING_QUERY_GROUPS
            ],
        },
        "summary": {
            "lead_count": 0,
            "pending_count": 0,
            "verify_count": 0,
            "stale_count": 0,
            "watch_count": 0,
            "accepted_count": 0,
            "ignored_count": 0,
            "candidate_count": 0,
            "internal_review_count": 0,
            "last_result_count": 0,
        },
        "surface_limits": {
            "daily_candidate_limit": PROSPECTING_VISIBLE_CANDIDATE_LIMIT,
            "long_term_limit": PROSPECTING_VISIBLE_WATCH_LIMIT,
            "candidate_backlog_count": 0,
            "watch_backlog_count": 0,
        },
        "leads": [],
        "runs": [],
    }


def load_prospecting_state() -> dict:
    state = read_json_file(PROSPECTING_STATE_FILE, default_prospecting_state())
    if not isinstance(state, dict):
        state = default_prospecting_state()
    defaults = default_prospecting_state()
    state.setdefault("ok", True)
    state.setdefault("task", {})
    state["task"] = {**defaults["task"], **(state.get("task") or {})}
    state["task"]["rule"] = defaults["task"]["rule"]
    state["task"]["query_groups"] = defaults["task"]["query_groups"]
    state["task"].setdefault("searched_queries", PROSPECTING_QUERIES)
    state.setdefault("summary", defaults["summary"])
    state.setdefault("leads", [])
    state.setdefault("runs", [])
    if isinstance(state.get("leads"), list):
        for lead in state["leads"]:
            if isinstance(lead, dict) and lead.get("bid_id") and str(lead.get("id") or "").startswith("zlbx-"):
                lead.setdefault("source_provider", "知了标讯")
        state["leads"] = [
            lead for lead in state["leads"]
            if not (
                isinstance(lead, dict)
                and prospecting_zhiliao_false_positive(lead)
                and (lead.get("decision") or "pending") not in {"accepted", "watch", "ignored"}
            )
        ]
        for lead in state["leads"]:
            if isinstance(lead, dict):
                lead.setdefault("decision", "pending")
                lead.setdefault("history", [])
                lead.setdefault("why_matched", [])
                lead_text = f"{lead.get('title', '')} {lead.get('source_query', '')} {' '.join(lead.get('keyword_hits', []))}"
                revenue_evidence = lead.get("revenue_evidence")
                if not isinstance(revenue_evidence, dict):
                    revenue_evidence = prospecting_revenue_evidence(lead.get("company", ""), lead.get("title", ""))
                purchase_signal = lead.get("purchase_signal") or prospecting_purchase_signal(lead.get("title", ""))
                supplier_path = lead.get("supplier_path") or prospecting_supplier_path(lead.get("title", ""))
                tier = prospecting_icp_tier(lead_text, revenue_evidence, purchase_signal)
                lead["revenue_evidence"] = revenue_evidence
                lead["scale_rule"] = prospecting_scale_label(revenue_evidence)
                lead.setdefault("icp_tier", tier["code"])
                lead.setdefault("icp_tier_label", tier["label"])
                lead.setdefault("purchase_signal", purchase_signal)
                lead.setdefault("supplier_path", supplier_path)
                lead.setdefault("entry_strategy", prospecting_entry_strategy(lead_text, tier, supplier_path, purchase_signal))
                apply_prospecting_time_window(lead)
                title = str(lead.get("title") or "")
                if (
                    any(marker in title for marker in ("中标结果", "成交结果", "采购结果", "终止公告", "废标公告"))
                    and lead.get("decision", "pending") not in {"accepted", "watch", "ignored"}
                ):
                    lead["decision"] = "stale"
                    lead["actionability"] = "stale"
                    lead["status"] = "项目结果已公布，仅作供应商背景"
                lead["user_surface"] = prospecting_user_surface(lead)
        apply_prospecting_surface_limits(state)
    state["task"]["next_run_at"] = prospecting_next_run_at(
        datetime.now(LOCAL_TZ),
        state["task"].get("last_run_at"),
    )
    return state


def save_prospecting_state(state: dict) -> None:
    write_private_json(PROSPECTING_STATE_FILE, state)


def zlbx_api_key() -> str:
    env_key = os.environ.get("ZLBX_API_KEY", "").strip()
    if env_key:
        return env_key
    config = read_json_file(ZLBX_CONFIG_FILE, {})
    if isinstance(config, dict) and str(config.get("api_key") or "").strip():
        return str(config["api_key"]).strip()
    raise RuntimeError("知了标讯尚未配置，无法执行实时扫描")


def zlbx_post(tool: str, payload: dict, timeout: int = 30) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(
        f"{ZLBX_API_BASE}/{tool}",
        data=body,
        headers={
            "X-API-Key": zlbx_api_key(),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    ca_file = Path(os.environ.get("SSL_CERT_FILE", "")).expanduser() if os.environ.get("SSL_CERT_FILE") else Path("/etc/ssl/cert.pem")
    ssl_context = ssl.create_default_context(cafile=str(ca_file)) if ca_file.exists() else ssl.create_default_context()
    try:
        with urlrequest.urlopen(req, timeout=timeout, context=ssl_context) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        raise RuntimeError(f"知了标讯接口 HTTP {exc.code}：{detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"知了标讯连接失败：{exc.reason}") from exc
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("知了标讯返回了无法识别的数据") from exc
    if result.get("success") is not True:
        error = result.get("error") or result.get("detail") or "未知错误"
        if isinstance(error, dict):
            error = error.get("message") or error.get("code") or json.dumps(error, ensure_ascii=False)
        raise RuntimeError(f"知了标讯查询失败：{str(error)[:220]}")
    return result


def prospecting_notice_plain_text(detail: dict) -> str:
    source = " ".join(
        str(detail.get(key) or "")
        for key in ("title", "source", "source_ext")
    )
    clean = html.unescape(strip_html(source)).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", clean).strip()


def prospecting_dates_in_text(text: str) -> list[date]:
    dates: list[date] = []
    pattern = re.compile(
        r"(20\d{2})\s*(?:年|[-/.])\s*(\d{1,2})\s*(?:月|[-/.])\s*(\d{1,2})\s*日?"
    )
    for match in pattern.finditer(text or ""):
        try:
            value = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            continue
        if value not in dates:
            dates.append(value)
    return dates


def prospecting_deadline_from_detail(detail: dict) -> str:
    nodes = public_signal_hub.deadline_nodes(prospecting_notice_plain_text(detail))
    if any(node['unresolved'] for node in nodes): return ''
    return min((node['date'] for node in nodes if node['date']), default='')


def prospecting_notice_state(detail: dict) -> dict:
    title = str(detail.get("title") or "")
    process = str(detail.get("bid_process") or "")
    leading_attachment = html.unescape(strip_html(str(detail.get("source_ext") or "")))[:900]
    closed = (
        any(marker in title for marker in ZLBX_CLOSED_NOTICE_MARKERS)
        or any(marker in leading_attachment for marker in ZLBX_CLOSED_NOTICE_MARKERS)
        or process in {"中标", "中标结果", "合同", "成交"}
    )
    if closed:
        return {"code": "closed_result", "label": "已成交 / 中标", "background_only": True}
    if any(marker in title or marker in leading_attachment for marker in ("废标", "终止", "流标")):
        return {"code": "closed_result", "label": "已终止 / 废标", "background_only": True}
    return {"code": "open", "label": process or "招采进行中", "background_only": False}


def prospecting_tender_candidate_score(row: dict) -> int:
    title = str(row.get("title") or "")
    company = str(row.get("caller_name") or "")
    subjects = " ".join(row.get("sm_names") or [])
    text = f"{title} {company} {subjects}"
    if not title or not company or any(marker in text for marker in ZLBX_HARD_MISMATCH_MARKERS):
        return -100
    if "信息披露" in text and "CDP" in text.upper():
        return -100
    if any(marker in text for marker in ("效果广告", "广告投放", "素材制作", "场地租赁", "展览会")):
        return -100
    weights = {
        "会员系统": 12,
        "会员平台": 11,
        "小程序商城": 12,
        "私域": 10,
        "CRM系统": 10,
        "SCRM": 10,
        "CDP": 10,
        "积分商城": 10,
        "权益平台": 10,
        "客户运营": 8,
        "企业微信": 7,
        "即时零售": 7,
        "数字营销": 5,
        "O2O": 7,
        "导购": 6,
        "会员": 5,
        "小程序": 4,
        "CRM": 7,
    }
    score = sum(weight for marker, weight in weights.items() if marker.lower() in text.lower())
    if company:
        score += 2
    else:
        score -= 4
    if any(marker in title for marker in ("采购意向", "招标公告", "采购公告", "询比采购", "供应商征集")):
        score += 2
    if any(marker in title for marker in ("运维", "维保", "维护外包", "会话存档", "授权续费")):
        score -= 7
    money_wan = row.get("money_wan")
    if isinstance(money_wan, (int, float)) and money_wan >= 100:
        score += 1
    return score


def prospecting_zhiliao_false_positive(lead: dict) -> bool:
    if lead.get("source_provider") != "知了标讯" and not str(lead.get("id") or "").startswith("zlbx-"):
        return False
    title = str(lead.get("title") or "")
    company = str(lead.get("company") or "")
    subjects = " ".join(lead.get("subject_names") or [])
    text = f"{title} {company} {subjects}"
    if not company or normalize_work_text(company) == normalize_work_text(title):
        return True
    if any(marker in text for marker in ZLBX_HARD_MISMATCH_MARKERS):
        return True
    if "信息披露" in text and "CDP" in text.upper():
        return True
    return any(marker in text for marker in ("效果广告", "广告投放", "素材制作", "场地租赁", "展览会"))


def prospecting_tender_entry_strategy(title: str, background_only: bool) -> str:
    if background_only:
        return "先记录本次成交供应商、采购范围和服务周期，后续只在续约、增购或替换信号出现时重新进入准入判断。"
    if any(marker in title for marker in ("CRM", "SCRM", "CDP")):
        return "先判断这是底层 CRM 替换还是客户运营增量；避开重实施底座，重点核对会员、营销自动化、企微和商城连接是否可由业务平台承接。"
    if any(marker in title for marker in ("小程序商城", "商城系统")):
        return "先核对招标范围是标准商城还是重定制开发，再判断业务平台直接参与、联合交付或放弃，不能只因命中“小程序商城”就列明。"
    return "先核对采购主体、投标资质、评分口径和现有供应商；若不适合直接投标，再判断能否通过集成商或运营服务商联合进入。"


def prospecting_tender_row(search_row: dict, detail: dict, rank: int, score: int) -> dict:
    title = str(detail.get("title") or search_row.get("title") or "公开招采线索").strip()
    company = str(detail.get("caller_name") or search_row.get("caller_name") or "").strip()
    company = company or prospecting_lead_name(title)
    published_at = str(detail.get("pub_time") or search_row.get("pub_time") or "").strip()
    deadline = prospecting_deadline_from_detail(detail)
    notice = prospecting_notice_state(detail)
    subjects = [str(item).strip() for item in (detail.get("sm_names") or search_row.get("sm_names") or []) if str(item).strip()]
    subject_text = "、".join(subjects[:4]) or title
    if notice["background_only"]:
        reasons = [
            "公告正文显示项目已经成交或中标，不能作为当前投标窗口。",
            f"项目范围：{subject_text}。",
            "保留价值仅限于识别现有供应商、服务边界和未来续约/替换节点。",
        ]
        next_step = "记录成交供应商与服务周期；没有新的续约、增购或替换信号前，不生成销售动作。"
    else:
        reasons = [
            f"知了标讯核到公开招采，项目范围包含：{subject_text}。",
            f"公告发布时间：{published_at or '待核验'}；截止时间：{deadline or '正文暂未提取到'}。",
            "先由你判断是否列明；未列明前只停在发现线索阶段，不进入今日行动。",
        ]
        next_step = "核对业务平台能力边界、投标资质和可进入渠道，再决定列明、补证据、观察或剔除。"
    bid_id = detail.get("bid_id") or search_row.get("bid_id")
    region = " ".join(filter(None, [str(detail.get("province") or search_row.get("province") or "").strip(), str(detail.get("city") or search_row.get("city") or "").strip()]))
    lead = {
        "id": f"zlbx-{bid_id}" if bid_id else uuid.uuid5(uuid.NAMESPACE_URL, str(detail.get("url") or title)).hex[:12],
        "rank": rank,
        "company": company,
        "title": title,
        "source_url": str(detail.get("url") or search_row.get("url") or "").strip(),
        "published_at": published_at,
        "deadline": deadline,
        "source_query": "知了标讯 · 近21天公开招采",
        "source_provider": "知了标讯",
        "signal_type": "供应商路径" if notice["background_only"] else "招采采购",
        "purchase_signal": "已成交背景" if notice["background_only"] else "招采/采购触发",
        "supplier_path": "成交供应商待核验" if notice["background_only"] else "先查供应商路径",
        "entry_strategy": prospecting_tender_entry_strategy(title, notice["background_only"]),
        "status": "已成交，仅作路径" if notice["background_only"] else "待判断",
        "decision": "watch" if notice["background_only"] else "pending",
        "keyword_hits": prospecting_keyword_hits(f"{title} {subject_text}"),
        "why_matched": reasons,
        "signal": reasons[0],
        "next_step": next_step,
        "bid_id": bid_id,
        "bid_stage": str(detail.get("bid_process") or search_row.get("bid_process") or ""),
        "notice_state": notice["code"],
        "notice_state_label": notice["label"],
        "background_only": notice["background_only"],
        "amount_wan": detail.get("money_wan") or search_row.get("money_wan") or 0,
        "region": region,
        "subject_names": subjects[:8],
        "search_score": score,
        "detail_checked_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
        "force_include": True,
        "history": [],
    }
    apply_prospecting_time_window(lead, preserve_user_decision=True)
    return apply_prospecting_historical_watch(lead)


def prospecting_keyword_hits(text: str) -> list[str]:
    source = text.lower()
    hits = []
    for keyword in PROSPECTING_KEYWORDS:
        if keyword.lower() in source and keyword not in hits:
            hits.append(keyword)
    return hits[:5]


def prospecting_youzan_fit_hits(text: str) -> list[str]:
    source = text.lower()
    hits = []
    for keyword in YOUZAN_FIT_KEYWORDS:
        if keyword.lower() in source and keyword not in hits:
            hits.append(keyword)
    return hits[:5]


def prospecting_has_mismatch(text: str) -> bool:
    source = text.lower()
    return any(keyword.lower() in source for keyword in PROSPECTING_MISMATCH_KEYWORDS)


def prospecting_is_youzan_existing_case(text: str) -> bool:
    source = text or ""
    return any(marker in source for marker in PROSPECTING_YOUZAN_EXISTING_CASE_MARKERS)


def prospecting_known_brand(title: str) -> str:
    return next((brand for brand in KNOWN_YOUZAN_PROSPECT_BRANDS if brand in (title or "")), "")


def prospecting_existing_customer_exception(text: str) -> bool:
    source = text or ""
    return any(keyword in source for keyword in PROSPECTING_EXISTING_CUSTOMER_EXCEPTION_KEYWORDS)


def prospecting_existing_customer_match(company: str, title: str) -> dict | None:
    candidates = [
        normalize_registry_customer_name(company),
        normalize_registry_customer_name(title),
    ]
    candidates = [candidate for candidate in candidates if candidate and candidate not in {"待识别客户", "待核验客户"}]
    if not candidates:
        return None
    if ACCOUNT_STORE_FILE.exists():
        with sqlite3.connect('file:' + str(ACCOUNT_STORE_FILE) + '?mode=ro', uri=True) as connection:
            for (raw,) in connection.execute('SELECT payload_json FROM accounts'):
                item = json.loads(raw)
                if public_signal_hub.same_customer(company,item.get('name',''),public_signal_hub.identity_aliases):
                    return {'bucket':'formal_account','name':item.get('name',''),'status':item.get('account_state',''),'note':'已在正式账户主账本，新增信号沿用该客户'}
    customers = parse_client_registry()
    for bucket, bucket_items in customers.items():
        if bucket not in PROSPECTING_EXISTING_CUSTOMER_FILTER_BUCKETS:
            continue
        for item in bucket_items:
            item_name = normalize_registry_customer_name(item.get("name", ""))
            if not item_name:
                continue
            if public_signal_hub.same_customer(company,item.get('name',''),public_signal_hub.identity_aliases):
                return {
                    "bucket": bucket,
                    "name": item.get("name", ""),
                    "status": item.get("status", ""),
                    "note": item.get("note", ""),
                }
    return None


def prospecting_is_generic_article_title(title: str) -> bool:
    text = title or ""
    generic_markers = (
        "如何",
        "怎么",
        "为什么",
        "指南",
        "报告",
        "研究",
        "趋势",
        "盘点",
        "观察",
        "洞察",
        "几家",
        "某",
        "案例拆解",
        "适合",
        "秘密",
        "最前线",
        "独家",
        "商家",
        "业务平台新零售发布",
        "最近想上市的公司",
        "从零售",
    )
    return any(marker in text for marker in generic_markers)


def prospecting_is_vendor_funding_title(title: str) -> bool:
    text = title or ""
    vendor_markers = ("SaaS", "服务商", "系统厂商", "营销平台", "企微SCRM", "私域一体化")
    funding_markers = ("融资", "A轮", "B轮", "C轮", "领投", "创投", "完成", "投资", "战略投资")
    return any(marker in text for marker in vendor_markers) and any(marker in text for marker in funding_markers)


def prospecting_scale_label(text: str) -> str:
    if isinstance(text, dict):
        evidence = text
    else:
        evidence = prospecting_revenue_evidence("", text)
    amount = evidence.get("amount_yi")
    if public_signal_hub.verified_revenue(evidence):
        if amount >= 100:
            return "公开营收100亿+"
        if amount >= 30:
            return "公开营收30-100亿"
        if amount >= 10:
            return "公开营收10-30亿"
    return "营收待公开核验"


def prospecting_amount_to_yi(value: float, unit: str) -> float | None:
    unit = unit or ""
    if unit in {"万亿", "万亿元"}:
        return value * 10000
    if unit in {"亿元", "亿"}:
        return value
    if unit in {"万元", "万"}:
        return value / 10000
    return None


def prospecting_extract_revenue_evidence(text: str, source_label: str = "公开标题") -> dict | None:
    source = text or ""
    revenue_words = ("营收", "营业收入")
    number_pattern = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>万亿元|万亿|亿元|亿|万元|万)")
    for match in number_pattern.finditer(source):
        start = max(0, match.start() - 14)
        end = min(len(source), match.end() + 14)
        context = source[start:end]
        if not any(word in context for word in revenue_words) or re.search(r"目标|预计|预测|GMV", context, re.I):
            continue
        amount_yi = prospecting_amount_to_yi(float(match.group("num")), match.group("unit"))
        if amount_yi is None:
            continue
        return {
            "status": "pending_public_lookup",
            "label": f"标题提及营收约，待核验： {amount_yi:.1f} 亿",
            "amount_yi": round(amount_yi, 2),
            "source": source_label,
            "source_text": source[:180],
            "confidence": "medium",
        }
    phrase_match = re.search(r"(营收|营业收入).{0,10}(千亿|百亿|十亿)", source)
    if phrase_match:
        phrase = phrase_match.group(2)
        amount = 1000 if phrase == "千亿" else 100 if phrase == "百亿" else 10
        return {
            "status": "pending_public_lookup",
            "label": f"公开信息披露营收为{phrase}级",
            "amount_yi": amount,
            "source": source_label,
            "source_text": source[:180],
            "confidence": "low",
        }
    return None


def prospecting_revenue_pending(company: str, title: str) -> dict:
    return {
        "status": "pending_public_lookup",
        "label": "营收待公开核验",
        "amount_yi": None,
        "source": "待查年报 / 招股书 / 官方新闻 / 财经报道",
        "source_text": company or title or "",
        "confidence": "none",
    }


def prospecting_revenue_lookup(company: str) -> dict:
    normalized = normalize_registry_customer_name(company)
    if not normalized or normalized in {"待识别客户", "待核验客户"}:
        return prospecting_revenue_pending(company, "")
    cache = read_json_file(PROSPECTING_REVENUE_CACHE_FILE, {})
    cached = cache.get(normalized) if isinstance(cache, dict) else None
    now = datetime.now(LOCAL_TZ)
    if isinstance(cached, dict):
        cached_at = parse_optional_local_datetime(cached.get("checked_at"))
        if cached_at and (now - cached_at) < timedelta(days=14):
            return cached.get("evidence") or prospecting_revenue_pending(company, "")
    pending = prospecting_revenue_pending(company, "")
    pending["source_text"] = f"{company}：等待 Codex 自动搜索回传公开营收证据"
    cache[normalized] = {
        "checked_at": now.isoformat(timespec="seconds"),
        "company": company,
        "query": "Codex 自动搜索回传",
        "evidence": pending,
    }
    write_private_json(PROSPECTING_REVENUE_CACHE_FILE, cache)
    return pending


def prospecting_revenue_evidence(company: str, title: str, lookup: bool = False) -> dict:
    evidence = prospecting_extract_revenue_evidence(title, "公开线索标题")
    if evidence:
        return evidence
    if lookup:
        return prospecting_revenue_lookup(company)
    return prospecting_revenue_pending(company, title)


def prospecting_purchase_signal(text: str) -> str:
    source = text or ""
    if any(marker in source for marker in ("招标", "采购", "采购公告", "供应商征集", "中标")):
        return "招采/采购触发"
    if any(marker in source for marker in ("系统替换", "升级", "数字化转型", "建设", "项目")):
        return "系统升级触发"
    if any(marker in source for marker in ("会员", "私域", "复购", "O2O", "企业微信", "企微", "智能客服", "AI导购", "导购", "达人营销")):
        return "运营需求触发"
    return "触发待核验"


def prospecting_supplier_path(text: str) -> str:
    source = text or ""
    strong_competitors = ("微盟", "Shopify", "Salesforce", "销售易", "纷享销客")
    data_marketing_vendors = ("神策", "GrowingIO", "群脉", "Convertlab", "尘锋", "腾讯企点")
    ecosystem_vendors = ("阿里云", "腾讯云", "火山引擎", "华为云", "用友", "金蝶", "SAP", "埃森哲")
    if any(name in source for name in strong_competitors):
        return "强竞争/替换路径"
    if any(name in source for name in data_marketing_vendors):
        return "弱竞争/互补待判"
    if any(name in source for name in ecosystem_vendors):
        return "生态/集成带入"
    if any(marker in source for marker in ("服务商", "供应商", "中标", "集成商")):
        return "供应商路径待核验"
    return "先查供应商路径"


def prospecting_icp_tier(text: str, revenue_evidence: dict | None = None, purchase_signal: str | None = None) -> dict:
    source = text.lower()
    fit_hits = prospecting_youzan_fit_hits(text)
    purchase = purchase_signal or prospecting_purchase_signal(text)
    has_trigger = purchase != "触发待核验"
    amount = (revenue_evidence or {}).get("amount_yi")
    has_revenue = public_signal_hub.verified_revenue(revenue_evidence)
    has_strategic_scale = has_revenue and amount >= 100
    has_mid_scale = has_revenue and amount >= 30
    has_weak_scale = has_revenue and amount >= 10
    if has_strategic_scale and fit_hits and has_trigger:
        return {"code": "strategic_attack", "label": "战略主攻"}
    if (has_strategic_scale or has_mid_scale) and fit_hits:
        return {"code": "opportunity_watch", "label": "机会观察"}
    if purchase == "招采/采购触发" and fit_hits:
        return {"code": "trigger_track", "label": "触发跟踪"}
    if purchase == "系统升级触发" and fit_hits:
        return {"code": "trigger_track", "label": "触发跟踪"}
    if purchase == "运营需求触发" and fit_hits and any(
        marker in text for marker in ("积分", "权益", "权益兑换", "积分商城", "订单履约", "会员", "O2O")
    ):
        return {"code": "trigger_track", "label": "触发跟踪"}
    if has_weak_scale and fit_hits and has_trigger:
        return {"code": "trigger_track", "label": "触发跟踪"}
    return {"code": "not_now", "label": "暂不进入"}


def prospecting_entry_strategy(text: str, tier: dict, supplier_path: str, purchase_signal: str) -> str:
    if "强竞争" in supplier_path:
        return "先不要按合作带入处理；查清对方已用系统和能力缺口，再判断替换、绕开或从互补场景切入。"
    if "生态" in supplier_path or "集成" in supplier_path:
        return "优先查这个客户的现有集成商/云厂商/营销服务商，看是否能用联合方案或分润方式带入。"
    if purchase_signal == "招采/采购触发":
        return "先查招采文件、预算主体、评分口径和现有供应商，再决定是直连客户还是通过服务商进入。"
    if tier.get("code") == "strategic_attack":
        return "先做客户经营研究和供应商路径图，不冷启动直打；准备会员/私域/O2O/智能客服的场景材料找可进入的人。"
    if tier.get("code") == "opportunity_watch":
        return "先观察业务触发和预算窗口，补齐客户部门、系统现状、供应商关系，再决定是否列明。"
    return "暂不进入主攻队列；只有出现招采、系统替换、强运营需求或可信进入路径时再升级。"


def prospecting_should_keep_lead(title: str, query: str) -> bool:
    title_text = title or ""
    title_fit = prospecting_youzan_fit_hits(title_text)
    if prospecting_has_mismatch(title_text):
        return False
    if prospecting_is_youzan_existing_case(title_text) and not prospecting_existing_customer_exception(title_text):
        return False
    if prospecting_is_vendor_funding_title(title_text):
        return False
    if prospecting_is_generic_article_title(title_text) and not prospecting_known_brand(title_text):
        return False
    company = prospecting_lead_name(title_text)
    if company in PROSPECTING_EXCLUDED_COMPANIES:
        return False
    existing_customer = prospecting_existing_customer_match(company, title_text)
    if existing_customer and not prospecting_existing_customer_exception(title_text):
        return False
    return bool(title_fit)


def prospecting_reason_lines(title: str, query: str, group: dict, revenue_evidence: dict | None = None) -> list[str]:
    hits = prospecting_keyword_hits(title)
    fit_hits = prospecting_youzan_fit_hits(f"{title} {query}")
    reasons = [group.get("reason") or "公开信息出现业务平台适配客户经营信号"]
    if fit_hits:
        reasons.append(f"业务平台业务切口：{'、'.join(fit_hits[:4])}")
    if hits:
        reasons.append(f"业务信号：{'、'.join(hits[:4])}")
    evidence = revenue_evidence or prospecting_revenue_evidence("", title)
    if public_signal_hub.verified_revenue(evidence):
        reasons.append(f"公开营收证据：{evidence.get('label')}")
    else:
        reasons.append("营收未核验：不因搜索词或标题词直接定级")
    return reasons[:4]


def prospecting_lead_name(title: str) -> str:
    known_brand = prospecting_known_brand(title)
    if known_brand:
        return known_brand
    quoted_company = re.search(r"「([^」]{2,24})」(?:获|完成|宣布|与|和|推出|发布|融资|获近|获数)", title or "")
    if quoted_company:
        return quoted_company.group(1).strip()
    clean = re.sub(r"\s+", " ", title or "").strip()
    clean = re.sub(r"^(新闻|资讯|公告|报告|案例|公司动态|招募公告|征集公告|采购公告|中标公告)[：:｜|\-\s]+", "", clean)
    if "关于" in clean and clean.index("关于") >= 2:
        clean = clean.split("关于", 1)[0].strip()
    year_match = re.search(r"20\d{2}", clean)
    if year_match and year_match.start() >= 4:
        clean = clean[:year_match.start()].strip()
    for marker in ("客户关系管理", "CRM", "数据服务平台", "采购项目", "数字化转型项目"):
        marker_pos = clean.find(marker)
        if marker_pos >= 4:
            clean = clean[:marker_pos].strip()
            break
    for separator in (" - ", "｜", "|", "：", ":", "，", ",", "_"):
        if separator in clean:
            clean = clean.split(separator, 1)[0].strip()
            break
    clean = re.sub(r"(有限公司|股份有限公司|集团有限公司|集团|官网|官方网站).*$", r"\1", clean).strip()
    if re.match(r"^(20\d{2}|CRM|AI|ERP|数字化|采购|招标|中标|项目|供应商)", clean, re.I):
        return "待识别客户"
    return clean[:34] or "待核验客户"


def prospecting_result_to_lead(row: dict, query: str, group: dict, rank: int) -> dict:
    title = str(row.get("title") or "公开网页线索").strip()
    url = str(row.get("url") or "").strip()
    hits = prospecting_keyword_hits(f"{title} {query}")
    lead_id = uuid.uuid5(uuid.NAMESPACE_URL, url or title).hex[:12]
    company = prospecting_lead_name(title)
    revenue_evidence = prospecting_revenue_evidence(company, title, lookup=True)
    reasons = prospecting_reason_lines(title, query, group, revenue_evidence)
    lead_text = f"{title} {query}"
    purchase_signal = prospecting_purchase_signal(title)
    supplier_path = prospecting_supplier_path(title)
    tier = prospecting_icp_tier(lead_text, revenue_evidence, purchase_signal)
    existing_customer = prospecting_existing_customer_match(company, title)
    if existing_customer and prospecting_existing_customer_exception(title):
        reasons.append(f"已列明或历史客户已有：{existing_customer.get('name')}，因命中新项目/重启信号保留。")
    lead = {
        "id": lead_id,
        "rank": rank,
        "company": company,
        "title": title,
        "source_url": url,
        "source_provider": row.get("source_provider") or "",
        "published_at": row.get("published_at", ""),
        "deadline": row.get("deadline") or row.get("bid_deadline") or row.get("response_deadline") or row.get("submission_deadline") or "",
        "source_query": query,
        "signal_type": group.get("label", "公开信号"),
        "scale_rule": prospecting_scale_label(revenue_evidence),
        "revenue_evidence": revenue_evidence,
        "icp_tier": tier["code"],
        "icp_tier_label": tier["label"],
        "purchase_signal": purchase_signal,
        "supplier_path": supplier_path,
        "entry_strategy": prospecting_entry_strategy(lead_text, tier, supplier_path, purchase_signal),
        "status": "待核验",
        "decision": "pending",
        "keyword_hits": hits,
        "why_matched": reasons,
        "signal": reasons[0],
        "next_step": "先核验预算主人、业务触发、现有供应商和业务平台切口，再决定是否列明。",
        "history": [],
    }
    apply_prospecting_time_window(lead, preserve_user_decision=False)
    return apply_prospecting_historical_watch(lead)


def prospecting_group_for_import(row: dict) -> dict:
    text = " ".join(
        str(row.get(key, ""))
        for key in ("signal_type", "source_query", "title", "purchase_signal")
    )
    if any(marker in text for marker in ("招标", "采购", "中标", "供应商征集", "比选", "商务谈判")):
        return next(group for group in PROSPECTING_QUERY_GROUPS if group["id"] == "youzan_procurement")
    if any(marker in text for marker in ("O2O", "核销", "门店", "导购")):
        return next(group for group in PROSPECTING_QUERY_GROUPS if group["id"] == "o2o_member_operation")
    if any(marker in text for marker in ("企微", "企业微信", "智能客服", "AI导购", "AI")):
        return next(group for group in PROSPECTING_QUERY_GROUPS if group["id"] == "ai_customer_operation")
    if any(marker in text for marker in ("供应商", "中标", "服务商", "集成商")):
        return next(group for group in PROSPECTING_QUERY_GROUPS if group["id"] == "supplier_entry")
    if any(marker in text for marker in ("私域", "复购", "会员运营", "DTC")):
        return next(group for group in PROSPECTING_QUERY_GROUPS if group["id"] == "private_domain_growth")
    return next(group for group in PROSPECTING_QUERY_GROUPS if group["id"] == "strategic_retail")


def normalize_imported_revenue_evidence(row: dict, company: str, title: str) -> dict:
    evidence = row.get("revenue_evidence")
    if isinstance(evidence, dict):
        normalized = dict(evidence)
        normalized.setdefault("status", "pending_public_lookup")
        normalized.setdefault("label", prospecting_scale_label(normalized))
        normalized.setdefault("source", "Codex 搜索")
        normalized.setdefault("source_text", "")
        normalized.setdefault("confidence", "medium" if normalized.get("amount_yi") is not None else "none")
        if not public_signal_hub.verified_revenue(normalized, company):
            normalized["status"] = "pending_public_lookup"
            normalized["label"] = "营收待核验，暂不参与规模定级"
        return normalized
    amount = row.get("revenue_amount_yi")
    if isinstance(amount, (int, float)):
        return {
            "status": "pending_public_lookup",
            "label": "营收待核验，暂不参与规模定级",
            "amount_yi": round(float(amount), 2),
            "source": row.get("revenue_source") or "Codex 搜索",
            "source_url": row.get("revenue_source_url") or "",
            "source_text": row.get("revenue_source_text") or "",
            "confidence": row.get("revenue_confidence") or "medium",
        }
    return prospecting_revenue_evidence(company, title, lookup=False)


def prospecting_import_row_to_lead(row: dict, rank: int) -> dict:
    title = str(row.get("title") or row.get("headline") or "公开网页线索").strip()
    url = str(row.get("source_url") or row.get("url") or "").strip()
    company = str(row.get("company") or "").strip() or prospecting_lead_name(title)
    group = prospecting_group_for_import(row)
    query = str(row.get("source_query") or row.get("query") or group.get("label") or "Codex 搜索").strip()
    revenue_evidence = normalize_imported_revenue_evidence(row, company, title)
    purchase_signal = str(row.get("purchase_signal") or "").strip() or prospecting_purchase_signal(title)
    supplier_path = str(row.get("supplier_path") or "").strip() or prospecting_supplier_path(title)
    lead_text = " ".join(
        [
            title,
            query,
            str(row.get("signal", "")),
            " ".join(row.get("keyword_hits", []) if isinstance(row.get("keyword_hits"), list) else []),
        ]
    )
    tier = prospecting_icp_tier(lead_text, revenue_evidence, purchase_signal)
    lead_id = str(row.get("id") or uuid.uuid5(uuid.NAMESPACE_URL, f"{company}:{url or title}").hex[:12])
    reasons = row.get("why_matched")
    if not isinstance(reasons, list) or not reasons:
        reasons = prospecting_reason_lines(title, query, group, revenue_evidence)
    keyword_hits = row.get("keyword_hits")
    if not isinstance(keyword_hits, list):
        keyword_hits = prospecting_keyword_hits(title)
    deadline_keys = (
        "document_acquisition_deadline",
        "registration_deadline",
        "application_deadline",
        "question_deadline",
        "bid_deadline",
        "response_deadline",
        "submission_deadline",
        "deadline",
        "opening_at",
    )
    imported_deadline = prospecting_earliest_date(row, deadline_keys)
    lead = {
        "id": lead_id,
        "rank": rank,
        "company": company,
        "title": title,
        "source_url": url,
        "source_provider": row.get("source_provider") or "",
        "published_at": row.get("published_at", ""),
        "deadline": imported_deadline.isoformat() if imported_deadline else "",
        "document_acquisition_deadline": row.get("document_acquisition_deadline") or "",
        "question_deadline": row.get("question_deadline") or "",
        "opening_at": row.get("opening_at") or "",
        "source_query": query,
        "signal_type": row.get("signal_type") or group.get("label", "Codex 搜索"),
        "scale_rule": prospecting_scale_label(revenue_evidence),
        "revenue_evidence": revenue_evidence,
        "icp_tier": tier["code"],
        "icp_tier_label": tier["label"],
        "purchase_signal": purchase_signal,
        "supplier_path": supplier_path,
        "entry_strategy": row.get("entry_strategy") or prospecting_entry_strategy(lead_text, tier, supplier_path, purchase_signal),
        "status": row.get("status") or "待核验",
        "decision": "pending",
        "keyword_hits": keyword_hits[:5],
        "why_matched": reasons[:4],
        "signal": row.get("signal") or reasons[0],
        "next_step": row.get("next_step") or "先核验预算主人、业务触发、现有供应商和业务平台切口，再决定是否列明。",
        "bid_id": row.get("bid_id"),
        "bid_stage": row.get("bid_stage") or "",
        "notice_state": row.get("notice_state") or "",
        "notice_state_label": row.get("notice_state_label") or "",
        "background_only": bool(row.get("background_only")),
        "amount_wan": row.get("amount_wan") or 0,
        "region": row.get("region") or "",
        "subject_names": row.get("subject_names") if isinstance(row.get("subject_names"), list) else [],
        "search_score": row.get("search_score") or 0,
        "detail_checked_at": row.get("detail_checked_at") or "",
        "history": row.get("history") if isinstance(row.get("history"), list) else [],
    }
    return apply_prospecting_time_window(lead, preserve_user_decision=False)


def prospecting_import_should_keep(row: dict) -> bool:
    title = str(row.get("title") or row.get("headline") or "")
    query = str(row.get("source_query") or row.get("query") or row.get("signal_type") or "")
    company = str(row.get("company") or "").strip() or prospecting_lead_name(title)
    existing_customer = prospecting_existing_customer_match(company, title)
    if existing_customer and not prospecting_existing_customer_exception(title) and not row.get("force_prospecting"):
        return False
    text = f"{title} {query}"
    tender_markers = ("招标", "采购", "中标", "供应商征集", "比选", "商务谈判", "成交公告")
    is_tender_signal = any(marker in text for marker in tender_markers)
    historical_tender = bool(row.get("background_only")) or str(row.get("notice_state") or "") in {
        "closed_result",
        "closed_contract",
    } or any(marker in title for marker in ("中标结果", "成交结果", "采购结果", "中标公告", "成交公告"))
    if is_tender_signal and not historical_tender and not prospecting_earliest_date(
        row,
        (
            "document_acquisition_deadline",
            "registration_deadline",
            "application_deadline",
            "question_deadline",
            "bid_deadline",
            "response_deadline",
            "submission_deadline",
            "deadline",
            "opening_at",
        ),
    ):
        return False
    if row.get("force_include"):
        return True
    if is_tender_signal:
        return not prospecting_has_mismatch(text) and not prospecting_is_youzan_existing_case(text)
    return prospecting_should_keep_lead(title, query)


def merge_prospecting_leads(state: dict, incoming: list[dict], limit: int = 200) -> list[dict]:
    existing = [item for item in state.get("leads", []) if isinstance(item, dict)]
    identity_key = lambda value: min(public_signal_hub.identity_aliases(value))
    existing_by_company = {identity_key(item.get('company','')):item for item in existing}
    existing_by_id = {item.get("id"): item for item in existing if item.get("id")}
    existing_watch_by_company = {
        identity_key(item.get("company", "")): item
        for item in existing
        if item.get("decision") == "watch" and identity_key(item.get("company", ""))
    }
    merged_incoming: list[dict] = []
    incoming_ids: set[str] = set()
    for lead in incoming:
        apply_prospecting_time_window(lead, preserve_user_decision=False)
        apply_prospecting_historical_watch(lead)
        company_key = identity_key(lead.get("company", ""))
        id_match=existing_by_id.get(lead.get('id'))
        if id_match and identity_key(id_match.get('company',''))!=company_key:
            lead['id']=uuid.uuid5(uuid.NAMESPACE_URL, company_key+':'+str(lead.get('source_url') or lead.get('id'))).hex[:12]
            id_match=None
        current = id_match or existing_by_company.get(company_key)
        evidence_fields=('title','source_url','published_at','summary','signal_type','supplier_path','impact_judgment','recommended_action','entry_strategy','next_step','deadline')
        evidence={k:lead.get(k,'') for k in evidence_fields}
        prior_evidence=list((current or {}).get('additional_signals',[]))
        if current and public_signal_hub.public_url(current.get('source_url')):
            prior_evidence=public_signal_hub.merge_signals(prior_evidence,[{k:current.get(k,'') for k in (*evidence_fields,'first_seen_at','last_seen_at')}],'')
        lead['additional_signals']=public_signal_hub.merge_signals(prior_evidence,[evidence],datetime.now(LOCAL_TZ).isoformat(timespec='seconds'))
        if current and current.get('decision') in {'accepted','ignored'}:
            current['additional_signals']=lead['additional_signals']
            incoming_ids.add(str(current.get('id','')))
            merged_incoming.append(current)
            continue
        if current:
            decision = current.get("decision") or "pending"
            reactivated = decision == "watch" and lead.get("actionability") == "actionable" and not lead.get("background_only")
            if reactivated:
                now = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
                lead["decision"] = "pending"
                lead["status"] = "新触发待准入"
                lead["reactivated_from_watch_at"] = now
                lead["previous_watch_lead_id"] = str(current.get("id") or "")
                lead["watch_origin"] = {
                    "lead_id": str(current.get("id") or ""),
                    "title": str(current.get("title") or ""),
                    "source_url": str(current.get("source_url") or ""),
                    "watch_type": str(current.get("watch_type") or ""),
                    "watch_reason": str(current.get("watch_reason") or ""),
                    "next_trigger": str(current.get("next_trigger") or ""),
                    "watch_since": str(current.get("watch_since") or current.get("decided_at") or ""),
                }
                lead["history"] = [{
                    "at": now,
                    "action": "新触发回到准入判断",
                    "note": "核到 14-30 天有效窗口，等待用户重新判断是否准入。",
                }, *[item for item in current.get("history", []) if isinstance(item, dict)]][:10]
                for field in ("watch_type", "watch_reason", "next_trigger", "maintenance_mode", "execution_boundary", "watch_since"):
                    lead.pop(field, None)
            elif decision in {"accepted", "verify", "watch", "ignored"}:
                lead.update({
                    "status": current.get("status", lead.get("status", "")),
                    "decision": decision,
                    "decided_at": current.get("decided_at", ""),
                    "decision_note": current.get("decision_note", ""),
                    "added_customer_name": current.get("added_customer_name", ""),
                    "history": current.get("history", []),
                })
                for field in ("watch_type", "watch_reason", "next_trigger", "maintenance_mode", "execution_boundary", "watch_since"):
                    if current.get(field):
                        lead[field] = current[field]
        apply_prospecting_time_window(lead)
        if lead.get("id"):
            incoming_ids.add(str(lead["id"]))
        existing_by_company[company_key]=lead
        if lead.get('id'):existing_by_id[lead['id']]=lead
        merged_incoming=[item for item in merged_incoming if identity_key(item.get('company',''))!=company_key]
        merged_incoming.append(lead)

    remaining = [item for item in existing if str(item.get("id") or "") not in incoming_ids]
    for item in remaining:
        apply_prospecting_time_window(item)
    remaining.sort(
        key=lambda item: (
            0 if item.get("decision") in {"accepted", "verify", "watch", "ignored"} else 1,
            1 if item.get("actionability") == "stale" else 0,
            str(item.get("published_at") or ""),
        )
    )

    output: list[dict] = []
    seen_ids: set[str] = set()
    seen_companies: set[str] = set()
    for lead in [*[x for x in existing if x.get("decision") in {"accepted", "ignored"}], *merged_incoming, *remaining]:
        lead_id = str(lead.get("id") or "")
        company_key = identity_key(lead.get("company", ""))
        if lead_id and lead_id in seen_ids:
            continue
        if company_key and company_key not in {"待识别客户", "待核验客户"} and company_key in seen_companies:
            continue
        if lead_id:
            seen_ids.add(lead_id)
        if company_key and company_key not in {"待识别客户", "待核验客户"}:
            seen_companies.add(company_key)
        lead["rank"] = len(output) + 1
        output.append(lead)
        if len(output) >= limit:
            break
    return output


def prospecting_identity_key(value):
    return min(public_signal_hub.identity_aliases(value))


def prospecting_evidence_index(state):
    fields=('title','source_url','published_at','summary','impact_judgment','recommended_action','entry_strategy','next_step','deadline')
    index={}
    for item in state.get('leads',[]):
        for signal in [item,*item.get('additional_signals',[])]:
            if public_signal_hub.public_url(signal.get('source_url')):
                key=(prospecting_identity_key(item.get('company','')),public_signal_hub.signal_key(signal))
                index[key]=tuple(str(signal.get(k) or '') for k in fields)
    for name,record in state.get('customer_evidence',{}).items():
        for signal in record.get('signals',[]):
            index[(prospecting_identity_key(name),public_signal_hub.signal_key(signal))]=tuple(str(signal.get(k) or '') for k in fields)
    return index


def import_prospecting_payload(payload: dict) -> dict:
    with PROSPECTING_STATE_LOCK:
        return import_prospecting_payload_impl(payload)

def import_prospecting_payload_impl(payload: dict) -> dict:
    state = load_prospecting_state()
    run_id = str(payload.get('run_id') or '').strip()
    payload_source = payload.get('source') or 'codex_agent_search'
    previous_run = next((r for r in state.get('runs', []) if isinstance(r, dict) and run_id and r.get('run_id') == run_id and r.get('trigger') == payload_source), None)
    if previous_run and previous_run.get('status') in {'ok', 'no_change'}:
        count_fields = ('candidate_added_count', 'evidence_added_count', 'evidence_updated_count', 'retained_decision_count')
        return {'ok': True, 'replayed': True, 'imported_count': previous_run.get('result_count', 0), **{k: previous_run.get(k, 0) for k in count_fields}, 'prospecting': state}
    now = datetime.now(LOCAL_TZ)
    rows = payload.get("leads") or payload.get("items") or payload.get("signals") or []
    if not isinstance(rows, list):
        raise ValueError("leads must be list")

    old_evidence=prospecting_evidence_index(state)
    old_companies={prospecting_identity_key(x.get('company','')) for x in state.get('leads',[])}
    retained=0
    evidence_archive=state.setdefault('customer_evidence',{})
    leads = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or row.get("headline") or "").strip()
        if not title:
            continue
        company=str(row.get('company') or '').strip()
        protected=next((x for x in state.get('leads',[]) if x.get('decision') in {'accepted','ignored'} and public_signal_hub.same_customer(company,x.get('company',''),public_signal_hub.identity_aliases)),None)
        known=prospecting_existing_customer_match(company,title) if company else None
        if protected or known:
            if not public_signal_hub.public_url(row.get('source_url') or row.get('url')) or prospecting_is_youzan_existing_case(title) or prospecting_has_mismatch(title):continue
            if known and not protected:
                name=known['name']; prior=evidence_archive.get(name,{})
                signals=public_signal_hub.merge_signals(prior.get('signals',[]),[normalize_customer_intel_signal(row,name,1)],now.isoformat(timespec='seconds'))
                evidence_archive[name]={'customer':name,'updated_at':now.isoformat(timespec='seconds'),'signals':signals}
                continue
            retained+=1
        elif not prospecting_import_should_keep(row):
            continue
        lead = prospecting_import_row_to_lead(row, len(leads) + 1)
        for field in ('summary','impact_judgment','recommended_action'):lead[field]=str(row.get(field) or '')
        key = (min(public_signal_hub.identity_aliases(lead.get('company',''))),public_signal_hub.signal_key(lead))
        company_key = normalize_registry_customer_name(lead.get("company", ""))
        if key in seen:
            continue
        seen.add(key)
        leads.append(lead)
        if len(leads) >= 24:
            break

    if leads:
        state["leads"] = merge_prospecting_leads(state, leads)
    apply_prospecting_surface_limits(state)

    after_evidence=prospecting_evidence_index(state)
    added=sum(key not in old_evidence for key in after_evidence)
    updated=sum(key in old_evidence and value!=old_evidence[key] for key,value in after_evidence.items())
    counts={'candidate_added_count':len({prospecting_identity_key(x.get('company','')) for x in state.get('leads',[])}-old_companies),
            'evidence_added_count':added,'evidence_updated_count':updated,'retained_decision_count':retained}
    stored_count=added+updated
    task = dict(state.get("public_task") or {})
    has_zhiliao_leads = any(
        isinstance(item, dict) and item.get("source_provider") == "知了标讯"
        for item in state.get("leads", [])
    )
    task.update({
        "enabled": True,
        "schedule": "每天 06:00",
        "timezone": "Asia/Shanghai",
        "rule": default_prospecting_state()["task"]["rule"],
        "last_run_at": now.isoformat(timespec="seconds"),
        "last_run_status": "failed" if payload.get("status") == "failed" else "ok" if stored_count else "no_change" if payload.get("checked_queries") or leads else "no_import",
        "last_run_error": str(payload.get("error") or "搜索未完成")[:500] if payload.get("status") == "failed" else "" if stored_count or leads or payload.get("checked_queries") else "没有搜索覆盖回执，不能认定无新增",
        "next_run_at": prospecting_next_run_at(now, now.isoformat(timespec="seconds")),
        "searched_queries": payload.get("checked_queries", []),
        "query_groups": [
            {"id": group["id"], "label": group["label"], "reason": group["reason"]}
            for group in PROSPECTING_QUERY_GROUPS
        ],
        "source": "combined" if has_zhiliao_leads else payload_source,
        "source_label": "知了标讯 + AI 公开信号" if has_zhiliao_leads else "AI 公开信号",
        "scan_in_progress": False,
    })
    state["public_task"] = task
    coverage = {key: payload.get(key, []) if isinstance(payload.get(key), list) else [] for key in ('checked_queries', 'coverage_notes', 'source_links', 'reviewed_exclusions')}
    state["public_receipt"] = {"run_id":run_id,"run_date":str(payload.get("run_date") or now.date().isoformat()),"at":now.isoformat(timespec="seconds"),"checked_at":str(payload.get('checked_at') or ''),"scope":str(payload.get('scope') or ''),"imported_count":stored_count,**counts,**coverage,"status":task["last_run_status"]}
    state["summary"] = summarize_prospecting_state(state, len(leads))
    state["runs"] = [{
        "at": now.isoformat(timespec="seconds"),
        "trigger": payload_source,
        "status": task["last_run_status"],
        "result_count": stored_count,
        "run_id":str(payload.get("run_id") or ""),
        **counts,
        **coverage,
    }, *[item for item in state.get("runs", []) if isinstance(item, dict)]][:10]
    save_prospecting_state(state)
    return {"ok": True, "imported_count": stored_count, **counts, "prospecting": state}


def summarize_prospecting_state(state: dict, last_result_count: int | None = None) -> dict:
    leads = state.get("leads") if isinstance(state.get("leads"), list) else []
    pending_count = sum(1 for item in leads if item.get("decision", "pending") == "pending")
    verify_count = sum(1 for item in leads if item.get("decision") == "verify")
    stale_count = sum(1 for item in leads if item.get("decision") == "stale" or item.get("actionability") == "stale")
    watch_count = sum(1 for item in leads if item.get("user_surface") == "watch")
    accepted_count = sum(1 for item in leads if item.get("decision") == "accepted")
    ignored_count = sum(1 for item in leads if item.get("decision") == "ignored")
    candidate_count = sum(1 for item in leads if item.get("user_surface") == "candidate")
    internal_review_count = sum(1 for item in leads if item.get("user_surface") == "internal_review")
    candidate_backlog_count = sum(1 for item in leads if item.get("user_surface") == "candidate_backlog")
    watch_backlog_count = sum(1 for item in leads if item.get("user_surface") == "watch_backlog")
    previous = state.get("summary") if isinstance(state.get("summary"), dict) else {}
    return {
        "lead_count": len(leads),
        "pending_count": pending_count,
        "verify_count": verify_count,
        "stale_count": stale_count,
        "watch_count": watch_count,
        "accepted_count": accepted_count,
        "ignored_count": ignored_count,
        "candidate_count": candidate_count,
        "internal_review_count": internal_review_count,
        "candidate_backlog_count": candidate_backlog_count,
        "watch_backlog_count": watch_backlog_count,
        "last_result_count": last_result_count if last_result_count is not None else previous.get("last_result_count", len(leads)),
    }


def scan_zhiliao_tenders(state: dict) -> tuple[list[dict], dict]:
    today = datetime.now(LOCAL_TZ).date()
    query_payload = {
        "keywords": list(ZLBX_TENDER_KEYWORDS),
        "match_modes": ["sm", "title"],
        "exclude_keywords": list(ZLBX_EXCLUDE_KEYWORDS),
        "bid_type": "招标",
        "bid_process": [1, 2, 4],
        "begin_date": (today - timedelta(days=ZLBX_RECENT_SEARCH_DAYS)).isoformat(),
        "end_date": today.isoformat(),
        "page": 1,
        "page_size": 50,
        "sort_field": "pub_time",
        "sort_order": "desc",
    }
    search_result = zlbx_post("query_bids_advanced", query_payload)
    data = search_result.get("data") if isinstance(search_result.get("data"), dict) else {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    known_bid_ids = {
        str(item.get("bid_id"))
        for item in state.get("leads", [])
        if isinstance(item, dict) and item.get("bid_id") is not None and item.get("decision") not in {"verify", "pending"}
    }

    candidates: list[tuple[int, dict]] = []
    seen_candidates: set[str] = set()
    for row in items:
        if not isinstance(row, dict):
            continue
        score = prospecting_tender_candidate_score(row)
        if score < 7:
            continue
        title = str(row.get("title") or "").strip()
        company = str(row.get("caller_name") or "").strip()
        if prospecting_existing_customer_match(company, title):
            continue
        candidate_key = normalize_registry_customer_name(company) or normalize_work_text(title)
        if not candidate_key or candidate_key in seen_candidates:
            continue
        seen_candidates.add(candidate_key)
        candidates.append((score, row))
    candidates.sort(key=lambda item: (item[0], str(item[1].get("pub_time") or "")), reverse=True)

    leads: list[dict] = []
    detail_errors: list[str] = []
    detail_calls = 0
    detail_units = 0.0
    skipped_known = 0
    for score, row in candidates:
        bid_id = row.get("bid_id")
        if bid_id is None:
            continue
        if bid_id is not None and str(bid_id) in known_bid_ids:
            skipped_known += 1
            continue
        if detail_calls >= ZLBX_DETAIL_LIMIT:
            break
        detail_calls += 1
        try:
            detail_result = zlbx_post("get_bid_detail", {"bid_id": bid_id})
        except RuntimeError as exc:
            detail_errors.append(str(exc))
            continue
        detail_units += float((detail_result.get("meta") or {}).get("cost_units") or 0)
        detail = detail_result.get("data") if isinstance(detail_result.get("data"), dict) else {}
        if not detail:
            continue
        lead_row = prospecting_tender_row(row, detail, len(leads) + 1, score)
        if not lead_row.get("company") or lead_row.get("company") in {"待识别客户", "待核验客户"}:
            continue
        leads.append(lead_row)

    if not leads and detail_errors and not skipped_known:
        raise RuntimeError(detail_errors[0])
    search_units = float((search_result.get("meta") or {}).get("cost_units") or 0)
    return leads, {
        "search_total": int(data.get("total") or len(items)),
        "searched_item_count": len(items),
        "candidate_count": len(candidates),
        "detail_count": detail_calls,
        "known_count": skipped_known,
        "cost_units": search_units + detail_units,
        "detail_error_count": len(detail_errors),
    }


def run_prospecting_scan(trigger: str = "scheduled") -> dict:
    if not PROSPECTING_SCAN_LOCK.acquire(blocking=False):
        state = load_prospecting_state()
        state["task"]["scan_in_progress"] = True
        return state
    PROSPECTING_STATE_LOCK.acquire()
    try:
        state = load_prospecting_state()
        started_at = datetime.now(LOCAL_TZ)
        last_run = parse_optional_local_datetime((state.get("task") or {}).get("last_run_at"))
        if (
            trigger == "manual"
            and last_run
            and started_at - last_run < timedelta(minutes=ZLBX_MANUAL_COOLDOWN_MINUTES)
            and (state.get("task") or {}).get("source") in {"zhiliao_tender_search", "combined"}
        ):
            state["task"]["scan_in_progress"] = False
            state["task"]["manual_cooldown_seconds"] = max(
                0,
                int((timedelta(minutes=ZLBX_MANUAL_COOLDOWN_MINUTES) - (started_at - last_run)).total_seconds()),
            )
            return state
        state["task"]["scan_in_progress"] = True
        state["task"]["last_run_status"] = "running"
        state["task"]["last_run_error"] = ""
        save_prospecting_state(state)
        try:
            rows, scan_meta = scan_zhiliao_tenders(state)
            latest_state = load_prospecting_state()
            incoming = [
                prospecting_import_row_to_lead(row, index + 1)
                for index, row in enumerate(rows)
                if prospecting_import_should_keep(row)
            ]
            if incoming:
                latest_state["leads"] = merge_prospecting_leads(latest_state, incoming)
            apply_prospecting_surface_limits(latest_state)
            status = "ok" if incoming or scan_meta.get("known_count") else "no_result"
            error = ""
        except Exception as exc:
            latest_state = load_prospecting_state()
            incoming = []
            scan_meta = {}
            status = "search_unavailable"
            error = str(exc)[:260]

        finished_at = datetime.now(LOCAL_TZ)
        task = latest_state.get("task") or {}
        task_update = {
            "enabled": True,
            "schedule": "每天 06:00",
            "timezone": "Asia/Shanghai",
            "rule": default_prospecting_state()["task"]["rule"],
            "last_attempt_at": finished_at.isoformat(timespec="seconds"),
            "last_run_status": status,
            "last_run_error": error,
            "searched_queries": ["近21天公开招采", "会员 / CRM / 私域 / 小程序商城 / 企微 / 即时零售"],
            "query_groups": [
                {"id": group["id"], "label": group["label"], "reason": group["reason"]}
                for group in PROSPECTING_QUERY_GROUPS
            ],
            "source": "zhiliao_tender_search",
            "source_label": "知了标讯",
            "scan_in_progress": False,
            "scan_meta": scan_meta,
        }
        if status == "search_unavailable":
            retry_at = finished_at + timedelta(minutes=30)
            task_update["retry_after"] = retry_at.isoformat(timespec="seconds")
            task_update["next_run_at"] = retry_at.isoformat(timespec="seconds")
        else:
            task_update["last_run_at"] = finished_at.isoformat(timespec="seconds")
            task_update["retry_after"] = ""
            task_update["next_run_at"] = prospecting_next_run_at(
                finished_at,
                finished_at.isoformat(timespec="seconds"),
            )
        task.update(task_update)
        latest_state["task"] = task
        latest_state["summary"] = summarize_prospecting_state(latest_state, len(incoming))
        latest_state["runs"] = [{
            "at": finished_at.isoformat(timespec="seconds"),
            "trigger": trigger,
            "source": "zhiliao_tender_search",
            "status": status,
            "result_count": len(incoming),
            "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
            **scan_meta,
        }, *[item for item in latest_state.get("runs", []) if isinstance(item, dict)]][:10]
        save_prospecting_state(latest_state)
        return latest_state
    finally:
        PROSPECTING_STATE_LOCK.release()
        PROSPECTING_SCAN_LOCK.release()


def prospecting_due(state: dict) -> bool:
    task = state.get("task") or {}
    if task.get("enabled") is False:
        return False
    now = datetime.now(LOCAL_TZ)
    retry_after = parse_optional_local_datetime(task.get("retry_after"))
    if retry_after and now < retry_after:
        return False
    today_six = prospecting_today_six(now)
    last_run = parse_optional_local_datetime(task.get("last_run_at"))
    already_ran_today = bool(last_run and last_run.date() == now.date() and last_run >= today_six)
    return now >= today_six and not already_ran_today


def get_prospecting_payload(refresh_due: bool = True) -> dict:
    state = load_prospecting_state()
    if refresh_due and prospecting_due(state):
        state = run_prospecting_scan("scheduled")
    apply_prospecting_surface_limits(state)
    state["summary"] = summarize_prospecting_state(state)
    state["ok"] = True
    return state


def markdown_table_cell(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("|", "/")).strip()


def normalize_registry_customer_name(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value or "")
        .replace("（", "(")
        .replace("）", ")")
        .replace("有限责任公司", "")
        .replace("股份有限公司", "")
        .replace("有限公司", "")
        .replace("集团", "")
        .replace("/", " "),
    ).strip()


def client_registry_has_customer(name: str) -> bool:
    normalized = normalize_registry_customer_name(name)
    if not normalized:
        return False
    customers = parse_client_registry()
    for bucket_items in customers.values():
        for item in bucket_items:
            item_name = normalize_registry_customer_name(item.get("name", ""))
            if item_name and (item_name == normalized or item_name in normalized or normalized in item_name):
                return True
    return False


def append_prospect_to_client_registry(lead: dict) -> dict:
    company = markdown_table_cell(lead.get("company") or lead.get("title") or "待核验客户")
    if client_registry_has_customer(company):
        return {"ok": True, "status": "already_exists", "customer": company}

    text = read_text(CLIENT_REGISTRY)
    if "## 🟡 潜在目标" not in text:
        return {"ok": False, "status": "missing_section", "customer": company}

    today = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
    source = markdown_table_cell(lead.get("source_url") or lead.get("title") or "公开搜索")
    signal_type = markdown_table_cell(lead.get("signal_type") or "公开信号")
    note = markdown_table_cell(
        f"搜客线索（{today}，{signal_type}）：{lead.get('title') or company}；来源：{source}；待确认规模、预算窗口和对接人"
    )
    new_row = f"| {company} | P2 | {note} |"

    lines = text.splitlines()
    marker_index = next((idx for idx, line in enumerate(lines) if line.strip() == "## 🟡 潜在目标（有研究、未开始正式谈）"), -1)
    if marker_index < 0:
        marker_index = next((idx for idx, line in enumerate(lines) if line.strip().startswith("## 🟡 潜在目标")), -1)
    if marker_index < 0:
        return {"ok": False, "status": "missing_section", "customer": company}

    next_section = next((idx for idx in range(marker_index + 1, len(lines)) if lines[idx].startswith("## ") and idx > marker_index), len(lines))
    insert_at = next_section
    for idx in range(marker_index + 1, next_section):
        line = lines[idx].strip()
        if line.startswith("|") and "---" not in line and "客户" not in line:
            insert_at = idx + 1
    lines.insert(insert_at, new_row)
    CLIENT_REGISTRY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "status": "added", "customer": company}


def prospect_admission_missing(lead: dict) -> list[str]:
    missing: list[str] = []
    source_url = str(lead.get("source_url") or lead.get("url") or "").strip()
    if not source_url.startswith(("http://", "https://")):
        missing.append("真实信源")
    if not str(lead.get("purchase_signal") or lead.get("title") or "").strip():
        missing.append("业务触发")
    if not str(lead.get("entry_strategy") or lead.get("youzan_fit") or "").strip():
        missing.append("业务平台切口")
    if str(lead.get("actionability") or "") in {"stale", "needs_time_evidence"} or str(lead.get("decision") or "") == "stale":
        missing.append("有效时间窗口")
    return missing


def update_prospecting_lead_impl(payload: dict) -> dict:
    lead_id = str(payload.get("id", "")).strip()
    target = str(payload.get("target", "")).strip()
    note = str(payload.get("note", "")).strip()
    if not lead_id:
        raise ValueError("missing lead id")
    status_map = {
        "accept": ("accepted", "已列明", "列明"),
        "verify": ("verify", "待 AI 补证据", "AI 补证据"),
        "watch": ("watch", "观察中", "观察"),
        "ignore": ("ignored", "已剔除", "剔除"),
    }
    if target not in status_map:
        raise ValueError("unknown prospecting target")

    state = load_prospecting_state()
    leads = state.get("leads") if isinstance(state.get("leads"), list) else []
    lead = next((item for item in leads if isinstance(item, dict) and item.get("id") == lead_id), None)
    if not lead:
        raise ValueError("lead not found")
    if lead.get("decision") == "accepted" and target != "accept":
        raise ValueError("已准入客户必须在正式账户中调整状态，不能退回候选旁路")
    if target == "accept" and lead.get("decision") == "accepted":
        existing = next((a for a in account_store_rows() if a.get("id") == lead.get("account_id")), None)
        if existing:
            return {"ok": True, "lead": lead, "prospecting": state, "customer_pool": {"ok": True, "status": "already_admitted", "account_id": existing["id"], "customer": existing["name"], "message": "已在正式账户中，沿用当前阶段和跟进状态"}}
    if target == "accept":
        lead = apply_prospecting_time_window(lead)
        missing = prospect_admission_missing(lead)
        if prospecting_time_window(lead).get("actionability") != "actionable": missing.append("当前14–30天有效准备窗口")
        if missing:
            raise ValueError(f"准入前还缺：{'、'.join(missing)}")

    decision, status, action_label = status_map[target]
    now = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
    lead["decision"] = decision
    lead["status"] = status
    lead["decided_at"] = now
    lead["decision_note"] = note
    if target == "watch":
        lead.update(prospecting_watch_profile({
            **lead,
            "watch_type": strip_html(str(payload.get("watch_type") or lead.get("watch_type") or "").strip()),
            "watch_reason": strip_html(str(payload.get("watch_reason") or lead.get("watch_reason") or "").strip()),
            "next_trigger": strip_html(str(payload.get("next_trigger") or lead.get("next_trigger") or "").strip()),
        }))
    lead["user_surface"] = prospecting_user_surface(lead)
    lead.setdefault("history", [])
    lead["history"] = [{
        "at": now,
        "action": action_label,
        "note": note,
    }, *[item for item in lead.get("history", []) if isinstance(item, dict)]][:10]

    customer_pool_result = None
    if target == "accept":
        account = account_from_prospecting_lead(lead)
        saved_account = upsert_account_store(
            account,
            source_kind="workbench_ai_admission",
            sync_status="local_only",
        )
        lead["account_id"] = saved_account.get("id", "")
        lead["added_customer_name"] = saved_account.get("name", lead.get("company", ""))
        customer_pool_result = {
            "ok": True,
            "status": "workbench_added",
            "customer": lead["added_customer_name"],
            "account_id": lead["account_id"],
            "message": "已直接进入工作台账户主账本",
        }
        customer_pool_result["knowledge_registry"] = {"ok": True, "status": "unchanged", "message": "工作台准入保存在正式账户主账本；客户登记和CRM保持各自确认来源"}

    state["leads"] = leads
    apply_prospecting_surface_limits(state)
    state["summary"] = summarize_prospecting_state(state)
    save_prospecting_state(state)
    return {
        "ok": True,
        "lead": lead,
        "prospecting": state,
        "customer_pool": customer_pool_result,
    }


def update_prospecting_lead(payload: dict) -> dict:
    with PROSPECTING_STATE_LOCK:
        return update_prospecting_lead_impl(payload)


ACCOUNT_STAGE_DEFINITIONS = [
    {
        "id": "qualify",
        "label": "判断切口",
        "short": "切口",
        "description": "确认规模证据、业务触发、业务平台可进入的场景。",
    },
    {
        "id": "path",
        "label": "进入路径",
        "short": "路径",
        "description": "找到供应商、渠道、内部部门或已有系统边界。",
    },
    {
        "id": "contact",
        "label": "客户接触",
        "short": "接触",
        "description": "开始约访、调研、需求确认或攻坚沟通。",
    },
    {
        "id": "opportunity",
        "label": "商机推进",
        "short": "商机",
        "description": "围绕预算、方案、PoC、采购路径和合同推进。",
    },
]


def account_cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "；".join(filter(None, [account_cell_text(item) for item in value]))
    if isinstance(value, dict):
        for key in ("text", "name", "title", "value", "link", "url"):
            if value.get(key):
                return account_cell_text(value.get(key))
        return "；".join(filter(None, [account_cell_text(item) for item in value.values()]))
    return strip_html(str(value)).strip()


def lark_base_record_rows(table_id: str, *, view_id: str = "", limit: int = 200) -> list[dict]:
    args = [
        LARK_CLI_BIN,
        "base",
        "+record-list",
        "--as",
        "user",
        "--base-token",
        ACCOUNT_ADVANCEMENT_BASE_TOKEN,
        "--table-id",
        table_id,
        "--limit",
        str(limit),
        "--format",
        "json",
    ]
    if view_id:
        args.extend(["--view-id", view_id])
    payload = run_json_command(args, timeout=35)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    fields = data.get("fields") if isinstance(data.get("fields"), list) else []
    rows = data.get("data") if isinstance(data.get("data"), list) else []
    record_ids = data.get("record_id_list") if isinstance(data.get("record_id_list"), list) else []
    normalized: list[dict] = []
    for index, row in enumerate(rows):
        if not isinstance(row, list):
            continue
        item = {str(field): account_cell_text(row[pos] if pos < len(row) else "") for pos, field in enumerate(fields)}
        item["_record_id"] = str(record_ids[index]) if index < len(record_ids) else f"{table_id}-{index}"
        normalized.append(item)
    return normalized


def compact_account_name(value: str) -> str:
    text = account_cell_text(value)
    text = re.sub(r"\[[^\]]+\]\([^)]+\)", "", text)
    text = re.sub(r"[（(].*?[）)]", "", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[／/、|,，;；·]", "", text)
    for suffix in (
        "股份有限公司",
        "有限责任公司",
        "有限公司",
        "集团有限公司",
        "科技有限公司",
        "汽车销售有限公司",
        "销售有限公司",
        "新能源科技",
        "汽车科技",
        "汽车",
        "集团",
        "公司",
    ):
        text = text.replace(suffix, "")
    return text


def account_name_parts(value: str) -> list[str]:
    raw = account_cell_text(value)
    parts = [compact_account_name(part) for part in re.split(r"[／/、|,，;；]", raw)]
    return [part for part in parts if len(part) >= 2]


def account_names_match(account_name: str, channel_name: str) -> bool:
    account_key = compact_account_name(account_name)
    channel_key = compact_account_name(channel_name)
    if not account_key or not channel_key:
        return False
    if channel_key in account_key or account_key in channel_key:
        return True
    return any(part in account_key for part in account_name_parts(channel_name))


def priority_rank(priority: str) -> float:
    text = account_cell_text(priority).upper()
    match = re.search(r"P\s*(\d+(?:\.\d+)?)", text)
    if not match:
        return 9.0
    try:
        return float(match.group(1))
    except ValueError:
        return 9.0


def normalize_channel_record(record: dict) -> dict:
    name = record.get("供应商/渠道", "")
    customer = record.get("客户主体", "")
    return {
        "id": record.get("_record_id") or safe_filename(f"{customer}-{name}", "channel"),
        "customer": customer,
        "industry": record.get("行业", ""),
        "name": name,
        "signal": record.get("合作/项目线索", ""),
        "conflict": record.get("与业务平台冲突判断", ""),
        "value": record.get("渠道价值", ""),
        "status": record.get("验证状态", ""),
        "source": record.get("来源链接", ""),
        "next_action": record.get("下一步动作", ""),
        "updated_at": record.get("最近更新时间", ""),
    }


def account_deadline_matches(account_name: str, todos: list[dict]) -> list[dict]:
    matches = []
    for todo in todos:
        if str(todo.get("source_type") or todo.get("source_scope") or "") == "transcript_intake":
            continue
        customer = str(todo.get("customer") or todo.get("project") or todo.get("name") or "")
        if customer and (account_names_match(account_name, customer) or account_names_match(customer, account_name)):
            matches.append(todo)
    return matches


def infer_account_stage(account: dict) -> str:
    text = " ".join(
        [
            account.get("status_note", ""),
            account.get("recent_signal", ""),
            account.get("opportunity", ""),
            account.get("suggested_play", ""),
            account.get("cut_in", ""),
        ]
    )
    if any(marker in text for marker in ("报价", "预算", "方案", "PoC", "POC", "采购", "合同", "签约")):
        return "opportunity"
    if any(marker in text for marker in ("活跃跟进", "攻坚", "沟通纪要", "正式接触", "需求")):
        return "contact"
    if account.get("channel_count", 0) > 0:
        return "path"
    if account.get("cut_in") and (account.get("recent_signal") or account.get("opportunity")):
        return "qualify"
    return "qualify"


def infer_account_time_state(deadlines: list[dict], now: datetime | None = None) -> dict:
    current = now or datetime.now(LOCAL_TZ)
    parsed: list[tuple[datetime, dict]] = []
    for item in deadlines:
        try:
            parsed.append((parse_optional_local_datetime(str(item.get("deadline") or "")), item))
        except (TypeError, ValueError):
            continue
    if not parsed:
        return {"id": "none", "label": "未安排提醒", "deadline": ""}
    parsed.sort(key=lambda pair: pair[0])
    deadline, item = parsed[0]
    minutes = int((deadline - current).total_seconds() // 60)
    if minutes < 0:
        label = f"已超期 {max(1, abs(minutes) // 1440)} 天" if abs(minutes) >= 1440 else f"已超期 {abs(minutes)} 分钟"
        state_id = "overdue"
    elif minutes <= ACTIONABLE_SCHEDULE_WINDOW_MINUTES:
        label = "现在要推进" if minutes <= 0 else f"{minutes} 分钟后到点"
        state_id = "due"
    elif minutes < 1440:
        label = f"{max(1, minutes // 60)} 小时后"
        state_id = "scheduled"
    else:
        label = f"{minutes // 1440} 天后"
        state_id = "scheduled"
    return {
        "id": state_id,
        "label": label,
        "deadline": deadline.isoformat(timespec="minutes"),
        "todo_id": item.get("id", ""),
    }


def account_revenue_verified(value) -> bool:
    evidence = account_cell_text(value).lower()
    if not evidence:
        return False
    return not any(marker in evidence for marker in ("pending_public_lookup", "待补", "待查", "未核验", "none"))


def account_gap_labels(account: dict) -> list[str]:
    gaps: list[str] = []
    if not account_revenue_verified(account.get("revenue_evidence")):
        gaps.append("规模证据待补")
    if not account.get("channel_count"):
        gaps.append("渠道路径待查")
    status = f"{account.get('status_note', '')} {account.get('opportunity', '')}"
    if any(marker in status for marker in ("未正式接触", "需二次调研", "潜在目标", "观察")):
        gaps.append("客户侧负责人待确认")
    if not account.get("source"):
        gaps.append("来源链接待补")
    if account.get("channel_count") and any(marker in account.get("suggested_play", "") for marker in ("先找", "打听", "确认", "问清")):
        gaps.append("渠道人待验证")
    return gaps[:4]


def account_store_connection() -> sqlite3.Connection:
    WORKBENCH_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(ACCOUNT_STORE_FILE, timeout=15)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_account_store() -> None:
    global ACCOUNT_STORE_INITIALIZED
    if ACCOUNT_STORE_INITIALIZED:
        return
    with ACCOUNT_STORE_LOCK, account_store_connection() as connection:
        if ACCOUNT_STORE_INITIALIZED:
            return
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                name_key TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                lifecycle_stage TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_external_id TEXT NOT NULL DEFAULT '',
                sync_status TEXT NOT NULL DEFAULT 'local',
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS account_store_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS idempotency_results (
                request_id TEXT PRIMARY KEY,
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        try:
            ACCOUNT_STORE_FILE.chmod(0o600)
        except OSError:
            pass
        ACCOUNT_STORE_INITIALIZED = True


def account_store_name_key(name: str) -> str:
    return compact_account_name(name) or safe_filename(name, "account").lower()


def merge_account_payload(existing: dict, incoming: dict) -> dict:
    merged = dict(existing)
    for key, value in incoming.items():
        if value not in (None, "", [], {}):
            merged[key] = value
        elif key not in merged:
            merged[key] = value
    return merged


def upsert_account_store(account: dict, *, source_kind: str, sync_status: str = "local") -> dict:
    initialize_account_store()
    name = account_cell_text(account.get("name") or account.get("company"))
    if not name:
        raise ValueError("账户缺少客户名称")
    name_key = account_store_name_key(name)
    now = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
    incoming_stage = str(account.get("stage") or "qualify")
    valid_stages = {item["id"] for item in ACCOUNT_STAGE_DEFINITIONS}
    if incoming_stage not in valid_stages:
        incoming_stage = "qualify"

    with ACCOUNT_STORE_LOCK, account_store_connection() as connection:
        row = connection.execute("SELECT * FROM accounts WHERE name_key = ?", (name_key,)).fetchone()
        existing = json.loads(row["payload_json"]) if row else {}
        if row and source_kind == "workbench_ai_admission":
            return {**existing, "id": row["id"], "name": row["name"], "stage": row["lifecycle_stage"], "record_source": row["source_kind"], "sync_status": row["sync_status"]}
        merged = merge_account_payload(existing, account)
        account_id = str(row["id"] if row else account.get("id") or f"account-{uuid.uuid5(uuid.NAMESPACE_URL, name_key).hex[:14]}")
        existing_source = str(row["source_kind"]) if row else ""
        effective_source = existing_source if existing_source.startswith("workbench") and source_kind == "feishu_import" else source_kind
        effective_stage = str(row["lifecycle_stage"]) if row and source_kind in {"feishu_import", "workbench_legacy_migration"} else incoming_stage
        effective_sync = str(row["sync_status"]) if row and effective_source.startswith("workbench") and source_kind == "feishu_import" else sync_status
        merged.update({
            "id": account_id,
            "name": name,
            "stage": effective_stage,
            "record_source": effective_source,
            "sync_status": effective_sync,
        })
        merged.setdefault("account_state", "active")
        connection.execute(
            """
            INSERT INTO accounts (
                id, name_key, name, lifecycle_stage, source_kind, source_external_id,
                sync_status, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name_key) DO UPDATE SET
                name = excluded.name,
                lifecycle_stage = excluded.lifecycle_stage,
                source_kind = excluded.source_kind,
                source_external_id = excluded.source_external_id,
                sync_status = excluded.sync_status,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (
                account_id,
                name_key,
                name,
                effective_stage,
                effective_source,
                str(account.get("source_external_id") or account.get("id") or ""),
                effective_sync,
                json.dumps(merged, ensure_ascii=False),
                str(row["created_at"]) if row else now,
                now,
            ),
        )
    return merged


def account_from_prospecting_lead(lead: dict) -> dict:
    company = account_cell_text(lead.get("company") or lead.get("title") or "待核验客户")
    revenue = account_cell_text(lead.get("revenue_evidence"))
    source_url = account_cell_text(lead.get("source_url") or lead.get("url"))
    title = account_cell_text(lead.get("title"))
    next_action = account_cell_text(
        lead.get("entry_strategy")
        or lead.get("suggested_play")
        or lead.get("recommendation")
        or f"确认 {company} 的采购负责人、参与窗口和业务平台切入方式。"
    )
    account = {
        "id": f"prospect-{lead.get('id') or uuid.uuid5(uuid.NAMESPACE_URL, company).hex[:12]}",
        "name": company,
        "priority": "P1" if lead.get("actionability") == "actionable" or lead.get("icp_tier") in {"A", "S"} else "P2",
        "priority_rank": 1.0 if lead.get("actionability") == "actionable" else 2.0,
        "industry": account_cell_text(lead.get("industry") or lead.get("category")),
        "source_type": "AI候选准入",
        "source": source_url,
        "updated_at": str(lead.get("decided_at") or datetime.now(LOCAL_TZ).date().isoformat()),
        "dedupe": account_cell_text(lead.get("dedupe") or "已由工作台执行准入判断"),
        "status_note": "已由你从 AI 候选池准入，进入正式账户推进。",
        "recent_signal": title,
        "opportunity": account_cell_text(lead.get("why_now") or lead.get("fit_reason") or lead.get("purchase_signal") or title),
        "suggested_play": next_action,
        "cut_in": account_cell_text(lead.get("youzan_fit") or lead.get("entry_strategy")),
        "revenue_evidence": revenue,
        "channels": [],
        "channel_count": 0,
        "deadline_count": 0,
        "deadlines": [],
        "stage": "qualify",
        "account_state": "active",
        "next_action": next_action,
        "next_action_source": "AI候选准入",
        "tender_deadline": account_cell_text(lead.get("deadline")),
        "admission": {
            "lead_id": lead.get("id", ""),
            "decided_at": lead.get("decided_at", ""),
            "decision_note": lead.get("decision_note", ""),
            "source_provider": lead.get("source_provider", ""),
        },
    }
    account["gaps"] = account_gap_labels(account)
    return account


def account_store_count() -> int:
    initialize_account_store()
    with ACCOUNT_STORE_LOCK, account_store_connection() as connection:
        row = connection.execute("SELECT COUNT(*) AS count FROM accounts").fetchone()
    return int(row["count"] if row else 0)


def account_store_set_meta(key: str, value: str) -> None:
    initialize_account_store()
    with ACCOUNT_STORE_LOCK, account_store_connection() as connection:
        connection.execute(
            "INSERT INTO account_store_meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def account_store_meta() -> dict:
    initialize_account_store()
    with ACCOUNT_STORE_LOCK, account_store_connection() as connection:
        rows = connection.execute("SELECT key, value FROM account_store_meta").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def account_store_rows() -> list[dict]:
    initialize_account_store()
    with ACCOUNT_STORE_LOCK, account_store_connection() as connection:
        rows = connection.execute(
            "SELECT payload_json, lifecycle_stage, source_kind, sync_status FROM accounts ORDER BY name"
        ).fetchall()
    accounts: list[dict] = []
    for row in rows:
        try:
            account = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            continue
        account["stage"] = row["lifecycle_stage"] if row["lifecycle_stage"] in {item["id"] for item in ACCOUNT_STAGE_DEFINITIONS} else "qualify"
        account["record_source"] = row["source_kind"]
        account["sync_status"] = row["sync_status"]
        account.setdefault("account_state", "active")
        accounts.append(account)
    return accounts


def account_store_match(customer: str, accounts: list[dict] | None = None) -> dict | None:
    if not customer:
        return None
    candidates = accounts if accounts is not None else account_store_rows()
    exact_key = account_store_name_key(customer)
    exact = next((item for item in candidates if account_store_name_key(item.get("name", "")) == exact_key), None)
    if exact:
        return exact
    return next(
        (
            item for item in candidates
            if account_names_match(str(item.get("name") or ""), customer)
            or account_names_match(customer, str(item.get("name") or ""))
        ),
        None,
    )


def canonical_account_id(customer: str, accounts: list[dict] | None = None) -> str:
    matched = account_store_match(customer, accounts)
    return str(matched.get("id") or "") if matched else ""


def account_stage_gate(account: dict, target_stage: str) -> list[str]:
    current = str(account.get("stage") or "qualify")
    if current == "qualify" and target_stage == "path":
        checks = [("revenue_evidence", "规模证据"), ("source", "来源链接"), ("cut_in", "业务平台切口")]
    elif current == "path" and target_stage == "contact":
        checks = [("channel_count", "进入渠道"), ("next_action", "明确下一步")]
    elif current == "contact" and target_stage == "opportunity":
        checks = [("opportunity", "机会判断"), ("next_action", "明确下一步")]
    else:
        checks = []
    missing = []
    for key, label in checks:
        valid = account_revenue_verified(account.get(key)) if key == "revenue_evidence" else bool(account.get(key))
        if not valid:
            missing.append(label)
    return missing


def advance_account_stage(payload: dict) -> dict:
    account_id = strip_html(str(payload.get("id", "")).strip())
    target_stage = strip_html(str(payload.get("target_stage", "")).strip())
    override_reason = strip_html(str(payload.get("override_reason", "")).strip())
    valid_stages = [item["id"] for item in ACCOUNT_STAGE_DEFINITIONS]
    if not account_id or target_stage not in valid_stages:
        raise ValueError("缺少账户或目标阶段")
    initialize_account_store()
    with ACCOUNT_STORE_LOCK, account_store_connection() as connection:
        row = connection.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not row:
            raise ValueError("没有找到这个正式账户")
        account = json.loads(row["payload_json"])
        if str(account.get("account_state") or "active") != "active":
            raise ValueError("只有推进中的账户可以更新生命周期阶段")
        current_stage = str(row["lifecycle_stage"] or "qualify")
        current_index = valid_stages.index(current_stage) if current_stage in valid_stages else 0
        target_index = valid_stages.index(target_stage)
        if target_index != current_index + 1:
            raise ValueError("账户只能按顺序推进到下一个阶段")
        account["stage"] = current_stage
        missing = account_stage_gate(account, target_stage)
        if missing and not override_reason:
            raise ValueError(f"推进前还缺：{'、'.join(missing)}")
        now = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
        history = account.get("stage_history") if isinstance(account.get("stage_history"), list) else []
        account["stage"] = target_stage
        account["stage_history"] = [
            {
                "from": current_stage,
                "to": target_stage,
                "at": now,
                "override_reason": override_reason,
            },
            *history,
        ][:20]
        account["updated_at"] = now[:10]
        connection.execute(
            "UPDATE accounts SET lifecycle_stage = ?, payload_json = ?, updated_at = ? WHERE id = ?",
            (target_stage, json.dumps(account, ensure_ascii=False), now, account_id),
        )
    return {"ok": True, "account": account, "message": f"已推进到 {next(item['label'] for item in ACCOUNT_STAGE_DEFINITIONS if item['id'] == target_stage)}"}


def update_account_evidence(payload: dict) -> dict:
    account_id = strip_html(str(payload.get("id", "")).strip())
    if not account_id:
        raise ValueError("缺少正式账户")
    allowed_fields = {
        "recent_signal": "近期触发",
        "revenue_evidence": "规模证据",
        "source": "来源链接",
        "cut_in": "业务平台切口",
        "opportunity": "机会判断",
        "next_action": "明确下一步",
        "owner": "客户侧负责人",
    }
    updates = {
        key: strip_html(str(payload.get(key, "")).strip())
        for key in allowed_fields
        if key in payload
    }
    channel_path = strip_html(str(payload.get("channel_path", "")).strip())
    if not any(updates.values()) and not channel_path:
        raise ValueError("请至少补充一项账户证据")
    initialize_account_store()
    with ACCOUNT_STORE_LOCK, account_store_connection() as connection:
        row = connection.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not row:
            raise ValueError("没有找到这个正式账户")
        account = json.loads(row["payload_json"])
        changed: list[str] = []
        for key, value in updates.items():
            if value:
                account[key] = value
                changed.append(allowed_fields[key])
        if channel_path:
            channels = account.get("channels") if isinstance(account.get("channels"), list) else []
            local_channel_id = f"workbench-path-{account_id}"
            local_channel = {
                "id": local_channel_id,
                "customer": account.get("name", ""),
                "name": channel_path,
                "status": "工作台补充",
                "value": "已确认的进入路径或负责人",
                "next_action": updates.get("next_action") or account.get("next_action", ""),
                "source": updates.get("source") or account.get("source", ""),
                "updated_at": datetime.now(LOCAL_TZ).date().isoformat(),
            }
            channels = [item for item in channels if isinstance(item, dict) and item.get("id") != local_channel_id]
            channels.append(local_channel)
            account["channels"] = channels
            account["channel_count"] = len(channels)
            changed.append("进入路径")
        now = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
        history = account.get("evidence_history") if isinstance(account.get("evidence_history"), list) else []
        account["evidence_history"] = [{"at": now, "changed": changed}, *history][:20]
        account["updated_at"] = now[:10]
        account["stage"] = str(row["lifecycle_stage"] or "qualify")
        connection.execute(
            "UPDATE accounts SET payload_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(account, ensure_ascii=False), now, account_id),
        )
    return {"ok": True, "account": account, "message": f"已补充：{'、'.join(changed)}"}


def update_account_state(payload: dict) -> dict:
    account_id = strip_html(str(payload.get("id", "")).strip())
    target_state = strip_html(str(payload.get("account_state", "")).strip())
    reason = strip_html(str(payload.get("reason", "")).strip())
    labels = {"active": "推进中", "paused": "已暂停", "won": "已成交", "lost": "已流失", "archived": "已归档"}
    if not account_id or target_state not in labels:
        raise ValueError("缺少账户或目标状态")
    if target_state in {"paused", "lost", "archived"} and not reason:
        raise ValueError("暂停、流失或归档时需要填写原因")
    initialize_account_store()
    with ACCOUNT_STORE_LOCK, account_store_connection() as connection:
        row = connection.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not row:
            raise ValueError("没有找到这个正式账户")
        account = json.loads(row["payload_json"])
        previous = str(account.get("account_state") or "active")
        now = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
        history = account.get("account_state_history") if isinstance(account.get("account_state_history"), list) else []
        account["account_state"] = target_state
        account["account_state_history"] = [{"from": previous, "to": target_state, "reason": reason, "at": now}, *history][:20]
        connection.execute(
            "UPDATE accounts SET payload_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(account, ensure_ascii=False), now, account_id),
        )
    return {"ok": True, "account": account, "message": f"账户状态已更新为{labels[target_state]}"}


def apply_receipt_to_account(account_id: str, customer: str, resolution: str, next_step: str, status: str, receipt_id: str, project_id: str = "", action_id: str = "") -> str:
    matched_id = account_id or canonical_account_id(customer)
    if not matched_id:
        return ""
    initialize_account_store()
    with ACCOUNT_STORE_LOCK, account_store_connection() as connection:
        row = connection.execute("SELECT * FROM accounts WHERE id = ?", (matched_id,)).fetchone()
        if not row:
            return ""
        account = json.loads(row["payload_json"])
        now = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
        account["recent_signal"] = resolution
        if "working_actions" not in account and account.get("next_action"):
            account["unmapped_next_action"] = account["next_action"]
            account["unmapped_next_action_source"] = account.get("next_action_source", "账户原记录")
        actions = dict(account.get("working_actions") or {})
        key = action_id or receipt_id
        if status in {"已处理", "已闭环"}:
            actions.pop(key, None)
        else:
            actions[key] = {"action_id": key, "project_id": project_id, "next_step": next_step, "status": status}
        account["working_actions"] = actions
        account["next_action"] = "；".join(filter(None, [account.get("unmapped_next_action", ""), *[a["next_step"] for a in actions.values() if a.get("next_step")]]))
        account["next_action_source"] = "同一行动记录汇总"
        history = account.get("interaction_history") if isinstance(account.get("interaction_history"), list) else []
        history = [item for item in history if isinstance(item, dict) and item.get("receipt_id") != receipt_id]
        account["interaction_history"] = [
            {
                "receipt_id": receipt_id,
                "project_id": project_id,
                "action_id": action_id,
                "status": status,
                "resolution": resolution,
                "next_step": next_step,
                "at": now,
            },
            *history,
        ][:30]
        account["updated_at"] = now[:10]
        connection.execute(
            "UPDATE accounts SET payload_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(account, ensure_ascii=False), now, matched_id),
        )
    return matched_id


def normalize_account_record(record: dict, channels: list[dict], deadlines: list[dict]) -> dict:
    name = record.get("客户主体", "")
    related_channels = [
        channel for channel in channels
        if account_names_match(name, channel.get("customer", ""))
    ]
    related_deadlines = account_deadline_matches(name, deadlines)
    account = {
        "id": record.get("_record_id") or safe_filename(name, "account"),
        "name": name,
        "priority": record.get("优先级", "") or "P?",
        "priority_rank": priority_rank(record.get("优先级", "")),
        "industry": record.get("行业", ""),
        "source_type": record.get("线索来源类型", ""),
        "source": record.get("来源链接", ""),
        "updated_at": record.get("最近更新时间", ""),
        "dedupe": record.get("查重结果", ""),
        "status_note": record.get("状态备注", ""),
        "recent_signal": record.get("近期动作/证据", ""),
        "opportunity": record.get("机会判断", ""),
        "suggested_play": record.get("建议打法", ""),
        "cut_in": record.get("业务平台切口", ""),
        "revenue_evidence": record.get("年营收/规模证据", ""),
        "channels": related_channels[:8],
        "channel_count": len(related_channels),
        "deadline_count": len(related_deadlines),
        "deadlines": related_deadlines[:4],
    }
    account["stage"] = infer_account_stage(account)
    account["time_state"] = infer_account_time_state(related_deadlines)
    account["gaps"] = account_gap_labels(account)
    if related_channels and related_channels[0].get("next_action"):
        account["next_action"] = related_channels[0]["next_action"]
        account["next_action_source"] = "供应商渠道表"
    else:
        account["next_action"] = account.get("suggested_play") or "补齐规模证据、渠道人和客户侧负责人后再生成今日行动。"
        account["next_action_source"] = "客户机会表"
    return account


def build_account_today_actions(accounts: list[dict]) -> list[dict]:
    candidates = sorted(accounts, key=lambda item: (item.get("priority_rank", 9), -item.get("channel_count", 0), item.get("name", "")))
    actions = []
    for account in candidates:
        if len(actions) >= 6:
            break
        if "已合作" in account.get("status_note", "") and "新机会" not in account.get("status_note", ""):
            continue
        actions.append(
            {
                "account_id": account.get("id"),
                "customer": account.get("name"),
                "priority": account.get("priority"),
                "title": account.get("next_action") or "补齐下一步动作",
                "source": account.get("next_action_source", "客户机会表"),
                "stage": account.get("stage"),
                "gaps": account.get("gaps", []),
                "write_policy": "只作为推进建议；确认下一步和时间后，通过销售捕捉或处理结果写入 Deadline / 飞书任务提醒。",
            }
        )
    return actions


def account_advancement_payload_from_lark() -> dict:
    raw_accounts = lark_base_record_rows(ACCOUNT_ADVANCEMENT_CUSTOMER_TABLE_ID, limit=200)
    raw_channels = lark_base_record_rows(
        ACCOUNT_ADVANCEMENT_CHANNEL_TABLE_ID,
        view_id=ACCOUNT_ADVANCEMENT_CHANNEL_VIEW_ID,
        limit=200,
    )
    channels = [normalize_channel_record(record) for record in raw_channels]
    deadline_items = risk_todos_payload().get("items", [])
    accounts = [normalize_account_record(record, channels, deadline_items) for record in raw_accounts if record.get("客户主体")]
    accounts.sort(key=lambda item: (item.get("priority_rank", 9), item.get("name", "")))
    stage_counts = {stage["id"]: 0 for stage in ACCOUNT_STAGE_DEFINITIONS}
    for account in accounts:
        stage_counts[account.get("stage", "qualify")] = stage_counts.get(account.get("stage", "qualify"), 0) + 1
    stages = [{**stage, "count": stage_counts.get(stage["id"], 0)} for stage in ACCOUNT_STAGE_DEFINITIONS]
    now = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
    payload = {
        "ok": True,
        "generated_at": now,
        "summary": {
            "account_count": len(accounts),
            "channel_count": len(channels),
            "deadline_account_count": sum(1 for item in accounts if item.get("deadline_count", 0) > 0),
            "gap_count": sum(len(item.get("gaps", [])) for item in accounts),
        },
        "source": {
            "status": "live",
            "label": "飞书多维表格实时读取",
            "customer_table": "50亿+客户主体机会表",
            "channel_table": "供应商渠道明细表",
            "generated_at": now,
            "write_policy": "读取飞书客户机会和渠道明细；不自动生成今日待办、不自动写入飞书日程。",
        },
        "methodology": [
            {
                "name": "目标账户 ABM",
                "rule": "先用规模、触发、行业和现有系统边界筛账户，避免只靠一个大项目支撑。",
            },
            {
                "name": "MEDDICC 轻量版",
                "rule": "每个客户至少补齐痛点/指标、决策链、采购路径、竞争或供应商路径、下一步。",
            },
            {
                "name": "渠道联合开门",
                "rule": "先找不冲突供应商和集成商确认系统归属，再决定直连客户还是联合进入。",
            },
        ],
        "public_paths": [
            {
                "name": "公开招投标/采购公告",
                "use": "每天补客户近期采购、续签、系统替换和中标供应商。",
                "target": "先写入客户机会表和供应商渠道表，不直接进今日队列。",
            },
            {
                "name": "财报/招股书/官方新闻",
                "use": "验证营收规模、业务动作和组织变化。",
                "target": "作为定级证据；未核验不参与高优先级判断。",
            },
            {
                "name": "供应商/集成商路径",
                "use": "找到云厂商、系统商、本地服务商和项目联系人。",
                "target": "确认是否利益一致、是否能带入、是否与业务平台冲突。",
            },
            {
                "name": "Sales Company Research",
                "use": "补行业地图、客户研究、可复用案例和资料来源。",
                "target": "沉淀成账户证据，不直接生成客户承诺。",
            },
            {
                "name": "Sales Tips",
                "use": "结合飞书日程和销售上下文提示今天值得尝试的销售动作。",
                "target": "只推荐下一步；需要你确认后才进入执行链。",
            },
        ],
        "reminder_policy": {
            "deadline": "未闭环事项通过处理结果或销售捕捉进入工作台 Deadline。",
            "feishu": "只有明确下一步和时间，并选择同步时，才创建飞书任务提醒。",
            "calendar": "飞书日程用于读取客户相关会议；常规分享、周会、培训、例会不进入今日队列。",
            "daily_report": "项目群日报只读，不自动生成销售风险或待办。",
        },
        "stages": stages,
        "accounts": accounts,
        "channels": channels,
        "today_actions": build_account_today_actions(accounts),
    }
    write_private_json(ACCOUNT_ADVANCEMENT_CACHE_FILE, payload)
    return payload


def import_account_payload_to_store(payload: dict, *, source_kind: str = "feishu_import") -> int:
    imported = 0
    for account in payload.get("accounts", []):
        if not isinstance(account, dict) or not account.get("name"):
            continue
        upsert_account_store(account, source_kind=source_kind, sync_status="imported")
        imported += 1
    if imported:
        account_store_set_meta("feishu_imported_at", datetime.now(LOCAL_TZ).isoformat(timespec="seconds"))
        account_store_set_meta("feishu_imported_count", str(imported))
    return imported


def backfill_accepted_prospects_to_account_store() -> int:
    state = load_prospecting_state()
    imported = 0
    for lead in state.get("leads", []):
        if not isinstance(lead, dict) or lead.get("decision") != "accepted":
            continue
        account = account_from_prospecting_lead(lead)
        saved = upsert_account_store(account, source_kind="workbench_ai_admission", sync_status="local_only")
        if not lead.get("account_id"):
            lead["account_id"] = saved.get("id", "")
            imported += 1
    if imported:
        save_prospecting_state(state)
    return imported


def backfill_active_projects_to_account_store() -> int:
    customers = parse_client_registry()
    todos = parse_todo_log()
    existing = account_store_rows()
    imported = 0
    for project in build_deal_board(customers, todos):
        matched = account_store_match(str(project.get("name") or ""), existing)
        if project.get("bucket") != "active" or (matched and matched.get("record_source") != "workbench_legacy_migration"):
            continue
        base = {
            "name": project.get("name", ""),
            "priority": project.get("priority", "P1"),
            "industry": project.get("industry", ""),
            "source_type": "工作台历史客户迁移",
            "source": "",
            "status_note": project.get("status", "活跃跟进"),
            "legacy_stage": project.get("stage", ""),
            "recent_signal": project.get("signal", ""),
            "opportunity": project.get("note", ""),
            "suggested_play": project.get("next_action", ""),
            "cut_in": project.get("next_action", ""),
            "revenue_evidence": project.get("amount", ""),
            "owner": project.get("owner", ""),
            "channels": [],
            "channel_count": 0,
            "stage": "opportunity" if project.get("amount") or "已合作" in str(project.get("stage") or "") else "contact",
            "account_state": "active",
            "next_action": project.get("next_action", ""),
            "next_action_source": "工作台历史客户",
        }
        saved = upsert_account_store(base, source_kind="workbench_legacy_migration", sync_status="local")
        if matched:
            existing = [saved if item.get("id") == matched.get("id") else item for item in existing]
        else:
            existing.append(saved)
            imported += 1
    if imported:
        account_store_set_meta("legacy_projects_imported_at", datetime.now(LOCAL_TZ).isoformat(timespec="seconds"))
    return imported


def bootstrap_account_store() -> None:
    initialize_account_store()
    with ACCOUNT_STORE_LOCK, account_store_connection() as connection:
        rows = connection.execute("SELECT id, payload_json FROM accounts WHERE lifecycle_stage = 'discover'").fetchall()
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError:
                payload = {}
            payload["stage"] = "qualify"
            connection.execute(
                "UPDATE accounts SET lifecycle_stage = 'qualify', payload_json = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False), row["id"]),
            )
    if account_store_count() == 0:
        cached = read_json_file(ACCOUNT_ADVANCEMENT_CACHE_FILE, {})
        imported = import_account_payload_to_store(cached) if isinstance(cached, dict) else 0
        account_store_set_meta("bootstrap_source", "local_migration_cache" if imported else "empty")
        account_store_set_meta("bootstrap_count", str(imported))
    backfill_accepted_prospects_to_account_store()
    backfill_active_projects_to_account_store()
    backfill_workflow_receipt_ids()


def build_account_store_payload() -> dict:
    initialize_account_store()
    deadlines = risk_todos_payload().get("items", [])
    accounts = account_store_rows()
    for account in accounts:
        related_deadlines = account_deadline_matches(account.get("name", ""), deadlines)
        account["deadline_count"] = len(related_deadlines)
        account["deadlines"] = related_deadlines[:4]
        account["time_state"] = infer_account_time_state(related_deadlines)
        account["next_actions"] = [{"id": i.get("id"), "project_id": i.get("project_id", ""), "project_title": i.get("project_title", ""), "next_step": i.get("next_step") or i.get("action"), "deadline": i.get("deadline", ""), "status": i.get("status", "")} for i in related_deadlines]
        if related_deadlines:
            account["next_action"] = "；".join(filter(None, [account.get("unmapped_next_action", "") or (account.get("next_action", "") if account.get("next_action_source") != "同一行动记录汇总" else ""), *[(i.get("project_title", "") + "：" if i.get("project_title") else "") + (i.get("next_step") or i.get("action") or i.get("title", "")) for i in related_deadlines]]))
            account["next_action_source"] = "同一行动记录汇总"
        elif account.get("next_action_source") == "同一行动记录汇总":
            account["next_action"] = account.get("unmapped_next_action", "")
        account["gaps"] = account_gap_labels(account)
        account.setdefault("next_action", account.get("suggested_play") or "补齐关键证据后确认下一步。")
        account.setdefault("next_action_source", "工作台账户主账本")
    accounts.sort(key=lambda item: (priority_rank(item.get("priority", "")), item.get("name", "")))
    stage_counts = {stage["id"]: 0 for stage in ACCOUNT_STAGE_DEFINITIONS}
    for account in accounts:
        stage = account.get("stage", "qualify")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
    stages = [{**stage, "count": stage_counts.get(stage["id"], 0)} for stage in ACCOUNT_STAGE_DEFINITIONS]
    channels = [
        channel
        for account in accounts
        for channel in account.get("channels", [])
        if isinstance(channel, dict)
    ]
    meta = account_store_meta()
    now = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
    return {
        "ok": True,
        "generated_at": now,
        "summary": {
            "account_count": len(accounts),
            "channel_count": len(channels),
            "deadline_account_count": sum(1 for item in accounts if item.get("deadline_count", 0) > 0),
            "gap_count": sum(len(item.get("gaps", [])) for item in accounts),
            "local_admission_count": sum(1 for item in accounts if item.get("record_source") == "workbench_ai_admission"),
            "active_project_count": sum(1 for item in accounts if item.get("record_source") == "workbench_legacy_migration"),
        },
        "source": {
            "status": "local_canonical",
            "label": "工作台账户主账本",
            "detail": "客户准入在工作台即时生效；飞书表格只作为历史导入和可选协作镜像。",
            "feishu_imported_at": meta.get("feishu_imported_at", ""),
            "write_policy": "工作台是唯一状态源；飞书同步失败不会阻断客户推进。",
        },
        "methodology": [
            {"name": "准入判断", "rule": "规模、触发信号、切入口和来源证据达到最低要求后，由你决定进入正式账户。"},
            {"name": "账户推进", "rule": "客户阶段只描述业务生命周期；Deadline 单独描述什么时候需要行动。"},
            {"name": "行动承接", "rule": "只有被你采纳的明确下一步才进入今日行动或下次提醒。"},
        ],
        "reminder_policy": {
            "deadline": "未闭环事项进入工作台 Deadline。",
            "feishu": "飞书任务只做提醒镜像，不决定客户阶段。",
            "calendar": "飞书日程只承接真实会议。",
            "daily_report": "项目群日报只读。",
        },
        "stages": stages,
        "accounts": accounts,
        "channels": channels,
        "today_actions": build_account_today_actions(accounts),
    }


def refresh_account_store_from_feishu() -> dict:
    source_payload = account_advancement_payload_from_lark()
    imported = import_account_payload_to_store(source_payload)
    payload = build_account_store_payload()
    payload["sync_result"] = {
        "ok": True,
        "imported_count": imported,
        "message": f"已从飞书更新 {imported} 个历史账户；工作台准入账户未被覆盖。",
    }
    return payload


def get_account_advancement_payload() -> dict:
    try:
        return build_account_store_payload()
    except Exception as exc:
        return {
            "ok": False,
            "generated_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
            "error": calendar_failure_reason(exc),
            "source": {
                "status": "failed",
                "label": "工作台账户主账本读取失败",
                "write_policy": "不会用飞书缓存静默替代本地主账本。",
            },
            "summary": {"account_count": 0, "channel_count": 0, "deadline_account_count": 0, "gap_count": 0},
            "stages": ACCOUNT_STAGE_DEFINITIONS,
            "accounts": [],
            "channels": [],
            "today_actions": [],
            "public_paths": [],
            "methodology": [],
            "reminder_policy": {},
        }


def prospecting_scheduler_loop() -> None:
    while True:
        for key, operation in [('external_outbox', process_external_sync_outbox),
                               ('tender', lambda: run_prospecting_scan('scheduled') if prospecting_due(load_prospecting_state()) else None)]:
            try:
                result = operation()
                changes = {'checked_at': datetime.now(LOCAL_TZ).isoformat(timespec='seconds'), 'error': ''}
                if key == 'tender':
                    task = (result or {}).get('task', {})
                    outcome = task.get('last_run_status')
                    changes['status'] = 'ready' if outcome in {'ok', 'success', 'no_change','no_result'} else 'error' if outcome in {'error', 'failed','search_unavailable'} else 'waiting'
                    if changes['status'] == 'ready': changes['last_success_at'] = task.get('last_run_at', '')
                    if changes['status'] == 'error': changes['error'] = '招采检索尚未完成，历史记录保留；按重试窗口继续'
                else: changes['status'] = 'waiting'
                background_operations.record(WORKBENCH_DATA_ROOT, key, **changes)
            except Exception:
                background_operations.record(WORKBENCH_DATA_ROOT,key,status='error',last_attempt_at=datetime.now(LOCAL_TZ).isoformat(timespec='seconds'),error='本轮检查未完成，历史结果保留，下一轮自动重试')
        time.sleep(60)


def load_sync_state() -> dict:
    payload = read_json_file(SYNC_STATE_FILE, {"last_sync": {}})
    return payload if isinstance(payload, dict) else {"last_sync": {}}


def save_sync_state(state: dict) -> None:
    write_private_json(SYNC_STATE_FILE, state)


def extract_feishu_message_text(message: dict) -> str:
    msg_type = message.get("msg_type", "")
    raw = message.get("body", {}).get("content", "{}")
    try:
        content = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        content = {}

    if msg_type == "text":
        return strip_html(content.get("text", ""))
    if msg_type == "post":
        chunks = []
        post = content.get("post", {})
        for block in post.values():
            for row in block.get("content", []):
                for segment in row:
                    if isinstance(segment, dict) and segment.get("tag") == "text":
                        chunks.append(segment.get("text", ""))
        return "\n".join(chunks).strip()
    if msg_type == "file":
        return f"[文件] {content.get('file_name', '未知文件')}"
    if msg_type == "image":
        return "[图片]"
    if msg_type == "audio":
        return "[语音]"
    if msg_type == "merge_forward":
        return "[合并转发消息]"
    if msg_type == "system":
        return "[系统消息]"
    return f"[{msg_type or 'unknown'}消息]"


def format_feishu_message(message: dict) -> str:
    sender = message.get("sender", {})
    mentions = message.get("mentions", [])
    sender_name = mentions[0].get("name") if mentions and mentions[0].get("name") else sender.get("id", "unknown")[:8]
    create_time = message.get("create_time", "")
    try:
        time_str = datetime.fromtimestamp(int(create_time) / 1000).strftime("%H:%M:%S")
    except Exception:
        time_str = str(create_time)
    return f"- **{sender_name}** ({time_str}): {extract_feishu_message_text(message)}"


def save_project_messages(chat_name: str, messages: list[dict], date_str: str) -> tuple[Path, int]:
    MESSAGE_ROOT.mkdir(parents=True, exist_ok=True)
    path = MESSAGE_ROOT / f"{date_str}_{chat_name}.md"
    is_new = not path.exists()
    existing_lines = set(read_text(path).splitlines()) if path.exists() else set()
    added = 0
    with path.open("a", encoding="utf-8") as handle:
        if is_new:
            handle.write(f"# 飞书群消息 - {chat_name}\n")
            handle.write(f"> 日期: {date_str}\n\n")
        for message in messages:
            line = format_feishu_message(message)
            if line in existing_lines:
                continue
            handle.write(line + "\n")
            existing_lines.add(line)
            added += 1
    return path, added


def get_feishu_client():
    if str(FEISHU_API_ROOT) not in sys.path:
        sys.path.insert(0, str(FEISHU_API_ROOT))
    from hermes_api.feishu_client import FeishuClient
    from hermes_api.runtime import load_env_file

    env_file = load_env_file()
    if not env_file:
        raise RuntimeError("Feishu API env file not found")
    return FeishuClient()


def run_lark_cli_json(path: str, params: dict) -> dict:
    env = os.environ.copy()
    env["HERMES_HOME"] = str(HOME_ROOT / ".hermes")
    result = subprocess.run(
        [
            LARK_CLI_BIN,
            "api",
            "GET",
            path,
            "--as",
            "user",
            "--format",
            "json",
            "--params",
            json.dumps(params, ensure_ascii=False),
        ],
        capture_output=True,
        text=True,
        timeout=35,
        env=env,
    )
    raw_output = result.stdout.strip() or result.stderr.strip()
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise RuntimeError((raw_output or "lark-cli returned invalid JSON")[:500]) from exc
    if result.returncode != 0 or payload.get("ok") is False:
        message = payload.get("error", {}).get("message") or payload.get("msg") or result.stderr or "lark-cli request failed"
        raise RuntimeError(message)
    return payload


def lark_cli_env() -> dict:
    env = os.environ.copy()
    env["HERMES_HOME"] = str(HOME_ROOT / ".hermes")
    env["PATH"] = f"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:{env.get('PATH', '')}"
    return env


def run_json_command(args: list[str], timeout: int = 35, cwd: Path | None = None) -> dict:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=lark_cli_env(),
            cwd=str(cwd) if cwd else None,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("本机找不到 lark-cli，无法同步飞书") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("飞书请求超时，尚未确认执行结果；请稍后检查连接状态，不要重复生成授权") from exc
    raw_output = result.stdout.strip() or result.stderr.strip()
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise RuntimeError((raw_output or "command returned invalid JSON")[:500]) from exc
    if result.returncode != 0 or payload.get("ok") is False:
        message = payload.get("error", {}).get("message") or payload.get("msg") or "命令执行失败"
        raise RuntimeError(message)
    return payload


def calendar_failure_reason(error: Exception | str) -> str:
    message = str(error).strip() or "飞书没有返回明确原因"
    lowered = message.lower()
    if "lark-cli" in lowered and ("not found" in lowered or "找不到" in message):
        return "本机找不到 lark-cli，当前无法写入飞书日程。"
    if "auth" in lowered or "authorization" in lowered or "unauthorized" in lowered or "access token" in lowered or "授权" in message:
        return "飞书授权可能失效或未完成，请重新授权后再点重试。"
    if "timeout" in lowered or "timed out" in lowered or "超时" in message:
        return "飞书创建请求超时，可能是授权确认或网络响应太慢，可以稍后重试。"
    if "calendar" in lowered and ("permission" in lowered or "scope" in lowered or "权限" in message):
        return "当前飞书授权缺少日程写入权限，需要重新授权包含日程权限。"
    return message[:500]


def start_lark_auth() -> dict:
    # Multiple tabs must share one pending device flow. Replacing its code can
    # orphan a successful browser consent while the server polls another code.
    with LARK_AUTH_LOCK:
        existing = get_lark_auth_state()
        if existing.get("exists") and not existing.get("expired"):
            return {"ok": True, **existing, "reused": True}
        return _start_lark_auth_locked()


def _start_lark_auth_locked() -> dict:
    payload = run_json_command(
        [LARK_CLI_BIN, "auth", "login", "--scope", "im:message:readonly im:message.group_msg:get_as_user im:chat:read offline_access", "--no-wait", "--json"],
        timeout=25,
        cwd=WORKSPACE_ROOT,
    )
    verification_url = payload.get("verification_url")
    device_code = payload.get("device_code")
    expires_in = int(payload.get("expires_in", 600))
    if not verification_url or not device_code:
        raise RuntimeError("飞书授权启动失败，未返回 verification_url/device_code")

    # OAuth login returns JSON, but `auth qrcode` returns plain text. A QR side task
    # must not prevent the working verification link from reaching the user.
    expires_at = datetime.fromtimestamp(datetime.now().timestamp() + expires_in).strftime("%Y-%m-%d %H:%M:%S")
    state = {
        "device_code": device_code,
        "verification_url": verification_url,
        "qr_url": "",
        "expires_at": expires_at,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    LARK_AUTH_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LARK_AUTH_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    LARK_AUTH_STATE_FILE.chmod(0o600)
    return {"ok": True, **get_lark_auth_state()}


def get_lark_auth_state(include_device: bool = False) -> dict:
    state = read_json_file(LARK_AUTH_STATE_FILE, {})
    if not isinstance(state, dict) or not state:
        return {
            "exists": False,
            "state": "missing",
            "label": "还没有生成飞书授权链接",
            "remaining_seconds": 0,
            "expired": True,
        }
    expires_at_raw = state.get("expires_at", "")
    try:
        expires_at = datetime.strptime(expires_at_raw, "%Y-%m-%d %H:%M:%S")
        remaining = max(0, int((expires_at - datetime.now()).total_seconds()))
    except ValueError:
        remaining = 0
    expired = remaining <= 0
    public_state = {
        "exists": True,
        "state": "expired" if expired else "active",
        "label": "授权链接已过期" if expired else "授权链接有效",
        "verification_url": state.get("verification_url", ""),
        "qr_url": state.get("qr_url", ""),
        "expires_at": expires_at_raw,
        "created_at": state.get("created_at", ""),
        "remaining_seconds": remaining,
        "expired": expired,
    }
    if include_device:
        public_state["device_code"] = state.get("device_code", "")
    return public_state


def complete_lark_auth() -> dict:
    with LARK_AUTH_LOCK:
        # A previous request may have completed even if the browser timed out.
        # Never demand a new authorization when an actual read already works.
        sync_status = get_message_sync_status()
        if not sync_status.get("action_required"):
            return {"ok": True, "ready": True, "message": "飞书授权已接回，项目群读取验证通过", "sync_status": sync_status}
        return _complete_lark_auth_locked()


def _complete_lark_auth_locked() -> dict:
    auth_state = get_lark_auth_state(include_device=True)
    if not auth_state.get("exists"):
        raise RuntimeError("还没有待接收的授权请求，请先生成授权链接")
    if auth_state.get("expired"):
        raise RuntimeError("当前授权请求已过期，且项目群读取未通过；需要新的授权链接")
    device_code = auth_state.get("device_code")
    if not device_code:
        raise RuntimeError("授权状态缺少 device_code，请重新生成授权")
    run_json_command(
        [LARK_CLI_BIN, "auth", "login", "--device-code", device_code, "--json"],
        timeout=25,
        cwd=WORKSPACE_ROOT,
    )
    try:
        LARK_AUTH_STATE_FILE.unlink()
    except FileNotFoundError:
        pass
    sync_status = get_message_sync_status()
    ready = not sync_status.get("action_required")
    return {"ok": True, "ready": ready, "message": "飞书授权已接回，项目群读取验证通过" if ready else "飞书授权已接回，但项目群读取尚未通过：" + sync_status.get("detail", "请检查读取权限"), "sync_status": sync_status}


def collect_today_lark_messages(chat_id: str, today_start_ms: int, request_page=None) -> list[dict]:
    messages: list[dict] = []
    page_token = ""
    for _ in range(10):
        params = {
            "container_id_type": "chat",
            "container_id": chat_id,
            "page_size": 50,
            "sort_type": "ByCreateTimeDesc",
        }
        if page_token:
            params["page_token"] = page_token
        payload = request_page(params) if request_page else run_lark_cli_json("/open-apis/im/v1/messages", params)
        data = payload.get("data", {})
        items = data.get("items", []) or []
        if not items:
            if data.get("has_more"):
                raise RuntimeError("分页返回空页但仍有后续消息，本群未完整读取")
            break
        oldest_seen = None
        for message in items:
            create_time = int(message.get("create_time", "0") or 0)
            oldest_seen = create_time if oldest_seen is None else min(oldest_seen, create_time)
            if create_time >= today_start_ms:
                messages.append(message)
        if oldest_seen is not None and oldest_seen < today_start_ms:
            break
        page_token = data.get("page_token") or ""
        if not data.get("has_more"):
            break
        if not page_token or page_token == params.get("page_token"):
            raise RuntimeError("消息分页凭据缺失或重复，本群未完整读取")
    else:
        raise RuntimeError("当日消息超过500条安全读取上限，本群未完整读取；不计为完整成功")
    messages.reverse()
    return messages


def sync_messages_user_cli() -> dict:
    state = load_sync_state()
    today = datetime.now()
    today_start_ms = int(today.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    today_str = today.strftime("%Y-%m-%d")
    output = [f"使用小吴用户授权 lark-cli 同步 {len(PROJECT_CHATS)} 个项目群"]
    total = 0
    failed = 0

    for chat in PROJECT_CHATS:
        chat_id = chat["chat_id"]
        chat_name = chat["name"]
        key = f"user_cli_msg_{chat_id}"
        try:
            today_messages = collect_today_lark_messages(chat_id, today_start_ms)
        except Exception as exc:
            failed += 1
            output.append(f"{chat_name}: 拉取失败 - {calendar_failure_reason(exc)}")
            continue
        if today_messages:
            _, added = save_project_messages(chat_name, today_messages, today_str)
            total += added
            output.append(f"{chat_name}: 读取 {len(today_messages)} 条，写入 {added} 条")
        else:
            output.append(f"{chat_name}: 今天暂无新增")

        if today_messages:
            state.setdefault("last_sync", {})[key] = today_messages[-1].get("message_id", "")

    if failed == len(PROJECT_CHATS):
        raise RuntimeError("；".join(output[1:3]) + "。所有项目群读取失败，保留历史日报")

    save_sync_state(state)
    digest = build_message_digest(persist_reports=True)
    output.append(f"同步完成，共 {total} 条新消息，失败 {failed} 个群；原始消息与历史日报均保留")
    return {"ok": True, "output": output, "message_digest": digest, "new_messages": total, "failed_groups": failed, "total_groups": len(PROJECT_CHATS)}


def sync_messages_direct() -> dict:
    client = get_feishu_client()
    state = load_sync_state()
    today = datetime.now()
    today_start_ms = int(today.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    today_str = today.strftime("%Y-%m-%d")
    output = [f"使用 Feishu app API 同步 {len(PROJECT_CHATS)} 个项目群"]
    total = 0
    failed = 0

    for chat in PROJECT_CHATS:
        chat_id = chat["chat_id"]
        chat_name = chat["name"]
        key = f"direct_msg_{chat_id}"
        try:
            token = client.get_tenant_access_token()
            today_messages = collect_today_lark_messages(chat_id, today_start_ms, lambda params: client._request("GET", "/open-apis/im/v1/messages", query=params, token=token))
        except Exception as exc:
            failed += 1
            output.append(f"{chat_name}: 拉取失败 - {exc}")
            continue

        if today_messages:
            _, added = save_project_messages(chat_name, today_messages, today_str)
            total += added
            output.append(f"{chat_name}: 读取 {len(today_messages)} 条，写入 {added} 条")
        else:
            output.append(f"{chat_name}: 今天暂无新增")

        if today_messages:
            state.setdefault("last_sync", {})[key] = today_messages[-1].get("message_id", "")

    if failed == len(PROJECT_CHATS):
        raise RuntimeError("所有项目群读取失败，已保留上一次有效项目群日报")

    save_sync_state(state)
    digest = build_message_digest(persist_reports=True)
    output.append(f"同步完成，共 {total} 条新消息，失败 {failed} 个群；原始消息与历史日报均保留")
    return {"ok": True, "output": output, "message_digest": digest, "new_messages": total, "failed_groups": failed, "total_groups": len(PROJECT_CHATS)}


def sync_messages() -> dict:
    with MESSAGE_SYNC_LOCK:
        health_file = WORKBENCH_DATA_ROOT / "message_sync_health.json"
        health = read_json_file(health_file, {})
        health["last_attempt_at"] = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
        try:
            result = sync_messages_user_cli()
        except Exception as exc:
            try:
                result = sync_messages_direct()
                result["output"] = [f"用户通道不可用，已回退机器人通道：{exc}", *result.get("output", [])]
            except Exception as direct_exc:
                health.update(status="failed", error=f"用户通道：{exc}；机器人通道：{direct_exc}")
                health_file.parent.mkdir(parents=True, exist_ok=True)
                health_file.write_text(json.dumps(health, ensure_ascii=False, indent=2))
                raise RuntimeError(health["error"]) from direct_exc
        health.update(status="partial" if result.get("failed_groups") else "success", error="", new_messages=result.get("new_messages", 0), failed_groups=result.get("failed_groups", 0), output=result.get("output", []))
        if not result.get("failed_groups"):
            health["last_success_at"] = health["last_attempt_at"]
        health_file.parent.mkdir(parents=True, exist_ok=True)
        health_file.write_text(json.dumps(health, ensure_ascii=False, indent=2))
        result["sync_health"] = health
        return result


def get_message_sync_status() -> dict:
    try:
        run_lark_cli_json(
            "/open-apis/im/v1/messages",
            {
                "container_id_type": "chat",
                "container_id": PROJECT_CHATS[0]["chat_id"],
                "page_size": 1,
                "sort_type": "ByCreateTimeDesc",
            },
        )
        return {
            "mode": "user_cli",
            "label": "飞书用户读取已验证",
            "detail": "同步会优先使用用户态 lark-cli，可读取用户所在项目群。",
            "action_required": False,
            "auth": {
                "exists": True,
                "state": "authorized",
                "label": "飞书用户授权已完成",
                "remaining_seconds": 0,
                "expired": False,
            },
        }
    except Exception as exc:
        return {
            "mode": "app_fallback",
            "label": "飞书用户读取尚未通过",
            "detail": f"{exc}。app 回退只能读取机器人已加入的群。",
            "action_required": True,
            "auth": get_lark_auth_state(),
        }


def default_workflow_state() -> dict:
    return {
        "version": 1,
        "action_status": {},
        "risk_status": {},
        "schedule_status": {},
        "pm_item_status": {},
        "generated_actions": {},
        "generated_risks": {},
        "receipts": [],
        "updated_at": "",
    }


def load_workflow_state() -> dict:
    payload = read_json_file(WORKFLOW_STATE_FILE, default_workflow_state())
    if not isinstance(payload, dict):
        payload = default_workflow_state()
    state = default_workflow_state()
    state.update(payload)
    for key in ("action_status", "risk_status", "schedule_status", "pm_item_status", "generated_actions", "generated_risks"):
        if not isinstance(state.get(key), dict):
            state[key] = {}
    if not isinstance(state.get("receipts"), list):
        state["receipts"] = []
    hydrate_workflow_receipts(state)
    return state


def extract_resolution_from_page(relative_path: str) -> str:
    if not relative_path:
        return ""
    rel = Path(relative_path)
    candidates = [
        SALES_WORKBENCH_KNOWLEDGE_ROOT / rel,
        WORKBENCH_DATA_ROOT / rel,
    ]
    for candidate in candidates:
        if not candidate.exists() or not candidate.is_file():
            continue
        text = read_text(candidate)
        marker = "## 原始提交"
        if marker not in text:
            continue
        tail = text.split(marker, 1)[1].strip()
        if "\n## " in tail:
            tail = tail.split("\n## ", 1)[0].strip()
        return tail[:600].strip()
    return ""


def hydrate_receipt_resolution(receipt: dict) -> None:
    if not isinstance(receipt, dict) or receipt.get("resolution"):
        return
    resolution = extract_resolution_from_page(str(receipt.get("relative_path", "")))
    if resolution:
        receipt["resolution"] = resolution


def hydrate_workflow_receipts(state: dict) -> None:
    for receipt in state.get("receipts", []):
        hydrate_receipt_resolution(receipt)
        todo = receipt.get("todo")
        if isinstance(todo, dict) and receipt.get("resolution") and not todo.get("resolution"):
            todo["resolution"] = receipt["resolution"]
    for bucket in ("action_status", "risk_status", "schedule_status", "pm_item_status"):
        for record in state.get(bucket, {}).values():
            if not isinstance(record, dict):
                continue
            receipt = record.get("receipt")
            if isinstance(receipt, dict):
                hydrate_receipt_resolution(receipt)
                todo = receipt.get("todo")
                if isinstance(todo, dict) and receipt.get("resolution") and not todo.get("resolution"):
                    todo["resolution"] = receipt["resolution"]


def backfill_workflow_receipt_ids() -> int:
    state = load_workflow_state()
    accounts = account_store_rows()
    changed = 0
    excluded_customers = {"", "通用待办", "待匹配事项", "待绑定客户", "未绑定客户"}
    for receipt in state.get("receipts", []):
        if not isinstance(receipt, dict):
            continue
        customer = str(receipt.get("customer") or "").strip()
        if customer in excluded_customers or account_store_match(customer, accounts):
            continue
        migrated = upsert_account_store(
            {
                "name": customer,
                "priority": "P2",
                "source_type": "工作台历史回执迁移",
                "status_note": "已有历史工作回执，已迁入正式账户主账本。",
                "recent_signal": receipt.get("resolution") or receipt.get("title") or "历史工作回执",
                "opportunity": receipt.get("title") or "历史客户跟进",
                "suggested_play": receipt.get("next_step") or "复核历史回执并确认新的下一步。",
                "next_action": receipt.get("next_step") or "复核历史回执并确认新的下一步。",
                "next_action_source": "历史工作回执",
                "stage": "contact",
                "account_state": "active",
                "channels": [],
                "channel_count": 0,
            },
            source_kind="workbench_receipt_migration",
            sync_status="local",
        )
        accounts.append(migrated)
        changed += 1

    def enrich(receipt: dict) -> None:
        nonlocal changed
        if not isinstance(receipt, dict):
            return
        if not receipt.get("id"):
            identity = "|".join(
                [
                    str(receipt.get("relative_path") or ""),
                    str(receipt.get("submitted_at") or ""),
                    str(receipt.get("customer") or ""),
                    str(receipt.get("title") or ""),
                ]
            )
            receipt["id"] = f"legacy-receipt-{uuid.uuid5(uuid.NAMESPACE_URL, identity).hex[:16]}"
            changed += 1
        if not receipt.get("account_id"):
            account_id = canonical_account_id(str(receipt.get("customer") or ""), accounts)
            if account_id:
                receipt["account_id"] = account_id
                changed += 1
        todo = receipt.get("todo")
        if isinstance(todo, dict) and receipt.get("account_id") and not todo.get("account_id"):
            todo["account_id"] = receipt["account_id"]
            changed += 1

    for receipt in state.get("receipts", []):
        enrich(receipt)
    for bucket in ("action_status", "risk_status", "schedule_status", "pm_item_status"):
        for record in state.get(bucket, {}).values():
            if isinstance(record, dict):
                enrich(record.get("receipt"))
                if not record.get("account_id"):
                    account_id = canonical_account_id(str(record.get("customer") or ""), accounts)
                    if account_id:
                        record["account_id"] = account_id
                        changed += 1
    if changed:
        save_workflow_state(state)
    return changed


def save_workflow_state(state: dict) -> None:
    state["version"] = 1
    state["updated_at"] = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
    write_private_json(WORKFLOW_STATE_FILE, state)


def append_workflow_project_event(record: dict) -> str:
    customer = record.get("customer") or "未绑定客户"
    title = record.get("title") or "工作台流转"
    target = record.get("target") or ""
    status = record.get("status") or "已更新"
    if not customer or customer == "未绑定客户":
        return ""
    now = datetime.now(LOCAL_TZ)
    slug = safe_filename(f"{customer}-{title}-{target}", "workflow-event")
    page_name = f"{now.strftime('%Y-%m-%d')}_{slug}_{now.strftime('%H%M%S')}.md"
    page_path = WORKFLOW_EVENT_ROOT / page_name
    if page_path.exists():
        return str(page_path.relative_to(WORKBENCH_DATA_ROOT))
    source = record.get("item") if isinstance(record.get("item"), dict) else {}
    next_step = record.get("next_step") or source.get("next_step") or source.get("recommendation") or source.get("action") or source.get("task") or ""
    evidence = source.get("summary") or source.get("risk") or source.get("signal") or source.get("evidence") or ""
    lines = [
        f"# {customer} 工作台流转记录",
        "",
        f"**客户/项目**：[[{customer}]]",
        f"**事件类型**：{record.get('source_view') or '项目管理工作台'} -> {target or status}",
        f"**当前状态**：{status}",
        f"**标题**：{title}",
        f"**发生时间**：{now.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 当前判断",
        "",
        evidence or title,
        "",
        "## 下一步",
        "",
        next_step or "待在客户作战室继续补齐责任人和时间。",
        "",
        "## 来源",
        "",
        f"- 来源入口：{record.get('source_view') or '项目管理工作台'}",
        f"- 工作台状态键：`{record.get('key', '')}`",
        "",
        "## 关联",
        "",
        "- [[客户跟进]]",
        "- [[工作台流转]]",
        "",
    ]
    WORKFLOW_EVENT_ROOT.mkdir(parents=True, exist_ok=True)
    page_path.write_text("\n".join(lines), encoding="utf-8")
    return str(page_path.relative_to(WORKBENCH_DATA_ROOT))


def create_schedule_from_record(record: dict, source_scope: str = "workflow") -> dict:
    if source_scope == "pm_daily":
        raise ValueError("项目群日报是只读阅读区，不能转成日程或待办")
    source = record.get("item") if isinstance(record.get("item"), dict) else {}
    now = datetime.now(LOCAL_TZ)
    deadline = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    customer = record.get("customer") or source.get("customer") or source.get("name") or "未绑定客户"
    title = record.get("title") or source.get("title") or source.get("summary") or source.get("task") or "工作台待跟进"
    next_step = (
        record.get("next_step")
        or source.get("next_step")
        or source.get("action")
        or source.get("task")
        or source.get("summary")
        or "确认责任人、截止时间和下一步。"
    )
    todo = {
        "id": f"workflow-{safe_filename(record.get('key', title), 'schedule')}",
        "project_id": source.get("project_id", ""),
        "project_source": source.get("project_source", ""),
        "archive_revision": record.get("archive_revision", 0),
        "account_id": record.get("account_id") or source.get("account_id") or canonical_account_id(customer),
        "customer": customer,
        "title": title,
        "status": "待确认时间",
        "evidence": source.get("summary") or source.get("risk") or source.get("signal") or title,
        "action": source.get("action") or source.get("recommendation") or next_step,
        "next_step": next_step,
        "deadline": deadline.isoformat(timespec="minutes"),
        "reminder_minutes": 10,
        "resolution_path": "",
        "calendar": {
            "ok": False,
            "status": "skipped",
            "message": "已转入工作台 deadline，待确认时间后同步飞书提醒",
            "reason": "",
        },
        "created_at": now.isoformat(timespec="seconds"),
        "source_scope": source_scope,
        "source_type": source_scope,
        "pm_item_key": record.get("key", ""),
        "projectLine": project_line_for_customer(customer),
    }
    append_risk_todo(todo)
    log_path = RISK_TODO_LOG
    source_label = f"{record.get('source_view') or '工作台'}转日程"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n- [ ] {deadline.strftime('%Y-%m-%d %H:%M')} — {customer}：{next_step}（来源：{source_label}）\n")
    return todo


def discovery_preparation(payload):
    notes = discovery_workspace.load_notes(WORKBENCH_DATA_ROOT)
    leads = [apply_prospecting_time_window(dict(item)) for item in load_prospecting_state().get('leads', [])]
    prepared = discovery_handoff.prepare(payload.get('kind'), payload.get('source_id'), notes, leads,
        account_store_rows(), build_projects(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT))
    tasks = risk_todos_payload()['items']
    matches = [item for item in tasks if item.get('discovery_source_key') in prepared['lineage_keys'] or item.get('id') in prepared['action_ids']]
    if len(matches)>1:
        raise ValueError('该账户已有多条来源跟进，请在原跟进中核对，未重复创建')
    existing = matches[0] if matches else None
    claimed = project_rounds.followups(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT)['claimed_actions']
    claimed_projects = {claimed[aid] for aid in prepared['action_ids'] if aid in claimed}
    if not existing and len(claimed_projects)>1:
        raise ValueError('该账户来源已由不同项目承接，请在原项目核对')
    if not existing and claimed_projects:
        project_id = next(iter(claimed_projects))
        record = project_rounds.read_round(project_id, SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT)
        existing = {'id':'round:'+project_id, 'project_id':project_id, 'status':record['record']['status'], 'source_type':'project_round'}
    workflow = project_activity.read_store(WORKBENCH_DATA_ROOT/'workflow_state.json', {})
    past = workflow.get('schedule_status', {}).get(prepared['action_id'], {})
    prepared['existing'] = existing
    prepared['handled'] = not existing and bool(past.get('hidden'))
    return prepared


def save_discovery_handoff(payload):
    with STATE_FILE_LOCK, discovery_workspace.LOCK:
        prepared = discovery_preparation(payload)
        if type(payload.get('revision')) is not int or payload['revision'] != prepared['revision']:
            raise ValueError('判断记录已更新，请读取最新记录后继续；当前输入保留')
        if prepared['existing']:
            if payload.get('project_id') and prepared['existing'].get('project_id') != payload['project_id']:
                raise ValueError('本轮已关联另一个项目，请在原跟进中调整，不重复创建')
            return {'ok':True,'existing':True,'todo':prepared['existing'],'message':'沿用同一跟进记录，阶段、日期和反馈保持当前状态'}
        if prepared['handled']:
            return {'ok':True,'handled':True,'todo':None,'message':'这轮事项已处理；新沟通结果保存后可准备下一轮'}
        if payload.get('source_version') != prepared['source_version']:
            raise ValueError('来源或归属记录已变化，请重新查看准备结果')
        todo = discovery_handoff.todo(prepared, payload.get('project_id', ''))
        if todo.get('project_id'):
            record = project_rounds.read_round(todo['project_id'], SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT).get('record')
            if record and (record.get('relationship') == 'no_contact' or record.get('status') == '暂停跟进'):
                raise ValueError('项目有暂停或暂勿联系约定，请先在原项目核对，不从发现入口恢复')
        # One persistent owner. Receipts, rescheduling and project adoption already
        # consume this exact todo identity; no qualification-side task store.
        items = project_activity.read_store(RISK_TODO_FILE, [])
        if not any(i.get('id') == todo['id'] for i in items):
            save_risk_todos([*items, todo])
        return {'ok':True,'todo':todo,'message':'已承接本轮判断和约定日期；仅创建本地准备行动'}


def create_manual_todo_impl(payload: dict) -> dict:
    account_id = strip_html(str(payload.get("account_id", "")).strip())
    customer = strip_html(str(payload.get("customer", "")).strip()) or "通用待办"
    account_id = account_id or canonical_account_id(customer)
    title = strip_html(str(payload.get("title", "")).strip())
    next_step = strip_html(str(payload.get("next_step", "")).strip()) or title
    evidence = strip_html(str(payload.get("evidence", "")).strip()) or "销售捕捉"
    target = strip_html(str(payload.get("target", "now")).strip()) or "now"
    priority = strip_html(str(payload.get("priority", "P2")).strip()) or "P2"
    reminder_minutes = int(payload.get("reminder_minutes") or 10)
    sync_calendar = bool(payload.get("sync_calendar", False))
    deadline_raw = strip_html(str(payload.get("deadline", "")).strip())
    if not title:
        raise ValueError("请填写待办事项")
    if target not in {"now", "scheduled"}:
        target = "now"

    now = datetime.now(LOCAL_TZ)
    if target == "now":
        deadline = min(now + timedelta(minutes=15), now.replace(hour=23, minute=59, second=59, microsecond=0))
        status = "待处理"
    else:
        if not deadline_raw:
            raise ValueError("安排到下次提醒时需要填写时间")
        deadline = parse_local_datetime(deadline_raw)
        status = "推进中"

    stamp = now.strftime("%Y%m%d-%H%M%S")
    todo_id = f"manual-{stamp}-{uuid.uuid4().hex[:8]}-{safe_filename(customer, 'customer')}-{safe_filename(title, 'todo')}"[:160]
    calendar_result = {"ok": False, "status": "skipped", "message": "未启用飞书任务与私聊提醒"}
    if sync_calendar and deadline:
        try:
            calendar_result = create_feishu_task_reminder(
                customer=customer,
                title=title,
                next_step=next_step,
                deadline=deadline,
                reminder_minutes=reminder_minutes,
                evidence_path="工作台手动待办",
                evidence=evidence,
                action=next_step,
            )
            calendar_result["status"] = "synced"
            calendar_result["message"] = "飞书任务已创建；到期前将发送私聊提醒"
            calendar_result["reason"] = ""
        except Exception as exc:
            calendar_result = {
                "ok": False,
                "status": "failed",
                "message": "飞书任务提醒创建失败",
                "reason": calendar_failure_reason(exc),
            }

    todo = {
        "id": todo_id,
        "project_id": payload.get("project_id", ""),
        "project_source": payload.get("project_source", ""),
        "archive_revision": payload.get("archive_revision", 0),
        "workroom_request_id": f"workroom:{todo_id}"[:500],
        "account_id": account_id,
        "customer": customer,
        "title": title,
        "status": status,
        "priority": priority,
        "evidence": evidence,
        "action": next_step,
        "next_step": next_step,
        "deadline": deadline.isoformat(timespec="minutes"),
        "reminder_minutes": reminder_minutes,
        "resolution_path": "",
        "calendar": calendar_result,
        "created_at": now.isoformat(timespec="seconds"),
        "source_scope": "manual",
        "source_type": "manual",
        "reminder_consent": {"enabled": sync_calendar and target == "scheduled", "deadline": deadline.isoformat(timespec="minutes"), "confirmed_at": now.isoformat(timespec="seconds")},
        "projectLine": project_line_for_customer(customer),
    }
    append_risk_todo(todo)

    RISK_TODO_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RISK_TODO_LOG.open("a", encoding="utf-8") as handle:
        handle.write(
            f"\n- [ ] {deadline.strftime('%Y-%m-%d %H:%M')} — {customer}：{next_step}"
            f"（来源：销售捕捉；飞书提醒：{calendar_result.get('status')}）\n"
        )

    state = load_workflow_state()
    state["schedule_status"][todo_id] = {
        "kind": "schedule",
        "key": todo_id,
        "status": status,
        "hidden": False,
        "customer": customer,
        "account_id": account_id,
        "title": title,
        "next_step": next_step,
        "deadline": deadline.isoformat(timespec="minutes"),
        "updated_at": now.isoformat(timespec="seconds"),
        "source_view": "销售捕捉",
    }
    save_workflow_state(state)
    return {
        "ok": True,
        "todo": todo,
        "calendar": calendar_result,
        "workflow_state": state,
        "dashboard": get_dashboard_payload(),
    }


def check_project_sales_write(payload: dict) -> dict:
    projects = build_projects(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT)
    item = payload.get("item") if isinstance(payload.get("item"), dict) else payload
    project = project_activity.project_owner(item, projects)
    if project:
        a = project_archive.state(WORKBENCH_DATA_ROOT, project["id"])
        if a["archived"] or payload.get("archive_revision", 0) != a["revision"]:
            raise project_rounds.RevisionConflict("项目归档状态已变化，未创建销售操作，请重新核对")
    return project or {}


def create_manual_todo(payload: dict) -> dict:
    with project_archive.locked(WORKBENCH_DATA_ROOT), STATE_FILE_LOCK:
        check_project_sales_write(payload)
        return create_manual_todo_impl(payload)


def create_pm_schedule_from_record(record: dict) -> dict:
    raise ValueError("项目群日报是只读阅读区，不能转成日程或待办")


def workflow_record_impl(payload: dict) -> dict:
    kind = strip_html(str(payload.get("kind") or payload.get("type") or "").strip()) or "action"
    key = strip_html(str(payload.get("key") or payload.get("workflow_key") or "").strip())
    if not key:
        raise ValueError("缺少工作流 key")
    target = strip_html(str(payload.get("target", "")).strip())
    status = strip_html(str(payload.get("status", "")).strip()) or "已更新"
    now = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
    item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
    record = {
        "kind": kind,
        "archive_revision": payload.get("archive_revision", 0),
        "key": key,
        "target": target,
        "status": status,
        "customer": strip_html(str(payload.get("customer", item.get("customer", ""))).strip()),
        "account_id": strip_html(str(payload.get("account_id", item.get("account_id", ""))).strip()),
        "title": strip_html(str(payload.get("title", item.get("title", ""))).strip()),
        "next_step": strip_html(str(payload.get("next_step", item.get("next_step", ""))).strip()),
        "source_view": strip_html(str(payload.get("source_view", item.get("source_view", "项目管理工作台"))).strip()),
        "updated_at": now,
        "item": item,
    }
    state = load_workflow_state()
    if kind == "pm_item":
        record["status"] = "只读"
        record["hidden"] = False
        record["readonly"] = True
        state["pm_item_status"][key] = record
    elif kind == "risk":
        if target == "schedule":
            todo = create_schedule_from_record(record, "workflow")
            record["status"] = "已转日程"
            record["hidden"] = True
            record["todo"] = todo
            state["schedule_status"][todo["id"]] = {
                "kind": "schedule",
                "key": todo["id"],
                "status": "待确认时间",
                "hidden": False,
                "customer": todo["customer"],
                "title": todo["title"],
                "next_step": todo["next_step"],
                "deadline": todo["deadline"],
                "updated_at": now,
            }
        elif target == "action":
            record["status"] = "已转动作"
            record["hidden"] = True
        elif target in {"resolved", "ignore"}:
            record["status"] = "风险解除" if target == "resolved" else "已忽略"
            record["hidden"] = True
        state["risk_status"][key] = record
        if target == "action":
            state["generated_actions"][key] = record
    elif kind == "schedule":
        if target == "schedule":
            todo = create_schedule_from_record(record, "workflow")
            record["status"] = "已转日程"
            record["hidden"] = True
            record["todo"] = todo
        elif target == "action":
            record["status"] = "已转动作"
            record["hidden"] = True
            state["generated_actions"][key] = record
        elif target == "risk":
            record["status"] = "已转风险"
            record["hidden"] = True
            state["generated_risks"][key] = record
        elif target in {"done", "ignore"}:
            record["status"] = "已回填" if target == "done" else "已忽略"
            record["hidden"] = True
        state["schedule_status"][key] = record
    elif kind == "action":
        if target == "schedule":
            todo = create_schedule_from_record(record, "workflow")
            record["status"] = "已转日程"
            record["hidden"] = True
            record["todo"] = todo
            state["schedule_status"][todo["id"]] = {
                "kind": "schedule",
                "key": todo["id"],
                "status": "待确认时间",
                "hidden": False,
                "customer": todo["customer"],
                "title": todo["title"],
                "next_step": todo["next_step"],
                "deadline": todo["deadline"],
                "updated_at": now,
            }
        elif target in {"done", "ignore"}:
            record["status"] = "已处理" if target == "done" else "已忽略"
            record["hidden"] = True
        state["action_status"][key] = record
    else:
        state["action_status"][key] = record
    if target in {"action", "risk", "schedule", "resolved", "done"}:
        project_path = append_workflow_project_event(record)
        if project_path:
            record["project_path"] = project_path
    save_workflow_state(state)
    return {"ok": True, "record": record, "workflow_state": state}


def workflow_record(payload: dict) -> dict:
    with project_archive.locked(WORKBENCH_DATA_ROOT), STATE_FILE_LOCK:
        check_project_sales_write(payload)
        return workflow_record_impl(payload)


def get_dashboard_payload() -> dict:
    customers = parse_client_registry()
    todos = parse_todo_log()
    deal_board = build_deal_board(customers, todos)
    try:
        canonical_accounts = account_store_rows()
        for item in deal_board:
            matched = account_store_match(str(item.get("name") or ""), canonical_accounts)
            item["account_id"] = str(matched.get("id") or "") if matched else ""
            if matched:
                item["priority"] = matched.get("priority") or item.get("priority")
                item["stage"] = next(
                    (stage["label"] for stage in ACCOUNT_STAGE_DEFINITIONS if stage["id"] == matched.get("stage")),
                    item.get("stage"),
                )
                item["next_action"] = matched.get("next_action") or item.get("next_action")
                item["risk"] = matched.get("opportunity") or item.get("risk")
                item["signal"] = matched.get("recent_signal") or item.get("signal")
    except Exception:
        canonical_accounts = []
    ui_customers = customers_for_workbench(customers, todos)
    message_digest = build_message_digest()
    projects = build_projects(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT)
    rounds = project_rounds.followups(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT, projects=projects)
    risk_todos = risk_todos_payload(projects=projects, rounds=rounds)
    calendar_status = calendar_schedule_payload(deal_board, risk_todos.get("items", []), projects=projects, rounds=rounds)
    fxiaoke_status = fxiaoke_status_payload()
    prospecting = get_prospecting_payload(refresh_due=False)
    workflow_state = load_workflow_state()
    dashboard_risk_items = calendar_status.get("items", risk_todos.get("items", []))
    battle_actions = build_due_followup_actions([i for i in dashboard_risk_items if i.get("source_type") != "project_round"])
    battle_actions += [i for i in risk_todos["items"] if i.get("source_scope") in {"manual", "discovery"} and i.get("schedule_bucket") == "unscheduled"]
    battle_actions += [item for item in risk_todos["items"] if item.get("source_type") == "project_round" and item["schedule_bucket"] != "future"]
    battle_actions = [i for i in battle_actions if not i.get("sales_suppressed")]
    knowledge_timeline = build_knowledge_timeline()
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "knowledge_root": str(SALES_WORKBENCH_KNOWLEDGE_ROOT),
        "fxiaoke_status": fxiaoke_status,
        "prospecting": prospecting,
        "workflow_state": workflow_state,
        "risk_todos": dashboard_risk_items,
        "calendar_status": calendar_status,
        "summary": {
            "active_count": len(ui_customers["active"]),
            "active_project_count": sum(p["is_current"] and not p["archive"]["archived"] for p in project_archive.overlay(projects, WORKBENCH_DATA_ROOT, SALES_WORKBENCH_KNOWLEDGE_ROOT)),
            "potential_count": len(customers["potential"]),
            "pending_todos": len(todos["pending"]),
            "recent_intakes": len(list_recent_notes(INTAKE_ROOT, limit=20)),
            "message_days": len(message_digest["days"]),
            "message_total": message_digest["total_messages"],
        },
        "customers": ui_customers,
        "todos": todos,
        "deal_board": deal_board,
        "battle_actions": battle_actions,
        "risk_alerts": build_risk_alerts(deal_board, todos, message_digest),
        "message_digest": message_digest,
        "knowledge_timeline": knowledge_timeline,
        "sales_brain": build_sales_brain_payload(
            deal_board,
            battle_actions,
            calendar_status,
            fxiaoke_status,
            prospecting,
            message_digest,
            knowledge_timeline,
        ),
        "recent_intakes": list_recent_notes(INTAKE_ROOT),
        "recent_reports": list_recent_notes(REPORT_ROOT, limit=5),
        "rules": parse_work_rules(),
        "rule_candidates": get_rule_candidates(),
    }
    return normalize_display_names(payload)


def get_calendar_payload(refresh: bool = False) -> dict:
    customers = parse_client_registry()
    todos = parse_todo_log()
    deal_board = build_deal_board(customers, todos)
    try:
        canonical_accounts = account_store_rows()
        for item in deal_board:
            item["account_id"] = canonical_account_id(str(item.get("name") or ""), canonical_accounts)
    except Exception:
        pass
    risk_todos = risk_todos_payload()
    result = calendar_schedule_payload(deal_board, risk_todos.get("items", []), refresh=refresh)
    result["items"] = project_archive.decorate_items(result.get("items", []), WORKBENCH_DATA_ROOT, build_projects(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT))
    return result


def split_resolution_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    chunks = re.split(r"[。；;！？!?]|\s+-\s+|\n+", normalized)
    return [chunk.strip(" ，,：:") for chunk in chunks if chunk.strip(" ，,：:")]


def pick_resolution_lines(sentences: list[str], keywords: tuple[str, ...], limit: int = 3) -> list[str]:
    picked: list[str] = []
    for sentence in sentences:
        if any(keyword in sentence for keyword in keywords) and sentence not in picked:
            picked.append(sentence)
        if len(picked) >= limit:
            break
    return picked


def summarize_resolution(resolution: str, action: str, next_step: str, status: str) -> dict:
    sentences = split_resolution_sentences(resolution)
    done = pick_resolution_lines(
        sentences,
        ("已经", "已", "发了", "发给", "同步", "确认", "对齐", "约了", "拉了", "提交", "完成", "处理", "解决", "沟通"),
    )
    risk_change = pick_resolution_lines(
        sentences,
        ("风险", "卡点", "阻塞", "问题", "影响", "预算", "排期", "范围", "口径", "没问题", "不影响", "暂时"),
        limit=2,
    )
    next_lines = [next_step] if next_step else pick_resolution_lines(
        sentences,
        ("下一步", "后面", "后续", "待", "需要", "继续", "明天", "下周", "跟进"),
        limit=2,
    )
    conclusion = ""
    for sentence in sentences:
        if any(keyword in sentence for keyword in ("结论", "所以", "确认", "已经", "已", "完成", "闭环", "解决")):
            conclusion = sentence
            break
    if not conclusion and done:
        conclusion = done[0]
    if not conclusion:
        conclusion = sentences[0] if sentences else "已提交处理结果/当前进展，需结合原文查看。"

    return {
        "conclusion": conclusion,
        "done": done or [resolution[:160]],
        "risk_change": risk_change or [f"状态已标记为“{status}”，原风险建议为：{action or '未填写'}"],
        "next": next_lines or ["暂无下一步，视为本轮闭环。"],
    }


def parse_local_datetime(value: str) -> datetime | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("deadline 时间格式不正确") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TZ)
    return parsed.astimezone(LOCAL_TZ)


def load_risk_todos() -> list[dict]:
    payload = read_json_file(RISK_TODO_FILE, [])
    return payload if isinstance(payload, list) else []


def load_pm_daily_todos() -> list[dict]:
    payload = read_json_file(PM_DAILY_TODO_FILE, [])
    return payload if isinstance(payload, list) else []


def schedule_bucket_for_deadline(deadline: datetime | None, now: datetime) -> str:
    if not deadline:
        return "unscheduled"
    if deadline < now:
        return "overdue"
    if deadline.date() == now.date():
        return "today"
    if deadline.date() <= (now + timedelta(days=7)).date():
        return "week"
    return "later"


def enrich_schedule_timing(item: dict, deadline: datetime | None, now: datetime) -> dict:
    enriched = dict(item)
    if deadline:
        minutes = int((deadline - now).total_seconds() // 60)
        enriched["minutes_left"] = minutes
        enriched["schedule_bucket"] = schedule_bucket_for_deadline(deadline, now)
        if minutes < 0:
            enriched["countdown_label"] = f"已超期 {abs(minutes) // 1440} 天" if abs(minutes) >= 1440 else f"已超期 {abs(minutes)} 分钟"
            enriched["urgency"] = "overdue"
        elif minutes < 60:
            enriched["countdown_label"] = f"{minutes} 分钟后到期"
            enriched["urgency"] = "due"
        elif minutes < 1440:
            enriched["countdown_label"] = f"{minutes // 60} 小时后到期"
            enriched["urgency"] = "soon"
        else:
            enriched["countdown_label"] = f"{minutes // 1440} 天后到期"
            enriched["urgency"] = "normal"
    else:
        enriched["minutes_left"] = None
        enriched["schedule_bucket"] = "unscheduled"
        enriched["countdown_label"] = "未设置 deadline"
        enriched["urgency"] = "unknown"
    return enriched


def transcript_file_date(path: Path) -> date | None:
    match = re.search(r"(20\d{2})(\d{2})(\d{2})", path.name)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def infer_transcript_customer(path: Path, text: str) -> str:
    explicit = explicit_non_wenjie_labels(f"{path.parent.name} {path.name}")
    if len(explicit) == 1:
        return explicit[0]
    links = project_labels_from_wikilinks(text)
    if len(links) == 1:
        return links[0]
    source = f"{path.name}\n{text[:1200]}"
    if has_wenjie_context(source) and any(marker in source for marker in ("权益平台", "权益中台", "积分互换", "财经需求", "异业合作切口")):
        return "星海汽车权益平台"
    if has_wenjie_context(source) and any(marker in source for marker in ("星海汽车商城", "O2O", "门店调研", "经销商调研", "精品商城")):
        return "星海汽车商城"
    if any(alias in source for alias in ("星海汽车", "示例汽车集团", "DEMO_AUTO")):
        return "星海汽车商城"
    if "远航汽车" in source:
        return "远航汽车"
    if "松果宠物" in source:
        return "松果宠物宠物"
    if "清源健康" in source:
        return "清源健康健康"
    if "云杉百货" in source:
        return "云杉百货"
    return "通用待办"


def extract_transcript_next_actions(text: str) -> list[str]:
    tail = section_body(text, ("下一步", "后续动作", "行动建议"))
    actions: list[str] = []
    for raw_line in tail.splitlines():
        line = raw_line.strip()
        if not re.match(r"^(?:[-*]|\d+[.)、])\s", line) or re.match(r"^[-*]\s+\[[xX]\]", line):
            continue
        action = strip_html(re.sub(r"^(?:[-*]|\d+[.)、])\s*(?:\[ \]\s*)?", "", line))
        if action and action not in actions:
            actions.append(action)
    return actions


def transcript_deadline_for_date(file_day: date | None, now: datetime) -> datetime:
    base_day = file_day + timedelta(days=1) if file_day else now.date()
    return datetime(base_day.year, base_day.month, base_day.day, 10, 0, tzinfo=LOCAL_TZ)


def transcript_review_item(item: dict, review_at: datetime) -> dict:
    return {
        **item,
        "deadline": "",
        "review_at": review_at.isoformat(timespec="minutes"),
        "minutes_left": None,
        "schedule_bucket": "review",
        "countdown_label": "待判断",
        "urgency": "review",
    }


def transcript_package_id(customer: str, source_paths: list[str]) -> str:
    identity = "|".join([customer, *sorted(source_paths)])
    return f"transcript-package-{uuid.uuid5(uuid.NAMESPACE_URL, identity).hex[:12]}"


def transcript_candidate_package(customer: str, deadline: datetime, candidates: list[dict], now: datetime) -> dict:
    source_paths = sorted({str(item.get("source_path", "")) for item in candidates if item.get("source_path")})
    todo_id = transcript_package_id(customer, source_paths)
    count = len(candidates)
    preview_actions = [str(item.get("action", "")) for item in candidates[:8] if item.get("action")]
    evidence_lines = [
        f"近期录音/TXT整理候选材料包，共 {count} 条候选动作。",
        "",
        "候选动作：",
        *[f"{index + 1}. {action}" for index, action in enumerate(preview_actions)],
    ]
    if count > len(preview_actions):
        evidence_lines.append(f"...另有 {count - len(preview_actions)} 条候选动作未展开。")
    if source_paths:
        evidence_lines.extend(["", "来源文件：", *[f"- {path}" for path in source_paths[:6]]])
    title = f"{customer} · 录音/TXT待确认材料包（{count}条候选动作）"
    next_step = "逐条确认这批录音/TXT候选：转正式待办、并入现有 Deadline，或只沉淀到知识库。"
    return transcript_review_item(
        {
            "id": todo_id,
            "customer": customer,
            "title": title,
            "status": "待确认",
            "priority": "P1",
            "evidence": "\n".join(evidence_lines),
            "action": next_step,
            "next_step": next_step,
            "deadline": "",
            "reminder_minutes": 10,
            "resolution_path": "",
            "calendar": {"ok": False, "status": "skipped", "message": "录音/TXT候选材料包，待确认后再同步提醒"},
            "created_at": now.isoformat(timespec="seconds"),
            "source_scope": "transcript_intake",
            "source_type": "transcript_intake",
            "source_view": "录音/TXT待确认材料包",
            "projectLine": project_line_for_customer(customer),
            "transcript_candidate_count": count,
            "candidate_actions": candidates,
        },
        deadline,
    )


def build_transcript_todo_candidates(now: datetime, workflow_state: dict, limit: int = 8) -> list[dict]:
    if not TRANSCRIPT_ROOT.exists():
        return []
    candidates: list[dict] = []
    paths = sorted(
        TRANSCRIPT_ROOT.glob("**/*整理.md"),
        key=lambda item: item.stat().st_mtime if item.exists() else 0,
        reverse=True,
    )
    for path in paths[:24]:
        file_day = transcript_file_date(path)
        if file_day and file_day < (now.date() - timedelta(days=4)):
            continue
        text = read_text(path)
        actions = extract_transcript_next_actions(text)
        if not actions:
            continue
        customer = infer_transcript_customer(path, text)
        deadline = transcript_deadline_for_date(file_day, now)
        try:
            relative_path = str(path.relative_to(SALES_WORKBENCH_KNOWLEDGE_ROOT))
        except ValueError:
            relative_path = str(path)
        for action in actions[:3]:
            todo_id = f"transcript-{uuid.uuid5(uuid.NAMESPACE_URL, f'{relative_path}:{action}').hex[:12]}"
            state_record = workflow_state.get("schedule_status", {}).get(todo_id, {})
            if isinstance(state_record, dict) and (
                state_record.get("hidden")
                or isinstance(state_record.get("receipt"), dict)
                or isinstance(state_record.get("todo"), dict)
            ):
                continue
            candidates.append(
                transcript_review_item(
                    {
                        "id": todo_id,
                        "customer": customer,
                        "title": action,
                        "status": "待确认",
                        "priority": "P1",
                        "evidence": f"来自录音/TXT整理：{relative_path}",
                        "action": action,
                        "next_step": action,
                        "deadline": "",
                        "reminder_minutes": 10,
                        "resolution_path": "",
                        "calendar": {"ok": False, "status": "skipped", "message": "候选动作，确认后再创建提醒"},
                        "created_at": datetime.fromtimestamp(path.stat().st_mtime, LOCAL_TZ).isoformat(timespec="seconds"),
                        "source_scope": "transcript_intake",
                        "source_type": "transcript_intake",
                        "source_view": "录音/TXT候选动作",
                        "projectLine": project_line_for_customer(customer),
                        "transcript_candidate_count": 1,
                        "candidate_actions": [{"id": todo_id, "action": action, "source_path": relative_path}],
                    },
                    deadline,
                )
            )
    candidates.sort(key=lambda item: (item.get("minutes_left") is None, item.get("minutes_left") or 10**9, item.get("customer", "")))
    return candidates[:limit]


def is_superseded_schedule_todo(item: dict, workflow_state: dict) -> bool:
    todo_id = str(item.get("id") or item.get("workflow_key") or "").strip()
    if not todo_id:
        return False
    record = workflow_state.get("schedule_status", {}).get(todo_id)
    if not isinstance(record, dict):
        return False
    replacement_id = (
        record.get("receipt", {})
        .get("todo", {})
        .get("id", "")
    ) or record.get("todo", {}).get("id", "")
    return bool(replacement_id and replacement_id != todo_id)


def schedule_deadline_identity(item: dict) -> str:
    deadline_raw = str(item.get("deadline") or "").strip()
    if not deadline_raw:
        return ""
    try:
        deadline = parse_local_datetime(deadline_raw)
    except ValueError:
        return deadline_raw.replace(" ", "T")[:16]
    return deadline.isoformat(timespec="minutes")


def compact_followup_text(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(value or "").lower())


def followup_identity_text(item: dict) -> str:
    fields = [
        str(item.get("title") or ""),
        str(item.get("next_step") or ""),
        str(item.get("action") or ""),
    ]
    if item.get("source_type") == "feishu_calendar" or item.get("source_scope") == "feishu_calendar":
        fields.append(str(item.get("evidence") or ""))
    return compact_followup_text(" ".join(fields))


def common_prefix_length(left: str, right: str) -> int:
    count = 0
    for left_char, right_char in zip(left, right):
        if left_char != right_char:
            break
        count += 1
    return count


def char_ngrams(text: str, size: int = 2) -> set[str]:
    if not text:
        return set()
    if len(text) <= size:
        return {text}
    return {text[index : index + size] for index in range(0, len(text) - size + 1)}


def followup_text_similarity(left: str, right: str) -> float:
    left_grams = char_ngrams(left)
    right_grams = char_ngrams(right)
    if not left_grams or not right_grams:
        return 0.0
    return len(left_grams & right_grams) / len(left_grams | right_grams)


FOLLOWUP_ANCHOR_MARKERS = (
    "收敛7月上线排期",
    "7月上线",
    "人群包",
    "抽奖",
    "分享裂变",
    "分享有礼",
    "搜索优化",
    "示例预算",
    "48.2万",
    "482万",
    "框架补回",
    "框架承接",
    "O2O",
    "二期",
)


def shared_followup_markers(left: str, right: str) -> set[str]:
    return {marker for marker in FOLLOWUP_ANCHOR_MARKERS if marker.lower() in left and marker.lower() in right}


def is_similar_schedule_item(left: dict, right: dict) -> bool:
    left_id = str(left.get("id") or left.get("workflow_key") or "").strip()
    right_id = str(right.get("id") or right.get("workflow_key") or "").strip()
    if left_id and right_id and left_id == right_id:
        return True
    left_source = str(left.get("source_type") or left.get("source_scope") or "")
    right_source = str(right.get("source_type") or right.get("source_scope") or "")
    if {'project_round', 'discovery'} & {left_source, right_source}: return False
    if left.get('project_id') and right.get('project_id') and left['project_id'] != right['project_id']: return False
    if "manual" in {left_source, right_source} and left_id and right_id:
        return False

    left_customer = display_customer_name(str(left.get("customer") or "")).strip()
    right_customer = display_customer_name(str(right.get("customer") or "")).strip()
    if not left_customer or not right_customer or left_customer != right_customer:
        return False

    left_deadline = schedule_deadline_identity(left)
    right_deadline = schedule_deadline_identity(right)
    if not left_deadline or left_deadline != right_deadline:
        return False

    left_text = followup_identity_text(left)
    right_text = followup_identity_text(right)
    if min(len(left_text), len(right_text)) < 14:
        return False
    if common_prefix_length(left_text, right_text) >= 18:
        return True
    shared_markers = shared_followup_markers(left_text, right_text)
    if len(shared_markers) >= 3 and any(marker in shared_markers for marker in ("收敛7月上线排期", "7月上线", "人群包", "抽奖", "分享裂变", "分享有礼", "搜索优化")):
        return True
    return followup_text_similarity(left_text, right_text) >= 0.45


def schedule_item_timestamp(item: dict) -> float:
    for key in ("created_at", "updated_at", "submitted_at"):
        value = str(item.get(key) or "").strip()
        if not value:
            continue
        try:
            return parse_local_datetime(value).timestamp()
        except ValueError:
            continue
    return 0.0


def preferred_schedule_item(left: dict, right: dict) -> dict:
    def rank(item: dict) -> tuple[int, float, int, str]:
        source = str(item.get("source_type") or item.get("source_scope") or "")
        first_party = 0 if source == "feishu_calendar" else 1
        return (
            first_party,
            schedule_item_timestamp(item),
            len(followup_identity_text(item)),
            str(item.get("id") or ""),
        )

    return right if rank(right) >= rank(left) else left


def dedupe_similar_schedule_items(items: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    for item in items:
        match_index = next(
            (index for index, existing in enumerate(deduped) if is_similar_schedule_item(existing, item)),
            -1,
        )
        if match_index < 0:
            deduped.append(item)
        else:
            deduped[match_index] = preferred_schedule_item(deduped[match_index], item)
    return deduped


def risk_todos_payload(projects=None, rounds=None) -> dict:
    now = datetime.now(LOCAL_TZ)
    workflow_state = load_workflow_state()
    try:
        canonical_accounts = account_store_rows()
    except Exception:
        canonical_accounts = []
    items: list[dict] = []
    for item in load_risk_todos():
        if is_superseded_schedule_todo(item, workflow_state):
            continue
        todo_id = str(item.get("id") or item.get("workflow_key") or "").strip()
        state_record = workflow_state.get("schedule_status", {}).get(todo_id, {})
        if isinstance(state_record, dict) and state_record.get("hidden"):
            continue
        deadline_raw = str(item.get("deadline", ""))
        try:
            deadline = parse_local_datetime(deadline_raw)
        except ValueError:
            deadline = None
        enriched = enrich_schedule_timing({**item, "source_type": item.get("source_type") or item.get("source_scope", "workbench_deadline")}, deadline, now)
        enriched["account_id"] = enriched.get("account_id") or canonical_account_id(str(enriched.get("customer") or ""), canonical_accounts)
        items.append(enriched)
    # Extracted suggestions stay in project evidence/AI analysis. They are not
    # executed or scheduled work and must not create a second sales task queue.
    items = [item for item in items if item.get("source_type") != "transcript_intake"]
    projects = build_projects(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT) if projects is None else projects
    for item in items:
        project = project_activity.project_owner(item, projects)
        if project: item.update(project_id=project["id"], project_title=project["title"], project_source=project["source_path"])
    rounds = project_rounds.followups(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT, projects=projects) if rounds is None else rounds
    items = [i for i in items if i.get("id") not in rounds["claimed_actions"]]
    for item in rounds["items"]:
        items.append({**item, "project_title": item["title"], "workflow_key": item["id"], "todo_id": item["id"],
                      "source_type": "project_round", "source_scope": "project_round", "context_type": "project",
                      "deadline": item["due"], "resolution": item["feedback"],
                      "account_id": canonical_account_id(item["customer"].split('/')[-1], canonical_accounts),
                      "reminder_consent": {"enabled": False}, "calendar": {}, "signal": "项目执行记录"})
    items = dedupe_similar_schedule_items([i for i in items if i.get("source_type") != "project_round"]) + [i for i in items if i.get("source_type") == "project_round"]
    items.sort(key=lambda item: (item.get("minutes_left") is None, item.get("minutes_left") or 10**9))
    items = project_archive.decorate_items(items, WORKBENCH_DATA_ROOT, projects)
    delivery_state = load_feishu_reminder_delivery_state()
    items = attach_feishu_message_delivery(items, delivery_state, now)
    return normalize_display_names(
        {
            "ok": True,
            "items": items,
            "errors": rounds["errors"],
            "delivery": feishu_reminder_delivery_payload(items=items, state=delivery_state, now=now),
            "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )


def save_risk_todos(items: list[dict]) -> None:
    write_private_json(RISK_TODO_FILE, items)


def save_pm_daily_todos(items: list[dict]) -> None:
    write_private_json(PM_DAILY_TODO_FILE, items)


def create_feishu_calendar_event(
    *,
    customer: str,
    title: str,
    next_step: str,
    deadline: datetime,
    reminder_minutes: int,
    evidence_path: str,
    evidence: str,
    action: str,
) -> dict:
    end_time = deadline + timedelta(minutes=30)
    description = "\n".join(
        [
            f"客户/项目：{customer}",
            f"风险/待办：{title}",
            f"下一步：{next_step}",
            f"原始风险：{evidence or '未填写'}",
            f"建议动作：{action or '未填写'}",
            f"依据记录：{evidence_path}",
        ]
    )
    params = {
        "calendar_id": "primary",
        "idempotency_key": safe_filename(f"{customer}-{title}-{int(deadline.timestamp())}", "risk-todo")[:120],
    }
    data = {
        "summary": f"【待办】{customer}：{title[:42]}",
        "description": description,
        "start_time": {
            "timestamp": str(int(deadline.timestamp())),
            "timezone": "Asia/Shanghai",
        },
        "end_time": {
            "timestamp": str(int(end_time.timestamp())),
            "timezone": "Asia/Shanghai",
        },
        "reminders": [{"minutes": reminder_minutes}],
        "visibility": "default",
        "free_busy_status": "free",
        "vchat": {"vc_type": "no_meeting"},
    }
    result = run_json_command(
        [
            LARK_CLI_BIN,
            "calendar",
            "events",
            "create",
            "--as",
            "user",
            "--format",
            "json",
            "--params",
            json.dumps(params, ensure_ascii=False),
            "--data",
            json.dumps(data, ensure_ascii=False),
        ],
        timeout=35,
    )
    event = result.get("data", {}).get("event") or result.get("event") or {}
    return {
        "ok": True,
        "event_id": event.get("event_id", ""),
        "app_link": event.get("app_link", ""),
    }


def create_feishu_task_reminder(
    *,
    customer: str,
    title: str,
    next_step: str,
    deadline: datetime,
    reminder_minutes: int,
    evidence_path: str,
    evidence: str,
    action: str,
) -> dict:
    description = "\n".join(
        [
            f"客户/项目：{customer}",
            f"跟进事项：{title}",
            f"下一步：{next_step}",
            f"原始风险：{evidence or '未填写'}",
            f"建议动作：{action or '未填写'}",
            f"依据记录：{evidence_path}",
            "",
            "来源：工作台用户项目管理工作台",
        ]
    )
    client_token = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"sales-workbench-task:{customer}:{title}:{int(deadline.timestamp())}",
    ).hex
    data = {
        "summary": f"【销售跟进】{customer}：{title[:42]}",
        "description": description[:3000],
        "client_token": client_token,
        "due": {
            "timestamp": str(int(deadline.timestamp() * 1000)),
            "is_all_day": False,
        },
        "reminders": [{"relative_fire_minute": max(int(reminder_minutes), 0)}],
        "origin": {
            "platform_i18n_name": {"zh_cn": "工作台用户项目管理工作台"},
            "href": {
                "title": "打开项目管理工作台",
                "url": "http://127.0.0.1:8766/",
            },
        },
    }
    result = run_json_command(
        [
            LARK_CLI_BIN,
            "task",
            "tasks",
            "create",
            "--as",
            "user",
            "--format",
            "json",
            "--data",
            json.dumps(data, ensure_ascii=False),
        ],
        timeout=35,
    )
    task = result.get("data", {}).get("task") or result.get("task") or {}
    return {
        "ok": True,
        "type": "feishu_task",
        "task_guid": task.get("guid", ""),
        "task_id": task.get("task_id", ""),
        "app_link": task.get("url", ""),
    }


def feishu_task_identifier(calendar: dict | None) -> str:
    if not isinstance(calendar, dict):
        return ""
    return str(calendar.get("task_guid") or calendar.get("task_id") or "").strip()


def update_feishu_task_reminder(
    task_id: str,
    *,
    customer: str,
    title: str,
    next_step: str,
    deadline: datetime,
    reminder_minutes: int,
    evidence_path: str,
) -> dict:
    description = "\n".join(
        [
            f"客户/项目：{customer}",
            f"跟进事项：{title}",
            f"下一步：{next_step}",
            f"依据记录：{evidence_path}",
            "",
            "来源：工作台用户项目管理工作台",
        ]
    )
    result = run_json_command(
        [
            LARK_CLI_BIN,
            "task",
            "+update",
            "--as",
            "user",
            "--format",
            "json",
            "--task-id",
            task_id,
            "--summary",
            f"【销售跟进】{customer}：{title[:42]}",
            "--description",
            description[:3000],
            "--due",
            deadline.isoformat(timespec="minutes"),
        ],
        timeout=35,
    )
    run_json_command(
        [
            LARK_CLI_BIN,
            "task",
            "+reminder",
            "--as",
            "user",
            "--format",
            "json",
            "--task-id",
            task_id,
            "--set",
            f"{max(int(reminder_minutes), 0)}m",
        ],
        timeout=35,
    )
    task = result.get("data", {}).get("task") or result.get("task") or {}
    return {
        "ok": True,
        "type": "feishu_task",
        "task_guid": task.get("guid") or task_id,
        "task_id": task.get("task_id", ""),
        "app_link": task.get("url", ""),
        "status": "synced",
        "message": "飞书任务已更新；到期前将发送私聊提醒",
    }


def complete_feishu_task_reminder(task_id: str) -> dict:
    run_json_command(
        [
            LARK_CLI_BIN,
            "task",
            "+complete",
            "--as",
            "user",
            "--format",
            "json",
            "--task-id",
            task_id,
        ],
        timeout=35,
    )
    return {
        "ok": True,
        "type": "feishu_task",
        "task_guid": task_id,
        "status": "completed",
        "message": "已同步完成飞书任务提醒",
    }


def load_feishu_reminder_delivery_state() -> dict:
    payload = read_json_file(
        FEISHU_REMINDER_DELIVERY_FILE,
        {"version": 1, "deliveries": [], "updated_at": ""},
    )
    if not isinstance(payload, dict):
        payload = {}
    deliveries = payload.get("deliveries")
    return {
        "version": 1,
        "deliveries": deliveries if isinstance(deliveries, list) else [],
        "updated_at": str(payload.get("updated_at") or ""),
    }


def save_feishu_reminder_delivery_state(state: dict) -> None:
    payload = {
        "version": 1,
        "deliveries": list(state.get("deliveries") or [])[-240:],
        "updated_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
    }
    write_private_json(FEISHU_REMINDER_DELIVERY_FILE, payload)


def reminder_delivery_identity(kind: str, todo_id: str = "", deadline: str = "", day_key: str = "") -> str:
    raw = f"{kind}:{todo_id}:{deadline}:{day_key}"
    return f"reminder-{uuid.uuid5(uuid.NAMESPACE_URL, raw).hex[:20]}"


def reminder_delivery_record(state: dict, delivery_id: str) -> dict | None:
    return next(
        (
            item
            for item in state.get("deliveries", [])
            if isinstance(item, dict) and item.get("id") == delivery_id
        ),
        None,
    )


def reminder_delivery_sort_key(item: dict) -> str:
    return str(item.get("sent_at") or item.get("updated_at") or item.get("created_at") or "")


def reminder_delivery_should_attempt(existing: dict | None, now: datetime) -> bool:
    if not existing:
        return True
    if existing.get("status") == "sent":
        return False
    retry_raw = str(existing.get("next_retry_at") or "").strip()
    if not retry_raw:
        return True
    try:
        retry_at = parse_local_datetime(retry_raw)
    except ValueError:
        return True
    if not retry_at:
        return True
    return retry_at <= now


def record_feishu_reminder_delivery(
    state: dict,
    *,
    delivery_id: str,
    kind: str,
    todo_ids: list[str],
    deadline: str,
    day_key: str,
    title: str,
    result: dict | None = None,
    error: str = "",
) -> dict:
    now = datetime.now(LOCAL_TZ)
    existing = reminder_delivery_record(state, delivery_id) or {}
    attempts = int(existing.get("attempts") or 0) + 1
    status = "sent" if result is not None else "failed"
    record = {
        **existing,
        "id": delivery_id,
        "kind": kind,
        "todo_ids": todo_ids,
        "deadline": deadline,
        "day_key": day_key,
        "title": title,
        "status": status,
        "attempts": attempts,
        "message_id": str((result or {}).get("message_id") or existing.get("message_id") or ""),
        "sent_at": now.isoformat(timespec="seconds") if status == "sent" else str(existing.get("sent_at") or ""),
        "last_error": error,
        "next_retry_at": (
            ""
            if status == "sent"
            else (now + timedelta(minutes=min(60, 2 ** min(attempts, 5)))).isoformat(timespec="seconds")
        ),
        "created_at": str(existing.get("created_at") or now.isoformat(timespec="seconds")),
        "updated_at": now.isoformat(timespec="seconds"),
    }
    deliveries = [
        item
        for item in state.get("deliveries", [])
        if not isinstance(item, dict) or item.get("id") != delivery_id
    ]
    deliveries.append(record)
    state["deliveries"] = deliveries[-240:]
    save_feishu_reminder_delivery_state(state)
    return record


def send_feishu_reminder_message(text: str, idempotency_key: str) -> dict:
    if not FEISHU_REMINDER_ENABLED:
        raise RuntimeError("飞书私聊提醒未启用")
    if not FEISHU_REMINDER_CHAT_ID:
        raise RuntimeError("缺少 FEISHU_REMINDER_CHAT_ID")
    result = run_json_command(
        [
            LARK_CLI_BIN,
            "im",
            "+messages-send",
            "--as",
            "bot",
            "--chat-id",
            FEISHU_REMINDER_CHAT_ID,
            "--text",
            text,
            "--idempotency-key",
            idempotency_key,
        ],
        timeout=45,
    )
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    return {
        "ok": True,
        "message_id": str(
            message.get("message_id")
            or data.get("message_id")
            or result.get("message_id")
            or ""
        ),
    }


def compact_reminder_text(value: str, limit: int = 90) -> str:
    text = re.sub(r"\s+", " ", strip_html(str(value or ""))).strip()
    return text if len(text) <= limit else f"{text[: max(1, limit - 1)]}…"


def feishu_task_link(item: dict) -> str:
    calendar = item.get("calendar") if isinstance(item.get("calendar"), dict) else {}
    app_link = str(calendar.get("app_link") or "").strip()
    if app_link:
        return app_link
    task_guid = str(calendar.get("task_guid") or "").strip()
    task_id = str(calendar.get("task_id") or "").strip()
    if not task_guid:
        return ""
    suffix = f"&suite_entity_num={task_id}" if task_id else ""
    return f"https://applink.feishu.cn/client/todo/detail?guid={task_guid}{suffix}"


def format_due_reminder_message(item: dict, deadline: datetime) -> str:
    customer = str(item.get("customer") or "客户事项")
    title = compact_reminder_text(str(item.get("title") or item.get("next_step") or "待跟进事项"), 100)
    next_step = compact_reminder_text(str(item.get("next_step") or item.get("action") or title), 120)
    lines = [
        "⏰ 销售任务即将到期",
        "",
        f"客户：{customer}",
        f"任务：{title}",
        f"截止：{deadline.strftime('%m月%d日 %H:%M')}",
        f"下一步：{next_step}",
    ]
    task_link = feishu_task_link(item)
    if task_link:
        lines.extend(["", f"打开飞书任务：{task_link}"])
    lines.append("项目管理工作台：http://127.0.0.1:8766/")
    return "\n".join(lines)


def format_overdue_reminder_message(items: list[dict], now: datetime) -> str:
    lines = [
        f"🚨 销售任务超期提醒 · {now.strftime('%m月%d日')}",
        "",
        f"当前有 {len(items)} 条已超期、仍未闭环的任务：",
    ]
    for index, item in enumerate(items[:10], start=1):
        try:
            deadline = parse_local_datetime(str(item.get("deadline") or ""))
        except ValueError:
            deadline = now
        if not deadline:
            deadline = now
        overdue_minutes = max(1, int((now - deadline).total_seconds() // 60))
        overdue_label = (
            f"{max(1, overdue_minutes // 1440)} 天"
            if overdue_minutes >= 1440
            else f"{overdue_minutes} 分钟"
        )
        customer = str(item.get("customer") or "客户事项")
        title = compact_reminder_text(str(item.get("title") or item.get("next_step") or "待跟进事项"), 90)
        next_step = compact_reminder_text(str(item.get("next_step") or item.get("action") or ""), 110)
        lines.extend(
            [
                "",
                f"{index}. {customer}｜已超期 {overdue_label}",
                f"   {title}",
            ]
        )
        if next_step and next_step != title:
            lines.append(f"   下一步：{next_step}")
        task_link = feishu_task_link(item)
        if task_link:
            lines.append(f"   飞书任务：{task_link}")
    if len(items) > 10:
        lines.extend(["", f"另有 {len(items) - 10} 条请在工作台查看。"])
    lines.extend(
        [
            "",
            "请今天逐条选择：完成、延期，或更新下一步。",
            "项目管理工作台：http://127.0.0.1:8766/",
        ]
    )
    return "\n".join(lines)


def is_feishu_message_todo(item: dict) -> bool:
    if item.get("source_scope") in {"transcript_intake", "project_round"}:
        return False
    calendar = item.get("calendar") if isinstance(item.get("calendar"), dict) else {}
    return bool(feishu_task_identifier(calendar))


def feishu_reminder_gate(item: dict, now: datetime) -> dict:
    """Consent and time guard shared by UI and sender. Never infer consent from AI dates."""
    a = project_archive.state(WORKBENCH_DATA_ROOT, item.get("project_id"))
    if item.get("sales_suppressed") or project_archive.is_suppressed(a, item):
        return {"eligible": False, "status": "archived", "label": "项目已归档或旧提醒待重新确认，不自动催办"}
    if item.get("status") in {"已处理", "已完成", "已闭环", "已取消", "cancelled", "completed"}:
        return {"eligible": False, "status": "closed", "label": "已结束，不再提醒"}
    if item.get("source_scope") not in {"manual", "workflow_receipt"}:
        return {"eligible": False, "status": "needs_review", "label": "待确认事项与时间，不自动提醒"}
    try:
        deadline = parse_local_datetime(str(item.get("deadline") or ""))
    except ValueError:
        deadline = None
    if not deadline:
        return {"eligible": False, "status": "needs_review", "label": "待确认提醒时间"}
    consent = item.get("reminder_consent")
    if isinstance(consent, dict):
        try:
            confirmed = parse_local_datetime(str(consent.get("confirmed_at") or ""))
            consent_deadline = parse_local_datetime(str(consent.get("deadline") or ""))
        except ValueError:
            confirmed = consent_deadline = None
        if consent.get("enabled") is not True or not confirmed or confirmed > now or consent_deadline != deadline:
            return {"eligible": False, "status": "needs_review", "label": "未确认本次飞书提醒，留在工作台"}
    elif not (is_feishu_message_todo(item) and (item.get("resolution_path") or item.get("source_scope") == "manual")):
        return {"eligible": False, "status": "needs_review", "label": "历史事项缺少提醒确认，留在工作台"}
    if deadline < now:
        return {"eligible": False, "status": "needs_review", "label": "已过期，待重新安排；不补发、不每日催办"}
    return {"eligible": True, "status": "scheduled", "label": "已确认，将在约定时间前提醒一次"}


def attach_feishu_message_delivery(items: list[dict], state: dict, now: datetime) -> list[dict]:
    records = [item for item in state.get("deliveries", []) if isinstance(item, dict)]
    today_key = now.date().isoformat()
    enriched_items: list[dict] = []
    for item in items:
        enriched = dict(item)
        todo_id = str(item.get("id") or item.get("workflow_key") or "").strip()
        deadline_raw = schedule_deadline_identity(item)
        matching = [
            record
            for record in records
            if todo_id
            and (
                todo_id in (record.get("todo_ids") or [])
                or (
                    record.get("kind") == "due_soon"
                    and record.get("todo_id") == todo_id
                    and record.get("deadline") == deadline_raw
                )
            )
        ]
        matching.sort(key=reminder_delivery_sort_key, reverse=True)
        latest = matching[0] if matching else {}
        today_digest = next(
            (
                record
                for record in matching
                if record.get("kind") == "overdue_digest"
                and record.get("day_key") == today_key
                and record.get("status") == "sent"
            ),
            None,
        )
        matching_due = next(
            (
                record
                for record in matching
                if record.get("kind") == "due_soon"
                and record.get("deadline") == deadline_raw
                and record.get("status") == "sent"
            ),
            None,
        )
        if not FEISHU_REMINDER_ENABLED or not FEISHU_REMINDER_CHAT_ID:
            delivery = {"status": "disabled", "label": "飞书私聊未启用"}
        elif not feishu_reminder_gate(item, now)["eligible"]:
            delivery = feishu_reminder_gate(item, now)
        elif matching_due:
            delivery = {
                "status": "sent",
                "label": "到期前私聊已发送",
                "kind": "due_soon",
                "message_id": matching_due.get("message_id", ""),
                "sent_at": matching_due.get("sent_at", ""),
            }
        elif latest.get("status") == "failed" and latest.get("kind") == "due_soon" and latest.get("deadline") == deadline_raw:
            delivery = {
                "status": "failed",
                "label": "飞书私聊发送失败，仅在本次提醒时间窗内重试",
                "kind": latest.get("kind", ""),
                "last_error": latest.get("last_error", ""),
                "next_retry_at": latest.get("next_retry_at", ""),
            }
        else:
            delivery = feishu_reminder_gate(item, now)
        enriched["message_delivery"] = delivery
        enriched_items.append(enriched)
    return enriched_items


def feishu_reminder_delivery_payload(
    *,
    items: list[dict] | None = None,
    state: dict | None = None,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(LOCAL_TZ)
    state = state or load_feishu_reminder_delivery_state()
    records = [item for item in state.get("deliveries", []) if isinstance(item, dict)]
    records.sort(key=reminder_delivery_sort_key, reverse=True)
    successes = [item for item in records if item.get("status") == "sent"]
    failures = [item for item in records if item.get("status") == "failed"]
    return {
        "enabled": FEISHU_REMINDER_ENABLED,
        "configured": bool(FEISHU_REMINDER_CHAT_ID),
        "status": "disabled" if not FEISHU_REMINDER_ENABLED or not FEISHU_REMINDER_CHAT_ID else ("failed" if failures else "healthy"),
        "policy": {
            "due": "仅明确确认的事项，在约定时间前发送一次飞书私聊" if FEISHU_REMINDER_ENABLED else "飞书私聊自动提醒已关闭，原任务保留",
            "overdue": "每日超期汇总已关闭；过期事项留在工作台复核，不补发",
            "retry": "只在有效提醒时间窗内退避重试，不复活旧任务；幂等防重复" if FEISHU_REMINDER_ENABLED else "已停用自动发送与重试；不影响只读日报同步",
        },
        "active_count": len(items or []),
        "eligible_count": sum(feishu_reminder_gate(item, now)["eligible"] for item in items or []),
        "review_count": sum(not feishu_reminder_gate(item, now)["eligible"] for item in items or []),
        "sent_count": len(successes),
        "failed_count": len(failures),
        "last_success_at": str(successes[0].get("sent_at") or "") if successes else "",
        "last_error": str(failures[0].get("last_error") or "") if failures else "",
        "history": records[:20],
        "updated_at": str(state.get("updated_at") or ""),
        "generated_at": now.isoformat(timespec="seconds"),
    }


def process_feishu_reminder_deliveries(force_overdue: bool = False) -> dict:
    now = datetime.now(LOCAL_TZ)
    if not FEISHU_REMINDER_ENABLED or not FEISHU_REMINDER_CHAT_ID:
        return {
            "ok": False,
            "status": "disabled",
            "sent": 0,
            "failed": 0,
            "message": "飞书私聊提醒未启用或未配置接收会话",
        }

    with FEISHU_REMINDER_DELIVERY_LOCK:
        state = load_feishu_reminder_delivery_state()
        payload = risk_todos_payload()
        candidates: list[tuple[dict, datetime]] = []
        overdue: list[dict] = []
        for item in payload.get("items", []):
            if not isinstance(item, dict):
                continue
            try:
                deadline = parse_local_datetime(str(item.get("deadline") or ""))
            except ValueError:
                continue
            if not deadline:
                continue
            if deadline < now:
                overdue.append(item)
            if feishu_reminder_gate(item, now)["eligible"]:
                candidates.append((item, deadline))

        sent = 0
        failed = 0
        results: list[dict] = []
        for item, deadline in candidates:
            reminder_minutes = max(0, int(item.get("reminder_minutes") or 10))
            seconds_left = (deadline - now).total_seconds()
            if seconds_left < 0 or seconds_left > reminder_minutes * 60:
                continue
            todo_id = str(item.get("id") or item.get("workflow_key") or "").strip()
            deadline_key = deadline.isoformat(timespec="minutes")
            delivery_id = reminder_delivery_identity("due_soon", todo_id, deadline_key)
            existing = reminder_delivery_record(state, delivery_id)
            if not reminder_delivery_should_attempt(existing, now):
                continue
            try:
                with project_archive.locked(WORKBENCH_DATA_ROOT):
                    if not feishu_reminder_gate(item, datetime.now(LOCAL_TZ))["eligible"]: continue
                    result = send_feishu_reminder_message(
                        format_due_reminder_message(item, deadline),
                        delivery_id,
                    )
                record = record_feishu_reminder_delivery(
                    state,
                    delivery_id=delivery_id,
                    kind="due_soon",
                    todo_ids=[todo_id],
                    deadline=deadline_key,
                    day_key=now.date().isoformat(),
                    title=f"{item.get('customer') or '客户事项'} · 到期前提醒",
                    result=result,
                )
                sent += 1
            except Exception as exc:
                record = record_feishu_reminder_delivery(
                    state,
                    delivery_id=delivery_id,
                    kind="due_soon",
                    todo_ids=[todo_id],
                    deadline=deadline_key,
                    day_key=now.date().isoformat(),
                    title=f"{item.get('customer') or '客户事项'} · 到期前提醒",
                    error=calendar_failure_reason(exc),
                )
                failed += 1
            results.append(record)

        # No overdue sending path. force_overdue remains a backwards-compatible
        # request argument but can never reactivate the retired bulk digest.
        return {
            "ok": failed == 0,
            "status": "sent" if sent else ("failed" if failed else "no_change"),
            "sent": sent,
            "failed": failed,
            "overdue_count": len(overdue),
            "results": results,
            "delivery": feishu_reminder_delivery_payload(
                items=payload.get("items", []),
                state=state,
                now=now,
            ),
        }


def feishu_reminder_scheduler_loop() -> None:
    time.sleep(5)
    while True:
        try:
            process_feishu_reminder_deliveries()
        except Exception as exc:
            print(f"feishu-reminder: {calendar_failure_reason(exc)}", file=sys.stderr, flush=True)
        time.sleep(FEISHU_REMINDER_SCAN_SECONDS)


def load_external_sync_outbox() -> list[dict]:
    payload = read_json_file(EXTERNAL_SYNC_OUTBOX_FILE, [])
    return payload if isinstance(payload, list) else []


def enqueue_external_sync(operation: str, task_id: str, payload: dict, error: str = "") -> str:
    if operation not in {"complete", "update"} or not task_id:
        return ""
    now = datetime.now(LOCAL_TZ)
    identity = str(payload.get("receipt_id") or payload.get("todo_id") or uuid.uuid4().hex)
    outbox_id = f"feishu-{uuid.uuid5(uuid.NAMESPACE_URL, f'{operation}:{task_id}:{identity}').hex[:16]}"
    with STATE_FILE_LOCK:
        items = [item for item in load_external_sync_outbox() if item.get("id") != outbox_id]
        items.append({
            "id": outbox_id,
            "operation": operation,
            "task_id": task_id,
            "payload": payload,
            "status": "pending",
            "attempts": 1,
            "last_error": error,
            "next_retry_at": (now + timedelta(minutes=2)).isoformat(timespec="seconds"),
            "updated_at": now.isoformat(timespec="seconds"),
        })
        write_private_json(EXTERNAL_SYNC_OUTBOX_FILE, items[-100:])
    return outbox_id


def process_external_sync_outbox(limit: int = 10, force: bool = False) -> dict:
    now = datetime.now(LOCAL_TZ)
    with STATE_FILE_LOCK:
        snapshot = load_external_sync_outbox()
    selected: list[dict] = []
    for item in snapshot:
        if len(selected) >= limit or item.get("status") != "pending":
            continue
        try:
            retry_at = parse_local_datetime(str(item.get("next_retry_at") or ""))
        except ValueError:
            retry_at = None
        if force or not retry_at or retry_at <= now:
            selected.append(dict(item))

    results: dict[str, dict | None] = {}
    completed = 0
    for item in selected:
        operation = str(item.get("operation") or "")
        task_id = str(item.get("task_id") or "")
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        with project_archive.locked(WORKBENCH_DATA_ROOT):
            if operation == "update":
                origin = next((x for x in load_risk_todos() if x.get("id") == payload.get("todo_id")), payload)
                project = project_activity.project_owner(origin, build_projects(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT))
                if project:
                    a = project_archive.state(WORKBENCH_DATA_ROOT, project["id"])
                    if a["archived"] or str(payload.get("todo_id", "")) in a["suppressed_task_ids"]:
                        results[str(item.get("id") or "")] = {**item, "archive_hold": True, "last_error": "归档项目的原提醒保留，暂停自动重试"}
                        continue
            try:
                if operation == "complete":
                    complete_feishu_task_reminder(task_id)
                elif operation == "update":
                    deadline = parse_local_datetime(str(payload.get("deadline") or ""))
                    if not deadline:
                        raise ValueError("飞书任务补偿缺少 deadline")
                    update_feishu_task_reminder(
                        task_id,
                        customer=str(payload.get("customer") or ""),
                        title=str(payload.get("title") or ""),
                        next_step=str(payload.get("next_step") or ""),
                        deadline=deadline,
                        reminder_minutes=int(payload.get("reminder_minutes") or 10),
                        evidence_path=str(payload.get("evidence_path") or ""),
                    )
                else:
                    raise ValueError("未知飞书补偿操作")
                completed += 1
                results[str(item.get("id") or "")] = None
            except Exception as exc:
                attempts = int(item.get("attempts") or 0) + 1
                item["attempts"] = attempts
                item["last_error"] = calendar_failure_reason(exc)
                item["next_retry_at"] = (now + timedelta(minutes=min(60, 2 ** min(attempts, 5)))).isoformat(timespec="seconds")
                item["updated_at"] = now.isoformat(timespec="seconds")
                results[str(item.get("id") or "")] = item
    
    with STATE_FILE_LOCK:
        current = load_external_sync_outbox()
        remaining = []
        for item in current:
            item_id = str(item.get("id") or "")
            if item_id not in results:
                remaining.append(item)
            elif results[item_id] is not None:
                remaining.append(results[item_id])
        write_private_json(EXTERNAL_SYNC_OUTBOX_FILE, remaining[-100:])
    return {"ok": True, "processed": len(selected), "completed": completed, "pending": len(remaining)}


def event_time_to_datetime(value: dict, end_of_day: bool = False) -> datetime | None:
    if not isinstance(value, dict):
        return None
    if value.get("timestamp"):
        try:
            return datetime.fromtimestamp(int(value["timestamp"]), LOCAL_TZ)
        except (TypeError, ValueError, OSError):
            return None
    if value.get("date"):
        try:
            parsed_date = date.fromisoformat(str(value["date"]))
        except ValueError:
            return None
        base_time = datetime.max.time().replace(hour=23, minute=59, second=0, microsecond=0) if end_of_day else datetime.min.time()
        return datetime.combine(parsed_date, base_time, tzinfo=LOCAL_TZ)
    return None


def time_range_label(start_at: datetime | None, end_at: datetime | None) -> str:
    if not start_at:
        return "时间待确认"
    if end_at and start_at.date() == end_at.date():
        return f"{start_at.strftime('%m-%d %H:%M')} - {end_at.strftime('%H:%M')}"
    if end_at:
        return f"{start_at.strftime('%m-%d %H:%M')} - {end_at.strftime('%m-%d %H:%M')}"
    return start_at.strftime("%m-%d %H:%M")


def feishu_event_cache_window(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return start, end


def _refresh_feishu_calendar(cache_path, start_at, end_at, job):
    """One writer per cache. A failed refresh never replaces the last snapshot."""
    try:
        result = run_json_command(
            [
                LARK_CLI_BIN,
                "calendar",
                "events",
                "instance_view",
                "--as",
                "user",
                "--format",
                "json",
                "--params",
                json.dumps(
                    {
                        "calendar_id": "primary",
                        "start_time": str(int(start_at.timestamp())),
                        "end_time": str(int(end_at.timestamp())),
                    },
                    ensure_ascii=False,
                ),
            ],
            timeout=35,
        )
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ValueError("飞书未返回有效日程列表，不能认定没有日程")
        payload = {
            "ok": True,
            "range_key": job["range_key"],
            "fetched_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
            "fetched_at_ts": int(time.time()),
            "items": data["items"],
            "error": "",
        }
        write_private_json(cache_path, payload)
        with FEISHU_CALENDAR_READ_LOCK:
            job.update(result=payload, error="", retry_at=0)
    except Exception as exc:
        with FEISHU_CALENDAR_READ_LOCK:
            job.update(error=calendar_failure_reason(exc).replace("飞书创建请求超时", "飞书日程读取超时"), retry_at=time.time()+FEISHU_CALENDAR_READ_RETRY_SECONDS)
    finally:
        with FEISHU_CALENDAR_READ_LOCK:
            job["running"] = False
            job["done"].set()


def _calendar_cached_response(cache, range_key, job=None, force=False):
    job = job or {}
    available = bool(isinstance(cache, dict) and cache.get("range_key") == range_key
                     and cache.get("fetched_at_ts") and isinstance(cache.get("items"), list))
    same_job = job.get("range_key") == range_key
    error = job.get("error", "") if same_job else ""
    refreshing = bool(job.get("running"))
    stale = not available or int(cache.get("fetched_at_ts") or 0) <= time.time()-180 or bool(error)
    if error:
        message = "飞书日程更新失败"+("，显示上次结果：" if available else "，尚未读取当前日程：")+error
    elif refreshing:
        message = "飞书日程更新中，显示上次结果" if available else "正在读取飞书日程，尚不能确认有无日程"
    else:
        message = "" if available else "尚未读取当前窗口的飞书日程"
    return {**(cache if available else {}), "ok": available and not (force and bool(error)),
            "range_key": range_key, "items": cache["items"] if available else [],
            "fetched_at": cache.get("fetched_at", "") if available else "",
            "fetched_at_ts": cache.get("fetched_at_ts", 0) if available else 0,
            "from_cache": available, "cache_available": available, "stale": stale,
            "refreshing": refreshing, "refresh_error": error, "error": message,
            "read_state": "refreshing" if refreshing else "error" if error else "ready" if available and not stale else "stale" if available else "unread"}


def fetch_feishu_calendar_instances(start_at: datetime, end_at: datetime, refresh: bool = False) -> dict:
    cache_path = Path(FEISHU_CALENDAR_CACHE)
    key = str(cache_path.resolve())
    range_key = f"{int(start_at.timestamp())}:{int(end_at.timestamp())}"
    with FEISHU_CALENDAR_READ_LOCK:
        cache = read_json_file(cache_path, {})
        job = FEISHU_CALENDAR_READ_JOBS.get(key, {})
        view = _calendar_cached_response(cache, range_key, job)
        if not refresh and view["cache_available"] and not view["stale"]:
            return view
        if not job.get("running") and (refresh or job.get("range_key") != range_key or job.get("retry_at", 0) <= time.time()):
            prior_error = job.get("error", "") if job.get("range_key") == range_key else ""
            job = {"range_key": range_key, "running": True, "done": threading.Event(), "error": prior_error, "retry_at": 0}
            FEISHU_CALENDAR_READ_JOBS[key] = job
            try:
                threading.Thread(target=_refresh_feishu_calendar, args=(cache_path, start_at, end_at, job), daemon=True, name="calendar-cache-refresh").start()
            except Exception:
                job.update(running=False, error="未能启动日程后台更新", retry_at=time.time()+FEISHU_CALENDAR_READ_RETRY_SECONDS)
                job["done"].set()
        if not refresh:
            return _calendar_cached_response(cache, range_key, job)
    # Explicit user refresh retains its synchronous completion/error receipt,
    # joining an existing read rather than starting a competing CLI invocation.
    job["done"].wait()
    if job["range_key"] != range_key:
        return fetch_feishu_calendar_instances(start_at, end_at, refresh=True)
    with FEISHU_CALENDAR_READ_LOCK:
        view = _calendar_cached_response(job.get("result") or read_json_file(cache_path, {}), range_key, job, force=True)
        if not job.get("error"):
            view["from_cache"] = False
        return view


def event_matching_text(event: dict) -> str:
    attendees = event.get("attendees") if isinstance(event.get("attendees"), list) else []
    attendee_text = " ".join(str(item.get("display_name", "")) for item in attendees if isinstance(item, dict))
    organizer = event.get("event_organizer") if isinstance(event.get("event_organizer"), dict) else {}
    return " ".join(
        [
            str(event.get("summary", "")),
            str(event.get("description", "")),
            str(organizer.get("display_name", "")),
            attendee_text,
        ]
    )


def unmatched_calendar_customer(text: str) -> str:
    if any(keyword in text for keyword in ("山岚", "宜宾酒", "成都酒业")):
        return "山岚酒业"
    if "示例药业" in text:
        return "云南示例药业"
    if any(keyword in text for keyword in ("小组周会", "部门会议", "周常分享", "全员")):
        return "待匹配日程"
    return "待匹配日程"


ROUTINE_UNMATCHED_CALENDAR_PATTERNS = (
    "AI应用分享",
    "AI 应用分享",
    "应用分享",
    "大客&广告周常分享",
    "大客广告周常分享",
    "周常分享",
    "周常",
    "分享会",
    "内部分享",
    "培训",
    "例会",
    "小组周会",
    "内部周会",
    "部门会议",
    "全员",
)


def is_routine_unmatched_calendar_item(item: dict) -> bool:
    source = str(item.get("source_type") or item.get("source_scope") or "")
    if source != "feishu_calendar":
        return False
    if item.get("matched_customer"):
        return False
    if str(item.get("customer") or "") != "待匹配日程":
        return False
    text = " ".join(
        str(item.get(key) or "")
        for key in ("title", "evidence", "action", "next_step", "projectLine")
    )
    normalized = re.sub(r"\s+", "", text)
    return any(pattern in text or pattern in normalized for pattern in ROUTINE_UNMATCHED_CALENDAR_PATTERNS)


def normalize_calendar_event(event: dict, deal_board: list[dict], now: datetime, include_background: bool = False) -> dict | None:
    if event.get("status") == "cancelled":
        return None
    start_at = event_time_to_datetime(event.get("start_time", {}))
    end_at = event_time_to_datetime(event.get("end_time", {}), end_of_day=True)
    if not start_at:
        return None
    text = event_matching_text(event)
    board_item = find_board_item_for_text(text, deal_board)
    customer = board_item.get("name") if board_item else unmatched_calendar_customer(text)
    is_matched = bool(board_item)
    status = "待会后回填" if start_at < now and (not end_at or end_at < now) else "已同步"
    event_id = str(event.get("event_id", ""))
    item = {
        "id": f"feishu:{event_id}",
        "account_id": board_item.get("account_id", "") if board_item else "",
        "customer": customer,
        "matched_customer": is_matched,
        "title": str(event.get("summary", "") or "飞书日程"),
        "status": status,
        "evidence": str(event.get("description", "")),
        "action": "会前确认目标、风险和下一步；会后回填结论。",
        "next_step": "会后回填结论，并决定是否生成下一步。",
        "deadline": start_at.isoformat(timespec="minutes"),
        "end_time": end_at.isoformat(timespec="minutes") if end_at else "",
        "time_label": time_range_label(start_at, end_at),
        "reminder_minutes": 10,
        "resolution_path": "",
        "calendar": {
            "ok": True,
            "event_id": event_id,
            "app_link": event.get("app_link", ""),
            "status": "synced",
            "message": "飞书日程",
            "meeting_url": (event.get("vchat") or {}).get("meeting_url", "") if isinstance(event.get("vchat"), dict) else "",
            "organizer": (event.get("event_organizer") or {}).get("display_name", "") if isinstance(event.get("event_organizer"), dict) else "",
        },
        "created_at": "",
        "source_scope": "feishu_calendar",
        "source_type": "feishu_calendar",
        "projectLine": project_line_for_customer(customer) if is_matched else "待匹配日程",
    }
    if is_routine_unmatched_calendar_item(item) and not include_background:
        return None
    return enrich_schedule_timing(item, start_at, now)


def calendar_item_event_id(item: dict) -> str:
    calendar = item.get("calendar") if isinstance(item.get("calendar"), dict) else {}
    event_id = str(calendar.get("event_id") or "").strip()
    item_id = str(item.get("id") or "").strip()
    if event_id:
        return event_id
    if item_id.startswith("feishu:"):
        return item_id.removeprefix("feishu:")
    return ""


def calendar_title_text(item: dict) -> str:
    return compact_followup_text(str(item.get("title") or ""))


def calendar_titles_similar(left: dict, right: dict) -> bool:
    left_title = calendar_title_text(left)
    right_title = calendar_title_text(right)
    if not left_title or not right_title:
        return False
    if left_title in right_title or right_title in left_title:
        return True
    if common_prefix_length(left_title, right_title) >= 4 and left_title[-2:] == right_title[-2:]:
        return True
    return followup_text_similarity(left_title, right_title) >= 0.45


def same_calendar_meeting_group(left: dict, right: dict) -> bool:
    left_customer = display_customer_name(str(left.get("customer") or "")).strip()
    right_customer = display_customer_name(str(right.get("customer") or "")).strip()
    if not left_customer or left_customer != right_customer:
        return False
    left_start = schedule_deadline_identity(left)
    right_start = schedule_deadline_identity(right)
    if not left_start or left_start != right_start:
        return False
    return calendar_titles_similar(left, right)


def handled_calendar_items(calendar_items: list[dict], workflow_state: dict | None) -> list[dict]:
    if not isinstance(workflow_state, dict):
        return []
    by_id: dict[str, dict] = {}
    for item in calendar_items:
        item_id = str(item.get("id") or "").strip()
        event_id = calendar_item_event_id(item)
        if item_id:
            by_id[item_id] = item
        if event_id:
            by_id[f"feishu:{event_id}"] = item

    handled: list[dict] = []
    for key, record in (workflow_state.get("schedule_status") or {}).items():
        if not isinstance(record, dict) or not isinstance(record.get("receipt"), dict):
            continue
        if not str(key).startswith("feishu:"):
            continue
        item = by_id.get(str(key))
        if item:
            handled.append(item)
    return handled


def is_handled_calendar_duplicate(item: dict, handled_items: list[dict]) -> bool:
    if str(item.get("source_type") or item.get("source_scope") or "") != "feishu_calendar":
        return False
    return any(same_calendar_meeting_group(item, handled) for handled in handled_items)


def merge_schedule_items(deadline_items: list[dict], calendar_items: list[dict], workflow_state: dict | None = None) -> list[dict]:
    known_event_ids = {
        str((item.get("calendar") or {}).get("event_id", ""))
        for item in deadline_items
        if isinstance(item.get("calendar"), dict)
    }
    handled_items = handled_calendar_items(calendar_items, workflow_state)
    merged = [item for item in deadline_items if not is_routine_unmatched_calendar_item(item)]
    for item in calendar_items:
        if is_routine_unmatched_calendar_item(item):
            continue
        if is_handled_calendar_duplicate(item, handled_items):
            continue
        event_id = str((item.get("calendar") or {}).get("event_id", ""))
        if event_id and event_id in known_event_ids:
            continue
        merged.append(item)
    merged = dedupe_similar_schedule_items(merged)
    merged.sort(key=lambda item: (item.get("minutes_left") is None, item.get("minutes_left") or 10**9, item.get("customer", "")))
    return merged


def calendar_schedule_payload(deal_board: list[dict], deadline_items: list[dict], refresh: bool = False, projects=None, rounds=None) -> dict:
    projects = build_projects(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT) if projects is None else projects
    rounds = project_rounds.followups(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT, projects=projects) if rounds is None else rounds
    now = datetime.now(LOCAL_TZ)
    start_at, end_at = feishu_event_cache_window(now)
    fetched = fetch_feishu_calendar_instances(start_at, end_at, refresh=refresh)
    normalized = []
    for event in fetched.get("items", []):
        if not isinstance(event, dict):
            continue
        item = normalize_calendar_event(event, deal_board, now, include_background=True)
        if item:
            item["source_cached"] = bool(fetched.get("from_cache"))
            normalized.append(item)
    normalized = link_project_calendar_items(normalized, projects, SALES_WORKBENCH_KNOWLEDGE_ROOT)
    background_items = [dict(i, calendar_background=True) for i in normalized if not i.get("matched_customer") and not i.get("project_id")]
    background_ids = {i.get("id") for i in background_items}
    normalized = [i for i in normalized if i.get("id") not in background_ids]
    claimed = rounds['claimed_actions']
    inherited_events = {str((i.get('calendar') or {}).get('event_id') or '') for i in load_risk_todos() if i.get('id') in claimed}
    normalized = [i for i in normalized if i.get('id') not in claimed and not (calendar_item_event_id(i) and calendar_item_event_id(i) in inherited_events)]
    merged = merge_schedule_items([i for i in deadline_items if i.get("id") not in background_ids], normalized, load_workflow_state())
    return {
        "ok": bool(fetched.get("ok")),
        "label": "飞书日程更新中" if fetched.get("refreshing") else "飞书日程更新失败" if fetched.get("refresh_error") else "飞书日程已同步" if fetched.get("ok") and not fetched.get("stale") else "飞书日程待更新",
        "error": fetched.get("error", ""),
        "from_cache": bool(fetched.get("from_cache")),
        "fetched_at": fetched.get("fetched_at", ""),
        **{key: fetched.get(key) for key in ("cache_available", "stale", "refreshing", "refresh_error", "read_state")},
        "window": {
            "start": start_at.isoformat(timespec="minutes"),
            "end": end_at.isoformat(timespec="minutes"),
        },
        "background_items": background_items,
        "feishu_count": len(normalized),
        "deadline_count": len(deadline_items),
        "unmatched_count": sum(1 for item in normalized if not item.get("matched_customer")),
        "items": project_archive.decorate_items(merged, WORKBENCH_DATA_ROOT, projects),
    }


def append_risk_todo(todo: dict) -> None:
    with project_archive.locked(WORKBENCH_DATA_ROOT), STATE_FILE_LOCK:
        project = project_activity.project_owner(todo, build_projects(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT))
        if project:
            a = project_archive.state(WORKBENCH_DATA_ROOT, project["id"])
            if a["archived"] or todo.get("archive_revision", 0) != a["revision"]:
                raise project_rounds.RevisionConflict("项目归档状态已变化，未新增销售提醒，请重新核对")
        items = [
            item
            for item in load_risk_todos()
            if item.get("id") != todo.get("id") and not is_similar_schedule_item(item, todo)
        ]
        items.append(todo)
        items = dedupe_similar_schedule_items(items)
        items.sort(key=lambda item: item.get("deadline") or "")
        save_risk_todos(items)


def append_pm_daily_todo(todo: dict) -> None:
    with STATE_FILE_LOCK:
        items = [item for item in load_pm_daily_todos() if item.get("id") != todo.get("id")]
        items.append(todo)
        items.sort(key=lambda item: item.get("deadline") or "")
        save_pm_daily_todos(items)


def remove_todo_by_id(todo_id: str) -> dict:
    if not todo_id:
        return {"removed": False, "scope": "", "todo": None}
    with STATE_FILE_LOCK:
        stores = [
            ("knowledge", load_risk_todos, save_risk_todos),
            ("pm_daily", load_pm_daily_todos, save_pm_daily_todos),
        ]
        for scope, loader, saver in stores:
            items = loader()
            remaining = [item for item in items if item.get("id") != todo_id]
            if len(remaining) != len(items):
                removed = next((item for item in items if item.get("id") == todo_id), None)
                saver(remaining)
                return {"removed": True, "scope": scope, "todo": removed}
    return {"removed": False, "scope": "", "todo": None}


def retry_todo_calendar_impl(todo_id: str) -> dict:
    todo_id = strip_html(str(todo_id).strip())
    if not todo_id:
        raise ValueError("缺少待办 ID")

    stores = [
        ("knowledge", load_risk_todos, save_risk_todos),
        ("pm_daily", load_pm_daily_todos, save_pm_daily_todos),
    ]
    matched: dict | None = None
    matched_items: list[dict] | None = None
    matched_index = -1
    matched_save = None
    for _, loader, saver in stores:
        items = loader()
        for index, item in enumerate(items):
            if item.get("id") == todo_id:
                matched = dict(item)
                matched_items = items
                matched_index = index
                matched_save = saver
                break
        if matched:
            break

    if not matched or matched_items is None or matched_save is None or matched_index < 0:
        raise ValueError("没找到这条待办，可能已经被处理或移除")
    if not matched.get("deadline"):
        raise ValueError("这条待办没有 deadline，无法创建飞书任务提醒")

    existing_task_id = feishu_task_identifier(matched.get("calendar"))
    try:
        deadline = parse_local_datetime(str(matched.get("deadline")))
        if existing_task_id:
            calendar_result = update_feishu_task_reminder(
                existing_task_id,
                customer=str(matched.get("customer", "")),
                title=str(matched.get("title", "")),
                next_step=str(matched.get("next_step", "")),
                deadline=deadline,
                reminder_minutes=int(matched.get("reminder_minutes") or 10),
                evidence_path=str(matched.get("resolution_path", "")),
            )
        else:
            calendar_result = create_feishu_task_reminder(
                customer=str(matched.get("customer", "")),
                title=str(matched.get("title", "")),
                next_step=str(matched.get("next_step", "")),
                deadline=deadline,
                reminder_minutes=int(matched.get("reminder_minutes") or 10),
                evidence_path=str(matched.get("resolution_path", "")),
                evidence=str(matched.get("evidence", "")),
                action=str(matched.get("action", "")),
            )
        calendar_result["status"] = "synced"
        calendar_result["message"] = (
            "飞书任务已更新；到期前将发送私聊提醒"
            if existing_task_id
            else "飞书任务已创建；到期前将发送私聊提醒"
        )
        calendar_result["reason"] = ""
    except Exception as exc:
        calendar_result = {
            "ok": False,
            "status": "failed",
            "message": "飞书任务提醒更新失败" if existing_task_id else "飞书任务提醒创建失败",
            "reason": calendar_failure_reason(exc),
            "task_guid": existing_task_id,
        }

    matched["calendar"] = calendar_result
    matched["calendar_retry_at"] = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
    matched_items[matched_index] = matched
    matched_items.sort(key=lambda item: item.get("deadline") or "")
    matched_save(matched_items)
    return {"ok": True, "todo": matched, "calendar": calendar_result}


def retry_todo_calendar(todo_id: str) -> dict:
    with project_archive.locked(WORKBENCH_DATA_ROOT), STATE_FILE_LOCK:
        rows = load_risk_todos() + load_pm_daily_todos()
        item = next((x for x in rows if x.get("id") == todo_id), {})
        project = project_activity.project_owner(item, build_projects(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT))
        if project:
            a = project_archive.state(WORKBENCH_DATA_ROOT, project["id"])
            if a["archived"] or todo_id in a["suppressed_task_ids"]:
                raise project_rounds.RevisionConflict("归档及恢复前的旧提醒不自动重建；请核对现有事项")
        return retry_todo_calendar_impl(todo_id)


def is_pm_daily_payload(title: str, source_view: str, evidence: str = "") -> bool:
    haystack = f"{title} {source_view} {evidence}"
    markers = ("PM日报", "项目日报", "飞书日报", "飞书群日报", "群消息已归纳", "PM日报雷达")
    return any(marker in haystack for marker in markers)


def submit_risk_evidence_impl(payload: dict) -> dict:
    request_id = strip_html(str(payload.get("request_id", "")).strip())
    account_id = strip_html(str(payload.get("account_id", "")).strip())
    customer = strip_html(str(payload.get("customer", "")).strip())
    title = strip_html(str(payload.get("title", "")).strip())
    evidence = strip_html(str(payload.get("evidence", "")).strip())
    action = strip_html(str(payload.get("action", "")).strip())
    resolution = strip_html(str(payload.get("resolution", "")).strip())
    next_step = strip_html(str(payload.get("next_step", "")).strip())
    status = strip_html(str(payload.get("status", "已处理")).strip()) or "已处理"
    material_ref = str(payload.get("material_ref", "")).strip()
    source_view = strip_html(str(payload.get("source_view", "项目管理工作台")).strip()) or "项目管理工作台"
    workflow_key = strip_html(str(payload.get("workflow_key", "")).strip())
    pm_item_key = strip_html(str(payload.get("pm_item_key", "")).strip())
    object_type = strip_html(str(payload.get("object_type", "action")).strip()) or "action"
    todo_id = strip_html(str(payload.get("todo_id", "")).strip())
    deadline_raw = strip_html(str(payload.get("deadline", "")).strip())
    reminder_minutes = int(payload.get("reminder_minutes") or 10)
    sync_calendar = bool(payload.get("sync_calendar", True))
    if todo_id.startswith("round:") or (todo_id and todo_id in project_rounds.followups(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT)["claimed_actions"]):
        raise ValueError("此事项由项目执行记录维护，请返回对应项目保存进展，避免创建重复任务")
    projects = build_projects(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT)
    origin = next((item for item in load_risk_todos() if item.get("id") == todo_id), {})
    if origin.get("discovery_source_key"):
        if discovery_handoff.name_key(customer) != discovery_handoff.name_key(origin.get("customer")) or (account_id and account_id != origin.get("account_id")):
            raise ValueError("跟进所属客户已变化，请返回原记录处理")
        account_id = origin.get("account_id", "")
    project = project_activity.project_owner(origin, projects)
    requested_project = str(payload.get("project_id") or "")
    if requested_project:
        selected = next((p for p in projects if p["id"] == requested_project), None)
        if not selected or (project and selected["id"] != project["id"]):
            raise ValueError("事项所属项目已变化，请重新读取后处理")
        project = selected
    project_id = project["id"] if project else ""
    project_source = project["source_path"] if project else ""

    if not customer:
        raise ValueError("缺少客户名称")
    if not title:
        raise ValueError("缺少风险/待办标题")
    if not resolution:
        raise ValueError("请填写处理结果或当前进展")
    if status not in WORKBENCH_OUTCOME_STATUSES:
        raise ValueError("处理状态不在允许范围内")
    deadline = parse_local_datetime(deadline_raw) if deadline_raw else None
    if status != "已处理":
        if not next_step:
            raise ValueError("未闭环时请填写下一步动作")
        if not deadline:
            raise ValueError("未闭环时请填写 deadline")

    now = datetime.now(LOCAL_TZ)
    day = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%Y%m%d-%H%M%S")
    receipt_id = request_id or f"receipt-{uuid.uuid4().hex}"
    receipt_token = uuid.uuid5(uuid.NAMESPACE_URL, receipt_id).hex[:16]
    slug = safe_filename(f"{customer}-{title}", "risk-resolution")
    pm_daily = is_pm_daily_payload(title, source_view, evidence)
    if object_type == "pm_item" or pm_daily:
        raise ValueError("项目群日报只读，不提交处理结果、不生成反馈链、不创建待办或 Deadline")
    page_filename = f"receipt_{slug}_{receipt_token}.md"
    resolution_root = WORKFLOW_RECEIPT_ROOT
    asset_root = WORKFLOW_EVIDENCE_ASSET_ROOT
    rel_page = Path("workflow_receipts") / page_filename
    page_path = WORKBENCH_DATA_ROOT / rel_page
    page_already_exists = page_path.exists()
    storage_label = "项目管理工作台"
    saved_message = "已记录到工作推进线"
    resolution_root.mkdir(parents=True, exist_ok=True)
    asset_root.mkdir(parents=True, exist_ok=True)

    archived_lines: list[str] = []
    material_note = material_ref
    if material_ref and not page_already_exists:
        candidate = Path(os.path.expanduser(material_ref))
        if candidate.exists():
            if candidate.is_dir():
                raise ValueError("材料路径不能是文件夹，请填写具体文件路径")
            lowered = candidate.name.lower()
            if lowered in {".env", ".env.local"} or "secret" in lowered or "token" in lowered:
                raise ValueError("这个文件名像敏感凭据，未归档。请换成业务材料文件")
            if candidate.stat().st_size > 50 * 1024 * 1024:
                raise ValueError("材料超过 50MB，先压缩或改填材料说明")
            target_name = f"{receipt_token}-{safe_filename(candidate.name, 'evidence')}"
            target = asset_root / target_name
            shutil.copy2(candidate, target)
            rel_target = target.relative_to(WORKBENCH_DATA_ROOT)
            archived_lines.append(f"- 已归档材料：`{rel_target}`")
            material_note = f"{material_ref} -> {rel_target}"
        else:
            archived_lines.append(f"- 材料引用/链接：{material_ref}")
    elif not material_ref:
        archived_lines.append("- 未提交单独材料文件，仅记录处理结果/当前进展。")
    else:
        archived_lines.append("- 已沿用同一请求此前归档的依据材料。")

    digest = summarize_resolution(resolution, action, next_step, status)
    lines = [
        f"# {customer} 风险/待办处理依据",
        "",
        f"**客户/项目**：[[{customer}]]",
        f"**风险/待办**：{title}",
        f"**处理状态**：{status}",
        f"**提交时间**：{now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**来源入口**：{source_view}",
        f"**Deadline**：{deadline.strftime('%Y-%m-%d %H:%M') if deadline else '无'}",
        "",
        "## 小吴整理版",
        "",
        f"**处理结论**：{digest['conclusion']}",
        "",
        "### 已完成动作",
        "",
        *[f"- {line}" for line in digest["done"]],
        "",
        "### 风险变化/待确认",
        "",
        *[f"- {line}" for line in digest["risk_change"]],
        "",
        "### 下一步",
        "",
        *[f"- {line}" for line in digest["next"]],
        "",
        "## 原始提交",
        "",
        resolution,
        "",
        "## 关联风险/待办原文",
        "",
        f"- 证据/原文：{evidence or '未填写'}",
        f"- 建议动作：{action or '未填写'}",
        "",
        "## 依据材料",
        "",
        *archived_lines,
        "",
        "## 用户填写的下一步",
        "",
        next_step or "暂无下一步，视为本轮闭环。",
        "",
        "## 关联",
        "",
        "- [[客户跟进]]",
        "- [[风险处理]]",
        "",
    ]
    if not page_already_exists:
        write_private_text(page_path, "\n".join(lines))

    log_line = (
        f"\n### {day} {customer} 风险/待办处理依据\n\n"
        f"- 新增 `{rel_page}`，记录“{title}”的处理结果/当前进展、依据材料和下一步。\n"
    )
    log_path = WORKFLOW_RECEIPT_LOG
    if not page_already_exists:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(log_line.replace("新增 `", "新增工作回执 `"))

    existing_todo = next((item for item in load_risk_todos() if item.get("id") == todo_id), None) if todo_id else None
    existing_task_id = feishu_task_identifier((existing_todo or {}).get("calendar"))
    todo_payload = None
    closed_todo = {"removed": False, "scope": "", "todo": None}
    calendar_result = {"ok": False, "status": "skipped", "message": "已闭环，不创建飞书提醒"}
    if status == "已处理" and existing_task_id:
        try:
            calendar_result = complete_feishu_task_reminder(existing_task_id)
        except Exception as exc:
            outbox_id = enqueue_external_sync(
                "complete",
                existing_task_id,
                {"receipt_id": receipt_id, "todo_id": todo_id, "customer": customer, "title": title},
                calendar_failure_reason(exc),
            )
            calendar_result = {
                "ok": False,
                "status": "failed",
                "message": "本地已闭环，飞书任务完成失败",
                "reason": calendar_failure_reason(exc),
                "task_guid": existing_task_id,
                "retry_operation": "complete",
                "outbox_id": outbox_id,
            }
    if status == "已处理" and todo_id:
        closed_todo = remove_todo_by_id(todo_id)
    if status != "已处理" and deadline:
        todo_id = todo_id or f"followup-{receipt_token}"
        calendar_result = {"ok": False, "status": "skipped", "message": "未启用飞书任务与私聊提醒"}
        if sync_calendar:
            try:
                if existing_task_id:
                    calendar_result = update_feishu_task_reminder(
                        existing_task_id,
                        customer=customer,
                        title=title,
                        next_step=next_step,
                        deadline=deadline,
                        reminder_minutes=reminder_minutes,
                        evidence_path=str(rel_page),
                    )
                else:
                    calendar_result = create_feishu_task_reminder(
                        customer=customer,
                        title=title,
                        next_step=next_step,
                        deadline=deadline,
                        reminder_minutes=reminder_minutes,
                        evidence_path=str(rel_page),
                        evidence=evidence,
                        action=action,
                    )
                calendar_result["status"] = "synced"
                calendar_result["message"] = (
                    "飞书任务已更新；到期前将发送私聊提醒"
                    if existing_task_id
                    else "飞书任务已创建；到期前将发送私聊提醒"
                )
                calendar_result["reason"] = ""
            except Exception as exc:
                outbox_id = ""
                if existing_task_id:
                    outbox_id = enqueue_external_sync(
                        "update",
                        existing_task_id,
                        {
                            "receipt_id": receipt_id,
                            "todo_id": todo_id,
                            "customer": customer,
                            "title": title,
                            "next_step": next_step,
                            "deadline": deadline.isoformat(timespec="minutes"),
                            "reminder_minutes": reminder_minutes,
                            "evidence_path": str(rel_page),
                        },
                        calendar_failure_reason(exc),
                    )
                calendar_result = {
                    "ok": False,
                    "status": "failed",
                    "message": "飞书任务提醒更新失败" if existing_task_id else "飞书任务提醒创建失败",
                    "reason": calendar_failure_reason(exc),
                    "task_guid": existing_task_id,
                    "retry_operation": "update" if existing_task_id else "create",
                    "outbox_id": outbox_id,
                }
        elif existing_task_id:
            try:
                calendar_result = complete_feishu_task_reminder(existing_task_id)
                calendar_result["status"] = "detached"
                calendar_result["message"] = "已停止旧飞书任务镜像"
            except Exception as exc:
                outbox_id = enqueue_external_sync(
                    "complete",
                    existing_task_id,
                    {"receipt_id": receipt_id, "todo_id": todo_id, "customer": customer, "title": title},
                    calendar_failure_reason(exc),
                )
                calendar_result = {
                    "ok": False,
                    "status": "failed",
                    "message": "停止旧飞书任务镜像失败",
                    "reason": calendar_failure_reason(exc),
                    "task_guid": existing_task_id,
                    "retry_operation": "complete",
                    "outbox_id": outbox_id,
                }
        todo_payload = {
            "archive_revision": payload.get("archive_revision", 0),
            "project_id": project_id, "project_source": project_source,
            "id": todo_id,
            "workroom_request_id": request_id or f"workroom:{todo_id}"[:500],
            "account_id": account_id or canonical_account_id(customer),
            "customer": customer,
            "title": title,
            "status": status,
            "evidence": evidence,
            "action": action,
            "resolution": resolution,
            "next_step": next_step,
            "deadline": deadline.isoformat(timespec="minutes"),
            "reminder_minutes": reminder_minutes,
            "resolution_path": str(rel_page),
            "calendar": calendar_result,
            "created_at": now.isoformat(timespec="seconds"),
            "source_scope": "workflow_receipt",
            "reminder_consent": {"enabled": sync_calendar, "deadline": deadline.isoformat(timespec="minutes"), "confirmed_at": now.isoformat(timespec="seconds")},
        }
        # Carry trusted lineage from the stored action through feedback/rescheduling.
        # Caller fields cannot change customer ownership or the internal-only boundary.
        if origin.get("discovery_source_key"):
            for key in ("discovery_source_key", "discovery_note_revision", "discovery_source_version", "discovery_evidence", "internal_only", "source_type", "project_title"):
                if key in origin: todo_payload[key] = origin[key]
        append_risk_todo(todo_payload)
        if not page_already_exists:
            RISK_TODO_LOG.parent.mkdir(parents=True, exist_ok=True)
            todo_log_path = RISK_TODO_LOG
            with todo_log_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    f"\n- [ ] {deadline.strftime('%Y-%m-%d %H:%M')} — {customer}：{next_step}"
                    f"（来源：{rel_page}；飞书提醒：{calendar_result.get('status')}）\n"
                )

    action_id = todo_id or workflow_key or receipt_id
    account_id = apply_receipt_to_account(account_id, customer, resolution, next_step, status, receipt_id, project_id, action_id)
    receipt = {
        "project_id": project_id, "project_source": project_source, "action_id": action_id,
        "id": receipt_id,
        "account_id": account_id,
        "customer": customer,
        "title": title,
        "status": "已闭环" if status == "已处理" else status,
        "source_view": source_view,
        "relative_path": str(rel_page),
        "calendar": calendar_result,
        "todo": todo_payload,
        "closed_todo": closed_todo,
        "submitted_at": now.isoformat(timespec="seconds"),
        "resolution": resolution,
        "next_step": next_step,
    }
    workflow_state = load_workflow_state()
    if workflow_key:
        if object_type == "risk":
            target_bucket = "risk_status"
        elif object_type == "schedule":
            target_bucket = "schedule_status"
        else:
            target_bucket = "action_status"
        workflow_state[target_bucket][workflow_key] = {
            "kind": object_type,
            "key": workflow_key,
            "status": receipt["status"],
            "hidden": status == "已处理" or (object_type != "schedule" and bool(todo_payload)),
            "customer": customer,
            "account_id": account_id,
            "title": title,
            "next_step": next_step,
            "deadline": deadline.isoformat(timespec="minutes") if deadline else "",
            "receipt": receipt,
            "updated_at": now.isoformat(timespec="seconds"),
        }
    if pm_item_key:
        workflow_state["pm_item_status"][pm_item_key] = {
            "kind": "pm_item",
            "key": pm_item_key,
            "status": "已闭环" if status == "已处理" else status,
            "hidden": status == "已处理" or bool(todo_payload),
            "customer": customer,
            "title": title,
            "receipt": receipt,
            "updated_at": now.isoformat(timespec="seconds"),
        }
    workflow_state["receipts"] = [
        receipt,
        *[
            item for item in workflow_state.get("receipts", [])
            if isinstance(item, dict) and item.get("id") != receipt_id
        ],
    ][:60]
    save_workflow_state(workflow_state)

    return {
        "ok": True,
        "message": saved_message,
        "storage_label": storage_label,
        "path": str(page_path),
        "relative_path": str(rel_page),
        "material": material_note,
        "todo": todo_payload,
        "calendar": calendar_result,
        "receipt": receipt,
        "workflow_state": workflow_state,
    }


def idempotency_result(request_id: str) -> dict | None:
    if not request_id:
        return None
    initialize_account_store()
    with ACCOUNT_STORE_LOCK, account_store_connection() as connection:
        row = connection.execute(
            "SELECT response_json FROM idempotency_results WHERE request_id = ?",
            (request_id,),
        ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["response_json"])
    except json.JSONDecodeError:
        return None


def save_idempotency_result(request_id: str, response: dict) -> None:
    if not request_id:
        return
    initialize_account_store()
    with ACCOUNT_STORE_LOCK, account_store_connection() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO idempotency_results(request_id, response_json, created_at) VALUES (?, ?, ?)",
            (
                request_id,
                json.dumps(response, ensure_ascii=False),
                datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
            ),
        )


def clear_idempotency_result(request_id: str) -> None:
    if not request_id:
        return
    initialize_account_store()
    with ACCOUNT_STORE_LOCK, account_store_connection() as connection:
        connection.execute("DELETE FROM idempotency_results WHERE request_id = ?", (request_id,))


def recover_idempotent_response(request_id: str) -> dict | None:
    state = load_workflow_state()
    receipt = next(
        (
            item for item in state.get("receipts", [])
            if isinstance(item, dict) and item.get("id") == request_id
        ),
        None,
    )
    if not receipt:
        return None
    return {
        "ok": True,
        "message": "已恢复上一轮提交结果",
        "storage_label": "项目管理工作台",
        "relative_path": receipt.get("relative_path", ""),
        "todo": receipt.get("todo"),
        "calendar": receipt.get("calendar", {}),
        "receipt": receipt,
        "workflow_state": state,
        "idempotent_recovery": True,
    }


def finalize_workroom_request_cycle(request_id: str, response: dict) -> dict:
    todo = response.get("todo") if isinstance(response, dict) else None
    todo_id = str((todo or {}).get("id") or "").strip()
    if not request_id or not todo_id:
        return response

    cycle_token = uuid.uuid5(uuid.NAMESPACE_URL, request_id).hex[:16]
    next_request_id = f"workroom:{todo_id}:cycle:{cycle_token}"[:500]
    items = load_risk_todos()
    changed = False
    finalized_request_id = next_request_id
    for item in items:
        if str(item.get("id") or "").strip() != todo_id:
            continue
        current_request_id = str(item.get("workroom_request_id") or "").strip()
        fallback_request_id = f"workroom:{todo_id}"[:500]
        if current_request_id == next_request_id:
            break
        if current_request_id == request_id or (not current_request_id and request_id == fallback_request_id):
            item["workroom_request_id"] = next_request_id
            changed = True
        elif current_request_id:
            finalized_request_id = current_request_id
        break
    if changed:
        save_risk_todos(items)

    finalized = dict(response)
    finalized["todo"] = {**todo, "workroom_request_id": finalized_request_id}
    return finalized


def submit_risk_evidence(payload: dict) -> dict:
    with project_archive.locked(WORKBENCH_DATA_ROOT):
        projects = build_projects(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT)
        origin = next((i for i in load_risk_todos() if i.get("id") == payload.get("todo_id")), {})
        project = project_activity.project_owner(origin, projects) or project_activity.project_owner(payload, projects)
        if project:
            a = project_archive.state(WORKBENCH_DATA_ROOT, project["id"])
            if payload.get("archive_revision", 0) != a["revision"] or (a["archived"] and (not origin or payload.get("status") != "已处理")):
                raise project_rounds.RevisionConflict("项目归档状态已变化；归档后只能核对并记录既有收尾结果，不能新建销售跟进")
        return _submit_risk_evidence_current(payload)


def _submit_risk_evidence_current(payload: dict) -> dict:
    request_id = strip_html(str(payload.get("request_id", "")).strip())
    if not request_id:
        with STATE_FILE_LOCK:
            return submit_risk_evidence_impl(payload)
    with EVIDENCE_SUBMISSION_LOCK, STATE_FILE_LOCK:
        cached = idempotency_result(request_id)
        if cached is not None:
            if cached.get("_idempotency_status") == "pending":
                recovered = recover_idempotent_response(request_id)
                if recovered is not None:
                    recovered = finalize_workroom_request_cycle(request_id, recovered)
                    save_idempotency_result(request_id, recovered)
                    return recovered
                try:
                    response = submit_risk_evidence_impl(payload)
                except ValueError:
                    clear_idempotency_result(request_id)
                    raise
                response = finalize_workroom_request_cycle(request_id, response)
                save_idempotency_result(request_id, response)
                return {**response, "idempotent_resume": True}
            return {**cached, "idempotent_replay": True}
        save_idempotency_result(request_id, {"_idempotency_status": "pending", "request_id": request_id})
        try:
            response = submit_risk_evidence_impl(payload)
        except ValueError:
            clear_idempotency_result(request_id)
            raise
        response = finalize_workroom_request_cycle(request_id, response)
        save_idempotency_result(request_id, response)
        return response


class WorkbenchHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=str(UI_DIST_ROOT), **kwargs)

    def end_headers(self) -> None:
        if self.path in {"/", "/index.html"}:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        elif self.path.startswith("/assets/"):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN" if (re.fullmatch(r"/api/invoice-assets/[a-f0-9]{64}/preview", urlparse(self.path).path) or urlparse(self.path).path=="/api/material-library/files/preview") else "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'self'",
        )
        super().end_headers()

    def _trusted_origin(self) -> bool:
        origin = self.headers.get("Origin", "").strip()
        if not origin:
            return True
        parsed = urlparse(origin)
        host_header = self.headers.get("Host", "")
        host_name = urlparse(f"http://{host_header}").hostname or ""
        host_port = urlparse(f"http://{host_header}").port or self.server.server_port
        origin_port = parsed.port or 80
        loopback_hosts = {"127.0.0.1", "localhost", "::1"}
        return (
            parsed.scheme == "http"
            and (parsed.hostname or "") in loopback_hosts
            and host_name in loopback_hosts
            and int(host_port) == int(origin_port)
        )

    def _static_request_path(self, request_path: str) -> str | None:
        root = UI_DIST_ROOT.resolve()
        relative = unquote(request_path).lstrip("/") or "index.html"
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        if candidate.is_file():
            return f"/{candidate.relative_to(root).as_posix()}"
        if "." not in Path(relative).name and (root / "index.html").is_file():
            return "/index.html"
        return None

    def _serve_static(self, *, head_only: bool = False) -> None:
        parsed = urlparse(self.path)
        safe_path = self._static_request_path(parsed.path)
        if not safe_path:
            self._send_json({"error": "not found"}, status=404)
            return
        self.path = safe_path
        if head_only:
            super().do_HEAD()
        else:
            super().do_GET()

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # The browser left after work completed. Do not retry a response or
            # label a saved operation as failed just because its peer is gone.
            self.close_connection = True

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _redirect_to_canonical_workbench(self) -> None:
        self.send_response(302)
        self.send_header("Location", CANONICAL_WORKBENCH_URL)
        self.end_headers()

    def do_HEAD(self) -> None:
        if material_files.handle(self, SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT): return
        if material_library.handle(self, SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT):
            return
        self._serve_static(head_only=True)

    def do_GET(self) -> None:
        if workbench_agent.handle(self, SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT): return
        if urlparse(self.path).path == '/api/runtime-version':
            self._send_json({'ok':True,**RUNTIME_VERSION})
            return
        if material_files.handle(self, SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT): return
        if k100_sync.handle(self, WORKBENCH_DATA_ROOT, SALES_WORKBENCH_KNOWLEDGE_ROOT): return
        if project_notifications.handle(self, WORKBENCH_DATA_ROOT): return
        if project_archive.handle(self, SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT): return
        if local_resources.handle(self, WORKBENCH_DATA_ROOT): return
        if urlparse(self.path).path == '/api/public-signals':
            if not self._trusted_origin():
                self._send_json({'error':'origin not allowed'}, status=403)
                return
            try: self._send_json(get_public_signal_hub())
            except Exception:
                self._send_json({'error':'公开信号暂时无法读取，历史记录保留'}, status=503)
            return
        if urlparse(self.path).path == '/api/ai-hot':
            if not self._trusted_origin():
                self._send_json({'error': 'origin not allowed'}, status=403)
                return
            try:
                query = parse_qs(urlparse(self.path).query)
                self._send_json(ai_hot.read({key: values[0] for key, values in query.items()}, WORKBENCH_DATA_ROOT))
            except ValueError as exc:
                self._send_json({'error': str(exc)}, status=400)
            except ai_hot.FeedError as exc:
                self._send_json({'error': str(exc), 'code': exc.code}, status=503 if exc.status >= 500 else exc.status)
            except OSError:
                self._send_json({'error': '资讯缓存暂不可读，请稍后刷新'}, status=503)
            return
        if urlparse(self.path).path == '/api/communication-sync':
            if not self._trusted_origin():self._send_json({'error':'origin not allowed'},status=403);return
            try:self._send_json(communication_jobs.status(WORKBENCH_DATA_ROOT,SALES_WORKBENCH_KNOWLEDGE_ROOT))
            except (ValueError,OSError):self._send_json({'error':'整理状态暂不可读，已有资料保留，请稍后重试'},status=503)
            return
        if material_library.handle(self, SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT):
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/project-workspace/progress":
            try:
                self._send_json(project_analysis.progress_records(parse_qs(parsed.query).get('project_id',[''])[0], SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT))
            except (ValueError, OSError) as exc: self._send_json({'error':str(exc)}, status=400)
            return
        if parsed.path == "/api/quotes":
            try:
                quote_id = parse_qs(parsed.query).get('quote_id', [''])[0]
                self._send_json({'ok': True, **quote_versions.read(WORKBENCH_DATA_ROOT, quote_id)})
            except ValueError as exc: self._send_json({'error': str(exc)}, status=400)
            return
        if parsed.path == "/api/discovery/prepare":
            try:
                query=parse_qs(parsed.query)
                self._send_json(discovery_preparation({key:query.get(key,[''])[0] for key in ('kind','source_id')}))
            except (ValueError,OSError) as exc:self._send_json({'error':str(exc)},status=409)
            return
        if parsed.path == "/api/discovery/notes":
            self._send_json({"ok": True, **discovery_workspace.load_notes(WORKBENCH_DATA_ROOT)})
            return
        if parsed.path in {"/api/commercial/draft", "/api/project-workspace/source", "/api/messages/reports"}:
            try:
                query = parse_qs(parsed.query)
                if parsed.path == "/api/commercial/draft":
                    result = commercial.get_draft(query.get("project_id", [""])[0], SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT)
                elif parsed.path == "/api/project-workspace/source":
                    result = read_source(query.get("project_id", [""])[0], query.get("path", [""])[0], SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT)
                else:
                    offset = max(0, min(5000, int(query.get("offset", ["0"])[0])))
                    limit = max(1, min(30, int(query.get("limit", ["20"])[0])))
                    reports = load_persisted_pm_reports(offset + limit + 1)
                    result = {"ok": True, "days": reports[offset:offset + limit], "has_more": len(reports) > offset + limit}
                self._send_json(result)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/crm/status":
            try:
                self._send_json(legacy_crm_snapshot.status(WORKBENCH_DATA_ROOT))
            except Exception:
                self._send_json({"error": "本机钥匙串暂不可用"}, status=503)
            return
        if parsed.path == "/api/project-workspace/followups":
            try:
                self._send_json(risk_todos_payload())
            except (ValueError, OSError) as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/project-workspace/overview":
            try:
                self._send_json(project_analysis.overview(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT))
            except (ValueError, OSError) as exc:
                self._send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/project-workspace/analysis":
            try:
                self._send_json(project_analysis.status(parse_qs(parsed.query).get("project_id", [""])[0], SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT))
            except (ValueError, OSError) as exc:
                self._send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/crm/project-links":
            try:
                self._send_json(project_crm.audit(parse_qs(parsed.query).get("project_id", [""])[0], SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT))
            except (ValueError, OSError) as exc:
                self._send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/project-workspace/round":
            try:
                self._send_json(project_rounds.read_round(parse_qs(parsed.query).get("project_id", [""])[0], SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT))
            except (ValueError, OSError) as exc:
                self._send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/project-workspace":
            self._send_json({"ok": True, "projects": build_projects(SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT)})
            return
        if parsed.path == "/api/messages/health":
            self._send_json({"ok": True, "health": read_json_file(WORKBENCH_DATA_ROOT / "message_sync_health.json", {"status": "unknown"})})
            return
        if parsed.path == "/api/dashboard":
            self._send_json(get_dashboard_payload())
            return
        if parsed.path == "/api/messages/status":
            self._send_json(get_message_sync_status())
            return
        if parsed.path == "/api/messages/auth/state":
            self._send_json({"ok": True, "auth": get_lark_auth_state()})
            return
        if parsed.path == "/api/risk-todos":
            self._send_json(risk_todos_payload())
            return
        if parsed.path == "/api/reminder-delivery":
            self._send_json({"ok": True, "delivery": feishu_reminder_delivery_payload(items=risk_todos_payload().get("items", []))})
            return
        if parsed.path == "/api/calendar/events":
            self._send_json(get_calendar_payload(refresh=False))
            return
        if parsed.path == "/api/workflow/status":
            self._send_json({"ok": True, "workflow_state": load_workflow_state(), "external_sync_outbox": load_external_sync_outbox()})
            return
        if parsed.path == "/api/fxiaoke/status":
            self._send_json(fxiaoke_status_payload())
            return
        if parsed.path == "/api/prospecting":
            self._send_json(get_prospecting_payload(refresh_due=False))
            return
        if parsed.path == "/api/account-advancement":
            self._send_json(get_account_advancement_payload())
            return
        if parsed.path == "/api/intel":
            query = parse_qs(parsed.query).get("q", [""])[0].strip()
            if not query:
                self._send_json({"error": "missing q"}, status=400)
                return
            self._send_json(get_customer_intel_payload(query))
            return
        self._serve_static()

    def do_OPTIONS(self) -> None:
        if not self._trusted_origin():
            self._send_json({"error": "origin not allowed"}, status=403)
            return
        self.send_response(204)
        origin = self.headers.get("Origin", "").strip()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Request-ID")
        self.end_headers()

    def do_POST(self) -> None:
        if workbench_agent.handle(self, SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT): return
        if material_files.handle(self, SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT): return
        if k100_sync.handle(self, WORKBENCH_DATA_ROOT, SALES_WORKBENCH_KNOWLEDGE_ROOT): return
        if project_notifications.handle(self, WORKBENCH_DATA_ROOT): return
        if project_archive.handle(self, SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT): return
        if local_resources.handle(self, WORKBENCH_DATA_ROOT): return
        parsed = urlparse(self.path)
        if not self._trusted_origin():
            self._send_json({"error": "origin not allowed"}, status=403)
            return
        try:
            if parsed.path == '/api/communication-sync':
                try:self._send_json(communication_jobs.start(self._read_json_body(),WORKBENCH_DATA_ROOT,SALES_WORKBENCH_KNOWLEDGE_ROOT))
                except ValueError as exc:self._send_json({'error':str(exc)},status=400)
                return
            if parsed.path == "/api/quotes":
                try: self._send_json(quote_versions.save(WORKBENCH_DATA_ROOT, self._read_json_body()))
                except quote_versions.QuoteConflict as exc: self._send_json({'error': str(exc)}, status=409)
                return
            if parsed.path == "/api/discovery/handoff":
                self._send_json(save_discovery_handoff(self._read_json_body()))
                return
            if parsed.path == "/api/discovery/notes":
                self._send_json(discovery_workspace.save_note(self._read_json_body(), WORKBENCH_DATA_ROOT, [apply_prospecting_time_window(dict(item)) for item in load_prospecting_state().get("leads", [])], account_store_rows()))
                return
            if parsed.path in {"/api/commercial/draft", "/api/commercial/preview"}:
                method = commercial.save_draft if parsed.path.endswith("/draft") else commercial.preview_draft
                self._send_json(method(self._read_json_body(), SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT))
                return
            if parsed.path in ("/api/crm/configure", "/api/crm/sync"):
                self._send_json({"ok": False, "error": "业务平台旧CRM接口已停用，请使用新版 K100"}, status=410)
                return
            if parsed.path in ("/api/project-workspace/analysis", "/api/project-workspace/analysis/adopt"):
                try:
                    method = project_analysis.adopt if parsed.path.endswith("/adopt") else project_analysis.start
                    self._send_json(method(self._read_json_body(), SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT))
                except project_rounds.RevisionConflict as exc:
                    self._send_json({"error": str(exc)}, status=409)
                return
            if parsed.path == "/api/project-workspace/analysis/feedback":
                try:
                    self._send_json(project_analysis.quick_feedback(self._read_json_body(), SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT))
                except project_rounds.RevisionConflict as exc:
                    self._send_json({"error": str(exc)}, status=409)
                return
            if parsed.path == "/api/project-workspace/progress":
                self._send_json(k100_sync.save_workbench_progress(self._read_json_body(), SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT))
                return
            if parsed.path == "/api/project-workspace/round":
                try:
                    self._send_json(k100_sync.save_round(self._read_json_body(), SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT))
                except project_rounds.RevisionConflict as exc:
                    self._send_json({"error": str(exc)}, status=409)
                return
            if parsed.path == "/api/project-workspace/plan":
                self._send_json(save_plan(self._read_json_body(), SALES_WORKBENCH_KNOWLEDGE_ROOT, WORKBENCH_DATA_ROOT))
                return
            if parsed.path == "/api/messages/sync":
                self._send_json(sync_messages())
                return
            if parsed.path == "/api/messages/auth/start":
                self._send_json(start_lark_auth())
                return
            if parsed.path == "/api/messages/auth/complete":
                self._send_json(complete_lark_auth())
                return
            if parsed.path == "/api/intel":
                payload = self._read_json_body()
                query = str(payload.get("query", "")).strip()
                if not query:
                    self._send_json({"error": "missing query"}, status=400)
                    return
                self._send_json(get_customer_intel_payload(query))
                return
            if parsed.path == "/api/risk-evidence":
                self._send_json(submit_risk_evidence(self._read_json_body()))
                return
            if parsed.path == "/api/workflow/update":
                self._send_json(workflow_record(self._read_json_body()))
                return
            if parsed.path == "/api/manual-todo":
                self._send_json(create_manual_todo(self._read_json_body()))
                return
            if parsed.path == "/api/risk-todos/calendar/retry":
                payload = self._read_json_body()
                self._send_json(retry_todo_calendar(str(payload.get("todo_id", ""))))
                return
            if parsed.path == "/api/reminder-delivery/run":
                payload = self._read_json_body()
                self._send_json(
                    process_feishu_reminder_deliveries(
                        force_overdue=bool(payload.get("force_overdue", False)),
                    )
                )
                return
            if parsed.path == "/api/integrations/retry":
                self._send_json(process_external_sync_outbox(force=True))
                return
            if parsed.path == "/api/calendar/sync":
                self._send_json(get_calendar_payload(refresh=True))
                return
            if parsed.path == "/api/fxiaoke/sync-preview":
                self._send_json(fxiaoke_sync_preview())
                return
            if parsed.path == "/api/account-advancement/sync":
                self._send_json(refresh_account_store_from_feishu())
                return
            if parsed.path == "/api/account-advancement/stage":
                self._send_json(advance_account_stage(self._read_json_body()))
                return
            if parsed.path == "/api/account-advancement/evidence":
                self._send_json(update_account_evidence(self._read_json_body()))
                return
            if parsed.path == "/api/account-advancement/state":
                self._send_json(update_account_state(self._read_json_body()))
                return
            if parsed.path == "/api/prospecting/run":
                self._send_json(run_prospecting_scan("manual"))
                return
            if parsed.path == "/api/prospecting/import":
                self._send_json(import_prospecting_payload(self._read_json_body()))
                return
            if parsed.path == "/api/customer-intel/import":
                self._send_json(import_customer_intel_payload(self._read_json_body()))
                return
            if parsed.path == "/api/prospecting/lead":
                self._send_json(update_prospecting_lead(self._read_json_body()))
                return
            self._send_json({"error": "not found"}, status=404)
        except project_rounds.RevisionConflict as exc:
            self._send_json({"error": str(exc)}, status=409)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def log_message(self, format: str, *args) -> None:
        return


class WorkbenchHTTPServer(ThreadingHTTPServer):
    request_queue_size = 128


def main() -> int:
    parser = argparse.ArgumentParser(description="Project workbench server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("项目管理工作台只允许绑定本机回环地址")

    bootstrap_account_store()
    server = WorkbenchHTTPServer((args.host, args.port), WorkbenchHandler)
    from release_startup import grace_seconds, start_worker
    sync_stop=threading.Event()
    startup_delay=grace_seconds(WORKBENCH_DATA_ROOT)
    start_worker(prospecting_scheduler_loop,(),sync_stop,startup_delay)
    if os.environ.get("SALES_WORKBENCH_BACKGROUND_UPKEEP",os.environ.get("SALES_WORKBENCH_PROJECT_AUTO_SYNC","0")) != "0":
        start_worker(background_operations.run_loop,(WORKBENCH_DATA_ROOT,SALES_WORKBENCH_KNOWLEDGE_ROOT,sync_stop),sync_stop,startup_delay)
    if os.environ.get('SALES_WORKBENCH_PROJECT_AUTO_SYNC','0')!='0':
        start_worker(project_analysis.sync_loop,(SALES_WORKBENCH_KNOWLEDGE_ROOT,WORKBENCH_DATA_ROOT,sync_stop),sync_stop,startup_delay)
    def stop_service(signum,frame):
        sync_stop.set()
        workbench_agent.stop_all()
        project_analysis.stop_processes()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM,stop_service)
    if FEISHU_REMINDER_ENABLED:
        start_worker(feishu_reminder_scheduler_loop,(),sync_stop,startup_delay)
    print(f"sales-workbench: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        sync_stop.set()
        workbench_agent.stop_all()
        project_analysis.stop_processes()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
