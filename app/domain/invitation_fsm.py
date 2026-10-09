"""Автомат статусов приглашений/откликов и проверки перед отправкой. Чистые функции."""
from __future__ import annotations

from datetime import datetime, timedelta

TRANSITIONS: dict[str, set[str]] = {
    "sent": {"viewed", "accepted", "declined", "withdrawn", "expired"},
    "viewed": {"accepted", "declined", "withdrawn", "expired"},
}
ACTOR_FOR: dict[str, str] = {"viewed": "candidate", "accepted": "candidate", "declined": "candidate",
                             "withdrawn": "employer", "expired": "system"}
TERMINAL = {"accepted", "declined", "withdrawn", "expired"}


def can_transition(current: str, new: str, actor: str) -> bool:
    return new in TRANSITIONS.get(current, set()) and ACTOR_FOR.get(new) == actor


def validate_salary(frm: int | None, to: int | None) -> str | None:
    """ТЗ: зарплата обязательна, диапазон «от–до» в рублях."""
    if frm is None or to is None:
        return "SALARY_REQUIRED"
    if frm <= 0 or to < frm:
        return "SALARY_INVALID"
    if to > 100_000_000:
        return "SALARY_UNREALISTIC"
    return None


def check_invite_limits(now: datetime, *, sent_last_24h: int, per_day: int, last_invite_to_candidate: datetime | None,
                        pair_cooldown_days: int, account_age_days: int) -> str | None:
    limit = min(per_day, 5) if account_age_days < 7 else per_day   # у новых аккаунтов лимит строже
    if sent_last_24h >= limit:
        return "INVITE_LIMIT"
    if last_invite_to_candidate and now < last_invite_to_candidate + timedelta(days=pair_cooldown_days):
        return "INVITE_COOLDOWN"
    return None
