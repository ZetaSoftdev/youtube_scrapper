import re

with open("database_async.py", "r") as f:
    content = f.read()

# Add get_channel_by_id
new_func = """
async def get_channel_by_id(channel_db_id: int) -> dict | None:
    def _inner():
        with get_db() as conn:
            row = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_db_id,)).fetchone()
            return dict(row) if row else None
    return await run_in_threadpool(_inner)
"""
content = content.replace("async def get_channels", new_func + "\nasync def get_channels")

# Add try/except for IntegrityError in save_video
# Find save_video
save_video_str = """async def save_video(channel_db_id: int, video_id: str, title: str, detected_via: str) -> dict:
    def _inner():
        url = f"https://www.youtube.com/watch?v={video_id}"
        with get_db() as conn:
            try:
                cur = conn.execute(
                    \"\"\"INSERT INTO videos
                       (channel_id, video_id, video_url, title, detected_via, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)\"\"\",
                    (channel_db_id, video_id, url, title, detected_via, datetime.utcnow().isoformat())
                )
                if cur.lastrowid:
                    row = conn.execute("SELECT * FROM videos WHERE id = ?", (cur.lastrowid,)).fetchone()
                    return dict(row)
            except sqlite3.IntegrityError:
                pass
        return {}
    return await run_in_threadpool(_inner)
"""

# Replace old save_video with the new one
old_save_video_regex = r"async def save_video\(.*?\).*?return await run_in_threadpool\(_inner\)\n"
content = re.sub(old_save_video_regex, save_video_str, content, flags=re.DOTALL)

# Add try/except for add_channel too
add_channel_str = """async def add_channel(topic_id: int, channel_id: str, channel_name: str,
                thumbnail_url: str, subscriber_count: int,
                video_fetch_count: int, sort_by: str) -> dict:
    def _inner():
        with get_db() as conn:
            try:
                cur = conn.execute(
                    \"\"\"INSERT INTO channels
                       (topic_id, channel_id, channel_name, thumbnail_url, subscriber_count,
                        video_fetch_count, sort_by, added_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)\"\"\",
                    (topic_id, channel_id, channel_name, thumbnail_url, subscriber_count,
                     video_fetch_count, sort_by, datetime.utcnow().isoformat())
                )
                row = conn.execute("SELECT * FROM channels WHERE id = ?", (cur.lastrowid,)).fetchone()
                return dict(row)
            except sqlite3.IntegrityError:
                return {}
    return await run_in_threadpool(_inner)
"""
old_add_channel_regex = r"async def add_channel\(.*?\).*?return await run_in_threadpool\(_inner\)\n"
content = re.sub(old_add_channel_regex, add_channel_str, content, flags=re.DOTALL)

with open("database_async.py", "w") as f:
    f.write(content)
