# Pixiv Image Manager

A visual tool for managing Pixiv-downloaded images. Quickly review new downloads in folder B,
auto-match artist folders to your curated collection in folder A, and move images with one click.

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start the server:

```bash
python main.py
```

3. Open http://localhost:8000 in your browser.

4. Click the ⚙️ Settings button and configure:
   - **Folder A (主文件夹)**: Your curated image collection, organized by artist name
   - **Folder B (下载文件夹)**: Where your Pixiv download plugin saves new images
   - **Confidence threshold**: Auto-match sensitivity (default 0.80)
   - **Duplicate action**: What to do when a file already exists (skip/rename/overwrite)

## How It Works

### Workflow

1. **Scan** — Click the 🔄 Scan button. The app scans folder B for new images, groups them
   by artist subfolder, and auto-matches each to your folder A collection.

2. **Review** — Browse the left panel to see all detected artist folders. Each shows:
   - Match target and confidence score
   - Number of new images
   - Match status (confirmed ⚠️ / auto-matched ✅)

3. **Confirm** — Click any folder to preview its images. If the auto-match is correct,
   click ✅ Confirm. If not, select the correct folder from the dropdown or press S to skip.

4. **Process** — Click "全部处理" to move all confirmed items, or "处理选中" for just one.
   Images are moved from B into the correct A subfolder. Empty B folders are cleaned up.

### Matching Logic

The fuzzy matcher tries these strategies in order:
1. **Exact match** — names are identical
2. **Stripped match** — matches after removing common suffixes (dates, @handles, etc.)
3. **Prefix match** — A folder name is a prefix of B folder name (handles `artist` → `artist_extra`)
4. **Substring match** — one name contains the other
5. **Levenshtein distance** — high similarity ratio

Confidence ≥ 95% is auto-confirmed. Lower scores are highlighted for manual review.

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| ↑/↓ | Navigate folders |
| Enter | Confirm current match |
| S | Skip current folder |
| Esc | Close lightbox / config modal |

## File Structure

```
pixiv-manager/
├── main.py              # FastAPI backend, all API routes
├── matcher.py           # Fuzzy artist name matching logic
├── file_ops.py           # Folder scanning and file move operations
├── thumbnail.py          # On-demand thumbnail generation & caching
├── static/
│   └── index.html        # Single-page web UI
├── requirements.txt
└── README.md
```

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/config` | Get settings |
| POST | `/api/config` | Update settings |
| POST | `/api/scan` | Scan B, match to A |
| POST | `/api/rematch` | Re-match with manual overrides |
| POST | `/api/process` | Execute moves |
| GET | `/api/folders-a` | List A subfolders |
| GET | `/api/thumbnail/{hash}?path=` | Serve thumbnail |
| GET | `/api/image/{hash}?path=` | Serve full image |
| POST | `/api/clear-thumbnails` | Clear thumbnail cache |
