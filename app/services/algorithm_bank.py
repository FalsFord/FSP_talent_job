"""Verified algorithm templates with independent oracles and deterministic hidden cases."""
import random
from collections import Counter,deque
from math import gcd
from functools import reduce

SPECS=[
 ('max_subarray','Максимальная сумма подмассива','Динамическое программирование','Прочитайте целые числа через пробел. Выведите максимальную сумму непустого непрерывного подмассива. Для пустого ввода выведите 0.','-2 1 -3 4 -1 2 1 -5 4','6',['subarray','динамич','подмассив','kadane']),
 ('gcd_all','Общий делитель последовательности','Теория чисел','Прочитайте целые числа через пробел. Выведите неотрицательный наибольший общий делитель всех чисел. Для пустого ввода выведите 0.','18 -24 30','6',['gcd','делител','чисел','euclid']),
 ('second_distinct','Второй максимум','Массивы','Прочитайте целые числа через пробел. Выведите второе по величине различное число. Если различных чисел меньше двух, выведите NONE.','5 1 5 3','3',['maximum','max','максим','массив']),
 ('mode','Самое частое значение','Хеш-таблицы','Прочитайте целые числа через пробел. Выведите самое частое число. При равной частоте выберите наименьшее. Для пустого ввода выведите NONE.','3 1 3 1 2','1',['frequency','hash','частот','словар','таблиц']),
 ('lis_length','Длина возрастающей подпоследовательности','Бинарный поиск','Прочитайте целые числа через пробел. Выведите длину самой длинной строго возрастающей подпоследовательности, не обязательно непрерывной. Для пустого ввода выведите 0.','3 1 2 2 5','3',['binary','search','бинар','подпоследователь','lis']),
 ('longest_run','Самая длинная серия','Последовательности','Прочитайте целые числа через пробел. Выведите длину максимальной непрерывной серии одинаковых чисел. Для пустого ввода выведите 0.','1 1 2 2 2 1','3',['sequence','последователь','серия','run']),
 ('two_sum','Пара с заданной суммой','Хеш-таблицы','Первая строка содержит целое целевое число. Вторая строка содержит целые числа через пробел и может быть пустой. Выведите YES, если два разных элемента дают целевую сумму, иначе NO.','8\n3 5 1','YES',['two sum','pair','пара','сумм','hash']),
 ('binary_index','Первое вхождение','Бинарный поиск','Первая строка содержит искомое целое число. Вторая содержит отсортированные по возрастанию целые числа. Выведите индекс первого вхождения, считая от 0, или -1, если числа нет.','2\n1 2 2 5','1',['binary','search','бинар','поиск']),
 ('rotate','Циклический сдвиг','Массивы','Первая строка содержит неотрицательное число k. Вторая содержит целые числа через пробел. Сдвиньте последовательность вправо на k позиций и выведите числа через пробел. Пустой массив даёт пустой вывод.','2\n1 2 3 4','3 4 1 2',['rotate','сдвиг','rotation','массив']),
 ('merge_intervals','Объединение интервалов','Сортировка','Ввод: сначала число интервалов n, затем n пар целых чисел l r, где l <= r. Объедините пересекающиеся или касающиеся интервалы. Выведите каждую пару l r в отдельной строке в порядке возрастания l. При n=0 вывод пустой.','3\n1 3\n2 6\n8 10','1 6\n8 10',['interval','интервал','sort','сортиров']),
 ('shortest_path','Кратчайший путь в графе','Графы','Первая строка: n m, число вершин и рёбер неориентированного графа. Далее m пар вершин от 0 до n-1. Найдите число рёбер кратчайшего пути из 0 в n-1; если пути нет, выведите -1. При n=1 ответ 0.','4 3\n0 1\n1 2\n2 3','3',['graph','граф','bfs','path','путь']),
 ('mixed_brackets','Три вида скобок','Стек','Прочитайте строку из скобок ()[]{}. Выведите YES, если все скобки закрываются в правильном порядке и соответствуют по типу, иначе NO. Пустая строка сбалансирована.','{[()]}','YES',['stack','стек','скоб','bracket']),
]
CATALOG=[{'id':key,'title':title,'topic':topic,'level':'Средний','statement':statement+' Не более 10000 элементов/рёбер; целые числа от -10000 до 10000 (для графа: 1 <= n <= 10000).','example':{'input':sample,'output':answer},'hint':'Выберите подходящую структуру данных и проверьте граничные случаи.','keywords':words} for key,title,topic,statement,sample,answer,words in SPECS]

