import urllib.request
import urllib.error

base_url = "http://2.24.195.66/nlm-yt-feed/"
assets = [
    "",
    "static/app.js",
    "static/style.css",
    "static/index.html"
]

print("Testing live assets on http://2.24.195.66/nlm-yt-feed/ ...\n")
for asset in assets:
    url = base_url + asset
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            print(f"[OK] {response.getcode()} - {url}")
            headers = response.info()
            print(f"     Content-Type: {headers.get('Content-Type')}")
            print(f"     Server: {headers.get('Server')}")
    except urllib.error.URLError as e:
        if hasattr(e, 'code'):
            print(f"[FAIL] {e.code} - {url}")
            print(f"       Reason: {e.reason}")
        else:
            print(f"[ERROR] {e.reason} - {url}")
