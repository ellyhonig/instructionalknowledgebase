"""Persist a small local cover frame for every downloaded instructional part."""

import logging
import subprocess
import uuid

from . import config
from .util import safe_id

log = logging.getLogger(__name__)


def ensure(video_id: str, duration: float = 0):
    if not video_id or safe_id(video_id) != video_id or video_id in (".", ".."):
        raise ValueError("Invalid video ID")
    config.THUMBNAILS.mkdir(parents=True, exist_ok=True)
    target = config.THUMBNAILS / f"{video_id}.jpg"
    if target.is_file() and target.stat().st_size:
        return target
    source = config.VIDEOS / f"{video_id}.mp4"
    if not source.is_file():
        return None
    temporary = config.THUMBNAILS / f"{video_id}.{uuid.uuid4().hex}.jpg"
    try:
        # Skip opening title screens, with a first-frame fallback for very short videos.
        for at in (min(90, max(0, duration * .1)), 0):
            result = subprocess.run(
                ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", str(at), "-i", str(source),
                 "-frames:v", "1", "-vf", "scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2",
                 "-q:v", "3", str(temporary)], capture_output=True, timeout=60,
            )
            if result.returncode == 0 and temporary.is_file() and temporary.stat().st_size:
                temporary.replace(target)
                return target
        log.warning("Could not create thumbnail for %s", video_id)
    except (OSError, subprocess.SubprocessError):
        log.warning("Could not create thumbnail for %s", video_id, exc_info=True)
    finally:
        temporary.unlink(missing_ok=True)
    return None


def backfill():
    from . import db
    con = db.connect()
    try:
        videos = con.execute("SELECT id, duration FROM videos").fetchall()
    finally:
        con.close()
    saved = sum(ensure(v["id"], v["duration"] or 0) is not None for v in videos)
    print(f"Thumbnails ready: {saved}/{len(videos)}")


if __name__ == "__main__":
    backfill()
