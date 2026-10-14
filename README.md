# BJJ Vault

Download Bilibili/YouTube instructionals, transcribe locally with Whisper, generate structured
Obsidian notes using the installed Codex CLI signed in with ChatGPT, and search through MCP.
MCP clip requests return temporary links hosted on this PC, without exporting or attaching video files.

## Windows installation on clonkker

This installation is in `X:\instructionalknowledgebase`. Videos, transcripts, notes, Python
environment, downloaded models, package caches, and temporary audio are stored under this folder.
It reuses the already installed Python, ffmpeg, and Codex executables.

```powershell
cd X:\instructionalknowledgebase
.\Setup-Windows.ps1
.\Start-Vault.ps1
.\.venv\Scripts\python.exe -X utf8 Queue-Instructionals.py
```

Open **http://localhost:8765** to watch processing, search, and play videos. The 12 supplied URLs
are in `instructionals.txt`; multipart uploads expand into separate jobs. Repeat batch queueing
skips URLs already recorded in `data/batch-report.json`. Use the web Retry button for failed jobs.
Processing runs serially in the background and can take hours. Leave the computer on. Start-Vault
keeps running after the shell closes; it does not automatically launch after a Windows restart.
Run `.\Stop-Vault.ps1` to stop it. Starting again resumes cached stages and partial downloads.
Logs are in `data/logs/`.

## ChatGPT authentication, without API keys

`codex login status` must report **Logged in using ChatGPT**. If needed, run `codex login`
and choose ChatGPT sign-in. The default note provider is `codex`, invoked locally with an
output schema. It checks the login type, removes API-key variables from the subprocess, and
ignores custom provider configuration. It uses your ChatGPT plan and its usage limits;
the language model runs through OpenAI, while video storage and Whisper run on your PC.
An API-key login is rejected. Claude remains an optional provider for existing Mac users.

## MCP: ask a question and receive a streaming link

The local Codex configuration has `bjj-vault` registered. New Codex sessions load it.
To register this installation elsewhere:

```powershell
codex mcp add bjj-vault --env BJJVAULT_ROOT=X:\instructionalknowledgebase --env PYTHONUTF8=1 -- X:\instructionalknowledgebase\.venv\Scripts\python.exe -X utf8 -m bjjvault.mcp_server
```

Ask about a technique. The agent searches notes/transcripts, verifies the time range with
`get_transcript`, and calls `make_clip(video_id, start, end)`. The result contains a `play_url`,
start/end seconds, and UTC `expires_at`. Click the link to stream that range and replay it.
The player pauses at the selected end. Playback uses HTTP byte ranges on the source MP4,
so a new clip file is unnecessary. Links last one hour by default, survive server restarts
until expiry, and allow ranges up to five minutes. Expired links return HTTP 410; request a new one.

Links work on this PC with the web server running. The default server binds to loopback;
they are not public internet links or cross-device links. Token expiry applies to new player
and media requests; it cannot retract media a browser has already buffered.

Open `vault/` in Obsidian and start at `Home.md`. Persistent note timestamp links use the
ordinary local player and require the server to be running.

## CLI and settings

```powershell
.\.venv\Scripts\bjjvault.exe add <url>
.\.venv\Scripts\bjjvault.exe search "body lock passing"
.\.venv\Scripts\bjjvault.exe clip <video_id> 120 180
.\.venv\Scripts\bjjvault.exe reindex
```

Set environment variables before starting the server: `BJJVAULT_WHISPER` (Windows default
`small.en`), `BJJVAULT_WHISPER_DEVICE` (`cpu` by default, `cuda` requires compatible CUDA/cuDNN),
`BJJVAULT_CODEX_MODEL` (otherwise Codex chooses its default), `CODEX_BIN`,
`BJJVAULT_LINK_TTL` (seconds, default 3600), `BJJVAULT_MAX_HEIGHT` (1080),
`BJJVAULT_COOKIES_BROWSER` (e.g. `chrome` for an existing Bilibili login),
`BJJVAULT_ROOT`, `BJJVAULT_PORT`, and `BJJVAULT_AI_PROVIDER` (`codex` or `claude`).
On Apple Silicon transcription uses MLX Whisper; Windows uses faster-whisper.

Bilibili's public playback endpoint is used when the WBI endpoint returns success with no streams.
Mobile short-link share parameters are removed so all parts are ingested. Availability, quality,
and login requirements still depend on Bilibili.

## Validation

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```

Tests verify byte-range seeking, HEAD responses, token expiry for both player and media,
invalid ranges/path input, and that streaming links create no clip files.
