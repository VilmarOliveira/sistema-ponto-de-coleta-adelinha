/* Uses only the isolated local fixture server from serve_responsive.py. */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const BASE='http://127.0.0.1:5001';
const SETTINGS='/painel/configuracoes/cartoes-explicativos';
(async()=>{
  const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  try {
    const admin=await browser.newPage();
    await admin.goto(BASE+'/login');
    await admin.locator('[name=user]').fill('admin');
    await admin.locator('[name=password]').fill('responsivo-local-123');
    await Promise.all([admin.waitForURL('**/painel'),admin.locator('button[type=submit],form button').filter({hasText:'Entrar'}).click()]);
    const png=await admin.evaluate(async()=>{const c=document.createElement('canvas');c.width=800;c.height=1200;const x=c.getContext('2d');x.fillStyle='#00ced1';x.fillRect(0,0,800,1200);x.fillStyle='#262626';x.font='bold 60px sans-serif';x.fillText('Teste legível',30,100);x.font='20px sans-serif';x.fillText(String(Date.now()),30,150);return c.toDataURL('image/png').split(',')[1];});
    const image=Buffer.from(png,'base64');
    for(const width of [320,360,390,430,768,1024,1440]) {
      await admin.setViewportSize({width,height:900});await admin.goto(BASE+SETTINGS);
      assert(await admin.locator('text=800 × 1200 px').count()===4);
      assert(await admin.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    }
    await admin.setViewportSize({width:390,height:844});
    const form=admin.locator('form').filter({has:admin.locator('[name=card_id][value="1"]')});
    const originalTitle=await form.locator('[name=title]').inputValue();
    const originalSrc=await form.locator('[data-banner-preview]').getAttribute('src');
    await form.locator('[name=title]').fill('Cancelar edição');
    await form.locator('[type=file]').setInputFiles({name:'card.png',mimeType:'image/png',buffer:image});
    await admin.waitForFunction(()=>document.querySelector('#explanatory-1').validationMessage==='');
    await form.getByRole('link',{name:'Cancelar',exact:true}).click();
    assert.equal(await form.locator('[name=title]').inputValue(),originalTitle);
    assert.equal(await form.locator('[data-banner-preview]').getAttribute('src'),originalSrc);
    for(const file of [
      {name:'invalid.png',mimeType:'image/png',buffer:Buffer.from('not a real PNG')},
      {name:'large.png',mimeType:'image/png',buffer:Buffer.alloc(900*1024+1)},
    ]) {
      await form.locator('[type=file]').setInputFiles(file);
      await form.locator('[data-upload-error]').waitFor({state:'visible'});
      assert.equal(await form.locator('[data-banner-preview]').getAttribute('src'),originalSrc);
      assert(await form.locator('[type=file]').evaluate(el=>!el.checkValidity()));
    }
    await form.locator('[type=file]').setInputFiles({name:'card.png',mimeType:'image/png',buffer:image});
    await admin.waitForFunction(()=>document.querySelector('#explanatory-1').validationMessage==='');
    await form.locator('[name=title]').fill('Cartão publicado pelo painel');
    await form.locator('[name=alt_text]').fill('Cartão turquesa com texto de exemplo');
    await Promise.all([admin.waitForURL('**/cartoes-explicativos'),form.getByRole('button',{name:'Salvar alterações'}).click()]);
    await admin.getByText('Cartão atualizado com sucesso!',{exact:true}).waitFor();
    const revision=await form.locator('[data-banner-preview]').getAttribute('src');assert.notEqual(revision,originalSrc);
    for(const width of [320,360,390,430,768,1024,1440]) {
      const context=await browser.newContext({viewport:{width,height:900},isMobile:width<768,hasTouch:width<768});
      const page=await context.newPage();const requests=[];const jsErrors=[];
      page.on('request',req=>requests.push(req.url()));page.on('pageerror',e=>jsErrors.push(e.message));
      await page.goto(BASE+'/');
      assert.equal(await page.locator('.steps-grid').count(),0);
      assert.equal(await page.getByRole('heading',{name:'Veja um exemplo de como é fácil usar nosso serviço',exact:true}).count(),1);
      const layout=await page.locator('.explanatory-grid').evaluate(grid=>{
        const box=el=>{const r=el.getBoundingClientRect();return {top:r.top,left:r.left,width:r.width,height:r.height};};
        return {beforeStores:!!(grid.closest('section').compareDocumentPosition(document.querySelector('.favorite-stores')) & Node.DOCUMENT_POSITION_FOLLOWING),
          cards:[...grid.children].map(card=>({title:box(card.querySelector('h3')),image:box(card.querySelector('picture')),link:box(card.querySelector('.enlarge-desktop')),padding:getComputedStyle(card.querySelector('img')).padding,position:getComputedStyle(card.querySelector('img')).objectPosition}))};
      });
      assert(layout.beforeStores);
      assert.equal(layout.cards.length,4);
      for(const card of layout.cards){
        assert(Math.abs(card.image.width/card.image.height-2/3)<.005);
        assert.equal(card.padding,'0px');assert.equal(card.position,'50% 50%');
      }
      if(width<768){
        assert(layout.cards.every(card=>Math.abs(card.image.left-layout.cards[0].image.left)<1));
        for(let i=1;i<4;i++)assert(layout.cards[i].title.top>layout.cards[i-1].image.top+layout.cards[i-1].image.height);
      }else{
        const group=width>1024?4:2;
        for(let start=0;start<4;start+=group){
          for(let i=start+1;i<start+group;i++){
            for(const part of ['title','image','link'])assert(Math.abs(layout.cards[i][part].top-layout.cards[start][part].top)<1,`${width}: ${part} alignment`);
          }
        }
      }
      const link=page.locator('[data-card-enlarge]').first();
      await link.scrollIntoViewIfNeeded();
      await page.waitForFunction(()=>document.querySelector('.explanatory-open img').complete);
      assert(!requests.some(url=>url.includes('/original?')));
      const selected=await link.locator('img').evaluate(el=>({src:el.currentSrc,fit:getComputedStyle(el).objectFit}));
      assert(selected.src.includes(width<768?'/celular?':'/computador?'));assert.equal(selected.fit,'contain');
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      if(width<768)assert(await link.locator('.enlarge-touch').isVisible());else assert(await link.locator('.enlarge-desktop').isVisible());
      // Keyboard activation, native modal focus confinement, Escape and focus restoration.
      await link.focus();await page.keyboard.press('Enter');
      const dialog=page.locator('[data-card-dialog]');await dialog.waitFor({state:'visible'});
      await page.locator('[data-card-full]').evaluate(img=>img.decode());
      assert(requests.some(url=>url.includes('/original?')));
      assert.equal(await page.locator('[data-card-full]').getAttribute('alt'),'Cartão turquesa com texto de exemplo');
      assert(await page.evaluate(()=>document.querySelector('dialog').contains(document.activeElement)));
      await page.keyboard.press('Tab');assert(await page.evaluate(()=>document.querySelector('dialog').contains(document.activeElement)));
      await page.keyboard.press('Escape');assert(!(await dialog.isVisible()));assert(await link.evaluate(el=>el===document.activeElement));
      if(width<768) {
        await link.tap();await page.locator('[data-card-close]').tap();assert(!(await dialog.isVisible()));
        await link.tap();await page.touchscreen.tap(2,2);assert(!(await dialog.isVisible()));
      } else {
        await link.click();await page.locator('[data-card-close]').click();assert(!(await dialog.isVisible()));
        await link.click();await page.mouse.click(2,2);assert(!(await dialog.isVisible()));
      }
      assert.equal(jsErrors.length,0);
      fs.mkdirSync('/tmp/adelinha-card-results',{recursive:true});
      await page.screenshot({path:`/tmp/adelinha-card-results/cards-${width}.png`});
      await context.close();
    }
    // A new session reads the saved metadata and derivatives without deployment.
    await admin.reload();assert.equal(await form.locator('[name=title]').inputValue(),'Cartão publicado pelo painel');
    console.log('PASS: uploads, validation, cancel, persistence, cache version, responsive thumbnails and modal at 7 widths.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
