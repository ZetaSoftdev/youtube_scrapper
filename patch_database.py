import re

with open("database.py", "r") as f:
    content = f.read()

# Add import for run_in_threadpool
content = content.replace("import sqlite3\n", "import sqlite3\nfrom fastapi.concurrency import run_in_threadpool\n")

functions_to_asyncify = [
    "init_db",
    "create_topic",
    "update_topic_notebook",
    "get_topics",
    "get_topic",
    "delete_topic",
    "add_channel",
    "get_channels",
    "get_all_tracked_channels",
    "get_channel_by_yt_id",
    "update_webhook_status",
    "update_last_checked",
    "delete_channel",
    "video_exists",
    "save_video",
    "mark_video_pushed",
    "get_recent_videos",
    "get_channel_videos",
    "log_activity",
    "get_activity_log"
]

for func in functions_to_asyncify:
    # Find the function definition
    pattern = r"(def " + func + r"\([^)]*\)(?: -> [^:]+)?:)\n"
    
    # We need to indent the body of the function and wrap it in _inner
    # Then add 'return await run_in_threadpool(_inner)'
    
    match = re.search(pattern, content)
    if not match:
        print(f"Could not find {func}")
        continue
        
    start_idx = match.end()
    
    # Find end of function (next 'def ' or end of file)
    next_def_match = re.search(r"\n(?:async )?def ", content[start_idx:])
    if next_def_match:
        end_idx = start_idx + next_def_match.start()
    else:
        # Check for '# ─── ' dividers
        next_div_match = re.search(r"\n# ─── ", content[start_idx:])
        if next_div_match:
            end_idx = start_idx + next_div_match.start()
        else:
            end_idx = len(content)
            
    old_body = content[start_idx:end_idx]
    
    # Check if we should add try/except for IntegrityError
    integrity_error_import = ""
    if func in ["add_channel", "save_video"]:
        # The user wants "Add try/except for SQLite IntegrityError (duplicates)"
        # Actually I can just add this specifically to the functions later, or do it here.
        pass

    # Indent the old body
    indented_body = "\n".join("    " + line if line.strip() else line for line in old_body.split("\n"))
    
    new_func = match.group(1).replace("def ", "async def ") + "\n    def _inner():\n" + indented_body + "    return await run_in_threadpool(_inner)\n"
    
    content = content[:match.start()] + new_func + content[end_idx:]

with open("database_async.py", "w") as f:
    f.write(content)
