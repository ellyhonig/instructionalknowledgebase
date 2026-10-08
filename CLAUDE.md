# BJJ Vault

Personal knowledge base of Brazilian Jiu-Jitsu instructionals. Videos are downloaded from YouTube/Bilibili,
transcribed with local Whisper, organized into notes by headless Claude, written to an Obsidian vault (`vault/`),
and indexed for hybrid semantic/keyword search. The `bjj-vault` MCP server (`.mcp.json`) exposes it.

## Answering BJJ questions
When the user asks how to do something, what an instructor says about X, or wants to see a technique:
1. `search` with the question in natural language (try 1-2 rephrasings if results look weak; use `kind="technique"`
   for structured notes). Look at several results across instructionals, not just the top one.
2. If you need the exact moment, use `get_transcript` around the result's range and tighten start/end to where
   the relevant thing is actually said/shown.
3. Answer concisely in the user's terms, attributing details to instructors ("Chewjitsu: grip the wrist, not the forearm").
4. Always give the moment(s): call `make_clip` for the 1-3 best ranges (usually 15-120s) and return the
   `play_url` (and file path), plus the `watch_url` to see it in context and the Obsidian note path.
5. If nothing in the vault covers it, say so plainly — don't answer from general knowledge as if it came from the vault.

To add videos: `add_instructional(url)` (web app must be running) or `uv run bjjvault add <url>`.

## Code layout
- `bjjvault/pipeline.py` — stages: download → transcribe → organize → notes → index (each cached in `data/`)
- `download.py` (yt-dlp), `transcribe.py` (mlx-whisper), `organize.py` (`claude -p` + pydantic schema),
  `notes.py` (vault writer + Technique/Position/Instructor hubs), `index.py` (fastembed + SQLite FTS5),
  `clips.py` (ffmpeg), `web/app.py` (FastAPI UI + worker), `mcp_server.py`, `cli.py`
- Generated notes keep user edits below the `<!-- bjjvault:end -->` marker.
- After changing note formatting or the index: `uv run bjjvault reindex` (no re-download/re-transcribe/re-organize).
- Re-run Claude organizing for a video: `uv run bjjvault add <url> --redo-notes`.
