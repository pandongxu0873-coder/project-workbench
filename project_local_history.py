"""Every saved round and correction remains available as historical evidence."""
def historical_sources(local,corrections,source_dates):
 sources=[]
 for item in local.get('history',[]):
  if item['revision']==local.get('revision'):continue
  record=item['record']
  content='历史工作记录版本，不代表一次新的客户沟通；重复反馈可能只是被沿用。\n'+'\n'.join(f'{key}：{value}' for key,value in record.items())
  sources.append({'path':f'local://round/history/{item["revision"]}','date':source_dates('', '\n'.join(record.get(k,'') for k in ('facts','feedback'))),'recorded_at':record['saved_at'],'content':content,'truncated':False})
 for item in corrections[:-1]:
  sources.append({'path':f'user://correction/{item["revision"]}','date':source_dates('',item['text']),'recorded_at':item['date'],'content':item['text'] or '此版本补充为空；仅表示编辑记录，不证明历史客户事实被撤销。','truncated':False})
 return sources
