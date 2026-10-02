"""Synthetic-only browser workflow fixture. All model output is a fixed test mock."""
import os,sys,socket,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_project_analysis import AnalysisTests
fixture=AnalysisTests();fixture.setUp()
fixture.source.write_text(f'# 合成验收项目（非真实客户）\n**客户**：[[合成验收客户]]\n## 沟通反馈 2026-09-26\n合成验收：客户希望先核对范围。\n[[raw/reply]]\n')
fixture.generate()
os.environ.update(SALES_WORKBENCH_KNOWLEDGE_ROOT=str(fixture.k),SALES_WORKBENCH_WORKBENCH_STATE_ROOT=str(fixture.s),SALES_WORKBENCH_PROJECT_AUTO_SYNC='0',SALES_WORKBENCH_BACKGROUND_UPKEEP='0',FEISHU_REMINDER_ENABLED='0',LARK_CLI_BIN='/usr/bin/false')
import server
server.WORKBENCH_DATA_ROOT=fixture.s
from urllib.parse import urlparse
# No scheduler start; no real model is reachable after fixture creation.
def deny(*a,**k):raise RuntimeError('Synthetic UAT forbids model/network')
server.project_analysis.run_model=deny;socket.create_connection=deny
class H(server.WorkbenchHandler):
 def do_GET(self):
  p=urlparse(self.path).path
  if p in {'/api/project-workspace','/api/project-workspace/overview','/api/project-workspace/analysis','/api/project-workspace/round'}:return super().do_GET()
  if p=='/api/calendar/events':self._send_json({'items':[],'error':'隔离环境禁用外部日程'});return
  if p=='/api/account-advancement':self._send_json({'accounts':[]});return
  if p.startswith('/api/'):
   self._send_json({'ok':True,'items':[],'records':[],'accounts':[],'groups':[],'connections':[]});return
  self._serve_static()
 def do_POST(self):
  if urlparse(self.path).path in {'/api/project-workspace/analysis/feedback','/api/project-workspace/round'}:return super().do_POST()
  self._send_json({'error':'合成验收仅开放本机执行记录'},status=403)
print('Synthetic workflow http://127.0.0.1:8880',flush=True)
try:server.WorkbenchHTTPServer(('127.0.0.1',8880),H).serve_forever()
finally:fixture.doCleanups()
