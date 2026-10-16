"""Authenticated mobile gateway to the local vault, plus scoped temporary clip links."""
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from starlette.background import BackgroundTask
from .playback import router
from .. import config, mobile_auth

app = FastAPI(title="BJJ Vault mobile", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(router)


@app.middleware('http')
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    response.headers['X-Frame-Options'] = 'DENY'
    return response


def same_origin(request: Request) -> bool:
    origin = request.headers.get('origin')
    if origin is None:
        return True
    parsed = urlsplit(origin)
    return parsed.scheme in ('http', 'https') and parsed.netloc.lower() == request.headers.get('host', '').lower()


@app.get('/healthz')
def health():
    return {'ok': True}


@app.get('/login', response_class=HTMLResponse)
def login_page():
    return HTMLResponse('''<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Unlock BJJ Vault</title><style>body{background:#141413;color:#ecebe7;font:17px system-ui;margin:0}
main{max-width:26rem;margin:12vh auto;padding:24px}input,button{box-sizing:border-box;width:100%;font:inherit;padding:14px;margin:8px 0;border-radius:8px;border:1px solid #555}
button{background:#7c9cff;color:#111;cursor:pointer}p{color:#bbb}</style><main><h1>Unlock BJJ Vault</h1>
<p id="message">Enter your private access token to open your library.</p>
<form id="login" method="post" action="/login"><label for="token">Access token</label>
<input id="token" name="token" type="password" autocomplete="off" required maxlength="256"><button>Open vault</button></form>
<form method="post" action="/logout"><button>Sign out of this browser</button></form></main>
<script>const form=document.getElementById('login');
form.addEventListener('submit',async event=>{event.preventDefault();
try{const response=await fetch('/login',{method:'POST',credentials:'same-origin',headers:{Accept:'application/json'},body:new URLSearchParams(new FormData(form))});
if(response.ok){location.replace('/');}else{const result=await response.json();document.getElementById('message').textContent=result.detail||'Could not sign in.';}}
catch(error){document.getElementById('message').textContent='Could not connect. Please try again.';}});
const token=new URLSearchParams(location.hash.slice(1)).get('token');
if(token){history.replaceState(null,'','/login');document.getElementById('token').value=token;form.requestSubmit();}</script></html>''')


@app.post('/login')
async def login(request: Request):
    if not same_origin(request):
        return JSONResponse({'detail': 'Cross-site sign-in rejected'}, status_code=403)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 2048:
            return JSONResponse({'detail': 'Sign-in request too large'}, status_code=413)
        body.extend(chunk)
    try:
        form = parse_qs(body.decode('utf-8'), max_num_fields=2)
    except (ValueError, UnicodeError):
        return JSONResponse({'detail': 'Invalid sign-in form'}, status_code=400)
    if not mobile_auth.valid_token(form.get('token', [''])[0]):
        return JSONResponse({'detail': 'Invalid access token. Open /login to try again.'}, status_code=401)
    response = JSONResponse({'ok': True}) if 'application/json' in request.headers.get('accept', '') else RedirectResponse('/', status_code=303)
    response.set_cookie(mobile_auth.COOKIE_NAME, mobile_auth.session_cookie(),
        max_age=mobile_auth.SESSION_SECONDS, secure=True, httponly=True, samesite='strict', path='/')
    return response


@app.post('/logout')
def logout(request: Request):
    if not same_origin(request):
        return JSONResponse({'detail': 'Cross-site request rejected'}, status_code=403)
    response = RedirectResponse('/login', status_code=303)
    response.delete_cookie(mobile_auth.COOKIE_NAME, secure=True, httponly=True, samesite='strict', path='/')
    return response


HOP_HEADERS = {'host','connection','keep-alive','proxy-authenticate','proxy-authorization',
               'te','trailer','transfer-encoding','upgrade'}


@app.api_route('/{path:path}', methods=['GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS'])
async def vault(request: Request, path: str):
    bearer = request.headers.get('authorization', '')
    bearer_ok = bearer.startswith('Bearer ') and mobile_auth.valid_token(bearer[7:])
    cookie_ok = mobile_auth.valid_session(request.cookies.get(mobile_auth.COOKIE_NAME, ''))
    if not (bearer_ok or cookie_ok):
        if request.method in ('GET','HEAD') and not path.startswith('api/'):
            return RedirectResponse('/login', status_code=303)
        return JSONResponse({'detail': 'Access token required'}, status_code=401)
    if request.method not in ('GET','HEAD','OPTIONS') and not same_origin(request):
        return JSONResponse({'detail': 'Cross-site request rejected'}, status_code=403)
    if path in ('docs', 'redoc', 'openapi.json'):
        return JSONResponse({'detail': 'Not found'}, status_code=404)
    # Construct against a fixed loopback origin: request paths can never select another host.
    url = httpx.URL(f'http://127.0.0.1:{config.PORT}').copy_with(
        path='/' + path, query=request.url.query.encode())
    headers = {k:v for k,v in request.headers.items()
               if k.lower() not in HOP_HEADERS | {'authorization','cookie','content-length'}}
    client = httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5), trust_env=False)
    try:
        upstream = await client.send(client.build_request(request.method, url,
            headers=headers, content=request.stream()), stream=True)
    except httpx.HTTPError:
        await client.aclose()
        return JSONResponse({'detail': 'The local vault is offline. Start-Vault.ps1 on the PC.'}, status_code=502)
    response_headers = {k:v for k,v in upstream.headers.items()
                        if k.lower() not in HOP_HEADERS | {'set-cookie'}}

    async def close():
        await upstream.aclose()
        await client.aclose()

    return StreamingResponse(upstream.aiter_raw(), status_code=upstream.status_code,
                             headers=response_headers, background=BackgroundTask(close))


def main():
    import uvicorn
    mobile_auth.access_token()
    uvicorn.run(app, host="127.0.0.1", port=config.MOBILE_PORT, access_log=False)


if __name__ == "__main__":
    main()
