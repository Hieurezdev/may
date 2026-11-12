import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';

const baseURL = process.env.MAY_TEST_BASE_URL || 'http://127.0.0.1:8000';

const browser = await chromium.launch({
  executablePath: '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
  headless: true,
  args: ['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--enable-unsafe-swiftshader'],
});
try {
  const page = await browser.newPage({viewport:{width:1440,height:1050},acceptDownloads:true});
  const login = await page.request.post(baseURL + '/api/auth/login', {data:{email:'merchant@may.local',password:'MayDemo2026!'}});
  assert.equal(login.status(),200);
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(baseURL + '/#/try-on');
  await page.locator('#start-camera').click();
  await page.locator('#camera-badge.camera-live').waitFor({state:'visible'});
  const tracks = await page.evaluateHandle(()=>document.querySelector('#tryon-video').srcObject.getTracks());
  const before=await page.locator('#tryon-canvas').evaluate(canvas=>canvas.toDataURL());
  await page.waitForTimeout(350);
  const after=await page.locator('#tryon-canvas').evaluate(canvas=>canvas.toDataURL());
  assert.notEqual(before,after,'Live camera frames should change');
  await page.screenshot({path:'/tmp/may-camera-live.png',fullPage:true});
  const download=page.waitForEvent('download');
  await page.locator('#download-tryon').click();
  await (await download).saveAs('/tmp/may-camera-capture.png');
  await page.locator('#toggle-camera').click();
  assert.equal(await tracks.evaluate(list=>list.every(track=>track.readyState==='ended')),true);
  await page.locator('#camera-badge.camera-live').waitFor({state:'hidden'});
  await page.locator('#toggle-camera').click();
  await page.locator('#camera-badge.camera-live').waitFor({state:'visible'});
  const secondTracks=await page.evaluateHandle(()=>document.querySelector('#tryon-video').srcObject.getTracks());
  await page.locator('nav [data-nav="/shop"]').click();
  await page.locator('#sort-products').waitFor({state:'visible'});
  assert.equal(await secondTracks.evaluate(list=>list.every(track=>track.readyState==='ended')),true);
  console.log('Camera: changing realtime frames, screenshot, stop and route cleanup passed.');
  await page.locator('.chat-launcher').click();
  await page.frameLocator('#ami-avatar').locator('#ami-loading').waitFor({state:'hidden',timeout:60000});
  await page.screenshot({path:'/tmp/may-ami-chat.png'});
  console.log('Ami: Live2D loaded in chat.');
  assert.deepEqual(errors,[]);
} finally {await browser.close();}
