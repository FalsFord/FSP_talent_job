"""Authenticated adapter to Reqcore's built-in AI scoring; no simulated scores."""
import hmac
import os
import json
import re
from datetime import datetime, timezone
import httpx
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel
from .engine import Criteria, auto_criteria

app = FastAPI(title='EndPoint Reqcore bridge', version='2.0.0')

def authorize(x_service_token: str = Header(default='')):
    expected = os.environ.get('ATS_SERVICE_TOKEN', '')
    if not expected or not hmac.compare_digest(expected, x_service_token):
        raise HTTPException(401, 'Internal service authentication required')

async def reqcore(path, payload=None):
    async with httpx.AsyncClient(timeout=300) as client:
        url = os.environ.get('REQCORE_URL', 'http://reqcore:3000') + '/api/endpoint/' + path
        headers = {'X-Service-Token': os.environ['ATS_SERVICE_TOKEN']}
        try:
            result = await (client.get(url, headers=headers) if payload is None else client.post(url, json=payload, headers=headers))
        except httpx.RequestError as exc:
            raise HTTPException(503, 'Reqcore или локальная модель недоступны. Отклик остаётся на ручном рассмотрении.') from exc
        if result.is_error:
            raise HTTPException(503, 'Reqcore или локальная модель недоступны. Отклик остаётся на ручном рассмотрении.')
        return result.json()

class Evaluation(BaseModel):
    candidate: dict
    criteria: Criteria
    vacancy: dict
    cover_letter: str | None = None

@app.get('/health')
def health():
    return {'status': 'ok', 'provider': 'Reqcore'}

@app.post('/status', dependencies=[Depends(authorize)])
async def status():
    return await reqcore('health')

@app.post('/parse', dependencies=[Depends(authorize)])
async def parse_resume(body: dict):
    return await reqcore('parse', body)

@app.post('/auto-config', dependencies=[Depends(authorize)])
def auto_config(vacancy: dict):
    return auto_criteria(vacancy)

def job_description(vacancy):
    return '\n'.join(f'{key}: {value}' for key, value in vacancy.items() if value is not None)

@app.post('/generate-config', dependencies=[Depends(authorize)])
async def generate_config(vacancy: dict):
    config = auto_criteria(vacancy)
    result = await reqcore('criteria', {'title': vacancy['title'], 'description': job_description(vacancy)})
    config['reqcore_criteria'] = [
        {**c, 'key': f'reqcore_{index}_' + (re.sub(r'[^a-z0-9_]', '_', c['key'].lower())[:50].strip('_') or 'criterion'), 'maxScore': 10}
        for index, c in enumerate(result['criteria'])
    ]
    config['source'] = 'reqcore_ai'
    return Criteria(**config).model_dump()

@app.post('/validate-config', dependencies=[Depends(authorize)])
def validate_config(body: Criteria):
    return body.model_dump()

def definitions(config):
    requirements = {
        'grade': ('Грейд', f'Минимальный грейд {config.min_grade}. Различай подтверждённый и заявленный грейд; неизвестный грейд требует уточнения.' if config.min_grade else None, 'custom'),
        'experience': ('Опыт', f'Опыт от {config.min_experience_years} лет; учитывать качество релевантного опыта и проекты.', 'experience'),
        'skills': ('Технологии', 'Требуемые технологии: ' + ', '.join(config.required_skills) if config.required_skills else None, 'technical'),
        'format': ('Формат работы', 'Требуемый формат: ' + config.work_format if config.work_format else None, 'custom'),
        'salary': ('Зарплатные ожидания', f'Ожидания не выше {config.salary_max} рублей' if config.salary_max else None, 'custom'),
    }
    result = [{'key': key, 'name': name, 'description': description, 'category': category, 'maxScore': 10, 'weight': config.weights[key]}
              for key, (name, description, category) in requirements.items() if description and config.weights[key] > 0]
    result.extend(c for c in config.reqcore_criteria if c['weight'] > 0)
    return result

