"""Official, fixed-host DeepSeek model discovery. No Harness or paid generation."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request
from security import credential_urlopen


def list_models(engine, draft_key=None):
    from integrations import IntegrationError
    key = draft_key if draft_key not in (None, '') else engine.read('ai').get('apiKey', '')
    if not isinstance(key, str) or not key.strip() or len(key) > 1000 or any(c.isspace() for c in key):
        raise IntegrationError('请填写 DeepSeek API Key，或先保存有效密钥')
    request = Request('https://api.deepseek.com/models', headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json'})
    try:
        with credential_urlopen(request, timeout=20) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024: raise ValueError()
        result = json.loads(raw)
        models = [{'id': item['id']} for item in result.get('data', [])[:200]
                  if isinstance(item, dict) and isinstance(item.get('id'), str)
                  and re.fullmatch(r'[^\x00-\x20\x7f]{1,100}', item['id'])]
        if not models: raise ValueError()
        return {'models': models, 'message': '连接成功，已读取当前账号的模型；未生成正文，密钥需点击保存后才保存。'}
    except HTTPError as error:
        raise IntegrationError('DeepSeek 连接检查失败（HTTP %s），请核对密钥和账号权限' % error.code)
    except (URLError, OSError):
        raise IntegrationError('暂时连接不到 DeepSeek 官方 API，请稍后重试')
    except (ValueError, TypeError, AttributeError):
        raise IntegrationError('DeepSeek 未返回有效模型列表，已有设置保留')
