#!/bin/zsh
cd "$(dirname "$0")"
asr_python=""
for candidate in python3 python3.12 python3.11 python3.10 "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3,10))' 2>/dev/null; then
    asr_python="$candidate"
    break
  fi
done
if [[ -n "$asr_python" ]]; then
  if "$asr_python" tools/setup_transcription.py; then
    echo "本机转录已启用，可返回学习图谱继续整理。"
  else
    echo "安装尚未完成，请查看上面的错误信息后重试。"
  fi
else
  echo "请先安装 Python 3.10 或更新版本，再运行此脚本。"
fi
read -r "?按回车关闭此窗口…"
