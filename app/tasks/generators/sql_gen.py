"""SQL-генераторы. Эталонный запрос выполняется на трёх наборах данных (один показываем кандидату,
два скрыты) — это защищает от «зашитых» ответов и от обмена готовыми решениями."""
from __future__ import annotations

import random

from app.tasks.datasets import build_dataset, preview, schema_text
from app.tasks.rng import rng_for
from app.tasks.runners.sql_runner import SqlRunError, run_select
from app.tasks.themes import THEMES, pick_theme
from app.tasks.types import ContextPack, GeneratorDef, Kind, TaskSpec

_NOTE = ("Один SELECT (допустим WITH … SELECT), диалект SQLite. Результат сравнивается по значениям и порядку "
         "столбцов, названия столбцов не важны. Запрос проверяется на нескольких наборах данных.")


def _finish(gid, grade, topic, seed, ctx: ContextPack, theme_name, theme, statement, ref_sql, ordered, rng_ds,
            ds_kwargs, difficulty, nontrivial) -> TaskSpec | None:
    datasets, expected = [], []
    for k in range(3):
        ds = build_dataset(rng_ds(k), theme, **ds_kwargs)
        try:
            res = run_select(ds, ref_sql)
        except SqlRunError:
            return None
        if not nontrivial(res.rows):
            return None
        datasets.append(ds)
        expected.append(res.rows)
    return TaskSpec(
        generator_id=gid, kind=Kind.SQL_QUERY, language="sql", grade=grade, topic=topic, seed=seed,
        statement=statement,
        public={"dialect": "sqlite", "schema": schema_text(theme), "preview": preview(datasets[0]), "note": _NOTE,
                "starter": "SELECT ", "theme": theme_name},
        private={"datasets": datasets, "expected": expected, "ordered": ordered, "reference_sql": ref_sql},
        difficulty=difficulty, time_limit_s=420, sources=list(ctx.sources[:3]),
    )


def _make(gid, topic, difficulty, grade_for_build, params_fn, ds_kwargs=None):
    """Фабрика build-функции: params_fn(rng, theme) -> (statement, ref_sql, ordered, nontrivial)."""
    ds_kwargs = ds_kwargs or {}

    def build(rng: random.Random, ctx: ContextPack, grade: str, seed: int) -> TaskSpec:
        theme_name = pick_theme(rng, ctx.text)
        theme = THEMES[theme_name]
        for attempt in range(12):
            statement, ref, ordered, nontrivial = params_fn(rng, theme)
            spec = _finish(gid, grade, topic, seed, ctx, theme_name, theme, statement, ref, ordered,
                           lambda k, a=attempt: rng_for(seed, gid, "ds", a, k), ds_kwargs, difficulty, nontrivial)
            if spec:
                return spec
        raise RuntimeError(f"cannot build non-trivial task for {gid}")

    return build


def _rows_between(lo, hi=None):
    return lambda rows: len(rows) >= lo and (hi is None or len(rows) <= hi)


# ---- intern ---------------------------------------------------------------------------------
def _p_filter_sort(rng, t):
    T, K = rng.choice(range(500, 3000, 100)), rng.randint(3, 6)
    st = (f"Выведите id и {t['amt']} {t['child_gen']} со статусом '{t['ok']}' и значением {t['amt']} больше {T}. "
          f"Отсортируйте по {t['amt']} по убыванию, при равенстве — по id по возрастанию. Оставьте первые {K} строк. "
          f"Столбцы: id, {t['amt']}.")
    ref = (f"SELECT id, {t['amt']} FROM {t['child']} WHERE status='{t['ok']}' AND {t['amt']} > {T} "
           f"ORDER BY {t['amt']} DESC, id ASC LIMIT {K}")
    return st, ref, True, _rows_between(2)


