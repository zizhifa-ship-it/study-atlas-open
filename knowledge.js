import {cornellSheet} from './cornell.js';
// 脑图由已保存的 AI 知识模块派生，无外部脚本或图形服务。
const esc = (value='') => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const kindNames={evidence:'依据核对',contradiction:'前后矛盾',omission:'内容遗漏',uncertainty:'不确定结论',structure:'模块结构'};
function lines(text, max=18, count=3) {
  const result=[];let line='',width=0;
  for(const char of String(text)){
    const step=/[\x00-\x7f]/.test(char)?.55:1;
    if(width+step>max){result.push(line);line='';width=0;}
    line+=char;width+=step;
  }
  if(line) result.push(line);
  if(result.length>count) return [...result.slice(0,count-1),result[count-1].slice(0,-1)+'…'];
  return result;
}
export function mindmapSVG(knowledge, compact=false) {
  const rowHeights=knowledge.modules.map(m=>compact?94:Math.max(110,Math.min(m.concepts.length,6)*54+10));
  const h=Math.max(300,rowHeights.reduce((a,b)=>a+b,0)+40),w=compact?510:830,rootY=h/2;
  let body=`<rect width="${w}" height="${h}" fill="#f8faf4"/>`;
  const box=(x,y,width,height,label,color,id='')=>{
    const labelLines=lines(label,width/12-1,3);
    return `<g ${id?`role="button" tabindex="0" aria-label="打开模块 ${esc(label)}" data-action="knowledge-module" data-module="${esc(id)}"`:''}><rect x="${x}" y="${y}" width="${width}" height="${height}" rx="12" fill="${color}" stroke="#cbd8c3"/><text fill="#294638" font-size="13" font-family="-apple-system,PingFang SC,Microsoft YaHei,sans-serif">${labelLines.map((t,i)=>`<tspan x="${x+12}" y="${y+height/2-(labelLines.length-1)*9+i*18+4}">${esc(t)}</tspan>`).join('')}</text></g>`;
  };
  const rootH=82;body+=box(18,rootY-rootH/2,190,rootH,knowledge.title,'#dce9bc');
  let y=20;
  for(let i=0;i<knowledge.modules.length;i++){
    const m=knowledge.modules[i],center=y+rowHeights[i]/2;
    body+=`<path d="M208 ${rootY} C240 ${rootY} 246 ${center} 280 ${center}" fill="none" stroke="#99ae89" stroke-width="2"/>`;
    body+=box(280,center-35,210,70,m.title,'#e9f0df',m.id);
    if(!compact){const concepts=m.concepts.slice(0,6);for(let j=0;j<concepts.length;j++){
      const cy=center-(concepts.length-1)*27+j*54;
      body+=`<path d="M490 ${center} C520 ${center} 533 ${cy} 560 ${cy}" fill="none" stroke="#bbcbb1" stroke-width="1.5"/>`;
      body+=box(560,cy-22,250,44,concepts[j].name,'#fff',m.id);
    }}
    y+=rowHeights[i];
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="group" aria-label="${esc(knowledge.title)} 知识脑图">${body}</svg>`;
}
export function knowledgePanel(video, tab='details', compact=false, markdown) {
  const k=video.knowledge,active=['queued','metadata','transcript','ai'].includes(video.automation?.status);
  if(!k) return `<section class="panel knowledge-empty"><h2>AI 知识模块</h2><p>把课程组织成康奈尔笔记、知识脑图和复习问答。</p><button class="button primary" data-action="build-knowledge" data-id="${esc(video.id)}" ${active?'disabled':''}>${active?'正在整理…':'让 AI 构建知识模块'}</button><small>使用当前连接的 AI，完成后自动保存。</small></section>`;
  const pending=k.review.issues.filter(i=>!i.resolved).length;
  const tabs=[['details','详尽笔记'],['mindmap','知识脑图']];
  let html=`<section class="panel knowledge-panel"><div class="knowledge-title"><div><span class="small-label">${k.modules.length} 个知识模块</span><h2>${esc(k.title)}</h2><p>${esc(k.overview)}</p></div></div><div class="knowledge-tabs" role="tablist" aria-label="知识模块视图">${tabs.map(([id,label])=>`<button role="tab" aria-selected="${tab===id}" class="${tab===id?'selected':''}" data-action="knowledge-tab" data-tab="${id}" data-id="${esc(video.id)}">${label}</button>`).join('')}</div>`;
  if(tab==='mindmap'){
    html+=`<div class="mindmap-toolbar"><p>点击模块或概念可跳到详解；横向滚动查看完整脑图。</p><button class="button small" data-action="knowledge-collapse" data-id="${esc(video.id)}">${compact?'展开概念':'收起概念'}</button><button class="button small" data-action="download-mindmap" data-id="${esc(video.id)}">下载脑图 SVG</button></div><div class="mindmap-stage">${mindmapSVG(k,compact)}</div>`;
  }else{
    html+=`<nav class="module-index" aria-label="模块目录">${k.modules.map((m,i)=>`<button data-action="knowledge-module" data-module="${esc(m.id)}">${i+1}. ${esc(m.title)}</button>`).join('')}</nav>`;
    html+=k.modules.map((m,i)=>{
      const body=`<div class="rich-notes">${markdown(m.notes)}</div><details><summary>概念卡片 · ${m.concepts.length}</summary><dl class="concept-cards">${m.concepts.map(c=>`<div><dt>${esc(c.name)}</dt><dd>${esc(c.explanation)}</dd></div>`).join('')}</dl></details>${m.examples.length?`<h4>课程例子与步骤</h4><div class="rich-notes">${m.examples.map(t=>'<p>'+esc(t)+'</p>').join('')}</div>`:''}${m.pitfalls.length?`<h4>易错点与边界</h4><ul>${m.pitfalls.map(t=>'<li>'+esc(t)+'</li>').join('')}</ul>`:''}<h4>复习与自测</h4><button class="button small soft" data-action="practice-start" data-id="${esc(video.id)}" data-module="${esc(m.id)}">开始本模块自测</button>${m.questions.map(q=>`<details class="quiz"><summary>${esc(q.question)}</summary><p>${esc(q.answer)}</p></details>`).join('')}${m.evidence.length?`<details class="evidence"><summary>查看本模块依据摘录 [S1]</summary>${m.evidence.map(t=>'<blockquote>'+esc(t)+'</blockquote>').join('')}</details>`:''}`;
      return `<article class="knowledge-module" id="module-${esc(m.id)}"><h3><span>${String(i+1).padStart(2,'0')}</span>${esc(m.title)}</h3><p class="module-objective"><strong>学习目标：</strong>${esc(m.objective)}</p>${m.prerequisites.length?'<p class="module-prerequisites"><strong>前置知识：</strong>'+m.prerequisites.map(esc).join('、')+'</p>':''}${cornellSheet(m,body)}</article>`;
    }).join('');
  }
  html+=`<div class="source-list"><a href="${esc(video.url)}" target="_blank" rel="noopener noreferrer">[S1] 原课程：${esc(video.title)} ↗</a></div></section>`;
  return html;
}

export function qualityReport(video) {
  const k=video.knowledge, active=['queued','metadata','transcript','ai'].includes(video.automation?.status);
  if(!k) return '<p class="metadata">知识模块完成后，可在这里查看核对结果。</p>';
  const pending=k.review.issues.filter(i=>!i.resolved).length;
  let html='';
    html+=`<div class="review-banner ${pending?'needs-review':''}"><strong>${pending?pending+' 个问题仍待核对':'已完成第二轮 AI 自查'}</strong><p>${esc(k.review.summary)}</p><small>自查不是正确性保证。摘录匹配只核对文字是否出现，不证明推理一定正确。</small></div><p class="metadata">检查依据：${esc(k.materialKind)} · ${esc(new Date(k.review.checkedAt).toLocaleString('zh-CN',{hour12:false}))}</p>`;
    html+=k.review.issues.map(issue=>`<article class="review-issue"><span class="review-tag ${issue.resolved?'resolved':''}">${issue.resolved?'AI 已修订':'待核对'} · ${esc(kindNames[issue.kind])}</span><h3>${esc(k.modules.find(m=>m.id===issue.moduleId)?.title || '整门课程')}</h3><p>${esc(issue.problem)}</p><p><strong>下一步：</strong>${esc(issue.suggestion)}</p></article>`).join('') || '<p class="review-empty">本轮没有提出具体问题；仍需结合原课检查关键结论。</p>';
    if(k.review.corrections.length)html+='<h3>本轮修订记录</h3><ul>'+k.review.corrections.map(c=>'<li>'+esc(c)+'</li>').join('')+'</ul>';
    html+=`<button class="button soft" data-action="review-knowledge" data-id="${esc(video.id)}" ${active?'disabled':''}>再自查一次</button>`;

  return html;
}
