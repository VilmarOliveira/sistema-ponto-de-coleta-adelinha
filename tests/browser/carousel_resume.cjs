/* Isolated fixture server; virtual clock makes timing assertions exact. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const BASE='http://127.0.0.1:5001';
const results=[];
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
 try{
  for(const mobile of [false,true]){
   const context=await browser.newContext({viewport:{width:mobile?390:1440,height:900},isMobile:mobile,hasTouch:mobile});
   const page=await context.newPage();await page.clock.install({time:new Date('2026-10-27T12:00:00Z')});await page.clock.pauseAt(new Date('2026-10-27T12:00:00Z'));
   await page.goto(BASE+'/');await page.mouse.move(1,899);
   const index=()=>page.locator('[data-slide]').evaluateAll(slides=>slides.findIndex(el=>el.classList.contains('active')));
   const tick=ms=>page.clock.runFor(ms);
   const event=(target,name)=>page.evaluate(({target,name})=>(target==='window'?window:document).dispatchEvent(new Event(name)),{target,name});
   const fullDelay=async(before)=>{await tick(2999);assert.equal(await index(),before);await tick(1);assert.equal(await index(),(before+1)%3);};
   assert.equal(await page.locator('[data-slide]').count(),3);
   assert.equal(await page.locator('[data-slide-to]').count(),3);
   assert.equal(await page.getByRole('button',{name:/Pausar|Anterior|Próximo/}).count(),0);
   await fullDelay(await index());results.push({mobile,case:'3000ms'});
   // Repeated lifecycle notifications must replace, never multiply, timers.
   let before=await index();for(let i=0;i<10;i++)await event('window','pageshow');await fullDelay(before);
   await tick(6000);assert.equal(await index(),before);results.push({mobile,case:'no duplicate timers'});
   before=await index();await tick(1200);
   await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'));});
   await tick(120000);assert.equal(await index(),before);
   await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'));});
   await fullDelay(before);results.push({mobile,case:'hidden tab and full resume delay'});
   for(const [stop,start] of [['blur','focus'],['pagehide','pageshow'],['freeze','resume']]){
    before=await index();const target=stop==='freeze'?'document':'window';await event(target,stop);await tick(60000);assert.equal(await index(),before);await event(target,start);await fullDelay(before);
    results.push({mobile,case:stop+'/'+start});
   }
   // Overdue callback without lifecycle events must not advance immediately.
   before=await index();await page.clock.fastForward(120000);assert.equal(await index(),before);await fullDelay(before);results.push({mobile,case:'overdue timer fallback'});
   if(!mobile){
    await page.locator('[data-carousel]').hover();before=await index();await tick(9000);assert.equal(await index(),before);
    await page.mouse.move(1,899);await fullDelay(before);results.push({mobile,case:'hover'});
    const dot=page.locator('[data-slide-to]').nth(1);await dot.focus();before=await index();await tick(9000);assert.equal(await index(),before);
    await page.locator('.brand').focus();await fullDelay(before);results.push({mobile,case:'desktop focus'});
    // A stale hover flag is corrected by any subsequent mouse move.
    await page.locator('[data-carousel]').dispatchEvent('pointerenter',{pointerType:'mouse'});before=await index();await tick(4000);assert.equal(await index(),before);
    await page.mouse.move(2,898);await fullDelay(before);results.push({mobile,case:'lost pointerleave recovery'});
   }else{
    const touch=async(type,x,touches=1)=>page.locator('.banner-slides').evaluate((el,{type,x,touches})=>{
     const rect=el.getBoundingClientRect();const point=new Touch({identifier:1,target:el,clientX:x,clientY:rect.top+30});
     el.dispatchEvent(new TouchEvent(type,{bubbles:true,touches:touches?[point]:[],changedTouches:[point]}));
    },{type,x,touches});
    await touch('touchstart',250);before=await index();await tick(9000);assert.equal(await index(),before);await touch('touchend',250,0);await fullDelay(before);results.push({mobile,case:'touch hold and release'});
    await touch('touchstart',250);before=await index();await touch('touchend',100,0);assert.equal(await index(),(before+1)%3);await fullDelay(await index());results.push({mobile,case:'swipe'});
    await touch('touchstart',250);before=await index();await event('window','blur');await tick(60000);await event('window','focus');await fullDelay(before);results.push({mobile,case:'interrupted touch cleared on unlock'});
    await touch('touchstart',250);before=await index();await touch('touchcancel',250,0);await fullDelay(before);results.push({mobile,case:'touchcancel'});
    await page.locator('[data-slide-to]').nth(1).tap();assert.equal(await index(),1);await fullDelay(1);results.push({mobile,case:'mobile dot does not stick paused'});
   }
   await page.emulateMedia({reducedMotion:'reduce'});before=await index();await tick(90000);assert.equal(await index(),before);
   await page.locator('[data-slide-to]').nth(2).click();assert.equal(await index(),2);
   await page.keyboard.press('ArrowLeft');assert.equal(await index(),1);
   await page.locator('.brand').focus();await page.mouse.move(1,899);await page.emulateMedia({reducedMotion:'no-preference'});await tick(32);await page.waitForTimeout(100);await event('window','focus');await fullDelay(1);results.push({mobile,case:'reduced motion and manual navigation'});
   await context.close();
  }
  // Actually suspend JavaScript with CDP; visible headless pages ignore
  // Page.setWebLifecycleState(frozen), so use the debugger for the late tick.
  const context=await browser.newContext();const page=await context.newPage();await page.goto(BASE+'/');await page.mouse.move(1,899);
  const cdp=await context.newCDPSession(page);const before=await page.locator('[data-slide].active').getAttribute('aria-label');
  await cdp.send('Debugger.enable');await cdp.send('Debugger.pause');await new Promise(r=>setTimeout(r,3500));await cdp.send('Debugger.resume');await cdp.send('Debugger.disable');
  assert.equal(await page.locator('[data-slide].active').getAttribute('aria-label'),before);
  await page.waitForTimeout(2000);assert.equal(await page.locator('[data-slide].active').getAttribute('aria-label'),before);
  await page.waitForTimeout(1300);assert.notEqual(await page.locator('[data-slide].active').getAttribute('aria-label'),before);results.push({case:'Chromium JavaScript suspension via CDP debugger'});
  // Serve the actual homepage with one active slide, as configured by admin.
  await page.route(BASE+'/',async route=>{const response=await route.fetch();let html=await response.text();html=html.replace(/<figure class="banner-slide"[\s\S]*?<\/figure>/g,'').replace(/<div class="banner-controls">[\s\S]*?<\/div>/,'');await route.fulfill({response,body:html});});
  await page.clock.install();await page.goto(BASE+'/');await page.clock.fastForward(60000);assert.equal(await page.locator('[data-slide]').count(),1);assert.equal(await page.locator('[data-slide].active').count(),1);assert.equal(await page.locator('[data-slide-to]').count(),0);results.push({case:'single banner fixed'});
  await context.close();fs.mkdirSync('/tmp/adelinha-carousel-results',{recursive:true});fs.writeFileSync('/tmp/adelinha-carousel-results/report.json',JSON.stringify({passed:true,results},null,2));
  console.log(`PASS: ${results.length} carousel timing/lifecycle/interaction scenarios.`);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
