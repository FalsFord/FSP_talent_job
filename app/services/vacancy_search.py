"""Meaning-aware IT vacancy ranking with optional GigaChat embeddings."""
import asyncio
import hashlib
import math
import re
from collections import OrderedDict
from app.tasks.rag.llm import get_llm
from app.tasks.rag.gigachat import GigaChatLLM, GigaChatError

CONCEPTS={
    'backend':('backend','бэкенд','бекенд','серверн','api','fastapi','django','spring'),
    'frontend':('frontend','фронтенд','интерфейс','react','vue','angular'),
    'fullstack':('fullstack','full-stack','фулстек','полный цикл'),
    'python':('python','питон','пайтон'), 'golang':('golang','golang-разработчик','go','голанг'),
    'javascript':('javascript','js','джаваскрипт'), 'typescript':('typescript','ts'),
    'sql':('sql','базы данных','базами данных','postgresql','postgres','постгрес'),
    'devops':('devops','девопс','инфраструктур','kubernetes','ci/cd'),
    'remote':('remote','удалён','удален','удаленка','из дома','дистанцион'),
    'office':('office','офис'), 'hybrid':('hybrid','гибрид'),
}
cache=OrderedDict()
lock=asyncio.Lock()

def concepts(text):
    text=text.lower().replace('ё','е')
    return {key for key,aliases in CONCEPTS.items() if any(re.search(r'(?<!\w)'+re.escape(alias.replace('ё','е')),text) for alias in aliases)}

def lexical_score(query,vacancy):
    title=vacancy['title'].lower();skills=' '.join(vacancy['skills']).lower()
    all_text=' '.join([title,skills,vacancy.get('company_name') or '',vacancy['description'],vacancy.get('work_format') or ''])
    wanted=concepts(query);tokens=re.findall(r'[\w+#]+',query.lower())
    score=4*len(wanted & concepts(title))+2*len(wanted & concepts(skills))+len(wanted & concepts(all_text))
    score+=sum(3 if token in title else 2 if token in skills else 1 if token in all_text.lower() else 0 for token in tokens if len(token)>1)
    return score

def cosine(a,b):
    return sum(x*y for x,y in zip(a,b))/(math.sqrt(sum(x*x for x in a))*math.sqrt(sum(x*x for x in b)) or 1)

async def vectors(texts):
    llm=get_llm()
    if not isinstance(llm,GigaChatLLM): return None
    keys=[hashlib.sha256(text.encode()).hexdigest() for text in texts]
    async with lock:
        missing={key:text for key,text in zip(keys,texts) if key not in cache}
        if missing:
            data=await llm.request('/embeddings',{'model':'Embeddings','input':list(missing.values())})
            rows=sorted(data['data'],key=lambda row:row['index'])
            if len(rows)!=len(missing): raise ValueError('Incomplete embeddings')
            for key,row in zip(missing,rows):
                vector=row['embedding']
                if not vector or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in vector): raise ValueError('Invalid embedding')
                cache[key]=vector
        result=[cache[key] for key in keys]
        while len(cache)>1024: cache.popitem(last=False)
        return result

async def rank(query,items):
    if not query.strip(): return items,'recent'
    embeddings=None
    if items:
        texts=[query]+[(v['title']+'\n'+', '.join(v['skills'])+'\n'+v['description'])[:900] for v in items]
        try: embeddings=await asyncio.wait_for(vectors(texts),timeout=20)
        except (GigaChatError,ValueError,KeyError,TypeError,asyncio.TimeoutError): pass
    scored=[]
    for i,item in enumerate(items):
        lexical=lexical_score(query,item)
        score=lexical+(4*cosine(embeddings[0],embeddings[i+1]) if embeddings else 0)
        if lexical or embeddings: scored.append((score,item))
    scored.sort(key=lambda pair:pair[0],reverse=True)
    return [item for _,item in scored], 'semantic' if embeddings else 'concepts'
