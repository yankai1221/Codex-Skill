---
name: zzzplus-imagegen
description: Use for EVERY request to generate, draw, design or edit an image (posters, product promotional images, illustrations, covers, image editing, multi-image reference blending) through the configured Codex relay provider using gpt-image-2.6. In this relay environment the built-in image_gen tool and the built-in imagegen skill are NOT available and OPENAI_API_KEY is not needed - use this skill instead and never ask the user to set OPENAI_API_KEY. 用户要生成图片、画图、设计海报、修改图片或多图融合时一律使用本技能。
---

# ZZZPLUS 图片生成

把自然语言要求交给随附脚本执行，无需用户编写 API 请求。固定模型 `gpt-image-2.6`；使用当前 Codex Provider 中转地址，绝不切换到 Wokey 上游或其他模型。

## 开始前

1. 确认本会话实际生效的 Provider、profile、配置层及启动覆盖。脚本默认只读 `$CODEX_HOME/config.toml`（未设置则 `~/.codex/config.toml`），自动读取文件中的 profile。会话/CLI 覆盖无法从静态文件自动推断；有覆盖时传 `--profile`、已确认生效的 `--config-layer`（按低到高优先级）、非敏感 `-c 'model_provider="..."'`。有歧义就询问，不把文件默认值冒充会话值。不要自动加载未信任的项目配置。
2. 在本 Skill 目录运行 `python scripts/imagegen.py check`，核对地址和凭证来源。Python 需 3.11+，不依赖 pip 包；Windows 可用 `py -3`，macOS/Linux 常用 `python3`。`check` 会在提交前用免费的 `GET /models` 检测连通性并给出选中的 `transport`（Windows 先 PowerShell，不通则 urllib；其他系统 urllib）。如果 `check` 显示 transport 为空或报 SSL/TLS 错误，让用户检查网络/代理；PowerShell 报 SSL 握手失败时可显式加 `--transport urllib`。生图提交失败后禁止自动换方式重发，避免重复扣费。
3. 只复用脚本支持的当前 Provider 凭证。缺少静态凭证、使用未支持的凭证助手或仅有 OAuth 登录缓存时，按脚本提示让用户在本机补充兼容认证；不索要聊天明文密钥，不要求 `ZZZPLUS_API_KEY`。不要打印 config/auth 原文、环境变量值或认证请求头。不要用 `-c` 或命令行传密钥。

## 选择模式

- 文生图：`python scripts/imagegen.py generate --prompt "用户描述"`
- 单图编辑：`python scripts/imagegen.py edit --prompt "用户编辑要求" --image "/absolute/input.png"`
- 多图参考：同一 edit 命令重复 `--image`。先查看图片，明确顺序及用途；把“Image 1 是场景，保持构图；Image 2 是产品，保留外观”等角色写入 prompt。脚本上传所有图片为重复 `image` 文件字段，不是 `image[]`，也不是路径字符串。
- 异步文生图：先阅读 [异步协议与 API](references/API.md)。必须拿到经服务商确认的查询协议文件，再执行 `python scripts/imagegen.py async --async-spec "/absolute/protocol.json" --prompt "用户描述"`。当前文档只确认提交头，不含查询地址，未配置时禁止付费提交。异步编辑不在本版本支持范围内。

复杂描述或含引号/换行时，将 prompt 放入 UTF-8 文件，使用 `--prompt-file`；该临时文件不进入分发包。默认保存至当前工作目录 `generated-images`；可用 `--output-dir` 指定用户需要的位置。参考图片为 PNG/JPEG/WebP，1–8 张、每张不超过 10MB、总共不超过 40MB。实际尺寸和质量由服务端选择，不保证提示词中的分辨率。

## 完成与失败

仅在输出 `IMAGE_PATH=` 且检查实际图片后宣布成功，并用绝对路径展示图片；不能展示 Base64。返回本地路径、实际采用的 prompt 和本次模式。按宿主输出目录约定保存最终交付物。

HTTP 错误或提交超时不要自动重复付费生成；明确报告失败/未知状态。错误信息会区分 SSL 握手失败、连接失败（均为请求未发出，不扣费）、超时（状态未知，勿重发）和服务端 HTTP 状态码；把原始中文错误如实转告用户，不要笼统说成“HTTP 0”。异步任务 ID 不是成功，必须完成轮询并保存真实图片。达到等待上限时保留任务记录，使用 `poll --job-file "/absolute/job-....json"` 恢复，避免重新提交。不要转发凭证到跨域结果地址；本版拒绝跨域链接和 HTTP 重定向。

安装、升级、卸载见 [中文说明](README.md)。协议参数与凭证优先级见 [API 说明](references/API.md)。
