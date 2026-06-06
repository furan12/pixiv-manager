"""
Pixiv Image Manager — FastAPI Backend
Manages images downloaded from Pixiv: scans, matches artists, moves files.
"""
import json
import os
import shutil
import hashlib
import base64
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from matcher import match_folders
from file_ops import scan_folder_b, scan_folder_a, move_images, get_state, save_state
from thumbnail import get_thumbnail, clear_thumbnail_cache

app = FastAPI(title="Pixiv Image Manager")

CONFIG_PATH = Path("config.json")
STATE_PATH = Path(".pixiv_manager_state.json")
THUMB_CACHE_DIR = Path("thumb_cache")

# ── Config models ──────────────────────────────────────────────

class Config(BaseModel):
    folder_a_path: str = ""
    folder_b_path: str = ""
    confidence_threshold: float = 0.80
    move_or_copy: str = "move"
    duplicate_action: str = "skip"  # "skip" | "rename" | "overwrite"


class ConfigUpdate(BaseModel):
    folder_a_path: Optional[str] = None
    folder_b_path: Optional[str] = None
    confidence_threshold: Optional[float] = None
    move_or_copy: Optional[str] = None
    duplicate_action: Optional[str] = None


class RematchRequest(BaseModel):
    overrides: dict[str, str] = {}  # b_folder -> forced_a_folder


class ProcessRequest(BaseModel):
    pairs: list[dict]  # [{b_folder, a_folder}]


# ── Config helpers ──────────────────────────────────────────────

def load_config() -> Config:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Config(**data)
    return Config()


def save_config(cfg: Config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg.model_dump(), f, indent=2, ensure_ascii=False)


# ── Startup ─────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    THUMB_CACHE_DIR.mkdir(exist_ok=True)


# ── API: Config ─────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    """Return current configuration."""
    return load_config()


@app.post("/api/config")
async def update_config(body: ConfigUpdate):
    """Update configuration."""
    cfg = load_config()
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(cfg, key, value)
    save_config(cfg)
    return cfg


# ── API: Scan & Match ───────────────────────────────────────────

@app.post("/api/scan")
async def scan():
    """Scan folder B, match artists to folder A, return grouped results."""
    cfg = load_config()

    if not cfg.folder_a_path or not cfg.folder_b_path:
        raise HTTPException(
            status_code=400,
            detail="Please configure both folder A and folder B paths first.",
        )

    path_a = Path(cfg.folder_a_path)
    path_b = Path(cfg.folder_b_path)

    if not path_a.exists():
        raise HTTPException(status_code=400, detail=f"Folder A not found: {path_a}")
    if not path_b.exists():
        raise HTTPException(status_code=400, detail=f"Folder B not found: {path_b}")

    # Scan
    a_folders = scan_folder_a(path_a)
    b_data = scan_folder_b(path_b)

    # Match
    b_names = list(b_data.keys())
    matches = match_folders(b_names, a_folders, cfg.confidence_threshold)

    # Build result
    state = get_state(STATE_PATH)
    results = []
    for b_name, matched_a, confidence in matches:
        images = b_data[b_name]
        new_count = len([img for img in images if img not in state.get("processed", set())])
        results.append({
            "b_folder": b_name,
            "matched_a_folder": matched_a,
            "confidence": round(confidence, 4),
            "image_count": len(images),
            "new_count": new_count,
            "images": images,
        })

    return {
        "results": results,
        "a_folders": a_folders,
        "total_images": sum(r["image_count"] for r in results),
        "total_new": sum(r["new_count"] for r in results),
    }


# ── API: Images ─────────────────────────────────────────────────

@app.get("/api/images/{b_folder:path}")
async def list_images(b_folder: str):
    """List image files in a specific B subfolder."""
    cfg = load_config()
    path_b = Path(cfg.folder_b_path) / b_folder
    if not path_b.exists():
        raise HTTPException(status_code=404, detail="Folder not found")

    images = scan_folder_b(Path(cfg.folder_b_path)).get(b_folder, [])
    return {"b_folder": b_folder, "images": images}


# ── API: Folders A ──────────────────────────────────────────────

@app.get("/api/folders-a")
async def list_folders_a():
    """List all subfolder names in folder A (for manual override dropdown)."""
    cfg = load_config()
    if not cfg.folder_a_path:
        raise HTTPException(status_code=400, detail="Folder A not configured")
    folders = scan_folder_a(Path(cfg.folder_a_path))
    return {"folders": folders}


# ── API: Rematch ────────────────────────────────────────────────

@app.post("/api/rematch")
async def rematch(body: RematchRequest):
    """Re-run matching with manual overrides for specific B folders."""
    cfg = load_config()
    path_a = Path(cfg.folder_a_path)
    path_b = Path(cfg.folder_b_path)

    a_folders = scan_folder_a(path_a)
    b_data = scan_folder_b(path_b)
    b_names = list(b_data.keys())

    matches = match_folders(b_names, a_folders, cfg.confidence_threshold)

    # Apply overrides
    results = []
    for b_name, matched_a, confidence in matches:
        if b_name in body.overrides:
            matched_a = body.overrides[b_name]
            confidence = 1.0
        images = b_data[b_name]
        state = get_state(STATE_PATH)
        new_count = len([img for img in images if img not in state.get("processed", set())])
        results.append({
            "b_folder": b_name,
            "matched_a_folder": matched_a,
            "confidence": round(confidence, 4),
            "image_count": len(images),
            "new_count": new_count,
            "images": images,
        })

    return {"results": results, "a_folders": a_folders,
            "total_images": sum(r["image_count"] for r in results)}


# ── API: Process (Move) ─────────────────────────────────────────

@app.post("/api/process")
async def process(body: ProcessRequest):
    """Move images from B to A for confirmed pairings."""
    cfg = load_config()
    path_a = Path(cfg.folder_a_path)
    path_b = Path(cfg.folder_b_path)

    results = move_images(
        pairs=body.pairs,
        path_a=path_a,
        path_b=path_b,
        duplicate_action=cfg.duplicate_action,
    )

    # Update state with processed files
    state = get_state(STATE_PATH)
    for r in results:
        if r["status"] == "moved":
            state.setdefault("processed", set()).add(r["file"])
    save_state(STATE_PATH, state)

    return {"results": results}


# ── API: Thumbnail & Image serving ──────────────────────────────

def _hash_path(p: str) -> str:
    return hashlib.sha256(p.encode()).hexdigest()[:16]


@app.get("/api/thumbnail/{path_hash}")
async def serve_thumbnail(path_hash: str, path: str = Query(...)):
    """Serve a thumbnail for the given file path."""
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    thumb_path = get_thumbnail(file_path, THUMB_CACHE_DIR, size=(300, 300))
    return FileResponse(thumb_path)


@app.get("/api/image/{path_hash}")
async def serve_image(path_hash: str, path: str = Query(...)):
    """Serve a full-resolution image."""
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path)


# ── API: Clear thumbnails ───────────────────────────────────────

@app.post("/api/clear-thumbnails")
async def clear_thumbnails():
    """Clear the thumbnail cache."""
    clear_thumbnail_cache(THUMB_CACHE_DIR)
    return {"status": "ok"}


# ── Static files (UI) ───────────────────────────────────────────

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


# ── Entry point ─────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
