"""Small pinned MIT solution corpus; independent Russian task briefs, no LeetCode scraping."""
import argparse
import ast
import asyncio
import hashlib
import json
from pathlib import Path
import httpx
from app.services.knowledge_service import upsert_document, knowledge_stats

COMMIT='3186ede2ea4c4788e87be4b509bf2b66d5eba0e9'
BASE=f'https://raw.githubusercontent.com/neetcode-gh/leetcode/{COMMIT}'
TASKS=[
 ('0001-two-sum','Два слагаемых','hash array массив хеш', 'Найдите индексы двух разных элементов массива, сумма которых равна заданному числу.'),
 ('0003-longest-substring-without-repeating-characters','Подстрока без повторений','string sliding-window строка', 'Найдите длину самого длинного непрерывного участка строки без повторяющихся символов.'),
 ('0011-container-with-most-water','Максимальная площадь','array two-pointers массив', 'По высотам вертикальных отрезков выберите пару с максимальным произведением расстояния на меньшую высоту.'),
 ('0015-3sum','Тройка с нулевой суммой','array sort массив', 'Найдите разные тройки значений массива, сумма которых равна нулю; одинаковые тройки не повторяйте.'),
 ('0020-valid-parentheses','Парные скобки','stack стек скобки', 'Проверьте правильность вложенности круглых, квадратных и фигурных скобок.'),
 ('0021-merge-two-sorted-lists','Слияние списков','list список', 'Объедините два упорядоченных односвязных списка, сохранив порядок значений.'),
 ('0033-search-in-rotated-sorted-array','Поиск после циклического сдвига','array binary-search массив', 'Определите индекс искомого значения в отсортированном массиве без повторений после циклического сдвига.'),
 ('0049-group-anagrams','Группы анаграмм','hash string строка', 'Объедините слова в группы, если у них совпадает набор букв с учётом числа повторений.'),
 ('0053-maximum-subarray','Максимальная сумма отрезка','array sum массив сумма', 'Найдите наибольшую сумму непустого непрерывного участка массива целых чисел.'),
 ('0070-climbing-stairs','Подъём по ступеням','dynamic-programming динамика', 'Посчитайте число способов подняться на n ступеней, делая шаг на одну либо две ступени.'),
 ('0121-best-time-to-buy-and-sell-stock','Разница цен','array массив', 'По последовательности цен найдите максимальную неотрицательную прибыль одной покупки и более поздней продажи.'),
 ('0125-valid-palindrome','Палиндром текста','string two-pointers строка', 'Проверьте, читается ли текст одинаково в обе стороны после удаления неалфавитных символов и приведения регистра.'),
 ('0153-find-minimum-in-rotated-sorted-array','Минимум после сдвига','array binary-search массив', 'Найдите наименьший элемент в упорядоченном массиве без повторений, к которому применили циклический сдвиг.'),
 ('0155-min-stack','Стек с минимумом','stack стек', 'Реализуйте стек с добавлением, удалением, просмотром вершины и получением минимума за постоянное время.'),
 ('0206-reverse-linked-list','Разворот связного списка','reverse list список', 'Измените направление связей односвязного списка и верните новую голову.'),
 ('0217-contains-duplicate','Повторяющиеся значения','set unique array множество массив', 'Определите, встречается ли хотя бы одно значение массива больше одного раза.'),
 ('0238-product-of-array-except-self','Произведение остальных','prefix array префикс массив', 'Для каждой позиции вычислите произведение всех элементов массива, кроме элемента на этой позиции, без деления.'),
 ('0242-valid-anagram','Проверка анаграммы','hash string строка', 'Проверьте, совпадают ли частоты символов в двух строках.'),
 ('0347-top-k-frequent-elements','Самые частые значения','hash array массив', 'Верните k различных значений массива с наибольшей частотой появления.'),
 ('0704-binary-search','Двоичный поиск','binary-search array массив', 'Найдите индекс значения в отсортированном массиве или сообщите, что значение отсутствует.'),
]

