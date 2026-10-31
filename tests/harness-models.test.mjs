import test from 'node:test';
import assert from 'node:assert/strict';
import {selectionKey,modelEntry,effortOptions,harnessModelFields,bindHarnessModelFields} from '../harness-models.js';
const catalog={groups:[{id:'local',name:'Local <unsafe>',models:[{id:'a/model:7b',name:'A <model>',efforts:[{id:'low'},{id:'high'}],defaultEffort:'high'}, {id:'plain',name:'Plain',efforts:[]}]}]};
test('provider and model identifiers remain separate and escaped',()=>{
 const selected={provider:'local',model:'a/model:7b',reasoningEffort:'low'};
 assert.equal(modelEntry(catalog,selectionKey(selected)).id,'a/model:7b');
 const html=harnessModelFields({configured:true,model:selected,catalog});
 assert(html.includes('Local &lt;unsafe&gt;'));assert(html.includes('A &lt;model&gt;'));assert(html.includes('value="low" selected'));
 assert(!html.includes('<model>'));
 assert(harnessModelFields({configured:false}).includes('disabled'));
 assert(effortOptions({efforts:[]}).includes('由模型管理'));
});
test('switching models resets unsupported effort and disables effort on plain model',()=>{
 let onChange;const select={value:'',addEventListener:(name,fn)=>onChange=fn};const effort={value:'max',innerHTML:'',disabled:true};
 bindHarnessModelFields({elements:{namedItem:name=>name==='harnessModel'?select:effort}},catalog);
 select.value=selectionKey({provider:'local',model:'a/model:7b'});onChange();assert(effort.innerHTML.includes('value="high" selected'));assert.equal(effort.disabled,false);
 select.value=selectionKey({provider:'local',model:'plain'});onChange();assert.equal(effort.disabled,true);assert(effort.innerHTML.includes('由模型管理'));
});
