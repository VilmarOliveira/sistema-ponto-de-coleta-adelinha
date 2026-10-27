/* Execute com NODE_PATH apontando para playwright/jsqr instalados fora do checkout.
   O servidor de fixtures é exclusivamente local e bloqueia integrações reais. */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const BASE = process.env.RESPONSIVE_BASE_URL || 'http://127.0.0.1:5001';
if (!['127.0.0.1','localhost'].includes(new URL(BASE).hostname)) throw new Error('Use somente o servidor local de fixtures.');
const WIDTHS = [320,360,390,430,768,1024,1440];
const PASSWORD = 'responsivo-local-123';
const OUT = process.env.RESPONSIVE_REPORT_DIR || path.join(os.tmpdir(),'adelinha-responsive-results');
fs.mkdirSync(OUT,{recursive:true});
const report = {widths:WIDTHS,cases:[],failures:[],interactions:[]};
const ONLY_INTERACTIONS = process.argv.includes('--only-interactions');
if (ONLY_INTERACTIONS && fs.existsSync(path.join(OUT,'report.json'))) {
  const previous = JSON.parse(fs.readFileSync(path.join(OUT,'report.json'),'utf8'));
  report.cases = previous.cases; report.failures = previous.failures;
  report.interactions = previous.interactions.filter(item => item.width && item.role);
}
const frame = page => page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
const errors = [];

async function login(page,role){
  if(role === 'public')return;
  const customer = role === 'client' || role === 'client_empty';
  await page.goto(BASE+(customer?'/cliente/login':'/login'));
  if(customer){await page.locator('[name=cpf]').fill(role==='client'?'52998224725':'98765432100');}
  else {await page.locator('[name=user]').fill({admin:'admin',manager:'gerente@example.test',clerk:'atendente@example.test'}[role]);}
  await page.locator('[name=password]').fill(PASSWORD);
  await Promise.all([page.waitForURL(customer?'**/cliente':'**/painel'), page.locator('form button').filter({hasText:'Entrar'}).click()]);
}

async function audit(page,width,role,url,state){
  await frame(page);
  const result=await page.evaluate(()=>{
    const issues=[];const viewport=innerWidth;
    const visible=el=>{const b=el.getBoundingClientRect(),s=getComputedStyle(el);return b.width>0&&b.height>0&&s.visibility!=='hidden'&&s.display!=='none'&&!el.closest('[hidden],[aria-hidden="true"]');};
    if(document.documentElement.scrollWidth>viewport+1||document.body.scrollWidth>viewport+1)issues.push({kind:'page-overflow',viewport,html:document.documentElement.scrollWidth,body:document.body.scrollWidth});
    if(['hidden','clip'].includes(getComputedStyle(document.body).overflowX))issues.push({kind:'overflow-masked'});
    for(const el of document.querySelectorAll('main input:not([type=hidden]),main select,main textarea,main button,main .button,main summary,main canvas,main img')){
      if(!visible(el))continue;
      const box=el.getBoundingClientRect();
      const table=el.closest('.table-scroll');
      if(!table&&(box.left < -1||box.right>viewport+1))issues.push({kind:'element-overflow',tag:el.tagName,text:(el.innerText||el.name||el.alt||'').slice(0,80),left:box.left,right:box.right});
      if(el.matches('input:not([type=checkbox]):not([type=radio]),select,textarea')&&parseFloat(getComputedStyle(el).fontSize)<16)issues.push({kind:'small-field-font',name:el.name});
      if(el.matches('button,.button,summary')&&box.height<43.5)issues.push({kind:'small-touch-target',text:el.textContent.slice(0,60),height:box.height});
    }
    const header=document.querySelector('.site-header'),brand=header.querySelector('.brand'),toggle=header.querySelector('.nav-toggle'),nav=header.querySelector('.site-nav');
    const br=brand.getBoundingClientRect(),tr=toggle.getBoundingClientRect(),nr=nav.getBoundingClientRect();
    if(visible(toggle)){
      if(Math.abs((br.top+br.height/2)-(tr.top+tr.height/2))>2)issues.push({kind:'brand-menu-misaligned',brand:br.toJSON(),toggle:tr.toJSON()});
      if(br.right+4>tr.left)issues.push({kind:'brand-menu-overlap'});
      if(toggle.getAttribute('aria-expanded')==='false'&&header.getBoundingClientRect().height>120)issues.push({kind:'tall-mobile-header',height:header.getBoundingClientRect().height});
    }else if(visible(nav)&&br.right+4>nr.left)issues.push({kind:'brand-nav-overlap'});
    const logged=header.querySelector('.logged-user');
    if(logged&&visible(logged)&&getComputedStyle(logged).overflow==='hidden')issues.push({kind:'truncated-user-name'});
    for(const wrapper of document.querySelectorAll('.table-scroll')){
      const b=wrapper.getBoundingClientRect();if(b.left< -1||b.right>viewport+1)issues.push({kind:'table-wrapper-overflow'});
    }
    return {issues,headerHeight:header.getBoundingClientRect().height,menu:visible(toggle)?'compact':'full',scrollWidth:document.documentElement.scrollWidth};
  });
  const entry={width,role,url,state,...result};
  const existing=report.cases.findIndex(item=>item.width===width&&item.role===role&&item.url===url&&item.state===state);
  if(existing<0)report.cases.push(entry);else report.cases[existing]=entry;
  report.failures=report.failures.filter(item=>!(item.width===width&&item.role===role&&item.url===url&&item.state===state));
  for(const issue of result.issues)report.failures.push({width,role,url,state,...issue});
}

