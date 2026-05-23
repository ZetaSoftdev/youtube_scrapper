import requests
import json
import sys

BASE_URL = "http://2.24.195.66/nlm-yt-feed"

def test(name, req):
    print(f"\n--- Testing: {name} ---")
    try:
        resp = req()
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text[:500]}")
    except Exception as e:
        print(f"Exception: {e}")

# 1. Test unhandled exceptions (e.g. invalid URL for resolve)
test("Resolve invalid URL", lambda: requests.get(f"{BASE_URL}/api/channels/resolve?url=invalid_url_format"))

# 2. Test topic creation without name (Validation Error)
test("Create topic missing name", lambda: requests.post(f"{BASE_URL}/api/topics", json={"description": "Missing name field"}))

# 3. Test empty topic name
test("Create topic empty name", lambda: requests.post(f"{BASE_URL}/api/topics", json={"name": ""}))

# 4. Create a valid topic
resp = requests.post(f"{BASE_URL}/api/topics", json={"name": "QA Test Topic", "description": "QA test description"})
topic_id = None
if resp.status_code == 201:
    topic_id = resp.json().get("id")

if topic_id:
    # 5. Add channel with missing required fields
    test("Add channel missing channel_name", lambda: requests.post(f"{BASE_URL}/api/channels", json={
        "topic_id": topic_id,
        "channel_id": "UC_x5XG1OV2P6uZZ5FSM9Ttw"
    }))

    # 6. Add channel with invalid topic ID
    test("Add channel invalid topic_id", lambda: requests.post(f"{BASE_URL}/api/channels", json={
        "topic_id": 9999999,
        "channel_id": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
        "channel_name": "Google Developers"
    }))

    # 7. Add duplicate channel
    resp_channel = requests.post(f"{BASE_URL}/api/channels", json={
        "topic_id": topic_id,
        "channel_id": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
        "channel_name": "Google Developers"
    })
    
    test("Add duplicate channel", lambda: requests.post(f"{BASE_URL}/api/channels", json={
        "topic_id": topic_id,
        "channel_id": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
        "channel_name": "Google Developers"
    }))

    # 8. Unhandled exceptions in youtube.py via manual fetch
    channel_db_id = resp_channel.json().get("id") if resp_channel.status_code == 201 else None
    if channel_db_id:
        test("Manual fetch with invalid count type", lambda: requests.post(f"{BASE_URL}/api/channels/{channel_db_id}/fetch", json={"count": "invalid"}))
        
    # Clean up
    requests.delete(f"{BASE_URL}/api/topics/{topic_id}")
    
# 9. Search channels with empty query
test("Search empty query", lambda: requests.get(f"{BASE_URL}/api/channels/search?q="))

# 10. Search channels with extreme pagination/results
test("Search extreme max_results", lambda: requests.get(f"{BASE_URL}/api/channels/search?q=tech&max_results=1000000"))

# 11. SQL injection attempts
test("Topic SQL Injection", lambda: requests.post(f"{BASE_URL}/api/topics", json={"name": "'); DROP TABLE topics;--"}))

