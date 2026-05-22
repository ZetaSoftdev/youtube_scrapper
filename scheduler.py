"""
scheduler.py — Background jobs using APScheduler.
- Renews PubSubHubbub subscriptions every 9 days (they expire after 10)
- RSS fallback polling every 6 hours (catches anything webhook missed)
"""

import os
import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

import database as db
import youtube
import notebooklm

scheduler = AsyncIOScheduler(timezone="UTC")


def _callback_url() -> str:
    server_url = os.getenv("SERVER_URL", "").rstrip("/")
    return f"{server_url}/webhook/youtube"


async def _push_new_video(channel: dict, video_id: str, title: str, via: str):
    """Save video to DB and push to NotebookLM if not already pushed."""
    if db.video_exists(video_id):
        return

    video = db.save_video(channel["id"], video_id, title, detected_via=via)
    if not video:
        return

    url = f"https://www.youtube.com/watch?v={video_id}"
    notebook_id = channel.get("notebook_id", "")

    if notebook_id:
        success = await notebooklm.add_source(notebook_id, url)
        if success:
            db.mark_video_pushed(video_id)
            db.log_activity(
                topic_id=channel["topic_id"],
                channel_name=channel["channel_name"],
                video_title=title,
                video_url=url,
                status="success",
                message=f"Auto-added via {via}"
            )
        else:
            db.log_activity(
                topic_id=channel["topic_id"],
                channel_name=channel["channel_name"],
                video_title=title,
                video_url=url,
                status="error",
                message="Failed to add to NotebookLM"
            )


async def rss_fallback_poll():
    """
    Poll all tracked channels via RSS every 6 hours.
    This is the safety net — catches any videos the webhook may have missed.
    """
    print(f"[Scheduler] RSS fallback poll started at {datetime.utcnow().isoformat()}")
    channels = db.get_all_tracked_channels()

    for channel in channels:
        try:
            rss_videos = await youtube.fetch_rss_videos(channel["channel_id"])
            for v in rss_videos:
                await _push_new_video(channel, v["video_id"], v["title"], via="rss")
            db.update_last_checked(channel["id"])
        except Exception as e:
            print(f"[Scheduler] RSS poll error for {channel['channel_name']}: {e}")

    print(f"[Scheduler] RSS fallback poll done — {len(channels)} channels checked")


async def renew_webhooks():
    """
    Re-subscribe to PubSubHubbub for all tracked channels every 9 days.
    PubSubHubbub subscriptions expire after 10 days, so we renew at day 9.
    """
    print(f"[Scheduler] Renewing PubSubHubbub subscriptions...")
    callback = _callback_url()
    channels = db.get_all_tracked_channels()

    for channel in channels:
        try:
            ok = await youtube.subscribe_to_channel(channel["channel_id"], callback)
            if ok:
                db.update_webhook_status(channel["id"], True)
        except Exception as e:
            print(f"[Scheduler] Webhook renewal error for {channel['channel_name']}: {e}")

    print(f"[Scheduler] Webhook renewal done — {len(channels)} channels")


def start_scheduler():
    """Register and start all background jobs."""

    # RSS fallback: runs every 6 hours
    scheduler.add_job(
        rss_fallback_poll,
        trigger=IntervalTrigger(hours=6),
        id="rss_fallback",
        replace_existing=True,
        name="RSS Fallback Poller",
    )

    # Webhook renewal: runs every 9 days
    scheduler.add_job(
        renew_webhooks,
        trigger=IntervalTrigger(days=9),
        id="webhook_renewal",
        replace_existing=True,
        name="Webhook Renewal",
    )

    scheduler.start()
    print("[Scheduler] Background jobs started")
