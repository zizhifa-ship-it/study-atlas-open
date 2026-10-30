"""可选独立环境中的语音识别进程。音频和模型都在本机使用。"""
import json
import os
import sys
from pathlib import Path
from faster_whisper import WhisperModel


def write_json(path, value):
    target = Path(path); temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False)); os.replace(temp, target)


if __name__ == '__main__':
    config = json.load(sys.stdin)
    model = WhisperModel(config['model'], device='cpu', compute_type='int8', download_root=config['downloadRoot'], local_files_only=True)
    segments, info = model.transcribe(config['audio'], beam_size=5, vad_filter=True, condition_on_previous_text=False)
    lines, timeline = [], []
    for segment in segments:
        if segment.text.strip():
            lines.append(segment.text.strip());timeline.append({'start':round(segment.start,3),'end':round(segment.end,3),'text':segment.text.strip()})
        if sum(len(line) for line in lines) > 200000: raise ValueError('Transcription exceeds the supported chapter size')
        write_json(config['progress'], {'seconds': segment.end, 'duration': info.duration})
    write_json(config['output'], {'transcript': '\n'.join(lines), 'language': info.language, 'segmentCount': len(lines), 'durationSec': info.duration, 'segments': timeline})
