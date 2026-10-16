"""Resumable, verified HTTP ranges for Bilibili CDNs that frequently drop large responses."""
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import requests


def fetch(urls: list[str], destination: Path, cache: Path, headers: dict,
          progress: Callable[[str], None] | None = None, seed: Path | None = None,
          chunk_size: int = 256 * 1024, workers: int = 4) -> Path:
    """Cache small byte ranges, resume partial responses, and assemble only verified bytes."""
    total = None
    usable = []
    for url in urls:
        try:
            with requests.get(url, headers={**headers, 'Range': 'bytes=0-0', 'Accept-Encoding': 'identity'},
                              timeout=(10, 15), stream=True) as response:
                response.raise_for_status()
                match = re.fullmatch(r'bytes 0-0/(\d+)', response.headers.get('Content-Range', ''))
                if response.status_code != 206 or not match:
                    continue
                size = int(match.group(1))
                if total is None:
                    total = size
                if size == total:
                    usable.append(url)
        except requests.RequestException:
            continue
    if not usable or not total:
        raise RuntimeError('No usable byte-range playback mirror. Retry to refresh Bilibili playback URLs.')
    cache = cache / str(total)
    cache.mkdir(parents=True, exist_ok=True)
    starts = list(range(0, total, chunk_size))
    if seed is not None and seed.is_file():
        with seed.open('rb') as source:
            for start in starts:
                data = source.read(min(chunk_size, total-start))
                if len(data) != min(chunk_size, total-start):
                    break
                part = cache / f'{start}.bin'
                if not part.exists():
                    part.write_bytes(data)

    lock = threading.Lock()
    complete = 0

    def one(start):
        nonlocal complete
        end = min(start + chunk_size, total) - 1
        expected = end-start+1
        part = cache / f'{start}.bin'
        if not part.exists() or part.stat().st_size != expected:
            temporary = part.with_suffix('.partial')
            if temporary.exists() and temporary.stat().st_size > expected:
                temporary.unlink()
            for attempt in range(8):
                have = temporary.stat().st_size if temporary.exists() else 0
                if have == expected:
                    temporary.replace(part)
                    break
                try:
                    with requests.get(usable[attempt % len(usable)],
                        headers={**headers, 'Range': f'bytes={start+have}-{end}', 'Accept-Encoding': 'identity'},
                        timeout=(10, 15), stream=True) as response:
                        response.raise_for_status()
                        if response.status_code != 206 or response.headers.get('Content-Range') != f'bytes {start+have}-{end}/{total}':
                            raise RuntimeError('CDN returned an unexpected byte range')
                        with temporary.open('ab') as output:
                            for data in response.iter_content(16*1024):
                                if output.tell()+len(data) > expected:
                                    raise RuntimeError('CDN exceeded the requested byte range')
                                output.write(data)
                    if temporary.stat().st_size == expected:
                        temporary.replace(part)
                        break
                except (requests.RequestException, RuntimeError):
                    if attempt == 7:
                        raise RuntimeError(f'Bilibili interrupted range {start}-{end}; partial progress is cached.') from None
            else:
                raise RuntimeError(f'Bilibili range {start}-{end} remains incomplete; retry resumes it.')
        with lock:
            complete += 1
            if progress and (complete % 16 == 0 or complete == len(starts)):
                progress(f'downloading {complete/len(starts):.1%} (resumable ranges)')
        return part

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, starts))
    destination.parent.mkdir(parents=True, exist_ok=True)
    assembling = destination.with_suffix(destination.suffix+'.assembling')
    with assembling.open('wb') as output:
        for start in starts:
            output.write((cache/f'{start}.bin').read_bytes())
    if assembling.stat().st_size != total:
        raise RuntimeError('Assembled download size mismatch')
    assembling.replace(destination)
    return destination
