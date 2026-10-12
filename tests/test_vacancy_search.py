import unittest
from unittest.mock import AsyncMock,patch
from app.services.vacancy_search import rank,lexical_score,cosine

JOBS=[{'id':'backend','title':'Backend-разработчик Python','skills':['Python','FastAPI'],'description':'Сервисы API','company_name':'Компания','work_format':'remote'}, {'id':'frontend','title':'Frontend React','skills':['React'],'description':'Интерфейсы','company_name':'Компания','work_format':'office'}]
class SearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_semantic_vectors_rank_and_fallback(self):
        with patch('app.services.vacancy_search.vectors',AsyncMock(return_value=[[1,0],[1,0],[0,1]])):
            items,method=await rank('обработка заказов',JOBS)
            self.assertEqual(method,'semantic');self.assertEqual(items[0]['id'],'backend')
        with patch('app.services.vacancy_search.vectors',AsyncMock(side_effect=ValueError('provider unavailable'))):
            items,method=await rank('серверная разработка на питоне',JOBS)
            self.assertEqual(method,'concepts');self.assertEqual(items[0]['id'],'backend')
    async def test_empty_query_and_synonyms(self):
        items,method=await rank('',JOBS)
        self.assertEqual(items,JOBS);self.assertEqual(method,'recent')
        self.assertGreater(lexical_score('фронтенд интерфейсы',JOBS[1]),lexical_score('фронтенд интерфейсы',JOBS[0]))
        self.assertAlmostEqual(cosine([1,0],[1,0]),1)
        self.assertEqual(cosine([0,0],[1,0]),0)
if __name__=='__main__': unittest.main()
