"""Queue supplied links once; report each expansion failure without stopping the batch."""
import json
from pathlib import Path
from bjjvault import config, db, pipeline

report = []
previous = config.DATA / 'batch-report.json'
old = json.loads(previous.read_text(encoding='utf-8')) if previous.exists() else []
for url in (config.ROOT / 'instructionals.txt').read_text(encoding='utf-8').splitlines():
    if not url.strip():
        continue
    try:
        # Expansion normalizes URLs, so preserve the mapping for repeatable batch runs.
        match = next((r for r in old if r['url'] == url and r.get('jobs')), None)
        result = match or {'url': url, 'jobs': pipeline.enqueue(url)}
    except Exception as exc:
        result = {'url': url, 'error': str(exc)}
    report.append(result)
    (config.DATA / 'batch-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)
