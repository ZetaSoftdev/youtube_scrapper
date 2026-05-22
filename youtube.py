"""
youtube.py — All YouTube Data API v3 interactions.
Handles: channel search, video fetching, PubSubHubbub webhook subscription.
"""

import os
import httpx
import xml.etree.ElementTree as ET
from typing import Optional

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
PUBSUBHUBBUB_HUB = "https://pubsubhubbub.appspot.com/subscribe"


def _api_key() -> str:
    key = os.getenv("YOUTUBE_API_KEY", "")
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY not set in environment")
    return key


# ─── Channel Search ──────────────────────────────────────────────────────────

async def search_channels(query: str, max_results: int = 10,
                          min_subscribers: int = 0) -> list[dict]:
    """
    Search YouTube for channels matching a keyword query.
    Returns enriched channel data including subscriber count and reason for suggestion.
    Quota cost: 100 (search) + 1 (stats batch) = 101 units per call.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        # Step 1: Search for channel IDs
        search_resp = await client.get(f"{YOUTUBE_API_BASE}/search", params={
            "key": _api_key(),
            "part": "snippet",
            "type": "channel",
            "q": query,
            "maxResults": min(max_results * 2, 50),  # Fetch extra to filter by min_subscribers
            "relevanceLanguage": "en",
        })
        search_resp.raise_for_status()
        search_data = search_resp.json()

        if not search_data.get("items"):
            return []

        channel_ids = [item["snippet"]["channelId"] for item in search_data["items"]]

        # Step 2: Batch fetch stats (subscriber count, view count) — 1 unit per call
        stats_resp = await client.get(f"{YOUTUBE_API_BASE}/channels", params={
            "key": _api_key(),
            "part": "snippet,statistics,brandingSettings",
            "id": ",".join(channel_ids),
        })
        stats_resp.raise_for_status()
        stats_data = stats_resp.json()

    # Build enriched channel list
    channels = []
    for item in stats_data.get("items", []):
        stats = item.get("statistics", {})
        snippet = item.get("snippet", {})
        sub_count = int(stats.get("subscriberCount", 0))

        if sub_count < min_subscribers:
            continue

        # Generate "why suggested" reasoning
        reasons = []
        if sub_count >= 1_000_000:
            reasons.append(f"{sub_count // 1_000_000}M subscribers — highly established")
        elif sub_count >= 100_000:
            reasons.append(f"{sub_count // 1_000}K subscribers — strong following")
        elif sub_count >= 10_000:
            reasons.append(f"{sub_count // 1_000}K subscribers — growing channel")

        view_count = int(stats.get("viewCount", 0))
        if view_count >= 10_000_000:
            reasons.append("high total viewership")

        reasons.append(f"matched keyword '{query}'")

        channels.append({
            "channel_id": item["id"],
            "channel_name": snippet.get("title", ""),
            "description": snippet.get("description", "")[:200],
            "thumbnail_url": snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
            "subscriber_count": sub_count,
            "view_count": view_count,
            "video_count": int(stats.get("videoCount", 0)),
            "country": snippet.get("country", ""),
            "why_suggested": " · ".join(reasons) if reasons else f"Matched keyword '{query}'",
            "channel_url": f"https://www.youtube.com/channel/{item['id']}",
        })

    # Sort by subscriber count descending
    channels.sort(key=lambda x: x["subscriber_count"], reverse=True)
    return channels[:max_results]


async def get_channel_by_url(channel_url: str) -> Optional[dict]:
    """
    Resolve a channel URL (handle, custom URL, or /channel/ format) to channel data.
    Handles: youtube.com/@handle, youtube.com/c/name, youtube.com/channel/ID
    """
    channel_id = None

    # Direct channel ID
    if "/channel/" in channel_url:
        channel_id = channel_url.split("/channel/")[-1].strip("/").split("?")[0]
    elif "/@" in channel_url:
        handle = channel_url.split("/@")[-1].strip("/").split("?")[0]
        channel_id = await _resolve_handle(handle)
    elif "/c/" in channel_url or "/user/" in channel_url:
        # Try searching by the custom name
        part = channel_url.split("/c/")[-1] if "/c/" in channel_url else channel_url.split("/user/")[-1]
        name = part.strip("/").split("?")[0]
        channel_id = await _resolve_handle(name)

    if not channel_id:
        return None

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{YOUTUBE_API_BASE}/channels", params={
            "key": _api_key(),
            "part": "snippet,statistics",
            "id": channel_id,
        })
        resp.raise_for_status()
        data = resp.json()

    if not data.get("items"):
        return None

    item = data["items"][0]
    stats = item.get("statistics", {})
    snippet = item.get("snippet", {})

    return {
        "channel_id": item["id"],
        "channel_name": snippet.get("title", ""),
        "description": snippet.get("description", "")[:200],
        "thumbnail_url": snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
        "subscriber_count": int(stats.get("subscriberCount", 0)),
        "view_count": int(stats.get("viewCount", 0)),
        "video_count": int(stats.get("videoCount", 0)),
        "country": snippet.get("country", ""),
        "why_suggested": "Added manually by URL",
        "channel_url": f"https://www.youtube.com/channel/{item['id']}",
    }


async def _resolve_handle(handle: str) -> Optional[str]:
    """Resolve a YouTube handle or username to a channel ID."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{YOUTUBE_API_BASE}/channels", params={
            "key": _api_key(),
            "part": "id",
            "forHandle": handle,
        })
        resp.raise_for_status()
        data = resp.json()
        if data.get("items"):
            return data["items"][0]["id"]
    return None


