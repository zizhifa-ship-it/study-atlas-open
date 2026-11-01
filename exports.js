import {localizedVideo} from './translations.js';
import {cornellData} from './cornell.js';
// 纯文本导出；只在用户主动下载时包含其个人学习内容。
export const paperStageNames = {candidate:'待筛选',screening:'精读中',included:'已纳入',excluded:'已排除'};
const paperReviewNames = {question:'研究问题',method:'方法',data:'数据 / 样本',findings:'主要发现',limitations:'局限',relevance:'关联与可复用点'};
const flatText = value => String(value || '').replace(/\s+/g, ' ').trim();
const paperLabel = p => [String(p.year || '年份待补'), String(p.venue || '期刊 / 会议待补')].join(' · ');
const paperAuthors = p => (p.authors || []).join('、') || '作者未填写';
function citationKey(p, used) {
  const firstAuthor = String((p.authors || [])[0] || 'paper').trim();
  const surname = (firstAuthor.includes(',') ? firstAuthor.split(',')[0].trim() : firstAuthor.split(/\s+/).pop()) || 'paper';
  const base = (surname.normalize('NFKD').replace(/[^A-Za-z0-9]/g, '') || 'paper') + (p.year || 'nd');
  let key = base, index = 2;
  while (used.has(key)) key = base + String(index++);
  used.add(key);
  return key;
}
function bibValue(value) {
  return String(value || '').replace(/[{}]/g, '').replace(/\s+/g, ' ').trim();
}
export function paperBibtex(papers) {
  const used = new Set();
  return (papers || []).map(p => {
    const fields = [
      ['author', (p.authors || []).join(' and ')],
      ['title', '{' + bibValue(p.title) + '}'],
      ['year', p.year || ''],
      ['journal', p.venue || ''],
      ['doi', p.doi || ''],
      ['url', p.url || p.pdfUrl || ''],
      ['keywords', (p.keywords || []).join(', ')],
    ].filter(([, value]) => String(value).trim());
    if (p.arxivId && !p.doi) fields.push(['eprint', p.arxivId], ['archivePrefix', 'arXiv']);
    return '@article{' + citationKey(p, used) + ',\n' + fields.map(([key, value]) => '  ' + key + ' = {' + bibValue(value) + '}').join(',\n') + '\n}\n';
  }).join('\n');
}
export function paperRis(papers) {
  return (papers || []).map(p => {
    const rows = ['TY  - JOUR', 'TI  - ' + flatText(p.title), ...(p.authors || []).map(author => 'AU  - ' + flatText(author))];
    if (p.year) rows.push('PY  - ' + p.year);
    if (p.venue) rows.push('JO  - ' + flatText(p.venue));
    if (p.doi) rows.push('DO  - ' + p.doi);
    if (p.url || p.pdfUrl) rows.push('UR  - ' + (p.url || p.pdfUrl));
    if (p.arxivId) rows.push('AN  - arXiv:' + p.arxivId);
    for (const keyword of p.keywords || []) rows.push('KW  - ' + flatText(keyword));
    rows.push('ER  - ', '');
    return rows.join('\n');
  }).join('\n');
}
function csvCell(value) {
  return '"' + String(value ?? '').replace(/"/g, '""') + '"';
}
export function papersCsv(papers) {
  const header = ['title','authors','year','venue','doi','stage','readState','question','method','data','findings','limitations','relevance','url'];
  const rows = [header.join(',')];
  for (const p of papers || []) {
    const review = p.review || {};
    rows.push([p.title, (p.authors || []).join('; '), p.year, p.venue, p.doi, paperStageNames[p.stage] || p.stage, p.readState, review.question, review.method, review.data, review.findings, review.limitations, review.relevance, p.url || p.pdfUrl].map(csvCell).join(','));
  }
  return rows.join('\n') + '\n';
}
export function researchMarkdown(library) {
  const research = library.research || {};
  const papers = (library.papers || []).filter(p => p.stage === 'included');
  const cell = value => flatText(value).replace(/\|/g, '\\|') || '待补';
  const lines = ['# 学术路径', '', '## 研究问题', '', research.question || '待补', '', '## 范围与边界', '', research.scope || '待补', '', '## 检索策略', '', research.searchStrategy || '待补', '', '## 纳入标准', '', research.inclusion || '待补', '', '## 排除标准', '', research.exclusion || '待补', '', '## 综述矩阵', ''];
  if (papers.length) {
    lines.push('| 论文 | 年 | 研究问题 | 方法 | 数据 / 样本 | 主要发现 | 局限 | 关联 |', '| --- | --- | --- | --- | --- | --- | --- | --- |');
    for (const p of papers) {
      const review = p.review || {};
      lines.push('| ' + [p.title, p.year || '', review.question, review.method, review.data, review.findings, review.limitations, review.relevance].map(cell).join(' | ') + ' |');
    }
  } else lines.push('还没有“已纳入”的论文。');
  lines.push('', '## 综合论证', '', research.synthesis || '待补', '', '## 参考文献', '');
  for (const p of papers) {
    const url = p.url || p.pdfUrl || (p.doi ? 'https://doi.org/' + p.doi : '');
    lines.push('- ' + paperAuthors(p) + '（' + (p.year || '年份待补') + '）。' + p.title + '。' + (p.venue || '') + (url ? ' <' + url + '>' : ''));
  }
  return lines.join('\n');
}
export function libraryMarkdown(library, languages={}) {
  const lines=['# 我的学习图谱','','按“分类 → 视频 → 知识模块 → 笔记”整理。',''];
  const md=v=>String(v || '').replace(/[\\`*_{}\[\]<>#|]/g,'\\$&');
  const link=v=>String(v).replace(/[<>\s]/g,encodeURIComponent);
  const status={todo:'待学习',learning:'学习中',done:'已学完'};
  function addCategory(c,depth) {
    lines.push('#'.repeat(Math.min(depth,6))+' '+md(c.name),'',c.description || '','');
    for(const original of library.videos.filter(v=>v.categoryId===c.id)) {
      const v=localizedVideo(original,languages[original.id] || 'zh-CN');
      lines.push(v.url.startsWith('studyatlas://material/')?`### ${md(v.aiTitle || v.title)}（本地资料）`:`### [${md(v.aiTitle || v.title)}](<${link(v.url)}>)`,'',`- 作者：${md(v.author || '未填写')}`,`- 状态：${status[v.status]}`,`- 标签：${(v.tags || []).map(md).join('、') || '无'}`,'');
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
  for(const i of library.insights || []) lines.push('## '+md(i.title),'',i.content,'',...i.sources.map(s=>s.url.startsWith('studyatlas://material/')?`- ${md(s.source+' '+s.title)}（本地资料）`:`- [${md(s.source+' '+s.title)}](<${link(s.url)}>)`),'');
  if((library.papers || []).length) {
    lines.push('## 论文知识库','');
    for(const p of library.papers) {
      lines.push('### '+md(p.title),'','- 作者：'+md(paperAuthors(p)),'- 年份 / 来源：'+md(paperLabel(p)),'- 阶段：'+(paperStageNames[p.stage] || p.stage),'- 阅读：'+(p.readState || '未读'));
      if(p.doi) lines.push('- DOI：[`'+md(p.doi)+'`](<https://doi.org/'+link(p.doi)+'>)');
      if(p.url) lines.push('- 原文：[打开](<'+link(p.url)+'>)');
      if(p.pdfUrl) lines.push('- PDF：[打开](<'+link(p.pdfUrl)+'>)');
      if(p.keywords?.length) lines.push('- 关键词：'+p.keywords.map(md).join('、'));
      if(p.abstract) lines.push('','**摘要**','',p.abstract);
      const review=p.review || {};
      for(const [key,label] of Object.entries(paperReviewNames)) if(review[key]) lines.push('**'+label+'**：',review[key],'');
      for(const n of p.notes || []) lines.push('**摘录'+(n.page ? ' · 第 '+n.page+' 页' : '')+'**','',n.quote ? '> '+n.quote.replace(/\n/g,'\n> ') : '',n.text || '','');
    }
  }
  const research = library.research || {};
  if(['question','scope','searchStrategy','inclusion','exclusion','synthesis'].some(key => String(research[key] || '').trim())) {
    lines.push('## 学术路径','','**研究问题**','',research.question || '待补','','**范围与边界**','',research.scope || '待补','','**检索策略**','',research.searchStrategy || '待补','','**纳入标准**','',research.inclusion || '待补','','**排除标准**','',research.exclusion || '待补','','**综合论证**','',research.synthesis || '待补','');
  }
  if(library.learning?.attempts.length) {
    lines.push('## 自测与复习记录','','以下为个人作答及 AI 反馈，请自行保管。','');
    for(const a of library.learning.attempts) lines.push('### '+md(a.question),'',a.createdAt+' · '+(a.score===null?'不计分':a.score+' 分')+(a.assisted?' · 参考后作答':''),'','**我的答案**','',a.answer,'','**AI 反馈**','',a.feedback,'','**参考改写**','',a.suggestedAnswer,'','**下次复习**：'+(a.dueAt || '未更新'),'');
  }
  return lines.join('\n');
}
