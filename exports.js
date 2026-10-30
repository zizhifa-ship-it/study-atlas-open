import {localizedVideo} from './translations.js';
import {cornellData} from './cornell.js';
// 纯文本导出；只在用户主动下载时包含其个人学习内容。
export function libraryMarkdown(library, languages={}) {
  const lines=['# 我的学习图谱','','按“分类 → 视频 → 知识模块 → 笔记”整理。',''];
  const md=v=>String(v || '').replace(/[\\`*_{}\[\]<>#|]/g,'\\$&');
  const link=v=>String(v).replace(/[<>\s]/g,encodeURIComponent);
  const status={todo:'待学习',learning:'学习中',done:'已学完'};
  function addCategory(c,depth) {
    lines.push('#'.repeat(Math.min(depth,6))+' '+md(c.name),'',c.description || '','');
    for(const original of library.videos.filter(v=>v.categoryId===c.id)) {
      const v=localizedVideo(original,languages[original.id] || 'zh-CN');
      lines.push(`### [${md(v.aiTitle || v.title)}](<${link(v.url)}>)`,'',`- 作者：${md(v.author || '未填写')}`,`- 状态：${status[v.status]}`,`- 标签：${(v.tags || []).map(md).join('、') || '无'}`,'');
      if(v.summary) {const c=cornellData(v);lines.push('#### 康奈尔笔记','','**提示与问题**','',...c.cues.map(q=>'- '+q),'','**课堂记录**','',v.summary,'','**归纳小结**','',c.summary,'');}
      const k=v.knowledge;
      if(k) {
        lines.push('#### 知识模块与脑图大纲','',k.overview,'');
        for(const m of k.modules) {
          lines.push('- '+md(m.title),...m.concepts.map(c=>'  - '+md(c.name)), '');
        }
        for(const m of k.modules) {
          const c=cornellData(m);lines.push('#### '+md(m.title),'','**学习目标**：'+m.objective,'','**前置知识**：'+(m.prerequisites.join('、') || '无'),'','**康奈尔提示与问题**','',...c.cues.map(q=>'- '+q),'','**课堂记录**','',m.notes,'','**归纳小结**','',c.summary,'');
          if(m.procedure){const f=m.procedure;lines.push('**实验与操作流程**','','目标：'+f.goal,'',...f.requirements.map(t=>'- 条件：'+t),'');for(const [i,step] of f.steps.entries())lines.push((i+1)+'. '+step.action,'','预期现象：'+step.expected,'','验证方法：'+step.verify,'');lines.push('结果与边界：'+f.conclusion,'');}
          lines.push('**概念卡片**','',...m.concepts.map(c=>'- **'+md(c.name)+'**：'+c.explanation),'');
          if(m.examples.length) lines.push('**课程例子**','',...m.examples.map(t=>'- '+t),'');
          if(m.pitfalls.length) lines.push('**易错点**','',...m.pitfalls.map(t=>'- '+t),'');
          for(const q of m.questions) lines.push('**自测：'+md(q.question)+'**','',q.answer,'');
          for(const q of m.evidence) lines.push('> '+q.replace(/\n/g,'\n> '),'');
        }
        lines.push('#### AI 自查报告','',k.review.summary,'','AI 自查不保证全部结论正确。','');
        for(const i of k.review.issues) lines.push('- '+(i.resolved?'已修订':'待核对')+'：'+i.problem+'；建议：'+i.suggestion,'');
      }
      if(v.notes.length) lines.push('#### 我的补充与批注','');
      for(const n of v.notes) lines.push('**'+(n.timeSec===null?'随记':n.timeSec+' 秒')+'**','',n.text,'');
    }
    for(const child of library.categories.filter(x=>x.parentId===c.id)) addCategory(child,depth+1);
  }
  for(const c of library.categories.filter(c=>c.parentId===null)) addCategory(c,2);
  for(const i of library.insights || []) lines.push('## '+md(i.title),'',i.content,'',...i.sources.map(s=>`- [${md(s.source+' '+s.title)}](<${link(s.url)}>)`),'');
  if(library.learning?.attempts.length) {
    lines.push('## 自测与复习记录','','以下为个人作答及 AI 反馈，请自行保管。','');
    for(const a of library.learning.attempts) lines.push('### '+md(a.question),'',a.createdAt+' · '+(a.score===null?'不计分':a.score+' 分')+(a.assisted?' · 参考后作答':''),'','**我的答案**','',a.answer,'','**AI 反馈**','',a.feedback,'','**参考改写**','',a.suggestedAnswer,'','**下次复习**：'+(a.dueAt || '未更新'),'');
  }
  return lines.join('\n');
}