async def suggest_similar_channels(channel_id: str, existing_ids: list[str]) -> list[dict]:
    """
    Suggest channels similar to the given one using the channel's topic keywords.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        # Get the channel's topic categories to use as search seeds
        resp = await client.get(f"{YOUTUBE_API_BASE}/channels", params={
            "key": _api_key(),
            "part": "snippet,topicDetails",
            "id": channel_id,
        })
        resp.raise_for_status()
        data = resp.json()

    if not data.get("items"):
        return []

    item = data["items"][0]
    channel_name = item["snippet"]["title"]
    description = item["snippet"].get("description", "")

    # Use channel name as seed query for similarity
    seed_query = channel_name.split(" ")[0] if channel_name else "business"
    suggestions = await search_channels(seed_query, max_results=8)

    # Filter out channels already added
    return [c for c in suggestions if c["channel_id"] not in existing_ids + [channel_id]][:5]


# ─── Video Fetching ──────────────────────────────────────────────────────────

async def fetch_videos(channel_id: str, count: int = 10,
                       sort_by: str = "date") -> list[dict]:
    """
    Fetch the latest or most popular videos from a channel.
    sort_by: 'date' (recently uploaded) or 'viewCount' (most popular)
    Quota cost: ~3 units per call.
    """
    order = "date" if sort_by == "date" else "viewCount"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{YOUTUBE_API_BASE}/search", params={
            "key": _api_key(),
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "order": order,
            "maxResults": min(count, 50),
        })
        resp.raise_for_status()
        data = resp.json()

    videos = []
    for item in data.get("items", []):
        vid_id = item.get("id", {}).get("videoId")
        if not vid_id:
            continue
        videos.append({
            "video_id": vid_id,
            "title": item["snippet"].get("title", ""),
            "published_at": item["snippet"].get("publishedAt", ""),
            "thumbnail": item["snippet"].get("thumbnails", {}).get("medium", {}).get("url", ""),
            "video_url": f"https://www.youtube.com/watch?v={vid_id}",
        })

    return videos


# ─── PubSubHubbub Webhook Management ────────────────────────────────────────

async def subscribe_to_channel(channel_id: str, callback_url: str) -> bool:
    """
    Subscribe to YouTube's PubSubHubbub hub for real-time new video notifications.
    Subscription lasts ~10 days — scheduler auto-renews it.
    """
    topic_url = f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(PUBSUBHUBBUB_HUB, data={
            "hub.mode": "subscribe",
            "hub.topic": topic_url,
            "hub.callback": callback_url,
            "hub.verify": "async",  # YouTube verifies asynchronously
        })
        # 202 Accepted = subscription request received (YouTube will verify async)
        return resp.status_code in (200, 202, 204)


async def unsubscribe_from_channel(channel_id: str, callback_url: str) -> bool:
    """Unsubscribe from PubSubHubbub when a channel is removed."""
    topic_url = f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(PUBSUBHUBBUB_HUB, data={
            "hub.mode": "unsubscribe",
            "hub.topic": topic_url,
            "hub.callback": callback_url,
            "hub.verify": "async",
        })
        return resp.status_code in (200, 202, 204)


def parse_webhook_payload(xml_body: bytes) -> Optional[dict]:
    """
    Parse the Atom XML payload YouTube sends when a new video is uploaded.
    Returns {channel_id, video_id, title} or None if unparseable.
    """
    try:
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
        }
        root = ET.fromstring(xml_body)
        entry = root.find("atom:entry", ns)
        if entry is None:
            return None

        video_id_el = entry.find("yt:videoId", ns)
        channel_id_el = entry.find("yt:channelId", ns)
        title_el = entry.find("atom:title", ns)

        if video_id_el is None or channel_id_el is None:
            return None

        return {
            "video_id": video_id_el.text,
            "channel_id": channel_id_el.text,
            "title": title_el.text if title_el is not None else "",
        }
    except ET.ParseError:
        return None


# ─── RSS Fallback Polling ────────────────────────────────────────────────────

async def fetch_rss_videos(channel_id: str) -> list[dict]:
    """
    Fetch the latest videos via YouTube's RSS feed.
    No API quota cost. Returns up to 15 most recent videos.
    Used as fallback when webhook misses something.
    """
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(rss_url, follow_redirects=True)
            resp.raise_for_status()
        except Exception:
            return []

    videos = []
    try:
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
            "media": "http://search.yahoo.com/mrss/",
        }
        root = ET.fromstring(resp.content)
        for entry in root.findall("atom:entry", ns):
            vid_id_el = entry.find("yt:videoId", ns)
            title_el = entry.find("atom:title", ns)
            if vid_id_el is None:
                continue
            videos.append({
                "video_id": vid_id_el.text,
                "title": title_el.text if title_el is not None else "",
            })
    except ET.ParseError:
        pass

    return videos
