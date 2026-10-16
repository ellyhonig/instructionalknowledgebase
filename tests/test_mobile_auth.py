import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from bjjvault import config, mobile_auth
from bjjvault.web.mobile import app


class MobileAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=config.TMP)
        self.paths=patch.object(config,'MOBILE_ACCESS_TOKEN_FILE',Path(self.temp.name)/'token.txt')
        self.paths.start()
        self.client=TestClient(app,base_url='https://vault.test')
        self.token=mobile_auth.access_token()

    def tearDown(self):
        self.client.close()
        self.paths.stop()
        self.temp.cleanup()

    def sign_in(self):
        response=self.client.post('/login',data={'token':self.token},follow_redirects=False)
        self.assertEqual(response.status_code,303)
        self.assertEqual(response.headers['location'],'/')
        return response

    def test_login_and_secure_cookie(self):
        self.assertEqual(self.client.post('/login',data={'token':'wrong'}).status_code,401)
        response=self.sign_in()
        cookie=response.headers['set-cookie']
        self.assertIn('HttpOnly',cookie)
        self.assertIn('Secure',cookie)
        self.assertIn('SameSite=strict',cookie)
        self.assertNotIn(self.token,cookie)
        self.assertTrue(mobile_auth.valid_session(self.client.cookies[mobile_auth.COOKIE_NAME]))
        self.assertEqual(self.client.post('/login',content='token='+'x'*3000).status_code,413)
        response=self.client.post('/login',data={'token':self.token},headers={'Accept':'application/json'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json(),{'ok':True})
        self.assertIn('Secure',response.headers['set-cookie'])

    def test_expiry_tampering_rotation_and_logout(self):
        self.sign_in()
        value=self.client.cookies[mobile_auth.COOKIE_NAME]
        self.assertFalse(mobile_auth.valid_session(value+'x'))
        with patch('bjjvault.mobile_auth.time.time',return_value=10**12):
            self.assertFalse(mobile_auth.valid_session(value))
        config.MOBILE_ACCESS_TOKEN_FILE.write_text('a'*43,encoding='utf-8')
        self.assertFalse(mobile_auth.valid_session(value))
        self.assertEqual(self.client.get('/api/jobs').status_code,401)
        self.client.post('/logout',follow_redirects=False)
        self.assertNotIn(mobile_auth.COOKIE_NAME,self.client.cookies)

    def test_cross_site_mutations_rejected(self):
        self.assertEqual(self.client.post('/login',data={'token':self.token},
            headers={'Origin':'https://attacker.test'}).status_code,403)
        self.sign_in()
        self.assertEqual(self.client.post('/api/jobs',json={'url':'example'},
            headers={'Origin':'https://attacker.test'}).status_code,403)

    def test_authenticated_proxy_streams_ranges_query_and_request_body(self):
        captured=[]
        async def upstream(request):
            body=await request.aread()
            captured.append((request,body))
            if request.url.path=='/media/demo.mp4':
                return httpx.Response(206,headers={'Content-Range':'bytes 2-5/16','Content-Length':'4',
                    'Content-Type':'video/mp4'},stream=httpx.ByteStream(b'2345'))
            return httpx.Response(200,headers={'Content-Type':'application/json'},
                stream=httpx.ByteStream(b'{"ok":true}'))
        original=httpx.AsyncClient
        def factory(**kwargs):
            return original(transport=httpx.MockTransport(upstream),**kwargs)
        with patch('bjjvault.web.mobile.httpx.AsyncClient',side_effect=factory):
            # Browser cookie authorization, video range preserved.
            self.sign_in()
            response=self.client.get('/media/demo.mp4',headers={'Range':'bytes=2-5'})
            self.assertEqual(response.status_code,206)
            self.assertEqual(response.content,b'2345')
            self.assertEqual(response.headers['content-range'],'bytes 2-5/16')
            self.assertEqual(captured[-1][0].headers['range'],'bytes=2-5')
            self.assertNotIn('cookie',captured[-1][0].headers)
            response=self.client.post('/api/jobs?source=phone',json={'url':'example'},
                headers={'Origin':'https://vault.test'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(captured[-1][0].url.query,b'source=phone')
            self.assertEqual(json.loads(captured[-1][1]),{'url':'example'})
            # Independent API clients may use the same token as a bearer credential.
            self.client.cookies.clear()
            self.assertEqual(self.client.get('/api/jobs',headers={'Authorization':'Bearer '+self.token}).status_code,200)
            self.assertNotIn('authorization',captured[-1][0].headers)
            self.assertEqual(captured[-1][0].url.host,'127.0.0.1')


if __name__=='__main__':
    unittest.main()