# ---- junior ---------------------------------------------------------------------------------
def _p_join_agg(rng, t):
    T = rng.choice(range(3000, 9000, 100))
    st = (f"Для каждого {t['parent_sg']} выведите name и суммарную {t['amt_name']} {t['child_gen']} со статусом "
          f"'{t['ok']}' (столбец total). Оставьте только тех, у кого total строго больше {T}. "
          f"Сортировка: total по убыванию, затем name по возрастанию. Столбцы: name, total.")
    ref = (f"SELECT p.name, SUM(c.{t['amt']}) AS total FROM {t['parent']} p JOIN {t['child']} c ON c.{t['fk']}=p.id "
           f"WHERE c.status='{t['ok']}' GROUP BY p.id, p.name HAVING SUM(c.{t['amt']}) > {T} "
           f"ORDER BY total DESC, p.name ASC")
    return st, ref, True, _rows_between(2)


def _p_count_city(rng, t):
    st = (f"Для каждого города выведите city и количество {t['parent_gen']} (столбец cnt), у которых есть хотя бы "
          f"одно {t['child_sg']} со статусом '{t['ok']}'. Сортировка: cnt по убыванию, затем city по возрастанию. "
          f"Столбцы: city, cnt.")
    ref = (f"SELECT p.city, COUNT(DISTINCT p.id) AS cnt FROM {t['parent']} p JOIN {t['child']} c "
           f"ON c.{t['fk']}=p.id WHERE c.status='{t['ok']}' GROUP BY p.city ORDER BY cnt DESC, p.city ASC")
    return st, ref, True, _rows_between(2)


# ---- middle ---------------------------------------------------------------------------------
def _p_anti_join(rng, t):
    # Порог задаём относительно MAX(created_at): набор данных у каждого кандидата свой.
    n = rng.randint(10, 20)
    st = (f"Выведите id и name {t['parent_gen']}, у которых нет ни одного {t['child_sg']} за последние {n} дней "
          f"относительно самой поздней даты created_at в таблице {t['child']} (включая саму эту дату). "
          f"Сортировка по id. Столбцы: id, name.")
    ref = (f"SELECT p.id, p.name FROM {t['parent']} p WHERE NOT EXISTS (SELECT 1 FROM {t['child']} c "
           f"WHERE c.{t['fk']}=p.id AND julianday(c.created_at) >= julianday((SELECT MAX(created_at) FROM {t['child']})) - {n - 1}) "
           f"ORDER BY p.id")
    return st, ref, True, _rows_between(2)


def _p_topn_city(rng, t):
    N = rng.choice([2, 3])
    st = (f"Для каждого города выведите по {N} строк таблицы {t['child']} с наибольшим {t['amt']} (при равенстве — с меньшим id): "
          f"city, order_id, {t['amt']}, rn (номер 1…{N} внутри города). Сортировка: city, rn. "
          f"Столбцы: city, order_id, {t['amt']}, rn.")
    ref = (f"SELECT city, order_id, {t['amt']}, rn FROM (SELECT p.city AS city, c.id AS order_id, c.{t['amt']} AS {t['amt']}, "
           f"ROW_NUMBER() OVER (PARTITION BY p.city ORDER BY c.{t['amt']} DESC, c.id ASC) AS rn "
           f"FROM {t['child']} c JOIN {t['parent']} p ON p.id=c.{t['fk']}) WHERE rn <= {N} ORDER BY city, rn")
    return st, ref, True, _rows_between(4)


def _p_above_avg(rng, t):
    st = (f"Выведите id, {t['fk']} и {t['amt']} тех {t['child_gen']}, значение {t['amt']} которых строго больше "
          f"среднего {t['amt']} {t['child_gen']} этого же {t['parent_sg']}. Сортировка по id. "
          f"Столбцы: id, {t['fk']}, {t['amt']}.")
    ref = (f"SELECT id, {t['fk']}, {t['amt']} FROM (SELECT id, {t['fk']}, {t['amt']}, "
           f"AVG({t['amt']}) OVER (PARTITION BY {t['fk']}) AS avg_amt FROM {t['child']}) "
           f"WHERE {t['amt']} > avg_amt ORDER BY id")
    return st, ref, True, _rows_between(3)


