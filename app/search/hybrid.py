import math


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return max(0.0, min(1.0, dot / (na * nb)))


def keyword_overlap(query: str, document: str) -> float:
    q = {t for t in query.lower().split() if len(t) > 2}
    d = {t for t in document.lower().split() if len(t) > 2}
    if not q:
        return 0.0
    return len(q & d) / len(q)


def skill_jaccard(need_skills: list[str], candidate_skills: list[str]) -> float:
    a = {s.lower() for s in need_skills}
    b = {s.lower() for s in candidate_skills}
    if not a:
        return 0.5
    if not b:
        return 0.0
    return len(a & b) / len(a | b)


def compute_match_score(
    *,
    semantic: float,
    keyword: float,
    grade_match: bool,
    skill_j: float,
    profile_strength: float,
    fsp_boost: float,
) -> float:
    grade_factor = 1.0 if grade_match else 0.6
    strength = min(profile_strength / 100.0, 1.0)
    score = (
        0.35 * semantic
        + 0.20 * keyword
        + 0.20 * skill_j
        + 0.15 * grade_factor
        + 0.07 * strength
        + 0.03 * fsp_boost
    )
    return round(min(max(score, 0.0), 1.0), 4)
