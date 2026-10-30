"""默认开启的无损省量：紧凑 JSON、已校验响应缓存与本机用量统计。"""
import copy
import hashlib
import json
import threading

_STATS_LOCK = threading.Lock()
VERSION = 1


def compact_json(value):
    # 不删除字段、正文或代码空白，只移除 JSON 结构分隔符的额外空格。
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def model_identity(engine):
    ai = engine.read('ai')
    if ai.get('mode', 'harness') == 'deepseek':
        return ['deepseek', ai.get('model', 'deepseek-flash')]
    harness = engine.read('harness')
    return ['harness', harness.get('baseUrl', 'http://127.0.0.1:3080'), harness.get('model', {})]


def record_usage(engine, **changes):
    """统计失败不影响笔记保存；仅保存计数，不保存正文或连接信息。"""
    try:
        with _STATS_LOCK:
            stats = engine.read('ai-efficiency')
            if not isinstance(stats, dict): stats = {}
            for key, value in changes.items():
                previous = stats.get(key, 0)
                stats[key] = (previous if type(previous) is int and previous >= 0 else 0) + max(0, int(value))
            engine.write('ai-efficiency', stats)
    except (OSError, ValueError, TypeError):
        pass


def record_model_call(engine, prompt, result):
    usage = result.get('usage') or {}
    if not isinstance(usage, dict): usage = {}
    inp = usage.get('prompt_tokens', usage.get('inputTokens'))
    out = usage.get('completion_tokens', usage.get('outputTokens'))
    values = {'modelCalls': 1, 'inputCharacters': len(prompt)}
    if type(inp) is int and type(out) is int and inp >= 0 and out >= 0:
        values.update(promptTokens=inp, completionTokens=out, usageReports=1)
    record_usage(engine, **values)


def efficiency_status(engine):
    try: stats = engine.read('ai-efficiency')
    except (OSError, ValueError): stats = {}
    if not isinstance(stats, dict): stats = {}
    keys = ['modelCalls', 'inputCharacters', 'cacheHits', 'avoidedInputCharacters', 'promptTokens', 'completionTokens', 'usageReports']
    return {'enabled': engine.read('ai').get('smartCache', True) is not False,
            **{k: stats.get(k, 0) if type(stats.get(k, 0)) is int and stats.get(k, 0) >= 0 else 0 for k in keys}}


def validated_request(engine, generator, prompt, validate, task):
    """仅缓存通过调用方完整校验的响应；命中后重新校验，损坏即重新生成。"""
    if engine is None or not callable(getattr(engine, 'write', None)):
        return validate(generator(prompt))
    enabled = engine.read('ai').get('smartCache', True) is not False
    key = hashlib.sha256(compact_json([VERSION, task, model_identity(engine), prompt]).encode()).hexdigest()
    name = 'ai-cache-' + key
    if enabled:
        try:
            cached = engine.read(name)
            if cached.get('version') == VERSION and cached.get('key') == key:
                value = validate(copy.deepcopy(cached['response']))
                record_usage(engine, cacheHits=1, avoidedInputCharacters=len(prompt))
                return value
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            pass
    response = generator(prompt)  # 网络或模型错误不缓存、不自动重试。
    value = validate(response)
    if enabled:
        try:
            engine.write(name, {'version': VERSION, 'key': key,
                               'response': {'content': response['content'], 'model': response.get('model', '')}})
            local = getattr(engine, 'local', None)
            if local is not None:
                # 有界私有缓存，已有课程笔记与翻译不参与清理。
                entries = sorted(local.glob('ai-cache-*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
                for old in entries[256:]:
                    old.unlink(missing_ok=True)
        except (OSError, ValueError, TypeError, KeyError):
            pass
    return value
