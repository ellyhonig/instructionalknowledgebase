from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .. import clips, config, db, download, index, organize, pipeline
from ..util import fmt_ts, source_url
from .playback import router as playback_router

config.ensure_dirs()
app = FastAPI(title="BJJ Vault")
app.include_router(playback_router)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.filters["ts"] = fmt_ts
app.mount("/media", StaticFiles(directory=config.VIDEOS), name="media")
app.mount("/clips", StaticFiles(directory=config.CLIPS), name="clips")
(config.VAULT / "Assets").mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=config.VAULT / "Assets"), name="assets")


@app.on_event("startup")
def start_worker():
    pipeline.Worker().start()


class AddReq(BaseModel):
    url: str


class ClipReq(BaseModel):
    video_id: str
    start: float
    end: float


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    con = db.connect()
    videos = [dict(r) for r in con.execute("SELECT * FROM videos ORDER BY rowid DESC")]
    con.close()
    return templates.TemplateResponse(request, "index.html", {"videos": videos})


@app.post("/api/jobs")
def add_job(req: AddReq):
    try:
        ids = pipeline.enqueue(req.url.strip())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Couldn't read that link: {e}")
    return {"queued": ids}


@app.get("/api/jobs")
def jobs():
    con = db.connect()
    rows = [dict(r) for r in con.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 500")]
    con.close()
    return rows


@app.post("/api/jobs/{job_id}/retry")
def retry(job_id: int):
    con = db.connect()
    with con:
        con.execute("UPDATE jobs SET status='queued', error=NULL, detail='' WHERE id=?", (job_id,))
    con.close()
    return {"ok": True}


@app.get("/api/search")
def search(q: str, limit: int = 10):
    return index.search(q, limit=limit)


@app.post("/api/clip")
def clip(req: ClipReq):
    try:
        result = clips.create_link(req.video_id, req.start, req.end)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))
    return {"url": result["play_url"], **result}


@app.get("/watch/{video_id}", response_class=HTMLResponse)
def watch(request: Request, video_id: str, t: float = 0, end: float | None = None):
    if not download.video_path(video_id).exists():
        raise HTTPException(404, "Video not downloaded")
    meta = download.load_meta(video_id)
    try:
        org = organize.load(video_id)
    except FileNotFoundError:
        org = None
    return templates.TemplateResponse(request, "watch.html", {
        "meta": meta, "org": org, "t": t, "end": end, "video_id": video_id,
        "source": source_url(meta.get("url", ""), t),
    })


def main():
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)
