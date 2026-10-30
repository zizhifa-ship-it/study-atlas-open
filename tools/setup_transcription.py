"""安装独立的可选本机转录环境与模型，不改变系统 Python。"""
import json
import os
import subprocess
import sys
from pathlib import Path


if __name__ == '__main__':
    if sys.version_info < (3, 10):
        raise SystemExit('本机转录需要 Python 3.10 或更新版本，请安装后再运行此脚本。')
    root = Path(__file__).resolve().parent.parent
    env = root / '.venv-asr'
    runtime = env / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    model = sys.argv[1] if len(sys.argv) > 1 else 'base'
    if model not in {'base', 'small', 'medium'}: raise SystemExit('请选择 base、small 或 medium 模型')
    if not runtime.is_file(): subprocess.run([sys.executable, '-m', 'venv', str(env)], check=True)
    print('安装本机转录依赖…', flush=True)
    subprocess.run([str(runtime), '-m', 'pip', 'install', '-r', str(root / 'requirements-transcription.txt')], check=True)
    local = root / '.local'; local.mkdir(mode=0o700, exist_ok=True)
    models = local / 'asr-models'; models.mkdir(mode=0o700, exist_ok=True)
    print('下载转录模型，完成后处理音频无需模型 API…', flush=True)
    code = 'from faster_whisper import WhisperModel; import sys; WhisperModel(sys.argv[1],device="cpu",compute_type="int8",download_root=sys.argv[2])'
    subprocess.run([str(runtime), '-c', code, model, str(models)], check=True)
    target = local / 'transcription.json'
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump({'enabled': True, 'model': model, 'runtime': str(runtime.relative_to(root)), 'downloadRoot': '.local/asr-models'}, out)
    print('本机转录已启用。原字幕不可用时，网站会读取音轨并在本机转录。', flush=True)