def oracle(key,source):
 lines=source.split('\n');nums=list(map(int,source.split())) if key!='mixed_brackets' else []
 if key=='max_subarray':
  if not nums:return '0'
  best=running=nums[0]
  for x in nums[1:]:running=max(x,running+x);best=max(best,running)
  return str(best)
 if key=='gcd_all':return str(reduce(gcd,nums,0))
 if key=='second_distinct':
  values=sorted(set(nums));return str(values[-2]) if len(values)>1 else 'NONE'
 if key=='mode':
  c=Counter(nums);return str(min(c,key=lambda x:(-c[x],x))) if c else 'NONE'
 if key=='lis_length':
  from bisect import bisect_left
  tails=[]
  for x in nums:
   i=bisect_left(tails,x)
   if i==len(tails):tails.append(x)
   else:tails[i]=x
  return str(len(tails))
 if key=='longest_run':
  best=running=0;previous=None
  for x in nums:running=running+1 if x==previous else 1;previous=x;best=max(best,running)
  return str(best)
 if key in ('two_sum','binary_index','rotate'):
  target=int(lines[0]);a=list(map(int,' '.join(lines[1:]).split()))
  if key=='two_sum':
   seen=set()
   for x in a:
    if target-x in seen:return 'YES'
    seen.add(x)
   return 'NO'
  if key=='binary_index':return str(a.index(target)) if target in a else '-1'
  if not a:return ''
  k=target%len(a);return ' '.join(map(str,a[-k:]+a[:-k] if k else a))
 if key=='merge_intervals':
  merged=[]
  for l,r in sorted(zip(nums[1::2],nums[2::2])):
   if merged and l<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],r)
   else:merged.append([l,r])
  return '\n'.join(f'{l} {r}' for l,r in merged)
 if key=='shortest_path':
  n=nums[0];graph=[[] for _ in range(n)]
  for a,b in zip(nums[2::2],nums[3::2]):graph[a].append(b);graph[b].append(a)
  distance=[-1]*n;distance[0]=0;q=deque([0])
  while q:
   a=q.popleft()
   for b in graph[a]:
    if distance[b]<0:distance[b]=distance[a]+1;q.append(b)
  return str(distance[-1])
 stack=[];pairs={')':'(',']':'[','}':'{'}
 for c in source.strip():
  if c in '([{':stack.append(c)
  elif not stack or stack.pop()!=pairs[c]:return 'NO'
 return 'NO' if stack else 'YES'

def cases(key,seed=9281):
 rng=random.Random(seed);spec=next(t for t in CATALOG if t['id']==key)
 sources=[(spec['example']['input'],5)]
 for n in (0,1,5,20,250,2500,10000):
  a=[rng.randint(-1000,1000) for _ in range(n)]
  if key in ('two_sum','binary_index','rotate'):
   if key=='binary_index':a.sort()
   target=(a[n//2] if a else 0) if key=='binary_index' else rng.randrange(30)
   source=str(target)+'\n'+' '.join(map(str,a))
  elif key=='merge_intervals':
   intervals=[(x,x+rng.randrange(10)) for x in a];source=str(n)+'\n'+'\n'.join(f'{l} {r}' for l,r in intervals)
  elif key=='shortest_path':
   vertices=max(1,n);edges=[(i,i+1) for i in range(vertices-1) if n!=5 or i!=2];source=f'{vertices} {len(edges)}\n'+'\n'.join(f'{l} {r}' for l,r in edges)
  elif key=='mixed_brackets':source=('([]{})'*(n//6)) if n%2==0 else ('['*(n//2)+')'*(n-n//2))
  else:source=' '.join(map(str,a))
  sources.append((source,n))
 edges={'max_subarray':['-9 -2 -5','5 -1 2 -8 10'],'mode':['4 2 4 2','1 1 2'],'lis_length':['3 2 1','2 2 2'],'longest_run':['7 7 7 7'],'two_sum':['6\n3','6\n3 3'],'binary_index':['2\n2 2 2','9\n1 2'],'mixed_brackets':['([)]','{[()]}','']}
 sources.extend((source,len(source.split())) for source in edges.get(key,[]))
 return [(source,oracle(key,source),n) for source,n in sources]
