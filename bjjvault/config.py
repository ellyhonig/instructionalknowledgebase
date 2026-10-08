"""Paths, ports and model settings. Override any of these with env vars."""

import glob
import os
import shutil
from pathlib import Path

ROOT = Path(os.environ.get("BJJVAULT_ROOT", Path(__file__).resolve().parent.parent))
DATA = ROOT / "data"
VAULT = ROOT / "vault"

VIDEOS = DATA / "videos"
META = DATA / "meta"
TRANSCRIPTS = DATA / "transcripts"
ORGANIZED = DATA / "organized"
CLIPS = DATA / "clips"
DB_PATH = DATA / "vault.db"

HOST = os.environ.get("BJJVAULT_HOST", "127.0.0.1")
PORT = int(os.environ.get("BJJVAULT_PORT", "8765"))
BASE_URL = f"http://localhost:{PORT}"

WHISPER_MODEL = os.environ.get("BJJVAULT_WHISPER", "mlx-community/whisper-large-v3-turbo")
EMBED_MODEL = os.environ.get("BJJVAULT_EMBED", "BAAI/bge-small-en-v1.5")
CLAUDE_MODEL = os.environ.get("BJJVAULT_CLAUDE_MODEL", "opus")
# e.g. "chrome" or "safari" -- lets yt-dlp use your browser login (higher Bilibili quality)
COOKIES_BROWSER = os.environ.get("BJJVAULT_COOKIES_BROWSER")
MAX_HEIGHT = int(os.environ.get("BJJVAULT_MAX_HEIGHT", "1080"))


def ensure_dirs() -> None:
    for d in (VIDEOS, META, TRANSCRIPTS, ORGANIZED, CLIPS, VAULT):
        d.mkdir(parents=True, exist_ok=True)


def claude_bin() -> str:
    """Find a Claude Code CLI that's logged in: $CLAUDE_BIN, `claude` on PATH, or the desktop app's bundled copy."""
    if env := os.environ.get("CLAUDE_BIN"):
        return env
    if found := shutil.which("claude"):
        return found
    pattern = os.path.expanduser(
        "~/Library/Application Support/Claude/claude-code/*/*/claude.app/Contents/MacOS/claude"
    )

    def version_key(p: str):
        ver = Path(p).parents[3].name
        return tuple(int(x) if x.isdigit() else 0 for x in ver.split("."))

    candidates = sorted(glob.glob(pattern), key=version_key)
    if candidates:
        return candidates[-1]
    raise RuntimeError("Claude Code CLI not found. Install it or set CLAUDE_BIN.")
