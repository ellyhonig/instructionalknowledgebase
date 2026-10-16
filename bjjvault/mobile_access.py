"""Supervise an authenticated mobile gateway and a temporary Cloudflare HTTPS tunnel."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from . import config


def _write_json(path: Path, data: dict):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data), encoding='utf-8')
    temporary.replace(path)


def main():
    config.ensure_dirs()
    logs = config.DATA / 'logs'
    logs.mkdir(exist_ok=True)
    binary = config.ROOT / '.tools' / 'cloudflared.exe'
    if not binary.is_file():
        raise RuntimeError('Run Start-Mobile.ps1 to install the portable tunnel binary.')
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    gateway = tunnel = None
    state_path = config.DATA / 'mobile-processes.json'
    config.MOBILE_URL_FILE.unlink(missing_ok=True)
    try:
        with (logs/'mobile-gateway.log').open('a', encoding='utf-8') as gateway_log:
            gateway = subprocess.Popen([sys.executable, '-X', 'utf8', '-m', 'bjjvault.web.mobile'],
                cwd=config.ROOT, stdout=gateway_log, stderr=gateway_log, creationflags=flags)
            for _ in range(40):
                if gateway.poll() is not None:
                    raise RuntimeError('Mobile gateway stopped; check data/logs/mobile-gateway.log.')
                try:
                    if requests.get(f'http://127.0.0.1:{config.MOBILE_PORT}/healthz', timeout=1).status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(.25)
            else:
                raise RuntimeError('Mobile gateway did not start.')
            tunnel = subprocess.Popen([str(binary), '--no-autoupdate', 'tunnel', '--url',
                f'http://127.0.0.1:{config.MOBILE_PORT}', '--protocol', 'http2'],
                cwd=config.ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='replace', creationflags=flags)
            _write_json(state_path, {'supervisor_pid': os.getpid(), 'gateway_pid': gateway.pid,
                                    'tunnel_pid': tunnel.pid})
            with (logs/'mobile-tunnel.log').open('a', encoding='utf-8') as tunnel_log:
                for line in tunnel.stderr:
                    tunnel_log.write(line)
                    tunnel_log.flush()
                    if gateway.poll() is not None:
                        raise RuntimeError('Mobile gateway stopped.')
                    if match := re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line):
                        url = match.group(0)
                        _write_json(config.MOBILE_URL_FILE, {'url': url, 'supervisor_pid': os.getpid()})
                        print(f'Mobile clip access: {url}', flush=True)
                raise RuntimeError(f'Tunnel stopped with exit code {tunnel.wait()}.')
    finally:
        config.MOBILE_URL_FILE.unlink(missing_ok=True)
        for process in (tunnel, gateway):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        state_path.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
