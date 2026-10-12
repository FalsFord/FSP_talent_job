"""Автомат статусов приглашений/откликов и проверки перед отправкой. Чистые функции."""
from __future__ import annotations

TRANSITIONS: dict[str, set[str]] = {
    "accepted": {"withdrawn"},
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
