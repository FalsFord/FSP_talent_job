import json,re

def issues(t):
    result=[];title=str(t.get('title') or '').strip();condition=str(t.get('condition') or t.get('statement') or '').strip()
    if len(title)<3 or re.fullmatch(r'новое задание(?:\s*\d+)?',title,re.I):result.append('Укажите название')
    if len(condition)<10 or condition=='Опишите задачу и требования к решению.':result.append('Заполните условие')
    practice=str(t.get('practice_id') or '')
    if practice.startswith('custom:') or t.get('purpose')=='practice' and not practice:
        try:
            tests=json.loads(t.get('tests_json') or '[]')
            valid=isinstance(tests,list) and 1<=len(tests)<=20 and all(isinstance(v,dict) and isinstance(v.get('input'),str) and isinstance(v.get('output'),str) and (v['input'].strip() or v['output'].strip()) and len(v['input'])<=20000 and len(v['output'])<=20000 for v in tests)
        except (ValueError,TypeError):valid=False
        if not valid:result.append('Добавьте заполненные проверочные тесты')
    elif not practice and not str(t.get('criteria') or '').strip() and not t.get('rubric'):result.append('Укажите критерии оценки')
    return result

def require_ready(tasks):
    from fastapi import HTTPException
    if not tasks:raise HTTPException(409,'Добавьте задания перед отправкой')
    errors=[f"Задание {i+1}: {', '.join(issues(t))}" for i,t in enumerate(tasks) if issues(t)]
    if errors:raise HTTPException(422,'Набор не готов к отправке. '+'; '.join(errors))
