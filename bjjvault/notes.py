"""Write the Obsidian vault: per-instructional notes + cross-linked Technique / Position / Instructor hubs."""

import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

from . import config, transcribe
from .util import fmt_ts, player_url, safe_name, source_url

START, END = "<!-- bjjvault:start -->", "<!-- bjjvault:end -->"


def _fm(d: dict) -> str:
    lines = ["---"]
    for k, v in d.items():
        lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def _write_managed(path: Path, frontmatter: dict, body: str) -> None:
    """Regenerate our section but keep anything the user wrote below the end marker."""
    user = "\n\n## My notes\n\n"
    if path.exists():
        old = path.read_text(encoding="utf-8")
        if END in old:
            user = old.split(END, 1)[1]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{_fm(frontmatter)}\n{START}\n{body.rstrip()}\n{END}{user}", encoding="utf-8")


def folder_name(org: dict) -> str:
    return safe_name(f"{org['instructor']} — {org['title']}", 110)


def chapter_note_name(i: int, ch: dict) -> str:
    return safe_name(f"{i + 1:02d} — {ch['title']}", 90)


def technique_heading(t: dict) -> str:
    m, sec = divmod(int(t["start"]), 60)
    return safe_name(f"{t['name']} @ {m}m{sec:02d}s", 120)


def _links(video_id: str, url: str, start: float, end: float) -> str:
    out = f"[▶ {fmt_ts(start)}–{fmt_ts(end)}]({player_url(video_id, start, end)})"
    if url:
        out += f" · [↗ source]({source_url(url, start)})"
    return out


def _thumbnail(video_id: str, t: dict) -> str | None:
    assets = config.VAULT / "Assets"
    assets.mkdir(parents=True, exist_ok=True)
    name = f"{video_id}-{int(t['start'])}.jpg"
    out = assets / name
    if not out.exists():
        at = t["start"] + max(1.0, (t["end"] - t["start"]) * 0.4)
        video = config.VIDEOS / f"{video_id}.mp4"
        r = subprocess.run(
            ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", f"{at:.2f}", "-i", str(video),
             "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4", str(out)],
        )
        if r.returncode or not out.exists():
            return None
    return name


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items)


