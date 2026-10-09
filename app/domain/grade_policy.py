"""Политика грейда (ТЗ: грейд не понижается принудительно; смена не чаще раза в N дней).
Чистые функции: время передаётся параметром, БД не используется."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

PASS_RATIO = 0.70
BORDER_RATIO = 0.60
VALIDITY_DAYS = 180       # срок действия подтверждения грейда
STALE_DECAY_DAYS = 90     # за это время после истечения вес линейно падает до STALE_FLOOR
STALE_FLOOR = 0.7
MICRO_INTERVAL_DAYS = 7


def classify_result(ratio: float, confidence: float, pass_ratio: float = PASS_RATIO,
                    border_ratio: float = BORDER_RATIO) -> str:
    if confidence < 0.5:
        return "borderline" if ratio >= border_ratio else "fail"
    if ratio >= pass_ratio:
        return "pass"
    return "borderline" if ratio >= border_ratio else "fail"


def session_ratio(items: list[tuple[float | None, float]]) -> tuple[float, float]:
    """items: (score|None, weight). Возвращает (доля баллов, доля оценённых заданий по весу)."""
    total_w = sum(w for _, w in items) or 1.0
    scored = [(s, w) for s, w in items if s is not None]
    sw = sum(w for _, w in scored)
    if sw == 0:
        return 0.0, 0.0
    return sum(s * w for s, w in scored) / sw, sw / total_w


def confidence_from(scored_fraction: float, integrity_flags: list[str]) -> float:
    penalty = min(0.6, 0.15 * len(integrity_flags))
    return max(0.0, min(1.0, scored_fraction) - penalty)


def infer_purpose(confirmed_level: int | None, target_level: int) -> str:
    if confirmed_level is None:
        return "onboarding"
    if target_level == confirmed_level:
        return "reattest"
    return "up" if target_level > confirmed_level else "down"


@dataclass
class Eligibility:
    allowed: bool
    code: str | None = None
    message: str = ""
    available_at: datetime | None = None


def check_start(now: datetime, *, purpose: str, confirmed_level: int | None, grade_changed_at: datetime | None,
                last_attempt_same_target_at: datetime | None, last_expired_at: datetime | None,
                last_micro_at: datetime | None, cooldown_days: int = 90, retake_days: int = 7,
                expired_retry_hours: int = 24) -> Eligibility:
    if purpose == "micro":
        if confirmed_level is None:
            return Eligibility(False, "NOT_CATEGORIZED", "Мини-тест доступен после присвоения категории")
        if last_micro_at and now < last_micro_at + timedelta(days=MICRO_INTERVAL_DAYS - 1):
            return Eligibility(False, "MICRO_NOT_DUE", "Мини-тест уже пройден на этой неделе",
                               last_micro_at + timedelta(days=MICRO_INTERVAL_DAYS - 1))
        return Eligibility(True)
    if last_expired_at and now < last_expired_at + timedelta(hours=expired_retry_hours):
        return Eligibility(False, "EXPIRED_COOLDOWN", "Предыдущая попытка не была завершена вовремя",
                           last_expired_at + timedelta(hours=expired_retry_hours))
    if purpose in ("up", "down") and grade_changed_at and now < grade_changed_at + timedelta(days=cooldown_days):
        return Eligibility(False, "GRADE_CHANGE_COOLDOWN",
                           f"Грейд можно менять не чаще одного раза в {cooldown_days} дней",
                           grade_changed_at + timedelta(days=cooldown_days))
    if last_attempt_same_target_at and now < last_attempt_same_target_at + timedelta(days=retake_days):
        return Eligibility(False, "RETAKE_COOLDOWN", f"Повторная попытка на этом уровне — через {retake_days} дней",
                           last_attempt_same_target_at + timedelta(days=retake_days))
    return Eligibility(True)


@dataclass
class Decision:
    new_level: int | None        # новый подтверждённый уровень (None — без изменений)
    changed: bool                # изменился/присвоен уровень → стартует отсчёт ограничения на смену
    reconfirmed: bool            # продлено подтверждение текущего уровня
    next_step: str               # continue | try_lower | retry_later | can_try_higher
    code: str


def decide(*, purpose: str, target_level: int, confirmed_level: int | None, result: str, ratio: float = 0.0) -> Decision:
    if purpose == "micro":
        return Decision(None, False, False, "continue", "MICRO_DONE")
    if result == "pass":
        if purpose == "reattest":
            return Decision(confirmed_level, False, True, "continue", "RECONFIRMED")
        higher = "can_try_higher" if ratio >= 0.9 else "continue"
        return Decision(target_level, True, False, higher, "GRADE_CONFIRMED" if purpose == "onboarding" else "GRADE_CHANGED")
    code = "BORDERLINE" if result == "borderline" else "NOT_PASSED"
    if purpose == "onboarding":
        return Decision(None, False, False, "try_lower" if target_level > 0 else "retry_later", code)
    return Decision(None, False, False, "retry_later", code)   # грейд НЕ понижается принудительно


def verification_status(now: datetime, valid_until: datetime | None) -> str:
    if valid_until is None:
        return "unconfirmed"
    return "confirmed" if now <= valid_until else "stale"


def freshness_multiplier(now: datetime, valid_until: datetime | None) -> float:
    """1.0 пока подтверждение действует; затем линейное снижение до STALE_FLOOR. Грейд при этом не меняется."""
    if valid_until is None:
        return STALE_FLOOR
    if now <= valid_until:
        return 1.0
    late = (now - valid_until).days
    return max(STALE_FLOOR, 1.0 - (1.0 - STALE_FLOOR) * min(1.0, late / STALE_DECAY_DAYS))
