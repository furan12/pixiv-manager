"""
File operations: scan folders, discover images, move files.
"""
import os
import json
import shutil
from pathlib import Path
from typing import Optional

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def scan_folder_a(path: Path) -> list[str]:
    """List all subfolder names in folder A (artist directories)."""
    if not path.exists():
        return []
    folders = []
    for entry in path.iterdir():
        if entry.is_dir():
            folders.append(entry.name)
    return sorted(folders)


def scan_folder_b(path: Path) -> dict[str, list[str]]:
    """
    Scan folder B and return {b_subfolder_name: [image_filenames]}.
    Only includes folders that contain at least one image file.
    Only includes files with image extensions.
    """
    if not path.exists():
        return {}

    result = {}
    for entry in sorted(path.iterdir()):
        if not entry.is_dir():
            continue

        images = []
        for img_entry in sorted(entry.iterdir()):
            if img_entry.is_file() and img_entry.suffix.lower() in IMAGE_EXTENSIONS:
                images.append(img_entry.name)

        if images:
            result[entry.name] = images

    return result


def move_images(
    pairs: list[dict],
    path_a: Path,
    path_b: Path,
    duplicate_action: str = "skip",
) -> list[dict]:
    """
    Move images from B subfolders to A subfolders.

    Args:
        pairs: [{b_folder, a_folder}]
        path_a: Root of folder A
        path_b: Root of folder B
        duplicate_action: "skip" | "rename" | "overwrite"

    Returns:
        [{file, from_path, to_path, status, reason}]
    """
    results = []

    for pair in pairs:
        b_folder = pair["b_folder"]
        a_folder = pair["a_folder"]
        src_dir = path_b / b_folder
        dst_dir = path_a / a_folder

        if not src_dir.exists():
            continue

        # Ensure target directory exists
        dst_dir.mkdir(parents=True, exist_ok=True)

        for img_entry in sorted(src_dir.iterdir()):
            if not img_entry.is_file():
                continue
            if img_entry.suffix.lower() not in IMAGE_EXTENSIONS:
                continue

            src_path = img_entry
            dst_path = dst_dir / img_entry.name

            status = "moved"
            reason = ""

            # Handle duplicate
            if dst_path.exists():
                if duplicate_action == "skip":
                    status = "skipped"
                    reason = "duplicate filename"
                elif duplicate_action == "overwrite":
                    try:
                        dst_path.unlink()
                    except OSError as e:
                        status = "error"
                        reason = f"cannot overwrite: {e}"
                elif duplicate_action == "rename":
                    # Append (1), (2), etc.
                    stem = dst_path.stem
                    suffix = dst_path.suffix
                    counter = 1
                    while dst_path.exists():
                        dst_path = dst_dir / f"{stem} ({counter}){suffix}"
                        counter += 1

            # Move the file
            if status != "skipped" and status != "error":
                try:
                    shutil.move(str(src_path), str(dst_path))
                except OSError as e:
                    status = "error"
                    reason = f"move failed: {e}"

            results.append({
                "file": img_entry.name,
                "from_folder": b_folder,
                "to_folder": a_folder,
                "from_path": str(src_path),
                "to_path": str(dst_path),
                "status": status,
                "reason": reason,
            })

        # Remove empty B subfolder after move
        try:
            remaining = [f for f in src_dir.iterdir() if f.is_file()]
            if not remaining:
                src_dir.rmdir()
        except OSError:
            pass  # folder not empty or other issue, skip

    return results


def get_state(state_path: Path) -> dict:
    """Load processing state (tracking which images have been processed)."""
    if state_path.exists():
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Convert list back to set
            if "processed" in data:
                data["processed"] = set(data["processed"])
            return data
    return {"processed": set()}


def save_state(state_path: Path, state: dict):
    """Save processing state."""
    # Convert set to list for JSON serialization
    data = {"processed": list(state.get("processed", set()))}
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
