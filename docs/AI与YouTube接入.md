# 连接 Harness、AI 整理与 YouTube

## 1. 连接你已有的 DeepSeek Harness

1. 在终端运行你已经使用的 `npx @deepseek-ai/dsh web`，保持终端运行。
2. 知识库左侧点“AI / Harness 设置”，再点“连接 Harness”。
3. 将终端最新打印的完整本机启动链接粘贴进密码输入框，点“连接并检查模型”。
4. 设置里的模型显示成功后，点“检查连接”，确认服务仍可访问。

启动链接带有登录 token。应用将其交换为服务支持的签名会话凭据，只保存于 `.local/harness.json`，不会把启动 token 显示到页面或提交到仓库。Harness 登录失效时使用终端最新链接重新连接。

本项目按已安装的 DSH `0.2.1-rc.2` 实际接口实现：`/api/session/modelCatalog`、`create`、`rename`、`prompt`、`projections`、`page` 和 `cancel`。它为每个整理任务创建独立学习会话，使用 `minimal` preset，只读取自己创建会话的结果。提示词要求纯文本整理，不调用工具。该 preset 仍属于 Harness agent 运行时，工具与权限由你的 Harness 配置决定；如果需要完全没有 agent 工具的纯模型调用，可切换到官方 API 模式。

这里调用 Harness 自己的会话接口，复用原有模型配置。后续 Harness 版本改变协议时，需要按实际接口更新适配器。

## 2. 使用 DeepSeek 官方 API

在“AI / Harness 设置”中把“整理时使用”切换成“DeepSeek 官方 API”，填写模型名称与 API Key。默认使用官方文档列出的 `deepseek-flash`，也可以按你的账户权限修改。Key 在本机保存，后续打开设置不会回显。

