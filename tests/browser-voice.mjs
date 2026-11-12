import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';

const baseURL = process.env.MAY_TEST_BASE_URL || 'http://127.0.0.1:8000';

// Deterministic synthetic audio keeps this UI test independent of paid services.
const sampleRate=16000, samples=sampleRate*2;
const wave=Buffer.alloc(44+samples*2);
wave.write('RIFF',0);wave.writeUInt32LE(wave.length-8,4);wave.write('WAVEfmt ',8);
wave.writeUInt32LE(16,16);wave.writeUInt16LE(1,20);wave.writeUInt16LE(1,22);
wave.writeUInt32LE(sampleRate,24);wave.writeUInt32LE(sampleRate*2,28);
wave.writeUInt16LE(2,32);wave.writeUInt16LE(16,34);wave.write('data',36);wave.writeUInt32LE(samples*2,40);
for(let i=0;i<samples;i++)wave.writeInt16LE(Math.round(Math.sin(i/sampleRate*2*Math.PI*330)*9000),44+i*2);
const browser=await chromium.launch({executablePath:'/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',headless:true,args:['--enable-unsafe-swiftshader']});
try {
  const page=await browser.newPage({viewport:{width:1440,height:1050}});
  const login=await page.request.post(baseURL+'/api/auth/login',{data:{email:'merchant@may.local',password:'MayDemo2026!'}});
  assert.equal(login.status(),200);
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  let speechRequests=0;
  await page.route('**/api/chat',route=>{
    if(route.request().method()==='POST')return route.fulfill({json:{content:'Chào bạn, Ami gợi ý áo len CANIFA 149.000 đồng.',product_ids:['6te24w007'],message_id:999,mode:'qwen-proxy'}});
    return route.continue();
  });
  await page.route('**/api/chat/999/speech',route=>{speechRequests++;return route.fulfill({status:200,contentType:'audio/wav',body:wave});});
  await page.goto(baseURL+'/#/shop');
  await page.locator('.chat-launcher').click();
  await page.frameLocator('#ami-avatar').locator('#ami-loading').waitFor({state:'hidden',timeout:60000});
  const frame=page.frames().find(frame=>frame.url().endsWith('/ami-assets/may-avatar.html'));
  await frame.evaluate(()=>{
    window.testMouthSamples=[];
    window.addEventListener('message',event=>{if(event.data?.type==='may-ami-mouth')window.testMouthSamples.push(event.data.value);});
  });
  await page.locator('#auto-read').check();
  await page.locator('#chat-input').fill('Tư vấn áo len dưới 400 nghìn');
  await page.locator('#chat-form [type="submit"]').click();
  await page.locator('#ami-stage.is-speaking').waitFor({state:'visible'});
  await frame.waitForFunction(()=>window.testMouthSamples.some(value=>value>0.1));
  await page.locator('[data-action="stop-speaking"]').click();
  await page.locator('#ami-stage.is-speaking').waitFor({state:'hidden'});
  await page.locator('[data-action="speak-message"][data-id="999"]').click();
  await page.locator('#ami-stage.is-speaking').waitFor({state:'visible'});
  assert.equal(speechRequests,1,'Replaying a response should reuse decoded audio');
  await page.locator('[data-action="stop-speaking"]').click();
  await page.locator('[data-action="chat-voice"]').click();
  await page.locator('#record-audio').waitFor({state:'visible'});
  await page.locator('[data-action="close-modal"]').click();
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:'/tmp/may-ami-mobile.png'});
  assert.deepEqual(errors,[]);
  console.log('Ami: spoken reply, amplitude-driven mouth, stop, cached replay, microphone dialog and mobile layout passed.');
} finally {await browser.close();}