# ---- senior ---------------------------------------------------------------------------------
def _p_running_total(rng, t):
    st = (f"Для каждой даты created_at выведите: day (дата), daily_total — сумма {t['amt']} {t['child_gen']} со "
          f"статусом '{t['ok']}' за этот день, running_total — накопленная сумма daily_total от первой даты до "
          f"текущей включительно. Даты без подходящих {t['child_gen']} не выводить. Сортировка по day. "
          f"Столбцы: day, daily_total, running_total.")
    ref = (f"SELECT day, daily_total, SUM(daily_total) OVER (ORDER BY day) AS running_total FROM "
           f"(SELECT created_at AS day, SUM({t['amt']}) AS daily_total FROM {t['child']} "
           f"WHERE status='{t['ok']}' GROUP BY created_at) ORDER BY day")
    return st, ref, True, _rows_between(5)


def _p_streak(rng, t):
    K = rng.choice([2, 3])
    st = (f"Для каждого {t['parent_sg']} найдите наибольшую серию подряд идущих календарных дней, в каждый из которых "
          f"было хотя бы одно {t['child_sg']} (по created_at). Выведите {t['fk']} и streak (длина серии) только для "
          f"тех, у кого streak не меньше {K}. Сортировка: streak по убыванию, затем {t['fk']} по возрастанию. "
          f"Столбцы: {t['fk']}, streak.")
    ref = (f"WITH d AS (SELECT DISTINCT {t['fk']} AS pid, created_at AS day FROM {t['child']}), "
           f"g AS (SELECT pid, day, CAST(julianday(day) AS INTEGER) - ROW_NUMBER() OVER (PARTITION BY pid ORDER BY day) AS grp FROM d), "
           f"s AS (SELECT pid, grp, COUNT(*) AS len FROM g GROUP BY pid, grp) "
           f"SELECT pid, MAX(len) AS streak FROM s GROUP BY pid HAVING MAX(len) >= {K} ORDER BY streak DESC, pid ASC")
    return st, ref, True, _rows_between(2)


def _p_cond_agg(rng, t):
    st = (f"Для каждого {t['parent_sg']}, у которого есть хотя бы одно {t['child_sg']}, выведите: id, paid_cnt — число "
          f"{t['child_gen']} со статусом '{t['ok']}', bad_cnt — со статусом '{t['bad']}', bad_share — доля "
          f"'{t['bad']}' среди всех {t['child_gen']} этого {t['parent_sg']}, округлённая до 2 знаков. "
          f"Сортировка: bad_share по убыванию, затем id. Столбцы: id, paid_cnt, bad_cnt, bad_share.")
    ref = (f"SELECT p.id, SUM(CASE WHEN c.status='{t['ok']}' THEN 1 ELSE 0 END) AS paid_cnt, "
           f"SUM(CASE WHEN c.status='{t['bad']}' THEN 1 ELSE 0 END) AS bad_cnt, "
           f"ROUND(1.0*SUM(CASE WHEN c.status='{t['bad']}' THEN 1 ELSE 0 END)/COUNT(*), 2) AS bad_share "
           f"FROM {t['parent']} p JOIN {t['child']} c ON c.{t['fk']}=p.id GROUP BY p.id ORDER BY bad_share DESC, p.id")
    return st, ref, True, _rows_between(4)


# ---- lead -----------------------------------------------------------------------------------
def _p_retention(rng, t):
    N = rng.choice([7, 10, 14])
    st = (f"Какова доля {t['parent_gen']}, оформивших второе {t['child_sg']} не позднее чем через {N} дней после "
          f"первого (по created_at, при равенстве дат порядок задаёт id), среди всех {t['parent_gen']}, у которых "
          f"есть хотя бы одно {t['child_sg']}? Выведите одну строку и один столбец share, округлено до 2 знаков.")
    ref = (f"WITH r AS (SELECT {t['fk']} AS pid, created_at, id, ROW_NUMBER() OVER (PARTITION BY {t['fk']} ORDER BY created_at, id) AS rn "
           f"FROM {t['child']}), f AS (SELECT pid, created_at AS d1 FROM r WHERE rn=1), "
           f"s AS (SELECT pid, created_at AS d2 FROM r WHERE rn=2) "
           f"SELECT ROUND(1.0*SUM(CASE WHEN s.d2 IS NOT NULL AND julianday(s.d2)-julianday(f.d1) <= {N} THEN 1 ELSE 0 END)/COUNT(*), 2) AS share "
           f"FROM f LEFT JOIN s ON s.pid=f.pid")
    return st, ref, False, lambda rows: len(rows) == 1 and rows[0][0] is not None and 0 < rows[0][0] < 1


