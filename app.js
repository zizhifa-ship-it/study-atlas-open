import {visualGuide,videoCover} from './video-media.js';
import {localizedVideo, effectiveLanguage, translationControls, noteLanguages} from './translations.js';
import {cornellSheet} from './cornell.js';
import {knowledgePanel, mindmapSVG, qualityReport} from './knowledge.js';
import {practicePage, practicePool, cardKey, mergePracticeAttempts} from './practice.js';
import {libraryMarkdown} from './exports.js';
// 阅读顺序：数据与请求 → 页面渲染 → 编辑窗口 → 用户操作。
const $ = (selector) => document.querySelector(selector);
const esc = (value = '') => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const uid = () => crypto.randomUUID();
const now = () => new Date().toISOString();
const state = {library: null, view: 'home', id: null, search: '', status: 'all', favorites: false, integrations:null, aiDraft:null, aiJob:null, knowledgeTabs:{}, compactMaps:{}, noteLanguages:{}, practiceData:null,
  practice:{mode:'today',course:'',current:null,drafts:{},revealed:{},skipped:[],busy:null,pendingRequests:{}}};
try {state.noteLanguages=JSON.parse(localStorage.getItem('study-atlas-note-languages') || '{}');if(!state.noteLanguages || typeof state.noteLanguages!=='object' || Array.isArray(state.noteLanguages))state.noteLanguages={};for(const [id,language] of Object.entries(state.noteLanguages))if(!noteLanguages[language])delete state.noteLanguages[id];}catch {state.noteLanguages={};}
const personalNotes = v => v.notes.filter(n=>!n.text.startsWith('旧版总结（'));
const statusNames = {todo: '待学习', learning: '学习中', done: '已学完'};
const modal = $('#modal');
let toastTimer;
const paths = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  play: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="m10 9 5 3-5 3z"/>',
  note: '<path d="M14 3H5v18h14V8zM14 3v6h5M8 13h8M8 17h5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  network: '<rect x="9" y="2" width="6" height="6" rx="1"/><rect x="2" y="16" width="6" height="6" rx="1"/><rect x="16" y="16" width="6" height="6" rx="1"/><path d="M12 8v4M5 16v-4h14v4"/>',
  code: '<path d="m8 6-6 6 6 6M16 6l6 6-6 6M14 3l-4 18"/>',
  spark: '<path d="m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3zM20 2v4M18 4h4"/>',
  book: '<path d="M3 4h5q4 0 4 4v14q0-4-4-4H3zM21 4h-5q-4 0-4 4v14q0-4 4-4h5z"/>',
  star: '<path d="m12 2 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  export: '<path d="M12 15V2M7 7l5-5 5 5M4 13v8h16v-8"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.book}</svg>`;
const networkArt = `<svg viewBox="0 0 230 170" fill="none" aria-hidden="true"><path d="M115 40v40M115 80H48v38M115 80h67v38" stroke="#a8be83" stroke-width="1.5" stroke-dasharray="4 5"/><circle cx="115" cy="80" r="5" fill="#d8e8a3"/><rect x="91" y="7" width="48" height="43" rx="9" fill="#d5e4a6"/><path d="M104 23h22M104 30h14" stroke="#547145" stroke-width="2"/><rect x="22" y="116" width="52" height="40" rx="8" fill="#6a8657" stroke="#c2d397"/><rect x="155" y="116" width="52" height="40" rx="8" fill="#6a8657" stroke="#c2d397"/><path d="M37 135h22M170 135h22M48 126v18M181 126v18" stroke="#d3e0ab" stroke-width="1.5"/><circle cx="185" cy="44" r="17" stroke="#76905e"/><path d="m178 44 5 5 9-10" stroke="#d3e0ab" stroke-width="2"/></svg>`;

function toast(message, error = false) {
  clearTimeout(toastTimer);
  const node = $('#toast');
  node.textContent = message;
  node.className = `toast${error ? ' error' : ''}`;
  node.hidden = false;
  toastTimer = setTimeout(() => { node.hidden = true; }, error ? 7500 : 3200);
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || '操作失败，请重试');
  return body;
}

async function save(next) {
  $('#save-status').textContent = '正在保存…';
  try {
    state.library = await request('/api/library', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(next)});
    await refreshPractice();
    state.dirty=false;renderAll();
  } catch (error) {
    $('#save-status').textContent = '保存失败，修改尚未写入';
    throw error;
  }
}

const category = id => state.library.categories.find(c => c.id === id);
const video = id => state.library.videos.find(v => v.id === id);
const displayTitle = v => v.aiTitle || v.title;
const children = id => state.library.categories.filter(c => c.parentId === id);
function categoryPath(id) {
  const result = [];
  for (let c = category(id); c; c = category(c.parentId)) result.unshift(c);
  return result;
}
const pathName = id => categoryPath(id).map(c => c.name).join(' / ');
function descendants(id) {
  return [id, ...children(id).flatMap(c => descendants(c.id))];
}
function categoryVideos(id) {
  const ids = new Set(descendants(id));
  return state.library.videos.filter(v => ids.has(v.categoryId));
}
const noteCount = videos => videos.reduce((sum, v) => sum + personalNotes(v).length + (v.summary ? 1 : 0), 0);
function timeLabel(seconds) {
  if (seconds === null || seconds === undefined) return '随记';
  const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = seconds % 60;
  return h ? `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}` : `${m}:${String(s).padStart(2,'0')}`;
}
function parseTime(value, optional = false) {
  if (!value.trim()) return optional ? null : 0;
  const parts = value.trim().split(':');
  if (parts.length > 3 || parts.some(p => !/^\d+$/.test(p)) || parts.slice(1).some(p => Number(p) > 59)) {
    throw new Error('时间请填写为 4:25 或 1:04:25');
  }
  const seconds = parts.reduce((sum, part) => sum * 60 + Number(part), 0);
  if (seconds > 3600000) throw new Error('时间过长，请检查输入');
  return seconds;
}
function canonicalURL(raw) {
  let url;
  try { url = new URL(/^https?:\/\//i.test(raw.trim()) ? raw.trim() : 'https://' + raw.trim()); }
  catch { throw new Error('请填写有效的视频链接'); }
  if (!['http:','https:'].includes(url.protocol) || !url.hostname || url.username || url.password || /\s/.test(url.href)) throw new Error('请填写有效的 http 或 https 视频链接');
  const host = url.hostname.toLowerCase();
  let youtubeId;
  if (['youtu.be','www.youtu.be'].includes(host)) youtubeId = url.pathname.split('/')[1];
  if (['youtube.com','www.youtube.com','m.youtube.com'].includes(host)) youtubeId = url.searchParams.get('v') || url.pathname.match(/^\/(?:shorts|embed|live)\/([^/]+)/)?.[1];
  if (youtubeId && /^[A-Za-z0-9_-]{11}$/.test(youtubeId)) return `https://www.youtube.com/watch?v=${youtubeId}`;
  if (['bilibili.com','www.bilibili.com','m.bilibili.com'].includes(host) && /\/video\/BV[A-Za-z0-9]+/.test(url.pathname)) {
    const result = new URL('https://www.bilibili.com' + url.pathname.match(/\/video\/BV[A-Za-z0-9]+/)[0] + '/');
    if (url.searchParams.has('p')) result.searchParams.set('p', url.searchParams.get('p'));
    return result.href;
  }
  url.hash = '';
  return url.href;
}
function platform(url) {
  const host = new URL(url).hostname;
  if (/(^|\.)youtube\.com$|(^|\.)youtu\.be$/.test(host)) return 'YouTube';
  if (/(^|\.)bilibili\.com$|(^|\.)b23\.tv$/.test(host)) return '哔哩哔哩';
  return '视频课程';
}
function jumpURL(v, time) {
  const url = new URL(v.url);
  if (time !== null && /(^|\.)(youtube\.com|youtu\.be|bilibili\.com)$/.test(url.hostname)) url.searchParams.set('t', String(time));
  return url.href;
}

function go(view, id = '') {
  state.dirty=false;
  $('#search').value = '';
  state.search = '';
  state.status = 'all';
  state.favorites = false;
  const hash = '#' + view + (id ? '/' + encodeURIComponent(id) : '');
  if (location.hash === hash) route(); else location.hash = hash;
}
function route() {
  const [view, id] = location.hash.slice(1).split('/');
  state.view = ['home','category','videos','notes','video','insights','knowledge','practice','quality'].includes(view) ? view : 'home';
  state.id = id ? decodeURIComponent(id) : null;
  if ((state.view === 'category' && !category(state.id)) || (state.view === 'video' && !video(state.id))) state.view = 'home';
  if (state.library) renderAll();
}

