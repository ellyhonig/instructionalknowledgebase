"""yt-dlp wrapper: expand playlists / Bilibili multi-part uploads, download mp4 + metadata."""

import json
from pathlib import Path
from typing import Callable

import yt_dlp

from . import config
from .util import safe_id


def _base_opts() -> dict:
    opts = {"quiet": True, "no_warnings": True, "noprogress": True}
    if config.COOKIES_BROWSER:
        opts["cookiesfrombrowser"] = (config.COOKIES_BROWSER,)
    return opts


def expand(url: str) -> list[dict]:
    """Return [{url, title}] for every video behind a link (1 for a single video)."""
    with yt_dlp.YoutubeDL({**_base_opts(), "extract_flat": "in_playlist"}) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") == "playlist" and info.get("entries"):
        out = []
        for e in info["entries"]:
            if not e:
                continue
            u = e.get("url") or e.get("webpage_url")
            if u and not u.startswith("http") and e.get("ie_key") == "Youtube":
                u = f"https://www.youtube.com/watch?v={u}"
            if u:
                out.append({"url": u, "title": e.get("title") or "", "playlist": info.get("title")})
        return out
    return [{"url": info.get("webpage_url") or url, "title": info.get("title") or "", "playlist": None}]


def video_id_for(info: dict) -> str:
    return safe_id(f"{info.get('extractor_key', 'vid')}-{info['id']}").lower()


def download(url: str, playlist: str | None = None, progress: Callable[[str], None] | None = None) -> dict:
    """Download one video to data/videos/<id>.mp4 and write data/meta/<id>.json. Returns the meta dict."""
    config.ensure_dirs()
    with yt_dlp.YoutubeDL(_base_opts()) as ydl:
        info = ydl.extract_info(url, download=False)
    vid = video_id_for(info)
    out = config.VIDEOS / f"{vid}.mp4"

    if not out.exists():
        h = config.MAX_HEIGHT

        def hook(d):
            if progress and d.get("status") == "downloading":
                progress(f"downloading {d.get('_percent_str', '').strip()}")

        opts = {
            **_base_opts(),
            "format": f"bv*[height<={h}][vcodec^=avc1]+ba[ext=m4a]/bv*[height<={h}]+ba/b[height<={h}]/b",
            "merge_output_format": "mp4",
            "outtmpl": str(config.VIDEOS / f"{vid}.%(ext)s"),
            "progress_hooks": [hook],
            "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        if not out.exists():
            raise RuntimeError(f"Download finished but {out.name} is missing")

    meta = {
        "id": vid,
        "title": info.get("title") or vid,
        "uploader": info.get("uploader") or info.get("channel") or "",
        "url": info.get("webpage_url") or url,
        "duration": info.get("duration") or 0,
        "extractor": info.get("extractor_key") or "",
        "upload_date": info.get("upload_date") or "",
        "description": (info.get("description") or "")[:4000],
        "chapters": [
            {"title": c.get("title"), "start": c.get("start_time"), "end": c.get("end_time")}
            for c in (info.get("chapters") or [])
        ],
        "playlist": playlist or info.get("playlist_title"),
        "language": info.get("language"),
        "video_path": str(out),
    }
    (config.META / f"{vid}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return meta


def load_meta(video_id: str) -> dict:
    return json.loads((config.META / f"{video_id}.json").read_text())


def video_path(video_id: str) -> Path:
    return config.VIDEOS / f"{video_id}.mp4"
