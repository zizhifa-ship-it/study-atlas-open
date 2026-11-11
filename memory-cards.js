const esc=(v='')=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function shortText(value,limit=150){const plain=String(value||'').replace(/^#{1,6}\s+/gm,'').replace(/\*\*/g,'').replace(/\s+/g,' ').trim();return plain.length>limit?plain.slice(0,limit)+'…':plain;}
export function memoryPoints(module){const candidates=(module.concepts||[]).slice(0,3).map(c=>c.name+'：'+c.explanation);if(!candidates.length)candidates.push(...String(module.notes||'').split(/\n\s*\n/).filter(Boolean));return [...new Set(candidates.map(s=>shortText(s,160)).filter(Boolean))].slice(0,3);}
export function nextRecall(previous,rating,time=Date.now()){
  if(previous?.reviewedAt&&time-previous.reviewedAt<10000)return previous;
  const stage=rating==='remember'?Math.min(5,(previous?.stage||0)+1):0;
  const delay=rating==='remember'?[1,3,7,14,30][stage-1]*86400000:600000;
  return {stage,rating,reviewedAt:time,nextAt:time+delay};
}
export function memoryCards(video,{browserStudy=false,time=Date.now()}={}){
  return '<p class="metadata memory-intro">先看问题回忆，再展开答案。每张卡只保留重点预览；完整说明可切换到“完整笔记”。</p><div class="memory-grid">'+video.knowledge.modules.map((m,i)=>{
    const progress=video.studyProgress?.[m.id],due=!progress?.nextAt||progress.nextAt<=time;
    const practice=browserStudy?(due?`<p class="memory-recall-label">刚才能独立想起来吗？</p><div class="button-row"><button class="button small soft" data-action="memory-rate" data-module="${esc(m.id)}" data-rating="remember">我记得了</button><button class="button small" data-action="memory-rate" data-module="${esc(m.id)}" data-rating="again">再看一次</button></div>`:`<p class="metadata recall-saved">已记录 · 下次复习 ${esc(new Date(progress.nextAt).toLocaleDateString('zh-CN'))}</p>`):`<button class="button small soft" data-action="practice-start" data-id="${esc(video.id)}" data-module="${esc(m.id)}">用练习检验理解</button>`;
    return `<article class="memory-card knowledge-module" id="module-${esc(m.id)}"><h3><span>${String(i+1).padStart(2,'0')}</span>${esc(m.title)}</h3><p class="memory-purpose">${esc(shortText(m.objective,120))}</p><ul class="memory-points">${memoryPoints(m).map(p=>'<li>'+esc(p)+'</li>').join('')}</ul>${m.examples?.[0]?'<div class="memory-example"><strong>一个例子</strong><p>'+esc(shortText(m.examples[0],220))+'</p></div>':''}${m.pitfalls?.[0]?'<p class="memory-boundary"><strong>注意：</strong>'+esc(shortText(m.pitfalls[0],140))+'</p>':''}<div class="memory-questions">${(m.questions||[]).slice(0,3).map(q=>'<details class="quiz memory-question"><summary>'+esc(q.question)+'</summary><p>'+esc(q.answer)+'</p></details>').join('')}</div>${practice}<button class="link-button" data-action="memory-detail" data-id="${esc(video.id)}" data-module="${esc(m.id)}">查看这个知识点的完整说明 →</button></article>`;
  }).join('')+'</div>';
}
