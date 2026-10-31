"""只暴露模型目录的必要字段；不把 Harness 原始配置传给浏览器。"""


def catalog_view(raw):
    raw = raw if isinstance(raw, dict) else {}
    routable = raw.get('routableProviders', [])
    groups = []
    def label(value, limit=200):
        return value[:limit] if isinstance(value, str) else ''
    for group in raw.get('groups', [])[:100]:
        if not isinstance(group, dict) or group.get('id') not in routable:
            continue
        models = []
        for model in group.get('models', [])[:200]:
            if not isinstance(model, dict) or not label(model.get('id')):
                continue
            reasoning = model.get('reasoning') or {}
            efforts = [{'id': label(e.get('id')), 'name': label(e.get('name') or e.get('id'))}
                       for e in reasoning.get('efforts', [])[:30] if isinstance(e, dict) and label(e.get('id'))]
            models.append({'id': label(model['id']), 'name': label(model.get('name') or model['id']),
                           'efforts': efforts, 'defaultEffort': label(reasoning.get('defaultEffort'))})
        if models:
            groups.append({'id': label(group['id']), 'name': label(group.get('name') or group['id']), 'models': models})
    default = raw.get('default') or {}
    return {'groups': groups, 'default': {k: label(default[k]) for k in ('provider', 'model', 'reasoningEffort') if k in default}}


def validate_selection(catalog, selection):
    if not isinstance(selection, dict):
        raise ValueError('请选择 Harness 模型')
    for group in catalog.get('groups', []):
        if group['id'] != selection.get('provider'):
            continue
        for model in group['models']:
            if model['id'] != selection.get('model'):
                continue
            selected = {'provider': group['id'], 'model': model['id']}
            effort = selection.get('reasoningEffort')
            if model['efforts']:
                effort = effort or model['defaultEffort'] or model['efforts'][0]['id']
                if effort not in [e['id'] for e in model['efforts']]:
                    raise ValueError('这个模型不支持所选推理强度，请刷新模型列表')
                selected['reasoningEffort'] = effort
            elif effort:
                raise ValueError('这个模型没有可选择的推理强度')
            return selected
    raise ValueError('所选模型当前不可用，请检查 Harness 的供应商配置并刷新模型列表；不会自动改用其他模型')
