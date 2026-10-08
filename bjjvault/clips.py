import subprocess
from pathlib import Path

from . import config
from .util import safe_id

MAX_CLIP = 300


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
         "-t", f"{end - start:.2f}", "-c:v", "h264_videotoolbox", "-b:v", "4M", "-c:a", "aac",
         "-movflags", "+faststart", str(out)],
        check=True,
    )
    return out
