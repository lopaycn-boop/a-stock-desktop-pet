import requests
r = requests.get('http://127.0.0.1:8000/version', timeout=3)
d = r.json()
v = d.get('version', '?')
f = len(d.get('features', []))
print(f'Backend: v{v} features={f} status=OK')