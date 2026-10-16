"""Paths, ports and model settings. Override any of these with env vars."""

import glob
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(os.environ.get("BJJVAULT_ROOT", Path(__file__).resolve().parent.parent))
DATA = ROOT / "data"
VAULT = ROOT / "vault"
CACHE = DATA / "cache"
TMP = DATA / "tmp"
TMP.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(CACHE / "huggingface"))
os.environ.setdefault("FASTEMBED_CACHE_PATH", str(CACHE / "fastembed"))
os.environ.setdefault("TEMP", str(TMP))
os.environ.setdefault("TMP", str(TMP))

VIDEOS = DATA / "videos"
META = DATA / "meta"
TRANSCRIPTS = DATA / "transcripts"
ORGANIZED = DATA / "organized"
CLIPS = DATA / "clips"
DB_PATH = DATA / "vault.db"

HOST = os.environ.get("BJJVAULT_HOST", "127.0.0.1")
PORT = int(os.environ.get("BJJVAULT_PORT", "8765"))
BASE_URL = f"http://localhost:{PORT}"
MOBILE_URL_FILE = DATA / "mobile-url.json"
MOBILE_ACCESS_TOKEN_FILE = DATA / "mobile-access-token.txt"
MOBILE_PORT = int(os.environ.get("BJJVAULT_MOBILE_PORT", "8767"))
LINK_TTL = int(os.environ.get("BJJVAULT_LINK_TTL", "3600"))


def playback_base_url() -> str:
    """Read the current HTTPS tunnel address on every call, including from existing MCP sessions."""
    url = os.environ.get("BJJVAULT_PUBLIC_URL")
    if not url:
        try:
            url = json.loads(MOBILE_URL_FILE.read_text(encoding="utf-8"))["url"]
        except (OSError, ValueError, KeyError):
            return BASE_URL
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("Mobile playback URL must be an HTTPS origin without credentials, path, or query")
    return url.rstrip("/")

USE_MLX = sys.platform == "darwin" and platform.machine() == "arm64"
WHISPER_MODEL = os.environ.get("BJJVAULT_WHISPER", "mlx-community/whisper-large-v3-turbo" if USE_MLX else "small.en")
WHISPER_DEVICE = os.environ.get("BJJVAULT_WHISPER_DEVICE", "cpu")
AI_PROVIDER = os.environ.get("BJJVAULT_AI_PROVIDER", "codex")
CODEX_MODEL = os.environ.get("BJJVAULT_CODEX_MODEL")
EMBED_MODEL = os.environ.get("BJJVAULT_EMBED", "BAAI/bge-small-en-v1.5")
CLAUDE_MODEL = os.environ.get("BJJVAULT_CLAUDE_MODEL", "opus")
# e.g. "chrome" or "safari" -- lets yt-dlp use your browser login (higher Bilibili quality)
COOKIES_BROWSER = os.environ.get("BJJVAULT_COOKIES_BROWSER")
MAX_HEIGHT = int(os.environ.get("BJJVAULT_MAX_HEIGHT", "1080"))


def ensure_dirs() -> None:
    for d in (VIDEOS, META, TRANSCRIPTS, ORGANIZED, CLIPS, VAULT, CACHE, TMP):
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
