import test from 'node:test';
import assert from 'node:assert/strict';
import {DirectAI,splitText,validateNotes} from '../browser/ai.js';
import {importLibrary,sourceURL} from '../browser/library.js';
const cornell={cues:['What does IP solve?'],summary:'IP identifies a destination for network routing. [S1]'};
const notes=()=>({title:'Network basics',category:'Networking',tags:['IP'],summary:'IP provides network addressing. [S1]',cornell,overview:'Understand addressing and routing.',modules:[{title:'IP addressing',objective:'Explain addressing',notes:'IP addresses identify network interfaces. [S1]',cornell,prerequisites:[],concepts:[{name:'IP',explanation:'Network addressing'}],examples:[],pitfalls:[],questions:[{question:'What is IP used for?',answer:'Network addressing.'}],evidence:['IP provides network addressing.']}]});
test('direct browser API uses fixed official host, bearer header, no cookies and no redirects',async()=>{
  const calls=[];const ai=new DirectAI({fetcher:async(url,options)=>{calls.push({url,options});return Response.json({data:[{id:'account-model'}]});}});ai.configure('test-key-not-for-public-use','account-model');
  assert.deepEqual(await ai.models(),['account-model']);assert.equal(calls[0].url,'https://api.deepseek.com/models');assert.equal(calls[0].options.headers.Authorization,'Bearer test-key-not-for-public-use');assert.equal(calls[0].options.credentials,'omit');assert.equal(calls[0].options.redirect,'error');assert(!calls[0].url.includes('test-key'));
});
test('notes cache only stores validated output, reuses results, and isolates models',async()=>{
  const cache=new Map(),calls=[];const ai=new DirectAI({readCache:async k=>cache.get(k),writeCache:async(k,v)=>cache.set(k,v),fetcher:async(url,o)=>{calls.push(JSON.parse(o.body));return Response.json({choices:[{finish_reason:'stop',message:{content:JSON.stringify(notes())}}]});}});ai.configure('test-key','model-a');
  const source='IP provides network addressing for routers and hosts.';await ai.notes(source,'English');await ai.notes(source,'English');assert.equal(calls.length,1);assert(!JSON.stringify([...cache.values()]).includes('test-key'));ai.model='model-b';await ai.notes(source,'English');assert.equal(calls.length,2);
});
test('long-source splitting preserves every character and tail; bounded calls are resumable',async()=>{
  const source='A'.repeat(12000)+'B'.repeat(12000)+'FINAL_END';assert.equal(splitText(source).join(''),source);const cache=new Map();let count=0;
  const ai=new DirectAI({readCache:async k=>cache.get(k),writeCache:async(k,v)=>cache.set(k,v),fetcher:async(url,o)=>{count++;if(count===2)return new Response('{}',{status:429});const prompt=JSON.parse(o.body).messages[1].content;assert(prompt.length<12500);return Response.json({choices:[{finish_reason:'stop',message:{content:prompt.slice(-30)}}]});}});ai.configure('test-key','model-a');
  await assert.rejects(ai.prepare(source),/429/);assert.equal(count,2);const result=await ai.prepare(source);assert(result.includes('FINAL_END'));assert.equal(count,4);
});
test('incomplete response, missing Cornell cues and title-only input cannot become notes',async()=>{
  const bad=notes();bad.cornell={cues:[],summary:'Missing prompt cues'};assert.throws(()=>validateNotes(bad),/康奈尔/);
  let calls=0;const ai=new DirectAI({fetcher:async()=>{calls++;return Response.json({choices:[{finish_reason:'length',message:{content:'partial'}}]});}});ai.configure('test-key','model-a');await assert.rejects(ai.notes('title','English'),/实际资料/);assert.equal(calls,0);await assert.rejects(ai.completion('actual source'),/上限/);assert.equal(calls,1);
});
test('backup import drops credentials and executable links; preserves notes and original source',()=>{
  const source='Actual source with important final conclusion.';const imported=importLibrary({schemaVersion:1,apiKey:'never-import-key',categories:[],videos:[{id:'abc',title:'A course',url:'https://www.youtube.com/watch?v=abcdefghijk',transcript:source,summary:'Existing summary',notes:[{text:'My annotation'}],knowledge:{...notes(),review:{issues:[]}}}]});
  assert(!JSON.stringify(imported).includes('never-import-key'));assert.equal(imported.videos[0].transcript,source);assert.equal(imported.videos[0].notes[0].text,'My annotation');assert.equal(imported.videos[0].knowledge.modules.length,1);assert.throws(()=>sourceURL('javascript:alert(1)','abc'),/http/);
});


// Local retrieval covers later chapters without sending the full source.
import {relevantContext} from '../browser/retrieval.js';
test('question retrieval finds a tail-only concept within a fixed token budget',()=>{
 const source='网络基础内容。'.repeat(3000)+'最后一章：量子密钥用于专用安全实验。';
 const selected=relevantContext({transcript:source},'量子密钥是什么？');
 assert(selected.includes('量子密钥'));assert(selected.length<=10000);
});
