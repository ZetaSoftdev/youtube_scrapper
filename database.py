"""
database.py — SQLite setup and all DB operations.
Single source of truth for all data persistence.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = "data.db"


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables if they don't exist."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                notebook_id TEXT DEFAULT '',
                notebook_url TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL,
                channel_id TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                thumbnail_url TEXT DEFAULT '',
                subscriber_count INTEGER DEFAULT 0,
                video_fetch_count INTEGER DEFAULT 10,
                sort_by TEXT DEFAULT 'date',
                webhook_subscribed INTEGER DEFAULT 0,
                last_checked TEXT DEFAULT '',
                added_at TEXT NOT NULL,
                FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE,
                UNIQUE(topic_id, channel_id)
            );

            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                video_id TEXT NOT NULL UNIQUE,
                video_url TEXT NOT NULL,
                title TEXT DEFAULT '',
                pushed_to_nlm INTEGER DEFAULT 0,
                pushed_at TEXT DEFAULT '',
                detected_via TEXT DEFAULT 'manual',
                created_at TEXT NOT NULL,
                FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER,
                channel_name TEXT DEFAULT '',
                video_title TEXT DEFAULT '',
                video_url TEXT DEFAULT '',
                status TEXT DEFAULT 'success',
                message TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
        """)


# ─── Topics ─────────────────────────────────────────────────────────────────

def create_topic(name: str, description: str = "") -> dict:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO topics (name, description, created_at) VALUES (?, ?, ?)",
            (name, description, datetime.utcnow().isoformat())
        )
        row = conn.execute("SELECT * FROM topics WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


def update_topic_notebook(topic_id: int, notebook_id: str, notebook_url: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE topics SET notebook_id = ?, notebook_url = ? WHERE id = ?",
            (notebook_id, notebook_url, topic_id)
        )


def get_topics() -> list:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT t.*, COUNT(c.id) as channel_count
            FROM topics t
            LEFT JOIN channels c ON c.topic_id = t.id
            GROUP BY t.id
            ORDER BY t.created_at DESC
            """).fetchall()
        return [dict(r) for r in rows]


def get_topic(topic_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
        return dict(row) if row else None


def delete_topic(topic_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))


# ─── Channels ────────────────────────────────────────────────────────────────

def add_channel(topic_id: int, channel_id: str, channel_name: str,
                thumbnail_url: str, subscriber_count: int,
                video_fetch_count: int, sort_by: str) -> dict:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO channels
               (topic_id, channel_id, channel_name, thumbnail_url, subscriber_count,
                video_fetch_count, sort_by, added_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (topic_id, channel_id, channel_name, thumbnail_url, subscriber_count,
             video_fetch_count, sort_by, datetime.utcnow().isoformat())
        )
        row = conn.execute("SELECT * FROM channels WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


def get_channels(topic_id: int) -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM channels WHERE topic_id = ? ORDER BY added_at DESC",
            (topic_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_tracked_channels() -> list:
    """Used by the RSS fallback poller — returns every channel across all topics."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT c.*, t.notebook_id, t.name as topic_name
               FROM channels c
               JOIN topics t ON t.id = c.topic_id""").fetchall()
        return [dict(r) for r in rows]


def get_channel_by_yt_id(yt_channel_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT c.*, t.notebook_id FROM channels c JOIN topics t ON t.id = c.topic_id WHERE c.channel_id = ?",
            (yt_channel_id,)
        ).fetchone()
        return dict(row) if row else None


def update_webhook_status(channel_db_id: int, subscribed: bool):
    with get_db() as conn:
        conn.execute(
            "UPDATE channels SET webhook_subscribed = ? WHERE id = ?",
            (1 if subscribed else 0, channel_db_id)
        )


def update_last_checked(channel_db_id: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE channels SET last_checked = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), channel_db_id)
        )


def delete_channel(channel_db_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM channels WHERE id = ?", (channel_db_id,))


# ─── Videos ──────────────────────────────────────────────────────────────────

def video_exists(video_id: str) -> bool:
    with get_db() as conn:
        row = conn.execute("SELECT id FROM videos WHERE video_id = ?", (video_id,)).fetchone()
        return row is not None


def save_video(channel_db_id: int, video_id: str, title: str, detected_via: str) -> dict:
    url = f"https://www.youtube.com/watch?v={video_id}"
    with get_db() as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO videos
               (channel_id, video_id, video_url, title, detected_via, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (channel_db_id, video_id, url, title, detected_via, datetime.utcnow().isoformat())
        )
        if cur.lastrowid:
            row = conn.execute("SELECT * FROM videos WHERE id = ?", (cur.lastrowid,)).fetchone()
            return dict(row)
    return {}


def mark_video_pushed(video_id: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE videos SET pushed_to_nlm = 1, pushed_at = ? WHERE video_id = ?",
            (datetime.utcnow().isoformat(), video_id)
        )


def get_recent_videos(limit: int = 50) -> list:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT v.*, c.channel_name, t.name as topic_name
               FROM videos v
               JOIN channels c ON c.id = v.channel_id
               JOIN topics t ON t.id = c.topic_id
               ORDER BY v.created_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_channel_videos(channel_db_id: int) -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM videos WHERE channel_id = ? ORDER BY created_at DESC",
            (channel_db_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ─── Activity Log ────────────────────────────────────────────────────────────

def log_activity(topic_id: int, channel_name: str, video_title: str,
                 video_url: str, status: str, message: str = ""):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO activity_log
               (topic_id, channel_name, video_title, video_url, status, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (topic_id, channel_name, video_title, video_url, status, message,
             datetime.utcnow().isoformat())
        )


def get_activity_log(limit: int = 100) -> list:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT a.*, t.name as topic_name
               FROM activity_log a
               LEFT JOIN topics t ON t.id = a.topic_id
               ORDER BY a.created_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