def write_instructional(video_id: str, meta: dict, org: dict) -> Path:
    folder = config.VAULT / "Instructionals" / folder_name(org)
    folder.mkdir(parents=True, exist_ok=True)
    url = meta.get("url", "")
    rel = f"Instructionals/{folder.name}"

    # chapter notes
    for i, ch in enumerate(org["chapters"]):
        parts = [
            f"# {ch['title']}",
            f"Part of [[{rel}/_Overview|{org['title']}]] · {_links(video_id, url, ch['start'], ch['end'])}",
            ch["summary"],
        ]
        for t in ch["techniques"]:
            thumb = _thumbnail(video_id, t)
            sec = [f"## {technique_heading(t)}"]
            sec.append(
                f"**[[{safe_name(t['canonical'])}]]** · from [[{safe_name(t['position'])}]] · "
                f"`{t['category']}` · {_links(video_id, url, t['start'], t['end'])}"
            )
            if thumb:
                sec.append(f"![[{thumb}|480]]")
            sec.append(t["summary"])
            if t["steps"]:
                sec.append("### Steps\n" + "\n".join(f"{n}. {s}" for n, s in enumerate(t["steps"], 1)))
            if t["key_details"]:
                sec.append("### Key details\n" + _bullets(t["key_details"]))
            if t["common_mistakes"]:
                sec.append("### Common mistakes\n" + _bullets(t["common_mistakes"]))
            if t["opponent_reactions"]:
                sec.append("### Reactions & counters\n" + _bullets(t["opponent_reactions"]))
            if t["related"]:
                sec.append("**Related:** " + ", ".join(f"[[{safe_name(r)}]]" for r in t["related"]))
            parts.append("\n\n".join(sec))
        fm = {
            "type": "chapter", "instructional": org["title"], "instructor": org["instructor"],
            "video_id": video_id, "start": ch["start"], "end": ch["end"],
            "tags": ["bjj/chapter"],
        }
        _write_managed(folder / f"{chapter_note_name(i, ch)}.md", fm, "\n\n".join(parts))

    # overview
    rows = ["| Time | Technique | Position | Type |", "|---|---|---|---|"]
    for i, ch in enumerate(org["chapters"]):
        for t in ch["techniques"]:
            link = f"[[{rel}/{chapter_note_name(i, ch)}#{technique_heading(t)}\\|{t['name'].replace('|', '/')}]]"
            rows.append(
                f"| [{fmt_ts(t['start'])}]({player_url(video_id, t['start'], t['end'])}) | {link} "
                f"| [[{safe_name(t['position'])}]] | {t['category']} |"
            )
    chapters = "\n".join(
        f"{i + 1}. [[{rel}/{chapter_note_name(i, ch)}|{ch['title']}]] — "
        f"[{fmt_ts(ch['start'])}]({player_url(video_id, ch['start'], ch['end'])})"
        for i, ch in enumerate(org["chapters"])
    )
    body = "\n\n".join([
        f"# {org['title']}",
        f"**Instructor:** [[{safe_name(org['instructor'])}]] · **Level:** {org['level']} · **{org['gi']}** · "
        f"**Length:** {fmt_ts(meta.get('duration') or 0)}",
        f"[▶ Watch locally]({player_url(video_id, 0)})" + (f" · [↗ Original]({url})" if url else "")
        + f" · [[Transcripts/{video_id}|Full transcript]]",
        "## Summary\n" + org["summary"],
        "## Principles\n" + _bullets(org["principles"]) if org["principles"] else "",
        "## Chapters\n" + chapters,
        "## Techniques\n" + "\n".join(rows),
    ])
    fm = {
        "type": "instructional", "title": org["title"], "instructor": org["instructor"],
        "source": url, "video_id": video_id, "duration": meta.get("duration"),
        "level": org["level"], "gi": org["gi"], "series": meta.get("playlist"),
        "positions": org["positions"], "tags": ["bjj/instructional"],
    }
    _write_managed(folder / "_Overview.md", fm, body)
    write_transcript(video_id, meta, org)
    return folder


def write_transcript(video_id: str, meta: dict, org: dict) -> None:
    tr = transcribe.load(video_id)
    paras, cur = [], []
    for s in tr["segments"]:
        if cur and (s["start"] - cur[0]["start"] > 45 or len(cur) >= 8):
            paras.append(cur)
            cur = []
        cur.append(s)
    if cur:
        paras.append(cur)
    body = [f"# Transcript — {org['title']}", f"[[Instructionals/{folder_name(org)}/_Overview|Back to overview]]"]
    for p in paras:
        body.append(f"[**{fmt_ts(p[0]['start'])}**]({player_url(video_id, p[0]['start'])}) "
                    + " ".join(s["text"] for s in p))
    fm = {"type": "transcript", "video_id": video_id, "language": tr.get("language"), "tags": ["bjj/transcript"]}
    _write_managed(config.VAULT / "Transcripts" / f"{video_id}.md", fm, "\n\n".join(body))


def _all_organized() -> list[tuple[str, dict, dict]]:
    out = []
    for f in sorted(config.ORGANIZED.glob("*.json")):
        vid = f.stem
        meta_f = config.META / f"{vid}.json"
        meta = json.loads(meta_f.read_text(encoding="utf-8")) if meta_f.exists() else {}
        out.append((vid, meta, json.loads(f.read_text(encoding="utf-8"))))
    return out


