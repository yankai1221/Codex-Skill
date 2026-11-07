import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import provider
import image_api

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=')


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def config(self, text):
        (self.home / 'config.toml').write_text(text, encoding='utf-8')

    def test_current_provider_env_and_no_config_changes(self):
        self.config('model="keep-me"\nmodel_provider="relay"\n[model_providers.relay]\nbase_url="https://relay.test/v1/"\nenv_key="MY_KEY"\n')
        before = (self.home / 'config.toml').read_bytes()
        p = provider.resolve(self.home, env={'MY_KEY': 'private-test-value'})
        self.assertEqual(p.base_url, 'https://relay.test/v1')
        self.assertEqual(p.headers['Authorization'], 'Bearer private-test-value')
        self.assertNotIn('private-test-value', repr(p))
        self.assertEqual(before, (self.home / 'config.toml').read_bytes())

    def test_profile_and_runtime_override(self):
        self.config('model_provider="bad"\nprofile="pictures"\n[profiles.pictures]\nmodel_provider="relay"\n[model_providers.relay]\nbase_url="https://relay.test"\nexperimental_bearer_token="test-token"\n')
        p = provider.resolve(self.home, overrides=['model_providers.relay.base_url="https://other.test/v1"'], env={})
        self.assertEqual(p.base_url, 'https://other.test/v1')

    def test_builtin_base_and_static_auth_json(self):
        self.config('openai_base_url="https://relay.test"\n')
        (self.home/'auth.json').write_text(json.dumps({'OPENAI_API_KEY':'static-key','tokens':{'access_token':'not-for-use'}}))
        p = provider.resolve(self.home, env={})
        self.assertEqual(p.base_url, 'https://relay.test/v1')
        self.assertEqual(p.headers['Authorization'], 'Bearer static-key')

    def test_oauth_cache_is_not_api_key(self):
        self.config('openai_base_url="https://relay.test/v1"\n')
        (self.home/'auth.json').write_text(json.dumps({'tokens':{'access_token':'private-oauth'}}))
        with self.assertRaises(provider.ConfigError):
            provider.resolve(self.home, env={})

    def test_missing_provider_env_does_not_fallback(self):
        self.config('model_provider="relay"\n[model_providers.relay]\nbase_url="https://relay.test/v1"\nenv_key="MISSING"\n')
        with self.assertRaises(provider.ConfigError):
            provider.resolve(self.home, env={'OPENAI_API_KEY':'wrong-provider-key'})

    def test_explicit_layer_has_precedence(self):
        self.config('model_provider="relay"\n[model_providers.relay]\nbase_url="https://relay.test/v1"\nenv_key="MY_KEY"\n')
        layer=self.home/'project.toml'
        layer.write_text('[model_providers.relay]\nbase_url="https://project.test/v1"\n')
        self.assertEqual(provider.resolve(self.home, env={'MY_KEY':'test'}, layers=[layer]).base_url, 'https://project.test/v1')

    def test_reject_official_default_and_insecure_urls(self):
        for text in ['', 'openai_base_url="http://relay.test/v1"', 'openai_base_url="https://user:password@relay.test/v1"']:
            self.config(text)
            with self.assertRaises(provider.ConfigError): provider.resolve(self.home, env={'OPENAI_API_KEY':'test'})

    def test_dynamic_headers_override_case_insensitively(self):
        self.config('model_provider="relay"\n[model_providers.relay]\nbase_url="https://relay.test/v1"\n[model_providers.relay.http_headers]\nAuthorization="Bearer old"\nX-Client="old"\n[model_providers.relay.env_http_headers]\nauthorization="AUTH"\nx-client="CLIENT"\n')
        p=provider.resolve(self.home,env={'AUTH':'Bearer new','CLIENT':'new-client'})
        self.assertEqual([v for k,v in p.headers.items() if k.lower()=='authorization'],['Bearer new'])
        self.assertEqual([v for k,v in p.headers.items() if k.lower()=='x-client'],['new-client'])


class ImageTests(unittest.TestCase):
    def test_url_normalization(self):
        for value in ['https://relay.test', 'https://relay.test/', 'https://relay.test/v1', 'https://relay.test/v1/']:
            self.assertEqual(provider.normalize_base(value), 'https://relay.test/v1')
        self.assertEqual(provider.normalize_base('https://relay.test/proxy/v1'), 'https://relay.test/proxy/v1')

    def test_base64_saved_as_real_image_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            response={'data':[{'b64_json':base64.b64encode(PNG).decode()}]}
            a=image_api.save_result(response, Path(tmp)/'generated-images')
            b=image_api.save_result(response, Path(tmp)/'generated-images')
            self.assertNotEqual(a,b)
            self.assertEqual(a.read_bytes(), PNG)
            self.assertEqual(len(list(a.parent.iterdir())), 2)

    def test_invalid_base64_or_non_image_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for b in ['invalid!', base64.b64encode(b'not an image').decode()]:
                with self.assertRaises(image_api.APIError):
                    image_api.save_result({'data':[{'b64_json':b}]},Path(tmp))

    def test_multipart_has_all_repeated_file_fields(self):
        from email.parser import BytesParser
        from email.policy import default
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'a.png'; b=Path(tmp)/'b.png'
            a.write_bytes(PNG); b.write_bytes(PNG)
            body,ctype=image_api.multipart('combine', [a,b])
            msg=BytesParser(policy=default).parsebytes(('Content-Type: '+ctype+'\r\n\r\n').encode()+body)
            files=[part for part in msg.iter_parts() if part.get_param('name',header='content-disposition')=='image']
            self.assertEqual(len(files),2)
            self.assertEqual([x.get_payload(decode=True) for x in files], [PNG,PNG])
            self.assertNotIn(b'name="image[]"',body)

    def test_poll_config_required_before_submit(self):
        p=provider.Provider('https://relay.test/v1', {'Authorization':'Bearer test'}, 'test','test')
        with self.assertRaises(image_api.APIError):
            image_api.generate(p,'lake',Path('unused'),async_mode=True)

    def test_cross_origin_job_url_rejected(self):
        with self.assertRaises(image_api.APIError):
            image_api.same_origin_url('https://relay.test/v1','https://attacker.test/jobs/1')