function renderNavigation() {
  const {videos} = state.library;
  let html = [['home','grid','分类总览',state.library.categories.length],['videos','play','全部视频',videos.length],['notes','note','学习笔记',noteCount(videos)],['knowledge','network','知识模块',state.library.videos.reduce((n,v)=>n+(v.knowledge?.modules.length || 0),0)],['insights','spark','AI 总结与经验',(state.library.insights || []).length]]
    .map(([view, symbol, name, count]) => `<button class="nav-item${state.view === view && !state.search ? ' active' : ''}" data-action="navigate" data-view="${view}">${icon(symbol)}${name}<span class="nav-count">${count}</span></button>`).join('');
  html += `<button class="nav-item${state.view==='practice'?' active':''}" data-action="navigate" data-view="practice">${icon('book')}复习与自测<span class="nav-count">${(state.practiceData?.counts.due || 0)+(state.practiceData?.counts.new || 0)}</span></button>`;
  html += `<button class="nav-item${state.view==='quality'?' active':''}" data-action="navigate" data-view="quality">${icon('note')}质量与来源</button>`;
  html += `<div class="nav-section-title">学习分类<button aria-label="新建分类" data-action="new-category">＋</button></div>`;
  function addCategories(parent, depth = 0) {
    for (const c of children(parent)) {
      html += `<button class="nav-item category-nav${depth ? ' child-nav' : ''}${state.view === 'category' && state.id === c.id && !state.search ? ' active' : ''}" data-action="navigate" data-view="category" data-id="${esc(c.id)}"><span class="category-dot ${c.color}"></span>${esc(c.name)}<span class="nav-count">${categoryVideos(c.id).length}</span></button>`;
      if (depth < 5) addCategories(c.id, depth + 1);
    }
  }
  addCategories(null);
  html += '<div class="nav-section-title">连接与整理</div><button class="nav-item" data-action="ai-settings">'+icon('spark')+'AI / Harness 设置</button><button class="nav-item" data-action="youtube">'+icon('play')+'YouTube 播放列表（可选）</button>';
  $('#navigation').innerHTML = html;
}

