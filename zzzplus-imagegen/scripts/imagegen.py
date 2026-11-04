#!/usr/bin/env python3
"""Natural-language skill's reusable CLI; no credentials accepted in arguments."""
import argparse
import json
from pathlib import Path
import sys
import uuid
import image_api
from provider import resolve, ConfigError
from image_api import generate, poll, APIError


def main():
    p=argparse.ArgumentParser(description='通过当前 Codex Provider 使用 gpt-image-2.5 生图或编辑')
    p.add_argument('mode',choices=['check','generate','edit','async','poll'])
    p.add_argument('--prompt')
    p.add_argument('--prompt-file',type=Path)
    p.add_argument('--image',action='append',type=Path,default=[])
    p.add_argument('--output-dir',type=Path,default=Path('generated-images'))
    p.add_argument('--codex-home',type=Path)
    p.add_argument('--config-layer',action='append',type=Path,default=[])
    p.add_argument('--profile')
    p.add_argument('-c','--config',action='append',default=[],help='非敏感的实际生效 TOML 覆盖；不得传 API Key')
    p.add_argument('--async-spec',type=Path)
    p.add_argument('--job-file',type=Path)
    p.add_argument('--interval',type=float,default=5)
    p.add_argument('--wait',type=float,default=600)
    p.add_argument('--timeout',type=float,default=180)
    p.add_argument('--transport',choices=['auto','urllib','powershell'],default='auto',help='Windows auto 使用 PowerShell；其他系统使用 urllib；不会失败后自动切换重发')
    a=p.parse_args()
    try:
        image_api.TRANSPORT=a.transport
        provider=resolve(a.codex_home,a.profile,a.config,layers=a.config_layer)
        if a.mode=='check':
            print(json.dumps({'provider':provider.name,'base_url':provider.base_url,'credential_source':provider.credential_source,'model':'gpt-image-2.5'},ensure_ascii=False,indent=2))
            return 0
        if min(a.interval,a.wait,a.timeout)<=0: raise APIError('超时和轮询间隔必须大于零。')
        spec=json.loads(a.async_spec.read_text(encoding='utf-8-sig')) if a.async_spec else None
        if a.mode=='poll':
            if not a.job_file: raise APIError('poll 需要 --job-file。')
            job=json.loads(a.job_file.read_text(encoding='utf-8-sig'))
            if job['base_url']!=provider.base_url or job['provider']!=provider.name:
                raise APIError('当前 Provider 与任务提交时不一致；拒绝使用其他凭证查询。')
            result=poll(provider,job['job_id'],spec or job['async_spec'],a.output_dir,a.interval,a.wait,a.timeout)
        else:
            prompt=a.prompt_file.read_text(encoding='utf-8-sig') if a.prompt_file else a.prompt
            if not prompt: raise APIError('需要 --prompt 或 --prompt-file。')
            if a.mode=='edit' and not a.image: raise APIError('edit 至少需要一张 --image。')
            if a.mode!='edit' and a.image: raise APIError('参考图片必须使用 edit 模式。')
            job_file=a.job_file
            if a.mode=='async' and not job_file:
                job_file=a.output_dir/('job-'+uuid.uuid4().hex+'.json')
            if job_file and job_file.exists(): raise APIError('任务记录已存在；请选择新路径以免重复提交。')
            if job_file:
                job_file.parent.mkdir(parents=True,exist_ok=True)
                print('任务记录位置：'+str(job_file.resolve()),flush=True)
            result=generate(provider,prompt,a.output_dir,a.image,a.mode=='async',spec,a.interval,a.wait,a.timeout,job_file)
        print('IMAGE_PATH='+str(result))
        return 0
    except (ConfigError,APIError) as e:
        print('错误：'+str(e),file=sys.stderr)
        return 1
    except (OSError,ValueError,KeyError,TypeError):
        print('错误：本地文件、JSON 配置或参数无效；未输出原始响应或凭证。',file=sys.stderr)
        return 1


if __name__=='__main__': sys.exit(main())
