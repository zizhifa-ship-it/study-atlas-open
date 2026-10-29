// 笔记语言与界面语言独立；译文只在当前原稿版本有效时展示。
export const noteLanguages = {'zh-CN':'简体中文',en:'英语',de:'德语',ja:'日语',ko:'韩语',fr:'法语',es:'西班牙语',ru:'俄语'};
const esc = (v='') => String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function localizedVideo(video, language='zh-CN') {
  const translated=video.translations?.[language];
  if(language==='zh-CN' || !translated || translated.stale) return video;
  return {...video,aiTitle:translated.title,summary:translated.summary,cornell:translated.cornell,
    knowledge:video.knowledge ? {...video.knowledge,title:translated.title,overview:translated.overview,modules:translated.modules} : null};
}

export function effectiveLanguage(video, desired='zh-CN') {
  return desired!=='zh-CN' && video.translations?.[desired] && !video.translations[desired].stale ? desired : 'zh-CN';
}

export function translationControls(video, desired='zh-CN') {
  const current=effectiveLanguage(video,desired), active=['queued','metadata','transcript','ai'].includes(video.automation?.status);
  const missing=desired!=='zh-CN' && current!==desired;
  return `<section class="note-language-bar" aria-label="笔记多语言翻译"><label>笔记语言<select data-note-language="${esc(video.id)}" aria-label="选择笔记语言">${Object.entries(noteLanguages).map(([code,label])=>`<option value="${code}"${desired===code?' selected':''}>${label}${code!=='zh-CN' && video.translations?.[code] && !video.translations[code].stale?' · 已保存':''}</option>`).join('')}</select></label><div class="note-language-status">${missing?`<p>${video.translations?.[desired]?.stale?'原稿已更新，译文需要更新。':'首次使用需要生成译文。'}当前显示中文原稿。</p><button class="button small soft" data-action="translate-notes" data-id="${esc(video.id)}" data-language="${esc(desired)}" ${active?'disabled':''}>${active?'等待当前任务完成':'生成'+noteLanguages[desired]+'笔记'}</button><small>使用已连接的 AI；保存后切换可直接读取。</small>`:`<span>${current==='zh-CN'?'中文原稿':noteLanguages[current]+'译文 · 中文原稿保留'}</span>`}</div></section>`;
}
