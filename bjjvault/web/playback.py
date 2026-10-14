"""Token-authenticated playback routes shared by the local app and the clip-only mobile gateway."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

from .. import clips, download
from ..util import fmt_ts

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.filters["ts"] = fmt_ts


def _link(token: str):
    link = clips.resolve_link(token)
    if not link:
        raise HTTPException(410, "This clip link has expired or does not exist. Request a new link.")
    if not download.video_path(link["video_id"]).is_file():
        raise HTTPException(404, "Video no longer available")
    return link


@router.get("/clip/{token}", response_class=HTMLResponse)
def stream_player(request: Request, token: str):
    link = _link(token)
    return templates.TemplateResponse(request, "clip.html", {"link": link, "token": token},
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.api_route("/stream/{token}", methods=["GET", "HEAD"])
def stream_media(token: str):
    link = _link(token)
    return FileResponse(download.video_path(link["video_id"]), media_type="video/mp4",
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
