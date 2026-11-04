# iPad 独立使用与网页 DeepSeek API

本次增加的是可选入口，继续使用原来的 Python 后端、资料库、笔记模块、任务队列与模型调用机制。电脑本机版 `server.py`、局域网 `--lan` 和 Harness 仍可使用。

## 先区分网站和模型

| 方式 | iPad 访问条件 | 电脑是否必须运行 | 是否需要 Harness |
| --- | --- | --- | --- |
| Mac 局域网网站 + 官方 API | 同一私网，Mac 上的网站服务运行 | 是，仅网站服务 | 否 |
| Mac 局域网网站 + Harness | 同一私网，网站与 Harness 均运行 | 是 | 是 |
| 独立服务器 + 网页 API（新增） | iPad Safari 打开自己的 HTTPS 域名 | 否 | 否 |

只切换成 API 不会把网站自动部署到互联网。GitHub 仓库和 GitHub Pages 也不负责运行 Python、保存私有资料或保管 API Key。

## 网页直接设置 DeepSeek

1. 打开“AI 连接设置”，选择“DeepSeek 官方 API（网页直连，无需 Harness）”。
2. 输入自己的 API Key，点击“检查连接并读取模型”。此步骤只读取账号模型，不生成笔记；草稿密钥不会在检查时自动保存。
3. 从模型输入框选择实际模型 ID，点击“保存 AI 设置”。
4. 导入 PDF、文字或视频资料，再生成笔记、脑图与复习题；各功能继续使用同一套队列、校验与缓存。

网站后端调用官方 `https://api.deepseek.com/models` 和 `https://api.deepseek.com/chat/completions`。浏览器不用跨域请求 DeepSeek，也不会把密钥写入 localStorage、JSON 备份或导出讲义。保留已保存密钥时不要在输入框重新填写；连接错误不自动切换模型或重复付费调用。所选学习资料会发送至 DeepSeek，费用按自己的账号计算。

官方接口说明：[模型列表](https://api-docs.deepseek.com/api/list-models/)、[聊天生成](https://api-docs.deepseek.com/api/create-chat-completion/)。

## 独立服务器：已有服务器后再执行

本仓库提供 `deploy/compose.yml`、`deploy/Dockerfile`、Caddy HTTPS 配置和 `private_server.py`。它们不是已经上线的网站；需要一台安装 Docker Compose 的服务器和指向该服务器的域名。暂不购买服务器也可保留配置，继续使用电脑版本。

1. 在服务器下载项目，复制 `deploy/.env.example` 为 `deploy/.env`。
2. 编辑 `deploy/.env`：填 `PUBLIC_HOST=自己的域名`（不带 https:// 或路径）、至少 16 位的独立随机 `STUDY_ATLAS_ACCESS_PASSWORD`。`DEEPSEEK_API_KEY` 可留空，在网站中设置。
3. 确认域名 A/AAAA 记录和服务器一致，允许外部访问 80/443。执行：

```sh
docker compose --env-file deploy/.env -f deploy/compose.yml up -d --build
```

在 iPad 打开 `https://自己的域名`，输入网站口令，再在网页选择模型。服务器持续运行时，Mac 可以关机。登录 Cookie 采用 HttpOnly、Secure、SameSite=Strict；默认七天会话。退出登录或修改部署口令会撤销已有会话。口令以加盐摘要校验，不把明文登录口令写进资料卷。

查看与停止：

```sh
docker compose --env-file deploy/.env -f deploy/compose.yml logs --tail 50 atlas
docker compose --env-file deploy/.env -f deploy/compose.yml down
```

不要加 `down -v`，否则会删除资料卷。更新项目后重新执行 `up -d --build`。个人资料在 `atlas-state` 持久卷；迁移前在网页导出 JSON，另行备份整个资料卷。API Key 不在 JSON 备份中，新环境需要重新配置。

## 部署边界

- 这是**单人私有网站**，不是公共多人 SaaS。持有同一口令的设备有同样权限和一份资料；仍通过修订号避免过期页面覆盖新内容。
- 只有 Caddy 暴露 80/443，应用端口 8765 不映射到公网。不要另行发布应用端口；后端仅信任配置的 HTTPS Host、Origin 和代理协议头。
- 部署版默认官方 API，禁用服务器上的本机 Harness / Ollama / LM Studio 选项；电脑版保留这些选项。可选云端兼容 API 仍支持各自独立密钥。
- 镜像构建采用白名单文件，排除 `.local`、个人资料库、密钥、日志、导出文件和真实 PDF。`deploy/.env` 被 Git 忽略，示例仅含空密钥和占位值。
- 镜像包含 PDF 文字读取、中文字体、yt-dlp、FFmpeg 和 Node.js。视频平台仍可能要求登录、限流或没有字幕；本配置不安装大型本地语音模型。无字幕资料可以补充转录或 PDF，不能保证所有链接都自动读取成功。
- Caddy 自动 HTTPS 需要正确的 DNS、可达域名和证书签发条件。参考 [Caddy HTTPS 指南](https://caddyserver.com/docs/quick-starts/https) 与 [代理头说明](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)。
