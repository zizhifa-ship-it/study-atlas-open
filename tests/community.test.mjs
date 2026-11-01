import test from 'node:test';
import assert from 'node:assert/strict';
import {libraryMarkdown} from '../exports.js';
test('本地资料的阅读版导出保留代码，并且不输出伪造的网页链接',()=>{
 const code='```c\n#include <stdio.h>\n  printf("hello");\n```';
 const url='studyatlas://material/'+'a'.repeat(32);
 const markdown=libraryMarkdown({categories:[{id:'local',parentId:null,name:'课堂资料'}],videos:[{id:'lesson',url,title:'课堂讲义',categoryId:'local',status:'todo',summary:code,tags:[],notes:[]}],insights:[{title:'共同点',content:'从原始资料理解概念。',sources:[{source:'S1',title:'课堂讲义',url}]}]});
 assert(markdown.includes(code));assert(markdown.includes('本地资料'));assert(!markdown.includes('studyatlas://'));
});
