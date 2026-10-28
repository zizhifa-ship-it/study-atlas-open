// 可选浏览器测试：需自行安装 playwright 和 chromium；正式应用无此依赖。
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdir,readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root=fileURLToPath(new URL('../',import.meta.url));
const artifacts=process.env.STUDY_ATLAS_TEST_ARTIFACTS || root+'.browser-test';
const fixture=spawn(process.env.PYTHON_EXECUTABLE || 'python3',['tests/browser_fixture.py'],{cwd:root,stdio:['ignore','pipe','pipe']});
fixture.stderr.on('data',chunk=>process.stderr.write(chunk));
const base=await new Promise((resolve,reject)=>{
  let buffer='';const timeout=setTimeout(()=>reject(new Error('临时测试服务没有启动')),10000);
  fixture.stdout.on('data',chunk=>{buffer+=chunk;const match=buffer.match(/TEST_URL=(http:\/\/127\.0\.0\.1:\d+)/);if(match){clearTimeout(timeout);resolve(match[1]);}});
  fixture.once('exit',code=>{clearTimeout(timeout);reject(new Error('临时服务退出：'+code));});
});
let browser;
try {
  browser=await chromium.launch({headless:true,...(process.env.STUDY_ATLAS_TEST_BROWSER ? {executablePath:process.env.STUDY_ATLAS_TEST_BROWSER}: {})});const page=await browser.newPage({viewport:{width:1365,height:1000}});
  page.setDefaultTimeout(10000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/#practice');await page.getByRole('heading',{name:'复习与自测',exact:true}).waitFor();
  await page.getByLabel('你的理解',{exact:true}).fill('不知道');
  await page.getByRole('button',{name:'提交给 AI 批改',exact:true}).click();
  await page.getByRole('status',{name:'AI 批改结果',exact:true}).getByText('15 / 100',{exact:true}).waitFor();
  await page.getByRole('tab',{name:'错题本',exact:true}).click();
  assert.equal(await page.locator('.practice-question').count(),1);
  await page.getByLabel('你的理解',{exact:true}).fill('DHCP 会自动为设备分配 IP 地址。');
  await page.getByRole('button',{name:'提交给 AI 批改',exact:true}).click();
  await page.getByRole('status',{name:'AI 批改结果',exact:true}).getByText('90 / 100',{exact:true}).waitFor();
  assert.equal(await page.locator('.practice-question').count(),0);
  await page.getByRole('tab',{name:'作答记录',exact:true}).click();assert.equal(await page.locator('.practice-history').count(),2);
  await page.reload();await page.getByRole('tab',{name:'作答记录',exact:true}).click();assert.equal(await page.locator('.practice-history').count(),2);
  await page.getByRole('tab',{name:'待复习与新题',exact:true}).click();
  await page.getByLabel('你的理解',{exact:true}).fill('未提交的草稿');await page.getByRole('tab',{name:'全部题目',exact:true}).click();
  await page.getByRole('tab',{name:'待复习与新题',exact:true}).click();assert.equal(await page.getByLabel('你的理解',{exact:true}).inputValue(),'未提交的草稿');
  await mkdir(artifacts,{recursive:true});await page.screenshot({path:artifacts+'/desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'手机布局不应横向溢出');
  await page.screenshot({path:artifacts+'/mobile.png',fullPage:true});
  await page.getByRole('button',{name:'回到模块详解 →',exact:true}).click();
  await page.locator('#module-m1').waitFor();
  assert(await page.locator('#module-m1').evaluate(el=>Math.abs(el.getBoundingClientRect().top)<100),'回到资料时应定位到对应模块');
  await page.locator('#module-m1').getByRole('button',{name:'开始本模块自测',exact:true}).click();
  await page.getByRole('heading',{name:'复习与自测',exact:true}).waitFor();
  await page.getByRole('button',{name:'备份学习记录',exact:true}).click();
  const download=page.waitForEvent('download',{timeout:10000});await page.getByRole('button',{name:'导出 JSON',exact:true}).click();
  const backup=JSON.parse(await readFile(await (await download).path(),'utf8'));
  assert.equal(backup.learning.attempts.length,2);assert.equal(backup.videos[0].knowledge.modules.length,1);
  assert.equal(errors.length,0,errors.join('\n'));
  console.log('浏览器验证通过：答题 → 批改 → 错题 → 再答 → 保存 → 刷新 → 草稿 → 手机布局 → JSON 备份。');
} finally {
  await browser?.close();fixture.kill('SIGINT');
}