function categoryCard(c) {
  const videos = categoryVideos(c.id);
  const symbol = c.color === 'blue' ? 'code' : c.color === 'purple' ? 'spark' : c.color === 'orange' ? 'book' : 'network';
  return `<article class="category-card ${c.color}"><div class="category-tools"><button class="icon-button" aria-label="编辑分类 ${esc(c.name)}" data-action="edit-category" data-id="${esc(c.id)}">···</button></div><button class="category-open" aria-label="打开分类 ${esc(c.name)}" data-action="navigate" data-view="category" data-id="${esc(c.id)}"><span class="category-icon">${icon(symbol)}</span><h3>${esc(c.name)}</h3><p>${esc(c.description || '为这个方向建立你自己的知识目录。')}</p><div class="category-meta"><span>${videos.length} 个视频</span><span>·</span><span>${children(c.id).length} 个子分类</span><span>↗</span></div></button></article>`;
}
function videoCard(v) {
  const cover=videoCover(v);
  return `<article class="video-card"><button class="video-cover${cover?' has-thumbnail':''}" data-action="navigate" data-view="video" data-id="${esc(v.id)}" aria-label="查看视频 ${esc(displayTitle(v))}"><span class="cover-visual">${cover?`<img src="${esc(cover)}" alt="原视频封面" loading="lazy" referrerpolicy="no-referrer">`:networkArt}</span><span class="cover-label">${esc(platform(v.url))} / ${esc(category(v.categoryId)?.name)}</span><span class="cover-title">${esc(category(v.categoryId)?.name || '我的课程')}<br>学习笔记。</span><span class="cover-play">▶</span>${v.durationSec ? `<span class="duration">${timeLabel(v.durationSec)}</span>` : ''}</button><div class="video-body"><div class="card-topline"><span>${esc(pathName(v.categoryId))}</span><span class="status-pill ${v.status}">${statusNames[v.status]}</span></div><button class="video-title" data-action="navigate" data-view="video" data-id="${esc(v.id)}">${esc(displayTitle(v))}</button><p class="video-author">${esc(v.author || '作者待补充')}</p>${v.automation?.status ? `<p class="import-state">${esc(importNames[v.automation.status] || '')}</p>` : ''}<div class="tags">${v.tags.slice(0,5).map(t => `<button class="tag" data-action="search-tag" data-tag="${esc(t)}">${esc(t)}</button>`).join('')}</div><div class="video-foot"><span>${noteCount([v])} 篇笔记</span><button class="icon-button favorite${v.favorite ? ' active' : ''}" aria-label="${v.favorite ? '取消重点收藏' : '重点收藏'} ${esc(displayTitle(v))}" data-action="favorite" data-id="${esc(v.id)}">${icon('star')}</button></div></div></article>`;
}
function empty(title, text, action = '') {
  return `<div class="empty-state"><h3>${title}</h3><p>${text}</p>${action}</div>`;
}
function heading(kicker, title, description, buttons = '') {
  return `<div class="page-heading"><div><div class="eyebrow">${kicker}</div><h1>${esc(title)}</h1><p>${esc(description)}</p></div><div class="button-row">${buttons}</div></div>`;
}
const addVideoButton = '<button class="button primary" data-action="new-video">' + icon('plus') + '粘贴链接一键整理</button>';
const addCategoryButton = '<button class="button" data-action="new-category">' + icon('plus') + '新建分类</button>';
function homePage() {
  const {videos, categories} = state.library;
  const learning = videos.filter(v => v.status === 'learning').slice(0, 1);
  return heading('我的学习知识库', '把好奇，整理成知识。', '粘贴公开视频链接，自动识别、分类并整理学习笔记。', addCategoryButton + addVideoButton)
    + `<section class="hero"><div class="hero-copy"><div class="hero-kicker">收藏 · 理解 · 融会贯通</div><h2>收藏只是开始，<br>理解才是<em>你的收获。</em></h2><p>只需一个链接，让 AI 把视频归入知识目录，留下有来源的学习笔记。</p><div class="steps"><span><b>01</b> 粘贴链接</span><span><b>02</b> 自动分类</span><span><b>03</b> 生成笔记</span></div></div><div class="hero-visual">${networkArt}</div></section>`
    + `<div class="stat-row">${[[categories.length,'个分类','让知识各归其位'],[videos.length,'个视频','收藏每一个启发'],[videos.filter(v => v.status === 'done').length,'个学完','一点进步，也算数'],[noteCount(videos),'篇笔记','留下自己的理解']].map(([n,label,tip])=>`<div class="stat"><div><strong>${n}</strong><span>${label}</span></div><small>${tip}</small></div>`).join('')}</div>`
    + `<section><div class="section-head"><h2>我的学习分类 <span>学习分类</span></h2><button class="text-button" data-action="new-category">管理自己的知识目录 ＋</button></div><div class="category-grid">${children(null).map(categoryCard).join('')}</div>${!categories.length ? empty('从第一个分类开始', '可以先建立“网络工程”，再在里面添加“网络基础”。', addCategoryButton) : ''}</section>`
    + `<section><div class="section-head"><h2>${learning.length ? '继续上次的学习' : '最近收藏'} <span>继续学习</span></h2><button class="text-button" data-action="navigate" data-view="videos">查看全部 →</button></div>${videos.length ? `<div class="continue-grid"><div>${(learning.length ? learning : videos.slice(-1)).map(videoCard).join('')}</div><aside class="learning-tip"><div class="tip-kicker">学习小提醒</div><h3>看到一个好视频，<br>复制链接，让 AI 帮你整理。</h3><p>网站读取可用字幕，由 DeepSeek 自动分类、写笔记并保存。看完后核对和补充自己的理解，让知识真正属于你。</p></aside></div>` : empty('还没有收藏视频', '粘贴 YouTube 或哔哩哔哩链接，自动分类并制作图文笔记。', addVideoButton)}</section>`;
}
function filteredVideos(videos) {
  return videos.filter(v => (state.status === 'all' || v.status === state.status) && (!state.favorites || v.favorite));
}
function videoSection(videos) {
  const filtered = filteredVideos(videos).slice().sort((a,b) => b.updatedAt.localeCompare(a.updatedAt));
  return `<div class="filter-row">${[['all','全部'],['todo','待学习'],['learning','学习中'],['done','已学完']].map(([id,name])=>`<button class="filter-tab${state.status === id ? ' selected' : ''}" data-action="filter" data-status="${id}">${name}</button>`).join('')}<button class="filter-tab${state.favorites ? ' selected' : ''}" aria-pressed="${state.favorites}" data-action="filter-favorites">☆ 重点收藏</button><span class="result-count">${filtered.length} 个视频</span></div>${filtered.length ? `<div class="video-list">${filtered.map(videoCard).join('')}</div>` : empty('这里还没有视频', '换个筛选条件，或为这个分类收藏第一个视频。', addVideoButton)}`;
}
function categoryPage() {
  const c = category(state.id);
  return heading('学习目录', c.name, c.description || '给学习一个清晰的方向。', `<button class="button" data-action="synthesize">${icon('spark')}归纳共通经验</button><button class="button" data-action="edit-category" data-id="${esc(c.id)}">编辑分类</button>` + addCategoryButton + addVideoButton)
    + (children(c.id).length ? `<div class="section-head"><h2>子分类</h2></div><div class="category-grid">${children(c.id).map(categoryCard).join('')}</div>` : '')
    + '<div class="section-head"><h2>分类里的视频</h2></div>' + videoSection(categoryVideos(c.id));
}
function notesPage() {
  const videos = state.library.videos.filter(v => v.summary || v.notes.length);
  return heading('把课程转化为知识', '学习笔记', 'AI 负责梳理知识与总结，你专注理解、提问和批注。', exportButtons() + '<button class="button" data-action="batch-ai">AI 整理待办</button>')
    + (videos.length ? videos.map(v => `<article class="knowledge-card"><span class="small-label">${esc(pathName(v.categoryId))}</span><h2>${esc(displayTitle(v))}</h2>${v.summary ? `${cornellSheet(v,`<div class="rich-notes">${renderMarkdown(v.summary)}</div>`)}` : ''}${personalNotes(v).map(n => `<div class="note"><div class="note-header"><a class="note-time" href="${esc(jumpURL(v,n.timeSec))}" target="_blank" rel="noopener noreferrer">${timeLabel(n.timeSec)} ↗</a></div><div class="note-text">${esc(n.text)}</div></div>`).join('')}<button class="link-button" data-action="navigate" data-view="video" data-id="${esc(v.id)}">打开视频与笔记 →</button></article>`).join('') : empty('你的第一篇笔记，从一个问题开始', '打开一个视频，写下“这个概念解决什么问题？”', '<button class="button primary" data-action="navigate" data-view="videos">选择视频</button>'));
}
function knowledgePage() {
  const ready=state.library.videos.filter(v=>v.knowledge);
  return heading('从课程到知识结构','AI 知识模块','按模块阅读康奈尔笔记，用脑图连接概念，再用自己的例子复习。',addVideoButton)
    + (ready.length ? '<div class="knowledge-grid">'+ready.map(v=>{
      const k=v.knowledge,pending=k.review.issues.filter(i=>!i.resolved).length;
      return `<article class="knowledge-card"><span class="small-label">${esc(pathName(v.categoryId))} · ${k.modules.length} 个模块</span><h2>${esc(k.title)}</h2><p>${esc(k.overview)}</p><div class="tags">${k.modules.map(m=>'<span class="tag">'+esc(m.title)+'</span>').join('')}</div><button class="button soft" data-action="navigate" data-view="video" data-id="${esc(v.id)}">打开详尽笔记与脑图</button></article>`;
    }).join('')+'</div>' : empty('先把一门课组织成知识模块','打开已有视频，让 AI 规划模块、逐模块详解并自查。','<button class="button primary" data-action="navigate" data-view="videos">选择课程</button>'));
}
function detailPage() {
  const base=video(state.id), desired=state.noteLanguages[base.id] || 'zh-CN', v=localizedVideo(base,desired);
  return `<button class="back-button" data-action="navigate" data-view="category" data-id="${esc(v.categoryId)}">← 返回 ${esc(pathName(v.categoryId))}</button>`
    + heading(platform(v.url) + ' / '+noteLanguages[effectiveLanguage(base,desired)]+'学习笔记', displayTitle(v), v.author || '作者待补充', exportButtons(v.id) + `<button class="button soft" data-action="ai-summary" data-id="${esc(v.id)}">${icon('spark')}AI 自动写好笔记</button><button class="button" data-action="edit-video" data-id="${esc(v.id)}">编辑视频</button>`)
    + translationControls(base,desired)
    + automationPanel(base)
    + visualGuide(v)
    + knowledgePanel(v,state.knowledgeTabs[v.id] || 'details',state.compactMaps[v.id] || false,renderMarkdown)
    + (effectiveLanguage(base,desired)!=='zh-CN' ? `<details class="panel original-comparison"><summary>对照中文原稿</summary><div class="rich-notes">${renderMarkdown(base.summary)}</div>${(base.knowledge?.modules || []).map(m=>`<h3>${esc(m.title)}</h3><div class="rich-notes">${renderMarkdown(m.notes)}</div>`).join('')}</details>` : '')
    + `<div class="detail-layout"><div><section class="watch-banner"><div><h2>AI 先整理，你再理解与批注。</h2><p>查看笔记、回顾提示，随时返回原视频。${v.durationSec ? '视频时长 ' + timeLabel(v.durationSec) + '。' : ''}</p></div><a class="button primary" href="${esc(v.url)}" target="_blank" rel="noopener noreferrer">打开视频 ↗</a></section><section class="panel"><div class="section-head" style="margin-top:0"><h2>AI 知识总结</h2><span class="small-label">已保存 · 可导出到无边记</span></div>${v.summary ? `${cornellSheet(v,`<div class="rich-notes">${renderMarkdown(v.summary)}</div>`)}<div class="source-list"><a href="${esc(v.url)}" target="_blank" rel="noopener noreferrer">[S1] 原视频：${esc(v.title)} ↗</a></div>` : '<p class="metadata">AI 整理完成后，知识脉络、例子与复习问题会出现在这里。</p>'}<details><summary>补充或修订中文原稿（选填）</summary><form id="summary-form"><label class="field"><span>这个视频主要讲了什么？</span><textarea name="summary" maxlength="30000" placeholder="用自己的话记录核心概念、适用场景、还没弄懂的问题…">${esc(base.summary)}</textarea></label><button class="button small" type="submit">保存修订</button></form></details></section><section class="panel"><div class="section-head" style="margin-top:0"><h2>我的补充与批注 <span>${personalNotes(v).length} 条补充</span></h2><button class="button small soft" data-action="new-note" data-id="${esc(v.id)}">＋ 写笔记</button></div>${personalNotes(v).length ? personalNotes(v).slice().sort((a,b)=>(a.timeSec ?? Infinity)-(b.timeSec ?? Infinity)).map(n => `<article class="note"><div class="note-header"><a class="note-time" href="${esc(jumpURL(v,n.timeSec))}" target="_blank" rel="noopener noreferrer">${timeLabel(n.timeSec)} ↗</a><span class="note-date">${esc(n.createdAt.slice(0,10))}</span><button class="icon-button" aria-label="编辑笔记 ${esc(n.text.slice(0,30))}" data-action="edit-note" data-id="${esc(n.id)}">···</button></div><div class="note-text">${esc(n.text)}</div></article>`).join('') : '<p class="metadata">遇到一个值得记住的概念，标上时间，写下一句话。</p>'}</section></div><aside><section class="panel"><h2>学习进度</h2><label class="field"><span>当前状态</span><select id="detail-status">${Object.entries(statusNames).map(([id,name])=>`<option value="${id}"${v.status === id ? ' selected' : ''}>${name}</option>`).join('')}</select></label><button class="button small${v.favorite ? ' soft' : ''}" data-action="favorite" data-id="${esc(v.id)}">${icon('star')}${v.favorite ? '已重点收藏' : '加入重点收藏'}</button><div class="metadata"><strong>所属分类</strong><p>${esc(pathName(v.categoryId))}</p><strong>标签</strong><div class="tags">${v.tags.map(t=>`<button class="tag" data-action="search-tag" data-tag="${esc(t)}">${esc(t)}</button>`).join('') || '尚未添加'}</div><strong>收藏时间</strong><p>${esc(v.createdAt.slice(0,10))}</p></div></section></aside></div>`;
}
function qualityPage() {
  return heading('按需查看','质量与来源','查看资料来源、核对问题和修订记录。日常阅读请进入课程笔记。')
    + state.library.videos.map(v=>`<details class="panel quality-course" data-quality-video="${esc(v.id)}"><summary>${esc(displayTitle(v))}<span class="quality-meta">${v.knowledge ? v.knowledge.modules.length+' 个模块' : '模块尚未完成'}</span></summary><div class="quality-content"><p><strong>来源：</strong>${esc(v.transcriptInfo?.source || (v.transcript ? '已保存的课程资料' : '尚无学习资料'))}${v.transcriptInfo?.language?' · '+esc(v.transcriptInfo.language):''}</p>${v.transcriptInfo?.kind==='asr'?'<p class="notice">本机语音识别可能误听术语、数字与代码，请结合课程核对。</p>':''}<p class="metadata">最近任务：${esc(v.automation?.message || '尚无记录')}${v.automation?.model?' · 模型：'+esc(v.automation.model):''}</p><div class="button-row"><button class="button small" data-action="navigate" data-view="video" data-id="${esc(v.id)}">打开笔记</button><button class="button small soft" data-action="format-cornell" data-id="${esc(v.id)}" ${v.knowledge?'':'disabled'}>AI 整理康奈尔结构</button><button class="button small" data-action="build-knowledge" data-id="${esc(v.id)}">重新构建模块</button>${['YouTube','哔哩哔哩'].includes(platform(v.url))?`<button class="button small" data-action="retry-import" data-id="${esc(v.id)}">重新获取与整理</button>`:''}</div>${v.visuals?`<p class="metadata">图文导学：${esc(v.visuals.message)}。画面用于回顾，AI 笔记依据字幕或转录整理。</p>`:''}<button class="button small" data-action="build-visuals" data-id="${esc(v.id)}">重新生成图文导学</button>${qualityReport(v)}${v.notes.some(n=>n.text.startsWith('旧版总结（'))?`<details class="saved-history"><summary>历史总结版本</summary>${v.notes.filter(n=>n.text.startsWith('旧版总结（')).map(n=>`<article class="review-issue"><p class="metadata">${esc(n.createdAt.slice(0,10))}</p><div class="rich-notes">${renderMarkdown(n.text)}</div></article>`).join('')}</details>`:''}<section class="panel"><details><summary>字幕与学习资料（通常由网站自动读取）</summary><div class="section-head" style="margin-top:15px"><h2>原始资料</h2><button class="button small" data-action="fetch-transcript" data-id="${esc(v.id)}">获取原字幕 / 本机转录</button><button class="button small soft" data-action="import-transcript" data-id="${esc(v.id)}">导入转录文件并自动制作笔记</button></div><form data-transcript-form="${esc(v.id)}"><label class="field"><span>转录文本 / 课堂资料（供 AI 整理使用）</span><textarea name="transcript" maxlength="200000" rows="6" placeholder="读取字幕，或将视频页面的转录文本粘贴到这里。AI 会依据这些资料及你的笔记整理。">${esc(v.transcript || '')}</textarea><small>${(v.transcript || '').length.toLocaleString()} 字符 · 资料先保存，AI 才会使用；部分视频的字幕可能无法自动读取。</small></label><button class="button small" type="submit">保存学习资料</button></form></details></section></div></details>`).join('');
}

