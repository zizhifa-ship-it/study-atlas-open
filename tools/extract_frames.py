"""读取少量公开视频画面，不保存完整视频；输入与输出路径由服务端控制。"""
import json
import os
import sys
from pathlib import Path
import av


if __name__ == '__main__':
    request = json.load(sys.stdin); folder = Path(request['folder'])
    with av.open(request['url'], options={'headers': 'Referer: ' + request['referer'] + '\r\nUser-Agent: Mozilla/5.0\r\n'}, timeout=(12, 20)) as source:
        for item in request['frames']:
            source.seek(int(item['timeSec'] * av.time_base), backward=True)
            for index, frame in enumerate(source.decode(video=0)):
                if index > 2000: raise RuntimeError('Cannot seek near requested scene')
                if frame.time is None or frame.time < item['timeSec']: continue
                width = min(960, frame.width); width -= width % 2
                height = round(frame.height * width / frame.width); height -= height % 2
                frame = frame.reformat(width=width, height=height, format='yuvj420p')
                frame.pts = None
                target = folder / item['asset']; temp = target.with_suffix('.tmp')
                with av.open(str(temp), 'w', format='image2') as output:
                    stream = output.add_stream('mjpeg', rate=1); stream.width=width; stream.height=height; stream.pix_fmt='yuvj420p'
                    for packet in stream.encode(frame): output.mux(packet)
                    for packet in stream.encode(None): output.mux(packet)
                os.chmod(temp, 0o600); os.replace(temp, target)
                break
