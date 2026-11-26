'use strict';
/* Flow — one learning loop: listen → read → check → use it → review what you saved,
   steered by the knowledge graph (18 grammar nodes) and AI. See NEXT.md. */
(function () {
  const view = document.getElementById('view');
  const bar = document.getElementById('bar');
  const sheetEl = document.getElementById('sheet');
  const sheetCard = document.getElementById('sheetCard');
  const toastEl = document.getElementById('toast');
  const S = { user: null, csrf: '', meta: null, home: null, homeFresh: false, placed: '', guest: load('flow-next-guest'), lastRoute: '', voice: load('flow-next-voice') || 'us-f' };
  const VOICE_LABELS = { 'us-f': '美音 · 女', 'us-m': '美音 · 男', 'uk-f': '英音 · 女', 'uk-m': '英音 · 男' };
  const STEP = { listen: '听', read: '读', check: '理解', output: '用出来' };
  const STEPS = Object.keys(STEP);
  const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- utilities ---------- */
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
  // 「AI 生成」标识（2026-11-25，《人工智能生成合成内容标识办法》）：AI 写的、给学员看的内容都带它，样式在 99-ai-mark.css。
  // aiMark(note)：放在一块内容最上面的一行，note 是后面的一句小字（可省），如「未经人工审核」；aiTag()：卡片信息行里的小标签。
  function aiTag() { return '<span class="ai-mark" title="这部分由人工智能生成，可能有错，仅供参考">AI 生成</span>'; }
  // 合成的声音（文章录音、AI 朗读、AI 角色和考官的话、单词和例句读音）：《标识办法》要求合成人声在交互界面上有显著提示。
  // 2026-11-25 用户：提示要有，但不抢眼——不再每个喇叭旁边一个胶囊，一页一行小灰字，按播放时它和播放键在同一屏（语流 B7 的最低
  // 要求：不用点开就看得见、≥12px、浅色深色对比度 ≥4.5、字里有「AI」和「合成」或者「AI 朗读」）。aiVoiceNote(text, tag, cls)：
  // 这一行（样式在 99-ai-mark.css）；喇叭多、页面要滚动的地方（例句、长单词表）每个喇叭再加一个 aiBadge()，读屏的名字写「（AI 朗读）」。
  // 每个会放合成声音的页面部分都要调用 aiVoiceNote（tests/test_ai_mark.py 查）。
  function aiVoiceNote(text, tag, cls) { tag = tag || 'p'; return `<${tag} class="ai-voice-note${cls ? ' ' + cls : ''}" title="这段声音由人工智能合成，不是真人录音">${esc(text || '读音由 AI 合成')}</${tag}>`; }
  function aiBadge() { return '<i class="ai-badge" aria-hidden="true">AI</i>'; }
  // a speaker in a list of many (单词表、对比的句子、用得上的说法、改写的几种说法): 「（AI 朗读）」 in its name, a faint 「AI」 on it
  function sayIcon(attrs, label) { return `<button class="icon-btn has-ai" type="button" ${attrs} aria-label="${esc(label)}（AI 朗读）">${ICON.speak}${aiBadge()}</button>`; }
  function aiMark(note) { return `<div class="ai-line">${aiTag()}${note ? `<span>${esc(note)}</span>` : ''}</div>`; }
  function load(k) { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch (e) { return null; } }
  function save(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } }
  function rid(prefix) { return prefix + '-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10); }
  function toast(msg) { toastEl.textContent = msg; toastEl.classList.add('show'); toast.at = Date.now(); clearTimeout(toast.t); toast.t = setTimeout(() => toastEl.classList.remove('show'), 2400); }
  // An AI request still running after 15 s (the AI busy, a queue at the gateway): a line under the button just pressed,
  // 「AI 还在听…」 for a recording, 「AI 还在想…」 otherwise, gone when the answer comes. Background fills (example
  // sentences while reviewing) have no button and show nothing. Buttons pressed by click, tap or keyboard alike.
  const AI_WAIT_MS = 15000, AI_QUIET = /^\/api\/next\/vocab\/examples/;
  let lastPress = { el: null, at: 0 };
  document.addEventListener('click', e => { const b = e.target && e.target.closest && e.target.closest('button, .btn, [role=button]'); if (b) lastPress = { el: b, at: Date.now() }; }, true);
  function aiWait(path, body) {
    if (!body || typeof body.request_id !== 'string' || AI_QUIET.test(path)) return () => {};
    const btn = Date.now() - lastPress.at < 1500 ? lastPress.el : null;
    if (!btn || btn.closest('[data-own-wait]')) return () => {};  // the page shows its own progress (口语情景: seconds, resend)
    let line = null;
    const t = setTimeout(() => {
      if (!btn.isConnected) return;
      // under the row of buttons when the button sits in one, else right under the button
      let host = btn, up = btn.parentElement;
      if (up && getComputedStyle(up).display.includes('flex') && !getComputedStyle(up).flexDirection.startsWith('column')) host = up;
      line = document.createElement('p');
      line.className = 'ai-wait small';
      line.setAttribute('role', 'status');
      line.textContent = body.audio ? 'AI 还在听，可能要多等一会儿' : 'AI 还在想，可能要多等一会儿';
      host.insertAdjacentElement('afterend', line);
    }, AI_WAIT_MS);
    return () => { clearTimeout(t); if (line) line.remove(); };
  }
  // Each account's AI calls of the day (ai_quota.header, 语流 B7 #405): an AI answer says "<remaining>/<limit>/<level>".
  // Once a day, when under a fifth is left (low) or the last one was just used (out), one line says so; 「我的 → 设置 →
  // AI 用量」 has the rest. A refused call says its own words (the error), so nothing more then.
  const AIQ = { told: '' };
  function aiQuotaSeen(h, ok) {
    const m = /^(\d*)\/(\d*)\/(ok|low|out)$/.exec(h || '');
    if (!m || !ok || !m[2] || m[3] === 'ok') return;
    const mark = new Date().toISOString().slice(0, 10) + ':' + m[3];  // the count's day starts at 00:00 UTC (08:00 Beijing)
    let told = AIQ.told; try { told = localStorage.getItem('flow.aiQuotaTold') || told; } catch (e) { /* the memory copy */ }
    if (told === mark) return;
    AIQ.told = mark; try { localStorage.setItem('flow.aiQuotaTold', mark); } catch (e) { /* the memory copy */ }
    setTimeout(() => toast(m[3] === 'out' ? `今天的 ${m[2]} 次 AI 用完了，北京时间早上 8 点重置；学材料、背单词和做题照常能用`
      : `今天的 AI 还剩 ${m[1]} 次，北京时间早上 8 点重置`), 800);  // after the answer is on the page
  }
  // One request to the server: an error becomes a message the page can show, and a session that ended asks to sign in
  // again (not for a preload: quiet). Returns the answer parsed (j) and as text (t, for the data layer to share).
  async function request(path, body, quiet) {
    const opt = { credentials: 'same-origin', headers: {} };
    if (uiLang() === 'en') opt.headers['X-Flow-Lang'] = 'en';  // the server answers in English too (ui_lang.py)
    if (body !== undefined) { opt.method = 'POST'; opt.headers['Content-Type'] = 'application/json'; if (S.csrf) opt.headers['X-CSRF-Token'] = S.csrf; opt.body = JSON.stringify(body); }
    let r;
    const waiting = aiWait(path, body);
    try { r = await fetch(path, opt); } catch (x) { waiting(); noteIssue('api', '网络连接失败', path.split('?')[0]); const e = new Error('网络连接失败，请检查网络'); e.network = true; throw e; }
    const t = await r.text().catch(() => '');
    waiting();
    aiQuotaSeen(r.headers.get('X-Flow-AI-Quota'), r.ok);
    let j = {}; try { j = t ? JSON.parse(t) : {}; } catch (x) { /* not JSON: an error page */ }
    if (!r.ok) {
      if (r.status >= 500) noteIssue('api', `服务器返回 ${r.status}`, path.split('?')[0]);  // 4xx are answers (a wrong password …), not faults
      // No message of ours (an nginx page while the server restarts, a gateway timeout, an upload too large): plain words,
      // no status code (UI audit 2026-11-25: 「请求失败（502）」 on every page during a release). The server's own messages stay.
      const plain = r.status === 413 ? '内容太大，传不上去，换小一点的再试' : r.status >= 500 || r.status === 429 ? '服务暂时有点忙，请稍后重试' : '没有成功，请稍后重试';
      const e = new Error(j.error || plain); e.status = r.status; e.field = j.field; e.code = j.code;
      // Signed out on the server (30 days away, a password change, 退出所有设备): say so and offer to sign in again.
      if (r.status === 401 && S.user && !quiet && !/^\/api\/(login|register|auth\/)/.test(path)) {
        S.user = null; S.csrf = ''; e.message = '登录已过期，请重新登录';
        if (sheetEl.hidden) setTimeout(() => openLogin('登录已过期，请重新登录。登录后会回到这一页。'), 0);
      }
      // under 14 without a guardian's agreement: the AI on the learner's own words waits for it (81-privacy.js)
      if (r.status === 403 && j.code === 'guardian' && !quiet) setTimeout(() => guardianSheet(), 0);
      // 数据存放在香港 or 用户协议 not agreed on the server while this page thought they were (drawn from the copy kept on
      // the phone, or withdrawn on another device; feedback #1, 2026-11-25: 单词 stuck on 「重试」): read the account again
      // and let the router show the consent page (one line, 「同意，继续学习」, then 导出 / 注销 / 退出), once in a while
      if (r.status === 403 && j.code === 'storage' && S.user && !quiet && Date.now() - (request.held || 0) > 3000) {
        request.held = Date.now();
        setTimeout(() => { dataForget(); S.home = null; route(); }, 0);
      }
      // the day's AI stop (ai_routes.day_full: 429 code ai_day_full, back at 08:00 Beijing): also what still works.
      // AI voice says its own line (01-audio-offline.js).
      if (j.code === 'ai_day_full' && !path.startsWith('/api/next/tts')) e.message = (j.error || '今天的 AI 用量已满，北京时间早上 8 点恢复。') + zhEn('学材料、背单词、复习和做题照常能用。', ' Texts, words, review and exercises still work.');
      throw e;
    }
    return { j, t };
  }
  // Reading goes through the data layer (05-data.js: shared, kept a short while, preloaded). Sending waits until the
  // server has said who is signed in (the page may first be drawn from the copy kept on the phone), and empties the
  // data layer's memory, since what was sent may change what the pages show.
  async function api(path, body) {
    if (body === undefined) return dataGet(path);
    await DATA.ready;
    const { j } = await request(path, body);
    dataForget();
    return j;
  }
  const ICON = {
    play: '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>',
    speak: '<svg viewBox="0 0 24 24"><path d="M4 10v4h4l5 4V6L8 10zM16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/></svg>',
    eye: '<svg viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
    star: '<svg viewBox="0 0 24 24"><path d="m12 3 2.8 5.8 6.2.9-4.5 4.4 1 6.2L12 17.4l-5.5 2.9 1-6.2L3 9.7l6.2-.9z"/></svg>',
    trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>',
    stop: '<svg viewBox="0 0 24 24"><rect x="6.5" y="6.5" width="11" height="11" rx="2"/></svg>',
  };
  const playIcon = (on, size) => (on ? ICON.stop : ICON.play).replace('<svg', `<svg width="${size || 18}" height="${size || 18}" fill="currentColor"`);
  const skeleton = () => '<div class="skeleton" aria-hidden="true"><i class="t"></i><i class="s"></i><i class="b"></i><i></i><i></i><i class="s"></i></div>';
  const doneRing = '<svg class="done-ring" viewBox="0 0 72 72" aria-hidden="true"><circle cx="36" cy="36" r="30"/><path d="M24 37l8 8 16-17"/></svg>';
  function level() { return (S.home && S.home.level) || (S.guest && S.guest.level) || 'B1'; }
  function hasProfile() { return S.user ? !!(S.home && S.home.profile) || !!(S.guest && S.guest.level) : !!(S.guest && S.guest.level); }
  function guestQuery(first) {
    if (S.user) return '';
    const g = S.guest || {};
    return (first ? '?' : '&') + 'level=' + encodeURIComponent(g.level || 'B1') + (g.themes && g.themes.length ? '&themes=' + encodeURIComponent(g.themes.join(',')) : '');
  }
  function enter(el) { if (!el) return; el.classList.remove('enter'); void el.offsetWidth; el.classList.add('enter'); }
  const ST_LABEL = { untouched: '还没接触', met: '读到过', used: '用出来过', watch: '需要留意', solid: '做题已验证' };  // next_service.STATUS_LABEL
  function nodeChip(n) { const st = n.status || 'untouched'; return `<a class="node-chip st st-${esc(st)}" href="#/graph/${encodeURIComponent(n.id || n.node)}" title="${esc(ST_LABEL[st] || '')}" aria-label="${esc(n.title)}，${esc(ST_LABEL[st] || '')}">${esc(n.title)}</a>`; }
  // Input: coarse pointer = finger. Hover-only affordances and keyboard hints are adjusted for it.
  const TOUCH = matchMedia('(pointer: coarse)').matches;
  const isTyping = e => !!(e && e.target && e.target.closest && e.target.closest('input:not([type=checkbox]):not([type=radio]),textarea,select,[contenteditable]'));
  const srEl = document.getElementById('sr');
  function announce(t) { if (!srEl || !t) return; srEl.textContent = ''; setTimeout(() => { srEl.textContent = t; }, 40); }
  // Scroll so an element sits just below the sticky header (and the study step bar when there is one).
  function bringIntoView(el, smooth) {
    if (!el) return;
    const steps = view.querySelector('.steps');
    const off = bar.offsetHeight + (steps && !steps.contains(el) ? steps.offsetHeight : 0) + 10;
    scrollTo({ top: Math.max(0, el.getBoundingClientRect().top + scrollY - off), behavior: smooth === false || REDUCED ? 'auto' : 'smooth' });
  }

