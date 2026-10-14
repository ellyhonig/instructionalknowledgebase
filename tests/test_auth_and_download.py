import subprocess
import unittest
from unittest.mock import patch

from bjjvault.download import BiliBiliIE, _BiliBiliIE, _canonical_share_url
from bjjvault.organize import Organized, _call_codex


class AuthAndDownloadTests(unittest.TestCase):
    def test_api_key_login_is_rejected_before_generation(self):
        status = subprocess.CompletedProcess([], 0, stdout='', stderr='Logged in using an API key')
        with patch('bjjvault.organize.shutil.which', return_value='codex.cmd'), \
             patch('bjjvault.organize.subprocess.run', return_value=status) as run, \
             patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key', 'CODEX_API_KEY': 'test-key'}):
            with self.assertRaisesRegex(RuntimeError, 'API-key login is not allowed'):
                _call_codex('test')
            self.assertEqual(run.call_count, 1)
            self.assertNotIn('OPENAI_API_KEY', run.call_args.kwargs['env'])
            self.assertNotIn('CODEX_API_KEY', run.call_args.kwargs['env'])

    def test_strict_output_schema(self):
        schema = Organized.model_json_schema()
        for obj in [schema, *schema['$defs'].values()]:
            self.assertFalse(obj['additionalProperties'])
            self.assertEqual(set(obj['required']), set(obj['properties']))

    def test_empty_success_uses_public_playback_fallback(self):
        ie = BiliBiliIE()
        with patch.object(_BiliBiliIE, '_download_playinfo', return_value={'quality':32}), \
             patch.object(ie, '_download_json', return_value={'code':0,'data':{'dash':{'video':[{}]}}}) as fetch:
            self.assertIn('dash', ie._download_playinfo('BVdemo',123))
            self.assertEqual(fetch.call_count,1)

    def test_failed_playback_does_not_trigger_fallback(self):
        ie = BiliBiliIE()
        with patch.object(_BiliBiliIE, '_download_playinfo', return_value=None), \
             patch.object(ie, '_download_json') as fetch:
            self.assertIsNone(ie._download_playinfo('BVdemo',123))
            fetch.assert_not_called()

    def test_short_share_expands_upload_but_explicit_part_is_preserved(self):
        from unittest.mock import Mock
        response=Mock(headers={'Location':'https://www.bilibili.com/video/BVdemo/?p=1&share_source=COPY'})
        with patch('requests.get',return_value=response):
            self.assertEqual(_canonical_share_url('https://b23.tv/demo'),'https://www.bilibili.com/video/BVdemo/')
        self.assertEqual(_canonical_share_url('https://www.bilibili.com/video/BVdemo?p=3'),
                         'https://www.bilibili.com/video/BVdemo?p=3')


if __name__ == '__main__':
    unittest.main()
