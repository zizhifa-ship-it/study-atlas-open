import test from 'node:test';
import assert from 'node:assert/strict';
import {deepseekFields} from '../deepseek-settings.js';
test('direct API UI never returns a saved key and escapes model/deployment strings',()=>{
  const html=deepseekFields({ai:{model:'"><script>',hasApiKey:true,apiKey:'must-not-render'},deployment:{mode:'private-server',message:'<private server>'}});
  assert(!html.includes('must-not-render'));assert(!html.includes('<script>'));
  assert(html.includes('&lt;private server&gt;'));assert(html.includes('data-deepseek-check'));
});
