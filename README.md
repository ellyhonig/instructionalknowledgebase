# BJJ Vault

Collect jiu-jitsu instructionals from YouTube/Bilibili → local Whisper transcripts → Claude-organized Obsidian notes
→ ask questions in Claude Code and get back answers **with clips**.

## Use
```bash
uv run bjjvault serve        # web app at http://localhost:8765 — paste links, watch progress, search, play
uv run bjjvault add <url>    # or ingest from the terminal (video, playlist, or multi-part Bilibili)
```
- Open `vault/` as a vault in Obsidian. Start at `Home.md`. Timestamp links (▶) open the local player, so keep `serve` running.
- Open Claude Code in this folder and ask: *"how do I finish the kimura when they grip their belt?"* — it uses the
  `bjj-vault` MCP server to search, then cuts clips into `data/clips/`.

## Requirements
`brew install ffmpeg yt-dlp uv`, plus the Claude desktop app or Claude Code CLI signed in (used headlessly for note-writing;
no API key). Whisper and embedding models download on first run.

## Settings (env vars)
`BJJVAULT_CLAUDE_MODEL` (default `opus`), `BJJVAULT_WHISPER`, `BJJVAULT_COOKIES_BROWSER=chrome` (use your browser login
for higher Bilibili quality / members-only videos), `BJJVAULT_MAX_HEIGHT` (default 1080), `CLAUDE_BIN`.
