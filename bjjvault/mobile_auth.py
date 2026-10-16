"""Persistent vault access token and short browser sessions; secrets stay in ignored data/."""
import argparse
import hashlib
import hmac
import secrets
import time

from . import config

COOKIE_NAME = '__Host-bjjvault'
SESSION_SECONDS = 7 * 24 * 60 * 60


def access_token() -> str:
    path = config.MOBILE_ACCESS_TOKEN_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('x', encoding='utf-8') as output:
            output.write(secrets.token_urlsafe(32) + '\n')
    except FileExistsError:
        pass
    value = path.read_text(encoding='utf-8').strip()
    if len(value) < 32 or not value.isascii():
        raise RuntimeError('Invalid mobile access token file; rotate it locally.')
    return value


def valid_token(value: str) -> bool:
    return bool(value and value.isascii() and len(value) <= 256 and
                hmac.compare_digest(value, access_token()))


def session_cookie() -> str:
    payload = f'{int(time.time()) + SESSION_SECONDS}.{secrets.token_hex(12)}'
    signature = hmac.new(access_token().encode(), ('session:' + payload).encode(), hashlib.sha256).hexdigest()
    return payload + '.' + signature


def valid_session(value: str) -> bool:
    try:
        expires, nonce, signature = value.split('.')
        if len(nonce) != 24 or len(signature) != 64 or int(expires) <= time.time():
            return False
        expected = hmac.new(access_token().encode(), f'session:{expires}.{nonce}'.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    except (ValueError, TypeError):
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--link', action='store_true', help='Print a private sign-in link for the current tunnel')
    parser.add_argument('--rotate', action='store_true', help='Replace the token and invalidate existing browser sessions')
    args = parser.parse_args()
    if args.rotate:
        temporary = config.MOBILE_ACCESS_TOKEN_FILE.with_suffix('.tmp')
        temporary.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(secrets.token_urlsafe(32) + '\n', encoding='utf-8')
        temporary.replace(config.MOBILE_ACCESS_TOKEN_FILE)
    token = access_token()
    if args.link:
        origin = config.playback_base_url()
        if origin == config.BASE_URL:
            raise RuntimeError('Start mobile access before requesting a phone sign-in link.')
        # Fragments are not sent in HTTP requests, server logs, or Referer headers.
        print(f'{origin}/login#token={token}')


if __name__ == '__main__':
    main()