def adapt_report(result, config, criteria, candidate):
    evaluations = {e['criterionKey']: e for e in result['scoring']['evaluations']}
    rows = []
    known_weight = sum_weight = weighted = 0
    for criterion in criteria:
        e = evaluations[criterion['key']]
        confidence = e['confidence']
        missing = {'grade': not candidate.get('grade') or not candidate.get('grade_verified'),
                   'experience': candidate.get('experience_min') is None and not candidate.get('work_experience') and not candidate.get('resume_text'),
                   'skills': not candidate.get('skills') and not candidate.get('resume_text'), 'format': not candidate.get('work_formats'),
                   'salary': candidate.get('salary_min') is None}.get(criterion['key'], False)
        ratio = e['applicantScore'] / criterion['maxScore']
        evidence = e['evidence']
        grades = {'intern': 0, 'junior': 1, 'middle': 2, 'senior': 3, 'lead': 4}
        if criterion['key'] == 'grade' and candidate.get('grade_verified') and candidate.get('grade') in grades and config.min_grade in grades and grades[candidate['grade']] < grades[config.min_grade]:
            ratio, confidence = 0, 100
            evidence = f"Подтверждённый грейд {candidate['grade']} ниже требуемого {config.min_grade}. " + evidence
        if criterion['key'] == 'experience' and candidate.get('experience_max') is not None and candidate['experience_max'] < config.min_experience_years:
            ratio, confidence = 0, 100
            evidence = f"В профиле указан опыт не более {candidate['experience_max']} лет; требуется от {config.min_experience_years}. " + evidence
        known = confidence >= 70 and not missing
        weight = criterion['weight']
        sum_weight += weight
        weighted += ratio * weight
        if known: known_weight += weight
        rows.append({'key': criterion['key'], 'label': criterion['name'], 'requirement': criterion['description'],
                     'status': ('match' if ratio >= .7 else 'mismatch') if known else 'unknown',
                     'ratio': ratio, 'weight': weight, 'confidence': confidence, 'evidence': evidence,
                     'strengths': e['strengths'], 'gaps': e['gaps']})
    coverage = round(100 * known_weight / sum_weight) if sum_weight else 0
    score = round(100 * weighted / sum_weight) if sum_weight else 0
    category = 'review'
    if coverage >= 80:
        if score >= config.suitable_threshold:
            category = 'suitable'
        elif score <= config.unsuitable_threshold and all(r['status'] != 'unknown' for r in rows if r['weight']):
            category = 'unsuitable'
    grades = {'intern': 0, 'junior': 1, 'middle': 2, 'senior': 3, 'lead': 4}
    definite_grade = config.strict_grade and config.min_grade in grades and candidate.get('grade_verified') and candidate.get('grade') in grades and grades[candidate['grade']] < grades[config.min_grade]
    definite_experience = config.strict_experience and candidate.get('experience_max') is not None and candidate['experience_max'] < config.min_experience_years
    if definite_grade or definite_experience: category = 'unsuitable'
    return {'category': category, 'score': score, 'coverage': coverage, 'criteria': rows,
            'summary': result['scoring']['summary'], 'provider': 'Reqcore', 'model': result.get('model'),
            'usage': result.get('usage'), 'evaluated_at': datetime.now(timezone.utc).isoformat(),
            'decision_owner': 'employer', 'notice': 'Рекомендация Reqcore ATS. Итоговое решение принимает работодатель; статус отклика автоматически не меняется.'}

@app.post('/evaluate', dependencies=[Depends(authorize)])
async def evaluation(body: Evaluation):
    criteria = definitions(body.criteria)
    if not criteria: raise HTTPException(422, 'Не заданы профессиональные критерии')
    result = await reqcore('evaluate', {'jobTitle': body.vacancy['title'], 'jobDescription': job_description(body.vacancy),
                                      'resumeText': json.dumps(body.candidate, ensure_ascii=False),
                                      'coverLetterText': body.cover_letter, 'criteria': criteria})
    return adapt_report(result, body.criteria, criteria, body.candidate)
