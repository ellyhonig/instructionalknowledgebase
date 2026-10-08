"""Local Whisper (mlx, runs on Apple Silicon GPU) -> data/transcripts/<id>.json."""

import json
import subprocess
import tempfile
from pathlib import Path

from . import config


def transcribe(video_id: str, video: Path) -> dict:
    out = config.TRANSCRIPTS / f"{video_id}.json"
    if out.exists():
        return json.loads(out.read_text())

    import mlx_whisper  # heavy import; only when needed

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        subprocess.run(
            ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(video),
             "-vn", "-ac", "1", "-ar", "16000", str(wav)],
            check=True,
        )
        result = mlx_whisper.transcribe(
            str(wav),
            path_or_hf_repo=config.WHISPER_MODEL,
            word_timestamps=True,
            condition_on_previous_text=False,  # avoids runaway repetition on long videos
            hallucination_silence_threshold=2.0,
        )

    segments = [
        {
            "start": round(s["start"], 2),
            "end": round(s["end"], 2),
            "text": s["text"].strip(),
            "words": [
                {"w": w["word"], "s": round(w["start"], 2), "e": round(w["end"], 2)}
                for w in s.get("words", [])
            ],
        }
        for s in result["segments"]
        if s["text"].strip()
    ]
    data = {"video_id": video_id, "language": result.get("language"), "segments": segments}
    out.write_text(json.dumps(data, ensure_ascii=False))
    return data


def load(video_id: str) -> dict:
    return json.loads((config.TRANSCRIPTS / f"{video_id}.json").read_text())


def text_between(transcript: dict, start: float, end: float) -> str:
    return " ".join(s["text"] for s in transcript["segments"] if s["end"] > start and s["start"] < end)
