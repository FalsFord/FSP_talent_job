"""Тесты ядра конвейера заданий. Запуск: python -m unittest discover -s tests -v (только стандартная библиотека)."""
import random
import re
import unittest
from datetime import date, datetime, timedelta

from app.domain import grade_policy as gp
from app.domain import invitation_fsm as fsm
from app.domain import ranking as rk
from app.domain import trust_rules as tr
from app.tasks import grading
from app.tasks.blueprint import compose_test, quotas, session_time_limit
from app.tasks.generators import ALL_GENERATORS, REGISTRY, eligible
from app.tasks.quiz_bank import QUIZ_ITEMS
from app.tasks.rag import chunking, classify, retriever
from app.tasks.rag.llm import validate_draft_items
from app.tasks.runners.code_runner import java_available
from app.tasks.runners.sql_runner import SqlRunError, run_select
from app.tasks.types import ContextPack, Kind
from app.tasks.validation import validate_bank, validate_spec

NOW = datetime(2026, 10, 8, 12, 0)


class SqlSandbox(unittest.TestCase):
    def setUp(self):
        spec = REGISTRY["sql.intern.filter_sort"].build(random.Random(1), ContextPack(), "intern", 1)
        self.ds = spec.private["datasets"][0]

    def test_blocks_dangerous_statements(self):
        for q in ["DROP TABLE orders", "SELECT 1; DROP TABLE orders", "PRAGMA table_info(orders)", "ATTACH DATABASE 'x' AS y",
                  "WITH x AS (SELECT 1) DELETE FROM orders", "SELECT load_extension('x')", "UPDATE orders SET id=1"]:
            with self.assertRaises(SqlRunError, msg=q):
                run_select(self.ds, q)

    def test_timeout(self):
        with self.assertRaises(SqlRunError) as cm:
            run_select(self.ds, "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT count(*) FROM c", timeout_s=0.5)
        self.assertEqual(cm.exception.code, "TIMEOUT")


class Generators(unittest.TestCase):
    def test_bank_validation_non_code(self):
        rep = validate_bank(ALL_GENERATORS, seeds=range(8), skip_code_exec=True)
        for gid, r in rep.items():
            self.assertEqual(r["built_ok"], r["attempts"], f"{gid}: {r['errors']}")

    def test_code_generators_structurally_valid(self):
        rep = validate_bank([g for g in ALL_GENERATORS if g.needs_code_exec], seeds=range(5))
        for gid, r in rep.items():
            self.assertEqual(r["built_ok"], r["attempts"], f"{gid}: {r['errors']}")

    def test_sql_discriminates_wrong_solutions(self):
        # Текстовые «мутанты» эталона (>→>=, DESC→ASC, …) должны давать другой результат хотя бы на одном наборе.
        # Часть мутантов эквивалентна эталону (напр., JOIN→LEFT JOIN при фильтре по дочерней таблице), поэтому
        # требуем порог не 100 %, а: каждое задание ≥ 0.3 (в среднем по сидам), среднее по банку ≥ 0.6.
        means = []
        for g in [g for g in ALL_GENERATORS if g.language == "sql" and g.kind == Kind.SQL_QUERY]:
            vals = []
            for sd in range(6):
                spec = g.build(random.Random(sd), ContextPack(), g.grades[0], sd)
                rep = validate_spec(spec)
                self.assertTrue(rep.ok, rep.errors)
                if "discrimination" in rep.metrics:
                    vals.append(rep.metrics["discrimination"])
            m = sum(vals) / len(vals)
            self.assertGreaterEqual(m, 0.3, g.id)
            means.append(m)
        self.assertGreaterEqual(sum(means) / len(means), 0.6)

    def test_deterministic_by_seed_and_varied_across_seeds(self):
        for gid in ("sql.middle.topn_city", "py.junior.mutable_default", "java.junior.int_overflow"):
            g = REGISTRY[gid]
            a = g.build(random.Random(7), ContextPack(), g.grades[0], 7)
            b = g.build(random.Random(7), ContextPack(), g.grades[0], 7)
            self.assertEqual(a.fingerprint(), b.fingerprint())
            fps = {g.build(random.Random(s), ContextPack(), g.grades[0], s).fingerprint() for s in range(10)}
            self.assertGreater(len(fps), 5, gid)

    def test_rag_context_steers_theme(self):
        ctx = ContextPack(text="курьер доставка логистика доставки курьеров")
        spec = REGISTRY["sql.junior.join_agg"].build(random.Random(3), ctx, "junior", 3)
        self.assertEqual(spec.public["theme"], "delivery")

    def test_options_never_leak_answer_key_in_public(self):
        for g in [g for g in ALL_GENERATORS if g.kind == Kind.PREDICT]:
            spec = g.build(random.Random(2), ContextPack(), g.grades[0], 2)
            self.assertNotIn("correct", spec.public)
            self.assertIn(spec.private["correct"], spec.public["options"])


