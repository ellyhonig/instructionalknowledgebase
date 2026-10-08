import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from . import config


def fmt_ts(seconds: float) -> str:
    s = int(max(0, seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def safe_name(text: str, max_len: int = 80) -> str:
    """Make a string safe for an Obsidian file/folder name and wikilinks."""
    text = re.sub(r'[\\/:*?"<>|#^\[\]]', " ", text or "")
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:max_len].rstrip(" .") or "Untitled"


def safe_id(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_")


def player_url(video_id: str, start: float, end: float | None = None) -> str:
    url = f"{config.BASE_URL}/watch/{video_id}?t={int(start)}"
    if end is not None:
        url += f"&end={int(end)}"
    return url


def source_url(url: str, start: float) -> str:
    """Link to the original platform at a timestamp (YouTube & Bilibili both accept t=)."""
    if not url:
        return ""
    parts = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(parts.query) if k != "t"]
    q.append(("t", f"{int(start)}s" if "youtu" in parts.netloc else str(int(start))))
    return urlunparse(parts._replace(query=urlencode(q)))
