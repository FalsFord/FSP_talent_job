"""Read-only sandbox smoke test: no candidate, score or XP writes."""
import asyncio
import base64
from app.api.endpoint import judge
from app.services.daily_algorithms import cases

async def main():
    source='import sys\na=list(map(int,sys.stdin.read().split()))\nprint(" ".join(str(x+3) for x in reversed(a)))'
    samples=[]
    for stdin,expected,n in cases({'kind':'reverse','parameter':3,'seed':42}):
        row=await judge('/submissions?base64_encoded=true&wait=false','POST',{'source_code':base64.b64encode(source.encode()).decode(),'stdin':base64.b64encode(stdin.encode()).decode(),'language_id':71,'cpu_time_limit':2,'wall_time_limit':5,'memory_limit':128000,'enable_network':False})
        for _ in range(60):
            result=await judge('/submissions/'+row['token']+'?base64_encoded=true')
            if result['status']['id']>2:break
            await asyncio.sleep(.3)
        assert result['status']['id']==3,result
        assert base64.b64decode(result.get('stdout') or '').decode().strip()==expected.strip()
        assert result.get('time') is not None and result.get('memory') is not None
        samples.append((n,result['time'],result['memory']))
    print('PASS real Judge0 correctness/time/memory:',samples)

asyncio.run(main())
