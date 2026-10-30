import test from 'node:test';
import assert from 'node:assert/strict';
import {localizedVideo,effectiveLanguage,translationControls,noteLanguages} from '../translations.js';
import {knowledgePanel,qualityReport} from '../knowledge.js';
const module={id:'m1',title:'寻址',notes:'原有内容',objective:'理解',prerequisites:[],concepts:[],examples:[],pitfalls:[],questions:[],evidence:[]};
const video={id:'v1',title:'原课',summary:'中文原稿',notes:[],url:'https://example.com/course',knowledge:{title:'原稿',overview:'概览',modules:[module],review:{issues:[],summary:'核对细节',corrections:[],checkedAt:'2026-10-29'}},translations:{en:{title:'Course',summary:'English notes',overview:'Overview',cornell:{cues:['Why?'],summary:'Summary'},modules:[{...module,title:'Addressing',notes:'English module'}],stale:false}}};
test('选择语言只替换笔记副本，中文原稿与批注保留',()=>{const copy=localizedVideo(video,'en');assert.equal(copy.summary,'English notes');assert.equal(copy.knowledge.modules[0].title,'Addressing');assert.equal(video.summary,'中文原稿');assert.equal(copy.notes,video.notes);assert.equal(effectiveLanguage(video,'en'),'en');});
test('过期或未生成译文不会被当作当前内容',()=>{const changed={...video,translations:{en:{...video.translations.en,stale:true}}};assert.equal(localizedVideo(changed,'en'),changed);assert.equal(effectiveLanguage(changed,'en'),'zh-CN');assert(translationControls(changed,'en').includes('原稿已更新'));assert(translationControls(video,'de').includes('生成德语笔记'));assert.equal(Object.keys(noteLanguages).length,8);});
test('主要阅读区只有笔记与脑图，自查被放到专属板块',()=>{const main=knowledgePanel(video,'details',false,x=>x);assert(!main.includes('自查报告'));assert(!main.includes('核对细节'));assert(!main.includes('重建模块'));assert(qualityReport(video).includes('核对细节'));assert(qualityReport(video).includes('再自查一次'));});
