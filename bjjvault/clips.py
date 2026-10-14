import subprocess
import math
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config, db, download
from .util import safe_id

MAX_CLIP = 300


def create_link(video_id: str, start: float, end: float, ttl: int | None = None) -> dict:
    """Create an expiring local player URL, streaming the source without exporting a file."""
    if safe_id(video_id) != video_id:
        raise ValueError("Invalid video id")
    if not download.video_path(video_id).is_file():
        raise FileNotFoundError(f"No video for {video_id}")
    duration = download.load_meta(video_id).get("duration", 0)
    if not all(math.isfinite(v) for v in (start, end)) or start < 0 or end <= start:
        raise ValueError("Expected finite timestamps with 0 <= start < end")
    if end - start > MAX_CLIP or (duration and end > duration):
        raise ValueError(f"Range must fit the video and be at most {MAX_CLIP} seconds")
    ttl = config.LINK_TTL if ttl is None else ttl
    if not 1 <= ttl <= 86400:
        raise ValueError("Link lifetime must be between 1 second and 24 hours")
    token = secrets.token_urlsafe(32)
    expires = time.time() + ttl
    con = db.connect()
    with con:
        con.execute("DELETE FROM stream_links WHERE expires <= ?", (time.time(),))
        con.execute("INSERT INTO stream_links VALUES (?,?,?,?,?)", (token, video_id, start, end, expires))
    con.close()
    playback_url = config.playback_base_url()
    return {"play_url": f"{playback_url}/clip/{token}",
            "start": start, "end": end,
            "expires_at": datetime.fromtimestamp(expires, timezone.utc).isoformat(),
            "in_context_url": f"{config.BASE_URL}/watch/{video_id}?t={start}&end={end}",
            "phone_accessible": playback_url != config.BASE_URL,
            "note": "Streams from this PC while BJJ Vault and mobile access are running. Anyone with the full link can play it until expiry. The in-context URL is local to the PC."}


def resolve_link(token: str) -> dict | None:
    con = db.connect()
    row = con.execute("SELECT * FROM stream_links WHERE token=? AND expires>?", (token, time.time())).fetchone()
    con.close()
    return dict(row) if row else None


def make_clip(video_id: str, start: float, end: float, pad: float = 1.5) -> Path:
    src = config.VIDEOS / f"{video_id}.mp4"
    if not src.exists():
        raise FileNotFoundError(f"No video for {video_id}")
    start = max(0.0, start - pad)
    end = min(end + pad, start + MAX_CLIP)
    out = config.CLIPS / f"{safe_id(video_id)}_{int(start)}-{int(end)}.mp4"
    if out.exists():
        return out
    config.CLIPS.mkdir(parents=True, exist_ok=True)
    # re-encode (hardware encoder) so the clip starts exactly at `start` instead of the previous keyframe
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", f"{start:.2f}", "-i", str(src),
         "-t", f"{end - start:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-b:v", "4M", "-c:a", "aac",
         "-movflags", "+faststart", str(out)],
        check=True,
    )
    return out
