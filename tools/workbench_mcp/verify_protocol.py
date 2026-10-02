import asyncio
import json
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    root=Path(__file__).resolve().parent
    report={}
    async with stdio_client(StdioServerParameters(command=str(root/'run.sh'))) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            listed=await session.list_tools();report['tools']=[t.name for t in listed.tools]
            assert len(listed.tools)==7
            assert all(t.annotations.readOnlyHint and not t.annotations.destructiveHint for t in listed.tools)
            calls=[('overview',{}),('list_code',{'limit':3}),('read_code',{'path':'project_analysis.py','start_line':910,'line_count':24}),('search_code',{'query':'SYNC_DISCOVERY_SECONDS','limit':3}),('sync_status',{}),('analysis_status',{'limit':3}),('log_summary',{})]
            report['calls']=[]
            for name,args in calls:
                result=await session.call_tool(name,args)
                assert not result.isError,(name,result)
                body=''.join(c.text for c in result.content if c.type=='text')
                report['calls'].append({'tool':name,'ok':True,'response_bytes':len(body.encode())})
            rejected=await session.call_tool('read_code',{'path':'../../.codex/auth.json'})
            assert rejected.isError
            report['traversal_rejected']=True
    print(json.dumps(report,ensure_ascii=False,indent=2))
asyncio.run(main())
