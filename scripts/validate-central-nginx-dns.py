#!/usr/bin/env python3
from pathlib import Path

conf = Path('infrastructure/nginx/default.conf').read_text(encoding='utf-8')
required = (
    'resolver 127.0.0.11',
    'set $ithute_auth_upstream http://ithute-auth:8080;',
    'proxy_pass $ithute_auth_upstream;',
    'set $ithute_push_upstream http://ithute-push:8080;',
    'proxy_pass $ithute_push_upstream;',
    'set $ithute_realtime_upstream http://ithute-realtime:8080;',
)
for value in required:
    if value not in conf:
        raise SystemExit(f'missing central Nginx routing contract: {value}')
if conf.count('proxy_pass $ithute_realtime_upstream;') != 2:
    raise SystemExit('Realtime HTTP and WebSocket routes must both use the dynamic upstream')
for service in ('auth', 'push', 'realtime'):
    static = f'proxy_pass http://ithute-{service}:'
    if static in conf:
        raise SystemExit(f'static central Docker upstream is forbidden: {static}')
print('Central Nginx Docker DNS routing contract passed.')
