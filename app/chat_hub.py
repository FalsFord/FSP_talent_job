import asyncio
import json
from collections import defaultdict
from redis.asyncio import Redis

class ChatHub:
    def __init__(self):
        self.redis=None
        self.pubsub=None
        self.listener=None
        self.connections=defaultdict(dict)

    async def start(self,url):
        self.redis=Redis.from_url(url,decode_responses=True)
        await self.redis.ping()
        self.pubsub=self.redis.pubsub()
        await self.pubsub.psubscribe('endpoint:chat:offer:*')
        self.listener=asyncio.create_task(self._listen())

    async def close(self):
        if self.listener:
            self.listener.cancel()
            try: await self.listener
            except asyncio.CancelledError: pass
        if self.pubsub: await self.pubsub.aclose()
        if self.redis: await self.redis.aclose()

    async def connect(self,offer_id,websocket,user_id):
        self.connections[offer_id][websocket]=user_id

    def disconnect(self,offer_id,websocket):
        self.connections[offer_id].pop(websocket,None)
        if not self.connections[offer_id]: self.connections.pop(offer_id,None)

    async def publish(self,offer_id,payload):
        await self.redis.publish(f'endpoint:chat:offer:{offer_id}',json.dumps(payload,separators=(',',':')))

    async def _listen(self):
        async for event in self.pubsub.listen():
            if event.get('type')!='pmessage': continue
            try:
                offer_id=event['channel'].rsplit(':',1)[1]
                payload=json.loads(event['data'])
            except (ValueError,KeyError,TypeError,json.JSONDecodeError):
                continue
            sockets=tuple(self.connections.get(offer_id,{}).items())
            if sockets:
                packets=[]
                for _,user_id in sockets:
                    packet=dict(payload)
                    if isinstance(packet.get('message'),dict):
                        packet['message']={**packet['message'],'mine':packet['message'].get('sender_id')==user_id}
                    packets.append(packet)
                results=await asyncio.gather(*(ws.send_json(packet) for (ws,_),packet in zip(sockets,packets)),return_exceptions=True)
                for (ws,_),result in zip(sockets,results):
                    if isinstance(result,Exception): self.disconnect(offer_id,ws)

chat_hub=ChatHub()
