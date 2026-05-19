# app.py
from pathlib import Path
from flask import Flask, jsonify, send_from_directory, make_response, abort, request
import os
import sqlite3
import xxhash
from datetime import datetime
import threading

ROOT = Path(__file__).parent.resolve()
DEFAULT_IMAGES_DIR = ROOT / "comfy_images"
ALLOWED = {".webp", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".avif"}

# Thumbnail cache settings
CACHE_DIR = ROOT / ".cache"
THUMBNAIL_DIR = CACHE_DIR / "thumbnails"
THUMBNAIL_SIZE = (800, 800)  # Max thumbnail size
THUMBNAIL_QUALITY = 85  # WebP quality (0-100)
DB_FILE = CACHE_DIR / "image_cache.db"

app = Flask(__name__, static_folder=None)

# Config file for folder management
CONFIG_FILE = ROOT / "gallery_config.json"

# Default config
DEFAULT_CONFIG = {
    "folders": [
        {
            "name": "comfy_images",
            "recursive": False
        }
    ]
}

def load_config():
    """Load gallery config or create default."""
    if CONFIG_FILE.exists():
        try:
            import json
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(config):
    """Save gallery config."""
    import json
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


# ==================== IMAGE CACHE ====================

def init_cache_db():
    """Initialize the SQLite cache database."""
    CACHE_DIR.mkdir(exist_ok=True)
    THUMBNAIL_DIR.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE NOT NULL,
            xxhash TEXT NOT NULL,
            size INTEGER,
            width INTEGER,
            height INTEGER,
            mtime REAL,
            thumbnail_created INTEGER DEFAULT 0,
            thumbnail_path TEXT,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_file_path ON images(file_path)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_xxhash ON images(xxhash)')
    conn.commit()
    conn.close()


def get_file_xxhash(file_path):
    """Calculate xxh64 hash of a file."""
    h = xxhash.xxh64()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def get_image_dimensions(file_path):
    """Get image dimensions without loading full image."""
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            return img.size
    except:
        return (0, 0)


