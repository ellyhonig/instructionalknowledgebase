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

    def test_series_numbering_keeps_name_and_ignores_versions(self):
        cases = {
            'Body Lock System 1: Grips, Entries, and Control': ('Body Lock System', 1),
            'Body Lock System 3: Top Half Guard': ('Body Lock System', 3),
            'Inside Leglocks — Part 02: Finishes': ('Inside Leglocks', 2),
            'Inside Leglocks Vol. 3': ('Inside Leglocks', 3),
            'Inside Leglocks Pt1': ('Inside Leglocks', 1),
            'Inside Leglocks Disc 2': ('Inside Leglocks', 2),
            'Guard Retention 2.0': ('Guard Retention 2.0', None),
            'BJJ 101': ('BJJ 101', None),
            'Training 2026': ('Training 2026', None),
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(library._series(title), expected)

    @patch.object(index, '_embed_query', return_value=np.array([1, 0], dtype=np.float32))
    def test_separate_uploads_merge_in_part_order_and_search_all_parts(self, embed):
        videos = [
            ('body-three', 'Body Lock System 3: Top Half Guard', 'Nick Rodriguez'),
            ('body-one', 'Body Lock System 1: Grips', 'Nick Rodriguez'),
            ('body-other-instructor', 'Body Lock System 2: Entries', 'Other Instructor'),
            ('different-series', 'Outside Passing Part 1', 'Nick Rodriguez'),
            ('inside-one', 'Inside Leglocks & False Reaps, Part 1', 'Pawel Jaworski'),
            ('inside-two', 'Inside Leglocks and False Reaps — Volume 2', 'Pawel Jaworski'),
            ('unknown-one', 'Unknown Series Part 1', 'Unknown'),
            ('unknown-two', 'Unknown Series Part 2', 'Unknown'),
        ]
        con = db.connect()
        with con:
            for vid, title, instructor in videos:
                con.execute('INSERT INTO videos VALUES (?,?,?,?,?,?)', (vid, title, instructor, '', 60, ''))
                text = 'body lock guard passing'
                cur = con.execute('INSERT INTO chunks (video_id,kind,start,end,text,embedding) VALUES (?,?,?,?,?,?)',
                                  (vid, 'transcript', 0, 30, text, np.array([1, 0], dtype=np.float32).tobytes()))
                con.execute('INSERT INTO chunks_fts (rowid,text) VALUES (?,?)', (cur.lastrowid, text))
        con.close()
        groups = library.instructionals()
        body = next(g for g in groups if g['id'] == 'body-three')
        self.assertEqual(body['title'], 'Body Lock System')
        self.assertEqual(body['video_ids'], ['body-one', 'body-three'])
        self.assertEqual(body['duration'], 120)
        self.assertEqual(set(body['aliases']), {'body-one', 'body-three'})
        inside = next(g for g in groups if g['id'] == 'inside-one')
        self.assertEqual(inside['video_ids'], ['inside-one', 'inside-two'])
        self.assertTrue(any(g['id'] == 'body-other-instructor' for g in groups))
        self.assertTrue(any(g['id'] == 'different-series' for g in groups))
        self.assertTrue(any(g['id'] == 'unknown-one' for g in groups))
        self.assertTrue(any(g['id'] == 'unknown-two' for g in groups))
        for scope in ('body-one', 'body-three'):
            response = self.client.get('/api/search', params={'q': 'body lock', 'instructional_id': scope})
            self.assertEqual(response.status_code, 200)
            self.assertEqual({r['video_id'] for r in response.json()}, {'body-one', 'body-three'})
