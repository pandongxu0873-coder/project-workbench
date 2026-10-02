"""Contract tests: synthetic records only, no schedulers, no external network."""
import os,sys,json,socket
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=Path(os.environ['SALES_WORKBENCH_WORKBENCH_STATE_ROOT']);kb=root/'synthetic-knowledge';(kb/'tracking').mkdir(parents=True,exist_ok=True)
os.environ['SALES_WORKBENCH_KNOWLEDGE_ROOT']=str(kb)
import server
# Legacy scenario labels are synthetic fixtures; never read real customer files.
server.initialize_account_store()
server.upsert_account_store({'name':'云杉百货','stage':'contact','account_state':'active','next_action':'合成验收：核对范围','industry':'合成零售'},source_kind='workbench_legacy_migration',sync_status='local')
seed={'task':{'last_run_at':'','last_run_status':'idle','scan_in_progress':False},'leads':[
 {'id':'synthetic-accepted','company':'合成准入客户','title':'合成会员采购','decision':'accepted','source_url':'https://example.com/synthetic','source':'合成来源','entry_strategy':'合成切口','published_at':'2026-01-01'},
 {'id':'synthetic-missing-window','company':'合成无窗口客户','title':'合成会员采购招标公告','decision':'pending','source_url':'https://example.com/missing','published_at':'2026-09-26'},
 {'id':'synthetic-historical-label','company':'中免集团三亚市内免税店有限公司','title':'合成历史窗口回归样例','decision':'watch','deadline':'2026-07-07','source_url':'https://example.com/historical','published_at':'2026-06-01'}]}
server.save_prospecting_state(seed);server.bootstrap_account_store()
def deny(*a,**k):raise RuntimeError('external network disabled for tests')
socket.create_connection=deny
port=int(sys.argv[sys.argv.index('--port')+1]);server.WorkbenchHTTPServer(('127.0.0.1',port),server.WorkbenchHandler).serve_forever()
