import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from bjjvault import clips, config, db
from bjjvault.web.mobile import app


class MobileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=config.TMP)
        self.root = Path(self.temp.name)
        self.paths = patch.multiple(config, VIDEOS=self.root/'videos', META=self.root/'meta',
            CLIPS=self.root/'clips', DB_PATH=self.root/'test.db', MOBILE_URL_FILE=self.root/'mobile-url.json',
            MOBILE_ACCESS_TOKEN_FILE=self.root/'token.txt')
        self.paths.start()
        self.env = patch.dict(os.environ)
        self.env.start()
        os.environ.pop('BJJVAULT_PUBLIC_URL', None)
        config.ensure_dirs()
        (config.VIDEOS/'demo.mp4').write_bytes(b'0123456789abcdef')
        (config.META/'demo.json').write_text(json.dumps({'duration':20}),encoding='utf-8')
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.paths.stop()
        self.temp.cleanup()

    def test_url_refreshes_without_restarting_mcp(self):
        self.assertEqual(config.playback_base_url(), config.BASE_URL)
        for origin in ('https://one.trycloudflare.com','https://two.trycloudflare.com'):
            config.MOBILE_URL_FILE.write_text(json.dumps({'url':origin}),encoding='utf-8')
            link = clips.create_link('demo',2,7)
            self.assertTrue(link['play_url'].startswith(origin+'/clip/'))
            self.assertTrue(link['phone_accessible'])
        config.MOBILE_URL_FILE.unlink()
        self.assertEqual(config.playback_base_url(), config.BASE_URL)

    def test_rejects_unsafe_public_origins(self):
        for url in ('http://example.com','https://u:p@example.com','https://example.com/path','https://example.com?token=x'):
            with self.subTest(url=url), patch.dict(os.environ,{'BJJVAULT_PUBLIC_URL':url}), self.assertRaises(ValueError):
                config.playback_base_url()

    def test_gateway_requires_authentication_for_library_and_controls(self):
        for path in ('/media/demo.mp4','/watch/demo','/assets/test.jpg','/docs','/openapi.json'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path,follow_redirects=False).status_code,303)
        self.assertEqual(self.client.get('/api/search').status_code,401)
        self.assertEqual(self.client.get('/api/jobs').status_code,401)
        self.assertEqual(self.client.post('/api/jobs',json={'url':'example'}).status_code,401)

    def test_token_required_and_expired_access_denied(self):
        self.assertEqual(self.client.get('/clip/bogus').status_code,410)
        self.assertEqual(self.client.get('/stream/bogus').status_code,410)
        token=clips.create_link('demo',2,7)['play_url'].rsplit('/',1)[1]
        self.assertEqual(self.client.get('/clip/'+token).status_code,200)
        response=self.client.get('/stream/'+token,headers={'Range':'bytes=3-6'})
        self.assertEqual(response.status_code,206)
        self.assertEqual(response.content,b'3456')
        self.assertEqual(response.headers['cache-control'],'no-store')
        c=db.connect()
        with c:
            c.execute('UPDATE stream_links SET expires=0 WHERE token=?',(token,))
        c.close()
        self.assertEqual(self.client.head('/stream/'+token).status_code,410)


if __name__ == '__main__':
    unittest.main()
