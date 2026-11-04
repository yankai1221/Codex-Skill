# 测试报告

测试日期：2026-11-04（Asia/Singapore）。版本：1.0.0。

## 真实接口验收

使用用户当时实际配置的当前 Provider，地址 `https://zzzplus.com/v1`，认证来源为该 Provider 的 `experimental_bearer_token`。报告不含凭证值；未使用 Wokey 密钥或其上游地址代替验收。

Windows：Python 3.14 + Windows 自动选择的 PowerShell 请求方式。

| 项目 | 结果 | 证据 |
|---|---|---|
| 文生图 POST /images/generations | 成功 | 57.8 秒，保存 PNG 1,859,534 字节，蓝色陶瓷球，已打开目视检查 |
| data[0].b64_json 解码 | 成功 | 上述图片均由该字段严格 Base64 解码保存，不是链接或文本文件 |
| 单图编辑 POST /images/edits | 成功 | 真正上传一张红色参考图，27.9 秒，PNG 1,191,003 字节，红色背景与白色球体，已打开检查 |
| 多图参考 | 成功 | 上传红、蓝两张独立 PNG，重复 `image` 文件字段；29.3 秒，PNG 1,531,567 字节，左红方块及右蓝球，已打开检查 |
| 异步请求返回任务 ID | **未通过** | 使用 Prefer: respond-async 和新 UUID Idempotency-Key 实际提交，返回 HTTP 502，没有拿到任务 ID |
| 真实任务状态查询 | **无法验收** | 无任务 ID，且公开文档未提供查询路由/完整协议；未猜测或发送臆造查询 |
| 真实异步结果获取与保存 | **无法验收** | 同上；不能用同步成功替代异步成功 |
| 当前 Provider 认证复用 | 成功 | 使用只读解析器从当前 Provider 读取现有凭证，不要求 ZZZPLUS_API_KEY |
| 原 Codex 配置/主模型不变 | 成功 | 真实测试前后 config.toml SHA-256 相同；脚本没有配置写入逻辑 |

实际提示词：

1. 文生图：`A studio photograph of a blue ceramic sphere on a white table, soft lighting, no text.`
2. 单图：`Use this red reference as the background color. Add a small white ceramic sphere in the center.`
3. 多图：`Image 1 provides the red color for the left cube. Image 2 provides the blue color for the right sphere. Show both objects on a white studio table, no text.`
4. 异步提交：`A minimal illustration of a green circle on a white background, no text.`

输入参考图由测试程序生成红、蓝纯色方块，不使用私人照片。所有真实输出图片及原始运行记录都留在开发验收目录，**不进入 ZIP 或 GitHub**。

## 请求方式差异

早期 Python urllib 的文生图、单图、多图、异步请求均返回 HTTP 502。进一步用与 PowerShell 成功请求一致的提示词、地址、凭证测试 urllib，仍出现 `upstream_server_error`；只更换客户端标识的诊断也未成功。认证相同已在内存比较验证，未输出密钥或其摘要。PowerShell 同步对照成功，因此 Windows 默认在提交前选择该方式，不会在失败后自动切换并重复扣费。尚不能确定上游行为差异的完整根因。

## 离线功能与契约测试

运行 `python -X utf8 -m unittest discover -s tests -v`：**20 项通过**。

覆盖：Provider/profile/运行时覆盖、配置层优先级、内置 openai_base_url、env_key 缺失拒绝回退、只读配置、静态 auth.json 与 OAuth 缓存隔离、大小写不敏感请求头覆盖、/v1 去重、Base64 真实字节保存、文件名不覆盖、非法图片拒绝、多图 multipart 解析、缺少异步协议时提交前拒绝、跨域拒绝、重定向不转发认证、安装/备份升级/卸载、拒绝移动无关目录、PowerShell 本地真实 HTTP 请求。

异步契约测试使用**本地测试服务器**确认 POST 提交 → 返回测试任务 ID → GET 状态 → 读取结果对象 → 保存图片，每次提交幂等键不同；另测失败及等待上限不保存图片。这些是离线自动化测试，**不是实际服务商异步验收通过的证据**。

独立 Skill 行为测试确认：不会把多图编辑擅自变成异步编辑；查询协议未确认时不会猜测轮询地址。发现的请求头大小写覆盖问题已通过先失败后通过的回归测试修复。

## 规范和分发检查

- 官方 `quick_validate.py`：通过（Skill is valid）。
- agents/openai.yaml：YAML 可解析，自动触发启用，默认提示词正确引用 Skill。
- 独立 ZIP 只含完整 Skill 目录；不含 API Key、个人配置、真实测试图片、运行缓存或原始接口响应。
- 跨平台安装/升级/卸载脚本在 Windows 临时目录实测通过；macOS/Linux 尚未上机验收。
- 所有已知限制见 [KNOWN_ISSUES.md](KNOWN_ISSUES.md)。不能将本报告解读为四种模式全部真实验收通过。
