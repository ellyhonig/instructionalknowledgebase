"""MCP server so Claude Code can search the vault and cut clips. Never print to stdout here (stdio transport)."""

import json

from mcp.server.fastmcp import FastMCP

from . import clips, config, db, index, pipeline, transcribe
from .util import fmt_ts, player_url, source_url

mcp = FastMCP("bjj-vault")


@mcp.tool()
def search(query: str, limit: int = 8, kind: str | None = None, video_id: str | None = None) -> str:
    """Semantic + keyword search across every instructional in the BJJ vault.

    Returns ranked moments with video_id, start/end seconds, the technique notes or transcript text,
    and the Obsidian note path. Use natural-language questions ("how to finish kimura when they grab their belt").
    kind: optional "technique" (structured notes) or "transcript" (raw spoken windows).
    """
    results = index.search(query, limit=limit, kind=kind, video_id=video_id)
    for r in results:
        r["time"] = f"{fmt_ts(r['start'])}–{fmt_ts(r['end'])}"
        r["watch_url"] = player_url(r["video_id"], r["start"], r["end"])
        r["source_url"] = source_url(r["source_url"], r["start"])
        r["note"] = f"vault/{r['note']}"
    return json.dumps(results, ensure_ascii=False, indent=1)


@mcp.tool()
def get_transcript(video_id: str, start: float, end: float) -> str:
    """Exact timestamped transcript for a time range of a video, to verify or pin down the precise moment."""
    tr = transcribe.load(video_id)
    return "\n".join(f"[{fmt_ts(s['start'])} / {s['start']:.1f}s] {s['text']}"
                     for s in tr["segments"] if s["end"] > start and s["start"] < end)


@mcp.tool()
def make_clip(video_id: str, start: float, end: float) -> str:
    """Return an expiring localhost streaming link for a downloaded instructional range in seconds.
    No clip file is created or attached. Keep ranges tight (usually 15–120s, maximum 300s).
    The web app must be running on this PC; links expire after one hour by default."""
    return json.dumps(clips.create_link(video_id, start, end))


@mcp.tool()
def list_instructionals() -> str:
    """All instructionals in the vault with ids, instructor, duration and note folder."""
    con = db.connect()
    rows = [dict(r) for r in con.execute("SELECT * FROM videos ORDER BY instructor, title")]
    con.close()
    return json.dumps(rows, ensure_ascii=False, indent=1)


@mcp.tool()
def list_techniques(position: str | None = None) -> str:
    """Every technique in the vault (optionally filtered by position) with where it's taught."""
    con = db.connect()
    q = ("SELECT c.technique, c.position, c.video_id, v.instructor, c.start, c.end FROM chunks c "
         "JOIN videos v ON v.id=c.video_id WHERE c.kind='technique'")
    args = []
    if position:
        q += " AND lower(c.position) LIKE ?"
        args.append(f"%{position.lower()}%")
    rows = [dict(r) for r in con.execute(q + " ORDER BY c.technique", args)]
    con.close()
    return json.dumps(rows, ensure_ascii=False, indent=1)


@mcp.tool()
def add_instructional(url: str) -> str:
    """Queue a YouTube/Bilibili video or playlist for download, transcription and note-writing.
    Processing happens in the web app's worker, so `uv run bjjvault serve` must be running."""
    ids = pipeline.enqueue(url)
    return f"Queued {len(ids)} video(s). Track progress at {config.BASE_URL}"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