async function inspect(page,width,role,url){
  const response=await page.goto(BASE+url);
  if(![200,410].includes(response.status()))throw new Error(`${role} ${url}: HTTP ${response.status()}`);
  await page.evaluate(()=>document.fonts.ready);
  await audit(page,width,role,url,'initial');
  const toggle=page.locator('[data-nav-toggle]');
  if(await toggle.isVisible()){
    await toggle.click();await audit(page,width,role,url,'menu-open');
    assert.equal(await toggle.getAttribute('aria-expanded'),'true');
    for(const link of await page.locator('#main-nav a').all())assert(await link.isVisible());
    await page.keyboard.press('Escape');assert.equal(await toggle.getAttribute('aria-expanded'),'false');
  }
  if(await page.locator('main details').count()){
    await page.locator('main details').evaluateAll(elements=>elements.forEach(el=>el.open=true));
    await audit(page,width,role,url,'details-open');
  }
  if(url==='/painel'){
    await page.locator('[name=package_ids][value="2"]').check();
    await page.locator('[name=payment_method][value="Pix"]').check();
    await page.waitForFunction(()=>document.querySelector('#pix-code').value.length>50);
    await page.locator('#pix-qr').evaluate(img=>img.decode());
    await audit(page,width,role,url,'pix-visible');
    await page.addScriptTag({path:require.resolve('jsqr/dist/jsQR.js')});
    const decoded=await page.locator('#pix-qr').evaluate(img=>{
      const canvas=document.createElement('canvas');canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;
      const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0);
      return jsQR(ctx.getImageData(0,0,canvas.width,canvas.height).data,canvas.width,canvas.height).data;
    });
    const code=await page.locator('#pix-code').inputValue();assert.equal(decoded,code);
    await page.context().grantPermissions(['clipboard-read','clipboard-write']);
    await page.locator('[data-copy="#pix-code"]').click();assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),code);
    report.interactions.push({width,role,test:'Pix QR decode and exact clipboard copy',passed:true});
  }
}