class Grading(unittest.TestCase):
    def test_sql_reference_passes_and_wrong_fails(self):
        spec = REGISTRY["sql.junior.join_agg"].build(random.Random(11), ContextPack(), "junior", 11)
        ok = grading.grade_answer(spec.kind, "sql", spec.public, spec.private, {"value": spec.private["reference_sql"]})
        self.assertEqual(ok.score, 1.0)
        bad = grading.grade_answer(spec.kind, "sql", spec.public, spec.private, {"value": "SELECT 1"})
        self.assertEqual(bad.score, 0.0)
        # «почти верное» решение с ошибкой на границе (> вместо >=) должно ловиться хотя бы на части сидов
        caught = 0
        for sd in range(10):
            sp = REGISTRY["sql.junior.join_agg"].build(random.Random(sd), ContextPack(), "junior", sd)
            r = grading.grade_answer(sp.kind, "sql", sp.public, sp.private,
                                     {"value": sp.private["reference_sql"].replace("> ", ">= ", 1)})
            caught += r.score < 1.0
        self.assertGreaterEqual(caught, 2)

    def test_sql_hardcoded_answer_fails_on_hidden_datasets(self):
        spec = REGISTRY["sql.intern.filter_sort"].build(random.Random(4), ContextPack(), "intern", 4)
        rows = spec.private["expected"][0]
        literal = " UNION ALL ".join("SELECT " + ", ".join(repr(c) for c in r) for r in rows)
        res = grading.grade_answer(spec.kind, "sql", spec.public, spec.private, {"value": literal})
        self.assertLessEqual(res.score, 1 / 3 + 1e-9)

    def test_predict_and_quiz(self):
        spec = REGISTRY["py.senior.dict_mutation"].build(random.Random(1), ContextPack(), "senior", 1)
        self.assertEqual(grading.grade_answer(spec.kind, "python", spec.public, spec.private, spec.private["correct"]).score, 1.0)
        wrong = next(o for o in spec.public["options"] if o != spec.private["correct"])
        self.assertEqual(grading.grade_answer(spec.kind, "python", spec.public, spec.private, wrong).score, 0.0)

    def test_python_code_task_and_solution_not_transferable(self):
        def solve_for(statement):
            a, b = map(int, re.search(r"делятся на (\d+) или на (\d+)", statement).groups())
            return f"def solve(n):\n    return sum(i for i in range(1, n) if i % {a} == 0 or i % {b} == 0)\n"

        g = REGISTRY["py.intern.sum_multiples"]
        s1 = g.build(random.Random(1), ContextPack(), "intern", 1)
        s2 = next(s for s in (g.build(random.Random(k), ContextPack(), "intern", k) for k in range(2, 40))
                  if re.search(r"делятся на (\d+) или на (\d+)", s.statement).groups() !=
                  re.search(r"делятся на (\d+) или на (\d+)", s1.statement).groups())
        own = grading.grade_answer(s1.kind, "python", s1.public, s1.private, solve_for(s1.statement), code_exec_enabled=True)
        self.assertEqual(own.score, 1.0, own.details)
        stolen = grading.grade_answer(s2.kind, "python", s2.public, s2.private, solve_for(s1.statement), code_exec_enabled=True)
        self.assertLess(stolen.score, 1.0)   # чужое решение под другие константы не проходит

    def test_code_exec_disabled_is_unscored(self):
        s = REGISTRY["py.intern.sum_multiples"].build(random.Random(1), ContextPack(), "intern", 1)
        r = grading.grade_answer(s.kind, "python", s.public, s.private, "def solve(n): return 0", code_exec_enabled=False)
        self.assertIsNone(r.score)

    @unittest.skipUnless(java_available(), "JDK недоступен")
    def test_java_code_task(self):
        s = REGISTRY["java.junior.sum_multiples"].build(random.Random(2), ContextPack(), "junior", 2)
        a, b = map(int, re.search(r"делятся на (\d+) или на (\d+)", s.statement).groups())
        good = f"class Solution {{ static long solve(int n) {{ long s=0; for (int i=1;i<n;i++) if (i%{a}==0||i%{b}==0) s+=i; return s; }} }}"
        self.assertEqual(grading.grade_answer(s.kind, "java", s.public, s.private, good, code_exec_enabled=True).score, 1.0)
        self.assertLess(grading.grade_answer(s.kind, "java", s.public, s.private, good.replace("s+=i", "s+=1"), code_exec_enabled=True).score, 0.15)

    def test_rubric(self):
        spec = REGISTRY["approach.sql"].build(random.Random(1), ContextPack(text="медленный запрос explain индекс"), "senior", 1)
        strong = ("Сначала смотрю план EXPLAIN ANALYZE и ищу seq scan, затем проверяю индексы: составной покрывающий индекс "
                  "с учётом селективности. Переписываю запрос: убираю select *, функции в where и лишние join. Обновляю статистику, "
                  "делаю vacuum, использую keyset-пагинацию и материализованные представления для агрегатов; партиционирование по дате.")
        weak = "Надо оптимизировать запрос."
        s_strong, _ = grading.score_rubric(strong, spec.private["rubric"])
        s_weak, _ = grading.score_rubric(weak, spec.private["rubric"])
        self.assertGreater(s_strong, 0.6)
        self.assertLessEqual(s_weak, 0.3)
        stuffed, _ = grading.score_rubric("индекс " * 80, spec.private["rubric"])
        self.assertLessEqual(stuffed, 0.4)


