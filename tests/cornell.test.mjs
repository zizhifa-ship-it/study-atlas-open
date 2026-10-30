import test from 'node:test';
import assert from 'node:assert/strict';
import {cornellSheet,procedureBlock} from '../cornell.js';
test('普通笔记具有提示、记录和底部归纳，旧版问答也能显示',()=>{
  const html=cornellSheet({notes:'原有记录',questions:[{question:'为什么需要 IP？',answer:'IP 用于跨网络寻址。'}]},'<p>课堂正文</p>');
  for(const text of ['提示与问题','课堂记录','归纳小结','为什么需要 IP','IP 用于跨网络寻址'])assert(html.includes(text));
  assert(html.indexOf('cornell-summary')>html.indexOf('cornell-notes'));
});
test('实验流程显示操作、预期现象和验证方法，并转义资料中的 HTML',()=>{
  const html=procedureBlock({goal:'验证网络',requirements:['工具'],steps:[{action:'<script>alert(1)</script>',expected:'收到响应',verify:'检查返回值'}],conclusion:'限定资料范围'});
  assert(html.includes('预期现象'));assert(html.includes('验证方法'));assert(html.includes('&lt;script&gt;'));assert(!html.includes('<script>'));
});