来源：[DeepSeek 官方 API 入门](https://api-docs.deepseek.com/)。模型名称和供应商价格可能更新，以账户和官方文档为准。

## 3. 一链接入库：自动分类并写笔记

连接一次 AI 后，点“粘贴链接一键整理”，只填公开 YouTube 视频链接。应用先保存链接，再识别标题和作者，读取公开字幕，交给 AI 选择现有分类或建立新分类、提取标签、撰写中文学习笔记并自动保存。结果标注本视频来源 `[S1]`，请结合原视频核对。分类结构仍为“分类 → 视频 → 笔记”。

字幕使用本机 `yt-dlp`，不是 YouTube 账号读取接口。安装方式见 [yt-dlp 官方文档](https://github.com/yt-dlp/yt-dlp#installation)，并按其说明准备 JavaScript 运行时；本项目自动检测 Node.js。字幕可以是人工字幕或自动字幕，自动字幕可能存在识别错误。只获取文字，不下载音视频、不使用浏览器 Cookie。

没有字幕时，AI 只根据标题分类，正文笔记强制留空，显示“待补充字幕”。在视频详情粘贴并保存转录，再点“重新自动整理”。其他平台保留手动收藏与粘贴资料。标题识别、网络或模型失败时保留链接，显示原因，不自动重试计费请求。服务器重启将未完成任务标记为中断，需要手动重新整理。

一键整理最多发送字幕前 10 万字符，超长资料会在结果提示处理范围。自动流程只向模型发送本视频标题、作者、字幕及分类目录；不会发送 OAuth 配置、API Key、Harness Cookie 或其他视频笔记。调用模型本身的鉴权凭据只用于向所选服务认证。

也可以使用人工核对草稿流程：先保存字幕或个人笔记，点“AI 整理笔记”，编辑草稿后“加入视频总结”。草稿保存在页面内存，刷新前请保存。自动整理与手动 AI 操作共享模型锁，同一时间只调用一个任务；不自动更换服务商。

## 4. 从多个视频提炼共通经验

1. 为至少两条视频保存有内容的字幕或笔记。
2. 打开它们所属分类，点“归纳共通经验”；也可从“AI 总结与经验”选择其他分类中的视频。
3. 勾选 2 到 12 条视频，填写主题，例如“网络故障排查的通用步骤”。
4. AI 比较共通点、差异与适用条件，并提炼可复用步骤，重要结论应标注 `[S1]`、`[S2]` 等来源。
5. 核对后保存，之后可以搜索、导出并查看原视频来源。

一次最多发送 14 万字符的资料；更长内容先按章节整理。结论需要结合原材料核对，资料不足时应保留疑问。

AI 整理会将勾选的资料发送给当前模型服务。Harness 默认可能使用云端 DeepSeek，也可能由你配置成本地模型；处理位置由实际模型配置决定。开源时排除个人资料不代表云端 AI 从不处理它们。

## 5. 可选：授权 YouTube 账号（粘贴链接无需此步骤）

这里授权的是**你自己运行的学习知识库**。项目通过 Google 官方授权页取得只读权限，不使用浏览器登录文件。

### 首次准备 OAuth 客户端

1. 打开 [Google Cloud API 控制台](https://console.cloud.google.com/apis/dashboard)，选择或新建一个项目。
2. 在 API 库启用 **YouTube Data API v3**。
3. 在 **Google Auth Platform** 配置应用名称、支持邮箱和受众。个人开发可以使用测试状态，并把自己的 Google 账号加入测试用户。
4. 在 **Clients / 客户端** 创建 OAuth 客户端，应用类型选择 **Desktop app / 桌面应用**。
5. 下载该客户端的 JSON 配置。

首次使用 Google Cloud 如果显示服务条款，由你本人阅读并确认。此项目不需要创建付费服务器或购买域名。

### 在知识库里连接

1. 左侧点“YouTube 播放列表（可选）”。
2. 点“导入 OAuth 客户端 JSON”，选择刚下载的桌面应用客户端文件。
3. 点“连接 YouTube”，再点“打开 Google 授权页”。
4. 在 Google 页面自己选择账号并确认 **查看 YouTube 账号** 的只读权限。这里不请求修改、删除视频或发表评论的权限。
5. Google 跳回本机成功页面后，回到知识库点“我已完成，读取账号”。

授权链接有效期为 10 分钟。Google 测试状态可能限制可登录用户和授权有效期，出现 `access_denied` 时先核对测试用户名单。桌面应用回调地址由端口自动组成，默认是 `http://127.0.0.1:8765/api/youtube/callback`。

随后可以读取频道名称和自己的播放列表，选择某个列表，预览后把勾选视频导入已有分类。每页最多 50 个，可继续读取下一页；相同链接会跳过，不覆盖已有笔记。

账号接入范围是频道信息、自建播放列表与列表内视频。观看历史、稍后观看不作为可保证的导入来源；任意他人视频的字幕也不是账号只读权限的一部分。

断开本机连接会删除本项目保存的 YouTube token。若要撤销 Google 端授权，可在 [Google 账号的第三方连接](https://myaccount.google.com/connections) 中移除对应应用。

官方参考：[桌面应用 OAuth 与 PKCE](https://developers.google.com/youtube/data/guides/auth/installed-apps)、[读取自己的播放列表](https://developers.google.com/youtube/data/reference/rest/v3/playlists/list)、[字幕下载权限](https://developers.google.com/youtube/data/reference/rest/v3/captions/download)。

## 6. GitHub 保存的是什么

开源仓库只保存项目代码、文档、MIT 许可证和 `data/library.example.json` 空白示例。个人视频收藏、字幕、总结、笔记与经验归纳位于被 Git 忽略的 `data/library.json`；API Key、Harness 凭据、YouTube OAuth 客户端和 token 位于被忽略的 `.local/`。

导出 JSON 包含个人学习资料，不包含连接凭据，应该自行保管，不能把它当成开源示例上传。提交前使用 `git status --ignored` 和 `git diff --cached` 检查内容，也要检查提交作者邮箱是否符合自己的隐私要求。

GitHub 保存项目不等于网页已在线部署。本机服务需要终端运行，点“保存”也不会自动提交 GitHub。跨设备同步、在线登录和自动任务属于后续开发。
