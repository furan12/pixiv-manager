"""
Fuzzy name matching for Pixiv artist folder names.
Handles cases where B folder "artist_extra" should match A folder "artist".
"""
import re
from typing import Optional

try:
    import Levenshtein
    HAS_LEVENSHTEIN = True
except ImportError:
    HAS_LEVENSHTEIN = False


def _normalize(name: str) -> str:
    """Lowercase, strip whitespace, collapse underscores/spaces."""
    name = name.lower().strip()
    name = re.sub(r"[_\-–—\s]+", " ", name)
    name = re.sub(r"[@＠]", "", name)
    return name.strip()


def _levenshtein_ratio(a: str, b: str) -> float:
    """Compute similarity ratio between two strings using Levenshtein distance."""
    if not HAS_LEVENSHTEIN:
        # Pure Python fallback
        return _simple_ratio(a, b)
    return Levenshtein.ratio(a, b)


def _simple_ratio(a: str, b: str) -> float:
    """Simple similarity ratio — fallback when Levenshtein lib not available."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    shorter = min(a, b, key=len)
    longer = max(a, b, key=len)
    # Count matching characters
    matches = sum(1 for c in shorter if c in longer)
    return matches / len(longer)


def _strip_common_suffixes(name: str) -> str:
    """Remove common Pixiv suffixes that plugins may append."""
    patterns = [
        r"\s*[\(（][^)）]*[\)）]\s*$",   # anything in parentheses at end
        r"\s*[-_]\s*\d{4}[-_]\d{2}[-_]\d{2}$",  # dates like 2024-01-15
        r"\s*[-_]\s*\d{4}$",                     # year suffix
        r"\s*[@＠]\w+\s*$",                       # @twitter_handle
        r"\s*\d+[pP]\s*$",                        # 100p etc.
        r"\s*[#＃]\w+\s*$",                        # hashtag
    ]
    for pat in patterns:
        name = re.sub(pat, "", name)
    return name.strip()


def match_folders(
    b_folders: list[str],
    a_folders: list[str],
    threshold: float = 0.80,
) -> list[tuple[str, Optional[str], float]]:
    """
    Match each B folder to the best A folder.

    Returns: list of (b_folder, matched_a_folder_or_None, confidence)

    Strategies, tried in order per B folder:
    1. Exact match (normalized)
    2. Exact match after stripping common suffixes
    3. Prefix match: A name is a prefix of B name (or vice versa)
    4. Substring match: A name fully contained in B name (or vice versa)
    5. Levenshtein ratio >= threshold
    6. Unmatched → None
    """
    a_norm = {name: _normalize(name) for name in a_folders}
    a_stripped = {name: _strip_common_suffixes(_normalize(name)) for name in a_folders}

    results = []

    for b in b_folders:
        b_norm = _normalize(b)
        b_stripped = _strip_common_suffixes(b_norm)
        best_a = None
        best_conf = 0.0

        for a in a_folders:
            a_n = a_norm[a]
            a_s = a_stripped[a]

            # Strategy 1: Exact normalized match
            if b_norm == a_n:
                best_a = a
                best_conf = 1.0
                break

            # Strategy 2: Exact stripped match
            if b_stripped == a_s and b_stripped:
                best_a = a
                best_conf = 0.98
                break

            # Strategy 3: Prefix match
            if a_n and b_norm.startswith(a_n):
                conf = len(a_n) / len(b_norm)
                if conf > best_conf:
                    best_a = a
                    best_conf = max(0.85, conf)
            elif b_norm and a_n.startswith(b_norm):
                conf = len(b_norm) / len(a_n)
                if conf > best_conf:
                    best_a = a
                    best_conf = max(0.85, conf)

            # Strategy 4: Substring match
            if a_n and b_norm and (a_n in b_norm or b_norm in a_n):
                shorter = min(len(a_n), len(b_norm))
                longer = max(len(a_n), len(b_norm))
                conf = shorter / longer if longer > 0 else 0
                conf = max(0.70, conf)
                if conf > best_conf:
                    best_a = a
                    best_conf = conf

        # Strategy 5: Levenshtein (only if no good match yet)
        if best_conf < threshold:
            for a in a_folders:
                a_n = a_norm[a]
                conf = _levenshtein_ratio(b_norm, a_n)
                if conf > best_conf:
                    best_a = a
                    best_conf = conf
                # Also try with stripped version
                conf_s = _levenshtein_ratio(b_stripped, a_stripped[a])
                if conf_s > best_conf:
                    best_a = a
                    best_conf = conf_s

        # Apply threshold
        if best_conf < threshold:
            best_a = None
            best_conf = 0.0

        results.append((b, best_a, best_conf))

    return results
