import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from bjjvault import config, db, index, library, thumbnails
from bjjvault.web.app import app


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=config.TMP)
        root = Path(self.temp.name)
        self.paths = patch.multiple(config, DB_PATH=root/'vault.db', THUMBNAILS=root/'thumbnails',
                                    VIDEOS=root/'videos')
        self.paths.start()
        config.ensure_dirs()
        self.client = TestClient(app)  # No lifespan: do not start an ingestion worker.
        con = db.connect()
        with con:
            for vid, title in [('bilibili-demo_p1', 'Inside Leglocks — Part 1'),
                               ('bilibili-demo_p2', 'Inside Leglocks, Part 2'),
                               ('bilibili-other', 'Passing')]:
                con.execute('INSERT INTO videos VALUES (?,?,?,?,?,?)', (vid, title, 'Instructor', '', 60, ''))
                text = 'K guard leglock entry'
                cur = con.execute('INSERT INTO chunks (video_id,kind,start,end,text,embedding) VALUES (?,?,?,?,?,?)',
                                  (vid, 'transcript', 0, 30, text, np.array([1, 0], dtype=np.float32).tobytes()))
                con.execute('INSERT INTO chunks_fts (rowid,text) VALUES (?,?)', (cur.lastrowid, text))
        con.close()

    def tearDown(self):
        self.client.close()
        self.paths.stop()
        self.temp.cleanup()

    def test_groups_parts_and_uses_saved_thumbnail(self):
        (config.THUMBNAILS/'bilibili-demo_p2.jpg').write_bytes(b'cover')
        groups = library.instructionals()
        self.assertEqual(len(groups), 2)
        group = next(i for i in groups if i['id'] == 'bilibili-demo')
        self.assertEqual(group['title'], 'Inside Leglocks')
        self.assertEqual(group['video_ids'], ['bilibili-demo_p1', 'bilibili-demo_p2'])
        self.assertEqual(group['thumbnail'], '/thumbnails/bilibili-demo_p2.jpg')
        page = self.client.get('/')
        self.assertIn('data-instructional="bilibili-demo"', page.text)
        self.assertIn('/thumbnails/bilibili-demo_p2.jpg', page.text)

    @patch.object(index, '_embed_query', return_value=np.array([1, 0], dtype=np.float32))
    def test_selected_instructional_only_returns_its_parts(self, embed):
        response = self.client.get('/api/search', params={'q': 'K guard', 'instructional_id': 'bilibili-demo'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual({r['video_id'] for r in response.json()}, {'bilibili-demo_p1', 'bilibili-demo_p2'})
        self.assertEqual(len(self.client.get('/api/search?q=K%20guard').json()), 3)
        self.assertEqual(self.client.get('/api/search?q=guard&instructional_id=missing').status_code, 404)
        self.assertEqual(index.search('guard', video_ids=[]), [])
        self.assertEqual({r['video_id'] for r in index.search('guard', video_id='bilibili-other')}, {'bilibili-other'})

    def test_cover_cache_does_not_require_source_or_ffmpeg(self):
        path = config.THUMBNAILS/'cached.jpg'
        path.write_bytes(b'cached cover')
        with patch.object(thumbnails.subprocess, 'run') as run:
            self.assertEqual(thumbnails.ensure('cached'), path)
            run.assert_not_called()
        with self.assertRaises(ValueError):
            thumbnails.ensure('../outside')
