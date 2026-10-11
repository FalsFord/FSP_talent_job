"""Vacancy configuration schema. Actual AI screening lives in Reqcore."""
import re
from datetime import datetime, timezone
from pydantic import BaseModel, Field, model_validator

GRADES = {'intern': 0, 'junior': 1, 'middle': 2, 'senior': 3, 'lead': 4}
ALIASES = {'postgres': 'postgresql', 'golang': 'go', 'js': 'javascript', 'ts': 'typescript'}


def skill_key(value):
    value = value.strip().lower()
    return ALIASES.get(value, value)


class Criteria(BaseModel):
    mode: str = Field(default='auto', pattern='^(auto|manual)$')
    min_grade: str | None = Field(default=None, pattern='^(intern|junior|middle|senior|lead)$')
    min_experience_years: float = Field(default=0, ge=0, le=50)
    required_skills: list[str] = Field(default_factory=list, max_length=50)
    work_format: str | None = Field(default=None, pattern='^(remote|office|hybrid)$')
    salary_max: int | None = Field(default=None, ge=0)
    weights: dict[str, int] = Field(default_factory=lambda: {'grade': 25, 'experience': 25, 'skills': 35, 'format': 10, 'salary': 5})
    suitable_threshold: int = Field(default=75, ge=1, le=100)
    unsuitable_threshold: int = Field(default=35, ge=0, le=99)
    strict_grade: bool = True
    strict_experience: bool = True
    reqcore_criteria: list[dict] = Field(default_factory=list, max_length=10)
    source: str = 'vacancy_fields'

    @model_validator(mode='after')
    def valid_weights(self):
        reserved = {'grade', 'experience', 'skills', 'format', 'salary'}
        keys = []
        for c in self.reqcore_criteria:
            if not isinstance(c.get('key'), str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', c['key']) or c['key'] in reserved:
                raise ValueError('Ключи дополнительных критериев должны быть уникальными')
            keys.append(c['key'])
            if not isinstance(c.get('name'), str) or not 1 <= len(c['name']) <= 200:
                raise ValueError('Нужно название критерия')
            if not isinstance(c.get('description'), str) or len(c['description']) > 4000:
                raise ValueError('Описание критерия не длиннее 4000 символов')
            if c.get('category') not in ('technical', 'experience', 'soft_skills', 'education', 'custom'):
                raise ValueError('Оцениваются только профессиональные требования')
            if not isinstance(c.get('weight'), int) or not 0 <= c['weight'] <= 100 or c.get('maxScore') != 10:
                raise ValueError('Проверьте вес и максимум оценки критерия')
        if len(set(keys)) != len(keys):
            raise ValueError('Ключи критериев должны быть уникальными')
        if set(self.weights) != {'grade', 'experience', 'skills', 'format', 'salary'}:
            raise ValueError('Нужны веса грейда, опыта, навыков, формата и зарплаты')
        if any(not 0 <= v <= 100 for v in self.weights.values()) or not sum(self.weights.values()):
            raise ValueError('Вес должен быть от 0 до 100; сумма больше нуля')
        if self.unsuitable_threshold >= self.suitable_threshold:
            raise ValueError('Порог неподходящих должен быть ниже порога подходящих')
        self.required_skills = list(dict.fromkeys(s.strip() for s in self.required_skills if s.strip()))
        if any(len(s) > 128 for s in self.required_skills):
            raise ValueError('Название навыка не длиннее 128 символов')
        return self


def auto_criteria(vacancy):
    text = ' '.join(str(vacancy.get(k) or '') for k in ('title', 'description', 'requirements', 'experience'))
    grade = str(vacancy.get('grade') or '').lower().replace('+', '')
    if grade not in GRADES:
        grade = next((g for g in reversed(GRADES) if re.search(r'\b' + g + r'\b', text, re.I)), None)
    match = re.search(r'(?:от\s*|не менее\s*|минимум\s*|at least\s*)?(\d+(?:[.,]\d+)?)\s*(?:[–—-]\s*\d+\s*)?(?:лет|год[а]?|years?)', text, re.I)
    years = min(50, float(match[1].replace(',', '.'))) if match else 0
    skills = vacancy.get('skills', [])
    if not skills:
        technologies = ['Python', 'JavaScript', 'TypeScript', 'Java', 'Go', 'PHP', 'SQL', 'PostgreSQL', 'Redis', 'Docker', 'Kubernetes', 'React', 'Vue', 'FastAPI', 'Django', 'Spring', 'Git', 'Linux']
        skills = [s for s in technologies if re.search(r'(?<!\w)' + re.escape(s) + r'(?!\w)', text, re.I)]
    settings = Criteria(min_grade=grade, min_experience_years=years,
                        required_skills=skills, work_format=vacancy.get('work_format'),
                        salary_max=vacancy.get('salary_max') or None)
    return settings.model_dump()

