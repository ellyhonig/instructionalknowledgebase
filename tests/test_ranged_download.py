import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from bjjvault import config
from bjjvault.ranged_download import fetch


class RangeDownloadTests(unittest.TestCase):
    def test_dropped_response_resumes_and_cached_ranges_are_reused(self):
        data = bytes(range(256))*1024
        requests_seen = []
        failed = set()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                value = self.headers['Range'].split('=')[1]
                start, end = map(int, value.split('-'))
                end = min(end,len(data)-1)
                requests_seen.append((start,end))
                self.send_response(206)
                self.send_header('Content-Range',f'bytes {start}-{end}/{len(data)}')
                self.send_header('Content-Length',str(end-start+1))
                self.end_headers()
                if end-start>1 and start not in failed and start % 65536 == 0:
                    failed.add(start)
                    self.wfile.write(data[start:start+32768])
                    self.wfile.flush()
                    self.close_connection = True
                else:
                    self.wfile.write(data[start:end+1])

            def log_message(self,*args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory(dir=config.TMP) as tmp:
                root=Path(tmp)
                url=f'http://127.0.0.1:{server.server_port}/video'
                fetch([url],root/'output',root/'cache',{},chunk_size=65536,workers=2)
                self.assertEqual((root/'output').read_bytes(),data)
                self.assertIn((32768,65535),requests_seen)
                count=len(requests_seen)
                fetch([url],root/'output2',root/'cache',{},chunk_size=65536,workers=2)
                self.assertEqual(len(requests_seen),count+1)
                self.assertEqual((root/'output2').read_bytes(),data)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_server_ignoring_ranges_is_rejected(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length','4')
                self.end_headers()
                self.wfile.write(b'data')

            def log_message(self,*args):
                pass

        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory(dir=config.TMP) as tmp, self.assertRaisesRegex(RuntimeError,'No usable'):
                fetch([f'http://127.0.0.1:{server.server_port}/video'],Path(tmp)/'out',Path(tmp)/'cache',{})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
