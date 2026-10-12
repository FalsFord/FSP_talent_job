import unittest,json
from fastapi import HTTPException
from app.services.task_readiness import issues,require_ready

class Readiness(unittest.TestCase):
    def test_placeholders(self):
        t={'title':'Новое задание','condition':'Опишите задачу и требования к решению.','practice_id':'custom:1'}
        self.assertEqual(len(issues(t)),3)
        with self.assertRaises(HTTPException) as exc:require_ready([t])
        self.assertEqual(exc.exception.status_code,422)
    def test_empty_tests(self):
        t={'title':'Сумма чисел','condition':'Прочитайте числа и выведите их сумму.','practice_id':'custom:1'}
        for raw in ('','[]','bad','[{"input":"","output":""}]','[{"input":"1"}]'):
            self.assertTrue(issues({**t,'tests_json':raw}))
        self.assertFalse(issues({**t,'tests_json':json.dumps([{'input':'','output':'0'}])}))
    def test_cases(self):
        t={'title':'Сервис заказов','condition':'Создайте сервис заказов с обработкой ошибок.'}
        self.assertTrue(issues(t));require_ready([{**t,'criteria':'Проверка ошибок и тестирование'}])
    def test_catalog_algorithm(self):
        require_ready([{'title':'Разворот чисел','condition':'Прочитайте числа и выведите их в обратном порядке.','practice_id':'reverse'}])
    def test_empty_set(self):
        with self.assertRaises(HTTPException):require_ready([])

unittest.main()
