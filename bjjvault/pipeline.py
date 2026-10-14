"""Job queue: URL -> download -> transcribe -> organize -> notes -> index. Each stage is cached on disk, so
a failed job can be retried and resumes where it stopped."""

import threading
import time
import traceback

from . import config, db, download, index, notes, organize, transcribe

STAGES = ["queued", "downloading", "transcribing", "organizing", "writing notes", "indexing", "done"]


def enqueue(url: str) -> list[int]:
    """Expand a link (playlist / multi-part) into one job per video."""
    con = db.connect()
    ids = []
    with con:
        for e in download.expand(url):
            cur = con.execute("INSERT INTO jobs (url, playlist, title) VALUES (?,?,?)",
                              (e["url"], e["playlist"], e["title"]))
            ids.append(cur.lastrowid)
    con.close()
    return ids


def _set(job_id: int, **fields) -> None:
    con = db.connect()
    with con:
        sets = ", ".join(f"{k}=?" for k in fields) + ", updated=CURRENT_TIMESTAMP"
        con.execute(f"UPDATE jobs SET {sets} WHERE id=?", (*fields.values(), job_id))
    con.close()


def process(video_url: str, playlist: str | None = None, on_status=lambda status, detail="": None,
            redo_notes: bool = False) -> str:
    on_status("downloading")
    meta = download.download(video_url, playlist, progress=lambda d: on_status("downloading", d))
    vid = meta["id"]
    on_status("transcribing", meta["title"])
    tr = transcribe.transcribe(vid, download.video_path(vid))
    if redo_notes:
        (config.ORGANIZED / f"{vid}.json").unlink(missing_ok=True)
        for part in (config.ORGANIZED / "parts").glob(f"{vid}.part-*.json"):
            part.unlink()
        notes.remove_stale(vid)
    on_status("organizing", f"{config.AI_PROVIDER} is writing structured notes")
    org = organize.organize(vid, meta, tr)
    on_status("writing notes")
    notes.write_instructional(vid, meta, org)
    notes.rebuild_hubs()
    on_status("indexing")
    n = index.index_video(vid, meta, org)
    on_status("done", f"{len(org['chapters'])} chapters, {n} searchable chunks")
    return vid


def run_job(job: dict) -> None:
    jid = job["id"]

    def status(s, detail=""):
        _set(jid, status=s, detail=detail)

    try:
        vid = process(job["url"], job["playlist"], on_status=status)
        _set(jid, video_id=vid, title=download.load_meta(vid)["title"])
    except Exception as e:  # noqa: BLE001
        _set(jid, status="error", error=f"{e}\n{traceback.format_exc()[-1500:]}")


class Worker(threading.Thread):
    """Processes queued jobs one at a time (Whisper and Claude are the bottlenecks anyway)."""

    def __init__(self):
        super().__init__(daemon=True)

    def run(self):
        con = db.connect()
        with con:  # jobs interrupted by a restart go back in the queue
            con.execute("UPDATE jobs SET status='queued' WHERE status NOT IN ('done','error','queued')")
        con.close()
        while True:
            con = db.connect()
            row = con.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
            con.close()
            if row:
                run_job(dict(row))
            else:
                time.sleep(2)
