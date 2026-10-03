// Run before every publish:  node tools/release.cjs "What changed, in one line"
// Bumps the version everywhere (app, version.json, sw.js) and refreshes the offline file list,
// so phones show "Update available" with that note.
const fs = require('fs');
const path = require('path');
const docs = path.join(__dirname, '..', 'docs');
const setArg = process.argv.find((x) => x.startsWith('--set='));
const note = process.argv.slice(2).filter((x) => !x.startsWith('--')).join(' ').trim();

const vj = JSON.parse(fs.readFileSync(path.join(docs, 'version.json'), 'utf8'));
const [a, b, c] = vj.version.split('.').map(Number);
const next = setArg ? setArg.slice(6) : `${a}.${b}.${c + 1}`;
vj.version = next;
vj.date = new Date().toISOString().slice(0, 10);
vj.notes = note ? [{ version: next, date: vj.date, text: note }, ...(vj.notes || [])].slice(0, 20) : vj.notes || [];
fs.writeFileSync(path.join(docs, 'version.json'), JSON.stringify(vj, null, 1));

let html = fs.readFileSync(path.join(docs, 'index.html'), 'utf8');
html = html.replace(/const APP_VERSION='[\d.]+'/, `const APP_VERSION='${next}'`);
fs.writeFileSync(path.join(docs, 'index.html'), html);

const list = [];
(function walk(dir) {
  for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, f.name);
    if (f.isDirectory()) { if (f.name !== 'img') walk(p); }          // photos are cached as they're viewed
    else if (!['sw.js', 'version.json'].includes(f.name)) list.push(path.relative(docs, p).split(path.sep).join('/'));
  }
})(docs);
let sw = fs.readFileSync(path.join(docs, 'sw.js'), 'utf8');
sw = sw.replace(/const VERSION = 'wardrobe-v[\d.]+'/, `const VERSION = 'wardrobe-v${next}'`);
sw = sw.replace(/\/\/ FILES-START[\s\S]*\/\/ FILES-END/, `// FILES-START\nconst FILES = ${JSON.stringify(['./', ...list])};\n// FILES-END`);
fs.writeFileSync(path.join(docs, 'sw.js'), sw);
console.log(`Released ${next}${note ? ' — ' + note : ''} (${list.length + 1} files cached offline)`);
