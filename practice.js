// 界面只显示真实作答和批改记录，不把收藏数量当作学习成果。
const esc = (v='') => String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const cardKey = card => card.videoId + ':' + card.questionId;
const verdicts = {correct:'回答较完整',partial:'还需补充',incorrect:'需要重学',insufficient:'暂不计分'};
const time = v => v ? new Date(v).toLocaleString('zh-CN',{hour12:false,month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}) : '尚未安排';

export function practicePool(data, ui) {
  return (data?.items || []).filter(c=>(!ui.course || c.videoId===ui.course) &&
    (ui.mode==='weak' ? c.isWeak : ui.mode==='all' ? true : c.isDue || c.isNew));
}

function feedbackPanel(attempt) {
  if (!attempt) return '';
  return `<section class="practice-feedback ${attempt.score===null?'uncertain':attempt.score<80?'needs-work':'complete'}" aria-label="AI 批改结果" role="status"><div class="section-head"><h3>${esc(verdicts[attempt.verdict])}</h3><strong>${attempt.score===null?'不计分':attempt.score+' / 100'}</strong></div><p>${esc(attempt.feedback)}</p>${attempt.assisted?'<p class="metadata">本次看过参考答案，作为辅助练习保存，不增加独立答对次数。</p>':''}${attempt.missingPoints.length?'<h4>需要补充的知识点</h4><ul>'+attempt.missingPoints.map(p=>'<li>'+esc(p)+'</li>').join('')+'</ul>':''}<h4>参考改写</h4><p>${esc(attempt.suggestedAnswer)}</p>${attempt.evidence?'<details><summary>查看批改依据</summary><blockquote>'+esc(attempt.evidence)+'</blockquote></details>':''}<p class="metadata">${attempt.score===null?'本轮未更新复习进度。':'下次复习：'+time(attempt.dueAt)+' · 连续独立答对 '+attempt.streak+' 次'}</p><small>AI 依据已保存模块批改，可能漏错；引用匹配不等于事实认证。</small></section>`;
}

