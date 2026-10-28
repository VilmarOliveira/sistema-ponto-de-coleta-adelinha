const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const BASE='http://127.0.0.1:5001';
const widths=[320,360,390,430,768,1024,1440];
const out='/tmp/adelinha-stores-results';fs.mkdirSync(out,{recursive:true});
const cases=[];
const frame=page=>page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
async function login(page,role){
  if(role==='public')return;
  await page.goto(BASE+(role==='client'?'/cliente/login':'/login'));
  await page.locator(role==='client'?'[name=cpf]':'[name=user]').fill(role==='client'?'52998224725':'admin');
  await page.locator('[name=password]').fill('responsivo-local-123');
  await Promise.all([page.waitForURL(role==='client'?'**/cliente':'**/painel'),page.locator('form button').filter({hasText:'Entrar'}).click()]);
}
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 try{
  for(const width of widths)for(const role of ['public','client','admin']){
   const context=await browser.newContext({viewport:{width,height:900},isMobile:width<768,hasTouch:width<768});
   const page=await context.newPage();await login(page,role);
   for(const path of ['/', '/duvidas-frequentes','/blog',role==='public'?'/cliente/login':role==='client'?'/cliente':'/painel']){
    await page.goto(BASE+path);await page.evaluate(()=>document.fonts.ready);await frame(page);
    const cta=page.locator('.header-signup:visible');assert.equal(await cta.count(),role==='public'?1:0);
    assert.equal(await page.locator('.header-signup').count(),role==='public'?2:0);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${role} ${width} ${path}: overflow`);
    const geometry=await page.locator('.site-header').evaluate(header=>{
     const visible=el=>el&&getComputedStyle(el).display!=='none'&&el.getBoundingClientRect().width>0;
     const nodes=[header.querySelector('.brand'),header.querySelector('.signup-mobile'),header.querySelector('[data-nav-toggle]')].filter(visible);
     return nodes.map(el=>{const r=el.getBoundingClientRect();return {left:r.left,right:r.right,center:r.top+r.height/2,height:r.height};});
    });
    for(let i=1;i<geometry.length;i++){
     assert(geometry[i].left>=geometry[i-1].right+3,`${width}: overlap`);
     assert(Math.abs(geometry[i].center-geometry[i-1].center)<2,`${width}: vertical alignment`);
    }
    if(role==='public'){
     assert(await page.locator('.brand-text strong').evaluate(el=>el.scrollWidth<=el.clientWidth));
     assert.equal(await cta.getAttribute('href'),'/#cadastro');assert(await cta.locator('svg').count());
     assert((await cta.boundingBox()).height>=44);
    }
    const toggle=page.locator('[data-nav-toggle]');
    if(await toggle.isVisible()){
     await toggle.click();assert.equal(await page.locator('.header-signup:visible').count(),role==='public'?1:0);
     assert(await page.locator('#main-nav').isVisible());await page.keyboard.press('Escape');
    }
    cases.push({width,role,path});
   }
   if(role==='public'){
    await page.goto(BASE+'/duvidas-frequentes');await page.addInitScript(()=>{if(location.hash==='#cadastro')sessionStorage.setItem('adelinha-scroll','123');});
    await page.locator('.header-signup:visible').click();await page.waitForURL('**/#cadastro');
    await page.evaluate(()=>document.fonts.ready);await frame(page);
    assert(await page.locator('#cadastro').isVisible());
    await page.waitForFunction(()=>{const y=document.querySelector('#cadastro').getBoundingClientRect().top;return y>=-2&&y<150;});
    const top=await page.locator('#cadastro').evaluate(el=>el.getBoundingClientRect().top);
    assert(top>=-2&&top<150,`CTA anchor: ${width}, top=${top}`);
   } else {
    await page.goto(BASE+'/');
    const toggle=page.locator('[data-nav-toggle]');if(await toggle.isVisible())await toggle.click();
    await page.locator('#main-nav button').filter({hasText:'Sair'}).click();
    await frame(page);assert.equal(await page.locator('.header-signup:visible').count(),1);
   }
   await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:`${out}/header-${role}-${width}.png`});
   await context.close();
  }
  const page=await browser.newPage({viewport:{width:1440,height:900}});await page.goto(BASE+'/');
  const marquee=page.locator('.store-marquee');await marquee.scrollIntoViewIfNeeded();
  await page.locator('.store-group:first-child img').evaluateAll(images=>Promise.all(images.map(im=>im.decode())));
  assert.equal(await page.locator('.store-group:first-child img').count(),16);
  assert.equal(await page.locator('.store-group[aria-hidden=true] img').count(),16);
  assert(!(await page.getByText('Destinatário fictício:',{exact:false}).count()));
  const animation=()=>page.locator('.store-track').evaluate(el=>{const a=el.getAnimations()[0];return {time:a.currentTime,state:getComputedStyle(el).animationPlayState,x:new DOMMatrixReadOnly(getComputedStyle(el).transform).m41};});
  await page.mouse.move(0,0);await marquee.evaluate(el=>el.blur());const first=await animation();await page.waitForTimeout(200);const second=await animation();assert(second.x<first.x);
  await marquee.hover();const hover=await animation();await page.waitForTimeout(200);assert(Math.abs((await animation()).time-hover.time)<25);
  await page.mouse.move(0,0);await marquee.focus();const focus=await animation();await page.waitForTimeout(200);assert(Math.abs((await animation()).time-focus.time)<25);
  await marquee.evaluate(el=>el.blur());
  const seam=await page.locator('.store-track').evaluate(track=>{
   const groups=track.querySelectorAll('.store-group');const widths=[...groups].map(g=>g.getBoundingClientRect().width);
   const a=track.getAnimations()[0];a.pause();a.currentTime=64999;
   return {widths,offset:groups[1].getBoundingClientRect().left-track.parentElement.getBoundingClientRect().left};
  });assert(Math.abs(seam.widths[0]-seam.widths[1])<.1);assert(Math.abs(seam.offset)<1);
  for(const width of widths){
   await page.setViewportSize({width,height:900});await page.emulateMedia({reducedMotion:'reduce'});await frame(page);
   const reduced=await page.locator('.store-marquee').evaluate(el=>({animation:getComputedStyle(el.querySelector('.store-track')).animationName,duplicates:getComputedStyle(el.querySelector('[aria-hidden=true]')).display,overflow:document.documentElement.scrollWidth>innerWidth,mask:getComputedStyle(el).maskImage}));
   assert.equal(reduced.animation,'none');assert.equal(reduced.duplicates,'none');assert(!reduced.overflow);assert.equal(reduced.mask,'none');
   await marquee.scrollIntoViewIfNeeded();await page.screenshot({path:`${out}/logos-reduced-${width}.png`});
  }
  await page.emulateMedia({reducedMotion:'no-preference'});await page.setViewportSize({width:1440,height:900});await marquee.scrollIntoViewIfNeeded();await page.screenshot({path:`${out}/logos-1440.png`});
  fs.writeFileSync(`${out}/report.json`,JSON.stringify({cases,passed:true,checks:['auth','logout','anchor','alignment','16 logos','seam','hover','focus','reduced motion']},null,2));
  console.log(`PASS: ${cases.length} page/state/width checks, signup anchor/logout, 16 local logos, continuous seam, hover/focus and reduced motion.`);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
