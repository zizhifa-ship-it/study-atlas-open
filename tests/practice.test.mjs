import test from 'node:test';
import assert from 'node:assert/strict';
import {practicePage, mergePracticeAttempts, practicePool} from '../practice.js';
import {libraryMarkdown} from '../exports.js';

test('合并备份映射课程编号并保留已有作答，不重复导入',()=>{
  const original={attempts:[{id:'a',videoId:'local',answer:'保留当前回答'}]};
  const incoming={attempts:[{id:'a',videoId:'old',answer:'旧备份回答'},{id:'b',videoId:'old',sourceHash:'stable-source'},{id:'c',videoId:'missing'}]};
  const merged=mergePracticeAttempts(original,incoming,new Map([['old','local']]));
  assert.equal(merged.attempts.length,2);assert.equal(merged.attempts[0].answer,'保留当前回答');
  assert.equal(merged.attempts[1].videoId,'local');assert.equal(merged.attempts[1].sourceHash,'stable-source');
  assert.equal(original.attempts.length,1);
});

test('学生答案、AI 反馈和课程名称都不能注入页面 HTML',()=>{
  const unsafe='<img src=x onerror=alert(1)>';
  const card={videoId:'v',questionId:'q',videoTitle:unsafe,moduleTitle:'协议',question:unsafe,isNew:true,isDue:false,isWeak:false,url:'https://example.com',referenceAnswer:unsafe,
    lastAttempt:{verdict:'partial',score:60,feedback:unsafe,missingPoints:[unsafe],suggestedAnswer:unsafe,evidence:unsafe,streak:0,dueAt:'2026-10-29T00:00:00Z'}};
  const data={counts:{due:0,new:1,weak:1,recent:0},items:[card],history:[]};
  const ui={mode:'today',course:'',current:null,skipped:[],drafts:{'v:q':unsafe},revealed:{'v:q':true}};
  const html=practicePage(data,{videos:[]},ui);
  assert(!html.includes('<img src=x'));assert(html.includes('&lt;img'));
  assert.equal(practicePool(data,{...ui,mode:'weak'}).length,0);
  assert.equal(practicePool(data,{...ui,mode:'all'}).length,1);
});

test('Markdown 保留详尽模块、自查和自测记录，排除连接凭据与完整字幕',()=>{
  const lib={categories:[{id:'c',name:'分类',parentId:null}],videos:[{id:'v',title:'原始标题',aiTitle:'中文课程',url:'https://example.com',categoryId:'c',author:'讲师',status:'learning',tags:[],notes:[],transcript:'full-private-transcript',
    knowledge:{overview:'知识脉络',modules:[{title:'IP 与 DHCP',objective:'理解寻址',prerequisites:[],notes:'## 定义\n完整详解 [S1]',concepts:[{name:'IP',explanation:'逻辑地址'}],examples:['课程中的例子'],pitfalls:['混淆点'],questions:[{question:'为什么需要 IP？',answer:'跨网络寻址'}],evidence:['原文摘录']}],review:{summary:'实际自查结果',issues:[{resolved:false,problem:'仍有疑问',suggestion:'回到原文'}]}}}],
    insights:[],learning:{attempts:[{question:'为什么需要 IP？',createdAt:'2026-10-28',score:50,answer:'个人作答',feedback:'具体反馈',suggestedAnswer:'参考改写',dueAt:'2026-10-29'}]},apiKey:'private-api-key'};
  const output=libraryMarkdown(lib);
  for(const term of ['中文课程','知识脉络','## 定义','完整详解','逻辑地址','跨网络寻址','原文摘录','实际自查结果','待核对','个人作答','具体反馈'])assert(output.includes(term),term);
  assert(!output.includes('private-api-key'));assert(!output.includes('full-private-transcript'));
});
