"""Image transport and explicitly configured async protocol; stdlib only."""
import base64
import binascii
import json
import mimetypes
import shutil
import subprocess
import sys
from pathlib import Path
import time
import uuid
from urllib.parse import urljoin, urlsplit, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

MODEL = 'gpt-image-2.5'
MAX_RESPONSE = 80 * 1024 * 1024
TRANSPORT = 'auto'


class APIError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def powershell_request(url, headers, body=None, timeout=180):
    executable=shutil.which('pwsh') or shutil.which('powershell')
    if not executable: raise APIError('找不到 PowerShell；可显式选择 --transport urllib。')
    # Credentials travel through stdin, never process arguments or temporary files.
    script=Path(__file__).with_name('http_request.ps1')
    payload=json.dumps({'url':url,'headers':headers,'body':base64.b64encode(body).decode() if body is not None else None,'timeout':max(1,int(timeout))})
    try:
        result=subprocess.run([executable,'-NoProfile','-NonInteractive','-File',str(script)],input=payload.encode('utf-8'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout+15)
        if result.returncode: raise APIError('PowerShell 请求未正常完成；未自动重试。')
        data=json.loads(result.stdout.decode('utf-8-sig'))
        status=int(data['status'])
        if not 200<=status<300: raise APIError(f'图片接口 HTTP {status}；请求未自动重试。')
        raw=base64.b64decode(data['body'],validate=True)
        if len(raw)>MAX_RESPONSE: raise APIError('接口响应超过安全大小限制。')
        return raw,data['headers'],status
    except (OSError,subprocess.TimeoutExpired,ValueError,KeyError):
        raise APIError('PowerShell 网络请求失败或超时；提交可能已被接受，请勿盲目重发。') from None


def request(url, headers, body=None, timeout=180):
    if TRANSPORT=='powershell' or (TRANSPORT=='auto' and sys.platform=='win32'):
        return powershell_request(url,headers,body,timeout)
    req = Request(url, data=body, headers=headers, method='POST' if body is not None else 'GET')
    try:
        with build_opener(NoRedirect).open(req, timeout=timeout) as r:
            raw = r.read(MAX_RESPONSE+1)
            if len(raw) > MAX_RESPONSE:
                raise APIError('接口响应超过安全大小限制。')
            return raw, dict(r.headers), r.status
    except HTTPError as e:
        # Deliberately do not echo upstream response bodies or URL queries.
        code=e.code
        e.close()
        raise APIError(f'图片接口 HTTP {code}；请检查服务端权限、余额及接口支持。请求未自动重试。') from None
    except (URLError, TimeoutError, OSError):
        raise APIError('网络请求失败或超时；提交可能已被服务端接受，请勿盲目重复提交。') from None


def request_json(url, headers, body=None, timeout=180):
    raw, response_headers, status = request(url, headers, body, timeout)
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        raise APIError('接口未返回合法 JSON。') from None
    if not isinstance(data, dict):
        raise APIError('接口 JSON 顶层须为对象。')
    return data, response_headers, status


def image_extension(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return '.png'
    if data.startswith(b'\xff\xd8\xff'): return '.jpg'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP': return '.webp'
    raise APIError('返回内容不是支持的 PNG/JPEG/WebP 图片。')


def write_image(data, out):
    ext = image_extension(data)
    out = Path(out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    name = time.strftime('image-%Y%m%d-%H%M%S-') + uuid.uuid4().hex + ext
    path = out/name
    with path.open('xb') as f:
        f.write(data)
    return path


def save_result(response, out):
    try:
        b64 = response['data'][0]['b64_json']
        data = base64.b64decode(b64, validate=True)
    except (KeyError, IndexError, TypeError, ValueError, binascii.Error):
        raise APIError('缺少合法的 data[0].b64_json；不能将任务 ID 当作生成完成。') from None
    return write_image(data, out)


def multipart(prompt, images):
    if not 1 <= len(images) <= 8:
        raise APIError('编辑需要 1–8 张参考图片。')
    boundary = 'zzzplus-' + uuid.uuid4().hex
    parts = []
    total = 0
    def add(headers, data):
        parts.append(('--'+boundary+'\r\n'+headers+'\r\n\r\n').encode()+data+b'\r\n')
    for name, value in [('model',MODEL),('prompt',prompt)]:
        add(f'Content-Disposition: form-data; name="{name}"',value.encode('utf-8'))
    for i, path in enumerate(images):
        try:
            p=Path(path).expanduser()
            if p.stat().st_size > 10*1024*1024: raise APIError('每张参考图不得超过 10MB。')
            raw = p.read_bytes()
        except OSError:
            raise APIError('无法读取参考图片。请确认路径和权限。') from None
        ext=image_extension(raw)
        total += len(raw)
        if total > 40*1024*1024: raise APIError('参考图总大小不得超过 40MB。')
        mime={'.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp'}[ext]
        # ASCII synthetic names avoid header injection and Unicode filename ambiguity.
        add(f'Content-Disposition: form-data; name="image"; filename="reference-{i+1}{ext}"\r\nContent-Type: {mime}',raw)
    parts.append(('--'+boundary+'--\r\n').encode())
    return b''.join(parts), 'multipart/form-data; boundary='+boundary


def same_origin_url(base, value):
    url=urljoin(base+'/',value)
    a,b=urlsplit(base),urlsplit(url)
    if (a.scheme,a.hostname,a.port)!=(b.scheme,b.hostname,b.port) or b.username or b.password or b.fragment:
        raise APIError('任务/结果地址必须与当前 Provider 同源；不会向其他域名转发凭证。')
    return url


def field(obj, path):
    try:
        for p in path.split('.') if path else []:
            obj=obj[int(p)] if isinstance(obj,list) else obj[p]
        return obj
    except (KeyError,IndexError,TypeError,ValueError):
        raise APIError('响应缺少 async-spec 指定的字段，请向服务商核实协议。') from None


def validate_spec(spec):
    required=['id_path','status_url','status_path','success_states','failure_states','result_path','result_kind']
    if not isinstance(spec,dict) or any(k not in spec for k in required):
        raise APIError('异步查询协议尚未确认；请提供完整 --async-spec，未发出付费提交。')
    if spec['result_kind'] not in ('image_response','image_url','result_json_url'):
        raise APIError('async-spec result_kind 不支持。')
    for key in ['id_path','status_url','status_path','result_path']:
        if not isinstance(spec[key],str): raise APIError('async-spec 字段路径须为字符串。')
    if '{id}' not in spec['status_url']: raise APIError('status_url 必须包含 {id} 占位符。')
    for key in ['success_states','failure_states']:
        if not isinstance(spec[key],list) or not spec[key]: raise APIError('async-spec 状态集合必须为非空数组。')


def poll(provider, job_id, spec, out, interval=5, wait=600, timeout=180):
    validate_spec(spec)
    status_url=same_origin_url(provider.base_url,spec['status_url'].replace('{id}',quote(str(job_id),safe='')))
    deadline=time.monotonic()+wait
    while time.monotonic()<deadline:
        remaining=deadline-time.monotonic()
        obj,_,_=request_json(status_url,provider.headers,timeout=min(timeout,max(0.1,remaining)))
        status=field(obj,spec['status_path'])
        if status in spec['failure_states']: raise APIError('异步任务失败或取消；未保存图片。')
        if status in spec['success_states']:
            result=field(obj,spec['result_path'])
            if spec['result_kind']=='image_response': return save_result(result,out)
            url=same_origin_url(provider.base_url,result)
            if spec['result_kind']=='result_json_url':
                result,_,_=request_json(url,provider.headers,timeout=timeout)
                return save_result(result,out)
            raw,_,_=request(url,provider.headers,timeout=timeout)
            return write_image(raw,out)
        time.sleep(min(interval,max(0,deadline-time.monotonic())))
    raise APIError('异步轮询达到等待上限；任务可能仍在运行。请使用 poll 恢复，不要重新提交。')


def generate(provider, prompt, out, images=None, async_mode=False, spec=None, interval=5, wait=600, timeout=180, job_file=None):
    if not prompt.strip(): raise APIError('图片描述不能为空。')
    if interval<=0 or wait<=0 or timeout<=0: raise APIError('等待及超时参数必须大于零。')
    headers=dict(provider.headers)
    if async_mode:
        if images: raise APIError('异步模式仅用于文生图。')
        validate_spec(spec)
        same_origin_url(provider.base_url,spec['status_url'].replace('{id}','validation'))
        headers['Prefer']='respond-async'
        headers['Idempotency-Key']=str(uuid.uuid4())
    if images:
        body,ctype=multipart(prompt,images)
        endpoint='/images/edits'
    else:
        body=json.dumps({'model':MODEL,'prompt':prompt}).encode()
        ctype='application/json'
        endpoint='/images/generations'
    headers['Content-Type']=ctype
    obj,_,_=request_json(provider.base_url+endpoint,headers,body,timeout)
    if not async_mode: return save_result(obj,out)
    # Some compatible providers ignore Prefer and return a completed image.
    if isinstance(obj.get('data'),list) and obj['data'] and obj['data'][0].get('b64_json'):
        return save_result(obj,out)
    job_id=field(obj,spec['id_path'])
    if not isinstance(job_id,(str,int)) or not str(job_id): raise APIError('异步响应没有合法任务 ID。')
    if job_file:
        # No auth headers, prompt, source paths or images are persisted.
        path=Path(job_file).expanduser().resolve()
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='utf-8') as f:
            json.dump({'job_id':job_id,'base_url':provider.base_url,'provider':provider.name,'async_spec':spec},f,ensure_ascii=False,indent=2)
    print('异步任务已提交，正在查询；尚未生成图片。',flush=True)
    return poll(provider,job_id,spec,out,interval,wait,timeout)
