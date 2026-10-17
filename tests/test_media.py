import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from bjjvault import config
from bjjvault.media import validate_video


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg required')
class MediaTests(unittest.TestCase):
    def test_truncated_mp4_is_rejected_even_when_its_header_has_full_duration(self):
        with tempfile.TemporaryDirectory(dir=config.TMP) as directory:
            good = Path(directory) / 'good.mp4'
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                            'testsrc2=size=96x64:rate=10', '-t', '2', '-c:v', 'libx264',
                            '-movflags', '+faststart', str(good)], check=True)
            validate_video(good, 2)
            bad = Path(directory) / 'truncated.mp4'
            data = good.read_bytes()
            bad.write_bytes(data[:len(data) // 2])
            with self.assertRaises((ValueError, subprocess.SubprocessError)):
                validate_video(bad, 2)
            with self.assertRaises(ValueError):
                validate_video(good, 120)
