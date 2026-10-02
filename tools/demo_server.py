"""Offline synthetic UI preview. No credentials, model calls, connectors or writes."""
import argparse,json
from datetime import datetime,timedelta
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
ROOT=Path(__file__).resolve().parents[1]
TODAY=datetime.now().date()
def day(n=0):return (TODAY+timedelta(days=n)).isoformat()
PROJECTS=[{'id':f'demo-{i}','customer':name,'title':title,'latest_evidence_date':day(-1),'analysis_state':'ready','analysis_stale':False,'execution_state':'ready','brief':{'stage':stage,'attention':'可推进','next_action':'核对演示材料，确认范围'},'execution':{'record':{'relationship':'active'}}} for i,(name,title,stage) in enumerate([
 ('星河科技','客户服务知识检索','需求澄清'),('云杉零售','会员运营升级','方案验证'),('松果教育','智能文档助手','商务推进'),('远航制造','项目协作平台','交付实施'),('青岳文旅','服务流程梳理','需求澄清'),('晴川健康','知识库治理','方案验证'),('麦田食品','渠道协作工具','商务推进'),('晨曦能源','服务工单优化','交付实施')])]
NODES=[{'id':f'demo-node-{i}','customer':p['customer'],'project_id':p['id'],'title':p['title'],'deadline':day(i)+'T10:00:00+08:00','next_step':step,'status':'已安排','source_type':'manual'} for i,(p,step) in enumerate(zip(PROJECTS,['范围评审','方案交流','合同核对','交付验收']))]
def payload(path,query):
 if path=='/api/k100/business-summary':
  date=query.get('date',[day()])[0];year=date[:4]
  return {'ok':True,'metric':{'completed':2680000,'target':4000000,'gap':1320000,'rate':67},'cash':{'available':True,'received':1560000,'pending':720000,'order_count':8,'orders':[]},'range':{'from':year+'-01-01','through':date},'source_updated_at':day()+'T09:00:00+08:00','source_paused':False}
 if path=='/api/project-workspace/overview':return {'ok':True,'projects':PROJECTS}
 if path=='/api/project-workspace':return {'ok':True,'projects':PROJECTS}
 if path=='/api/dashboard':return {'ok':True,'risk_todos':NODES,'battle_actions':[],'calendar_status':{'ok':True,'read_state':'ready','background_items':[]},'summary':{},'data_updated_at':day()+' 09:00'}
 if path=='/api/agent/preferences':return {'ok':True,'deferred':[]}
 if path=='/api/agent/conversations':return {'ok':True,'items':[]}
 if path=='/api/agent/conversation':return {'ok':True,'id':query.get('id',['demo'])[0],'messages':[],'input':'','input_revision':0,'status':'idle'}
 if path=='/api/project-notifications':return {'ok':True,'items':[],'unread_count':0}
 return {'ok':True,'items':[],'projects':[],'accounts':[],'groups':[],'records':[],'connections':[],'health':{'status':'demo'},'delivery':{'items':[]},'status':'demo','configured':False}
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT/'dist'),**kwargs)
 def do_GET(self):
  p=urlparse(self.path)
  if p.path.startswith('/api/'):
   data=json.dumps(payload(p.path,parse_qs(p.query)),ensure_ascii=False).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data);return
  super().do_GET()
 def do_POST(self):
  data=json.dumps({'ok':False,'error':'离线演示只展示合成数据，不执行保存、模型调用、同步或外部操作。'},ensure_ascii=False).encode();self.send_response(403);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(data)
 def log_message(self,*args):pass
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8878);args=ap.parse_args()
 print(f'Synthetic read-only preview: http://127.0.0.1:{args.port}/',flush=True)
 ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
