// Rank locally so questions about later chapters do not resend an entire course.
export function relevantContext(video,question,budget=10000){
  const words=question.toLowerCase().match(/[a-z0-9]{2,}/g)||[],han=(question.match(/[\u3400-\u9fff]+/g)||[]).join('');
  const terms=[...new Set([...words,...Array.from({length:Math.max(0,han.length-1)},(_,i)=>han.slice(i,i+2))])].slice(0,80);
  const sources=[{title:'课程总结',text:video.summary||''},...(video.knowledge?.modules||[]).map(m=>({title:m.title,text:m.notes})),...(video.notes||[]).slice(-5).map(n=>({title:'我的补充',text:n.text}))];
  if(!sources.some(s=>s.text))sources.push({title:'原始资料',text:video.transcript||''});
  const blocks=[];for(const source of sources)for(let i=0;i<source.text.length;i+=1800){const text=source.text.slice(i,i+1800),lower=(source.title+' '+text).toLowerCase();blocks.push({text:source.title+'（片段）\n'+text,score:terms.reduce((sum,t)=>sum+(lower.includes(t)?1:0),0),order:blocks.length});}
  blocks.sort((a,b)=>b.score-a.score||a.order-b.order);let result='以下是当前资料的相关片段，可能不是完整课程。资料不足时须说明。\n';
  for(const block of blocks){if(result.length+block.text.length+2>budget)continue;result+=block.text+'\n\n';if(result.length>budget-1900)break;}return result;
}
