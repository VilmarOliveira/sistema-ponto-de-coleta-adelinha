/* Shared offline money/Pix rules; server revalidates every imported operation. */
(function(root){
 'use strict';
 const cents=value=>{const n=Number(String(value??'0').replace(',','.'));if(!Number.isFinite(n)||n<0)throw new Error('Confira os valores informados.');return Math.round((n+Number.EPSILON)*100);};
 const money=value=>new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}).format(value);
 const day=value=>{const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Sao_Paulo',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(value));const get=k=>parts.find(p=>p.type===k).value;return Date.UTC(Number(get('year')),Number(get('month'))-1,Number(get('day')))/86400000;};
 function fees(p,at=new Date()){
  const base=cents(p.base_price),lateDays=p.notified_at?Math.max(0,day(at)-day(p.notified_at)-3):0;
  const settled=cents(p.settled||0),due=Math.max(0,base+lateDays*50-settled),remainingBase=Math.max(0,base-settled);
  return {base:remainingBase/100,late_fee:(due-remainingBase)/100,late_days:lateDays,total:due/100,prepaid:Number(p.prepaid||0)};
 }
 function quote(packages,form,at=new Date()){
  const totals=packages.map(p=>fees(p,at)),base=totals.reduce((n,p)=>n+cents(p.base),0),late=totals.reduce((n,p)=>n+cents(p.late_fee),0);
  const surcharge=cents(form.surcharge_amount||0),reason=(form.surcharge_reason||'').trim();
  if(surcharge&&!reason)throw new Error('Informe o motivo do acréscimo.');
  const discountValue=cents(form.discount_amount||0),percent=Number(String(form.discount_percent||0).replace(',','.'));
  if(!Number.isFinite(percent)||percent<0||percent>100)throw new Error('Desconto percentual deve ficar entre 0 e 100.');
  if(String(form.discount_amount||'').trim()&&String(form.discount_percent||'').trim())throw new Error('Escolha desconto em valor ou porcentagem.');
  const original=base+late+surcharge,discount=percent?Math.round(original*percent/100):discountValue;
  if(discount>original)throw new Error('O desconto não pode superar o total.');
  return {base:base/100,late:late/100,surcharge:surcharge/100,discount:discount/100,original:original/100,total:(original-discount)/100,packages:totals};
 }
 const field=(id,value)=>{const n=new TextEncoder().encode(value).length;if(n>99)throw new Error('Campo Pix muito longo.');return id+String(n).padStart(2,'0')+value;};
 function pix(config,amount){
  if(!config?.enabled||!config.key||!config.receiver_name)throw new Error('Atualize os dados conectado e configure o Pix manual deste ambiente.');
  const value=cents(amount);if(value<=0)throw new Error('Pix exige valor maior que zero.');
  const key=String(config.key),name=String(config.receiver_name).normalize('NFKD').replace(/[^\x00-\x7F]/g,'').trim().toUpperCase().slice(0,25);
  if(!name||key.length>77||/[^\x20-\x7E]/.test(key))throw new Error('Nome ou chave Pix inválidos.');
  const merchant=field('00','BR.GOV.BCB.PIX')+field('01',key);
  const raw=field('00','01')+field('26',merchant)+field('52','0000')+field('53','986')+field('54',(value/100).toFixed(2))+field('58','BR')+field('59',name)+field('60','FRANCA')+field('62',field('05','***'))+'6304';
  let crc=65535;for(const byte of new TextEncoder().encode(raw)){crc^=byte<<8;for(let n=0;n<8;n++)crc=crc&32768?((crc<<1)^4129)&65535:(crc<<1)&65535;}
  return raw+crc.toString(16).toUpperCase().padStart(4,'0');
 }
 const api={cents,money,fees,quote,pix,day};
 root.OfflineFinance=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);