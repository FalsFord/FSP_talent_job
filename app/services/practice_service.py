"""Small stdin/stdout exercises. Test expectations stay on the server."""
import random

CATALOG = [
    {'id':'reverse','title':'Разворот последовательности','topic':'Массивы','level':'Начальный',
     'statement':'Прочитайте строку целых чисел, разделённых пробелами. Выведите числа в обратном порядке. Пустой ввод даёт пустую строку.',
     'example':{'input':'1 2 3 4','output':'4 3 2 1'}, 'hint':'Сохраните числа в массиве и обойдите его с конца.', 'keywords':['reverse','list','массив','список']},
    {'id':'unique','title':'Уникальные значения','topic':'Множества','level':'Начальный',
     'statement':'Прочитайте целые числа через пробел. Выведите количество различных чисел. Для пустого ввода выведите 0.',
     'example':{'input':'3 1 3 2 1','output':'3'}, 'hint':'Множество хранит каждое значение только один раз.', 'keywords':['unique','duplicate','уникаль','дубликат']},
    {'id':'sum','title':'Сумма элементов','topic':'Массивы','level':'Начальный',
     'statement':'Прочитайте целые числа через пробел. Выведите их сумму. Пустой ввод имеет сумму 0.',
     'example':{'input':'5 -2 8','output':'11'}, 'hint':'Начните с нуля и прибавляйте каждое число.', 'keywords':['sum','сумм','aggregate']},
    {'id':'brackets','title':'Баланс скобок','topic':'Стек','level':'Средний',
     'statement':'На вход дана строка из символов ( и ). Выведите YES, если скобки сбалансированы, иначе NO. Пустая строка сбалансирована.',
     'example':{'input':'(()())','output':'YES'}, 'hint':'Следите за балансом: он не может стать отрицательным и должен закончиться нулём.', 'keywords':['stack','скоб','стек','balance']},
]
from app.services.algorithm_bank import CATALOG as EXTRA
CATALOG.extend(EXTRA)

def get_task(key):
    return next((t for t in CATALOG if t['id'] == key), None)

def tests(key):
    if any(t['id']==key for t in EXTRA):
        from app.services.algorithm_bank import cases
        return [(source,expected) for source,expected,_ in cases(key)]
    rng = random.Random(9281)
    if key == 'brackets':
        return [(s, 'YES' if s in ('', '()', '(()())', '(())()') else 'NO') for s in ['', '()', '(()())', '(())()', ')(', '(()', '())(']]
    arrays = [[], [0], [-5, 2, -5], [1, 2, 3, 4], [7]*20, [rng.randint(-100,100) for _ in range(250)]]
    return [(' '.join(map(str,a)), ' '.join(map(str,a[::-1])) if key=='reverse' else str(len(set(a))) if key=='unique' else str(sum(a))) for a in arrays]
