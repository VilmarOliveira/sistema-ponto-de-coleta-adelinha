'use strict';
(() => {
 const $=id=>document.getElementById(id);
 const DB='adelinha-contingency-v1';
 let db, state=null, key=null, envelope=null, identity=null, busy=false, idle;
 const encoder=new TextEncoder(), decoder=new TextDecoder();
 const bytesTo64=bytes=>{let s='';for(const n of bytes)s+=String.fromCharCode(n);return btoa(s);};
 const from64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
 const clone=value=>JSON.parse(JSON.stringify(value));
 const say=(message,error=false)=>{$('message').textContent=message;$('message').classList.toggle('error',error);};
 const statusLabels={local:'Aguardando envio',review:'Enviado • conferir online',conflict:'Conflito • revisar online',linked:'Sincronizado no sistema',dismissed:'Conferido • não aplicado'};
 function connection() {
  $('connection').textContent=navigator.onLine?'Conexão disponível • Sincronização exige sessão ativa':'Sem internet • Dados salvos neste aparelho';
  $('connection').classList.toggle('online',navigator.onLine);
 }
 function transaction(mode,fn) {
  return new Promise((resolve,reject)=>{
   const tx=db.transaction('vault',mode), store=tx.objectStore('vault');
   let value;
   tx.oncomplete=()=>resolve(value);tx.onerror=()=>reject(tx.error||new Error('Não foi possível salvar no navegador.'));tx.onabort=()=>reject(tx.error||new Error('Dados alterados em outra aba. Bloqueie e abra novamente.'));
   fn(store,v=>{value=v;},()=>tx.abort());
  });
 }
 function readVault(){return transaction('readonly',(s,set)=>{const r=s.get('current');r.onsuccess=()=>set(r.result||null);});}
 async function derive(password,salt) {
  const material=await crypto.subtle.importKey('raw',encoder.encode(password),'PBKDF2',false,['deriveKey']);
  return crypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:310000,hash:'SHA-256'},material,{name:'AES-GCM',length:256},false,['encrypt','decrypt']);
 }
 function validEnvelope(value) {
  return value&&value.version===1&&value.origin===location.origin&&typeof value.scope==='string'&&/^[a-f0-9]{64}$/.test(value.scope)
   &&typeof value.salt==='string'&&typeof value.iv==='string'&&typeof value.cipher==='string'&&typeof value.revision==='string'
   &&from64(value.salt).length===16&&from64(value.iv).length===12&&value.cipher.length<28000000;
 }
 async function save(next,initial=false) {
  const iv=crypto.getRandomValues(new Uint8Array(12));
  const encoded=encoder.encode(JSON.stringify(next));
  if(encoded.byteLength>12*1024*1024)throw new Error('A base local atingiu o limite. Faça backup, sincronize e confira os registros antes de continuar.');
  const cipher=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:encoder.encode(envelope.scope)},key,encoded);
  const row={...envelope,iv:bytesTo64(iv),cipher:bytesTo64(new Uint8Array(cipher)),revision:crypto.randomUUID()};
  const previous=envelope.revision;
  await transaction('readwrite',(s,set,abort)=>{
   const r=s.get('current');
   r.onsuccess=()=>{
    if((initial&&r.result)||(!initial&&r.result?.revision!==previous)){abort();return;}
    s.put(row,'current');set(true);
   };
  });
  envelope=row;state=next;
 }
 async function mutate(change) {
  const next=clone(state);change(next);await save(next);render();
 }
 function resetIdle() {
  clearTimeout(idle);if(state)idle=setTimeout(()=>{lock();say('Acesso local bloqueado após 15 minutos sem uso.');},15*60*1000);
 }
 function lock(){
  state=null;key=null;identity=null;clearTimeout(idle);
  document.querySelectorAll('#workspace input,#workspace textarea').forEach(x=>{if(x.type==='checkbox')x.checked=false;else x.value='';});
  $('records').replaceChildren();$('pickup-packages').replaceChildren();
  for(const id of ['package-list','client-info','pickup-client-info','online-history','client-contract','local-receipt','pix-qr'])$(id).replaceChildren();
  $('pix-code').value='';clientSignature.clear();
  $('package-client').replaceChildren();$('pickup-client').replaceChildren();clearSignature();
  $('workspace').hidden=true;$('gate').hidden=false;$('lock').hidden=true;
  $('identity').textContent='';$('prepared').textContent='';
  $('unlock-form').hidden=!envelope;$('prepare-form').hidden=!!envelope;$('restore-label').hidden=!!envelope;
  $('unlock-password').value='';$('new-password').value='';$('repeat-password').value='';
 }
 async function task(fn){
  if(busy)return;busy=true;
  document.querySelectorAll('button').forEach(x=>x.disabled=true);
  try{await fn();resetIdle();}catch(error){say(error.message||'Não foi possível concluir. Os registros já salvos foram preservados.',true);}
  finally{busy=false;document.querySelectorAll('button').forEach(x=>x.disabled=false);}
 }
 async function api(path,form=null) {
  let response;const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),15000);
  try{response=await fetch('/offline/api/'+path,{method:form?'POST':'GET',body:form,credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal,headers:{Accept:'application/json'}});}
  catch(_){throw new Error('Sem conexão ou sessão expirada. Seus registros continuam salvos. Entre novamente na Área do Ponto e tente sincronizar.');}
  finally{clearTimeout(timeout);}
  if(!response.headers.get('content-type')?.includes('application/json'))throw new Error('Entre novamente na Área do Ponto para continuar online.');
  const result=await response.json();if(!response.ok)throw new Error(result.error||'Confira sua sessão e permissões na Área do Ponto.');
  return result;
 }
 async function sessionIdentity(){
  const result=await api('session');
  if(state&&result.scope!==state.scope)throw new Error('Use o mesmo operador e ambiente da preparação. Não envie estes dados com outra conta.');
  identity=result;return result;
 }
 const formData=value=>{const form=new FormData();for(const [k,v] of Object.entries(value))form.set(k,v);return form;};
 async function prepareWorker(){
  if(!('serviceWorker'in navigator)||!crypto.subtle)throw new Error('Este navegador precisa de HTTPS, armazenamento local e suporte offline. Use Chrome ou Edge atualizado.');
  const registration=await navigator.serviceWorker.register('/offline/sw.js',{scope:'/offline/'});
  await navigator.serviceWorker.ready;
  if(registration.installing)await new Promise((resolve,reject)=>{const worker=registration.installing;worker.addEventListener('statechange',()=>{if(worker.state==='activated')resolve();if(worker.state==='redundant')reject(new Error('Não foi possível preparar as telas offline.'));});});
  const cache=await caches.open('adelinha-offline-shell-v2');
  for(const path of ['/static/offline/index.html','/static/offline/offline.css','/static/offline/offline.js','/static/offline/finance.js','/static/offline/qrcode.js'])if(!await cache.match(path))throw new Error('As telas offline não foram preparadas. Tente novamente conectado.');
 }
 function ensureReady(){
  if(!state)throw new Error('Desbloqueie o aparelho.');
  if(Date.now()>Date.parse(state.snapshot.expires_at))throw new Error('Preparação vencida. Atualize os dados online para registrar novas operações. Os registros existentes foram preservados.');
 }
 function canonical(ref,kind){
  const op=state.operations.find(x=>x.event.id===ref&&x.event.kind===kind&&x.state==='linked'&&x.linked_id);
  return op?'srv:'+op.linked_id:ref;
 }
 function projected(){
  const clients=state.snapshot.clients.map(c=>({...c,plan:c.plan?{...c.plan}:null,ref:'srv:'+c.id,label:c.public_id}));
  const packages=state.snapshot.packages.map(p=>({...p,ref:'srv:'+p.id,client_ref:'srv:'+p.client_id}));
  for(const op of state.operations){
   if(op.event.kind==='client'&&op.state!=='dismissed'&&!clients.some(c=>c.ref===canonical(op.event.id,'client')))clients.push({...op.event.data,ref:op.event.id,label:'OFFC-'+op.event.id.slice(0,8)});
   if(op.event.kind==='package'&&!['linked','dismissed'].includes(op.state)){
    const d=op.event.data,category=(d.width+d.height+d.length<=80&&d.weight<=10)?'Pequeno':'Grande',client_ref=canonical(d.client_ref,'client');
    packages.push({...d,client_ref,ref:op.event.id,public_id:'OFFP-'+op.event.id.slice(0,8),status:'aguardando_aviso',category,base_price:d.plan_covered?0:category==='Pequeno'?(state.snapshot.prices?.small||4.9):(state.snapshot.prices?.large||9.9),created_at:op.event.created_at,notified_at:null,settled:0});
    const client=clients.find(c=>c.ref===client_ref);if(d.plan_covered&&client?.plan)client.plan.available=Math.max(0,client.plan.available-(category==='Pequeno'?1:2));
   }
  }
  for(const op of state.operations.filter(x=>x.event.kind==='notify'&&x.state!=='dismissed')){
   const ref=canonical(op.event.data.package_ref,'package'),p=packages.find(x=>x.ref===ref);
   if(p&&!p.notified_at){p.notified_at=op.event.created_at;p.status='aguardando_retirada';}
  }
  const withdrawn=new Set(state.operations.filter(x=>x.event.kind==='pickup'&&x.state!=='dismissed').flatMap(x=>x.event.data.package_refs.map(ref=>canonical(ref,'package'))));
  return {clients,packages:packages.filter(p=>!withdrawn.has(p.ref)&&p.status!=='retirado')};
 }
 function choices(select,clients){
  const previous=select.value;
  select.replaceChildren(new Option('Selecione o cliente',''));
  for(const c of clients)select.add(new Option(c.name+' • '+c.label,c.ref));
  if(clients.some(x=>x.ref===previous))select.value=previous;
 }
 function pickupChoices(){
  if(!state)return;
  const box=$('pickup-packages');box.replaceChildren();
  const packages=projected().packages.filter(p=>p.client_ref===$('pickup-client').value&&p.status==='aguardando_retirada');
  for(const p of packages){
   const label=document.createElement('label');label.className='check';
   const check=document.createElement('input');check.type='checkbox';check.value=p.ref;check.name='package_refs';
   label.append(check,document.createTextNode((p.public_id||p.tracking)+' • '+p.tracking+' • '+p.category));box.append(label);
  }
  if(!packages.length)box.textContent='Nenhum pacote aguardando retirada. Registre o aviso de chegada, se necessário.';
  showClient('pickup-client','pickup-client-info');updateQuote();
 }
 function tab(name){
  for(const key of ['client','package','pickup','records'])$('tab-'+key).hidden=key!==name;
  document.querySelectorAll('[data-tab]').forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.tab===name)));
 }
 function render(){
  if(!state)return;
  $('gate').hidden=true;$('workspace').hidden=false;$('lock').hidden=false;
  $('identity').textContent=(state.snapshot.environment==='test'?'AMBIENTE DE TESTES':'PRODUÇÃO')+' • '+state.snapshot.operator;
  $('prepared').textContent='Preparado em '+new Date(state.snapshot.prepared_at).toLocaleString('pt-BR')+' • Validade: 7 dias • '+state.snapshot.name;
  const data=projected();
  $('package-count').textContent=String(data.packages.length);
  $('pending-count').textContent=String(state.operations.filter(x=>x.state==='local').length);
  $('review-count').textContent=String(state.operations.filter(x=>['review','conflict'].includes(x.state)).length);
  choices($('package-client'),data.clients);choices($('pickup-client'),data.clients);pickupChoices();
  $('records').replaceChildren();
  for(const op of [...state.operations].reverse()){
   const {event}=op;const entry=document.createElement('details'), title=document.createElement('summary');
   const label=event.kind==='client'?'Cliente':event.kind==='package'?'Pacote':event.kind==='notify'?'Aviso':'Retirada';
   title.textContent=label+' OFF-'+event.id.slice(0,8)+' • '+(statusLabels[op.state]||op.state);
   entry.append(title);
   const date=document.createElement('p');date.textContent='Registrado em '+new Date(event.created_at).toLocaleString('pt-BR');entry.append(date);
   const pre=document.createElement('pre');const show={...event.data};delete show.signature;delete show.revisions;
   pre.textContent=JSON.stringify(show,null,2);entry.append(pre);
   if(/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(event.data.signature||'')){const image=document.createElement('img');image.alt='Assinatura registrada na retirada';image.src=event.data.signature;image.style.maxWidth='100%';entry.append(image);}
   if(event.kind==='pickup'){const receipt=document.createElement('button');receipt.type='button';receipt.textContent='Comprovante local';receipt.addEventListener('click',()=>printReceipt(op));entry.append(receipt);}
   if(event.kind==='client'&&['review','conflict'].includes(op.state)){const finish=document.createElement('a');finish.className='button';finish.textContent='Concluir validação do cadastro online';finish.href='/offline/registration/'+event.id;finish.target='_blank';finish.rel='noopener';entry.append(finish);}
   if(op.reason){const reason=document.createElement('p');reason.textContent=op.reason;entry.append(reason);}
   if(op.state==='local'){const p=document.createElement('p');p.textContent='Salvo somente neste aparelho. Faça backup e sincronize quando houver conexão.';entry.append(p);}
   if(['review','conflict'].includes(op.state)){
    const explanation=document.createElement('p');explanation.textContent='Após concluir e conferir a operação no fluxo online, informe o código do cliente (CLIPCA), pacote (PCTPCA) ou comprovante (CMPPCA). O vínculo não cria nem cobra novamente.';
    const form=document.createElement('form'),label1=document.createElement('label'),label2=document.createElement('label'),target=document.createElement('input'),note=document.createElement('input'),button=document.createElement('button');
    label1.textContent='Código online';target.name='target';target.required=true;target.maxLength=30;label1.append(target);
    label2.textContent='Observação da conferência';note.name='note';note.required=true;note.maxLength=1000;label2.append(note);
    button.textContent='Conferir e vincular';button.className='primary';form.append(explanation,label1,label2,button);
    form.addEventListener('submit',event=>{event.preventDefault();task(async()=>{
     await sessionIdentity();const result=await api('reconcile',formData({csrf_token:identity.csrf_token,id:op.event.id,target:target.value,note:note.value}));
     await mutate(next=>{const item=next.operations.find(x=>x.event.id===op.event.id);item.state=result.state;item.reason='Vínculo conferido online.';});
     say('Registro vinculado. Histórico local e online preservados.');
    });});
    const dismiss=document.createElement('button');dismiss.type='button';dismiss.textContent='Não aplicar registro incorreto ou duplicado';
    dismiss.addEventListener('click',()=>task(async()=>{
     if(!note.value.trim())throw new Error('Informe o motivo na observação da conferência.');
     if(!confirm('Preservar o histórico e marcar este registro como não aplicado? Nenhum cadastro, pacote ou pagamento online será alterado.'))return;
     await sessionIdentity();const result=await api('dismiss',formData({csrf_token:identity.csrf_token,id:op.event.id,note:note.value}));
     await mutate(next=>{const item=next.operations.find(x=>x.event.id===op.event.id);item.state=result.state;item.reason=note.value;});
     say('Registro conferido como não aplicado. Histórico preservado.');
    }));
    form.append(dismiss);entry.append(form);
   }
   $('records').append(entry);
  }
  renderOverview();showClient('package-client','client-info');
  if(state.snapshot.contract)$('client-contract').textContent=state.snapshot.contract.label+'\n\n'+state.snapshot.contract.body;
  resetIdle();
 }
 async function append(kind,data){
  ensureReady();
  const event={id:crypto.randomUUID(),kind,created_at:new Date().toISOString(),data};
  await mutate(next=>next.operations.push({event,state:'local',reason:''}));
  say('Registro salvo neste aparelho. Faça backup protegido ao concluir o atendimento.');
 }

 function validCPF(raw){
  const value=(raw||'').replace(/\D/g,'');if(!/^\d{11}$/.test(value)||/^(\d)\1{10}$/.test(value))return false;
  for(let count=9;count<11;count++){let n=0;for(let i=0;i<count;i++)n+=Number(value[i])*(count+1-i);let digit=(n*10)%11;if(digit===10)digit=0;if(digit!==Number(value[count]))return false;}return true;
 }
 function showClient(selectId,boxId){
  if(!state)return;const c=projected().clients.find(x=>x.ref===$(selectId).value);
  $(boxId).textContent=c?[c.name,c.cpf?'CPF: '+c.cpf:'',c.email||'',c.phone||'',[c.residential_street,c.residential_number,c.residential_district,c.residential_city,c.residential_state].filter(Boolean).join(', '),c.plan?'Plano: '+c.plan.available+' créditos disponíveis na preparação':'Atendimento avulso'].filter(Boolean).join('\n'):'';
 }
 function selectedPackages(){
  const selected=new Set([...$('pickup-packages').querySelectorAll('input:checked')].map(x=>x.value));
  return projected().packages.filter(p=>selected.has(p.ref));
 }
 function currentQuote(){return OfflineFinance.quote(selectedPackages(),Object.fromEntries(new FormData($('pickup-form'))));}
 function updateQuote(){
  if(!state)return;
  $('pix-qr').replaceChildren();$('pix-code').value='';$('confirm-pickup').checked=false;
  $('offline-pix').hidden=$('offline-payment-method').value!=='Pix AI';
  const pix=state.snapshot.pix;
  $('pix-recipient').textContent=pix?.enabled?'Titular: '+pix.receiver_name+' • Chave: '+pix.key:'Pix não preparado neste ambiente. Atualize os dados online.';
  try{
   const q=currentQuote();$('pickup-form').elements.amount.value=q.total.toFixed(2);
   $('offline-totals').textContent='Pacotes: '+OfflineFinance.money(q.base)+' • Atraso: '+OfflineFinance.money(q.late)+' → Acréscimo: '+OfflineFinance.money(q.surcharge)+' → Desconto: '+OfflineFinance.money(q.discount)+' → Total a pagar: '+OfflineFinance.money(q.total);
  }catch(error){$('offline-totals').textContent=error.message;$('pickup-form').elements.amount.value='';}
 }
 function makePix(){
  const q=currentQuote(),code=OfflineFinance.pix(state.snapshot.pix,q.total),qr=qrcode(0,'M');qr.addData(code);qr.make();
  $('pix-qr').replaceChildren();
  const svg=new DOMParser().parseFromString(qr.createSvgTag({cellSize:4,margin:16}),'image/svg+xml').documentElement;
  $('pix-qr').append(document.importNode(svg,true));$('pix-code').value=code;
 }
 function renderOverview(){
  if(!state)return;const {clients,packages}=projected(),search=$('package-search').value.toLocaleLowerCase();
  $('package-list').replaceChildren();
  for(const p of packages.filter(p=>[p.public_id,p.tracking,clients.find(c=>c.ref===p.client_ref)?.name].join(' ').toLocaleLowerCase().includes(search))){
   const article=document.createElement('article'),label=document.createElement('span'),owner=clients.find(c=>c.ref===p.client_ref),fee=OfflineFinance.fees(p);
   label.textContent=(p.public_id||'Pacote local')+' • '+p.tracking+' • '+(owner?.name||'Cliente')+' • '+p.category+' • Prateleira '+p.shelf+' • '+(p.notified_at?'Aguardando retirada':'Aguardando aviso')+' • Saldo '+OfflineFinance.money(fee.total);
   article.append(label);
   if(!p.notified_at){const button=document.createElement('button');button.textContent='Registrar aviso de chegada';button.type='button';button.addEventListener('click',()=>task(async()=>{await append('notify',{package_ref:p.ref,revision:p.revision||''});say('Aviso registrado localmente. O prazo usa esta data e não será reiniciado na sincronização.');}));article.append(button);}
   $('package-list').append(article);
  }
  $('online-history').replaceChildren();for(const r of state.snapshot.history||[]){const p=document.createElement('p');p.textContent='CMPPCA-'+r.id+' • '+new Date(r.picked_at).toLocaleString('pt-BR')+' • '+r.receiver_name+' • '+r.payment_method+' • '+OfflineFinance.money(r.total_paid)+(r.payment_note?' • '+r.payment_note:'');$('online-history').append(p);}
 }
 function printReceipt(op){
  const box=$('local-receipt');box.replaceChildren();const heading=document.createElement('h2');heading.textContent='Comprovante local • '+(op.linked_id?'CMPPCA-'+op.linked_id:'OFF-'+op.event.id.slice(0,8));box.append(heading);
  const d=op.event.data;for(const value of ['Registrado em '+new Date(op.event.created_at).toLocaleString('pt-BR'),'Quem retirou: '+d.receiver_name,d.document_type+': '+d.document,'Pacotes: '+d.package_refs.join(', '),'Pagamento: '+d.payment_method,'Valor: '+OfflineFinance.money(d.amount),'Observação: '+(d.payment_note||d.notes||'—'),op.state==='linked'?'Integrado ao sistema online':'Registro local aguardando sincronização']){
   const p=document.createElement('p');p.textContent=value;box.append(p);
  }
  if(/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(d.signature||'')){const image=document.createElement('img');image.src=d.signature;image.alt='Assinatura';image.style.maxWidth='100%';box.append(image);}
  box.hidden=false;window.print();box.hidden=true;
 }
 function signaturePad(id){
  const canvas=$(id),ctx=canvas.getContext('2d');let drawing=false,signed=false;
  const point=e=>{const b=canvas.getBoundingClientRect();return [(e.clientX-b.left)*canvas.width/b.width,(e.clientY-b.top)*canvas.height/b.height];};
  canvas.addEventListener('pointerdown',e=>{e.preventDefault();drawing=true;canvas.setPointerCapture(e.pointerId);ctx.beginPath();ctx.moveTo(...point(e));});
  canvas.addEventListener('pointermove',e=>{if(drawing){ctx.lineWidth=2;ctx.lineTo(...point(e));ctx.stroke();signed=true;}});
  canvas.addEventListener('pointerup',()=>drawing=false);canvas.addEventListener('pointercancel',()=>drawing=false);
  return {signed:()=>signed,value:()=>canvas.toDataURL('image/png'),clear:()=>{ctx.clearRect(0,0,canvas.width,canvas.height);drawing=false;signed=false;}};
 }
 const clientSignature=signaturePad('client-signature');
 $('clear-client-signature').addEventListener('click',clientSignature.clear);
 $('package-search').addEventListener('input',renderOverview);
 $('package-client').addEventListener('change',()=>{showClient('package-client','client-info');category();});
 $('pickup-form').addEventListener('input',e=>{if(['surcharge_amount','surcharge_reason','discount_amount','discount_percent','payment_method','package_refs'].includes(e.target.name))updateQuote();});
 $('generate-pix').addEventListener('click',()=>{try{makePix();say('Pix gerado neste PC. Confira o crédito no banco antes de confirmar a retirada.');}catch(error){say(error.message,true);}});
 $('copy-pix').addEventListener('click',()=>task(async()=>{if(!$('pix-code').value)makePix();try{await navigator.clipboard.writeText($('pix-code').value);say('Código Pix copiado.');}catch(_){$('pix-code').select();say('Selecione o código e use Ctrl+C para copiar.');}}));
 let drawing=false,signed=false;
 const canvas=$('signature'),ctx=canvas.getContext('2d');
 function clearSignature(){ctx.clearRect(0,0,canvas.width,canvas.height);signed=false;drawing=false;}
 function point(event){const box=canvas.getBoundingClientRect();return [(event.clientX-box.left)*canvas.width/box.width,(event.clientY-box.top)*canvas.height/box.height];}
 canvas.addEventListener('pointerdown',event=>{event.preventDefault();drawing=true;canvas.setPointerCapture(event.pointerId);ctx.beginPath();ctx.moveTo(...point(event));});
 canvas.addEventListener('pointermove',event=>{if(!drawing)return;ctx.lineWidth=2;ctx.lineCap='round';ctx.lineTo(...point(event));ctx.stroke();signed=true;});
 canvas.addEventListener('pointerup',()=>{drawing=false;});canvas.addEventListener('pointercancel',()=>{drawing=false;});
 $('clear-signature').addEventListener('click',clearSignature);
 $('prepare-form').addEventListener('submit',event=>{event.preventDefault();task(async()=>{
  const password=$('new-password').value;
  if(password.length<8||password!==$('repeat-password').value)throw new Error('As senhas locais devem ser iguais e ter pelo menos 8 caracteres.');
  const snapshot=await api('prepare');identity={...snapshot};
  await prepareWorker();if(navigator.storage?.persist)await navigator.storage.persist();
  const salt=crypto.getRandomValues(new Uint8Array(16));key=await derive(password,salt);
  delete snapshot.csrf_token;
  envelope={version:1,origin:location.origin,scope:snapshot.scope,salt:bytesTo64(salt),revision:null};
  await save({scope:snapshot.scope,device:crypto.randomUUID(),snapshot,operations:[]},true);
  $('new-password').value='';$('repeat-password').value='';render();tab('records');
  say('Aparelho preparado. Agora é possível abrir esta página sem internet. Guarde sua senha e faça backup dos registros.');
 });});
 $('unlock-form').addEventListener('submit',event=>{event.preventDefault();task(async()=>{
  const row=await readVault();if(!validEnvelope(row))throw new Error('Backup local inválido ou de outro endereço.');
  const trial=await derive($('unlock-password').value,from64(row.salt));
  let decoded;
  try{decoded=JSON.parse(decoder.decode(await crypto.subtle.decrypt({name:'AES-GCM',iv:from64(row.iv),additionalData:encoder.encode(row.scope)},trial,from64(row.cipher))));}
  catch(_){throw new Error('Senha local incorreta ou arquivo danificado. Os dados não foram alterados.');}
  if(decoded.scope!==row.scope||!Array.isArray(decoded.operations)||!Array.isArray(decoded.snapshot?.clients)||!Array.isArray(decoded.snapshot?.packages))throw new Error('Dados locais incompatíveis.');
  key=trial;envelope=row;state=decoded;$('unlock-password').value='';render();tab('records');say('Dados locais desbloqueados.');
 });});
 $('client-form').addEventListener('submit',event=>{event.preventDefault();task(async()=>{
  const data=Object.fromEntries(new FormData(event.target));
  if(!state.snapshot.contract)throw new Error('Atualize os dados para preparar o contrato vigente.');
  if(!clientSignature.signed())throw new Error('Colete a assinatura do cliente.');
  if(!validCPF(data.cpf))throw new Error('CPF inválido. Confira os números.');
  data.registration_version=2;data.signature=clientSignature.value();data.contract_version=state.snapshot.contract.version;data.contract_digest=state.snapshot.contract.digest;
  if(data.cpf&&state.operations.some(x=>x.event.kind==='client'&&x.event.data.cpf===data.cpf))throw new Error('Já existe cadastro local com esse CPF.');
  await append('client',data);event.target.reset();clientSignature.clear();
 });});
 function category(){
  const data=Object.fromEntries(new FormData($('package-form'))),sum=Number(data.width)+Number(data.height)+Number(data.length);
  $('category').textContent=sum>150||Number(data.weight)>20?'Pacote acima do limite: não receber.':sum>0&&Number(data.weight)>0?((sum<=80&&Number(data.weight)<=10)?'Pequeno':'Grande')+' • Valor e cobertura do plano serão conferidos online.':'Informe peso e medidas.';
 }
 $('package-form').addEventListener('input',category);
 $('package-form').addEventListener('submit',event=>{event.preventDefault();task(async()=>{
  const data=Object.fromEntries(new FormData(event.target));
  for(const field of ['width','height','length','weight']){data[field]=Number(data[field]);if(!Number.isFinite(data[field])||data[field]<=0)throw new Error('Confira peso e medidas.');}
  if(data.width+data.height+data.length>150||data.weight>20)throw new Error('Pacote recusado: limite de 150 cm na soma e 20 kg.');
  data.tracking=data.tracking.trim().toUpperCase();
  if(state.snapshot.packages.some(p=>p.tracking?.toUpperCase()===data.tracking)||state.operations.some(x=>x.event.kind==='package'&&x.event.data.tracking===data.tracking))throw new Error('Rastreio já cadastrado nos dados locais. Confira antes de receber.');
  const client=projected().clients.find(c=>c.ref===data.client_ref),small=data.width+data.height+data.length<=80&&data.weight<=10,cost=small?1:2;
  data.plan_covered=!!(client?.plan&&Date.parse(client.plan.ends_at)>Date.now()&&client.plan.available>=cost);
  data.plan_cycle_id=data.plan_covered?client.plan.cycle_id:null;
  await append('package',data);event.target.reset();category();
 });});
 $('pickup-client').addEventListener('change',pickupChoices);
 $('pickup-form').addEventListener('submit',event=>{event.preventDefault();task(async()=>{
  const data=Object.fromEntries(new FormData(event.target));data.package_refs=[...$('pickup-packages').querySelectorAll('input:checked')].map(x=>x.value);
  if(!data.package_refs.length)throw new Error('Selecione ao menos um pacote.');
  if(!signed)throw new Error('Colete a assinatura de quem retira.');
  data.revisions={};for(const ref of data.package_refs){const p=state.snapshot.packages.find(x=>'srv:'+x.id===ref);if(p)data.revisions[ref]=p.revision;}
  data.financial_version=2;data.payment_note=data.notes||'';data.signature=canvas.toDataURL('image/png');data.amount=Number(data.amount);
  const quoted=currentQuote();if(!quoted||OfflineFinance.cents(quoted.total)!==OfflineFinance.cents(data.amount))throw new Error('Confira o total da retirada.');
  if(data.payment_method==='Pix AI'&&data.amount>0){const config=state.snapshot.pix;data.pix={key:config?.key,receiver_name:config?.receiver_name,payload:OfflineFinance.pix(config,data.amount)};}
  await append('pickup',data);event.target.reset();clearSignature();pickupChoices();
 });});
 $('refresh').addEventListener('click',()=>task(async()=>{
  await prepareWorker();await sessionIdentity();const snapshot=await api('prepare');if(snapshot.scope!==state.scope)throw new Error('Ambiente ou operador diferente.');
  delete snapshot.csrf_token;await mutate(next=>{next.snapshot=snapshot;});say('Base local atualizada. Registros de contingência preservados.');
 }));
 $('sync').addEventListener('click',()=>task(async()=>{
  await sessionIdentity();
  let total=0;
  while(true){
   const batch=state.operations.filter(x=>x.state==='local').slice(0,20);if(!batch.length)break;
   const payload=JSON.stringify({scope:state.scope,device:state.device,events:batch.map(x=>x.event)});
   const result=await api('sync',formData({csrf_token:identity.csrf_token,payload}));
   await mutate(next=>{for(const item of result.results){const op=next.operations.find(x=>x.event.id===item.id);if(op){op.state=item.state;op.reason=item.reason;op.linked_id=item.linked_id;}}});total+=batch.length;
  }
  const rank={client:0,package:1,notify:2,pickup:3};
  const pending=state.operations.filter(x=>['review','conflict'].includes(x.state)).sort((a,b)=>(rank[a.event.kind]-rank[b.event.kind])||a.event.created_at.localeCompare(b.event.created_at));
  let imported=0;
  for(let offset=0;offset<pending.length;offset+=20){
   const ids=pending.slice(offset,offset+20).map(x=>x.event.id);
   const result=await api('import',formData({csrf_token:identity.csrf_token,payload:JSON.stringify({scope:state.scope,ids})}));
   await mutate(next=>{for(const item of result.results){const op=next.operations.find(x=>x.event.id===item.id);if(op){op.state=item.state;op.reason=item.reason;op.linked_id=item.linked_id;if(item.state==='linked')imported++;}}});
  }
  const snapshot=await api('prepare');delete snapshot.csrf_token;await mutate(next=>{next.snapshot=snapshot;});
  const remaining=state.operations.filter(x=>['review','conflict'].includes(x.state)).length;
  say(total+' registros enviados. '+imported+' integrados ao sistema online. '+remaining+' pendências para revisar.');
 }));
 $('inbox').addEventListener('click',()=>task(async()=>{
  await sessionIdentity();let offset=0,count=0;
  do{
   const result=await api('inbox?offset='+offset);
   await mutate(next=>{for(const item of result.items){let op=next.operations.find(x=>x.event.id===item.id);if(op){op.state=item.state;op.reason=item.reason;op.linked_id=item.linked_id;}else next.operations.push({event:item.event,state:item.state,reason:item.reason,linked_id:item.linked_id});count++;}});
   offset=result.next_offset;
  }while(offset!==null);
  say(count+' registros consultados. Dados locais preservados.');
 }));
 $('export').addEventListener('click',()=>task(async()=>{
  const row=await readVault();const url=URL.createObjectURL(new Blob([JSON.stringify(row)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download='adelinha-offline-'+new Date().toISOString().slice(0,10)+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),5000);
  say('Backup protegido gerado. Guarde o arquivo e a senha local em locais separados.');
 }));
 $('restore').addEventListener('change',event=>task(async()=>{
  if(await readVault())throw new Error('Já há dados neste navegador. Não substitua registros locais.');
  const file=event.target.files[0];if(!file||file.size>20*1024*1024)throw new Error('Arquivo inválido ou maior que 20 MB.');
  if(navigator.onLine)await prepareWorker();
  let row;try{row=JSON.parse(await file.text());if(!validEnvelope(row))throw new Error();}catch(_){throw new Error('Backup incompatível ou de outro endereço do site.');}
  await transaction('readwrite',(s,set,abort)=>{const r=s.get('current');r.onsuccess=()=>{if(r.result){abort();return;}s.put(row,'current');};});
  envelope=row;lock();say('Backup restaurado. Digite a senha local para desbloquear.');
 }));
 $('forget').addEventListener('click',()=>task(async()=>{
  if(state.operations.some(x=>!['linked','dismissed'].includes(x.state)))throw new Error('Há registros pendentes de envio ou conferência. Faça backup e conclua os vínculos antes de remover os dados.');
  if(prompt('Digite APAGAR para remover os dados locais já conferidos.')!=='APAGAR')return;
  const previous=envelope.revision;
  await transaction('readwrite',(s,set,abort)=>{const r=s.get('current');r.onsuccess=()=>{if(r.result?.revision!==previous){abort();return;}s.delete('current');};});
  envelope=null;lock();say('Dados locais removidos. O histórico enviado ao servidor foi preservado.');
 }));
 $('lock').addEventListener('click',()=>{lock();say('Dados locais bloqueados.');});
 document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>tab(button.dataset.tab)));
 for(const event of ['pointerdown','keydown'])document.addEventListener(event,resetIdle,{passive:true});
 window.addEventListener('online',connection);window.addEventListener('offline',connection);
 window.addEventListener('pagehide',()=>{state=null;key=null;identity=null;});
 window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});
 async function boot(){
  connection();
  if(!crypto.subtle||!window.indexedDB)throw new Error('Use navegador com HTTPS e armazenamento local habilitado.');
  db=await new Promise((resolve,reject)=>{const request=indexedDB.open(DB,1);request.onupgradeneeded=()=>request.result.createObjectStore('vault');request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
  envelope=await readVault();lock();
 }
 boot().catch(error=>say(error.message||'Não foi possível abrir o armazenamento local.',true));
})();