async function preserveSignature(browser){
  const page=await browser.newPage({viewport:{width:390,height:844},hasTouch:true,isMobile:true});
  await page.goto(BASE+'/');await page.evaluate(()=>document.fonts.ready);await page.locator('#registration-form [name=name]').fill('Dados preenchidos permanecem durante rotação');
  const canvas=page.locator('#registration-form canvas');await canvas.scrollIntoViewIfNeeded();
  const box=await canvas.boundingBox();const session=await page.context().newCDPSession(page);
  await session.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:box.x+25,y:box.y+40}]});
  await session.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:box.x+65,y:box.y+70}]});
  await session.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:box.x+110,y:box.y+40}]});
  await session.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  const hidden=page.locator('#registration-form [name=signature]');
  const value=await hidden.inputValue();assert(value.startsWith('data:image/png;base64,'));
  for(const width of [...WIDTHS,932,390]){
    await page.setViewportSize({width,height:width===932?430:844});await frame(page);
    await audit(page,width,'public','/','signature-resize');
    assert.equal(await hidden.inputValue(),value);
    assert.equal(await canvas.evaluate(el=>el.toDataURL()),value);
    assert.equal(await page.locator('#registration-form [name=name]').inputValue(),'Dados preenchidos permanecem durante rotação');
  }
  report.interactions.push({test:'Touch signature and filled fields retained through all widths and orientation',passed:true});
  await page.close();
}

async function carouselAndSupport(browser){
  const page=await browser.newPage({viewport:{width:390,height:844},hasTouch:true,isMobile:true});
  await page.clock.install();await page.goto(BASE+'/');
  await page.clock.pauseAt(new Date(Date.now()+1000));await page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));
  assert.equal(await page.locator('[data-slide]').count(),3);
  assert.equal(await page.locator('[data-carousel-prev],[data-carousel-next],[data-carousel-pause]').count(),0);
  const before=await page.locator('[data-slide].active').getAttribute('aria-label');
  await page.clock.fastForward(2999);assert.equal(await page.locator('[data-slide].active').getAttribute('aria-label'),before);
  await page.clock.fastForward(1);assert.notEqual(await page.locator('[data-slide].active').getAttribute('aria-label'),before);
  await page.locator('.banner-slides').dispatchEvent('touchstart',{touches:[{identifier:1,clientX:300,clientY:150}]});
  await page.locator('.banner-slides').dispatchEvent('touchend',{changedTouches:[{identifier:1,clientX:80,clientY:150}]});
  assert.equal(await page.locator('[data-slide].active').getAttribute('aria-label'),'3 de 3');
  assert.equal(await page.locator('[data-slide] img').first().evaluate(el=>getComputedStyle(el).objectFit),'contain');
  report.interactions.push({test:'Carousel 3s, swipe and indicators, no arrows or pause control',passed:true});
  await page.close();
  const supportPage=await browser.newPage({viewport:{width:390,height:844}});await supportPage.goto(BASE+'/');
  for(const fraction of [0,.2,.5,.8,1]){
    await supportPage.evaluate(value=>scrollTo(0,(document.documentElement.scrollHeight-innerHeight)*value),fraction);await frame(supportPage);
    const conflicts=await supportPage.evaluate(()=>{
      const float=document.querySelector('.support-float');if(getComputedStyle(float).visibility==='hidden')return [];
      const r=float.getBoundingClientRect();return [...document.querySelectorAll('main input:not([type=hidden]),main textarea,main select,main button,main a.button,main canvas,main img')].filter(el=>{
        const b=el.getBoundingClientRect();return !el.closest('[hidden],[aria-hidden="true"]')&&b.width&&b.height&&b.left<r.right&&b.right>r.left&&b.top<r.bottom&&b.bottom>r.top;
      }).map(el=>el.tagName);
    });assert.deepEqual(conflicts,[]);
  }
  report.interactions.push({test:'Floating WhatsApp does not cover controls, signatures or images while scrolling',passed:true});
  await supportPage.close();
}

