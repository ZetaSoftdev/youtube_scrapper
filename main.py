"""
main.py — FastAPI application.
All API routes + PubSubHubbub webhook handler.
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

import database as db
import youtube
import notebooklm
from scheduler import start_scheduler, _callback_url, _push_new_video

# ─── App Lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    start_scheduler()
    yield

app = FastAPI(title="YouTube Intelligence Feed", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ─── Frontend ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse("static/index.html")


# ─── Health / Status ──────────────────────────────────────────────────────────

@app.get("/api/status")
async def status():
    nlm_ok = await notebooklm.is_nlm_available()
    return {
        "status": "ok",
        "nlm_available": nlm_ok,
        "server_url": os.getenv("SERVER_URL", "not set"),
    }


# ─── Topics ──────────────────────────────────────────────────────────────────

class TopicCreate(BaseModel):
    name: str
    description: Optional[str] = ""


@app.get("/api/topics")
async def list_topics():
    return db.get_topics()


@app.post("/api/topics", status_code=201)
async def create_topic(body: TopicCreate):
    topic = db.create_topic(body.name, body.description or "")

    # Create a linked NotebookLM notebook
    notebook_id = await notebooklm.create_notebook(body.name)
    if notebook_id:
        db.update_topic_notebook(topic["id"], notebook_id, notebook_id)
        topic["notebook_id"] = notebook_id

    return topic


@app.delete("/api/topics/{topic_id}", status_code=204)
async def delete_topic(topic_id: int):
    topic = db.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    db.delete_topic(topic_id)
    return Response(status_code=204)


# ─── Channel Search & Discovery ───────────────────────────────────────────────

@app.get("/api/channels/search")
async def search_channels(
    q: str,
    min_subscribers: int = 0,
    max_results: int = 10,
):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    try:
        results = await youtube.search_channels(q.strip(), max_results, min_subscribers)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"YouTube API error: {str(e)}")
    return results


@app.get("/api/channels/resolve")
async def resolve_channel_url(url: str):
    """Resolve a YouTube channel URL to channel data."""
    result = await youtube.get_channel_by_url(url.strip())
    if not result:
        raise HTTPException(status_code=404, detail="Channel not found")
    return result


@app.get("/api/channels/suggest")
async def suggest_channels(channel_id: str, topic_id: int):
    """Suggest similar channels after adding one."""
    existing = db.get_channels(topic_id)
    existing_ids = [c["channel_id"] for c in existing]
    suggestions = await youtube.suggest_similar_channels(channel_id, existing_ids)
    return suggestions


# ─── Channel Management ───────────────────────────────────────────────────────

class ChannelAdd(BaseModel):
    topic_id: int
    channel_id: str
    channel_name: str
    thumbnail_url: Optional[str] = ""
    subscriber_count: Optional[int] = 0
    video_fetch_count: int = 10
    sort_by: str = "date"  # "date" or "viewCount"


@app.get("/api/topics/{topic_id}/channels")
async def list_channels(topic_id: int):
    return db.get_channels(topic_id)


@app.post("/api/channels", status_code=201)
async def add_channel(body: ChannelAdd):
    topic = db.get_topic(body.topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    # Add to DB
    channel = db.add_channel(
        topic_id=body.topic_id,
        channel_id=body.channel_id,
        channel_name=body.channel_name,
        thumbnail_url=body.thumbnail_url or "",
        subscriber_count=body.subscriber_count or 0,
        video_fetch_count=body.video_fetch_count,
        sort_by=body.sort_by,
    )

    # Fetch initial videos and push to NotebookLM
    if topic.get("notebook_id"):
        videos = await youtube.fetch_videos(body.channel_id, body.video_fetch_count, body.sort_by)
        pushed = 0
        for v in videos:
            if not db.video_exists(v["video_id"]):
                saved = db.save_video(channel["id"], v["video_id"], v["title"], "manual")
                if saved:
                    ok = await notebooklm.add_source(topic["notebook_id"], v["video_url"])
                    if ok:
                        db.mark_video_pushed(v["video_id"])
                        pushed += 1
        channel["videos_pushed"] = pushed

    # Subscribe to PubSubHubbub for real-time tracking
    callback = _callback_url()
    if callback and "your-server" not in callback:
        ok = await youtube.subscribe_to_channel(body.channel_id, callback)
        db.update_webhook_status(channel["id"], ok)
        channel["webhook_subscribed"] = ok

    return channel


@app.delete("/api/channels/{channel_db_id}", status_code=204)
async def remove_channel(channel_db_id: int):
    channels = db.get_all_tracked_channels()
    channel = next((c for c in channels if c["id"] == channel_db_id), None)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Unsubscribe from webhook
    callback = _callback_url()
    if callback:
        await youtube.unsubscribe_from_channel(channel["channel_id"], callback)

    db.delete_channel(channel_db_id)
    return Response(status_code=204)


# ─── Manual Fetch ─────────────────────────────────────────────────────────────

class FetchRequest(BaseModel):
    count: int = 10
    sort_by: str = "date"


@app.post("/api/channels/{channel_db_id}/fetch")
async def manual_fetch(channel_db_id: int, body: FetchRequest):
    """Manually trigger a video fetch for a channel and push to NotebookLM."""
    channels = db.get_all_tracked_channels()
    channel = next((c for c in channels if c["id"] == channel_db_id), None)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    videos = await youtube.fetch_videos(channel["channel_id"], body.count, body.sort_by)
    pushed = 0
    skipped = 0

    for v in videos:
        if db.video_exists(v["video_id"]):
            skipped += 1
            continue
        saved = db.save_video(channel["id"], v["video_id"], v["title"], "manual")
        if saved and channel.get("notebook_id"):
            ok = await notebooklm.add_source(channel["notebook_id"], v["video_url"])
            if ok:
                db.mark_video_pushed(v["video_id"])
                pushed += 1

    return {"pushed": pushed, "skipped": skipped, "total": len(videos)}


# ─── Activity Log ─────────────────────────────────────────────────────────────

@app.get("/api/activity")
async def activity_log(limit: int = 100):
    return db.get_activity_log(limit)


@app.get("/api/videos")
async def recent_videos(limit: int = 50):
    return db.get_recent_videos(limit)


# ─── Temporary Secure Credential Upload Route ─────────────────────────────────
import shutil

@app.post("/temp-upload-credentials")
async def temp_upload_credentials(
    cookies: UploadFile = File(...),
    metadata: UploadFile = File(...),
    token: str = None
):
    if token != "azeem_secret_upload_token_2026_xyz":
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    target_dir = os.path.expanduser("~/.notebooklm-mcp-cli/profiles/default")
    os.makedirs(target_dir, exist_ok=True)
    
    cookies_path = os.path.join(target_dir, "cookies.json")
    metadata_path = os.path.join(target_dir, "metadata.json")
    
    with open(cookies_path, "wb") as buffer:
        shutil.copyfileobj(cookies.file, buffer)
        
    with open(metadata_path, "wb") as buffer:
        shutil.copyfileobj(metadata.file, buffer)
        
    return {"status": "success", "message": "Credentials uploaded successfully"}


# ─── PubSubHubbub Webhook ─────────────────────────────────────────────────────

@app.get("/webhook/youtube")
async def webhook_verify(
    hub_mode: Optional[str] = None,
    hub_challenge: Optional[str] = None,
    hub_topic: Optional[str] = None,
    hub_lease_seconds: Optional[int] = None,
):
    """
    YouTube's hub verifies our server by sending a GET with a challenge.
    We must echo the challenge back to confirm the subscription.
    """
    if hub_mode == "subscribe" and hub_challenge:
        # Update webhook status in DB based on the topic URL
        if hub_topic and "channel_id=" in hub_topic:
            yt_channel_id = hub_topic.split("channel_id=")[-1]
            channel = db.get_channel_by_yt_id(yt_channel_id)
            if channel:
                db.update_webhook_status(channel["id"], True)
        return Response(content=hub_challenge, media_type="text/plain")

    return Response(status_code=200)


@app.post("/webhook/youtube")
async def webhook_receive(request: Request):
    """
    Receive new video notification from YouTube's PubSubHubbub hub.
    Parses the Atom XML payload, extracts video ID, pushes to NotebookLM.
    """
    body = await request.body()
    parsed = youtube.parse_webhook_payload(body)

    if not parsed:
        # Not a parseable video notification — ignore silently
        return Response(status_code=200)

    yt_channel_id = parsed["channel_id"]
    video_id = parsed["video_id"]
    title = parsed["title"]

    channel = db.get_channel_by_yt_id(yt_channel_id)
    if not channel:
        # Notification for a channel we don't track — ignore
        return Response(status_code=200)

    # Push to NotebookLM in background (don't block the webhook response)
    import asyncio
    asyncio.create_task(_push_new_video(channel, video_id, title, via="webhook"))

    return Response(status_code=200)
