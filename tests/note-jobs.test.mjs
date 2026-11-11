import test from 'node:test';
import assert from 'node:assert/strict';
import {NoteJobs,duplicateSource} from '../browser/jobs.js';
import {DirectAI} from '../browser/ai.js';
import {memoryPoints,nextRecall} from '../memory-cards.js';
const clone=value=>structuredClone(value);
const course=()=>({id:'v1',title:'课程',transcript:'IP provides addressing and DHCP assigns addresses.',summary:'',notes:[],noteLanguage:'简体中文'});
const result=()=>({title:'寻址',category:'网络',tags:['IP'],summary:'IP负责寻址。',cornell:{cues:['IP做什么？'],summary:'记住寻址。'},overview:'理解地址。',modules:[{id:'m1',title:'IP',objective:'解释寻址',notes:'IP负责寻址。',concepts:[],questions:[],evidence:[]}],material:'IP provides addressing and DHCP assigns addresses.'});
function fixture(ai){let library={schemaVersion:1,revision:0,videos:[course()],categories:[],papers:[],insights:[]};const jobs=new Map();const storage={ai,readLibrary:async()=>clone(library),saveLibrary:async(next,rev,job)=>{assert.equal(rev,library.revision);library=clone({...next,revision:rev+1});if(job)jobs.set(job.videoId,clone(job));},getJob:async id=>clone(jobs.get(id)),setJob:async job=>jobs.set(job.videoId,clone(job))};return {storage,jobs,get library(){return library;},coordinator:()=>new NoteJobs(storage)};}
test('audit failure and a new page continue audit only; saved notes and annotations survive',async()=>{
 let notes=0,reviews=0;const ai={model:'a',notes:async()=>{notes++;return result();},review:async()=>{reviews++;throw Error('audit connection failed');}};const f=fixture(ai);
 await assert.rejects(f.coordinator().run('v1'),/audit connection/);assert.equal(f.library.videos[0].summary,'IP负责寻址。');assert.equal(f.jobs.get('v1').stage,'audit');
 f.library.videos[0].notes.push({id:'manual',text:'我的理解'});ai.notes=async()=>assert.fail('must not regenerate');ai.review=async()=>{reviews++;return {status:'reviewed',summary:'已核对',issues:[],corrections:[],checkedAt:'now'};};
 await f.coordinator().run('v1');assert.equal(notes,1);assert.equal(reviews,2);assert.equal(f.jobs.get('v1').status,'done');assert.equal(f.library.videos[0].notes[0].text,'我的理解');
});
test('ready notes are read without another model call and identical sources resolve to one record',async()=>{
 const ai={notes:async()=>assert.fail('ready notes must not call model')};const f=fixture(ai);Object.assign(f.library.videos[0],{summary:'已保存',knowledge:{modules:[{}]}});
 assert.deepEqual(await f.coordinator().run('v1'),{reused:true});assert.equal(duplicateSource(f.library.videos,f.library.videos[0].transcript,'').id,'v1');
});
test('rapid duplicate actions share one generation and one audit',async()=>{
 let notes=0,release;const gate=new Promise(r=>release=r);const ai={model:'a',notes:async()=>{notes++;await gate;return result();},review:async()=>({status:'reviewed',summary:'核对完成',issues:[],corrections:[]})};const f=fixture(ai),coordinator=f.coordinator();const first=coordinator.run('v1'),second=coordinator.run('v1');release();await Promise.all([first,second]);assert.equal(notes,1);assert.equal(f.jobs.get('v1').status,'done');
});
test('source changed during generation never overwrites newer user content',async()=>{
 const ai={model:'a',notes:async()=>{f.library.videos[0].transcript='A new user edited source with sufficient details.';return result();}};const f=fixture(ai);await assert.rejects(f.coordinator().run('v1'),/资料或笔记/);assert.equal(f.library.videos[0].summary,'');assert(f.jobs.get('v1').result);assert(f.library.videos[0].transcript.startsWith('A new'));
});
test('unknown network result is not automatically sent or charged again',async()=>{
 const requests=new Map();let calls=0;const ai=new DirectAI({readRequest:async k=>requests.get(k),writeRequest:async(k,v)=>requests.set(k,v),claimRequest:async k=>{const old=requests.get(k);if(old?.status==='pending'||old?.status==='responded')return {claimed:false,record:old};const record={status:'pending'};requests.set(k,record);return {claimed:true,record};},fetcher:async()=>{calls++;throw TypeError('connection lost');}});ai.configure('test-only-key','model-a');await assert.rejects(ai.cached('source',x=>x),e=>e.code==='RESULT_UNCERTAIN');await assert.rejects(ai.cached('source',x=>x),e=>e.code==='RESULT_UNCERTAIN');assert.equal(calls,1);
});
test('an arrived response survives cache failure and is reused without resending',async()=>{
 const requests=new Map();let calls=0;const ai=new DirectAI({readRequest:async k=>requests.get(k),writeRequest:async(k,v)=>requests.set(k,v),claimRequest:async k=>{const r=requests.get(k);return r?{claimed:false,record:r}:{claimed:true,record:{status:'pending'}};},writeCache:async()=>{throw Error('cache full');},fetcher:async()=>{calls++;return Response.json({choices:[{finish_reason:'stop',message:{content:'saved response'}}]});}});ai.configure('test-only-key','model-a');assert.equal(await ai.cached('source',x=>x),'saved response');assert.equal(await ai.cached('source',x=>x),'saved response');assert.equal(calls,1);
});
test('recall cards stay small, keep original text intact and schedule self-assessment once',()=>{
 const module={notes:'原文'.repeat(1000),concepts:Array.from({length:8},(_,i)=>({name:'概念'+i,explanation:'说明'.repeat(150)}))};const before=clone(module);const points=memoryPoints(module);assert.equal(points.length,3);assert(points.every(x=>x.length<=161));assert.deepEqual(module,before);
 const first=nextRecall(null,'remember',100000);assert.equal(first.nextAt,100000+86400000);assert.deepEqual(nextRecall(first,'remember',100001),first);assert.equal(nextRecall(first,'again',200000).nextAt,800000);
});
test('missing key keeps a queued job which automatically continues after connection',async()=>{
 const f=fixture({notes:async()=>{const error=Error('connect first');error.code='MISSING_KEY';throw error;}});await f.coordinator().queue(f.library.videos[0]);await assert.rejects(f.coordinator().run('v1'),e=>e.code==='MISSING_KEY');assert.equal(f.jobs.get('v1').status,'queued');let count=0;f.storage.ai={model:'a',notes:async()=>{count++;return result();},review:async()=>({status:'reviewed',summary:'done',issues:[]})};await f.coordinator().run('v1');await f.coordinator().run('v1');assert.equal(count,1);assert.equal(f.jobs.get('v1').status,'done');
});
test('format repair is bounded and does not resend original source',async()=>{
 const prompts=[],cache=new Map(),requests=new Map(),source='SOURCE_ONLY_SENT_ONCE: IP provides addressing for hosts.';const full={...result(),modules:[{...result().modules[0],cornell:{cues:['IP?'],summary:'Addressing'}}]};let calls=0;
 const ai=new DirectAI({readRequest:async k=>requests.get(k),writeRequest:async(k,v)=>requests.set(k,v),readCache:async k=>cache.get(k),writeCache:async(k,v)=>cache.set(k,v),fetcher:async(url,o)=>{prompts.push(JSON.parse(o.body).messages[1].content);calls++;return Response.json({choices:[{finish_reason:'stop',message:{content:calls===1?'```json\n{"title":"IP", "summary":"Addressing",}\n```':JSON.stringify(full)}}]});}});ai.configure('test-key','model-a');await ai.notes(source,'English');await ai.notes(source,'English');assert.equal(calls,2);assert(prompts[0].includes('SOURCE_ONLY_SENT_ONCE'));assert(!prompts[1].includes('SOURCE_ONLY_SENT_ONCE'));assert(prompts[1].includes('只修复'));
});
