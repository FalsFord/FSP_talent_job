"""GigaChat OAuth and inference. Credentials never leave the backend."""
import asyncio
import base64
import json
import math
import ssl
import time
from uuid import uuid4
import httpx


class GigaChatError(RuntimeError):
    pass


class GigaChatLLM:
    def __init__(self, *, credentials='', client_id='', client_secret='', scope='GIGACHAT_API_PERS',
                 model='GigaChat', base_url='https://api.giga.chat/v1',
                 oauth_url='https://ngw.devices.sberbank.ru:9443/api/v2/oauth', ca_bundle='', transport=None):
        self.credentials=credentials.strip()
        if not self.credentials and client_id and client_secret:
            self.credentials=base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
        if self.credentials.startswith('Basic '): self.credentials=self.credentials[6:].strip()
        self.scope,self.model,self.base_url,self.oauth_url=scope,model,base_url.rstrip('/'),oauth_url
        self.ssl=ssl.create_default_context()
        if ca_bundle: self.ssl.load_verify_locations(cafile=ca_bundle)
        self.transport=transport
        self.token=None;self.expires=0;self.lock=asyncio.Lock()

    def client(self):
        return httpx.AsyncClient(timeout=httpx.Timeout(90,connect=15),verify=self.ssl,
                                 transport=self.transport,trust_env=False,follow_redirects=False)

    async def access_token(self):
        if not self.credentials: raise GigaChatError('Для GigaChat нужен Authorization Key или Client Secret')
        async with self.lock:
            if self.token and self.expires>time.time()+30: return self.token
            try:
                async with self.client() as client:
                    response=await client.post(self.oauth_url,headers={'Authorization':'Basic '+self.credentials,
                        'RqUID':str(uuid4()),'Accept':'application/json'},data={'scope':self.scope})
                self.ensure_ok(response,auth=True)
                data=response.json();token=data['access_token'];expires=float(data['expires_at'])
                if expires>1e12: expires/=1000
                if not isinstance(token,str) or not token.strip() or not math.isfinite(expires) or expires<=time.time(): raise ValueError('Invalid token')
                self.token,self.expires=token,expires
                return token
            except httpx.HTTPError as exc:
                raise GigaChatError('Не удалось подключиться к GigaChat. Проверьте сеть и сертификат.') from exc
            except (ValueError,KeyError,TypeError) as exc:
                raise GigaChatError('GigaChat вернул некорректный токен доступа') from exc

    @staticmethod
    def ensure_ok(response,auth=False):
        if response.is_success: return
        if response.status_code in (401,403):
            raise GigaChatError('GigaChat отклонил авторизацию. Проверьте ключ и scope.' if auth else 'Нет доступа к выбранной модели GigaChat.')
        if response.status_code==402: raise GigaChatError('Достигнут лимит GigaChat. Проверьте баланс токенов и повторите позже.')
        if response.status_code==429: raise GigaChatError('GigaChat отклонил генерацию из-за лимита (429). Повторите позже или проверьте лимиты GigaChat.')
        raise GigaChatError('GigaChat временно недоступен' if response.status_code>=500 else 'GigaChat отклонил запрос генерации')

    async def request(self,path,body=None):
        for attempt in range(2):
            token=await self.access_token()
            try:
                async with self.client() as client:
                    response=await client.request('POST' if body is not None else 'GET',self.base_url+path,
                        headers={'Authorization':'Bearer '+token,'Accept':'application/json'},json=body)
            except httpx.HTTPError as exc:
                raise GigaChatError('Не удалось получить ответ GigaChat. Повторите позже.') from exc
            if response.status_code==401 and attempt==0:
                async with self.lock:
                    if self.token==token: self.token=None;self.expires=0
                continue
            self.ensure_ok(response)
            try: return response.json()
            except ValueError as exc: raise GigaChatError('Некорректный ответ GigaChat') from exc

    async def complete_json(self,system,user,schema=None,*,max_tokens=2500):
        body={'model':self.model,'max_tokens':max_tokens,
            'messages':[{'role':'system','content':system},{'role':'user','content':user}]}
        if schema:
            body['response_format']={'type':'json_schema','schema':schema,'strict':True}
        data=await self.request('/chat/completions',body)
        try:
            choice=data['choices'][0]
            if choice.get('finish_reason') not in ('stop',None): raise ValueError('Incomplete response')
            content=choice['message']['content'].strip()
            if len(content)>40000: raise ValueError('Too large')
            if content.startswith('```') and content.endswith('```'):
                content=content.split('\n',1)[1].rsplit('```',1)[0].strip()
            result=json.loads(content)
            if not isinstance(result,dict): raise ValueError('Not an object')
            return result
        except (KeyError,IndexError,TypeError,ValueError,AttributeError) as exc:
            raise GigaChatError('GigaChat вернул неполный или некорректный черновик. Повторите генерацию.') from exc
