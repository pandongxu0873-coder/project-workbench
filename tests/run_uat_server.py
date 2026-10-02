"""Ephemeral UI acceptance fixture; no schedulers, credentials or real business writes."""
import os
import sys
import tempfile
from pathlib import Path
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory(prefix="project-workbench-uat-") as folder:
    root = Path(folder)
    knowledge = root / "knowledge"
    (knowledge / "projects").mkdir(parents=True)
    (knowledge / "raw").mkdir()
    (knowledge / "raw" / "reply.md").write_text("UAT 隔离样例，不是真实客户确认：36.5 人日。")
    (knowledge / "projects" / "星海汽车验收样例.md").write_text('---\nupdated: 2026-09-06\nsources: ["raw/reply.md"]\n---\n# 星海汽车隔离验收项目\n\n**客户**：[[星海汽车测试样例]]\n\n## 一句话判断\n本数据只用于隔离交互验收，不是真实客户。\n\n## 当前待办\n- [ ] 技术确认接口评估\n- [ ] 售前确认方案边界\n')
    os.environ.update(SALES_WORKBENCH_KNOWLEDGE_ROOT=str(knowledge), SALES_WORKBENCH_WORKBENCH_STATE_ROOT=str(root / "state"), FEISHU_REMINDER_ENABLED="0", LARK_CLI_BIN="/usr/bin/false")
    import server
    server.legacy_crm_snapshot.status = lambda root: {"ok": True, "mode": "read_only", "configured": False, "snapshot": None}
    server.get_message_sync_status = lambda: {"ok": False, "action_required": True, "message": "隔离环境，不连接飞书"}
    print("UAT only: http://127.0.0.1:8879", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8879), server.WorkbenchHandler).serve_forever()
