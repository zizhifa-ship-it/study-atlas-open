import test from 'node:test';
import assert from 'node:assert/strict';
import {libraryMarkdown} from '../exports.js';
import {knowledgePanel} from '../knowledge.js';
import {readFileSync} from 'node:fs';
test('本地资料的阅读版导出保留代码，并且不输出伪造的网页链接',()=>{
 const code='```c\n#include <stdio.h>\n  printf("hello");\n```';
 const url='studyatlas://material/'+'a'.repeat(32);
 const markdown=libraryMarkdown({categories:[{id:'local',parentId:null,name:'课堂资料'}],videos:[{id:'lesson',url,title:'课堂讲义',categoryId:'local',status:'todo',summary:code,tags:[],notes:[]}],insights:[{title:'共同点',content:'从原始资料理解概念。',sources:[{source:'S1',title:'课堂讲义',url}]}]});
 assert(markdown.includes(code));assert(markdown.includes('本地资料'));assert(!markdown.includes('studyatlas://'));
});
test('公开示例的模块来源能在站内查看，公开视频仍能返回原平台',()=>{
 const sample=JSON.parse(readFileSync(new URL('../examples/demo-library.json',import.meta.url),'utf8'));
 const video=sample.videos[0];
 const html=knowledgePanel(video,'details',false,text=>text);
 assert(html.includes('查看原始课堂资料'));
 assert(html.includes('data-view="quality"'));
 assert(!html.includes('href="studyatlas://'));
 const external=knowledgePanel({...video,url:'https://www.youtube.com/watch?v=example'},'details',false,text=>text);
 assert(external.includes('href="https://www.youtube.com/watch?v=example"'));
});
