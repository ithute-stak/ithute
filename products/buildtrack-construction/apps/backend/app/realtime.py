from collections import defaultdict
from fastapi import WebSocket
class Hub:
 def __init__(self):self.clients=defaultdict(set)
 async def connect(self,c,w):await w.accept();self.clients[c].add(w)
 def leave(self,c,w):self.clients[c].discard(w)
 async def send(self,c,e):
  for w in tuple(self.clients[c]):
   try:await w.send_json(e)
   except Exception:self.leave(c,w)
hub=Hub()
