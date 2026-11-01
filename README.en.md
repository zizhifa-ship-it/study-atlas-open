# Study Atlas

[简体中文](README.md)

A local-first learning library for public YouTube / Bilibili videos, classroom text and Markdown. Organize categories, sources and notes; create source-backed knowledge modules, Cornell notes, mind maps, translations and review questions. The interface is currently primarily Simplified Chinese.

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

MIT license. Contributions and reproducible bug reports are welcome. Do not attach credentials, personal libraries or private captions to public issues.
