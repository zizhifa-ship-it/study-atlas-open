# Study Atlas

[简体中文](README.md)

> **Noncommercial use is free. Commercial use of newly licensed material requires prior written permission from [zizhifa-ship-it](https://github.com/zizhifa-ship-it) and individually agreed fees.** [Policy and application](COMMERCIAL-LICENSE.md) · [Apply](https://github.com/zizhifa-ship-it/study-atlas-open/issues/new?template=commercial-license.yml). Previously MIT-licensed material retains its existing rights.

## Overview / 简介

A local-first AI learning library designed for beginners to explore and customize. Organize **categories → videos or class materials → notes**: paste public YouTube / Bilibili links or import text, Markdown and captions, connect your preferred model, and create source-backed knowledge modules, Cornell notes, mind maps, translations and review questions. Export PDF / iPad Freeform materials and JSON backups. The interface is currently primarily Simplified Chinese.

一个在自己电脑运行的 AI 学习知识库，适合初学者阅读和修改。按 **分类 → 视频或课堂资料 → 笔记** 整理内容，连接自己选择的模型，生成知识模块、康奈尔笔记、脑图、翻译和复习题，支持 PDF / iPad 无边记导出与 JSON 备份。详细中文说明见 [中文指南](README.md)。

> **许可：**非商业免费；受新许可约束的内容，商业使用须先获得书面许可并按约付费。旧 MIT 内容保留原权利，详见 [许可政策与申请](COMMERCIAL-LICENSE.md)。

## Run locally

Download the source ZIP and extract it into your own user folder. Python **3.9+** is required. Core storage, annotations, text imports and JSON / Markdown backups use only Python's standard library.

- Windows: double-click `start.bat`, or run `py -3 server.py --open`.
- macOS / Linux: run `sh start.sh` in the project folder.
- All platforms: `python server.py --open` with the appropriate Python executable.

Open `http://127.0.0.1:8765`. Keep the terminal running. Use `--port 8766` if needed. The app binds to loopback only; it is intended for each person to install on their own computer.

Open **首次使用 / 环境自检** in the sidebar for a read-only setup check. You can import TXT, Markdown or caption files before connecting AI. Plain text and Markdown preserve code indentation and line breaks. PDF / Word files need text extraction first.

## Choose an AI connection

Use an existing DeepSeek Harness, the official DeepSeek API, or the compatible-interface option with **Ollama, LM Studio, SiliconFlow or OpenRouter**. Local model servers require no Harness account. Select a provider, read its model list or enter a model ID, then save. Model quality and hardware requirements vary.

Local endpoints are restricted to loopback; cloud endpoints use fixed official addresses. Credentials are isolated per provider and redirects are rejected. Requests use non-streaming Chat Completions. See the [installation and provider guide](docs/安装与兼容接口.md) for supported endpoints and limitations.

## Optional features

PDF / Apple Freeform exports need `requirements.txt` and a Chinese font. Video extraction needs yt-dlp and may need Node.js. Local multilingual transcription needs Python 3.10+ and `tools/setup_transcription.py`; installation downloads model weights. These dependencies are optional for text-only use.

## Privacy and portability

Personal data stays in `data/library.json`; credentials, caches and models stay in `.local/` or ignored virtual environments. They are excluded from the public source package. Selected learning content is sent to the AI provider you configure; local storage does not mean cloud inference never receives it.

Export a complete JSON backup before upgrading or changing computers. Import it into a fresh installation; duplicate sources retain the existing version. Credentials and cached video frames are not included. Reconfigure connections on the new machine.

This is a single-user local app. Shared public hosting requires a separate design for authentication, HTTPS and data isolation.

## Development

```sh
python -m unittest discover -s tests -v
npm run check
npm run test:js
```

Browser tests use isolated temporary data and simulated AI. They require Playwright and a browser. The CI workflow defines Windows / macOS / Linux startup and onboarding tests on Python 3.9 and 3.12; check Actions for actual run results.

## License and commercial use

New original material, to the extent the maintainer has authority to license it, is covered by [LICENSE](LICENSE): noncommercial use is free, and commercial use requires a separate written license and compliance with agreed payment conditions. Prices and scope are quoted individually through the [commercial application](COMMERCIAL-LICENSE.md). A request, donation or payment alone does not grant a license.

Code and documentation previously published under MIT through commit `7bcb7e431bc6a7f1725cbab534906afbb7f7285e`, including the existing core functionality and that material retained in later releases, remain under [the original MIT license](LICENSE-MIT-LEGACY), including commercial-use rights. This change is not retroactive. The new restricted license is source-available, not OSI open source. Third-party rights remain unchanged.

Reproducible bug reports are welcome. Do not attach credentials, personal libraries or private captions to public issues.
