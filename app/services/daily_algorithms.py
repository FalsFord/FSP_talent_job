"""Retrieval-driven, parameterized algorithms; private deterministic oracles, no LLM execution."""
import hashlib
import math
import random
import re
from app.services import knowledge_service
from app.services.reward_service import today

KINDS = {
    'sum': ('Сумма кратных', 'Массивы', ['sum', 'сумм', 'array', 'массив']),
    'unique': ('Различные остатки', 'Множества', ['unique', 'уникаль', 'set', 'множеств']),
    'reverse': ('Обратный порядок с преобразованием', 'Массивы', ['reverse', 'список', 'list', 'массив']),
    'brackets': ('Баланс скобок', 'Стек', ['stack', 'стек', 'скоб', 'balance']),
    'prefix': ('Максимальная сумма префикса', 'Массивы', ['prefix', 'префикс', 'сумм', 'array']),
    'runs': ('Соседние изменения', 'Последовательности', ['sequence', 'последователь', 'сравнен', 'array']),
}

def oracle(kind, p, a):
    if kind == 'sum': return str(sum(x for x in a if x % p == 0))
    if kind == 'unique': return str(len({x % p for x in a}))
    if kind == 'reverse': return ' '.join(str(x+p) for x in reversed(a))
    if kind == 'runs': return str(sum(a[i] != a[i-1] for i in range(1, len(a))))
    if kind == 'prefix':
        total = best = 0
        for x in a:
            total += x
            best = max(best, total)
        return str(best)
    balance = 0
    for c in a:
        balance += 1 if c == '(' else -1
        if balance < 0: return 'NO'
    return 'YES' if balance == 0 else 'NO'

