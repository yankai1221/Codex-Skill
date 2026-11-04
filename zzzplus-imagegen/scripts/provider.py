"""Read-only Codex provider resolution. Never reuse OAuth session tokens."""
from dataclasses import dataclass, field
from pathlib import Path
import copy
import json
import os
import tomllib
from urllib.parse import urlsplit, urlunsplit


class ConfigError(Exception):
    pass


@dataclass
class Provider:
    base_url: str
    headers: dict = field(repr=False)
    name: str = ''
    credential_source: str = ''


def normalize_base(value):
    u = urlsplit(value.strip())
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ConfigError('Provider base_url 必须是无凭证、无查询参数的 HTTPS 地址。')
    path = u.path.rstrip('/')
    if not path.endswith('/v1'):
        path += '/v1'
    return urlunsplit((u.scheme, u.netloc, path, '', ''))


def merge(target, values):
    for k, v in values.items():
        if isinstance(v, dict) and isinstance(target.get(k), dict):
            merge(target[k], v)
        else:
            target[k] = copy.deepcopy(v)


def read_toml(path):
    try:
        return tomllib.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        raise ConfigError('无法读取或解析配置文件；请检查路径和 TOML 格式。') from None


def resolve(home=None, profile=None, overrides=None, env=None, layers=None):
    env = os.environ if env is None else env
    home = Path(home or env.get('CODEX_HOME') or Path.home()/'.codex').expanduser()
    cfg = read_toml(home/'config.toml') if (home/'config.toml').exists() else {}
    for layer in layers or []:
        merge(cfg, read_toml(layer))
    runtime = {}
    for item in overrides or []:
        try:
            merge(runtime, tomllib.loads(item))
        except ValueError:
            raise ConfigError('运行时覆盖须使用 TOML key=value 格式。') from None
    chosen = profile or runtime.get('profile') or cfg.get('profile')
    if chosen:
        profiles = cfg.get('profiles', {})
        if chosen not in profiles:
            raise ConfigError('指定的 Codex profile 不存在。')
        merge(cfg, profiles[chosen])
    merge(cfg, runtime)
    name = cfg.get('model_provider', 'openai')
    p = cfg.get('model_providers', {}).get(name)
    builtin = p is None and name == 'openai'
    if p is None and not builtin:
        raise ConfigError('当前 model_provider 未在 model_providers 中定义。')
    p = p or {}
    base = p.get('base_url') or (cfg.get('openai_base_url') or env.get('OPENAI_BASE_URL') if builtin else None)
    if not base:
        raise ConfigError('未找到当前 Provider 的中转 base_url；不会自动调用官方或其他上游。')
    base = normalize_base(base)
    headers = {}
    def set_header(header,value):
        for existing in list(headers):
            if existing.lower()==header.lower(): del headers[existing]
        headers[header]=value
    for header,value in p.get('http_headers', {}).items():
        set_header(header,value)
    for header, variable in p.get('env_http_headers', {}).items():
        value = env.get(variable)
        if not value:
            raise ConfigError('当前 Provider 所需的请求头环境变量尚未配置。')
        set_header(header,value)
    token = p.get('experimental_bearer_token')
    source = 'provider.experimental_bearer_token' if token else ''
    if not token and p.get('env_key'):
        token = env.get(p['env_key'])
        source = 'provider.env_key'
        if not token:
            raise ConfigError('当前 Provider 的 env_key 对应环境变量为空；请在本机配置后重试。')
    if token:
        for k in list(headers):
            if k.lower() == 'authorization': del headers[k]
        headers['Authorization'] = 'Bearer ' + token
    elif any(k.lower() == 'authorization' for k in headers):
        source = 'provider.http_headers/env_http_headers'
    else:
        # OPENAI_API_KEY is a static API credential, unlike tokens.access_token.
        token = env.get('OPENAI_API_KEY')
        source = 'environment.OPENAI_API_KEY'
        if not token and (home/'auth.json').exists():
            try:
                token = json.loads((home/'auth.json').read_text(encoding='utf-8-sig')).get('OPENAI_API_KEY')
            except (ValueError, OSError):
                raise ConfigError('无法读取静态认证配置。') from None
            source = 'auth.json.OPENAI_API_KEY'
        if not isinstance(token, str) or not token.strip():
            raise ConfigError('没有可复用的静态 API 凭证。不会使用 Codex OAuth 登录缓存；请为当前 Provider 配置 env_key 及对应环境变量，或兼容的 OPENAI_API_KEY。无需 ZZZPLUS_API_KEY。')
        headers['Authorization'] = 'Bearer ' + token
    for k, v in headers.items():
        if not isinstance(v, str) or '\r' in v or '\n' in v or '\r' in k or '\n' in k:
            raise ConfigError('Provider 请求头格式不合法。')
        if k.lower() in ('host','content-length','content-type','prefer','idempotency-key'):
            raise ConfigError('Provider 自定义请求头覆盖了图片请求保留字段。')
    return Provider(base, headers, str(name), source)