class HTTPContractTests(unittest.TestCase):
    """Offline contract server, explicitly NOT real-provider acceptance."""
    def test_async_posts_unique_keys_polls_and_saves(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                body=self.rfile.read(int(self.headers['Content-Length']))
                received.append((self.path,dict(self.headers),json.loads(body)))
                payload={'task':'job-123'}
                self.send_response(202); self.end_headers(); self.wfile.write(json.dumps(payload).encode())
            def do_GET(self):
                received.append((self.path,dict(self.headers),None))
                payload={'state':'done','output':{'data':[{'b64_json':base64.b64encode(PNG).decode()}]}}
                self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(payload).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}/v1'
            p=provider.Provider(base,{'Authorization':'Bearer offline-test'},'test','test')
            spec={'id_path':'task','status_url':'jobs/{id}','status_path':'state','success_states':['done'],'failure_states':['failed'],'result_path':'output','result_kind':'image_response'}
            with tempfile.TemporaryDirectory() as tmp:
                for i in range(2):
                    path=image_api.generate(p,'test prompt',Path(tmp),async_mode=True,spec=spec,interval=.01,wait=1,job_file=Path(tmp)/f'job{i}.json')
                    self.assertEqual(path.read_bytes(),PNG)
            self.assertEqual([x[0] for x in received],['/v1/images/generations','/v1/jobs/job-123']*2)
            self.assertEqual(received[0][2],{'model':'gpt-image-2.6','prompt':'test prompt'})
            self.assertEqual(received[0][1]['Prefer'],'respond-async')
            self.assertNotEqual(received[0][1]['Idempotency-Key'],received[2][1]['Idempotency-Key'])
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_failure_and_timeout_never_save_picture(self):
        p=provider.Provider('https://relay.test/v1',{},'test','test')
        spec={'id_path':'task','status_url':'jobs/{id}','status_path':'state','success_states':['done'],'failure_states':['failed'],'result_path':'output','result_kind':'image_response'}
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(image_api,'request_json',return_value=({'state':'failed'},{},200)):
                with self.assertRaises(image_api.APIError): image_api.poll(p,'1',spec,Path(tmp))
            with patch.object(image_api,'request_json',return_value=({'state':'pending'},{},200)):
                with self.assertRaises(image_api.APIError): image_api.poll(p,'1',spec,Path(tmp),interval=.001,wait=.01)
            self.assertEqual(list(Path(tmp).iterdir()),[])

    def test_redirect_does_not_forward_auth(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from threading import Thread
        hits=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                hits.append(self.path)
                self.send_response(302); self.send_header('Location','/stolen'); self.end_headers()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        t=Thread(target=server.serve_forever,daemon=True); t.start()
        try:
            with self.assertRaises(image_api.APIError):image_api.request(f'http://127.0.0.1:{server.server_port}/start',{'Authorization':'Bearer test'})
            self.assertEqual(hits,['/start'])
        finally:server.shutdown(); server.server_close(); t.join()

    @unittest.skipUnless(sys.platform=='win32','Windows transport integration')
    def test_powershell_transport_real_local_http(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from threading import Thread
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                received.append(self.rfile.read(int(self.headers['Content-Length'])))
                self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()
                self.wfile.write(b'{"ok":true}')
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        t=Thread(target=server.serve_forever,daemon=True); t.start()
        try:
            raw,h,status=image_api.powershell_request(f'http://127.0.0.1:{server.server_port}/test',{'Authorization':'Bearer test','Content-Type':'application/json'},b'{"hello":"world"}',10)
            self.assertEqual(json.loads(raw),{'ok':True})
            self.assertEqual(received,[b'{"hello":"world"}'])
            self.assertEqual(status,200)
        finally:server.shutdown(); server.server_close(); t.join()


class InstallerTests(unittest.TestCase):
    def test_install_upgrade_uninstall_preserve_original_backup(self):
        import subprocess
        script=Path(__file__).resolve().parents[1]/'scripts/install.py'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'skills'
            def run(*args):
                return subprocess.run([sys.executable,str(script),*args,'--target',str(root)],capture_output=True)
            first=run('install')
            self.assertEqual(first.returncode,0,first.stderr)
            dest=root/'zzzplus-imagegen'
            self.assertTrue((dest/'SKILL.md').exists())
            (dest/'personal-note.txt').write_text('preserve')
            self.assertNotEqual(run('install').returncode,0)
            self.assertEqual(run('install','--upgrade').returncode,0)
            backups=list((root.parent/'skill-backups').glob('zzzplus-imagegen-*'))
            self.assertEqual((backups[0]/'personal-note.txt').read_text(),'preserve')
            self.assertEqual(run('uninstall').returncode,0)
            self.assertFalse(dest.exists())

    def test_installer_refuses_unrelated_folder(self):
        import subprocess
        script=Path(__file__).resolve().parents[1]/'scripts/install.py'
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'skills/zzzplus-imagegen'; dest.mkdir(parents=True)
            (dest/'keep.txt').write_text('keep')
            result=subprocess.run([sys.executable,str(script),'uninstall','--target',str(dest.parent)],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual((dest/'keep.txt').read_text(),'keep')


if __name__=='__main__': unittest.main()
