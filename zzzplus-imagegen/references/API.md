# 接口与异步协议

## 文档依据

核查日期：2026-11-04。

- Wokey 图片文档：https://wokey.ai/docs/images
- 该页面公开示例模块：`https://wokey.ai/assets/DocsImagesPage-Dq8sL-DW.js`（构建版本可能变化）。
- 官方 Skill 规范：https://developers.openai.com/codex/skills/ ，现重定向到 https://learn.chatgpt.com/docs/build-skills 。
- Codex 配置参考：https://developers.openai.com/codex/config-reference/ 。

文档确认：`POST /v1/images/generations` 使用 JSON，`model=gpt-image-2.6`（默认）或 `grok-imagine-image-2.0`、`prompt`；返回 `data[0].b64_json`。编辑使用 `/v1/images/edits`，multipart 实际文件上传。文档接受重复 image 或 image[]；本 Skill 严格使用重复 `image`。1–8 张 PNG/JPEG/WebP，每张最多 10MB，总计最多 40MB。不传 mask、size、quality、n、stream，避免声称服务端无法保证的能力。

所有运行地址来自当前 Provider；文档的上游地址仅作为来源，不是运行回退地址。base_url 去末尾斜杠，若未以 `/v1` 结尾则追加 `/v1`，再追加 `/images/generations` 或 `/images/edits`；保留已有代理路径。不接受 HTTP、地址中的用户名/密码、查询参数或片段。

## 配置与认证边界

配置优先级：主配置 → 显式传入且确认可信的配置层（按参数顺序）→ 所选 profile → `-c` 覆盖。`--profile` 覆盖配置中的 profile；自定义 Provider 的 base_url 优先。内置 OpenAI Provider 兼容 root `openai_base_url`，以及 `OPENAI_BASE_URL`。未明确配置中转地址就报错，不擅自选择官方端点。

凭证顺序：当前 Provider `experimental_bearer_token` → `env_key` 指定环境变量 → 现有 Authorization 请求头 → 静态 `OPENAI_API_KEY` 环境变量 → 当前 CODEX_HOME 的 `auth.json.OPENAI_API_KEY`。配置的 env_key 缺失时直接报错，不换其他凭证。保留 `http_headers` / `env_http_headers` 的非保留请求头；动态环境头覆盖同名静态头。只报告来源标签，不报告值。

不会使用 `auth.json.tokens`、系统钥匙串或 OAuth access/refresh token，不执行凭证助手。启动时临时覆盖、远端管理配置和进程内状态不能仅凭磁盘推断；调用者必须提供已经确认的实际生效非敏感覆盖。尚未支持的托管/动态认证必须明确告知用户，不得把不确定配置当作已核实。

## 异步：已确认和待确认内容

已确认：JSON 生成接口，加 `Prefer: respond-async`、每次唯一的 `Idempotency-Key`、Content-Type 和现有 Authorization。公开页面与其完整示例只说“Job ID → poll status → download image”，**未公布任务查询路由、任务 ID 字段名、状态字段、终态枚举或结果结构**。因此不提供猜测的默认轮询接口。

管理员从服务商获得协议后编写本地 JSON，通过 `--async-spec` 传入；该文件不应含认证信息。以下是字段定义，不是已确认的服务端示例：

| 字段 | 含义 |
|---|---|
| id_path | 提交响应中的任务 ID 路径，例如服务商确认的字段路径 |
| status_url | 经确认的任务查询 URL 模板，必须含 `{id}`；可为同源绝对地址或相对于 base_url 的路径 |
| status_path | 状态响应中的状态字段路径 |
| success_states | 完成终态值数组 |
| failure_states | 失败/取消终态值数组 |
| result_path | 状态响应中的结果字段路径；空字符串代表整个响应 |
| result_kind | `image_response`：结果为含 data[0].b64_json 的对象；`image_url`：结果为同源图片 URL；`result_json_url`：结果为同源 JSON 地址，其返回含 data[0].b64_json |

路径以点分隔，数组使用数字索引。不支持字面量带点的 JSON 键。GET 查询，无额外查询认证参数。状态未终结则默认每 5 秒查询，最多 600 秒；`--interval` / `--wait` / `--timeout` 可调整。任务 ID 经 URL 编码。失败、超时、字段缺失均明确报错；不把这些情况当作成功，不自动重新提交。

异步提交前校验协议，自动创建不覆盖的 `job-UUID.json`，仅保存任务 ID、Provider 标识、base_url 和非敏感协议，便于 `poll --job-file` 恢复。记录不含密钥、请求头、prompt 或图片。若服务端忽略 Prefer 并同步返回 b64_json，保存图片并如实说明未验证异步流程。服务端任务创建后到记录落盘前发生断电/磁盘故障，仍可能无法恢复；不可盲目重发。

默认禁止所有 HTTP 重定向，任务和下载 URL 必须同源；若服务商使用跨域签名 CDN 结果，需增加经审核的无凭证下载策略，本版本不会向跨域发送密钥。

## 请求方式

Windows `auto` 预先选择 PowerShell 7/5.1，请求头和二进制请求体经标准输入传入随附 `http_request.ps1`；JSON 响应中的 base64 不直接显示给用户。macOS/Linux `auto` 使用 urllib。显式 `--transport` 可选择方式，但不会在请求失败后自动切换，以免重复扣费。真实测试中 urllib 多次返回上游 `upstream_server_error` 502，而相同地址、凭证和提示词的 PowerShell 对照成功；不能据此断言所有 urllib 或所有 macOS/Linux 环境都失败或成功。
