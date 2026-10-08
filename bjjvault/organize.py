"""Turn a timestamped transcript into structured notes using the local, logged-in Claude Code CLI."""

import json
import subprocess
import tempfile
from typing import Literal

from pydantic import BaseModel, Field

from . import config
from .util import fmt_ts

Category = Literal[
    "submission", "sweep", "pass", "escape", "takedown", "guard retention",
    "control", "transition", "back take", "defense", "concept", "drill", "other",
]


class Technique(BaseModel):
    name: str = Field(description="Specific name as taught, e.g. 'Kimura from closed guard with leg over head'")
    canonical: str = Field(description="Short canonical technique name in Title Case used across the whole vault, e.g. 'Kimura'")
    aliases: list[str] = Field(description="Other names people use, e.g. 'Double wristlock', 'Gyaku ude garami'")
    position: str = Field(description="Canonical starting position in Title Case, e.g. 'Closed Guard'")
    category: Category
    start: float = Field(description="Seconds where teaching of this technique begins")
    end: float = Field(description="Seconds where it ends")
    summary: str = Field(description="1-2 sentence description of what it is and when to use it")
    steps: list[str] = Field(description="Ordered, concrete step-by-step instructions, each a full sentence")
    key_details: list[str] = Field(description="The instructor's specific details, cues and 'secrets' (grips, angles, weight, timing)")
    common_mistakes: list[str]
    opponent_reactions: list[str] = Field(description="Counters/reactions mentioned and how to respond")
    related: list[str] = Field(description="Canonical names of related techniques mentioned (follow-ups, combos)")


class Chapter(BaseModel):
    title: str
    start: float
    end: float
    summary: str
    techniques: list[Technique]


class Organized(BaseModel):
    title: str = Field(description="Clean title for the instructional")
    instructor: str = Field(description="Instructor's name if identifiable, else the channel name")
    summary: str = Field(description="3-5 sentence overview of what the instructional covers and its core ideas")
    level: Literal["beginner", "intermediate", "advanced", "mixed"]
    gi: Literal["gi", "no-gi", "both", "unknown"]
    positions: list[str]
    principles: list[str] = Field(description="Overarching concepts/principles taught throughout")
    chapters: list[Chapter]


SYSTEM = """You are an expert Brazilian Jiu-Jitsu black belt and meticulous note-taker. You turn transcripts \
of BJJ instructionals into precise, well-organized study notes.

Rules:
- Every timestamp is in SECONDS and must come from the transcript's [mm:ss] markers. Technique start/end ranges must \
tightly cover where that technique is actually demonstrated/explained, so a clip of that range shows it.
- Split the video into logical chapters (use the creator's chapters if given). Inside chapters, list each distinct \
technique or variation separately; a variation taught for >30s deserves its own entry.
- Steps must be concrete and actionable (which hand, which grip, where the weight goes). Never invent details that \
aren't in the transcript; if the instructor is vague, be brief.
- Use standard English BJJ terminology even if the transcript is in another language or the speech-to-text \
mis-heard terms (e.g. 'come Ura' -> 'Kimura', 'deal a riva' -> 'De La Riva').
- Reuse existing canonical technique/position names from the vault vocabulary when they match.
- Intros, sponsor reads and outros are not techniques."""


def _vocabulary() -> tuple[list[str], list[str]]:
    techs, positions = set(), set()
    for f in config.ORGANIZED.glob("*.json"):
        data = json.loads(f.read_text())
        positions.update(data.get("positions", []))
        for ch in data.get("chapters", []):
            for t in ch.get("techniques", []):
                techs.add(t["canonical"])
                positions.add(t["position"])
    return sorted(techs), sorted(positions)


def _transcript_lines(segments: list[dict]) -> str:
    return "\n".join(f"[{fmt_ts(s['start'])}] {s['text']}" for s in segments)


def _call_claude(prompt: str) -> dict:
    cmd = [
        config.claude_bin(), "-p",
        "--output-format", "json",
        "--model", config.CLAUDE_MODEL,
        "--tools", "",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--system-prompt", SYSTEM,
        "--json-schema", json.dumps(Organized.model_json_schema()),
    ]
    last_err = ""
    for _ in range(3):
        # run from a temp dir so this repo's CLAUDE.md / settings aren't loaded
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=tmp, timeout=1800)
        try:
            out = json.loads(proc.stdout)
            if out.get("is_error"):
                raise RuntimeError(out.get("result") or "claude returned an error")
            data = out.get("structured_output") or json.loads(out["result"])
            return Organized.model_validate(data).model_dump()
        except Exception as e:  # noqa: BLE001 - retry any parse/validation failure
            last_err = f"{e}; stderr: {proc.stderr[-500:]}"
    raise RuntimeError(f"Claude organize failed: {last_err}")


PART_SECONDS = 75 * 60  # long instructionals are organized in parts to keep output detailed


def organize(video_id: str, meta: dict, transcript: dict) -> dict:
    out = config.ORGANIZED / f"{video_id}.json"
    if out.exists():
        return json.loads(out.read_text())

    techs, positions = _vocabulary()
    segs = transcript["segments"]
    parts: list[list[dict]] = []
    for s in segs:
        if not parts or s["start"] - parts[-1][0]["start"] > PART_SECONDS:
            parts.append([])
        parts[-1].append(s)

    results = []
    for i, part in enumerate(parts):
        header = [
            f"Video title: {meta.get('title')}",
            f"Channel: {meta.get('uploader')}",
            f"Duration: {fmt_ts(meta.get('duration') or segs[-1]['end'])}",
        ]
        if meta.get("playlist"):
            header.append(f"Part of series: {meta['playlist']}")
        if meta.get("description"):
            header.append(f"Description:\n{meta['description'][:1500]}")
        if meta.get("chapters"):
            header.append("Creator chapters:\n" + "\n".join(
                f"[{fmt_ts(c['start'] or 0)}] {c['title']}" for c in meta["chapters"]))
        if len(parts) > 1:
            header.append(
                f"NOTE: this is part {i + 1} of {len(parts)} of the transcript "
                f"({fmt_ts(part[0]['start'])}-{fmt_ts(part[-1]['end'])}). Only organize this part."
            )
        if techs:
            header.append("Existing vault technique names: " + ", ".join(techs[:400]))
        if positions:
            header.append("Existing vault position names: " + ", ".join(positions[:200]))
        prompt = "\n\n".join(header) + "\n\nTRANSCRIPT:\n" + _transcript_lines(part) + \
            "\n\nProduce the structured notes."
        results.append(_call_claude(prompt))

    merged = results[0]
    for r in results[1:]:
        merged["chapters"].extend(r["chapters"])
        merged["positions"] = sorted(set(merged["positions"]) | set(r["positions"]))
        merged["principles"].extend(p for p in r["principles"] if p not in merged["principles"])
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=2))
    return merged


def load(video_id: str) -> dict:
    return json.loads((config.ORGANIZED / f"{video_id}.json").read_text())