class Blueprint(unittest.TestCase):
    def pool(self):
        return QUIZ_ITEMS

    def build(self, grade, langs, **kw):
        return compose_test(seed=kw.pop("seed", 42), grade=grade, languages=langs, n_items=12, purpose="onboarding",
                            contexts={}, quiz_pool=self.pool(), code_exec=kw.pop("code_exec", False), java_ok=True, **kw)

    def test_composition_and_no_code_when_disabled(self):
        for grade in ("intern", "junior", "middle", "senior", "lead"):
            specs = self.build(grade, ["python", "sql"])
            self.assertGreaterEqual(len(specs), 9, grade)
            self.assertFalse([s for s in specs if s.kind == Kind.CODE_FUNCTION], grade)
            self.assertTrue([s for s in specs if s.kind == Kind.SQL_QUERY], grade)

    def test_code_tasks_when_enabled(self):
        specs = self.build("middle", ["python", "sql"], code_exec=True)
        self.assertTrue([s for s in specs if s.kind == Kind.CODE_FUNCTION])
        self.assertLessEqual(len([s for s in specs if s.kind == Kind.APPROACH]), 1)

    def test_languages_respected(self):
        specs = self.build("junior", ["java", "sql"])
        self.assertEqual({s.language for s in specs} - {"java", "sql"}, set())
        self.assertTrue([s for s in specs if s.language == "java"])

    def test_retake_gives_different_tasks(self):
        a = {s.fingerprint() for s in self.build("middle", ["python", "sql"], seed=1)}
        b = {s.fingerprint() for s in self.build("middle", ["python", "sql"], seed=2)}
        self.assertLess(len(a & b) / max(1, len(a)), 0.5)

    def test_recent_generators_deprioritised(self):
        first = self.build("junior", ["python", "sql"], seed=3)
        recent = {s.generator_id for s in first if not s.generator_id.startswith("item:")}
        again = self.build("junior", ["python", "sql"], seed=4, recent_generators=recent)
        overlap = len({s.generator_id for s in again if not s.generator_id.startswith("item:")} & recent)
        self.assertLessEqual(overlap, len(recent))

    def test_time_limit_bounds(self):
        specs = self.build("senior", ["python", "sql"])
        self.assertTrue(900 <= session_time_limit(specs, "onboarding") <= 3600)
        self.assertTrue(300 <= session_time_limit(specs[:6], "micro") <= 900)

    def test_quotas_sum(self):
        for n in (6, 12, 20):
            self.assertEqual(sum(quotas(n, "senior", "onboarding").values()), n)


