const esc=(v='')=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const validAsset = value => typeof value==='string' && /^[a-f0-9]{64}\.(jpg|png|webp)$/.test(value);
export const assetURL = id => validAsset(id) ? '/api/media/'+id : '';

export function videoCover(video) {
  if(validAsset(video.visuals?.cover))return assetURL(video.visuals.cover);
  if(video.thumbnail)return video.thumbnail;
  const url=new URL(video.url),id=url.searchParams.get('v');
  return url.hostname==='www.youtube.com' && /^[A-Za-z0-9_-]{11}$/.test(id || '') ? 'https://i.ytimg.com/vi/'+id+'/hqdefault.jpg' : '';
}

export function visualGuide(video) {
  const cover=videoCover(video),frames=video.visuals?.frames || [],active=['queued','metadata','transcript','ai'].includes(video.automation?.status);
  if(!cover&&!frames.length)return `<section class="panel visual-guide"><h2>图文导学</h2><button class="button small soft" data-action="build-visuals" data-id="${esc(video.id)}" ${active?'disabled':''}>补充封面与视频画面</button></section>`;
  return `<section class="panel visual-guide" aria-label="图文导学"><div class="section-head"><div><span class="small-label">先看画面，带着问题读笔记</span><h2>图文导学</h2></div>${frames.length<3?`<button class="button small soft" data-action="build-visuals" data-id="${esc(video.id)}" ${active?'disabled':''}>${active?'正在整理…':'补充视频画面'}</button>`:''}</div>${cover?`<a class="course-poster" href="${esc(video.url)}" target="_blank" rel="noopener noreferrer"><img src="${esc(cover)}" alt="${esc(video.title)} · 原视频封面" referrerpolicy="no-referrer"><span>打开原视频 ↗</span></a>`:''}${frames.length?`<div class="scene-gallery">${frames.map(f=>{const url=new URL(video.url);url.searchParams.set('t',String(f.timeSec));const label=video.knowledge?.modules.find(m=>m.id===f.moduleId)?.title || f.label;return `<figure><a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer"><img src="${esc(assetURL(f.asset))}" alt="原视频 ${Math.floor(f.timeSec/60)}:${String(f.timeSec%60).padStart(2,'0')} 画面" loading="lazy"><span>${Math.floor(f.timeSec/60)}:${String(f.timeSec%60).padStart(2,'0')} ↗</span></a><figcaption>${esc(label)}</figcaption></figure>`;}).join('')}</div>`:''}</section>`;
}
