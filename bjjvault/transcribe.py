"""Local Whisper on Windows/Linux or Apple Silicon -> data/transcripts/<id>.json."""

import json
import subprocess
import tempfile
from pathlib import Path

from . import config


def transcribe(video_id: str, video: Path) -> dict:
    out = config.TRANSCRIPTS / f"{video_id}.json"
    if out.exists():
        return json.loads(out.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(dir=config.TMP) as tmp:
        wav = Path(tmp) / "audio.wav"
        subprocess.run(
            ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(video),
             "-vn", "-ac", "1", "-ar", "16000", str(wav)],
            check=True,
        )
        if config.USE_MLX:
            import mlx_whisper
            result = mlx_whisper.transcribe(
                str(wav), path_or_hf_repo=config.WHISPER_MODEL, word_timestamps=True,
                condition_on_previous_text=False, hallucination_silence_threshold=2.0,
            )
        else:
            from faster_whisper import WhisperModel
            model = WhisperModel(config.WHISPER_MODEL, device=config.WHISPER_DEVICE,
                                 compute_type="int8" if config.WHISPER_DEVICE == "cpu" else "float16",
                                 download_root=str(config.CACHE / "whisper"))
            stream, info = model.transcribe(str(wav), word_timestamps=True, vad_filter=True,
                                           condition_on_previous_text=False)
            result = {"language": info.language, "segments": []}
            for s in stream:
                result["segments"].append({"start": s.start, "end": s.end, "text": s.text,
                    "words": [{"word": w.word, "start": w.start, "end": w.end} for w in (s.words or [])]})

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
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def load(video_id: str) -> dict:
    return json.loads((config.TRANSCRIPTS / f"{video_id}.json").read_text(encoding="utf-8"))


def text_between(transcript: dict, start: float, end: float) -> str:
    return " ".join(s["text"] for s in transcript["segments"] if s["end"] > start and s["start"] < end)
