"""Offline OAuth, refresh and response validation checks; no real token usage."""
import asyncio
import base64
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID
import httpx
from app.tasks.rag.gigachat import GigaChatLLM, GigaChatError


class GigaChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_extend_keeps_original_and_new_uses_other_template(self):
        from app.services.employer_task_service import draft_from_context
        context = SimpleNamespace(sources=['A','B'],chunks=[{'text':'Очередь задач','label':'A'},{'text':'Кеширование запросов','label':'B'}],text='Контекст')
        original={'title':'Очередь','condition':'Существующее условие с данными и ограничениями.','rubric':[{'point':'Исходный критерий','keywords':['retry']}],'sources':['A'],'template_source':'A','source_details':[]}
        llm=SimpleNamespace(complete_json=AsyncMock(return_value={'additions':'Добавьте стратегию обработки повторных запросов. Опишите, как проверить идемпотентность при отказе сервиса.','rubric':[{'point':'Дополнительный критерий','keywords':['идемпотентность']}]}))
        with patch('app.services.employer_task_service.ks.retrieve_context',AsyncMock(return_value=context)), patch('app.services.employer_task_service.get_llm',return_value=llm):
            result=await draft_from_context(None,language='python',grade='middle',context_text='Проверить надёжность',template=original)
            self.assertTrue(result['statement'].startswith(original['condition']))
            self.assertEqual(result['title'],original['title'])
            self.assertEqual(result['rubric'][0],original['rubric'][0])
            self.assertEqual(result['template_source'],'A')
            llm.complete_json.return_value={'title':'Кеширование','statement':'Разработайте кеш запросов и опишите инвалидацию данных. Предложите проверки корректности и защиты от устаревших результатов.','rubric':[{'point':'Инвалидация','keywords':['кеш']},{'point':'Проверки','keywords':['тест']}]}
            new=await draft_from_context(None,language='python',grade='middle',context_text='Проверить надёжность',exclude_sources=['A'])
            self.assertEqual(new['template_source'],'B')
            prompt=json.loads(llm.complete_json.call_args.args[1])
            self.assertIsNone(prompt['existing_task'])
            self.assertEqual(prompt['materials'][0]['source'],'B')

    async def test_rag_context_and_case_schema(self):
        from app.services.employer_task_service import draft_from_context
        context = SimpleNamespace(sources=['Учебный материал'],chunks=[{'text':'Очередь задач','label':'Учебный материал','readiness':'partial','url':'https://example.org'}])
        valid = {'title':'Очередь задач','statement':'Разработайте очередь задач и опишите стратегию повторов, обработку ошибок и способ контроля времени выполнения.','rubric':[{'point':'Повторы','keywords':['retry']},{'point':'Обработка ошибок','keywords':['ошибка']}]}
        llm = SimpleNamespace(complete_json=AsyncMock(return_value=valid))
        with patch('app.services.employer_task_service.ks.retrieve_context',AsyncMock(return_value=context)), patch('app.services.employer_task_service.get_llm',return_value=llm):
            result = await draft_from_context(None,language='python',grade='middle',context_text='Нужна очередь',purpose='qualification')
            self.assertEqual(result['title'],valid['title'])
            prompt = json.loads(llm.complete_json.call_args.args[1])
            self.assertEqual(prompt['purpose'],'qualification')
            self.assertTrue(prompt['materials'][0]['partial'])
            self.assertEqual(result['sources'],context.sources)
            llm.complete_json.return_value={'title':'x'}
            with self.assertRaises(GigaChatError):
                await draft_from_context(None,language='python',grade='middle',context_text='Нужна очередь')

    async def test_oauth_cache_refresh_and_json(self):
        tokens = []
        calls = []
        def handler(request):
            calls.append(request)
            if request.url.path.endswith('/oauth'):
                self.assertEqual(request.headers['authorization'], 'Basic ' + base64.b64encode(b'id:secret').decode())
                self.assertEqual(UUID(request.headers['rquid']).version, 4)
                self.assertEqual(request.content, b'scope=GIGACHAT_API_PERS')
                tokens.append('token' + str(len(tokens)))
                return httpx.Response(200, json={'access_token': tokens[-1], 'expires_at': (time.time()+1800)*1000})
            if request.headers['authorization'] == 'Bearer token0':
                return httpx.Response(401)
            body = json.loads(request.content)
            self.assertEqual(body['model'], 'GigaChat')
            self.assertNotIn('temperature', body)
            return httpx.Response(200, json={'choices':[{'finish_reason':'stop','message':{'content':'```json\n{"title":"Кейс"}\n```'}}]})
        client = GigaChatLLM(client_id='id',client_secret='secret',transport=httpx.MockTransport(handler))
        await asyncio.gather(*[client.access_token() for _ in range(5)])
        self.assertEqual(len(tokens), 1)
        self.assertEqual(await client.complete_json('system','context'), {'title':'Кейс'})
        self.assertEqual(len(tokens), 2)
        await client.complete_json('system','context')
        self.assertEqual(len(tokens), 2)

    async def test_errors_do_not_expose_provider_body(self):
        for code in (401,403,429,500):
            client = GigaChatLLM(credentials='secret',transport=httpx.MockTransport(lambda r: httpx.Response(code,text='PRIVATE_TOKEN')))
            with self.assertRaises(GigaChatError) as caught:
                await client.access_token()
            self.assertNotIn('PRIVATE_TOKEN',str(caught.exception))

    async def test_reject_invalid_or_truncated_output(self):
        for content, finish in [('[]','stop'), ('invalid','stop'), ('{}','length')]:
            def handler(request):
                if request.url.path.endswith('/oauth'):
                    return httpx.Response(200,json={'access_token':'token','expires_at':time.time()+1800})
                return httpx.Response(200,json={'choices':[{'finish_reason':finish,'message':{'content':content}}]})
            client = GigaChatLLM(credentials='secret',transport=httpx.MockTransport(handler))
            with self.assertRaises(GigaChatError): await client.complete_json('system','context')

    async def test_expired_token_is_rejected(self):
        client = GigaChatLLM(credentials='secret',transport=httpx.MockTransport(lambda r: httpx.Response(200,json={'access_token':'token','expires_at':time.time()-1})))
        with self.assertRaises(GigaChatError): await client.access_token()


if __name__ == '__main__': unittest.main()
