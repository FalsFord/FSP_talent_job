"""Pinned, bounded 200-task corpus from three MIT repositories. Downloaded code is never executed."""
import argparse
import ast
import asyncio
import hashlib
import json
from pathlib import Path
import httpx
from app.services.algorithm_import import TASKS,COMMIT
from app.services.knowledge_service import upsert_document,knowledge_stats

REPOS={
 'neetcode':('neetcode-gh/leetcode',COMMIT,'LICENSE'),
 'exercism':('exercism/python','6105f6d9d3ef66ce3d5c8f529d2882af3d76b706','LICENSE'),
 'thealgorithms':('TheAlgorithms/Python','215c1f0710f610aaf5ebaeab04edacec3f5308cd','LICENSE.md'),
}

def topic_tags(name):
    groups={
        'array массив':('array','sum','product','container','stock','median','permutation','jump','range'),
        'string строка':('string','palindrome','anagram','roman','substring','zigzag','letter','word'),
        'stack стек':('parenthes','stack','bracket'), 'list список':('linked','list','node'),
        'tree дерево':('tree','bst','ancestor'), 'graph граф':('graph','island','course','path','network'),
        'hash множество':('duplicate','unique','anagram','two-sum','frequent'),
        'binary-search поиск':('search','rotated'), 'sort сортировка':('sort','merge','3sum','4sum'),
        'dynamic-programming динамика':('stairs','coin','decode','edit-distance','regex','regular-expression'),
    }
    return list(dict.fromkeys(['algorithm',*[tag for tags,terms in groups.items() if any(term in name for term in terms) for tag in tags.split()]]))

