const CACHE='adelinha-offline-shell-v3';
const SHELL='/static/offline/index.html';
const ASSETS=[SHELL,'/static/offline/offline.css','/static/offline/offline.js','/static/offline/finance.js','/static/offline/qrcode.js'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('adelinha-offline-shell-')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);
 if(event.request.method!=='GET'||url.origin!==self.location.origin)return;
 if(url.pathname.startsWith('/offline/api/'))return;
 if(ASSETS.includes(url.pathname)){
  event.respondWith(caches.match(url.pathname).then(cached=>cached||fetch(event.request)));
 }else if(event.request.mode==='navigate'&&url.pathname==='/offline/'){
  event.respondWith(fetch(event.request).then(response=>response.status>=500?caches.match(SHELL):response).catch(()=>caches.match(SHELL)));
 }
});