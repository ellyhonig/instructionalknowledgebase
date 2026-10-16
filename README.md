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

The home page shows saved thumbnail covers. Select a cover to highlight it and restrict questions
to that instructional, including all indexed parts of the same Bilibili upload. The selected title
appears above the question box and is remembered in that browser. Choose **Search all** to search
the whole library. Only successfully indexed parts appear in the library; check **Processing** for
pending or failed parts. Search returns matching notes and timestamped video passages.

Covers are extracted locally from downloaded videos into `data/thumbnails/`, and new ingestions
save them automatically. To backfill an existing library, run
`.\.venv\Scripts\python.exe -X utf8 -m bjjvault.thumbnails`.

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

By default, links work on this PC with the web server running. Enable the mobile tunnel below
for phone-accessible HTTPS links. Token expiry applies to new player
and media requests; it cannot retract media a browser has already buffered.

## Phone access through mobile Codex

On your phone, choose your connected Windows PC in Codex/Remote and use a PC-connected chat.
Ask: **Use bjj-vault to find the body-lock passing explanation and give me a phone-playable clip link.**
The MCP server is registered globally on the PC, so a chat can use it without opening the repository
folder on the phone. The repo and media stay on X: (clonkker). To show the repo as a saved project,
use Add/Open project in the desktop app and select `X:\instructionalknowledgebase`; then select
that saved project on mobile. Other registered projects on X: demonstrate that secondary drives work.

```powershell
cd X:\instructionalknowledgebase
.\Start-Mobile.ps1
```

This downloads a checksum-verified portable Cloudflare Tunnel binary into `.tools/`, starts an
authenticated loopback gateway on port 8767, and forwards it to a temporary HTTPS address.
No Cloudflare account, OpenAI API key, phone VPN app, or router port-forwarding rule is needed.
The full library, search, video player, and ingestion controls require your private vault access token.

Run `.\Get-MobileAccess.ps1` to print a private one-click sign-in link for your phone. The token is
kept in ignored `data/mobile-access-token.txt` on X:. Its URL fragment is consumed by the sign-in
page and removed from browser history before the token is submitted. The browser receives a
Secure, HttpOnly, SameSite=Strict session cookie valid for seven days. Unauthenticated API calls
are rejected and unauthenticated page visits open sign-in. Visit `/login` to sign out of a browser.
API clients can instead send `Authorization: Bearer <vault-access-token>`.

To replace the token and invalidate existing browser sessions, run:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m bjjvault.mobile_auth --rotate
.\Get-MobileAccess.ps1
```

Temporary MCP clip links retain their own scoped, expiring tokens: anyone holding a complete
clip URL can view that source until expiry, without unlocking the rest of the library. Playback
streams through Cloudflare from this PC. New phone requests must keep the PC and services online.

The address changes when the tunnel restarts. New links automatically use the current address,
including from MCP sessions that have loaded this version. Request a new link after a tunnel restart.
Cloudflare Quick Tunnels are temporary and have no uptime guarantee; use a named tunnel or private
network for a permanent hostname. See https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/.

`Start-Vault.ps1` also starts mobile access after it has been enabled. `Stop-Vault.ps1` stops both
servers; starting again restores both. `Stop-Mobile.ps1` stops and disables mobile access while
leaving ingestion running. Logs and runtime addresses/PIDs stay under ignored `data/` on X:.

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

Bilibili DASH streams download in small, verified, resumable byte ranges with four connections.
Interrupted chunks resume from their saved bytes, alternative CDN mirrors are used when available,
and existing partial yt-dlp downloads seed the range cache. The cache lives in `data/downloads/`.
The final MP4 is published only after all video/audio ranges have been verified and merged.

## Validation

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```

Tests verify byte-range seeking, HEAD responses, token expiry for both player and media,
invalid ranges/path input, and that streaming links create no clip files.
