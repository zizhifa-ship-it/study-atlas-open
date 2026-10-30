import test from 'node:test';
import assert from 'node:assert/strict';
import {visualGuide,videoCover,assetURL} from '../video-media.js';
test('图文导学展示真实封面和画面，点击保留 B 站分 P 与时间点',()=>{
 const v={id:'v1',title:'课程<script>',url:'https://www.bilibili.com/video/BV1234567890/?p=2',knowledge:{modules:[{id:'m1',title:'地址分配'}]},visuals:{cover:'a'.repeat(64)+'.jpg',frames:[{asset:'b'.repeat(64)+'.jpg',timeSec:83,label:'原视频画面',moduleId:'m1'}]}};
 const html=visualGuide(v);assert(html.includes('p=2&amp;t=83'));assert(html.includes('1:23'));assert(html.includes('地址分配'));assert(html.includes('课程&lt;script&gt;'));assert(!html.includes('<script>'));assert.equal(videoCover(v),'/api/media/'+'a'.repeat(64)+'.jpg');
});
test('图片地址只使用平台封面与已保存的画面，不接受文件路径',()=>{
 assert.equal(assetURL('../../private'), '');
 assert.equal(videoCover({url:'https://www.youtube.com/watch?v=abcdefghijk'}),'https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg');
});