export function practicePage(data, library, ui) {
  if (!data) return `<section class="panel empty-state"><h2>暂时无法读取复习题目</h2><p>${esc(ui.error || '请确认本机服务已更新并正常运行。')}</p><button class="button" data-action="practice-refresh">重新读取</button></section>`;
  const counts=data.counts, filtered=data.items.filter(c=>!ui.course || c.videoId===ui.course);
  const options=[...new Map(data.items.map(c=>[c.videoId,c.videoTitle]))];
  const tabs=[['today','待复习与新题'],['weak','错题本'],['all','全部题目'],['history','作答记录']];
  let html=`<section class="page-heading"><div><span class="eyebrow">把笔记变成自己的知识</span><h1>复习与自测</h1><p>先独立回答，再让 AI 对照模块资料指出遗漏；根据真实作答安排下一次复习。</p></div><button class="button soft" data-action="backup">备份学习记录</button></section><div class="practice-stats" aria-label="复习概况">${[['待复习',counts.due],['未练新题',counts.new],['需要巩固',counts.weak],['近24小时作答',counts.recent]].map(([title,n])=>`<div><span>${title}</span><strong>${n}</strong></div>`).join('')}</div><div class="practice-filters"><div role="tablist" aria-label="复习范围">${tabs.map(([id,label])=>`<button role="tab" aria-selected="${ui.mode===id}" data-action="practice-mode" data-mode="${id}">${label}</button>`).join('')}</div><label>课程<select id="practice-course" aria-label="筛选复习课程"><option value="">全部课程</option>${options.map(([id,title])=>`<option value="${esc(id)}" ${ui.course===id?'selected':''}>${esc(title)}</option>`).join('')}</select></label></div>`;
  if(!data.items.length && !data.history.length) return html+'<section class="panel empty-state"><h2>先让 AI 为一门课程构建知识模块</h2><p>已保存模块中的复习问答会自动成为自测题，无须重复生成。</p><button class="button primary" data-action="navigate" data-view="knowledge">去知识模块</button></section>';
  if(ui.mode==='history') {
    const history=data.history.filter(a=>!ui.course || a.videoId===ui.course);
    html+='<section class="panel"><div class="section-head"><h2>最近作答</h2><span class="metadata">显示最近 50 条；完整记录保存在 JSON 备份</span></div>';
    html+=history.slice(0,50).map(a=>{
      const v=library.videos.find(v=>v.id===a.videoId),current=data.items.find(c=>c.videoId===a.videoId&&c.questionId===a.questionId&&c.sourceHash===a.sourceHash);
      return `<article class="practice-history"><div class="metadata">${time(a.createdAt)} · ${esc(v?.aiTitle || v?.title || '已移除课程')} · ${current?'当前资料':'旧版或已移除题目'}</div><h3>${esc(a.question)}</h3><p><strong>你的答案：</strong>${esc(a.answer)}</p><p><strong>${esc(verdicts[a.verdict])} · ${a.score===null?'不计分':a.score+' 分'}${a.assisted?' · 参考后作答':''}</strong></p><p>${esc(a.feedback)}</p><details><summary>查看参考与依据</summary><p>${esc(a.suggestedAnswer)}</p><blockquote>${esc(a.evidence)}</blockquote></details></article>`;
    }).join('') || '<p class="metadata">当前课程还没有作答记录。</p>';
    return html+'</section>';
  }
  const pool=practicePool(data,ui);
  const active=filtered.find(c=>cardKey(c)===ui.current) || pool.find(c=>!ui.skipped.includes(cardKey(c)));
  html+='<div class="practice-layout"><aside class="panel practice-queue"><h2>'+ (ui.mode==='weak'?'需要巩固的题目':ui.mode==='all'?'全部自测题':'本轮练习') +` <span class="metadata">${pool.length}</span></h2><div class="practice-question-list">`;
  html+=pool.map(c=>`<button class="practice-question ${active&&cardKey(active)===cardKey(c)?'selected':''}" data-action="practice-question" data-key="${esc(cardKey(c))}"><small>${esc(c.moduleTitle)}</small><span>${esc(c.question)}</span><small>${c.isNew?'未练新题':c.isDue?'已到复习时间':time(c.progress.dueAt)}${c.isWeak?' · 需要巩固':''}</small></button>`).join('') || '<p class="metadata">这个范围没有待练习题目。</p>';
  html+='</div><p class="metadata">间隔采用简单规则：独立答对后为 1、3、7、14、30 天；部分理解次日复习，错误回答 10 分钟后重练。这是练习计划，不是掌握度认证。</p></aside>';
  if(!active) {
    const future=filtered.filter(c=>c.progress && !c.isDue).sort((a,b)=>a.progress.dueAt.localeCompare(b.progress.dueAt));
    html+='<section class="panel empty-state"><h2>'+(pool.length?'本轮题目已查看':'这个范围暂时没有待办')+'</h2><p>可以查看全部题目继续练习，或稍后按计划返回。</p><button class="button soft" data-action="practice-mode" data-mode="all">查看全部题目</button>'+(pool.length?'<button class="button" data-action="practice-reset-session">重新开始本轮</button>':'')+(future.length?'<p class="metadata">最近一次安排：'+time(future[0].progress.dueAt)+'</p>':'')+'</section></div>';
    return html;
  }
  const key=cardKey(active),last=active.lastAttempt,draft=ui.drafts[key] || '',revealed=ui.revealed[key],busy=!!ui.busy;
  html+=`<section class="panel practice-card" data-question-key="${esc(key)}"><p class="small-label">${esc(active.videoTitle)} / ${esc(active.moduleTitle)}</p><h2>${esc(active.question)}</h2><p class="metadata">${active.isNew?'尚无有效计分记录':(active.isDue?'已到复习时间':'计划复习时间：'+time(active.progress.dueAt))}</p><form id="practice-form" data-key="${esc(key)}"><div class="field"><label for="practice-answer"><span>你的理解</span></label><textarea id="practice-answer" name="answer" rows="6" maxlength="6000" required ${busy?'disabled':''} placeholder="先用自己的话回答，尽量说明原因和适用条件。">${esc(draft)}</textarea></div><div class="button-row"><button type="submit" class="button primary" ${busy?'disabled':''}>${busy?'AI 正在对照资料批改…':'提交给 AI 批改'}</button><button type="button" class="button" data-action="practice-reference" data-key="${esc(key)}" ${busy?'disabled':''}>${revealed?'参考答案已显示':'显示参考答案'}</button><button type="button" class="button" data-action="practice-next" data-key="${esc(key)}" ${busy?'disabled':''}>下一题</button></div><p class="metadata">未提交答案暂存在当前页面；提交后自动保存。AI 批改会使用当前 Harness 或 DeepSeek 额度。</p></form>${revealed?'<div class="practice-reference"><strong>模块中的参考答案</strong><p>'+esc(active.referenceAnswer)+'</p><small>查看后本题会标记为辅助练习。</small></div>':''}${feedbackPanel(last)}<div class="button-row practice-source"><button class="link-button" data-action="practice-source" data-video="${esc(active.videoId)}" data-module="${esc(active.moduleId)}">回到模块详解 →</button><a href="${esc(active.url)}" target="_blank" rel="noopener noreferrer">打开原视频 ↗</a></div></section></div>`;
  return html;
}

export function mergePracticeAttempts(current, incoming, videoIds) {
  if(incoming===undefined) return current || {attempts:[]};
  if(!incoming || !Array.isArray(incoming.attempts) || incoming.attempts.length>10000) throw new Error('自测记录备份格式不正确');
  const merged=structuredClone(current || {attempts:[]}),ids=new Set(merged.attempts.map(a=>a.id));
  for(const a of incoming.attempts) {
    if(!a || typeof a!=='object' || !videoIds.has(a.videoId) || ids.has(a.id)) continue;
    merged.attempts.push({...a,videoId:videoIds.get(a.videoId)});ids.add(a.id);
  }
  return merged;
}