class GradePolicy(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(gp.classify_result(0.75, 1.0), "pass")
        self.assertEqual(gp.classify_result(0.65, 1.0), "borderline")
        self.assertEqual(gp.classify_result(0.4, 1.0), "fail")
        self.assertEqual(gp.classify_result(0.9, 0.3), "borderline")   # низкая уверенность не даёт pass

    def test_no_forced_downgrade(self):
        d = gp.decide(purpose="reattest", target_level=2, confirmed_level=2, result="fail")
        self.assertIsNone(d.new_level)
        d = gp.decide(purpose="up", target_level=3, confirmed_level=2, result="fail")
        self.assertIsNone(d.new_level)
        self.assertFalse(d.changed)

    def test_onboarding_fail_offers_lower(self):
        d = gp.decide(purpose="onboarding", target_level=2, confirmed_level=None, result="fail")
        self.assertEqual((d.next_step, d.new_level), ("try_lower", None))
        self.assertEqual(gp.decide(purpose="onboarding", target_level=0, confirmed_level=None, result="fail").next_step, "retry_later")

    def test_pass_assigns_and_starts_clock(self):
        d = gp.decide(purpose="onboarding", target_level=2, confirmed_level=None, result="pass", ratio=0.8)
        self.assertEqual((d.new_level, d.changed), (2, True))
        self.assertEqual(gp.decide(purpose="up", target_level=3, confirmed_level=2, result="pass", ratio=0.95).next_step, "can_try_higher")
        r = gp.decide(purpose="reattest", target_level=2, confirmed_level=2, result="pass")
        self.assertTrue(r.reconfirmed and not r.changed)

    def common(self, **over):
        base = dict(purpose="up", confirmed_level=2, grade_changed_at=None, last_attempt_same_target_at=None,
                    last_expired_at=None, last_micro_at=None)
        base.update(over)
        return gp.check_start(NOW, **base)

    def test_cooldown_90_days(self):
        e = self.common(grade_changed_at=NOW - timedelta(days=30))
        self.assertFalse(e.allowed)
        self.assertEqual(e.code, "GRADE_CHANGE_COOLDOWN")
        self.assertEqual(e.available_at, NOW - timedelta(days=30) + timedelta(days=90))
        self.assertTrue(self.common(grade_changed_at=NOW - timedelta(days=91)).allowed)

    def test_reattest_not_limited_by_grade_cooldown(self):
        self.assertTrue(self.common(purpose="reattest", grade_changed_at=NOW - timedelta(days=5)).allowed)

    def test_retake_and_expired_cooldowns(self):
        self.assertEqual(self.common(purpose="onboarding", confirmed_level=None,
                                     last_attempt_same_target_at=NOW - timedelta(days=2)).code, "RETAKE_COOLDOWN")
        self.assertEqual(self.common(purpose="onboarding", confirmed_level=None,
                                     last_expired_at=NOW - timedelta(hours=3)).code, "EXPIRED_COOLDOWN")
        self.assertTrue(self.common(purpose="onboarding", confirmed_level=None).allowed)   # тест ниже — сразу

    def test_micro_weekly(self):
        self.assertFalse(self.common(purpose="micro", last_micro_at=NOW - timedelta(days=2)).allowed)
        self.assertTrue(self.common(purpose="micro", last_micro_at=NOW - timedelta(days=7)).allowed)
        self.assertFalse(self.common(purpose="micro", confirmed_level=None).allowed)

    def test_freshness_decay_and_status(self):
        vu = NOW + timedelta(days=10)
        self.assertEqual(gp.verification_status(NOW, vu), "confirmed")
        self.assertEqual(gp.freshness_multiplier(NOW, vu), 1.0)
        late = NOW + timedelta(days=10 + 45)
        self.assertEqual(gp.verification_status(late, vu), "stale")
        self.assertAlmostEqual(gp.freshness_multiplier(late, vu), 0.85, places=2)
        self.assertEqual(gp.freshness_multiplier(NOW + timedelta(days=500), vu), gp.STALE_FLOOR)

    def test_session_ratio_ignores_unscored(self):
        ratio, frac = gp.session_ratio([(1.0, 1), (0.0, 1), (None, 2)])
        self.assertEqual(ratio, 0.5)
        self.assertEqual(frac, 0.5)


class Ranking(unittest.TestCase):
    def test_fsp_no_history_is_zero_not_penalty(self):
        self.assertEqual(rk.fsp_score([]), 0.0)
        s0 = rk.strength_score(test_ratio=0.8, fsp=0.0, task_ratio=None, freshness=1.0)
        s1 = rk.strength_score(test_ratio=0.8, fsp=rk.fsp_score([{"place": 2, "date": date.today()}]), task_ratio=None, freshness=1.0)
        self.assertGreater(s1, s0)
        self.assertEqual(s0, 48.0)

    def test_fsp_recency_decay(self):
        new = rk.fsp_score([{"place": 1, "date": date.today()}])
        old = rk.fsp_score([{"place": 1, "date": date.today() - timedelta(days=365 * 4)}])
        self.assertGreater(new, old)

    def test_stale_reduces_strength_not_grade(self):
        fresh = rk.strength_score(test_ratio=0.8, fsp=0.2, task_ratio=0.5, freshness=1.0)
        stale = rk.strength_score(test_ratio=0.8, fsp=0.2, task_ratio=0.5, freshness=0.7)
        self.assertAlmostEqual(stale / fresh, 0.7, places=2)

    def test_skills_overlap_weights_verified_higher(self):
        v, matched, miss = rk.skills_overlap(["Python", "SQL", "Kafka"], {"python": "verified", "sql": "declared"})
        self.assertAlmostEqual(v, (1.0 + 0.5) / 3)
        self.assertEqual((matched, miss), (["Python", "SQL"], ["Kafka"]))

    def test_rank_order_prefers_strong_within_similar_match(self):
        m = rk.match_score(semantic=0.7, skills=0.8, keyword=0.5, grade=1.0, fmt=1.0)
        self.assertGreater(rk.rank_score(m, 80), rk.rank_score(m, 40))

    def test_reasons(self):
        r = rk.build_reasons(semantic=0.6, skills=0.8, matched=["Python", "SQL"], missing=["Kafka"], verified=["Python"],
                             grade_fit_v=1.0, fmt_ok=True, fsp=0.3, fsp_count=2, status="stale")
        codes = [x["code"] for x in r]
        self.assertTrue({"SEMANTIC", "SKILLS", "GRADE", "FORMAT", "FSP", "STALE"} <= set(codes))


class Invitations(unittest.TestCase):
    def test_transitions(self):
        self.assertTrue(fsm.can_transition("sent", "viewed", "candidate"))
        self.assertTrue(fsm.can_transition("viewed", "accepted", "candidate"))
        self.assertFalse(fsm.can_transition("declined", "accepted", "candidate"))   # терминальный статус
        self.assertFalse(fsm.can_transition("sent", "accepted", "employer"))        # работодатель не принимает за кандидата
        self.assertFalse(fsm.can_transition("sent", "viewed", "employer"))
        self.assertTrue(fsm.can_transition("sent", "withdrawn", "employer"))
        self.assertFalse(fsm.can_transition("accepted", "withdrawn", "employer"))

    def test_salary_rules(self):
        self.assertIsNone(fsm.validate_salary(100000, 150000))
        self.assertEqual(fsm.validate_salary(None, 1), "SALARY_REQUIRED")
        self.assertEqual(fsm.validate_salary(200000, 100000), "SALARY_INVALID")
        self.assertEqual(fsm.validate_salary(0, 10), "SALARY_INVALID")

    def test_limits(self):
        kw = dict(per_day=20, pair_cooldown_days=30)
        self.assertIsNone(fsm.check_invite_limits(NOW, sent_last_24h=3, last_invite_to_candidate=None, account_age_days=30, **kw))
        self.assertEqual(fsm.check_invite_limits(NOW, sent_last_24h=5, last_invite_to_candidate=None, account_age_days=2, **kw), "INVITE_LIMIT")
        self.assertEqual(fsm.check_invite_limits(NOW, sent_last_24h=0, last_invite_to_candidate=NOW - timedelta(days=3), account_age_days=30, **kw), "INVITE_COOLDOWN")


class Trust(unittest.TestCase):
    def test_flags(self):
        good, gf = tr.vacancy_trust(salary_from=200000, salary_to=300000, account_age_days=60, email_domain_matches=True,
                                    text="Разрабатываем платёжный сервис на Python и PostgreSQL. Ищем backend-разработчика в команду из пяти человек, "
                                         "работа над API, ревью кода, тестирование и сопровождение в production.")
        bad, bf = tr.vacancy_trust(salary_from=50000, salary_to=500000, account_age_days=1,
                                   text="ПИШИТЕ В TELEGRAM @fastmoney, нужна предоплата 5000")
        self.assertGreater(good, 70)
        self.assertLess(bad, 30)
        self.assertTrue({"OFFPLATFORM_CONTACT", "MONEY_REQUEST"} <= set(bf))
        self.assertEqual(gf, [])


class Rag(unittest.TestCase):
    MD = ("# Тестовое задание: Backend-разработчик (Python, Junior)\n\nКомпания разрабатывает сервис доставки. "
          "Нужно реализовать REST API на FastAPI с хранением в PostgreSQL.\n\n## Требования\n\n- кэш с TTL\n- тесты pytest\n\n"
          "Описание " + "подробностей " * 120)

    def test_parse_and_chunk(self):
        doc = chunking.parse_markdown(self.MD)
        self.assertIn("Backend", doc.title)
        chunks = chunking.chunk_text(doc.text, max_chars=500, overlap=60)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 700 for c in chunks))

    def test_classify(self):
        m = classify.classify("backend/python/acme/test.md", "Backend-разработчик (Python, Junior)", self.MD)
        self.assertIn("python", m.languages)
        self.assertEqual(m.grade_hint, "junior")
        self.assertEqual(m.company, "acme")
        self.assertIn("caching", m.topics)
        self.assertIn("rest_api", m.topics)

    def test_rrf_and_mmr(self):
        fused = retriever.rrf([["a", "b", "c"], ["c", "a", "d"]])
        self.assertEqual(fused[0][0], "a")
        cands = [{"id": 1, "vec": [1, 0], "base": 0.5}, {"id": 2, "vec": [0.99, 0.01], "base": 0.5}, {"id": 3, "vec": [0, 1], "base": 0.4}]
        picked = retriever.mmr(cands, [1, 0], k=2, lam=0.6)
        self.assertEqual({p["id"] for p in picked}, {1, 3})   # дубликат отброшен ради разнообразия

    def test_topic_hints_and_context(self):
        ctx = retriever.build_context("q", [{"text": "оконная функция row_number over partition", "label": "doc A"}], ALL_GENERATORS)
        self.assertIn("window_row_number", ctx.topic_hints)
        self.assertEqual(ctx.sources, ["doc A"])

    def test_context_biases_selection(self):
        ctx = retriever.build_context("q", [{"text": "window row_number over partition оконные", "label": "d"}], ALL_GENERATORS)
        picks = 0
        for seed in range(10):
            specs = compose_test(seed=seed, grade="middle", languages=["sql"], n_items=6, purpose="onboarding",
                                 contexts={"sql": ctx}, quiz_pool=QUIZ_ITEMS, code_exec=False, java_ok=False)
            picks += any(s.topic == "window_row_number" for s in specs)
        self.assertGreaterEqual(picks, 8)

    def test_llm_draft_validation(self):
        good = {"items": [{"statement": "Что делает оператор yield?", "options": ["a", "b", "c", "d"], "correct": "a"}]}
        bad = {"items": [{"statement": "x", "options": ["a", "a", "c", "d"], "correct": "z"}]}
        self.assertEqual(len(validate_draft_items(good)), 1)
        self.assertEqual(validate_draft_items(bad), [])


