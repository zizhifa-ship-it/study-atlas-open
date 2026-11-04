import test from 'node:test';
import assert from 'node:assert/strict';
import {readLearningFile} from '../file-import.js';

test('PDF uses local extraction endpoint and retains warning and page metadata', async () => {
  const calls=[];
  const result=await readLearningFile({name:'lesson.pdf',size:100}, async(path,data)=>{calls.push({path,data});return {content:'Page text',pages:2,warning:'OCR',filename:'lesson.md'};},async()=> 'JVBERi0=');
  assert.equal(calls[0].path,'/api/material/pdf');assert.equal(calls[0].data.base64,'JVBERi0=');
  assert.equal(result.pages,2);assert.equal(result.warning,'OCR');assert.equal(result.filename,'lesson.md');
  assert.equal(result.readLocally,true);
});
test('DOCX and HTML use the local document endpoint', async () => {
  for (const name of ['notes.docx','notes.html']) {
    const calls=[];
    const result=await readLearningFile({name,size:100},async(path,data)=>{calls.push({path,data});return {content:'Local text',filename:'notes.md',readLocally:true};},async()=> 'UEs=');
    assert.equal(calls[0].path,'/api/material/document');
    assert.equal(calls[0].data.filename,name);
    assert.equal(result.content,'Local text');
    assert.equal(result.readLocally,true);
  }
});
test('oversized PDF is rejected before encoding or network; text stays literal',async()=>{
  const unexpected=()=>{throw Error('must not be called');};
  await assert.rejects(readLearningFile({name:'big.pdf',size:9*1024*1024},unexpected,unexpected),/8 MB/);
  await assert.rejects(readLearningFile({name:'program.exe',size:10},unexpected),/请选择/);
  const result=await readLearningFile({name:'code.md',size:40,text:async()=> '  code();\n\nTAIL'},unexpected);
  assert.equal(result.content,'  code();\n\nTAIL');
  assert.equal(result.readLocally,true);
});