def cases(task):
    if task['kind']=='gigachat':
        import json
        return [(c['input'],c['output'],c.get('size',len(c['input'].split()))) for c in json.loads(task['tests_json'])]
    if task['kind'].startswith('bank:'):
        from app.services.algorithm_bank import cases as bank_cases
        return bank_cases(task['kind'].split(':',1)[1],task['seed'])
    rng = random.Random(task['seed'])
    if task['kind'] == 'brackets':
        values = ['', '()', ')(', '(()', '())(', '(()())', *['()'*(n//2) for n in (250,2500,10000)]]
        return [(a, oracle('brackets', 0, a), len(a)) for a in values]
    values = [[], [0], [-12,-3,0,3,12], [7]*20]
    values += [[rng.randint(-1000,1000) for _ in range(n)] for n in (250,2500,10000)]
    return [(' '.join(map(str,a)), oracle(task['kind'],task['parameter'],a), len(a)) for a in values]

async def generate(db, day, *, user_id=None):
    if user_id is not None:
        from app.services.algorithm_generation import generate as generate_algorithm
        from app.api.endpoint import state, save
        history=await state(db,user_id,'practice:algorithm-history',{'counts':{},'titles':[]})
        counts=dict(history.get('counts',{})); titles=list(history.get('titles',[])); result=[]
        topics=['массивы строки хеш таблицы','поиск сортировка стек очереди','графы деревья обход BFS','динамическое программирование теория чисел']
        for index,topic in enumerate(topics):
            task=await generate_algorithm(db,context='Ежедневная практика алгоритмов: '+topic,
                grade='junior',counts=counts,avoid_titles=titles)
            source=task['template_source'];counts[source]=counts.get(source,0)+1;titles.append(task['title'])
            result.append({**task,'id':f'{day}-gigachat-{index+1}','day':day,'kind':'gigachat'})
        await save(db,user_id,'practice:algorithm-history',{'counts':counts,'titles':titles[-200:]})
        return result
    ctx = await knowledge_service.retrieve_context(db, query='алгоритмы массивы множества стек сортировка бинарный поиск граф BFS динамическое программирование хеш таблицы теория чисел', language='python', grade='junior', k=24)
    if not ctx.chunks:
        raise ValueError('В базе RAG нет материалов для практики. Загрузите материалы в базу знаний.')
    seed = int(hashlib.sha256(day.encode()).hexdigest()[:12],16)
    rng = random.Random(seed)
    ranked = []
    for kind, (_, _, terms) in KINDS.items():
        matching = [c for c in ctx.chunks if any(term in c['text'].lower() for term in terms)]
        if matching: ranked.append((len(matching)+rng.random(),kind,matching))
    from app.services.algorithm_bank import CATALOG as bank
    for t in bank:
        matching=[c for c in ctx.chunks if any(term in c['text'].lower() for term in t['keywords'])]
        if matching:ranked.append((rng.random(),'bank:'+t['id'],matching))
    if not ranked: raise ValueError('RAG не нашёл алгоритмических тем в материалах. Добавьте материалы об алгоритмах.')
    result = []
    from datetime import date
    ordered=sorted(ranked,key=lambda row:row[1]);start=date.fromisoformat(day).toordinal()*4%len(ordered)
    rotated=ordered[start:]+ordered[:start];chosen=[];topics=set()
    for row in rotated:
        topic=next(t['topic'] for t in bank if 'bank:'+t['id']==row[1]) if row[1].startswith('bank:') else KINDS[row[1]][1]
        if topic not in topics:chosen.append(row);topics.add(topic)
        if len(chosen)==4:break
    chosen+= [r for r in rotated if r not in chosen][:max(0,4-len(chosen))]
    for _,kind,matching in chosen:
        if kind.startswith('bank:'):
            t=next(t for t in bank if 'bank:'+t['id']==kind)
            result.append({**{k:v for k,v in t.items() if k!='keywords'},'id':f"{day}-{t['id']}",'day':day,'kind':kind,'seed':rng.randrange(2**31),'parameter':0,'generation_method':'retrieval_templates','sources':list(dict.fromkeys(c['label'] for c in matching[:2]))})
            continue
        p = rng.randint(2,9)
        statement = {
            'sum': f'Прочитайте целые числа через пробел. Выведите сумму только чисел, кратных {p}. Для пустого ввода выведите 0.',
            'unique': f'Прочитайте целые числа через пробел. Выведите количество различных остатков от деления на {p}. Остаток нормализуется в диапазон от 0 до {p-1}, в том числе для отрицательных чисел: ((x % {p}) + {p}) % {p}. Для пустого ввода выведите 0.',
            'reverse': f'Прочитайте целые числа через пробел. Выведите их в обратном порядке, прибавив к каждому {p}. Пустой ввод даёт пустой вывод.',
            'prefix': 'Прочитайте целые числа через пробел. Выведите максимальную сумму префикса, включая пустой префикс с суммой 0.',
            'runs': 'Прочитайте целые числа через пробел. Выведите количество соседних пар с различными значениями. Для нуля или одного числа выведите 0.',
            'brackets': 'Дана строка из ( и ). Выведите YES, если скобки сбалансированы, иначе NO. Пустая строка сбалансирована.',
        }[kind]
        a = '(()())' if kind == 'brackets' else [3,6,3,9]
        result.append({'id':f'{day}-{kind}', 'day':day, 'kind':kind,'parameter':p,'seed':rng.randrange(2**31),
            'title':KINDS[kind][0], 'topic':KINDS[kind][1], 'level':'Средний' if kind in ('prefix','brackets') else 'Начальный',
            'statement':statement+' Не более 10000 элементов; числа от −1000 до 1000.' if kind != 'brackets' else statement+' Длина до 10000.',
            'example':{'input':a if isinstance(a,str) else ' '.join(map(str,a)), 'output':oracle(kind,p,a)},
            'hint':'Решение возможно за один проход. Продумайте, какие данные необходимо хранить.',
            'generation_method':'retrieval_templates', 'sources':list(dict.fromkeys(c['label'] for c in matching[:2]))})
    return result

def complexity(results):
    samples = [{'n':r['n'],'seconds':float(r['time'])} for r in results if r['passed'] and r.get('time') is not None and r['n']>=250]
    unknown = {'estimate':None,'method':'Рост времени на входах 250, 2500, 10000; приблизительная оценка, не доказательство.', 'samples':samples}
    if len(samples)<3 or min(s['seconds'] for s in samples)<=.02: return unknown
    x=[math.log(s['n']) for s in samples]; y=[math.log(s['seconds']) for s in samples]
    mx=sum(x)/len(x); my=sum(y)/len(y)
    slope=sum((a-mx)*(b-my) for a,b in zip(x,y))/sum((a-mx)**2 for a in x)
    if slope < .2: return unknown  # runtime startup dominates; do not claim O(1)
    estimate = 'O(n)' if slope<1.2 else 'O(n log n)' if slope<1.55 else 'O(n²)' if slope<2.5 else 'хуже O(n²)'
    return {**unknown,'estimate':estimate,'exponent':round(slope,2)}

def syntax_failure(results):
    return any(re.search(r'SyntaxError|IndentationError|TabError|expected.*(?:;|token|expression)|illegal start|unclosed|unexpected token', r.get('error') or '', re.I) for r in results)

def assessment(results, passed, total, syntax_errors):
    times=[float(r['time']) for r in results if r.get('time') is not None]
    memories=[float(r['memory']) for r in results if r.get('memory') is not None]
    time=max(times) if times else None; memory=max(memories) if memories else None
    solved=passed==total
    components={'correctness':round(60*passed/total,2),
        'time':round(20*max(0,1-time/2),2) if solved and time is not None else 0,
        'memory':round(10*max(0,1-memory/128000),2) if solved and memory is not None else 0,
        'syntax':max(0,10-2*syntax_errors) if solved else 0}
    return {'score':round(sum(components.values()),2),'components':components,'syntax_errors':syntax_errors,
        'time_seconds':time,'memory_kb':memory,'complexity':complexity(results),
        'note':'Учебная оценка: 60 за тесты, 20 за время, 10 за память, 10 за отсутствие синтаксических ошибок (−2 за проверку с ошибкой). Время и память включают среду языка; грейд не меняется.'}