class Simulation(unittest.TestCase):
    def test_synthetic_validation_invariants(self):
        """Механика должна быть монотонной и разделять уровни; сгенерированные задания не повторяются между попытками."""
        from app.tasks import simulation as sim

        r = sim.run(n_per_grade=8, seed=7, n_items=16, margin=0.6)
        self.assertGreaterEqual(r["discrimination_middle_test"]["auc_(>=middle vs <middle)"], 0.85)
        self.assertGreaterEqual(r["placement_with_overstated_declaration"]["within_one_grade"], 0.85)
        self.assertLess(r["leak_resistance_middle"]["share_of_items_repeating_verbatim"]["generated"], 0.02)


class Degenerate(unittest.TestCase):
    def test_group_task_never_degenerate(self):
        g = REGISTRY["py.junior.group_first_letter"]
        rep = validate_bank([g], seeds=range(150))[g.id]
        self.assertEqual(rep["built_ok"], rep["attempts"], rep["errors"])


class Registry(unittest.TestCase):
    def test_coverage_every_language_grade(self):
        for lang in ("python", "java", "sql"):
            for grade in ("intern", "junior", "middle", "senior", "lead"):
                quiz = [i for i in QUIZ_ITEMS if i["language"] == lang and i["grade"] == grade]
                gens = eligible(lang, grade, code_exec=False, java_ok=False)
                self.assertGreaterEqual(len(quiz) + len(gens), 4, (lang, grade))


if __name__ == "__main__":
    unittest.main()
