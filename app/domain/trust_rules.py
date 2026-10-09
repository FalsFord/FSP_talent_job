"""Простые rule-based проверки вакансий/приглашений (задел под «защиту от фиктивных вакансий», плюс по ТЗ).
Это первый уровень (правила); статистика и ML — этапы развития, а не часть MVP."""
from __future__ import annotations

import re

_OFFPLATFORM = re.compile(r"(t\.me/|telegram|телеграм|whatsapp|вотсап|viber|вайбер|@\w{4,}|\+?\d[\d\s().-]{9,})", re.I)
_MONEY = re.compile(r"(предоплат|внести (плату|сумму)|депозит|оплатить обучение|взнос|купить доступ)", re.I)


def text_flags(text: str) -> list[str]:
    flags = []
    if _OFFPLATFORM.search(text or ""):
        flags.append("OFFPLATFORM_CONTACT")
    if _MONEY.search(text or ""):
        flags.append("MONEY_REQUEST")
    letters = [c for c in (text or "") if c.isalpha()]
    if len(letters) > 30 and sum(c.isupper() for c in letters) / len(letters) > 0.6:
        flags.append("SHOUTING")
    if len((text or "").strip()) < 80:
        flags.append("SHORT_DESCRIPTION")
    return flags


def vacancy_trust(*, salary_from: int, salary_to: int, text: str, account_age_days: int,
                  email_domain_matches: bool = False) -> tuple[int, list[str]]:
    """Возвращает (0..100, флаги). Веса — стартовая гипотеза, калибруются по жалобам и модерации."""
    score, flags = 70, text_flags(text)
    penalty = {"OFFPLATFORM_CONTACT": 20, "MONEY_REQUEST": 40, "SHOUTING": 10, "SHORT_DESCRIPTION": 10}
    score -= sum(penalty[f] for f in flags)
    if salary_from > 0 and salary_to / salary_from > 3:
        flags.append("SALARY_RANGE_TOO_WIDE")
        score -= 10
    if account_age_days < 7:
        flags.append("NEW_ACCOUNT")
        score -= 10
    if email_domain_matches:
        score += 15
    return max(0, min(100, score)), flags
