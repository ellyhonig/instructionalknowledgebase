import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from bjjvault import clips, config, db
from bjjvault.web.app import app


class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=config.TMP)
        root = Path(self.temp.name)
        self.paths = patch.multiple(config, VIDEOS=root/'videos', META=root/'meta',
                                   DB_PATH=root/'test.db', CLIPS=root/'clips', MOBILE_URL_FILE=root/'mobile-url.json')
        self.paths.start()
        config.ensure_dirs()
        (config.VIDEOS/'demo.mp4').write_bytes(b'0123456789abcdef')
        (config.META/'demo.json').write_text(json.dumps({'duration': 20}), encoding='utf-8')
        # Do not enter lifespan; no background ingestion worker is needed for these requests.
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.paths.stop()
        self.temp.cleanup()

    def test_link_range_head_and_no_export(self):
        result = clips.create_link('demo', 2, 7)
        path = result['play_url'].split(config.BASE_URL)[1]
        token = path.rsplit('/', 1)[1]
        page = self.client.get(path)
        self.assertEqual(page.status_code, 200)
        self.assertIn('const start = 2.0, end = 7.0', page.text)
        response = self.client.get('/stream/'+token, headers={'Range': 'bytes=2-5'})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b'2345')
        self.assertEqual(response.headers['content-range'], 'bytes 2-5/16')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        head = self.client.head('/stream/'+token)
        self.assertEqual(head.status_code, 200)
        self.assertEqual(head.content, b'')
        self.assertEqual(list(config.CLIPS.iterdir()), [])

    def test_expiry_blocks_both_player_and_media(self):
        token = clips.create_link('demo', 2, 7)['play_url'].rsplit('/',1)[1]
        con = db.connect()
        with con:
            con.execute('UPDATE stream_links SET expires=0 WHERE token=?', (token,))
        con.close()
        self.assertEqual(self.client.get('/clip/'+token).status_code, 410)
        self.assertEqual(self.client.get('/stream/'+token).status_code, 410)
        self.assertEqual(self.client.get('/stream/invalid').status_code, 410)

    def test_invalid_ranges_and_ids(self):
        for start,end in [(-1,4),(4,4),(7,2),(0,21),(0,float('inf')),(float('nan'),4)]:
            with self.subTest(start=start,end=end), self.assertRaises(ValueError):
                clips.create_link('demo',start,end)
        with self.assertRaises(ValueError):
            clips.create_link('../demo',0,4)
        with self.assertRaises(FileNotFoundError):
            clips.create_link('missing',0,4)


if __name__ == '__main__':
    unittest.main()