async function preservePayment(browser){
  const page=await browser.newPage({viewport:{width:1024,height:900}});
  await login(page,'admin');await page.goto(BASE+'/painel');
  await page.locator('[name=package_ids][value="2"]').check();
  await page.locator('[name=payment_method][value="Pix"]').check();
  await page.locator('[name=receiver_name]').fill('Retirada com dados preservados');
  await page.locator('[name=document_type]').selectOption('CPF');
  await page.locator('[name=receiver_document]').fill('52998224725');
  await page.locator('[name=surcharge_reason]').fill('Motivo de teste para preservar os dados preenchidos');
  await page.locator('[name=surcharge_amount]').fill('2,50');
  await page.waitForFunction(()=>document.querySelector('#pix-code').value.includes('54047.40'));
  await page.locator('[name=payment_confirmed]').check();
  const canvas=page.locator('#pickup-form canvas');await canvas.scrollIntoViewIfNeeded();
  const box=await canvas.boundingBox();await page.mouse.move(box.x+20,box.y+35);await page.mouse.down();
  await page.mouse.move(box.x+80,box.y+70,{steps:4});await page.mouse.move(box.x+130,box.y+40,{steps:4});await page.mouse.up();
  const snapshot=()=>page.evaluate(()=>{
    const form=document.querySelector('#pickup-form');
    return {fields:[...form.elements].filter(el=>el.name&&!['csrf_token','package_ids'].includes(el.name)).map(el=>({name:el.name,value:el.value,checked:el.checked})),
      packages:[...document.querySelectorAll('[name=package_ids]:checked')].map(el=>el.value),
      canvas:form.querySelector('canvas').toDataURL(),pix:document.querySelector('#pix-code').value};
  });
  const before=await snapshot();assert(before.canvas.length>500);assert(before.fields.find(field=>field.name==='pickup_signature').value.startsWith('data:image/png;base64,'));
  for(const width of [...WIDTHS,932]){await page.setViewportSize({width,height:width===932?430:900});await frame(page);await audit(page,width,'admin','/painel','payment-resize');assert.deepEqual(await snapshot(),before);}
  report.interactions.push({test:'Withdrawal fields, package selection, payment confirmation, Pix and mouse signature retained on resize',passed:true});
  await page.locator('#pickup-form .clear-signature').click();
  const oldData=await page.evaluate(()=>{
    const old=document.createElement('canvas');old.width=700;old.height=150;
    old.getContext('2d').fillRect(40,30,200,60);const data=old.toDataURL();
    document.querySelector('#pickup-form').restoreSignature(data);return data;
  });
  await page.waitForFunction(data=>document.querySelector('#pickup-form .signature-value').value===data,oldData);
  const restored=await canvas.evaluate(el=>({bitmap:el.toDataURL(),inside:el.getContext('2d').getImageData(50,115,1,1).data[3],outside:el.getContext('2d').getImageData(50,70,1,1).data[3]}));
  assert.equal(restored.inside,255);assert.equal(restored.outside,0);
  for(const width of [390,1440]){
    await page.setViewportSize({width,height:900});await frame(page);
    assert.equal(await canvas.evaluate(el=>el.toDataURL()),restored.bitmap);
    assert.equal(await page.locator('#pickup-form .signature-value').inputValue(),oldData);
  }
  report.interactions.push({test:'Older signature drafts retain pixels and proportions without stretching or clearing',passed:true});
  await page.close();
}

async function priorityColumns(browser){
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  await login(page,'admin');await page.goto(BASE+'/painel/configuracoes/usuarios?tab=equipe');
  for(const width of WIDTHS){
    await page.setViewportSize({width,height:1000});await frame(page);
    await page.locator('.user-edit').first().evaluate(el=>el.open=false);
    await audit(page,width,'admin','/painel/configuracoes/usuarios?tab=equipe','column-priority');
    if(width>=768){
      const lines=await page.locator('tbody tr').first().locator('td').first().locator('b').evaluate(el=>{const range=document.createRange();range.selectNodeContents(el);return range.getClientRects().length});
      assert.equal(lines,1,'Identificador não deve ser quebrado no meio em tabelas de tablet/desktop');
      const statusLines=await page.locator('thead th').nth(3).evaluate(el=>{const range=document.createRange();range.selectNodeContents(el);return range.getClientRects().length});
      assert.equal(statusLines,1,'Cabeçalho Situação deve ficar legível sem corte de palavra');
    }
    await page.locator('.user-edit').first().evaluate(el=>el.open=true);
    await audit(page,width,'admin','/painel/configuracoes/usuarios?tab=equipe','column-priority-edit-open');
  }
  report.interactions.push({test:'Priority ID/status columns and complete edit actions remain legible at every width',passed:true});
  await page.close();
}

