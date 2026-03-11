import urllib.request
try:
    req = urllib.request.Request("http://127.0.0.1:8000/api/dashboard/benchmark/llm?tier=fast", method="POST")
    with urllib.request.urlopen(req) as response:
        print(response.read().decode())
except Exception as e:
    print(e)
