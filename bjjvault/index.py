"""Hybrid semantic + keyword search over technique notes and transcript windows."""

import re
import threading

import numpy as np

from . import config, db, transcribe
from .notes import chapter_note_name, folder_name, technique_heading

_model = None
_lock = threading.Lock()


def _embedder():
    global _model
    with _lock:
        if _model is None:
            from fastembed import TextEmbedding
            _model = TextEmbedding(config.EMBED_MODEL, cache_dir=str(config.CACHE / "fastembed"))
    return _model


def _embed_docs(texts: list[str]) -> np.ndarray:
    return np.array(list(_embedder().embed(texts)), dtype=np.float32)


def _embed_query(q: str) -> np.ndarray:
    return np.array(list(_embedder().query_embed(q))[0], dtype=np.float32)


def _windows(segments: list[dict], size: float = 60, step: float = 30) -> list[tuple[float, float, str]]:
    if not segments:
        return []
    out, t, last = [], segments[0]["start"], segments[-1]["end"]
    while t < last:
        segs = [s for s in segments if s["end"] > t and s["start"] < t + size]
        if segs:
            out.append((segs[0]["start"], segs[-1]["end"], " ".join(s["text"] for s in segs)))
        t += step
    return out


def index_video(video_id: str, meta: dict, org: dict) -> int:
    tr = transcribe.load(video_id)
    folder = folder_name(org)
    rows = []  # (kind, technique, position, chapter, start, end, text, note)
    for i, ch in enumerate(org["chapters"]):
        note = f"Instructionals/{folder}/{chapter_note_name(i, ch)}"
        for t in ch["techniques"]:
            spoken = transcribe.text_between(tr, t["start"], t["end"])
            text = "\n".join([
                f"{t['name']} ({t['canonical']}; also: {', '.join(t['aliases'])})",
                f"Position: {t['position']}. Category: {t['category']}. Instructor: {org['instructor']}.",
                t["summary"],
                "Steps: " + " ".join(t["steps"]),
                "Details: " + " ".join(t["key_details"]),
                "Mistakes: " + " ".join(t["common_mistakes"]),
                "Reactions: " + " ".join(t["opponent_reactions"]),
                "Said: " + spoken[:1500],
            ])
            rows.append(("technique", t["canonical"], t["position"], ch["title"], t["start"], t["end"],
                         text, f"{note}#{technique_heading(t)}"))
    for start, end, text in _windows(tr["segments"]):
        ch = next((c for c in org["chapters"] if c["start"] <= start < c["end"]), None)
        rows.append(("transcript", "", "", ch["title"] if ch else "", start, end, text,
                     f"Transcripts/{video_id}"))

    emb = _embed_docs([r[6] for r in rows]) if rows else np.zeros((0, 384), np.float32)
    con = db.connect()
    with con:
        ids = [r[0] for r in con.execute("SELECT id FROM chunks WHERE video_id=?", (video_id,))]
        con.executemany("DELETE FROM chunks_fts WHERE rowid=?", [(i,) for i in ids])
        con.execute("DELETE FROM chunks WHERE video_id=?", (video_id,))
        con.execute(
            "INSERT OR REPLACE INTO videos VALUES (?,?,?,?,?,?)",
            (video_id, org["title"], org["instructor"], meta.get("url", ""), meta.get("duration") or 0,
             f"Instructionals/{folder}"),
        )
        for r, e in zip(rows, emb):
            cur = con.execute(
                "INSERT INTO chunks (video_id, kind, technique, position, chapter, start, end, text, note, embedding)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (video_id, *r, e.tobytes()),
            )
            con.execute("INSERT INTO chunks_fts (rowid, text, technique, position, chapter) VALUES (?,?,?,?,?)",
                        (cur.lastrowid, r[6], r[1], r[2], r[3]))
    con.close()
    return len(rows)


STOPWORDS = set("""a an and are as at be but by can do does for from get how i if in into is it me my of on or
should so that the their them then they this to up use what when where which who why will with you your""".split())


def _fts_query(q: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", q.lower())
    return " OR ".join(f'"{w}"' for w in words if len(w) > 2 and w not in STOPWORDS)


def search(query: str, limit: int = 8, kind: str | None = None, video_id: str | None = None) -> list[dict]:
    con = db.connect()
    where, args = [], []
    if kind:
        where.append("c.kind=?"); args.append(kind)
    if video_id:
        where.append("c.video_id=?"); args.append(video_id)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = con.execute(
        f"SELECT c.*, v.title AS video_title, v.instructor, v.url FROM chunks c "
        f"JOIN videos v ON v.id=c.video_id {clause}", args
    ).fetchall()
    if not rows:
        con.close()
        return []
    by_id = {r["id"]: r for r in rows}

    mat = np.frombuffer(b"".join(r["embedding"] for r in rows), dtype=np.float32).reshape(len(rows), -1)
    sims = mat @ _embed_query(query)
    sem_rank = {rows[i]["id"]: rank for rank, i in enumerate(np.argsort(-sims)[:100])}
    sim_of = {rows[i]["id"]: float(sims[i]) for i in range(len(rows))}

    kw_rank = {}
    if fq := _fts_query(query):
        hits = con.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT 100", (fq,)
        ).fetchall()
        kw_rank = {h[0]: rank for rank, h in enumerate(r for r in hits if r[0] in by_id)}
    con.close()

    scores = {}
    for cid in set(sem_rank) | set(kw_rank):
        s = 1 / (60 + sem_rank.get(cid, 1000)) + 0.5 / (60 + kw_rank.get(cid, 1000))
        if by_id[cid]["kind"] == "technique":
            s *= 1.15  # structured notes are the better answer when they match
        scores[cid] = s

    results, seen = [], []
    for cid in sorted(scores, key=scores.get, reverse=True):
        r = by_id[cid]
        # skip transcript windows that mostly repeat a moment we already returned
        dur = max(1.0, r["end"] - r["start"])
        if r["kind"] == "transcript" and any(
            v == r["video_id"] and (min(r["end"], e) - max(r["start"], s)) / dur > 0.5 for v, s, e in seen
        ):
            continue
        seen.append((r["video_id"], r["start"], r["end"]))
        results.append({
            "video_id": r["video_id"], "video_title": r["video_title"], "instructor": r["instructor"],
            "kind": r["kind"], "technique": r["technique"], "position": r["position"], "chapter": r["chapter"],
            "start": r["start"], "end": r["end"], "note": r["note"], "source_url": r["url"],
            "similarity": round(sim_of[cid], 3), "text": r["text"],
        })
        if len(results) >= limit:
            break
    return results