def rebuild_hubs() -> None:
    """Regenerate Technique / Position / Instructor hub notes and Home.md from every organized video."""
    techniques: dict[str, list] = defaultdict(list)
    tech_names: dict[str, str] = {}
    aliases: dict[str, set] = defaultdict(set)
    related: dict[str, set] = defaultdict(set)
    positions: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    instructors: dict[str, list] = defaultdict(list)
    vids = _all_organized()

    for vid, meta, org in vids:
        rel = f"Instructionals/{folder_name(org)}"
        instructors[safe_name(org["instructor"])].append((rel, org, meta))
        for i, ch in enumerate(org["chapters"]):
            for t in ch["techniques"]:
                key = safe_name(t["canonical"]).lower()
                tech_names.setdefault(key, safe_name(t["canonical"]))
                aliases[key].update(a for a in t["aliases"] if a)
                related[key].update(safe_name(r) for r in t["related"])
                techniques[key].append((vid, meta, org, rel, chapter_note_name(i, ch), t))
                positions[safe_name(t["position"])][t["category"]].add(tech_names[key])

    for key, entries in techniques.items():
        name = tech_names[key]
        pos = sorted({safe_name(e[5]["position"]) for e in entries})
        body = [f"# {name}", "**Positions:** " + ", ".join(f"[[{p}]]" for p in pos)]
        if aliases[key]:
            body.append("**Also called:** " + ", ".join(sorted(aliases[key])))
        body.append(f"## Taught in ({len(entries)})")
        for vid, meta, org, rel, chap, t in entries:
            body.append(
                f"### {org['instructor']} — {t['name']}\n"
                f"[[{rel}/{chap}#{technique_heading(t)}|Open notes]] · from [[{safe_name(t['position'])}]] · "
                f"{_links(vid, meta.get('url', ''), t['start'], t['end'])}\n\n{t['summary']}"
                + ("\n\n" + _bullets(t["key_details"][:6]) if t["key_details"] else "")
            )
        rel_links = sorted(r for r in related[key] if r.lower() != key)
        if rel_links:
            body.append("## Related\n" + ", ".join(f"[[{r}]]" for r in rel_links))
        _write_managed(
            config.VAULT / "Techniques" / f"{name}.md",
            {"type": "technique", "aliases": sorted(aliases[key]), "positions": pos, "tags": ["bjj/technique"]},
            "\n\n".join(body),
        )

    for pos, cats in positions.items():
        body = [f"# {pos}"]
        for cat in sorted(cats):
            body.append(f"## {cat.title()}\n" + _bullets([f"[[{n}]]" for n in sorted(cats[cat])]))
        _write_managed(config.VAULT / "Positions" / f"{pos}.md", {"type": "position", "tags": ["bjj/position"]},
                       "\n\n".join(body))

    for name, items in instructors.items():
        body = [f"# {name}", "## Instructionals"] + [
            f"- [[{rel}/_Overview|{org['title']}]] ({org['level']}, {fmt_ts(meta.get('duration') or 0)})"
            for rel, org, meta in items
        ]
        _write_managed(config.VAULT / "Instructors" / f"{name}.md", {"type": "instructor", "tags": ["bjj/instructor"]},
                       "\n\n".join(body))

    home = [
        "# BJJ Vault",
        f"{len(vids)} instructionals · {len(techniques)} techniques · {len(positions)} positions",
        "## Instructionals\n" + _bullets(
            [f"[[Instructionals/{folder_name(o)}/_Overview|{o['instructor']} — {o['title']}]]" for _, _, o in vids]),
        "## Positions\n" + _bullets([f"[[{p}]]" for p in sorted(positions)]),
        "## Techniques\n" + _bullets([f"[[{tech_names[k]}]]" for k in sorted(tech_names)]),
    ]
    _write_managed(config.VAULT / "Home.md", {"type": "home"}, "\n\n".join(home))


def remove_stale(video_id: str) -> None:
    """Delete generated note files for a video (used before re-organizing)."""
    for f in (config.VAULT / "Instructionals").rglob("*.md") if (config.VAULT / "Instructionals").exists() else []:
        if re.search(rf'^video_id: "{re.escape(video_id)}"$', f.read_text(encoding="utf-8"), re.M):
            f.unlink()
