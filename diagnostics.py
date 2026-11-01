"""首次使用的只读本机检查；不联网、不安装软件、不公开本机路径。"""
import importlib.util
import platform
import shutil
import sys
from pathlib import Path


def readiness(root, integrations):
    root = Path(root)
    ai, harness = integrations.read('ai'), integrations.read('harness')
    mode = ai.get('mode', 'harness')
    if mode == 'compatible':
        from compatible_ai import config_for
        try: config_for(ai); configured = True
        except ValueError: configured = False
    else:
        configured = bool(ai.get('apiKey')) if mode == 'deepseek' else bool(harness.get('cookies'))
    from transcript_sources import asr_status, ytdlp_prefix
    transcription = asr_status(root)
    try: ytdlp_prefix(root); captions_ready = True
    except ValueError: captions_ready = False
    checks = [
        {'id':'library', 'name':'收藏、文字笔记与 JSON / Markdown 备份', 'ready':True, 'detail':'基础功能已可使用，不需要模型密钥。'},
        {'id':'ai', 'name':'AI 笔记与知识模块', 'ready':configured, 'detail':'已保存 AI 配置，实际连通性与额度以服务为准。' if configured else '在 AI 设置中连接 Harness、官方 API 或兼容接口。'},
        {'id':'captions', 'name':'视频字幕读取', 'ready':captions_ready, 'detail':'需要 yt-dlp；YouTube 提取还可能需要 Node.js。也可以直接导入文字或字幕文件。'},
        {'id':'node', 'name':'YouTube JavaScript 运行时', 'ready':bool(shutil.which('node')), 'detail':'仅用于部分视频平台提取，文字课程无需此项。'},
        {'id':'asr', 'name':'无字幕音轨的本机转录', 'ready':bool(transcription.get('ready')), 'detail':'可选：Python 3.10+ 运行 tools/setup_transcription.py；首次安装会下载模型。'},
        {'id':'pdf', 'name':'PDF 与无边记导出依赖', 'ready':bool(importlib.util.find_spec('reportlab') and importlib.util.find_spec('pypdfium2')), 'detail':'可选：在运行环境安装 requirements.txt；中文导出还需要中文字体。其他 Python 环境的依赖不计入本次自检。'},
    ]
    return {'platform':{'Darwin':'macOS','Windows':'Windows','Linux':'Linux'}.get(platform.system(),platform.system()),
            'python':platform.python_version(), 'checks':checks, 'aiConfigured':configured,
            'privacy':'资料和密钥保存在当前电脑。选择云端模型时，所选学习资料会发送给该模型服务。'}