async def fetch(root):
    root.mkdir(parents=True,exist_ok=True)
    records=[]
    async with httpx.AsyncClient(timeout=30,trust_env=False) as client:
        response=await client.get(BASE+'/LICENSE'); response.raise_for_status()
        license_text=response.text
        if not license_text.startswith('MIT License'): raise ValueError('Unexpected upstream license')
        (root/'LICENSE').write_text(license_text,encoding='utf-8')
        for slug,title,topics,brief in TASKS:
            response=await client.get(BASE+'/python/'+slug+'.py'); response.raise_for_status()
            code=response.text
            if len(code)>100000: raise ValueError('Source too large')
            ast.parse(code)  # validate syntax only; NEVER import/execute downloaded code
            problem=slug.split('-',1)[1]
            records.append({'slug':slug,'title':title,'topics':topics.split(), 'brief':brief,
                'code':code,'problem_url':'https://leetcode.com/problems/'+problem+'/',
                'solution_url':f'https://github.com/neetcode-gh/leetcode/blob/{COMMIT}/python/{slug}.py',
                'commit':COMMIT,'sha256':hashlib.sha256(code.encode()).hexdigest(),
                'solution_validation':'Python AST syntax only; not a verified Judge0 oracle'})
            await asyncio.sleep(.15)
    (root/'corpus.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    return records

async def ingest(db,root):
    records=json.loads((root/'corpus.json').read_text(encoding='utf-8'))
    license_text=(root/'LICENSE').read_text(encoding='utf-8')
    stats={'created':0,'updated':0,'unchanged':0}
    for item in records:
        if item['commit']!=COMMIT or hashlib.sha256(item['code'].encode()).hexdigest()!=item['sha256']: raise ValueError('Corpus checksum mismatch')
        ast.parse(item['code'])
        grade='junior' if item['slug'] in ('0001-two-sum','0020-valid-parentheses','0070-climbing-stairs','0121-best-time-to-buy-and-sell-stock','0125-valid-palindrome','0206-reverse-linked-list','0217-contains-duplicate','0242-valid-anagram','0704-binary-search') else 'middle'
        common={'languages':['python'],'grade_hint':grade,'company':None,'license_':'MIT (solution); Copyright (c) 2022 neetcode-gh; task brief authored by EndPoint'}
        text=f"Алгоритмическая тема: {item['title']}\n{item['brief']}\nТемы: {' '.join(item['topics'])}\nЭто краткое авторское описание темы, не полное условие для автоматической проверки.\nОригинальная задача: {item['problem_url']}"
        st=await upsert_document(db,source='algorithm-briefs',path=item['problem_url'],title=item['title'],text=text,topics=['algorithm','ready',*item['topics']],**common);stats[st]+=1
        text=f"Решение: {item['title']}\nАвтор: neetcode-gh; MIT; commit {COMMIT}\nИсточник: {item['solution_url']}\nПроверена только синтаксическая корректность; решение не является автоматически проверенным эталоном.\n```python\n{item['code']}\n```\n{license_text}"
        st=await upsert_document(db,source='algorithm-solutions',path=item['problem_url']+'#python-solution',title='Решение: '+item['title'],text=text,topics=['algorithm','solution',*item['topics']],**common);stats[st]+=1
    await db.commit()
    return {'import':stats,'tasks':len(records),'solutions':len(records),'commit':COMMIT,'knowledge':await knowledge_stats(db)}

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',default='/data/algorithms/neetcode');parser.add_argument('--fetch',action='store_true');parser.add_argument('--ingest',action='store_true');args=parser.parse_args()
    root=Path(args.root)
    if args.fetch: print(json.dumps({'downloaded':len(await fetch(root)),'root':str(root)}))
    if args.ingest:
        from app.db.session import SessionLocal
        async with SessionLocal() as db: print(json.dumps(await ingest(db,root),ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
