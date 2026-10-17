"""yt-dlp wrapper: expand playlists / Bilibili multi-part uploads, download mp4 + metadata."""

import json
import time
import subprocess
from urllib.parse import urlsplit
from pathlib import Path
from typing import Callable

import yt_dlp
from yt_dlp.extractor.bilibili import BiliBiliIE as _BiliBiliIE

from . import config
from .media import validate_video
from .util import safe_id


class BiliBiliIE(_BiliBiliIE):
    """Use the public playback endpoint when WBI succeeds but returns no streams."""

    def extract_formats(self, play_info):
        formats = super().extract_formats(play_info)
        dash = (play_info or {}).get('dash') or {}
        mirrors = {}
        for item in [*(dash.get('video') or []), *(dash.get('audio') or [])]:
            base = item.get('baseUrl') or item.get('base_url')
            mirrors[base] = item.get('backupUrl') or item.get('backup_url') or []
        for fmt in formats:
            fmt['_backup_urls'] = mirrors.get(fmt['url'], [])
        return formats

    def _download_playinfo(self, bvid, cid, headers=None, query=None, fatal=True):
        info = super()._download_playinfo(bvid, cid, headers=headers, query=query, fatal=fatal)
        if info and not info.get("dash") and not info.get("durl"):
            response = self._download_json(
                "https://api.bilibili.com/x/player/playurl", bvid,
                query={"bvid": bvid, "cid": cid, "fnval": 4048, "qn": 32},
                headers=headers, fatal=False, note="Trying public playback endpoint")
            if response and response.get("code") == 0:
                data = response.get("data") or {}
                if data.get("dash") or data.get("durl"):
                    return data
        return info


def _ydl(opts):
    ydl = yt_dlp.YoutubeDL(opts)
    ydl.add_info_extractor(BiliBiliIE())
    return ydl


def _canonical_share_url(url: str) -> str:
    if urlsplit(url).hostname == "b23.tv":
        import requests
        response = requests.get(url, timeout=30, allow_redirects=False)
        response.raise_for_status()
        resolved = urlsplit(response.headers.get("Location", response.url))
        if resolved.hostname in ("www.bilibili.com", "bilibili.com") and resolved.path.startswith("/video/"):
            # Mobile share URLs always append p=1; omit it to ingest all chapters of the upload.
            return f"https://www.bilibili.com{resolved.path}"
    return url


def _base_opts() -> dict:
    opts = {"quiet": True, "no_warnings": True, "noprogress": True,
            "socket_timeout": 30, "retries": 3,
            "http_chunk_size": 1024 * 1024,
            "http_headers": {"User-Agent": "Mozilla/5.0"},
            "cachedir": str(config.CACHE / "yt-dlp")}
    if config.COOKIES_BROWSER:
        opts["cookiesfrombrowser"] = (config.COOKIES_BROWSER,)
    return opts


def expand(url: str) -> list[dict]:
    """Return [{url, title}] for every video behind a link (1 for a single video)."""
    with _ydl({**_base_opts(), "extract_flat": "in_playlist"}) as ydl:
        info = ydl.extract_info(_canonical_share_url(url), download=False)
    if info.get("_type") == "playlist" and info.get("entries"):
        out = []
        for part_number, e in enumerate(info["entries"], 1):
            if not e:
                continue
            u = e.get("url") or e.get("webpage_url")
            if u and not u.startswith("http") and e.get("ie_key") == "Youtube":
                u = f"https://www.youtube.com/watch?v={u}"
            if u:
                out.append({"url": u, "title": e.get("title") or f"{info.get('title') or 'Instructional'} — Part {part_number}", "playlist": info.get("title")})
        return out
    return [{"url": info.get("webpage_url") or url, "title": info.get("title") or "", "playlist": None}]


def video_id_for(info: dict) -> str:
    return safe_id(f"{info.get('extractor_key', 'vid')}-{info['id']}").lower()


def _download_bilibili(info: dict, vid: str, out: Path, progress=None) -> bool:
    formats = info.get('requested_formats') or [info]
    if not formats or any(not f.get('url', '').startswith('https://') or f.get('fragments') for f in formats):
        return False
    from .ranged_download import fetch
    directory = config.DATA / 'downloads' / vid
    inputs = []
    for fmt in formats:
        format_id = safe_id(str(fmt.get('format_id', 'media')))
        ext = fmt.get('ext') or 'mp4'
        destination = directory / f'{format_id}.{ext}'
        seed = config.VIDEOS / f'{vid}.f{format_id}.{ext}.part'
        headers = {**info.get('http_headers', {}), **fmt.get('http_headers', {}), 'User-Agent':'Mozilla/5.0'}
        fetch([fmt['url'], *fmt.get('_backup_urls', [])], destination,
              directory / f'{format_id}-ranges', headers, progress=progress, seed=seed)
        inputs += ['-i', str(destination)]
    temporary = directory / 'merged.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', *inputs,
                    '-c', 'copy', '-movflags', '+faststart', str(temporary)], check=True)
    validate_video(temporary, info.get('duration') or 0)
    temporary.replace(out)
    return True


def download(url: str, playlist: str | None = None, progress: Callable[[str], None] | None = None) -> dict:
    """Download one video to data/videos/<id>.mp4 and write data/meta/<id>.json. Returns the meta dict."""
    config.ensure_dirs()
    h = config.MAX_HEIGHT
    selector = f"bv*[height<={h}][vcodec^=avc1]+ba[ext=m4a]/bv*[height<={h}]+ba/b[height<={h}]/b"
    with _ydl({**_base_opts(), 'format': selector}) as ydl:
        info = ydl.extract_info(url, download=False)
    vid = video_id_for(info)
    out = config.VIDEOS / f"{vid}.mp4"

    if out.exists():
        try:
            validate_video(out, info.get('duration') or 0)
        except (ValueError, subprocess.SubprocessError):
            # Preserve the damaged copy on X: and replace it using the current downloader.
            damaged = config.DATA / 'damaged-media'
            damaged.mkdir(exist_ok=True)
            out.replace(damaged / f'{vid}.{time.time_ns()}.mp4')
            if progress:
                progress('Replacing a damaged cached video')

    ranged = False
    if not out.exists() and info.get('extractor_key') == 'BiliBili':
        ranged = _download_bilibili(info, vid, out, progress)
    if not out.exists() and not ranged:
        last_progress = 0.0

        def hook(d):
            nonlocal last_progress
            now = time.monotonic()
            if progress and d.get("status") == "downloading" and now - last_progress >= 1:
                last_progress = now
                progress(f"downloading {d.get('_percent_str', '').strip()}")

        opts = {
            **_base_opts(),
            "format": selector,
            "merge_output_format": "mp4",
            "outtmpl": str(config.VIDEOS / f"{vid}.%(ext)s"),
            "progress_hooks": [hook],
            "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
        }
        with _ydl(opts) as ydl:
            ydl.download([url])
        if not out.exists():
            raise RuntimeError(f"Download finished but {out.name} is missing")
        validate_video(out, info.get('duration') or 0)

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
    (config.META / f"{vid}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def load_meta(video_id: str) -> dict:
    return json.loads((config.META / f"{video_id}.json").read_text(encoding="utf-8"))


def video_path(video_id: str) -> Path:
    return config.VIDEOS / f"{video_id}.mp4"