function searchPage() {
  const terms = state.search.toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const matches = text => terms.every(term => text.toLocaleLowerCase().includes(term));
  const categories = state.library.categories.filter(c => matches(pathName(c.id) + ' ' + c.description));
  const videos = state.library.videos.filter(v => matches([v.title,v.author,v.tags.join(' '),pathName(v.categoryId),v.summary,...v.notes.map(n=>n.text),v.knowledge ? JSON.stringify(v.knowledge.modules) : ''].join(' ')));
  const insights = (state.library.insights || []).filter(x=>matches(x.title+' '+x.content));
  return heading('搜索我的知识库', `搜索“${state.search}”`, '搜索范围包含分类、视频标题、作者、标签、知识总结和时间点笔记。')
    + (categories.length ? `<div class="section-head"><h2>相关分类</h2></div><div class="category-grid">${categories.map(categoryCard).join('')}</div>` : '')
    + `<div class="section-head"><h2>相关视频与笔记</h2></div>${videos.length ? `<div class="video-list">${videos.map(videoCard).join('')}</div>` : empty('没有找到匹配视频', '试试更短的关键词，或检查视频和笔记是否已经保存。')}`
    + (insights.length ? '<div class="section-head"><h2>相关共通经验</h2></div>'+insights.map(insightCard).join('') : '');
}
function renderMain() {
  if (!state.library) return;
  let html;
  if (state.search) html = searchPage();
  else if (state.view === 'category') html = categoryPage();
  else if (state.view === 'video') html = detailPage();
  else if (state.view === 'notes') html = notesPage();
  else if (state.view === 'knowledge') html = knowledgePage();
  else if (state.view === 'quality') html = qualityPage();
  else if (state.view === 'practice') html = practicePage(state.practiceData,state.library,state.practice);
  else if (state.view === 'insights') html = insightsPage();
  else if (state.view === 'videos') html = heading('我的视频库','全部视频','收藏有价值的课程，按照自己的节奏学习。',addVideoButton) + videoSection(state.library.videos);
  else html = homePage();
  $('#content').innerHTML = html;
  const name = state.search ? '搜索' : state.view === 'category' ? pathName(state.id) : state.view === 'video' ? pathName(video(state.id).categoryId) + ' / 视频笔记' : ({home:'分类总览',videos:'全部视频',notes:'学习笔记',insights:'AI 总结与经验',knowledge:'知识模块',practice:'复习与自测',quality:'质量与来源'}[state.view] || '分类总览');
  $('#breadcrumb').innerHTML = '我的学习空间 <span class="muted">/</span> <strong>' + esc(name) + '</strong>';
  if(state.view==='video' && state.pendingModule) {
    document.getElementById('module-'+state.pendingModule)?.scrollIntoView({block:'start'});
    state.pendingModule=null;
  }
}
function renderAll() {
  renderNavigation(); renderMain();
  $('#save-status').textContent = '已保存到项目 · 第 ' + state.library.revision + ' 版';
}

function showModal(title, description, content, onSubmit) {
  if (modal.open) modal.close();
  modal.innerHTML = `<div class="modal-head"><h2 id="modal-title">${esc(title)}</h2><button class="icon-button" aria-label="关闭窗口" data-action="close-modal">✕</button></div><p class="modal-description">${esc(description)}</p>${content}`;
  const form = modal.querySelector('form');
  if (form && onSubmit) form.addEventListener('submit', async event => {
    event.preventDefault();
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    try { await onSubmit(new FormData(form)); modal.close(); }
    catch (error) { form.querySelector('.form-error').textContent = error.message; }
    finally { submit.disabled = false; }
  });
  modal.showModal();
}
const actions = (label, extra = '') => `<p class="form-error" role="alert"></p><div class="modal-actions">${extra}<button type="button" class="button" data-action="close-modal">取消</button><button type="submit" class="button primary">${label}</button></div>`;
function categoryOptions(selected, excluded = new Set(), root = false) {
  return (root ? '<option value="">无，作为一级分类</option>' : '') + state.library.categories.filter(c=>!excluded.has(c.id)).map(c=>`<option value="${esc(c.id)}"${selected === c.id ? ' selected' : ''}>${esc(pathName(c.id))}</option>`).join('');
}
function categoryModal(id) {
  const c = id ? category(id) : {name:'',parentId:state.view === 'category' ? state.id : null,description:'',color:'green'};
  showModal(id ? '编辑分类' : '先建一个学习分类', '分类可以继续细分。例如：网络工程 → 网络基础 → TCP/IP。', `<form><label class="field"><span>分类名称</span><input name="name" required maxlength="60" placeholder="例如：网络基础" value="${esc(c.name)}"></label><label class="field"><span>上级分类</span><select name="parentId">${categoryOptions(c.parentId,id ? new Set(descendants(id)) : new Set(),true)}</select></label><label class="field"><span>一句话说明</span><input name="description" maxlength="500" placeholder="这个分类准备学习什么？" value="${esc(c.description)}"></label><label class="field"><span>分类颜色</span><select name="color">${[['green','苔绿'],['blue','雾蓝'],['purple','淡紫'],['orange','暖杏']].map(([value,name])=>`<option value="${value}"${c.color === value ? ' selected' : ''}>${name}</option>`).join('')}</select></label>${actions('保存分类',id ? `<button type="button" class="button danger" data-action="delete-category" data-id="${esc(id)}">删除空分类</button>` : '')}</form>`, async form => {
    const next = structuredClone(state.library);
    const item = {id:id || uid(),name:form.get('name').trim(),parentId:form.get('parentId') || null,description:form.get('description').trim(),color:form.get('color')};
    if (next.categories.some(other => other.id !== id && other.parentId === item.parentId && other.name === item.name)) throw new Error('这个位置已经有同名分类了');
    if (id) next.categories[next.categories.findIndex(x=>x.id === id)] = item; else next.categories.push(item);
    await save(next); toast('分类已保存');
  });
}
const importNames = {queued:'等待整理',metadata:'正在识别视频',transcript:'正在读取字幕',ai:'AI 正在分类与写笔记',ready:'已自动整理',needs_content:'待补充字幕',failed:'整理未完成'};
function automationPanel(v) {
  const status=v.automation?.status;
  if(!status || status==='ready') return '';
  const active=['queued','metadata','transcript','ai'].includes(status);
  return `<section class="panel import-panel" role="status"><strong>${active?'正在准备笔记':'这次整理尚未完成'}</strong><p>${active?esc(v.automation.message):'已有笔记保留，可在“质量与来源”里查看原因并重试。'}</p>${active?'<small>完成后自动保存，可以继续浏览其他课程。</small>':`<button class="button small" data-action="navigate" data-view="quality" data-id="${esc(v.id)}">查看详情</button>`}</section>`;
}
function smartImportModal() {
  showModal('粘贴链接，一键整理','支持公开 YouTube、哔哩哔哩视频及 b23.tv 分享链接。原视频语言自动识别。', `<form><label class="field"><span>视频链接</span><input name="url" required maxlength="3000" placeholder="粘贴 YouTube、哔哩哔哩或 b23.tv 链接" autocomplete="off" autofocus></label><p class="metadata">网站自动识别原语言字幕；没有可用字幕时尝试本机语音转录，再由 AI 直接制作中文笔记，不需要视频提供中文字幕。B站分 P 请打开要学的那一集后复制链接。资料会发送给已配置的模型，并使用当前额度。</p><label class="source-choice"><input type="checkbox" name="detailed" checked><span>自动制作详尽笔记、脑图与复习问答<small>完成后自动核对，报告位于“质量与来源”；取消后仅生成基础总结。</small></span></label>${actions('开始自动整理','<button type="button" class="button" data-action="manual-video">手动收藏其他平台</button>')}</form>`, async form => {
    const result=await post('/api/import',{url:form.get('url').trim(),detailed:form.get('detailed')==='on'});
    state.library=result.library;go('video',result.videoId);renderAll();
    toast(result.duplicate ? '这个视频已收藏，已为你打开' : '链接已保存，正在自动整理');
  });
}

