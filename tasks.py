"""整理任务的只读摘要与恢复路径；不向页面暴露资料正文或连接配置。"""
import hashlib
from ai_efficiency import model_identity
from knowledge import material_hash, material_for

ACTIVE = {'queued', 'metadata', 'transcript', 'ai'}
TASK_NAMES = {'import':'视频笔记', 'detailed':'视频与详尽模块', 'knowledge':'知识模块',
              'supplement-notes':'补充资料辅助笔记', 'review':'笔记自查', 'format':'康奈尔版式', 'visuals':'图文导学'}


def checkpoint_summary(engine, video):
    name = 'knowledge-job-' + hashlib.sha256(video['id'].encode()).hexdigest()[:24]
    try:
        job = engine.read(name)
        if not job:
            return {'available': False, 'reason': 'none'}
        if job.get('fingerprint') != material_hash(video):
            return {'available': False, 'reason': 'source_changed'}
        if job.get('version') != 3:
            return {'available': False, 'reason': 'legacy'}
        if job.get('modelKey') != model_identity(engine):
            return {'available': False, 'reason': 'model_changed'}
        draft = job.get('draft') or {}
        modules = draft.get('modules') or job.get('modules') or []
        total = len(draft.get('modules') or (job.get('plan') or {}).get('modules') or [])
        return {'available': True, 'reason': 'matched', 'mode': job.get('mode', 'build'),
                'modulesDone': len(modules), 'modulesTotal': total,
                'reviewsDone': len(job.get('reports') or []), 'reviewsTotal': (total + 1) // 2}
    except (ValueError, OSError, TypeError, AttributeError):
        return {'available': False, 'reason': 'unreadable'}


def recovery_mode(engine, video):
    task = video.get('automation', {}).get('task', '')
    checkpoint = checkpoint_summary(engine, video)
    if task in {'visuals', 'format', 'review'} or task.startswith('translate:'):
        return task
    if task == 'knowledge':
        return 'knowledge'
    if task == 'supplement-notes':
        if checkpoint['available']:
            return 'knowledge'
        digest = (video.get('transcriptInfo') or {}).get('digest')
        return 'supplement-notes' if isinstance(digest, str) and len(digest.strip()) >= 20 else 'saved-detailed'
    if task == 'import':
        return 'saved-import' if len(video.get('transcript', '').strip()) >= 20 else 'import'
    if checkpoint['available']:
        return 'review' if checkpoint.get('mode') == 'review' else ('saved-detailed' if task in {'', 'detailed'} else 'knowledge')
    if len(video.get('transcript', '').strip()) >= 20:
        # 已有总结时直接构建模块，避免重做导入与总结；用户批注不作为可覆盖目标。
        return 'saved-detailed'
    return 'detailed'


def task_snapshot(importer):
    with importer.lock:
        with importer.queue.mutex:
            waiting = [item[0] for item in importer.queue.queue]
        videos = importer.store.read()['videos']
        running = getattr(importer, 'running', None)
        items = []
        for video in videos:
            auto = video.get('automation') or {}
            if not auto.get('status'):
                continue
            status = auto['status']
            task = auto.get('task', '')
            try:
                _, material_kind = material_for(video)
            except ValueError:
                material_kind = ''
            items.append({'videoId': video['id'], 'title': video.get('aiTitle') or video['title'],
                          'status': status, 'message': auto.get('message', ''), 'model': auto.get('model', ''),
                          'task': task, 'taskName': '笔记翻译' if task.startswith('translate:') else TASK_NAMES.get(task, '课程整理'),
                          'queuePosition': waiting.index(video['id']) + 1 if video['id'] in waiting else None,
                          'running': bool(running and running[0] == video['id']),
                          'hasNotes': bool(video.get('summary') or video.get('knowledge')),
                          'hasMaterial': bool(material_kind), 'materialKind': material_kind,
                          'checkpoint': checkpoint_summary(importer.integrations, video) if status in ACTIVE | {'failed'} else {'available': False, 'reason': 'none'}})
    priority = {'metadata': 0, 'transcript': 0, 'ai': 0, 'queued': 1, 'failed': 2, 'needs_content': 2, 'ready': 3}
    items.sort(key=lambda x: (priority.get(x['status'], 4), x['queuePosition'] or 0))
    return {'items': items, 'counts': {'active': sum(i['status'] in ACTIVE for i in items),
             'waiting': sum(i['status'] == 'queued' for i in items),
             'attention': sum(i['status'] in {'failed', 'needs_content'} for i in items),
             'ready': sum(i['status'] == 'ready' for i in items)}}
