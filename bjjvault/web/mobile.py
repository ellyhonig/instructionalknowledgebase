"""Clip-only HTTP origin for the HTTPS tunnel. No library, media mounts, or ingestion tools."""
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from .playback import router
from .. import config

app = FastAPI(title="BJJ Vault clips", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(router)


@app.get("/", response_class=HTMLResponse)
def ready():
    return HTMLResponse('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>BJJ Vault</title><main style="max-width:36rem;margin:3rem auto;padding:1rem;font:18px system-ui">'
        '<h1>BJJ Vault is reachable</h1><p>Ask your PC-connected Codex chat for a temporary clip link, '
        'then tap the link to play it here.</p></main>', headers={"Cache-Control": "no-store"})


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=config.MOBILE_PORT, access_log=False)


if __name__ == "__main__":
    main()
