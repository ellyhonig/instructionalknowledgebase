"""Library cards and search scopes for uploads and numbered instructional series."""

import re
import unicodedata

from . import config, db


def _series(title: str) -> tuple[str, int | None]:
    """Recognize part/volume labels or a small trailing number, retaining the series name."""
    title = unicodedata.normalize("NFKC", title).strip()
    marker = re.search(r"\b(?:parts?|pt\.?|vol(?:ume)?\.?|disc|disk)\s*[-:#]?\s*(\d{1,3})(?![\w.])", title, re.I)
    if marker is None:
        # Bare numbering must end the title or introduce a subtitle, not be a year or version.
        marker = re.search(r"\s+(\d{1,2})(?=\s*(?:$|[:—–]|-\s))", title)
    if marker:
        base = title[:marker.start()].strip(" ,:;—–-([")
        if base:
            return base, int(marker[1])
    return title, None


def _normalized(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().replace("&", " and ")
    return " ".join(re.findall(r"\w+", text))


def instructionals() -> list[dict]:
    con = db.connect()
    try:
        videos = [dict(r) for r in con.execute("SELECT * FROM videos ORDER BY rowid")]
    finally:
        con.close()
    groups = {}
    for video in videos:
        # Downloader IDs retain the upload ID and append _pN for each part.
        key = re.sub(r"_p\d+$", "", video["id"]) if video["id"].startswith("bilibili-") else video["id"]
        if key not in groups:
            title, part = _series(video["title"])
            groups[key] = {"id": key, "title": title, "instructor": video["instructor"],
                           "video_ids": [], "duration": 0, "thumbnail": None, "aliases": [key], "part": part}
        group = groups[key]
        group["video_ids"].append(video["id"])
        group["duration"] += video["duration"] or 0
        if group["thumbnail"] is None and (config.THUMBNAILS / f'{video["id"]}.jpg').is_file():
            group["thumbnail"] = f'/thumbnails/{video["id"]}.jpg'
    # Compare upload groups, so chapter titles inside one multipart upload never split it.
    buckets = {}
    for group in groups.values():
        instructor = _normalized(group["instructor"] or "")
        key = (instructor, _normalized(group["title"])) if instructor not in ("", "unknown", "unknown instructor") else (group["id"],)
        buckets.setdefault(key, []).append(group)
    merged = []
    for bucket in buckets.values():
        if len(bucket) == 1 or not any(g["part"] is not None for g in bucket):
            merged.extend(bucket)
            continue
        canonical = bucket[0]["id"]
        aliases = [alias for g in bucket for alias in g["aliases"]]
        ordered = sorted(bucket, key=lambda g: g["part"] if g["part"] is not None else 0)
        first = ordered[0]
        merged.append({**first, "id": canonical, "aliases": aliases,
                       "video_ids": [vid for g in ordered for vid in g["video_ids"]],
                       "duration": sum(g["duration"] for g in bucket),
                       "thumbnail": next((g["thumbnail"] for g in ordered if g["thumbnail"]), None)})
    for group in merged:
        group.pop("part", None)
    return list(reversed(merged))
