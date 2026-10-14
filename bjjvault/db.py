import sqlite3

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY, title TEXT, instructor TEXT, url TEXT, duration REAL, folder TEXT
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    video_id TEXT, kind TEXT, technique TEXT, position TEXT, chapter TEXT,
    start REAL, end REAL, text TEXT, note TEXT, embedding BLOB
);
CREATE INDEX IF NOT EXISTS chunks_video ON chunks(video_id);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, technique, position, chapter, tokenize='porter');
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY, url TEXT, playlist TEXT, video_id TEXT, title TEXT,
    status TEXT DEFAULT 'queued', detail TEXT DEFAULT '', error TEXT,
    created TEXT DEFAULT CURRENT_TIMESTAMP, updated TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS stream_links (
    token TEXT PRIMARY KEY, video_id TEXT NOT NULL, start REAL NOT NULL,
    end REAL NOT NULL, expires REAL NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    config.ensure_dirs()
    con = sqlite3.connect(config.DB_PATH, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con