async def fetch(root):
    root.mkdir(parents=True,exist_ok=True)
    semaphore=asyncio.Semaphore(3)
    async with httpx.AsyncClient(timeout=40,trust_env=False,headers={'User-Agent':'EndPoint-algorithm-corpus/1.0'}) as client:
        async def get(url):
            async with semaphore:
                for attempt in range(3):
                    try:
                        r=await client.get(url);r.raise_for_status()
                        limit=3000000 if url.startswith('https://api.github.com/') else 250000
                        if len(r.content)>limit:raise ValueError('Oversized source')
                        return r
                    except httpx.HTTPError:
                        if attempt==2:raise
                        await asyncio.sleep(2**attempt)
        trees={};licenses={}
        for key,(repo,commit,license_path) in REPOS.items():
            trees[key]=(await get(f'https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1')).json()['tree']
            licenses[key]=(await get(f'https://raw.githubusercontent.com/{repo}/{commit}/{license_path}')).text
            if 'MIT License' not in licenses[key]:raise ValueError('Unexpected license '+key)
            (root/(key+'-LICENSE.txt')).write_text(licenses[key],encoding='utf-8')
        existing={slug+'.py':(title,topics,brief) for slug,title,topics,brief in TASKS}
        nc=sorted(t['path'] for t in trees['neetcode'] if t['path'].startswith('python/') and t['path'].endswith('.py'))
        mandatory=['python/'+p for p in existing]
        nc=mandatory+[p for p in nc if p not in mandatory][:120-len(mandatory)]
        ex=sorted(t['path'] for t in trees['exercism'] if t['path'].startswith('exercises/practice/') and t['path'].endswith('/.meta/example.py'))
        exclude={'hello-world','markdown','book-store','react','rest-api','grep','sgf-parsing'}
        ex=[p for p in ex if p.split('/')[2] not in exclude][:70]
        alg=[]
        for category in ('sorts','searches','strings','dynamic_programming','data_structures/arrays'):
            candidates=sorted(t['path'] for t in trees['thealgorithms'] if t['path'].startswith(category+'/') and t['path'].endswith('.py') and not t['path'].endswith('__init__.py'))
            alg.extend(candidates[:10])
        skipped=[]
        async def record(key,path):
            repo,commit,_=REPOS[key]
            raw=f'https://raw.githubusercontent.com/{repo}/{commit}/'
            code=(await get(raw+path)).text
            try:tree=ast.parse(code)
            except SyntaxError as exc:
                skipped.append({'repo':repo,'path':path,'reason':str(exc)});return None
            stem=Path(path).stem
            if key=='neetcode':
                slug=stem.split('-',1)[1];title=slug.replace('-',' ').title()
                url='https://leetcode.com/problems/'+slug+'/'
                topics=topic_tags(slug)
                brief=f'Алгоритмическая задача {title}. Реализуйте методы по указанным сигнатурам. Это краткая тематическая карточка, полное условие доступно по оригинальной ссылке.'
                if stem+'.py' in existing:title,terms,brief=existing[stem+'.py'];topics=terms.split()
            elif key=='exercism':
                slug=path.split('/')[2];title=slug.replace('-',' ').title()
                url=f'https://exercism.org/tracks/python/exercises/{slug}'
                brief=(await get(raw+f'exercises/practice/{slug}/.docs/instructions.md')).text
                topics=['algorithm','practice','sequence','string']
            else:
                slug=stem;title=stem.replace('_',' ').title()
                url=f'https://github.com/{repo}/blob/{commit}/{path}'
                docs=[ast.get_docstring(tree) or '']+[ast.get_docstring(n) or '' for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
                clean=[d.split('>>>')[0].split('Example:')[0].strip() for d in docs]
                brief='\n\n'.join(d for d in clean if d)[:8000] or f'Реализуйте алгоритм {title}. Сигнатуры входа и выхода приведены ниже.'
                topics=['algorithm',path.split('/')[0], 'array' if '/arrays/' in path else path.split('/')[0]]
            signatures=[]
            for node in ast.walk(tree):
                if isinstance(node,ast.FunctionDef) and not node.name.startswith('test'):
                    signatures.append(node.name+'('+', '.join(a.arg for a in node.args.args)+')')
            return {'source_repo':key,'repo':repo,'commit':commit,'path':path,'title':title,'brief':brief,
                'topics':topics,'code':code,'signatures':signatures[:20],'url':url,
                'solution_url':f'https://github.com/{repo}/blob/{commit}/{path}',
                'sha256':hashlib.sha256(code.encode()).hexdigest(),'validation':'AST syntax only; not executed'}
        downloaded=await asyncio.gather(*(record(key,path) for key,paths in [('neetcode',nc),('exercism',ex),('thealgorithms',alg)] for path in paths))
        records=[]
        for key,limit in [('neetcode',100),('exercism',60),('thealgorithms',40)]:
            chosen=[r for r in downloaded if r and r['source_repo']==key][:limit]
            assert len(chosen)==limit, f'Not enough valid sources: {key}'
            records.extend(chosen)
        (root/'skipped.json').write_text(json.dumps(skipped,ensure_ascii=False,indent=2),encoding='utf-8')
        assert len({r['url'] for r in records})==200
        (root/'corpus.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'downloaded':len(records),'sources':{'neetcode':100,'exercism':60,'thealgorithms':40}}))

async def ingest(db,root):
    records=json.loads((root/'corpus.json').read_text(encoding='utf-8'))
    assert len(records)==200 and len({r['url'] for r in records})==200
    licenses={key:(root/(key+'-LICENSE.txt')).read_text(encoding='utf-8') for key in REPOS}
    # Validate everything before writing any documents.
    for r in records:
        assert r['commit']==REPOS[r['source_repo']][1]
        assert r['sha256']==hashlib.sha256(r['code'].encode()).hexdigest()
        ast.parse(r['code'])
    stats={'created':0,'updated':0,'unchanged':0}
    for r in records:
        topics=['algorithm','ready',*r['topics']]
        common={'languages':['python'],'grade_hint':'junior' if r['source_repo']=='exercism' else 'middle','company':None,'license_':f"MIT; {r['repo']}; attribution and full license in solution document"}
        brief=f"Алгоритмы: {r['title']}\nИсточник: {r['url']}\n{r['brief']}\nТемы: {' '.join(r['topics'])}\nСигнатуры: {'; '.join(r['signatures'])}\nОписание не является автоматически проверенным заданием Judge0."
        st=await upsert_document(db,source='algorithm-briefs',path=r['url'],title=r['title'],text=brief,topics=topics,**common);stats[st]+=1
        solution=f"Решение: {r['title']}\nИсточник: {r['solution_url']}\nCommit: {r['commit']}\nПроверен только синтаксис; код не исполнялся.\n```python\n{r['code']}\n```\n{licenses[r['source_repo']]}"
        st=await upsert_document(db,source='algorithm-solutions',path=r['url']+'#python-solution',title='Решение: '+r['title'],text=solution,topics=['algorithm','solution',*r['topics']],**common);stats[st]+=1
    await db.commit()
    result={'import':stats,'tasks':200,'solutions':200,'knowledge':await knowledge_stats(db)}
    (root/'import-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

async def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default='/corpus');p.add_argument('--fetch',action='store_true');p.add_argument('--ingest',action='store_true');a=p.parse_args();root=Path(a.root)
    if a.fetch:await fetch(root)
    if a.ingest:
        from app.db.session import SessionLocal
        async with SessionLocal() as db:print(json.dumps(await ingest(db,root),ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
