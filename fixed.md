# Thread-Safety Fixes — `app.py`

## Problem

Under concurrent Flask requests, SQLite immediately raised `database is locked` errors because:

- Every function called `sqlite3.connect()` with no timeout — threads failed instantly instead of waiting.
- Multiple threads could enter write paths simultaneously with no coordination.
- The background thumbnail worker used a plain `list` + `threading.Lock` that only guarded the `pop()`, not the overall write pipeline.
- `_scan_images()` called `update_or_create_image_record()` (a write) inline for every image on every API request, making lock contention proportional to gallery size.

---

## Fix 1 — `_get_conn()` helper + WAL mode

**What changed:** Replaced every bare `sqlite3.connect(DB_FILE)` call with a new `_get_conn()` helper.

```python
def _get_conn(timeout: float = 30) -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, timeout=timeout, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn
```

**Why it fixes the issue:**
- `timeout=30` — threads wait up to 30 seconds for a lock instead of raising immediately.
- `journal_mode=WAL` — Write-Ahead Logging allows unlimited concurrent readers while writers queue up safely. The default journal mode takes an exclusive lock on the entire file, which is what caused the collisions.
- `busy_timeout=30000` — sets the same 30-second wait at the SQLite C layer as a second line of defence.
- `check_same_thread=False` — required when a connection is used across threads (Flask worker pool).

---

## Fix 2 — `_db_write_lock` module-level write lock

**What changed:** Added a single `threading.Lock` that wraps every `INSERT` and `UPDATE` block.

```python
_db_write_lock = threading.Lock()
```

Used in `init_cache_db`, `update_or_create_image_record`, and `mark_thumbnail_created`:

```python
with _db_write_lock:
    conn = _get_conn()
    try:
        # ... INSERT / UPDATE ...
        conn.commit()
    finally:
        conn.close()
```

**Why it fixes the issue:** WAL mode serialises writers at the SQLite level, but there is still a window between a thread checking a row and writing it (check-then-act). The Python-level lock eliminates that race entirely by ensuring only one thread is inside any write path at a time. Read-only functions (`get_thumbnail_path`, `thumbnails_status`) deliberately skip this lock — WAL mode lets them run concurrently with writers at no cost.

---

## Fix 3 — Replaced plain-list queue with `queue.Queue` + persistent daemon worker

**What changed:** The old thumbnail queue was a bare `list` with a `threading.Lock` and a worker that exited as soon as the list was momentarily empty.

```python
# Before — broken
thumbnail_queue = []
thumbnail_lock = threading.Lock()

def process_thumbnail_queue():
    while True:
        with thumbnail_lock:
            if not thumbnail_queue:
                break          # ← exits permanently if queue drains mid-burst
            file_path = thumbnail_queue.pop(0)
        ...
```

Replaced with:

```python
import queue as _queue
thumbnail_queue = _queue.Queue()

def _thumbnail_worker():
    while True:
        try:
            file_path = thumbnail_queue.get(timeout=5)
        except _queue.Empty:
            continue           # ← stays alive, ready for the next item
        try:
            ...                # generate thumbnail
        finally:
            thumbnail_queue.task_done()

def _ensure_thumbnail_worker():
    # Starts the daemon thread exactly once at module load
    ...
```

**Why it fixes the issue:**
- `queue.Queue.put()` and `get()` are inherently thread-safe — no manual lock needed.
- The worker never exits; it blocks on `get(timeout=5)` and loops, so items added during or after an initial burst are always processed.
- The thread is a daemon, so it shuts down cleanly when the Flask process exits.
- `_ensure_thumbnail_worker()` uses its own lock to guarantee the thread starts exactly once even if multiple requests race at startup.

---

## Fix 4 — Removed inline writes from `_scan_images()`

**What changed:** `_scan_images()` previously called `update_or_create_image_record()` (a write operation involving hashing and DB access) for every image on every `GET /api/images` request.

```python
# Before — write on every request per image
update_or_create_image_record(str(p))
thumb_path = get_thumbnail_path(str(p))
```

Replaced with a cheap read + background enqueue:

```python
# After — read only; generation offloaded to worker
thumb_path = get_thumbnail_path(str(p))
if thumb_path is None:
    thumbnail_queue.put(str(p))   # worker handles it asynchronously
```

**Why it fixes the issue:** This is the change that most directly reduces lock contention. API requests now only *read* from the DB (which WAL mode handles concurrently) and hand off any missing-thumbnail work to the background worker. Gallery scans with hundreds of images no longer hammer the write lock on every request.

---

## Summary of files changed

| File | Changes |
|------|---------|
| `app.py` | Added `_get_conn()`, `_db_write_lock`, `queue.Queue`-based worker, read-only `_scan_images()` |

## Compatibility

No changes to the public API, config format, thumbnail paths, or database schema. The existing `gallery_config.json` and `.cache/image_cache.db` are fully compatible with the updated code.
