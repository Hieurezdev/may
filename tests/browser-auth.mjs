import assert from 'node:assert/strict';
import {chromium} from 'playwright-core';
const baseURL=process.env.MAY_TEST_BASE_URL||'http://127.0.0.1:8767';
const browser=await chromium.launch({executablePath:process.env.MAY_BROWSER_PATH||'/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',headless:true});
try {
 const page=await browser.newPage();
 await page.goto(baseURL+'/#/shop');
 await page.locator('#sort-products').waitFor();
 const response=await page.request.post(baseURL+'/api/auth/login',{data:{email:'merchant@may.local',password:'Wrong-password'}});
 assert.equal(response.status(),401);
 assert.equal((await page.request.get(baseURL+'/api/admin/products')).status(),401);
 const login=await page.request.post(baseURL+'/api/auth/login',{data:{email:'merchant@may.local',password:'MayDemo2026!'}});
 assert.equal(login.status(),200);
 assert.equal((await page.request.get(baseURL+'/api/admin/products')).status(),200);
 await page.request.post(baseURL+'/api/auth/logout');
 assert.equal((await page.request.get(baseURL+'/api/admin/products')).status(),401);
 console.log('Browser authentication: guest browsing, failed login, role access and logout passed.');
}finally{await browser.close();}
