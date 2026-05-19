---
name: testing-ai-gallery
description: Test the AI Gallery Pro Flask app end-to-end. Use when verifying gallery UI, metadata extraction, cache, export, or folder management changes.
---

# Testing AI Gallery Pro

## Prerequisites

```bash
pip install flask pillow xxhash
```

## Starting the Server

```bash
cd /home/ubuntu/repos/AI-Image-Gallery
python app.py
```

Server runs at `http://127.0.0.1:8888`. The default folder config may point to `comfy_images/` — if your test images are elsewhere (e.g. `images/`), configure via the Folders UI or API:

```bash
curl -X POST http://127.0.0.1:8888/api/config \
  -H "Content-Type: application/json" \
  -d '{"folders":[{"name":"images","recursive":true}]}'
```

## Test Data Setup

The repo includes sample ComfyUI PNG images in `images/`. For subfolder testing, create a subfolder with a copy:

```bash
mkdir -p images/subfolder
cp images/ComfyUI_02459_.png images/subfolder/ComfyUI_subfolder_test.png
```

Enable `recursive: true` on the folder to pick up subfolder images.

## Key Test Areas

### 1. Cache Status Menu
- Click the 📊 button in the header toolbar
- Verify dropdown opens with stats (Total images, Thumbnails created, Pending, Cache size)
- Click "Generate All Thumbnails" — verify it processes all images and updates stats
- Only one 📊 button should exist (watch for duplicate element IDs)

### 2. Dropdown Positioning
- Click "Folders" and "Cache Status" buttons
- Both dropdowns should appear directly below their trigger buttons (requires `.relative` CSS on parent)
- If dropdowns float to wrong position, check for missing `position: relative` on the `.control-group` wrapper

### 3. Export Workflow JSON
- Open an image in lightbox, click "Export JSON"
- Verify downloaded filename ends with single `.json` (not `.json.json`)
- The filename format is `{seed}_{imagename}_{sampler}_{cfg}_{steps}.json`
- Fields may show "unknown" if the workflow doesn't contain those values

### 4. Subfolder Export Workflow
- Open a **subfolder** image in lightbox, click "Export JSON"
- Verify export succeeds (not 404 "Image not found")
- The frontend sends `subfolder` in the request body; the backend uses it to construct the correct file path
- Bug pattern: `export_workflow` constructs path as `ROOT/folder/filename` without subfolder — same fix needed as `search_metadata`
- Quick API verification:
  ```bash
  # Should succeed (200)
  curl -X POST http://127.0.0.1:8888/api/export/workflow \
    -H "Content-Type: application/json" \
    -d '{"folder":"images","subfolder":"subfolder","filename":"ComfyUI_subfolder_test.png"}'
  # Should fail (404) — proves subfolder param is needed
  curl -X POST http://127.0.0.1:8888/api/export/workflow \
    -H "Content-Type: application/json" \
    -d '{"folder":"images","filename":"ComfyUI_subfolder_test.png"}'
  ```

### 5. Filtered Export Correctness
- Type a partial filename in "Filter filename..." to show a subset of images
- Open one of the filtered images in lightbox and export
- Verify the exported filename matches the **visible** image, not some other image from the full unfiltered list
- Bug pattern: code uses `allImages[currentIndex]` instead of `currentImages[currentIndex]`
- Also check the `exportWorkflow` guard: should be `if (!currentImages[currentIndex]) return;` not `if (!allImages[currentIndex]) return;`

### 6. Security: Path Traversal Protection
- The `export_workflow` endpoint accepts user-controlled `folder`, `subfolder`, and `filename` params
- Verify folder is validated against the config allowlist (same as `images_from_folder`)
- Verify path traversal via `../` in any parameter returns 403, not 404/500
- Verify error messages don't leak filesystem paths
- Quick security test:
  ```bash
  # Traversal via subfolder — should return 403 "Invalid path"
  curl -s -X POST http://127.0.0.1:8888/api/export/workflow \
    -H "Content-Type: application/json" \
    -d '{"folder":"images","subfolder":"../../..","filename":"passwd"}'
  # Invalid folder — should return 403 "Invalid folder"
  curl -s -X POST http://127.0.0.1:8888/api/export/workflow \
    -H "Content-Type: application/json" \
    -d '{"folder":"etc","filename":"passwd"}'
  # Traversal via filename — should return 403 "Invalid path"
  curl -s -X POST http://127.0.0.1:8888/api/export/workflow \
    -H "Content-Type: application/json" \
    -d '{"folder":"images","filename":"../../../etc/passwd"}'
  ```

### 7. Subfolder Metadata Search
- With recursive enabled, use "Search prompts..." to search metadata
- Verify subfolder images are found and no server 500 errors occur
- Check Flask server console for errors — subfolder path resolution bugs cause FileNotFoundError

### 8. Lightbox & AI Info
- Click any image to open lightbox
- Verify positive/negative prompt, generation settings (Steps, CFG, Sampler, Scheduler, Seed) display correctly
- Navigate between images with arrow buttons
- Counter should show correct index (e.g. "1 / 4")

## Useful API Endpoints for Debugging

```bash
# Get all images
curl http://127.0.0.1:8888/api/images

# Search metadata
curl -X POST http://127.0.0.1:8888/api/metadata/search \
  -H "Content-Type: application/json" -d '{"query":"portrait"}'

# Export workflow (root image)
curl -X POST http://127.0.0.1:8888/api/export/workflow \
  -H "Content-Type: application/json" -d '{"folder":"images","filename":"ComfyUI_02459_.png"}'

# Export workflow (subfolder image — must include subfolder param)
curl -X POST http://127.0.0.1:8888/api/export/workflow \
  -H "Content-Type: application/json" -d '{"folder":"images","subfolder":"subfolder","filename":"ComfyUI_subfolder_test.png"}'

# Cache status
curl http://127.0.0.1:8888/api/thumbnails/status
```

## Common Issues

- **403 errors on subfolder thumbnails**: May be caused by truncated URLs in the DOM — check if the full path resolves correctly
- **Search returns no results**: The search checks PNG tEXt/iTXt chunks for ComfyUI metadata — JPEG/WebP use EXIF. Ensure test images have embedded metadata.
- **Server shows "0 images"**: Check folder config — the default `comfy_images` folder might not exist. Use the API or UI to add the correct folder.
- **Subfolder export returns 404**: Ensure the frontend sends `subfolder` in the request body and the backend includes it in the path construction. Both `search_metadata` and `export_workflow` need subfolder handling.
- **Path traversal returns 200/500 instead of 403**: Check that `export_workflow` validates folder against config allowlist and uses `resolve().is_relative_to()` to block `../` traversal.
