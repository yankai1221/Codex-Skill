# ZZZPLUS Codex 图片生成 Skill

版本：1.0.0。Python 3.11+，无需 pip 运行依赖。Windows 默认调用自带 PowerShell（优先 PowerShell 7，其次 5.1）；macOS/Linux 默认使用 Python 标准库网络请求。

通过自然语言生成图片、设计海报/宣传图/插画/封面、编辑单图、融合多张参考图。固定模型 `gpt-image-2.5`，只读现有 Codex 中转 Provider 和可复用静态凭证，不修改主模型，不要求设置 ZZZPLUS_API_KEY。

**验收边界：请先阅读 [测试报告](TEST_REPORT.md) 和 [未解决问题](KNOWN_ISSUES.md)。异步脚本支持可配置的真实轮询，但上游公开文档未给出查询协议，不能开箱即用地保证异步端到端成功。**

## 安装（通用，推荐）

1. 下载独立 ZIP 并解压。找到其中的 `zzzplus-imagegen` 文件夹。
2. 确认 Python 版本至少 3.11。
3. 进入该文件夹，执行：

```text
python scripts/install.py install
```

Windows 若 `python` 不可用，改为 `py -3`；macOS/Linux 通常改为 `python3`。安装到官方用户级 Skill 目录 `~/.agents/skills/zzzplus-imagegen`。重开 Codex 会话后即可被发现；不需要把生图模型加入聊天主模型列表。

也可手动把整个 `zzzplus-imagegen` 文件夹复制到 `~/.agents/skills/`，或项目的 `.agents/skills/`。若所用旧版 Codex 仅发现 `~/.codex/skills/`，手动复制到那里，或指定 `--target` 为该 skills 父目录。不要同时安装到多个发现目录，以免出现重名 Skill。

验证（在 Skill 目录运行）：

```text
python scripts/imagegen.py check
```

只显示 Provider 地址、认证来源和固定图片模型，不显示密钥。Skill 不会更改现有配置。如果只有 Codex OAuth 登录缓存或凭证助手，需用户在本机为当前 Provider 补充兼容静态凭证配置；不能假设登录缓存能被脚本使用。不要把密钥贴到聊天、命令行或 GitHub。

`--transport auto` 在 Windows 提交前选定 PowerShell，其他系统选定 urllib；也可显式传 `--transport urllib` 或 `--transport powershell`。失败后绝不自动换方式重复提交。Windows 的认证信息仅通过子进程标准输入传递，不放进命令行或临时文件。完整 PowerShell 文件也包含在安装包中。

## 在 Codex 中使用

直接说：“生成一张日出湖景”“设计一张产品宣传海报”“根据这张图片把背景改成雪山”“参考第一张的场景和第二张的产品融合生成新图”。也可明确写 `$zzzplus-imagegen`。

脚本会根据模式调用中转站并保存到当前目录 `generated-images/`，文件名含时间和 UUID，不覆盖旧图。Codex 检查后展示图片。不同 Codex 实例的 profile、项目配置或启动覆盖必须如实传给脚本；遇到歧义先确认，不会凭静态主配置声称已识别所有会话状态。

命令行可选用法：

```text
python scripts/imagegen.py generate --prompt "A quiet lake at sunrise"
python scripts/imagegen.py edit --prompt "保持人物不变，将背景改成湖泊" --image "/absolute/input.png"
python scripts/imagegen.py edit --prompt "Image 1 提供场景，Image 2 提供产品，融合两者" --image "/absolute/scene.png" --image "/absolute/product.png"
python scripts/imagegen.py async --prompt "A quiet lake at sunrise" --async-spec "/absolute/confirmed-protocol.json"
python scripts/imagegen.py poll --job-file "/absolute/generated-images/job-UUID.json"
```

Windows 路径使用带引号的实际盘符路径。长 prompt 可以用 `--prompt-file` 指定 UTF-8 文件。图片编辑支持 PNG/JPEG/WebP，最多 8 张，单张 10MB、总共 40MB。真实图片尺寸由服务端决定，不能保证指定分辨率。

## 升级

解压新版本，在**新版本目录**执行：

```text
python scripts/install.py install --upgrade
```

旧版本整体移至 skills 父目录旁的 `skill-backups/zzzplus-imagegen-UUID`，再安装新版。不覆盖用户的 Codex 配置和生成图片。若安装在自定义目录，升级时使用相同的 `--target`。安装包无需额外依赖下载。

## 卸载与恢复

```text
python scripts/install.py uninstall
```

卸载会将本 Skill 从发现目录移到 `skill-backups`，保留备份，不删除图片和主配置。自定义目录使用同一 `--target`。重开 Codex 会话生效。需要恢复时手动将选定备份移回原安装位置；确认不再需要后可自行删除备份。手动安装也可仅移走 `zzzplus-imagegen` 目录。

## 测试

```text
python -m unittest discover -s tests -v
```

离线契约测试使用本地 HTTP 服务器和公开测试图片字节，不调用付费接口。离线通过不代表真实服务商已验收。真实验收结果见测试报告。
