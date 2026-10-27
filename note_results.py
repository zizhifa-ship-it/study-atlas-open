"""保存 AI 结果时保留人工笔记与旧版总结。"""
import uuid
from datetime import datetime, timezone
from integrations import IntegrationError


def apply_ai_summary(target, content, model, previous_summary):
    stamp = datetime.now(timezone.utc).isoformat()
    content = content.strip()
    if not content or len(content) > 30000:
        raise IntegrationError("AI 笔记为空或太长，请分段整理")
    current = target.get("summary", "")
    note = None
    if current != previous_summary:
        # 人工在生成过程中修改了正文，保留正文，把 AI 结果另存为一条笔记。
        note = "AI 新整理 · " + model + "\n\n" + content
        message = "已保留你正在编辑的总结，AI 结果另存到补充笔记"
    else:
        if current and current != content:
            note = "旧版总结（AI 重新整理前保留）\n\n" + current
        message = "AI 笔记已自动保存"
    if note:
        if len(target.get("notes", [])) >= 1000 or len(note) > 30000:
            raise IntegrationError("补充笔记已满；请先导出备份并整理后重试，原资料未覆盖")
        target.setdefault("notes", []).append({"id": uuid.uuid4().hex, "timeSec": None, "text": note, "createdAt": stamp})
    if current == previous_summary:
        target["summary"] = content
    target["updatedAt"] = stamp
    return message


def persist_generation(store, request, result, original):
    with store.lock:
        data = store.read()
        if result["mode"] == "summary":
            vid = result["sourceIds"][0]
            target = next((v for v in data["videos"] if v["id"] == vid), None)
            baseline = next((v for v in original["videos"] if v["id"] == vid), None)
            if not target or not baseline:
                raise IntegrationError("视频已移除，生成结果没有写入原记录")
            if target["url"] != baseline["url"]:
                raise IntegrationError("视频链接已修改，旧资料的生成结果未写入")
            message = apply_ai_summary(target, result["content"], result.get("model", ""), baseline.get("summary", ""))
            target["automation"] = {"status": "ready", "message": message, "model": result.get("model", "")}
        else:
            sources = result["sources"]
            found = next((x for x in data.get("insights", []) if x["content"] == result["content"] and x["sources"] == sources), None)
            if not found:
                title = request.get("title", "我的学习共通经验")
                if not isinstance(title, str) or not title.strip() or len(title) > 300:
                    raise IntegrationError("经验标题格式不正确")
                found = {"id": uuid.uuid4().hex, "title": title.strip(), "content": result["content"], "sources": sources,
                         "model": result.get("model", ""), "createdAt": datetime.now(timezone.utc).isoformat()}
                data.setdefault("insights", []).append(found)
            result["insightId"] = found["id"]
        result["library"] = store.save(data)
        result["saved"] = True
        return result
