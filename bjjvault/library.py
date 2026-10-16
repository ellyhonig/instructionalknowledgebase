"""Library cards and search scopes, grouping Bilibili upload parts together."""

import re

from . import config, db


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
            title = re.split(r"\s*(?:[—–,:-]\s*)?\bPart\s+\d+\b", video["title"], maxsplit=1, flags=re.I)[0].strip()
            groups[key] = {"id": key, "title": title, "instructor": video["instructor"],
                           "video_ids": [], "duration": 0, "thumbnail": None}
        group = groups[key]
        group["video_ids"].append(video["id"])
        group["duration"] += video["duration"] or 0
        if group["thumbnail"] is None and (config.THUMBNAILS / f'{video["id"]}.jpg').is_file():
            group["thumbnail"] = f'/thumbnails/{video["id"]}.jpg'
    return list(reversed(groups.values()))
