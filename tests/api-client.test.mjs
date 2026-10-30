import test from 'node:test';
import assert from 'node:assert/strict';
import {createApiFetch} from '../api-client.js';

test('写入前取得令牌，多次写入复用内存令牌，令牌不进入 URL',async()=>{
  const calls=[];const api=createApiFetch(async(url,options)=>{calls.push({url,options});return new Response(JSON.stringify(url==='/api/security'?{token:'a'.repeat(64)}:{ok:true}));});
  await api('/api/library',{method:'PUT',body:'{}'});await api('/api/import',{method:'POST',body:'{}'});
  assert.equal(calls.filter(x=>x.url==='/api/security').length,1);
  assert.equal(calls[1].options.headers.get('X-Study-Atlas-Token'),'a'.repeat(64));assert(!calls.some(x=>x.url.includes('a'.repeat(64))));
  await assert.rejects(api('https://other.example/collect',{method:'POST'}));
});
test('只在明确的令牌失效 403 后安全刷新一次，不重试计费错误',async()=>{
  let boot=0,writes=0;const api=createApiFetch(async(url)=>{
    if(url==='/api/security'){boot++;return Response.json({token:String(boot).repeat(64)});}
    writes++;return writes===1?Response.json({code:'security_token'},{status:403}):Response.json({error:'upstream failed'},{status:500});
  });
  const response=await api('/api/import',{method:'POST',body:'{}'});assert.equal(response.status,500);assert.equal(boot,2);assert.equal(writes,2);
});
