# AI Gallery Pro

An advanced image gallery for AI-generated images (ComfyUI, Automatic1111) with metadata extraction, workflow export, and powerful browsing features.

## Features

### 🖼️ Image Browsing
- **Grid View** - Responsive grid with customizable sizes (Small/Medium/Large)
- **List View** - Detailed list view with folder information
- **Image Counter** - Shows current position and total images
- **Theme Toggle** - Dark/Light theme support

### 📁 Folder Management
- **List View** - Quick add available folders
- **Tree View** - Browse subdirectories and select specific folders
- **Recursive Mode** - Optionally scan all subfolders
- Add/remove multiple image folders
- Configuration persisted in `gallery_config.json`
- Supports symlinks (like ComfyUI output folders)
- **Create symlinks** to include folders from anywhere on your system

**Quick symlink example (Linux/Mac):**
```bash
cd /home/john/Documents/ALECIA-AI/mcp_tools/AI-Image-Gallery/
ln -s /path/to/images folder_name
```

#### Using Tree View
1. Click "📁 Folders" button
2. Switch to "Tree View" tab
3. Select a folder from the dropdown
4. Browse the folder structure
5. Click on a folder to select it
6. Check "Recursive" to include all subfolders
7. Click "+ Add Selected Folder"

### 🔍 Search & Filter
- **Filename Search** - Filter images by filename
- **Metadata Search** - Search through prompts, workflows, and parameters
- Real-time filtering as you type

### 📋 AI Metadata Extraction
- **ComfyUI Support** - Extract prompts and workflows from PNG metadata
- **Automatic1111 Support** - Parse parameters from JPEG/PNG EXIF
- **WebP Support** - Extract metadata from WebP format
- Display positive/negative prompts
- Show generation settings (Steps, CFG, Sampler, Scheduler, Seed)

### 🖱️ Advanced Controls
- **Mouse Drag** - Pan around zoomed images
- **Mouse Wheel** - Zoom in/out (1x to 5x)
- **Double Click** - Reset zoom and pan
- **Touch Support** - Pinch to zoom, drag to pan on mobile
- **Keyboard Navigation** - Arrow keys for navigation, Space for slideshow, E for export

### 📥 Workflow Export
- Export ComfyUI workflows with custom naming
- Format: `{seed}_{imageName}_{sampler}_{cfg}_{steps}.json`
- One-click download or use `E` key

### 🎬 Slideshow Mode
- Auto-cycling with fullscreen
- Configurable 3.5 second interval
- Pause/resume with Space button

## Installation

### Requirements
- Python 3.7+
- Flask
- Pillow (PIL)

```bash
pip install flask pillow
```

## Usage

### Running the Server

```bash
cd /home/john/Documents/ALECIA-AI/mcp_tools/AI-Image-Gallery/
python3 app.py
```

The server will start at `http://127.0.0.1:8888`

### Adding Images

1. Place images in subdirectories of the gallery folder
2. Click the "📁 Folders" button in the header
3. Click "↻" to refresh available folders
4. Click `+ FolderName` to add folders to the gallery

For ComfyUI users, the default `comfy_images` symlink will be automatically included.

### Adding Symlinked Folders (for folders outside gallery directory)

If you want to include images from a folder elsewhere on your system (e.g., another ComfyUI output folder), create a symlink:

**Linux/Mac:**
```bash
cd /home/john/Documents/ALECIA-AI/mcp_tools/AI-Image-Gallery/
ln -s /path/to/your/images my_images_folder
```

**Windows (PowerShell as Administrator):**
```powershell
cd "C:\path\to\AI-Image-Gallery"
New-Item -ItemType SymbolicLink -Path "my_images_folder" -Target "C:\path\to\your\images"
```

Then:
1. Restart the Flask server
2. Click "📁 Folders"
3. Click "↻" to refresh
4. Add your new symlinked folder

**Example - Adding another ComfyUI output:**
```bash
cd /home/john/Documents/ALECIA-AI/mcp_tools/AI-Image-Gallery/
ln -s /media/john/external-drive/AI/ComfyUI2/output comfy_ui_v2
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `←` / `→` | Previous/Next image |
| `Space` | Toggle slideshow |
| `Escape` | Close modal or info panel |
| `E` | Export workflow JSON |

## API Endpoints

### Images
- `GET /api/images` - List all images from configured folders
- `GET /images/<folder>/<filename>` - Serve image from specific folder

### Configuration
- `GET /api/config` - Get current folder configuration
- `POST /api/config` - Update folder configuration
  ```json
  {
    "folders": ["comfy_images", "my_images"]
  }
  ```

### Folders
- `GET /api/folders` - List available folders in gallery directory
- `GET /api/folder/tree?folder=name` - Get folder tree structure for browsing

### Search
- `POST /api/metadata/search` - Search images by metadata
  ```json
  {
    "query": "portrait blue eyes"
  }
  ```

### Export
- `POST /api/export/workflow` - Export workflow JSON from image
  ```json
  {
    "folder": "comfy_images",
    "filename": "ComfyUI_00163_.png"
  }
  ```

## Configuration

The gallery uses a `gallery_config.json` file to persist folder settings:

```json
{
  "folders": [
    {
      "name": "comfy_images",
      "recursive": false
    },
    {
      "name": "my_archive",
      "recursive": true
    }
  ]
}
```

**Options:**
- `name` - Folder name (must be in gallery directory or symlinked)
- `recursive` - If true, scans all subfolders for images

**Example - Adding your ComfyUI output folder:**
```bash
cd /home/john/Documents/ALECIA-AI/mcp_tools/AI-Image-Gallery/
ln -s /media/john/35ff53f0-74df-4018-90b0-4ee8a466e97e/AI/ComfyUI/output comfy_images
```

Then restart the server and add it via the Folders menu.

## File Structure

```
AI-Image-Gallery/
├── app.py                 # Flask backend server
├── index.html            # Frontend with all features
├── gallery_config.json   # Folder configuration (auto-created)
├── comfy_images/         # Symlink to ComfyUI output (default)
└── README.md             # This file
```

## Supported Image Formats

- PNG (with tEXt/iTXt/zTXt metadata chunks)
- JPEG (with EXIF metadata)
- WebP (with EXIF metadata)
- GIF, BMP, AVIF (basic display, limited metadata)

## License

MIT License

## Credits

Based on contributions from various AI image gallery projects.