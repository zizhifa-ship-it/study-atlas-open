# 学习图谱 · Study Atlas

一个适合初学者阅读和修改的视频学习知识库。按 **分类 → 视频 → 笔记** 整理学习资料。

- 创建多级分类，整理自己的课程目录。
- 收藏 YouTube、哔哩哔哩和其他平台的视频链接。
- 标记待学习、学习中、已学完，以及重点收藏。
- 为视频写知识总结和带时间点的笔记。
- 搜索标题、作者、分类、标签及笔记正文。
- 导出完整 JSON 备份或 Markdown 笔记，合并导入备份。
- 每次保存前自动备份，保留最近 30 份；不同页面的保存冲突会提示。
- 连接本机 DeepSeek Harness，或配置 DeepSeek 官方 API。
- 根据字幕、转录和现有笔记生成可编辑草稿，核对后加入视频总结。
- 比较多条视频的共通规律、差异和适用条件，归纳可复用经验并保留来源。
- 通过 YouTube 官方只读授权读取自己的频道和播放列表，选择后导入视频。

默认提供通用学习分类和空白视频库。首次启动时自动从 `data/library.example.json` 创建本机数据文件。源码采用 MIT 许可证，个人学习资料与连接凭据不提交。

## 在 Mac 上启动

在项目目录执行下面的命令启动，保持终端窗口运行。也可以先执行 `chmod +x 启动学习图谱.command`，再双击这个启动文件。

```sh
python3 server.py --open
```

打开 <http://127.0.0.1:8765>。按 `Control+C` 停止服务，资料仍然保留。

需要 Python 3.9 或更新版本。后端只用标准库，无需安装 npm 包或数据库。基础整理功能不需要密钥；AI 功能需要已有的 Harness 连接或 DeepSeek API Key。若系统中没有 Python，可从 [Python 官网](https://www.python.org/downloads/) 安装，然后使用上面的命令。

端口冲突时：

```sh
python3 server.py --port 8766 --open
```

启动脚本默认使用 Mac 自带开发工具提供的 `/usr/bin/python3`。如果你的 Python 安装在别处，改用终端中的 `python3 server.py --open`。

## 第一次使用

1. 点“新建分类”，创建自己的学习方向；进入分类后可以继续添加子分类。
2. 进入分类，点“收藏视频”，粘贴链接、填写标题并选择分类。
3. 打开视频卡片，点“打开视频”在原平台观看。
4. 回到知识库写总结，或在“时间点笔记”记录例如 `4:25` 的知识点。
5. 用顶部搜索框搜索笔记中的关键词。按 `/` 可以直接定位搜索框。

手动收藏时填写标题；从 YouTube 播放列表导入时会带上标题和作者。视频在原平台播放，部分平台不支持时间跳转。本版本不下载完整视频。

## AI 整理与 YouTube 授权

详见 [AI 与 YouTube 接入指南](docs/AI与YouTube接入.md)。

AI 操作顺序：保存字幕或笔记 → 点击“AI 整理笔记” → 核对可编辑的草稿和来源 → 加入总结。多视频归纳在分类页“归纳共通经验”或“AI 总结与经验”页面发起。AI 草稿暂存在当前页面内存，刷新前请保存需要保留的结果。

Harness 连接复用你已运行的本机服务；DeepSeek API 模式调用官方 `https://api.deepseek.com/chat/completions`。点击生成会使用原模型账户的额度或计费规则。生成失败不会自动切换服务商或重复发起付费请求。

YouTube 官方只读授权需要自己的 Google Cloud 桌面 OAuth 客户端。账号授权与字幕读取是两个流程；官方字幕下载接口要求拥有视频编辑权限。自动字幕按钮使用本机 `yt-dlp` 读取可用字幕，失败时可手动粘贴转录。[YouTube 官方字幕权限说明](https://developers.google.com/youtube/data/reference/rest/v3/captions/download)

连接凭据放在 `.local/`，文件权限为仅当前用户可读写；该目录已被 Git 忽略，不包含在应用导出的学习资料中。Google 授权使用 PKCE、一次性 state 与 `youtube.readonly` 权限。

“本地保存”指存储位置。使用 AI 时，选中的字幕与笔记会发送给所配置的模型服务；读取 YouTube 账号时会与 Google 通信。这些资料不会上传到 GitHub。

## 文件与保存

```text
study-atlas/
├── index.html              页面结构
├── styles.css              页面样式、手机布局
├── app.js                  分类、视频、笔记和搜索逻辑
├── server.py               本机服务、数据校验和保存
├── integrations.py         Harness、DeepSeek API、YouTube OAuth
├── data/
│   ├── library.json        你的分类、视频和笔记
│   ├── library.example.json 可提交的空白示例
│   └── .backups/           自动备份（不会提交到 GitHub）
├── docs/
│   ├── 从零开发.md          按功能顺序学习开发
│   └── AI与YouTube接入.md    连接与授权步骤
├── tests/                  数据保存、接口和连接测试
└── 启动学习图谱.command
```

`data/library.json` 是正式数据源，已被 Git 忽略。使用页面保存时文件会直接更新；关闭浏览器或停止服务不会清空资料。通过“导出与备份”下载的 JSON 包含个人学习资料，请自行保管。

本版本在自己的电脑运行，访问地址只绑定 `127.0.0.1`。GitHub 保存项目源码、文档与空白示例；个人视频库、笔记、账号配置和凭据留在本机。网页里的“保存”不会上传 GitHub，也不会自动同步手机。跨设备使用可通过自行保管的 JSON 备份导入，在线同步需要后续开发。

恢复自动备份：先停止服务，将 `data/.backups/` 中选中的 JSON **复制**到其他位置留存，再通过页面的“从备份合并导入”恢复缺少的视频。如果需要恢复被修改的旧笔记，先导出当前完整 JSON，然后在停止服务的情况下，用选定备份替换 `data/library.json`。合并导入遇到重复视频链接会保留当前版本。

## 学习开发与上传 GitHub

从 [从零开发教程](docs/从零开发.md) 开始，先学分类，再学视频，最后学笔记和 Git。每个阶段都有一个可以动手完成的小练习。

本项目可以公开开源。`data/library.json`、`.local/`、自动备份、临时文件和完整视频都在 `.gitignore` 中。不要使用 `git add -f` 强制添加这些个人资料。示例数据只放在 `data/library.example.json`，不含真实账号或个人视频收藏。

GitHub 普通仓库会阻止超过 100 MiB 的单个文件，所以这里收录视频链接。需要管理完整视频时，可以另设本地视频目录或对象存储。[GitHub 大文件说明](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)

## 验证保存功能

```sh
python3 -m unittest discover -s tests -v
```

测试使用临时数据副本，不修改你的知识库。检查内容包括保存后重新读取、自动备份、错误数据不覆盖原文件、保存冲突和 HTTP 读写。