SQL_GENERATORS = [
    GeneratorDef("sql.intern.filter_sort", "sql", Kind.SQL_QUERY, "select_where_order", ("intern",), -1.0,
                 ("where", "order by", "limit", "фильтр", "select"),
                 _make("sql.intern.filter_sort", "select_where_order", -1.0, None, _p_filter_sort)),
    GeneratorDef("sql.junior.join_agg", "sql", Kind.SQL_QUERY, "join_group_having", ("junior",), -0.2,
                 ("join", "group by", "having", "агрегат", "sum"),
                 _make("sql.junior.join_agg", "join_group_having", -0.2, None, _p_join_agg)),
    GeneratorDef("sql.junior.count_city", "sql", Kind.SQL_QUERY, "join_distinct_count", ("junior", "intern"), -0.4,
                 ("count", "distinct", "join", "group by"),
                 _make("sql.junior.count_city", "join_distinct_count", -0.4, None, _p_count_city)),
    GeneratorDef("sql.middle.anti_join", "sql", Kind.SQL_QUERY, "anti_join_subquery", ("middle", "junior"), 0.4,
                 ("not exists", "left join", "подзапрос", "subquery", "anti"),
                 _make("sql.middle.anti_join", "anti_join_subquery", 0.4, None, _p_anti_join)),
    GeneratorDef("sql.middle.topn_city", "sql", Kind.SQL_QUERY, "window_row_number", ("middle", "senior"), 0.6,
                 ("window", "row_number", "over", "partition", "оконн", "top"),
                 _make("sql.middle.topn_city", "window_row_number", 0.6, None, _p_topn_city)),
    GeneratorDef("sql.middle.above_avg", "sql", Kind.SQL_QUERY, "window_avg_subquery", ("middle",), 0.5,
                 ("avg", "window", "подзапрос", "cte", "partition"),
                 _make("sql.middle.above_avg", "window_avg_subquery", 0.5, None, _p_above_avg)),
    GeneratorDef("sql.senior.running_total", "sql", Kind.SQL_QUERY, "window_running_total", ("senior", "middle"), 1.0,
                 ("running", "накоп", "window", "sum over", "отчёт", "report"),
                 _make("sql.senior.running_total", "window_running_total", 1.0, None, _p_running_total)),
    GeneratorDef("sql.senior.streak", "sql", Kind.SQL_QUERY, "gaps_and_islands", ("senior", "lead"), 1.5,
                 ("streak", "серия", "island", "consecutive", "row_number", "retention", "активност"),
                 _make("sql.senior.streak", "gaps_and_islands", 1.5, None, _p_streak, {"bursts": True})),
    GeneratorDef("sql.senior.cond_agg", "sql", Kind.SQL_QUERY, "conditional_aggregation", ("senior", "middle"), 1.1,
                 ("case when", "conditional", "pivot", "доля", "share", "fraud", "отмен"),
                 _make("sql.senior.cond_agg", "conditional_aggregation", 1.1, None, _p_cond_agg)),
    GeneratorDef("sql.lead.retention", "sql", Kind.SQL_QUERY, "cohort_retention", ("lead", "senior"), 1.9,
                 ("retention", "cohort", "удержани", "когорт", "метрик", "analytics", "аналитик"),
                 _make("sql.lead.retention", "cohort_retention", 1.9, None, _p_retention, {"n_children": 60, "days": 50})),
]
