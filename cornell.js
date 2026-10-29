const esc = (v='') => String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function cornellData(item) {
  if(item.cornell) return item.cornell;
  const questions=item.questions || [];
  const cues=questions.map(q=>q.question).slice(0,6);
  const plain=String(item.summary || item.notes || '').replace(/^#{1,6}\s+/gm,'').replace(/\*\*/g,'');
  return {cues:cues.length?cues:['这个主题解决什么问题？','核心概念怎样联系？','有哪些条件和易错点？'],
    summary:questions.length?questions.map(q=>q.answer).join(' ').slice(0,950):plain.split('\n').find(line=>line.trim().length>20)?.slice(0,950) || '依据正文，用自己的话回顾本页的核心结论。'};
}

export function procedureBlock(procedure) {
  if(!procedure) return '';
  return `<section class="procedure-notes" aria-label="实验与操作流程"><h4>实验与操作流程</h4><p><strong>目标：</strong>${esc(procedure.goal)}</p>${procedure.requirements.length?'<p><strong>条件：</strong>'+procedure.requirements.map(esc).join('；')+'</p>':''}<ol>${procedure.steps.map(s=>`<li><p class="procedure-action">${esc(s.action)}</p><p><strong>预期现象：</strong>${esc(s.expected)}</p><p><strong>验证方法：</strong>${esc(s.verify)}</p></li>`).join('')}</ol><p><strong>结果与边界：</strong>${esc(procedure.conclusion)}</p></section>`;
}

export function cornellSheet(item, content) {
  const data=cornellData(item);
  return `<section class="cornell-sheet" aria-label="康奈尔笔记"><header><span>康奈尔笔记</span><button type="button" class="link-button" data-action="cornell-toggle" aria-expanded="true">遮住记录自测</button></header><div class="cornell-columns"><aside class="cornell-cues"><h4>提示与问题</h4><ol>${data.cues.map(c=>'<li>'+esc(c)+'</li>').join('')}</ol><p>遮住右侧记录，尝试只看提示复述。</p></aside><div class="cornell-notes"><h4 class="cornell-area-title">课堂记录</h4><div class="cornell-record">${content}${procedureBlock(item.procedure)}</div></div></div><footer class="cornell-summary"><h4>归纳小结</h4><p>${esc(data.summary)}</p></footer></section>`;
}
