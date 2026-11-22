/* Flow service worker.
   - The app shell (page, script, styles, icons) opens without a network.
   - Audio (/audio/…) is fetched whole once and kept, then any byte range is served from the cache, so
     word pronunciations and example sentences play instantly on a weak connection and work offline.
   - API calls always go to the network; the page keeps its own small offline queue for reviews. */
'use strict';
const SHELL = 'flow-shell-__ASSET__';  // filled in by the server: changes whenever next.js or next.css does
const AUDIO = 'flow-audio-v1';
const SHELL_FILES = ['/', '/next.css?v=__ASSET__', '/next.js?v=__ASSET__', '/manifest.webmanifest', '/icon-192.png', '/apple-touch-icon.png'];
const AUDIO_MAX = 160;

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== SHELL && k !== AUDIO).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
  if (url.pathname.startsWith('/audio/')) { e.respondWith(audio(req, url)); return; }
  if (req.mode === 'navigate') {
    if (url.pathname !== '/' || url.search) return;  // the classic site and other pages stay network-only
    e.respondWith(fetch(req).then(r => { if (r.ok) caches.open(SHELL).then(c => c.put('/', r.clone())); return r; })
      .catch(() => caches.match('/')));
    return;
  }
  if (/^\/(next\.(js|css)|manifest\.webmanifest|icon-\d+\.png|apple-touch-icon\.png)$/.test(url.pathname)) {
    e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(r => {
      if (r.ok) { const copy = r.clone(); caches.open(SHELL).then(c => c.put(req, copy)); }
      return r;
    })));
  }
});

self.addEventListener('message', e => {
  if (e.data && e.data.type === 'prefetch' && Array.isArray(e.data.urls)) {
    e.waitUntil((async () => {
      const cache = await caches.open(AUDIO);
      for (const u of e.data.urls.slice(0, 40)) {
        const url = new URL(u, self.location.origin);
        if (url.origin !== self.location.origin || !url.pathname.startsWith('/audio/')) continue;
        if (await cache.match(url.href)) continue;
        try { const r = await fetch(url.href); if (r.ok && r.status === 200) await cache.put(url.href, r); } catch (err) { break; }
      }
      await trim(cache);
    })());
  }
});

async function audio(req, url) {
  const cache = await caches.open(AUDIO);
  let full = await cache.match(url.href);
  if (!full) {
    try {
      const r = await fetch(url.href);  // the whole file, without Range: files are small (0.1–1 MB)
      if (!r.ok || r.status !== 200) return r;
      await cache.put(url.href, r.clone());
      trim(cache);
      full = r;
    } catch (err) {
      return new Response('', { status: 504, statusText: 'offline' });
    }
  }
  const range = req.headers.get('Range');
  if (!range) return full;
  const buf = await full.arrayBuffer();
  const m = /bytes=(\d*)-(\d*)/.exec(range);
  const size = buf.byteLength;
  let start = m && m[1] ? Number(m[1]) : 0;
  let end = m && m[2] ? Number(m[2]) : size - 1;
  if (m && !m[1] && m[2]) { start = Math.max(0, size - Number(m[2])); end = size - 1; }
  end = Math.min(end, size - 1);
  if (start > end || start >= size) return new Response('', { status: 416, headers: { 'Content-Range': `bytes */${size}` } });
  return new Response(buf.slice(start, end + 1), {
    status: 206,
    headers: { 'Content-Type': full.headers.get('Content-Type') || 'audio/mp4', 'Content-Range': `bytes ${start}-${end}/${size}`,
               'Content-Length': String(end - start + 1), 'Accept-Ranges': 'bytes' },
  });
}

async function trim(cache) {
  const keys = await cache.keys();
  for (let k = 0; k < keys.length - AUDIO_MAX; k++) await cache.delete(keys[k]);
}