async function printAndLogo(browser){
  const page=await browser.newPage({viewport:{width:794,height:1123}});
  await login(page,'client');await page.goto(BASE+'/cliente/comprovantes/1');
  await page.emulateMedia({media:'print'});await page.evaluate(()=>document.fonts.ready);
  assert.equal(await page.locator('.site-header').isVisible(),false);
  assert.equal(await page.locator('.support-float').isVisible(),false);
  assert(await page.locator('.table-scroll').evaluate(el=>el.scrollWidth<=el.clientWidth+1));
  const printed=await page.pdf({format:'A4',path:path.join(OUT,'receipt-print.pdf')});
  assert(printed.subarray(0,5).toString()==='%PDF-');
  const original=await page.request.get(BASE+'/comprovantes/1/pacotes/3.pdf');
  assert.equal(original.status(),200);assert.match(original.headers()['content-type'],/application\/pdf/);
  assert((await original.body()).includes(Buffer.from('4,90')));
  const contract=await page.request.get(BASE+'/cliente/contrato-assinado.pdf');
  assert.equal(contract.status(),200);assert.match(contract.headers()['content-type'],/application\/pdf/);
  report.interactions.push({test:'Receipt print, native table, original PDF and signed contract downloads',passed:true});
  await page.emulateMedia({media:'screen'});
  // Valida também o contêiner com uma logo quadrada, sem depender de arte privada.
  await page.goto(BASE+'/');
  await page.locator('.brand').evaluate(el=>{el.innerHTML='<img src="/static/whatsapp-original.jpg" alt="Imagem quadrada de teste">'});
  await page.locator('.brand img').evaluate(img=>img.decode());
  for(const width of WIDTHS){
    await page.setViewportSize({width,height:900});await frame(page);
    const data=await page.locator('.brand img').evaluate(el=>({fit:getComputedStyle(el).objectFit,width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height}));
    assert.equal(data.fit,'contain');assert(Math.abs(data.width-data.height)<1);
  }
  report.interactions.push({test:'Square-image logo container proportions at every requested width',passed:true});
  await page.close();
}

(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
 try{
  const request=await browser.newPage();const manifest=await(await request.request.get(BASE+'/__responsive/manifest')).json();await request.close();
  if (!ONLY_INTERACTIONS) for(const width of WIDTHS){
    for(const [role,urls] of Object.entries(manifest)){
      const context=await browser.newContext({viewport:{width,height:width>=768?1000:844},isMobile:width<768,hasTouch:width<1024});
      await context.route('**/*',route=>new URL(route.request().url()).origin===new URL(BASE).origin?route.continue():route.abort());
      const page=await context.newPage();page.on('pageerror',error=>errors.push({width,role,message:error.message}));
      await login(page,role);
      for(const url of urls)await inspect(page,width,role,url);
      if(role==='manager'||role==='clerk')assert.equal((await page.request.get(BASE+'/painel/configuracoes')).status(),403);
      if(role==='admin'){
        await page.goto(BASE+'/painel/clientes/2');await page.locator('[name=confirmation]').fill('CLIPCA-2');
        let dialogSeen=false;page.once('dialog',async dialog=>{assert.equal(dialog.type(),'confirm');dialogSeen=true;await dialog.dismiss()});
        await page.locator('#excluir button').click();assert(dialogSeen);
        await page.goto(BASE+'/painel/configuracoes/usuarios?tab=equipe');
        await page.locator('.user-edit').first().evaluate(el=>el.open=true);await frame(page);
        await page.screenshot({path:path.join(OUT,`users-${width}.png`),fullPage:false});
      }
      await context.close();
    }
    console.log(`${width}px: matrix complete`);
  }
  await preserveSignature(browser);await carouselAndSupport(browser);await preservePayment(browser);await priorityColumns(browser);await printAndLogo(browser);
  report.failures.push(...errors.map(error=>({kind:'javascript-error',...error})));
  fs.writeFileSync(path.join(OUT,'report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify({cases:report.cases.length,interactions:report.interactions.length,failures:report.failures.length,report:path.join(OUT,'report.json')}));
  if(report.failures.length){console.error(JSON.stringify(report.failures.slice(0,35),null,2));process.exitCode=1;}
 }finally{await browser.close();}
})().catch(error=>{console.error(error);fs.writeFileSync(path.join(OUT,'report.json'),JSON.stringify(report,null,2));process.exit(1)});