function videoModal(id) {
  if (!state.library.categories.length) { toast('先创建一个分类，再收藏视频'); categoryModal(); return; }
  const v = id ? video(id) : {title:'',url:'',author:'',categoryId:state.view === 'category' ? state.id : state.library.categories[0].id,tags:[],durationSec:0,status:'todo'};
  showModal(id ? '编辑视频' : '把好视频放进分类', '支持 YouTube、哔哩哔哩和其他课程链接。标题由你填写，方便以后找到。', `<form><label class="field"><span>视频链接</span><input name="url" required maxlength="3000" placeholder="https://www.youtube.com/watch?v=…" value="${esc(v.url)}"></label><label class="field"><span>视频标题</span><input name="title" required maxlength="500" placeholder="给课程一个好找的名字" value="${esc(displayTitle(v))}"></label><label class="field"><span>放入分类</span><select name="categoryId" required>${categoryOptions(v.categoryId)}</select></label><div class="field-row"><label class="field"><span>作者 / 频道（选填）</span><input name="author" maxlength="200" value="${esc(v.author)}"></label><label class="field"><span>时长（选填）</span><input name="duration" placeholder="例如：8:26" value="${v.durationSec ? timeLabel(v.durationSec) : ''}"></label></div><label class="field"><span>标签（选填）</span><input name="tags" maxlength="1200" placeholder="用逗号分隔，例如：OSI, TCP/IP, 网络入门" value="${esc(v.tags.join(', '))}"></label><label class="field"><span>学习状态</span><select name="status">${Object.entries(statusNames).map(([value,name])=>`<option value="${value}"${v.status === value ? ' selected' : ''}>${name}</option>`).join('')}</select></label>${actions('保存视频',id ? `<button type="button" class="button danger" data-action="delete-video" data-id="${esc(id)}">移除视频</button>` : '')}</form>`, async form => {
    const url = canonicalURL(form.get('url'));
    if (state.library.videos.some(other=>other.id !== id && canonicalURL(other.url) === url)) throw new Error('这个视频已经收藏过了，可以在搜索中找到它');
    const next = structuredClone(state.library);
    const item = {...(id ? v : {id:uid(),favorite:false,summary:'',notes:[],createdAt:now()}),title:form.get('title').trim(),url,categoryId:form.get('categoryId'),author:form.get('author').trim(),durationSec:parseTime(form.get('duration')),tags:[...new Set(form.get('tags').split(/[,，]/).map(t=>t.trim()).filter(Boolean))],status:form.get('status'),updatedAt:now()};
    if (id) next.videos[next.videos.findIndex(x=>x.id === id)] = item; else next.videos.push(item);
    await save(next); toast('视频已保存到分类');
  });
}
function noteModal(id) {
  const v = video(state.id), n = id ? v.notes.find(x=>x.id === id) : {text:'',timeSec:null};
  showModal(id ? '编辑笔记' : '记下这一刻的理解', v.title, `<form><label class="field"><span>视频时间点（选填）</span><input name="time" placeholder="例如：4:25" value="${n.timeSec === null ? '' : timeLabel(n.timeSec)}"><small>保存后可点击时间，跳回视频对应位置。其他课程平台可能不支持时间跳转。</small></label><label class="field"><span>笔记内容</span><textarea name="text" required maxlength="30000" rows="7" placeholder="这个概念是什么？它解决什么问题？可以举个例子吗？">${esc(n.text)}</textarea></label>${actions('保存笔记',id ? `<button type="button" class="button danger" data-action="delete-note" data-id="${esc(id)}">移除笔记</button>` : '')}</form>`, async form => {
    const next = structuredClone(state.library), target = next.videos.find(x=>x.id === v.id);
    const item = {id:id || uid(),text:form.get('text').trim(),timeSec:parseTime(form.get('time'),true),createdAt:id ? n.createdAt : now()};
    if (id) target.notes[target.notes.findIndex(x=>x.id === id)] = item; else target.notes.push(item);
    target.updatedAt = now(); await save(next); toast('笔记已保存');
  });
}
function confirmModal(title, description, callback) {
  showModal(title,description,`<form>${actions('确认')}</form>`,callback);
}
function renderMarkdown(markdown) {
  const inline=text=>esc(text).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>');
  let list=false,code=false,html='';
  for(const raw of markdown.split('\n')) {
    const line=raw.trim();
    if(line.startsWith('```')) {if(list){html+='</ul>';list=false;}code=!code;html+=code?'<pre><code>':'</code></pre>';continue;}
    if(code){html+=esc(raw)+'\n';continue;}
    if(/^[-*] /.test(line)){if(!list){html+='<ul>';list=true;}html+='<li>'+inline(line.slice(2))+'</li>';continue;}
    if(list){html+='</ul>';list=false;}
    const heading=line.match(/^(#{1,6})\s+(.+)/);
    if(heading){const level=Math.min(4,heading[1].length+1);html+=`<h${level}>${inline(heading[2])}</h${level}>`;}
    else if(line) html+='<p>'+inline(line)+'</p>';
  }
  if(list)html+='</ul>';if(code)html+='</code></pre>';
  return html;
}
function exportButtons(id='') {
  return `<button class="button soft" data-action="ipad-export" data-id="${esc(id)}">导出到 iPad 无边记</button>`;
}
function ipadExportModal(id='') {
  showModal('带到 iPad，在无边记继续思考','导出仅使用已保存的笔记、补充和经验归纳，不包含原始字幕、账号或密钥。',`<div class="backup-option"><div><h3>无边记素材包 · 图片＋PDF</h3><p>每页一张清晰图片，带批注留白；解压后把所需图片拖进看板。</p></div><button class="button small primary" data-action="download-study" data-kind="freeform" data-video="${esc(id)}">下载素材包</button></div><div class="backup-option"><div><h3>阅读与归档 · PDF</h3><p>保留可选择的文字、视频来源链接和手写练习页。</p></div><button class="button small" data-action="download-study" data-kind="pdf" data-video="${esc(id)}">下载 PDF</button></div><ol class="help-list"><li>通过 AirDrop 或你自己的 iCloud 云盘传到 iPad。</li><li>在“文件”里轻点 ZIP 解压，分屏拖入 PNG 图片到无边记；也可插入 PDF 作为附件。</li><li>用 Apple Pencil 或手指在画布上添加手写、文本和连线。</li></ol><p class="modal-description" style="margin-top:14px">图片里的文字不能直接编辑。无边记中的批注由无边记保存，不会自动回写本网站；AI 原稿会继续留在知识库。</p><div class="modal-actions"><button class="button" data-action="close-modal">完成</button></div>`);
}
async function downloadStudy(kind,id,button) {
  const label=button.textContent;button.disabled=true;button.textContent='正在生成…';
  try {
    const response=await fetch('/api/export?format='+encodeURIComponent(kind)+(id?'&videoId='+encodeURIComponent(id)+'&language='+encodeURIComponent(effectiveLanguage(video(id),state.noteLanguages[id] || 'zh-CN')):''));
    if(!response.ok) {const result=await response.json();throw new Error(result.error || '导出失败');}
    const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');
    link.href=url;link.download=kind==='freeform'?'无边记学习素材.zip':'AI学习笔记.pdf';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
    toast('文件已生成，请保存后传到 iPad');
  } finally {button.disabled=false;button.textContent=label;}
}
function batchAIModal() {
  const pending=state.library.videos.filter(v=>['YouTube','哔哩哔哩'].includes(platform(v.url))&&(!v.summary||['failed','needs_content'].includes(v.automation?.status)));
  if(!pending.length){toast('目前的视频已有笔记；可在视频详情中重新整理');return;}
  showModal('让 AI 整理尚未完成的课程',`本次可将 ${Math.min(pending.length,20)} 条视频加入队列。系统依次读取字幕、分类、写笔记并保存；会使用当前模型额度。`, `<form>${actions('开始自动整理')}</form>`,async()=>{
    let count=0;
    for(const v of pending.slice(0,20)){const r=await post('/api/import',{url:v.url,retry:true});state.library=r.library;if(!r.duplicate)count++;}
    renderAll();toast(`已安排 ${count} 条视频自动整理`);
  });
}

function backupModal() {
  showModal('导出与备份', '个人学习文件请自行保管，导出不会上传到 GitHub。', `<div class="backup-option"><div><h3>iPad 无边记 · PDF 与图片</h3><p>AI 笔记带手写留白，图片可拖进无边记画布。</p></div><button class="button small primary" data-action="ipad-export">选择导出</button></div><div class="backup-option"><div><h3>完整备份 · JSON</h3><p>包含分类、视频、知识模块、全部笔记与自测记录。</p></div><button class="button small" data-action="export-json">导出 JSON</button></div><div class="backup-option"><div><h3>阅读版 · Markdown</h3><p>包含详尽模块、脑图大纲、自查与个人作答。</p></div><button class="button small" data-action="export-markdown">导出笔记</button></div><div class="backup-option"><div><h3>从备份合并导入</h3><p>保留当前资料，重复链接保留当前版本。</p></div><button class="button small" data-action="import">选择 JSON</button></div><p class="modal-description">每次保存前还会自动保留一个本机备份，最近 30 份位于 data/.backups。备份仅保存在这台电脑，记得另存完整 JSON。</p><div class="modal-actions"><button class="button" data-action="close-modal">完成</button></div>`);
}
function download(filename, content, mime) {
  const url = URL.createObjectURL(new Blob([content], {type:mime}));
  const a = document.createElement('a'); a.href=url; a.download=filename;
  document.body.append(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(url),10000);
}
function markdown() { return libraryMarkdown(state.library,state.noteLanguages); }
function prepareImport(incoming) {
  if (incoming?.schemaVersion !== 1 || !Array.isArray(incoming.categories) || !Array.isArray(incoming.videos) || incoming.categories.length > 1000 || incoming.videos.length > 10000) throw new Error('请选择学习图谱导出的 JSON 备份');
  const next = structuredClone(state.library), ids = new Map(), visiting = new Set();
  function addCategory(c) {
    if(ids.has(c.id)) return ids.get(c.id);
    if(visiting.has(c.id)) throw new Error('备份里的分类存在循环');
    visiting.add(c.id);
    let parentId = null;
    if(c.parentId) {
      const parent=incoming.categories.find(x=>x.id===c.parentId);
      if(!parent) throw new Error('备份里的上级分类不存在');
      parentId=addCategory(parent);
    }
    const found=next.categories.find(x=>x.name===c.name && x.parentId===parentId);
    const id=found?.id || uid();
    if(!found) next.categories.push({...c,id,parentId});
    ids.set(c.id,id); visiting.delete(c.id); return id;
  }
  for(const c of incoming.categories) addCategory(c);
  const urls=new Set(next.videos.map(v=>canonicalURL(v.url)));
  let added=0,skipped=0;
  const videoIds=new Map();
  for(const v of incoming.videos) {
    const url=canonicalURL(v.url);
    if(urls.has(url)) {videoIds.set(v.id,next.videos.find(x=>canonicalURL(x.url)===url).id);skipped++;continue;}
    const newId=uid();videoIds.set(v.id,newId);
    next.videos.push({...v,id:newId,categoryId:ids.get(v.categoryId),url});
    urls.add(url); added++;
  }
  next.insights ||= [];
  if(incoming.insights !== undefined && (!Array.isArray(incoming.insights)||incoming.insights.length>3000)) throw new Error('经验归纳备份格式不正确');
  for(const item of incoming.insights || []) {
    if(next.insights.some(x=>x.title===item.title&&x.content===item.content)) continue;
    next.insights.push({...item,id:uid(),sources:(item.sources || []).map(s=>({...s,videoId:videoIds.get(s.videoId)||s.videoId}))});
  }
  next.learning=mergePracticeAttempts(next.learning,incoming.learning,videoIds);
  return {next,added,skipped,categories:next.categories.length-state.library.categories.length};
}

document.addEventListener('click', async event => {
  const button = event.target.closest('[data-action]');
  if(!button || button.disabled) return;
  const {action,id,view,status,tag} = button.dataset;
  try {
    if(action==='navigate') go(view,id);
    else if(action==='close-modal') modal.close();
    else if(action==='new-category') categoryModal();
    else if(action==='edit-category') categoryModal(id);
    else if(action==='new-video') smartImportModal();
    else if(action==='build-knowledge'||action==='review-knowledge') {const r=await post('/api/knowledge/build',{videoId:id,reviewOnly:action==='review-knowledge'});state.library=r.library;renderAll();toast(r.duplicate?'这个课程正在整理，请等待完成':'AI 任务已排队，完成后自动保存');}
    else if(action==='build-visuals') {const r=await post('/api/media/build',{videoId:id});state.library=r.library;renderAll();toast('已开始准备真实封面与视频画面');}
    else if(action==='translate-notes') {const r=await post('/api/notes/translate',{videoId:id,language:button.dataset.language});state.library=r.library;renderAll();toast(r.cached?'已读取保存的译文':'AI 已开始翻译，完成后自动切换');}
    else if(action==='format-cornell') {const r=await post('/api/knowledge/format',{videoId:id});state.library=r.library;renderAll();toast('AI 已开始整理康奈尔提示与小结，正文继续保留');}
    else if(action==='cornell-toggle') {const sheet=button.closest('.cornell-sheet');const hidden=sheet.classList.toggle('cornell-recall');button.setAttribute('aria-expanded',String(!hidden));button.textContent=hidden?'显示记录与小结':'遮住记录自测';}
    else if(action==='knowledge-tab') {state.knowledgeTabs[id]=button.dataset.tab;renderMain();}
    else if(action==='knowledge-collapse') {state.compactMaps[id]=!state.compactMaps[id];renderMain();}
    else if(action==='knowledge-module') {const mid=button.dataset.module;state.knowledgeTabs[state.id]='details';renderMain();document.getElementById('module-'+mid)?.scrollIntoView({block:'start'});}
    else if(action==='download-mindmap') download('知识脑图.svg',mindmapSVG(localizedVideo(video(id),state.noteLanguages[id] || 'zh-CN').knowledge),'image/svg+xml;charset=utf-8');
    else if(action==='import-transcript') {state.materialVideo=id;$('#transcript-file').click();}
    else if(action==='manual-video') videoModal();
    else if(action==='retry-import') {button.disabled=true;const r=await post('/api/import',{url:video(id).url,retry:true});state.library=r.library;renderAll();toast('已加入自动整理队列');}
    else if(action==='edit-video') videoModal(id);
    else if(action==='new-note') noteModal();
    else if(action==='edit-note') noteModal(id);
    else if(action==='filter') {state.status=status;renderMain();}
    else if(action==='filter-favorites') {state.favorites=!state.favorites;renderMain();}
    else if(action==='search-tag') {$('#search').value=tag;state.search=tag;renderAll();}
    else if(action==='favorite') {
      const next=structuredClone(state.library),v=next.videos.find(x=>x.id===id);
      v.favorite=!v.favorite; await save(next); toast(v.favorite ? '已加入重点收藏' : '已取消重点收藏');
    }
    else if(action==='delete-category') {
      if(children(id).length || state.library.videos.some(v=>v.categoryId===id)) throw new Error('请先移动分类里的视频和子分类，再删除这个空分类');
      confirmModal('删除这个空分类？',category(id).name+'。删除前会自动保留本机备份。',async()=>{
        const next=structuredClone(state.library);next.categories=next.categories.filter(c=>c.id!==id);
        if(state.view==='category'&&state.id===id) {state.view='home';state.id=null;}
        await save(next);go('home');toast('空分类已移除');
      });
    }
    else if(action==='delete-video') confirmModal('从知识库移除视频？','这个视频的总结和笔记也会一起移除。删除前会自动保留本机备份。',async()=>{
      const next=structuredClone(state.library),parent=video(id).categoryId;
      next.videos=next.videos.filter(v=>v.id!==id);state.view='category';state.id=parent;
      await save(next);go('category',parent);toast('视频已移除');
    });
    else if(action==='delete-note') confirmModal('移除这条笔记？','删除前会自动保留本机备份。',async()=>{
      const next=structuredClone(state.library),v=next.videos.find(x=>x.id===state.id);
      v.notes=v.notes.filter(n=>n.id!==id);v.updatedAt=now();await save(next);toast('笔记已移除');
    });
    else if(action==='backup') backupModal();
    else if(action==='ipad-export') ipadExportModal(id || '');
    else if(action==='download-study') await downloadStudy(button.dataset.kind,button.dataset.video || '',button);
    else if(action==='batch-ai') batchAIModal();
    else if(action==='export-json') download(`study-atlas-${new Date().toLocaleDateString('sv-SE')}.json`,JSON.stringify(state.library,null,2)+'\n','application/json;charset=utf-8');
    else if(action==='export-markdown') download('我的学习图谱.md',markdown(),'text/markdown;charset=utf-8');
    else if(action==='import') $('#import-file').click();
  } catch(error) {toast(error.message,true);}
});

document.addEventListener('submit',async event=>{
  if(event.target.id!=='summary-form') return;
  event.preventDefault();
  const button=event.target.querySelector('[type="submit"]');button.disabled=true;
  try {
    const next=structuredClone(state.library),v=next.videos.find(x=>x.id===state.id);
    v.summary=new FormData(event.target).get('summary').trim();delete v.cornell;v.updatedAt=now();
    await save(next);toast('知识总结已保存');
  } catch(error) {toast(error.message,true);button.disabled=false;}
});
document.addEventListener('change',async event=>{
  if(event.target.id!=='detail-status') return;
  try {
    const next=structuredClone(state.library),v=next.videos.find(x=>x.id===state.id);
    v.status=event.target.value;v.updatedAt=now();await save(next);toast('学习状态已保存');
  } catch(error) {event.target.value=video(state.id).status;toast(error.message,true);}
});
$('#search').addEventListener('input',event=>{state.search=event.target.value.trim();renderAll();});
document.addEventListener('keydown',event=>{
  if(event.key==='/'&&!modal.open&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)) {event.preventDefault();$('#search').focus();}
});
$('#import-file').addEventListener('change',async event=>{
  const file=event.target.files[0];event.target.value='';if(!file) return;
  try {
    if(file.size>4*1024*1024) throw new Error('备份最多支持 4 MB');
    const result=prepareImport(JSON.parse(await file.text()));
    confirmModal('合并这份备份？',`将新增 ${result.categories} 个分类、${result.added} 个视频；跳过 ${result.skipped} 个重复链接，保留当前版本。`,async()=>{await save(result.next);toast('备份已合并');});
  } catch(error) {toast(error instanceof SyntaxError ? '这个文件不是有效的 JSON' : error.message,true);}
});
window.addEventListener('hashchange',route);

// AI 默认自动保存，保留人工笔记与旧版总结。
const post = (url, data={}) => request(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
const hasMaterial = v => [(v.transcript||''),v.summary,...v.notes.map(n=>n.text),v.knowledge ? JSON.stringify(v.knowledge.modules) : ''].join('\n').trim().length>=20;
function insightCard(item) {
  return `<article class="knowledge-card"><div class="small-label">共通经验 · ${esc(item.createdAt.slice(0,10))}</div><h2>${esc(item.title)}</h2><div class="rich-notes">${renderMarkdown(item.content)}</div><div class="source-list">${item.sources.map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">[${esc(s.source)}] ${esc(s.title)} ↗</a>`).join('')}</div><button class="link-button" data-action="delete-insight" data-id="${esc(item.id)}">移除这篇归纳</button></article>`;
}
function insightsPage() {
  const status=state.integrations;
  const connection=status?.ai.mode==='deepseek' ? 'DeepSeek API' : status?.harness.configured ? 'Harness · '+(status.harness.model.model || 'DeepSeek') : '尚未连接 AI';
  return heading('连接知识 · 提炼经验','AI 总结与共通经验','从多条视频里寻找共同规律，也保留差异和适用条件。',`<button class="button" data-action="ai-settings">AI 连接设置</button><button class="button primary" data-action="synthesize">${icon('spark')}开始归纳</button>`)
    + `<div class="notice">当前使用：${esc(connection)}。整理依据是你保存的字幕、总结与时间点笔记；生成结果标注来源并自动保存，你可以随时补充与修订。</div>`
    + (state.aiJob ? '<div class="notice">正在整理所选资料，完成后自动保存。</div>' : '')
    + (state.aiDraft ? '<div class="panel"><h2>有一份待核对的 AI 草稿</h2><p class="metadata">先检查结论和来源，再加入知识库。</p><button class="button small soft" data-action="show-draft">查看草稿</button></div>' : '')
    + ((state.library.insights || []).length ? state.library.insights.slice().reverse().map(insightCard).join('') : empty('让不同视频里的知识连接起来','先为至少两条视频保存字幕或笔记，再选中它们归纳共通经验。','<button class="button soft" data-action="navigate" data-view="videos">去整理视频资料</button>'));
}
async function refreshIntegrations() {state.integrations=await request('/api/integrations/status');return state.integrations;}
async function aiSettings() {
  const status=await refreshIntegrations();
  showModal('连接你的 AI 工具','优先使用本机 DeepSeek Harness，也可切换到官方 DeepSeek API。连接凭据只保存在本机 .local，导出备份不包含凭据。',`<div class="notice">资料获取：原语言字幕优先；${status.transcription?.ready ? '本机语音转录已启用（'+esc(status.transcription.model)+'）' : '可运行项目中的“安装本机转录.command”启用无字幕转录'}。中文笔记由 AI 直接整理。</div><div class="notice">Harness：${status.harness.configured ? '已连接 '+esc(status.harness.model.model || '')+' · '+esc(status.harness.baseUrl) : '尚未连接'}<div class="button-row" style="margin-top:10px"><button class="button small" data-action="harness-connect">${status.harness.configured?'更新连接':'连接 Harness'}</button><button class="button small" data-action="harness-check">检查连接</button></div></div><form><label class="field"><span>整理时使用</span><select name="mode"><option value="harness"${status.ai.mode==='harness'?' selected':''}>本机 DeepSeek Harness</option><option value="deepseek"${status.ai.mode==='deepseek'?' selected':''}>DeepSeek 官方 API</option></select></label><label class="field"><span>官方 API 模型（仅 API 模式使用）</span><input name="model" maxlength="100" value="${esc(status.ai.model)}"></label><label class="field"><span>DeepSeek API Key（仅 API 模式使用）</span><input name="apiKey" type="password" autocomplete="new-password" placeholder="${status.ai.hasApiKey?'已保存；留空保留现有密钥':'选择 Harness 时无需填写'}"><small>API 模式请求发送到 api.deepseek.com，费用由你的 DeepSeek 账户承担。</small></label>${actions('保存 AI 设置')}</form>`,async form=>{state.integrations=await post('/api/integrations/ai',{mode:form.get('mode'),model:form.get('model'),apiKey:form.get('apiKey')});renderAll();toast('AI 设置已保存');});
}
function harnessConnectModal() {
  showModal('连接终端里的 Harness','在运行 dsh web 的终端复制最新的完整启动链接。它用于取得本机连接，保存后不会显示 token。',`<form><label class="field"><span>Harness 启动链接</span><input name="url" type="password" required autocomplete="off" placeholder="http://127.0.0.1:3080/?token=…"></label>${actions('连接并检查模型')}</form>`,async form=>{state.integrations=await post('/api/integrations/harness/connect',{url:form.get('url')});renderAll();toast('Harness 已连接');});
}
function synthesisModal() {
  const available=state.view==='category'?categoryVideos(state.id):state.library.videos;
  if(!available.length) {toast('先在分类里收藏视频并保存资料');return;}
  showModal('寻找这些视频的共通经验','每次选择 2 到 12 条有字幕或笔记的视频。AI 会比较共同点、差异、适用条件与可复用步骤。',`<form><label class="field"><span>这次想归纳什么？</span><input name="title" maxlength="300" value="${esc(state.view==='category'?category(state.id).name+' · 共通经验':'我的学习共通经验')}"></label><div class="source-picker">${available.map(v=>`<label class="source-choice"><input type="checkbox" name="videos" value="${esc(v.id)}"${hasMaterial(v)?' checked':' disabled'}><span>${esc(displayTitle(v))}<small>${esc(pathName(v.categoryId))} · ${hasMaterial(v)?'已有学习资料':'请先补充字幕或笔记'}</small></span></label>`).join('')}</div>${actions('让 AI 比较与归纳')}</form>`,async form=>{
    const ids=form.getAll('videos');if(ids.length<2||ids.length>12) throw new Error('请选择 2 到 12 条视频');
    const title=form.get('title').trim() || '我的学习共通经验';
    // 先关闭选择窗口，生成状态在另一个窗口中显示。
    setTimeout(()=>runAI('synthesis',ids,title),0);
  });
}
async function runAI(mode,videoIds,title='') {
  if(state.aiJob) {toast('正在整理，请等待当前任务结束');return;}
  state.aiJob={mode,videoIds,title};
  showModal('AI 正在整理，完成后自动保存','所选字幕与笔记会交给当前模型。即使关闭这个弹窗，后端完成后也会保存结果。','<div class="ai-working"><span class="spinner"></span><p>正在提取知识脉络、比较差异、归纳可复用经验…</p></div>');
  const indicator=modal.querySelector('.ai-working');
  try {
    const result=await post('/api/ai/generate',{mode,videoIds,title:title || '我的学习共通经验'});
    state.library=result.library;state.aiJob=null;renderAll();
    if(modal.open&&modal.contains(indicator)) {
      showModal('AI 笔记已自动保存','可以继续补充自己的理解，或导出到 iPad 无边记。',`<div class="rich-notes">${renderMarkdown(result.content)}</div><div class="modal-actions"><button class="button" data-action="close-modal">完成</button><button class="button primary" data-action="ipad-export">导出到无边记</button></div>`);
    } else toast('AI 整理已完成并保存');
  } catch(error) {
    state.aiJob=null;renderAll();
    if(modal.open&&modal.contains(indicator)) showModal('这次整理尚未完成',error.message,'<div class="modal-actions"><button class="button" data-action="close-modal">关闭</button><button class="button soft" data-action="ai-settings">检查 AI 设置</button></div>');
    else toast(error.message,true);
  }
}

async function youtubeModal() {
  const status=await refreshIntegrations();
  let account='',rows='';
  if(status.youtube.connected) {
    const [profile,playlists]=await Promise.all([request('/api/youtube/account'),request('/api/youtube/playlists')]);
    account=profile.channels.map(c=>`${c.title} ${c.customUrl}`).join('、') || '已授权账号';
    state.ytPlaylists=playlists.items;state.ytNext=playlists.nextPageToken;
    rows=youtubePlaylistRows();
  }
  showModal('YouTube 账号与播放列表','使用 Google 官方只读授权，读取你的频道资料、播放列表与列表内视频。导入时由你选择分类。',`<div class="notice">${status.youtube.connected?'已连接：'+esc(account):status.youtube.configured?'OAuth 客户端已配置，等待你完成授权。':'先从 Google Cloud 导出“桌面应用”OAuth 客户端 JSON，并启用 YouTube Data API v3。'}</div>${!status.youtube.configured?'<ol class="help-list"><li>在 Google Cloud 选择项目，启用 YouTube Data API v3。</li><li>配置 Google Auth Platform，并将自己加入测试用户。</li><li>创建“桌面应用”OAuth 客户端，下载 JSON 后导入。</li></ol><a class="button small" style="margin:15px 0" href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener noreferrer">打开 Google Cloud 配置 ↗</a>':''}<div class="button-row"><button class="button small" data-action="youtube-client">导入 OAuth 客户端 JSON</button>${status.youtube.configured?'<button class="button small primary" data-action="youtube-auth">'+(status.youtube.connected?'重新授权':'连接 YouTube')+'</button>':''}${status.youtube.connected?'<button class="button small" data-action="youtube-disconnect">断开本机连接</button>':''}</div><div id="youtube-playlists">${rows}</div><p class="modal-description" style="margin-top:20px">本版本读取频道和自建播放列表。观看历史、稍后观看等不作为可保证的导入来源。字幕另行读取或粘贴，账号授权不会赋予下载他人字幕的编辑权限。</p><div class="modal-actions"><button class="button" data-action="close-modal">完成</button></div>`);
}
function youtubePlaylistRows() {
  return `<div class="section-head"><h2>选择一个播放列表</h2></div>${state.ytPlaylists.map(p=>`<div class="backup-option"><div><h3>${esc(p.title)}</h3><p>${p.count} 个视频</p></div><button class="button small" data-action="youtube-open-playlist" data-id="${esc(p.id)}">选择并预览</button></div>`).join('') || '<p class="metadata">这个账号暂无可读取的自建播放列表。</p>'}${state.ytNext?'<button class="button small" data-action="youtube-more">读取更多播放列表</button>':''}`;
}
async function youtubeImportModal(id,page='') {
  const list=state.ytPlaylists.find(p=>p.id===id);
  const data=await request('/api/youtube/playlist-items?id='+encodeURIComponent(id)+(page?'&pageToken='+encodeURIComponent(page):''));
  state.ytImport={list,data};
  showModal('导入“'+list.title+'”','每页最多 50 个视频。先选择本机分类，再导入勾选的视频；重复链接会跳过。',`<form><label class="field"><span>放入哪个分类？</span><select name="categoryId" required>${categoryOptions(state.library.categories[0]?.id)}</select></label><div class="source-picker">${data.items.map(item=>`<label class="source-choice"><input type="checkbox" name="videos" value="${esc(item.videoId)}" checked><span>${esc(item.title)}<small>${esc(item.author)}</small></span></label>`).join('')||'<p class="metadata">这一页没有可导入的视频。</p>'}</div>${data.nextPageToken?'<button type="button" class="button small" data-action="youtube-next-items">查看下一页视频</button>':''}${actions('导入选中的视频')}</form>`,async form=>{
    const selected=new Set(form.getAll('videos'));if(!selected.size) throw new Error('至少勾选一个视频');
    const next=structuredClone(state.library),urls=new Set(next.videos.map(v=>canonicalURL(v.url)));let count=0;
    for(const item of data.items.filter(x=>selected.has(x.videoId))) {
      const url='https://www.youtube.com/watch?v='+item.videoId;if(urls.has(url)) continue;
      next.videos.push({id:uid(),title:item.title,url,categoryId:form.get('categoryId'),author:item.author,durationSec:0,tags:[list.title.slice(0,60)],status:'todo',favorite:false,summary:'',transcript:'',notes:[],createdAt:now(),updatedAt:now()});urls.add(url);count++;
    }
    await save(next);toast(`已导入 ${count} 个视频；${selected.size-count} 个重复链接已跳过`);
  });
}

document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-action]');if(!button||button.disabled) return;
  const {action,id}=button.dataset;
  try {
    if(action==='ai-settings') await aiSettings();
    else if(action==='harness-connect') harnessConnectModal();
    else if(action==='harness-check') {button.disabled=true;const info=await post('/api/integrations/harness/check');toast('连接正常：'+info.model.model);}
    else if(action==='ai-summary') {
      const v=video(id);
      if(['YouTube','哔哩哔哩'].includes(platform(v.url))) {const r=await post('/api/import',{url:v.url,retry:true});state.library=r.library;renderAll();toast('AI 已开始整理，完成后自动保存');}
      else if(hasMaterial(v)) await runAI('summary',[id]);
      else toast('这个来源还需要补充字幕或学习资料');
    }
    else if(action==='synthesize') synthesisModal();
    else if(action==='show-draft') toast('AI 结果已改为自动保存，请在学习笔记或共通经验中查看');
    else if(action==='fetch-transcript') {
      button.disabled=true;button.textContent='正在获取原字幕或本机转录…';
      const result=await post('/api/ai/transcript',{videoId:id});
      const next=structuredClone(state.library),v=next.videos.find(v=>v.id===id);v.transcript=result.transcript;v.transcriptInfo={kind:result.kind || 'captions',source:result.source || '取得的学习资料',language:result.language || '',createdAt:result.createdAt || now()};v.updatedAt=now();await save(next);toast(result.partial?'已保存取得的字幕；部分语言未成功，请核对内容':'字幕已保存，可以使用 AI 整理');
    }
    else if(action==='delete-insight') confirmModal('移除这篇经验归纳？','移除前会自动保留本机备份，原视频与笔记会保留。',async()=>{const next=structuredClone(state.library);next.insights=next.insights.filter(x=>x.id!==id);await save(next);toast('经验归纳已移除');});
    else if(action==='youtube') await youtubeModal();
    else if(action==='youtube-client') $('#youtube-client-file').click();
    else if(action==='youtube-auth') {
      const auth=await post('/api/youtube/auth-url');
      showModal('在 Google 完成只读授权','请在 Google 页面选择自己的账号并确认只读权限。完成后回到这里读取播放列表。',`<a class="button primary" href="${esc(auth.url)}" target="_blank" rel="noopener noreferrer">打开 Google 授权页 ↗</a><div class="modal-actions"><button class="button" data-action="youtube">我已完成，读取账号</button></div>`);
    }
    else if(action==='youtube-disconnect') {await post('/api/youtube/disconnect');await youtubeModal();toast('本机连接已移除');}
    else if(action==='youtube-open-playlist') await youtubeImportModal(id);
    else if(action==='youtube-more') {const data=await request('/api/youtube/playlists?pageToken='+encodeURIComponent(state.ytNext));state.ytPlaylists.push(...data.items);state.ytNext=data.nextPageToken;$('#youtube-playlists').innerHTML=youtubePlaylistRows();}
    else if(action==='youtube-next-items') await youtubeImportModal(state.ytImport.list.id,state.ytImport.data.nextPageToken);
  } catch(error) {toast(error.message,true);}
  finally {button.disabled=false;if(action==='fetch-transcript') button.textContent='获取原字幕 / 本机转录';}
});
document.addEventListener('submit',async event=>{
  if(!event.target.dataset.transcriptForm) return;
  event.preventDefault();const button=event.target.querySelector('[type="submit"]');button.disabled=true;
  try {const next=structuredClone(state.library),v=next.videos.find(x=>x.id===event.target.dataset.transcriptForm);v.transcript=new FormData(event.target).get('transcript').trim();v.transcriptInfo={kind:'imported',source:'手动提供的学习资料',language:'',createdAt:now()};v.updatedAt=now();await save(next);toast('学习资料已保存');}
  catch(error) {toast(error.message,true);button.disabled=false;}
});
$('#youtube-client-file').addEventListener('change',async event=>{
  const file=event.target.files[0];event.target.value='';if(!file)return;
  try {if(file.size>50000)throw new Error('客户端配置文件过大');await post('/api/youtube/client',JSON.parse(await file.text()));await youtubeModal();toast('OAuth 客户端已配置，可以进行只读授权');}
  catch(error) {toast(error instanceof SyntaxError?'这个文件不是有效的 OAuth JSON':error.message,true);}
});

async function refreshPractice() {
  try {state.practiceData=await request('/api/learning');state.practice.error='';}
  catch(error) {state.practice.error=error.message;}
  return state.practiceData;
}

document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-action]');if(!button || button.disabled) return;
  const {action,key,mode,id}=button.dataset,ui=state.practice;
  if(!action.startsWith('practice-')) return;
  try {
    if(action==='practice-mode') {ui.mode=mode;ui.current=null;ui.skipped=[];renderMain();}
    else if(action==='practice-question') {ui.current=key;renderMain();}
    else if(action==='practice-reference') {ui.revealed[key]=true;renderMain();}
    else if(action==='practice-next') {ui.skipped.push(key);ui.current=null;state.dirty=false;renderMain();}
    else if(action==='practice-reset-session') {ui.skipped=[];ui.current=null;renderMain();}
    else if(action==='practice-refresh') {await refreshPractice();renderAll();}
    else if(action==='practice-start') {
      await refreshPractice();ui.course=id;ui.mode='all';ui.skipped=[];
      const first=state.practiceData?.items.find(c=>c.videoId===id && (!button.dataset.module || c.moduleId===button.dataset.module));
      ui.current=first ? cardKey(first) : null;go('practice');
    }
    else if(action==='practice-source') {
      state.pendingModule=button.dataset.module;
      state.knowledgeTabs[button.dataset.video]='details';go('video',button.dataset.video);
    }
  } catch(error) {toast(error.message,true);}
});

document.addEventListener('input',event=>{
  const form=event.target.closest('#practice-form');
  if(form && event.target.name==='answer') state.practice.drafts[form.dataset.key]=event.target.value;
});
document.addEventListener('change',event=>{
  if(event.target.id==='practice-course') {
    state.practice.course=event.target.value;state.practice.current=null;state.practice.skipped=[];renderMain();
  }
});
document.addEventListener('submit',async event=>{
  if(event.target.id!=='practice-form') return;
  event.preventDefault();const ui=state.practice;if(ui.busy) return;
  const key=event.target.dataset.key,card=state.practiceData.items.find(c=>cardKey(c)===key);
  if(!card) {toast('题目已更新，请刷新后重试',true);return;}
  const answer=new FormData(event.target).get('answer').trim();if(!answer) return;
  const assisted=!!ui.revealed[key],old=ui.pendingRequests[key];
  const pending=old?.answer===answer && old.assisted===assisted ? old : {id:uid(),answer,assisted};
  ui.pendingRequests[key]=pending;ui.drafts[key]=answer;ui.current=key;ui.busy=key;renderMain();
  try {
    const result=await post('/api/learning/grade',{requestId:pending.id,videoId:card.videoId,questionId:card.questionId,answer,assisted});
    state.practiceData=result.practice;state.library=await request('/api/library');
    delete ui.drafts[key];delete ui.pendingRequests[key];ui.revealed[key]=true;
    if(state.view==='practice')state.dirty=false;
    toast('AI 反馈和下次复习时间已保存');
  } catch(error) {toast(error.message,true);}
  finally {ui.busy=null;renderNavigation();if(state.view==='practice')renderMain();}
});

try {state.library=await request('/api/library');await refreshIntegrations().catch(()=>{});await refreshPractice();route();}
catch(error) {
  $('#content').innerHTML=empty('暂时打不开学习资料',esc(error.message)+'。请确认启动窗口仍在运行，然后刷新页面。');
  $('#save-status').textContent='尚未连接';
}

// 只在不编辑内容时刷新，避免后台整理打断尚未保存的笔记。
setInterval(async () => {
  if (!state.library || state.dirty || state.practice.busy || modal.open || document.activeElement?.matches('input,textarea,select') || document.hidden) return;
  try {
    const latest=await request('/api/library');
    if (latest.revision !== state.library.revision) {
      state.library=latest;await refreshPractice();route();
    }
  } catch { /* 暂时断开时保留当前页面与未提交数据。 */ }
}, 4000);

document.addEventListener('input', event => {if(event.target.closest('#content form')) state.dirty=true;});

document.addEventListener('keydown',event=>{
  const target=event.target.closest?.('[role="button"][data-action="knowledge-module"]');
  if(target && ['Enter',' '].includes(event.key)){event.preventDefault();target.dispatchEvent(new MouseEvent('click',{bubbles:true}));}
});

$('#transcript-file').addEventListener('change',async event=>{
  const file=event.target.files[0];event.target.value='';if(!file)return;
  try {if(file.size>800000)throw new Error('请按章节导入，单个文件最多 800 KB');
    const result=await post('/api/material/import',{videoId:state.materialVideo,filename:file.name,content:await file.text(),generate:true});
    state.library=result.library;renderAll();toast('学习资料已保存，AI 将自动制作中文笔记与知识模块');
  }catch(error){toast(error.message,true);}
});

document.addEventListener('change',event=>{
  const id=event.target.dataset.noteLanguage;
  if(id && noteLanguages[event.target.value]) {state.noteLanguages[id]=event.target.value;try{localStorage.setItem('study-atlas-note-languages',JSON.stringify(state.noteLanguages));}catch{}renderMain();}
});

document.addEventListener('error',event=>{
  const image=event.target;if(image.tagName==='IMG' && image.closest('.course-poster,.scene-gallery,.video-cover')){image.hidden=true;image.parentElement.classList.add('image-unavailable');}
},true);