def update_or_create_image_record(file_path):
    """Update or create image record in cache. Returns whether thumbnail needs generation."""
    if not Path(file_path).exists():
        return False

    try:
        stat = Path(file_path).stat()
        mtime = stat.st_mtime
        size = stat.st_size
        xxh = get_file_xxhash(file_path)
        width, height = get_image_dimensions(file_path)

        # Generate thumbnail path
        thumbnail_name = f"{xxh}.webp"
        thumbnail_path = THUMBNAIL_DIR / thumbnail_name

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Check if record exists and if it needs updating
        cursor.execute('SELECT xxhash, thumbnail_created FROM images WHERE file_path = ?', (str(file_path),))
        row = cursor.fetchone()

        needs_thumbnail = False

        if row:
            stored_xxhash, thumbnail_created = row
            # Update if hash changed or thumbnail doesn't exist
            if stored_xxhash != xxh or not thumbnail_path.exists():
                cursor.execute('''
                    UPDATE images SET
                        xxhash = ?, size = ?, width = ?, height = ?, mtime = ?,
                        thumbnail_created = 0, thumbnail_path = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE file_path = ?
                ''', (xxh, size, width, height, mtime, str(thumbnail_path), str(file_path)))
                needs_thumbnail = True
        else:
            # Create new record
            cursor.execute('''
                INSERT INTO images (file_path, xxhash, size, width, height, mtime, thumbnail_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (str(file_path), xxh, size, width, height, mtime, str(thumbnail_path)))
            needs_thumbnail = True

        conn.commit()
        conn.close()
        return needs_thumbnail

    except Exception as e:
        print(f"Error updating cache for {file_path}: {e}")
        return False


def generate_thumbnail(file_path, thumbnail_path, size=THUMBNAIL_SIZE):
    """Generate WebP thumbnail for an image."""
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            # Convert to RGB if necessary (for JPEG)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Calculate thumbnail size maintaining aspect ratio
            img.thumbnail(size, Image.Resampling.LANCZOS)

            # Save as WebP
            img.save(thumbnail_path, 'WEBP', quality=THUMBNAIL_QUALITY, method=6)
            return True
    except Exception as e:
        print(f"Error generating thumbnail for {file_path}: {e}")
        return False


def mark_thumbnail_created(file_path):
    """Mark thumbnail as created in cache."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('UPDATE images SET thumbnail_created = 1, updated_at = CURRENT_TIMESTAMP WHERE file_path = ?', (str(file_path),))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error marking thumbnail created: {e}")


def get_thumbnail_path(file_path):
    """Get thumbnail path for an image, or None if not cached."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT thumbnail_path, thumbnail_created FROM images WHERE file_path = ?', (str(file_path),))
        row = cursor.fetchone()
        conn.close()

        if row:
            thumbnail_path, thumbnail_created = row
            if thumbnail_created and Path(thumbnail_path).exists():
                return thumbnail_path
    except Exception as e:
        print(f"Error getting thumbnail path: {e}")
    return None


# Background thread for thumbnail generation
thumbnail_queue = []
thumbnail_lock = threading.Lock()

def process_thumbnail_queue():
    """Background worker to generate thumbnails."""
    while True:
        with thumbnail_lock:
            if not thumbnail_queue:
                break

            file_path = thumbnail_queue.pop(0)

        try:
            needs_thumbnail = update_or_create_image_record(file_path)
            if needs_thumbnail:
                xxh = get_file_xxhash(file_path)
                thumbnail_path = THUMBNAIL_DIR / f"{xxh}.webp"
                if generate_thumbnail(file_path, thumbnail_path):
                    mark_thumbnail_created(file_path)
        except Exception as e:
            print(f"Error processing thumbnail for {file_path}: {e}")

    return True


# Initialize cache on module load
init_cache_db()


@app.route("/")
@app.route("/index.html")
def index():
    return send_from_directory(ROOT, "index.html")


@app.route("/images/<folder>/<path:filename>")
def images_from_folder(folder, filename):
    """Serve image from a specific folder."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        abort(403)

    # Security: only allow folders from config
    config = load_config()
    allowed_folders = [
        f if isinstance(f, str) else f.get("name", "")
        for f in config.get("folders", [])
    ]

    if folder not in allowed_folders:
        abort(403)

    folder_path = ROOT / folder
    if not folder_path.exists() or not folder_path.is_dir():
        abort(404)

    return send_from_directory(folder_path, filename)


@app.route("/images/<path:filename>")
def images(filename):
    # Legacy support - serve from comfy_images
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        abort(403)
    return send_from_directory(DEFAULT_IMAGES_DIR, filename)


@app.route("/favicon.ico")
def favicon():
    return ("", 204)


@app.route("/thumbnail/<xxhash>")
def serve_thumbnail(xxhash):
    """Serve cached WebP thumbnail by xxhash."""
    thumbnail_path = THUMBNAIL_DIR / f"{xxhash}.webp"
    if not thumbnail_path.exists():
        abort(404)
    return send_from_directory(THUMBNAIL_DIR, f"{xxhash}.webp")


@app.route("/api/thumbnails/generate", methods=["POST"])
def generate_thumbnails():
    """Generate thumbnails for images. Can be called with specific paths or all."""
    import json
    data = request.get_json() or {}

    # Get image paths to process
    if "paths" in data and data["paths"]:
        # Process specific images
        paths = data["paths"]
    else:
        # Process all images from current config
        paths = _scan_images_full_paths()

    results = {"total": len(paths), "processed": 0, "failed": 0, "cached": 0}

    for file_path in paths:
        try:
            thumbnail_path = get_thumbnail_path(file_path)
            if thumbnail_path:
                results["cached"] += 1
                continue

            if generate_thumbnail(file_path, thumbnail_path or THUMBNAIL_DIR / f"{get_file_xxhash(file_path)}.webp"):
                mark_thumbnail_created(file_path)
                update_or_create_image_record(file_path)
                results["processed"] += 1
            else:
                results["failed"] += 1
        except Exception as e:
            results["failed"] += 1

    return jsonify(results)


@app.route("/api/thumbnails/status")
def thumbnails_status():
    """Get thumbnail generation status."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM images')
    total = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM images WHERE thumbnail_created = 1')
    created = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM images WHERE thumbnail_created = 0')
    pending = cursor.fetchone()[0]

    # Get total size of thumbnails
    total_size = 0
    for f in THUMBNAIL_DIR.glob("*.webp"):
        total_size += f.stat().st_size

    conn.close()

    return jsonify({
        "total": total,
        "created": created,
        "pending": pending,
        "cache_size_mb": round(total_size / (1024 * 1024), 2),
        "cache_dir": str(CACHE_DIR)
    })


def _scan_images_full_paths():
    """Return list of full file paths for all images."""
    config = load_config()
    out = []

    for folder_config in config.get("folders", []):
        if isinstance(folder_config, str):
            folder_name = folder_config
            recursive = False
        else:
            folder_name = folder_config.get("name")
            recursive = folder_config.get("recursive", False)

        if not folder_name:
            continue

        folder_path = ROOT / folder_name
        if not folder_path.exists() or not folder_path.is_dir():
            continue

        if recursive:
            for p in sorted(folder_path.rglob("*")):
                if p.is_file() and p.suffix.lower() in ALLOWED:
                    out.append(str(p))
        else:
            for p in sorted(folder_path.iterdir()):
                if p.is_file() and p.suffix.lower() in ALLOWED:
                    out.append(str(p))

    return out


def _scan_images():
    """Return list of image info with thumbnail URLs for all configured folders."""
    config = load_config()
    out = []

    for folder_config in config.get("folders", []):
        if isinstance(folder_config, str):
            folder_name = folder_config
            recursive = False
        else:
            folder_name = folder_config.get("name")
            recursive = folder_config.get("recursive", False)

        if not folder_name:
            continue

        folder_path = ROOT / folder_name
        if not folder_path.exists() or not folder_path.is_dir():
            continue

        if recursive:
            for p in sorted(folder_path.rglob("*")):
                if p.is_file() and p.suffix.lower() in ALLOWED:
                    st = p.stat()
                    rel_path = p.relative_to(folder_path)

                    # Update/create cache record and get thumbnail info
                    update_or_create_image_record(str(p))
                    thumb_path = get_thumbnail_path(str(p))
                    thumb_xxhash = Path(thumb_path).stem if thumb_path else None

                    out.append({
                        "path": f"images/{folder_name}/{rel_path}",
                        "folder": folder_name,
                        "subfolder": str(rel_path.parent) if rel_path.parent != Path('.') else "",
                        "filename": p.name,
                        "size": st.st_size,
                        "mtime": int(st.st_mtime),
                        "thumbnail": f"/thumbnail/{thumb_xxhash}" if thumb_xxhash else None,
                    })
        else:
            for p in sorted(folder_path.iterdir()):
                if p.is_file() and p.suffix.lower() in ALLOWED:
                    st = p.stat()

                    # Update/create cache record and get thumbnail info
                    update_or_create_image_record(str(p))
                    thumb_path = get_thumbnail_path(str(p))
                    thumb_xxhash = Path(thumb_path).stem if thumb_path else None

                    out.append({
                        "path": f"images/{folder_name}/{p.name}",
                        "folder": folder_name,
                        "subfolder": "",
                        "filename": p.name,
                        "size": st.st_size,
                        "mtime": int(st.st_mtime),
                        "thumbnail": f"/thumbnail/{thumb_xxhash}" if thumb_xxhash else None,
                    })
    return out


@app.route("/api/images")
def list_images():
    """Return every allowed image file in /images with size+mtime for cache-busting."""
    items = _scan_images()
    resp = make_response(jsonify(items))
    resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp


@app.route("/api/config", methods=["GET"])
def get_config():
    """Get current gallery configuration."""
    return jsonify(load_config())


@app.route("/api/config", methods=["POST", "PUT"])
def update_config():
    """Update gallery configuration."""
    config = request.get_json()
    if not config or "folders" not in config:
        return jsonify({"error": "Invalid config"}), 400

    valid_folders = []
    for folder in config["folders"]:
        # Handle both old format (string) and new format (dict)
        if isinstance(folder, str):
            folder_name = folder
            folder_config = {"name": folder_name, "recursive": False}
        else:
            folder_config = folder
            folder_name = folder_config.get("name")

        if not folder_name:
            continue

        folder_path = ROOT / folder_name
        if folder_path.exists() and (folder_path.is_dir() or folder_path.is_symlink()):
            valid_folders.append(folder_config)

    config["folders"] = valid_folders
    save_config(config)
    return jsonify(config)


@app.route("/api/folders", methods=["GET"])
def list_folders():
    """List available folders in the gallery directory."""
    folders = []
    for p in ROOT.iterdir():
        if p.is_dir() and not p.name.startswith('.') and p.name != '__pycache__':
            folders.append(p.name)
    return jsonify(folders)


@app.route("/api/folder/tree", methods=["GET"])
def get_folder_tree():
    """Get folder tree structure for a specific folder."""
    folder_name = request.args.get("folder", "")
    if not folder_name:
        return jsonify({"error": "Folder name required"}), 400

    folder_path = ROOT / folder_name
    if not folder_path.exists() or not folder_path.is_dir():
        return jsonify({"error": "Folder not found"}), 404

    def build_tree(path, relative_to=None):
        """Recursively build folder tree."""
        items = []
        try:
            for item in sorted(path.iterdir()):
                if item.name.startswith('.'):
                    continue
                if item.is_dir():
                    sub_tree = build_tree(item)
                    if sub_tree:
                        items.append({
                            "name": item.name,
                            "type": "folder",
                            "children": sub_tree
                        })
                elif item.suffix.lower() in ALLOWED:
                    items.append({
                        "name": item.name,
                        "type": "file"
                    })
        except PermissionError:
            pass
        return items

    return jsonify(build_tree(folder_path))


@app.route("/api/metadata/search", methods=["POST"])
def search_metadata():
    """Search images by metadata."""
    data = request.get_json()
    query = data.get("query", "").lower().strip()
    if not query:
        images = _scan_images()
        resp = make_response(jsonify(images))
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
        return resp

    images = _scan_images()
    matching_images = []

    for img in images:
        folder_path = ROOT / img["folder"]
        subfolder = img.get("subfolder", "")
        if subfolder:
            img_path = folder_path / subfolder / img["filename"]
        else:
            img_path = folder_path / img["filename"]

        if not img_path.exists():
            continue

        try:
            from PIL import Image
            with Image.open(img_path) as pil_img:
                meta = pil_img.info or {}
                meta_text = ""

                if "prompt" in meta:
                    meta_text += str(meta["prompt"]).lower()
                if "workflow" in meta:
                    meta_text += str(meta["workflow"]).lower()
                if "parameters" in meta:
                    meta_text += str(meta["parameters"]).lower()

                meta_text += img["filename"].lower()

                if query in meta_text:
                    matching_images.append(img)
        except Exception:
            continue

    resp = make_response(jsonify(matching_images))
    resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp


@app.route("/api/export/workflow", methods=["POST"])
def export_workflow():
    """Export workflow JSON from an image."""
    import json
    from PIL import Image

    data = request.get_json()
    folder = data.get("folder")
    filename = data.get("filename")
    subfolder = data.get("subfolder", "")

    if not folder or not filename:
        return jsonify({"error": "Missing folder or filename"}), 400

    config = load_config()
    allowed_folders = [
        f if isinstance(f, str) else f.get("name", "")
        for f in config.get("folders", [])
    ]
    if folder not in allowed_folders:
        return jsonify({"error": "Invalid folder"}), 403

    folder_path = ROOT / folder
    if subfolder:
        img_path = folder_path / subfolder / filename
    else:
        img_path = folder_path / filename

    if not img_path.resolve().is_relative_to(folder_path.resolve()):
        return jsonify({"error": "Invalid path"}), 403

    if not img_path.exists():
        return jsonify({"error": "Image not found"}), 404

    try:
        with Image.open(img_path) as img:
            info = img.info or {}

            workflow_json = None
            if "workflow" in info:
                try:
                    workflow_json = json.loads(info["workflow"])
                except:
                    pass
            elif "prompt" in info:
                try:
                    workflow_json = json.loads(info["prompt"])
                except:
                    pass

            if not workflow_json:
                return jsonify({"error": "No workflow found in image"}), 404

            seed = "unknown"
            sampler = "unknown"
            cfg = "unknown"
            steps = "unknown"

            for node in workflow_json.values():
                if isinstance(node, dict) and "inputs" in node:
                    inp = node["inputs"]
                    if "seed" in inp:
                        seed = str(inp["seed"])
                    if "sampler_name" in inp:
                        sampler = str(inp["sampler_name"])
                    if "cfg" in inp:
                        cfg = str(inp["cfg"])
                    if "steps" in inp:
                        steps = str(inp["steps"])
                    if seed != "unknown" and sampler != "unknown":
                        break

            base_name = Path(filename).stem
            export_filename = f"{seed}_{base_name}_{sampler}_{cfg}_{steps}"
            export_filename = "".join(c for c in export_filename if c.isalnum() or c in "._-") + ".json"

            return jsonify({
                "filename": export_filename,
                "workflow": workflow_json,
                "settings": {
                    "seed": seed,
                    "sampler": sampler,
                    "cfg": cfg,
                    "steps": steps
                }
            })

    except Exception:
        return jsonify({"error": "Failed to process image"}), 500


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    if not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        config = load_config()
        total_images = len(_scan_images())

        # Extract folder names from config
        folder_names = []
        for f in config.get("folders", []):
            if isinstance(f, str):
                folder_names.append(f)
            else:
                name = f.get("name", "")
                recursive = f.get("recursive", False)
                folder_names.append(f"{name}{' (recursive)' if recursive else ''}")

        print(f"🚀 AI Gallery Pro")
        print(f"📂 Folders: {', '.join(folder_names) if folder_names else 'None'}")
        print(f"🖼️  Total images: {total_images}")
        print(f"🌐 Server running at http://127.0.0.1:8888")

    app.run(host="127.0.0.1", port=8888, debug=debug)
