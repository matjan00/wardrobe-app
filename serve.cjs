const http=require('http'),fs=require('fs'),path=require('path');
const root=path.join(__dirname,'docs'),types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.png':'image/png','.webp':'image/webp','.webmanifest':'application/manifest+json','.jpg':'image/jpeg','.svg':'image/svg+xml'};
http.createServer((q,r)=>{let p=decodeURIComponent(q.url.split('?')[0]);if(p.endsWith('/'))p+='index.html';
const f=path.join(root,p);if(!f.startsWith(root))return r.writeHead(403).end();
fs.readFile(f,(e,d)=>{if(e)return r.writeHead(404).end('not found');r.writeHead(200,{'Content-Type':types[path.extname(f)]||'application/octet-stream'});r.end(d)})}).listen(5200);
