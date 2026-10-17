"""Check decoded frames, rather than trusting an MP4 header's duration."""
import json
import subprocess
from pathlib import Path


def validate_video(path: Path, expected_duration: float = 0) -> None:
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                            'format=duration:stream=codec_type', '-of', 'json', str(path)],
                           capture_output=True, text=True, timeout=30, check=True)
    info = json.loads(probe.stdout)
    duration = float(info.get('format', {}).get('duration') or 0)
    if duration <= 0 or not any(s.get('codec_type') == 'video' for s in info.get('streams', [])):
        raise ValueError(f'{path.name}: missing video or duration')
    if expected_duration and duration < expected_duration - max(2, expected_duration * .01):
        raise ValueError(f'{path.name}: video is shorter than its source')
    for fraction in (.1, .5, .9):
        at = max(0, min(duration * fraction, duration - .1))
        decoded = subprocess.run(
            ['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-ss', str(at), '-i', str(path),
             '-map', '0:v:0', '-frames:v', '1', '-f', 'framemd5', '-'],
            capture_output=True, text=True, timeout=40,
        )
        frames = [line for line in decoded.stdout.splitlines() if line.strip() and not line.startswith('#')]
        if decoded.returncode or not frames:
            raise ValueError(f'{path.name}: video does not decode at {at:.1f}s; retry the download')
