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
  // 全英文界面: the small tag in an info line stays 「AI 生成」 (D2: Chinese first; where both do not fit, the Chinese alone);
  // on the line above AI content (aiMark) it reads 「AI 生成 · AI-generated」. Its title is in the page's language.
  function aiTag() { return aiPill(' translate="no"'); }
  function aiPill(attrs) { return `<span class="ai-mark"${attrs} title="${zhEn('这部分由人工智能生成，可能有错，仅供参考', 'Written by AI. It may be wrong; use it as a guide only')}">AI 生成</span>`; }
  // 合成的声音（文章录音、AI 朗读、AI 角色和考官的话、单词和例句读音）：《标识办法》要求合成人声在交互界面上有显著提示。
  // 2026-11-25 用户：提示要有，但不抢眼——不再每个喇叭旁边一个胶囊，一页一行小灰字，按播放时它和播放键在同一屏（语流 B7 的最低
  // 要求：不用点开就看得见、≥12px、浅色深色对比度 ≥4.5、字里有「AI」和「合成」或者「AI 朗读」）。aiVoiceNote(text, tag, cls)：
  // 这一行（样式在 99-ai-mark.css）；喇叭多、页面要滚动的地方（例句、长单词表）每个喇叭再加一个 aiBadge()，读屏的名字写「（AI 朗读）」。
  // 每个会放合成声音的页面部分都要调用 aiVoiceNote（tests/test_ai_mark.py 查）。
  function aiVoiceNote(text, tag, cls) { tag = tag || 'p'; return `<${tag} class="ai-voice-note${cls ? ' ' + cls : ''}" title="这段声音由人工智能合成，不是真人录音">${esc(text || '读音由 AI 合成')}</${tag}>`; }
  function aiBadge() { return '<i class="ai-badge" aria-hidden="true">AI</i>'; }
  // a speaker in a list of many (单词表、对比的句子、用得上的说法、改写的几种说法): 「（AI 朗读）」 in its name, a faint 「AI」 on it
  function sayIcon(attrs, label) { return `<button class="icon-btn has-ai" type="button" ${attrs} aria-label="${esc(label)}（AI 朗读）">${ICON.speak}${aiBadge()}</button>`; }
  function aiMark(note) { return `<div class="ai-line">${aiPill('')}${note ? `<span>${esc(note)}</span>` : ''}</div>`; }
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

  /* ---------- 界面语言 (全英文界面, 语流 E1, 2026-11-26; docs/english-ui.md) ---------- */
  // Chinese is the default and stays so: English only when the learner chose it (我的 → 使用习惯, 07-lang.js), never
  // from the browser's language. The choice is read once, before anything is drawn; switching reloads the page. Until
  // the English pages are done it opens only on the 内测版 and on a test server (localhost).
  //
  // Two ways a page gets its English:
  //  - zhEn('中文', 'English') where the text is made, for words that never reach the page as text (a title, a confirm(),
  //    a canvas) or whose word order changes. zhEn('中文') alone looks the Chinese up in the tables below.
  //  - the tables (enTable(), the 01-en-*.js parts): what is drawn on the page is put into English as it appears, text
  //    and the attributes in EN_ATTRS, by the exact Chinese (spaces folded). Numbers in it are {n} in the key, any other
  //    part {x}; the English names them {1}, {2} … in order, and {1|day|days} picks the singular when that number is 1.
  //    ' · ' joins parts that are looked up one by one.
  // Chinese meant to stay Chinese in English mode (a word's meaning, a translation, what the learner wrote) sits in an
  // element with data-zh: it is left as it is, read with a Chinese voice (markEnglish in 02-shell.js marks it), and the
  // check for missing English (tools/ui_test.py english) does not count it. translate="no" also leaves a part alone.
  // These are written the old way on purpose (iPhones on iOS 12–14: no Intl.PluralRules, no ?. or ??).
  function uiLangOpen() {
    return document.documentElement.dataset.channel === 'beta' || /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
  }
  function uiLang() {
    if (!uiLang.v) uiLang.v = uiLangOpen() && load('flow-lang') === 'en' ? 'en' : 'zh';
    return uiLang.v;
  }
  function zhEn(zh, en) { return uiLang() === 'en' ? (en != null ? en : enText(zh)) : zh; }
  function enTable(rows) {
    const all = enTable.all || (enTable.all = {});
    Object.keys(rows).forEach(k => { all[k.replace(/\s+/g, ' ').trim()] = rows[k]; });
    enTable.ready = null;  // the patterns are built again on the next look-up
  }
  const ZH_CHAR = /[㐀-鿿豈-﫿]/;
  const EN_NUM = /\d+(?:\.\d+)?/g;
  // the table split into exact keys and patterns ({x}, or {n} next to other text), built once after the last enTable()
  function enReady() {
    if (enTable.ready) return enTable.ready;
    const exact = {}, pats = [], outs = {}, all = enTable.all || {};
    Object.keys(all).forEach(k => {
      if (ZH_CHAR.test(all[k])) outs[all[k]] = 1;  // English that keeps some Chinese (「AI 生成 · AI-generated」): already done
      if (k.indexOf('{x}') < 0) { exact[k] = all[k]; return; }
      const parts = k.split(/(\{[nx]\})/), lit = parts.filter((p, i) => i % 2 === 0 && p);
      const re = new RegExp('^' + parts.map((p, i) => (i % 2 ? (p === '{n}' ? '(\\d+(?:\\.\\d+)?)' : '(.+?)') : p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))).join('') + '$');
      pats.push({ re, en: all[k], lit: lit.slice().sort((a, b) => b.length - a.length)[0] || '', size: lit.join('').length });
    });
    pats.sort((a, b) => b.size - a.size);  // the most specific first: more fixed text, fewer parts left open
    enTable.ready = { exact, pats, outs };
    return enTable.ready;
  }
  function enFill(en, vals) {
    return en.replace(/\{(\d+)(?:\|([^|{}]*)\|([^|{}]*))?\}/g, (m, i, one, many) => {
      const v = vals[Number(i) - 1] == null ? '' : vals[Number(i) - 1];
      return one == null ? v : Number(v) === 1 ? one : many;
    });
  }
  // The English for one piece of Chinese text, or null when the tables have none.
  function enLookup(s) {
    if (!ZH_CHAR.test(s)) return null;
    const tb = enReady();
    if (Object.prototype.hasOwnProperty.call(tb.exact, s)) return tb.exact[s];
    if (tb.outs[s]) return null;
    const nums = s.match(EN_NUM);
    if (nums) { const k = s.replace(EN_NUM, '{n}'); if (Object.prototype.hasOwnProperty.call(tb.exact, k)) return enFill(tb.exact[k], nums); }
    for (let i = 0; i < tb.pats.length; i++) {
      const p = tb.pats[i];
      if (p.lit && s.indexOf(p.lit) < 0) continue;
      const m = p.re.exec(s);
      if (m) return enFill(p.en, m.slice(1).map(enPart));
    }
    if (s.indexOf(' · ') >= 0) {
      const parts = s.split(' · '), out = parts.map(x => (ZH_CHAR.test(x) ? enLookup(x.trim()) : x));
      if (out.every(x => x != null)) return out.join(' · ');
    }
    // a heading read with its back mark (「‹使用习惯」, what a screen reader is told on a new page) or an arrow after it
    const mk = /^([‹›<>←→↗·•✓✦]+\s*)?([\s\S]*?)(\s*[‹›<>←→↗·•✓✦]+)?$/.exec(s);
    if (mk && (mk[1] || mk[3]) && mk[2] && mk[2] !== s) { const en = enLookup(mk[2]); if (en != null) return (mk[1] || '') + en + (mk[3] || ''); }
    return null;
  }
  // a part a pattern caught: its Chinese looked up too, the spaces and ' · ' around it kept (「 · 新词」 → " · New words")
  function enPart(x) {
    if (!ZH_CHAR.test(x)) return x;
    const m = /^([\s·]*)([\s\S]*?)([\s·]*)$/.exec(x), en = enLookup(m[2]);
    return en == null ? x : m[1] + en + m[3];
  }
  function enText(zh) { const s = String(zh == null ? '' : zh).replace(/\s+/g, ' ').trim(), en = enLookup(s); return en == null ? zh : en; }

  // ---- the page in English as it is drawn
  const EN_ATTRS = ['aria-label', 'placeholder', 'title', 'alt', 'aria-valuetext', 'aria-roledescription'];
  const EN_SET = new WeakMap();  // what this wrote into a text node or an attribute, so it is not looked up again
  // text left alone: Chinese meant to stay, and what a field holds (a field's placeholder and name are still put into English)
  const enSkip = el => !!(el && el.closest && el.closest('[data-zh],[translate="no"],script,style,textarea,[contenteditable="true"],noscript'));
  const enKeep = el => !!(el && el.closest && el.closest('[data-zh],[translate="no"]'));
  function enTextNode(n) {
    const v = n.nodeValue;
    if (!v || !ZH_CHAR.test(v) || EN_SET.get(n) === v || enSkip(n.parentElement)) return;
    const en = enLookup(v.replace(/\s+/g, ' ').trim());
    if (en == null) return;
    const out = (/^\s/.test(v) ? ' ' : '') + en + (/\s$/.test(v) ? ' ' : '');
    EN_SET.set(n, out); n.nodeValue = out;
    const el = n.parentElement;  // marked Chinese while it was (02-shell.js markEnglish): English now
    if (el && el.hasAttribute('data-lz')) { el.removeAttribute('data-lz'); el.removeAttribute('lang'); }
  }
  function enAttr(el, a) {
    const v = el.getAttribute(a);
    if (!v || !ZH_CHAR.test(v) || enKeep(el)) return;
    const done = EN_SET.get(el);
    if (done && done[a] === v) return;
    const en = enLookup(v.replace(/\s+/g, ' ').trim());
    if (en == null) return;
    const d = done || {}; d[a] = en; EN_SET.set(el, d); el.setAttribute(a, en);
  }
  function enTree(root) {
    if (!root) return;
    if (root.nodeType === 3) { enTextNode(root); return; }
    if (root.nodeType !== 1 || enKeep(root) || /^(SCRIPT|STYLE|NOSCRIPT)$/.test(root.tagName)) return;
    const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode: x => (x.nodeType === 1 && /^(SCRIPT|STYLE|NOSCRIPT)$/.test(x.tagName) || x.nodeType === 1 && (x.hasAttribute('data-zh') || x.getAttribute('translate') === 'no')
        ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
    });
    let n = root;
    do {
      if (n.nodeType === 3) enTextNode(n);
      else for (let i = 0; i < EN_ATTRS.length; i++) if (n.hasAttribute(EN_ATTRS[i])) enAttr(n, EN_ATTRS[i]);
    } while ((n = w.nextNode()));
  }
  if (uiLang() === 'en') {
    document.documentElement.lang = 'en';
    // Run in the same turn as the change (a MutationObserver's callback comes before the next paint): no Chinese flashes.
    new MutationObserver(ms => {
      for (let i = 0; i < ms.length; i++) {
        const m = ms[i];
        if (m.type === 'childList') for (let j = 0; j < m.addedNodes.length; j++) enTree(m.addedNodes[j]);
        else if (m.type === 'characterData') enTextNode(m.target);
        else if (m.type === 'attributes') enAttr(m.target, m.attributeName);
      }
    }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: EN_ATTRS });
    // the page shell (next.html), once every table is in: right after next.js has run, before anything is painted
    Promise.resolve().then(() => { enTree(document.body); document.title = enText(document.title); });
  }

  // ---- numbers, counts, dates and lists, in the page's language
  // qty(3, '天', 'day') → 「3 天」 / "3 days"; the English plural is the word with an s unless given (qty(2, '个', 'box', 'boxes'))
  function qty(n, zh, en, enMany) { return uiLang() === 'en' ? numText(n) + ' ' + (Number(n) === 1 ? en : (enMany || en + 's')) : n + ' ' + zh; }  // i18n: keep
  // 1234 → "1,234" in English; Chinese keeps the number as it was written
  function numText(n) {
    if (uiLang() !== 'en' || typeof n !== 'number' || !isFinite(n)) return String(n);
    const p = String(n).split('.');
    return p[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (p[1] ? '.' + p[1] : '');
  }
  const EN_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const EN_DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'], ZH_DAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];  // i18n: keep
  const asDate = d => (d instanceof Date ? d : new Date(typeof d === 'string' && /^\d{4}-\d\d-\d\d$/.test(d) ? d + 'T00:00:00' : d));
  // 「11月26日」 / "Nov 26"; with the year: 「2026年11月26日」 / "Nov 26, 2026"
  function dayMonth(d, withYear) {
    d = asDate(d);
    if (uiLang() === 'en') return EN_MONTHS[d.getMonth()] + ' ' + d.getDate() + (withYear ? ', ' + d.getFullYear() : '');
    return (withYear ? d.getFullYear() + '年' : '') + (d.getMonth() + 1) + '月' + d.getDate() + '日';  // i18n: keep
  }
  function weekday(d) { d = asDate(d); return (uiLang() === 'en' ? EN_DAYS : ZH_DAYS)[d.getDay()]; }
  // 「听、读、写」 / "listen, read, and write"
  function listJoin(items) {
    if (uiLang() !== 'en') return items.join('、');  // i18n: keep
    if (items.length < 3) return items.join(' and ');
    return items.slice(0, -1).join(', ') + ', and ' + items[items.length - 1];
  }
  /* ---------- 语流's own icons (B9, 2026-11-26; the user: 有些地方纯文字有点太干巴巴了……做一些原创图标上去) ----------
     One set for every page: a 24 grid, a 1.6 line, round ends and corners. A shape with class "w" is a soft patch behind
     the main outline, class "t" a thin line; nothing is coloured: an icon takes the colour of the text around it (99-icons.css).
       fi('mic')        the icon, 22px, in the text colour: in front of a row's name, in a tool tile
       fiTile('bell')   the icon in a 34px soft square: the rows of a settings list
     Icons are decoration (aria-hidden): the row's own words name it. Add a new one here, not in a page's own file. */
  const FI = {
    retry: '<rect class="w" x="4" y="4" width="16" height="16" rx="4.5"/><rect x="4" y="4" width="16" height="16" rx="4.5"/><path d="M8.5 12.3l2.4 2.4 4.6-5.2"/>',  // 错题和句型复习
    bookx: '<path class="w" d="M6 4h11a1 1 0 0 1 1 1v15H7a1 1 0 0 1-1-1z"/><path d="M6 4h11a1 1 0 0 1 1 1v15H7a1 1 0 0 1-1-1z"/><path d="M10 9.5l4 4m0-4-4 4"/>',  // 错题本
    graph: '<circle class="w" cx="12" cy="6" r="2.6"/><circle cx="12" cy="6" r="2.6"/><circle cx="6" cy="17.5" r="2.6"/><circle cx="18" cy="17.5" r="2.6"/><path d="M10.8 8.3 7.3 15.2M13.2 8.3l3.5 6.9M8.6 17.5h6.8"/>',  // 知识图谱
    shuffle: '<path d="M4 7.5h3c2 0 3.2 1 4.2 3l1.6 3c1 2 2.2 3 4.2 3H20M4 16.5h3c1 0 1.8-.3 2.5-.9M20 7.5h-3c-1 0-1.8.3-2.5.9"/><path d="M17.5 5l2.5 2.5-2.5 2.5M17.5 14l2.5 2.5-2.5 2.5"/>',  // 混合练习
    flag: '<path class="w" d="M6.5 5H17l-2.5 4 2.5 4H6.5z"/><path d="M6.5 21V5H17l-2.5 4 2.5 4H6.5"/>',  // 语法起点小测
    read: '<path class="w" d="M3.5 6.5c2.8-1 5.7-1 8.5.5v12c-2.8-1.5-5.7-1.5-8.5-.5z"/><path d="M12 7c-2.8-1.5-5.7-1.5-8.5-.5v12c2.8-1 5.7-1 8.5.5 2.8-1.5 5.7-1.5 8.5-.5v-12c-2.8-1-5.7-1-8.5.5zm0 0v12"/>',  // 轻松读
    layers: '<path class="w" d="M12 4l8 4.5-8 4.5-8-4.5z"/><path d="M12 4l8 4.5-8 4.5-8-4.5z"/><path d="M4 12.5l8 4.5 8-4.5M4 16.5l8 4.5 8-4.5"/>',  // 全部材料
    docpen: '<path class="w" d="M6 3h8l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1V7z"/><path d="M14 3v4h4M8.5 12.5h7M8.5 16.5h4.5"/>',  // 写作、贴一篇
    chat: '<path class="w" d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-7l-4 3v-3H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"/><path d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-7l-4 3v-3H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"/><path d="M8 11h.01M12 11h.01M16 11h.01"/>',  // 口语情景
    mic: '<rect class="w" x="9" y="3" width="6" height="11" rx="3"/><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/>',  // 发音
    stack: '<rect class="w" x="4" y="8" width="13" height="12" rx="2.5"/><rect x="4" y="8" width="13" height="12" rx="2.5"/><path d="M8 4.5h10a2 2 0 0 1 2 2V16M8 14h5"/>',  // 背单词、新词
    venn: '<circle class="w" cx="9" cy="12" r="5.5"/><circle cx="9" cy="12" r="5.5"/><circle cx="15" cy="12" r="5.5"/>',  // 词汇辨析
    cal: '<rect class="w" x="4" y="5" width="16" height="15" rx="3"/><rect x="4" y="5" width="16" height="15" rx="3"/><path d="M4 10h16M8.5 3v4M15.5 3v4M8.5 14.5h3.5"/>',  // 背词计划
    gauge: '<path class="w" d="M4 16.5a8 8 0 0 1 16 0z"/><path d="M4 16.5a8 8 0 0 1 16 0"/><path d="M12 16.5l3.5-5M4 20h16"/>',  // 测词汇量
    exam: '<rect class="w" x="5" y="4.5" width="14" height="16.5" rx="2.5"/><rect x="5" y="4.5" width="14" height="16.5" rx="2.5"/><path d="M9 3h6v3H9zM8.5 11.5h7M8.5 15.5h4.5"/>',  // 考试练习
    hex: '<path d="M12 3 19.8 7.5v9L12 21l-7.8-4.5v-9z"/><path class="t" d="M12 12V3M12 12l7.8 4.5M12 12l-7.8 4.5"/><path class="w" d="M12 7.5l3.4 6.4-6.9-.2z"/><path d="M12 7.5l3.4 6.4-6.9-.2z"/>',  // 能力 (the tab's icon: a web, three axes, a shape; the user chose it)
    spark: '<path class="w" d="M11 4l1.9 4.9 4.9 1.9-4.9 1.9L11 17.6l-1.9-4.9-4.9-1.9 4.9-1.9z"/><path d="M11 4l1.9 4.9 4.9 1.9-4.9 1.9L11 17.6l-1.9-4.9-4.9-1.9 4.9-1.9z"/><path d="M18.5 16v4M16.5 18h4"/>',  // 今天建议
    again: '<circle class="w" cx="12" cy="12" r="7.5"/><path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5v4.2h-4.2"/>',  // 复习
    book: '<path class="w" d="M6 4h11a1 1 0 0 1 1 1v13H7.5A1.5 1.5 0 0 0 6 19.5z"/><path d="M6 19.5V5a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v13H7.5a1.5 1.5 0 0 0 0 3H18"/><path d="M10 8.5h4.5"/>',  // 词书
    trend: '<path class="w" d="M4 20l5-7 4 3 7-9v13z"/><path d="M4 16.5l5-5.5 4 3 7-8"/><path d="M15.5 6H20v4.5"/>',  // 我的进步
    week: '<rect class="w" x="4" y="5" width="16" height="15" rx="3"/><rect x="4" y="5" width="16" height="15" rx="3"/><path d="M8.5 16v-3M12 16V9.5M15.5 16v-4.5"/>',  // 周报
    target: '<circle class="w" cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.5"/><path d="M12 12h.01"/>',  // 学习目标
    cap: '<path class="w" d="M12 5l9 4.5-9 4.5-9-4.5z"/><path d="M12 5l9 4.5-9 4.5-9-4.5z"/><path d="M7 12v4c1.5 1.4 3.2 2 5 2s3.5-.6 5-2v-4M21 9.5V15"/>',  // 水平
    calok: '<rect class="w" x="4" y="5" width="16" height="15" rx="3"/><rect x="4" y="5" width="16" height="15" rx="3"/><path d="M4 10h16M8.5 3v4M15.5 3v4M9 15l2 2 4-4"/>',  // 每天的目标
    voice: '<path class="w" d="M4 10h3.5L12 6v12l-4.5-4H4z"/><path d="M4 10h3.5L12 6v12l-4.5-4H4z"/><path d="M15.5 9.5a4 4 0 0 1 0 5M18 7a7.5 7.5 0 0 1 0 10"/>',  // 朗读声音
    sliders: '<path d="M5 8h8.5M18.5 8H19M5 16h.5M10.5 16H19"/><circle class="w" cx="16" cy="8" r="2.4"/><circle cx="16" cy="8" r="2.4"/><circle class="w" cx="8" cy="16" r="2.4"/><circle cx="8" cy="16" r="2.4"/>',  // 使用习惯
    bell: '<path class="w" d="M6.5 16v-5a5.5 5.5 0 0 1 11 0v5l1.5 2h-14z"/><path d="M6.5 16v-5a5.5 5.5 0 0 1 11 0v5l1.5 2h-14z"/><path d="M10.5 20.5h3"/>',  // 提醒
    compass: '<circle class="w" cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="8"/><path d="M15.2 8.8l-1.9 4.5-4.5 1.9 1.9-4.5z"/>',  // 新手引导
    people: '<circle class="w" cx="9" cy="9" r="3"/><circle cx="9" cy="9" r="3"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0M15.5 6.3a3 3 0 0 1 0 5.4M17.3 14.7a5 5 0 0 1 3.2 4.3"/>',  // 班级
    shield: '<path class="w" d="M12 3.5l7 2.5v5.5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M12 3.5l7 2.5v5.5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M9.2 12l2 2 3.6-3.8"/>',  // 账号和隐私
    help: '<circle class="w" cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="8"/><path d="M9.8 9.8a2.3 2.3 0 1 1 3.3 2.1c-.7.4-1.1.9-1.1 1.6M12 16.4h.01"/>',  // 帮助
    bars: '<rect class="w" x="4" y="5" width="16" height="15" rx="3"/><path d="M7.5 17v-5M12 17V8M16.5 17v-3"/>',  // 统计
    inbox: '<path class="w" d="M5 15.5h14V19a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1z"/><path d="M12 4v9.5m0 0l-3.5-3.5m3.5 3.5l3.5-3.5M5 16v3a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3"/>',  // 反馈
  };
  function fi(name, cls) { return `<svg class="fi${cls ? ' ' + cls : ''}" viewBox="0 0 24 24" aria-hidden="true">${FI[name] || ''}</svg>`; }
  function fiTile(name) { return `<span class="fi-tile" aria-hidden="true">${fi(name)}</span>`; }
  /* ---------- speech (with word boundaries for read-along highlighting) ---------- */
  // WeChat's built-in browser (and some other in-app browsers) cannot use the browser voice, and plays sound only when it
  // starts inside a tap; the way out it offers is 「在浏览器打开」.
  const WECHAT = /MicroMessenger/i.test(navigator.userAgent);
  // the voice a page falls back to: in a browser its own, in 语流's apps the system's (iOS, Android, desktop: B3, 2026-11-25)
  const SYS_VOICE = () => (window.FlowApp ? '系统自带的声音' : '浏览器的声音');
  function noSound(what) { noteIssue('audio', what + (WECHAT ? '（微信）' : '')); toast(WECHAT ? `微信里${what}：点右上角「···」，选「在浏览器打开」就能听` : `这个浏览器${what}，换 Safari 或 Chrome 试试`); }
  const TTS = {
    ok: 'speechSynthesis' in window, rate: Number(load('flow-next-rate')) || 1, voice: null, token: 0,
    // the browser's English voice in the accent of 朗读声音 (S.voice: us-… or uk-…)
    pick() {
      if (!this.ok) return null;
      const uk = (S.voice || '').startsWith('uk'), vs = speechSynthesis.getVoices().filter(v => /^en[-_]/i.test(v.lang));
      const pref = uk ? ['Daniel', 'Kate', 'Serena', 'Google UK English Female', 'Google UK English Male', 'Microsoft Sonia', 'Microsoft Libby']
        : ['Samantha', 'Google US English', 'Microsoft Aria', 'Microsoft Jenny', 'Karen', 'Daniel', 'Google UK English Female'];
      this.voice = pref.map(n => vs.find(v => v.name.includes(n))).find(Boolean) || vs.find(v => (uk ? /en[-_]GB/i : /en[-_]US/i).test(v.lang)) || vs[0] || null;
      this.accent = uk ? 'uk' : 'us';
      return this.voice;
    },
    // A sentence goes to the server voice whenever it is on (SV below: CosyVoice, made once and stored, works in WeChat
    // too), word highlighting or not: the owner hears the browser voice as a robot (2026-11-25), so a text is lit sentence
    // by sentence rather than read by it. onword counts only where the browser voice reads. o: {pack, voice, title}.
    say(text, onend, onword, o) {
      if (SV.on() && text && text.length <= SV.MAX) { SV.say(text, onend, { ...(o || {}), onword }); return; }
      this.browser(text, onend, onword, null, null, o && o.rate);
    },
    // A word on its own (and a card's example) is said at 1x: 语速 is for the whole text and 伴读 only (the owner,
    // 2026-11-26: at 1.5x a tapped word came out fast too). o.rate does the same for the server voice and CLIP below.
    word(text, onend) { this.say(text, onend, null, { rate: 1 }); },
    // onfail: the sentence was not said (no voice, or iOS dropped it twice); without it, onend is called then, so whoever
    // waits on the sentence goes on (a whole text pauses instead: LONG). onstart: the voice has begun this sentence.
    browser(text, onend, onword, onfail, onstart, rate) {
      LONG.other();
      if (!this.ok) { noSound('不能用电脑朗读的声音'); if (onfail) onfail(); return; }
      const t = ++this.token, busy = speechSynthesis.speaking || speechSynthesis.pending;
      if (busy) speechSynthesis.cancel();
      // iOS sometimes drops an utterance spoken right after cancel() (语流 07 on the iPhone 17e and iPad simulators,
      // 2026-11-25): it ends at once without starting, or it never starts. So: cancel only what is speaking, speak a beat
      // later when something was cancelled, and take an end without a start as a dropped sentence: try it once more,
      // then give up (onfail) rather than count it as said (a whole text would race to its end and be marked heard).
      let tries = 0;
      const say = () => {
        if (t !== this.token) return;
        const u = new SpeechSynthesisUtterance(text), uk = (S.voice || '').startsWith('uk');
        u.lang = uk ? 'en-GB' : 'en-US'; u.rate = rate || this.rate; const v = this.voice && this.accent === (uk ? 'uk' : 'us') ? this.voice : this.pick(); if (v) u.voice = v;
        let started = false, ended = false, poll = 0, heard = 0, reach = -1;
        const give = () => { ended = true; clearTimeout(watch); clearInterval(poll); if (t !== this.token) return; if (onfail) onfail(); else if (onend) onend(); };  // final: an end the cancel brings later is not counted
        const again = () => { clearTimeout(watch); clearInterval(poll); if (t !== this.token) return; if (++tries < 2) setTimeout(say, 250); else give(); };
        const done = () => { if (ended) return; ended = true; clearInterval(poll); if (t === this.token && onend) onend(); };
        // Word boundaries say how far the voice really got (each word as it is said): kept whether or not words are lit
        const words = [...text.matchAll(/\S+/g)], lastWord = words.length ? words[words.length - 1].index : 0;
        u.onboundary = e => {
          if (e.name === 'sentence') return;
          heard = Date.now(); reach = Math.max(reach, e.charIndex);
          if (onword && t === this.token) onword(e.charIndex);
        };
        u.onstart = () => {
          started = true; clearTimeout(watch); if (t === this.token && onstart) onstart();
          // Started, then never said it ended. Two kinds (语流 B5's runs, 2026-11-25), told apart by the word boundaries:
          // - the voice went quiet without an end (speaking false): after half a second the sentence counts as said;
          // - the voice says "speaking" on and on: with the words reported up to the last one and then nothing for a
          //   moment, it was said (end not reported); stuck part-way (an iPad offline: two words, then nothing, the next
          //   sentence pending for ever) it was not: stop it and let the text wait at that sentence, saying why.
          //   A voice that reports no words at all is let go after the longest the sentence could take.
          let quiet = 0;
          const rate = this.rate || 1, t0 = Date.now(), lull = Math.max(2500, 2000 / rate);
          const cap = t0 + Math.max(8000, words.length * 700 / rate + 3000);
          poll = setInterval(() => {
            if (t !== this.token || ended) { clearInterval(poll); return; }
            if (!speechSynthesis.speaking && !speechSynthesis.pending) { if (++quiet >= 2) done(); return; }
            quiet = 0;
            const now = Date.now();
            if (heard && reach >= lastWord && now - heard > 1500 / rate) { clearInterval(poll); speechSynthesis.cancel(); done(); return; }  // all said
            if ((heard && reach < lastWord && now - heard > lull) || now > cap) { clearInterval(poll); speechSynthesis.cancel(); give(); }  // stuck
          }, 250);
        };
        u.onend = () => { clearTimeout(watch); if (t !== this.token || ended) return; if (started) done(); else again(); };
        u.onerror = e => { if (e && /interrupted|canceled/.test(e.error || '')) { clearTimeout(watch); clearInterval(poll); return; } if (!ended) again(); };  // ours: stopped, or a new sentence
        // A browser with speechSynthesis but no voice to speak with (WeChat on Android) neither starts nor fails: after
        // 2.5 s without a start, say so (and stop counting on it) instead of waiting in silence. One that has voices but
        // did not start this time (an iPad offline, 语流 B5's run 2026-11-25) is no reason to send anyone to another
        // browser: a whole text says why at its sentence (onfail), a single sentence asks for one more tap.
        const watch = setTimeout(() => {
          if (t !== this.token || started) return;
          speechSynthesis.cancel();
          if (!speechSynthesis.getVoices().length) { this.ok = false; noSound('不能用电脑朗读的声音'); } else if (!onfail) toast(`${SYS_VOICE()}这次没读出来，再点一次试试`);
          give();
        }, 2500);
        try { speechSynthesis.speak(u); } catch (e) { again(); }  // refused outright: as a dropped sentence
      };
      if (busy) setTimeout(say, 60); else say();
    },
    stop() { this.token++; if (this.ok) speechSynthesis.cancel(); SV.note(''); if (SV.active) { SV.active = false; CLIP.stop(); } },
    can() { return this.ok || SV.on(); },  // some voice can say a sentence here
  };
  if (TTS.ok) speechSynthesis.onvoiceschanged = () => TTS.pick();

  /* ---------- server voice (tts_service): what the browser would say, in CosyVoice, made once and stored for everyone ---------- */
  // The first tap on a sentence asks the server for it (made then, 1–4 s, or already stored: at once); the file is played
  // on the short-clip player, which the first tap anywhere has unlocked (WeChat plays only sound started that way).
  // One address book for every page (听, 读, 跟读, 口语, 雅思…): a sentence is asked for once in a voice, and the answer is
  // kept on this phone for 30 days (at most 600), so what was heard before plays offline too (sw.js keeps the files). A
  // sentence of the learner's own article goes with its pack, so its file is the owner's only (/audio/own/).
  // While a sentence is being made a line says so (after 0.6 s); when the browser voice has to read instead, one line
  // says why (today's share used, offline, the network, too slow), once per reason while the page is open.
  const SV = {
    MAX: 1500, urls: new Map(), active: false, off: '', told: new Set(), KEY: 'flow-sv-urls', KEEP: 600, DAYS: 30, SLOW: 20000,
    on() { const s = S.home && S.home.session; return !!(s && s.tts) && !this.off; },
    key(text, o) { return ((o && o.voice) || S.voice || 'us-f') + '|' + ((o && o.pack) || '') + '|' + text; },
    hash(k) {  // a short name for the address book (cyrb53)
      let a = 0xdeadbeef, b = 0x41c6ce57;
      for (let i = 0; i < k.length; i++) { const c = k.charCodeAt(i); a = Math.imul(a ^ c, 2654435761); b = Math.imul(b ^ c, 1597334677); }
      a = Math.imul(a ^ (a >>> 16), 2246822507) ^ Math.imul(b ^ (b >>> 13), 3266489909); b = Math.imul(b ^ (b >>> 16), 2246822507) ^ Math.imul(a ^ (a >>> 13), 3266489909);
      return (b >>> 0).toString(36) + (a >>> 0).toString(36);
    },
    kept() {
      if (!this._kept) { const o = load(this.KEY) || {}, cut = Date.now() - this.DAYS * 864e5; for (const k of Object.keys(o)) if (!Array.isArray(o[k]) || o[k][1] < cut) delete o[k]; this._kept = o; }
      return this._kept;
    },
    keep(k, u) {
      const o = this.kept(); o[this.hash(k)] = [u, Date.now()];
      const ks = Object.keys(o); if (ks.length > this.KEEP) ks.sort((x, y) => o[x][1] - o[y][1]).slice(0, ks.length - this.KEEP).forEach(x => delete o[x]);
      clearTimeout(this._save); this._save = setTimeout(() => save(this.KEY, o), 400);
    },
    // -> Promise of the sentence's address; rejects with an Error whose .code says why (off, cap, import_cap, busy,
    // guest, store, gateway, offline, net). Online the server is always asked (a stored sentence answers at once); the
    // address kept on the phone is used when it cannot be reached.
    url(text, o) {
      const k = this.key(text, o);
      if (this.urls.has(k)) return this.urls.get(k);
      // No connection at all: the address kept on this device at once, or 'offline' at once, rather than a request that
      // cannot go out (each sentence of a whole text waited 1–2 s under 「正在准备朗读第 N 句…」, B3's offline run 2026-11-26)
      if (navigator.onLine === false) {
        const old = this.kept()[this.hash(k)];
        if (old) return Promise.resolve(old[0]);
        return Promise.reject(Object.assign(new Error('离线中'), { code: 'offline' }));
      }
      const p = (async () => {
        await DATA.ready;
        try {
          const u = (await request('/api/next/tts', { text, voice: (o && o.voice) || S.voice, ...(o && o.pack ? { pack: o.pack } : {}) }, true)).j.url;  // not api(): it empties the data layer
          this.keep(k, u); return u;
        } catch (e) {
          const old = this.kept()[this.hash(k)];
          if (e.network && old) return old[0];
          const err = new Error(e.message); err.server = e.message;
          err.code = e.network ? (navigator.onLine === false ? 'offline' : 'net') : (e.code || (e.status >= 500 ? 'gateway' : 'other'));
          // the day's AI stop (ai_day_full) is not switched off here: sentences made already still come from the server
          if (err.code === 'off' || err.code === 'cap') this.off = err.code;  // today's share used (or switched off): the browser voice from now on
          throw err;
        }
      })();
      this.urls.set(k, p); p.catch(() => this.urls.delete(k));  // a failure is asked again next time
      return p;
    },
    // what is made already, in one request (an article's sentences; an import is made in the background after importing)
    async have(texts, o) {
      if (!this.on() || !texts.length) return 0;
      try {
        await DATA.ready;
        const r = await request('/api/next/tts/have', { voice: S.voice, texts, ...(o && o.pack ? { pack: o.pack } : {}) }, true);
        let n = 0;
        r.j.urls.forEach((u, i) => { if (!u) return; n += 1; const k = this.key(texts[i], o); if (!this.urls.has(k)) this.urls.set(k, Promise.resolve(u)); this.keep(k, u); });
        return n;
      } catch (e) { return 0; }
    },
    // one line on why the browser voice reads this time; once per reason while the page is open
    why(e) {
      const code = (e && e.code) || 'other';
      this.lines = this.lines || {};
      const v = SYS_VOICE();
      const line = this.lines[code] || { offline: `离线中，这句还没存到本机，先用${v}`, net: `网络不好，这句先用${v}`, slow: `自然人声这次生成得太慢，先用${v}`,
        guest: `登录后能听 AI 朗读（自然人声），现在先用${v}`, off: `AI 朗读（自然人声）暂时没开，先用${v}`,
        ai_day_full: `今天的 AI 用量已满，北京时间早上 8 点恢复；新的句子先用${v}，已经生成过的照常放`,
        ai_paused: `你的 AI 功能暂停中，新的句子先用${v}，已经生成过的照常放` }[code]
        || (e && e.server) || `AI 朗读（自然人声）这次没生成出来，先用${v}`;
      this.lines[code] = line;
      if (!this.told.has(code)) { this.told.add(code); toast(line); noteIssue('audio', '服务器朗读退回浏览器声音', code); }
      return line;
    },
    slow(p) { return Promise.race([p, new Promise((ok, no) => setTimeout(() => no(Object.assign(new Error('slow'), { code: 'slow' })), this.SLOW))]); },
    // 「正在准备朗读…」 over the page, from 0.6 s until the sentence is ready (or something else speaks)
    note(text) {
      let el = document.getElementById('svWait');
      if (!text) { if (el) el.hidden = true; return; }
      if (!el) { el = document.createElement('div'); el.id = 'svWait'; el.className = 'sv-wait'; el.setAttribute('role', 'status'); document.body.appendChild(el); }
      el.textContent = text; el.hidden = false;
    },
    async say(text, onend, o) {
      o = o || {};
      const t = ++TTS.token; if (TTS.ok) speechSynthesis.cancel();
      const k = this.key(text, o), ready = this.urls.has(k);
      const late = ready ? 0 : setTimeout(() => { if (t === TTS.token) this.note('正在准备朗读…'); }, 600);
      let u = null, err = null;
      try { u = await this.slow(this.url(text, o)); } catch (e) { err = e; }
      clearTimeout(late);
      if (t !== TTS.token) return;  // stopped, or something else spoke, while the sentence was being made
      this.note('');
      if (!u) { this.why(err); TTS.browser(text, onend, o.onword); return; }
      CLIP.play(u, 0, 1e6, text, () => { this.active = false; if (onend) onend(); }, null, { url: u, from: 0, to: Infinity, title: o.title ? zhEn(o.title) : zhEn('语流', 'Flow'), rate: o.rate });  // the lock screen: in the page's language
      this.active = true; TTS.token = t;  // CLIP.play stops the browser voice (a new token); keep this one current
    },
  };
  // Words of one sentence as spans that know their character offset, so boundary events can light them up.
  function wordSpans(sentence, cls, extra) {
    let html = '', off = 0;
    sentence.split(/([A-Za-z]+(?:'[A-Za-z]+)?)/).forEach((part, k) => {
      if (k % 2 === 0) html += esc(part);
      else html += `<span class="${cls(part)}" data-c="${off}" data-w="${esc(part)}"${extra || ''}>${esc(part)}</span>`;
      off += part.length;
    });
    return html;
  }
  function lightWord(container, charIndex) {
    let cur = null;
    container.querySelectorAll('[data-c]').forEach(el => { if (Number(el.dataset.c) <= charIndex) cur = el; });
    container.querySelectorAll('.cur').forEach(el => el.classList.remove('cur'));
    if (cur) cur.classList.add('cur');
  }

  /* ---------- two lines for audio: this server first (fastest from mainland China), then the media domain ---------- */
  // S.home.session.media = {base: '<media domain>/audio', version} when the server keeps audio in R2 (flow/media.py).
  function mediaAlt(url) {
    const m = S.home && S.home.session && S.home.session.media;
    // server-voice files, a learner's own articles' voice (private: never asked of another host) and word clips (.aac, cut
    // by this server from a sprite) are not in R2
    if (!m || !m.base || !/^\/audio\//.test(url || '') || /^\/audio\/(tts|own)\//.test(url) || /\.aac(\?|$)/.test(url)) return '';
    return `${m.base}/${url.split('?')[0].slice(7).replace(/\.mp4$/, '.m4a')}?v=${encodeURIComponent(m.version)}`;
  }
  const mainDown = () => Date.now() - (S.mediaMainDown || 0) < 120000;  // after a failure, the other line for 2 minutes
  async function mediaJSON(url) {
    const alt = mediaAlt(url);
    if (!(alt && mainDown())) {
      try { const r = await fetch(url); if (r.ok) return await r.json(); } catch (e) { /* this server did not answer */ }
      if (!alt) throw new Error('no audio timing');
      S.mediaMainDown = Date.now();
    }
    const r = await fetch(alt); if (!r.ok) throw new Error('no audio timing');
    return r.json();
  }
  // Point an <audio> at this server; if it fails, or waits more than 8 s while playing, switch once to the media
  // domain, keeping the position and whether it was playing (a.dataset.want).
  function mediaSrc(a, url) {
    const alt = mediaAlt(url);
    a.dataset.src = url; a.dataset.alt = alt; a.dataset.line = alt && mainDown() ? 'alt' : 'main';
    if (!a.dataset.armed) {
      a.dataset.armed = '1';
      a.addEventListener('error', () => mediaSwap(a));
      a.addEventListener('waiting', () => { clearTimeout(a.stallTimer); a.stallTimer = setTimeout(() => mediaSwap(a), 8000); });
      a.addEventListener('playing', () => clearTimeout(a.stallTimer));
      a.addEventListener('pause', () => clearTimeout(a.stallTimer));
    }
    a.preload = 'auto'; a.src = a.dataset.line === 'alt' ? alt : PRELOAD.url(url);  // this server: the preloaded copy if there is one
  }
  function mediaSwap(a) {
    clearTimeout(a.stallTimer);
    if (!a.dataset.alt || a.dataset.line === 'alt') return false;
    S.mediaMainDown = Date.now();
    // where it was; a file that failed before it loaded starts where it was asked to (a._from: a clip, a sentence)
    const at = a.readyState ? a.currentTime || 0 : a._from || 0, play = a.dataset.want === '1';
    a.dataset.line = 'alt'; a.src = a.dataset.alt; a.load();
    a.addEventListener('loadedmetadata', () => { try { a.currentTime = at; } catch (e) { /* not seekable yet */ } if (play) a.play().catch(() => {}); }, { once: true });
    return true;
  }
  // Both lines failed (or there is only one): nothing more to try for this file.
  const mediaGaveUp = a => !a.dataset.alt || a.dataset.line === 'alt';
  // Recordings and word sounds are AAC (.mp4, .m4a, .aac). A device that cannot decode it (a Linux desktop without its
  // codec, 语流 C3, 2026-11-25) has them read sentence by sentence in AI 朗读 instead, and is told why once, rather than
  // 「音频暂时没加载出来，稍后再点一次」 for a file that can never play there.
  // Only the question with the codec tells: a browser answers 「audio/mp4」 from the container alone (WebKitGTK says
  // 'maybe' with just GStreamer's mp4 demuxer and no AAC decoder, C3), so that one says nothing.
  let AAC = (() => {
    try { return document.createElement('audio').canPlayType('audio/mp4; codecs="mp4a.40.2"') !== ''; }
    catch (e) { return true; }
  })();
  let aacTold = false;
  function noAac() {
    if (aacTold) return; aacTold = true;
    noteIssue('audio', '这台设备放不了 AAC 录音', '');
    toast(SV.on() ? '这台设备放不了录音的格式，改用 AI 朗读一句一句读' : '这台设备放不了录音的格式，先用浏览器的声音读');
  }

  /* ---------- narration: pre-generated Kokoro audio + timings (sentence exact, words estimated) ---------- */
  const NAR = {
    audio: new Audio(), meta: null, key: '', raf: 0, stopAt: null, onTick: null, onEnd: null, aac: AAC,
    async load(id, voice, version) {
      if (!AAC) { noAac(); return false; }  // as a text without a recording: sentence by sentence
      const key = voice + '/' + id + '@' + version;
      if (this.key === key && this.meta) return true;
      this.stop(); this.meta = null; this.key = '';
      try {
        this.meta = await mediaJSON(`/audio/${voice}/${encodeURIComponent(id)}.json?v=${version}`); this.key = key;
        const net = this.net = `/audio/${voice}/${encodeURIComponent(id)}.mp4?v=${version}`;
        mediaSrc(this.audio, net);  // the copy in memory, when it was preloaded
        PRELOAD.warm(net).then(b => { if (b && this.net === net && this.audio.paused && this.audio.getAttribute('src') === net) this.audio.src = b; });
        return true;
      } catch (e) { return false; }
    },
    play(from, to, onTick, onEnd) {
      if (!AAC) { this.onEnd = onEnd; this.noFormat(); return; }  // found out before (the file would not decode): no try
      LONG.other();
      this.stopLoop(); this.stopAt = to; this.onTick = onTick; this.onEnd = onEnd; this.paused = false;
      const a = this.audio, asked = a.src;
      this.name();
      claim(a); a.playbackRate = TTS.rate; a.preservesPitch = true; a.dataset.want = '1'; a._from = from;
      try { a.currentTime = from; } catch (e) { /* not seekable yet */ }
      // Refused (WeChat: not inside a tap): say how to hear it. A file that fails is tried on the other line first
      // (mediaSwap changes the source, and that play() is the one that counts); only when none is left, give up.
      // A source that cannot be played (NotSupportedError) is left to the 'error' listener: it tells a missing file from
      // one this device cannot decode (noFormat) before saying anything.
      a.play().catch(e => {
        if (e && e.name === 'NotAllowedError') { noSound('没有放出声音'); this.finish(); return; }
        if (a.src !== asked || !mediaGaveUp(a)) return;
        if (e && e.name === 'NotSupportedError' && !a.error) return;  // the 'error' listener comes next and decides
        this.failed();
      });
      const loop = () => {
        const t = this.audio.currentTime;
        if (this.onTick) this.onTick(t);
        if ((this.stopAt != null && t >= this.stopAt) || this.audio.ended) { this.audio.pause(); this.finish(); return; }
        this.raf = requestAnimationFrame(loop);
      };
      this.raf = requestAnimationFrame(loop);
    },
    finish() { this.stopLoop(); this.audio.dataset.want = ''; this.paused = false; MS.release('nar'); const cb = this.onEnd; this.onEnd = null; this.onTick = null; if (cb) cb(); },
    // the lock screen and the Dynamic Island: 「语流 · 标题」, play/pause, and previous/next sentence while a whole text plays
    name() {
      const id = (this.key.split('/')[1] || '').split('@')[0]; let m = null;
      try { m = MAT[id]; } catch (e) { /* the study page's cache (20-study.js) */ }
      MS.claim('nar', zhEn('语流 · ' + ((m && m.title) || '朗读')), {
        play: () => this.resume(), pause: () => this.audio.pause(), stop: () => { this.stop(); MINI.end(); },
        previoustrack: this.stopAt == null ? () => this.step(-1) : null, nexttrack: this.stopAt == null ? () => this.step(1) : null });
    },
    resume() { if (this.audio.dataset.want === '1') this.audio.play().catch(() => {}); },
    // previous / next sentence of a whole text (the page follows: onTick lights the sentence playing)
    step(d) {
      if (this.stopAt != null || !this.meta) return;
      const ss = this.meta.sentences, t = this.audio.currentTime;
      let i = ss.findIndex(x => t < x.e + 0.25); if (i < 0) i = ss.length - 1;
      if (d < 0 && t - ss[i].s > 1.5) d = 0;  // well into a sentence: back to its start first, as players do
      const j = Math.max(0, Math.min(ss.length - 1, i + d));
      try { this.audio.currentTime = ss[j].s; } catch (e) { /* not seekable yet */ }
    },
    gaveUp() { if (!this.raf && !this.onEnd) return; noteIssue('audio', '全文录音没加载出来', this.net ? this.net.split('?')[0] : ''); toast('音频暂时没加载出来，稍后再点一次'); this.finish(); },
    // Both lines failed: a file this device cannot decode (「not supported」 with the file there: noFormat), or one that
    // did not come (gaveUp). 「not supported」 is also what a missing file says, so the server is asked first.
    failed() {
      const e = this.audio.error, net = this.net;
      if (e && e.code === 4 && net && AAC) { fetch(net, { method: 'HEAD', credentials: 'same-origin' }).then(r => (r.ok ? this.noFormat() : this.gaveUp()), () => this.gaveUp()); return; }
      this.gaveUp();
    },
    // The file came (the server has it) and still would not play: this device cannot decode it, whatever canPlayType
    // said. From now on as with no AAC (NAR.load says no recording), and a whole text playing goes on sentence by sentence.
    noFormat() {
      AAC = false; this.aac = false; noAac();
      const r = LONG.r;
      if (r && r.nm && this.onEnd) { this.stopLoop(); this.audio.dataset.want = ''; this.onEnd = null; this.onTick = null; r.nm = null; r.cont = false; r.at = null; LONG.go(); return; }
      this.finish();
    },
    stopLoop() { cancelAnimationFrame(this.raf); this.raf = 0; },
    stop() { this.stopLoop(); this.audio.dataset.want = ''; this.paused = false; MS.release('nar'); this.onEnd = null; this.onTick = null; try { this.audio.pause(); } catch (e) { /* ignore */ } },
    // -> [sentence index, char offset of the current word] at time t
    locate(t) {
      const ss = this.meta.sentences; let si = -1;
      for (let i = 0; i < ss.length; i++) { if (t >= ss[i].s - 0.02 && t < ss[i].e + 0.25) { si = i; break; } if (t < ss[i].s) break; }
      if (si < 0) return [-1, null];
      let wc = null; for (const w of ss[si].w) { if (t >= w[1]) wc = w[0]; else break; }
      return [si, wc];
    },
  };
  NAR.audio.addEventListener('error', () => { if (mediaGaveUp(NAR.audio)) NAR.failed(); });
  // Paused by something other than the page (a call, the lock screen, another app's sound): the page says so (MINI:
  // 已暂停 and 继续) instead of showing it still playing; playing again (继续, the lock screen) takes it back.
  NAR.audio.addEventListener('pause', () => {
    const a = NAR.audio; if (a.dataset.want !== '1' || a.ended || (NAR.stopAt != null && a.currentTime >= NAR.stopAt)) return;
    NAR.paused = true; MS.state('paused');
    if (LONG.nar()) LONG.held(); else MINI.pause(true, () => NAR.resume());
  });
  NAR.audio.addEventListener('play', () => {
    if (!NAR.paused || NAR.audio.dataset.want !== '1') return;
    NAR.paused = false; NAR.name();
    if (LONG.nar()) LONG.going(); else MINI.pause(false);
  });
  function lightAt(container, charOffset) {
    container.querySelectorAll('.cur').forEach(el => el.classList.remove('cur'));
    if (charOffset == null) return;
    const el = container.querySelector(`[data-c="${charOffset}"]`); if (el) el.classList.add('cur');
  }
  /* ---------- what the lock screen and the Dynamic Island show while 语流 makes a sound (navigator.mediaSession) ---------- */
  // One owner at a time: 'nar' (a whole text, with play/pause and previous/next sentence) or 'short' (Web Audio below).
  // Without it iOS shows the page's address; with it, 「语流 · 标题」 and controls that act on the page.
  const MS = {
    owner: null, ACTIONS: ['play', 'pause', 'stop', 'previoustrack', 'nexttrack'],
    claim(owner, title, handlers) {
      this.owner = owner; const ms = navigator.mediaSession; if (!ms) return;
      // 「AI 朗读」 on the lock screen, the notification shade and a desktop's media controls too (they draw from this, not
      // the page; 《标识办法》): every voice 语流 plays is synthesized (Kokoro, CosyVoice). The same as the desktop app's #199
      try { ms.metadata = window.MediaMetadata ? new MediaMetadata({ title, artist: zhEn('语流 Flow · AI 朗读', '语流 Flow · AI voice') }) : null; } catch (e) { /* ignore */ }
      this.ACTIONS.forEach(k => { try { ms.setActionHandler(k, (handlers && handlers[k]) || null); } catch (e) { /* not supported */ } });
      this.state('playing');
    },
    state(st) { try { if (navigator.mediaSession) navigator.mediaSession.playbackState = st; } catch (e) { /* ignore */ } },
    release(owner) {
      if (this.owner !== owner) return; this.owner = null; const ms = navigator.mediaSession; if (!ms) return;
      try { ms.metadata = null; } catch (e) { /* ignore */ }
      this.ACTIONS.forEach(k => { try { ms.setActionHandler(k, null); } catch (e) { /* ignore */ } });
      this.state('none');
    },
  };

  /* ---------- short sounds on iPhones and iPads ---------- */
  // An <audio> is a media session for iOS: every play() sets one up (the Dynamic Island and Now Playing show it and take
  // it away again), and the moment that takes ate the start of a word (the owner, 2026-11-24). Two ways, both on the
  // 内测版 until the owner has tried them on an iPhone and chosen one before the next release (语流 1, 2026-11-25):
  //  - 连续 (the default): Web Audio (AUDIO, here). A buffer source starts on the context's own clock, so nothing is
  //    lost; the island shows 「语流 · 单词」 while words are being played, and goes 20 s after the last.
  //  - 标准 (我的 → 设置 → 单词读音方式, or ?audio=element in Safari): short <audio> clips cut by the server with
  //    silence in front (CLIP below). Under 0.95 s an <audio> is not shown in Now Playing: about 66% of the American
  //    and 55% of the British words are, with 0.2 s in front.
  // Neither is silenced by the ringer switch. What WebKit does (its source, read 2026-11-25):
  //  - an AudioContext alone is in the Ambient category, which the ringer switch mutes, unless navigator.audioSession.type
  //    is 'playback' (or 'play-and-record'); under those it is eligible for Now Playing (AudioContext::isNowPlayingEligible)
  //    while it runs, so it is named 「语流」 (MS) and suspended 20 s after the last sound;
  //  - an <audio> shorter than 0.95 s is never shown in Now Playing (MediaElementSession, YouveGotMailDuration);
  //  - setting the type is refused where the page may not use the microphone: then this player is not used, and the
  //    short <audio> clips below are (the ringer switch does not mute those);
  //  - iOS 26 home-screen apps: a context may stay silent after the app comes back (WebKit bug 291892): it is closed when
  //    the page is hidden and made again for the next sound.
  const WORD_CLIPS = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  (() => {  // switches for trying in Safari: ?audio=element|compat|auto|webaudio, ?lead=0.05–0.4|auto (silence before a word)
    const q = location.search, a = /[?&]audio=(webaudio|element|compat|auto)\b/.exec(q), l = /[?&]lead=([\d.]+|auto)\b/.exec(q);
    if (a) save('flow-audio', a[1] === 'element' || a[1] === 'compat' ? 'compat' : null);
    if (l) save('flow-lead', l[1] === 'auto' ? null : Number(l[1]));
  })();
  // the silence in front of a cut clip: long enough for an iPhone to wake its sound, short enough that most words stay
  // under 0.95 s (word_clip.LEAD; with 0.2 s, 66% of the American and 55% of the British words do)
  // (我的 → 设置 → 单词读音方式 sets it too; read at each play, so a change counts at once)
  const LEADS = [0.1, 0.15, 0.2, 0.25, 0.3], LEAD_DEFAULT = 0.2;
  const clipLead = () => (v => (v >= 0.05 && v <= 0.4 ? v : LEAD_DEFAULT))(Number(load('flow-lead')));
  const AUDIO = {
    ctx: null, src: null, done: null, own: null, token: 0, bufs: new Map(), idle: 0, off: false,
    AC: window.AudioContext || window.webkitAudioContext,
    // not while the page is hidden (the screen locked): the context is closed then (below), and an <audio> plays on there
    // (继续 on the lock screen for a whole text read sentence by sentence)
    usable() { return WORD_CLIPS && !!this.AC && !!navigator.audioSession && !this.off && this.mode() !== 'compat' && document.visibilityState !== 'hidden'; },
    // 我的 → 设置 → 单词读音方式 (iPhones and iPads), kept on this phone (the home-screen app has no address bar for
    // ?audio= and ?lead=, and keeps its own storage): 'auto' = 连续 (Web Audio where it works) or 'compat' = 标准 (the
    // <audio> clips), and the silence in front of a clip
    mode() { return load('flow-audio') === 'compat' ? 'compat' : 'auto'; },
    setMode(m) { save('flow-audio', m === 'compat' ? 'compat' : null); if (m === 'compat') this.drop(); this.off = false; },
    lead() { return clipLead(); },
    setLead(v) { save('flow-lead', LEADS.includes(v) && v !== LEAD_DEFAULT ? v : null); },
    LEADS, LEAD_DEFAULT,
    // The page's audio session type, for this player and for recording (语流 9): AUDIO.session('play-and-record') before
    // the microphone, AUDIO.session('playback') after. Returns the type in effect ('playback', 'play-and-record', 'auto'…),
    // or null where the browser has no navigator.audioSession (then nothing is changed). A type WebKit refuses (no
    // microphone allowed) stays as it was: compare the result with what was asked.
    session(type) {
      const as = navigator.audioSession; if (!as) return null;
      try { if (type && as.type !== type) as.type = type; } catch (e) { /* refused */ }
      return as.type || null;
    },
    context() {
      if (!this.ctx) {
        try { this.ctx = new this.AC(); } catch (e) { this.off = true; return null; }
        this.ctx.onstatechange = () => {  // a call or another app took the sound: what was playing is over (or, for a
          // whole text being read, paused: cut)
          const c = this.ctx; if (!c || !this.src || c.state === 'running') return;
          const end = this.done, cut = this.cut; this.stop(); if (cut) cut(); else if (end) end();
        };
      }
      return this.ctx;
    },
    // the first tap anywhere: the context is started once inside it (later sounds may start it outside a tap: a word
    // said when its look-up arrives), then rests, so nothing shows in the Dynamic Island until a sound plays
    wake() {
      if (!this.usable()) return;
      const c = this.context(); if (!c || c.state === 'running') return;
      c.resume().then(() => { if (!this.src && !this.own) c.suspend().catch(() => {}); }).catch(() => {});
    },
    buffer(url) {
      if (this.bufs.has(url)) { const b = this.bufs.get(url); this.bufs.delete(url); this.bufs.set(url, b); return b; }  // most recent last
      const c = this.ctx;
      const p = fetch(url).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.arrayBuffer(); })
        .then(data => new Promise((ok, no) => { const q = c.decodeAudioData(data, ok, no); if (q && q.then) q.then(ok, no); }));
      p.catch(() => this.bufs.delete(url));
      this.bufs.set(url, p); while (this.bufs.size > 40) this.bufs.delete(this.bufs.keys().next().value);
      return p;
    },
    // url from `from` to `to` seconds (Infinity: to its end) at `rate`. onend when it is over; onfail(error) when it
    // cannot (the caller then plays it the old way). False at once when this player is not to be used here.
    // own: a second slot that does not stop the first (the learner's recording after the original).
    play(url, from, to, rate, onend, onfail, title, own, cut) {
      if (!this.usable()) return false;
      if (this.session('playback') !== 'playback') { this.off = true; return false; }  // refused: the ringer switch would mute it
      const c = this.context(); if (!c) return false;
      if (!own) this.stop();
      const t = own ? 0 : ++this.token;
      clearTimeout(this.idle);
      if (c.state !== 'running') c.resume().catch(() => {});
      MS.claim('short', zhEn(title || '语流'), { pause: () => this.halt(), stop: () => this.halt() });
      this.buffer(url).then(buf => {
        if (!own && t !== this.token) return;
        const s = c.createBufferSource(); s.buffer = buf; s.playbackRate.value = rate || 1; s.connect(c.destination);
        const start = Math.max(0, from || 0), end = Math.min(buf.duration, to === Infinity || to == null ? buf.duration : to);
        s.onended = () => {
          if (own ? this.own !== s : this.src !== s) return;
          if (own) this.own = null; else { this.src = null; this.done = null; }
          this.rest(); if (onend) onend();
        };
        if (own) { if (this.own) { this.own.onended = null; try { this.own.stop(); } catch (e) { /* ignore */ } } this.own = s; } else { this.src = s; this.done = onend; this.cut = cut || null; }
        s.start(c.currentTime + 0.03, start, Math.max(0.01, end - start));
        // a context that would not run (refused outside a tap, or broken): the old way, once
        setTimeout(() => { if ((own ? this.own : this.src) === s && c.state !== 'running') { if (own) this.own = null; else this.stop(); if (onfail) onfail(new Error('not running')); } }, 1500);
      }).catch(e => { if ((own || t === this.token) && onfail) onfail(e); });
      return true;
    },
    stop() { this.token++; const s = this.src; this.src = null; this.done = null; this.cut = null; if (s) { s.onended = null; try { s.stop(); } catch (e) { /* not started */ } } },
    halt() { this.stop(); if (this.own) { this.own.onended = null; try { this.own.stop(); } catch (e) { /* ignore */ } this.own = null; } this.rest(); },
    // 20 s after the last sound the context rests: WebKit takes 语流 out of Now Playing (and the Dynamic Island)
    rest() {
      clearTimeout(this.idle);
      this.idle = setTimeout(() => { if (this.src || this.own || !this.ctx) return; if (this.ctx.state === 'running') this.ctx.suspend().catch(() => {}); MS.release('short'); }, 20000);
    },
    drop() { const cut = this.src && this.cut; this.halt(); clearTimeout(this.idle); const c = this.ctx; this.ctx = null; if (c) c.close().catch(() => {}); MS.release('short'); if (cut) cut(); },
  };
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') AUDIO.drop(); });

  /* ---------- short clips: a word's pronunciation, one sentence of a narration, a sentence of the server voice ---------- */
  // On iPhones and iPads a word (and a sentence of a narration) is its own small file, cut by the server with clipLead()
  // seconds of silence in front (word_clip.py), played from its start on an <audio>: the waking of the sound happens in
  // the silence. Its source is let go when it ends, so WebKit no longer counts it for Now Playing (a page that once was
  // the Now Playing app shows even short sounds there until it has nothing left to show; a paused whole text may still
  // count, which only a phone can tell). Unless 标准 is chosen they play on AUDIO instead, where it works.
  // Elsewhere the sprite and the narration are played as before.
  const CLIP = {
    audio: new Audio(), raf: 0, metas: {}, want: null,
    accent() { return (S.voice || 'us-f').startsWith('uk') ? 'uk' : 'us'; },
    stop() { AUDIO.stop(); cancelAnimationFrame(this.raf); this.want = null; this.audio.dataset.want = ''; try { this.audio.pause(); } catch (e) { /* not playing */ } },
    // play() is called right away, inside the tap: in-app browsers (WeChat) and iPhones refuse a play() that starts
    // later, when the file has loaded. A new file plays muted until it has jumped to the clip.
    // text: said by the browser voice if neither line can play the clip.
    // to: Infinity plays a file to its end (a word clip). fallback: [src, from, to] played instead if src fails.
    // wa: {url, from, to, title}: what AUDIO plays instead, where it is used (no url: the <audio> only).
    // wa.rate: 1 for a word or an example (TTS.word); left out, a sentence of the whole text follows 语速
    // wa.cut: called instead of onend when a call (or the page hidden) cuts the sound off: a whole text pauses there
    play(src, from, to, text, onend, fallback, wa) {
      LONG.other();
      NAR.stop(); TTS.stop(); this.stop();
      const want = this.want = { from, to, text, onend, fallback, title: wa && wa.title, cut: wa && wa.cut, rate: (wa && wa.rate) || TTS.rate };
      if (wa && wa.url && AUDIO.play(wa.url, wa.from, wa.to, want.rate, () => { if (this.want === want) { this.want = null; if (onend) onend(); } },
        () => { if (this.want === want) this.element(src, from, to, text, onend, fallback, want); }, wa.title, false,
        wa.cut && (() => { if (this.want === want) { this.want = null; wa.cut(); } }))) { want.wa = true; return; }
      this.element(src, from, to, text, onend, fallback, want);
    },
    element(src, from, to, text, onend, fallback, want) {
      const a = this.audio; want.src = src;  // what was asked for: the error below says why a word was not heard
      const loop = () => {
        if (this.want !== want) return;
        if (a.currentTime >= to || a.ended) { a.pause(); this.want = null; if (to === Infinity && WORD_CLIPS) { this.letGo(); MS.release('short'); } if (onend) onend(); return; }
        this.raf = requestAnimationFrame(loop);
      };
      const refused = e => { if (this.want === want && e && e.name === 'NotAllowedError') noSound('没有放出声音'); };
      claim(a); a.playbackRate = want.rate || TTS.rate; a.dataset.want = '1'; a._from = from;
      // a word longer than 0.95 s still shows in the Dynamic Island: named, not an address (metadata changes nothing else)
      if (WORD_CLIPS && want.title) MS.claim('short', want.title, { pause: () => this.stop(), stop: () => this.stop() });
      if (a.dataset.src === src && a.readyState >= 1) {
        try { a.currentTime = from; } catch (e) { /* not seekable yet */ }
        a.muted = false; a.play().catch(refused); this.raf = requestAnimationFrame(loop); return;
      }
      mediaSrc(a, src);
      if (!from && to === Infinity) { a.muted = false; a.play().catch(refused); this.raf = requestAnimationFrame(loop); return; }  // from its start: no jump to wait for
      a.muted = true;
      a.addEventListener('loadedmetadata', () => { if (this.want === want) { try { a.currentTime = from; } catch (e) { /* ignore */ } } }, { once: true });
      a.addEventListener('seeked', () => { if (this.want !== want) return; a.muted = false; this.raf = requestAnimationFrame(loop); }, { once: true });
      a.play().catch(refused);
    },
    letGo() { const a = this.audio; a.dataset.src = ''; a.removeAttribute('src'); try { a.load(); } catch (e) { /* ignore */ } },
    // c: {text, audio: {us: [sprite, start, end], uk: [...]}}; falls back to the browser voice
    word(c) {
      const au = c.audio || {}, ac = au[this.accent()] ? this.accent() : au.us ? 'us' : au.uk ? 'uk' : null;
      if (!ac || !AAC) { if (ac) noAac(); TTS.word(c.text); return; }  // no recording, or none this device can play
      const w = au[ac], sprite = `/audio/words/${ac}/${w[0]}.mp4`, clip = this.wordSrc(c);
      if (WORD_CLIPS) this.play(clip, 0, Infinity, c.text, null, [sprite, w[1], w[2]], { url: clip, from: clipLead() - 0.02, to: clipLead() + w[2] - w[1] + 0.04, title: zhEn('语流 · 单词', 'Flow · Words'), rate: 1 });
      else this.play(sprite, w[1], w[2], c.text, null, null, { rate: 1 });
    },
    // the file word(c) plays: the word's own clip on an iPhone or iPad, its sprite elsewhere (prefetched by the review)
    wordSrc(c) {
      const au = (c && c.audio) || {}, ac = au[this.accent()] ? this.accent() : au.us ? 'us' : au.uk ? 'uk' : null;
      if (!ac) return null;
      const w = au[ac];
      return WORD_CLIPS ? `/audio/words/${ac}/${w[0]}.aac?s=${w[1]}&e=${w[2]}&l=${clipLead()}` : `/audio/words/${ac}/${w[0]}.mp4`;
    },
    // ex: {pack, i, text, audio: narration version or 0}; onend when it has been said (对比回放 plays the recording then)
    async sentence(ex, onend) {
      if (!ex.audio || !AAC) { if (ex.audio) noAac(); TTS.word(ex.text, onend); return; }
      const key = S.voice + '/' + ex.pack;
      try {
        if (!this.metas[key]) this.metas[key] = await mediaJSON(`/audio/${S.voice}/${encodeURIComponent(ex.pack)}.json?v=${ex.audio}`);
        const s = this.metas[key].sentences[ex.i]; if (!s) throw new Error('no sentence');
        const base = `/audio/${S.voice}/${encodeURIComponent(ex.pack)}`, e = s.e + 0.05, cut = `${base}.aac?v=${ex.audio}&s=${s.s}&e=${e}&l=${clipLead()}`;
        const wa = { url: cut, from: clipLead() - 0.02, to: clipLead() + e - s.s + 0.02, title: zhEn('语流 · 例句', 'Flow · Example'), rate: 1 };
        if (WORD_CLIPS) this.play(cut, 0, Infinity, ex.text, onend, [`${base}.mp4?v=${ex.audio}`, s.s, e], wa);
        else this.play(`${base}.mp4?v=${ex.audio}`, s.s, e, ex.text, onend, null, { rate: 1 });
      } catch (e) { TTS.word(ex.text, onend); }
    },
    // the learner's own recording (a blob: URL), after or beside the original: it does not stop what plays
    mine(url, onend) {
      if (AUDIO.play(url, 0, Infinity, 1, onend, () => this.mineElement(url, onend), zhEn('语流 · 我的录音', 'Flow · My recording'), true)) return;
      this.mineElement(url, onend);
    },
    mineElement(url, onend) { const a = new Audio(url); if (onend) a.onended = () => onend(); a.play().catch(() => { if (onend) onend(); }); },
  };
  // paused by something other than the page (a call) while a whole text's sentence plays: it waits there (LONG)
  CLIP.audio.addEventListener('pause', () => {
    const w = CLIP.want, a = CLIP.audio; if (!w || !w.cut || w.wa || a.dataset.want !== '1' || a.ended || a.currentTime >= w.to) return;
    CLIP.want = null; cancelAnimationFrame(CLIP.raf); a.dataset.want = ''; w.cut();
  });
  CLIP.audio.addEventListener('error', () => {
    const w = CLIP.want; if (!w || !mediaGaveUp(CLIP.audio)) return;
    if (w.fallback) { const n = CLIP.want = { ...w, fallback: null }; CLIP.element(w.fallback[0], w.fallback[1], w.fallback[2], w.text, w.onend, null, n); return; }  // no clip from the server: the sprite, as before (once)
    CLIP.stop();
    if (!w.text) return;
    // the clip and the sprite both failed: say why before the browser's voice (audio-inventory.md, 语流 9: never a
    // silent switch to a machine voice); a word has its own two lines, apart from a sentence's (SV.why: once per reason).
    // No browser voice either (WeChat): TTS.browser says how to hear it instead, and nothing is said about a voice.
    const off = navigator.onLine === false;
    if (TTS.ok) SV.why(/\/audio\/words\//.test(w.src || '')
      ? { code: off ? 'word_offline' : 'word_net', server: off ? `离线中，这个词的读音还没存到本机，先用${SYS_VOICE()}` : `网络不好，这个词的读音没加载出来，先用${SYS_VOICE()}` }
      : { code: off ? 'offline' : 'net' });
    TTS.browser(w.text, w.onend);  // not TTS.say: that may be this player again (the server voice); onend still runs (对比回放 plays the recording then)
  });
  /* ---------- preloading: the recording likely to be played next is fetched while the page is open ---------- */
  // iPhones and WeChat's browser download a recording only when it is played: on a phone network that is a second or
  // two after the tap. The recording being studied (and today's article, from 今日) is fetched in the background and kept
  // in memory as a blob: URL, so a tap plays at once. Not with Save-Data or on 2G; at most 8 recordings are kept.
  // (Word sounds are not preloaded: a word's file holds about 100 words, and the player fetches only that word's bytes.)
  const PRELOAD = {
    done: new Map(), going: new Map(), app: false,
    // Save-Data, 2G, or 语流's iOS app saving power (低电量模式, iOS 27 asking apps to do less: FlowApp 'frugal', C1):
    // nothing fetched ahead (today's texts kept offline, the next material, its recording, the next sentences)
    frugal() { const c = navigator.connection; return this.app || !!(c && (c.saveData || /(^|-)2g$/.test(c.effectiveType || ''))); },
    url(u) { return this.done.get(u) || u; },
    warm(u) {
      if (!u) return Promise.resolve(null);
      if (this.done.has(u)) return Promise.resolve(this.done.get(u));
      if (this.going.has(u)) return this.going.get(u);
      if (this.frugal()) return Promise.resolve(null);
      const p = fetch(u).then(r => (r.ok ? r.blob() : null)).then(b => {
        this.going.delete(u); if (!b || !b.size) return null;
        const blob = URL.createObjectURL(b); this.done.set(u, blob);
        for (const [old, ou] of this.done) {  // oldest first; a recording a player is using stays
          if (this.done.size <= 8) break;
          if (![NAR.audio, CLIP.audio].some(a => a.getAttribute('src') === ou)) { this.done.delete(old); URL.revokeObjectURL(ou); }
        }
        return blob;
      }).catch(() => { this.going.delete(u); return null; });
      this.going.set(u, p); return p;
    },
  };
  if (window.FlowApp && FlowApp.has && FlowApp.has('frugal')) {
    const take = d => { PRELOAD.app = !!(d && d.on); };
    Promise.resolve(FlowApp.call('app.frugal')).then(take, () => {});
    if (FlowApp.on) FlowApp.on('frugal', take);
  }
  // From 今日: the material most likely opened next, and its recording, so the study page opens and plays without a wait.
  async function preloadMaterial(id) {
    if (!id || MAT[id] || PRELOAD.frugal()) return;
    try {
      const m = await api(materialPath(id));
      MAT[id] = m; m._preloaded = Date.now(); snapMaterial(materialPath(id), m);
      const vs = (m.audio && m.audio.voices) || [];
      if (vs.length) PRELOAD.warm(`/audio/${vs.includes(S.voice) ? S.voice : vs[0]}/${encodeURIComponent(id)}.mp4?v=${m.audio.version}`);
    } catch (e) { /* it loads when opened */ }
  }

  /* ---------- unlocking: a media element that has played once inside a tap may play later on its own ---------- */
  // WeChat's browser, iPhones and many Android in-app browsers refuse sound that does not start inside a tap, which is
  // what a play after a download is (a word's clip, a sentence after its timings, a reply read out). On the first tap
  // anywhere, both players play a moment of silence; from then on they may play when their file arrives.
  // Four samples of silence, as a blob: URL (the page's CSP allows blob: and 'self' for media, not data:).
  const SILENT = (() => {
    try { const b = atob('UklGRiwAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQgAAAAAAAAAAAAAAA=='), u = new Uint8Array(b.length);
      for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i);
      return URL.createObjectURL(new Blob([u], { type: 'audio/wav' })); } catch (e) { return ''; }
  })();
  function claim(a) { a._uses = (a._uses || 0) + 1; a.muted = false; }
  function unlockAudio() {
    ['touchend', 'click', 'keydown'].forEach(t => window.removeEventListener(t, unlockAudio, true));
    AUDIO.wake();
    [NAR.audio, CLIP.audio].forEach(a => {
      const own = a.getAttribute('src'), uses = a._uses || 0;
      if (!own && SILENT) a.setAttribute('src', SILENT);
      a.muted = true;
      const after = () => {
        if ((a._uses || 0) !== uses) return;  // this same tap started real playback: leave it alone
        a.pause(); a.muted = false;
        if (!own && a.getAttribute('src') === SILENT) { a.removeAttribute('src'); a.load(); }
      };
      try { const p = a.play(); if (p && p.then) p.then(after, after); else after(); } catch (e) { after(); }
    });
    if (TTS.ok) { try { const u = new SpeechSynthesisUtterance(' '); u.volume = 0; speechSynthesis.speak(u); } catch (e) { /* ignore */ } }
  }
  ['touchend', 'click', 'keydown'].forEach(t => window.addEventListener(t, unlockAudio, true));
  // Attached to the page: some Android in-app browsers lose a detached player's sound.
  addEventListener('DOMContentLoaded', () => { [NAR.audio, CLIP.audio].forEach(a => { a.hidden = true; document.body.appendChild(a); }); });
  if (document.readyState !== 'loading') [NAR.audio, CLIP.audio].forEach(a => { a.hidden = true; document.body.appendChild(a); });

  /* ---------- mini player: while a whole text plays, its control stays on screen however far the text scrolls ---------- */
  // A whole text (LONG): 暂停 / 继续, and ✕ to close it (where it was is kept). A sentence repeating: 停止. Paused from
  // outside the page (a call, the lock screen): 已暂停, and the button says 继续.
  const pauseIcon = size => `<svg width="${size || 18}" height="${size || 18}" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4.5" height="14" rx="1.2"/><rect x="13.5" y="5" width="4.5" height="14" rx="1.2"/></svg>`;
  const MINI = {
    el: null, h: null, label: '', resumeFn: null, dk: null,
    box() {
      if (!this.el) { this.el = document.createElement('div'); this.el.className = 'mini-player'; this.el.setAttribute('role', 'region'); this.el.setAttribute('aria-label', '播放控制'); document.body.appendChild(this.el); }
      this.el.classList.toggle('docked', !!this.dk); document.body.classList.toggle('docked', !!this.dk);
      return this.el;
    },
    // 精听 (the user's pick of 语流 B9's design, 2026-11-25): with nothing playing the bar stays above the tabs with the
    // page's start button (#playAll, 「播放全文」 or 「从第 N 句继续」), 「AI 合成」 and the speed; playing, it is the usual
    // player, its 暂停 / 继续 still #playAll for that text. dk: {key, ai, paint(), play(), rate()}. Other pages: only while playing.
    dock(dk) { this.dk = dk; if (!this.h) this.idle(); else this.box(); NATIVE.adopt(); },  // the app playing this text: taken back
    undock() { this.dk = null; document.body.classList.remove('docked'); if (this.el) this.el.classList.remove('docked'); if (!this.h) this.hide(); },
    // 👁 (盲听) by the speed while nothing plays (B9's r36 audit F1: it had a row of its own above the sentences)
    eye() { const on = !!(this.dk && this.dk.blind && this.dk.blind.on()); return `<button type="button" class="eye${on ? ' on' : ''}" id="blind" aria-pressed="${on}" title="盲听：先只听不看" aria-label="盲听">${ICON.eye}</button>`; },
    idle() {
      const dk = this.dk, el = this.box();
      el.innerHTML = `<button type="button" class="toggle" id="playAll"></button>${aiVoiceNote('AI 合成', 'span')}<span class="sp"></span>`
        + '<button type="button" class="speed-set" aria-label="播放设置：语速、每句几遍、句后停顿"></button>' + (dk.blind ? this.eye() : '');
      el.querySelector('#playAll').onclick = () => dk.play();
      el.querySelector('.speed-set').onclick = () => dk.rate();
      if (dk.blind) el.querySelector('#blind').onclick = () => dk.blind.toggle();
      el.classList.remove('paused'); el.classList.add('idle'); el.hidden = false; document.body.classList.add('playing');
      this.ai(typeof dk.ai === 'function' ? dk.ai() : !!dk.ai);
      dk.paint();
    },
    show(label, h) {
      if (typeof h === 'function') h = { stop: h };
      this.h = h; this.label = label; this.resumeFn = null;
      const el = this.box(), mine = !!(this.dk && h.key && h.key === this.dk.key);
      el.innerHTML = `<span class="eq" aria-hidden="true"><i></i><i></i><i></i></span><span class="lbl"></span>${aiVoiceNote('AI 合成', 'span')}`
        + (h.toggle ? `<button type="button" class="toggle"${mine ? ' id="playAll"' : ''}></button>${mine ? '<button type="button" class="speed-set" aria-label="播放设置：语速、每句几遍、句后停顿"></button>' : ''}<button type="button" class="stop close" aria-label="关闭播放（记住读到哪里）">✕</button>`
          : `<button type="button" class="stop">${playIcon(true, 15)}<span>停止</span></button>`);
      el.querySelector('.lbl').textContent = label;
      el.querySelector('.stop').onclick = () => { const st = this.h && this.h.stop; this.hide(); if (st) st(); };
      if (h.toggle) el.querySelector('.toggle').onclick = () => this.h.toggle();
      if (mine) { const dk = this.dk; el.querySelector('.speed-set').onclick = () => dk.rate(); }
      el.classList.remove('paused', 'idle'); el.hidden = false; document.body.classList.add('playing');
      this.ai(h.ai !== false);
      this.paint();
      if (mine) this.dk.paint();
    },
    paint() {
      if (!this.onResize) { this.onResize = () => this.paint(); addEventListener('resize', this.onResize); }  // 「12/30」 follows the width
      if (!this.el || this.el.hidden || !this.h) return;
      const on = this.el.classList.contains('paused'), t = this.el.querySelector('.toggle'), lbl = this.el.querySelector('.lbl'), text = on ? '已暂停' : this.label;
      // 精听's bar keeps 1× while playing (B9 F3): where 「第 12 / 30 句」 would not fit with it, 「12/30」
      lbl.textContent = this.dk && innerWidth < 370 ? text.replace(/^第 (\d+) \/ (\d+) 句$/, '$1/$2') : text;
      if (t) { t.innerHTML = on ? `${playIcon(false, 15)}<span>继续</span>` : `${pauseIcon(15)}<span>暂停</span>`; t.classList.toggle('resume', on); t.setAttribute('aria-label', on ? '继续' : '暂停'); }
      let b = this.el.querySelector('.resume:not(.toggle)');
      if (!t && on && !b) { b = document.createElement('button'); b.type = 'button'; b.className = 'resume'; b.innerHTML = `${playIcon(false, 15)}<span>继续</span>`; this.el.insertBefore(b, this.el.querySelector('.stop')); }
      if (b) { if (!t && on) b.onclick = () => { if (this.resumeFn) this.resumeFn(); }; else b.remove(); }
    },
    update(label) { this.label = label; this.paint(); },
    // 「AI 合成」 follows the voice really heard: 语流's own (a recording, AI 朗读) or, fallen back, the browser's (B9, 2026-11-25)
    ai(on) { const n = this.el && this.el.querySelector('.ai-voice-note'); if (n) n.hidden = !on; },
    paused(on) { if (this.el && !this.el.hidden && this.h) { this.el.classList.toggle('paused', !!on); this.paint(); } },
    // a recording paused from outside, with no whole text around it: 已暂停, and 继续 calls resume
    pause(on, resume) { if (!this.el || this.el.hidden || !this.h) return; this.resumeFn = resume || null; this.paused(on); },
    // stopped: 精听's bar goes back to its start button; anywhere else the bar goes
    hide() {
      this.h = null;
      if (this.dk) { this.idle(); return; }
      if (this.el) { this.el.hidden = true; this.el.classList.remove('paused', 'idle'); } document.body.classList.remove('playing');
    },
    end() { const b = this.el && !this.el.hidden && this.el.querySelector('.stop'); if (b) b.click(); },
  };

  /* ---------- where a whole text was left: per text and per page (听 / 读), on this phone for 30 days ---------- */
  const PROG = {
    KEY: 'flow-progress', DAYS: 30, MAX: 100,
    all() { const o = load(this.KEY) || {}, cut = Date.now() - this.DAYS * 864e5; for (const k of Object.keys(o)) if (!o[k] || !(o[k].at > cut)) delete o[k]; return o; },
    get(k) { return (k && this.all()[k]) || null; },
    // the sentence to go on from, when it is not the first and the text still has it
    at(k, n) { const p = this.get(k); return p && p.i > 0 && p.i < n ? p.i : 0; },
    set(k, i) {
      if (!k) return; const o = this.all(); if (i > 0) o[k] = { i, at: Date.now() }; else delete o[k];
      const ks = Object.keys(o); if (ks.length > this.MAX) ks.sort((x, y) => o[x].at - o[y].at).slice(0, ks.length - this.MAX).forEach(x => delete o[x]);
      save(this.KEY, o);
    },
    clear(k) { if (k) { const o = this.all(); delete o[k]; save(this.KEY, o); } },
  };

  /* ---------- in 语流's iOS app the app plays a whole text (ios/README.md, 「网页和 App 之间的桥」) ---------- */
  // window.FlowApp is there only inside the app (Safari, the home-screen app and WeChat do as before). LONG keeps its own
  // state (where it is, MINI, PROG, onState / onWord) and the app plays: on with the screen locked and while this page
  // sleeps, the lock screen's buttons, on again after a call. Its news ('audio') moves LONG along; 'audio-tick' (four a
  // second, the page in front) lights the word of a recording, smoothed between ticks.
  const NATIVE = {
    tick: null, raf: 0, sent: '', lone: null, last: null, watcher: null,
    on() { return !!(window.FlowApp && FlowApp.has && FlowApp.has('audio')); },
    // 复读 (times, the pause after each sentence) and 语速, as the page has them now (docs/native-bridge.md §3 set)
    knobs(r) { return { rep: r.rep ? r.rep() : 1, gap: r.texts.map((_, k) => (r.gap ? r.gap(k) : 0)), rate: TTS.rate || 1 }; },
    // changed while the app plays (a 复读 or 语速 chip, or meanwhile): the app gets them at once
    retune(force) {
      const r = LONG.r; if (!r || !r.native) return;
      const k = JSON.stringify(this.knobs(r));
      if (force || k !== this.sent) { this.sent = k; FlowApp.audio.set(this.knobs(r)).catch(() => {}); }
    },
    // The app's own 语速 and 单句循环, changed on the lock screen (iOS 27, 语流 C1's #335: rate, rep and loop in 'audio' and
    // state(), why 'remote'): the page takes them, its chips follow, and nothing is pushed back (a forced set put 1× back).
    // 单句循环 there is rep 0 with loop; turned off, the app sends the page's own back. An older app sends none: false.
    takeKnobs(d, r) {
      if (!d || typeof d.rate !== 'number' || !(d.rate > 0)) return false;
      if (d.rate !== TTS.rate) { TTS.rate = d.rate; save('flow-next-rate', TTS.rate); NAR.audio.playbackRate = TTS.rate; }
      if (typeof d.rep === 'number' && d.rep >= 0 && r.setRep) r.setRep(d.rep);
      this.sent = JSON.stringify(this.knobs(r));
      if (r.onKnobs) r.onKnobs();
      return true;
    },
    start(r) {
      const d = this.last;
      if (this.lone === r.key && d && d.key === r.key && d.state !== 'idle') {
        // this page loaded again while the app went on with this very text: take it back where the app is, no new start
        // (r.auto: 精听 took it back by itself, MINI.dock / adopt: a paused text stays paused; a tap on 继续 resumes it)
        const keep = !!r.auto && d.state === 'paused';
        this.lone = null; if (typeof d.i === 'number') r.i = d.i; r.state = d.state === 'paused' && !keep ? 'playing' : d.state; r.note = '';
        if (d.state === 'paused' && !keep) FlowApp.audio.resume().catch(() => {});
        MINI.paused(keep); if (!this.takeKnobs(d, r)) this.retune(true); LONG.save(); LONG.emit(); this.loop(); return;  // the app's knobs, else the page's
      }
      const o = { key: r.key, title: r.title || '', from: r.i, ...this.knobs(r) };
      if (S.csrf) o.csrf = S.csrf;
      if (r.nm) { o.src = NAR.net; o.sentences = r.nm.sentences.map(x => [x.s, x.e]); o.loop = !!r.loop; const alt = mediaAlt(NAR.net); if (alt) o.alt = alt; }
      else {  // no recording: each sentence with the address this phone already has for it (SV address book), else null (§3 items)
        const voice = r.voice || S.voice, pack = r.pack;
        o.items = r.texts.map(text => ({ text, url: (SV.kept()[SV.hash(SV.key(text, { voice, pack }))] || [])[0] || null }));
        o.voice = voice; if (pack) o.pack = pack;
      }
      this.sent = JSON.stringify(this.knobs(r));
      FlowApp.audio.play(o).then(x => { if (!(x && x.ok) && LONG.r === r) this.fail(r, x && x.message); }, () => { if (LONG.r === r) this.fail(r); });
    },
    // the app could not (a call going on): this page reads it, as in Safari
    fail(r, why) { r.native = false; if (why) toast(why); LONG.go(); },
    news(d) {
      const r = LONG.r;
      if (!r || !r.native || d.key !== r.key) { this.orphan(d); return; }
      if (d.state === 'idle') { if (d.why === 'ended') LONG.finish(); else if (d.why !== 'user') LONG.stop(); return; }
      if (typeof d.i === 'number' && d.i !== r.i) { r.i = d.i; r.n = 0; LONG.save(); }
      // the app fell back to the phone's own voice: why, said by the page as everywhere on the site (SV.why: once a reason)
      r.state = d.state; r.note = d.fail ? SV.why(d.fail) : (d.note || ''); MINI.ai(!!r.nm || !d.fail);
      MINI.paused(d.state === 'paused');
      if (d.why === 'remote') this.takeKnobs(d, r);  // 语速 or 单句循环 changed on the lock screen
      this.retune();  // 复读 or 语速 changed on the page meanwhile
      LONG.emit(); this.loop();
    },
    // the app made a sentence this phone had no address for: kept in the SV address book (§3 audio-made), so it is
    // not made twice and the page finds it too (offline, in Safari)
    made(d) {
      const r = LONG.r;
      if (!d || !d.url || !r || !r.native || d.key !== r.key || !(d.i >= 0) || d.i >= r.texts.length) return;
      SV.keep(SV.key(r.texts[d.i], { voice: r.voice || S.voice, pack: r.pack }), d.url);
    },
    // the sentence moved on between two 'audio' news (they come with each new sentence, §3; a tick says it as well)
    ticked(d) {
      this.tick = d;
      const r = LONG.r;
      if (r && r.native && d && d.key === r.key && typeof d.i === 'number' && d.i !== r.i) { r.i = d.i; r.n = 0; LONG.save(); LONG.emit(); }
    },
    // the app's news kept on this phone too (PROG), so 「从第 N 句继续」 is where the app got to, also after this page
    // loaded again; read to the end clears it, any other stop keeps it (§3 进度)
    keep(d) {
      if (!d || !d.key) return;
      this.last = d;
      if (d.state === 'idle' && d.why === 'ended') PROG.clear(d.key); else if (typeof d.i === 'number') PROG.set(d.key, d.i);
      const w = this.watcher; if (w && w.key === d.key && !LONG.of(d.key)) w.paint();
    },
    // the page with this text's 播放全文 / 伴读 button: in the app the button says where the app got to, its stored place
    // when the page opens and its news while it plays this text without this page (loaded again meanwhile)
    follow(key, paint) {
      this.watcher = { key, paint };
      this.reconcile(key).then(() => { if (!LONG.of(key)) paint(); });
    },
    // where the app got to in a text against this phone's PROG, the newer one counts (§3: the app played on while this
    // page slept, or read it to the end): true when PROG changed, so the page can say 「从第 N 句继续」 again
    reconcile(key) {
      if (!this.on() || !key) return Promise.resolve(false);
      return Promise.resolve(FlowApp.audio.progress(key)).then(p => {
        if (!p || !(p.at > 0)) return false;
        const mine = PROG.get(key);
        if (mine && mine.at >= p.at) return false;
        if (p.ended || !(p.i > 0)) { if (!mine) return false; PROG.clear(key); return true; }
        if (mine && mine.i === p.i) return false;
        PROG.set(key, p.i); return true;
      }, () => false);
    },
    loop() {
      cancelAnimationFrame(this.raf);
      const r = LONG.r; if (!r || !r.native || !r.nm || r.state !== 'playing' || !r.onWord) return;
      const f = () => {
        const k = this.tick; if (LONG.r !== r || r.state !== 'playing') return;
        if (k && k.key === r.key && NAR.meta === r.nm) { const [si, wc] = NAR.locate(k.t + Math.max(0, Date.now() - k.at) / 1000 * (k.rate || 1)); if (si >= 0 && si === r.i) r.onWord(si, wc); }  // only the app's sentence: an older tick never lights the one before
        this.raf = requestAnimationFrame(f);
      };
      this.raf = requestAnimationFrame(f);
    },
    // the app's text, which this page did not start, after the router hid MINI for a new page: on screen again
    reshow() { const d = this.last; if (!LONG.r && this.lone && d && d.key === this.lone && d.state !== 'idle') this.orphan(d); },
    // the app plays the very text whose 精听 page is open (loaded again, or come back to): the page takes it back by
    // itself, so its one bar is that text's player, the sentence lit; true when it did
    adopt() {
      const d = this.last, dk = MINI.dk;
      if (!dk || !dk.attach || LONG.r || !d || this.lone !== d.key || d.key !== dk.key || d.state === 'idle') return false;
      dk.attach(); return true;
    },
    // this page loaded again (a new version, iOS ended it in the background) while the app goes on: its control is back
    orphan(d) {
      this.keep(d);
      if (LONG.r) return;
      if (d.state === 'idle') { if (this.lone) { this.lone = null; MINI.hide(); } return; }
      if (MINI.dk && MINI.dk.key === d.key) { this.lone = d.key; if (this.adopt()) return; }
      const label = (d.title || '朗读') + (d.n ? ` · 第 ${d.i + 1} / ${d.n} 句` : '');
      if (this.lone !== d.key || !MINI.el || MINI.el.hidden || !MINI.h) {  // !MINI.h: 精听's idle bar is there, not the app's player
        this.lone = d.key;
        MINI.show(label, { toggle: () => (MINI.el.classList.contains('paused') ? FlowApp.audio.resume() : FlowApp.audio.pause()), stop: () => { this.lone = null; FlowApp.audio.stop(); } });
      } else MINI.update(label);
      MINI.paused(d.state === 'paused');
    },
  };
  if (NATIVE.on()) {
    FlowApp.on('audio', d => NATIVE.news(d));
    FlowApp.on('audio-tick', d => NATIVE.ticked(d));
    FlowApp.on('audio-made', d => NATIVE.made(d));
    FlowApp.audio.state().then(d => { if (d && d.state !== 'idle') NATIVE.news(d); }, () => {});
  }

  /* ---------- a whole text read aloud: 听's 播放全文 and 读's 伴读 (owner, 2026-11-25) ---------- */
  // The recording (Kokoro) when there is one, straight through (or sentence by sentence when 复读 is set); otherwise the
  // server voice sentence by sentence, the next two asked for while one plays, a line while one is being made (never the
  // browser voice for being slow), and the browser voice only for a sentence the server could not give, with the reason.
  // 暂停 / 继续: a recording goes on from the second it stopped, a sentence-by-sentence reading from the start of the
  // sentence it stopped in. The same from the mini player, the lock screen and the Dynamic Island, after a call, the page
  // hidden, or another sound (a word, a recording) started meanwhile. Where it was left is kept per text and page (PROG)
  // until its end is reached: 「从第 N 句继续」. One text at a time.
  // o: {key, texts, nm (Kokoro timings, or null), pack, title, loop (sentence by sentence even with a recording),
  //     rep() (times each sentence, 0 = until stopped), gap(i) (ms after sentence i), label(i),
  //     onState(state, i, note) ('waiting' | 'playing' | 'paused' | 'idle'), onWord(i, charOffset | null), onDone()}
  const LONG = {
    r: null, self: false,
    of(key) { return this.r && this.r.key === key ? this.r : null; },
    nar() { return !!(this.r && this.r.nm && NAR.audio.dataset.want === '1'); },
    start(o, from) {
      this.stop();
      const n = o.texts.length, r = this.r = { ...o, i: Math.max(0, Math.min(from || 0, n - 1)), n: 0, tok: 0, state: o.nm ? 'playing' : 'waiting', note: '', at: null };
      r.cont = !!o.nm && !o.loop;
      r.native = NATIVE.on();
      MINI.show(this.label(), { key: r.key, ai: !!(o.nm || SV.on()), toggle: () => this.toggle(), stop: () => this.stop() });  // ai: 语流's own voices, not the browser's
      if (r.native) { this.emit(); NATIVE.start(r); return; }  // 语流's iOS app plays it (NATIVE)
      if (o.nm) { this.emit(); this.go(); return; }  // inside the tap: WeChat plays a recording only when it starts there
      this.emit();
      const tok = r.tok;
      SV.have(o.texts, o).then(() => { if (this.r === r && r.tok === tok && r.state !== 'paused') this.go(); });
    },
    label() { const r = this.r; return r.state === 'waiting' ? `准备第 ${r.i + 1} 句…` : (r.label ? r.label(r.i) : `第 ${r.i + 1} / ${r.texts.length} 句`); },
    emit() { const r = this.r; if (!r) return; MINI.update(this.label()); if (r.onState) r.onState(r.state, r.i, r.note); },
    claim() {  // the lock screen for a sentence-by-sentence reading (a recording names itself: NAR.name)
      const r = this.r; if (!r || r.nm || r.native) return;
      MS.claim('long', '语流 · ' + (r.title || '朗读'), { play: () => this.resume(), pause: () => this.pause(), stop: () => { this.stop(); MINI.hide(); },
        previoustrack: () => this.step(-1), nexttrack: () => this.step(1) });
      if (r.state === 'paused') MS.state('paused');
    },
    // inside LONG: what it plays is not "another sound"
    own(f) { this.self = true; try { f(); } finally { this.self = false; } },
    go() {
      const r = this.r; if (!r) return;
      const tok = ++r.tok, s = r.nm && r.nm.sentences[r.i];
      if (r.cont) {
        const from = r.at != null ? r.at : s.s; r.at = null; r.state = 'playing'; this.emit();
        this.own(() => NAR.play(from, null, t => this.tick(t), () => { if (this.r === r && r.tok === tok) this.ended(); }));
        return;
      }
      if (r.nm) {
        r.state = 'playing'; MINI.ai(true); this.emit();
        this.own(() => NAR.play(s.s, s.e, t => { const [si, wc] = NAR.locate(t); if (si === r.i && r.onWord) r.onWord(si, wc); }, () => { if (this.r === r && r.tok === tok) this.after(); }));
        return;
      }
      this.sentence(tok);
    },
    tick(t) {  // a recording straight through: which sentence, which word
      const r = this.r; if (!r) return;
      const [si, wc] = NAR.locate(t);
      if (si >= 0 && si !== r.i) { r.i = si; this.emit(); this.save(); }
      if (si >= 0 && r.onWord) r.onWord(si, wc);
    },
    ended() {  // the recording stopped by itself: the end, or a file that would not load (then where it was is kept)
      const r = this.r, a = NAR.audio, last = r.nm.sentences[r.nm.sentences.length - 1];
      if (a.ended || a.currentTime >= last.s) this.finish(); else this.stop();
    },
    async sentence(tok) {
      const r = this.r, i = r.i, text = r.texts[i];
      for (const k of [i + 1, i + 2]) if (k < r.texts.length && SV.on()) SV.url(r.texts[k], r).then(u => PRELOAD.warm(u), () => {});
      let u = null, err = null;
      if (SV.on()) {
        const ready = SV.urls.has(SV.key(text, r));
        const late = ready ? 0 : setTimeout(() => { if (this.r === r && r.tok === tok) { r.state = 'waiting'; r.note = `正在准备朗读第 ${i + 1} 句…`; this.emit(); } }, 400);
        try { u = await SV.slow(SV.url(text, r)); } catch (e) { err = e; }
        clearTimeout(late);
        if (this.r !== r || r.tok !== tok) return;  // paused, stopped or moved on while it was being made
      }
      r.state = 'playing'; r.note = u ? '' : err ? SV.why(err) : SV.off ? SV.why({ code: SV.off }) : ''; MINI.ai(!!u); this.emit();
      const next = () => { if (this.r === r && r.tok === tok) this.after(); };
      if (u) {
        this.own(() => CLIP.play(u, 0, 1e6, text, next, null, { url: u, from: 0, to: Infinity, title: '语流 · ' + (r.title || '朗读'), cut: () => { if (this.r === r && r.tok === tok) this.held(); } }));
        this.claim();
      } else {
        // the browser voice could not say it (none here, or iOS dropped it twice): the text waits there, paused, with why
        const failed = () => { clearTimeout(stall); if (this.r !== r || r.tok !== tok) return; this.held(); r.note = `${SYS_VOICE()}没有读出这一句，点「继续」再试一次`; this.emit(); };
        // and if nothing at all comes back from it (never asked: something else spoke or stopped it in between; or no
        // event of any kind, which an iPad did once offline: 语流 07, 2026-11-25), it is not left "playing" there either
        const stall = setTimeout(failed, 4000);
        this.own(() => TTS.browser(text, () => { clearTimeout(stall); next(); }, c => { if (this.r === r && r.onWord) r.onWord(i, c); }, failed, () => clearTimeout(stall)));
      }
    },
    // one sentence said: again (复读), or the next, after its pause. The pause is the one after the sentence just said
    // (「留时间跟说」 is as long as that sentence), so it is taken before moving on
    after() {
      const r = this.r, rep = r.rep ? r.rep() : 1, g = r.gap ? r.gap(r.i) : 0;
      r.n += 1;
      if (!(rep === 0 || r.n < rep)) {
        r.n = 0; r.i += 1;
        if (r.i >= r.texts.length) { this.finish(); return; }
        this.save();
      }
      const tok = r.tok;
      if (g) r.timer = setTimeout(() => { if (this.r === r && r.tok === tok && r.state !== 'paused') this.go(); }, g); else this.go();
    },
    toggle() { if (!this.r) return; if (this.r.state === 'paused') this.resume(); else this.pause(); },
    pause() {
      const r = this.r; if (!r || r.state === 'paused') return;
      if (r.native) { FlowApp.audio.pause().catch(() => {}); r.state = 'paused'; r.note = ''; MINI.paused(true); this.save(); this.emit(); return; }
      if (r.cont && NAR.audio.dataset.want === '1') { r.at = NAR.audio.currentTime; NAR.audio.pause(); this.held(); return; }  // the listener calls held() too
      if (r.nm && NAR.audio.dataset.want === '1') { NAR.audio.pause(); this.held(); return; }  // 复读 on a recording: that sentence waits at its second
      r.tok++; clearTimeout(r.timer); this.own(() => { TTS.stop(); CLIP.stop(); });
      this.held();
    },
    held() {  // paused (by the learner, a call, the lock screen, the page hidden, another sound): where it was is kept
      const r = this.r; if (!r || r.state === 'paused') return;
      if (r.cont && r.at == null && NAR.audio.dataset.want === '1') r.at = NAR.audio.currentTime;
      if (!r.nm) { r.tok++; clearTimeout(r.timer); }
      r.state = 'paused'; r.note = ''; MINI.paused(true); MS.state('paused'); this.save(); this.emit();
    },
    going() { const r = this.r; if (!r || r.state !== 'paused') return; r.state = 'playing'; r.at = null; MINI.paused(false); MS.state('playing'); this.emit(); },
    resume() {
      const r = this.r; if (!r || r.state !== 'paused') return;
      if (r.native) {  // the app may have let it go meanwhile (closed by iOS): then it starts again where it was
        r.state = 'playing'; MINI.paused(false); this.emit();
        FlowApp.audio.resume().then(x => { if (this.r === r && (!x || x.key !== r.key || x.state === 'idle')) NATIVE.start(r); }, () => {});
        return;
      }
      if (r.nm && NAR.audio.dataset.want === '1') { this.going(); NAR.resume(); return; }  // still there, paused: on from that second
      r.state = 'playing'; MINI.paused(false); this.go();
    },
    // another sound is about to start (a word looked up, a sentence tapped, the microphone): the text waits, paused
    other() {
      const r = this.r; if (!r || this.self || r.state === 'paused') return;
      if (r.native) { this.pause(); return; }
      if (r.cont && NAR.audio.dataset.want === '1') r.at = NAR.audio.currentTime;
      if (r.nm) r.tok++;  // the recording is taken over: 继续 plays it again from r.at
      this.held();
    },
    step(d) {  // previous / next sentence (the lock screen)
      const r = this.r; if (!r) return;
      if (r.native) { FlowApp.audio.step(d).catch(() => {}); return; }
      if (r.cont) { NAR.step(d); return; }
      r.tok++; clearTimeout(r.timer); this.own(() => { TTS.stop(); CLIP.stop(); NAR.stop(); });
      r.i = Math.max(0, Math.min(r.texts.length - 1, r.i + d)); r.n = 0; r.at = null; r.state = 'playing'; MINI.paused(false); this.go();
    },
    save() { const r = this.r; if (r && r.key) PROG.set(r.key, r.i); },
    finish() {
      const r = this.r; if (!r) return;
      this.r = null; r.tok++; PROG.clear(r.key); MINI.hide(); MS.release('long'); cancelAnimationFrame(NATIVE.raf);
      if (r.onState) r.onState('idle', -1, '');
      if (r.onDone) r.onDone();
    },
    // stop reading (✕, leaving the page, another text): where it was is kept
    stop() {
      const r = this.r;
      if (!r) { if (NATIVE.lone) setTimeout(() => NATIVE.reshow(), 0); return; }  // a new page (the router hides MINI): the app's text keeps its control
      if (r.cont && NAR.audio.dataset.want === '1') { const [si] = NAR.locate(NAR.audio.currentTime); if (si >= 0) r.i = si; }
      this.save(); this.r = null; r.tok++; clearTimeout(r.timer);
      if (r.native) { cancelAnimationFrame(NATIVE.raf); FlowApp.audio.stop().catch(() => {}); }
      this.own(() => { TTS.stop(); CLIP.stop(); NAR.stop(); });
      MINI.hide(); MS.release('long');
      if (r.onState) r.onState('idle', -1, '');
    },
  };
  /* ---------- offline: reviews done without a connection are queued and synced with the time they happened ---------- */
  const OUTBOX = {
    key: 'flow-next-outbox',
    list() { return load(this.key) || []; },
    push(item) { const l = this.list(); l.push(item); save(this.key, l.slice(-500)); },
    // 撤销 of a rating made offline: it has not been sent, so it is simply taken out again
    unpush(item) { const l = this.list(), k = l.map(x => JSON.stringify(x)).lastIndexOf(JSON.stringify(item)); if (k >= 0) { l.splice(k, 1); save(this.key, l); return true; } return false; },
    async flush() {
      if (this.busy || !S.user || !navigator.onLine) return 0;
      this.busy = true; let sent = 0;
      try {
        let l = this.list();
        while (l.length) {
          const it = l[0];
          try { await api(it.path, it.body); } catch (e) { if (e.network) break; /* rejected (e.g. card deleted): drop it */ }
          l = this.list().slice(1); save(this.key, l); sent++;
        }
      } finally { this.busy = false; }
      if (sent) { toast(`没网时做的 ${sent} 项已同步`); refreshHome().catch(() => {}); }  // said once, here (also after the 'online' event)
      return sent;
    },
  };
  // sent when the phone is back online: 06-offline.js (which also says how much was synced)
  // Ask the service worker to keep today's audio (word sprites, example narration) for weak or no network.
  function prefetchAudio(urls) {
    const list = [...new Set(urls)].filter(Boolean).slice(0, 40);
    if (list.length && navigator.serviceWorker && navigator.serviceWorker.controller) navigator.serviceWorker.controller.postMessage({ type: 'prefetch', urls: list });
  }
  let installPrompt = null;
  window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); installPrompt = e; });

  // FSRS forgetting curve (same constants as fsrs.py): chance of recall t days after a review with stability s.
  const DECAY = -0.1542, FACTOR = Math.pow(0.9, 1 / DECAY) - 1;
  const recallAt = (s, t) => Math.pow(1 + FACTOR * Math.max(0, t) / s, DECAY);
  async function setVoice(v) {
    S.voice = v; save('flow-next-voice', v);
    if (S.user) { try { await api('/api/next/voice', { voice: v }); } catch (e) { /* keep local choice */ } }
  }
  function voiceChips(available) {
    return `<div class="voices" role="radiogroup" aria-label="朗读声音">${Object.entries(VOICE_LABELS).map(([k, l]) =>
      `<button class="chip small" role="radio" data-voice="${k}" aria-checked="${S.voice === k}" aria-pressed="${S.voice === k}" ${available && !available.includes(k) ? 'disabled' : ''}>${l}</button>`).join('')}</div>`;
  }

  /* ---------- English: the Me and Practice tabs, the guide's frame, What's new (81-me.js 49-practice.js 49-guide.js 83-updates.js); docs/english-ui.md has the terms ---------- */
  enTable({
    // 49-guide.js (the frame only: the guide itself stays Chinese)
    '指南目录': 'Guide contents', '下载 PDF 版': 'Download PDF', '去练习': 'Go to Practice', '回到目录': 'Back to contents',
    '在指南里搜索': 'Search the guide', '搜一搜：比如 复习、录音、提醒': 'Search (the guide is in Chinese)',
    '没有找到，换个词试试，或者看看「常见问题」。': 'Nothing found. Try another word, or see the FAQ chapter.',
    '更新于 {n}-{n}-{n}': 'Updated {1}-{2}-{3}',

    // 49-practice.js
    '听和读': 'Listen and read', '说和写': 'Speak and write', '混合练习': 'Mixed drill', '{n} 个语法点按顺序连成路线，点亮一个学一个': '{1} grammar points in one path. Light them up one by one',
    '{n} 个生活和校园情景，和 AI 对话': '{1} scenes with AI',
    '做错的题、句型和整句': 'Missed questions, patterns and sentences', '现在没有到期的': 'Nothing due now',
    '第一次用？看操作指南 ›': 'New here? Read the guide ›',
    '需要留意：{x}': 'Needs work: {1}', '该复习：{x}': 'Due for review: {1}', '已点亮 {n} / {n}': '{1} / {2} lit',
    '今天建议': 'Suggested for today',
    '{x}离目标最远（{n} 分）': '{1} is furthest from your goal ({2} points)',
    '去练听力': 'Practice listening', '去练阅读': 'Practice reading', '去练词汇': 'Practice vocabulary',
    '去练语法': 'Practice grammar', '去练口语': 'Practice speaking', '去练写作': 'Practice writing',
    '有 {n} 个词等你复习': '{1} {1|word|words} to review', '先复习再学新的，记得最牢。': 'Review first, then learn new ones: it sticks best.',
    '先做今天的计划': "Start with today's plan", '今日页已经按你的水平排好了顺序。': 'Today is already set up for your level.', '打开今日': 'Open Today',

    // 83-updates.js (the entries themselves are content: they stay as written)
    '语流每一次更新改了什么，新的在上面。标着「用法变了」的，是要换个方式用的地方。': 'What changed in each Flow update, newest first. Items marked “Works differently” are used in a new way.',
    '用法变了': 'Works differently', '新功能': 'New features', '改进': 'Improvements', '修好的问题': 'Fixes', '内测中': 'In beta', '只在内测版': 'Beta only', '已经能在这里试，还没上正式版。': 'You can try these here; they are not on the main site yet.',
    '还没有更新记录。': 'No updates yet.',
    // 「发现哪里不对，可以在<a>问题反馈</a>里告诉我们。」
    '发现哪里不对，可以在': 'Something not right? Tell us in ', '里告诉我们。': '.',
    '语流更新了': 'Flow has been updated', '查看全部变化': 'See all changes',

    // 81-me.js: the page
    '进步': 'Progress', '目标': 'Goal', '现在': 'Now', '未设置': 'Not set',
    '目标 A2': 'Goal A2', '目标 B1': 'Goal B1', '目标 B2': 'Goal B2', '目标 C1': 'Goal C1',
    '现在 A2': 'Now A2', '现在 B1': 'Now B1', '现在 B2': 'Now B2', '现在 C1': 'Now C1',
    '我的考试': 'My exam', '每周目标': 'Weekly goal', '每周 {n} 天': '{1} {1|day|days} a week', '每周进度邮件': 'Weekly progress email',
    '单词读音方式': 'Word playback', '背词': 'Learn words', '外观': 'Appearance', '每天提醒': 'Daily reminder',
    '添加到桌面': 'Add to home screen',
    'iOS 专属功能': 'iOS features', '锁屏、小组件、Siri 等': 'Lock Screen, widgets, Siri and more', '安卓专属功能': 'Android features',
    'Windows 专属功能': 'Windows features', 'Mac 专属功能': 'Mac features', 'App 专属功能': 'App features',
    "打不开 App 的设置页，把语流 App 更新到最新版再试": "Can't open the app's settings. Update the Flow app and try again",
    '修改密码': 'Change password', '退出所有设备': 'Sign out everywhere', '导出我的数据': 'Export my data', '注销账号': 'Delete account',
    '绑定邮箱后，可以用验证码登录，忘记密码时自己找回。30 天内来过就一直保持登录；在别人的手机或电脑上用完，记得退出。': "With an email added, you can sign in with a code and reset a forgotten password yourself. You stay signed in if you come back within 30 days; on someone else's phone or computer, sign out when you're done.",
    '还没有绑定': 'None yet', '还没有绑定（邮件服务暂未开启）': 'None yet (email is not available yet)', '（邮件服务暂未开启）': '(email is not available yet)',
    '邮箱：{x}，点这里更换': 'Email: {1}. Tap to change', '绑定邮箱': 'Add email', '更换邮箱': 'Change email',
    '系统权限': 'System permissions', '麦克风、通知': 'Microphone, notifications',
    '更多': 'More', '认识语流、匿名问卷、新手引导': 'About Flow, survey, tour',
    '还没有设置水平': 'Level not set', '每天 {n} 分钟': '{1} min a day',
    '入门（A2）': 'Elementary (A2)', '中级（B1）': 'Intermediate (B1)', '中高级（B2）': 'Upper intermediate (B2)', '高级（C1）': 'Advanced (C1)',
    '本周学习天数': 'Days this week', '学完的材料': 'Texts done', '单词与表达': 'Words and expressions',
    '登录后才能保存进度、收藏表达和使用 AI。': 'Sign in to save progress and expressions, and to use AI.',
    '已退出': 'Signed out',
    // 内测版
    '去正式版': 'Go to the main site',
    '这里是语流的内测版（flow.jasa.hk），新功能先在这里试。账号和数据都和正式版分开，内测期间可能会清空。': 'This is the Flow beta (flow.jasa.hk), where new features are tried first. Accounts and data are separate from the main site and may be cleared during the beta.',
    '现在是 {x}（{n} 月 {n} 日 {n}:{n} 更新）。': 'This is {1} (updated {2}/{3} {4}:{5}).', '现在是 {x}。': 'This is {1}.',
    '这一版内测改了什么': 'What changed in this beta', '用法变了：': 'Works differently:',
    // 更多
    '认识语流': 'About Flow', '一页看完语流能帮你做什么': 'What Flow can do for you, on one page',
    '匿名问卷': 'Anonymous survey', '你想要什么样的英语学习网站': 'What kind of English site do you want?',
    '再看一遍新手引导': 'Replay the tour', '今日的几个主要按钮在哪': 'Where the main buttons on Today are',
    '重新显示使用提示': 'Show tips again', '比如「点词查词」，用到时再说一次': 'Like “Tap a word to look it up”, shown again when it applies',
    '使用提示会在用到时再出现一次': 'Tips will show again when they apply',

    // 81-me.js: AI 用量
    'AI 用量': 'AI use', '暂停中': 'Paused', '今天已满': 'Full for today', '不限次数': 'Unlimited', '还能用 {n} 次': '{1} left', '今天已用完': 'Used up for today',
    '今天': 'Today', '/ {n} 次': '/ {1}', '次': 'times', '{n} 次': '{1} {1|time|times}', '今天用了 {n} 次，共 {n} 次': '{1} of {2} used today',
    '预计 {n} 月 {n} 日恢复。': 'Back around {1}/{2}.', '{x}预计 {n} 月 {n} 日恢复。': '{1} Back around {2}/{3}.', '去问题反馈': 'Go to Feedback',
    '用到 AI 的批改、讲解、出题和对话，每次算一次；大家共用的讲解和例句、没有成功的那次不算。AI 朗读另有字数上限，不算在这里。': "Each AI check, explanation, question set or dialogue counts once. Shared explanations and examples, and tries that failed, don't count. AI voice has its own character limit and isn't counted here.",
    '用到 AI 的批改、讲解、出题和对话，每次算一次；大家共用的讲解和例句、没有成功的那次不算。AI 朗读另有字数上限，不算在这里。{x}': "Each AI check, explanation, question set or dialogue counts once. Shared explanations and examples, and tries that failed, don't count. AI voice has its own character limit and isn't counted here. {1}",
    '你的额度由管理员调整过。': 'Your limit was adjusted by an admin.',

    // 81-me.js: 外观 (字号、行距、主题色)
    '标准': 'Normal', '大': 'Large', '特大': 'Extra large', '宽松': 'Wide', '行距宽松': 'Wide spacing',
    '主题色': 'Accent', '字号': 'Text size', '行距': 'Spacing',
    '只换按钮、进度和链接的颜色；答对答错的颜色和标识不变。浅色、深色跟着手机的设置。': 'Changes only the color of buttons, progress and links; right and wrong answers keep their colors and marks. Light and dark follow your phone.',
    '只换按钮、进度和链接的颜色；答对答错的颜色和标识不变。浅色、深色跟着手机的设置。{x}': 'Changes only the color of buttons, progress and links; right and wrong answers keep their colors and marks. Light and dark follow your phone. {1}',
    '登录后会记在账号上。': 'Sign in to keep it with your account.',
    '课文、听力句子、讲解和释义的字会变大，菜单和按钮不变。': 'Texts, listening lines, explanations and meanings get bigger; menus and buttons stay the same.',

    // 81-me.js: 单词读音方式 (iPhone and iPad)
    '连续': 'Continuous',
    '从第一个音开始放；连着点单词时，灵动岛会一直显示「语流 · 单词」，停下 20 秒后收起。（默认）': 'Plays from the very first sound. While you tap word after word, the Dynamic Island keeps showing Flow and hides 20 s after you stop. (Default)',
    '每个词是一个前面留了一点静音的小音频，大部分单词不会出现在灵动岛上。「连续」没有声音时选这个。': 'Each word is a short clip with a little silence in front, so most words do not show on the Dynamic Island. Choose this if “Continuous” plays no sound.',
    '前面 {n} 秒': '{1} s lead-in', '{n} 秒': '{1} s', '{n} 秒（默认）': '{1} s (default)', '（默认）': '(default)',
    '「标准」时单词前面留的静音': 'Silence before a word in “Standard”',
    '开头还被吞，就选长一点；开头都全，可以选短一点，出现在灵动岛上的单词会更少。': 'If the start of a word still gets cut off, choose longer; if starts are complete, you can choose shorter, and fewer words show on the Dynamic Island.',
    '两种方式在静音键打开时都能听到。只影响这台手机。': 'Both play even with the silent switch on. Only on this phone.',
    '单词读音方式：{x}': 'Word playback: {1}', '「标准」时单词前面留 {n} 秒静音': '{1} s of silence before words in “Standard”',

    // 81-me.js: 背词 (the row's value 「认识在右 · 新词简洁 · 复习简洁」 and the toasts are put together in code: their parts)
    '背词设置': 'Learn words', '「认识」放在': '“Know it” side',
    '认识在右': 'Know it: right', '认识在左': 'Know it: left', '「认识」放在认识在右': 'Know it: right', '「认识」放在认识在左': 'Know it: left',
    '新词简洁': 'New: simple', '新词详细': 'New: detailed', '复习简洁': 'Review: simple', '复习详细': 'Review: detailed',
    '右边（默认）': 'Right (default)', '左边': 'Left',
    '和大多数背词 App 一样，右手点着顺。往右滑是认识，往左滑是不认识。': "Like most word apps; easy for the right hand. Swipe right if you know it, left if you don't.",
    '往左滑是认识，往右滑是不认识。': "Swipe left if you know it, right if you don't.",
    '复习单词和测词汇量都跟着变：按钮的位置、滑动的方向，电脑上的按键（1 2 3 和 ← →）也按按钮在屏幕上的位置。只影响这台设备。': 'Review and the vocabulary test both follow it: button positions, swipe directions, and on a computer the keys (1 2 3 and ← →) match the buttons on screen. Only on this device.',
    '点卡片作答': 'Tap to answer', '开': 'On', '关': 'Off',
    '复习卡的左、中、右三块，和下面三个按钮一样（「认识」那边就是认识）。只翻面看答案，翻面后还是点按钮评分；点错了可以「撤销」。': 'The left, middle and right of a review card work like the three buttons below (the “Know it” side is Know it). A tap only flips the card; after flipping, rate it with the buttons. Tapped by mistake? Use “Undo”.',
    '只用下面的按钮、滑动和按键。': 'Use only the buttons below, swipes and keys.',
    '手机和平板默认开，用鼠标的电脑默认关。': 'On by default on phones and tablets; off on computers with a mouse.',
    '下次复习再看一次说明': 'Show the how-to at the next review', '下次复习时再看一次': "You'll see it again at the next review",
    '复习卡：简洁还是详细': 'Review card: simple or detailed', '背新词': 'New words',
    '详细：翻面后多给释义的词性、第 3 个例句、易混词和记忆情况，正面只多一行灰字，不提示答案。详细每张多花一点时间，每天单词的时间不变，能复习的词会少一些。复习时顶上的「简 / 详」也能随时换。': 'Detailed: after you flip, you also get the part of speech, a 3rd example, easily confused words and how well you remember it; the front only adds one gray line and gives no hint. Detailed cards take a little longer each, so with the same daily word time you review a few fewer words. You can switch any time at the top of the review.',
    '背新词用详细的卡片': 'New words: detailed cards', '背新词用简洁的卡片': 'New words: simple cards',
    '复习用详细的卡片': 'Review: detailed cards', '复习用简洁的卡片': 'Review: simple cards',
    '点卡片的左、中、右也能作答了': 'You can now answer by tapping the left, middle or right of the card',
    '点卡片作答关了，只用按钮和滑动': 'Card tapping is off. Use the buttons and swipes',

    // 81-me.js: 朗读声音, 每天提醒
    '语流里的读音和朗读都是 AI 合成的，不是真人录的：精选材料和单词用 Kokoro，其余（AI 的回复、口语情景、没有录音的句子）用 CosyVoice，都是自然人声。放声音的地方写着一行小灰字「读音由 AI 合成」或「朗读由 AI 合成」，喇叭多的列表里每个喇叭右上角有一个淡淡的「AI」。学一篇材料时，也可以在「听」这一步随时切换声音。': 'All audio in Flow is made by AI, not recorded by people: featured texts and words use Kokoro; the rest (AI replies, speaking scenes, lines with no recording) uses CosyVoice. Both are natural voices. Where audio plays, a small gray line says “AI voice”; in lists with many speakers, each has a faint “AI” at its top right. When you study a text, you can switch the voice any time in the Listen step.',
    '朗读声音：{x}': 'Voice: {1}',
    '加到手机日历：每天到点提醒你打开今天的计划。不用装 App、不用邮箱，iPhone 和安卓都能用。': "Add it to your phone's calendar: a daily reminder to open today's plan. No app or email needed; works on iPhone and Android.",
    '打开下载的文件，选「添加到日历」即可；不想要了就在日历里删掉这个日程。': 'Open the downloaded file and choose “Add to Calendar”. To stop, delete the event in your calendar.',

    // 81-me.js: 把语流放到桌面 (the steps are split by <b> and the share icon: each piece reads on into the next)
    '把语流放到桌面': 'Put Flow on your home screen',
    '像 App 一样从桌面一点就开，界面全屏；听过的音频会缓存下来，网络差的时候也能复习。': 'Opens with one tap, full screen, like an app. Audio you have played is saved, so you can review on a weak connection.',
    '分享按钮': 'Share button', '点屏幕': 'Tap the ', '点': 'Tap the ', '底部中间': 'bottom-center', '右上角': 'top-right', '的分享按钮': ' share button',
    '往下滑，点「': 'Scroll down, tap “', '添加到主屏幕': 'Add to Home Screen',
    '」，再点右上角的「添加」': '”, then tap “Add” at the top right', '」，再点「添加」': '”, then tap “Add”',
    '苹果手机要用': 'On an iPhone, only',
    '才能放到桌面：点下面的「复制网址」，打开 Safari，粘贴并前往': 'can add Flow to the home screen. Tap “Copy link” below, open Safari, then paste and go',
    '在 Safari 里点底部中间的分享按钮': 'In Safari, tap the bottom-center share button', '，选「': ', then choose “',
    '微信里不能放到桌面：点右上角「': "WeChat can't add to the home screen: tap “", '」，选「': '” at the top right, then choose “',
    '在浏览器里打开「我的 → 添加到桌面」，按那里的两步做': 'In the browser, open “Me → Add to home screen” and follow the two steps there',
    '点浏览器右上角的': "Tap the browser's top-right", '（有的浏览器在底部，是': ' (some browsers have it at the bottom:',
    '选「': 'Choose “', '」或「': '” or “', '安装应用': 'Install app', '」（有的手机叫「添加到桌面」）': '” (on some phones, “Add to desktop”)',
    '点浏览器的菜单按钮（华为浏览器在底部，是': 'Tap the browser menu button (in Huawei Browser it is at the bottom:',
    '找到「': 'Find “', '」点一下（有的版本叫「添加至桌面」）': '” and tap it (some versions say “Add to desktop”)',
    '用 Chrome 或 Edge 打开语流，点地址栏右边的「安装」图标': 'Open Flow in Chrome or Edge and click the “Install” icon at the right of the address bar',
    '装好以后，可以从开始菜单或程序坞打开': 'Once installed, open it from the Start menu or the Dock',
    '安装到桌面': 'Install', '放好了，在桌面上找「语流」': 'Done. Look for Flow on your home screen',
    '网址已复制，去 Safari 粘贴打开': 'Link copied. Paste it in Safari', '复制这个网址，到 Safari 里打开': 'Copy this link and open it in Safari',

    // 81-me.js: 邮箱, 修改密码
    '当前密码': 'Current password', '完成绑定': 'Confirm', '验证码已发送': 'Code sent',
    '先输入当前密码确认是你本人，再把发到新邮箱的 6 位验证码填回来。': "Enter your current password to confirm it's you, then enter the 6-digit code sent to the new email.",
    '请先发送验证码，再填邮件里的 6 位数字': 'Send the code first, then enter the 6 digits from the email',
    '邮箱已绑定，忘记密码时可以自己找回了': 'Email added. You can now reset a forgotten password yourself',
    '改好以后，所有手机和电脑上的登录都会退出，用新密码重新登录就行。': "After the change you'll be signed out on every phone and computer. Just sign in again with the new password.",
    '原密码': 'Old password', '再输一次新密码': 'New password again', '新密码至少 {n} 位': 'The new password needs at least {1} characters',
    '两次输入的新密码不一样': "The two new passwords don't match", '密码已修改，请用新密码登录。': 'Password changed. Sign in with the new password.',

    // 81-me.js: 导出我的数据, 注销账号, 退出所有设备
    '单词本 · Excel 表格': 'Word list · Excel sheet', '单词本 · 导入 Anki': 'Word list · for Anki', '全部学习记录': 'All learning records',
    '{n} 条 · .csv': '{1} {1|entry|entries} · .csv', '{n} 条 · .txt': '{1} {1|entry|entries} · .txt',
    '微信里不能保存文件：点右上角「…」，选「在浏览器打开」，再到「我的 → 导出我的数据」。': "WeChat can't save files: tap “…” at the top right, choose “Open in browser”, then go to “Me → Export my data”.",
    '表格用 Excel、WPS 或 Numbers 直接打开：英文、中文意思、原文例句、来源和复习情况各占一列。Anki：在电脑上「文件 → 导入」选这个文件，正面是英文，背面是中文意思和原文例句。全部学习记录是一个 JSON 文件，有单词本、每次复习、学过的材料、测评和设置，留底或换地方用。': 'Open the sheet in Excel, WPS or Numbers: English, Chinese meaning, the example from the text, source and review state each have a column. Anki: on a computer, use “File → Import” and pick this file; the front is English, the back the Chinese meaning and the example. All learning records is a JSON file with your word list, every review, texts studied, tests and settings, to keep or take elsewhere.',
    // 「注销后，这个账号和它的全部学习记录都会删除，<b>不能恢复</b>：单词本和……但会从头开始。」
    '注销后，这个账号和它的全部学习记录都会删除，': 'This deletes the account and all its learning records, and ', '不能恢复': 'they cannot be recovered',
    '：单词本和复习安排、学过的材料、测评和能力雷达、写作和口语的批改记录、发过的问题反馈和截图。同样的用户名和邮箱以后可以重新注册，但会从头开始。': ': your word list and review schedule, texts studied, tests and the skills radar, writing and speaking corrections, and the feedback and screenshots you sent. The same username and email can sign up again later, but start from zero.',
    '想留一份？': 'Want a copy?', '先导出单词本和学习记录': 'Export your word list and records first',
    '输入密码确认': 'Enter your password to confirm', '永久注销这个账号': 'Delete this account for good', '请输入密码': 'Enter your password',
    '账号已注销，学习记录已全部删除': 'Account deleted, with all its learning records',
    '退出所有设备？': 'Sign out everywhere?', '已在所有设备上退出': 'Signed out everywhere',
    '所有手机、平板和电脑上的语流都会退出登录，包括这一台。学习记录不会丢，重新登录就回来了。': "Flow will sign out on every phone, tablet and computer, this one too. Your learning records stay; sign in again and they're back.",
    // seen on the pages (english_run)
    '错题和句型复习': 'Review mistakes and patterns', '写一段短文，让 AI 批改': 'Write a short piece', '未加入': 'Not joined',
    // 49-practice.js after the 练习 page's new look (#449)
    '几个语法点打乱一起练，记得更牢': 'Mix several grammar points for better recall',
    '读比你低一级的短文，练速度、攒阅读量': 'Short texts a level below yours, for speed and volume',
    '按话题和级别挑一篇来学': 'Pick a text by topic and level', '贴一段任何英文，变成可以学的材料': 'Paste any English and study it',
    '中国学习者容易混的音，听辨再跟读': 'Sounds Chinese speakers mix up: hear the difference, then shadow',
    '到期的单词和短语，一张张过': 'Due words and phrases, one card at a time', '最容易混的词放在一起练': 'Practice the words most often confused',
    '换词书、改每天学多少': 'Change your word book or daily amount', '{n} 分钟估一估你认识多少词': 'Estimate your vocabulary in {1} min',
    '考试和测评': 'Exams and tests', '中考高考、四六级、考研、专四专八、雅思，限时做': 'Timed sets: Zhongkao, Gaokao, CET-4/6, Kaoyan, TEM-4/8, IELTS',
    '{n} 题定出你的语法起点': '{1} questions to find your grammar level', '错题和句型': 'Mistakes',
    '{x}离你的目标最远，先练它': '{1} is furthest from your goal', '去练{x}': 'Practice {1}',
    '{x}，有 {n} 项到期': '{1}, {2} due',
    // 81-privacy.js: 按我的学习记录推荐 (a description of the feature; D2 2026-11-26: English is fine, the name matches the privacy notes)
    '按我的学习记录推荐': 'Recommend from my learning records',
    '关掉「按我的学习记录推荐」以后，推荐只按你选的水平和新旧排，不看你的学习记录。': "Turn off “Recommend from my learning records” and suggestions follow only the level you picked and what's new, not your records.",
    '了解更多': 'Learn more',
    '打开时，语流按你的学习记录给你挑内容：今日的「今天这篇」和「也可以读」（看你学过哪些、哪些语法要补、收藏和在背的词）、今日好句、今日计划里练哪一项，以及级别建议和周报里的建议。':
      "When it's on, Flow picks content from your learning records: “Today's text” and “More to read” on Today (what you've studied, grammar to work on, the words you saved and are learning), the line of the day, what today's plan practices, and the level and weekly report suggestions.",
    '关掉以后马上生效，只按你自己选的水平推荐：精选的在前，新的在前，不再看你的学习记录。复习单词和错题、复听和「接着学」还是按你学过的安排，那是在复习你自己的内容。':
      "Turning it off works at once: suggestions follow only the level you picked, featured and newest first, without your records. Word and mistake reviews, listening again and “Continue” still follow what you've studied, since they go over your own work.",
    '用到了哪些记录（隐私说明）': 'Which records are used (privacy notes, in Chinese)',
    '错题和句型，有 {n} 项到期': 'Mistakes: {1} due',
    // ability_radar.TIPS: the head of 今天建议 on 练习, one line (B9)
    '逐句听写和精听': 'Dictation drills', '轻松读，读得多一点': 'Read more easy texts', '提高每天新词数': 'More new words a day',
    '语法混合复习': 'Mixed grammar review', '口语路线的情景对话': 'Speaking scenes',
    // 81-me.js after 我的's new look (tiles, folds)
    '这周学了 {n} 天 · 学完 {n} 篇 · {n} 个词': 'This week: {1} {1|day|days} · {2} {2|text|texts} · {3} {3|word|words}',
    '达标 {n} 周': 'Goal met {1} {1|week|weeks}', '最近 7 天': 'Last 7 days', '{n} 道': '{1}', '还没有': 'None yet',
    '提醒和每周邮件': 'Reminders and weekly email', '账号和隐私': 'Account and privacy', '导出、注销、数据存放': 'Export, delete, data storage',
    '指南、隐私说明、反馈': 'Guide, privacy notes, feedback',
    // 81-habits.js: 我的 → 使用习惯 (B5), and its summary on 我的's row (今日列表 · 松绿 · 字号标准)
    '今日列表': 'List view', '今日卡片': 'Card view', '字号标准': 'Normal text', '字号大': 'Large text', '字号特大': 'Extra large text',
    '新词卡': 'New-word card', '背单词「认识」在': '“Know it” on the', '右边': 'Right', '返回我的': 'Back to Me',
  });
  /* ---------- English: what the server writes for the pages (next_service, skills_service, vocab_service, output_service, progress_service); docs/english-ui.md has the terms ---------- */
  enTable({
    // next_service.py: the levels (level_label on 今日 「按「入门（A2）」…」, 起点检查 「入门：…」) and what each means; the goals and
    // targets are in 01-en-shell.js
    '入门': 'Elementary', '中级': 'Intermediate', '中高级': 'Upper intermediate', '高级': 'Advanced',
    '能看懂简单句子，日常交流还比较吃力': 'You can read simple sentences; everyday talk is still hard',
    '能应付日常交流，读工作或学习材料要查不少词': 'You manage everyday talk; work or study texts need many look-ups',
    '能读懂大部分文章，想说得更自然、写得更地道': 'You can read most texts and want to speak and write more naturally',
    '接近流利，想打磨措辞、语气和风格': 'Nearly fluent; you want to polish wording, tone and style',
    // next_service.py: why a text is on 今日 (the grey chips under a card)
    '日常交流用得上': 'Useful in everyday talk', '工作沟通用得上': 'Useful at work', '考试阅读常见的文体': 'A common style in exam reading',
    '留学和海外生活用得上': 'Useful for study and life abroad', '适合「看懂影视、新闻」': 'Good for “Films, TV and news”',
    '有故事，读着轻松': 'A story, easy to read',
    '补一补「{x}」': 'Brush up on “{1}”', '新知识点「{x}」': 'New grammar point “{1}”',
    '你在背的「{x}」在这篇里': 'Has “{1}”, a word you are learning', '你收藏的「{x}」又出现了': 'Has your saved “{1}” again',
    '这一级的精选学完了，先试试 {x} 的': 'Featured texts at this level done; try {1}',
    '精读重学：今天学过': 'Read again closely: studied today', '精读重学：昨天学过': 'Read again closely: studied yesterday',
    '精读重学：{n} 天前学过': 'Read again closely: studied {1} {1|day|days} ago', '{n} 天前学过': 'Studied {1} {1|day|days} ago',
    '和你的目标相关': 'Fits your goal',
    // a grammar point's evidence (event_service.summarize, read by next_service.graph_states): 知识点 page 「做题：…」
    '待建立': 'No record yet', '待验证': 'Not checked yet', '独立完成一次': 'Done alone once', '独立完成': 'Done alone',
    '延迟记得': 'Remembered a day later', '迁移已有证据': 'Used in a new context', '需要巩固': 'Needs more practice',

    // skills_service.py: the day's plan on 今日 (each step's title and the grey line under it)
    '选一本词书': 'Choose a word book',
    '先给你挑了《{x}》，每天背几个新词': 'We picked “{1}” for you: a few new words a day',
    '按你的考试先选好了《{x}》，确认一下就能每天背': 'We picked “{1}” for your exam. Confirm it to start',
    '单词：先复习最该复习的 {n} 个': 'Words: the {1} most due first', '单词：复习 {n} 个': 'Words: review {1}',
    '单词：先复习最容易忘的 {n} 个': 'Words: the {1} easiest to forget first',
    '单词：复习 {n} · 新词 {n}': 'Words: review {1} · {2} new', '单词：复习 {n}': 'Words: review {1}', '单词：新词 {n}': 'Words: {1} new',
    '今天复习完这一轮就好': 'Just finish this round today', '这一轮复习完了': 'This round is done',
    '还有 {n} 个复习留到之后几天': '{1} more {1|review waits|reviews wait} for the next few days',
    '新词明天继续': 'New words tomorrow', '今天先复习，新词明天继续': 'Review today, new words tomorrow',
    '补积压：还剩 {n} 个，大约 {n} 天补完': 'Catching up: {1} left, about {2} {2|day|days}',
    '今天的都完成了': 'All done for today', '复习到期的词，再学新词': 'Review due words, then learn new ones',
    '复听：{x}': 'Listen again: {1}', '今天复听过了：听懂了{x}': 'Listened again today. Understood: {1}',
    '先不看原文听一遍': 'Listen once without the text first',
    '低一级（{x}），先找回状态': 'One level down ({1}) to get back into it',
    '只听一遍，或只读一段': 'Listen once, or read one paragraph', '听一遍，再读一遍': 'Listen once, then read it',
    '听、读、做理解题': 'Listen, read, answer the questions',
    '再读一篇': 'Read one more', '听两句、答一句': 'Two lines, one reply', '听完用一句话回答': 'Listen, then reply in one sentence',
    '容易混的音，听辨 + 跟读': 'Sounds that get mixed up: hear the difference, then shadow',
    '复述今天这篇': "Retell today's text", '用自己的话讲一遍，AI 看你讲到了哪些要点': 'Say it in your own words; the AI checks which points you covered',
    '先读懂，再讲出来': 'Understand it, then say it',
    '写一段短文': 'Write a short paragraph', '按评分维度批改，错误进错题本': 'Marked on each scoring area; mistakes go to Mistakes',
    '翻译练习': 'Translation practice', '汉译英，对照原文找差距': 'Chinese into English, compared with the original',
    '逐句听写': 'Dictation, line by line', '听错的词直接进复习': 'Words you mishear go straight to review',
    '仿写一句': 'Rewrite one sentence', '照今天这篇里的一句话，换成你自己的内容，AI 帮你改': "Take a line from today's text, make it about you, and the AI corrects it",
    '语法复习': 'Grammar review', '今天做了 {n} 题': '{1} {1|question|questions} done today',
    '还有 {n} 个点明天接着练': '{1} more {1|point|points} tomorrow', '都练到了': 'All covered',
    '语法混合复习：{x}': 'Mixed grammar review: {1}', '{x} 等 {n} 个点': '{1} and more ({2} points)', '{n} 道题混着做': '{1} mixed questions',
    '考试练习：{x}': 'Exam practice: {1}', '这周的一套做完了': "This week's set is done", '考前 {n} 天': '{1} {1|day|days} to the exam',
    '摸底，可以跳过': 'A first look; you can skip it', '词汇、语法、阅读限时一套，这周哪天做都行': 'A timed set of vocabulary, grammar and reading, any day this week',
    '考点语法：{x}': 'Exam grammar: {1}', '{x}常考的语法点混着练，{n} 道题': 'Grammar points common in {1}, mixed: {2} questions',
    '能力测评': 'Skills test', '今天测过了，雷达图已更新': 'Tested today; the skills radar is updated',
    '{x}该测一测了，选一项就行': 'Time to test {1}. Pick one',
    '轻松读一篇': 'Read an easy text', '今天读了 {n} 篇': 'Read {1} {1|text|texts} today',
    '比你的水平低一点，只读不做题': 'A little below your level; just read, no questions',
    '口语：{x}': 'Speaking: {1}', '雅思 Part {n}': 'IELTS Part {1}', '雅思口语': 'IELTS Speaking', '情景对话': 'Role-play', '第 {n} 轮': 'Round {1}',
    '今天说过了': 'Done speaking today',
    '考官问 {n} 个问题，说完看四项估计分': 'The examiner asks {1} questions; then see estimated scores on 4 criteria',
    '考官问 {n} 个问题，说完看四项估计分（再练一轮）': 'The examiner asks {1} questions; then see estimated scores on 4 criteria (one more round)',
    '这次多一条：{x}': 'One more rule this time: {1}', '换角色：你演{x}，AI 演{x}': 'Swap roles: you play {1}, the AI plays {2}',
    '和 AI 演一个情景，说四五句': 'Act out a scene with the AI, 4 or 5 lines',
    '听写三句': 'Dictation: 3 lines', '练耳朵，也练拼写': 'Trains your ear and your spelling', '今天 {n}/{n}': 'Today {1}/{2}',
    '错题和句型复习 · {n} 道': 'Review mistakes and patterns · {1} due',
    '做错过的题和收藏的句型，到期再来一次': 'Questions you missed and patterns you saved, again when due',
    '今天练表达，单词留到下次。5 分钟的日子，单词和表达轮着来。': 'Today is for expression; words wait until next time. On 5-minute days, words and expression take turns.',
    // skills_service.py: the level suggestion on 今日, the skills, the weekly report's 接下来的重点
    '最近 {n} 次 {x} 的理解题和听写平均 {n}%，可以试试更难一点的材料。': 'Your last {1} Check and dictation scores at {2} average {3}%. You could try harder texts.',
    '最近 {n} 次 {x} 的理解题和听写平均只有 {n}%，先降一级打牢基础会更顺。': 'Your last {1} Check and dictation scores at {2} average only {3}%. Going down a level to build a base will make it easier.',
    '听力': 'Listening', '阅读': 'Reading', '口语': 'Speaking', '发音': 'Pronunciation',
    '先把单词积压清掉：现在有 {n} 个单词到了复习时间。接下来几天，每天先复习一轮，再学新的内容。':
      'Clear the word backlog first: {1} {1|word is|words are} due for review. For the next few days, do one round of review before anything new.',
    // 「{skill}是现在最弱的一项，接下来几天{what}。」: the what parts read inside that sentence
    '{x}是现在最弱的一项，接下来几天{x}。': '{1} is your weakest skill now. For the next few days, {2}.',
    '每天复述一篇或和 AI 对话一轮': 'retell a text or do one dialogue with the AI each day', '写一段短文让 AI 批改': 'write a short paragraph for the AI to mark',
    '每天听写三句': 'do dictation, 3 lines a day', '先读懂再做理解题': 'understand the text before the questions', '多练这一项': 'practice it more',
    '这 7 天还没学：每天 10 分钟，先从今天这篇开始。': "No study these 7 days. Try 10 min a day, starting with today's text.",

    // vocab_service.py: word books (背词计划), their groups, word roots, examples, the vocabulary test (the exam chips are in 01-en-shell.js)
    '基础词汇': 'Basic words', '进阶词汇': 'Intermediate words', '高阶词汇': 'Advanced words', '精通词汇': 'Proficiency words', '拓展词汇': 'Extended words',
    '最常用的词，读懂日常文章的地基': 'The most common words, the base for everyday texts',
    '读懂一般报刊、课本文章需要的常用词': 'Common words for newspapers and textbooks',
    '读懂深度文章和学术入门材料的常见词': 'Words for in-depth texts and first academic reading',
    '面向英语专业和高阶考试的较低频词': 'Less common words for English majors and advanced exams',
    '更少见的词，适合继续扩充词汇量': 'Rarer words to keep growing your vocabulary',
    '四级词汇': 'CET-4 words', '六级词汇': 'CET-6 words', '考研词汇': 'Kaoyan words', '雅思词汇': 'IELTS words', '托福词汇': 'TOEFL words', 'GRE 词汇': 'GRE words',
    '大学英语四级考试大纲词汇': 'Words on the CET-4 syllabus', '大学英语六级考试大纲词汇': 'Words on the CET-6 syllabus',
    '全国硕士研究生招生考试英语大纲词汇': 'Words on the national postgraduate entrance exam (Kaoyan) syllabus',
    'IELTS 常考词汇': 'Words common in IELTS', 'TOEFL 常考词汇': 'Words common in TOEFL', 'GRE 常考词汇，难度最高': 'Words common in the GRE, the hardest',
    // the data books (corpus_data/wordbooks*.json), sent by vocab_service.registry()
    '中考词汇': 'Zhongkao words', '高考词汇': 'Gaokao words', '学术英语': 'Academic English', '商务英语': 'Business English', '专四词汇': 'TEM-4 words', '专八词汇': 'TEM-8 words',
    '中考英语词汇，常用词在前': 'Zhongkao English words, common ones first', '高考英语词汇（含中考词），常用词在前': 'Gaokao English words (Zhongkao words included), common ones first',
    '大学课程和学术论文里最常用的学术词，适合掌握常用词以后学': 'The academic words used most in courses and papers; for after the common words',
    '商务文件、财经新闻和职场里最常用的词，适合掌握常用词以后学': 'The words used most in business papers, finance news and at work; for after the common words',
    '英语专业四级：约 6200 词，覆盖四级词汇，常用词在前': 'TEM-4: about 6,200 words, CET-4 words included, common ones first',
    '英语专业八级：专四之外再加约 4900 词，覆盖六级、考研词汇': 'TEM-8: about 4,900 words beyond TEM-4, CET-6 and Kaoyan words included',
    '按词频': 'By frequency', '中学英语': 'Middle and high school', '大学英语': 'College English', '英语专业': 'English majors', '出国留学': 'Study abroad',
    '学术与职场': 'Academic and work', '其他词书': 'Other word books',
    '词根': 'Root', '前缀': 'Prefix', '后缀': 'Suffix', '词缀': 'Affix', '名词后缀': 'Noun suffix', '形容词后缀': 'Adjective suffix', '动词后缀': 'Verb suffix', '副词后缀': 'Adverb suffix',
    '词典例句': 'Dictionary example', '超纲难词': 'Rare words',

    // output_service.py: 发音 (what the AI heard), the end of a role-play, the AI's 还可以这样说 labels (the prompt fixes them)
    '这次没听清读的是什么，可以再读一遍': "Couldn't make out what you said. Try again",
    '听起来是 {x}（和 {x} 同音）': 'Heard {1} (sounds the same as {2})', '听起来是 {x}': 'Heard {1}',
    '听起来像 {x}（和 {x} 同音），不像 {x}': 'Sounds like {1} (same sound as {2}), not {3}',
    '听起来像 {x}，更接近 {x}，不像 {x}': 'Sounds like {1}, closer to {2} than {3}', '听起来像 {x}，接近 {x}': 'Sounds like {1}, close to {2}',
    '听起来像 {x}，不像 {x}': 'Sounds like {1}, not {2}', '没听出 {x}，听着像 {x}，可以再读一遍': "Didn't hear {1}; it sounds like {2}. Try again",
    '听起来接近 {x}': 'Close to {1}', '听起来像 {x}': 'Sounds like {1}',
    '这一轮练完了，下面是具体的反馈。': 'This round is done. Here is the detailed feedback.',
    '更自然': 'More natural', '更正式': 'More formal', '更简洁': 'Shorter', '参考': 'Reference',

    // progress_service.py: the dates in 周报's 这周的一次进步 (「11月20日 · 写作 · AI 帮你改过」)
    '{n}月{n}日': '{1}/{2}',
  });
  /* ---------- English: the page shell (next.html, 00-head.js, 02-shell.js …); docs/english-ui.md has the terms ---------- */
  enTable({
    // next.html
    '今日': 'Today', '练习': 'Practice', '单词': 'Words', '我的': 'Me',
    '正在打开…': 'Opening…', '返回': 'Back', '听一遍': 'Play',
    '明天': 'Tomorrow', '好': 'OK', '全部': 'All', '搜索': 'Search', '筛选': 'Filter', '上一页': 'Previous', '下一页': 'Next',
    '结束': 'End', '下一个': 'Next', '不会': "Don't know", '到期': 'due', '跳到主要内容': 'Skip to content', '主导航': 'Main menu',
    '语流 Flow': '语流 Flow', '语流 Flow 今日': '语流 Flow, Today', '每天一篇，学了就能用': 'One text a day, put to use',
    '内测': 'Beta', '内测版': 'Beta',
    // 00-head.js: the four steps, AI marks (both languages, Chinese first), waiting, errors, the AI count
    '听': 'Listen', '读': 'Read', '理解': 'Check', '用出来': 'Use it',
    'AI 生成': 'AI 生成 · AI-generated',
    '这部分由人工智能生成，可能有错，仅供参考': 'Written by AI. It may be wrong; use it as a guide only',
    '读音由 AI 合成': '读音由 AI 合成 · AI voice',
    '这段声音由人工智能合成，不是真人录音': 'This voice is made by AI, not recorded by a person',
    '{x}（AI 朗读）': '{1} (AI voice)',
    'AI 还在听，可能要多等一会儿': 'The AI is still listening. This may take a little longer',
    'AI 还在想，可能要多等一会儿': 'The AI is still thinking. This may take a little longer',
    '今天的 {n} 次 AI 用完了，北京时间早上 {n} 点重置；学材料、背单词和做题照常能用': "You've used today's {1} AI {1|request|requests}. They reset at {2} a.m. Beijing time; texts, words and exercises still work",
    '今天的 AI 还剩 {n} 次，北京时间早上 {n} 点重置': '{1} AI {1|request|requests} left today. They reset at {2} a.m. Beijing time',
    '网络连接失败，请检查网络': 'No connection. Check your network',
    '内容太大，传不上去，换小一点的再试': 'Too large to upload. Try something smaller',
    '服务暂时有点忙，请稍后重试': 'The service is busy. Please try again shortly',
    '没有成功，请稍后重试': "That didn't work. Please try again shortly",
    '登录已过期，请重新登录': 'You have been signed out. Please sign in again',
    '登录已过期，请重新登录。登录后会回到这一页。': "You have been signed out. Please sign in again; you'll come back to this page.",
    '今天的 AI 用量已满，北京时间早上 {n} 点恢复。': "Today's AI use is full. It comes back at {1} a.m. Beijing time.",
    '今天的 AI 用量已满，北京时间早上 {n} 点恢复。学材料、背单词、复习和做题照常能用。': "Today's AI use is full. It comes back at {1} a.m. Beijing time. Texts, words, review and exercises still work.",
    '还没接触': 'Not started', '读到过': 'Seen in a text', '用出来过': 'Used', '需要留意': 'Needs work', '做题已验证': 'Proven in exercises',
    '美音 · 女': 'American · female', '美音 · 男': 'American · male', '英音 · 女': 'British · female', '英音 · 男': 'British · male',
    // common words of the whole site (buttons, and the TERMS used on more than one page)
    '开始': 'Start', '完成': 'Done', '好的': 'OK', '确定': 'OK', '知道了': 'Got it', '取消': 'Cancel', '关闭': 'Close',
    '下一步': 'Next', '继续': 'Continue', '下一句': 'Next', '上一句': 'Previous', '跳过': 'Skip', '重试': 'Try again',
    '展开': 'Show', '收起': 'Hide', '撤销': 'Undo', '清空': 'Clear', '保存': 'Save', '已保存': 'Saved', '提交': 'Submit',
    '发送': 'Send', '删除': 'Delete', '暂停': 'Pause', '停止': 'Stop', '以后再说': 'Not now', '去看看': 'Take a look',
    '推荐': 'Suggested', '回到今日': 'Back to Today', '返回{x}': 'Back to {1}',
    '登录': 'Sign in', '注册': 'Sign up', '登录 / 注册': 'Sign in / Sign up', '退出登录': 'Sign out', '账号': 'Account',
    '用户名': 'Username', '密码': 'Password', '邮箱': 'Email', '验证码': 'Code',
    '能力': 'Skills', '班级': 'Class', '老师': 'Teacher', '设置': 'Settings', '使用习惯': 'Preferences', '帮助': 'Help',
    '学习目标': 'Goal', '水平': 'Level', '提醒': 'Reminders', '操作指南': 'Guide', '更新记录': "What's new", '问题反馈': 'Feedback',
    '复习': 'Review', '收藏': 'Save', '已收藏': 'Saved', '新词': 'New words', '背词计划': 'Word plan', '词书': 'Word book',
    '测词汇量': 'Vocab test', '错题本': 'Mistake log', '例句': 'Example', '表达': 'Expression', '翻译': 'Translate', '语法': 'Grammar',
    '精选': 'Featured', '全部材料': 'All texts', '我的文章': 'My texts', '轻松读': 'Easy reading', '学一篇': 'Study a text',
    '能力雷达': 'Skills radar', '知识图谱': 'Grammar map', '语法起点小测': 'Grammar level', '词汇辨析': 'Word pairs',
    '口语路线': 'Speaking path', '发音入门': 'Sounds', '考试练习': 'Exam practice', '我的进步': 'My progress',
    '周报': 'Weekly report', '简洁': 'Simple', '详细': 'Detailed', '朗读': 'Read aloud', '朗读声音': 'Voice',
    'AI 合成': 'AI 合成 · AI voice', 'AI 朗读': 'AI 朗读 · AI voice', 'AI 朗读（自然人声）': 'AI 朗读 · AI voice',
    '朗读由 AI 合成': '朗读由 AI 合成 · AI voice',
    '{n} 天': '{1} {1|day|days}', '{n} 分钟': '{1} min',
    // exam names (09-start.js from /api/next/meta, 42-sprint.js, 60-review.js)
    '中考': 'Zhongkao', '高考': 'Gaokao', '四级': 'CET-4', '六级': 'CET-6', '考研': 'Kaoyan', '专四': 'TEM-4', '专八': 'TEM-8',
    '雅思': 'IELTS', '托福': 'TOEFL',
    // 01-audio-offline.js: the voice, the player, why the browser voice reads this time
    '系统自带的声音': 'the system voice', '浏览器的声音': 'the browser voice',
    '不能用电脑朗读的声音': "can't use the computer voice", '没有放出声音': 'played no sound',
    '微信里{x}：点右上角「···」，选「在浏览器打开」就能听': 'WeChat {1}. Tap “···” at the top right and choose “Open in browser” to listen',
    '这个浏览器{x}，换 Safari 或 Chrome 试试': 'This browser {1}. Try Safari or Chrome',
    '{x}这次没读出来，再点一次试试': 'Nothing played with {1} this time. Tap again',
    '离线中': 'Offline',
    '离线中，这句还没存到本机，先用{x}': "You're offline and this sentence isn't on this device yet. Using {1} for now",
    '网络不好，这句先用{x}': 'Weak connection. Using {1} for this sentence',
    '自然人声这次生成得太慢，先用{x}': 'The natural voice is slow this time. Using {1} for now',
    '登录后能听 AI 朗读（自然人声），现在先用{x}': 'Sign in to hear the natural AI voice. Using {1} for now',
    'AI 朗读（自然人声）暂时没开，先用{x}': 'The natural AI voice is off for now. Using {1}',
    '今天的 AI 用量已满，北京时间早上 {n} 点恢复；新的句子先用{x}，已经生成过的照常放': "Today's AI use is full. It comes back at {1} a.m. Beijing time. New sentences use {2} for now; ones already made still play",
    '你的 AI 功能暂停中，新的句子先用{x}，已经生成过的照常放': 'Your AI features are paused. New sentences use {1} for now; ones already made still play',
    'AI 朗读（自然人声）这次没生成出来，先用{x}': "The AI voice didn't come through this time. Using {1} for now",
    '离线中，这个词的读音还没存到本机，先用{x}': "You're offline and this word's sound isn't on this device yet. Using {1} for now",
    '网络不好，这个词的读音没加载出来，先用{x}': "Weak connection: this word's sound didn't load. Using {1} for now",
    '正在准备朗读…': 'Getting the audio ready…',
    '这台设备放不了录音的格式，改用 AI 朗读一句一句读': "This device can't play the recording, so the AI voice reads it sentence by sentence",
    '这台设备放不了录音的格式，先用浏览器的声音读': "This device can't play the recording. Using the browser voice for now",
    '音频暂时没加载出来，稍后再点一次': "The audio didn't load. Tap again in a moment",
    '语流': 'Flow', '我的录音': 'My recording',
    '播放控制': 'Player controls', '盲听': 'Listen only', '盲听：先只听不看': 'Listen only: hear it first, without the text',
    '播放设置：语速、每句几遍、句后停顿': 'Playback: speed, repeats, pause after each sentence',
    '关闭播放（记住读到哪里）': 'Close player (keeps your place)', '已暂停': 'Paused',
    '第 {n} / {n} 句': 'Sentence {1} / {2}', '准备第 {n} 句…': 'Getting sentence {1} ready…', '正在准备朗读第 {n} 句…': 'Getting sentence {1} ready…',
    '{x}没有读出这一句，点「继续」再试一次': "This sentence didn't play with {1}. Tap “Continue” to try again",
    '没网时做的 {n} 项已同步': 'Synced {1} {1|thing|things} you did offline',
    // 02-shell.js: keyboard shortcuts
    '键盘快捷键': 'Keyboard shortcuts', '通用': 'General', '显示这张快捷键表': 'Show this list of shortcuts', '跳到搜索框': 'Jump to the search box',
    '关闭弹窗': 'Close a panel', '提交写作、复述、翻译': 'Submit writing, a retelling or a translation',
    '空格 / K': 'Space / K', '播放、暂停或继续全文': 'Play, pause or resume the whole text',
    'Tab 进入正文，← →': 'Tab into the text, then ← →', '逐词移动': 'Move word by word', '查当前的词': 'Look up the current word',
    'AI 讲解当前这句': 'AI explains the current sentence',
    '正面：不认识 / 模糊 / 认识（「认识」放在左边时左右反过来）': "Front: Don't know / Not sure / Know it (swapped when “Know it” is on the left)",
    '翻面：记错了 / 模糊 / 没错': 'Back: Wrong / Not sure / Right', '从左到右的按钮': 'The buttons, left to right',
    '↵ 或 空格': '↵ or Space', '翻面：加了框的那个（正面选的那一个）': 'Back: the framed one (your pick on the front)',
    '太简单，以后不用再背': "Too easy, don't show it again", '其实记错了': 'I got it wrong after all',
    '测词汇量：默认不认识 / 认识（「认识」放在左边时反过来）': "Vocabulary test: Don't know / Know it (swapped when “Know it” is on the left)",
    '触屏：复习时左滑「不认识」、右滑「认识」；弹窗向下拖可以关闭。': "Touch: in review, swipe left for “Don't know” and right for “Know it”. Drag a panel down to close it.",
    // 02-shell.js: the tab bar (read by a screen reader), the email nudge, WeChat
    '{x}，有 {n} 项': '{1}, {2} waiting', '{x}，有 {n} 项{x}': '{1}, {2} {3}', '该测了': 'due for a test',
    '绑定邮箱，忘记密码时可以自己找回': 'Add an email to reset your password', '去绑定': 'Add',
    '以后再说，{n} 天后再提醒': 'Not now, remind me in {1} days',
    '在默认浏览器中打开': 'Open in default browser', '在浏览器打开': 'Open in browser', '在浏览器里打开': 'Open in your browser',
    '在浏览器里打开，用起来更顺': 'Open in your browser. It works better there', '点右上角的「···」': 'Tap “···” at the top right',
    '选「{x}」': 'Choose “{1}”',
    '在浏览器里可以听全部录音、用浏览器朗读，还能把语流放到手机桌面。': 'In a browser you can hear every recording, use the browser voice and add Flow to your home screen.',
    '复制网址': 'Copy link', '先在微信里看看': 'Stay in WeChat for now', '网址已复制，到浏览器里粘贴打开': 'Link copied. Paste it into your browser',
    '长按复制：{x}': 'Press and hold to copy: {1}',
    '微信里部分声音和安装功能用不了。点右上角「···」，选「{x}」，可以听全部音频，还能把语流装到桌面。': "Some sounds and installing don't work in WeChat. Tap “···” at the top right and choose “{1}” to hear all audio and add Flow to your home screen.",
    '关闭提示': 'Close notice',
    // 02-shell.js: sign in, sign up, a forgotten password (the consent ticks and their error stay Chinese)
    '显示密码': 'Show password', '隐藏密码': 'Hide password',
    '注册老师账号': 'Create a teacher account', '找回密码': 'Reset password', '注册语流': 'Sign up for Flow', '登录语流': 'Sign in to Flow',
    '填绑定的邮箱，收到验证码后设一个新密码。设好就直接登录，其他手机和电脑上的登录会退出。': "Enter your account's email, then set a new password with the code we send. You'll be signed in here and signed out on other phones and computers.",
    '注册或登录': 'Sign up or sign in', '返回登录': 'Back to sign in', '先不注册': 'Not now', '先不登录': 'Not now',
    '验证码已发送，请查看邮箱': 'Code sent. Check your email',
    '内测版要凭邀请码注册，请填写收到的邀请码': 'The beta needs an invite code to sign up. Enter the code you received',
    '用户名需 2–40 个字符，不能有空格和 @': 'Usernames are 2–40 characters, with no spaces or @',
    '密码至少 10 位': 'Passwords are at least 10 characters', '请输入邮件里的 6 位验证码': 'Enter the 6-digit code from the email',
    '密码已重设，已经登录': "Password reset. You're signed in",
    '老师账号注册好了，欢迎你': 'Teacher account ready. Welcome', '老师账号注册好了，欢迎你，{x}': 'Teacher account ready. Welcome, {1}',
    '注册成功，欢迎你': "You're signed up. Welcome", '注册成功，欢迎你，{x}': "You're signed up. Welcome, {1}",
    '欢迎回来': 'Welcome back', '欢迎回来，{x}': 'Welcome back, {1}',
    '发送验证码': 'Send code',
    '验证码 10 分钟内有效。收不到就看看垃圾邮件，60 秒后可以重发。': 'The code works for 10 minutes. No email? Check your spam folder. You can resend after 60 seconds.',
    '用户名或邮箱': 'Username or email', '用邮箱验证码登录': 'Sign in with an email code', '用密码登录': 'Sign in with a password',
    '忘记密码？': 'Forgot password?', '忘记密码：请联系老师或管理员重设。': 'Forgot your password? Ask your teacher or an admin to reset it.',
    '新密码': 'New password', '至少 10 位': 'At least 10 characters',
    '至少 10 位，最好是一句只有你知道的话': 'At least 10 characters. A phrase only you know works best',
    '设置新密码并登录': 'Set new password and sign in', '邀请码': 'Invite code',
    '内测版要凭邀请码注册。字母不分大小写，横线可以不写。': "The beta needs an invite code to sign up. Case doesn't matter, and you can leave out the dashes.",
    '2–40 个字符，可以用中文，不能有空格和 @。登录时用户名和邮箱都可以用。': '2–40 characters. Chinese is fine; no spaces or @. You can sign in with your username or your email.',
    '注册后可以在「我的」里绑定邮箱，忘记密码时用它找回。': 'After signing up, add an email in Me so you can reset a forgotten password.',
    '注册并登录': 'Sign up', '注册老师账号并登录': 'Create teacher account',
    '设置新密码': 'Set a new password', '保存新密码': 'Save new password',
    '链接 30 分钟内有效。设好以后，用新密码登录；其他设备上的登录会退出。': "This link works for 30 minutes. Then sign in with the new password; you'll be signed out on other devices.",
    '密码已重设': 'Password reset', '密码已重设，请用新密码登录。': 'Password reset. Sign in with your new password.',
    '{n} 秒后可重发': 'Resend in {1}s', '重新发送': 'Resend',
    // 02-shell.js: the error page
    '没网时，这些已存到本机的材料还能学：': "You're offline. These texts on this device still work:", '反馈这个问题': 'Report this problem',
    // 03-channel.js: the beta's line and its first sheet
    '新功能先在这里试，账号和数据与正式版分开，详见「我的」': 'New features are tried here first. Accounts and data are separate from the main site; see Me',
    '关闭内测版提示': 'Close beta notice', '这里是语流内测版': 'This is the Flow beta',
    '语流的网址改成了 flowlang.cn。': "Flow's address is now flowlang.cn.",
    '你的账号和学习记录都在 flowlang.cn，用原来的用户名和密码登录就行（换了网址，要重新登录一次）。加到了手机桌面的话，也请在 flowlang.cn 重新添加一次。': 'Your account and progress are on flowlang.cn. Sign in there with your usual username and password (the new address needs one new sign-in). If you added Flow to your home screen, add it again from flowlang.cn.',
    '语流正式版的网址是': "Flow's main site is",
    '这里（flow.jasa.hk）用来先试还没正式上线的新功能。账号和数据都和正式版分开，内测期间可能会清空。': 'This site (flow.jasa.hk) is for trying new features before they go live. Accounts and data are separate from the main site and may be cleared during the beta.',
    '去正式版 flowlang.cn': 'Go to flowlang.cn', '留在内测版': 'Stay on the beta',
    // 04-home-app.js: the way back, a new version
    '返回上一页': 'Go back', '有新版本，点一下更新': 'New version. Tap to update', '今天先不更新': 'Not today',
    '正在更新…': 'Updating…', '已更新到新版本': 'Updated to the new version',
    // 06-offline.js: a text kept on this device
    '存到本机': 'Keep offline', '✓ 已存到本机': '✓ Kept offline', '没网也能学': 'Works without internet',
    '存到本机，没网也能学': 'Keep on this device to study offline', '已存到本机，没网也能学': 'Kept on this device. You can study it offline',
    '现在没网，存不了': "You're offline, so it can't be kept", '正在存…': 'Saving…',
    '现在没网：已存到本机的 {n} 篇还能学': "You're offline. You can still study {1} {1|text|texts} on this device",
    '现在没网：复习单词还能做，联网后自动同步': "You're offline. Word review still works and syncs when you're back online",
    // 07-accent.js
    '松绿': 'Green', '靛蓝': 'Indigo',
    // 08-drafts.js
    '已恢复上次没写完的内容': 'Brought back what you were writing last time', '已清空': 'Cleared',
    // 08-tour.js: the first-day tour
    '第 {n} 步，共 {n} 步': 'Step {1} of {2}', '第 {n} 步，共 {n} 步：{x}。{x}': 'Step {1} of {2}: {3}. {4}',
    '今天的计划': "Today's plan",
    '每天要做的几步都在这里。必做的做完会自动打勾；还有时间的话，下面还能多学一点。': "Each day's steps are here. The must-dos tick themselves off when done; with time left, there is more below.",
    '背新词和复习都在这里。复习时右滑「认识」、左滑「不认识」；「认识」放在哪边，可以在「我的 → 设置」里改。': "New words and review are here. In review, swipe right for “Know it” and left for “Don't know”. You can swap the sides in Me → Settings.",
    '每篇文章分四步：听、读、理解、用出来，大约 10 分钟，学过的表达会进单词本。': 'Each text has four steps: Listen, Read, Check, Use it. It takes about 10 minutes, and the expressions you learn go to Words.',
    '口语和更多练习': 'Speaking and more practice',
    '在「练习」里和 AI 扮演的角色对话练口语，还有考试练习、语法和跟读。': 'In Practice, talk with AI characters to practice speaking. There is also exam practice, grammar and shadowing.',
    '学习目标、朗读声音、字号这些设置，还有操作指南和更新记录，都在这里。': "Settings like your goal, voice and text size are here, plus the guide and what's new.",
    '开始今天的第一项': "Start today's first step",
    '建一个班': 'Create a class', '写上班级名，点「新建班级」。建好以后可以改名。': 'Enter a class name and tap “New class”. You can rename it later.',
    '把邀请码发给学生': 'Send the invite code to students',
    '每个班有一个 6 位邀请码。学生在「我的 → 班级」里输入，就加进来了。': 'Each class has a 6-character invite code. Students enter it in Me → Class to join.',
    '建好班以后，班级上会显示 6 位邀请码。发给学生，学生在「我的 → 班级」里输入就加进来了。': 'Once the class is made, its 6-character invite code shows on it. Send it to students; they enter it in Me → Class to join.',
    '看全班汇总': 'See the class summary',
    '人数够了以后，点班级就能看全班这一周学了多少、哪里卡住。只看全班的数字，看不到单个学生。': 'Once enough students join, tap the class to see how much it studied this week and where it got stuck. You see class totals only, never single students.',
    // 09-start.js: goal and level (first run, and 我的 → 学习目标)
    '学习目标和水平': 'Goal and level', '你学英语主要为了什么？': 'What are you learning English for?',
    '选一个，之后在「我的」里随时能改。': 'Pick one. You can change it anytime in Me.', '学英语主要为了什么': 'What you learn English for',
    '准备哪个考试？': 'Which exam?', '考试日期（选填，不确定可以先空着）': 'Exam date (optional, leave it blank if unsure)',
    '想达到什么水平？': 'What level do you want to reach?',
    '现在的水平不用先测：文章先按比目标低一档挑，以后在「能力」里测一下就更准。': 'No test needed now: texts start one level below your goal. A test in Skills later makes it more accurate.',
    '一周大概能学几天？': 'How many days a week?',
    '学一步材料或复习几个词就算一天，哪周没学够也不会清零。': 'One step of a text or a few review words counts as a day. A short week never resets your count.',
    '现在的水平': 'Current level', '这是按目标估的。': 'This is a guess from your goal. ', '这是语法起点小测给的。': 'This comes from the grammar placement quiz. ',
    '去能力里测一下': 'Test in Skills', '，比自己估更准。': ' for a more accurate level.',
    '每天想学多久？': 'How long each day?', '感兴趣的话题': 'Topics you like', '可以多选，不选就每天随机。': 'Pick any. With none, topics vary each day.',
    '开始学习': 'Start learning', '注册账号': 'Sign up', '已有账号？登录': 'Have an account? Sign in',
    '不注册也能先学；注册以后，进度换手机、换电脑都在。': 'You can start without an account. Sign up to keep your progress on any phone or computer.',
    '第一次来？先花一分钟看看语流能帮你做什么': 'New here? Take a minute to see what Flow can do for you',
    '{x}后会为你建好《{x}》每天 {n} 个新词，可以在「单词」里改。': 'Tapping “{1}” sets up a word plan: “{2}”, {3} new words a day. You can change it in Words.',
    '登录后会为你建好《{x}》每天 {n} 个新词的背词计划，可以在「单词」里改。': 'Once you sign in, a word plan is set up: “{1}”, {2} new words a day. You can change it in Words.',
    '先选一个目标': 'Pick a goal first', '已为你建好《{x}》每天 {n} 个新词': 'Word plan ready: “{1}”, {2} new {2|word|words} a day',
    '文章先按比目标低一档挑的（{x}）': 'Texts start one level below your goal ({1})',
    '去能力里测一下现在的水平，推荐会更准，每天的计划也会跟着调整。': 'Take a test in Skills to find your level. Suggestions get more accurate, and your daily plan adjusts too.',
    // 09-start.js: labels from /api/next/meta (next_service GOALS, GOAL_HINT, TARGETS, THEMES, LEVELS)
    '日常交流': 'Everyday talk', '工作沟通': 'Work', '考试': 'Exams', '留学和海外生活': 'Study or live abroad',
    '看懂影视、新闻': 'Films, TV and news', '兴趣': 'For fun',
    '中考到考研、专四专八、雅思': 'From Zhongkao to Kaoyan, TEM-4/8, IELTS', '出门、聊天、看懂身边的英文': 'Getting around, chatting, English around you',
    '邮件、会议、写报告': 'Emails, meetings, reports', '上课、租房、办事': 'Classes, renting, errands',
    '不看字幕也能跟上': 'Keep up without subtitles', '没有具体目标，想慢慢学': 'No set goal, learning at my own pace',
    '简单日常': 'Simple everyday', '读懂一般文章': 'Read most texts', '自如讨论': 'Discuss with ease', '接近母语': 'Near native',
    '校园学习': 'Campus', '旅行生活': 'Travel', '日常生活': 'Daily life', '职场沟通': 'Workplace', '文化交流': 'Culture', '科学素养': 'Science',
    'A2 入门': 'A2 Elementary', 'B1 中级': 'B1 Intermediate', 'B2 中高级': 'B2 Upper intermediate', 'C1 高级': 'C1 Advanced',
  });
  /* ---------- English: studying one text (20-study.js … 25-finish.js, 30-lookup.js, 80-library.js); docs/english-ui.md has the terms ---------- */
  enTable({
    // 20-study.js: the header, where the text comes from (the labels origin() sends)
    'AI 改写': 'Rewritten by AI', '未经人工审核': 'Not reviewed by a person',
    '经规范检查': 'Checked against our rules', '经人工审核': 'Reviewed by a person',
    'AI 生成，经规范检查：看规范检查查什么': 'AI-generated, checked against our rules: see what is checked',
    '来源：': 'Source:', '来源：{x}': 'Source: {1}', '来源': 'Sources',
    '来源 {n} 条': '{1} {1|source|sources}', '参考资料 {n} 条': '{1} {1|reference|references}', '怎么写的': 'How it was written',
    'Flow 编辑部原创': 'Original, by the Flow editors', 'Flow 原创教学示例': 'Flow original teaching example',
    'Flow 原创分级教学情境；编排分级，持续校对中': 'Flow original graded scene; still being proofread',
    '今日一读（Flow 原创）': "Today's read (Flow original)", '今日热点（联网检索）': 'In the news (web search)',
    '我导入的文章': 'My imported text', 'AI 出题': 'Questions by AI', 'AI 辅助编写': 'with AI help',
    '这篇材料从哪来': 'Where this text comes from',
    '今日一读是 AI 每天写的一篇原创短文（AI 生成）：话题从固定的话题池和节日、节气里选，不联网检索，不写新闻、时政、真实人物，也不写具体日期和数字。发布前先查一遍新闻和时政的词，再让 AI 自己查一遍，有一项不过就不发。没有人逐篇读过，当作额外阅读就好。':
      "Today's read is a short original text the AI writes each day (AI-generated). Its topic comes from a fixed list, holidays and solar terms. It does not search the web and never covers news, politics or real people, or gives exact dates and figures. Before it goes out it is checked for news and political words, then the AI checks it once more; if any check fails, it is not published. No one reads each text, so take it as extra reading.",
    // three pieces of one sentence around <b>: the English reads in the same order
    '今日热点是 AI 联网检索新闻后改写成的学习材料，': 'In the news is a text the AI rewrites from news it finds online. It is ',
    '没有经过人工审核': 'not reviewed by a person',
    '。下面是它检索到的来源，事实以原文为准。': '. Below are the sources it found; check facts against the originals.',
    '精选材料由 Flow 编辑部按统一的写作规范原创：': 'Featured texts are written from scratch by the Flow editors under one set of writing rules:',
    '精选材料由 Flow 编辑部按统一的写作规范原创（{x}）：': 'Featured texts are written from scratch by the Flow editors under one set of writing rules ({1}):',
    '不抄、不改写已有的文章、书籍和影视台词；': 'Nothing is copied or adapted from existing articles, books, films or TV;',
    '只写广为人知、稳定的常识，不写具体的统计数字、年份、价格和研究结论；': 'Only well-known, settled facts: no exact figures, years, prices or research findings;',
    '不写在世的真实人物，也不写时事新闻；': 'No living people and no current news;',
    '引用名句只用已进入公有领域的，并写明出处；': 'Quotes only from the public domain, with their source;',
    '每道理解题的答案都要在原文里找得到依据，发布前由程序逐篇检查。': 'The answer to every Check question is in the text, and a program checks each text before it is published.',
    '这是 Flow 编辑部较早用 AI 编写的练习材料，比精选短，没有中文导读和表达。': 'This is an earlier practice text the Flow editors wrote with AI. It is shorter than the featured texts and has no Chinese summary or expressions.',
    '这是 Flow 编辑部较早用 AI 编写的练习材料（{x}），比精选短，没有中文导读和表达。': 'This is an earlier practice text the Flow editors wrote with AI ({1}). It is shorter than the featured texts and has no Chinese summary or expressions.',
    '文中引用的名句': 'Quotes in the text', '核对事实用的参考资料': 'References used to check facts',
    '连载《{x}》第 {n} / {n} 集': 'Series “{1}”, part {2} of {3}',

    // 21-study-listen.js: 精听, 复听, 播放设置, 跟读, 听写
    '精听': 'Close listening', '跟读': 'Shadow', '听写': 'Dictation', '听的方式': 'Ways to listen',
    '几乎都懂': 'Almost all', '大部分': 'Most', '一半左右': 'About half', '很少': 'Very little',
    '原文出来了：没听懂的句子，点句子前面的喇叭单独再听几遍。': 'Here is the text. For a sentence you missed, tap its speaker to hear it again.',
    '复听：先不看原文，从头听一遍': 'Listen again: from the start, without the text',
    '点「播放全文」。听完选一下听懂了多少，原文就会出来，再看没听懂的句子。': 'Tap “Play all”. When it ends, choose how much you understood; the text then appears, so you can look at what you missed.',
    '听懂了多少': 'How much you understood',
    '记下了：听懂了{x}。这篇已经听熟了，以后不再安排复听。': 'Noted: {1}. You know this one well now, so it will not come back to listen again.',
    '记下了：听懂了{x}。{n} 天后再听一次。': 'Noted: {1}. Listen again in {2} {2|day|days}.',
    '记下了：听懂了{x}，联网后同步。': 'Noted: {1}. It syncs when you are online.',
    '这台设备放不了录音的格式，改用 AI 朗读一句一句读。': "This device can't play the recording, so the AI voice reads it sentence by sentence.",
    '这台设备放不了录音的格式，先用浏览器朗读。': "This device can't play the recording, so the browser reads it aloud for now.",
    '这篇还没有录音，先用浏览器朗读。': 'No recording for this text yet, so the browser reads it aloud for now.',
    '点 👁 只听不看，点喇叭单句反复听。': 'Tap 👁 to listen only; tap a speaker to repeat one sentence.',
    '点 👁 只听不看，点喇叭单句反复听；空格键播放 / 暂停。': 'Tap 👁 to listen only; tap a speaker to repeat one sentence. Space plays and pauses.',
    '这个浏览器不支持朗读，可以直接去「读」。': "This browser can't read aloud. You can go straight to “Read”.",
    '播放第 {n} 句': 'Play sentence {1}', '共 {n} 句': '{1} {1|sentence|sentences}',
    '听完了，去读 →': 'Done, go to Read →', '去读 →': 'Go to Read →',
    '播放全文': 'Play all', '从第 {n} 句继续': 'Resume at sentence {1}',
    '盲听：只听不看，再点一次显示原文': 'Listen only: the text is hidden. Tap again to show it', '已显示原文': 'Text shown',
    '播放设置': 'Playback settings', '只听不看': 'Listen only', '从头开始': 'Start over', '语速': 'Speed',
    '每句': 'Per sentence', '句后': 'After each', '复读：每句几遍': 'Repeat: times per sentence', '复读：句后停顿': 'Repeat: pause after each sentence',
    '{n} 遍': '{1} {1|time|times}', '循环': 'Loop', '不停': 'No pause', '停 {n} 秒': 'Pause {1} s', '留时间跟说': 'Time to say it', '声音': 'Voice',
    '已切换为{x}': 'Switched to {1}', '复读第 {n} 句': 'Repeating sentence {1}',
    '读前先认识这 {n} 个词': 'Know these {1} {1|word|words} first', '朗读 {x}': 'Play “{1}”',
    '全部加入复习': 'Add all to review', '加入后会在文章里标出来': 'They will be marked in the text',
    '登录后可以把这些词加入复习，按遗忘曲线安排。': 'Sign in to add these words to review on the forgetting curve.',
    '已加入 {n} 个词，读的时候会标出来': 'Added {1} {1|word|words}. {1|It|They} will be marked when you read',
    '这些词已经在复习里了': 'These words are already in review',
    '这篇已经点评 {n} 句，发音分平均 {n}（AI 估计）': '{1} {1|sentence|sentences} scored, average {2} (AI estimate)',
    'AI 没听清这一句。离麦克风近一点，完整读一遍再点评。': "The AI couldn't hear this sentence clearly. Move closer to the mic, read the whole sentence, then try again.",
    '发音分': 'Pronunciation score', '准确': 'Accuracy', '流利': 'Fluency', '完整': 'Completeness',
    '要练的音': 'Sounds to practice', '去练 {x} →': 'Practice {1} →',
    '朗读由 AI 合成。': '朗读由 AI 合成 · AI voice',
    '点一句开始练：先点 ▶ 听原声，再点录音键跟着读一遍（再点一次停止）。「对比」先放原声再放你的录音；{x}':
      'Tap a sentence to practice: tap ▶ to hear it, then the record button to read it after (tap again to stop). “Compare” plays the original, then your recording. {1}',
    '「AI 点评」给一个发音分（AI 估计），写出它听到的内容和要练的音。': '“AI feedback” gives a pronunciation score (AI estimate), what it heard and sounds to practice.',
    '登录后可以让 AI 点评、给发音分。': 'Sign in for AI feedback and a pronunciation score.',
    '听原声': 'Hear the original', '对比': 'Compare', '✦ AI 点评': '✦ AI feedback',
    '这一句的发音分（AI 估计）': 'Pronunciation score for this sentence (AI estimate)', '停止录音': 'Stop recording',
    '登录后，AI 会听你的跟读，指出漏读、读错和需要连读的地方。': 'Sign in and the AI listens to your shadowing and points out missed words, mistakes and sounds to link.',
    '录音太长了，读这一句就好': 'The recording is too long. Just read this sentence',
    '流畅': 'Smooth', '基本流畅': 'Mostly smooth', '有点断断续续': 'A bit choppy',
    '发音分和点评由 AI 估计，仅供参考': 'Score and feedback are AI estimates, a guide only',
    '要注意的': 'Things to watch', '其他要注意的': 'Other things to watch', '建议：{x}': 'Tip: {1}',
    'AI 听到：{x}': 'AI heard: {1}', '（没听清）': '(not clear)', '读到 {n}/{n} 个词': '{1}/{2} words said',
    '这篇正确率 {n}%': 'Accuracy here: {1}%', '可以反复播放': 'Play it as often as you like',
    '播放这一句': 'Play sentence', '慢速': 'Slow', '检查': 'Check', '跳过这句': 'Skip',
    '听到什么写什么，拼不出的词先空着': "Write what you hear. Leave out words you can't spell",
    '听错的词可以直接加入复习。': 'Words you miss can go straight into review.', '这篇听写完了': 'Dictation done for this text',
    '写对 {n} / {n} 个词': '{1} of {2} words right', '把听错的 {n} 个词加入复习': 'Add {1} missed {1|word|words} to review',
    '登录后可以把听错的词加入复习。': 'Sign in to add missed words to review.',
    '已加入 {n} 个词': 'Added {1} {1|word|words}',
    '已加入 {n} 个词；另外 {n} 个是常用词或已在复习里': 'Added {1} {1|word|words}; {2} more {2|is a common word|are common words} or already in review',
    '这几个都是常用词（不用专门背），或已经在复习里了': 'These are all common words (no need to learn them) or already in review',
    '已加入 {n} 个': 'Added {1}', '不用加': 'Not needed',

    // 22-study-read.js: the reader, 伴读, new words, 这篇的收获
    '读的时候点过的词会出现在这里，勾选后按遗忘曲线复习。': 'Words you tap while reading show up here. Tick them to review on the forgetting curve.',
    '这篇的生词': 'New words in this text', '勾选的会按遗忘曲线复习': 'Ticked words are reviewed on the forgetting curve',
    '加入复习': 'Add to review', '登录后可以把这些词加入复习。': 'Sign in to add these words to review.',
    '先勾选要复习的词': 'Tick the words to review first',
    '表达 {n}': 'Expressions {1}', '词汇': 'Vocabulary', '词汇 {n}': 'Vocabulary {1}',
    '知识点': 'Grammar points', '知识点 {n}': 'Grammar {1}',
    '收藏 {x}': 'Save “{1}”', '能直接搬进你自己话里的搭配。': 'Word combinations you can use in your own sentences.',
    '改写版新出现的表达': 'New expressions in the rewrite', '在知识图谱里看 →': 'See it in the grammar map →',
    '{n} 个表达': '{1} {1|expression|expressions}', '{n} 个词': '{1} {1|word|words}', '{n} 个知识点': '{1} grammar {1|point|points}',
    '查过 {n} 个词，可以加入复习': '{1} looked-up {1|word|words} to add to review', '查过的词会收在这里': 'Words you look up are kept here',
    '这篇的收获': 'Takeaways', 'AI 讲解第 {n} 句': 'Explain sentence {1} with AI',
    '这一版由 AI 按你的难度改写，原文没有改动': 'AI rewrote this version for your level. The original is unchanged',
    '适合我的版本（{x} · AI 改写）': 'My level ({1} · rewritten by AI)', '原文（{x}）': 'Original ({1})',
    '中文导读': 'In Chinese', '改写成 {x} 难度': '{1} version', '这篇原文是 {x}，你选的是 {x}': 'This text is {1}; your level is {2}',
    '伴读': 'Read along', '本篇词汇': 'Text vocabulary', '可能超出你的水平': 'May be above your level', '你在背的词': 'Words you are learning',
    '点词查词，点句尾 ✦ 讲解整句，长按拖选可收藏': 'Tap a word to look it up, tap ✦ to explain a sentence, press and drag to save',
    '点词查词，点句尾 ✦ 讲解整句，选中可收藏；键盘：Tab 进入正文后 ← → 逐词，↵ 查词，E 讲解': 'Click a word to look it up, click ✦ to explain a sentence, select to save. Keys: Tab into the text, then ← → by word, ↵ look up, E explain',
    '正文：左右方向键逐词移动，回车查词': 'Text: arrow keys move by word, Enter looks it up',
    '边听边看文字，读到哪句亮哪句': 'Listen and read; each sentence lights up as it is read',
    '读完了，做理解题 →': 'Done, go to Check →',
    '登录后可以让 AI 把这篇改写成适合你的难度（每天的 AI 次数有上限）。': 'Sign in to have the AI rewrite this text for your level (AI use has a daily limit).',
    '正在改写…': 'Rewriting…', '已打开改写版': 'Rewrite opened', '改写好了': 'Rewrite ready',

    // 23-study-check.js: Check questions
    '这篇还没有理解题。': 'No questions for this text yet.', '✦ 让 AI 出几道理解题': '✦ Have AI write questions',
    '同时挑出值得学的表达，写一段中文导读（用 1 次 AI）。': 'It also picks expressions worth learning and writes a Chinese summary (uses 1 AI request).',
    '去用出来 →': 'Go to Use it →', '登录后可以让 AI 出题。': 'Sign in to have AI write questions.',
    '正在出题…': 'Writing questions…', '题目出好了': 'Questions ready',
    '这些题目由 AI 根据这篇文章出，仅供练习': 'AI wrote these questions from this text, for practice only',
    '第 {n} / {n} 题': 'Question {1} of {2}', '主旨': 'Main idea', '推断': 'Inference', '词义': 'Word meaning', '细节': 'Detail',
    '答对了。': 'Correct.', '答案在原文这里：': 'The answer is here in the text:', '题答对': 'correct',
    '把学会的一句做成卡片，分享或保存': 'Make a card from a line you learned, to share or keep',
    '觉得有用？按你的目标每天推荐一篇': 'Find it useful? Get one text a day for your goal',
    '选学习目标和想达到的水平，大约 20 秒；注册以后，进度和收藏会保存下来。': 'Choose a goal and the level you want, about 20 seconds. Sign up and your progress and saved items are kept.',
    '选学习目标': 'Choose a goal', '注册 / 登录': 'Sign up / Sign in',

    // 24-study-output.js: Use it (仿写 · 复述 · 对话 · 翻译 · 写作)
    '仿写': 'Rewrite', '复述': 'Retell', '对话': 'Dialogue', '写作': 'Writing', '输出练习': 'Output practice',
    '说出来': 'Say it',
    '不看原文，用自己的话把这篇讲一遍': 'Without looking, tell this text in your own words',
    '可以打字，也可以点录音键直接说（最长 2 分钟）。AI 会提炼原文要点，看你讲到了哪些，并改出最影响理解的错误。': 'Type, or tap the record button and speak (up to 2 min). The AI finds the key points of the text, checks which you covered and fixes the mistakes that hurt understanding most.',
    '用英文复述这篇': 'Retell this text in English', '打字或录音都行': 'Type or record', 'AI 看看我的复述': 'Check my retelling',
    '已录好一段，可以提交了（会先转写）': 'Recorded. You can send it now (it is transcribed first)',
    '登录后 AI 会看你的复述讲到了哪些要点。': 'Sign in and the AI checks which key points your retelling covers.',
    '先说一段或写几句英文': 'Say something or write a few sentences in English first', '正在看…': 'Checking…',
    '点评和示范复述由 AI 生成，仅供参考': 'Feedback and model retelling are AI-generated, a guide only',
    'AI 听到：': 'AI heard: ', '讲到 {n} / {n} 个要点': 'Covered {1} of {2} key points', '原文要点': 'Key points of the text',
    '用上了原文的表达：': 'Expressions from the text you used:', '示范复述': 'Model retelling',
    '朗读示范复述（AI 朗读）': 'Play the model retelling (AI voice)',
    '围绕这篇的话题和 AI 聊几句': 'Chat with the AI about this topic', '对话里的另一方由 AI 扮演': 'The AI plays the other person',
    'AI 扮演情景里的另一方。可以打字或说，每说一句它会顺手纠正；聊 4–6 轮后点「结束并总结」。': 'The AI plays the other person in the scene. Type or speak; it corrects each line as you go. After 4–6 turns, tap “End and sum up”.',
    '结束并总结': 'End and sum up', '开始对话': 'Start dialogue', '用英文回答…': 'Answer in English…',
    '登录后可以和 AI 做情景对话。': 'Sign in to role-play with the AI.', '{x}（AI 扮演：{x}）': '{1} (AI plays: {2})', '（AI 扮演：{x}）': '(AI plays: {1})',
    '提示：{x}': 'Hint: {1}', '聊得差不多了，可以结束并看总结': 'Good chat. You can end it and see the summary',
    '这一轮说满 {n} 句了，点「结束并总结」': 'That is {1} lines this round. Tap “End and sum up”',
    '这一轮说满 {n} 句了，点「结束并看反馈」': 'That is {1} lines this round. Tap “End and see feedback”',
    '先说一两句再总结': 'Say a line or two first', '总结和建议由 AI 生成，仅供参考': 'Summary and tips are AI-generated, a guide only',
    '说得好的句子': 'Lines you said well', '可以学的表达': 'Expressions to learn', '再练一轮': 'Another round', '换个练法：翻译': 'Try another way: Translate',
    '汉译英': 'Chinese → English', '英译汉': 'English → Chinese', '换一句': 'Another sentence', '你的译文': 'Your translation',
    '译成英文…': 'Translate into English…', '译成中文…': 'Translate into Chinese…',
    '译完对照原文，看哪里不一样。': 'When done, compare with the original to see what differs.',
    '意思准确、读起来像中文就是好译文。': 'A good translation is accurate and reads like natural Chinese.',
    '登录后可以做汉译英（中文原句由 AI 翻出，全站共享）。': 'Sign in to translate from Chinese (the Chinese sentences are translated by AI and shared by everyone).',
    '登录后 AI 会批改你的译文。': 'Sign in and the AI marks your translation.', '先写下你的译文': 'Write your translation first',
    '评分和讲解由 AI 生成，仅供参考': 'Score and explanation are AI-generated, a guide only', '得分 {n}': 'Score {1}',
    '原文': 'Original', '参考译文': 'Reference translation', '另一种自然说法：{x}': 'Another natural way: {1}',
    '建议 {n}–{n} 词': 'Aim for {1}–{2} words', '{n} 词': '{1} {1|word|words}',
    '围绕这篇的话题，写一段你自己的看法或经历。': 'Write a paragraph on this topic: your view or your own experience.',
    '按内容、结构、准确、丰富四个维度批改，给段落点评和示范段落；改出来的错误进错题本。': 'Marked on content, organization, accuracy and range, with notes on each paragraph and a model paragraph. Mistakes found go into Mistakes.',
    'AI 批改': 'Mark with AI', '你的英文作文': 'Your English essay',
    '登录后 AI 会按评分维度批改你的短文。': 'Sign in and the AI marks your writing on each scoring area.',
    '至少写 40 个词': 'Write at least 40 words', '正在批改…': 'Marking…',
    '内容切题': 'Content', '结构衔接': 'Organization', '语言准确': 'Accuracy', '词汇句式': 'Range',
    '批改、评分和示范由 AI 生成，仅供参考': 'Marking, scores and model are AI-generated, a guide only',
    '这篇体现的水平约 {x}': 'Level shown: about {1}', '段落点评': 'Paragraph notes', '第 {n} 段': 'Paragraph {1}',
    '可以写得更好': 'Could be better', '示范段落': 'Model paragraph', '再批改一次': 'Mark again',
    '这篇 {n} 词，任务建议 {n}–{n} 词：{x}': 'This is {1} {1|word|words}; the task asks for {2}–{3}. {4}',
    '内容展开得还不够，考试里会影响「内容」分。': 'The content is not developed enough; in an exam this lowers the “Content” score.',
    '超出了建议长度，考试里要注意时间和篇幅。': 'It is over the suggested length; in an exam, watch your time and length.',
    '朗读参考句（AI 朗读）': 'Play the model sentence (AI voice)',
    '可以试着用上你在背的词：': 'Try using words you are learning:', '（用对了算一次成功复习）': '(used correctly, it counts as a review)',
    '你的英文': 'Your English', '写一两句就好，写错没关系。': 'A sentence or two is enough. Mistakes are fine.',
    '让 AI 帮我改': 'Let AI correct it', '先用英文写一个短句。': 'Write a short sentence in English first.',
    '登录后 AI 会帮你改写，并给出三种更好的说法。': 'Sign in and the AI corrects it and gives three better ways to say it.',
    '正在看你写的…': 'Reading what you wrote…', '再改一次': 'Correct again',
    '批改由 AI 生成，仅供参考': 'Corrections are AI-generated, a guide only',
    '你写的已经是对的': 'What you wrote is already correct', '改对之后': 'Corrected', '用对了：': 'Used well:',
    '还可以这样说': 'Other ways to say it', '收藏这句': 'Save this sentence',
    '你用到了正在背的词': 'You used words you are learning',
    '用对的算一次成功复习；用错的会提前安排复习。': 'Used right, it counts as a review; used wrong, it comes back for review sooner.',
    '值得收藏': 'Worth saving',

    // 25-finish.js: 这篇完成了
    '这篇完成了': 'Text done', '正在整理这篇学到的…': 'Gathering what you learned…',
    '把学会的一句做成卡片': 'Make a card from a line you learned',
    '收藏的表达和生词会按遗忘曲线安排复习。': 'Saved expressions and new words come back for review on the forgetting curve.',
    '今天还可以用 AI {n} 次。收藏的表达和生词会按遗忘曲线安排复习。': '{1} AI {1|request|requests} left today. Saved expressions and new words come back for review on the forgetting curve.',
    '看知识图谱': 'See the grammar map', '下一集：第 {n} 集': 'Next: part {1}',
    // a saved list sits between these pieces: 「收藏了 3 个：」 <b>…</b> 「 等，明天开始复习」
    '收藏了 {n} 个：': 'Saved {1}:', '等': 'and more', '等，明天开始复习': 'and more; review starts tomorrow', '，明天开始复习': '; review starts tomorrow',
    '还没收藏。这篇的重点：': 'Nothing saved yet. Key ones here:', '这篇没有收藏表达': 'No expressions saved from this text',
    '没有收藏生词；这篇里有你在背的 {n} 个：': 'No new words saved. Words you are learning here ({1}):',
    '这篇没有收藏生词': 'No new words saved from this text', '这篇没有标出语法点': 'No grammar points marked in this text',
    '这篇的 {n} 个语法点都做题验证过了 ✓': 'Grammar here: all {1} proven in exercises ✓',
    '「{x}」写错了 {n} 次，做 {n} 题巩固': '“{1}”: wrong {2} {2|time|times}. Do {3} questions to firm it up',
    '「{x}」写错了 {n} 次（': '“{1}”: wrong {2} {2|time|times} (', '），做 {n} 题巩固': '). Do {1} questions to firm it up',
    '「{x}」需要留意，做 {n} 题巩固': '“{1}” needs work. Do {2} questions to firm it up',
    '这篇用到了「{x}」，做 {n} 题验证一下': 'This text uses “{1}”. Do {2} questions to check it',

    // 30-lookup.js: looking up a word, AI 讲解, saving
    '这个词在你的复习里，查了说明还不熟，已提前安排复习': "This word is in your review. Looking it up means it isn't solid yet, so it comes back sooner",
    '原形 {x}': 'Base form: {1}', '· 原形 {x}': '· Base form: {1}', '在这篇里': 'In this text',
    '词典里没有这个词，可以先收藏，复习时再查。': "This word isn't in the dictionary. Save it now and look it up when you review.",
    '容易混': 'Easy to mix up', '辨析练习 →': 'Practice word pairs →',
    '收藏这个词': 'Save word', '收藏整句': 'Save sentence', '✦ AI 讲解整句': '✦ Explain with AI',
    '登录后，AI 会结合知识图谱讲解这句话的结构、语气和可模仿的句型。': "Sign in and the AI explains this sentence's structure, tone and patterns to copy, linked to the grammar map.",
    'AI 讲解': 'AI explanation', '正在分析这句话…': 'Looking at this sentence…', '朗读这句（AI 朗读）': 'Play this sentence (AI voice)',
    '可模仿的句型': 'Pattern to copy', '收藏这个句型': 'Save pattern',
    '登录后才能收藏，并按遗忘曲线提醒你复习。': 'Sign in to save. You will be reminded to review on the forgetting curve.',
    '已经在复习里了，已更新原句': 'Already in review. Sentence updated', '已收藏，会按遗忘曲线提醒你复习': 'Saved. You will be reminded to review on the forgetting curve',
    '已在复习里 ✓': 'In review ✓', '已收藏 ✓': 'Saved ✓',

    // 80-library.js: All texts, a series
    '← 全部材料': '← All texts', '一读': 'Daily read',
    '{n} 篇': '{1} {1|text|texts}', '范围': 'Which texts', '难度': 'Level', '全部难度': 'All levels', '话题': 'Topic', '全部话题': 'All topics',
    '连载故事': 'Series', '单篇': 'Single texts', '这个筛选下还没有材料。': 'No texts for this filter yet.',
    '已读 {n} / {n} 集': 'Read {1} of {2}', '继续第 {n} 集': 'Continue with part {1}', '读完了': 'All read',
    '共 {n} 集': '{1} {1|part|parts}', '从第 {n} 集开始': 'Start with part {1}', '继续：第 {n} 集': 'Continue: part {1}',
    '六集都读完了。可以回到任意一集，再听一遍或者重写输出任务。': 'You have read all six parts. Go back to any part to listen again or redo the Use it tasks.',
    '每集约 300 词，C1 难度，原创连载。每集都有听、读、理解和输出四步，读完理解题就算读过这一集。': 'Each part is about 300 words at C1, an original series. Each has the four steps Listen, Read, Check and Use it; finish the questions and the part counts as read.',
    // after the new looks of 理解 and 用出来 (B9, 2026-11-26)
    '照这句写一句': 'Write one like this', '可以试着用上你在背的词：{x}（用对了算一次成功复习）': "Try a word you're learning: {1} (using it right counts as a review)",
    '用上了原文的表达：{x}': 'Used from the text: {1}', '提示：': 'Hint: ',
    '答对了': 'Correct', '答错了': 'Wrong', '正确答案是 {x}': 'The answer is {1}', '答案在原文这里': 'Where the text says it',
    '看结果': 'See results', '下一题': 'Next question', '你选的': 'Your pick', '去用出来': 'Go to Use it',
    '{x}，点一下再看这一题': '{1}. Tap to see this question again',
    // 80-library.js after its new look
    '低一级': 'A level down', '读到第 {n} 集 · 继续第 {n} 集': 'Read {1} · next: part {2}',
    // the record button (B9 #458: 「点录音键」 instead of 「点 ●」)
    '用英文回答，或者点录音键说出来': 'Answer in English, or tap the record button and speak',
    '点录音键开始说，说完再点一下结束': 'Tap the record button to start, and again when you finish',
  });
  /* ---------- English: 今日 (10-welcome-today.js, 11-progress.js, 12-daily-line.js, 26-two-lines.js, 70-learner.js); docs/english-ui.md has the terms ---------- */
  enTable({
    // 10-welcome-today.js: the greeting (with a name the comma is in the same text node), the plan, the cards
    '夜深了': "It's late", '早上好': 'Good morning', '中午好': 'Hello', '下午好': 'Good afternoon', '晚上好': 'Good evening',
    '夜深了，': "It's late, ", '早上好，': 'Good morning, ', '中午好，': 'Hello, ', '下午好，': 'Good afternoon, ', '晚上好，': 'Good evening, ',
    '已完成 {n} / {n} 步': '{1} of {2} steps done',
    '重学': 'Revisit', '简版': 'Short', '精读重学': 'Read again closely', '今天这篇': "Today's text",
    '这一级（{x}）的精选还剩 {n} 篇没学。{x}': '{2} featured {2|text|texts} left at your level ({1}). {3}',
    '学完以后先推 {x} 的精选，再推精读重学。': 'After these, we suggest {1} featured texts, then texts to read again closely.',
    '学完以后先推精读重学，每周也会加新的。': 'After these, we suggest texts to read again closely. New ones are added every week.',
    '这一级（{x}）的精选你都学过了：先推 {x} 的精选，也可以': "You've studied every featured text at your level ({1}). Next we suggest {2} featured texts, or you can",
    '换个水平': 'change your level',
    '{x} 的精选你都学过了：先精读重学，每周也会加新的。': "You've studied every featured text at {1}. Next, read texts again closely; new ones are added every week.",
    '{n} 步': '{1} {1|step|steps}', '约 {n} 分钟': 'About {1} min', '大约 {n} 分钟': 'About {1} min',
    '今天的计划完成了': "Today's plan is done",
    '今天的计划，已完成 {n} 步，共 {n} 步': "Today's plan: {1} of {2} steps done",
    '{x}今天的练习': "{1} today's practice",
    '都完成了。{x}多学的照样算进「这周进步」。': 'All done. {1} Extra study still counts toward “This week”.',
    '想多学一点，下一篇是《{x}》。': 'Want more? Next up: “{1}”.', '想多学一点，就再挑一篇。': 'Want more? Pick another text.',
    '再学一篇': 'Study another text', '做 {n} 道语法题': 'Do {1} grammar {1|question|questions}',
    '今天或明天什么时候有空复习？': 'When can you review, today or tomorrow?',
    '还有时间的话': 'If you have time', "{n} 项 · 不算进今天的计划": "{1} {1|item|items} · not part of today's plan",
    '本周任务': "This week's tasks", '这周哪天做都行，不占每天的时间': "Any day this week. It doesn't use your daily time",
    '周': 'W',
    '今天学一篇，用上一句。': 'Study a text today, then use a line from it.',
    '按「{x}（{x}）」为你挑选 ·': 'Picked for level {2} ·', '调整': 'Change', '今日推荐': "Today's pick",
    '{n} 词 · 约 {n} 分钟 · 听、读、理解、用出来': '{1} {1|word|words} · About {2} min · Listen, Read, Check, Use it',
    '今天没有可推荐的材料了。': 'No more texts to suggest today.',
    '本周学了 {n} 天': 'Studied {1} {1|day|days} this week', '本周 {n} 天': '{1} {1|day|days} this week',
    '也可以读': 'More to read', '按 {x} 挑选 · 调整': 'Picked for {1} · Change',
    '更多材料': 'More texts', '按话题和级别挑一篇': 'Pick one by topic and level',
    '今天学了约 {n} 分钟': 'About {1} min studied today', '都做完了': 'All done', '还要约 {n} 分钟': 'About {1} min to go',
    '必做 {n} 步 · 约 {n} 分钟': '{1} must-do {1|step|steps} · About {2} min',
    '我的材料': 'My texts', '继续《{x}》': 'Continue “{1}”', '练《{x}》': 'Practice “{1}”',
    '贴课本或讲义进来练': 'Paste in a textbook page or handout to practice', '你自己贴进来的': 'Pasted in by you',
    '课本、讲义、面试题都行，用语流的四步来练': "Textbooks, handouts, interview questions: practice any of them with Flow's four steps",
    // 欢迎回来 (the line under it and the words left are one text node)
    '单词还剩 {n} 个，大约 {n} 天补完。': '{1} {1|word|words} left, about {2} {2|day|days} to catch up.',
    '单词还有 {n} 个，之后几天慢慢补上。': '{1} {1|word|words} still to go, spread over the next few days.',
    '你 {n} 天没学了，没关系。今天只做 {n} 件事，约 {n} 分钟。': "You've been away {1} {1|day|days}. That's OK. Just {2} {2|thing|things} today, about {3} min.",
    '你 {n} 天没学了，没关系。今天只做 {n} 件事，约 {n} 分钟。{x}': "You've been away {1} {1|day|days}. That's OK. Just {2} {2|thing|things} today, about {3} min. {4}",
    '今天的几件事做完了，明天照常。': "Today's tasks are done. Back to normal tomorrow.",
    '今天的几件事做完了，明天照常。{x}': "Today's tasks are done. Back to normal tomorrow. {1}",
    '今天已经学了约 {n} 分钟，超过你定的 {n} 分钟，剩下的可以留到明天。': "You've studied about {1} min today, past your {2} min. The rest can wait until tomorrow.",
    // 每周目标
    '每周学几天': 'Days a week',
    '一周里学够这么多天就算达成。哪天没空也没关系，不会清零；坚持的是一周一周，不是天天打卡。': "Study this many days in a week to reach it. Missing a day is fine and nothing resets: it's about keeping going week by week, not checking in every day.",
    '学一步材料或复习几个词，都算学了这一天。': 'One step of a text or a few review words counts as a study day.',
    '每周目标：{n} 天': 'Weekly goal: {1} {1|day|days}',
    '本周目标达成！': 'Goal reached this week', '本周目标达成！一共达成 {n} 周了': 'Goal reached this week. {1} {1|week|weeks} so far',
    '学了 {n}/{n} 步': '{1}/{2} steps done', '已存到本机': 'Kept offline',
    // notices under the plan
    '班级试用几周了，花 {n} 分钟填一份匿名问卷？': 'Your class trial is a few weeks in. Take a {1}-minute anonymous survey?',
    '去填写': 'Take the survey', '不用了': 'No thanks',
    '登录后，进度和收藏的表达会保存下来': 'Sign in to keep your progress and saved expressions',
    '不登录也可以听、读和做理解题。': 'You can listen, read and answer check questions without signing in.',
    '最近两周每周学 {n} 天': 'You studied {1} {1|day|days} a week for the last 2 weeks',
    '最近两周学了 {n} 天和 {n} 天': 'You studied {1} and {2} days in the last 2 weeks',
    '{x}，要不要把目标改成每周 {n} 天？': '{1}. Change your goal to {2} {2|day|days} a week?',
    '目标定在做得到的地方，每周都能达成。以前达成的周不会被扣，以后也可以在「我的」→「每周目标」里改回来。': 'A goal you can keep is one you reach every week. Weeks already reached stay counted, and you can change it back in Me → Weekly goal.',
    '改成每周 {n} 天': 'Change to {1} {1|day|days}', '不用，保持 {n} 天': 'No, keep {1} {1|day|days}',
    '上周学了 {n} 天，目标达成了 🎉': 'You studied {1} {1|day|days} last week and reached your goal 🎉',
    '上周学了 {n} 天，离目标还差 {n} 天': 'You studied {1} {1|day|days} last week, {2} short of your goal',
    '这周接着来。': 'Keep going this week.',
    '没关系，这周重新开始，学一步材料或复习几个词就算一天。': "That's OK. This week is a fresh start: one step of a text or a few review words counts as a day.",
    '看周报': 'See weekly report',
    '把语流放到手机桌面': 'Add Flow to your home screen',
    '像 App 一样一点就开，全屏；听过的音频网络差的时候也能复习。': 'It opens with one tap, full screen, like an app. Audio you have played works for review even on a weak connection.',
    '怎么放': 'Show me how',
    '第一次用？看操作指南': 'New here? Read the guide', '每个页面怎么用、按哪里，一步一步讲清楚。': 'How each page works and what to tap, step by step.',
    // 单词 on 今日 (no plan yet)
    '背单词': 'Learn words', '按遗忘曲线': 'Spaced repetition',
    '选一本词书，每天几个新词；例句来自你读的文章，还能听原文录音。': 'Pick a word book and learn a few new words a day. Examples come from texts you read, with their original recordings.',
    '· 新词': '· New words', '今天的单词都完成了': "Today's words are done", '明天见': 'See you tomorrow', '查看': 'View',
    // 11-progress.js: 这周进步 (the card, its sheet), the weekly mail and its unsubscribe page
    '这周进步': 'This week', '看明细': 'Details', '已达成 {n} 周': '{1} {1|week|weeks} reached',
    '记住的新词': 'Words remembered', '学完的文章': 'Texts finished', '做题正确率': 'Accuracy', '上周 {n}': 'Last week {1}',
    '/{n}天': '/{1} {1|day|days}', '达成 ✓': 'Reached ✓', '还差 {n} 天': '{1} {1|day|days} to go',
    '比上周 ↑{n}': '↑{1} vs last week', '比上周 ↓{n}': '↓{1} vs last week', '和上周持平': 'Same as last week',
    '满 {n} 题才算': 'Counts from {1} questions', '这周还没做题': 'No questions yet this week',
    '上周题太少': 'Too few last week', '上周没做题': 'None last week', '还不够算': 'not enough yet',
    '这周进步：记住 {n} 个新词，学完 {n} 篇，做题正确率 {x}，本周学了 {n} 天，目标 {n} 天。点开看明细': 'This week: {1} new {1|word|words} remembered, {2} {2|text|texts} finished, accuracy {3}, {4} of {5} days studied. Tap for details',
    '这周进步：记住 {n} 个新词，学完 {n} 篇，做题正确率 {x}，本周学了 {n} 天，目标 {n} 天，已达成 {n} 周。点开看明细': 'This week: {1} new {1|word|words} remembered, {2} {2|text|texts} finished, accuracy {3}, {4} of {5} days studied, {6} {6|week|weeks} reached. Tap for details',
    '做完今天的第一步，这里就开始记录': "Finish today's first step to start the count", '数字都来自你自己的学习记录': 'All numbers come from your own study record',
    '{n} 月 {n} 日': '{1}/{2}', '{x} – {x} · 数字都来自你自己的学习记录': '{1} – {2} · All numbers come from your own study record',
    '本周 {n} / {n} 天': 'This week {1} / {2} days', '学了': 'Studied', '没学': 'Not studied',
    // 已经有 <b>3</b> 周达成了目标。… (the number between: "weeks" even for 1)
    '已经有': "You've reached your goal in", '周达成了目标。': 'weeks so far.', '还没有达成目标的周。': 'No week has reached the goal yet.',
    '{x}一周学够 {n} 天就算达成一周；哪天、哪周没学都不会清零，只会越攒越多。': '{1} A week counts once you study {2} {2|day|days} in it. Missed days or weeks never reset anything; the count only grows.',
    '学一步材料、复习几个词、做一组练习或读一篇轻松读，都算学了这一天。': 'One step of a text, a few review words, a set of exercises or an Easy reading text: each counts as a study day.',
    '改每周目标': 'Change weekly goal',
    '新词要隔天复习时还记得才算，一个词只算一次。上周 {n} 个。': 'A new word counts when you still know it at a review on a later day, and only once. Last week: {1}.',
    '这周还没有。今天学的新词，明天复习还记得就会出现在这里。': "None yet this week. New words from today show up here if you still know them at tomorrow's review.",
    '做完一篇的理解题就算学完。上周 {n} 篇。': 'A text counts as finished once you do its check questions. Last week: {1}.',
    '另外轻松读了 {n} 篇，共 {x} 个词。': 'Plus {1} Easy reading {1|text|texts}, {2} words in all.',
    // the accuracy line is one text node: this week, then last week
    '这周做了 {n} 题，对了 {n} 题。{x}': 'This week: {2} of {1} right. {3}',
    '这周做了 {n} 题，对了 {n} 题，满 {n} 题才算正确率。{x}': 'This week: {2} of {1} right. Accuracy counts from {3} questions. {4}',
    '这周还没做题。{x}': 'No questions yet this week. {1}',
    '上周 {n} 题对 {n} 题（{n}%）。': 'Last week: {2} of {1} right ({3}%).', '上周 {n} 题对 {n} 题。': 'Last week: {2} of {1} right.',
    '上周没做题。': 'No questions last week.',
    '算的是不看提示做的理解题、语法题、辨析和考试练习；语法起点小测不算（它会一直加难，错一半是正常的）。': 'This counts check questions, grammar questions, word pairs and exam practice done without hints. The grammar placement quiz does not count: it keeps getting harder, so missing half is normal.',
    '绑定邮箱后可以收': 'Add an email to get it', '每周日晚上 {n} 点': 'Sundays, {1} p.m.', '已关闭': 'Off',
    '每周日晚上 {n} 点，把这周的进步发到你绑定的邮箱：记住的新词、学完的文章、做题正确率和每周目标。这周没学的话，会提醒你一下；连着几周没学就不再发。': "Every Sunday at {1} p.m., this week's progress goes to your email: words remembered, texts finished, accuracy and your weekly goal. If you didn't study that week, it gives you a gentle nudge; after a few weeks without study, it stops.",
    '收不收每周进度邮件': 'Get the weekly progress email?', '每周收': 'Get it weekly', '不收': "Don't send",
    '每封邮件最下面也有退订链接。': 'Every email also has an unsubscribe link at the bottom.',
    '还没有绑定邮箱。': 'No email added yet.',
    '每周日晚上会收到进度邮件': "You'll get a progress email every Sunday evening", '不再发每周进度邮件': 'Weekly progress email turned off',
    '已退订': 'Unsubscribed', '退订每周进度邮件': 'Unsubscribe from the weekly progress email',
    '以后不会再收到每周进度邮件了。想再收，可以点下面的「撤销」，或者在「我的 → 每周进度邮件」里打开。': "You won't get the weekly progress email anymore. To get it again, tap “Undo” below, or turn it on in Me → Weekly progress email.",
    '每周日晚上 {n} 点，语流会把你这周的进步发到绑定的邮箱：记住的新词、学完的文章、做题正确率和每周目标。退订后就不再发。': "Every Sunday at {1} p.m., Flow sends this week's progress to your email: words remembered, texts finished, accuracy and your weekly goal. Unsubscribe and it stops.",
    '撤销，继续收': 'Undo, keep getting it', '去学习': 'Go study', '退订': 'Unsubscribe', '不退订，去学习': 'Keep it, go study',
    '会继续收到每周进度邮件': "You'll keep getting the weekly progress email",
    // 12-daily-line.js: 今日好句 (labels and buttons; its meaning and note stay Chinese) and 今日一读
    '今日好句': 'Line of the day', '{x}今日好句': '{1} line of the day',
    '公版名句': 'Public-domain quote', '语流文章': 'Flow text', '出自《{x}》': 'From “{1}”', '读原文': 'Read the text',
    '先听一遍，再点红点读出来（最长 {n} 秒），读完和原句对比着听。': 'Play it first, then tap the red dot and read it aloud (up to {1} s). Then compare it with the original.',
    '原句': 'Original', '录音': 'Record', '对比回放': 'Compare',
    '录好了，可以对比回放': 'Recorded. You can compare now',
    '发音分 · 准确 {n} · 流利 {n} · 完整 {n}/{n}': 'pronunciation · accuracy {1} · fluency {2} · completeness {3}/{4}',
    '（AI 估计，仅供参考）': ' (AI estimate, a guide only)',
    '· 读到 {n}/{n} 个词': '· {1}/{2} words read',
    '今日一读': "Today's read", '· 约 {n} 分钟': '· About {1} min', '读这篇 →': 'Read it →',
    // 26-two-lines.js: 听两句，答一句 (the question's Chinese and the AI's note are content)
    '听两句，用一句话回答': 'Hear two lines, answer in one sentence', '听这两句': 'Play the two lines',
    '出自《{x}》 ·': 'From “{1}” ·', '看原文': 'Show the text', '收起原文': 'Hide the text',
    '问题': 'Question', '用英文写一句': 'Write one sentence in English',
    '改成打字': 'Type instead', '给我一点提示': 'Give me a hint', '交上去': 'Submit',
    '可以这样开头：': 'Try starting with:', '可以这样开头：{x}': 'Try starting with: {1}', '可以这样开头': 'Try starting with',
    '没听清，再说一次吧': "Didn't catch that. Say it again",
    '请用英文写至少 {n} 个词': 'Write at least {1} words in English',
    '说到了': 'You got it', '意思还没到': 'Not quite there yet', '你说的': 'You said',
    '看了提示': 'With a hint', '没看提示，自己说的': 'No hint, all your own',
    '再说一次': 'Say it again', '先跳过，明天再练': 'Skip for now, practice tomorrow',
    '{x} · 「{x}」已存进单词本，明天复习 ·': '{1} · Saved “{2}” to Words for review tomorrow ·',
    // 70-learner.js: the ability list, the level suggestion, the microphone (its sheet's privacy sentence stays Chinese)
    '词汇量约 {x}': 'About {1} words', '已掌握 {n} 词': '{1} {1|word|words} learned', '测一次词汇量': 'Take the vocabulary test',
    '{n} 个知识点用对或做对': '{1} grammar {1|point|points} used or answered right', '{n} 个要留意': '{1} to watch',
    '读和写的时候会点亮': 'Lights up as you read and write',
    '{n} 次练习 · 平均 {n}%': '{1} {1|session|sessions} · average {2}%', '还没练过': 'Not practiced yet',
    '不用专门测：做理解题、听写、跟读和写作时自动记下。做一次测评会更准。': 'No special test needed: this is recorded as you do check questions, dictation, shadowing and writing. A test makes it more accurate.',
    '换到 {x}': 'Switch to {1}', '先不用': 'Not now', '已换到 {x}，推荐会跟着变': 'Switched to {1}. Suggestions will change to match',
    '要用一下麦克风': 'Flow needs the microphone',
    '接下来系统会问能不能用麦克风，请选「允许」。{x}': 'Your device will now ask to use the microphone. Choose “Allow”. {1}',
    '在语流 App 里只问这一次。': 'The Flow app asks only this once.',
    '放在 iPhone 主屏上的语流，每次重新打开后第一次录音，系统都会再问一次，这是 iOS 的规定。': 'With Flow on your iPhone home screen, iOS asks again the first time you record after each reopen. This is an iOS rule.',
    '好，开始录音': 'OK, start recording',
    '打开方法见操作指南「常见问题」里的「录音、跟读用不了？」': "The guide's FAQ shows how to turn it on",
    // a missing permission: the whole message is one text (where to turn it on differs by system)
    '没有拿到麦克风权限，打开方法见操作指南「常见问题」里的「录音、跟读用不了？」': "No microphone access. The guide's FAQ shows how to turn it on",
    '没有拿到麦克风权限，到 iPhone 的「设置 → 语流 → 麦克风」打开': 'No microphone access. Turn it on in iPhone Settings → Flow → Microphone',
    '没有拿到麦克风权限，到手机的「设置 → 应用 → 语流 → 权限 → 麦克风」打开': "No microphone access. Turn it on in your phone's Settings → Apps → Flow → Permissions → Microphone",
    '没有拿到麦克风权限，到手机的「设置 → 应用和元服务 → 语流 → 麦克风」打开': "No microphone access. Turn it on in your phone's Settings → Apps & services → Flow → Microphone",
    '没有拿到麦克风权限，到 Windows 的「设置 → 隐私和安全性 → 麦克风」打开': 'No microphone access. Turn it on in Windows Settings → Privacy & security → Microphone',
    '没有拿到麦克风权限，到 Mac 的「系统设置 → 隐私与安全性 → 麦克风」打开': 'No microphone access. Turn it on in Mac System Settings → Privacy & Security → Microphone',
    '没有拿到麦克风权限，到系统设置里找到语流，把麦克风打开': 'No microphone access. Find Flow in your system settings and turn the microphone on',
    '录音没能开始': "Recording didn't start", '录音被打断了，已经说的这段先用上': 'Recording was cut off. What you said so far will be used',
    '这个浏览器不支持录音，换 Safari 或 Chrome 试试': "This browser can't record. Try Safari or Chrome",
    '录音到了长度上限，已经停下，先交这一段': 'Recording reached the time limit and stopped. This part will be sent',
    '录音太长了，请在 {n} 分钟内说完再交': 'Too long. Keep it under {1} {1|minute|minutes}',
    '这些已经放进错题本，会按遗忘曲线回来让你再改一次。': 'These are now in Mistakes and will come back, spaced over time, for another try.',
    // 70-learner.js: before the first recording (D2 2026-11-26: English is fine; the system's own microphone prompt is not ours)
    '说出来的回答要录音。麦克风只在你点录音键以后、说话的这几秒打开，说完马上关；录音只在批改时发给 AI，服务器上不留。':
      'Your spoken answer is recorded. The microphone is on only for the seconds after you tap the record button, and off as soon as you stop. The recording goes to the AI only for checking and is not kept on the server.',
    // 13-today-views.js: 今日 as a list or as cards (B1 #442)
    '列表': 'List', '卡片': 'Cards', '今日的样子': 'Today view', '已完成': 'Done', '{n} 项': '{1}',
    '学了 {n} 天，目标达成': '{1} {1|day|days}, goal met', '学了 {n} 天，目标 {n} 天': '{1} of {2} days', '还没开始，目标 {n} 天': 'Not started, goal {1} days',
    '这周学了 {n} 天，目标达成': 'This week: {1} {1|day|days}, goal met', '这周学了 {n} 天，目标 {n} 天': 'This week: {1} of {2} days',
    '这周还没开始，目标 {n} 天': 'This week: not started, goal {1} days',
    '记住 {n} 个新词': '{1} new {1|word|words} remembered', '学完 {n} 篇': '{1} {1|text|texts} finished', '正确率 {n}%': '{1}% correct',
    '这周{x}：{x}。点开看明细': 'This week: {1}. {2}. Tap for details', '这周{x}。点开看明细': 'This week: {1}. Tap for details',
    '还要约 {n} 分钟 ·': 'About {1} min to go ·',
    '今天要做的几步': "Today's steps", '学了几天、记住多少': 'Days studied, words remembered', '每天一句，能听能跟读': 'A line a day to hear and shadow',
    '你自己贴进来的那篇': 'The text you pasted in', '每天一篇短文': 'A short text every day', '错题、复听、语法': 'Mistakes, listening again, grammar',
    '{n} 步，做完 {n} 步了': '{1} steps, {2} done', '{n} 步，都做完了': '{1} steps, all done', '学了 {n} 步，共 {n} 步': '{1} of {2} steps done',
    '还没开始': 'Not started', '接着读': 'Keep reading', '开始练': 'Start', '读这篇': 'Read this',
    '还可以再练 {n} 项': '{1} more to practice', '不算进今天的计划': "Not part of today's plan",
    '上一张': 'Previous', '下一张': 'Next', '今日，{n} 张卡片，左右翻': 'Today, {1} cards: swipe left or right', '第 {n} 张，共 {n} 张，{x}': 'Card {1} of {2}: {3}',
    '调整顺序': 'Reorder', '编辑': 'Edit', '上移': 'Move up', '下移': 'Move down',
    '按住一块拖动。排在最前面的，打开今日先看到。': 'Press and drag a block. The first one is what you see first on Today.',
    // #/today/edit (调整顺序) and the card names
    '这周': 'This week', '今日的顺序': 'Order on Today', '{x}，第 {n} 个，共 {n} 个': '{1}, {2} of {3}',
  });
  /* ---------- English: the Words tab and review (50-words.js, 60-review.js); docs/english-ui.md has the terms ---------- */
  enTable({
    // 50-words.js: the word list, its pills and due lines
    '空格': 'Blank',
    '熟知': 'Known', '待学': 'To learn', '已掌握': 'Learned', '已掌握 ·': 'Learned ·', '学习中': 'Learning',
    '记得 {n}%': 'Recall {1}%', '记得 {x}': 'Recall {1}', '此刻记得的概率': 'Chance you remember it now',
    '导入': 'Import',
    '该复习了': 'Due now', '今天晚些时候复习': 'Review later today', '明天复习': 'Review tomorrow', '{n} 天后复习': 'Review in {1} {1|day|days}',
    '周一': 'Mon', '周二': 'Tue', '周三': 'Wed', '周四': 'Thu', '周五': 'Fri', '周六': 'Sat', '周日': 'Sun',
    // 50-words.js: 这次什么时候复习 (a time today or tomorrow for the next reminder only) and the app's notifications
    '今天中午 12:30': 'Today, 12:30 p.m.', '今天傍晚 18:00': 'Today, 6 p.m.', '今晚 21:00': 'Tonight, 9 p.m.',
    '明早 8:00': 'Tomorrow, 8 a.m.', '明天中午 12:30': 'Tomorrow, 12:30 p.m.', '明晚 20:00': 'Tomorrow, 8 p.m.',
    '今天 {n}:{n}': 'today at {1}:{2}', '明天 {n}:{n}': 'tomorrow at {1}:{2}',
    '这台 iPhone': 'this iPhone', '这台手机': 'this phone', '这台电脑': 'this computer', '这台 Mac': 'this Mac', '这台设备': 'this device',
    '在这台 iPhone 上': 'on this iPhone', '在这台手机上': 'on this phone', '在这台电脑上': 'on this computer', '在这台 Mac 上': 'on this Mac', '在这台设备上': 'on this device',
    'iPhone 的「设置 → 语流 → 通知」': "the iPhone's “Settings → Flow → Notifications”",
    '手机的「设置 → 应用 → 语流 → 通知」': "the phone's “Settings → Apps → Flow → Notifications”",
    'Windows 的「设置 → 系统 → 通知」': 'Windows “Settings → System → Notifications”',
    'Mac 的「系统设置 → 通知」': "the Mac's “System Settings → Notifications”",
    '系统设置里的「通知」': '“Notifications” in system settings',
    '到点用 App 通知提醒': 'Use app notifications',
    '{x}，按上面的时间弹通知，不用邮箱': 'Notifications {1} at the time above, no email needed',
    '已开启：{x}到点用 App 通知提醒': 'On: app notifications {1} at your time',
    '通知设置': 'Notification settings',
    '登录后才能设复习提醒。': 'Sign in to set review reminders.',
    '选一个时间，下一次提醒就在那时候；之后回到每天 {n}:{n}。': 'Pick a time for the next reminder; after that it goes back to {1}:{2} daily.',
    '自己选时间：': 'Pick a time:',
    '取消这次（{x}），按每天 {n}:{n}': 'Cancel this one ({1}), back to {2}:{3} daily',
    '好，{x}提醒你复习。': "OK. We'll remind you {1}.",
    '到时发邮件提醒（有词要复习才发）。': " We'll email you then (only if words are due).",
    '账号还没绑定邮箱，可以': ' No email on your account yet. You can ',
    '加到手机日历': 'Add to calendar',
    '先选一个时间': 'Pick a time first',
    '好，按每天 {n}:{n} 提醒': 'OK, back to daily reminders at {1}:{2}',
    // 50-words.js: the Words page (signed out, today's card, a finished book, stats, search)
    '选一本词书，每天学几个新词，系统按遗忘曲线安排复习；': 'Pick a word book and learn a few new words a day; reviews follow the forgetting curve.',
    '读文章时点词收藏的单词和表达，也会一起复习。': 'Words and expressions you save while reading are reviewed too.',
    '先测测词汇量': 'Take the vocabulary test',
    '《{x}》背完了': 'You finished “{1}”',
    '离考试还有一段时间，先把学过的词复习牢，考完再换下一本。': 'Your exam is still a while away: keep reviewing what you have learned, and move on to a new book after it.',
    '接下来推荐《{x}》：你学过的词会跳过，还剩约 {x} 个新词。': 'Next we suggest “{1}”: words you have learned are skipped, about {2} new words left.',
    '可以在背词计划里换一本接着背。': 'You can pick another book in Word plan.',
    '换成《{x}》': 'Switch to “{1}”', '先只复习': 'Just review for now', '先只复习到考试': 'Just review until the exam', '换一本': 'Change book',
    '《{x}》还剩 {x} 个新词，大约 {x} 天背完。{x}': '“{1}”: {2} new {2|word|words} left, about {3} {3|day|days} to go. {4}',
    '《{x}》还剩 {n} 个新词，大约 {n} 天背完。': '“{1}”: {2} new {2|word|words} left, about {3} {3|day|days} to go.',
    '单词每天 {n} 分钟': 'Word time {1} min a day', '· 单词每天 {n} 分钟': '· Word time {1} min a day', '已完成 {n} 次': '{1} done',
    '今天的单词做完了': "Today's words are done",
    '还有 {n} 个复习留到之后几天，想多背可以继续': '{1} more {1|review waits|reviews wait} for the next few days. You can keep going if you like',
    '明天预计 {n} 个复习': '{1} due tomorrow',
    '补积压：还剩 {n} 个，大约 {n} 天补完。最容易忘的排在前面，补完之前先不加新词。': 'Catching up: {1} left, about {2} {2|day|days} to go. The ones easiest to forget come first; no new words until you catch up.',
    '到期的词比较多，今天先复习，新词明天继续。': 'Many words are due, so today is for review. New words continue tomorrow.',
    '继续复习': 'Keep reviewing', '再学 10 个': 'Learn 10 more',
    '（跳过 {n} 个常用词）': ' ({1} common {1|word|words} skipped)',
    '《{x}》已学 {x} / {x}{x}': '“{1}”: {2} / {3}{4} studied', '《{x}》已学 {n} / {n}': '“{1}”: {2} / {3} studied',
    '{x}每天 {x} 个新词 · 目标记住率 {x}%': '{1}{2} new {2|word|words} a day · Target recall {3}%',
    '预计 {n}月{n}日学完': 'Done by {1}/{2}', '预计 {n}年{n}月{n}日学完': 'Done by {2}/{3}/{1}',
    '已全部学过': 'All studied', '已全部学过 ·': 'All studied ·',
    '每天 {n} 个新词': '{1} new {1|word|words} a day', '目标记住率 {n}%': 'Target recall {1}%',
    '开始背单词': 'Start learning words',
    '选一本词书，每天几个新词，按遗忘曲线复习': 'Pick a word book: a few new words a day, reviewed on the forgetting curve',
    '例句来自你读的文章，还能听原文录音。不选词书也可以：读文章时点词收藏，收藏的词同样按遗忘曲线复习。': 'Examples come from the texts you read, with their recordings. No book needed: tap words to save them while reading, and saved words are reviewed the same way.',
    '选词书': 'Choose a word book', '先测词汇量（约 3 分钟）': 'Vocabulary test (about 3 min)',
    '收藏的词：复习 {n} · 待学 {n}': 'Saved words: {1} to review · {2} to learn',
    '开始复习': 'Start review',
    '共 {n} 个 · 已掌握 {n}': '{1} total · {2} learned',
    '单词工具': 'Word tools',
    '统计和复习预测': 'Stats and forecast',
    '已掌握 {n}': '{1} learned', '学习中 {n}': '{1} learning', '· 词汇量约 {x}': '· About {1} words',
    '词汇量估计': 'Estimated vocabulary',
    '未来 7 天的复习量': 'Reviews, next 7 days', '按你的记忆情况算出': 'Based on your memory', '未来 7 天复习量': 'Reviews in the next 7 days',
    '开始学习后，这里会显示每天大约要复习多少个。': 'Once you start, this shows about how many reviews each day has.',
    '最近 5 周每天复习次数': 'Reviews per day, last 5 weeks',
    '{n}-{n}-{n}：{n} 次': '{1}-{2}-{3}: {4} {4|review|reviews}',
    '搜索单词、意思或原句': 'Search words, meanings or sentences',
    '搜索单词、意思或原句{x}': 'Search words, meanings or sentences{1}', '（按 / 跳到这里）': ' (press /)',
    '导出单词本：Excel 表格或 Anki': 'Export words: Excel or Anki',
    '词书里的词都学过了': "You've studied every word in this book",
    '已换成《{x}》': 'Switched to “{1}”',
    // 50-words.js: 错题本 (its own page under 练习) and the list's empty states
    '登录后才能看错题本。': 'Sign in to see your mistakes.',
    '没找到「{x}」。可以换个写法，或者搜中文。': 'No match for “{1}”. Try another spelling, or search in Chinese.',
    '还没有错题。理解题答错、写作和口语里被改出的错误、读不准的发音、做错的语法题和辨析题，都会自动收进来。': 'No mistakes yet. Wrong comprehension answers, errors corrected in your writing and speaking, sounds you missed, and wrong grammar and word-pair answers all land here.',
    '清除搜索': 'Clear search',
    '复习到期的 {n} 道': 'Review the {1} due', '搜索错题': 'Search mistakes',
    '← 练习': '← Practice',
    '做错的题都在这里，到期了会在「错题和句型复习」里再考你 · 共 {n} 道': 'Every question you got wrong is here; when one is due, “Mistakes and patterns” asks it again · {1} in all',
    '错题': 'Mistake', '错题 ·': 'Mistake ·',
    '没找到「{x}」{x}。可以换个写法，或者搜中文意思。': 'No match for “{1}”{2}. Try another spelling, or search for the Chinese meaning.',
    '没找到「{x}」。可以换个写法，或者搜中文意思。': 'No match for “{1}”. Try another spelling, or search for the Chinese meaning.',
    '（只在「{x}」里找了）': ' (only in “{1}”)',
    '还没有单词。选一本词书，或者读文章时点词收藏。': 'No words yet. Pick a word book, or tap words to save them while reading.',
    '还没有收藏的表达。读文章时选中一段文字，或在「地道表达」里点 ☆。': 'No saved expressions yet. Select some words while reading, or tap ☆ in “Natural expressions”.',
    '还没有错题。理解题答错、写作和口语里被改出的错误，都会自动收进来。': 'No mistakes yet. Wrong comprehension answers and errors corrected in your writing and speaking are added here.',
    '还没有单词。选一本词书，或者学一篇材料时点词收藏。': 'No words yet. Pick a word book, or tap words to save them while you study a text.',
    '改错': 'Fix', '理解题': 'Comprehension',
    '在全部里找': 'Search all',
    // 50-words.js: a word's sheet (memory curve, examples, collocations, history)
    '记忆曲线：此刻记得的概率 {x}': 'Memory curve: recall now {1}',
    '目标 {n}%': 'Target {1}%', '下次复习': 'Next review', '上次复习': 'Last review',
    '你当时写的': 'What you wrote', '你收藏时的原句': 'The sentence you saved it from',
    '原文录音': 'Recording', '· 原文录音': '· Recording',
    '播放例句（AI 朗读）': 'Play example (AI voice)', '播放读音（AI 朗读）': 'Play word (AI voice)', '播放读音': 'Play word', '播放例句': 'Play example',
    '常用搭配和近义、易混词 · AI 生成，仅供参考': 'Collocations and similar words, a guide only · AI 生成 · AI-generated',
    '常用搭配和近义、易混词（AI 生成）': 'Collocations and similar words (AI-generated)',
    '常用搭配': 'Collocations', '近义和易混词': 'Similar and confusable words', '更多 {n} 条': '{1} more',
    '有不对的？': 'Something wrong?', 'AI 服务说明': 'About the AI service',
    '哪一条不对？': 'Which one is wrong?', '哪里不对？（可以不写）': "What's wrong? (optional)",
    '比如：意思不对、不常这样说（不用写你的名字）': 'For example: wrong meaning, not usually said (no need for your name)',
    '留言会给语流的管理员看，不显示你的名字。标了以后这条不再给你看，在这个词的详情里可以放回。': "Flow's admins see your note, without your name. Once marked, you won't see it again; you can put it back in this word's details.",
    '已标为不对：「{x}」不再给你看': "Marked wrong: you won't see “{1}” again",
    '已放回': 'Put back', '放回': 'Put back', '放回 {x}': 'Put back {1}',
    '忘了': 'Forgot', '模糊': 'Not sure', '记得': 'Remembered', '很熟': 'Easy', '读文章时查过': 'Looked up while reading',
    '{n}/{n} 忘了': '{1}/{2} Forgot', '{n}/{n} 模糊': '{1}/{2} Not sure', '{n}/{n} 记得': '{1}/{2} Remembered', '{n}/{n} 很熟': '{1}/{2} Easy',
    '{n}/{n} 熟知': '{1}/{2} Known', '{n}/{n} 读文章时查过': '{1}/{2} Looked up while reading',
    '复习记录：{x}': 'Review history: {1}',
    '记忆稳定性 {x}': 'Memory lasts {1}', '不到 1 天': 'under 1 day',
    '记忆稳定性 {n} 天': 'Memory lasts {1} {1|day|days}', '记忆稳定性 不到 {n} 天': 'Memory lasts under {1} day',
    '· 记忆稳定性 {n} 天': '· Memory lasts {1} {1|day|days}', '· 记忆稳定性 不到 {n} 天': '· Memory lasts under {1} day',
    '正在找例句…': 'Finding examples…', '暂时没有例句。': 'No examples yet.',
    '你标为不对的：': 'Marked wrong: ', '你标为不对的：{x}': 'Marked wrong: {1}',
    '取消熟知，继续复习': 'Review it again', '标为熟知，不再复习': 'Mark as known',
    '删除 {x}': 'Delete {1}',
    '已恢复复习': 'Back in review', '已标为熟知': 'Marked as known',
    '删除这个词和它的复习记录？': 'Delete this word and its review history?',
    // 50-words.js: importing a word list
    '导入词表': 'Import a word list',
    '每行一个单词或短语（也可以用逗号分开），一次最多 500 个。词典里有的会自动配上释义和例句；已经在复习里的会跳过。适合导入老师给的或自己整理的词表。': 'One word or phrase per line (or separated by commas), up to 500 at a time. Words in the dictionary get their meaning and examples; words already in review are skipped. Good for a list from your teacher or one of your own.',
    '导入了 {n} 个': 'Imported {1}', '导入了 {n} 个，跳过 {n} 个已有的': 'Imported {1}, skipped {2} already there',
    '导入了 {x} 个{x}': 'Imported {1}{2}', '，跳过 {n} 个已有的': ', skipped {1} already there',
    // 50-words.js: 背词计划 (word book, new words a day, word time, target recall, reminders)
    '登录后才能制定背词计划。': 'Sign in to make a word plan.',
    '已选': 'Selected', '{n},{n} 词': '{1},{2} words', '词频第 {x} 位': 'Frequency rank {1}', '这份词书怎么来的': 'How this book was made',
    '随时可以改，已学的进度不会丢。': 'Change it any time; you keep your progress.',
    '你在准备什么考试？点一下就选好对应的词书。': 'Preparing for an exam? Tap it to pick its word book.',
    '不考试': 'No exam',
    '换一本（共 {n} 本）': 'Change book ({1} in all)',
    '按词频的词书从你的水平往上走；其他词书按考试或用途分组，点一本就选中。': 'Frequency books go up from your level; the others are grouped by exam or use. Tap one to choose it.',
    '自己的词表': 'Your own list', '导入老师给的词表': "Import your teacher's list",
    '把手上的词表粘贴进来，和词书一起按遗忘曲线复习。': 'Paste in a list you have; it is reviewed on the forgetting curve along with your book.',
    '导入词表 →': 'Import a word list →',
    '每天新词': 'New words a day', '{n} 个': '{1}', '自己定：': 'Your own:', '个 / 天': 'a day',
    '改成每天 10 个': 'Make it 10 a day',
    '学完当天的，复习页还可以「再学 10 个」，不用改计划。': 'Done for the day? The review page offers “Learn 10 more”, no plan change needed.',
    '单词每天': 'Word time a day', '跟着每天计划（{n} 分钟）': 'Daily plan ({1} min)', '不限时间': 'No limit',
    '做到这个时间，今天的单词就算完成；剩下的复习按遗忘风险留到之后几天，想多背随时可以继续。': "Reach this time and today's words count as done; the rest wait for the next few days, by how likely you are to forget them. You can always keep going.",
    '目标记住率': 'Target recall',
    '系统会在你记住的概率降到这个数时安排复习。越高记得越牢，但每天复习更多；90% 是比较均衡的选择。': 'A word comes up for review when the chance you remember it drops to this. Higher holds words better but means more reviews a day; 90% is a good balance.',
    '跳过测试显示你已经认识的常用词{x}，按词频的词书不受影响': 'Skip common words the test showed you know{1}; frequency books are not affected',
    '跳过测试显示你已经认识的常用词，按词频的词书不受影响': 'Skip common words the test showed you know; frequency books are not affected',
    '（词频前 {n} 位）': ' (top {1})',
    '开始背': 'Start learning',
    '复习提醒': 'Review reminders',
    '遗忘曲线最怕"到期没人提醒"。选一个每天方便的时间：': 'What hurts memory most is a due review nobody reminds you of. Pick a time that suits you each day:',
    '提醒时间': 'Reminder time', '每天 {n}:{n}': 'Daily at {1}:{2}',
    '到点发邮件提醒（只在有词要复习时发）': 'Email me at that time (only when words are due)',
    '到点发邮件提醒（只在有词要复习时发）{x}': 'Email me at that time (only when words are due){1}',
    '账号还没绑定邮箱：可以在': 'No email on your account yet. Add one in ', '「我的」': '“Me”',
    '里绑定，或者先用下面的日历提醒。': ', or use the calendar reminder below for now.',
    '日历每天到点提醒，不依赖任何 App': 'Your calendar reminds you each day, no app needed',
    '下一次：{x}（只管这一次）': 'Next: {1} (just this once)',
    '哪天这个点没空，可以只改下一次的时间。': 'Busy at that time one day? Change just the next one.',
    '这次什么时候复习': 'Change next time',
    '已选《{x}》，{x} 词': 'Chosen: “{1}”, {2} words', '已选《{x}》，{x}': 'Chosen: “{1}”, {2}',
    '还没选词书': 'No word book chosen yet',
    '点上面的考试，或点「换一本」挑一本。': 'Tap an exam above, or “Change book” to pick one.',
    '先在上面选一本词书。': 'Pick a word book above first.',
    '学完《{x}》大约需要 {x} 天{x}；每天 {x} 个新词，一个月后每天大约要复习 {x} 个{x}': "About {2} {2|day|days} to finish “{1}”{3}. With {4} new {4|word|words} a day, a month from now you'll review about {5} a day{6}",
    '学完《{x}》大约需要 {n} 天；每天 {n} 个新词，一个月后每天大约要复习 {n} 个{x}': "About {2} {2|day|days} to finish “{1}”. With {3} new {3|word|words} a day, a month from now you'll review about {4} a day{5}",
    '，连新词约 {n} 分钟。': ', about {1} min with new words.',
    '。按现在的设置，一个月后每天大约要 {n} 分钟。': '. At this pace, that is about {1} min a day in a month.',
    '。按现在的设置，一个月后每天大约要 {x} 分钟{x}。': '. At this pace, that is about {1} min a day in a month{2}.',
    '。时间紧的话，可以改成每天 10 个新词': '. Short on time? Try 10 new words a day',
    '不限时间：每天到期的复习和新词都排进今天。': 'No limit: every due review and new word goes into today.',
    '按单词每天 {n} 分钟，每天大约能学 {n} 个新词。': 'With {1} min of word time a day, you can learn about {2} new {2|word|words} a day.',
    '按单词每天 {x} 分钟，每天大约能学 {x} 个新词{x}。': 'With {1} min of word time a day, you can learn about {2} new {2|word|words} a day{3}.',
    '。每天 {n} 个新词，一个月后单词每天约 {n} 分钟，比 {n} 分钟多：可以把单词时间改长，或者新词改成 {n} 个': '. {1} new words a day would take about {2} min a day in a month, more than {3} min: give words more time, or make it {4} new words',
    '新词改成每天 {n} 个': 'Make it {1} new {1|word|words} a day',
    '每天 {n}:{n} 会提醒你': "We'll remind you daily at {1}:{2}", '提醒时间已更新': 'Reminder time updated',
    '通知没有打开：可以到{x}里打开': 'Notifications are off. Turn them on in {1}',
    '好，每天 {n}:{n} 用 App 通知提醒你（有词要复习的日子）': 'OK. The app will remind you at {1}:{2} on days with words due',
    'App 通知提醒关了；邮件和日历提醒照旧': 'App notifications off; email and calendar reminders stay on',
    '没有关掉，再试一次': "Couldn't turn it off. Try again",
    '可以到{x}里改': 'You can change this in {1}',
    '计划已保存': 'Plan saved',
    // 50-words.js: 测词汇量
    '认识': 'Know it', '不认识': "Don't know",
    '认识这个词吗？看到能想起大概意思就算认识。': 'Do you know this word? If you can recall roughly what it means, you do.',
    '有几个是编出来的假词，用来校正估计。': 'A few are made-up words, to correct the estimate.',
    '正在估算…': 'Estimating…',
    '你选了不少假词，估计可能偏高，已经按比例扣除。': 'You picked quite a few made-up words, so the estimate may be high; it has been scaled down.',
    '按词频分段抽样估算，误差约几百词。': 'Estimated from samples at each frequency level; it may be off by a few hundred words.',
    '常用的 2 万词你几乎都认识，超出了这个测试能测的范围。建议用《{x}》这类考试词表{x}，也可以导入自己的词表。': 'You know nearly all of the 20,000 common words, more than this test can measure. Try an exam list such as “{1}”{2}, or import your own list.',
    '常用的 2 万词你几乎都认识，超出了这个测试能测的范围。建议用《{x}》这类考试词表，也可以导入自己的词表。': 'You know nearly all of the 20,000 common words, more than this test can measure. Try an exam list such as “{1}”, or import your own list.',
    '，或在「背词计划」里选英语专业的词书': ', or an English-major book in “Word plan”',
    '建议从《{x}》开始。': 'We suggest starting with “{1}”.',
    '结果已经记下，登录后会存到你的账号。': 'Your result is kept and goes to your account when you sign in.',
    '用《{x}》开始': 'Start with “{1}”', '重新测': 'Test again', '返回单词': 'Back to Words',
    '登录后可以按测试结果制定背词计划。': 'Sign in to make a word plan from your result.',
    // 60-review.js: the review page (top bar, progress, outcomes)
    '登录后才能复习。': 'Sign in to review.',
    '复习错题和句型': 'Review mistakes and patterns', '复习单词': 'Review words',
    '现在没有网络：先用缓存的复习，联网后自动同步': "You're offline: using saved reviews. They sync when you're back online",
    '过关！这张错题卡完成了，不会再出现': 'Passed. This mistake card is done and will not come back',
    '这题先放下：回原文把那一段再读一遍更有用': 'Leave this one for now: rereading that part of the text will help more',
    '后天带着原文再做一次': "You'll try it again in two days, with the text",
    '今天先到这儿，明天再见它': "That's it for today; you'll see it again tomorrow",
    '答对了，下次再换一道题确认一次': 'Right. Next time a different question checks it once more',
    '再巩固一次': 'Once more',
    '先做 {n} 个（还有 {n} 个）': 'First {1} ({2} more later)', '先做 {n} 个（还有 {n} 个） ·': 'First {1} ({2} more later) ·',
    '再听一次': 'Play again',
    '↶ 撤销': '↶ Undo',
    '撤销：回到这一张的正面': 'Undo: back to the front of this card',
    '撤销上一张：{x}': 'Undo last card: {1}',
    '撤销（还没有可撤销的）': 'Undo (nothing to undo yet)',
    '太简单': 'Too easy',
    '现在没有要复习的错题和句型。': 'No mistakes or patterns to review right now.',
    '现在没有要复习的单词。': 'No words to review right now.',
    '小技巧：右滑「认识」，左滑「不认识」': 'Tip: swipe right for “Know it”, left for “Forgot”',
    '小技巧：左滑「认识」，右滑「不认识」': 'Tip: swipe left for “Know it”, right for “Forgot”',
    // 60-review.js: mistakes coming back (a question again, a phrase to fix, a sound to say)
    '同一组易混词，换一道题：': 'Same word pair, a new question:', '同一组易混词，换一道题：{x}': 'Same word pair, a new question: {1}',
    '同一个语法点，换一道题': 'Same grammar point, a new question', '同一个语法点，换一道题：{x}': 'Same grammar point, a new question: {1}',
    '原文片段': 'From the text', '原文片段{x}': 'From the text{1}',
    '上次这样写：': 'Last time you wrote:',
    '想不起来': "Can't recall",
    '划线部分应该怎么写？': 'How should the underlined part read?',
    '读一遍': 'Say it',
    '点录音键读一遍，AI 听你读得准不准': 'Tap the record button and say it. The AI checks how you sound',
    '读准了': 'Said it right', '还不稳': 'Not quite', '不会读': "Can't say it",
    '✓ 换了一道题也答对了': '✓ Right on a new question too', '这题没答对': 'Not right this time',
    '回到「{x}」看一遍讲解 →': 'See the explanation in “{1}” →',
    '✓ 这次答对了，这道题过关': '✓ Right this time. This one is passed', '还是没答对': 'Still not right',
    '原文依据：': 'In the text: ', '回原文把这一段再读一遍 →': 'Reread this part of the text →',
    '✓ 改对了': '✓ Fixed', '✓ 改对了：': '✓ Fixed: ', '应该是': 'It should be', '应该是：': 'It should be: ',
    '你写的：': 'You wrote: ', '参考改法：': 'Suggested fix: ', '我写的也对': 'Mine is right too', '没写对，记下了': 'Wrong, noted',
    '✓ 这次读准了': '✓ Said right this time', 'AI 听成了「{x}」': 'The AI heard “{1}”',
    'AI 的判断只作参考，不会进错题本': "The AI's call is a guide only; it won't go into Mistakes",
    // 60-review.js: a word card, front and back
    '听发音，拼出这个词': 'Listen and spell the word', '拼写': 'Spelling', '输入单词': 'Type the word',
    '回忆这个句型': 'Recall this pattern', '回忆这个表达': 'Recall this expression',
    '想起来了': 'Know it', '有点模糊': 'Not sure',
    '首字母 {x} · {x} 个字母': 'Starts with “{1}” · {2} {2|letter|letters}',
    '「认识」换到右边了，想换回去：我的 → 使用习惯': '“Know it” is on the right now. To switch back: Me → Preferences',
    '右滑': 'swipe right', '左滑': 'swipe left', '右': 'right', '左': 'left',
    '点左、中、右也能作答，和下面的按钮一样；也可以{x}「认识」，{x}「不认识」。点单词只是播放。点一下收起': 'Tapping left, middle or right answers like the buttons below. You can also {1} for “Know it” and {2} for “Forgot”. Tapping the word only plays it. Tap to close',
    '翻面也是这三块：{x}或点{x}边是没错，另一边是记错了，中间是模糊。翻面前选的那个加了框，回车或空格就是它。点一下收起': 'The back has the same three parts: {1} or tap the {2} side for “Right”, the other side for “Wrong”, the middle for “Not sure”. The one you chose before turning has a frame; Enter or Space picks it. Tap to close',
    '再看 {n} 句 ⌄': 'See {1} more ⌄',
    '易混：': 'Often confused: ', '易混：{x}': 'Often confused: {1}', '怎么区分 ›': 'Tell them apart ›',
    '简': 'Brief', '详': 'Full', '复习卡': 'Review card',
    '最常用': 'Most common', '常用': 'Common', '较常用': 'Fairly common',
    '第 {n} 次见': 'Time {1}', '上次 今天': 'Last seen today', '上次 昨天': 'Last seen yesterday', '上次 {n} 天前': 'Last seen {1} {1|day|days} ago',
    '第一次见': 'First time',
    '记得的把握：高': 'Memory: strong', '记得的把握：中': 'Memory: medium', '记得的把握：低': 'Memory: weak', '记得的把握：—': 'Memory: —',
    '复习过 {n} 次': 'Reviewed {1} {1|time|times}', '复习过 {n} 次，忘过 {n} 次': 'Reviewed {1} {1|time|times}, forgot {2} {2|time|times}',
    '，忘过 {n} 次': ', forgot {1} {1|time|times}',
    '其实认识': 'Knew it', '没错': 'Right', '记错了': 'Wrong',
    '翻面前选的就是这一个，回车或空格就是它': 'This is what you chose before turning; Enter or Space picks it',
    '✓ 拼对了': '✓ Spelled right', '差一点：你写的是': 'Almost. You wrote', '你写的是': 'You wrote',
    '已撤销，再答一次这一张': 'Undone. Answer this card again',
    '已标为太简单，「{x}」不再复习': 'Marked too easy: no more review for “{1}”',
    // 60-review.js: the end of a round
    '这一轮复习了 {n} 个': '{1} reviewed this round',
    '用时约 {n} 分钟': 'About {1} min', '记住了 {n}%': '{1}% remembered', '· 记住了 {n}%': '· {1}% remembered', '· 熟知': '· Known',
    '共作答 {n} 次，其中 {n} 次是再巩固': '{1} answers, {2} of them repeats',
    '记得 {n} · 模糊 {n} · 忘了 {n}。': 'Remembered {1} · Not sure {2} · Forgot {3}.',
    '记得 {n} · 模糊 {n} · 忘了 {n} · 熟知 {n}。': 'Remembered {1} · Not sure {2} · Forgot {3} · Known {4}.',
    '记得 {x} · 模糊 {x} · 忘了 {x}{x}。': 'Remembered {1} · Not sure {2} · Forgot {3}{4}.',
    '记得的都往后推了。忘了的 {n} 个明天再来：忘了再想起来，正是记牢的过程。': 'The ones you remembered move further out. {1} forgotten {1|comes|come} back tomorrow: forgetting and recalling again is how memory gets strong.',
    '记得的都往后推了，最远的要 {n} 天后才再见。忘了的 {n} 个明天再来：忘了再想起来，正是记牢的过程。': 'The ones you remembered move further out, the furthest {1} {1|day|days} away. {2} forgotten {2|comes|come} back tomorrow: forgetting and recalling again is how memory gets strong.',
    '记得的都往后推了。这一轮全都记得，很稳。': 'The ones you remembered move further out. You remembered them all this round. Solid.',
    '记得的都往后推了，最远的要 {n} 天后才再见。这一轮全都记得，很稳。': 'The ones you remembered move further out, the furthest {1} {1|day|days} away. You remembered them all this round. Solid.',
    '忘了的 {n} 个明天再来：忘了再想起来，正是记牢的过程。': '{1} forgotten {1|comes|come} back tomorrow: forgetting and recalling again is how memory gets strong.',
    '记得的都往后推了{x}。': 'The ones you remembered move further out{1}.', '，最远的要 {n} 天后才再见': ', the furthest {1} {1|day|days} away',
    '这一轮全都记得，很稳。': 'You remembered them all this round. Solid.',
    '今天的单词做完了。': "Today's words are done.",
    '还有 {n} 个复习留到之后几天，最容易忘的排在前面。想多背可以继续。': ' {1} more {1|review waits|reviews wait} for the next few days, the easiest to forget first. You can keep going if you like.',
    '今天做到这里也行。': 'You can stop here for today.',
    '最要紧的 {n} 个已经复习过了，还有 {n} 个，之后几天接着来，最容易忘的排在前面。': ' The {1} most urgent are done. {2} more come over the next few days, the easiest to forget first.',
    '还有 {n} 个可以继续。': '{1} more to go if you like.',
    '再做 {n} 个': 'Do {1} more', '今天就到这里': 'Done for today',
    '还想多背：再学 10 个新词': 'Want more? Learn 10 new words',
    '· 明天大约复习 {n} 个': '· About {1} due tomorrow',
    // 50-words.js after the 单词 page's new look (#454)
    '今天要背': 'To learn today', '《{x}》': '“{1}”', '换词书或改计划 ›': 'Change word book or plan ›',
    '在学 {n} · 已掌握 {n}': '{1} learning · {2} learned', '导出单词本：Excel 表格或 Anki ›': 'Export your words: Excel or Anki ›',
    '搜单词、意思': 'Search words or meanings', '今天已完成 {n} 次': 'Done {1} {1|time|times} today',
    '还有 {n} 个复习留到之后几天，想多背可以继续{x}': '{1} more {1|review waits|reviews wait} for the next few days. Keep going if you like{2}',
    '先测词汇量（约 {n} 分钟）›': 'Take the vocab test first (about {1} min) ›', '开始复习 ›': 'Start review ›', '‹ 练习': '‹ Practice',
    '共 {n} 道 · 做错的题都在这里': '{1} total · every question you got wrong', '到期了会在「错题和句型复习」里再考你': 'They come back in “Review mistakes and patterns” when due',
    '到期要复习的': 'Due for review',
  });
  /* ---------- sheet ---------- */
  let sheetReturn = null;
  // Screen readers read the page in Chinese (lang="zh-CN"); English on it (a text, a question, a word, an example)
  // gets lang="en" as it appears, so it is read with an English voice. An element is marked when all of its text is
  // English; one that mixes both is left as it is (VoiceOver and TalkBack still switch for the Latin letters).
  // In English mode (00-i18n.js) the other way round: the page is lang="en" and Chinese on it (a meaning, a translation)
  // gets lang="zh-CN" (and data-lz, taken off again if the text is put into English later).
  const HAN = /[\u3400-\u9fff\uf900-\ufaff]/, LATIN2 = /[A-Za-z]{2}/;  // Chinese characters (not the full-width punctuation)
  function markEnglish(root) {
    const en = uiLang() === 'en', want = en ? HAN : LATIN2, other = en ? LATIN2 : HAN;
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), seen = new Set(); let n;
    while ((n = w.nextNode())) {
      const el = n.parentElement;
      if (!el || seen.has(el) || !want.test(n.nodeValue)) continue;
      seen.add(el);
      const own = el.closest('[lang]');
      if (own && own !== document.documentElement) continue;  // it says its language already
      if (!other.test(el.textContent) && !/^(SCRIPT|STYLE|TEXTAREA|OPTION)$/.test(el.tagName)) {
        if (en) { el.lang = 'zh-CN'; el.setAttribute('data-lz', ''); } else el.lang = 'en';
      }
    }
  }
  const EN_NEW = new Set(); let enFrame = 0;
  new MutationObserver(ms => {
    for (const m of ms) for (const x of m.addedNodes) { const e = x.nodeType === 1 ? x : x.parentElement; if (e) EN_NEW.add(e); }
    if (EN_NEW.size && !enFrame) enFrame = requestAnimationFrame(() => { enFrame = 0; EN_NEW.forEach(e => { if (e.isConnected) markEnglish(e); }); EN_NEW.clear(); });
  }).observe(document.body, { childList: true, subtree: true });
  function openSheet(html, onMount) {
    if (sheetEl.hidden) sheetReturn = document.activeElement;
    sheetCard.innerHTML = '<div class="grab" aria-hidden="true"></div>' + html; sheetEl.hidden = false; document.body.classList.add('sheet-open');
    // A finger does not need a focused field (it would pop the keyboard up over the sheet); a keyboard user does.
    const f = sheetCard.querySelector(TOUCH ? '[autofocus]' : '[autofocus],input,button:not([data-close])');
    setTimeout(() => (f || sheetCard).focus({ preventScroll: true }), 30);
    if (onMount) onMount(sheetCard);
  }
  // Closing slides the sheet down and fades it (0.16 s; B9's design audit, 2026-11-25), from wherever a finger let it
  // go. The sheet itself is closed at once (everything that asks whether one is open, focus, a sheet opened right after);
  // what moves is a copy of it, without ids, that nothing can reach and a screen reader does not see.
  function sheetGhost() {
    if (REDUCED || sheetEl.hidden || !sheetCard.firstChild) return;
    const g = sheetEl.cloneNode(true), c = g.querySelector('.sheet-card');
    g.removeAttribute('id'); g.querySelectorAll('[id]').forEach(x => x.removeAttribute('id'));
    g.classList.add('sheet-ghost'); g.setAttribute('aria-hidden', 'true'); g.inert = true;
    document.body.appendChild(g); if (c) c.scrollTop = sheetCard.scrollTop;
    setTimeout(() => g.remove(), 200);
  }
  function closeSheet() {
    sheetGhost();
    sheetEl.hidden = true; sheetCard.innerHTML = ''; sheetCard.style.transform = ''; document.body.classList.remove('sheet-open');
    if (sheetReturn && document.contains(sheetReturn) && sheetReturn.focus) sheetReturn.focus({ preventScroll: true });
    sheetReturn = null;
  }
  const sheetLocked = () => !!sheetCard.querySelector('[data-lock]');  // a sheet that waits for an answer (askAgeOnce)
  sheetEl.addEventListener('click', e => { const c = e.target.closest('[data-close]'); if (c && (!sheetLocked() || sheetCard.contains(c))) closeSheet(); });
  document.addEventListener('keydown', e => {
    if (sheetEl.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); if (!sheetLocked()) closeSheet(); return; }
    if (e.key !== 'Tab') return;
    const f = [...sheetCard.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),textarea:not([disabled]),select,[tabindex="0"]')].filter(x => x.offsetParent !== null);
    if (!f.length) return;
    if (!sheetCard.contains(document.activeElement)) { e.preventDefault(); f[0].focus(); return; }  // focus had slipped out
    if (e.shiftKey && (document.activeElement === f[0] || document.activeElement === sheetCard)) { e.preventDefault(); f[f.length - 1].focus(); }
    else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
  });
  // While a sheet is open, focus cannot wander into the page behind it (e.g. Tab pressed while it was still loading).
  document.addEventListener('focusin', e => { if (!sheetEl.hidden && !sheetEl.contains(e.target)) sheetCard.focus({ preventScroll: true }); });
  (function sheetSwipe() {  // drag the sheet down to close it, like any phone sheet
    let y0 = null, dy = 0;
    sheetCard.addEventListener('touchstart', e => { y0 = sheetCard.scrollTop <= 0 && e.touches.length === 1 ? e.touches[0].clientY : null; dy = 0; }, { passive: true });
    sheetCard.addEventListener('touchmove', e => { if (y0 == null) return; dy = e.touches[0].clientY - y0; if (dy > 0) sheetCard.style.transform = `translateY(${dy}px)`; }, { passive: true });
    sheetCard.addEventListener('touchend', () => { if (y0 == null) return; y0 = null; if (dy > 90 && !sheetLocked()) closeSheet(); else sheetCard.style.transform = ''; });
  })();
  // On phones the bottom tabs step aside while typing, so the keyboard never covers the field and its button.
  document.addEventListener('focusin', e => { if (TOUCH && isTyping(e)) document.body.classList.add('typing'); });
  document.addEventListener('focusout', () => setTimeout(() => { if (!isTyping({ target: document.activeElement })) document.body.classList.remove('typing'); }, 80));
  // ⌘/Ctrl + Enter sends any writing box that says where its button is (data-submit).
  document.addEventListener('keydown', e => {
    if (e.key !== 'Enter' || !(e.metaKey || e.ctrlKey) || !e.target.dataset || !e.target.dataset.submit) return;
    const b = document.querySelector(e.target.dataset.submit); if (b && !b.disabled) { e.preventDefault(); b.click(); }
  });
  // Site-wide keys: ? lists the shortcuts, / jumps to the search box.
  document.addEventListener('keydown', e => {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey || isTyping(e) || !sheetEl.hidden) return;
    if (e.key === '?') { e.preventDefault(); shortcutHelp(); }
    else if (e.key === '/') { const q = view.querySelector('input[type=search]'); if (q) { e.preventDefault(); q.focus(); } }
  });
  function shortcutHelp() {
    const rows = [['通用', [['?', '显示这张快捷键表'], ['/', '跳到搜索框'], ['Esc', '关闭弹窗'], ['⌘/Ctrl + ↵', '提交写作、复述、翻译']]],
      ['听', [['空格 / K', '播放、暂停或继续全文']]], ['读', [['Tab 进入正文，← →', '逐词移动'], ['↵', '查当前的词'], ['E', 'AI 讲解当前这句']]],
      ['复习', [['← ↓ →', '正面：不认识 / 模糊 / 认识（「认识」放在左边时左右反过来）'], ['← ↓ →', '翻面：记错了 / 模糊 / 没错'], ['1 / 2 / 3', '从左到右的按钮'], ['↵ 或 空格', '翻面：加了框的那个（正面选的那一个）'], ['E', '太简单，以后不用再背'], ['X', '其实记错了'],
        ['← →', '测词汇量：默认不认识 / 认识（「认识」放在左边时反过来）']]]];  // 「认识」放在 (50-words.js KNOW): by place on screen
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">键盘快捷键</h2>${rows.map(([t, ks]) => `<div class="stack-s"><div class="kicker">${t}</div><dl class="keys">${ks.map(([k, d]) => `<dt><kbd>${esc(k)}</kbd></dt><dd>${esc(d)}</dd>`).join('')}</dl></div>`).join('')}
      ${TOUCH ? '<p class="muted small">触屏：复习时左滑「不认识」、右滑「认识」；弹窗向下拖可以关闭。</p>' : ''}<button class="btn ghost" data-close>关闭</button></div>`);
  }

  /* ---------- session ---------- */
  // The home data carries the session too (who is signed in, the CSRF token): one request, not two in a row,
  // which on a line from mainland China to the server is about a second saved. Signed in, the server ignores the
  // guest's level and themes in the query, so asking before S.user is known gives the same answer.
  // The home data: who is signed in, today's plan and counts. Kept on the phone for the next visit (05-data.js).
  // Says whether anything changed since the copy the page was drawn from.
  async function refreshHome() {
    const before = S.home ? JSON.stringify(S.home) : '';
    S.home = await api('/api/next/home' + guestQuery(true));
    if (S.home.session) { S.user = S.home.session.user; S.csrf = S.user ? S.user.csrf : ''; setTimeout(askAgeOnce, 400); }
    roleTabs();
    S.homeFromSnap = false; DATA.ok();
    const changed = before !== JSON.stringify(S.home);
    if (changed) snapHome();
    if (S.home.profile && S.home.profile.voice) { S.voice = S.home.profile.voice; save('flow-next-voice', S.voice); }
    if (S.user && S.home.profile) accentFromAccount(S.home.profile);  // 主题色 kept with the account (07-accent.js)
    if (S.user && S.home.profile) langFromAccount(S.home.profile);  // and 界面语言 (07-lang.js)
    if (S.user && S.home.profile) prefsFromAccount(S.home.profile);  // and the rest of 使用习惯 (07-prefs.js)
    setDueBadge();
    return changed;
  }
  // 底栏 「练习」「单词」: a small ink dot when something waits, never a number (the user, 2026-11-26: 少数字，角标给人压力;
  // B9); a screen reader still hears how many, in the tab's own name: 「单词，有 10 项」
  function tabCount(id, n, name, what) {
    const b = document.getElementById(id); if (!b) return;
    b.hidden = !n; b.textContent = '';
    const a = b.closest('a'); if (a) { if (n) a.setAttribute('aria-label', `${name}，有 ${n} 项${what || ''}`); else a.removeAttribute('aria-label'); }
  }
  function setDueBadge() {
    const st = S.home && S.home.stats, due = st ? st.due + st.new : 0, other = st ? st.other_due || 0 : 0;
    tabCount('dueBadge', due, '单词');
    tabCount('otherBadge', other, '练习');  // the mistakes, patterns and sentences due again (练习 → 复习, 49-practice.js)
    tabCount('radarBadge', st ? st.radar_due || 0 : 0, '能力', '该测了');  // 底栏「能力」: skills due to be measured (48-radar.js)
  }
  // The page drawn again with fresher data, without the loading skeleton or the entrance animation, and only when it
  // would not take anything from the learner (a sheet open, typing in a field, another page by now, a whole text being
  // read or paused, a sound or a recording going: a redraw stops them — 语流 07's iPhone run, 2026-11-25: 播放全文 tapped
  // right after opening an article, the fresher 今日 came in and the reading was gone, as if read to its end).
  function redrawQuietly(drawnFor) {
    if (location.hash !== drawnFor || !sheetEl.hidden || (document.activeElement && /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName))) return;
    if (LONG.r || audioBusy()) return;
    S.homeFresh = true; route(true, true);
  }
  // Back in front after a while (the phone unlocked the next morning, a tab left open): the page still said what was
  // true when it was drawn, yesterday's 已完成 3 / 3, a tab's dot for words reviewed since on another device (B9's
  // audit, 2026-11-26: 提醒和真实状态对不上). The home data is asked for again: the tabs' dots follow at once, and 今日 and
  // 练习, which are made of it, are drawn again quietly if anything changed. A short look away asks nothing.
  const AWAY = { at: 0, long: 5 * 60000 };
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') { AWAY.at = Date.now(); return; }
    if (!AWAY.at || Date.now() - AWAY.at < AWAY.long || !S.home) return;
    AWAY.at = 0;
    const drawnFor = location.hash, name = parts()[0];
    refreshHome().then(changed => { if (changed && (name === '' || name === 'practice')) redrawQuietly(drawnFor); }).catch(() => { /* offline: the page stays */ });
  });
  function needLogin(reason) { openLogin(reason); return false; }
  /* ---------- sign in, sign up, a forgotten password ---------- */
  // With mail configured (production), sign-up, code login and a forgotten password use an emailed 6-digit code;
  // without it only username + password is offered, as the server then accepts.
  async function mailOn() {
    if (S.home && S.home.session && 'mail' in S.home.session) return !!S.home.session.mail;  // carried by the home data
    if (S.mail == null) { try { const h = await api('/api/health'); S.mail = !!h.mail; S.inviteOnly = !!h.invite; } catch (e) { return true; } }
    return S.mail;
  }
  // 内测版 (FLOW_SIGNUP_INVITE_ONLY, beta_invites.py): a new 学生账号 needs an invite code; 语流's sign-up asks for none
  async function inviteOn() {
    if (S.home && S.home.session && 'invite' in S.home.session) return !!S.home.session.invite;
    if (S.inviteOnly == null) await mailOn();
    return !!S.inviteOnly;
  }
  // An account without an email cannot reset a forgotten password by itself: say so on 今日 until it binds one
  // (or the learner says 以后再说, which waits 14 days).
  function mailNudgeHTML() {
    const u = S.user, mail = S.home && S.home.session && S.home.session.mail;
    if (!u || u.email_bound !== false || !mail || Date.now() - (load('flow-next-mail-nudge') || 0) < 14 * 864e5) return '';
    // one line, put away with ✕ (以后再说: 14 days), not a card with two buttons (学优秀 UI 第一批, the user's pick 2026-11-25)
    return `<div class="mail-nudge mail-line" id="mailNudge" role="note"><span>绑定邮箱，忘记密码时可以自己找回</span>
      <button class="link small" id="mnBind" type="button" data-tap="notice-mail">去绑定</button><button class="mn-x" id="mnLater" type="button" aria-label="以后再说，14 天后再提醒">✕</button></div>`;
  }
  // A few entry points are counted, how many taps a day and nothing about who, so the operator console can compare
  // the weeks before and after a release (flow_admin.TAP_LABEL lists them). Best effort: a lost count does not matter.
  document.addEventListener('click', e => {
    const t = e.target.closest && e.target.closest('[data-tap]'); if (!t) return;
    const fold = t.tagName === 'SUMMARY' && t.parentElement; if (fold && fold.open) return;
    try { navigator.sendBeacon('/api/next/tap', JSON.stringify({ k: t.dataset.tap })); } catch (x) { /* not counted */ }
  }, true);
  // In WeChat's built-in browser: a slim bar, under the top bar, on opening the page in the phone's browser, where every
  // sound plays and the app can be put on the home screen. Closed, it stays away for a week.
  function wechatBar() {
    if (!WECHAT) return;
    const ios = /iPhone|iPad|iPod/i.test(navigator.userAgent), menu = ios ? '在默认浏览器中打开' : '在浏览器打开';
    // The first visit in WeChat: an arrow to the ··· menu, the two steps, and a way to copy the address instead.
    if (!load('flow-wx-guide')) {
      save('flow-wx-guide', Date.now());
      const g = document.createElement('div'); g.className = 'wx-guide'; g.setAttribute('role', 'dialog'); g.setAttribute('aria-label', '在浏览器里打开');
      g.innerHTML = `<svg class="wx-arrow" viewBox="0 0 120 120" aria-hidden="true"><path d="M20 110 C 40 60, 70 40, 104 16" /><path d="M86 14 L106 14 L102 34" /></svg>
        <div class="wx-steps"><b>在浏览器里打开，用起来更顺</b>
          <ol><li>点右上角的「···」</li><li>选「${menu}」</li></ol>
          <span class="small">在浏览器里可以听全部录音、用浏览器朗读，还能把语流放到手机桌面。</span>
          <div class="row"><button class="btn" type="button" id="wxCopy">复制网址</button><button class="btn primary" type="button" id="wxStay">先在微信里看看</button></div></div>`;
      document.body.appendChild(g);
      g.querySelector('#wxStay').onclick = () => g.remove();
      g.querySelector('#wxCopy').onclick = async () => {
        const url = location.origin + '/';
        try { await navigator.clipboard.writeText(url); toast('网址已复制，到浏览器里粘贴打开'); } catch (e) { toast('长按复制：' + url); }
      };
    }
    if (Date.now() - (load('flow-wx-bar') || 0) < 7 * 864e5) return;
    const el = document.createElement('div'); el.className = 'wx-bar'; el.setAttribute('role', 'note');
    el.innerHTML = `<span>微信里部分声音和安装功能用不了。点右上角「···」，选「${menu}」，可以听全部音频，还能把语流装到桌面。</span>
      <button type="button" class="wx-x" aria-label="关闭提示">×</button>`;
    el.querySelector('.wx-x').onclick = () => { save('flow-wx-bar', Date.now()); el.remove(); };
    document.getElementById('bar').after(el);
  }
  function bindMailNudge(after) {
    const b = document.getElementById('mnBind'), l = document.getElementById('mnLater');
    if (b) b.onclick = () => bindEmailSheet('');
    if (l) l.onclick = () => { save('flow-next-mail-nudge', Date.now()); if (after) after(); else { const n = document.getElementById('mailNudge'); if (n) n.remove(); } };
  }
  const USERNAME_OK = /^[^\s@<>"'\\/]{2,40}$/;
  function pwField(label, name, auto, hint) {
    return `<label class="field">${label}<span class="pw-wrap"><input name="${name}" type="password" autocomplete="${auto}" ${auto === 'new-password' ? 'minlength="10"' : ''} required>
      <button class="pw-eye" type="button" aria-label="显示密码" aria-pressed="false" data-eye>${ICON.eye}</button></span>${hint ? `<span class="hint">${hint}</span>` : ''}</label>`;
  }
  function bindEyes(card) {
    card.querySelectorAll('[data-eye]').forEach(b => b.onclick = () => {
      const i = b.previousElementSibling, show = i.type === 'password';
      i.type = show ? 'text' : 'password'; b.setAttribute('aria-pressed', String(show)); b.setAttribute('aria-label', show ? '隐藏密码' : '显示密码'); i.focus();
    });
  }
  function fieldError(form, err, x) {  // the message under the form, and the field it is about marked and focused
    err.textContent = x.message;
    form.querySelectorAll('[aria-invalid]').forEach(i => i.removeAttribute('aria-invalid'));
    const f = x.field && form.elements[x.field]; if (f && f.setAttribute) { f.setAttribute('aria-invalid', 'true'); f.focus(); } else if (f && f[0]) f[0].focus();  // a radio group: its first
  }
  // opts.teacher: the token of a 老师注册链接 (teacher_service.py): only the sign-up, no 年龄段, and the account is a teacher's.
  async function openLogin(reason, tab, opts) {
    // 安卓 App 的基本模式（1.0.4 起：没同意《用户协议》《隐私和数据》）：登录、注册、验证码都会被 App 拦下（403 app-consent）。
    // 先请 App 再问一次同意（它等学员答完才回 'agreed' 或 'basic'）：同意了就接着打开这个框，还是不同意就不打开，
    // 免得填完才被拦（C2，docs/native-bridge.md §10）
    if (window.FlowApp && FlowApp.has && FlowApp.has('privacy')) {
      let st = null; try { st = await FlowApp.call('privacy.state'); } catch (e) { /* the app could not say: as in a browser */ }
      if (st && st.state === 'basic') {
        let r = null; try { r = await FlowApp.call('privacy.ask'); } catch (e) { /* no answer: as not agreed */ }
        if (r !== 'agreed') return;
      }
    }
    const mail = await mailOn(), teacher = opts && opts.teacher, invite = !teacher && await inviteOn();
    tab = teacher ? 'reg' : tab || 'pw'; if (!mail && (tab === 'code' || tab === 'reset')) tab = 'pw';
    // 注册 and 登录 side by side, one level (the owner on WeChat, 2026-11-25: 「注册一般和登录是一级的」); 密码 or 验证码 is
    // a choice inside 登录, a link under its form
    const tabs = [['reg', '注册', 'reg'], ['pw', '登录', 'pw code']];
    const reset = tab === 'reset';
    openSheet(`<div class="stack auth">
      <div><h2 class="h2" id="sheetTitle">${teacher ? '注册老师账号' : reset ? '找回密码' : tab === 'reg' ? '注册语流' : '登录语流'}</h2>${reason ? `<p class="muted small">${esc(reason)}</p>` : ''}</div>
      ${teacher ? '' : reset ? '<p class="small">填绑定的邮箱，收到验证码后设一个新密码。设好就直接登录，其他手机和电脑上的登录会退出。</p>'
        : `<div class="seg two" role="tablist" aria-label="注册或登录">${tabs.map(([k, l, on]) => `<button role="tab" type="button" data-tab="${k}" aria-selected="${on.split(' ').includes(tab)}">${l}</button>`).join('')}</div>`}
      <form id="authForm" class="stack" novalidate>${authFields(tab, mail, teacher, invite)}</form>
      <p class="err" id="authErr" role="alert"></p>
      ${reset ? '<button class="btn ghost" type="button" data-tab="pw">返回登录</button>' : `<button class="btn ghost" data-close type="button">${tab === 'reg' && !teacher ? '先不注册' : '先不登录'}</button>`}</div>`, card => {
      card.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => openLogin(reason, b.dataset.tab));
      bindEyes(card);
      if (tab === 'reg' && !teacher) bindAge(card, false);
      const form = card.querySelector('#authForm'), err = card.querySelector('#authErr');
      const sendBtn = card.querySelector('[data-send]');
      if (sendBtn) sendBtn.onclick = async () => {
        err.textContent = ''; sendBtn.disabled = true;
        try {
          // from a class invite link (82-class.js joinRoute): the class's own code allowance, not this network's (auth_service)
          const r = await api('/api/auth/code', { email: form.email.value.trim(), purpose: { reg: 'register', code: 'login', reset: 'reset' }[tab], ...(tab === 'reg' && S.invite ? { class: S.invite } : {}), ...(tab === 'reg' && invite ? { invite: form.invite.value.trim() } : {}) });
          toast(r.message || '验证码已发送，请查看邮箱'); countdown(sendBtn); form.code.focus();
        } catch (x) { fieldError(form, err, { message: x.message, field: x.field || 'email' }); sendBtn.disabled = false; }
      };
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        const v = n => (form.elements[n] ? form.elements[n].value : '');
        // the checks the server would make, said at once and without a round trip
        if (tab === 'reg' && invite && !v('invite').trim()) return fieldError(form, err, { message: '内测版要凭邀请码注册，请填写收到的邀请码', field: 'invite' });
        if (tab === 'reg' && !USERNAME_OK.test(v('username').trim())) return fieldError(form, err, { message: '用户名需 2–40 个字符，不能有空格和 @', field: 'username' });
        if ((tab === 'reg' || tab === 'reset') && v('password').length < 10) return fieldError(form, err, { message: '密码至少 10 位', field: 'password' });
        if ((tab === 'code' || tab === 'reset' || (tab === 'reg' && mail)) && !/^\d{6}$/.test(v('code').trim())) return fieldError(form, err, { message: '请输入邮件里的 6 位验证码', field: 'code' });
        const ag = teacher ? {} : readAge(form), agp = tab === 'reg' && !teacher ? ageProblem(ag, true, false) : '';
        if (agp) return fieldError(form, err, { message: agp, field: ag.age ? 'guardian' : 'age' });
        if (tab === 'reg' && !form.consent.checked) return fieldError(form, err, { message: '请先勾选同意：数据存放在香港，以及《用户协议》和《隐私和数据》', field: 'consent' });
        const btn = form.querySelector('[type=submit]'); btn.disabled = true;
        try {
          let r;
          if (tab === 'pw') r = await api('/api/login', { username: v('username').trim(), password: v('password') });
          else if (tab === 'code') r = await api('/api/login', { method: 'code', email: v('email').trim(), code: v('code').trim() });
          else if (reset) r = await api('/api/auth/reset', { email: v('email').trim(), code: v('code').trim(), password: v('password') });
          else r = await api('/api/register', teacher ? { email: v('email').trim(), code: v('code').trim(), username: v('username').trim(), password: v('password'), teacher, storage: true, terms: true }
            : { email: v('email').trim(), code: v('code').trim(), username: v('username').trim(), password: v('password'), age: ag.age, guardian: ag.guardian, storage: true, terms: true, ...(invite ? { invite: v('invite').trim() } : {}) });
          await afterLogin(); closeSheet();
          const name = (S.user && S.user.username) || r.username || '';
          toast(reset ? '密码已重设，已经登录' : teacher ? `老师账号注册好了，欢迎你${name ? '，' + name : ''}` : tab === 'reg' ? `注册成功，欢迎你${name ? '，' + name : ''}` : `欢迎回来${name ? '，' + name : ''}`);
          route(true);
        } catch (x) { fieldError(form, err, x); btn.disabled = false; }
      };
    });
  }
  function authFields(tab, mail, teacher, invite) {
    const email = '<label class="field">邮箱<input name="email" type="email" autocomplete="email" inputmode="email" autocapitalize="off" spellcheck="false" required></label>';
    const code = `<div class="code-row"><label class="field">验证码<input name="code" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="\\d{6}" required></label>
      <button class="btn small" type="button" data-send>发送验证码</button></div><span class="hint">验证码 10 分钟内有效。收不到就看看垃圾邮件，60 秒后可以重发。</span>`;
    if (tab === 'pw') return `<label class="field">用户名或邮箱<input name="username" type="text" autocomplete="username" autocapitalize="off" spellcheck="false" required></label>
      ${pwField('密码', 'password', 'current-password')}
      <div class="auth-links">${mail ? '<button class="link small" type="button" data-tab="code">用邮箱验证码登录</button><button class="link small" type="button" data-tab="reset">忘记密码？</button>' : '<span class="tiny muted">忘记密码：请联系老师或管理员重设。</span>'}</div>
      <button class="btn primary block" type="submit">登录</button>`;
    if (tab === 'code') return email + code + '<div class="auth-links"><button class="link small" type="button" data-tab="pw">用密码登录</button></div><button class="btn primary block" type="submit">登录</button>';
    if (tab === 'reset') return email + code + pwField('新密码', 'password', 'new-password', '至少 10 位，最好是一句只有你知道的话') + '<button class="btn primary block" type="submit">设置新密码并登录</button>';
    const inv = invite ? '<label class="field">邀请码<input name="invite" type="text" autocomplete="off" autocapitalize="characters" spellcheck="false" maxlength="12" required>'
      + '<span class="hint">内测版要凭邀请码注册。字母不分大小写，横线可以不写。</span></label>' : '';
    return inv + (mail ? email + code : '') + `<label class="field">用户名<input name="username" type="text" autocomplete="username" autocapitalize="off" spellcheck="false" maxlength="40" required>
        <span class="hint">2–40 个字符，可以用中文，不能有空格和 @。登录时用户名和邮箱都可以用。</span></label>
      ${pwField('密码', 'password', 'new-password', '至少 10 位，最好是一句只有你知道的话')}
      ${mail ? '' : '<span class="hint">注册后可以在「我的」里绑定邮箱，忘记密码时用它找回。</span>'}
      ${teacher ? '' : ageFields('', false)}
      ${consentField()}
      <button class="btn primary block" type="submit">${teacher ? '注册老师账号并登录' : '注册并登录'}</button>`;
  }
  // An older password-reset email links to /#reset=<token>: set the new password here, then sign in with it.
  function resetByLink(token) {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">设置新密码</h2><p class="small">链接 30 分钟内有效。设好以后，用新密码登录；其他设备上的登录会退出。</p>
      <form id="rlForm" class="stack" novalidate>${pwField('新密码', 'password', 'new-password', '至少 10 位')}<button class="btn primary block" type="submit">保存新密码</button></form>
      <p class="err" id="rlErr" role="alert"></p><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      bindEyes(card);
      const form = card.querySelector('#rlForm'), err = card.querySelector('#rlErr');
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        if (form.password.value.length < 10) return fieldError(form, err, { message: '密码至少 10 位', field: 'password' });
        const b = form.querySelector('[type=submit]'); b.disabled = true;
        try { await api('/api/recovery/reset', { token, password: form.password.value }); toast('密码已重设'); openLogin('密码已重设，请用新密码登录。', 'pw'); }
        catch (x) { fieldError(form, err, x); b.disabled = false; }
      };
    });
  }
  function countdown(btn) { let n = 60; btn.textContent = `${n} 秒后可重发`; const t = setInterval(() => { n--; if (n <= 0) { clearInterval(t); btn.disabled = false; btn.textContent = '重新发送'; } else btn.textContent = `${n} 秒后可重发`; }, 1000); }
  async function afterLogin() {
    await refreshHome();
    if (!S.home.profile && S.guest && S.guest.level) { try { await api('/api/next/profile', S.guest); await refreshHome(); } catch (e) { /* keep guest */ } }
    const gt = load('flow-next-guest-test');  // a vocabulary test taken before signing in
    if (gt && gt.answers) { try { await api('/api/next/vocab/test', { answers: gt.answers }); save('flow-next-guest-test', null); } catch (e) { /* try next time */ } }
  }

  /* ---------- 字号和行距 (81-me.js): set before anything is drawn ---------- */
  const TEXT = Object.assign({ size: 'm', lh: 'n' }, load('flow-next-text') || {});
  function applyText() { document.documentElement.dataset.size = TEXT.size; document.documentElement.dataset.lh = TEXT.lh; }
  applyText();

  /* ---------- the tab bar's place ---------- */
  // On phones the tabs are fixed to the bottom, outside the sticky top bar: iOS Safari moves a fixed element along
  // with a sticky ancestor, and inside the bar the tabs slid up the screen on a long page. On wide screens they are a
  // row of links in the top bar.
  const WIDE = matchMedia('(min-width:760px)');
  function placeTabs() {
    const t = document.querySelector('.tabs'), bar = document.getElementById('bar');
    if (!t || !bar) return;
    if (WIDE.matches && t.parentElement !== bar) bar.appendChild(t);
    else if (!WIDE.matches && t.parentElement === bar) bar.after(t);
  }
  placeTabs();
  if (WIDE.addEventListener) WIDE.addEventListener('change', placeTabs); else if (WIDE.addListener) WIDE.addListener(placeTabs);

  // A 老师账号's first tab is its classes (#/ is the teacher page, 82-class.js); everyone else's is 今日.
  function roleTabs() { const t = document.querySelector('[data-nav="today"] span'); if (t) t.textContent = S.user && S.user.teacher ? '班级' : '今日'; }

  /* ---------- router ---------- */
  function setNav(name) { document.querySelectorAll('[data-nav]').forEach(a => a.dataset.nav === name ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current')); homeBack(name); }
  function parts() { return location.hash.replace(/^#\/?/, '').split('/'); }
  async function route(keepScroll, quiet) {
    if (/^#reset=/.test(location.hash)) {  // an older password-reset email
      const token = decodeURIComponent(location.hash.slice(7)); history.replaceState(null, '', location.pathname + location.search + '#/');
      setTimeout(() => resetByLink(token), 0);
    }
    LONG.stop(); TTS.stop(); NAR.stop(); CLIP.stop(); MIC.stop(); MINI.undock(); MINI.hide(); hideSelbar(); swipeOff(); document.body.classList.remove('reviewing', 'onboarding'); bar.classList.remove('hide'); document.onselectionchange = null; document.onkeydown = null;
    const [name, a, b] = parts();
    if (name === 'about') { location.replace('/about'); return; }  // 认识语流 is its own page (the guide links here)
    const last = S.lastRoute.split('/');
    const sameMaterial = name === 'm' && last[0] === 'm' && last[1] === a && !!view.querySelector('#pane');
    S.prevRoute = S.lastRoute; S.lastRoute = parts().join('/');  // 问题反馈 says which page it came from
    if (!sameMaterial && !quiet) view.innerHTML = skeleton();
    let fresh = S.homeFresh; S.homeFresh = false;  // home data fetched just before this page: today() need not ask again
    try {
      if (!S.home) { await refreshHome(); fresh = true; }
      // 认识语流's 「注册账号」 (/#/join): the first page with the sign-up sheet open over it; signed in, just the first page.
      if (name === 'join') { location.replace('#/'); if (!S.user) setTimeout(() => openLogin('', 'reg'), 0); return; }
      // 数据存放在香港 not agreed (an older account, or paused): that page first, every page but the guide (81-privacy.js)
      if (S.user && (S.user.storage !== 'ok' || S.user.terms !== 'ok') && name !== 'guide') { setNav(''); await storageView(); }
      // 选方向和目标 is the first-time page: a guest lands on it (no goals yet), and when it signs in there (「已有账号？
      // 登录」, or 认识语流's 「免费开始学」 → the sign-in sheet over it) to an account that has its goals, 今日 follows instead
      // of the questions again (the owner, 2026-11-26: an older account was asked again after signing in from a link)
      else if (name === 'welcome' && a !== 'edit' && S.user && S.home && S.home.profile) { location.replace('#/'); return; }
      else if (name === 'welcome') { setNav(''); await welcome(a === 'edit'); }
      // 老师模式 (82-class.js): #/teacher/<token> is a 老师注册链接; a teacher account's home is its classes
      else if (name === 'teacher') { setNav(''); await teacherSignup(decodeURIComponent(a || '')); }
      else if (name === 'teach' || (name === '' && S.user && S.user.teacher)) { setNav('today'); await teachHome(); }
      // Only the personalised home needs the level questions first; everything else works for a new guest too.
      else if (!hasProfile() && !['me', 'vocab', 'sounds', 'library', 'graph', 'm', 'cards', 'import', 'report', 'review', 'placement', 'exam', 'series', 'mix', 'easy', 'words', 'speak', 'growth', 'radar', 'practice', 'guide', 'feedback', 'weekly-off', 'invite', 'class', 'updates'].includes(name)) { location.replace('#/welcome'); return; }
      else if (name === 'placement') { setNav('practice'); await placementView(); }
      else if (name === 'exam') { setNav('practice'); await (b ? examTypeView(a, decodeURIComponent(b)) : examView(a)); }
      else if (name === 'series') { setNav('today'); await seriesView(decodeURIComponent(a || '')); }
      else if (name === 'easy') { setNav('practice'); await (a ? easyRead(decodeURIComponent(a)) : easyView()); }
      else if (name === 'words' && a === 'confuse') { setNav('cards'); await (b ? confuseRound(decodeURIComponent(b)) : confuseView()); }
      else if (name === 'speak') { setNav('practice'); await (a === 'ielts' ? (b ? ieltsPractice(decodeURIComponent(b)) : ieltsView()) : a ? speakScene(decodeURIComponent(a)) : speakView()); }
      else if (name === 'radar') { setNav('radar'); await (a === 'goals' ? radarGoals() : a === 'test' && (b === 'reading' || b === 'listening') ? assessComprehension(b) : a === 'test' && (b === 'speaking' || b === 'writing') ? assessJudged(b) : a === 'test' ? radarTests() : radarView()); }
      else if (name === 'growth') { setNav('me'); await growthView(a ? decodeURIComponent(a) : ''); }
      else if (name === 'two') { setNav('today'); await twoView(decodeURIComponent(a || '')); }  // 听两句、答一句 (26-two-lines.js)
      else if (name === 'mix') { setNav('practice'); await mixView(a === 'pair' || a === 'topic' || a === 'exam' || a === 'more' ? a : 'due', b ? decodeURIComponent(b) : ''); }
      else if (name === 'm' && a) { setNav('today'); await study(decodeURIComponent(a), b || 'listen', sameMaterial); }
      else if (name === 'graph') { setNav('practice'); await (a ? nodeView(decodeURIComponent(a)) : graphView()); }
      else if (name === 'cards' && a === 'mistake') { setNav('practice'); await mistakeView(); }  // 错题本: 练习 → 复习
      // #/cards/find/<词>: the words list with that word searched (the iPhone's system search opens a word this way, 语流 C1)
      // (a 「/」 left unencoded, as in borrow / lend, is still part of the word)
      else if (name === 'cards' && a === 'find') { setNav('cards'); await vocabView(parts().slice(2).map(x => decodeURIComponent(x)).join('/').slice(0, 80), 1, ''); const sf = document.getElementById('sf'); if (sf) sf.scrollIntoView({ block: 'start' }); }
      else if (name === 'cards') { setNav('cards'); await vocabView('', 1, a || ''); }
      else if (name === 'import') { setNav('practice'); await importView(); }
      else if (name === 'sounds') { setNav('practice'); await soundsView(a ? decodeURIComponent(a) : ''); }
      else if (name === 'report') { setNav('me'); await reportView(); }
      else if (name === 'today') { setNav('today'); todayEditView(); }  // 调整顺序 (#/today/edit, 13-today-views.js)
      else if (name === 'weekly-off') { setNav('me'); await weeklyOffView(decodeURIComponent(a || '')); }  // the link in the Sunday mail
      else if (name === 'vocab') { setNav('cards'); await (a === 'plan' ? planView() : a === 'test' ? vocabTest() : vocabView()); }
      else if (name === 'review') { setNav(a === 'other' ? 'practice' : 'cards'); await reviewView(a === 'more', a === 'other' ? 'other' : 'words'); }
      else if (name === 'library') { setNav('practice'); await libraryView(); }
      else if (name === 'practice') { setNav('practice'); await practiceView(); }
      else if (name === 'guide') { setNav('practice'); await guideView(a ? decodeURIComponent(a) : ''); }
      else if (name === 'me') { setNav('me'); if (a === 'habits') habitsView(); else await meView(a); }  // #/me/account, #/me/help: that fold open; 使用习惯 (81-habits.js)
      else if (name === 'invite') { setNav('me'); await joinRoute(decodeURIComponent(a || '')); }
      else if (name === 'class' && a) { setNav(S.user && S.user.teacher ? 'today' : 'me'); await classView(decodeURIComponent(a)); }
      else if (name === 'feedback') { setNav('me'); await feedbackView(); }
      else if (name === 'updates') { setNav('me'); await updatesView(); }  // 更新记录 (83-updates.js)
      else { setNav('today'); await today(fresh); }
      if (!sameMaterial && name !== 'welcome' && !quiet) enter(view);
      if (!sameMaterial && !quiet) { const h = view.querySelector('h1'); announce(h ? h.textContent : document.title); }
      homeBackLink();  // 主屏 App: the page's own 「← 上一级」 line gives way to the top bar's 返回 (04-home-app.js)
      if (!quiet) tourMaybe();  // 新手引导: 今日 (or 我的班级) the first time a new account opens it (08-tour.js)
    } catch (e) {
      const kept = e.network ? OFF.list() : [];  // offline: what can still be studied
      view.innerHTML = `<div class="empty"><div class="big">⚠︎</div><p>${esc(e.message)}</p><button class="btn" id="retry">重试</button>
        ${kept.length ? `<p class="small">没网时，这些已存到本机的材料还能学：</p><div class="mlist">${kept.map(k => mrow(k, null, '', '')).join('')}</div>` : ''}
        <p class="small"><a class="link" href="#/feedback">反馈这个问题</a></p></div>`;
      // an older front end than the server's may be what failed: a new version first (04-home-app.js), then the page again
      document.getElementById('retry').onclick = async ev => { ev.currentTarget.disabled = true; if (!(await retryOrUpdate())) route(); };
      errorPageUpdate();
    } finally { if (!keepScroll && !sameMaterial && !quiet) view.focus({ preventScroll: true }); }
  }
  // How the page changed (the Navigation API where there is one; else a longer history means a link, and a back or a
  // redirect cannot be told apart, so neither closes a sheet)
  const NAV = { type: '', len: history.length };
  if (window.navigation && navigation.addEventListener) navigation.addEventListener('navigate', e => { NAV.type = e.navigationType || ''; });
  window.addEventListener('hashchange', () => {
    const [name, a] = parts(), last = S.lastRoute.split('/');
    if (!(name === 'm' && last[0] === 'm' && last[1] === a)) window.scrollTo(0, 0);
    // another page the learner went to (a link, 返回, the browser's or the phone's back): a sheet of the page left closes
    // with it (one waiting for an answer stays). The app's own redirects (location.replace: #/join → #/ → #/welcome) keep
    // the sheet a route opened on the way (#/join's 注册). A tip the page left showed is put away, one said on the way
    // here (「已保存」) stays.
    const redirect = NAV.type ? NAV.type === 'replace' : history.length === NAV.len; NAV.type = ''; NAV.len = history.length;
    if (!redirect && !sheetEl.hidden && !sheetLocked()) closeSheet();
    if (Date.now() - (toast.at || 0) > 400) toastEl.classList.remove('show');
    route();
  });
  // Focus mode: while reading, the top bar slides away on scroll down and comes back on scroll up.
  let lastY = 0;
  window.addEventListener('scroll', () => {
    const y = window.scrollY, reading = /^#\/m\//.test(location.hash);
    bar.classList.toggle('hide', reading && y > 140 && y > lastY + 2);
    if (y < lastY - 2) bar.classList.remove('hide');
    lastY = y;
  }, { passive: true });

  /* ---------- 内测版: flow.jasa.hk, a second site with its own data, where new versions run before 语流 gets them ---------- */
  // The server says which site the page is on (<html data-channel>, app.CHANNEL). 语流 itself is flowlang.cn. On the
  // 内测版: a line under the top bar on every page, 「内测」 in the tab's title, a note in the sign-in sheet (95-channel.css),
  // and once per phone a sheet saying where 语流 is. Until 2026-11-24 this address was 语流 itself, so what this phone
  // kept for an account from then (instant-page copies, materials kept for offline study, the review queue, answers not
  // sent yet) is cleared before the page starts: none of it belongs to this site's accounts.
  const BETA = document.documentElement.dataset.channel === 'beta';
  const MAIN_SITE = 'https://flowlang.cn';
  const BETA_BEFORE = (() => {
    if (!BETA || load('flow-channel') === 'beta') return null;
    let before = false;
    try {
      before = Object.keys(localStorage).some(k => k.startsWith('flow-'));
      ['flow-snap', 'flow-offline', 'flow-next-outbox', 'flow-next-review-cache', 'flow-habit-lastweek', 'flow-habit-cheered'].forEach(k => localStorage.removeItem(k));
    } catch (e) { /* private mode */ }
    save('flow-channel', 'beta');
    return before;
  })();
  // In Flow's 内测 apps (window.FlowApp: iOS, Android, desktop) the learner installed the 内测版 on purpose, and a link to
  // flowlang.cn would leave the app for the system browser: the line stays, without the link, and the sheet is not shown.
  const IN_FLOW_APP = !!window.FlowApp;
  // The line is one thin row and can be closed (the owner, 2026-11-25: on a phone it pushed one-screen pages past the
  // screen); closed, it stays closed on this device until BETA_NOTE changes (something learners on the 内测版 should
  // read). 「内测」 stays by the logo, and 我的 → 内测版 has the rest: the version, what changed, 去正式版, feedback.
  const BETA_NOTE = '2026-11-25';
  if (BETA) {
    document.title = '内测 · ' + document.title;
    const brand = document.querySelector('#bar .brand');  // no ?. here: iOS before 13.4 cannot read it (old-device support)
    if (brand) brand.insertAdjacentHTML('beforeend', '<span class="beta-pill" aria-label="内测版">内测</span>');
    if (load('flow-beta-bar') !== BETA_NOTE) {
      document.getElementById('bar').insertAdjacentHTML('afterend', `<p class="beta-bar" id="betaBar" role="note"><b>内测版</b><span>新功能先在这里试，账号和数据与正式版分开，详见「我的」</span><button class="bb-x" type="button" aria-label="关闭内测版提示" data-tap="beta-bar-close">✕</button></p>`);
      document.querySelector('#betaBar .bb-x').onclick = () => { save('flow-beta-bar', BETA_NOTE); TIPS.mark('beta-note'); document.getElementById('betaBar').remove(); };
      // closed on another device (kept on the account, 08-tips.js): gone here too once the phone knows. A new BETA_NOTE
      // that everyone should read again needs a new name in tour_service.TIPS.
      document.addEventListener('flow-tips', () => {
        const bar = document.getElementById('betaBar');
        if (bar && tipSeen('beta-note') === true) { save('flow-beta-bar', BETA_NOTE); bar.remove(); }
      });
    }
  }
  // Once per phone, after the first page is up, and once per account: it waits until the phone knows what the account
  // has seen (08-tips.js), so a second phone of the same learner does not show it again.
  if (BETA_BEFORE !== null && !IN_FLOW_APP) document.addEventListener('flow-tips', () => setTimeout(() => {
    if (tipSeen('beta-hello') === true) return;
    TIPS.mark('beta-hello');
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">这里是语流内测版</h2>
    ${BETA_BEFORE ? '<p><b>语流的网址改成了 flowlang.cn。</b></p><p class="small">你的账号和学习记录都在 flowlang.cn，用原来的用户名和密码登录就行（换了网址，要重新登录一次）。加到了手机桌面的话，也请在 flowlang.cn 重新添加一次。</p>'
      : zhEn('<p>语流正式版的网址是 <b>flowlang.cn</b>。</p>', '<p>Flow\'s main site is <b>flowlang.cn</b>.</p>')}
    <p class="small muted">这里（flow.jasa.hk）用来先试还没正式上线的新功能。账号和数据都和正式版分开，内测期间可能会清空。</p>
    <a class="btn primary" href="${MAIN_SITE}/" data-tap="beta-main">去正式版 flowlang.cn</a>
    <button class="btn ghost" data-close type="button">留在内测版</button></div>`);
  }, 700), { once: true });
  /* ---------- 主屏 App (Safari 「添加到主屏幕」, r28): a way back, the keyboard, and the version after a long sleep ---------- */
  // Opened from the home screen there is no browser around the page: no back button, no swipe back, and the app may
  // stay in the background for days. html.home-app marks it (also the Android/desktop install, display-mode standalone).
  // The iOS app (语流 20, ios/: Flow in a WKWebView, its user agent ending in FlowiOS/<version>) has no browser around
  // the page either, but there navigator.standalone and display-mode are not standalone. It follows theme-color and the
  // keyboard itself (the web view ends at the keyboard), so the two iOS work-arounds below stay off in it.
  // The desktop app (语流 22: Windows and macOS, a native window around the site, its user agent ending in
  // FlowDesktop/<version> (Windows) or (macOS)) has no browser back either: 返回 is its way back (with ⌘[ / Alt+← in its
  // own menu). Any of Flow's apps also says so before the page's scripts: window.FlowApp ({platform: 'ios' | 'windows' |
  // 'macos' …}). The keyboard work-around is for iPhones and iPads only, so the desktop leaves it alone anyway.
  // The HarmonyOS app (语流 C4, harmony/: ArkWeb, its user agent ending in FlowHarmony/<version>) is one of them too.
  const IN_IOS_APP = /FlowiOS\//.test(navigator.userAgent);
  const IN_APP = /Flow(iOS|Android|Desktop|Harmony)\//.test(navigator.userAgent) || !!window.FlowApp;  // as docs/native-bridge.md (#162) names them
  const HOME_APP = matchMedia('(display-mode: standalone)').matches || navigator.standalone === true || IN_APP;
  document.documentElement.classList.toggle('home-app', HOME_APP);
  // --bar-h: the top bar's height as it is (the status bar or Dynamic Island above it in the home-screen app), and
  // --top-h: all above the page (the bar, and the 内测版's line while it is open), for pages that fill one screen
  // (复习 and 测词汇量, 80-flat.css). 48px until measured; the inset is padding, so the border box is measured.
  if (window.ResizeObserver && bar) {
    const tops = () => { const r = document.documentElement.style, line = document.getElementById('betaBar');
      const b = Math.round(bar.getBoundingClientRect().height) || Math.round(parseFloat(getComputedStyle(document.body).paddingTop) || 0);  // no bar (phones): the status bar's room
      r.setProperty('--bar-h', b + 'px'); r.setProperty('--top-h', b + (line && line.isConnected ? Math.round(line.getBoundingClientRect().height) : 0) + 'px'); };
    const ro = new ResizeObserver(tops), line = document.getElementById('betaBar');
    ro.observe(bar, { box: 'border-box' }); if (line) ro.observe(line, { box: 'border-box' });
    if (line) new MutationObserver(tops).observe(line.parentNode, { childList: true });  // closed: removed, no size to report
  }

  // ---- 返回: in the top bar, in place of the logo, on every page but the four tabs and the first-visit page.
  // It goes to the page before when the app has one (the history kept here), else to the page's own tab (‹ 练习).
  const HIST = [location.hash || '#/'];
  const TAB_OF = { today: ['#/', '今日'], practice: ['#/practice', '练习'], radar: ['#/radar', '能力'], cards: ['#/cards', '单词'], me: ['#/me', '我的'] };
  // The four tab pages; #/teach is a 老师账号's home (its first tab, 「班级」, #121), the same page as its #/.
  const TAB_PAGES = ['', 'practice', 'radar', 'cards', 'me', 'teach'];  // radar: the 「能力」 tab (2026-11-26)
  // A page's tab as the tab bar shows it: a 老师账号's first tab says 班级, not 今日 (02-shell.js roleTabs)
  const tabOf = nav => {
    const a = document.querySelector(`.tabs [data-nav="${nav}"]`), t = TAB_OF[nav] || TAB_OF.today;
    return a ? [a.getAttribute('href') || t[0], ((a.querySelector('span') || {}).textContent || t[1]).trim()] : t;
  };
  addEventListener('hashchange', () => {
    const h = location.hash || '#/';
    if (HIST.length > 1 && HIST[HIST.length - 2] === h) HIST.pop(); else if (HIST[HIST.length - 1] !== h) HIST.push(h);
    if (HIST.length > 50) HIST.splice(0, HIST.length - 50);
  });
  // Called by setNav (02-shell.js) on every page with the tab it belongs to.
  // Phones (B9's batch 1, the user 2026-11-26): no 「语流 Flow」 bar once in the app; its room goes to the page. It stays
  // where it has something to say: 返回 in the home-screen app and Flow's apps (no browser back around them), and the
  // first-visit page (not in the app yet). A computer keeps it, with the tabs in it (98-home-app.css, html.bar-off).
  const PHONE = matchMedia('(max-width: 759px)');
  function homeBack(nav) {
    const btn = document.getElementById('backBtn'), brand = bar.querySelector('.brand');
    if (!btn) return;
    homeBack.nav = nav;
    const h = location.hash.replace(/^#\/?/, '');
    const root = TAB_PAGES.includes(h) || h === 'welcome';
    const show = HOME_APP && !root;
    btn.hidden = !show; brand.hidden = show;
    document.documentElement.classList.toggle('bar-off', PHONE.matches && !show && h !== 'welcome');
    if (!show) return;
    const tab = tabOf(TAB_OF[nav] ? nav : 'today'), prev = HIST.length > 1;
    btn.querySelector('span').textContent = prev ? '返回' : tab[1];
    btn.setAttribute('aria-label', prev ? '返回上一页' : '返回' + tab[1]);
    btn.onclick = () => { if (HIST.length > 1) history.back(); else location.hash = homeBack.up || tab[0]; };
    homeBack.up = '';
  }
  if (PHONE.addEventListener) PHONE.addEventListener('change', () => homeBack(homeBack.nav));
  else if (PHONE.addListener) PHONE.addListener(() => homeBack(homeBack.nav));  // Safari before 14
  // A sub-page's own 「← 口语路线」 line (a .link.small at the top of the page, before its title) says the same as the
  // top bar's 返回 and takes a line of the screen: in the app it is hidden, and 返回 with no page before goes where it
  // went (‹ 口语路线), not to the tab. In Safari there is no 返回 in the bar: the line stays.
  function homeBackLink() {
    const btn = document.getElementById('backBtn');
    if (!HOME_APP || !btn || btn.hidden) return;
    const h1 = view.querySelector('h1');
    const a = [...view.querySelectorAll('a.link.small')].find(x => /^←/.test(x.textContent.trim()) && (!h1 || x.compareDocumentPosition(h1) & Node.DOCUMENT_POSITION_FOLLOWING));
    if (!a) return;
    const box = a.parentElement !== view && a.parentElement.children.length === 1 && !a.parentElement.textContent.replace(a.textContent, '').trim() ? a.parentElement : a;
    box.classList.add('pg-back');
    if (HIST.length > 1) return;
    const to = a.getAttribute('href'), name = a.textContent.trim().replace(/^←\s*/, '');
    homeBack.up = to; btn.querySelector('span').textContent = name; btn.setAttribute('aria-label', '返回' + name);
  }

  // ---- 键盘: a field being typed in and its button stay above the keyboard. iOS lays fixed things (the bottom sheet)
  // against the whole screen and lets the keyboard cover them; visualViewport says how much of the screen is left.
  // --kb is the keyboard's height: the sheet stands on it, and the page gets that much room below to scroll into.
  if (window.visualViewport) {
    const vv = window.visualViewport, root = document.documentElement;
    const submitOf = el => {
      const s = el.dataset && el.dataset.submit;
      const named = s && document.querySelector(s);
      if (named) return named;
      if (el.form) { const b = el.form.querySelector('[type=submit], .btn.primary'); if (b) return b; }
      const box = el.closest('#sheetCard, form, section, .card, .stack') || el.parentElement;
      return [...box.querySelectorAll('button.primary, .btn.primary, button[type=submit]')].find(b => el.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) || null;
    };
    // Client rects → the part of the screen in sight: before iOS 26 they are against the layout viewport, which the
    // visual one may have panned down by offsetTop; on iOS 26+ (27.2 in the simulator) they are against what is in
    // sight already, offsetTop says something else, and pageTop ≈ scrollY. scrollY − pageTop is right for both.
    const shift = () => scrollY - vv.pageTop;
    // the sticky top bar and the study steps under it: a field brought into sight must not end up under them
    const headLine = () => Math.max(0, ...[bar, document.querySelector('main .steps')].filter(x => x && x.offsetParent !== null && /sticky|fixed/.test(getComputedStyle(x).position))
      .map(x => x.getBoundingClientRect()).filter(r => r.top < 120).map(r => r.bottom + shift()));
    let kbSeen = 0;  // the keyboard's height the last time it was up (iPhone portrait: about half the screen)
    // Flow's apps make the page itself shorter for the keyboard (Android's WebView, the iOS app's web view that ends at
    // the keyboard; 语流 21, 20): nothing is covered, but a field near the end and its button (登录, 发送) are now below the
    // page's own end. The page's height without a keyboard, per width, tells that: shorter while typing = a keyboard.
    let tallest = innerHeight, wide = innerWidth;
    const fit = () => {
      const kb = Math.max(0, Math.round(innerHeight - vv.height - vv.offsetTop));
      root.style.setProperty('--kb', kb + 'px');  // where fixed things (the sheet) stand
      // Up or not from the screen part covered: on iOS 26+ innerHeight shrinks with the keyboard, so kb above is 0 there.
      const covered = Math.round(root.clientHeight - vv.height), up = covered > 80;
      if (up) kbSeen = covered;
      const el = document.activeElement, typing = !!el && isTyping({ target: el });
      if (innerWidth !== wide) { wide = innerWidth; tallest = innerHeight; }  // turned: its own height again
      if (!typing) tallest = Math.max(tallest, innerHeight);
      const shrunk = typing && tallest - innerHeight > 80;
      document.body.classList.toggle('kb-open', up || shrunk);
      if (!(up || shrunk) || !typing) return;
      const btn = submitOf(el), card = el.closest('#sheetCard'), s = shift();
      const r = el.getBoundingClientRect(), b = btn && btn.offsetParent !== null ? btn.getBoundingClientRect() : r;
      const top = (card ? 0 : headLine()) + 8, bottom = vv.height - 8;
      const fieldTop = r.top + s, over = Math.max(r.bottom, b.bottom) + s - bottom;
      const by = over > 0 ? Math.min(over, fieldTop - top) : fieldTop < top ? fieldTop - top : 0;  // never push the field's top out
      if (by) (card || window).scrollBy({ top: by, behavior: 'auto' });
    };
    // On iPhones and iPads the page moves first, at the tap: when a field near the end of the page is to come into
    // sight, iOS 26+ moves the whole web view without telling the page (scrollY stays, the client rects do not
    // change) and stops at the keyboard itself, so its ∧ ∨ ✓ bar covers the field and its button (对话, 导入文章 —
    // tools/ios_sim_check.py, 2026-11-25). With room below the page and the field and its button already where the
    // keyboard will leave them in sight, iOS has nothing to move; fit() above then corrects what is left.
    const IOS_KB = !IN_IOS_APP && (/iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1));
    const makeRoom = el => {
      if (!IOS_KB || el.closest('#sheetCard') || root.clientHeight - vv.height > 80) return;  // a sheet stands on the keyboard; up already: fit()
      document.body.classList.add('kb-room');
      const btn = submitOf(el), s = shift(), r = el.getBoundingClientRect(), b = btn && btn.offsetParent !== null ? btn.getBoundingClientRect() : r;
      const kbH = kbSeen || Math.round(root.clientHeight * (innerWidth > innerHeight ? 0.62 : 0.5));
      const fieldTop = r.top + s, by = Math.min(Math.max(r.bottom, b.bottom) + s - (root.clientHeight - kbH - 12), fieldTop - headLine() - 12);
      if (by > 4 || fieldTop < headLine()) window.scrollBy({ top: by, behavior: 'auto' });
    };
    let raf = 0;
    const later = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(fit); };
    vv.addEventListener('resize', later);
    vv.addEventListener('scroll', later);
    document.addEventListener('focusin', e => { if (!isTyping(e)) return; makeRoom(e.target); setTimeout(fit, 320); });  // fit after iOS has moved things itself
    document.addEventListener('focusout', () => setTimeout(() => { if (!isTyping({ target: document.activeElement })) document.body.classList.remove('kb-room'); }, 0));
  }

  // ---- 新版本: back in front (or when the service worker changes), ask the server which version it serves. A new one
  // is taken at once on a resting page (one of the four tabs, nothing typed, no sheet, nothing playing or recording); anywhere
  // else one line offers it, and it is taken on the next resting page. The new service worker (sw.js: skipWaiting,
  // claim) is given up to 4 s to take over first, so the reload gets the new page and files, not the cached ones.
  // A version tried once and still not running is only offered again, never reloaded into a loop.
  const MY_ASSET = ((document.querySelector('script[src*="/next.js"]') || {}).src || '').split('v=')[1] || '';
  let NEW_ASSET = '', checked = 0, swSwitched = false;
  async function checkVersion(force) {
    if (!MY_ASSET || MY_ASSET.startsWith('__') || (!force && Date.now() - checked < 30e3)) return;
    checked = Date.now();
    let v = null;
    try { v = await fetch('/api/version', { cache: 'no-store', credentials: 'same-origin' }).then(r => (r.ok ? r.json() : null)); } catch (e) { return; }
    if (!v || !v.asset || v.asset === MY_ASSET) return;
    NEW_ASSET = v.asset;
    try { const reg = navigator.serviceWorker && await navigator.serviceWorker.getRegistration(); if (reg) reg.update().catch(() => {}); } catch (e) { /* no worker: the reload asks the server */ }  // the reload into the new version cuts the check short (WebKit: an unhandled "sw.js load failed")
    updateWhenSafe();
  }
  // Something playing or recording (the narration, a clip or the server/browser voice in 01-audio-offline.js, the
  // microphone in 70-learner.js, any <audio> on the page; read only): a reload would cut it off. The 今日 mini player,
  // 好句 and shadowing can all be going on a tab page.
  function audioBusy() {
    try {
      if (!NAR.audio.paused || !CLIP.audio.paused || MIC.busy()) return true;
      if (window.speechSynthesis && (speechSynthesis.speaking || speechSynthesis.pending)) return true;
    } catch (e) { return true; }
    return [...document.querySelectorAll('audio, video')].some(m => !m.paused);
  }
  function restingNow() {
    const h = location.hash.replace(/^#\/?/, '');
    return TAB_PAGES.includes(h) && sheetEl.hidden && document.visibilityState === 'visible'
      && !isTyping({ target: document.activeElement }) && !document.body.classList.contains('playing') && !audioBusy();
  }
  function updateWhenSafe() {
    if (!NEW_ASSET) return;
    if (load('flow-update-tried') !== NEW_ASSET && restingNow()) { takeUpdate(); return; }
    updateBar();
  }
  async function takeUpdate(asked) {
    save('flow-update-tried', NEW_ASSET);
    const sw = navigator.serviceWorker;
    // the new worker may have taken over already (then at once); otherwise wait for it, at most 4 s
    if (sw && sw.controller && !swSwitched) await new Promise(done => { sw.addEventListener('controllerchange', done, { once: true }); setTimeout(done, 4000); });
    // Unasked, the page may no longer be resting after that wait: a text opened and 播放全文 started, a recording
    // (语流 9 on the simulator, 2026-11-25: the reload cut a reading before its first sentence). Then the line offers it,
    // and the next resting page takes it.
    if (!asked && !restingNow()) { save('flow-update-tried', null); updateBar(); return; }
    location.reload();
  }
  function updateBar() {
    if (document.getElementById('updateBar') || load('flow-update-later') === NEW_ASSET + '|' + new Date().toDateString()) return;
    const box = document.createElement('div');
    box.className = 'update-bar'; box.id = 'updateBar'; box.setAttribute('role', 'status');
    box.innerHTML = '<button class="ub-go" type="button" data-tap="update-bar">有新版本，点一下更新</button><button class="ub-x" type="button" aria-label="今天先不更新">×</button>';
    document.body.appendChild(box);
    box.querySelector('.ub-go').onclick = e => { e.currentTarget.textContent = '正在更新…'; e.currentTarget.disabled = true; takeUpdate(true); };
    box.querySelector('.ub-x').onclick = () => { save('flow-update-later', NEW_ASSET + '|' + new Date().toDateString()); box.remove(); };
  }
  // 报错页 (02-shell.js route): a front end older than the server's may be what failed, e.g. a check the server added
  // since (the terms agreement, 2026-11-25: a copy cached before it got the same error on every 重试, B8). On an error
  // page a new version is taken at once, once per version; its 重试 takes one the server has, and with none tries again.
  async function errorPageUpdate() {
    await checkVersion(true);
    if (NEW_ASSET && load('flow-update-tried') !== NEW_ASSET) takeUpdate(true);
  }
  async function retryOrUpdate() {
    await checkVersion(true);
    if (!NEW_ASSET) return false;
    takeUpdate(true); return true;
  }
  // after a reload into the new version: said once
  if (MY_ASSET && load('flow-update-tried') === MY_ASSET) { save('flow-update-tried', null); setTimeout(() => toast('已更新到新版本'), 1200); }
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') checkVersion(); });
  if (navigator.serviceWorker) navigator.serviceWorker.addEventListener('controllerchange', () => { swSwitched = true; checkVersion(true); });
  addEventListener('hashchange', () => setTimeout(updateWhenSafe, 300));  // a pending version is taken on the next resting page
  setTimeout(() => checkVersion(true), 4000);  // once after opening (the page itself may have come from the cache), off the first screen's way

  // ---- 深色/浅色: an iPhone paints the strip under the status bar from the page when it loads and keeps it. A home-screen
  // app left open while the phone turns dark (or light) keeps a light strip on the dark page — a white band — until the
  // page loads again; going home and back does not change it, nor does a new theme-color (tools/ios_sim_check.py,
  // 2026-11-25). So a change of scheme is taken like a new version: a reload at once on a resting page, else on the next.
  if (navigator.standalone === true && window.matchMedia) {
    let schemeStale = false;
    const takeScheme = () => { if (schemeStale && restingNow()) { schemeStale = false; location.reload(); } };
    const mq = matchMedia('(prefers-color-scheme: dark)');
    const changed = () => { schemeStale = true; setTimeout(takeScheme, 300); };
    if (mq.addEventListener) mq.addEventListener('change', changed); else if (mq.addListener) mq.addListener(changed);
    document.addEventListener('visibilitychange', () => setTimeout(takeScheme, 300));
    addEventListener('hashchange', () => setTimeout(takeScheme, 300));
  }
  /* ---------- data: pages that show at once, preloading, one request per page at a time ---------- */
  // Three layers, so a page appears without waiting and the next one is often ready before it is tapped:
  // - In memory: GET answers are shared and kept two minutes (the site's lists of levels and goals a day), and a
  //   request in flight is shared too, so a page and a preload of it never fetch twice. Anything sent (a POST) may
  //   change them, so it empties this memory.
  // - On the phone (localStorage): the last 今日 and the last five materials, per account. The next visit draws the
  //   page from them at once while the fresh data loads, and draws it again, quietly, if anything changed. Signing
  //   out clears them; the session's CSRF token is never kept there (sending waits for the server's answer instead).
  // - Preloading: once the first page is on screen and the phone is idle, the data of the other tabs; when a finger
  //   touches a link, the data of the page it leads to. Nothing that changes data is preloaded (the review queue
  //   brings in today's new words, so it is fetched only on a touch of 复习). Not with Save-Data or on 2G, except on
  //   a touch: that page was asked for.
  const DATA = { mem: new Map(), ok: null, ready: null, fromSnap: false };
  DATA.ready = new Promise(ok => { DATA.ok = ok; });
  const KEEP_MS = [[/^\/api\/next\/meta$/, 864e5], [/./, 12e4]];
  const parseJSON = t => { try { return t ? JSON.parse(t) : {}; } catch (e) { return {}; } };
  function dataGet(path, quiet) {
    const now = Date.now(), e = DATA.mem.get(path);
    if (e && now - e.at < KEEP_MS.find(([re]) => re.test(path))[1]) return e.p.then(parseJSON);
    const p = request(path, undefined, quiet).then(x => x.t);
    DATA.mem.set(path, { at: now, p });
    p.catch(() => { const x = DATA.mem.get(path); if (x && x.p === p) DATA.mem.delete(path); });
    return p.then(parseJSON);
  }
  function dataForget() { for (const k of [...DATA.mem.keys()]) if (!/^\/api\/next\/meta$/.test(k)) DATA.mem.delete(k); }
  function prefetch(path) { if (path) dataGet(path, true).catch(() => {}); }
  const materialPath = id => '/api/next/material?id=' + encodeURIComponent(id) + (S.user ? '' : '&level=' + encodeURIComponent(level()));
  function libraryPath(f) {
    if (!f) { try { f = JSON.parse(sessionStorage.getItem('flow-next-lib') || 'null'); } catch (e) { f = null; } }
    f = f || { level: hasProfile() ? level() : '', theme: '', page: 1, featured: '1' };
    return `/api/next/library?level=${f.level}&theme=${f.theme}&page=${f.page}&featured=${f.featured}`;
  }

  // ---- the copy kept on the phone
  const SNAP = 'flow-snap';
  const snapOwner = () => (S.user ? 'u' + S.user.id : 'guest');
  function snapGet() { const s = load(SNAP); return s && s.v === 1 ? s : null; }
  function snapPut(fn) {
    try {
      const old = snapGet(), s = old && old.owner === snapOwner() ? old : { v: 1, owner: snapOwner(), mats: {} };
      fn(s); save(SNAP, s);
    } catch (e) { /* full or private mode: the next visit simply waits for the server */ }
  }
  function snapHome() {
    // S.home without the session's CSRF token (sending waits for the server's own answer)
    const h = JSON.parse(JSON.stringify(S.home || {}));
    if (h.session && h.session.user) delete h.session.user.csrf;
    snapPut(s => { s.home = h; s.at = Date.now(); });
  }
  function snapMaterial(path, m) {
    snapPut(s => {
      s.mats[path] = { at: Date.now(), m };
      Object.keys(s.mats).sort((a, b) => s.mats[b].at - s.mats[a].at).slice(5).forEach(k => delete s.mats[k]);
    });
  }
  function snapMaterialGet(path) { const s = snapGet(); return s && s.owner === snapOwner() && s.mats[path] ? s.mats[path].m : null; }
  // Signing out (and 注销账号): the account's copies on this phone go, with the review queue kept for offline review and
  // anything still waiting to be sent (the sign-out sends it first while there is a connection: OUTBOX.flush), so the
  // next person on a shared phone sees none of it and none of it is sent into their account.
  function snapClear() {
    save(SNAP, null); DATA.mem.clear(); OFF.clear(); draftClearAll();  // half-written texts too (08-drafts.js)
    try { localStorage.removeItem('flow-next-review-cache'); localStorage.removeItem('flow-next-outbox'); } catch (e) { /* private mode */ }
  }

  // ---- preloading
  const idle = f => (window.requestIdleCallback ? requestIdleCallback(f, { timeout: 2500 }) : setTimeout(f, 900));
  function prefetchTabs() {
    if (PRELOAD.frugal()) return;
    idle(() => {
      if (S.user) { prefetch('/api/next/vocab'); prefetch('/api/next/cards?q=&page=1&f='); prefetch('/api/next/radar'); }
      if (!S.meta) prefetch('/api/next/meta');
      prefetch(libraryPath());
    });
  }
  // A link's page, and the data it will ask for first: fetched while the finger is still on the screen.
  const ROUTE_DATA = [
    [/^#\/m\/([^/?]+)/, m => [materialPath(decodeURIComponent(m[1]))]],
    [/^#\/cards\/?$/, () => (S.user ? ['/api/next/vocab', '/api/next/cards?q=&page=1&f='] : [])],
    [/^#\/review$/, () => (S.user ? ['/api/next/review'] : [])],
    [/^#\/library$/, () => [libraryPath()]],
    [/^#\/practice$/, () => (S.user ? ['/api/next/radar'] : [])],
    [/^#\/me$/, () => (S.meta ? [] : ['/api/next/meta'])],
    [/^#\/graph$/, () => ['/api/next/graph' + guestQuery(true)]],
    [/^#\/growth$/, () => (S.user ? ['/api/next/growth'] : [])],
    [/^#\/report$/, () => (S.user ? ['/api/next/report'] : [])],
    [/^#\/series\/([^/?]+)/, m => ['/api/next/series?id=' + encodeURIComponent(decodeURIComponent(m[1]))]],
  ];
  function prefetchFor(hash) {
    for (const [re, f] of ROUTE_DATA) { const m = hash.match(re); if (m) { f(m).forEach(prefetch); return; } }
  }
  addEventListener('pointerdown', e => {
    const a = e.target && e.target.closest && e.target.closest('a[href^="#/"]');
    if (a) prefetchFor(a.getAttribute('href'));
  }, { capture: true, passive: true });
  /* ---------- 存到手机: materials kept on the phone, to study without a connection ---------- */
  // Today's article and the next two are kept by themselves (when the phone is idle; not with Save-Data or on 2G), any
  // other with 「存到手机」 on its page; ten at most, per account. A kept material has its text, its questions with the
  // answers (graded on the phone without a connection) and its narration (kept by the service worker). What is done
  // offline (steps, answers) waits in the outbox and is sent when the phone is back online, so progress and the
  // mistake book are recorded as usual.
  const OFF = {
    key: 'flow-offline', max: 10,
    all() { const s = load(this.key); return s && s.v === 1 && s.owner === snapOwner() ? s : { v: 1, owner: snapOwner(), mats: {} }; },
    get(id) { const s = this.all(); return s.mats[id] ? s.mats[id].m : null; },
    has(id) { return !!this.all().mats[id]; },
    count() { return Object.keys(this.all().mats).length; },
    list() { const s = this.all(); return Object.keys(s.mats).map(id => s.mats[id].m).filter(Boolean); },
    put(id, m) {
      const s = this.all(); s.mats[id] = { at: Date.now(), m };
      Object.keys(s.mats).sort((a, b) => s.mats[b].at - s.mats[a].at).slice(this.max).forEach(k => delete s.mats[k]);
      try { save(this.key, s); } catch (e) { /* full: the oldest stays out */ }
    },
    clear() { save(this.key, null); },
  };
  async function keepOffline(id, quiet) {
    try {
      const m = await dataGet(materialPath(id) + '&offline=1', quiet);
      OFF.put(id, m);
      if (MAT[id] && !MAT[id].answers) MAT[id].answers = m.answers;  // the page open now can grade offline too
      const vs = (m.audio && m.audio.voices) || [], sw = navigator.serviceWorker && navigator.serviceWorker.controller;
      if (vs.length && sw) {  // the narration and its timings, kept by the service worker like any audio it has served
        const base = `/audio/${vs.includes(S.voice) ? S.voice : vs[0]}/${encodeURIComponent(id)}`;
        sw.postMessage({ type: 'prefetch', urls: [`${base}.json?v=${m.audio.version}`, `${base}.mp4?v=${m.audio.version}`] });
      }
      if (!quiet) toast('已存到本机，没网也能学');  // the chip itself is short now, so the toast says what it means
      return true;
    } catch (e) { if (!quiet) toast(e.network ? '现在没网，存不了' : e.message); return false; }
  }
  function keepTodayOffline() {
    if (PRELOAD.frugal() || !S.home) return;
    const h = S.home, ids = [], read = h.path && h.path.steps && h.path.steps.find(s => s.key === 'read');
    if (read) ids.push(decodeURIComponent(read.href.split('/')[2] || ''));
    (h.today || []).forEach(m => ids.push(m.id));
    idle(() => [...new Set(ids)].filter(Boolean).slice(0, 3).forEach(id => { if (!OFF.has(id)) keepOffline(id, true); }));
  }
  // On a material's page: 存到手机, or that it is kept.
  function offChip(id) {
    // a phone with a down arrow in front, at the right of the kicker line (the full meaning is in the title and the toast)
    const icon = '<svg class="offi" viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="2.5" width="12" height="19" rx="2.5"/><path d="M12 7.5v7m-3-3 3 3 3-3"/></svg>';
    return OFF.has(id) ? '<span class="offk on" id="keepOff" title="没网也能学">✓ 已存到本机</span>' : `<button class="link small offk" id="keepOff" type="button" data-tap="study-keep" title="存到本机，没网也能学">${icon}存到本机</button>`;
  }
  function bindOffChip(id) {
    const b = document.getElementById('keepOff'); if (!b || b.tagName !== 'BUTTON') return;
    b.onclick = async () => { b.disabled = true; b.textContent = '正在存…'; const ok = await keepOffline(id); b.outerHTML = offChip(id); if (!ok) bindOffChip(id); };
  }
  // Losing and finding the connection: said once each way; what waited is sent.
  addEventListener('offline', () => { const n = OFF.count(); toast(n ? `现在没网：已存到本机的 ${n} 篇还能学` : '现在没网：复习单词还能做，联网后自动同步'); });
  addEventListener('online', () => { OUTBOX.flush(); });  // it says how much was synced
  /* ---------- 主题色 (我的 → 使用习惯): 松绿 (配色 A, the default) or 靛蓝; only the accent changes (99-accent.css) ---------- */
  // Signed in, it is kept with the account (/api/next/accent → profile.accent) and follows to another device; before
  // signing in, on this device. The device also keeps the last one, so the first screen is already drawn in it.
  // Right / wrong, the logo and the AI marks do not change with it (--ok, --red, --brand in 00-base.css).
  const ACCENTS = [['green', '松绿'], ['indigo', '靛蓝']];
  function applyAccent(a) {
    a = ACCENTS.some(x => x[0] === a) ? a : 'green';
    if (a === 'green') document.documentElement.removeAttribute('data-accent'); else document.documentElement.dataset.accent = a;
    save('flow-accent', a === 'green' ? null : a);
    return a;
  }
  applyAccent(load('flow-accent'));
  // The account's choice when the home data comes (refreshHome, 02-shell.js). One made on this device before signing in
  // goes to the account first, once, so signing in does not undo it.
  function accentFromAccount(p) {
    const g = load('flow-accent-guest');
    if (g) {
      save('flow-accent-guest', null);
      if (g !== (p.accent || 'green')) { p.accent = g; api('/api/next/accent', { accent: g }).catch(() => { /* the device keeps it */ }); }
    }
    applyAccent(p.accent);
  }
  const accentNow = () => document.documentElement.dataset.accent || 'green';
  const accentLabel = () => ACCENTS.find(x => x[0] === accentNow())[1];
  async function setAccent(a) {
    const was = accentNow(); applyAccent(a);
    if (!S.user) { save('flow-accent-guest', a); return; }  // chosen before signing in: given to the account once (below)
    try { await api('/api/next/accent', { accent: a }); if (S.home && S.home.profile) S.home.profile.accent = a; }
    catch (e) { applyAccent(was); toast(e.message); }
  }
  /* ---------- 界面语言: 中文 | English (我的 → 使用习惯, on its title row; 全英文界面, 语流 E1) ---------- */
  // Kept like 主题色 (07-accent.js): signed in, with the account (/api/next/lang → profile.lang), so another phone or
  // computer opens in it too; before signing in, on this device, handed to the account once after signing in. The
  // device keeps its own copy (flow-lang), read before the first page is drawn (uiLang(), 00-i18n.js).
  // Switching reloads the page once, on the same page, with this device's copies of 今日 and the texts cleared (they
  // hold the server's words). The two halves of the switch are each written in their own language, and what is said
  // around it in both, so a learner who opened English by mistake can always find the way back; for 10 s after the
  // switch a line offers to undo it. Going to English first says what changes (word meanings stay in Chinese) and, at
  // 入门 or before the level is known, that B1 is a better time for it. Chinese is never chosen for the learner.
  const LANG_UNDO_MS = 10000;
  function langSwitchHTML() {
    if (!uiLangOpen()) return '';
    const cur = uiLang();
    // the look of 列表 | 卡片 and 简 | 详 (.vt, 30-words.css; B9)
    return /* i18n: keep (each half in its own language) */ `<div class="vt lang-seg" role="radiogroup" aria-label="界面语言 Language" translate="no">${[['zh', '中文', 'zh-CN'], ['en', 'English', 'en']].map(([v, l, lg]) =>
      `<button type="button" role="radio" data-lang="${v}" lang="${lg}" class="${v === cur ? 'on' : ''}" aria-checked="${v === cur}">${l}</button>`).join('')}</div>`;
  }
  function langSwitchWire(root) {
    (root || document).querySelectorAll('.lang-seg [data-lang]').forEach(b => b.onclick = () => {
      if (b.getAttribute('aria-checked') === 'true') return;
      if (b.dataset.lang === 'en') langAskEnglish(); else setLang('zh');
    });
  }
  // Before English: what changes, in both languages, and a word for learners at 入门
  function langAskEnglish() {
    const lv = S.home && S.home.profile ? S.home.profile.level : (S.guest && S.guest.level) || '';
    const early = !lv || lv === 'A2';
    openSheet(/* i18n: keep (both languages) */ `<div class="stack" translate="no"><h2 class="h2" id="sheetTitle"><span lang="zh-CN">换成英文界面</span>&nbsp;·&nbsp;<span lang="en">Switch to English</span></h2>
      <p lang="zh-CN">按钮、标题和说明都会换成英文，AI 也用英文讲解（每段讲解下面能看中文）。单词的中文意思还在。随时可以在「我的 → 使用习惯」换回中文。</p>
      <p class="small muted" lang="en">Buttons, titles and instructions will be in English, and the AI will explain in English (with Chinese one tap away). Chinese word meanings stay. Switch back any time in Me → Preferences.</p>
      ${early ? /* i18n: keep */ `<p class="small" lang="zh-CN">你现在是入门水平，建议到中级（B1）再换。</p><p class="small muted" lang="en">At this level, Chinese may still be easier. B1 (intermediate) is a good time to switch.</p>` : ''}
      <button class="btn primary" type="button" id="langGo"><span lang="zh-CN">换成英文</span>&nbsp;·&nbsp;<span lang="en">Switch</span></button>
      <button class="btn ghost" type="button" data-close><span lang="zh-CN">取消</span>&nbsp;·&nbsp;<span lang="en">Cancel</span></button></div>`, card => {
      card.querySelector('#langGo').onclick = () => setLang('en');
    });
  }
  async function setLang(l, undoing) {
    l = l === 'en' ? 'en' : 'zh';
    const was = uiLang();
    if (l === was) return;
    if (S.user) {
      let r = null;
      try { r = await api('/api/next/lang', { lang: l }); } catch (e) { toast(e.message); return; }  // nothing changes here either
      if (r && r.kept === false) save('flow-lang-guest', l);  // no 学习目标 yet: handed to the account once there is one
    } else save('flow-lang-guest', l);
    save('flow-lang', l === 'en' ? 'en' : null);
    save('flow-lang-undo', undoing ? null : { from: was, at: Date.now() });
    langReload();
  }
  function langReload() {
    save(SNAP, null); DATA.mem.clear();  // 今日 and the texts kept on the device were written in the other language
    location.reload();
  }
  // With the profile (refreshHome, 02-shell.js): a choice made here before signing in goes to the account, once; else
  // the account's choice, made on another phone or computer, is followed (once per page: never a loop of reloads).
  function langFromAccount(p) {
    if (!uiLangOpen()) return;
    const g = load('flow-lang-guest');
    if (g) {
      save('flow-lang-guest', null);
      if (g !== (p.lang || 'zh')) {
        p.lang = g;
        api('/api/next/lang', { lang: g }).then(r => { if (r && r.kept === false) save('flow-lang-guest', g); }).catch(() => save('flow-lang-guest', g));
      }
      return;
    }
    const want = p.lang === 'en' ? 'en' : 'zh';
    if (want === uiLang() || langFromAccount.done) return;
    langFromAccount.done = true;
    save('flow-lang', want === 'en' ? 'en' : null);
    if ((load('flow-lang') === 'en') === (want === 'en')) langReload();  // only when this device could keep it
  }
  // Just switched: 10 s to take it back, said in both languages
  (function langUndoLine() {
    const u = load('flow-lang-undo');
    if (!u) return;
    save('flow-lang-undo', null);
    if (!(Date.now() - u.at < 30000) || !uiLangOpen()) return;
    const en = uiLang() === 'en';
    const el = document.createElement('div');
    el.className = 'easy-bar lang-undo'; el.setAttribute('role', 'status'); el.setAttribute('translate', 'no');  // the look of 复习's 太简单 · 撤销
    el.innerHTML = /* i18n: keep */ (en ? '<span lang="en">Now in English</span><span lang="zh-CN">已换成英文</span>' : '<span lang="zh-CN">已换成中文</span><span lang="en">Now in Chinese</span>')
      + /* i18n: keep */ `<button type="button" class="link small">${en ? '<span lang="en">Undo</span>&nbsp;·&nbsp;<span lang="zh-CN">撤销</span>' : '<span lang="zh-CN">撤销</span>&nbsp;·&nbsp;<span lang="en">Undo</span>'}</button>`;
    el.querySelector('button').onclick = () => { el.remove(); setLang(u.from, true); };
    document.body.appendChild(el);
    setTimeout(() => el.remove(), LANG_UNDO_MS);
  })();
  /* ---------- 使用习惯 kept with the account (我的 → 使用习惯, the user and B9, 2026-11-26) ---------- */
  // The pages read this device's copy (KNOW in 50-words.js, TEXT in 02-shell.js), so they draw at once and offline.
  // Signed in, each choice is also kept with the account (/api/next/prefs → profile.prefs, next_service.PREFS), and
  // another phone or computer takes it from there. 主题色 is kept the same way by 07-accent.js; 今日的样子 by 10-*.js.
  const PREF_IO = {
    // the value on this device, or null when nothing was chosen here (the page's default); put(v) writes it here only
    know: { get: () => { try { return localStorage.getItem('flow-know-side') === 'left' ? 'left' : null; } catch (e) { return null; } },
            put: v => { try { if (v === 'left') localStorage.setItem('flow-know-side', 'left'); else localStorage.removeItem('flow-know-side'); } catch (e) { /* private mode */ } } },
    card_new: { get: () => { try { return localStorage.getItem('flow-card-view-new'); } catch (e) { return null; } },
                put: v => { try { localStorage.setItem('flow-card-view-new', v); } catch (e) { /* private mode */ } } },
    card_review: { get: () => { try { return localStorage.getItem('flow-card-view-review'); } catch (e) { return null; } },
                   put: v => { try { localStorage.setItem('flow-card-view-review', v); } catch (e) { /* private mode */ } } },
    tap: { get: () => { try { const v = localStorage.getItem('flow-tap-zones'); return v ? (v === '1' ? 'on' : 'off') : null; } catch (e) { return null; } },
           put: v => { try { localStorage.setItem('flow-tap-zones', v === 'on' ? '1' : '0'); } catch (e) { /* private mode */ } } },
    size: { get: () => (load('flow-next-text') || {}).size || null, put: v => { TEXT.size = v; save('flow-next-text', TEXT); } },
    lh: { get: () => (load('flow-next-text') || {}).lh || null, put: v => { TEXT.lh = v; save('flow-next-text', TEXT); } },
  };
  // one choice made on this device: kept with the account too (a guest: here only, handed over after signing in)
  function prefSave(key, value) {
    if (S.user && S.home && S.home.profile) {
      S.home.profile.prefs = Object.assign({}, S.home.profile.prefs, { [key]: value });
      api('/api/next/prefs', { [key]: value }).catch(() => { /* this device keeps it; the next sign-in hands it over */ });
    }
  }
  // signed in (02-shell.js, with the profile): what the account keeps comes to this device; what was chosen here and the
  // account does not have yet (before signing in, or before 2026-11-26 when these were kept on the device only) goes to it
  function prefsFromAccount(p) {
    const kept = p.prefs || {}, mine = {};
    Object.keys(PREF_IO).forEach(k => {
      const io = PREF_IO[k], here = io.get();
      if (kept[k] != null) { if (here !== kept[k]) io.put(kept[k]); }
      else if (here != null) mine[k] = here;
    });
    if (Object.keys(mine).length) { p.prefs = Object.assign({}, kept, mine); api('/api/next/prefs', mine).catch(() => {}); }
    applyText();
  }
  /* ---------- QR codes (byte mode, error correction M, versions 1–6): the 分享卡片's way back to the site ---------- */
  // Written out here rather than loaded from elsewhere (the page loads nothing from other sites). tools/ui_test.py reads
  // the codes back with the browser's own BarcodeDetector where it has one. Up to 106 bytes: plenty for a link.
  const QR = (() => {
    const BLOCKS = [null, [10, 1, 16], [16, 1, 28], [26, 1, 44], [18, 2, 32], [24, 2, 43], [16, 4, 27]];  // [ECC per block, blocks, data per block]
    const ALIGN = [null, [], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34]];
    const EXP = new Array(512), LOG = new Array(256);  // GF(256) with x^8 + x^4 + x^3 + x^2 + 1
    for (let i = 0, x = 1; i < 255; i++) { EXP[i] = x; LOG[x] = i; x <<= 1; if (x & 256) x ^= 0x11d; }
    for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
    const mul = (a, b) => (a && b ? EXP[LOG[a] + LOG[b]] : 0);
    function ecc(data, n) {  // Reed–Solomon: the remainder of data·x^n divided by the generator of degree n
      let g = [1];
      for (let i = 0; i < n; i++) { const ng = new Array(g.length + 1).fill(0); g.forEach((v, j) => { ng[j] ^= v; ng[j + 1] ^= mul(v, EXP[i]); }); g = ng; }
      const r = data.concat(new Array(n).fill(0));
      for (let i = 0; i < data.length; i++) { const f = r[i]; if (f) g.forEach((v, j) => { r[i + j] ^= mul(v, f); }); }
      return r.slice(data.length);
    }
    function codewords(bytes, ver) {
      const [ecN, blocks, per] = BLOCKS[ver], cap = blocks * per, bits = [];
      const put = (v, n) => { for (let i = n - 1; i >= 0; i--) bits.push((v >> i) & 1); };
      put(4, 4); put(bytes.length, 8); bytes.forEach(b => put(b, 8));
      put(0, Math.min(4, cap * 8 - bits.length));
      while (bits.length % 8) bits.push(0);
      const data = [];
      for (let i = 0; i < bits.length; i += 8) data.push(bits.slice(i, i + 8).reduce((a, b) => a * 2 + b, 0));
      for (let p = 0; data.length < cap; p++) data.push(p % 2 ? 0x11 : 0xec);
      const ds = [], es = [];
      for (let b = 0; b < blocks; b++) { const d = data.slice(b * per, (b + 1) * per); ds.push(d); es.push(ecc(d, ecN)); }
      const out = [];
      for (let i = 0; i < per; i++) ds.forEach(d => out.push(d[i]));
      for (let i = 0; i < ecN; i++) es.forEach(e => out.push(e[i]));
      return out;
    }
    const MASKS = [(r, c) => (r + c) % 2 === 0, r => r % 2 === 0, (r, c) => c % 3 === 0, (r, c) => (r + c) % 3 === 0,
      (r, c) => (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0, (r, c) => ((r * c) % 2) + ((r * c) % 3) === 0,
      (r, c) => (((r * c) % 2) + ((r * c) % 3)) % 2 === 0, (r, c) => (((r + c) % 2) + ((r * c) % 3)) % 2 === 0];
    function penalty(m) {  // the standard's four rules; a lower score scans more easily (any mask is valid)
      const n = m.length; let s = 0, dark = 0;
      const line = get => { let run = 1; for (let i = 1; i < n; i++) { if (get(i) === get(i - 1)) { run++; if (run === 5) s += 3; else if (run > 5) s++; } else run = 1; } };
      for (let i = 0; i < n; i++) { line(j => m[i][j]); line(j => m[j][i]); }
      for (let r = 0; r < n - 1; r++) for (let c = 0; c < n - 1; c++) { const v = m[r][c]; if (v === m[r][c + 1] && v === m[r + 1][c] && v === m[r + 1][c + 1]) s += 3; }
      const pat = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0], rev = pat.slice().reverse();
      const at = (get, i, p) => p.every((b, k) => (get(i + k) ? 1 : 0) === b);
      for (let i = 0; i < n; i++) for (let j = 0; j + 11 <= n; j++) {
        const row = k => m[i][k], col = k => m[k][i];
        if (at(row, j, pat) || at(row, j, rev)) s += 40;
        if (at(col, j, pat) || at(col, j, rev)) s += 40;
      }
      m.forEach(r => r.forEach(v => { if (v) dark++; }));
      return s + 10 * Math.max(0, Math.ceil(Math.abs(dark * 20 - n * n * 10) / (n * n)) - 1);
    }
    function matrix(text) {
      const bytes = Array.from(new TextEncoder().encode(text));
      let ver = 1;
      while (ver <= 6 && bytes.length > BLOCKS[ver][1] * BLOCKS[ver][2] - 2) ver++;
      if (ver > 6) throw new Error('link too long for the QR code');
      const n = 17 + 4 * ver, M = [...Array(n)].map(() => new Array(n).fill(false)), fn = [...Array(n)].map(() => new Array(n).fill(false));
      const set = (r, c, v) => { M[r][c] = v; fn[r][c] = true; };
      for (const [r0, c0] of [[0, 0], [0, n - 7], [n - 7, 0]]) {  // finders, with their light separators
        for (let r = -1; r <= 7; r++) for (let c = -1; c <= 7; c++) {
          const rr = r0 + r, cc = c0 + c; if (rr < 0 || cc < 0 || rr >= n || cc >= n) continue;
          set(rr, cc, r >= 0 && r <= 6 && c >= 0 && c <= 6 && (r === 0 || r === 6 || c === 0 || c === 6 || (r >= 2 && r <= 4 && c >= 2 && c <= 4)));
        }
      }
      for (let i = 8; i < n - 8; i++) { set(6, i, i % 2 === 0); set(i, 6, i % 2 === 0); }  // timing
      const al = ALIGN[ver], last = al[al.length - 1];
      for (const r of al) for (const c of al) {
        if ((r === 6 && c === 6) || (r === 6 && c === last) || (r === last && c === 6)) continue;
        for (let dr = -2; dr <= 2; dr++) for (let dc = -2; dc <= 2; dc++) set(r + dr, c + dc, Math.max(Math.abs(dr), Math.abs(dc)) !== 1);
      }
      set(n - 8, 8, true);  // the dark module
      for (let i = 0; i < 9; i++) { if (!fn[8][i]) set(8, i, false); if (!fn[i][8]) set(i, 8, false); }  // format areas, filled later
      for (let i = 0; i < 8; i++) { if (!fn[8][n - 1 - i]) set(8, n - 1 - i, false); if (!fn[n - 1 - i][8]) set(n - 1 - i, 8, false); }
      const bits = []; codewords(bytes, ver).forEach(b => { for (let i = 7; i >= 0; i--) bits.push((b >> i) & 1); });
      let k = 0;
      for (let right = n - 1; right >= 1; right -= 2) {  // two columns at a time, up then down, from the bottom right
        if (right === 6) right = 5;
        for (let v = 0; v < n; v++) for (let j = 0; j < 2; j++) {
          const c = right - j, r = ((right + 1) & 2) === 0 ? n - 1 - v : v;
          if (!fn[r][c]) { M[r][c] = k < bits.length && bits[k] === 1; k++; }
        }
      }
      let best = null;
      for (let mask = 0; mask < 8; mask++) {
        const m = M.map((row, r) => row.map((v, c) => (fn[r][c] ? v : v !== MASKS[mask](r, c))));
        const data = mask;  // level M is 00
        let rem = data; for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >> 9) * 0x537);
        const f = ((data << 10) | rem) ^ 0x5412, bit = i => ((f >> i) & 1) === 1;
        for (let i = 0; i <= 5; i++) m[i][8] = bit(i);
        m[7][8] = bit(6); m[8][8] = bit(7); m[8][7] = bit(8);
        for (let i = 9; i < 15; i++) m[8][14 - i] = bit(i);
        for (let i = 0; i < 8; i++) m[8][n - 1 - i] = bit(i);
        for (let i = 8; i < 15; i++) m[n - 15 + i][8] = bit(i);
        m[n - 8][8] = true;
        const score = penalty(m);
        if (!best || score < best.score) best = { m, score };
      }
      return best.m;
    }
    // Drawn dark on light at x, y, size px across, with the quiet zone (4 modules) inside that size.
    function draw(g, text, x, y, size, dark = '#13261b', light = '#ffffff') {
      // whole pixels per module, the code centred in the box: no seams between modules
      const m = matrix(text), u = Math.max(1, Math.floor(size / (m.length + 8))), o = Math.round((size - u * m.length) / 2);
      g.fillStyle = light; g.fillRect(x, y, size, size); g.fillStyle = dark;
      m.forEach((row, r) => row.forEach((v, c) => { if (v) g.fillRect(x + o + c * u, y + o + r * u, u, u); }));
    }
    return { matrix, draw };
  })();
  /* ---------- drafts: what a learner wrote is still there after leaving the page ---------- */
  // A writing box with data-draft="<key>" keeps its text on this device while it is typed, and gets it back when the
  // box is drawn again (a tab tapped, a back swipe, the app closed), with a line under it: 「已恢复上次没写完的内容」 and
  // 「清空」 (which can be undone for a few seconds). The page calls draftDone(key) once what was written has been sent.
  // A draft belongs to the account that wrote it and is only given back to it (one written before signing in goes to
  // whoever signs in: write first, then 「登录后 AI 会…」);
  // signing out clears every draft on the device (snapClear, 05-data.js), so the next person on a shared computer
  // finds none. A draft not touched for 14 days is dropped. The essay and the model sentence (24-study-output.js) keep
  // their own drafts as before; signing out clears those too.
  const DRAFT_PRE = 'flow-next-draft-box-', DRAFT_DAYS = 14;
  const draftSlot = k => DRAFT_PRE + k;
  const draftHash = s => { let h = 5381; for (const ch of String(s)) h = (h * 33 + ch.charCodeAt(0)) >>> 0; return h.toString(36); };  // a key for a long question
  const draftNotes = k => document.querySelectorAll(`.draft-note[data-for="${CSS.escape(k)}"]`);
  function draftDone(k) { save(draftSlot(k), null); draftNotes(k).forEach(n => n.remove()); }
  function draftClearAll() {
    try { Object.keys(localStorage).filter(k => k.startsWith('flow-next-draft-') || k.startsWith('flow-next-essay-')).forEach(k => localStorage.removeItem(k)); } catch (e) { /* private mode */ }
  }
  document.addEventListener('input', e => {
    const t = e.target;
    if (!t || !t.dataset || !t.dataset.draft) return;
    save(draftSlot(t.dataset.draft), t.value.trim() ? { v: t.value, at: Date.now(), who: snapOwner() } : null);
  });
  // Fill a new box from its draft, unless its page has already put text in it. An input event follows, so the
  // page's own counter ("0 / 1000", "12 词") and checks see the text as if it had been typed.
  function draftFill(t) {
    if (t.value || t.dataset.draftFilled) return;
    t.dataset.draftFilled = '1';
    const k = t.dataset.draft, d = load(draftSlot(k));
    if (!d || !d.v) return;
    // written by someone else on this device: never shown (written before signing in: given to the account signed in now)
    if ((d.who !== snapOwner() && d.who !== 'guest') || Date.now() - (d.at || 0) > DRAFT_DAYS * 864e5) { save(draftSlot(k), null); return; }
    t.value = d.v;
    t.dispatchEvent(new Event('input', { bubbles: true }));
    const note = document.createElement('p');
    note.className = 'draft-note tiny muted'; note.dataset.for = k; note.setAttribute('role', 'status');
    const say = (msg, btn, act) => { note.innerHTML = `<span>${msg}</span><button type="button" class="link small">${btn}</button>`; note.querySelector('button').onclick = act; };
    const gone = () => note.remove();  // typing again after 清空: the undo is no longer offered
    const restored = () => say('已恢复上次没写完的内容', '清空', () => {
      const was = t.value;
      t.value = ''; t.dispatchEvent(new Event('input', { bubbles: true }));
      t.addEventListener('input', gone, { once: true });
      say('已清空', '撤销', () => { t.removeEventListener('input', gone); t.value = was; t.dispatchEvent(new Event('input', { bubbles: true })); restored(); });
      clearTimeout(note.t); note.t = setTimeout(() => { if (!t.value) gone(); }, 6000);
      if (!TOUCH) t.focus();
    });
    restored();
    t.insertAdjacentElement('afterend', note);
  }
  new MutationObserver(ms => {
    for (const m of ms) for (const n of m.addedNodes) {
      if (n.nodeType !== 1) continue;
      if (n.matches('textarea[data-draft]')) draftFill(n);
      else if (n.firstElementChild) n.querySelectorAll('textarea[data-draft]').forEach(draftFill);
    }
  }).observe(document.body, { childList: true, subtree: true });
  (function draftSweep() {  // old drafts, once per start
    try {
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const k = localStorage.key(i);
        if (!k || !k.startsWith(DRAFT_PRE)) continue;
        const d = load(k);
        if (!d || Date.now() - (d.at || 0) > DRAFT_DAYS * 864e5) localStorage.removeItem(k);
      }
    } catch (e) { /* private mode */ }
  })();
  /* ---------- 新手引导 v2 (the user, 2026-11-26: 「把初次使用的引导做完善，动画流畅、好看、讲得详细」, 「视觉压力小」;
     19:5x 「现在先做」): one step at a time over the whole screen. A new learner starts with 欢迎, 学英语为了什么 (more than
     one) and 想到什么水平 (these save the profile, as the one-page form under it would); then one step per place of the
     app, in the order of the tab bar, a small copy of which sits where the real one is and walks along with the steps.
     跳过 at any time (during the first three the one-page form is under it); closed half way, the next opening goes on
     from that step (this browser); once per account (tour_service: the learner tour; a guest: this browser); 我的 → 帮助
     plays the places again. Only transform and opacity move; with the system's 「减少动态效果」 nothing moves. ---------- */
  // The pictures (B9, 2026-11-26): the real page made very simple, a few shapes, no words; the part meant in a thicker ink
  // line (the accent is the button's only, 08-intro.css). `ip` parts come in one after another (d1…d4).
  const INTRO_ART = {
    tabs: `<svg viewBox="0 0 280 200"><rect class="fr ip" x="70" y="4" width="140" height="192" rx="22"/>
      <rect class="bar ip d1" x="86" y="22" width="108" height="40" rx="12"/><path class="lns ip d2" d="M90 82h92M90 102h70M90 122h84"/>
      <g class="ip d3"><rect class="hl" x="80" y="152" width="120" height="32" rx="12"/>${[98, 119, 140, 161, 182].map(x => `<circle class="dot" cx="${x}" cy="168" r="4"/>`).join('')}</g></svg>`,
    practice: `<svg viewBox="0 0 280 200"><rect class="hl ip" x="40" y="6" width="200" height="46" rx="14"/><path class="lns ip d1" d="M58 24h70M58 38h46"/>
      <rect class="btn ip d1" x="40" y="60" width="200" height="22" rx="11"/>
      <g class="ip d2"><rect class="fr" x="40" y="94" width="96" height="100" rx="14"/><path class="lns" d="M56 116h48M56 140h60M56 164h40"/></g>
      <g class="ip d3"><rect class="fr" x="144" y="94" width="96" height="100" rx="14"/><path class="lns" d="M160 116h56M160 140h44M160 164h52"/></g></svg>`,
    exam: `<svg viewBox="0 0 280 200"><g class="ip"><rect class="fr" x="40" y="4" width="200" height="58" rx="14"/><path class="lns" d="M58 22h64"/><rect class="btn" x="56" y="36" width="168" height="16" rx="8"/></g>
      <g class="ip d1"><rect class="fr" x="40" y="72" width="200" height="124" rx="16"/><path class="lns" d="M58 92h96M58 168h80M58 186h60"/></g>
      <g class="ip d2 open"><rect class="hl" x="48" y="106" width="184" height="46" rx="12"/><path class="lns" d="M64 122h72M64 138h112"/></g></svg>`,
    radar: `<svg viewBox="0 0 280 200"><path class="fr ip" d="M140 18 200.6 53v70L140 158 79.4 123V53z"/>
      <path class="axis ip d1" d="M140 88V18M140 88l60.6-35M140 88l60.6 35M140 88v70M140 88l-60.6 35M140 88 79.4 53"/>
      <path class="hl grow-in ip d2" d="M140 49.5 188.5 60 176.4 109 140 137 112.7 103.8 100.6 65.3z"/>
      <rect class="btn ip d3" x="60" y="172" width="160" height="22" rx="11"/></svg>`,
    words: left => `<svg viewBox="0 0 280 200"><g class="ip"><rect class="fr" x="20" y="14" width="120" height="122" rx="16"/><path class="lns" d="M36 38h52M36 66h80M36 90h64"/><rect class="btn" x="36" y="108" width="88" height="16" rx="8"/></g>
      <g class="ip d1"><rect class="bar" x="20" y="148" width="120" height="44" rx="14"/><path class="lns" d="M38 170h56"/></g>
      <g class="ip d2"><g class="swipe${left ? ' l' : ''}"><rect class="hl" x="158" y="22" width="102" height="132" rx="16"/><path class="lns" d="M180 74h58M188 98h42"/></g></g>
      <path class="arr ip d3" d="${left ? 'M234 178h-48m8-8-8 8 8 8' : 'M186 178h48m-8-8 8 8-8 8'}"/></svg>`,
    me: `<svg viewBox="0 0 280 200"><g class="ip"><rect class="fr" x="40" y="4" width="200" height="46" rx="14"/><circle class="bar" cx="64" cy="27" r="12"/><path class="lns" d="M88 21h60M88 35h90"/></g>
      <g class="ip d1">${[40, 108, 176].map(x => `<rect class="fr" x="${x}" y="60" width="64" height="40" rx="12"/>`).join('')}</g>
      <g class="ip d2"><rect class="fr" x="40" y="110" width="200" height="48" rx="14"/><path class="lns" d="M58 126h84M58 142h104"/></g>
      <g class="ip d3"><rect class="hl" x="40" y="166" width="200" height="12" rx="6"/><rect class="hl" x="40" y="184" width="200" height="12" rx="6"/></g></svg>`,
    growth: `<svg viewBox="0 0 280 200"><g class="ip"><rect class="fr" x="40" y="4" width="200" height="66" rx="16"/><path class="lns" d="M60 24h40"/><rect class="hl" x="60" y="38" width="96" height="18" rx="9"/></g>
      <g class="ip d1"><rect class="fr" x="40" y="80" width="200" height="62" rx="14"/><path class="lns" d="M60 100h56M60 122h76M190 100h30M196 122h24"/></g>
      <g class="ip d2"><rect class="fr" x="40" y="152" width="200" height="44" rx="14"/><rect class="bar" x="58" y="168" width="164" height="12" rx="6"/><rect class="fill grow-x" x="58" y="168" width="112" height="12" rx="6"/></g></svg>`,
    // 今日 as a list (the default, #442): 这周 with its seven days, the plan with its steps (the next one meant), the
    // one button; at the top right the 列表 | 卡片 switch
    today: `<svg viewBox="0 0 280 200"><g class="ip"><rect class="fr" x="44" y="4" width="192" height="192" rx="20"/></g>
      <g class="ip d1"><rect class="bar" x="168" y="16" width="56" height="18" rx="9"/><rect class="hl" x="170" y="18" width="26" height="14" rx="7"/></g>
      <g class="ip d1">${[0, 1, 2, 3, 4, 5, 6].map(k => `<circle class="${k < 3 ? 'fill' : 'bar'}" cx="${66 + k * 16}" cy="52" r="5"/>`).join('')}</g>
      <g class="ip d2"><rect class="bar" x="58" y="68" width="164" height="86" rx="14"/><rect class="hl" x="64" y="76" width="152" height="22" rx="11"/>
        <path class="lns" d="M90 87h70M90 115h86M90 137h60"/>${[87, 115, 137].map(y => `<circle class="dot" cx="76" cy="${y}" r="5"/>`).join('')}</g>
      <rect class="btn ip d3" x="58" y="164" width="164" height="20" rx="10"/></svg>`,
    // 周报 (#465): the week in one sentence over seven dots (the days studied filled), a block a subject, the button
    report: `<svg viewBox="0 0 280 200"><g class="ip"><rect class="fr" x="44" y="4" width="192" height="52" rx="16"/><path class="lns" d="M62 22h110"/>
        ${[0, 1, 2, 3, 4, 5, 6].map(k => `<circle class="${k === 1 || k === 4 ? 'bar' : 'fill'} pop" cx="${68 + k * 18}" cy="40" r="5"/>`).join('')}</g>
      <g class="ip d1"><rect class="fr" x="44" y="64" width="192" height="50" rx="14"/><path class="lns" d="M62 80h50M62 98h120"/></g>
      <g class="ip d2"><rect class="fr" x="44" y="122" width="192" height="44" rx="14"/><path class="lns" d="M62 138h60M62 154h96"/></g>
      <rect class="btn ip d3" x="44" y="174" width="192" height="20" rx="10"/></svg>`,
    // 使用习惯: six two-way switches in two columns, the text size a slider at the bottom
    habits: `<svg viewBox="0 0 280 200"><g class="ip">${[0, 1, 2].map(r => [0, 1].map(c => { const x = 44 + c * 98, y = 4 + r * 44, on = (r + c) % 2 ? x + 48 : x + 9;
        return `<rect class="fr" x="${x}" y="${y}" width="94" height="38" rx="12"/><rect class="bar" x="${x + 8}" y="${y + 16}" width="78" height="16" rx="8"/><rect class="hl" x="${on}" y="${y + 17}" width="37" height="14" rx="7"/>`; }).join('')).join('')}</g>
      <g class="ip d2"><rect class="fr" x="44" y="138" width="192" height="58" rx="14"/><path class="lns" d="M62 154h40"/><path class="axis" d="M70 178h140"/>
        <circle class="hl knob" cx="80" cy="178" r="9"/></g></svg>`,
  };
  // the steps; setup: only when there is no profile yet; tab: which place of the tab bar (今日 练习 能力 单词 我的), -1 all
  function introSteps(setup) {
    const left = typeof KNOW === 'object' && KNOW.side() === 'left';
    const all = [
      { id: 'hello', setup: true },
      { id: 'goals', setup: true, ask: true },
      { id: 'aim', setup: true, ask: true },
      { id: 'tabs', tab: -1, t: '底下五个地方', d: '今日、练习、能力、单词、我的。每天打开先看「今日」，别的随时点过去。', art: INTRO_ART.tabs },
      { id: 'today', tab: 0, t: '每天从「今日」开始', d: '今天的计划从上往下做，做完一项打一个勾。右上角能换成卡片的样子，长按一张卡片可以调整顺序。', art: INTRO_ART.today },
      { id: 'practice', tab: 1, t: '练习：想练哪样点哪样', d: '语法、听和读、说和写、单词、考试分成几块。最上面「今天建议」告诉你先练什么。', art: INTRO_ART.practice },
      { id: 'exam', tab: 1, t: '考试练习', d: '中考高考、四六级、考研、专四专八、雅思，每套 12–20 分钟限时做。设好「我的考试」就排在最前面。', art: INTRO_ART.exam },
      { id: 'radar', tab: 2, t: '能力：看看差在哪', d: '听力、阅读、词汇、语法、口语、写作六项，每项测 3–8 分钟。离目标最远的那项，每天会多练一点。', art: INTRO_ART.radar },
      { id: 'words', tab: 3, t: '单词和错题本', d: `每天要复习的和新词都在「单词」，${left ? '左' : '右'}滑认识。做错的题会进「错题本」，过几天再考你一次。`, art: INTRO_ART.words(left) },
      { id: 'me', tab: 4, t: '我的', d: '学习目标、朗读声音、提醒都在这里。「账号和隐私」「帮助」收在最下面，点开才展开。', art: INTRO_ART.me },
      { id: 'growth', tab: 4, t: '我的进步', d: '只和上个月的自己比：学了几天、读了多少词、快到哪个里程碑。在「我的」最上面点开。', art: INTRO_ART.growth },
      { id: 'report', tab: 4, t: '周报', d: '最近 7 天学了几天、学了什么、哪里进步了，一页看完，还能存成一张图分享。在「我的」最上面点开。', art: INTRO_ART.report },
      { id: 'habits', tab: 4, t: '使用习惯', d: '今日的样子、主题色、「认识」放哪边、字号这些，都在「我的 → 使用习惯」一页里改。', art: INTRO_ART.habits },
    ];
    return setup ? all : all.filter(s => !s.setup);
  }
  const INTRO = { el: null, steps: [], i: 0, done: null, prev: null, st: null, again: false, busy: false, tab: null, demo: 0, res: 0 };
  // how it moves (B9 and A0, 2026-11-26: 「新手引导是要有流畅的动画的哦」): both steps at once, fast then slow
  const INTRO_EASE = 'cubic-bezier(.2,.8,.2,1)', INTRO_MS = 300;
  // where it was left (this browser): the step's id and whose it was
  const introWho = () => (S.user ? 'u' + S.user.id : 'guest');
  function introLeftAt() { const a = load('flow-intro-at'); return a && a.who === introWho() ? a.id : ''; }
  const introTour = s => !s.setup;  // a step of the places: picture, title, sentence, and the one shared button

  // opts: { setup: from 欢迎, again: 我的 → 帮助, from: a step's id to go on from }; done(result, step, again)
  function introStart(opts, done) {
    if (INTRO.el) return;
    const steps = INTRO.steps = introSteps(!!opts.setup);
    INTRO.done = done; INTRO.again = !!opts.again; INTRO.prev = document.activeElement;
    INTRO.i = Math.max(0, steps.findIndex(s => s.id === opts.from)); INTRO.tab = null; INTRO.busy = false;
    INTRO.st = INTRO.st || { goals: [], exam: '', target: '', days: 0, picked: false, dayPicked: false };
    const el = INTRO.el = document.createElement('div');
    el.className = 'intro'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); el.setAttribute('aria-labelledby', 'introT'); el.tabIndex = -1;
    // 全英文界面 (E1): in Chinese for now, the whole of it at once (data-zh), until its words are in E1's tables
    el.setAttribute('data-zh', '');
    // the tab bar's own icons and names, in its place at the bottom (nothing to tap: it only shows where things are)
    const tabs = [...document.querySelectorAll('.tabs a')].map(a => `<span class="intro-tab">${a.querySelector('svg') ? a.querySelector('svg').outerHTML : ''}<span>${esc(a.textContent.trim())}</span></span>`).join('');
    el.innerHTML = `<div class="intro-top"><button class="intro-back" type="button" data-intro="back" aria-label="上一步" data-tap="intro-back"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg></button>
        <span class="intro-prog" aria-hidden="true"><i></i></span>
        <button class="intro-skip" type="button" data-intro="skip" data-tap="intro-skip">跳过</button></div>
      <div class="intro-stage"><div class="intro-go"><button class="btn primary block intro-next" type="button" data-intro="next" data-tap="intro-next">下一步</button></div>
        <div class="intro-under" aria-live="polite"></div></div>
      <div class="intro-tabs" aria-hidden="true"><span class="intro-pill"></span>${tabs}</div>`;
    document.body.appendChild(el); document.body.classList.add('introing');
    el.addEventListener('click', introClick);
    el.addEventListener('keydown', introKey);
    introDragWire(el.querySelector('.intro-stage'));
    addEventListener('resize', introLayout);
    introLayout();
    const page = introMake(INTRO.i);
    el.querySelector('.intro-stage').insertBefore(page, el.querySelector('.intro-go'));
    introSettle(page, true);
    requestAnimationFrame(() => requestAnimationFrame(() => { if (INTRO.el === el) el.classList.add('in'); }));
  }
  function introClick(e) {
    const b = e.target.closest('[data-intro]'); if (!b || b.disabled) return;
    const a = b.dataset.intro;
    if (a === 'skip') introEnd('skip');
    else if (a === 'back') introBack();
    else if (a === 'next') introNext();
    else if (a === 'login' || a === 'reg') { introEnd('later'); openLogin('', a === 'reg' ? 'reg' : ''); }
  }
  function introKey(e) {
    const el = INTRO.el; if (!el) return;
    if (e.key === 'Escape') { e.preventDefault(); introEnd('skip'); return; }
    const ask = INTRO.steps[INTRO.i].ask;
    if (!ask && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) { e.preventDefault(); if (e.key === 'ArrowRight') introNext(); else introBack(); return; }
    if (e.key !== 'Tab') return;  // the focus stays in it while it is open
    const bs = [...el.querySelectorAll('.intro-top button, .intro-step.cur button, .intro-go button, .intro-under button')].filter(b => !b.hidden && !b.disabled && b.offsetParent !== null);
    if (!bs.length) return;
    const k = bs.indexOf(document.activeElement);
    e.preventDefault(); bs[(k + (e.shiftKey ? bs.length - 1 : 1) + bs.length) % bs.length].focus();
  }

  // The places' steps keep their picture, title and sentence in one block of the same height (the tallest of them on
  // this screen), just above the one button, so the picture starts at the same place from step to step and the words
  // are never far from the button (the user, 13:3x: the button where the eye and the thumb already are).
  function introLayout() {
    const el = INTRO.el; if (!el) return;
    const stage = el.querySelector('.intro-stage'), probe = document.createElement('div');
    probe.className = 'intro-step intro-place intro-probe'; probe.setAttribute('aria-hidden', 'true');
    probe.innerHTML = INTRO.steps.filter(introTour).map(s => introStepHTML(s)).join('');
    stage.appendChild(probe);
    INTRO.res = Math.max(...[...probe.querySelectorAll('.intro-body')].map(b => b.offsetHeight), 0);
    probe.remove();
    stage.style.setProperty('--res', INTRO.res + 'px');
    // the room left over goes mostly above the block; under it, toward the button, 28 to 96 px
    const free = stage.clientHeight - (62 + 12 + 52) - INTRO.res - 28;
    stage.style.setProperty('--gap', Math.round(Math.max(28, Math.min(96, 28 + free * 0.4))) + 'px');
  }
  // one step's page (not yet the current one: no ids, not wired)
  function introMake(i) {
    const s = INTRO.steps[i], page = document.createElement('section');
    // (想达到什么水平 is short: it sits down by the button too, B9; 学英语为了什么 fills its room from the top)
    page.className = 'intro-step' + (s.ask ? ' ask' : '') + (s.id === 'aim' ? ' low' : '') + (introTour(s) ? ' intro-place' : '') + (s.id === 'hello' ? ' intro-hello' : '');
    page.dataset.k = String(i);
    page.innerHTML = introStepHTML(s);
    introArtPrep(page);
    return page;
  }
  // the lines of a picture are drawn: each stroke from nothing to its whole length (stroke-dashoffset, on this small
  // picture only; B9), its group's delay after the one before
  function introArtPrep(page) {
    if (REDUCED) return;
    page.querySelectorAll('.intro-art .fr, .intro-art .hl, .intro-art .lns, .intro-art .axis, .intro-art .arr').forEach(x => {
      let len = 0; try { len = Math.ceil(x.getTotalLength()); } catch (e) { len = 0; }
      if (!len) return;
      const g = x.closest('.d1, .d2, .d3'), k = g ? Number(g.className.baseVal.match(/\bd(\d)\b/)[1]) : 0;
      x.style.strokeDasharray = `${len} ${len + 40}`; x.style.strokeDashoffset = String(len + 20);
      x.style.setProperty('--dl', 60 + k * 70 + 'ms'); x.classList.add('draw');
    });
  }
  // the step now on screen: its ids and wiring, the top bar, the tab bar's mark, the shared button, the focus
  function introSettle(page, first, keep) {
    const el = INTRO.el, steps = INTRO.steps, s = steps[INTRO.i], n = steps.length, last = INTRO.i === n - 1;
    save('flow-intro-at', { id: s.id, who: introWho() });  // closed here, the next opening goes on from this step
    el.querySelectorAll('.intro-step').forEach(p => { if (p !== page && !p.classList.contains('leaving')) p.remove(); });
    page.classList.add('cur', 'seen'); page.removeAttribute('aria-hidden');
    if (!keep) page.style.transition = page.style.transform = page.style.opacity = '';
    page.style.willChange = '';  // (only while it moves, B9)
    el.querySelectorAll('#introT, #introD').forEach(x => x.removeAttribute('id'));
    const t = page.querySelector('.intro-t'), d = page.querySelector('.intro-d');
    if (t) t.id = 'introT'; if (d) d.id = 'introD';
    if (s.ask && !page.dataset.wired) { introWire(page, s); page.dataset.wired = '1'; }
    // the top: back from the second step on (not back into the choices once they are saved: 我的 → 学习目标 changes
    // them); how far along, a bar (no numbers to count down)
    el.querySelector('.intro-back').hidden = INTRO.i === 0 || !introCanGo(INTRO.i - 1);
    introBars(INTRO.i, null, 0);
    // the one button, the same place on every step (B9): its words, and under it 注册 / 登录 or what is still to choose
    const b = el.querySelector('.intro-go .intro-next');
    b.textContent = last ? (INTRO.again ? '看完了' : '开始学习') : s.id === 'hello' ? '开始' : '下一步';
    introUnder();
    // the focus: on the dialog when it opens (a screen reader hears its name; no ring drawn on a button), then on the
    // button, so 下一步 is one Enter away
    if (first) el.focus({ preventScroll: true }); else b.focus({ preventScroll: true });
    if (!first || INTRO.i) announce(`第 ${INTRO.i + 1} 步，共 ${n} 步：${t ? t.textContent : ''}。${d ? d.textContent : ''}`);
    introDemo(page);
  }
  // under the button: 注册 and 登录 on 欢迎 (a guest), what is still to choose on 学英语为了什么
  function introUnder() {
    const el = INTRO.el; if (!el) return;
    const s = INTRO.steps[INTRO.i], u = el.querySelector('.intro-under'), b = el.querySelector('.intro-go .intro-next');
    const st = INTRO.st, ok = s.id !== 'goals' || introGoalsOk();
    b.disabled = !ok || INTRO.busy;
    const html = s.id === 'hello' && !S.user ? '<div class="intro-acct"><button type="button" data-intro="reg" data-tap="intro-reg">注册账号</button><button type="button" data-intro="login" data-tap="intro-login">已有账号？登录</button></div>'
      : s.id === 'goals' && !ok ? `<p class="intro-need">${!st.goals.length ? '先选一个' : '再选一个考试'}</p>` : '';
    if (u.dataset.was !== html) { u.innerHTML = html; u.dataset.was = html; }
  }
  // the progress bar and the tab bar's mark: at step i, or part of the way (p, 0–1) to step j while a finger drags
  function introBars(i, j, p) {
    const el = INTRO.el, steps = INTRO.steps, n = steps.length;
    const prog = el.querySelector('.intro-prog i'), pill = el.querySelector('.intro-pill'), tabs = el.querySelector('.intro-tabs');
    const dragging = j != null;
    prog.style.transition = pill.style.transition = dragging ? 'none' : '';
    prog.style.transform = `scaleX(${(i + 1 + (dragging ? (j - i) * p : 0)) / n})`;
    const on = steps[i].tab == null ? null : steps[i].tab, to = dragging && steps[j].tab != null ? steps[j].tab : null;
    if (dragging) {  // the mark between two places follows the finger
      if (on != null && on >= 0 && to != null && to >= 0) pill.style.transform = `translateX(${(on + (to - on) * p) * 100}%)`;
      return;
    }
    tabs.classList.toggle('show', on != null);
    tabs.classList.toggle('sweep', on === -1);
    tabs.classList.toggle('reveal', INTRO.tab === -1 && on != null && on >= 0); INTRO.tab = on;
    pill.style.transform = `translateX(${Math.max(0, on || 0) * 100}%)`;
    tabs.querySelectorAll('.intro-tab').forEach((x, k) => x.classList.toggle('on', on === k));
  }
  // what a picture shows (单词's card swiped, 能力's shape growing, a row opening, a bar growing): once after it is
  // drawn, then gently again every few seconds while the step stays
  const INTRO_DEMO = {
    swipe: l => [{ transform: 'none' }, { transform: `translateX(${l ? -14 : 14}px) rotate(${l ? -4 : 4}deg)`, offset: 0.4 }, { transform: `translateX(${l ? -14 : 14}px) rotate(${l ? -4 : 4}deg)`, offset: 0.6 }, { transform: 'none' }],
    'grow-in': () => [{ transform: 'scale(.82)' }, { transform: 'none' }],
    'grow-x': () => [{ transform: 'scaleX(.55)' }, { transform: 'none' }],
    open: () => [{ transform: 'scaleY(.7)', opacity: 0.6 }, { transform: 'none', opacity: 1 }],
    knob: () => [{ transform: 'none' }, { transform: 'translateX(64px)', offset: 0.45 }, { transform: 'translateX(64px)', offset: 0.6 }, { transform: 'none' }],
  };
  function introDemo(page) {
    clearInterval(INTRO.demo); INTRO.demo = 0;
    if (REDUCED || !page.querySelector('.intro-art')) return;
    const parts = Object.keys(INTRO_DEMO).map(k => [k, page.querySelector('.intro-art .' + k)]).filter(x => x[1] && x[1].animate);
    if (!parts.length) return;
    const play = () => parts.forEach(([k, x]) => x.animate(INTRO_DEMO[k](x.classList.contains('l')), { duration: k === 'swipe' || k === 'knob' ? 1300 : 700, easing: INTRO_EASE }));
    let n = 0;
    const id = INTRO.demo = setInterval(() => { if (INTRO.el && page.isConnected && ++n <= 2) play(); else clearInterval(id); }, 4000);
  }
  // can a step be reached from this one: not past the choices before they are made (下一步 saves them), not back into
  // them once saved
  function introGoalsOk() { const st = INTRO.st; return st.goals.length > 0 && (!st.goals.includes('exam') || !!st.exam); }
  function introCanGo(j) {
    const steps = INTRO.steps, s = steps[INTRO.i], t = steps[j];
    if (!t || j === INTRO.i) return false;
    if (j > INTRO.i) return s.id === 'goals' ? introGoalsOk() : s.id !== 'aim';
    return !(t.setup && !s.setup && hasProfile());
  }

  // to step j: both at once, the one on screen out to one side and the new one in from the other, sliding and fading
  // (300 ms, fast then slow); from where a finger left them (from: the offset in px), or from the start
  // where a moving step is now (its translateX in px)
  function introX(x) {
    const t = getComputedStyle(x).transform, M = window.DOMMatrix || window.WebKitCSSMatrix;
    try { return t && t !== 'none' && M ? new M(t).m41 : 0; } catch (e) { return 0; }
  }
  // a turn still playing ends where it is: the one leaving goes on out quickly, the one arriving is the current one
  function introCut() {
    const a = INTRO.anim; if (!a) return;
    INTRO.anim = null; clearTimeout(a.t);
    const xo = introX(a.out), oo = Number(getComputedStyle(a.out).opacity);
    a.out.classList.add('leaving'); introPlace(a.out, xo, oo); a.out.offsetWidth;  // eslint-disable-line no-unused-expressions
    introPlace(a.out, a.outTo, 0, 140); setTimeout(() => a.out.remove(), 160);
    const xi = introX(a.in), oi = Number(getComputedStyle(a.in).opacity);
    introPlace(a.in, xi, oi); introSettle(a.in, false, true);
  }
  function introGo(j, from) {
    if (!INTRO.el || INTRO.busy || j < 0 || j >= INTRO.steps.length || j === INTRO.i) return;
    introCut();
    const stage = INTRO.el.querySelector('.intro-stage'), cur = stage.querySelector('.intro-step.cur'), dir = j > INTRO.i ? 1 : -1, W = stage.clientWidth;
    let nb = from && from.nb;
    if (!nb) {
      nb = introMake(j); nb.setAttribute('aria-hidden', 'true');
      stage.insertBefore(nb, stage.querySelector('.intro-go'));
      introPlace(nb, dir * W, 0);
      nb.offsetWidth;  // eslint-disable-line no-unused-expressions -- its start position drawn before it moves
      nb.classList.add('seen');
    }
    const moved = from ? Math.abs(from.dx) : 0, v = from ? Math.abs(from.v) : 0;
    const ms = REDUCED ? 0 : Math.round(Math.max(160, Math.min(INTRO_MS, v > 0.5 ? (W - moved) / v : INTRO_MS * (1 - moved / W) + 80)));
    introPlace(cur, -dir * W, 0, ms); introPlace(nb, 0, 1, ms);
    INTRO.i = j; introBars(j, null, 0);
    const a = INTRO.anim = { out: cur, in: nb, outTo: -dir * W };
    a.t = setTimeout(() => { if (INTRO.anim === a) INTRO.anim = null; cur.remove(); if (INTRO.el) introSettle(nb, false); }, ms + 20);
  }
  function introPlace(x, px, o, ms) {
    x.style.transition = ms ? `transform ${ms}ms ${INTRO_EASE}, opacity ${ms}ms ${INTRO_EASE}` : 'none';
    x.style.willChange = REDUCED ? '' : 'transform, opacity';
    x.style.transform = `translateX(${Math.round(px)}px)`; x.style.opacity = String(o);
  }
  function introBack() { if (introCanGo(INTRO.i - 1)) introGo(INTRO.i - 1); }

  // a finger: sideways (past 8 px; up and down still scrolls a list), the step follows it 1:1 with the next one beside
  // it; let go past a third of the screen, or with speed, and it turns, else it springs back. Nothing to turn to (the
  // first, the last, the choices not made): it gives a third of the way, then springs back.
  function introDragWire(stage) {
    let d = null;
    const W = () => stage.clientWidth;
    stage.addEventListener('touchstart', e => {
      if (INTRO.busy || e.touches.length > 1 || e.touches[0].clientX < 20) { d = null; return; }
      introCut();
      const p = e.touches[0]; d = { x0: p.clientX, y0: p.clientY, lock: '', dx: 0, dir: 0, nb: null, can: false, pts: [[p.clientX, performance.now()]] };
    }, { passive: true });
    stage.addEventListener('touchmove', e => {
      if (!d || INTRO.busy) return;
      const p = e.touches[0], dx = p.clientX - d.x0, dy = p.clientY - d.y0;
      if (!d.lock) { if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return; d.lock = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y'; }
      if (d.lock !== 'x') return;
      if (e.cancelable) e.preventDefault();
      d.pts.push([p.clientX, performance.now()]); if (d.pts.length > 6) d.pts.shift();
      const dir = dx < 0 ? 1 : -1;
      if (dir !== d.dir) {  // which side: the step it would turn to, drawn beside this one
        if (d.nb) d.nb.remove();
        d.dir = dir; d.j = INTRO.i + dir; d.can = introCanGo(d.j); d.nb = null;
        if (d.can) {
          d.nb = introMake(d.j); d.nb.setAttribute('aria-hidden', 'true'); d.nb.classList.add('seen');
          stage.insertBefore(d.nb, stage.querySelector('.intro-go'));
        }
      }
      const cur = stage.querySelector('.intro-step.cur'), w = W(), p01 = Math.min(1, Math.abs(dx) / w);
      d.dx = d.can ? dx : dx / 3;
      introPlace(cur, d.dx, d.can ? 1 - 0.7 * p01 : 1);
      if (d.nb) introPlace(d.nb, d.dir * w + dx, 0.3 + 0.7 * p01);
      if (d.can) introBars(INTRO.i, d.j, p01);
    }, { passive: false });
    const end = cancel => {
      if (!d || d.lock !== 'x') { d = null; return; }
      const a = d.pts[0], b = d.pts[d.pts.length - 1], v = b[1] > a[1] ? (b[0] - a[0]) / (b[1] - a[1]) : 0, w = W();
      const turn = !cancel && d.can && (Math.abs(d.dx) > w * 0.3 || (Math.abs(v) > 0.5 && Math.sign(v) === -d.dir));
      const cur = stage.querySelector('.intro-step.cur'), x = d;
      d = null;
      if (turn) { introGo(x.j, { nb: x.nb, dx: x.dx, v }); return; }
      // back to where it was (a little give past it from the edge)
      const ms = REDUCED ? 0 : 280;
      cur.style.transition = `transform ${ms}ms cubic-bezier(.34,1.3,.64,1), opacity ${ms}ms ${INTRO_EASE}`;
      cur.style.transform = 'translateX(0px)'; cur.style.opacity = '1';
      if (x.nb) { introPlace(x.nb, x.dir * w, 0, ms); setTimeout(() => x.nb.remove(), ms + 20); }
      introBars(INTRO.i, null, 0);
    };
    stage.addEventListener('touchend', () => end(false));
    stage.addEventListener('touchcancel', () => end(true));
  }
  function introStepHTML(s) {
    if (s.id === 'hello') {
      return `<div class="intro-body"><div class="intro-mark" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>
        <h2 class="intro-t intro-big">欢迎来到语流</h2>
        <p class="intro-d">每天十来分钟，听、读、说、背单词，跟着计划一点点往前走。先用半分钟定个目标。</p>
</div>`;
    }
    const M = S.meta || {}, st = INTRO.st;
    if (s.id === 'goals') {
      const goals = [...(M.goals || [])].sort((a, b) => (b.id === 'exam') - (a.id === 'exam'));
      return `<div class="intro-body wg"><h2 class="intro-t">你学英语主要为了什么？</h2>
        <p class="intro-d">可以多选，最多 3 个，第一个选的算主要目标。</p>
        <div class="intro-opts wg-goals" role="group" aria-label="学英语为了什么，可以多选">${goals.map(g => `<button class="opt" type="button" data-ig="${esc(g.id)}" aria-pressed="${st.goals.includes(g.id)}">
          <span class="l">${esc(g.label)}</span><span class="d">${esc((M.goal_hints || {})[g.id] || '')}</span><span class="main" hidden>主要</span><svg class="ck" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-6.5"/></svg></button>`).join('')}</div>
        <div class="intro-exam" id="introExam" hidden><h3 class="intro-h" id="introExamH">准备哪个考试？</h3>
          <div class="chips" role="radiogroup" aria-labelledby="introExamH">${(M.exams || []).map(x => `<button class="chip" type="button" role="radio" data-ie="${esc(x.id)}" aria-checked="${x.id === st.exam}">${esc(x.short)}</button>`).join('')}</div></div>
</div>`;
    }
    if (s.id === 'aim') {
      return `<div class="intro-body wg"><h2 class="intro-t">想达到什么水平？</h2>
        <p class="intro-d">按你的目标推荐了一档，可以改。现在的水平不用先测，以后在「能力」里测一下更准。</p>
        <div class="intro-opts wg-targets" role="radiogroup" aria-label="想达到什么水平">${(M.targets || []).map(x => `<button class="opt" type="button" role="radio" data-it="${esc(x.id)}" aria-checked="false">
          <b>${esc(x.id)}</b><span class="d">${esc(x.label)}</span><span class="rec" hidden>推荐</span></button>`).join('')}</div>
        <h3 class="intro-h" id="introDaysH">一周大概能学几天？</h3>
        <div class="chips intro-days" role="radiogroup" aria-labelledby="introDaysH">${[2, 3, 4, 5, 6, 7].map(d => `<button class="chip" type="button" role="radio" data-id="${d}" aria-checked="false">${d} 天</button>`).join('')}</div>
</div>`;
    }
    return `<div class="intro-body"><div class="intro-art" aria-hidden="true">${s.art}</div>
      <h2 class="intro-t">${esc(s.t)}</h2><p class="intro-d">${esc(s.d)}</p></div>`;
  }
  // the steps that ask: the same choices and rules as the one-page form (09-start.js welcome)
  function introWire(page, s) {
    const M = S.meta || {}, st = INTRO.st;
    page.addEventListener('click', e => {
      const b = e.target.closest('.opt, .chip');
      if (b && !REDUCED && b.animate) b.animate([{ transform: 'none' }, { transform: 'scale(.95)', offset: 0.35 }, { transform: 'none' }], { duration: 260, easing: 'cubic-bezier(.34,1.4,.64,1)' });
    });
    const hasExam = () => st.goals.includes('exam');
    if (s.id === 'goals') {
      const sync = () => {
        page.querySelectorAll('[data-ig]').forEach(b => {
          const on = st.goals.includes(b.dataset.ig), main = on && st.goals.length > 1 && b.dataset.ig === st.goals[0];
          b.setAttribute('aria-pressed', String(on)); b.querySelector('.main').hidden = !main;
        });
        page.querySelectorAll('[data-ie]').forEach(b => b.setAttribute('aria-checked', String(b.dataset.ie === st.exam)));
        page.querySelector('#introExam').hidden = !hasExam();
        if (INTRO.el && INTRO.steps[INTRO.i].id === 'goals') introUnder();
      };
      page.querySelectorAll('[data-ig]').forEach(b => b.onclick = () => {
        const g = b.dataset.ig;
        if (st.goals.includes(g)) st.goals = st.goals.filter(x => x !== g);
        else if (st.goals.length >= 3) { toast('最多选 3 个，先去掉一个再选'); return; }
        else st.goals = st.goals.concat(g);
        if (g === 'exam' && hasExam() && !st.exam && M.exams && M.exams.length === 1) st.exam = M.exams[0].id;
        sync();
      });
      page.querySelectorAll('[data-ie]').forEach(b => b.onclick = () => { st.exam = b.dataset.ie; sync(); });
      sync();
    } else if (s.id === 'aim') {
      const suggest = () => (M.target_for || {})[hasExam() && st.exam ? st.exam : st.goals[0]] || 'B1';
      if (!st.picked) st.target = suggest();
      if (!st.dayPicked) st.days = hasExam() ? 5 : 4;
      const sync = () => {
        page.querySelectorAll('[data-it]').forEach(b => { b.setAttribute('aria-checked', String(b.dataset.it === st.target)); b.querySelector('.rec').hidden = b.dataset.it !== suggest(); });
        page.querySelectorAll('[data-id]').forEach(b => b.setAttribute('aria-checked', String(Number(b.dataset.id) === st.days)));
      };
      page.querySelectorAll('[data-it]').forEach(b => b.onclick = () => { st.target = b.dataset.it; st.picked = true; sync(); });
      page.querySelectorAll('[data-id]').forEach(b => b.onclick = () => { st.days = Number(b.dataset.id); st.dayPicked = true; sync(); });
      sync();
    }
  }
  async function introNext() {
    const s = INTRO.steps[INTRO.i];
    if (!INTRO.el || INTRO.busy) return;
    if (INTRO.i === INTRO.steps.length - 1) { introEnd('done'); return; }
    if (s.id === 'goals' && !introGoalsOk()) return;
    if (s.id === 'aim') {  // the profile, as the one-page form saves it; then 今日 is drawn under the steps still to come
      const st = INTRO.st, exam = st.goals.includes('exam') ? st.exam : '';
      const prof = { goal: st.goals[0], goals: st.goals, target: st.target, level: S.placed || below(st.target), level_source: S.placed ? 'placed' : 'guess',
                     themes: [], minutes: 10, exam, exam_date: '', weekly_goal: st.days };
      const b = INTRO.el.querySelector('.intro-go .intro-next'); INTRO.busy = true; b.disabled = true;
      try { await welcomeSave(prof, false); } catch (x) { INTRO.busy = false; if (b) b.disabled = false; toast(x.message); return; }
      INTRO.busy = false;
      if (location.hash !== '#/') location.hash = '#/';
    }
    introGo(INTRO.i + 1);
  }
  // result: 'done' (the last step), 'skip', or 'later' (to 登录 / 注册: the steps go on after it, from where they were)
  function introEnd(result) {
    const el = INTRO.el; if (!el) return;
    const s = INTRO.steps[INTRO.i], step = INTRO.i + 1;
    INTRO.el = null; el.classList.remove('in'); document.body.classList.remove('introing');
    clearInterval(INTRO.demo); INTRO.demo = 0; INTRO.busy = false; removeEventListener('resize', introLayout);
    setTimeout(() => el.remove(), REDUCED ? 0 : 300);
    if (result !== 'later') save('flow-intro-at', null);
    if (INTRO.prev && INTRO.prev.isConnected && result !== 'done') { try { INTRO.prev.focus({ preventScroll: true }); } catch (e) { /* gone */ } }
    const cb = INTRO.done; INTRO.done = null;
    if (cb) cb(result, step, s);
  }

  /* 带着做第一步: a soft ring around the button meant and a short line by it. The page stays usable: tapping that button
     is the next step (the ring goes, the page it opens may have one more); 知道了, or going elsewhere, ends it. */
  const COACH = { el: null, at: null, then: '' };
  function coach(sels, title, text) {
    coachEnd();
    const at = sels.map(q => document.querySelector(q)).find(x => x && x.getBoundingClientRect().width > 0);
    if (!at) return false;
    const fixed = getComputedStyle(at).position === 'fixed' || at.closest('.mini-player, .tabs');
    if (!fixed) at.scrollIntoView({ block: 'center', behavior: 'auto' });
    const el = COACH.el = document.createElement('div');
    el.className = 'coach'; el.setAttribute('data-zh', '');  // (as the steps: in Chinese until E1's tables have it)
    // (placed by the outer two, coachPlace; the ring breathes and the card grows inside them)
    el.innerHTML = `<div class="coach-at" aria-hidden="true"><div class="coach-ring"></div></div>
      <div class="coach-tipat"><div class="coach-tip" role="note"><b>${esc(title)}</b><p>${esc(text)}</p><button class="coach-x" type="button" data-tap="coach-ok">知道了</button></div></div>`;
    document.body.appendChild(el); document.body.classList.add('coaching'); COACH.at = at;
    el.querySelector('.coach-x').onclick = () => { COACH.then = ''; coachEnd(); };
    at.addEventListener('click', coachEnd, { once: true });
    addEventListener('resize', coachPlace); addEventListener('scroll', coachPlace, { passive: true });
    coachPlace();
    requestAnimationFrame(() => requestAnimationFrame(() => { if (COACH.el === el) el.classList.add('in'); }));
    announce(`${title}。${text}`);
    return true;
  }
  // the ring follows the button with transform only (08-intro.css): its size once, its place as the page scrolls; the
  // card grows from the side of the button (its transform-origin there)
  function coachPlace() {
    const el = COACH.el; if (!el) return;
    if (!COACH.at.isConnected) { coachEnd(); return; }
    const at = el.querySelector('.coach-at'), tipat = el.querySelector('.coach-tipat'), tip = el.querySelector('.coach-tip'), r = COACH.at.getBoundingClientRect();
    const pad = 6, gap = 14, W = innerWidth, H = innerHeight, w = tip.offsetWidth, h = tip.offsetHeight;
    at.style.width = r.width + 2 * pad + 'px'; at.style.height = r.height + 2 * pad + 'px';
    at.style.transform = `translate(${Math.round(r.left - pad)}px,${Math.round(r.top - pad)}px)`;
    const left = Math.min(Math.max(16, r.left + r.width / 2 - w / 2), W - w - 16), below = r.bottom + pad + gap + h <= H - 8;
    const top = below ? r.bottom + pad + gap : Math.max(8, r.top - pad - gap - h);
    tipat.style.transform = `translate(${Math.round(left)}px,${Math.round(top)}px)`;
    tip.style.transformOrigin = `${Math.round(Math.min(w - 16, Math.max(16, r.left + r.width / 2 - left)))}px ${below ? '0' : '100%'}`;
  }
  function coachEnd() {
    const el = COACH.el; if (!el) return;
    COACH.el = null; COACH.at = null; document.body.classList.remove('coaching');
    removeEventListener('resize', coachPlace); removeEventListener('scroll', coachPlace);
    el.classList.remove('in'); setTimeout(() => el.remove(), REDUCED ? 0 : 300);
  }
  // after each page (02-shell.js, with tourMaybe): the page the first step opened gets its one ring
  function coachFollow() {
    if (COACH.el && !COACH.at.isConnected) coachEnd();
    if (!COACH.then) return;
    const want = COACH.then;
    if (want === 'step' && /^#\/m\/[^/]+(\/listen)?$/.test(location.hash)) {
      COACH.then = '';
      setTimeout(() => coach(['.mini-player #playAll', '#playAll'], '先听一遍', '点「播放全文」，跟着亮起来的句子听。听完点页面最下面的「听完了，去读」。'), REDUCED ? 0 : 450);
    } else if (want === 'step' && location.hash !== '#/') COACH.then = '';
  }
  // the steps over: on 今日, the plan's own button
  function introThen(result) {
    if (result !== 'done') return;
    COACH.then = 'step';
    const ring = () => { if (!coach(['#view .today-plan .go-next', '#view .go-next'], '从这里开始', '点它开始今天的第一项，做完会自动打勾。')) COACH.then = ''; };
    if (location.hash !== '#/') { location.hash = '#/'; setTimeout(ring, REDUCED ? 300 : 700); } else setTimeout(ring, REDUCED ? 0 : 380);
  }
  /* ---------- 使用提示: said the first time, then not again on any phone or computer (the user, 2026-11-25) ---------- */
  // tipSlot(name, text): where a page used to keep an instruction for good (「点词查词…」 on 读), a line with 知道了 the
  // first time. An account keeps what it put away on the server (/api/next/tips, tour_service.TIPS), so another device
  // does not say it again; a guest, this browser. 我的 → 帮助 → 更多 →「重新显示使用提示」 brings them all back.
  // Drawn with the page, never after it: what this account has put away is kept on the phone too (flow-tips-<who>) and
  // fetched once the account is known (boot, sign-in); until the phone knows, the tip waits for the next visit rather
  // than pushing the text down when the answer comes (语流 B8, 2026-11-25: 54 px, 2 s after the page on a slow line).
  const TIPS = {
    seen: null, who: undefined,
    me() { return S.user ? String(S.user.id || S.user.username) : 'guest'; },
    key(who) { return 'flow-tips-' + who; },
    // what is known for this account right now, without waiting: null when the phone does not know yet
    now() {
      const who = this.me();
      if (this.seen && this.who === who) return this.seen;
      const kept = load(this.key(who)) || (who === 'guest' ? load('flow-tips') : null);  // flow-tips: a guest's list before this
      if (Array.isArray(kept)) { this.who = who; this.seen = new Set(kept); return this.seen; }
      return who === 'guest' ? (this.who = who, this.seen = new Set()) : null;
    },
    // once at a time; 'flow-tips' on document when it is known (the 内测版's line and sheet wait for it, 03-channel.js)
    load() {
      if (this.busy) return this.busy;
      const who = this.me();
      this.busy = (async () => {
        if (who !== 'guest') {
          try {
            const seen = new Set((await api('/api/next/tips')).seen || []);
            // what was put away on this browser before signing in counts for the account too
            (load(this.key('guest')) || []).filter(n => !seen.has(n)).forEach(n => { seen.add(n); api('/api/next/tips', { tip: n }).catch(() => {}); });
            if (this.me() === who) { this.who = who; this.seen = seen; save(this.key(who), [...seen]); }
          } catch (e) { /* offline: the phone's copy stands */ }
        }
        this.busy = null;
        try { document.dispatchEvent(new CustomEvent('flow-tips')); } catch (e) { /* very old browsers: nothing waits */ }
        return this.now();
      })();
      return this.busy;
    },
    mark(name) {
      const seen = this.now() || new Set(); if (seen.has(name)) return;
      seen.add(name); this.seen = seen; this.who = this.me(); save(this.key(this.who), [...seen]);
      if (S.user) api('/api/next/tips', { tip: name }).catch(() => {});
    },
    unmark(name) {  // one back on its own (「下次复习时再看一次」)
      const seen = this.now(); if (seen) { seen.delete(name); save(this.key(this.me()), [...seen]); }
      if (S.user) api('/api/next/tips', { tip: name, seen: false }).catch(() => {});
    },
    async reset() {
      const who = this.me(); this.who = who; this.seen = new Set(); save(this.key(who), []); if (who === 'guest') save('flow-tips', null);
      TIP_LOCAL.forEach(k => save(k, null));  // put away on this phone before they were kept on the account
      if (S.user) await api('/api/next/tips', { reset: true });
    },
  };
  // 一次性入口 (the user, 2026-11-26: 「第一次用才需要的按钮，点过一次就不要再出现」): put away on this phone before they were
  // kept with the tips; each still counts, and is copied to the account the first time it is asked about
  const TIP_LOCAL = ['flow-tap-guide', 'flow-tap-guide-back', 'flow-next-swipe-tip', 'flow-know-tip', 'flow-beta-bar'];
  // true: this account (a guest: this browser) has put it away; false: not yet; null: the phone does not know yet, and
  // whatever asks says nothing this time rather than pushing the page about when the answer comes
  function tipSeen(name, local) {
    const seen = TIPS.now();
    if (local && load(local)) { if (seen && !seen.has(name)) TIPS.mark(name); return true; }
    if (!seen) { TIPS.load(); return null; }
    return seen.has(name);
  }
  function tipSlot(name, text) {
    const seen = TIPS.now();
    if (!seen) { TIPS.load(); return ''; }  // not known on this phone yet: next visit, never a jump now
    if (seen.has(name)) return '';
    return `<div class="tip-once" id="tip-${name}" role="note"><span>${esc(text)}</span><button class="link small" type="button" data-tip-ok="${name}">知道了</button></div>`;
  }
  document.addEventListener('click', e => {
    const o = e.target.closest && e.target.closest('[data-tip-seen]'); if (o) TIPS.mark(o.dataset.tipSeen);  // a one-time entry used
    const b = e.target.closest && e.target.closest('[data-tip-ok]'); if (!b) return;
    TIPS.mark(b.dataset.tipOk); const t = b.closest('.tip-once'); if (t) t.remove();
  });
  /* ---------- 新手引导 (the owner, 2026-11-25: 「加入首次使用引导」, 指一指): the first time a new account opens 今日, the
     real buttons one after another — the page dimmed around the one meant, a small card by it, 下一步 / 跳过. A 老师账号
     gets three on 我的班级. Once per account (tour_service.py); 我的 → 帮助 → 「再看一遍新手引导」 plays it again. That
     first day 今日's notices step aside (html.tour-day: one notice at a time). ---------- */
  const TOUR_STEPS = {
    // learner: 新手引导 v2 (08-intro.js) since 2026-11-26
    teacher: [
      { at: ['#tNew'], t: '建一个班', d: '写上班级名，点「新建班级」。建好以后可以改名。' },
      { at: ['#view .cls-row .muted'], t: '把邀请码发给学生', d: '每个班有一个 6 位邀请码。学生在「我的 → 班级」里输入，就加进来了。',
        alt: '建好班以后，班级上会显示 6 位邀请码。发给学生，学生在「我的 → 班级」里输入就加进来了。' },
      { at: ['#view .cls-row'], t: '看全班汇总', d: '人数够了以后，点班级就能看全班这一周学了多少、哪里卡住。只看全班的数字，看不到单个学生。',
        alt: '人数够了以后，点班级就能看全班这一周学了多少、哪里卡住。只看全班的数字，看不到单个学生。', last: '知道了' },
    ],
  };
  const TOUR = { name: '', i: 0, again: false, el: null, prev: null, at: null };
  if (load('flow-tour-day') === new Date().toDateString()) document.documentElement.classList.add('tour-day');

  // After each page: 今日 (我的班级 for a 老师账号) asks once per page load whether this account still has its tour.
  async function tourMaybe() {
    coachFollow();  // 08-intro.js: the page the first step opened
    if (TOUR.el || INTRO.el) return;
    const h = location.hash.replace(/^#\/?/, '');
    // a guest: the steps once on this browser (from 欢迎, 09-start.js); on 今日 only to go on from where they were left
    if (!S.user) { if (h === '' && !load('flow-intro') && introLeftAt()) introSoon({ from: introLeftAt() }); return; }
    const name = S.user.teacher ? 'teacher' : 'learner';
    if (!(S.user.teacher ? h === '' || h === 'teach' : h === '')) return;
    // a learner gets the steps (新手引导 v2, 08-intro.js); a 老师账号 keeps pointing at 我的班级
    if (tourMaybe.replay === name) { tourMaybe.replay = ''; if (name === 'learner') introSoon({ again: true }); else tourSoon(name, true, 350); return; }
    if (tourMaybe.asked === S.user.id) return;
    tourMaybe.asked = S.user.id;  // once per page load and account (another account signing in here is asked again)
    let d = null; try { d = await api('/api/next/tour'); } catch (e) { return; }
    if (!d || !d[name]) return;
    if (name === 'teacher') { tourSoon(name, false, 500); return; }  // after the page has settled
    // seen or skipped here before signing up: kept on the new account, not shown again
    const was = load('flow-intro');
    if (was === 'done' || was === 'skip') { api('/api/next/tour', { tour: 'learner', result: was, step: 1 }).catch(() => {}); return; }
    introSoon({ from: introLeftAt() });
  }
  // the steps, after the start animation and with no sheet open; how they ended kept on the account (a guest: this browser)
  function introSoon(opts) {
    const at = location.hash;
    setTimeout(function wait() {
      if (INTRO.el || location.hash !== at || !sheetEl.hidden) return;
      const sp = document.getElementById('splash');
      if (sp && !sp.classList.contains('out')) { setTimeout(wait, 150); return; }
      if (!opts.again) { save('flow-tour-day', new Date().toDateString()); document.documentElement.classList.add('tour-day'); }
      introStart(opts, (result, step) => {
        if (result === 'later') return;  // to 登录 / 注册: goes on from this step afterwards
        if (S.user) api('/api/next/tour', { tour: 'learner', result, step, again: !!opts.again }).catch(() => {});
        if (!opts.again) save('flow-intro', result);
        // 一次性 (one-time-list.md): what the steps said is not said again on its own (右滑认识, 第一次用？看操作指南)
        if (result === 'done') { TIPS.mark('swipe-tip'); TIPS.mark('guide'); }
        if (!opts.again) introThen(result);  // the first time only: 今日's first step done together
      });
    }, opts.again ? 300 : 450);
  }
  // after the start animation (09-start.js) has gone, and only on the page it was meant for, with no sheet open
  function tourSoon(name, again, ms) {
    const at = location.hash;
    setTimeout(function wait() {
      if (TOUR.el || location.hash !== at || !sheetEl.hidden) return;
      const sp = document.getElementById('splash');
      if (sp && !sp.classList.contains('out')) { setTimeout(wait, 150); return; }
      tourStart(name, again);
    }, ms);
  }
  // 我的 → 帮助 → 再看一遍新手引导
  function tourAgain() { const name = S.user && S.user.teacher ? 'teacher' : 'learner'; tourMaybe.replay = name; const to = name === 'teacher' ? '#/teach' : '#/'; if (location.hash === to) tourMaybe(); else location.hash = to; }

  function tourStart(name, again) {
    if (TOUR.el) return;
    TOUR.name = name; TOUR.i = 0; TOUR.again = again; TOUR.prev = document.activeElement;
    if (!again) { save('flow-tour-day', new Date().toDateString()); document.documentElement.classList.add('tour-day'); }
    const el = TOUR.el = document.createElement('div');
    el.className = 'tour'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); el.setAttribute('aria-labelledby', 'tourN tourT'); el.setAttribute('aria-describedby', 'tourD');
    el.innerHTML = '<div class="tour-hole" aria-hidden="true"></div><div class="tour-tip"></div>';
    el.addEventListener('keydown', e => {
      if (e.key === 'Escape') { e.preventDefault(); tourStop('skip'); return; }
      if (e.key !== 'Tab') return;  // the card keeps the focus while it is open
      const bs = [...el.querySelectorAll('button')], k = bs.indexOf(document.activeElement);
      e.preventDefault(); bs[(k + (e.shiftKey ? bs.length - 1 : 1)) % bs.length].focus();
    });
    el.addEventListener('click', e => { const b = e.target.closest('[data-tour]'); if (b) (b.dataset.tour === 'skip' ? tourStop('skip') : tourNext()); });
    document.body.appendChild(el); document.body.classList.add('touring');
    addEventListener('resize', tourPlace); addEventListener('scroll', tourPlace, { passive: true });
    tourShow();
  }
  function tourShow() {
    const steps = TOUR_STEPS[TOUR.name], s = steps[TOUR.i], n = steps.length, last = TOUR.i === n - 1;
    const vis = x => x && (x.offsetParent !== null || getComputedStyle(x).position === 'fixed') && x.getBoundingClientRect().width > 0;
    TOUR.at = s.at.map(q => document.querySelector(q)).find(vis) || null;
    if (TOUR.at && getComputedStyle(TOUR.at).position !== 'fixed' && !TOUR.at.closest('.tabs')) TOUR.at.scrollIntoView({ block: 'center', behavior: 'auto' });
    const tip = TOUR.el.querySelector('.tour-tip');
    tip.innerHTML = `<p class="tour-n tiny" id="tourN">第 ${TOUR.i + 1} 步，共 ${n} 步</p><h2 class="tour-t" id="tourT">${esc(s.t)}</h2><p class="small" id="tourD">${esc(TOUR.at || !s.alt ? s.d : s.alt)}</p>
      <div class="tour-acts"><button class="btn ghost small" type="button" data-tour="skip" data-tap="tour-skip">${last ? '关闭' : '跳过'}</button>
        <span class="tour-dots" aria-hidden="true">${steps.map((x, k) => `<i${k === TOUR.i ? ' class="on"' : ''}></i>`).join('')}</span>
        <button class="btn primary small" type="button" data-tour="next" data-tap="tour-next">${last ? esc(s.last || '知道了') : '下一步'}</button></div>`;
    tourPlace();
    tip.querySelector('[data-tour=next]').focus({ preventScroll: true });
    // a screen reader hears the dialog's name on the first step; after that the focus stays in it, so each new step is said
    if (TOUR.i) announce(`第 ${TOUR.i + 1} 步，共 ${n} 步：${s.t}。${TOUR.at || !s.alt ? s.d : s.alt}`);
  }
  // the hole around the button meant, and the card beside it (below when there is room, else above; mid-screen with nothing to point at)
  function tourPlace() {
    if (!TOUR.el) return;
    const hole = TOUR.el.querySelector('.tour-hole'), tip = TOUR.el.querySelector('.tour-tip'), W = innerWidth, H = innerHeight, pad = 6, gap = 12;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let r = TOUR.at && TOUR.at.isConnected ? TOUR.at.getBoundingClientRect() : null;
    // a block taller than the screen leaves room for (今天的计划 on a small phone): its top part is lit, the card under it
    if (r && r.bottom + pad + gap + h > H - 8 && r.top - pad - gap - h < 8) {
      const bottom = H - 8 - h - gap - pad;
      r = bottom - Math.max(r.top, 0) >= 48 ? { left: r.left, width: r.width, top: Math.max(r.top, 0), bottom } : r;
    }
    if (r) Object.assign(hole.style, { left: r.left - pad + 'px', top: r.top - pad + 'px', width: r.width + 2 * pad + 'px', height: r.bottom - r.top + 2 * pad + 'px' });
    else Object.assign(hole.style, { left: W / 2 + 'px', top: H / 2 + 'px', width: '0px', height: '0px' });
    let top = (H - h) / 2, left = (W - w) / 2;
    if (r) {
      left = Math.min(Math.max(16, r.left + r.width / 2 - w / 2), W - w - 16);
      if (r.bottom + pad + gap + h <= H - 8) top = r.bottom + pad + gap;
      else if (r.top - pad - gap - h >= 8) top = r.top - pad - gap - h;
      else top = Math.max(8, Math.min(H - h - 8, r.bottom + pad + gap));
    }
    Object.assign(tip.style, { left: Math.round(left) + 'px', top: Math.round(top) + 'px' });
  }
  function tourNext() {
    const n = TOUR_STEPS[TOUR.name].length;
    if (TOUR.i < n - 1) { TOUR.i += 1; tourShow(); return; }
    const name = TOUR.name; tourStop('done');
    if (name === 'learner') { const go = document.querySelector('#view .go-next'), to = go && go.getAttribute('href'); if (to && to[0] === '#') location.hash = to; }
    else { const f = document.querySelector('#tNew input'); if (f) f.focus(); }
  }
  function tourStop(result) {
    if (!TOUR.el) return;
    api('/api/next/tour', { tour: TOUR.name, result, step: TOUR.i + 1, again: TOUR.again }).catch(() => {});
    // seen through: what it said (where things are, 右滑「认识」) need not be said again (一次性入口, 08-tips.js)
    if (result === 'done' && TOUR.name === 'learner') { TIPS.mark('guide'); TIPS.mark('swipe-tip'); }
    TOUR.el.remove(); TOUR.el = null; TOUR.at = null; document.body.classList.remove('touring');
    removeEventListener('resize', tourPlace); removeEventListener('scroll', tourPlace);
    const back = TOUR.prev && TOUR.prev.isConnected ? TOUR.prev : view; if (back && back.focus) back.focus({ preventScroll: true });
  }
  /* ---------- 启动动画 (r27): on every opening, over the page while it is drawn underneath ---------- */
  // The mark (next.html, styled by 05-start.css) is on screen from the first paint: its five bars rise in about 0.4 s.
  // The first time, the name and line come up under it and it stays about a second; after that only the mark plays, and
  // it leaves as soon as the first page is drawn (at least 0.4 s after the page began, so it never just flickers). A tap
  // skips it; with reduced motion it only fades. If the script never runs, the stylesheet fades it after 3 s.
  const SPLASH = (() => {
    const el = document.getElementById('splash');
    if (!el) return { done() {} };
    const first = !load('flow-splash-seen');
    if (first) { el.classList.add('first'); save('flow-splash-seen', 1); }
    let gone = false;
    const hide = () => {
      if (gone) return; gone = true;
      el.classList.add('out');
      setTimeout(() => el.remove(), REDUCED ? 0 : 300);
    };
    el.addEventListener('click', hide);
    return { done() { setTimeout(hide, Math.max(0, (REDUCED ? 0 : first ? 1000 : 400) - performance.now())); } };
  })();

  /* ---------- 选方向和目标 (r27): once, for a new learner; the same page edits it from 我的 ---------- */
  // One page: what English is for (考试 opens which exam and its date, written to the exam goal of 考试冲刺), then the
  // level to reach, suggested from the exam or the goal. The current level is not asked: until a test says more,
  // materials start one band below the target (level_source 'guess'); 今日 then suggests a test (levelGuessHTML).
  const BANDS = ['A2', 'B1', 'B2', 'C1'];
  const below = t => BANDS[Math.max(0, BANDS.indexOf(t) - 1)] || 'B1';
  async function welcome(edit) {
    if (!S.meta || !S.meta.targets) S.meta = await api('/api/next/meta');
    const M = S.meta, cur = edit ? ((S.home && S.home.profile) || S.guest || {}) : {};
    // 学英语为了什么: more than one may be chosen (the user, 2026-11-26), up to three; the first is the main one (goal)
    const st = { goals: (cur.goals && cur.goals.length ? cur.goals : cur.goal ? [cur.goal] : []).slice(0, 3), goal: '', exam: cur.exam || '', date: cur.exam_date || '', target: cur.target || '', level: cur.level || '',
                 minutes: cur.minutes || 10, themes: (cur.themes || []).slice(), days: cur.weekly_goal || 0 };
    let picked = !!cur.target;  // a target chosen by hand is not replaced by the suggestion
    // 一周学几天 (r28 第 6 段, 每周目标): 5 for an exam, 4 otherwise (save_profile's default) until chosen by hand
    let dayPicked = !!cur.weekly_goal;
    st.goal = st.goals[0] || '';
    const hasExam = () => st.goals.includes('exam');
    const daysFor = () => (hasExam() ? 5 : 4);
    const suggest = () => M.target_for[hasExam() && st.exam ? st.exam : st.goal] || 'B1';
    const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    const radio = (attr, v, on, inner, cls = 'chip') => `<button class="${cls}" type="button" role="radio" data-${attr}="${esc(v)}" aria-checked="${on}">${inner}</button>`;
    document.body.classList.toggle('onboarding', !edit);
    view.innerHTML = `<div class="stack wg">
      <div>${edit ? '<span class="kicker">学习目标和水平</span>' : ''}<h1 class="h1">你学英语主要为了什么？</h1><p class="muted small">可以多选，最多 3 个，第一个选的算主要目标；之后在「我的」里随时能改。</p></div>
      <div class="wg-goals" role="group" aria-label="学英语为了什么，可以多选">${[...M.goals].sort((a, b) => (b.id === 'exam') - (a.id === 'exam')).map(g => `<button class="opt" type="button" data-goal="${esc(g.id)}" aria-pressed="${st.goals.includes(g.id)}">
        <span class="l">${esc(g.label)}</span><span class="d">${esc((M.goal_hints || {})[g.id] || '')}</span><span class="main" hidden>主要</span></button>`).join('')}</div><span class="sr-only" id="wgMainNote">主要目标</span>
      <section class="stack-s" id="wgExam" aria-labelledby="wgExamH" hidden><h2 class="h3" id="wgExamH">准备哪个考试？</h2>
        <div class="chips" role="radiogroup" aria-labelledby="wgExamH">${M.exams.map(e => radio('exam', e.id, e.id === st.exam, esc(e.short))).join('')}</div>
        <div class="stack-s" id="wgDate" hidden><label class="small" for="wgDateIn">考试日期（选填，不确定可以先空着）</label><input type="date" id="wgDateIn" min="${today}" value="${esc(st.date)}"></div></section>
      <section class="stack-s" aria-labelledby="wgTargetH"><h2 class="h3" id="wgTargetH">想达到什么水平？</h2>
        <div class="wg-targets" role="radiogroup" aria-labelledby="wgTargetH">${M.targets.map(t => radio('target', t.id, t.id === st.target,
          `<b>${t.id}</b><span class="d">${esc(t.label)}</span><span class="rec" hidden>推荐</span>`, 'opt')).join('')}</div>
        <p class="tiny muted">${edit ? '' : '现在的水平不用先测：文章先按比目标低一档挑，以后在「能力」里测一下就更准。'}</p></section>
      <section class="stack-s" aria-labelledby="wgDaysH"><h2 class="h3" id="wgDaysH">一周大概能学几天？</h2>
        <div class="chips wg-days" role="radiogroup" aria-labelledby="wgDaysH">${[2, 3, 4, 5, 6, 7].map(d => radio('days', d, d === st.days, `${d} 天`)).join('')}</div>
        <p class="tiny muted">学一步材料或复习几个词就算一天，哪周没学够也不会清零。</p></section>
      ${edit ? `<section class="stack-s" aria-labelledby="wgLevelH"><h2 class="h3" id="wgLevelH">现在的水平</h2>
          <div class="chips" role="radiogroup" aria-labelledby="wgLevelH">${M.levels.map(l => radio('level', l.id, l.id === st.level, `${l.id} ${esc(l.label)}`)).join('')}</div>
          <p class="tiny muted">${cur.level_source === 'guess' ? '这是按目标估的。' : cur.level_source === 'placed' ? '这是语法起点小测给的。' : ''}<a class="link" href="#/radar">去能力里测一下</a>，比自己估更准。</p></section>
        <section class="stack-s" aria-labelledby="wgMinH"><h2 class="h3" id="wgMinH">每天想学多久？</h2>
          <div class="chips" role="radiogroup" aria-labelledby="wgMinH">${M.minutes.map(m => radio('min', m, m === st.minutes, `${m} 分钟`)).join('')}</div></section>
        <section class="stack-s" aria-labelledby="wgThemeH"><h2 class="h3" id="wgThemeH">感兴趣的话题</h2><p class="tiny muted">可以多选，不选就每天随机。</p>
          <div class="chips" role="group" aria-labelledby="wgThemeH">${M.themes.map(t => `<button class="chip" type="button" data-theme="${t.id}" aria-pressed="${st.themes.includes(t.id)}">${esc(t.label)}</button>`).join('')}</div></section>` : ''}
      <p class="small wg-plan" id="wgPlan" aria-live="polite" hidden></p>
      <div class="wg-go stack-s"><button class="btn primary block" id="wgGo" type="button" data-tap="welcome-start">${edit ? '保存' : '开始学习'}</button>
        <p class="tiny muted tc" id="wgNeed" aria-live="polite" hidden></p>
        ${edit ? '<a class="btn ghost block" href="#/me">取消</a>' : S.user ? '' : `<div class="wg-acct"><button class="btn block" id="wgReg" type="button" data-tap="welcome-register">注册账号</button>
          <button class="btn block" id="wgLogin" type="button" data-tap="welcome-login">已有账号？登录</button></div>
        <p class="tiny muted tc">不注册也能先学；注册以后，进度换手机、换电脑都在。</p>`}</div>
      </div>`;  // 认识语流 (#32) is in 我的 → 帮助 → 更多: 新手引导 v2 says what it said (one-time-list.md #3)
    const sync = () => {
      if (!picked) st.target = suggest();
      if (!dayPicked) st.days = daysFor();
      view.querySelectorAll('[data-days]').forEach(b => b.setAttribute('aria-checked', String(Number(b.dataset.days) === st.days)));
      st.goal = st.goals[0] || '';
      view.querySelectorAll('[data-goal]').forEach(b => {
        const on = st.goals.includes(b.dataset.goal), main = on && st.goals.length > 1 && b.dataset.goal === st.goal;
        b.setAttribute('aria-pressed', String(on)); b.querySelector('.main').hidden = !main;
        // a screen reader hears which one is the main goal (the corner says 主要)
        if (main) b.setAttribute('aria-describedby', 'wgMainNote'); else b.removeAttribute('aria-describedby');
      });
      view.querySelectorAll('[data-exam]').forEach(b => b.setAttribute('aria-checked', String(b.dataset.exam === st.exam)));
      view.querySelectorAll('[data-target]').forEach(b => { b.setAttribute('aria-checked', String(b.dataset.target === st.target)); b.querySelector('.rec').hidden = !st.goal || b.dataset.target !== suggest(); });
      document.getElementById('wgExam').hidden = !hasExam();
      document.getElementById('wgDate').hidden = !hasExam() || !st.exam;
      document.getElementById('wgGo').disabled = !st.goals.length;
      // with an exam and no word plan yet, starting makes one on the exam's book (save_profile): said here first
      const e = hasExam() && M.exams.find(x => x.id === st.exam), plan = document.getElementById('wgPlan');
      const hasPlan = !!(S.home && S.home.stats && S.home.stats.vocab_plan);
      plan.hidden = !e || hasPlan;
      if (e && !hasPlan) plan.textContent = S.user ? `${edit ? '保存' : '开始学习'}后会为你建好《${e.book_title}》每天 10 个新词，可以在「单词」里改。`
        : `登录后会为你建好《${e.book_title}》每天 10 个新词的背词计划，可以在「单词」里改。`;
      const need = document.getElementById('wgNeed'); need.textContent = st.goals.length ? '' : '先选一个目标'; need.hidden = !!st.goals.length;
    };
    view.querySelectorAll('[data-goal]').forEach(b => b.onclick = () => {
      const g = b.dataset.goal;
      if (st.goals.includes(g)) st.goals = st.goals.filter(x => x !== g);
      else if (st.goals.length >= 3) { toast('最多选 3 个，先去掉一个再选'); return; }
      else st.goals = st.goals.concat(g);
      sync();
    });
    view.querySelectorAll('[data-exam]').forEach(b => b.onclick = () => { st.exam = b.dataset.exam; sync(); });
    view.querySelectorAll('[data-target]').forEach(b => b.onclick = () => { st.target = b.dataset.target; picked = true; sync(); });
    view.querySelectorAll('[data-days]').forEach(b => b.onclick = () => { st.days = Number(b.dataset.days); dayPicked = true; sync(); });
    view.querySelectorAll('[data-level]').forEach(b => b.onclick = () => { st.level = b.dataset.level; view.querySelectorAll('[data-level]').forEach(x => x.setAttribute('aria-checked', String(x === b))); });
    view.querySelectorAll('[data-min]').forEach(b => b.onclick = () => { st.minutes = Number(b.dataset.min); view.querySelectorAll('[data-min]').forEach(x => x.setAttribute('aria-checked', String(x === b))); });
    view.querySelectorAll('[data-theme]').forEach(b => b.onclick = () => { const t = b.dataset.theme; st.themes = st.themes.includes(t) ? st.themes.filter(x => x !== t) : st.themes.concat(t); b.setAttribute('aria-pressed', String(st.themes.includes(t))); });
    // 注册 and 登录 side by side, one as plain to see as the other (the owner on WeChat, 2026-11-25: 「注册一般和登录是一级的」)
    const login = document.getElementById('wgLogin'); if (login) login.onclick = () => openLogin();
    const reg = document.getElementById('wgReg'); if (reg) reg.onclick = () => openLogin('', 'reg');
    sync();
    document.getElementById('wgGo').onclick = async e => {
      const btn = e.currentTarget; btn.disabled = true;
      const exam = hasExam() ? st.exam : '', date = exam ? document.getElementById('wgDateIn').value : '';
      // the level: from the starting check if it was just taken; from 我的 as chosen (or kept); otherwise one band below the target
      const level = S.placed ? S.placed : edit ? st.level || below(st.target) : below(st.target);
      const source = S.placed ? 'placed' : edit && st.level === cur.level ? (cur.level_source || 'self') : edit && st.level ? 'self' : 'guess';
      const prof = { goal: st.goal, goals: st.goals, target: st.target, level, level_source: source, themes: st.themes, minutes: st.minutes, exam, exam_date: date, weekly_goal: st.days };
      try { await welcomeSave(prof, edit); } catch (x) { btn.disabled = false; toast(x.message); return; }
      location.hash = edit ? '#/me' : '#/';
    };
    // 新手引导 v2 (08-intro.js): a new learner gets 欢迎 and these choices one at a time over this page, once (跳过: this page)
    if (!edit && !hasProfile() && !load('flow-intro')) introSoon({ setup: true, from: introLeftAt() });
  }
  // the profile saved (this page, or the steps of 新手引导 v2); an error is thrown to the caller
  async function welcomeSave(prof, edit) {
    let made = null;
    if (S.user) made = (await api('/api/next/profile', prof)).plan_made;
    S.placed = ''; S.guest = { ...(S.guest || {}), ...prof }; save('flow-next-guest', S.guest);
    document.body.classList.remove('onboarding');
    await refreshHome(); S.homeFresh = true;
    if (made) toast(`已为你建好《${made.title}》每天 ${made.daily_new} 个新词`); else if (edit) toast('已保存');
    return made;
  }

  // 今日: the level was guessed from the target and nothing has been tested yet; one notice suggests a test (the
  // 能力 tab comes in r28; until then 能力雷达's test page). 「以后再说」 puts it off for a week.
  function levelGuessHTML(h) {
    if (!h.level_guess || Date.now() - (load('flow-level-hint-later') || 0) < 7 * 864e5) return '';
    return `<div class="card sunk section notice stack-s" id="levelGuess"><b>文章先按比目标低一档挑的（${esc(h.level)}）</b>
      <span class="small">去能力里测一下现在的水平，推荐会更准，每天的计划也会跟着调整。</span>
      <div class="row"><a class="btn small primary" href="#/radar/test" data-tap="notice-test">去能力里测一下</a><button class="btn small ghost" id="lgLater" type="button">以后再说</button></div></div>`;
  }
  function bindLevelGuess(redraw) {
    const b = document.getElementById('lgLater'); if (b) b.onclick = () => { save('flow-level-hint-later', Date.now()); redraw(); };
  }
  /* ---------- today ---------- */
  function greeting() { const h = new Date().getHours(); return h < 5 ? '夜深了' : h < 11 ? '早上好' : h < 14 ? '中午好' : h < 18 ? '下午好' : '晚上好'; }
  function stepDots(steps) { return `<span class="steps-dots" aria-label="已完成 ${steps.length} / 4 步">${STEPS.map(s => `<i class="${steps.includes(s) ? 'on' : ''}"></i>`).join('')}</span>`; }
  // 精选, or 重学 (a featured text recommended again) or 简版 (an older, shorter text): the kind of text, on every card
  function kindPill(m) { return m.redo ? '<span class="pill">重学</span>' : m.brief ? '<span class="pill">简版</span>' : m.featured ? '<span class="pill feat">精选</span>' : ''; }
  // How many featured texts are left at this level, from seven down; once none are, what 今日 recommends instead
  function featLeftHTML(h) {
    const n = h.featured_left;
    if (n == null || n > 7) return '';
    const msg = n > 0 ? `这一级（${h.level}）的精选还剩 ${n} 篇没学。${h.level_up ? `学完以后先推 ${h.level_up} 的精选，再推精读重学。` : '学完以后先推精读重学，每周也会加新的。'}`
      : h.level_up ? `这一级（${h.level}）的精选你都学过了：先推 ${h.level_up} 的精选，也可以<a class="link" href="#/welcome/edit">换个水平</a>。`
      : `${h.level} 的精选你都学过了：先精读重学，每周也会加新的。`;
    return `<p class="tiny muted feat-left">${msg}</p>`;
  }
  function reasonsHTML(m) { return m.reasons && m.reasons.length ? `<div class="reasons">${m.reasons.map(r => `<span class="reason">${esc(r)}</span>`).join('')}</div>` : ''; }
  function miniCard(m, tag) {
    return `<a class="card flat mini" href="#/m/${encodeURIComponent(m.id)}"><span class="t">${esc(m.title)}</span>
      <span class="meta">${kindPill(m)}${tag ? `<span class="pill amber">${esc(tag)}</span>` : ''}<span class="pill">${m.level}</span></span>
      <span class="p">${esc(m.preview)}</span><span class="tiny muted">${esc(m.theme_label)} · ${m.words} 词 · 约 ${m.minutes} 分钟${m.ai ? ' ' + aiTag() : ''}</span>${m.steps.length ? stepDots(m.steps) : ''}${reasonsHTML(m)}</a>`;
  }
  async function today(fresh) {
    // Drawn at once from the home data already here; the server's answer follows and, if anything changed, the page is
    // drawn again quietly (05-data.js). Only the very first visit, with nothing here yet, waits.
    if (!fresh) {
      if (S.home) { const drawnFor = location.hash; refreshHome().then(changed => { if (changed) redrawQuietly(drawnFor); }).catch(() => {}); }
      else await refreshHome();
    }
    const h = S.home, pick = h.today[0], st = h.stats;
    const name = S.user ? S.user.username : '';
    const path = S.user && h.path, weekN = st ? st.week.filter(d => d.active).length : 0;
    // A learner with a plan: 今日 in the look they chose (列表 or 卡片, 13-today-views.js), the switch beside the
    // greeting. Without a plan (a guest, or no goal set yet): one clear first action, today's article.
    let top = '', readId = '';
    if (path) readId = planFacts(h).readId;
    else if (pick) {
      top = `<div class="hello"><h1 class="h1">今天学一篇，用上一句。</h1><span class="muted small">按「${esc(h.level_label)}（${h.level}）」为你挑选 · <a class="link" href="#/welcome/edit">调整</a></span></div>
        <article class="card hero"><div class="meta">${kindPill(pick)}<span class="pill green">今日推荐</span><span class="pill">${pick.level}</span><span class="pill">${esc(pick.theme_label)}</span></div>
        <h2 class="title">${esc(pick.title)}</h2>${pick.title_en ? `<div class="title-en">${esc(pick.title_en)}</div>` : ''}<p class="preview">${esc(pick.preview)}</p>${reasonsHTML(pick)}
        <span class="muted small">${pick.words} 词 · 约 ${pick.minutes} 分钟 · 听、读、理解、用出来${pick.ai ? ' ' + aiTag() : ''}</span>
        <a class="btn primary block go-next" href="#/m/${encodeURIComponent(pick.id)}">开始学习<span aria-hidden="true">→</span></a></article>`;
    } else top = '<div class="empty">今天没有可推荐的材料了。</div>';
    const resume = h.resume && h.resume.id !== readId ? h.resume : null, news = h.news && h.news.id !== readId ? h.news : null;
    const more = h.today.filter(m => m.id !== readId && (path || m !== pick) && (!resume || m.id !== resume.id) && (!news || m.id !== news.id)).slice(0, 3);
    const deck = path && todayView() === 'cards' ? todayCards(h, news) : null;
    const notes = `${announceHTML(h) || updateCardHTML(h)}${trialSurveyHTML(h)}`;
    view.innerHTML = `<div class="greet-row"><span class="kicker greet">${greeting()}${name ? `，<span class="nm">${esc(name)}</span>` : ''}</span>
        ${path ? todaySwitchHTML() : st && !st.habit ? `<span class="wk" title="本周学了 ${weekN} 天"><span class="tiny muted">本周 ${weekN} 天</span><span class="week" aria-hidden="true">${st.week.map(d => `<span class="${d.active ? 'on' : ''}"></span>`).join('')}</span></span>` : ''}</div>
      ${deck ? `<div class="tv-notes">${notes}<div id="notice"></div></div>${deck.html}` : `${notes}
      ${path ? todayListHTML(h, news) : top + weekCardSlot()}
      <div id="notice"></div>
      ${S.user && !path ? vocabHome(st) : ''}
      <section class="section" aria-labelledby="mTitle"><div class="section-head"><h2 class="h2" id="mTitle">也可以读</h2><a class="link small hit44" href="#/welcome/edit">按 ${h.level} 挑选 · 调整</a></div>${featLeftHTML(h)}
        <div class="mlist">${resume ? mrow(resume, ['继续', 'green'], `#/m/${encodeURIComponent(resume.id)}/${nextStep(resume.steps)}`, 'home-resume') : ''}${more.map(m => mrow(m, null, '', 'home-pick')).join('')}
          <a class="mrow more" href="#/library" data-tap="home-more"><span class="t"><b>更多材料</b><span class="tiny muted">按话题和级别挑一篇</span></span><span class="go" aria-hidden="true">›</span></a></div></section>`}`;
    fillNotice(h);
    bindAnnounce(h); bindUpdateCard(h); bindTrialSurvey();  // 「语流更新了」 where a 公告 would be (83-updates.js)
    if (path) { bindTodaySwitch(); if (deck) mountDeck(deck.start); else bindTodayList(); }  // after the reminders: the deck fits under them
    EGG.bindGreeting(view.querySelector('.greet-row .greet'));  // 小彩蛋 (14-today-egg.js): hold the greeting
    if (path) EGG.planDone(h.path);  // and once, by itself, the first time today's plan is seen all done
    bindLine(h);  // 今日好句 (12-daily-line.js)
    const ro = document.getElementById('remindOnce'); if (ro) ro.onclick = () => remindOnce();  // 这次什么时候复习 (50-words.js)
    mountWeekCards(view);  // 这周进步 (11-progress.js)
    if (st && st.habit) cheerWeek(st.habit);
    const nextRead = readId || (pick && pick.id);
    if (nextRead) setTimeout(() => preloadMaterial(nextRead), 600);  // after the page is drawn, not before
  }
  // 欢迎回来 (r28 第 2 段): after three days or more away, the day back is short, and the plan says so first.
  function backHTML(p, next) {
    const b = p.back; if (!b) return '';
    const left = b.left ? (b.catch_days ? `单词还剩 ${b.left} 个，大约 ${b.catch_days} 天补完。` : `单词还有 ${b.left} 个，之后几天慢慢补上。`) : '';
    return `<div class="tp-back" role="status"><b>欢迎回来</b><span class="small">${next ? `你 ${b.days} 天没学了，没关系。今天只做 ${p.total} 件事，约 ${p.must_minutes} 分钟。` : '今天的几件事做完了，明天照常。'}${left}</span></div>`;
  }
  // Past the day's minutes by a fifth with 必做 not done: said once a day, under the plan's button, and nothing is stopped.
  // It stays for the quiet redraw and a quick look away (two minutes), then not again that day.
  function overLineHTML(p, next) {
    if (!p.over || !next) return '';
    const day = new Date().toDateString(), said = load('flow-over-said');
    if (said && said.day === day && Date.now() - said.t > 120000) return '';
    if (!said || said.day !== day) save('flow-over-said', { day, t: Date.now() });
    return `<p class="tp-over small" role="status">今天已经学了约 ${p.studied} 分钟，超过你定的 ${p.minutes} 分钟，剩下的可以留到明天。</p>`;
  }
  function habitSheet() {
    const hb = (S.home && S.home.stats && S.home.stats.habit) || { goal: 4 };
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">每周目标</h2>
      <p class="muted small">一周里学够这么多天就算达成。哪天没空也没关系，不会清零；坚持的是一周一周，不是天天打卡。</p>
      <div class="chips" role="radiogroup" aria-label="每周学几天">${[2, 3, 4, 5, 6, 7].map(n => `<button class="chip" type="button" role="radio" data-goal="${n}" aria-checked="${hb.goal === n}">每周 ${n} 天</button>`).join('')}</div>
      <p class="tiny muted">学一步材料或复习几个词，都算学了这一天。</p><button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      card.querySelectorAll('[data-goal]').forEach(b => b.onclick = async () => {
        try {
          const r = await api('/api/next/habit', { goal: Number(b.dataset.goal) });
          if (S.home && S.home.stats) S.home.stats.habit = r.habit;
          card.querySelectorAll('[data-goal]').forEach(x => x.setAttribute('aria-checked', String(x === b)));
          const v = document.getElementById('meHabitV'); if (v) v.textContent = `每周 ${r.habit.goal} 天`;
          refreshWeekCard();
          toast(`每周目标：${r.habit.goal} 天`);
        } catch (e) { toast(e.message); }
      });
    });
  }
  // The week's goal reached: said once, the first time 今日 shows it that week.
  function cheerWeek(hb) {
    if (!hb.met || load('flow-habit-cheered') === hb.monday) return;
    save('flow-habit-cheered', hb.monday);
    toast(hb.weeks > 1 ? `本周目标达成！一共达成 ${hb.weeks} 周了` : '本周目标达成！');
  }
  // A material as one row: title, then level, topic and time; a pill says why it is on the list. tag false: no pill,
  // where the section or the filter above already says what it would (全部材料 under 精选, B9's audit P2-E7).
  function mrow(m, tag, href, tapKey) {
    return `<a class="mrow" href="${href || '#/m/' + encodeURIComponent(m.id)}"${tapKey ? ` data-tap="${tapKey}"` : ''}><span class="t"><b>${esc(m.title)}</b>
      <span class="tiny muted">${m.level} · ${esc(m.theme_label)}${m.minutes ? ` · 约 ${m.minutes} 分钟` : ''}${m.steps && m.steps.length ? ` · 学了 ${m.steps.length}/4 步` : ''}${OFF.has(m.id) ? ' · 已存到本机' : ''}${m.ai ? ' ' + aiTag() : ''}</span></span>
      ${tag === false ? '' : tag ? `<span class="pill ${tag[1]}">${tag[0]}</span>` : kindPill(m)}<span class="go" aria-hidden="true">›</span></a>`;
  }
  // 公告 from the operators (xmc.hk console, r26): one line at the very top of 今日, for everyone, until it ends.
  // 「知道了」 (or going to its page) hides that one on this phone; a new one shows again.
  function announceHTML(h) {
    const a = h.announce;
    if (!a || load('flow-announce-seen') === a.id) return '';
    return `<div class="card sunk section notice announce stack-s" id="announce" role="status"><b>${esc(a.text)}</b>
      <div class="row">${a.link ? `<a class="btn small primary" href="${esc(a.link)}" data-tap="announce-open">去看看</a>` : ''}<button class="btn small ghost" id="annOk" type="button">知道了</button></div></div>`;
  }
  // 班级试用: three weeks in a class, a quiet line asks for the anonymous trial survey (survey_service.TRIAL) until it is
  // answered (survey.js notes it on this phone) or closed. Nothing on the server says who answered.
  function trialSurveyHTML(h) {
    if (!h.trial_survey || load('flow-trial-survey')) return '';
    return `<div class="card sunk section notice tsurvey" id="trialSv" role="status"><span>班级试用几周了，花 2 分钟填一份匿名问卷？</span>
      <div class="row"><a class="btn small primary" href="/survey?s=trial" data-tap="trial-survey">去填写</a><button class="btn small ghost" id="tsClose" type="button">不用了</button></div></div>`;
  }
  function bindTrialSurvey() {
    const b = document.getElementById('tsClose');
    if (b) b.onclick = () => { save('flow-trial-survey', 'closed'); document.getElementById('trialSv').remove(); };
  }
  function bindAnnounce(h) {
    const box = document.getElementById('announce'); if (!box) return;
    const seen = () => { save('flow-announce-seen', h.announce.id); box.remove(); };
    document.getElementById('annOk').onclick = seen;
    const go = box.querySelector('a'); if (go) go.addEventListener('click', () => save('flow-announce-seen', h.announce.id));
  }
  // One notice at a time under the plan, the most useful first: sign in (guest), a level that fits better, an email
  // for getting back in, then the guide for the first few days. Putting one off brings up the next.
  function noticeHTML(h) {
    if (!S.user) return `<div class="card sunk section notice stack-s"><b>登录后，进度和收藏的表达会保存下来</b><span class="muted small">不登录也可以听、读和做理解题。</span><div><button class="btn small" id="loginCta" data-tap="notice-login">登录 / 注册</button></div></div>`;
    if (h.suggest && Date.now() - (load('flow-next-suggest-skip') || 0) > 7 * 864e5) return suggestHTML(h.suggest);
    const lg = levelGuessHTML(h); if (lg) return lg;  // 09-start.js: a level guessed from the target, no test yet
    const hb = h.stats && h.stats.habit;  // on Monday and Tuesday: how last week went, once
    // r28: two weeks in a row short of the goal, each with some study: the goal the learner keeps, one tap (instead of 上周学了…)
    if (hb && hb.lower && (hb.days[0].today || hb.days[1].today) && load('flow-goal-lower') !== hb.monday) {
      const [a, b] = hb.lower.weeks, g = hb.lower.goal;
      return `<div class="card sunk section notice stack-s" id="goalLower"><b>${a === b ? `最近两周每周学 ${a} 天` : `最近两周学了 ${a} 天和 ${b} 天`}，要不要把目标改成每周 ${g} 天？</b>
        <span class="small">目标定在做得到的地方，每周都能达成。以前达成的周不会被扣，以后也可以在「我的」→「每周目标」里改回来。</span>
        <div class="row"><button class="btn small primary" id="glYes" type="button" data-tap="notice-goal-lower">改成每周 ${g} 天</button><button class="btn small ghost" id="glNo" type="button">不用，保持 ${hb.goal} 天</button></div></div>`;
    }
    // 上周小结 (Monday to Sunday: the weekly goal's 本周); its button opens 周报, which is the last 7 days (B9 / A0, 2026-11-25:
    // one word, one meaning), so it says 看周报, not 看上周报告
    if (hb && hb.last_week.done && (hb.days[0].today || hb.days[1].today) && load('flow-habit-lastweek') !== hb.monday)
      return `<div class="card sunk section notice stack-s" id="lastWeek"><b>${hb.last_week.met ? `上周学了 ${hb.last_week.done} 天，目标达成了 🎉` : `上周学了 ${hb.last_week.done} 天，离目标还差 ${hb.goal - hb.last_week.done} 天`}</b>
        <span class="small">${hb.last_week.met ? '这周接着来。' : '没关系，这周重新开始，学一步材料或复习几个词就算一天。'}</span>
        <div class="row"><a class="btn small primary" href="#/report" data-tap="notice-week">看周报</a><button class="btn small ghost" id="lwOk" type="button">知道了</button></div></div>`;
    const mail = mailNudgeHTML(); if (mail) return mail;
    if (installNudgeDue(h)) return `<div class="card sunk section notice stack-s" id="installNudge"><b>把语流放到手机桌面</b><span class="small">像 App 一样一点就开，全屏；听过的音频网络差的时候也能复习。</span>
      <div class="row"><button class="btn small primary" id="inGo" type="button" data-tap="notice-install">怎么放</button><button class="btn small ghost" id="inLater" type="button">以后再说</button></div></div>`;
    // 一次性 (08-tips.js): gone for good once tapped, the 操作指南 opened, or the 新手引导 seen through (also on another device)
    if ((!h.stats || (h.stats.materials_done || 0) < 3) && tipSeen('guide') === false) return `<a class="card sunk section notice guide-hint" href="#/guide" data-tap="notice-guide" data-tip-seen="guide"><span class="stack-s"><b>第一次用？看操作指南</b><span class="small muted">每个页面怎么用、按哪里，一步一步讲清楚。</span></span><span class="go" aria-hidden="true">›</span></a>`;
    return '';
  }
  function fillNotice(h) {
    const slot = document.getElementById('notice'); if (!slot) return;
    slot.innerHTML = noticeHTML(h);
    const cta = document.getElementById('loginCta'); if (cta) cta.onclick = () => openLogin();
    if (h.suggest) bindSuggest(h, () => fillNotice(h));
    bindLevelGuess(() => fillNotice(h));
    bindMailNudge(() => fillNotice(h));
    const gy = document.getElementById('glYes'), gn = document.getElementById('glNo'), hb = h.stats && h.stats.habit;
    const glDone = () => { save('flow-goal-lower', hb.monday); save('flow-habit-lastweek', hb.monday); fillNotice(h); };  // said once a week
    if (gn) gn.onclick = glDone;
    if (gy) gy.onclick = async () => {
      try {
        const r = await api('/api/next/habit', { goal: hb.lower.goal });
        h.stats.habit = r.habit;
        refreshWeekCard();
        toast(`每周目标：${r.habit.goal} 天`);
        save('flow-goal-lower', r.habit.monday); save('flow-habit-lastweek', r.habit.monday); fillNotice(h);
      } catch (e) { toast(e.message); }
    };
    const lw = document.getElementById('lwOk'); if (lw) lw.onclick = () => { save('flow-habit-lastweek', h.stats.habit.monday); fillNotice(h); };
    const lwr = document.querySelector('#lastWeek a'); if (lwr) lwr.addEventListener('click', () => save('flow-habit-lastweek', h.stats.habit.monday));
    const ig = document.getElementById('inGo'), il = document.getElementById('inLater');
    if (ig) ig.onclick = installSheet;
    if (il) il.onclick = () => { save('flow-install-later', Date.now()); fillNotice(h); };
  }
  function vocabHome(st) {
    if (!st) return '';
    const n = st.due + st.new;
    if (!st.vocab_plan && !n) return `<a class="card flat section mini" href="#/cards"><span class="t">背单词</span><span class="pill">按遗忘曲线</span><span class="p">选一本词书，每天几个新词；例句来自你读的文章，还能听原文录音。</span></a>`;
    return `<div class="card section due"><div><div class="kicker">单词</div><div>${n ? `复习 <b>${st.due}</b> · 新词 <b>${st.new}</b>` : '今天的单词都完成了'}</div>
      <div class="muted small">${n ? `大约 ${st.minutes} 分钟` : '明天见'}</div></div>${n ? '<a class="btn primary" href="#/review">开始</a>' : '<a class="btn" href="#/cards">查看</a>'}</div>`;
  }
  function nextStep(steps) { return STEPS.find(s => !steps.includes(s)) || 'output'; }

  /* ---------- 这周进步 (r27): a card that stands on its own; its details; the Sunday mail ---------- */
  // Four numbers from the learner's own records (progress_service.week): words remembered for the first time (a later
  // day's review still recalled them), texts finished, the share of questions answered right without a hint against
  // last week, and the weekly goal with the weeks reached so far (they only count up). A tap opens the details.
  // A part of its own: any page puts weekCardSlot() where it wants the card and calls mountWeekCards(root). The card
  // draws from the home data when that is here (今日 needs no second request), else it asks for its own
  // (GET /api/next/week?brief=1). It makes no assumption about what is above or below it (今日 today; 能力 later).
  const WEEKDAYS = uiLang() === 'en' ? 'MTWTFSS' : '一二三四五六日';  // i18n: keep (a day's first letter, Monday first)
  function accText(a) {
    const n = a.now, b = a.before;
    const value = n.rate != null ? n.rate + '%' : n.total ? `${n.right}/${n.total}` : '—';
    const sub = n.rate != null && b.rate != null ? (n.rate > b.rate ? `<span class="up">比上周 ↑${n.rate - b.rate}</span>` : n.rate < b.rate ? `比上周 ↓${b.rate - n.rate}` : '和上周持平')
      : n.rate == null ? (n.total ? `满 ${a.min} 题才算` : '这周还没做题') : b.total ? '上周题太少' : '上周没做题';
    return { value, sub };
  }
  // d: {remembered, finished, accuracy, habit} (the brief week). first: the card that carries the id #weekCard.
  function weekCardHTML(d, first) {
    const hb = d && d.habit;
    if (!S.user || !d || !d.remembered || !hb) return '';
    const acc = accText(d.accuracy), weeks = hb.weeks || 0;
    const empty = !d.remembered.now && !d.finished.now && !d.accuracy.now.total && !hb.done;
    const tile = (cls, value, label, sub) => `<span class="wk-tile${cls ? ' ' + cls : ''}"><b>${value}</b><span class="tiny muted">${label}</span><span class="tiny sub">${sub}</span></span>`;
    const label = `这周进步：记住 ${d.remembered.now} 个新词，学完 ${d.finished.now} 篇，做题正确率 ${d.accuracy.now.rate != null ? d.accuracy.now.rate + '%' : '还不够算'}，`
      + `本周学了 ${hb.done} 天，目标 ${hb.goal} 天${weeks ? `，已达成 ${weeks} 周` : ''}。点开看明细`;
    return `<button class="card week-card"${first !== false ? ' id="weekCard"' : ''} type="button" data-tap="home-week" aria-label="${esc(label)}">
      <span class="wk-head"><b>这周进步</b><span class="tiny wk-total${weeks ? ' on' : ''}">${weeks ? `已达成 ${weeks} 周` : '看明细'}<span aria-hidden="true"> ›</span></span></span>
      <span class="wk-tiles">${tile('', d.remembered.now, '记住的新词', `上周 ${d.remembered.before}`)}${tile('', d.finished.now, '学完的文章', `上周 ${d.finished.before}`)}`
      + `${tile('', acc.value, '做题正确率', acc.sub)}${tile('goal' + (hb.met ? ' met' : ''), `${hb.done}<small>/${hb.goal}天</small>`, '每周目标', hb.met ? '达成 ✓' : `还差 ${hb.goal - hb.done} 天`)}</span>
      <span class="wk-foot"><span class="week" aria-hidden="true">${hb.days.map(x => `<span class="${x.active ? 'on' : ''}${x.today ? ' today' : ''}"></span>`).join('')}</span>
        <span class="tiny muted">${empty ? '做完今天的第一步，这里就开始记录' : '数字都来自你自己的学习记录'}</span></span></button>`;
  }
  function weekCardSlot() { return S.user ? '<div class="week-slot" data-week-card></div>' : ''; }
  // Fills every slot under root. fresh: ask the server even when the home data is here (after the goal changed).
  async function mountWeekCards(root, fresh) {
    const slots = [...(root || document).querySelectorAll('[data-week-card]')];
    if (!slots.length || !S.user) return;
    const draw = d => slots.forEach((s, k) => {
      if (!s.isConnected) return;
      s.innerHTML = weekCardHTML(d, k === 0);
      const b = s.querySelector('.week-card'); if (b) b.onclick = weekSheet;
    });
    const st = S.home && S.home.stats;
    if (!fresh && st && st.progress && st.habit) return draw({ ...st.progress, habit: st.habit });
    try {
      const d = await api('/api/next/week?brief=1');
      if (st) { st.progress = { remembered: d.remembered, finished: d.finished, accuracy: d.accuracy, mail: d.mail, monday: d.monday, from: d.from, to: d.to }; st.habit = d.habit; }
      draw(d);
    } catch (e) { if (!slots.some(s => s.firstChild)) slots.forEach(s => s.remove()); }
  }
  // After the weekly goal changed: the card where a page has one, else 今日's 这周 line (13-today-views.js) drawn again
  async function refreshWeekCard() {
    if (document.querySelector('[data-week-card]')) return mountWeekCards(document, true);
    if (!document.getElementById('weekCard') && !document.querySelector('.tv-dc.tv-week')) return;
    try {
      const d = await api('/api/next/week?brief=1'), st = S.home && S.home.stats;
      if (st) { st.progress = { remembered: d.remembered, finished: d.finished, accuracy: d.accuracy, mail: d.mail, monday: d.monday, from: d.from, to: d.to }; st.habit = d.habit; }
      redrawToday();
    } catch (e) { /* the line stays as it was */ }
  }
  async function weekSheet() {
    openSheet('<div class="stack"><h2 class="h2" id="sheetTitle">这周进步</h2><div class="loading"><span class="spin"></span></div></div>');
    let w;
    try { w = await api('/api/next/week'); } catch (e) { closeSheet(); return toast(e.message); }
    if (sheetEl.hidden) return;
    const hb = w.habit, r = w.remembered, f = w.finished, a = accText(w.accuracy), an = w.accuracy.now, ab = w.accuracy.before;
    const day = s => { const [, m, d] = s.split('-').map(Number); return `${m} 月 ${d} 日`; };
    openSheet(`<div class="stack wk-sheet"><div><h2 class="h2" id="sheetTitle">这周进步</h2><span class="small muted">${day(w.from)} – ${day(w.to)} · 数字都来自你自己的学习记录</span></div>
      <section class="wk-sec" aria-label="每周目标"><div class="row between"><b>每周目标</b><span class="small ${hb.met ? 'met' : 'muted'}">本周 ${hb.done} / ${hb.goal} 天${hb.met ? ' · 达成 ✓' : ''}</span></div>
        <div class="wk-days">${hb.days.map((d, k) => `<span class="${d.active ? 'on' : ''}${d.today ? ' today' : ''}"><i aria-hidden="true"></i><span class="tiny">${WEEKDAYS[k]}</span><span class="sr-only">${d.active ? '学了' : '没学'}</span></span>`).join('')}</div>
        <p class="small">${hb.weeks ? `已经有 <b>${hb.weeks}</b> 周达成了目标。` : '还没有达成目标的周。'}一周学够 ${hb.goal} 天就算达成一周；哪天、哪周没学都不会清零，只会越攒越多。</p>
        <p class="tiny muted">学一步材料、复习几个词、做一组练习或读一篇轻松读，都算学了这一天。</p>
        <div><button class="btn small" id="wkGoal" type="button">改每周目标</button></div></section>
      <section class="wk-sec" aria-label="记住的新词"><div class="row between"><b>记住的新词</b><span class="wk-num">${r.now}</span></div>
        <p class="small muted">新词要隔天复习时还记得才算，一个词只算一次。上周 ${r.before} 个。</p>
        ${r.words.length ? `<div class="wk-words">${r.words.map(x => `<span class="pill" lang="en">${esc(x)}</span>`).join('')}</div>` : '<p class="small">这周还没有。今天学的新词，明天复习还记得就会出现在这里。</p>'}</section>
      <section class="wk-sec" aria-label="学完的文章"><div class="row between"><b>学完的文章</b><span class="wk-num">${f.now}</span></div>
        <p class="small muted">做完一篇的理解题就算学完。上周 ${f.before} 篇。</p>
        ${f.titles.length ? `<div class="wk-list">${f.titles.map(t => `<a class="link small" href="#/m/${encodeURIComponent(t.id)}" data-close>《${esc(t.title)}》</a>`).join('')}</div>` : ''}
        ${w.easy && w.easy[0] ? `<p class="small">另外轻松读了 ${w.easy[0]} 篇，共 ${Number(w.easy[1]).toLocaleString()} 个词。</p>` : ''}</section>
      <section class="wk-sec" aria-label="做题正确率"><div class="row between"><b>做题正确率</b><span class="wk-num">${a.value}</span></div>
        <p class="small">${an.total ? `这周做了 ${an.total} 题，对了 ${an.right} 题` : '这周还没做题'}${an.total && an.rate == null ? `，满 ${w.accuracy.min} 题才算正确率` : ''}。${ab.total ? `上周 ${ab.total} 题对 ${ab.right} 题${ab.rate != null ? `（${ab.rate}%）` : ''}。` : '上周没做题。'}</p>
        <p class="tiny muted">算的是不看提示做的理解题、语法题、辨析和考试练习；语法起点小测不算（它会一直加难，错一半是正常的）。</p></section>
      <div class="row"><a class="btn primary" href="#/report" data-close>周报</a><a class="btn" href="#/growth" data-close>我的进步</a><button class="btn ghost" data-close type="button">关闭</button></div></div>`, card => {
      card.querySelector('#wkGoal').onclick = habitSheet;
    });
  }
  // 我的 → 每周进度邮件: on by default for an account with an email; the mail's own link turns it off too.
  const MAILSTATE = { m: null };
  const mailState = () => (S.home && S.home.stats && S.home.stats.progress && S.home.stats.progress.mail) || MAILSTATE.m;
  function weeklyMailLabel() {
    const m = mailState();
    return !m ? '' : !m.email ? '绑定邮箱后可以收' : m.on ? '每周日晚上 8 点' : '已关闭';
  }
  // 我的: the row's value, asked for when the home data does not have it
  function fillMailRow() {
    if (mailState() || !S.user) return;
    api('/api/next/weekly-mail').then(m => { MAILSTATE.m = m; const v = document.getElementById('meMailV'); if (v) v.textContent = weeklyMailLabel(); }).catch(() => {});
  }
  function weeklyMailSheet() {
    const p = S.home && S.home.stats && S.home.stats.progress, m = mailState() || { on: true, email: false };
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">每周进度邮件</h2>
      <p class="small">每周日晚上 8 点，把这周的进步发到你绑定的邮箱：记住的新词、学完的文章、做题正确率和每周目标。这周没学的话，会提醒你一下；连着几周没学就不再发。</p>
      ${m.email ? `<div class="chips" role="radiogroup" aria-label="收不收每周进度邮件">${[[true, '每周收'], [false, '不收']].map(([v, l]) => `<button class="chip" type="button" role="radio" data-mail="${v}" aria-checked="${m.on === v}">${l}</button>`).join('')}</div>
        <p class="tiny muted">每封邮件最下面也有退订链接。</p>`
        : `<p class="small muted">还没有绑定邮箱。</p><div><button class="btn small primary" id="wmBind" type="button">绑定邮箱</button></div>`}
      <button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      card.querySelectorAll('[data-mail]').forEach(b => b.onclick = async () => {
        try {
          const r = await api('/api/next/weekly-mail', { on: b.dataset.mail === 'true' });
          if (p) p.mail = r; MAILSTATE.m = r;
          card.querySelectorAll('[data-mail]').forEach(x => x.setAttribute('aria-checked', String(x === b)));
          const v = document.getElementById('meMailV'); if (v) v.textContent = weeklyMailLabel();
          toast(r.on ? '每周日晚上会收到进度邮件' : '不再发每周进度邮件');
        } catch (e) { toast(e.message); }
      });
      const bind = card.querySelector('#wmBind'); if (bind) bind.onclick = () => bindEmailSheet('');
    });
  }
  // The link in the mail (#/weekly-off/<token>): no sign-in needed. It asks once, so a mail scanner opening the link
  // turns nothing off; 「撤销」 takes it back.
  async function weeklyOffView(token) {
    const draw = (off, err) => {
      view.innerHTML = `<div class="stack weekly-off"><div><span class="kicker">每周进度邮件</span><h1 class="h1">${off ? '已退订' : '退订每周进度邮件'}</h1></div>
        <p class="small">${off ? '以后不会再收到每周进度邮件了。想再收，可以点下面的「撤销」，或者在「我的 → 每周进度邮件」里打开。'
          : '每周日晚上 8 点，语流会把你这周的进步发到绑定的邮箱：记住的新词、学完的文章、做题正确率和每周目标。退订后就不再发。'}</p>
        <div class="row">${off ? '<button class="btn" id="offUndo" type="button">撤销，继续收</button><a class="btn primary" href="#/">去学习</a>'
          : '<button class="btn primary" id="offGo" type="button">退订</button><a class="btn ghost" href="#/">不退订，去学习</a>'}</div>
        <p class="err" role="alert">${esc(err || '')}</p></div>`;
      const send = on => async e => {
        e.currentTarget.disabled = true;
        try { await api('/api/next/weekly-mail/off', { token, on }); draw(!on); toast(on ? '会继续收到每周进度邮件' : '已退订'); }
        catch (x) { draw(on, x.message); }
      };
      const go = document.getElementById('offGo'); if (go) go.onclick = send(false);
      const undo = document.getElementById('offUndo'); if (undo) undo.onclick = send(true);
    };
    draw(false);
  }
  /* ---------- 今日好句 (r27): a row under 还有时间的话 that opens in place (列表), or a card of its own (卡片) ---------- */
  // 好句 (daily_line.py, in the home data): a public-domain line one day, a sentence from a 语流 text the next, with its
  // meaning and where it comes from. 听一遍 (the text's own narration when it has one, else the browser voice),
  // 跟读 (record, play back after the original; signed in, the AI says what to fix) and 收藏 (into review).
  // The sentence (the expression to learn in bold), what it means, where it is from, and 听一遍 · 跟读 · 收藏: opened in
  // place from its row under 还有时间的话 (列表), or the whole of its card (卡片, 13-today-views.js).
  function lineEnHTML(l) {
    let en = esc(l.en).split(' / ').join('<br>');
    if (l.expression) { const k = l.en.toLowerCase().indexOf(l.expression.toLowerCase()); if (k >= 0) en = esc(l.en.slice(0, k)) + '<b>' + esc(l.en.slice(k, k + l.expression.length)) + '</b>' + esc(l.en.slice(k + l.expression.length)); }
    return en;
  }
  function lineBodyHTML(l) {
    return `<p class="lc-en${l.say.length > 100 ? ' long' : ''}" lang="en">${lineEnHTML(l)}</p>
      <p class="lc-zh" data-zh>${esc(l.zh)}</p>${l.note ? `<p class="tiny muted lc-note" data-zh>${esc(l.note)}</p>` : ''}
      <p class="lc-src tiny">${l.kind === 'quote' ? '— ' : ''}${esc(l.source)}${l.label ? ' · ' + esc(l.label) : ''}${l.href ? ` · <a class="link" href="${esc(l.href)}" data-tap="line-read">读原文</a>` : ''}</p>
      <div class="lc-acts"><button class="btn small" id="lcSay" type="button" data-tap="line-say">${ICON.speak}听一遍</button>
        <button class="btn small" id="lcShadow" type="button" data-tap="line-shadow" aria-expanded="false" aria-controls="lcPanel">跟读</button>
        <button class="btn small" id="lcKeep" type="button" data-tap="line-keep">${ICON.star}收藏</button>${aiVoiceNote('AI 合成', 'span')}</div>
      <div id="lcPanel" hidden></div>`;
  }
  function lineDay(l) { return new Date().toDateString() + ' ' + l.id; }
  function sayLine(l, done) {
    if (l.kind === 'text' && l.audio) CLIP.sentence({ pack: l.pack, i: l.i, text: l.say, audio: l.audio }, done);
    else TTS.say(l.say, done);
  }
  function bindLine(h) {
    const l = h && h.line, box = document.getElementById('lineCard'); if (!l || !box) return;
    // 列表: a row that opens the sentence in place (open for the rest of the day); 卡片: always open, no row
    const fold = box.querySelector('#lcFold');
    if (fold) {
      const show = open => { box.classList.toggle('open', open); fold.setAttribute('aria-expanded', String(open)); };
      show(load('flow-line-open') === lineDay(l));
      fold.onclick = () => {
        const open = !box.classList.contains('open');
        show(open); save('flow-line-open', open ? lineDay(l) : null);
        if (!open) { MIC.stop(); const p = box.querySelector('#lcPanel'); if (p && !p.hidden) box.querySelector('#lcShadow').click(); }
      };
    }
    box.querySelector('#lcSay').onclick = () => sayLine(l);
    box.querySelector('#lcKeep').onclick = e => saveCard(l.kind === 'text'
      ? { text: l.expression, meaning: l.meaning, context: l.en, pack: l.pack }
      : { text: l.say, meaning: l.zh, context: l.source }, e.currentTarget);
    const tog = box.querySelector('#lcShadow'), panel = box.querySelector('#lcPanel');
    if (!tog || !panel) return;  // 卡片: 听一遍 and 收藏 only
    let blob = null, url = '';
    tog.onclick = () => {
      const open = panel.hidden; panel.hidden = !open; tog.setAttribute('aria-expanded', String(open));
      if (!open) { MIC.stop(); return; }
      panel.innerHTML = `<div class="lc-sh stack-s"><p class="small">先听一遍，再点红点读出来（最长 15 秒），读完和原句对比着听。</p>
        <div class="row"><button class="btn small" id="lsOrig" type="button">${ICON.speak}原句</button>${recBtn('lsRec', '录音')}
          <button class="btn small" id="lsBack" type="button" disabled>对比回放</button><button class="btn small" id="lsAI" type="button" disabled>✦ AI 点评</button></div>
        <div class="lc-out" aria-live="polite"></div></div>`;
      const rec = panel.querySelector('#lsRec'), back = panel.querySelector('#lsBack'), ai = panel.querySelector('#lsAI');
      panel.querySelector('#lsOrig').onclick = () => sayLine(l);
      rec.onclick = () => MIC.toggle(rec, 15, b => { blob = b; if (url) URL.revokeObjectURL(url); url = URL.createObjectURL(b); back.disabled = false; ai.disabled = false; toast('录好了，可以对比回放'); });
      back.onclick = () => sayLine(l, () => CLIP.mine(url));  // the original, then the learner's own recording
      ai.onclick = async () => {
        if (!S.user) return needLogin('登录后，AI 会听你的跟读，指出漏读、读错和需要连读的地方。');
        if (!blob) return;
        ai.disabled = true; ai.innerHTML = '<span class="spin"></span>';
        try {
          const body = { audio: await MIC.payload(blob), request_id: rid('ls'), ...(l.kind === 'text' ? { pack: l.pack, i: l.i } : { quote: l.id.slice(2) }) };
          const x = (await api('/api/next/shadow', body)).result;
          const flu = { smooth: '流畅', ok: '基本流畅', choppy: '有点断断续续' }[x.fluency] || '';
          const sc = x.score;  // 发音分 (r27 C, the same as 听 → 跟读): accuracy, fluency and how much of the line was said
          panel.querySelector('.lc-out').innerHTML = `<div class="card flat stack-s enter" data-ex-block>${aiMark('发音分和点评由 AI 估计，仅供参考')}${sc ? `<div class="small"><b class="lc-score">${sc.total}</b> 发音分 · 准确 ${sc.accuracy} · 流利 ${sc.fluency} · 完整 ${x.matched}/${x.words.length}<span class="tiny muted">（AI 估计，仅供参考）</span></div>` : ''}
            <div class="small">${x.words.map(w => `<span class="${w.ok ? '' : 'miss'}" lang="en">${esc(w.w)}</span>`).join(' ')}</div>
            <div class="tiny muted">AI 听到：<span lang="en">${esc(x.transcript || '（没听清）')}</span> · 读到 ${x.matched}/${x.words.length} 个词${flu && !sc ? ' · ' + flu : ''}</div>
            ${(x.sounds || []).map(sd => `<div class="small"><b lang="en">${esc(sd.sound)} ${esc(sd.word)}</b>：<span data-ex>${esc(sd.note)}</span>${sd.set ? ` <a class="link" href="#/sounds/${encodeURIComponent(sd.set)}" data-tap="shadow-sound">去练 ${esc(sd.set_title)} →</a>` : ''}</div>`).join('')}
            ${x.issues.map(it => `<div class="small"><b lang="en">${esc(it.word)}</b>：<span data-ex>${esc(it.note)}</span></div>`).join('')}${x.tip ? `<div class="small">建议：<span data-ex>${esc(x.tip)}</span></div>` : ''}</div>`;
        } catch (e) { toast(e.message); }
        ai.disabled = false; ai.textContent = '✦ AI 点评';
      };
    };
  }

  /* ---------- 今日的样子 (r39, the user's picks 2026-11-26, B9's v3): 列表 (the default) or 卡片 ---------- */
  // One order for both (the user: 「列表按什么顺序，卡片就按什么顺序」), kept with the account and changed on 调整顺序
  // (#/today/edit): 今天的计划 first by default. The list keeps its top fixed — 这周, 今天的计划, the one green button —
  // and folds the rest under 还有时间的话 in that order; the cards draw one white card each, side by side, the first in
  // the middle whenever 今日 opens (B9's spec, 第 4 版).
  // The same parts in both: a white block, a step row (number, title, time; the next one in ink), one green button.
  // The choice is kept with the account (POST /api/next/today-view); the switch on 今日 and 我的 → 使用习惯 (B5) call
  // setTodayView. Only learners with a plan have it: a guest's 今日 is one article.
  const TODAY_ORDER = ['plan', 'week', 'line', 'mine', 'news', 'extra'];  // next_service.TODAY_KEYS
  const TODAY_NAMES = { week: '这周', plan: '今天的计划', line: '今日好句', mine: '我的材料', news: '今日一读', extra: '还有时间的话' };
  const TODAY_DESC = { plan: '今天要做的几步', week: '学了几天、记住多少', line: '每天一句，能听能跟读', mine: '你自己贴进来的那篇', news: '每天一篇短文', extra: '错题、复听、语法' };
  function todayOrder() {
    const p = S.home && S.home.profile, got = (p && p.today_order || []).filter(k => TODAY_ORDER.indexOf(k) >= 0);
    return got.concat(TODAY_ORDER.filter(k => got.indexOf(k) < 0));
  }
  function todayView() { const p = S.home && S.home.profile; return p && p.today_view === 'cards' ? 'cards' : 'list'; }
  async function setTodayView(v) {
    const p = S.home && S.home.profile;
    if (!p || (v !== 'list' && v !== 'cards') || todayView() === v) return;
    const was = todayView();
    p.today_view = v; redrawToday();
    document.querySelectorAll('[data-today-view]').forEach(b => { const on = b.dataset.todayView === v; b.classList.toggle('on', on); b.setAttribute('aria-checked', String(on)); });
    try { await api('/api/next/today-view', { view: v }); }
    catch (e) { p.today_view = was; redrawToday(); toast(e.message); }
  }
  // 今日 drawn again in the other look, faded in (200 ms) unless the learner asked for less motion
  function redrawToday() {
    if (parts()[0] !== '' || !S.home || !S.home.path) return;
    today(true);
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches && view.animate) view.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 200, easing: 'ease-out' });
  }
  // 列表 | 卡片, the look of 背单词's 简 | 详 (.vt): a pair of radios, 44 px to tap
  function todaySwitchHTML() {
    const v = todayView();
    return `<div class="vt vt-today" role="radiogroup" aria-label="今日的样子">${[['list', '列表', 'today-view-list'], ['cards', '卡片', 'today-view-cards']].map(([k, l, tap]) =>
      `<button type="button" role="radio" data-today-view="${k}" data-tap="${tap}" aria-checked="${v === k}"${v === k ? ' class="on"' : ''}>${l}</button>`).join('')}</div>`;
  }
  function bindTodaySwitch() { document.querySelectorAll('.vt-today [data-today-view]').forEach(b => { b.onclick = () => setTodayView(b.dataset.todayView); }); }

  // ---- the parts ----
  // 这周: one sentence and the days as dots (progress_service.week and habit, in the home data); a tap opens the details
  function weekFacts(h) {
    const st = h.stats, hb = st && st.habit, pr = st && st.progress;
    if (!S.user || !hb) return null;
    const title = hb.met ? `学了 ${hb.done} 天，目标达成` : hb.done ? `学了 ${hb.done} 天，目标 ${hb.goal} 天` : `还没开始，目标 ${hb.goal} 天`;
    const rate = pr && pr.accuracy && pr.accuracy.now ? pr.accuracy.now.rate : null;
    const sub = pr && pr.remembered ? [`记住 ${pr.remembered.now} 个新词`, `学完 ${pr.finished.now} 篇`, rate != null ? `正确率 ${rate}%` : ''].filter(Boolean).join(' · ') : '';
    return { title, sub, days: hb.days || [], label: `这周${title}${sub ? '：' + sub : ''}。点开看明细` };
  }
  function planFacts(h) {
    const p = h.path, must = p.steps.filter(s => (s.group || 'must') === 'must'), extra = p.steps.filter(s => s.group === 'extra'), wk = p.steps.filter(s => s.group === 'week');
    const next = must.find(s => !s.done), read = must.find(s => s.key === 'read');
    const readId = read ? decodeURIComponent(read.href.split('/')[2] || '') : '';
    const art = [h.today[0], h.resume, ...h.today].find(m => m && m.id === readId);
    // 再学一篇 once the plan is done (r27): the next recommendation itself, not the whole library
    const more1 = h.today.find(m => m && m.id !== readId && (!(m.steps || []).includes('check') || m.redo));
    const left = p.must_minutes == null ? `约 ${p.minutes} 分钟` : p.done >= p.total ? (p.studied ? `今天学了约 ${p.studied} 分钟` : '都做完了')
      : p.done ? `还要约 ${p.left_minutes} 分钟` : `约 ${p.must_minutes} 分钟`;
    return { p, must, extra, wk, next, readId, art, more1, left };
  }
  // A step: its number (✓ when done), title, about how long; the next one in ink, the others quieter. No green.
  // The words step (key review, to #/review) is 背单词 here (B9's spec 第 4 版; B2 agreed, 2026-11-26): how many to
  // review and learn, and how a backlog is going, show on the words page; here only the minutes. 选一本词书 (the same
  // key, to #/vocab/plan) keeps its name: it asks for a word book first.
  const stepName = (s, f) => s.key === 'read' && f.art ? f.art.title : s.key === 'review' && s.href === '#/review' ? '背单词' : s.title;
  function stepsHTML(f) {
    return `<ol class="tv-steps">${f.must.map((s, k) => `<li><a class="tv-step${s.done ? ' done' : ''}${s === f.next ? ' next' : ''}" href="${esc(s.href)}">`
      + `<span class="n" aria-hidden="true">${s.done ? '✓' : k + 1}</span><span class="t">${esc(stepName(s, f))}</span>`
      + `<span class="m">${s.done ? '已完成' : s.minutes ? `约 ${s.minutes} 分钟` : ''}</span></a></li>`).join('')}</ol>`;
  }
  // the one green button: the plan's next step; once it is done, 再学一篇
  function goHTML(f) {
    return f.next ? `<a class="tv-btn go-next" href="${esc(f.next.href)}" data-tap="home-start">${f.p.done ? '继续' : '开始'}今天的练习</a>`
      : `<a class="tv-btn go-next" href="${f.more1 ? '#/m/' + encodeURIComponent(f.more1.id) : '#/library'}" data-tap="home-more-one">再学一篇</a>`;
  }
  function doneHTML(f) {
    return f.next ? '' : `<div class="tp-more"><span class="small">都完成了。${f.more1 ? `想多学一点，下一篇是《${esc(f.more1.title)}》。` : '想多学一点，就再挑一篇。'}多学的照样算进「这周进步」。</span>
      <a class="link small hit44" href="#/mix/more" data-tap="home-more-grammar">做 4 道语法题</a>
      <button class="link small hit44 tp-remind" type="button" id="remindOnce" data-tap="home-remind-once">今天或明天什么时候有空复习？</button></div>`;
  }
  // What is not counted in the plan, one line each: 今日好句 (opens in place: 听一遍, 跟读, 收藏), 我的材料, 今日一读
  // (marked AI 生成), then the plan's 还有时间的话. Name on the left, what it is on the right, in grey.
  function moreRows(h, f, news) {
    const by = {}, l = h.line, m = h.mine;
    by.line = [];
    if (l) by.line.push(`<div class="line-row" id="lineCard"><button class="tv-row named" id="lcFold" type="button" aria-expanded="false" aria-controls="lcBody" data-tap="line-fold">`
      + `<span class="t">今日好句</span><span class="m">${esc(l.source)}</span></button><div class="lc-body tv-line" id="lcBody">${lineBodyHTML(l)}</div></div>`);
    by.mine = [];
    if (S.user && m) {
      const it = m.item, href = it ? `#/m/${encodeURIComponent(it.id)}${it.started ? '/' + nextStep(it.steps) : ''}` : '#/import';
      by.mine.push(`<a class="tv-row named" href="${href}" data-tap="home-mine"><span class="t">我的材料</span><span class="m">${it ? `${it.started ? '继续' : '练'}《${esc(it.title)}》` : '贴课本或讲义进来练'}</span></a>`);
    }
    by.news = [];
    if (news) by.news.push(`<a class="tv-row named" href="#/m/${encodeURIComponent(news.id)}" data-tap="home-news"><span class="t">今日一读</span><span class="m">${aiTag()}${news.minutes ? ` · 约 ${news.minutes} 分钟` : ''}</span></a>`);
    by.extra = f.extra.map(s => extraRowHTML(s, 'home-extra'));
    return todayOrder().filter(k => by[k]).reduce((rows, k) => rows.concat(by[k]), []);
  }
  function extraRowHTML(s, tap) {
    return `<a class="tv-row${s.done ? ' done' : ''}" href="${esc(s.href)}" data-tap="${tap}"><span class="t">${esc(s.title)}</span><span class="m tm">${s.done ? '已完成' : s.minutes ? `约 ${s.minutes} 分钟` : ''}</span></a>`;
  }
  function weekTasksHTML(f) {
    return f.wk.length ? `<div class="tp-week"><div class="tp-week-head"><h2 class="h3">本周任务</h2><span class="tiny muted">这周哪天做都行，不占每天的时间</span></div>
      <div class="tv-card tv-more">${f.wk.map(s => extraRowHTML(s, 'home-week-task')).join('')}</div></div>` : '';
  }
  const CHEV = '<svg class="tv-chev" viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  // ---- 列表 ----
  // The top is fixed (the user: 这周 and 今天的计划 together, the green button under them); the rest follows the order.
  function todayListHTML(h, news) {
    const f = planFacts(h), w = weekFacts(h), rows = moreRows(h, f, news);
    const blocks = {
      week: () => w ? `<button class="tv-card tv-week" id="weekCard" type="button" data-tap="home-week" aria-label="${esc(w.label)}"><span class="tv-hd"><b>这周${esc(w.title)}</b>`
        + `<span class="tv-days" aria-hidden="true">${w.days.map(d => `<i class="${d.active ? 'on' : ''}"></i>`).join('')}</span></span>${w.sub ? `<span class="tv-sub">${esc(w.sub)}</span>` : ''}</button>` : '',
      plan: () => `<section class="today-plan" aria-labelledby="tpTitle">${backHTML(f.p, f.next)}
        <div class="tv-card tv-plan"><div class="tv-hd"><h1 id="tpTitle">${f.next ? '今天的计划' : '今天的计划完成了'}</h1><span>${esc(f.left)} · `
        + `<span class="tp-count" role="img" aria-label="今天的计划，已完成 ${f.p.done} 步，共 ${f.p.total} 步"><span aria-hidden="true">${f.p.done} / ${f.p.total}</span></span></span></div>
          ${sprintLine(h)}${stepsHTML(f)}${f.p.note ? `<p class="tiny muted tp-note">${esc(f.p.note)}</p>` : ''}</div>
        ${goHTML(f)}${overLineHTML(f.p, f.next)}${doneHTML(f)}
        ${rows.length ? `<details class="tp-extra tv-fold"${f.next ? '' : ' open'}><summary><span>还有时间的话</span><span class="tv-n">${rows.length} 项${CHEV}</span></summary>
          <div class="tv-card tv-more">${rows.join('')}</div><a class="link small hit44 tv-edit" href="#/today/edit" data-tap="today-edit">调整顺序</a></details>` : ''}${weekTasksHTML(f)}</section>`
    };
    return ['week', 'plan'].map(k => blocks[k]()).join('');
  }
  function bindTodayList() {
    const wc = document.getElementById('weekCard'); if (wc) wc.onclick = weekSheet;
  }

  // ---- 卡片 ----
  // One screen: the cards in the same order, 今天的计划 in the middle when 今日 opens, a sliver of each neighbour.
  // Native scroll snapping (one card a swipe), the cards beside it a little smaller and fainter while it moves: never
  // tilted, coloured or thrown, so it does not look like answering a word card. Reminders sit in one line above.
  function todayCards(h, news) {
    const f = planFacts(h), w = weekFacts(h), l = h.line, m = S.user && h.mine, it = m && m.item, extra = f.extra.concat(f.wk);
    const WK = uiLang() === 'en' ? 'MTWTFSS' : '一二三四五六日';  // i18n: keep (a day's first letter, Monday first)
    const cards = {
      week: () => w && `<p class="tv-lb">这周</p><h2 class="tv-big">${esc(w.title)}</h2>${w.sub ? `<p class="tv-sub">${esc(w.sub)}</p>` : ''}
        <div class="tv-wk7 tv-mid" aria-hidden="true">${w.days.map((d, k) => `<span><i class="${d.active ? 'on' : ''}${d.today ? ' today' : ''}"></i>${WK[k]}</span>`).join('')}</div>
        <button class="tv-act" type="button" id="tvWeek" data-tap="home-week">看明细</button>`,
      plan: () => `<div class="tv-scroll">${backHTML(f.p, f.next)}<h1 class="tv-lb" id="tpTitle">${f.next ? '今天的计划' : '今天的计划完成了'}</h1><p class="tv-big">${esc(f.left)}</p>
        <p class="tv-sub"><span class="tp-count" role="img" aria-label="今天的计划，已完成 ${f.p.done} 步，共 ${f.p.total} 步"><span aria-hidden="true">${f.p.total} 步，${f.next ? `做完 ${f.p.done} 步了` : '都做完了'}</span></span></p>
        ${sprintLine(h)}<div class="tv-st">${stepsHTML(f)}</div>${f.p.note ? `<p class="tiny muted tp-note">${esc(f.p.note)}</p>` : ''}${overLineHTML(f.p, f.next)}
        ${f.next ? '' : `<a class="link small hit44 tv-also" href="#/mix/more" data-tap="home-more-grammar">做 4 道语法题</a>`}</div>${goHTML(f)}`,  // a short card: the words scroll, the button stays
      line: () => l && `<p class="tv-lb">今日好句</p><p class="tv-quote lc-en${l.say.length > 100 ? ' long' : ''}" lang="en">${lineEnHTML(l)}</p><p class="tv-p lc-zh" data-zh>${esc(l.zh)}</p>
        <p class="tv-sub lc-src">${esc(l.source)}${l.label ? ' · ' + esc(l.label) : ''}${l.href ? ` · <a class="link" href="${esc(l.href)}" data-tap="line-read">读原文</a>` : ''}</p>
        <div class="tv-foot"><div id="lcPanel" hidden></div>${aiVoiceNote('朗读由 AI 合成', 'p', 'tv-ai')}<div class="tv-three"><button class="tv-act" type="button" id="lcSay" data-tap="line-say">听一遍</button>`
        + `<button class="tv-act" type="button" id="lcShadow" data-tap="line-shadow" aria-expanded="false" aria-controls="lcPanel">跟读</button>`
        + `<button class="tv-act" type="button" id="lcKeep" data-tap="line-keep">收藏</button></div></div>`,
      mine: () => m && (it ? `<p class="tv-lb">我的材料</p><h2 class="tv-ttl">${esc(it.title)}</h2>
        <p class="tv-sub">${it.started ? `学了 ${(it.steps || []).length} 步，共 4 步` : [it.level, it.words ? it.words + ' 词' : '', '还没开始'].filter(Boolean).map(esc).join(' · ')}</p>
        ${it.started ? `<div class="tv-bar" aria-hidden="true"><i style="width:${Math.round((it.steps || []).length / 4 * 100)}%"></i></div>` : ''}
        ${it.opening ? `<p class="tv-en" lang="en">${esc(it.opening)}</p>` : ''}
        <a class="tv-act" href="#/m/${encodeURIComponent(it.id)}${it.started ? '/' + nextStep(it.steps) : ''}" data-tap="home-mine">${it.started ? '接着读' : '开始练'}</a>`
        : `<p class="tv-lb">我的材料</p><h2 class="tv-big">贴课本或讲义进来练</h2><p class="tv-sub">课本、讲义、面试题都行，用语流的四步来练</p>
        <a class="tv-act" href="#/import" data-tap="home-mine">贴一篇</a>`),
      news: () => news && `<p class="tv-lb">今日一读 · ${aiTag()}</p><h2 class="tv-ttl">${esc(news.title)}</h2>
        <p class="tv-sub">${[news.level, news.theme_label, news.minutes ? `约 ${news.minutes} 分钟` : ''].filter(Boolean).map(esc).join(' · ')}</p>${news.preview ? `<p class="tv-p tv-clamp">${esc(news.preview)}</p>` : ''}
        <a class="tv-act" href="#/m/${encodeURIComponent(news.id)}" data-tap="home-news">读这篇</a>`,
      extra: () => extra.length && `<p class="tv-lb">还有时间的话</p><h2 class="tv-big">还可以再练 ${extra.length} 项</h2><p class="tv-sub">不算进今天的计划</p>
        <div class="tv-rows">${extra.map(s => extraRowHTML(s, s.group === 'week' ? 'home-week-task' : 'home-extra')).join('')}</div>`
    };
    const list = todayOrder().map(k => ({ k, html: cards[k] && cards[k]() })).filter(c => c.html);
    const n = list.length, start = 0;  // the learner's first card, in the middle, whenever 今日 opens
    const html = `<div class="tv-deckbox"><button class="tv-arrow prev" type="button" aria-label="上一张" tabindex="-1">‹</button>
      <div class="tv-deck" id="tvDeck" role="list" aria-label="今日，${n} 张卡片，左右翻" tabindex="0">${list.map((c, k) =>
        `<section class="tv-dc tv-${c.k}${c.k === 'plan' ? ' today-plan' : ''}"${c.k === 'line' ? ' id="lineCard"' : ''} role="listitem" aria-label="第 ${k + 1} 张，共 ${n} 张，${TODAY_NAMES[c.k]}" data-card="${c.k}">${c.html}</section>`).join('')}</div>
      <button class="tv-arrow next" type="button" aria-label="下一张" tabindex="-1">›</button></div>
      <div class="tv-under"><span></span><div class="tv-dots" aria-hidden="true">${list.map((c, k) => `<i class="${k === start ? 'on' : ''}"></i>`).join('')}</div>
        <a class="link small hit44 tv-edit" href="#/today/edit" data-tap="today-edit">编辑</a></div>`;
    return { html, start };
  }
  function mountDeck(start) {
    const dk = document.getElementById('tvDeck'); if (!dk) return;
    const cards = [...dk.children], dots = [...document.querySelectorAll('.tv-dots i')];
    const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
    // as tall as the screen allows: the deck, its dots and the tab bar on one screen (shorter on a phone held sideways)
    const fit = () => {
      const tabs = document.querySelector('.tabs'), tb = tabs && getComputedStyle(tabs).position === 'fixed' ? tabs.getBoundingClientRect().top : innerHeight;
      const room = tb - (dk.getBoundingClientRect().top + scrollY) - 60;  // from the page's top (今日 opens there); the dots and 编辑 under it
      dk.style.setProperty('--dk-h', Math.max(180, Math.min(560, Math.round(room))) + 'px');  // a phone held sideways: short, its button still on the screen
    };
    // where card k sits: in the middle on a phone (one card a screen); first from the left when two or three fit side
    // by side (a computer, an iPad), where the first card could never be in the middle
    const step = () => cards[0].offsetWidth + (parseFloat(getComputedStyle(dk).columnGap) || 0);
    const pad = () => parseFloat(getComputedStyle(dk).paddingLeft) || 0;
    const side = () => dk.clientWidth > cards[0].offsetWidth * 1.6;
    const left = k => side() ? k * step() : pad() + k * step() + cards[0].offsetWidth / 2 - dk.clientWidth / 2;
    const at = () => Math.max(0, Math.min(cards.length - 1, Math.round(side() ? dk.scrollLeft / step() : (dk.scrollLeft + dk.clientWidth / 2 - pad() - cards[0].offsetWidth / 2) / step())));
    let frame = 0;
    const paint = () => {
      frame = 0;
      const k = at();
      dots.forEach((x, i) => x.classList.toggle('on', i === k));
      if (calm || side()) return;  // side by side on a wide screen: all in full view, none smaller
      const s = step(), mid = dk.scrollLeft + dk.clientWidth / 2;
      cards.forEach((c, i) => { const d = Math.min(1, Math.abs(pad() + i * s + c.offsetWidth / 2 - mid) / s); c.style.transform = d > 0.01 ? `scale(${1 - 0.04 * d})` : ''; c.style.opacity = d > 0.01 ? String(1 - 0.5 * d) : ''; });
    };
    const go = k => dk.scrollTo({ left: left(Math.max(0, Math.min(cards.length - 1, k))), behavior: calm ? 'auto' : 'smooth' });
    fit();
    dk.scrollLeft = left(start); paint();
    // measured again once the line above has its height (a reminder filled in, closed, or the fonts arriving): one height
    // for all six cards, the dots and 编辑 never moving while the cards are swiped
    const refit = () => { if (!dk.isConnected) return; const k = at(); fit(); dk.scrollLeft = left(k); paint(); };
    const notes = document.querySelector('.tv-notes');
    if (notes && window.ResizeObserver) new ResizeObserver(refit).observe(notes);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(refit);
    dk.addEventListener('scroll', () => { if (!frame) frame = requestAnimationFrame(paint); }, { passive: true });
    dk.addEventListener('keydown', e => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      e.preventDefault(); go(at() + (e.key === 'ArrowRight' ? 1 : -1));
    });
    // a reader or the keyboard moving into a card brings it to the middle
    dk.addEventListener('focusin', e => { const c = e.target.closest && e.target.closest('.tv-dc'); if (c && c !== cards[at()]) go(cards.indexOf(c)); });
    const prev = document.querySelector('.tv-arrow.prev'), next = document.querySelector('.tv-arrow.next');
    if (prev) prev.onclick = () => go(at() - 1);
    if (next) next.onclick = () => go(at() + 1);
    const wk = document.getElementById('tvWeek'); if (wk) wk.onclick = weekSheet;
    // a long press on a card (half a second, a short buzz where the phone has one) opens 调整顺序, as on a phone's home
    // screen; a move or a scroll first is a swipe, and the tap after a long press is not a tap on what is under it
    let hold = 0, held = false, x0 = 0, y0 = 0;
    const stop = () => { clearTimeout(hold); hold = 0; };
    dk.addEventListener('pointerdown', e => {
      if (e.button > 0 || !e.target.closest('.tv-dc')) return;
      held = false; x0 = e.clientX; y0 = e.clientY; stop();
      hold = setTimeout(() => { held = true; hold = 0; if (navigator.vibrate) navigator.vibrate(10); location.hash = '#/today/edit'; }, 500);
    });
    dk.addEventListener('pointermove', e => { if (hold && Math.abs(e.clientX - x0) + Math.abs(e.clientY - y0) > 8) stop(); });
    ['pointerup', 'pointercancel', 'scroll'].forEach(t => dk.addEventListener(t, stop, { passive: true }));
    dk.addEventListener('click', e => { if (held) { e.preventDefault(); e.stopPropagation(); held = false; } }, true);
    dk.addEventListener('contextmenu', e => { if (e.target.closest('.tv-dc')) e.preventDefault(); });
    const onResize = () => { if (!dk.isConnected) return removeEventListener('resize', onResize); refit(); };
    addEventListener('resize', onResize);
  }

  // ---- 调整顺序 (#/today/edit): the blocks as small white tiles in two columns, dragged into place ----
  // Held, a tile lifts (a little larger, with a shadow), a grey space stays where it was and the others make room; let
  // go, it drops there. A screen reader hears 「今天的计划，第 1 个，共 6 个」 and has 上移 / 下移; the arrow keys move a
  // tile too. 完成 keeps the order with the account (POST /api/next/today-view {order}) and goes back to 今日, its new
  // first block first. This version only orders: nothing is hidden.
  function todayEditView() {
    if (!S.user || !S.home || !S.home.path) { location.hash = '#/'; return; }
    view.innerHTML = `<div class="greet-row tv-edit-head"><h1 class="tv-edit-t">调整顺序</h1><button class="btn tv-done" type="button" id="tvDone" data-tap="today-edit-done">完成</button></div>
      <ol class="tv-grid" id="tvGrid" aria-label="今日的顺序">${todayOrder().map(k => `<li class="tv-tile" tabindex="0" data-k="${k}"><b>${TODAY_NAMES[k]}</b><span>${TODAY_DESC[k]}</span><i class="tv-ix" aria-hidden="true"></i>`
        + `<button class="sr-only" type="button" data-mv="-1">上移</button><button class="sr-only" type="button" data-mv="1">下移</button></li>`).join('')}</ol>
      <p class="small muted tv-edit-hint">按住一块拖动。排在最前面的，打开今日先看到。</p>`;
    const grid = document.getElementById('tvGrid');
    const tiles = () => [...grid.querySelectorAll('.tv-tile')];
    const renumber = () => { const all = tiles(); all.forEach((t, i) => { t.querySelector('.tv-ix').textContent = i + 1; t.setAttribute('aria-label', `${TODAY_NAMES[t.dataset.k]}，第 ${i + 1} 个，共 ${all.length} 个`); }); };
    const move = (t, by) => {
      const all = tiles(), i = all.indexOf(t), j = Math.max(0, Math.min(all.length - 1, i + by));
      if (i === j) return;
      grid.insertBefore(t, by > 0 ? all[j].nextSibling : all[j]); renumber(); t.focus();
      announce(`${TODAY_NAMES[t.dataset.k]}，第 ${j + 1} 个`);
    };
    renumber();
    grid.addEventListener('click', e => { const b = e.target.closest('[data-mv]'); if (b) move(b.closest('.tv-tile'), Number(b.dataset.mv)); });
    grid.addEventListener('keydown', e => {
      const t = e.target.closest('.tv-tile'); if (!t || e.target !== t) return;
      const by = { ArrowUp: -1, ArrowLeft: -1, ArrowDown: 1, ArrowRight: 1 }[e.key];
      if (by) { e.preventDefault(); move(t, by); }
    });
    // dragging: the tile follows the finger (fixed, on top); a grey slot moves through the others to where it would drop
    let drag = null;
    grid.addEventListener('pointerdown', e => {
      const t = e.target.closest('.tv-tile'); if (!t || e.button > 0 || e.target.closest('button')) return;
      drag = { t, id: e.pointerId, x0: e.clientX, y0: e.clientY, on: false };
    });
    grid.addEventListener('pointermove', e => {
      if (!drag || e.pointerId !== drag.id) return;
      const t = drag.t;
      if (!drag.on) {
        if (Math.abs(e.clientX - drag.x0) + Math.abs(e.clientY - drag.y0) < 6) return;
        // the page's entry animation (.enter>*, 20-motion-graph.css) stays on the grid at its last frame, and an element
        // with a transform animation is what a fixed child is placed against: the lifted tile went off by the grid's
        // distance from the screen's corner. Taken off the grid for good (back on, it would play again).
        grid.style.animation = 'none';
        const r = t.getBoundingClientRect();
        drag.on = true; drag.slot = document.createElement('li'); drag.slot.className = 'tv-slot'; drag.slot.setAttribute('aria-hidden', 'true');
        grid.insertBefore(drag.slot, t);
        t.classList.add('lift'); t.style.left = r.left + 'px'; t.style.top = r.top + 'px'; t.style.width = r.width + 'px'; t.style.height = r.height + 'px';
        // and whatever else may still place it against something other than the screen: measured once, the difference taken back
        const r2 = t.getBoundingClientRect();
        if (Math.abs(r2.left - r.left) + Math.abs(r2.top - r.top) > 0.5) { t.style.left = (2 * r.left - r2.left) + 'px'; t.style.top = (2 * r.top - r2.top) + 'px'; }
        t.style.transformOrigin = `${drag.x0 - r.left}px ${drag.y0 - r.top}px`;  // it grows around the finger, which keeps its place on it
        try { t.setPointerCapture(e.pointerId); } catch (err) { /* the pointer is gone */ }
      }
      e.preventDefault();
      t.style.transform = `translate(${e.clientX - drag.x0}px, ${e.clientY - drag.y0}px) scale(1.04)`;
      const over = tiles().find(x => x !== t && (b => e.clientX >= b.left && e.clientX <= b.right && e.clientY >= b.top && e.clientY <= b.bottom)(x.getBoundingClientRect()));
      if (over) { const kids = [...grid.children], a = kids.indexOf(drag.slot), b = kids.indexOf(over); grid.insertBefore(drag.slot, a < b ? over.nextSibling : over); }
    });
    const drop = () => {
      if (!drag) return;
      const t = drag.t;
      if (drag.on) { grid.insertBefore(t, drag.slot); drag.slot.remove(); t.classList.remove('lift'); t.style.cssText = ''; renumber(); }
      drag = null;
    };
    grid.addEventListener('pointerup', drop); grid.addEventListener('pointercancel', drop);
    document.getElementById('tvDone').onclick = async e => {
      const order = tiles().map(t => t.dataset.k), b = e.currentTarget;
      b.disabled = true;
      try {
        const r = await api('/api/next/today-view', { order });
        if (S.home && S.home.profile) S.home.profile.today_order = r.today_order;
        location.hash = '#/';
      } catch (err) { b.disabled = false; toast(err.message); }
    };
  }
  /* ---------- 小彩蛋 (the user's pick 2026-11-26: 「长按的时候会来一些有意思的特效……每一次都不一样」) ----------
     Hold 今日's greeting (about 0.45 s), or see the day's plan all done for the first time that day: one of four little
     shows drawn from 语流's mark, never the same kind twice in a row, and its numbers, direction and words new each time:
     a row of sound bars sweeping across; rounded squares rippling out from the finger; a handful of bars thrown up and
     falling; 「你好」 in another language with which one under it. Over in 1.5 s; no sound; on top of the page but never in
     the way of a tap (the canvas takes no pointer events, and is made only to play and taken away after); not at all
     with 减少动态效果; nothing kept or sent. B9's drawing (ui-refine/batch1/compare-page.html), sized to the screen. */
  const EGG = (() => {
    // the word, the language in Chinese, and in English (the line under it follows 界面语言: zhEn, 00-i18n.js)
    const HELLO = [['Hello', '英', 'English'], ['Bonjour', '法', 'French'], ['Hola', '西班牙', 'Spanish'], ['Ciao', '意大利', 'Italian'], ['Hallo', '德', 'German'],
      ['Olá', '葡萄牙', 'Portuguese'], ['こんにちは', '日', 'Japanese'], ['안녕하세요', '韩', 'Korean'], ['Merhaba', '土耳其', 'Turkish'], ['Aloha', '夏威夷', 'Hawaiian'],
      ['Namaste', '印地', 'Hindi'], ['Hej', '瑞典', 'Swedish'], ['Sawubona', '祖鲁', 'Zulu'], ['Xin chào', '越南', 'Vietnamese'], ['Habari', '斯瓦希里', 'Swahili'],
      ['Shalom', '希伯来', 'Hebrew']];
    const MS = 1500;
    let last = -1, busy = false;
    const calm = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
    const rnd = (a, b) => a + Math.random() * (b - a);
    const out = t => 1 - Math.pow(1 - t, 3);
    function play(x, y) {
      if (busy || calm()) return false;
      busy = true;
      const W = innerWidth, H = innerHeight, dpr = Math.min(2, window.devicePixelRatio || 1);
      const cv = document.createElement('canvas');
      cv.className = 'egg-layer'; cv.setAttribute('aria-hidden', 'true');
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
      document.body.appendChild(cv);
      const ctx = cv.getContext('2d');
      const css = getComputedStyle(document.body), tok = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
      const accent = tok('--green') || '#1a8a4a', ink = tok('--ink') || '#1b1d1a', ink2 = tok('--ink2') || '#4a4d46', muted = tok('--muted') || '#6f7369', paper = tok('--paper') || '#fff';
      const font = css.fontFamily || 'sans-serif';
      if (x == null) { x = W / 2; y = H / 2; }
      const rr = (px, py, w, h, r) => {
        r = Math.min(r, w / 2, h / 2); ctx.beginPath(); ctx.moveTo(px + r, py);
        ctx.arcTo(px + w, py, px + w, py + h, r); ctx.arcTo(px + w, py + h, px, py + h, r); ctx.arcTo(px, py + h, px, py, r); ctx.arcTo(px, py, px + w, py, r);
        ctx.closePath(); ctx.fill();
      };
      // 1 · a row of sound bars sweeping across a band around the finger
      const wave = () => {
        const n = Math.floor(rnd(14, 30)), ph = rnd(0, 6), sp = rnd(1, 3), amp = rnd(0.3, 0.6), dir = Math.random() < 0.5 ? 1 : -1;
        const B = Math.min(260, H * 0.4), top = Math.max(0, Math.min(H - B, y - B / 2));
        return t => {
          const gap = W / n, bw = Math.min(9, gap * 0.42);
          ctx.fillStyle = accent; ctx.globalAlpha = Math.min(1, (1 - t) * 2.4);
          for (let i = 0; i < n; i++) {
            const u = i / (n - 1), on = Math.max(0, Math.min(1, (t * 2 - (dir > 0 ? u : 1 - u) * 0.8) * 3));
            const h = (B * 0.1 + B * amp * Math.abs(Math.sin(u * sp * 6 + ph + t * 7 * dir))) * out(on);
            if (h > 1) rr(gap * i + (gap - bw) / 2, top + (B - h) / 2, bw, h, bw / 2);
          }
        };
      };
      // 2 · the mark's rounded square, rippling out from the finger
      const rings = () => {
        const n = Math.floor(rnd(3, 6)), gap = rnd(0.1, 0.18), big = Math.min(Math.max(W, H) * rnd(0.7, 1.1), 900);
        return t => {
          ctx.strokeStyle = accent; ctx.lineWidth = 3;
          for (let i = 0; i < n; i++) {
            const u = t - i * gap; if (u <= 0) continue;
            const s = out(Math.min(1, u * 1.4)) * big, r = s * 0.24;
            ctx.globalAlpha = Math.max(0, 0.75 * (1 - u * 1.5));
            ctx.beginPath(); ctx.moveTo(x - s / 2 + r, y - s / 2);
            ctx.arcTo(x + s / 2, y - s / 2, x + s / 2, y + s / 2, r); ctx.arcTo(x + s / 2, y + s / 2, x - s / 2, y + s / 2, r);
            ctx.arcTo(x - s / 2, y + s / 2, x - s / 2, y - s / 2, r); ctx.arcTo(x - s / 2, y - s / 2, x + s / 2, y - s / 2, r);
            ctx.closePath(); ctx.stroke();
          }
        };
      };
      // 3 · a handful of small bars thrown up from the finger, falling back
      const burst = () => {
        const n = Math.floor(rnd(22, 44)), ps = [];
        for (let i = 0; i < n; i++) {
          const a = rnd(0, Math.PI * 2), v = rnd(110, 330);
          ps.push({ vx: Math.cos(a) * v, vy: Math.sin(a) * v - 140, r: rnd(0, 6), s: rnd(-7, 7), w: rnd(3, 6), h: rnd(8, 24), c: Math.random() < 0.65 ? accent : ink2 });
        }
        return t => {
          const T = t * 1.4; ctx.globalAlpha = Math.max(0, 1 - t * t);
          ps.forEach(p => { ctx.save(); ctx.translate(x + p.vx * T, y + p.vy * T + 430 * T * T); ctx.rotate(p.r + p.s * T); ctx.fillStyle = p.c; rr(-p.w / 2, -p.h / 2, p.w, p.h, p.w / 2); ctx.restore(); });
        };
      };
      // 4 · 「你好」 in another language, a letter at a time, and which language under it, on a soft card of its own in the
      // middle of the screen (over the page's own words it would not read)
      const hello = () => {
        const w = HELLO[Math.floor(Math.random() * HELLO.length)], chars = Array.from(w[0]), tilt = rnd(-0.04, 0.04);
        return t => {
          ctx.save(); ctx.translate(W / 2, H * 0.42); ctx.rotate(tilt);
          ctx.font = `600 40px ${font}`; ctx.textBaseline = 'middle';
          const tw = ctx.measureText(w[0]).width, bw = Math.max(tw, 150) + 56, fade = Math.min(1, t * 6) * Math.min(1, (1 - t) * 3);
          ctx.globalAlpha = fade * 0.96; ctx.fillStyle = paper; ctx.shadowColor = 'rgba(0,0,0,.14)'; ctx.shadowBlur = 24; ctx.shadowOffsetY = 6;
          rr(-bw / 2, -50, bw, 104, 22); ctx.shadowColor = 'transparent'; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
          let px = -tw / 2;
          chars.forEach((ch, i) => {
            const u = Math.max(0, Math.min(1, t * 4 - i * 0.22)), cw = ctx.measureText(ch).width;
            ctx.globalAlpha = out(u) * Math.min(1, (1 - t) * 3); ctx.fillStyle = ink; ctx.fillText(ch, px, -8 + (1 - out(u)) * 18); px += cw;
          });
          ctx.font = `400 13.5px ${font}`; ctx.fillStyle = muted; ctx.globalAlpha = Math.max(0, Math.min(1, t * 4 - 1)) * Math.min(1, (1 - t) * 3);
          const s = zhEn(`${w[1]}语里的「你好」`, `“Hello” in ${w[2]}`); ctx.fillText(s, -ctx.measureText(s).width / 2, 30);
          ctx.restore();
        };
      };
      const kinds = [wave, rings, burst, hello];
      let k;
      do { k = Math.floor(Math.random() * kinds.length); } while (k === last);
      last = k;
      const draw = kinds[k](), t0 = performance.now();
      cv.dataset.kind = ['wave', 'rings', 'burst', 'hello'][k];
      const loop = () => {
        const t = (performance.now() - t0) / MS;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H); ctx.globalAlpha = 1;
        if (t >= 1 || !cv.isConnected) { cv.remove(); busy = false; return; }
        draw(t); requestAnimationFrame(loop);
      };
      requestAnimationFrame(loop);
      return true;
    }
    // hold the greeting: a move, a lift or a scroll first is not a hold; the text is never selected
    function bindGreeting(el) {
      if (!el) return;
      let hold = 0, x0 = 0, y0 = 0;
      const stop = () => { clearTimeout(hold); hold = 0; };
      el.addEventListener('pointerdown', e => {
        if (e.button > 0) return;
        x0 = e.clientX; y0 = e.clientY; stop();
        hold = setTimeout(() => { hold = 0; play(x0, y0); }, 450);
      });
      el.addEventListener('pointermove', e => { if (hold && Math.abs(e.clientX - x0) + Math.abs(e.clientY - y0) > 10) stop(); });
      ['pointerup', 'pointercancel', 'pointerleave'].forEach(t => el.addEventListener(t, stop));
      el.addEventListener('contextmenu', e => e.preventDefault());
    }
    // the day's plan all done, seen on 今日 for the first time that day: once, by itself
    function planDone(p) {
      if (!p || !p.total || p.done < p.total) return;
      const day = new Date().toDateString();
      if (load('flow-egg-done') === day) return;
      save('flow-egg-done', day);
      setTimeout(() => play(), 350);
    }
    return { play, bindGreeting, planDone };
  })();
  /* ---------- study ---------- */
  let selbar = null;
  function hideSelbar() { if (selbar) { selbar.remove(); selbar = null; } }
  const MAT = {}; // the material being studied: step changes reuse it instead of refetching and re-animating the header
  // Under the title: where the text comes from and how AI took part (r20). The writing rules of the originals, or the
  // sources of a news text, are one tap away.
  // 「AI 生成」 (2026-11-25, 人工智能生成合成内容标识办法): every text Flow wrote with AI says so under its title, in the
  // shared style (aiMark, 00-head.js). The user's words for a featured text: 「AI 生成，经规范检查」; 经人工审核 only on
  // one the user has read themselves (reviewed_by_human). null: no mark, an article the learner imported is theirs (only
  // its AI questions are marked); '': the mark alone, the older texts (简版) were written before the writing rules.
  function aiNote(m) {
    const o = m.origin || { kind: 'original' };
    if (o.kind === 'import') return null;
    if (o.kind === 'news') return 'AI 改写 · 未经人工审核';
    return m.featured ? (o.reviewed_by_human ? '经规范检查 · 经人工审核' : '经规范检查') : '';
  }
  // 「经规范检查」 says what was checked: a tap opens that section of the guide (#/guide/ai-check)
  function aiCheckLink(mark) { return `<a class="ai-link" href="#/guide/ai-check" data-tap="study-ai-check" aria-label="AI 生成，经规范检查：看规范检查查什么">${mark}</a>`; }
  function originHTML(m, extra = '') {  // extra: 存到手机 (06-offline.js), on the same line so the step below stays in view
    const o = m.origin || { kind: 'original', label: m.source, ai: '', reviewed: null, url: '', references: m.provenance || [] };
    const note = aiNote(m);
    // 「AI 生成 · 经规范检查」 and 来源 share one grey line under the title (2026-11-25, B7: the same words, quieter); two links stay two
    return `<div class="head-note">${note === null ? '' : m.featured ? aiCheckLink(aiMark(note)) : aiMark(note)}<div class="origin tiny"><span class="muted">来源：${o.url ? `<a class="link" href="${esc(o.url)}" target="_blank" rel="noopener noreferrer">${esc(o.label)}</a>` : esc(o.label)}</span>${note === null && o.ai ? `<span class="otag">${esc(o.ai)}</span>` : ''}${note === null && o.reviewed === false ? '<span class="otag warn">未经人工审核</span>' : ''}${o.kind === 'import' ? '' : `<button class="link tiny hit44" type="button" id="originMore" data-tap="study-origin">${o.references.length ? `${o.kind === 'news' ? '来源' : '参考资料'} ${o.references.length} 条` : '怎么写的'}</button>`}${extra}</div></div>`;
  }
  function originSheet(m) {
    const o = m.origin, news = o.kind === 'news', topic = o.kind === 'topic';
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">这篇材料从哪来</h2>
      ${topic ? '<p class="small">今日一读是 AI 每天写的一篇原创短文（AI 生成）：话题从固定的话题池和节日、节气里选，不联网检索，不写新闻、时政、真实人物，也不写具体日期和数字。发布前先查一遍新闻和时政的词，再让 AI 自己查一遍，有一项不过就不发。没有人逐篇读过，当作额外阅读就好。</p>'
        : news ? '<p class="small">今日热点是 AI 联网检索新闻后改写成的学习材料，<b>没有经过人工审核</b>。下面是它检索到的来源，事实以原文为准。</p>'
        : m.featured ? `<p class="small">精选材料由 Flow 编辑部按统一的写作规范原创${o.ai ? `（${esc(o.ai)}）` : ''}：</p>
          <ul class="small origin-rules"><li>不抄、不改写已有的文章、书籍和影视台词；</li><li>只写广为人知、稳定的常识，不写具体的统计数字、年份、价格和研究结论；</li><li>不写在世的真实人物，也不写时事新闻；</li><li>引用名句只用已进入公有领域的，并写明出处；</li><li>每道理解题的答案都要在原文里找得到依据，发布前由程序逐篇检查。</li></ul>`
        : `<p class="small">这是 Flow 编辑部较早用 AI 编写的练习材料${o.ai ? `（${esc(o.ai)}）` : ''}，比精选短，没有中文导读和表达。</p>`}
      ${(o.quotes || []).length ? `<div class="stack-s"><b class="small">文中引用的名句</b>${o.quotes.map(q => `<span class="small">“${esc(q.text)}” · ${esc(q.author)}，${esc(q.work)}（${esc(String(q.year))}）</span>`).join('')}</div>` : ''}
      ${o.references.length ? `<div class="stack-s"><b class="small">${news ? '来源' : '核对事实用的参考资料'}</b>${o.references.map(r => `<a class="link small" href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a>`).join('')}</div>` : ''}
      <button class="btn ghost" data-close type="button">知道了</button></div>`);
  }

  async function study(id, step, same) {
    let m = (same || (MAT[id] && Date.now() - (MAT[id]._preloaded || 0) < 6e5)) && MAT[id];
    if (m) delete m._preloaded;
    if (!m) {
      // A copy kept on the phone (one of the last five opened) shows at once; the server's copy replaces it for the
      // next step. Otherwise the request is often already on its way: preloaded from 今日 or when the link was touched.
      // A material kept with 存到手机 (06-offline.js) comes first: only that copy has the answers, to grade without a
      // connection, and the fresher copy from the server keeps them.
      const path = materialPath(id), off = OFF.get(id), kept = off || snapMaterialGet(path);
      if (kept) {
        m = kept; MAT[id] = m;
        api(path).then(f => { if (!f.answers && kept.answers) f.answers = kept.answers; if (MAT[id] === kept) MAT[id] = f; snapMaterial(path, f); if (off) OFF.put(id, f); }).catch(() => {});
      }
      else { m = await api(path); MAT[id] = m; snapMaterial(path, m); }
    }
    const done = new Set(m.steps.concat(load('flow-next-steps-' + id) || []));
    const st = { step: STEPS.includes(step) ? step : 'listen', showOriginal: !!m._showOriginal, blind: false };
    const lines = () => st.showOriginal && m.original ? m.original : m.sentences;

    function markStep(s) {
      if (done.has(s)) return;
      done.add(s); save('flow-next-steps-' + id, Array.from(done));
      // without a connection the step waits in the outbox and is sent when the phone is back online
      if (S.user) api('/api/next/progress', { pack: id, step: s }).catch(e => { if (e.network) OUTBOX.push({ path: '/api/next/progress', body: { pack: id, step: s } }); });
      const tab = view.querySelector(`[data-step="${s}"]`); if (tab && !tab.querySelector('.ok')) tab.insertAdjacentHTML('beforeend', '<span class="ok">✓</span>');
    }
    function go(s) { location.hash = `#/m/${encodeURIComponent(id)}/${s}`; }

    if (!same) {
      // 存到手机 sits at the right of the kicker line, so the source line under the title stays one line on a phone
      view.innerHTML = `<div class="study-head"><div class="sh-top"><span class="kicker">${m.series ? `<a class="link" href="#/series/${encodeURIComponent(m.series.id)}">连载《${esc(m.series.title)}》第 ${m.series.part} / ${m.series.of} 集</a> · ${m.level}` : `${esc(m.theme_label)} · ${m.level}${m.variant ? ' → ' + m.variant.level : ''}${m.featured ? ' · 精选' : ''}`}</span>${offChip(id)}</div>
        <h1 class="h1">${esc(m.title)}</h1>${m.title_en ? `<div class="title-en">${esc(m.title_en)}</div>` : ''}
        ${originHTML(m)}</div>
        <div class="steps" role="tablist"><span class="ind" aria-hidden="true"></span>${STEPS.map(s => `<button role="tab" data-step="${s}" aria-selected="false">${STEP[s]}${done.has(s) ? '<span class="ok">✓</span>' : ''}</button>`).join('')}</div>
        <section id="pane"></section>`;
      view.querySelectorAll('[data-step]').forEach(b => b.onclick = () => go(b.dataset.step));
      const om = view.querySelector('#originMore'); if (om) om.onclick = () => originSheet(m);
    }
    // Slide the tab indicator, and slide the pane in from the direction of travel.
    const tabs = [...view.querySelectorAll('[data-step]')];
    const prev = tabs.findIndex(b => b.getAttribute('aria-selected') === 'true');
    tabs.forEach(b => b.setAttribute('aria-selected', String(b.dataset.step === st.step)));
    const head = view.querySelector('.study-head'); if (head) head.dataset.at = st.step;
    bindOffChip(id);  // phones: a shorter header once past listen and read
    const active = tabs.find(b => b.dataset.step === st.step), ind = view.querySelector('.steps .ind');
    const place = () => { ind.style.width = active.offsetWidth + 'px'; ind.style.transform = `translateX(${active.offsetLeft}px)`; };
    if (prev < 0) { ind.style.transition = 'none'; place(); requestAnimationFrame(() => { ind.style.transition = ''; }); } else requestAnimationFrame(place);
    const pane = view.querySelector('#pane');
    pane.style.setProperty('--dir', (prev > STEPS.indexOf(st.step) ? -14 : 14) + 'px');
    pane.classList.remove('pane-enter'); void pane.offsetWidth; pane.classList.add('pane-enter');
    // Switching steps far down the page: jump so the step bar sits under the header and the new content starts right below
    // it (the header comes back when scrolling up, so its height is always allowed for).
    if (same) { const top = view.querySelector('.study-head').getBoundingClientRect().bottom + scrollY - bar.offsetHeight; if (scrollY > top) scrollTo({ top, behavior: 'auto' }); }

    /* listen: sentence list, word-by-word highlight while it plays */
    // Narration is usable when this material has the chosen voice and the shown text is the original.
    async function narration(ls) {
      const voices = (m.audio && m.audio.voices) || [];
      if (!voices.length || (m.variant && !st.showOriginal)) return null;
      // not recorded in the learner's voice: another of its recordings, for this text only (S.voice, the setting, stays)
      const ok = await NAR.load(id, voices.includes(S.voice) ? S.voice : voices[0], m.audio.version);
      return ok && NAR.meta && NAR.meta.sentences.length === ls.length ? NAR.meta : null;
    }
    const LOOP = Object.assign({ rep: 1, gap: 0 }, load('flow-next-loop') || {});  // 复读, kept on the phone
    // 复听 (relisten_service), from 今日: the text hidden at first; after a listen, how much was understood, then the text.
    const RELISTEN = [[3, '几乎都懂'], [2, '大部分'], [1, '一半左右'], [0, '很少']];
    function relistenHTML() {
      return st.relistened ? `<div class="card sunk stack-s relisten" id="relisten" aria-live="polite"><b>${esc(st.relistened)}</b><span class="small muted">原文出来了：没听懂的句子，点句子前面的喇叭单独再听几遍。</span></div>`
        : `<div class="card sunk stack-s relisten" id="relisten"><b>复听：先不看原文，从头听一遍</b>
          <span class="small">点「播放全文」。听完选一下听懂了多少，原文就会出来，再看没听懂的句子。</span>
          <div class="chips" role="group" aria-label="听懂了多少">${RELISTEN.map(([k, l]) => `<button class="chip" type="button" data-und="${k}">${l}</button>`).join('')}</div></div>`;
    }
    function bindRelisten() {
      const showText = () => {
        st.blind = false; pane.querySelectorAll('.line .txt').forEach(t => t.classList.remove('blind'));
        document.querySelectorAll('#blind, #psBlind').forEach(bl => { bl.classList.remove('on'); bl.setAttribute('aria-pressed', 'false'); });  // 👁 is in the bar
        const box = pane.querySelector('#relisten'); if (box) box.outerHTML = relistenHTML();
      };
      pane.querySelectorAll('[data-und]').forEach(b => b.onclick = async () => {
        const body = { pack: id, understood: Number(b.dataset.und) }, label = b.textContent;
        pane.querySelectorAll('[data-und]').forEach(x => { x.disabled = true; });
        try {
          const r = await api('/api/next/relisten', body);
          st.relistened = `记下了：听懂了${r.label}。` + (r.known ? '这篇已经听熟了，以后不再安排复听。' : `${r.next_days} 天后再听一次。`);
        } catch (e) {
          if (!e.network) { toast(e.message); pane.querySelectorAll('[data-und]').forEach(x => { x.disabled = false; }); return; }
          OUTBOX.push({ path: '/api/next/relisten', body });  // without a connection: sent when the phone is back online
          st.relistened = `记下了：听懂了${label}，联网后同步。`;
        }
        showText();
      });
    }
    async function listen() {
      MINI.undock();  // 精听 docks it again below; 跟读 and 听写 have their own buttons
      const again = parts()[3] === 'again' && !!S.user;
      if (again && !st.againSet) { st.againSet = true; st.mode = 'listen'; st.blind = true; }
      if (st.mode === 'shadow') return shadowMode();
      if (st.mode === 'dictate') return dictateMode();
      const ls = lines();
      const nm = await narration(ls);
      const voices = (m.audio && m.audio.voices) || [];
      // The user's pick (语流 B9's design, 2026-11-25): 播放全文, 「AI 合成」, the speed and 👁 sit in the bar above the tabs
      // (MINI, docked), where the thumb is, and the text starts high on the first screen (B9's r36 audit F1: no row of tools
      // above the sentences); 播放设置 opens from 「1×」 as a sheet, with 「从头开始」 and 只听不看 at its top, playing or not;
      // the how-to is a first-use tip (08-tips.js).
      const rateL = r => `${r}×`;
      // 「AI 合成」 is said once, in the bar by the play button (the user, 2026-11-25: no second line); the browser's own
      // voice is not AI, and only this line says so
      // a recording this device cannot play (no AAC decoder): said here too, as the reason the text is read sentence by sentence
      const lead = voices.length && !NAR.aac ? (SV.on() ? '这台设备放不了录音的格式，改用 AI 朗读一句一句读。' : '这台设备放不了录音的格式，先用浏览器朗读。')
        : nm || SV.on() ? '' : '这篇还没有录音，先用浏览器朗读。';
      const hint = `点 👁 只听不看，点喇叭单句反复听${TOUCH ? '' : '；空格键播放 / 暂停'}。`;  // one line on SE (F1)
      pane.innerHTML = `${again ? relistenHTML() : ''}${modeTabs()}${prereadHTML()}
        <p class="tiny muted sv-prep" id="lsPrep" role="status" hidden></p>
        ${!nm && !TTS.can() ? '<p class="err">这个浏览器不支持朗读，可以直接去「读」。</p>' : ''}
        <p class="muted tiny listen-tip">${lead}</p>
        ${tipSlot('listen', hint)}
        <div class="lines">${ls.map((s, i) => `<div class="line" data-i="${i}"><button class="icon-btn" data-say="${i}" aria-label="播放第 ${i + 1} 句">${ICON.speak}</button><div class="txt ${st.blind ? 'blind' : ''}">${wordSpans(s, () => 'kw')}</div></div>`).join('')}</div>
        <div class="section row between"><span class="muted small">共 ${ls.length} 句${nm ? ' · ' + Math.round(nm.duration / 60 * 10) / 10 + ' 分钟' : ''}</span><button class="btn" id="toRead">听完了，去读 →</button></div>`;
      let shown = -1;
      const lineEl = i => pane.querySelector(`.line[data-i="${i}"]`);
      const setNow = i => pane.querySelectorAll('.line').forEach(el => { const on = Number(el.dataset.i) === i; el.classList.toggle('now', on); if (!on) el.querySelectorAll('.cur').forEach(x => x.classList.remove('cur')); });
      const light = (el, c) => { if (!el) return; if (c == null) el.querySelectorAll('.cur').forEach(x => x.classList.remove('cur')); else lightWord(el, c); };
      // 播放全文 (LONG, 01-audio-offline.js): 暂停 / 继续, and where it was left kept on this phone: 「从第 N 句继续」.
      // #playAll is the bar's button: its start label is painted here, its 暂停 / 继续 by the player (MINI.paint).
      const PKEY = 'listen:' + id;
      const setBtn = () => {
        const b = document.getElementById('playAll'), rs = document.getElementById('playRestart'), rb = MINI.el && MINI.el.querySelector('.speed-set');
        const r = LONG.of(PKEY), at = r ? r.i : PROG.at(PKEY, ls.length);
        if (rs) rs.hidden = !at;
        if (rb) rb.textContent = rateL(TTS.rate);
        if (!b || MINI.h) return;
        b.innerHTML = `${playIcon(false, 15)}<span>${at ? `从第 ${at + 1} 句继续` : '播放全文'}</span>`;
        b.setAttribute('aria-pressed', 'false');
      };
      const prepLine = note => { const p = pane.querySelector('#lsPrep'); if (p) { p.textContent = note || ''; p.hidden = !note; } };
      const stopAll = () => { loopTok++; clearTimeout(loopTimer); LONG.stop(); TTS.stop(); NAR.stop(); shown = -1; setNow(-1); MINI.hide(); setBtn(); };
      // 复读: a sentence said LOOP.rep times (0: until stopped), with a pause after it: none, 2 s, or as long as the
      // sentence itself and a little more, to say it back.
      let loopTok = 0, loopTimer = 0;
      const gapMs = i => (LOOP.gap === -1 ? Math.max(1500, nm ? (nm.sentences[i].e - nm.sentences[i].s) * 1300 : ls[i].split(' ').length * 450) : LOOP.gap * 1000);
      const sayRepeated = (i, then, n = 0) => {
        const tok = loopTok;
        sayLine(i, () => {
          if (tok !== loopTok) return;
          const more = LOOP.rep === 0 || n + 1 < LOOP.rep, next = () => { if (tok === loopTok) { if (more) sayRepeated(i, then, n + 1); else if (then) then(); } };
          const g = more || then ? gapMs(i) : 0;
          if (g) loopTimer = setTimeout(next, g); else next();
        });
      };
      const looping = () => LOOP.rep !== 1 || LOOP.gap !== 0;
      // one sentence: its part of the recording, else the server voice (the browser voice only when that cannot)
      const sayLine = (i, then) => {
        if (nm) { NAR.play(nm.sentences[i].s, nm.sentences[i].e, t => { const [si, wc] = NAR.locate(t); if (si === i) lightAt(lineEl(i), wc); }, then); return; }
        const el = lineEl(i); TTS.say(ls[i], then, c => lightWord(el, c), { pack: id, title: '语流 · ' + m.title });
      };
      // 语速 and 复读 set from outside (the iOS app's lock screen, NATIVE.takeKnobs): kept; the bar's 1× and an open 播放设置 follow
      const knobsShown = () => {
        setBtn();
        document.querySelectorAll('#sheet [data-rate]').forEach(x => x.setAttribute('aria-pressed', String(Number(x.dataset.rate) === TTS.rate)));
        document.querySelectorAll('#sheet [data-rep]').forEach(x => x.setAttribute('aria-pressed', String(Number(x.dataset.rep) === LOOP.rep)));
      };
      const readAll = (from, auto) => LONG.start({
        key: PKEY, texts: ls, nm, pack: id, title: m.title, loop: looping(), rep: () => LOOP.rep, gap: gapMs, label: i => `第 ${i + 1} / ${ls.length} 句`, auto: !!auto,
        setRep: n => { LOOP.rep = n; save('flow-next-loop', LOOP); }, onKnobs: knobsShown,
        onState: (state, i, note) => {
          setBtn(); prepLine(note);
          if (state === 'idle') { shown = -1; setNow(-1); return; }
          if (i !== shown) { shown = i; setNow(i); const el = lineEl(i); if (el && state !== 'paused') el.scrollIntoView({ block: 'center', behavior: REDUCED ? 'auto' : 'smooth' }); }
        },
        onWord: (i, c) => light(lineEl(i), c),
        onDone: () => markStep('listen'),
      }, from);
      const playAll = () => {
        if (LONG.of(PKEY)) { LONG.toggle(); return; }
        loopTok++; clearTimeout(loopTimer);  // a sentence repeating
        readAll(PROG.at(PKEY, ls.length));
      };
      // 播放设置 from 「1×」: 语速, 复读 (times, the pause after), 声音; it takes effect at once, also on what is playing
      // 盲听 (只听不看): the bar's 👁, the switch in 播放设置, and the sentences, kept in step
      const setBlind = on => {
        st.blind = on; pane.querySelectorAll('.txt').forEach(t => t.classList.toggle('blind', on));
        document.querySelectorAll('#blind, #psBlind').forEach(b => { b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on)); });
        toast(on ? '盲听：只听不看，再点一次显示原文' : '已显示原文');
      };
      const playsetHTML = () => `<div class="stack"><h2 class="h2" id="sheetTitle">播放设置</h2>
        <div class="row between ps-top"><button class="chip small${st.blind ? ' on' : ''}" type="button" id="psBlind" aria-pressed="${st.blind}">${ICON.eye}<span>只听不看</span></button>
          <button class="btn small" type="button" id="playRestart"${PROG.at(PKEY, ls.length) || LONG.of(PKEY) ? '' : ' hidden'}>从头开始</button></div>
        <div class="loopbar">
          <div class="lg" role="group" aria-label="语速"><span class="tiny muted">语速</span>${[0.75, 1, 1.25].map(r => `<button class="chip small" type="button" data-rate="${r}" aria-pressed="${TTS.rate === r}">${r}×</button>`).join('')}</div>
          <div class="lg" role="group" aria-label="复读：每句几遍"><span class="tiny muted">每句</span>${[[1, '1 遍'], [3, '3 遍'], [5, '5 遍'], [0, '循环']].map(([n, l]) => `<button class="chip small" type="button" data-rep="${n}" aria-pressed="${LOOP.rep === n}">${l}</button>`).join('')}</div>
          <div class="lg" role="group" aria-label="复读：句后停顿"><span class="tiny muted">句后</span>${[[0, '不停'], [2, '停 2 秒'], [-1, '留时间跟说']].map(([n, l]) => `<button class="chip small" type="button" data-gap="${n}" aria-pressed="${LOOP.gap === n}">${l}</button>`).join('')}</div>
          ${voices.length ? `<div class="lg"><span class="tiny muted">声音</span>${voiceChips(voices)}</div>` : ''}</div>
        <button class="btn block" type="button" id="psDone" data-close>好</button></div>`;
      const openPlayset = () => openSheet(playsetHTML(), card => {
        card.querySelector('#psBlind').onclick = () => setBlind(!st.blind);
        card.querySelector('#playRestart').onclick = () => { closeSheet(); LONG.stop(); PROG.clear(PKEY); readAll(0); };
        card.querySelectorAll('[data-rep], [data-gap]').forEach(b => b.onclick = () => {
          const k = 'rep' in b.dataset ? 'rep' : 'gap'; LOOP[k] = Number(b.dataset[k]); save('flow-next-loop', LOOP);
          NATIVE.retune();  // the app playing it gets the new 复读 at once
          card.querySelectorAll(`[data-${k}]`).forEach(x => x.setAttribute('aria-pressed', String(x === b)));
        });
        card.querySelectorAll('[data-rate]').forEach(b => b.onclick = () => {
          TTS.rate = Number(b.dataset.rate); save('flow-next-rate', TTS.rate); NAR.audio.playbackRate = TTS.rate; NATIVE.retune();
          card.querySelectorAll('[data-rate]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); setBtn();
        });
        card.querySelectorAll('[data-voice]').forEach(b => b.onclick = async () => { if (b.disabled) return; closeSheet(); stopAll(); await setVoice(b.dataset.voice); listen(); toast('已切换为' + VOICE_LABELS[b.dataset.voice]); });
      });
      // attach: the app plays this text (语流's iOS app, loaded again): the bar becomes its player (NATIVE.adopt)
      MINI.dock({ key: PKEY, ai: () => !!nm || SV.on(), paint: setBtn, play: playAll, rate: openPlayset, attach: () => readAll(PROG.at(PKEY, ls.length), true),
        blind: { on: () => st.blind, toggle: () => setBlind(!st.blind) } });
      setBtn();
      NATIVE.follow(PKEY, setBtn);  // in the app: the button says where the app got to (it may have played on, or still plays)
      pane.querySelectorAll('[data-say]').forEach(b => b.onclick = () => {
        const i = Number(b.dataset.say); stopAll(); setNow(i);
        if (looping()) MINI.show(`复读第 ${i + 1} 句`, { stop: stopAll, ai: !!nm || SV.on() });  // a stop button on screen while it repeats
        sayRepeated(i, () => { setNow(-1); MINI.hide(); });
      });
      pane.querySelectorAll('.line .txt').forEach((t, i) => t.onclick = e => { if (e.target.dataset.w && !st.blind) lookupSheet(e.target.dataset.w, ls[i], id); });
      pane.querySelector('#toRead').onclick = () => { stopAll(); markStep('listen'); go('read'); };
      if (again) bindRelisten();
      bindListenHead(stopAll);
      document.onkeydown = e => {
        if (isTyping(e) || !sheetEl.hidden || e.metaKey || e.ctrlKey || e.altKey) return;
        const b = document.getElementById('playAll'); if (b && (e.key === ' ' || e.key === 'k')) { e.preventDefault(); b.click(); }
      };
    }

    /* listen modes: 精听 (sentence list) · 跟读 (record, compare, AI feedback) · 听写 (type what you hear) */
    const MODES = { listen: '精听', shadow: '跟读', dictate: '听写' };
    if (!st.mode) st.mode = MODES[load('flow-next-listen-mode')] ? load('flow-next-listen-mode') : 'listen';
    const stripLabel = s => s.replace(/^(?:[A-Z][a-z]+(?: [A-Z][a-z]+)?|[A-Z]):\s+/, '');  // speaker labels and Q:/A: are shown, not read
    // The words worth knowing before listening, folded into one line (open it for the meaning, the sound, review).
    function prereadHTML() {
      const pr = m._prHidden ? [] : (m.preread || []);
      return pr.length ? `<details class="fold preread"><summary data-tap="listen-preread"><b class="small">读前先认识这 ${pr.length} 个词</b><span class="tiny muted">${pr.map(w => esc(w.word)).join(' · ')}</span></summary>
          <div class="stack-s"><div class="pr-list">${pr.map((w, k) => `<div class="pr"><button class="icon-btn" data-prsay="${k}" aria-label="朗读 ${esc(w.word)}">${ICON.speak}</button>
            <div><b>${esc(w.word)}</b> <span class="ph">${esc(w.phonetic)}</span><div class="tiny muted" data-zh>${esc(w.meaning)}</div></div></div>`).join('')}</div>
          <div class="row"><button class="btn small primary" id="prAdd">全部加入复习</button><span class="muted tiny">加入后会在文章里标出来</span></div></div></details>` : '';
    }
    function modeTabs() {
      return `<div class="seg modes" role="tablist" aria-label="听的方式">${Object.entries(MODES).map(([k, l]) => `<button role="tab" data-mode="${k}" aria-selected="${st.mode === k}">${l}</button>`).join('')}</div>`;
    }
    function listenHead() { return modeTabs() + prereadHTML(); }
    function bindListenHead(stop) {
      pane.querySelectorAll('[data-mode]').forEach(b => b.onclick = () => { stop(); st.mode = b.dataset.mode; save('flow-next-listen-mode', st.mode); listen(); });
      const pr = m.preread || [];
      pane.querySelectorAll('[data-prsay]').forEach(b => b.onclick = () => { stop(); const w = pr[Number(b.dataset.prsay)]; CLIP.word({ text: w.word, audio: w.audio }); });
      const add = pane.querySelector('#prAdd');
      if (add) add.onclick = async () => {
        if (!S.user) return needLogin('登录后可以把这些词加入复习，按遗忘曲线安排。');
        add.disabled = true;
        try {
          const r = await api('/api/next/vocab/add', { pack: id, items: pr.map(w => ({ word: w.word, sentence: findContext(w.form, lines()) })) });
          toast(r.added ? `已加入 ${r.added} 个词，读的时候会标出来` : '这些词已经在复习里了');
          m.mine = (m.mine || []).concat(pr.map(w => ({ form: w.form, id: 0 })));
          m._prHidden = true; pane.querySelector('.preread').remove(); refreshHome().catch(() => {});
        } catch (e) { toast(e.message); add.disabled = false; }
      };
    }
    function wordDiff(target, typed) {  // same alignment as the server's compare_words
      const t = (target.toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g) || []), h = (typed.toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g) || []);
      const L = Array.from({ length: t.length + 1 }, () => new Array(h.length + 1).fill(0));
      for (let i = t.length - 1; i >= 0; i--) for (let j = h.length - 1; j >= 0; j--) L[i][j] = t[i] === h[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
      const out = []; let i = 0, j = 0;
      while (i < t.length) {
        if (j < h.length && t[i] === h[j]) { out.push({ w: t[i], ok: true }); i++; j++; }
        else if (j < h.length && L[i][j + 1] >= L[i + 1][j]) j++;
        else { out.push({ w: t[i], ok: false }); i++; }
      }
      return out;
    }
    const wordsHTML = ws => `<div class="wdiff">${ws.map(w => `<span class="${w.ok ? 'ok' : 'miss'}">${esc(w.w)}</span>`).join(' ')}</div>`;

    // 发音分 of 跟读: accuracy and fluency are the AI's estimate from the recording, completeness is counted from what it
    // heard (next_service.pron_score). Each sentence's latest score stays on its row while the material is open.
    const shScores = m._shScores || (m._shScores = {});
    function shAvgHTML() {
      const v = Object.values(shScores);
      return `<p class="tiny muted" id="shAvg"${v.length ? '' : ' hidden'}>${v.length ? `这篇已经点评 ${v.length} 句，发音分平均 ${Math.round(v.reduce((a, b) => a + b, 0) / v.length)}（AI 估计）` : ''}</p>`;
    }
    function pronHTML(x) {
      const sc = x.score;
      if (!sc) return x.matched ? '' : '<div class="small err">AI 没听清这一句。离麦克风近一点，完整读一遍再点评。</div>';
      const bar = (l, v, txt) => `<div class="ab"><span class="nm">${l}</span><span class="vbar"><i data-w="${v}"></i></span><span class="lv">${txt == null ? v : txt}</span></div>`;
      return `<div class="pron"><div class="pron-top"><b class="pron-n">${sc.total}</b><span class="stack-xs"><b>发音分</b></span></div>
          <div class="ab-list">${bar('准确', sc.accuracy)}${bar('流利', sc.fluency)}${bar('完整', sc.complete, `${x.matched}/${x.words.length}`)}</div></div>`;
    }
    function soundsHTML(ss) {
      return ss && ss.length ? `<div class="stack-s"><b class="small">要练的音</b>${ss.map(s => `<div class="snd small"><b class="ph">${esc(s.sound)}</b>
          <span><b>${esc(s.word)}</b>：<span data-ex>${esc(s.note)}</span>${s.set ? ` <a class="link" href="#/sounds/${encodeURIComponent(s.set)}" data-tap="shadow-sound">去练 ${esc(s.set_title)} →</a>` : ''}</span></div>`).join('')}</div>` : '';
    }
    async function shadowMode() {
      const ls = lines(), nm = await narration(ls);
      // Every sentence keeps its ▶; the recording tools (the record key, 对比, AI 点评) show under the sentence being practised only,
      // so eleven rows of four buttons do not bury the text. A tap anywhere on a sentence makes it the one.
      pane.innerHTML = `${listenHead()}<p class="muted small">${nm || SV.on() ? aiVoiceNote('朗读由 AI 合成。', 'span', 'in') : ''}点一句开始练：先点 ▶ 听原声，再点录音键跟着读一遍（再点一次停止）。「对比」先放原声再放你的录音；${S.user ? '「AI 点评」给一个发音分（AI 估计），写出它听到的内容和要练的音。' : '登录后可以让 AI 点评、给发音分。'}</p>
        ${shAvgHTML()}
        <div class="lines">${ls.map((s, i) => `<div class="line sh${i === 0 ? ' cur' : ''}" data-i="${i}"><div class="txt">${esc(s)}</div>
          <div class="sh-ctl"><button class="icon-btn" data-o="${i}" aria-label="听原声">${ICON.play.replace('<svg', '<svg fill="currentColor"')}</button>
            <button class="icon-btn rec" data-r="${i}" aria-label="录音" aria-pressed="false">${REC_MARK}</button>
            <button class="btn small" data-c="${i}" disabled>对比</button><button class="btn small" data-ai="${i}" disabled>✦ AI 点评</button>${shScores[i] != null ? `<span class="pron-chip" data-sc="${i}" title="这一句的发音分（AI 估计）">${shScores[i]}</span>` : `<span class="pron-chip" data-sc="${i}" hidden></span>`}</div>
          <div class="sh-out"></div></div>`).join('')}</div>
        <div class="section row between"><span></span><button class="btn" id="toRead">去读 →</button></div>`;
      const REC = { mr: null, blobs: {}, timer: 0, url: {} };
      const row = i => pane.querySelector(`.line[data-i="${i}"]`);
      pane.querySelectorAll('.line.sh').forEach(l => l.addEventListener('click', () => {
        if (l.classList.contains('cur')) return;
        pane.querySelectorAll('.line.sh.cur').forEach(x => x.classList.remove('cur')); l.classList.add('cur');
      }, true));  // capture: a tap on ▶ of another sentence plays it and makes it the one
      const stop = () => { TTS.stop(); NAR.stop(); CLIP.stop(); if (REC.mr && REC.mr.state === 'recording') REC.mr.stop(); };
      const orig = (i, then) => { if (nm) NAR.play(nm.sentences[i].s, nm.sentences[i].e, null, then); else TTS.say(stripLabel(ls[i]), then, null, { pack: id }); };
      async function record(i, btn) {
        if (REC.mr && REC.mr.state === 'recording') { REC.mr.stop(); return; }
        if (!micReady(() => record(i, btn))) return;
        stop();
        let stream;
        try { stream = await micOpen(); } catch (e) { toast(e.message); return; }  // 70-learner.js: open only while recording
        const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
        const mr = recorderFor(stream, type ? { mimeType: type } : undefined, 25), chunks = [];  // the app's cap; the timer below stops it sooner
        REC.mr = mr;
        mr.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
        mr.onstop = () => {
          micClose(stream); clearTimeout(REC.timer); btn.classList.remove('on'); btn.setAttribute('aria-label', '录音');
          if (!chunks.length) return;
          REC.blobs[i] = new Blob(chunks, { type: mr.mimeType || type || 'audio/webm' });
          if (REC.url[i]) URL.revokeObjectURL(REC.url[i]);
          REC.url[i] = URL.createObjectURL(REC.blobs[i]);
          row(i).querySelector('[data-c]').disabled = false; row(i).querySelector('[data-ai]').disabled = false;
        };
        mr.start(); btn.classList.add('on'); btn.setAttribute('aria-label', '停止录音');
        const secs = nm ? (nm.sentences[i].e - nm.sentences[i].s) * 2.2 + 2 : 12;
        REC.timer = setTimeout(() => { if (mr.state === 'recording') mr.stop(); }, Math.min(25, secs) * 1000);
      }
      function compare(i) { stop(); orig(i, () => CLIP.mine(REC.url[i])); }
      async function aiCheck(i, btn) {
        if (!S.user) return needLogin('登录后，AI 会听你的跟读，指出漏读、读错和需要连读的地方。');
        const blob = REC.blobs[i]; if (!blob) return;
        if (blob.size > 1400000) { toast('录音太长了，读这一句就好'); return; }
        btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
        try {
          const data = await new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1]); r.onerror = no; r.readAsDataURL(blob); });
          const mime = /wav/.test(blob.type) ? 'audio/wav' : /mp4|m4a|aac/.test(blob.type) ? 'audio/mp4' : /ogg/.test(blob.type) ? 'audio/ogg' : 'audio/webm';  // wav: 语流's iOS app
          const x = (await api('/api/next/shadow', { pack: id, i, audio: { mime_type: mime, data }, request_id: rid('sh') })).result;
          const flu = { smooth: '流畅', ok: '基本流畅', choppy: '有点断断续续' }[x.fluency];
          const out = row(i).querySelector('.sh-out');
          out.innerHTML = `<div class="card flat sh-res stack-s enter" data-ex-block>${aiMark('发音分和点评由 AI 估计，仅供参考')}${pronHTML(x)}${soundsHTML(x.sounds)}
            ${x.issues.length ? `<div class="stack-s"><b class="small">${x.sounds && x.sounds.length ? '其他要注意的' : '要注意的'}</b>${x.issues.map(it => `<div class="small"><b>${esc(it.word)}</b>：<span data-ex>${esc(it.note)}</span></div>`).join('')}</div>` : ''}
            ${x.tip ? `<div class="small tip">建议：<span data-ex>${esc(x.tip)}</span></div>` : ''}
            <div class="stack-xs">${wordsHTML(x.words)}<div class="tiny muted">AI 听到：${esc(x.transcript || '（没听清）')} · 读到 ${x.matched}/${x.words.length} 个词${x.score ? '' : ' · ' + flu}</div></div></div>`;
          requestAnimationFrame(() => requestAnimationFrame(() => out.querySelectorAll('.vbar i').forEach(b => { b.style.width = b.dataset.w + '%'; })));
          if (x.score) {
            shScores[i] = x.score.total;
            const chip = row(i).querySelector('[data-sc]'); chip.textContent = x.score.total; chip.hidden = false;
            const avg = pane.querySelector('#shAvg'); if (avg) avg.outerHTML = shAvgHTML();
          }
        } catch (e) { toast(e.message); }
        btn.disabled = false; btn.textContent = '✦ AI 点评';
      }
      pane.querySelectorAll('[data-o]').forEach(b => b.onclick = () => { stop(); orig(Number(b.dataset.o)); });
      pane.querySelectorAll('[data-r]').forEach(b => b.onclick = () => record(Number(b.dataset.r), b));
      pane.querySelectorAll('[data-c]').forEach(b => b.onclick = () => compare(Number(b.dataset.c)));
      pane.querySelectorAll('[data-ai]').forEach(b => b.onclick = () => aiCheck(Number(b.dataset.ai), b));
      pane.querySelector('#toRead').onclick = () => { stop(); markStep('listen'); go('read'); };
      bindListenHead(stop);
    }

    async function dictateMode() {
      const ls = lines(), nm = await narration(ls);
      const score = m._dictScore || (m._dictScore = { got: 0, total: 0 });
      let i = Math.min(m._dictI || 0, ls.length - 1);
      const stop = () => { TTS.stop(); NAR.stop(); CLIP.stop(); };
      const play = slow => {
        stop(); const keep = TTS.rate; TTS.rate = slow ? 0.75 : keep;
        if (nm) NAR.play(nm.sentences[i].s, nm.sentences[i].e, null, null); else TTS.say(stripLabel(ls[i]), null, null, { pack: id });
        TTS.rate = keep;
      };
      function render() {
        pane.innerHTML = `${listenHead()}<div class="card flat dict stack"><div class="row between"><span class="kicker">听写 · 第 ${i + 1} / ${ls.length} 句</span>
            <span class="muted tiny">${score.total ? '这篇正确率 ' + Math.round(score.got / score.total * 100) + '%' : '可以反复播放'}</span></div>
          <div class="row"><button class="btn primary" id="dPlay">${ICON.play.replace('<svg', '<svg width="16" height="16" fill="currentColor"')}<span>播放这一句</span></button><button class="btn small" id="dSlow">慢速</button>${nm || SV.on() ? aiVoiceNote('AI 合成', 'span') : ''}</div>
          <textarea id="dIn" rows="3" lang="en" enterkeyhint="done" placeholder="听到什么写什么，拼不出的词先空着" autocapitalize="off" autocomplete="off" autocorrect="off" spellcheck="false"></textarea>
          <div class="row"><button class="btn" id="dCheck">检查</button><button class="btn ghost" id="dSkip">跳过这句</button></div><div id="dOut"></div></div>
          <div class="section row between"><span class="muted small">听错的词可以直接加入复习。</span><button class="btn" id="toRead">去读 →</button></div>`;
        const inp = pane.querySelector('#dIn');
        pane.querySelector('#dPlay').onclick = () => { play(false); inp.focus({ preventScroll: true }); };
        pane.querySelector('#dSlow').onclick = () => play(true);
        const next = () => { i += 1; m._dictI = i; if (i >= ls.length) { m._dictI = 0; markStep('listen'); toast('这篇听写完了'); i = 0; } render(); play(false); };
        pane.querySelector('#dSkip').onclick = next;
        pane.querySelector('#dCheck').onclick = () => {
          const target = stripLabel(ls[i]), ws = wordDiff(target, inp.value), got = ws.filter(w => w.ok).length;
          score.got += got; score.total += ws.length;
          m._dictChecked = (m._dictChecked || 0) + 1; if (m._dictChecked >= 3) markStep('listen');
          if (S.user && ws.length) api('/api/next/skill', { kind: 'dictation', score: got / ws.length, pack: id }).catch(() => {});
          const missed = [...new Set(ws.filter(w => !w.ok).map(w => w.w))].filter(w => w.length > 3);
          pane.querySelector('#dOut').innerHTML = `<div class="stack-s enter">${wordsHTML(ws)}<div class="muted tiny">写对 ${got} / ${ws.length} 个词</div>
            <div class="row">${missed.length ? `<button class="btn small" id="dAdd">把听错的 ${missed.length} 个词加入复习</button>` : ''}<button class="btn small primary" id="dNext">${i + 1 < ls.length ? '下一句' : '完成'}</button></div></div>`;
          pane.querySelector('#dNext').onclick = next;
          const add = pane.querySelector('#dAdd');
          if (add) add.onclick = async () => {
            if (!S.user) return needLogin('登录后可以把听错的词加入复习。');
            add.disabled = true;
            try {
              const r = await api('/api/next/vocab/add', { pack: id, min_rank: 1500, items: missed.map(w => ({ word: w, sentence: target })) });
              const rest = missed.length - (r.added || 0);
              toast(r.added ? `已加入 ${r.added} 个词${rest ? `；另外 ${rest} 个是常用词或已在复习里` : ''}` : '这几个都是常用词（不用专门背），或已经在复习里了');
              add.textContent = r.added ? `已加入 ${r.added} 个` : '不用加';
            }
            catch (e) { toast(e.message); add.disabled = false; }
          };
        };
        inp.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); pane.querySelector('#dCheck').click(); } });
        pane.querySelector('#toRead').onclick = () => { stop(); go('read'); };
        bindListenHead(stop);
      }
      render();
    }

    /* after reading: the words looked up here (and the pre-reading list) can go into review in one tap */
    function newWordItems() {
      const looked = [...((m._looked && m._looked.values()) || [])];
      const mine = new Set((m.mine || []).map(x => x.form));
      const items = looked.filter(x => !mine.has(x.word)).map(x => ({ ...x, on: true }));
      (m.preread || []).forEach(w => { if (!items.some(x => x.word === w.word) && !mine.has(w.form)) items.push({ word: w.word, meaning: w.meaning, sentence: findContext(w.form, lines()), on: false }); });
      return items.slice(0, 14);
    }
    function newWordsHTML() {
      const items = newWordItems();
      if (!items.length) return '<p class="muted small">读的时候点过的词会出现在这里，勾选后按遗忘曲线复习。</p>';
      return `<div class="stack-s" id="newWords"><div class="row between"><b class="small">这篇的生词</b><span class="muted tiny">勾选的会按遗忘曲线复习</span></div>
        <div class="nw-list">${items.map((x, k) => `<label class="nw"><input type="checkbox" data-nw="${k}" ${x.on ? 'checked' : ''}><b>${esc(x.word)}</b><span class="muted tiny" data-zh>${esc(x.meaning || '')}</span></label>`).join('')}</div>
        <div><button class="btn small primary" id="nwAdd">加入复习</button></div></div>`;
    }
    function bindNewWords() {
      const box = pane.querySelector('#newWords'); if (!box) return;
      const items = newWordItems();
      box.querySelector('#nwAdd').onclick = async e => {
        if (!S.user) return needLogin('登录后可以把这些词加入复习。');
        const pick = [...box.querySelectorAll('[data-nw]:checked')].map(c => items[Number(c.dataset.nw)]).filter(Boolean);
        if (!pick.length) { toast('先勾选要复习的词'); return; }
        const btn = e.currentTarget; btn.disabled = true;
        try {
          const r = await api('/api/next/vocab/add', { pack: id, items: pick.map(x => ({ word: x.word, sentence: x.sentence || '' })) });
          toast(r.added ? `已加入 ${r.added} 个词` : '这些词已经在复习里了'); refreshHome().catch(() => {});
          m.mine = (m.mine || []).concat(pick.map(x => ({ form: x.word.toLowerCase(), id: 0 }))); m._looked = new Map();
          if (m._onLook) m._onLook();
        } catch (x) { toast(x.message); btn.disabled = false; }
      };
    }
    // What this text leaves you with, in one folded card under the text: expressions, words (the ones looked up
    // too, to put into review) and grammar points, one tab at a time. Open or closed and the tab are remembered.
    function gainsTabs() {
      const vocab = m.vocabulary.length + (m.variant ? m.variant.notes.length : 0), fresh = newWordItems().filter(x => x.on).length;
      return [
        m.expressions.length && ['expr', '表达', m.expressions.length, () => `<p class="muted tiny">能直接搬进你自己话里的搭配。</p><div class="stack-s">${m.expressions.map((x, i) => `<div class="expr"><span class="e">${esc(x.text)}</span><span class="row"><button class="icon-btn" data-sayx="${i}" aria-label="朗读">${ICON.speak}</button><button class="icon-btn" data-sx="${i}" aria-label="收藏 ${esc(x.text)}">${ICON.star}</button></span><span class="m" data-zh>${esc(x.meaning)}</span><span class="n" data-zh>${esc(x.note || '')}</span></div>`).join('')}</div>`],
        ['words', '词汇', vocab + fresh, () => `${m.vocabulary.length ? `<div class="vocab-list">${m.vocabulary.map((v, i) => `<div class="vrow"><span class="term">${esc(v.term)}</span><button class="icon-btn" data-sv="${i}" aria-label="收藏 ${esc(v.term)}">${ICON.star}</button><span class="muted small" data-zh>${esc(v.meaning)}</span><span class="vex">${esc(v.example || '')}</span></div>`).join('')}</div>` : ''}
          ${(m.variant && m.variant.notes.length) ? `<b class="small">改写版新出现的表达</b><div class="vocab-list">${m.variant.notes.map((v, i) => `<div class="vrow"><span class="term">${esc(v.text)}</span><button class="icon-btn" data-sn="${i}" aria-label="收藏">${ICON.star}</button><span class="muted small" data-zh>${esc(v.meaning)}</span></div>`).join('')}</div>` : ''}
          <div id="nwSlot">${newWordsHTML()}</div>`],
        m.notes.length && ['notes', '知识点', m.notes.length, () => `<div class="stack-s">${m.notes.map(n => `<div class="knote"><div class="row between">${nodeChip({ id: n.node, title: n.title, status: n.status })}<span class="tiny muted">${esc(n.label)}</span></div><q>${esc(n.quote)}</q><div class="small muted" data-zh>${esc(n.explanation)}</div></div>`).join('')}
          <a class="link small" href="#/graph">在知识图谱里看 →</a></div>`]].filter(Boolean);
    }
    function gainsSummary() {
      const vocab = m.vocabulary.length + (m.variant ? m.variant.notes.length : 0), fresh = newWordItems().filter(x => x.on).length;
      return [m.expressions.length && `${m.expressions.length} 个表达`, vocab && `${vocab} 个词`, m.notes.length && `${m.notes.length} 个知识点`, fresh && `查过 ${fresh} 个词，可以加入复习`].filter(Boolean).join(' · ') || '查过的词会收在这里';
    }
    function gainsHTML() {
      const tabs = gainsTabs();
      let open = false, cur = tabs[0][0];
      try { open = localStorage.getItem('flow-gains-open') === '1'; const t = localStorage.getItem('flow-gains-tab'); if (tabs.some(x => x[0] === t)) cur = t; } catch (e) { /* private mode */ }
      return `<details class="card flat fold gains section" id="gains"${open ? ' open' : ''}><summary data-tap="read-gains"><b>这篇的收获</b><span class="tiny muted" id="gainsSum">${gainsSummary()}</span></summary>
        <div class="seg gtabs" role="tablist" aria-label="这篇的收获">${tabs.map(([k, l, n]) => `<button role="tab" type="button" data-gt="${k}" aria-selected="${k === cur}">${l} ${n}</button>`).join('')}</div>
        ${tabs.map(([k, , , html]) => `<div class="gpane stack-s" data-gp="${k}" role="tabpanel"${k === cur ? '' : ' hidden'}>${html()}</div>`).join('')}</details>`;
    }
    function bindGains() {
      const g = pane.querySelector('#gains'); if (!g) return;
      g.addEventListener('toggle', () => { try { localStorage.setItem('flow-gains-open', g.open ? '1' : ''); } catch (e) { /* private mode */ } });
      g.querySelectorAll('[data-gt]').forEach(b => b.onclick = () => {
        g.querySelectorAll('[data-gt]').forEach(x => x.setAttribute('aria-selected', String(x === b)));
        g.querySelectorAll('[data-gp]').forEach(p => { p.hidden = p.dataset.gp !== b.dataset.gt; });
        try { localStorage.setItem('flow-gains-tab', b.dataset.gt); } catch (e) { /* private mode */ }
      });
    }

    /* read: tap a word, ✦ explains a sentence, select to save, read-along, expressions, knowledge points */
    function wordClass(part) {
      const key = part.toLowerCase();
      const isVocab = m.vocabulary.some(v => v.term.toLowerCase() === key);
      const mine = (m.mine || []).some(x => x.form === key) ? ' mine' : '';
      return (isVocab ? 'w vocab' : (m.hard[key] ? 'w hard' : 'w')) + mine;
    }
    // The ✦ is glued to the sentence's last word, so it can never wrap to the start of the next line.
    // A line that begins with a speaker ("Staff: …") starts a new turn on its own line.
    function sentenceHTML(s, i) {
      let html = wordSpans(s, wordClass, ` data-s="${i}"`);
      const at = html.lastIndexOf('<span class="');
      const btn = `<button class="link tiny" data-ex="${i}" aria-label="AI 讲解第 ${i + 1} 句">✦</button>`;
      html = at < 0 ? html + btn : html.slice(0, at) + '<span class="nobr">' + html.slice(at) + btn + '</span>';
      const turn = i > 0 && /^[A-Z][a-z]+(?: [A-Z][a-z]+)?:\s/.test(s) ? ' turn' : '';
      return `<span class="sent${turn}" data-si="${i}">${html}</span> `;
    }
    function read() {
      const ls = lines();
      // One row of tools (中文导读, 改写成我的难度, 伴读), all one kind of button, and one line of colour key and hints, so
      // the text starts on the first screen of a phone; the summary opens under the row. 「AI 朗读」 has its own line
      // right under the row, beside 伴读 and always there with it (B7 and B8, 2026-11-25: one mark per group of voices).
      const variantBar = m.variant ? `<div class="seg" role="tablist"><button data-ver="v" aria-selected="${!st.showOriginal}">适合我的版本（${m.variant.level} · AI 改写）</button><button data-ver="o" aria-selected="${st.showOriginal}">原文（${m.original_level}）</button><span></span></div>${st.showOriginal ? '' : aiMark('这一版由 AI 按你的难度改写，原文没有改动')}` : '';
      pane.innerHTML = `<div class="read-tools">${m.summary_zh ? '<button class="btn small" id="zhGuide" type="button" aria-expanded="false" aria-controls="zhText">中文导读</button>' : ''}
          ${m.can_variant ? `<button class="btn small" id="mkVar" type="button" title="这篇原文是 ${m.original_level}，你选的是 ${m.user_level}">改写成 ${m.user_level} 难度</button>` : ''}
          <button class="btn small" id="readAlong" title="边听边看文字，读到哪句亮哪句">${playIcon(false, 14)}<span>伴读</span></button>
          <button class="link tiny" id="alongRestart" type="button" hidden>从头开始</button></div>
        <div class="read-line">${aiVoiceNote('朗读由 AI 合成', 'p', 'read-ai')}<div class="legend"><span>本篇词汇</span><span class="h">可能超出你的水平</span>${(m.mine || []).length ? '<span class="m">你在背的词</span>' : ''}</div></div>
        <p class="tiny muted sv-prep" id="svPrep" role="status" hidden></p>
        ${m.summary_zh ? `<p class="guide-zh small" id="zhText" data-zh hidden>${esc(m.summary_zh)}</p>` : ''}${variantBar}
        ${tipSlot('read', `点词查词，点句尾 ✦ 讲解整句，${TOUCH ? '长按拖选' : '选中'}可收藏${TOUCH ? '' : '；键盘：Tab 进入正文后 ← → 逐词，↵ 查词，E 讲解'}`)}
        <div class="text" id="reader" tabindex="0" aria-label="正文：左右方向键逐词移动，回车查词">${ls.map((s, i) => sentenceHTML(s, i)).join('')}</div>
        <div class="section row between"><span></span><button class="btn primary" id="toCheck">读完了，做理解题 →</button></div>
        ${gainsHTML()}`;
      const reader = pane.querySelector('#reader');
      // The narration's timings are fetched now, so a tap on 伴读 can start the sound inside the tap (in-app browsers
      // such as WeChat's refuse sound that starts after a download).
      let nmNow = null; narration(ls).then(x => { nmNow = x; }).catch(() => {});
      pane.querySelectorAll('[data-ver]').forEach(b => b.onclick = () => { st.showOriginal = b.dataset.ver === 'o'; m._showOriginal = st.showOriginal; read(); });
      const zg = pane.querySelector('#zhGuide');
      if (zg) zg.onclick = () => { const t = pane.querySelector('#zhText'), open = t.hidden; t.hidden = !open; zg.setAttribute('aria-expanded', String(open)); };
      const mk = pane.querySelector('#mkVar');
      if (mk) mk.onclick = async () => {
        if (!S.user) return needLogin('登录后可以让 AI 把这篇改写成适合你的难度（每天的 AI 次数有上限）。');
        mk.disabled = true; mk.innerHTML = '<span class="spin"></span> 正在改写…';
        try { const r = await api('/api/next/variant', { pack: id, level: m.user_level, request_id: rid('nv') }); m.variant = { level: r.level, body: r.body, notes: r.notes }; m.original = m.sentences; m.sentences = splitSentences(r.body); m.can_variant = false; read(); toast(r.cached ? '已打开改写版' : '改写好了'); }
        catch (e) { toast(e.message); mk.disabled = false; mk.textContent = `改写成 ${m.user_level} 难度`; }
      };
      reader.onclick = e => {
        const ex = e.target.closest('[data-ex]'); if (ex) return explainSheet(ls[Number(ex.dataset.ex)], id);
        const w = e.target.closest('.w'); if (w && !String(getSelection()).trim()) lookupSheet(w.dataset.w, ls[Number(w.dataset.s)], id, w.classList.contains('mine'));
      };
      // Read-along (LONG, 01-audio-offline.js): sentence by sentence; the current sentence stays bright, the rest dims, the
      // current word lights up when a recording (or the browser voice) says which. A text without a recording (an imported
      // article, a 热点 before its recording) is read by the server voice (owner, 2026-11-25): each sentence made once and
      // kept (an import's for its owner only), the next two asked for while one plays, a line while one is being made; the
      // browser voice only for a sentence the server cannot give, with the reason. 暂停 / 继续, and where it was left is
      // kept on this phone (「从第 N 句继续」) until the end is reached.
      const ra = pane.querySelector('#readAlong'), restart = pane.querySelector('#alongRestart'), prep = pane.querySelector('#svPrep');
      const RKEY = 'read:' + id, sentEl = i => reader.querySelector(`.sent[data-si="${i}"]`);
      let alongShown = -1;
      const setRa = () => {
        const r = LONG.of(RKEY), at = r ? r.i : PROG.at(RKEY, ls.length);
        ra.innerHTML = r && r.state !== 'paused' ? `${pauseIcon(14)}<span>暂停</span>` : `${playIcon(false, 14)}<span>${r ? '继续' : at ? `从第 ${at + 1} 句继续` : '伴读'}</span>`;
        restart.hidden = !at; reader.classList.toggle('reading', !!r);
      };
      const stopAlong = () => LONG.stop();
      const readAlong = from => LONG.start({
        key: RKEY, texts: ls, nm: nmNow, pack: id, title: m.title, label: i => `第 ${i + 1} / ${ls.length} 句`,  // the 「AI 朗读」 mark and the lit sentence say what plays
        onState: (state, i, note) => {
          setRa(); prep.textContent = note || ''; prep.hidden = !note;
          if (state === 'idle') { alongShown = -1; reader.querySelectorAll('.now,.cur').forEach(x => x.classList.remove('now', 'cur')); return; }
          const s = sentEl(i);
          if (i !== alongShown && s) { alongShown = i; reader.querySelectorAll('.sent.now').forEach(x => x.classList.remove('now')); s.classList.add('now'); if (state !== 'paused') s.scrollIntoView({ block: 'center', behavior: REDUCED ? 'auto' : 'smooth' }); }
        },
        onWord: (i, c) => { const s = sentEl(i); if (!s) return; if (c == null) s.querySelectorAll('.cur').forEach(x => x.classList.remove('cur')); else lightWord(s, c); },
        onDone: () => markStep('read'),
      }, from);
      ra.onclick = async () => {
        if (LONG.of(RKEY)) { LONG.toggle(); return; }
        if (!nmNow) { ra.disabled = true; nmNow = await narration(ls); ra.disabled = false; }  // fetched when the page opened, as a rule
        readAlong(PROG.at(RKEY, ls.length));
      };
      restart.onclick = async () => { LONG.stop(); PROG.clear(RKEY); if (!nmNow) nmNow = await narration(ls); readAlong(0); };
      setRa();
      NATIVE.follow(RKEY, setRa);  // in the app: the button says where the app got to (it may have played on, or still plays)
      // An expression is read by the server voice (the browser voice where it is off); with neither (WeChat on Android,
      // the server voice off), its sentence from the narration.
      pane.querySelectorAll('[data-sayx]').forEach(b => b.onclick = () => {
        const x = m.expressions[Number(b.dataset.sayx)], k = ls.findIndex(s => s.toLowerCase().includes(x.text.toLowerCase()));
        if (!TTS.can() && nmNow && k >= 0) NAR.play(nmNow.sentences[k].s, nmNow.sentences[k].e, null, null); else TTS.say(x.text, null, null, { pack: id });
      });
      pane.querySelectorAll('[data-sx]').forEach(b => b.onclick = () => { const x = m.expressions[Number(b.dataset.sx)]; saveCard({ text: x.text, meaning: x.meaning + (x.note ? '｜' + x.note : ''), context: findContext(x.text, ls), pack: id }, b); });
      pane.querySelectorAll('[data-sv]').forEach(b => b.onclick = () => { const v = m.vocabulary[Number(b.dataset.sv)]; saveCard({ text: v.term, meaning: v.meaning, context: findContext(v.term, ls) || v.example, pack: id }, b); });
      pane.querySelectorAll('[data-sn]').forEach(b => b.onclick = () => { const v = m.variant.notes[Number(b.dataset.sn)]; saveCard({ text: v.text, meaning: v.meaning, context: findContext(v.text, ls), pack: id }, b); });
      pane.querySelector('#toCheck').onclick = () => { stopAlong(); markStep('read'); go('check'); };
      // Reading to the end of the text counts as having read it (after a short while on the page, not a quick scroll).
      const t0r = Date.now();
      if ('IntersectionObserver' in window) {
        const io = new IntersectionObserver(es => { if (es.some(x => x.isIntersecting) && Date.now() - t0r > 20000) { markStep('read'); io.disconnect(); } });
        io.observe(pane.querySelector('#toCheck'));
      }
      // Keyboard reading: ← → walk the words, ↵ looks one up, E explains its sentence.
      const words = () => [...reader.querySelectorAll('.w')];
      let kw = -1;
      const kmove = k => { const ws = words(); if (!ws.length) return; reader.querySelectorAll('.kfocus').forEach(x => x.classList.remove('kfocus')); kw = Math.max(0, Math.min(ws.length - 1, k)); ws[kw].classList.add('kfocus'); ws[kw].scrollIntoView({ block: 'nearest' }); };
      reader.addEventListener('keydown', e => {
        if (e.metaKey || e.ctrlKey || e.altKey) return;
        const ws = words();
        if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); kmove(kw < 0 ? 0 : kw + (e.key === 'ArrowRight' ? 1 : -1)); }
        else if (e.key === 'Enter' && kw >= 0) { e.preventDefault(); const w = ws[kw]; lookupSheet(w.dataset.w, ls[Number(w.dataset.s)], id, w.classList.contains('mine')); }
        else if ((e.key === 'e' || e.key === 'E') && kw >= 0) { e.preventDefault(); explainSheet(ls[Number(ws[kw].dataset.s)], id); }
      });
      reader.addEventListener('blur', () => reader.querySelectorAll('.kfocus').forEach(x => x.classList.remove('kfocus')));
      bindGains(); bindNewWords();
      m._onLook = () => {
        const slot = pane.querySelector('#nwSlot'); if (!slot) return;
        slot.innerHTML = newWordsHTML(); bindNewWords();
        const sum = pane.querySelector('#gainsSum'); if (sum) sum.textContent = gainsSummary();
        const n = (gainsTabs().find(x => x[0] === 'words') || [])[2], t = pane.querySelector('[data-gt="words"]'); if (t) t.textContent = '词汇 ' + n;
      };
      const onSel = () => {
        const sel = getSelection(); const t = String(sel).replace(/\s+/g, ' ').trim();
        if (!t || t.length > 160 || !/[A-Za-z]/.test(t) || !reader.contains(sel.anchorNode)) { hideSelbar(); return; }
        const sentEl = sel.anchorNode.parentElement && sel.anchorNode.parentElement.closest('.sent');
        const ctx = sentEl ? ls[Number(sentEl.dataset.si)] : '';
        if (!selbar) { selbar = document.createElement('div'); selbar.className = 'selbar'; document.body.appendChild(selbar); }
        selbar.innerHTML = `<span>${esc(t)}</span><button type="button">收藏</button>`;
        selbar.querySelector('button').onclick = () => { const from = selbar; saveCard({ text: t, context: ctx, pack: id }, null, from); sel.removeAllRanges(); setTimeout(hideSelbar, 50); };
      };
      document.onselectionchange = () => { clearTimeout(onSel.t); onSel.t = setTimeout(onSel, 250); };
    }

    /* check: one question a screen; answer, then the evidence sentence is swept in under the two options that stay */
    function check() {
      if (!m.questions.length) {
        pane.innerHTML = `<div class="empty"><p>这篇还没有理解题。</p>${m.imported ? '<button class="btn primary" id="mkQ">✦ 让 AI 出几道理解题</button><p class="muted tiny">同时挑出值得学的表达，写一段中文导读（用 1 次 AI）。</p>' : ''}</div><div class="row between"><span></span><button class="btn" id="toOut">去用出来 →</button></div>`;
        pane.querySelector('#toOut').onclick = () => { markStep('check'); go('output'); };
        const mk = pane.querySelector('#mkQ');
        if (mk) mk.onclick = async () => {
          if (!S.user) return needLogin('登录后可以让 AI 出题。');
          mk.disabled = true; mk.innerHTML = '<span class="spin"></span> 正在出题…';
          try { await api('/api/next/import/enrich', { id, request_id: rid('ie') }); delete MAT[id]; toast('题目出好了'); route(true); }
          catch (e) { toast(e.message); mk.disabled = false; mk.textContent = '✦ 让 AI 出几道理解题'; }
        };
        return;
      }
      // One question a screen (B9, 2026-11-26; the user on the mock-ups: 完全做，按照现在的效果图). A tap answers: the other
      // options fold away, the learner's pick and the right one stay, and the block under them says which was right,
      // shows the sentence in the text, and holds the one button (下一题, 看结果 after the last). The result page lists
      // the questions (a tap opens one again, as it was answered) and leads on to 用出来.
      const n = m.questions.length, got = {};   // got[i] = { pick, answer, correct, evidence }
      const all = () => Object.keys(got).length === n;
      const note = m.imported ? aiMark('这些题目由 AI 根据这篇文章出，仅供练习') : '';
      const result = k => { const g = got[k];
        return `<p class="chk-h"><b>${g.correct ? '答对了' : '正确答案是 ' + 'ABCD'[g.answer]}</b>${g.evidence ? '<span class="tiny muted">答案在原文这里</span>' : ''}</p>${g.evidence ? `<div class="evidence">${esc(g.evidence)}</div>` : ''}
          <button class="btn primary block chk-go" id="chkGo" type="button">${all() ? '看结果' : '下一题'}</button>`; };
      // The question goes to the top of the screen (the material's title scrolls away), so that on a short phone the two
      // options that stay and the block under them are all on screen; the first question is left where the step opened.
      // Under the step bar when that stays at the top of the screen (its own height and where it sticks), else at the top.
      const toQ = () => { const q = pane.querySelector('.q'), st = document.querySelector('.steps'); if (!q) return;
        const cs = st ? getComputedStyle(st) : null, under = cs && cs.position === 'sticky' ? st.getBoundingClientRect().height + (parseFloat(cs.top) || 0) : 0;
        window.scrollTo({ top: Math.max(0, window.scrollY + q.getBoundingClientRect().top - under - 8), behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' }); };
      const onward = () => { const b = pane.querySelector('#chkGo'); if (!b) return;
        b.onclick = () => { const next = m.questions.findIndex((q, i) => !got[i]); if (next < 0) { end(); window.scrollTo(0, 0); } else { show(next); toQ(); } }; };
      const show = k => {
        const q = m.questions[k], g = got[k];
        pane.innerHTML = `<div class="stack-s chk1">${note}<div class="q" data-q="${k}"><div class="chk-top"><span class="tiny muted">第 ${k + 1} / ${n} 题${q.type ? ` · ${esc(q.type)}` : ''}</span>
          <span class="chk-dots" aria-hidden="true">${m.questions.map((x, i) => `<i${i <= k || got[i] ? ' class="on"' : ''}></i>`).join('')}</span></div>
          <div class="prompt">${esc(q.prompt)}</div>
          ${q.options.map((o, j) => `<div class="chk-o${g && j !== g.answer && j !== g.pick ? ' gone' : ''}"><button class="ans${g ? (j === g.answer ? ' right' : j === g.pick ? ' wrong' : '') : ''}" data-q="${k}" data-o="${j}"${g ? ' disabled' : ''}><span class="k">${'ABCD'[j]}</span><span class="t">${esc(o)}</span>${g && j === g.pick && !g.correct ? '<span class="me">你选的</span>' : ''}</button></div>`).join('')}
          <div class="fb card flat chk-res" aria-live="polite">${g ? result(k) : ''}</div></div></div>`;
        onward();
        const box = pane.querySelector('.q');
        box.querySelectorAll('.ans').forEach(b => b.onclick = async () => {
          if (got[k] || box.dataset.busy) return;
          const j = Number(b.dataset.o);
          box.dataset.busy = '1'; box.querySelectorAll('.ans').forEach(x => x.disabled = true);
          try {
            let r;
            try { r = await api('/api/next/check', { pack: id, index: k, choice: j }); }
            catch (e) {
              // Without a connection, a material kept on the phone is graded there with its own answers; the answer is
              // sent when the phone is back online (mistake book, progress).
              const a = e.network && m.answers && m.answers[k]; if (!a) throw e;
              r = { correct: j === a.answer, answer: a.answer, evidence: a.evidence };
              if (S.user) OUTBOX.push({ path: '/api/next/check', body: { pack: id, index: k, choice: j } });
            }
            got[k] = { pick: j, answer: r.answer, correct: r.correct, evidence: r.evidence };
            if (all()) markStep('check');
            if (!box.isConnected) return;   // the learner went to another step while it was being checked
            box.querySelectorAll('.ans').forEach(x => { const o = Number(x.dataset.o);
              if (o === r.answer) x.classList.add('right');
              else if (o === j) { x.classList.add('wrong'); x.insertAdjacentHTML('beforeend', '<span class="me">你选的</span>'); }
              else x.parentNode.classList.add('gone'); });
            box.querySelector('.fb').innerHTML = result(k);
            onward(); toQ();
            const go2 = box.querySelector('#chkGo'); if (go2 && !matchMedia('(pointer:coarse)').matches) go2.focus({ preventScroll: true });
          } catch (e) { toast(e.message); delete box.dataset.busy; box.querySelectorAll('.ans').forEach(x => x.disabled = false); }
        });
      };
      const end = () => {
        const right = Object.values(got).filter(g => g.correct).length;
        pane.innerHTML = `<div class="stack chk1 chk-end"><div class="card flat chk-sum"><p class="tiny muted">理解</p><h2 class="chk-score"><b>${right} / ${n}</b> 题答对</h2>
          <div class="chk-list">${m.questions.map((q, i) => `<button class="chk-it" type="button" data-k="${i}"><span class="k${got[i].correct ? ' ok' : ''}" aria-hidden="true">${got[i].correct ? '✓' : '✕'}</span><span class="t">${esc(q.prompt)}</span><span class="sr-only">${got[i].correct ? '答对了' : '答错了'}，点一下再看这一题</span><span class="go" aria-hidden="true">›</span></button>`).join('')}</div></div>
          <div id="score"><button class="btn primary block chk-go" id="toOut" type="button">去用出来</button>
            ${(m.expressions || []).length ? '<div class="row"><button class="link small" id="shareX" type="button" data-tap="share-material">把学会的一句做成卡片，分享或保存</button></div>' : ''}</div></div>`;
        pane.querySelectorAll('.chk-it').forEach(b => b.onclick = () => { show(Number(b.dataset.k)); toQ(); });
        const sx = pane.querySelector('#shareX'); if (sx) sx.onclick = () => shareFromMaterial(m);
        pane.querySelector('#toOut').onclick = () => go('output');
        // After a first article tried without any questions: offer the level questions (and an account) next.
        if (!S.user && !hasProfile()) pane.querySelector('#score').insertAdjacentHTML('beforeend', `<div class="card stack-s enter try-next"><b>觉得有用？按你的目标每天推荐一篇</b>
          <span class="small muted">选学习目标和想达到的水平，大约 20 秒；注册以后，进度和收藏会保存下来。</span>
          <div class="row"><a class="btn primary" href="#/welcome" data-tap="trial-level">选学习目标</a><button class="btn" id="trialReg" type="button">注册 / 登录</button></div></div>`);
        const tr = pane.querySelector('#trialReg'); if (tr) tr.onclick = () => openLogin();
      };
      show(0);
    }

    /* output: write, get the AI rewrite comparison, tied back to the knowledge graph */
    /* output modes: 仿写 (above) · 复述 · 情景对话 · 翻译 · 写作 — all built on this material */
    const OUT_MODES = { model: '仿写', retell: '复述', dialog: '对话', translate: '翻译', essay: '写作' };
    function outTabs(cur) {
      return `<div class="seg outmodes" role="tablist" aria-label="输出练习">${Object.entries(OUT_MODES).map(([k, l]) => `<a role="tab" href="#/m/${encodeURIComponent(id)}/output${k === 'model' ? '' : '/' + k}" aria-selected="${cur === k}">${l}</a>`).join('')}</div>`;
    }
    const needAI = reason => { if (!S.user) { needLogin(reason); return true; } return false; };
    // AI answers take seconds. The learner may switch mode, direction or sentence meanwhile, and the pane is redrawn
    // (same text, same #pane). So each wait keeps the element it will write into. If that element has left the page
    // when the answer arrives, the answer is dropped: no error, no sound, nothing written into the newer page.

    function retellMode() {
      pane.innerHTML = `${outTabs('retell')}<div class="card flat task stack-s"><b>不看原文，用自己的话把这篇讲一遍</b>
          <span class="muted small">可以打字，也可以点录音键直接说（最长 2 分钟）。AI 会提炼原文要点，看你讲到了哪些，并改出最影响理解的错误。</span></div>
        <textarea id="rtText" data-draft="retell-${esc(id)}" aria-label="用英文复述这篇" rows="6" maxlength="2500" lang="en" data-submit="#rtGo" placeholder="In this article, ..."></textarea>
        <div class="row between"><span class="row">${recBtn('rtMic', '说出来')}<span class="muted tiny" id="rtState">打字或录音都行</span></span><button class="btn primary" id="rtGo">AI 看看我的复述</button></div>
        <div id="rtOut"></div>`;
      let blob = null;
      const mic = pane.querySelector('#rtMic'), state = pane.querySelector('#rtState');
      mic.onclick = () => MIC.toggle(mic, 120, b => { blob = b; state.textContent = '已录好一段，可以提交了（会先转写）'; });
      pane.querySelector('#rtGo').onclick = async e => {
        if (needAI('登录后 AI 会看你的复述讲到了哪些要点。')) return;
        const text = pane.querySelector('#rtText').value.trim();
        if (!blob && (text.match(/[A-Za-z]+/g) || []).length < 8) { toast('先说一段或写几句英文'); return; }
        const btn = e.currentTarget, out = pane.querySelector('#rtOut'); btn.disabled = true; btn.innerHTML = '<span class="spin"></span> 正在看…';
        try {
          const body = { pack: id, request_id: rid('rt') };
          if (blob) body.audio = await MIC.payload(blob); else body.text = text;
          const x = (await api('/api/next/retell', body)).result;
          if (!out.isConnected) return;
          out.innerHTML = `<div class="result enter stack" data-ex-block>${aiMark('点评和示范复述由 AI 生成，仅供参考')}
            ${blob ? `<div class="card sunk small"><span class="muted">AI 听到：</span>${esc(x.transcript)}</div>` : ''}
            <div class="card verdict"><span class="dot"></span><div><span data-ex>${esc(x.comment)}</span><div class="tiny muted">讲到 ${x.points.filter(p => p.covered).length} / ${x.points.length} 个要点</div></div></div>
            <div class="card flat stack-s"><b>原文要点</b>${x.points.map(p => `<div class="small"><span class="${p.covered ? 'ok-mark' : 'bad-mark'}">${p.covered ? '✓' : '✗'}</span> <span data-ex>${esc(p.point)}</span></div>`).join('')}</div>
            ${x.used.length ? `<div class="small">用上了原文的表达：${x.used.map(u => `<span class="pill green">${esc(u)}</span>`).join(' ')}</div>` : ''}
            ${fixesHTML(x.fixes)}
            ${x.model ? `<div class="card flat stack-s"><div class="row between"><b>示范复述</b><span class="say-pair">${aiVoiceNote('AI 合成', 'span')}<button class="icon-btn" id="rtSay" type="button" aria-label="朗读示范复述（AI 朗读）">${ICON.speak}</button></span></div><div class="text small">${esc(x.model)}</div></div>` : ''}</div>`;
          const say = pane.querySelector('#rtSay'); if (say) say.onclick = () => TTS.say(x.model);
          bringIntoView(pane.querySelector('#rtOut'));
          markStep('output'); showFinish(pane, m, id); blob = null; state.textContent = '打字或录音都行'; if (body.text) draftDone('retell-' + id);  // a recording sent: the typed draft stays
        } catch (x) { toast(x.message); }
        btn.disabled = false; btn.textContent = 'AI 看看我的复述';
      };
    }

    function dialogMode() {
      const hist = [];
      pane.innerHTML = `${outTabs('dialog')}<div class="card flat task stack-s"><b${m.speaking_task ? ' data-zh' : ''}>${esc(m.speaking_task || '围绕这篇的话题和 AI 聊几句')}</b>
          <div class="ai-line">${aiTag()}<span>对话里的另一方由 AI 扮演</span>${aiVoiceNote('AI 朗读', 'span')}</div><span class="muted small">AI 扮演情景里的另一方。可以打字或说，每说一句它会顺手纠正；聊 4–6 轮后点「结束并总结」。</span></div>
        <div class="chat" id="chat" data-ex-block></div>
        <div id="dlgIn" class="stack-s" hidden><div class="tiny muted" id="dlgHint"></div>
          <div class="chat-in"><textarea id="dlgText" rows="2" maxlength="480" lang="en" enterkeyhint="send" placeholder="用英文回答…"></textarea>${recBtn('dlgMic', '说出来')}<button class="btn primary" id="dlgSend">发送</button></div>
          <div><button class="btn small ghost" id="dlgEnd">结束并总结</button></div></div>
        <div><button class="btn primary" id="dlgStart">开始对话</button></div><div id="dlgOut"></div>`;
      const chat = pane.querySelector('#chat');
      const bubble = (role, text, extra) => { chat.insertAdjacentHTML('beforeend', `<div class="msg ${role}"><div class="b">${esc(text)}</div>${extra || ''}</div>`); chat.lastElementChild.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' }); };
      // 8 lines a round (output_service.DIALOG_LINES): then only 结束并总结, which the server takes whatever the length
      const FULL = 8, full = () => hist.filter(h => h.role === 'me').length >= FULL;
      const busy = on => { ['#dlgSend', '#dlgEnd', '#dlgMic', '#dlgText'].forEach(s => { const b = pane.querySelector(s); if (b) b.disabled = (on && s !== '#dlgText') || (s !== '#dlgEnd' && full()); }); };  // the box only when the round is full
      // After each reply: the newest message and the answer box are on screen together, above the keyboard and the tabs.
      const showInput = () => { const box = pane.querySelector('#dlgIn'); if (box && !box.hidden) box.scrollIntoView({ block: 'end', behavior: REDUCED ? 'auto' : 'smooth' }); };
      async function turn(body) {
        busy(true);
        try { const x = (await api('/api/next/dialog', { pack: id, history: hist, request_id: rid('dg'), ...body })).result; return chat.isConnected ? x : null; }
        catch (e) { toast(e.message); return null; } finally { busy(false); }
      }
      pane.querySelector('#dlgStart').onclick = async e => {
        if (needAI('登录后可以和 AI 做情景对话。')) return;
        const btn = e.currentTarget; btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
        const x = await turn({}); if (!x) { btn.disabled = false; btn.textContent = '开始对话'; return; }
        btn.parentNode.remove();
        chat.insertAdjacentHTML('beforeend', `<div class="scene small"><span data-ex>${esc(x.scene)}</span>${x.role ? `（AI 扮演：${esc(x.role)}）` : ''}</div>`);
        bubble('ai', x.reply); TTS.say(x.reply); hist.push({ role: 'ai', text: x.reply });
        pane.querySelector('#dlgIn').hidden = false; showInput(); if (!TOUCH) pane.querySelector('#dlgText').focus({ preventScroll: true });
      };
      async function send(text, blob) {
        if (full()) return;
        const body = blob ? { audio: await MIC.payload(blob) } : { text };
        const x = await turn(body); if (!x) return;
        const me = x.heard || text;
        bubble('me', me, x.correction ? `<div class="fix tiny"><del>${esc(x.correction.original)}</del> → <b>${esc(x.correction.better)}</b> <span class="muted" data-ex>${esc(x.correction.why)}</span></div>` : '');
        hist.push({ role: 'me', text: me });
        bubble('ai', x.reply); TTS.say(x.reply); hist.push({ role: 'ai', text: x.reply });
        pane.querySelector('#dlgHint').textContent = x.hint ? '提示：' + x.hint : '';
        busy(false); showInput();
        if (full()) pane.querySelector('#dlgHint').textContent = `这一轮说满 ${FULL} 句了，点「结束并总结」`;
        else if (hist.length >= 14) toast('聊得差不多了，可以结束并看总结');
      }
      pane.querySelector('#dlgSend').onclick = () => { const t = pane.querySelector('#dlgText'); const v = t.value.trim(); if (!v) return; t.value = ''; send(v); };
      pane.querySelector('#dlgText').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); pane.querySelector('#dlgSend').click(); } });
      const mic = pane.querySelector('#dlgMic'); mic.onclick = () => MIC.toggle(mic, 30, b => send('', b));
      pane.querySelector('#dlgEnd').onclick = async e => {
        if (hist.filter(h => h.role === 'me').length < 1) { toast('先说一两句再总结'); return; }
        const btn = e.currentTarget; btn.innerHTML = '<span class="spin"></span>';
        const x = await turn({ end: true }); if (!x) { btn.textContent = '结束并总结'; return; }
        pane.querySelector('#dlgIn').hidden = true; TTS.stop(); markStep('output');
        pane.querySelector('#dlgOut').innerHTML = `<div class="result enter stack" data-ex-block>${aiMark('总结和建议由 AI 生成，仅供参考')}<div class="card verdict"><span class="dot"></span><div data-ex>${esc(x.summary)}</div></div>
          ${x.good.length ? `<div class="card flat stack-s"><b>说得好的句子</b>${x.good.map(g => `<div class="small text">${esc(g)}</div>`).join('')}</div>` : ''}
          ${fixesHTML(x.fixes)}
          ${x.expressions.length ? `<div class="card flat stack-s"><b>可以学的表达</b>${x.expressions.map((ex, k) => `<div class="row between small"><span><b>${esc(ex.text)}</b> <span class="muted" data-zh>${esc(ex.meaning)}</span></span><button class="btn small" data-kx="${k}">收藏</button></div>`).join('')}</div>` : ''}
          <div class="row"><button class="btn primary" id="dlgAgain">再练一轮</button><a class="btn" href="#/m/${encodeURIComponent(id)}/output/translate">换个练法：翻译</a></div></div>`;
        pane.querySelectorAll('[data-kx]').forEach(b => b.onclick = () => { const ex = x.expressions[Number(b.dataset.kx)]; saveCard({ text: ex.text, meaning: ex.meaning, context: '', pack: id }, b); });
        pane.querySelector('#dlgAgain').onclick = () => { scrollTo({ top: 0 }); dialogMode(); };
        showFinish(pane, m, id); bringIntoView(pane.querySelector('#dlgOut'));
      };
    }

    function translateMode() {
      const ls = lines().map(s => s.replace(/^(?:[A-Z][a-z]+(?: [A-Z][a-z]+)?|[A-Z]):\s+/, ''));
      const good = ls.map((s, i) => [s, i]).filter(([s]) => (s.match(/[A-Za-z]+/g) || []).length >= 8);
      let k = Math.max(0, good.findIndex(([, i]) => i === m.dictation_index)), dir = load('flow-next-trans-dir') || 'zh2en';
      async function render() {
        const [en, i] = good[k] || [ls[0], 0];
        pane.innerHTML = `${outTabs('translate')}<div class="seg two" role="tablist"><button data-dir="zh2en" aria-selected="${dir === 'zh2en'}">汉译英</button><button data-dir="en2zh" aria-selected="${dir === 'en2zh'}">英译汉</button></div>
          <div class="card flat stack-s"><div class="row between"><span class="kicker">第 ${k + 1} / ${good.length} 句</span><button class="link small" id="trNext">换一句</button></div>
            <div class="text" id="trSrc" data-zh>${dir === 'en2zh' ? esc(en) : '<span class="spin"></span>'}</div></div>
          <textarea id="trIn" data-draft="trans-${esc(id)}-${dir}-${i}" aria-label="你的译文" rows="3" maxlength="800" lang="${dir === 'zh2en' ? 'en' : 'zh'}" data-submit="#trGo" placeholder="${dir === 'zh2en' ? '译成英文…' : '译成中文…'}"></textarea>
          <div class="row between"><span class="muted tiny">${dir === 'zh2en' ? '译完对照原文，看哪里不一样。' : '意思准确、读起来像中文就是好译文。'}</span><button class="btn primary" id="trGo">提交</button></div><div id="trOut"></div>`;
        pane.querySelectorAll('[data-dir]').forEach(b => b.onclick = () => { dir = b.dataset.dir; save('flow-next-trans-dir', dir); render(); });
        pane.querySelector('#trNext').onclick = () => { k = (k + 1) % good.length; render(); };
        if (dir === 'zh2en') {
          if (!S.user) { pane.querySelector('#trSrc').innerHTML = '<span class="muted small">登录后可以做汉译英（中文原句由 AI 翻出，全站共享）。</span>'; }
          else {
            const src = pane.querySelector('#trSrc');
            const zh = await api('/api/next/translate/source', { pack: id, i, request_id: rid('ts') }).then(r => r.zh, e => e.message);
            if (!src.isConnected) return;  // a newer render() owns the pane (and its #trGo)
            src.textContent = zh;
          }
        }
        pane.querySelector('#trGo').onclick = async e => {
          if (needAI('登录后 AI 会批改你的译文。')) return;
          const text = pane.querySelector('#trIn').value.trim(); if (text.length < 2) { toast('先写下你的译文'); return; }
          const btn = e.currentTarget, out = pane.querySelector('#trOut'); btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
          try {
            const x = (await api('/api/next/translate', { pack: id, i, direction: dir, text, request_id: rid('tr') })).result;
            if (!out.isConnected) return;
            out.innerHTML = `<div class="result enter stack" data-ex-block>${aiMark('评分和讲解由 AI 生成，仅供参考')}<div class="card verdict"><span class="dot"></span><div>得分 ${Math.round(x.score * 100)}<div class="small" data-ex>${esc(x.accuracy)}</div><div class="small muted" data-ex>${esc(x.fluency)}</div></div></div>
              ${fixesHTML(x.fixes)}<div class="card flat stack-s"><b>${dir === 'zh2en' ? '原文' : '参考译文'}</b><div class="text small" data-zh>${esc(dir === 'zh2en' ? x.original : x.reference)}</div>
              ${dir === 'zh2en' && x.reference && x.reference !== x.original ? `<div class="tiny muted">另一种自然说法：${esc(x.reference)}</div>` : ''}</div></div>`;
            markStep('output'); showFinish(pane, m, id); bringIntoView(pane.querySelector('#trOut')); draftDone(`trans-${id}-${dir}-${i}`);
          } catch (x) { toast(x.message); }
          btn.disabled = false; btn.textContent = '提交';
        };
      }
      render();
    }

    function essayMode() {
      const key = 'flow-next-essay-' + id, lv = m.user_level || level();
      // The task's own word count wins ("写 200–250 词"); otherwise a range that fits the level.
      const asked = /(\d{2,3})\s*[–~\-—至到]\s*(\d{2,3})\s*(?:个)?(?:英文)?词/.exec(m.writing_task || '');
      const range = asked ? [Number(asked[1]), Number(asked[2])] : { A2: [60, 120], B1: [80, 160], B2: [120, 250], C1: [180, 350] }[lv] || [80, 200];
      pane.innerHTML = `${outTabs('essay')}<div class="card flat task stack-s"><div class="kicker">建议 ${range[0]}–${range[1]} 词</div><b${m.writing_task ? ' data-zh' : ''}>${esc(m.writing_task || '围绕这篇的话题，写一段你自己的看法或经历。')}</b>
          <span class="muted small">按内容、结构、准确、丰富四个维度批改，给段落点评和示范段落；改出来的错误进错题本。</span></div>
        <textarea id="esIn" aria-label="你的英文作文" rows="10" maxlength="3000" lang="en" data-submit="#esGo" placeholder="Write here…">${esc(load(key) || '')}</textarea>
        <div class="row between"><span class="counter" id="esN"></span><button class="btn primary" id="esGo">AI 批改</button></div><div id="esOut"></div>`;
      const ta = pane.querySelector('#esIn'), n = pane.querySelector('#esN');
      const count = () => { const w = (ta.value.match(/[A-Za-z]+(?:'[A-Za-z]+)?/g) || []).length; n.textContent = `${w} 词`; n.classList.toggle('warn', w && (w < range[0] || w > range[1])); return w; };
      ta.oninput = () => { save(key, ta.value); count(); }; count();
      pane.querySelector('#esGo').onclick = async e => {
        if (needAI('登录后 AI 会按评分维度批改你的短文。')) return;
        if (count() < 40) { toast('至少写 40 个词'); return; }
        const btn = e.currentTarget, out = pane.querySelector('#esOut'); btn.disabled = true; btn.innerHTML = '<span class="spin"></span> 正在批改…';
        try {
          const x = (await api('/api/next/essay', { pack: id, text: ta.value, request_id: rid('es') })).result;
          if (!out.isConnected) return;
          const dims = { content: '内容切题', organization: '结构衔接', accuracy: '语言准确', range: '词汇句式' };
          pane.querySelector('#esOut').innerHTML = `<div class="result enter stack" data-ex-block>${aiMark('批改、评分和示范由 AI 生成，仅供参考')}<div class="card verdict"><span class="dot"></span><div><span data-ex>${esc(x.comment)}</span>${x.level ? `<div class="tiny muted">这篇体现的水平约 ${esc(x.level)}</div>` : ''}</div></div>
            <div class="card flat ab-list">${Object.entries(dims).map(([k, l]) => `<div class="ab"><span class="nm">${l}</span><span class="vbar"><i data-w="${x.scores[k] * 20}"></i></span><span class="lv">${x.scores[k]} / 5</span></div>`).join('')}</div>
            ${x.paragraphs.length ? `<div class="card flat stack-s"><b>段落点评</b>${x.paragraphs.map(pg => `<div class="small"><b>第 ${pg.para} 段</b>：<span data-ex>${esc(pg.note)}</span></div>`).join('')}</div>` : ''}
            ${fixesHTML(x.fixes)}
            ${x.better.length ? `<div class="card flat stack-s"><b>可以写得更好</b>${x.better.map(b => `<div class="small"><del>${esc(b.from)}</del><br><ins>${esc(b.to)}</ins><div class="tiny muted" data-ex>${esc(b.why)}</div></div>`).join('')}</div>` : ''}
            ${x.model ? `<div class="card flat stack-s"><b>示范段落</b><div class="text small">${esc(x.model)}</div></div>` : ''}</div>`;
          requestAnimationFrame(() => requestAnimationFrame(() => pane.querySelectorAll('#esOut .vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
          const wn = count();
          if (wn < range[0] || wn > range[1]) pane.querySelector('#esOut .result > .ai-line').insertAdjacentHTML('afterend', `<div class="card sunk small">这篇 ${wn} 词，任务建议 ${range[0]}–${range[1]} 词：${wn < range[0] ? '内容展开得还不够，考试里会影响「内容」分。' : '超出了建议长度，考试里要注意时间和篇幅。'}</div>`);
          markStep('output'); showFinish(pane, m, id); bringIntoView(pane.querySelector('#esOut'));
        } catch (x) { toast(x.message); }
        btn.disabled = false; btn.textContent = '再批改一次';
      };
    }

    function output() {
      const om = parts()[3];
      if (om === 'retell') return retellMode();
      if (om === 'dialog') return dialogMode();
      if (om === 'translate') return translateMode();
      if (om === 'essay') return essayMode();
      const key = 'flow-next-draft-' + id;
      const draft = load(key) || '';
      // 仿写 in three blocks (B9, 2026-11-26; the user on the mock-ups: 完全做，按照现在的效果图): the sentence to copy with
      // the task under it, the box to write in with its count, and the one full-width button.
      pane.innerHTML = `${outTabs('model')}<div class="stack-s out1"><div class="card flat task out-card">
          ${m.task.model ? `<div class="out-top"><span class="tiny muted">照这句写一句</span><span class="say-pair">${aiVoiceNote('AI 合成', 'span')}<button class="icon-btn out-say" id="sayModel" type="button" aria-label="朗读参考句（AI 朗读）">${ICON.speak}</button></span></div>
          <div class="model" lang="en">${esc(m.task.model)}</div>` : ''}
          <p class="out-task" data-zh>${esc(m.task.prompt)}</p>
          ${m.task.hint ? `<div class="muted small" data-zh>${esc(m.task.hint)}</div>` : ''}${tryHintHTML(id)}
          ${(m.mine || []).length ? `<div class="muted small">可以试着用上你在背的词：${[...new Set(m.mine.map(x => x.form))].slice(0, 5).map(w => `<b>${esc(w)}</b>`).join('、')}（用对了算一次成功复习）</div>` : ''}</div>
        <label class="card flat out-write"><span class="sr-only">你的英文</span><textarea id="ans" maxlength="600" lang="en" data-submit="#go" placeholder="写一两句就好，写错没关系。">${esc(draft)}</textarea><span class="counter" id="cnt">${draft.length} / 600</span></label>
        <button class="btn primary block out-go" id="go">让 AI 帮我改</button>
        <p class="err" id="outErr" role="alert"></p><div id="result"></div></div>`;
      const ta = pane.querySelector('#ans');
      ta.oninput = () => { save(key, ta.value); pane.querySelector('#cnt').textContent = ta.value.length + ' / 600'; };
      const sm = pane.querySelector('#sayModel'); if (sm) sm.onclick = () => TTS.say(m.task.model);
      pane.querySelector('#go').onclick = async () => {
        const text = ta.value.trim(), err = pane.querySelector('#outErr'); err.textContent = '';
        if (!/[A-Za-z]{2,}.*\s+.*[A-Za-z]/.test(text)) { err.textContent = '先用英文写一个短句。'; return; }
        if (!S.user) return needLogin('登录后 AI 会帮你改写，并给出三种更好的说法。');
        const btn = pane.querySelector('#go'); btn.disabled = true; btn.innerHTML = '<span class="spin"></span> 正在看你写的…';
        try { const r = await api('/api/next/rewrite', { pack: id, text, request_id: rid('nr') }); markStep('output'); S.tryNode = null; if (!err.isConnected) return; renderResult(r.result, text, r.remaining); }
        catch (e) { err.textContent = e.message; }
        btn.disabled = false; btn.textContent = '再改一次';
      };
    }
    function renderResult(r, yours, remaining) {
      const box = pane.querySelector('#result');
      const same = r.corrected.trim() === yours.trim();
      box.innerHTML = `<div class="result enter" data-ex-block><div class="ai-line">${aiTag()}<span>批改由 AI 生成，仅供参考</span>${aiVoiceNote('AI 朗读', 'span')}</div>
        <div class="card verdict ${esc(r.verdict)}"><span class="dot"></span><div data-ex>${esc(r.summary)}</div></div>
        <div class="card compare"><div class="kicker">${same ? '你写的已经是对的' : '改对之后'}</div>
          ${same ? '' : `<div class="yours">${esc(yours)}</div>`}<div class="fixed">${esc(r.corrected)} ${sayIcon(`data-say-text="${esc(r.corrected)}"`, '朗读')}</div>
          ${r.changes.length ? `<div>${r.changes.map(c => `<div class="change"><span class="ft"><del>${esc(c.from)}</del> → <ins>${esc(c.to)}</ins></span><span class="why" data-ex>${esc(c.why)}</span>${c.node ? `<span>${nodeChip({ id: c.node, title: c.node_title || c.node, status: 'watch' })}</span>` : ''}</div>`).join('')}</div>` : ''}
          ${r.used_well && r.used_well.length ? `<div class="used-well small"><span class="muted">用对了：</span>${r.used_well.map(n => nodeChip({ id: n.id, title: n.title, status: 'used' })).join('')}</div>` : ''}</div>
        <div class="stack-s"><h2 class="h2">还可以这样说</h2>${r.versions.map((v, i) => `<div class="version"><div class="row between"><span class="pill green">${esc(v.label)}</span><span class="row">${sayIcon(`data-say-text="${esc(v.text)}"`, '朗读')}<button class="icon-btn" data-keep-v="${i}" aria-label="收藏这句">${ICON.star}</button></span></div><div class="v">${esc(v.text)}</div><div class="small muted" data-ex>${esc(v.why)}</div></div>`).join('')}</div>
        ${r.word_use && r.word_use.length ? `<div class="card sunk stack-s"><div class="kicker">你用到了正在背的词</div>${r.word_use.map(u => `<div class="small"><span class="${u.ok ? 'ok-mark' : 'bad-mark'}">${u.ok ? '✓' : '✗'}</span> <b>${esc(u.word)}</b>：<span data-ex>${esc(u.note)}</span></div>`).join('')}
          <div class="tiny muted">用对的算一次成功复习；用错的会提前安排复习。</div></div>` : ''}
        ${r.keep ? `<div class="card sunk row between"><div><div class="kicker">值得收藏</div><b class="text">${esc(r.keep.text)}</b> <span class="muted small" data-zh>${esc(r.keep.meaning)}</span></div><button class="btn small primary" id="keep">收藏</button></div>` : ''}
        </div>`;
      box.querySelectorAll('[data-say-text]').forEach(b => b.onclick = () => TTS.say(b.dataset.sayText));
      showFinish(pane, m, id, remaining);  // 这篇完成了, with what this text gave (25-finish.js)
      box.querySelectorAll('[data-keep-v]').forEach(b => b.onclick = () => { const v = r.versions[Number(b.dataset.keepV)]; saveCard({ text: v.text, meaning: v.label + '：' + v.why, context: '', pack: id }, b); });
      const k = box.querySelector('#keep'); if (k) k.onclick = () => saveCard({ text: r.keep.text, meaning: r.keep.meaning, context: r.corrected, pack: id }, k);
      box.scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'start' });
    }
    ({ listen, read, check, output })[st.step]();
  }
  /* ---------- 这篇完成了 (r27): after 用出来, three lines on what this text gave the learner ---------- */
  // The expressions and words saved from this text, and one grammar point to work on (progress_service.text_summary):
  // one the AI corrected in what was written for it, else one of its points that needs attention or has not been
  // checked with questions yet. Each line goes where that work continues. Shown after any of the five ways of 用出来,
  // once at the end of the step (a second answer draws it again with what has changed). The share card stays.
  function finishCard(m, id, remaining) {
    const share = (m.expressions || []).length ? '<button class="link small" id="shareDone" type="button" data-tap="share-material">把学会的一句做成卡片</button>' : '';
    const next = m.series && m.series.next ? `<a class="btn" href="#/">回到今日</a><a class="btn primary" href="#/m/${encodeURIComponent(m.series.next)}">下一集：第 ${m.series.part + 1} 集</a>`
      : '<a class="btn" href="#/graph">看知识图谱</a><a class="btn primary" href="#/">回到今日</a>';
    return `<div class="card done-card fin enter" id="finCard">${doneRing}<h2 class="h2">这篇完成了</h2>
      ${S.user ? '<div class="fin-sum" id="finSum" aria-live="polite" aria-busy="true"><span class="fin-wait"><span class="spin"></span> 正在整理这篇学到的…</span></div>' : ''}
      ${share}<p class="muted tiny">${remaining != null ? '今天还可以用 AI ' + remaining + ' 次。' : ''}收藏的表达和生词会按遗忘曲线安排复习。</p>
      <div class="row center">${next}</div></div>`;
  }
  function finishLines(s, id) {
    const row = (k, text, href, tap) => href ? `<a class="fin-row" href="${href}" data-tap="${tap}"><span class="k">${k}</span><span class="t">${text}</span><span class="go" aria-hidden="true">›</span></a>`
      : `<div class="fin-row"><span class="k">${k}</span><span class="t">${text}</span></div>`;
    const list = xs => xs.slice(0, 2).map(x => `<b lang="en">${esc(x.text || x)}</b>`).join('、');
    const e = s.expressions, w = s.words, g = s.grammar;
    const expr = e.count ? row('表达', `收藏了 ${e.count} 个：${list(e.saved)}${e.count > 2 ? ' 等' : ''}`, '#/cards/phrase', 'finish-expr')
      : e.key.length ? row('表达', `还没收藏。这篇的重点：${list(e.key)}`, `#/m/${encodeURIComponent(id)}/read`, 'finish-expr') : row('表达', '这篇没有收藏表达');
    const words = w.count ? row('新词', `收藏了 ${w.count} 个：${list(w.saved)}${w.count > 2 ? ' 等' : ''}，明天开始复习`, '#/cards/word', 'finish-words')
      : w.mine.length ? row('新词', `没有收藏生词；这篇里有你在背的 ${w.mine.length} 个：${list(w.mine)}${w.mine.length > 2 ? ' 等' : ''}`, '#/cards/word', 'finish-words')
      : row('新词', '这篇没有收藏生词');
    const node = g && g.id ? `#/graph/${encodeURIComponent(g.id)}` : '';
    const gram = !g ? row('语法', '这篇没有标出语法点')
      : g.all_solid ? row('语法', `这篇的 ${g.count} 个语法点都做题验证过了 ✓`)
      : g.why === 'flag' ? row('语法', `「${esc(g.title)}」写错了 ${g.times} 次${g.change ? `（<span lang="en">${esc(g.change)}</span>）` : ''}，做 4 题巩固`, node, 'finish-grammar')
      : g.why === 'watch' ? row('语法', `「${esc(g.title)}」需要留意，做 4 题巩固`, node, 'finish-grammar')
      : row('语法', `这篇用到了「${esc(g.title)}」，做 4 题验证一下`, node, 'finish-grammar');
    return expr + words + gram;
  }
  // The finish card at the end of the step's pane (one; drawn again after another answer), then its three lines.
  async function showFinish(pane, m, id, remaining) {
    let slot = pane.querySelector('#finSlot');
    if (!slot) { slot = document.createElement('div'); slot.id = 'finSlot'; slot.className = 'section'; pane.appendChild(slot); }
    slot.innerHTML = finishCard(m, id, remaining);
    const sd = slot.querySelector('#shareDone'); if (sd) sd.onclick = () => shareFromMaterial(m);
    const box = slot.querySelector('#finSum'); if (!box) return;
    try {
      const s = await api('/api/next/text-summary?pack=' + encodeURIComponent(id));
      if (box.isConnected) { box.innerHTML = finishLines(s, id); box.removeAttribute('aria-busy'); }
    } catch (e) { box.remove(); }
  }
  /* ---------- 听两句、答一句 (r29, the user's pick 2026-11-26): 5 分钟的表达日 ---------- */
  // Two neighbouring sentences of today's text, heard first (the recording when this text as shown has one, else the
  // server voice), then a question the AI writes on them (two_lines.ask, marked AI 生成), one sentence back by voice or
  // typing, and one line of AI feedback (two_lines.check). 给我一点提示 shows a way to begin and marks the answer as
  // helped (assisted). The phrase to learn goes into 单词本 at once, with 撤销.
  function twoPair(m) {
    // the first pair that holds one of the text's marked expressions, else the first two sentences
    const ss = m.sentences || [], ex = (m.expressions || []).map(e => (e.text || '').toLowerCase()).filter(Boolean);
    for (let i = 0; i + 1 < ss.length; i++) {
      const pair = (ss[i] + ' ' + ss[i + 1]).toLowerCase();
      if (ex.some(e => pair.indexOf(e) >= 0)) return i;
    }
    return 0;
  }
  async function twoView(pid) {
    const m = MAT[pid] || await api(materialPath(pid));
    MAT[pid] = m;
    const i = twoPair(m), lines = [(m.sentences || [])[i] || '', (m.sentences || [])[i + 1] || ''];
    const voice = !m.variant && m.audio && (m.audio.voices || []).indexOf(S.voice) >= 0 ? m.audio.version : 0;
    let q = null, hinted = false, blob = null;
    view.innerHTML = `<div class="one-task stack">
      <div><span class="kicker">今天的计划 · 约 3 分钟</span><h1 class="h1">听两句，用一句话回答</h1></div>
      <div class="two-listen"><button class="btn block" id="twPlay" type="button" data-tap="two-play">${ICON.speak}听这两句</button>
        <span class="small muted">出自《${esc(m.title)}》 · <button class="link small" id="twShow" type="button">看原文</button></span>
        <p class="two-lines" id="twLines" lang="en" hidden>${lines.map(esc).join('<br>')}</p>${aiVoiceNote('朗读由 AI 合成')}</div>
      <div class="two-q" id="twQ"><span class="tiny muted">问题 ${aiTag()}</span><b lang="en" id="twQen"><span class="spin"></span></b><span class="small muted" id="twQzh"></span>
        <span class="small two-hint" id="twHint" hidden></span></div>
      <div class="two-answer" id="twAns">
        <button class="btn primary block two-say" id="twMic" type="button">说出来</button>
        <textarea id="twText" rows="2" maxlength="300" lang="en" placeholder="用英文写一句" hidden></textarea>
        <div class="two-alts"><button class="link small hit44" id="twType" type="button">改成打字</button><button class="link small hit44" id="twHelp" type="button" data-tap="two-hint">给我一点提示</button></div>
        <button class="btn primary block" id="twSend" type="button" hidden>交上去</button></div>
      <div id="twOut"></div></div>`;
    const $ = s => view.querySelector(s);
    $('#twPlay').onclick = () => CLIP.sentence({ pack: pid, i, text: lines[0], audio: voice }, () => CLIP.sentence({ pack: pid, i: i + 1, text: lines[1], audio: voice }));
    $('#twShow').onclick = e => { $('#twLines').hidden = !$('#twLines').hidden; e.currentTarget.textContent = $('#twLines').hidden ? '看原文' : '收起原文'; };
    try {
      q = (await api('/api/next/two/ask', { pack: pid, i, lines, request_id: rid('ta') })).result;
      if (!$('#twQen')) return;
      $('#twQen').textContent = q.question; $('#twQzh').textContent = q.zh || '';
    } catch (e) { if ($('#twQen')) $('#twQen').textContent = e.message; return; }
    $('#twHelp').onclick = () => { hinted = true; $('#twHint').hidden = false; $('#twHint').textContent = '可以这样开头：' + (q.hint || ''); $('#twHelp').hidden = true; };
    $('#twType').onclick = () => { $('#twText').hidden = false; $('#twSend').hidden = false; $('#twMic').hidden = true; $('#twType').hidden = true; $('#twText').focus(); };
    const send = async body => {
      $('#twOut').innerHTML = '<p class="small muted"><span class="spin"></span> 正在看…</p>';
      try {
        const x = (await api('/api/next/two/check', Object.assign({ pack: pid, i, lines, question: q.question, assisted: hinted, request_id: rid('tc') }, body))).result;
        if (!$('#twOut')) return;
        if (x.heard_nothing) { $('#twOut').innerHTML = `<p class="small">${esc(x.note || '没听清，再说一次吧')}</p>`; return; }  // no answer: say it again
        twoFeedback(pid, m, x, body.text || '', hinted);
      } catch (e) { if ($('#twOut')) $('#twOut').innerHTML = `<p class="small">${esc(e.message)}</p>`; }
    };
    $('#twMic').onclick = () => MIC.toggle($('#twMic'), 30, async b => { blob = b; send({ audio: await MIC.payload(blob) }); });
    $('#twSend').onclick = () => {
      const text = $('#twText').value.trim();
      if ((text.match(/[A-Za-z]+/g) || []).length < 3) { toast('请用英文写至少 3 个词'); return; }
      send({ text });
    };
  }
  // The feedback, said plainly: met or not yet, what was said, a better way; the phrase to learn is kept, with 撤销.
  async function twoFeedback(pid, m, x, said, hinted) {
    const met = x.met === 'met', better = esc(x.better || '').replace(/\[\[(.+?)\]\]/g, '<b>$1</b>');
    ['#twAns', '#twQ'].forEach(s => { const e = view.querySelector(s); if (e) e.hidden = true; });
    const ls = view.querySelector('.two-listen'); if (ls) ls.hidden = true;  // the answer's page: what was said and a better way, nothing else
    view.querySelector('h1').textContent = met ? '说到了' : '意思还没到';
    scrollTo(0, 0);
    const out = view.querySelector('#twOut');
    out.innerHTML = `<div class="two-fb stack-s" data-ex-block><span class="tiny muted">✦ AI 点评</span><span class="${met ? 'two-ok' : ''}" data-ex>${esc(x.note || '')}</span>
        ${said ? `<div class="stack-s"><span class="tiny muted">你说的</span><span class="two-en" lang="en">${esc(said)}</span></div>` : ''}
        ${better ? `<div class="stack-s"><span class="tiny muted">${met ? '还可以这样说' : '可以这样开头'}</span><span class="two-en" lang="en">${better}</span></div>` : ''}
        <span class="tiny muted" id="twSaved">${hinted ? '看了提示' : '没看提示，自己说的'}</span></div>
      ${met ? `<div class="two-row"><button class="btn block" id="twAgain" type="button">再说一次</button><a class="btn primary block" href="#/" data-tap="two-next">下一步</a></div>`
        : `<button class="btn primary block" id="twAgain" type="button">再说一次</button><a class="link small hit44 two-skip" href="#/">先跳过，明天再练</a>`}`;
    out.querySelector('#twAgain').onclick = () => twoView(pid);
    if (met && x.save && S.user) {
      try {
        const r = await api('/api/next/cards', { text: x.save, meaning: '', context: (x.better || '').replace(/\[\[|\]\]/g, ''), pack: pid });
        const line = out.querySelector('#twSaved');
        if (!r.existing && line) {
          line.innerHTML = `${hinted ? '看了提示' : '没看提示，自己说的'} · 「${esc(x.save)}」已存进单词本，明天复习 · <button class="link tiny" id="twUndo" type="button">撤销</button>`;
          line.querySelector('#twUndo').onclick = async () => {
            try { await api('/api/next/cards/delete', { id: r.card.id }); line.textContent = hinted ? '看了提示' : '没看提示，自己说的'; } catch (e) { toast(e.message); }
          };
        }
      } catch (e) { /* kept for later: the feedback stands */ }
    }
  }
  // no lookbehind assertion here: Safari before iOS 16.4 cannot parse one, and then none of next.js runs (2026-11-25)
  function splitSentences(body) { return body.replace(/([.!?]["”’]?)\s+/g, '$1\u0001').split('\u0001').map(s => s.trim()).filter(Boolean); }
  function findContext(term, ls) { const t = term.toLowerCase(); return ls.find(s => s.toLowerCase().includes(t)) || ''; }

  async function lookupSheet(word, sentence, pack, mine) {
    if (mine && S.user) api('/api/next/vocab/met', { word }).then(r => { if (r.card && r.card.moved) toast('这个词在你的复习里，查了说明还不熟，已提前安排复习'); }).catch(() => {});
    openSheet(`<p class="loading"><span class="spin"></span></p>`);
    let e = null;
    try { e = (await api('/api/next/lookup?w=' + encodeURIComponent(word))).entry; } catch (x) { /* show fallback */ }
    const meaning = e ? e.meaning : '';
    // The recorded pronunciation when there is one (it plays in every browser, WeChat's too); else the browser voice.
    const sayWord = () => (e && e.audio && (e.audio.us || e.audio.uk) ? CLIP.word({ text: e.word, audio: e.audio }) : TTS.word(e ? e.word : word));
    const mt = MAT[pack];
    // This text's own gloss (本篇词汇) says what the word means here; the dictionary lists every sense.
    const here = mt && (mt.vocabulary || []).find(v => { const t = v.term.toLowerCase(); return t === word.toLowerCase() || (e && t === e.lemma); });
    if (e && mt) { (mt._looked = mt._looked || new Map()).set(e.lemma, { word: e.lemma, meaning: meaning.split('；').slice(0, 2).join('；').slice(0, 40), sentence }); if (mt._onLook) mt._onLook(); }
    openSheet(`<div class="stack">
      ${wordHead(e ? e.word : word, (e ? e.phonetic : '') + (e && e.lemma !== word.toLowerCase() ? ' · 原形 ' + e.lemma : ''))}
      ${here ? `<div class="here"><span class="pill green">在这篇里</span> <span data-zh>${esc(here.meaning)}</span></div>` : ''}
      <div class="mean${here ? ' dict' : ''}"${e ? ' data-zh' : ''}>${e ? esc(meaning).replace(/；|;/g, '<br>') : '<span class="muted">词典里没有这个词，可以先收藏，复习时再查。</span>'}</div>
      ${e && e.example ? `<div class="small muted text">${esc(e.example)}</div>` : ''}
      ${e && e.confusable && e.confusable.length ? e.confusable.map(g => `<div class="cf-hint"><div><span class="pill amber">容易混</span> <b class="en">${esc(g.words.join(' / '))}</b></div>
        <div class="tiny muted" data-zh>${esc(g.how)}</div><a class="link small" href="#/words/confuse/${encodeURIComponent(g.id)}" data-close>辨析练习 →</a></div>`).join('') : ''}
      <div class="card sunk small text">${esc(sentence)}</div>
      <div class="row"><button class="btn primary" id="saveW">${ICON.star.replace('<svg', '<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8"')}收藏这个词</button><button class="btn" id="saveS">收藏整句</button><button class="btn" id="exS">✦ AI 讲解整句</button></div>
      <button class="btn ghost" data-close>关闭</button></div>`, card => {
      card.querySelectorAll('#sayW, .tapsay').forEach(b => { b.onclick = sayWord; });
      card.querySelector('#saveW').onclick = () => saveCard({ text: e ? e.lemma : word, meaning: here ? here.meaning + '；' + meaning : meaning, context: sentence, pack }, card.querySelector('#saveW')).then(ok => {
        if (!ok || !mt) return;
        const forms = new Set([word.toLowerCase(), e ? e.lemma : word.toLowerCase()]);
        mt.mine = (mt.mine || []).concat([...forms].map(f => ({ form: f, id: 0 })));
        document.querySelectorAll('#reader .w').forEach(w => { if (forms.has(w.dataset.w.toLowerCase())) w.classList.add('mine'); });
        if (mt._onLook) mt._onLook();
      });
      card.querySelector('#saveS').onclick = () => saveCard({ text: sentence, meaning: '', context: '', pack }, card.querySelector('#saveS'));
      card.querySelector('#exS').onclick = () => explainSheet(sentence, pack);
    });
    sayWord();
  }
  async function explainSheet(sentence, pack) {
    if (!S.user) { needLogin('登录后，AI 会结合知识图谱讲解这句话的结构、语气和可模仿的句型。'); return; }
    openSheet(`<div class="stack"><div class="kicker">AI 讲解</div><div class="text" id="sheetTitle">${esc(sentence)}</div><p class="loading"><span class="spin"></span> 正在分析这句话…</p></div>`);
    try {
      const r = await api('/api/next/explain', { pack, sentence, request_id: rid('nx') });
      const x = r.result;
      openSheet(`<div class="stack explain enter" data-ex-block><div class="row between"><div class="kicker">AI 讲解</div>${aiTag()}<span class="say-pair"><button class="icon-btn say-btn" id="sayS" type="button" aria-label="朗读这句（AI 朗读）">${ICON.speak}</button>${aiVoiceNote('AI 合成', 'span')}</span></div>
        <div class="text" id="sheetTitle">${esc(sentence)}</div>
        <div class="tr" data-zh>${esc(x.translation)}</div>${x.structure ? `<div class="small muted" data-ex>${esc(x.structure)}</div>` : ''}
        ${x.points.map(p => `<div class="pt"><b>${esc(p.text)}</b><span class="small" data-ex>${esc(p.note)}</span>${p.node ? `<span>${nodeChip({ id: p.node, title: p.node_title || p.node, status: 'met' })}</span>` : ''}</div>`).join('')}
        ${x.pattern ? `<div class="card sunk stack-s"><div class="kicker">可模仿的句型</div><div class="frame">${esc(x.pattern.frame)}</div>${x.pattern.example ? `<div class="text small">${esc(x.pattern.example)}</div>` : ''}<div><button class="btn small" id="savePat">收藏这个句型</button></div></div>` : ''}
        <button class="btn ghost" data-close>关闭</button></div>`, card => {
        card.querySelector('#sayS').onclick = () => TTS.say(sentence, null, null, { pack, rate: 1 });  // an import's sentence: its owner's file
        card.querySelectorAll('.node-chip').forEach(a => a.addEventListener('click', closeSheet));
        const sp = card.querySelector('#savePat'); if (sp) sp.onclick = () => saveCard({ text: x.pattern.frame, meaning: '句型' + (x.pattern.example ? '｜例：' + x.pattern.example : ''), context: sentence, pack }, sp);
      });
    } catch (e) { openSheet(`<div class="stack"><p class="err">${esc(e.message)}</p><button class="btn" data-close>关闭</button></div>`); }
  }
  async function saveCard(c, btn, from) {
    if (!S.user) { needLogin('登录后才能收藏，并按遗忘曲线提醒你复习。'); return false; }
    try {
      const r = await api('/api/next/cards', c);
      toast(r.existing ? '已经在复习里了，已更新原句' : '已收藏，会按遗忘曲线提醒你复习');
      if (btn) { btn.classList.add('on'); if (btn.classList.contains('btn')) { btn.disabled = true; btn.textContent = r.existing ? '已在复习里 ✓' : '已收藏 ✓'; } }
      if (!r.existing) flyToBank(c.text, btn || from);
      return true;
    } catch (e) { toast(e.message); return false; }
  }
  // A small label flies from where you saved it to the 单词 tab, so you see where it went.
  function flyToBank(text, fromEl) {
    const tab = document.querySelector('[data-nav="cards"]');
    if (!tab) return;
    if (!REDUCED && fromEl && fromEl.getBoundingClientRect) {
      const a = fromEl.getBoundingClientRect(), b = tab.getBoundingClientRect();
      const f = document.createElement('div'); f.className = 'flyer'; f.textContent = text.length > 24 ? text.slice(0, 22) + '…' : text;
      f.style.left = a.left + 'px'; f.style.top = a.top + 'px'; document.body.appendChild(f);
      requestAnimationFrame(() => requestAnimationFrame(() => { f.style.transform = `translate(${b.left + b.width / 2 - a.left - 30}px, ${b.top - a.top}px) scale(.5)`; f.style.opacity = '0'; }));
      setTimeout(() => f.remove(), 700);
    }
    setTimeout(() => { tab.classList.remove('bump'); void tab.offsetWidth; tab.classList.add('bump'); }, REDUCED ? 0 : 520);
  }

  /* ---------- 看中文 under the AI's English explanations (全英文界面, 语流 E1; the AI side is 语流 B7's ai_lang.py) ---------- */
  // In English mode the AI explains in English. Each block of AI feedback (data-ex-block: a result, a look-up's
  // explanation, a dialog's chat) gets one 「Show Chinese · 看中文」 button right after it, in both languages. Tapped, the
  // block's explanation lines (data-ex) go to /api/next/zh, 20 to a request (not counted as AI uses), and each comes
  // back in Chinese under its line: data-zh (left as it is, read with a Chinese voice), with 「AI 生成」 beside the button,
  // since an AI translated it. While it is on, lines added later (a dialog's next turn) come in Chinese too; tapped
  // again, the Chinese is hidden. In Chinese mode nothing here runs (the explanations are Chinese already).
  const EXZH_MAX = 20;
  // &nbsp; around the dot: a button lays its text out as flex items, which drop plain spaces at their ends
  const EXZH_SHOW = '<span lang="en">Show Chinese</span>&nbsp;·&nbsp;<span lang="zh-CN">看中文</span>';  // i18n: keep (both languages)
  const EXZH_HIDE = '<span lang="en">Hide Chinese</span>&nbsp;·&nbsp;<span lang="zh-CN">收起中文</span>';  // i18n: keep (both languages)
  const exZhLines = block => [...block.querySelectorAll('[data-ex]')].filter(el => !el.querySelector('.ex-zh') && el.textContent.trim());
  function exZhRow(block) {
    const next = block.nextElementSibling;
    if (next && next.classList.contains('ex-zh-row')) return next;
    const row = document.createElement('div');
    row.className = 'ex-zh-row'; row.setAttribute('translate', 'no');
    row.innerHTML = `<button class="link small" type="button" aria-pressed="false">${EXZH_SHOW}</button>`;
    block.insertAdjacentElement('afterend', row);
    row.querySelector('button').onclick = () => exZhToggle(block, row);
    return row;
  }
  async function exZhFill(block) {
    const lines = exZhLines(block);
    for (let k = 0; k < lines.length; k += EXZH_MAX) {
      const part = lines.slice(k, k + EXZH_MAX);
      const r = await api('/api/next/zh', { texts: part.map(el => el.textContent.trim().slice(0, 600)) });
      part.forEach((el, i) => {
        const zh = r && r.zh && r.zh[i];
        if (zh && el.isConnected && !el.querySelector('.ex-zh')) el.insertAdjacentHTML('beforeend', `<span class="ex-zh" data-zh lang="zh-CN">${esc(zh)}</span>`);
      });
    }
  }
  async function exZhToggle(block, row) {
    const b = row.querySelector('button');
    if (b.disabled) return;
    if (block.dataset.exzh === 'on') {
      block.dataset.exzh = 'off'; b.setAttribute('aria-pressed', 'false'); b.innerHTML = EXZH_SHOW; return;
    }
    b.disabled = true; b.classList.add('busy');
    try {
      await exZhFill(block);
      block.dataset.exzh = 'on'; b.setAttribute('aria-pressed', 'true'); b.innerHTML = EXZH_HIDE;
      if (!row.querySelector('.ai-mark')) b.insertAdjacentHTML('beforebegin', aiTag());
    } catch (e) { toast(e.message); }
    b.disabled = false; b.classList.remove('busy');
  }
  if (uiLang() === 'en') {
    // a block as it is drawn, or a line added to one (a dialog's next turn)
    const exZhScan = n => {
      const blocks = [];
      if (n.matches('[data-ex-block]')) blocks.push(n);
      n.querySelectorAll('[data-ex-block]').forEach(b => blocks.push(b));
      const up = n.parentElement && n.parentElement.closest('[data-ex-block]');
      if (up) blocks.push(up);
      blocks.forEach(b => {
        if (!exZhLines(b).length) return;
        exZhRow(b);
        if (b.dataset.exzh === 'on') exZhFill(b).catch(() => { /* the button stays; a tap asks again */ });
      });
    };
    new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => { if (n.nodeType === 1 && !n.classList.contains('ex-zh') && !n.classList.contains('ex-zh-row')) exZhScan(n); })))
      .observe(document.body, { childList: true, subtree: true });
  }
  /* ---------- knowledge graph ---------- */
  const STATUS_ORDER = ['solid', 'used', 'met', 'watch', 'untouched'];
  const LEVEL_ORDER = ['A2', 'B1', 'B2', 'C1'];
  // The point to practise next: one flagged in their writing or a wrong answer first, then one whose spaced re-check
  // has come (any level), then at the learner's level one they have met but not yet checked, then a new one; easier first.
  function nextPoint(g) {
    const all = g.topics.flatMap(t => t.nodes.map(n => ({ ...n, topic: t.title })));
    const rank = n => n.status === 'watch' ? 0 : n.due ? 1 : { met: 2, used: 3, untouched: 4 }[n.status];
    const open = all.filter(n => n.status === 'watch' || n.due || (n.focus && n.status !== 'solid'));
    open.sort((a, b) => rank(a) - rank(b) || LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level) || b.materials - a.materials);
    return open[0] || all.find(n => n.status !== 'solid') || null;
  }
  // The learning route: the 44 points in the order to learn them, one line per level, like stops on a metro line.
  // Only the level being learnt is open (the one with the next stop, else the learner's level); the others fold.
  const BAND = { A2: '入门', B1: '进阶', B2: '中高级', C1: '高级' };
  function routeHTML(g, next) {
    const openBand = (next && (g.route.find(b => b.nodes.some(n => n.id === next.id)) || {}).band) || (g.route.some(b => b.band === g.level) ? g.level : g.route[0] && g.route[0].band);
    return `<div class="route">${g.route.map(b => {
      const lit = b.nodes.filter(n => n.status !== 'untouched').length;
      return `<details class="rband fold"${b.band === openBand ? ' open' : ''}><summary class="rband-h"><b>${b.band}</b><span class="small muted">${BAND[b.band]} · ${b.nodes.length} 个点 · 已点亮 ${lit}</span></summary>
        <ol class="rline">${b.nodes.map((n, k) => { const here = next && n.id === next.id;
          return `<li class="rnode st st-${n.status}${n.status !== 'untouched' ? ' lit' : ''}${here ? ' here' : ''}" data-k="${k}"><a href="#/graph/${encodeURIComponent(n.id)}">
            <i class="dot" aria-hidden="true"></i><span class="t">${esc(n.title)}${here ? '<span class="here-tag">下一站</span>' : ''}${n.due ? '<span class="due-tag">该复习</span>' : ''}</span><span class="go" aria-hidden="true">›</span></a></li>`; }).join('')}</ol></details>`;
    }).join('')}</div>`;
  }
  async function graphView() {
    const g = await api('/api/next/graph' + guestQuery(true));
    const s = g.summary, next = nextPoint(g);
    const focusAll = g.topics.flatMap(t => t.nodes).filter(n => n.focus), focusSolid = focusAll.filter(n => n.status === 'solid').length;
    view.innerHTML = `<div><h1 class="h1">知识图谱</h1>
        <p class="muted small">${g.total} 个语法点，分成 ${g.topics.length} 类。读到、用出来、做题做对都会点亮它；AI 在你写作里发现的问题也会标在这里。</p></div>
      ${next ? `<div class="gnext"><div class="small muted">「${esc(g.level)}」现在的重点 ${focusAll.length} 个，已验证 ${focusSolid} 个</div>
        <a class="btn primary block go-next" href="#/graph/${encodeURIComponent(next.id)}">下一个：${esc(next.title)}<span aria-hidden="true">→</span></a>
        <div class="tiny muted">${next.status === 'watch' ? '你在写作或做题里在这里出过错，先补上它。' : next.due ? '按遗忘曲线该复习它了：做 4 道题，记得更牢。' : next.status === 'untouched' ? '先看讲解，再做几道题验证。' : '你已经读到过它，做几道题把它变成“已验证”。'}</div>
        ${s.due > 1 ? `<div class="tiny muted">一共 ${s.due} 个点该复习了，每天做一个就好。</div>` : ''}</div>` : ''}
      ${s.solid + s.used + s.met + s.watch < 5 ? `<a class="card flat place-cta" href="#/placement"><b>不知道从哪开始？</b><span class="small muted">做 16 道题的语法小测，3–6 分钟：给你一个起点等级，做对的点直接点亮。</span></a>` : ''}
      <div class="seg two section" role="tablist" aria-label="看法"><button role="tab" data-gv="route">学习路线</button><button role="tab" data-gv="all">全部 ${g.total} 个点</button></div>
      <div id="gRoute">${routeHTML(g, next)}</div><div id="gAll">
      <div class="gsum section">${[['solid', '已验证'], ['used', '用出来过'], ['met', '读到过'], ['watch', '要留意']].map(([k, l]) => `<div class="st st-${k}"><b>${s[k]}</b><span>${l}</span></div>`).join('')}</div>
      <div class="tgrid section" role="list" aria-label="13 类语法">${g.topics.map(t => {
        const lit = t.nodes.filter(n => n.status !== 'untouched').length, watch = t.nodes.some(n => n.status === 'watch');
        const focus = t.nodes.some(n => n.focus && n.status !== 'solid');
        return `<a class="tile${focus ? ' focus' : ''}" role="listitem" href="#/graph" data-topic="${esc(t.id)}" aria-label="${esc(t.title)}：${lit} / ${t.nodes.length} 个点亮${watch ? '，有要留意的' : ''}">
          <span class="ring" data-p="${Math.round(lit / t.nodes.length * 100)}"><b>${lit}/${t.nodes.length}</b>${watch ? '<i class="warn" aria-hidden="true"></i>' : ''}</span><span class="tl">${esc(t.title)}</span></a>`;
      }).join('')}</div>
      <div class="glegend">${STATUS_ORDER.map(k => `<span class="st st-${k}">${esc(g.labels[k])}</span>`).join('')}<span class="fz">${esc(g.level)} 重点</span></div>
      <div class="topic-list section">${g.topics.map(t => `<section class="topic" id="topic-${esc(t.id)}"><div class="row between"><h2 class="h2">${esc(t.title)}</h2><span class="tiny muted">${t.nodes.filter(n => n.status !== 'untouched').length} / ${t.nodes.length}</span></div>
        <div class="plist">${t.nodes.map(n => `<a class="nrow st st-${n.status}${n.focus ? ' focus' : ''}" href="#/graph/${encodeURIComponent(n.id)}"><i class="dot" aria-hidden="true"></i>
          <span class="t"><b>${esc(n.title)}</b><span class="tiny muted">${esc(n.label)}${n.due ? ' · <span class="due-tag">该复习</span>' : ''}${n.materials ? ` · ${n.materials} 篇材料` : ''}</span></span><span class="lv">${esc(n.level || '')}</span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div></section>`).join('')}</div>
      </div>${S.user ? '' : '<p class="muted small section">登录后，你读过、写过、做对的内容会实时点亮这张图。</p>'}`;
    const show = gv => {
      document.getElementById('gRoute').hidden = gv !== 'route'; document.getElementById('gAll').hidden = gv === 'route';
      view.querySelectorAll('[data-gv]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.gv === gv)));
      try { localStorage.setItem('flow-graph-view', gv); } catch (e) { /* private mode */ }
      if (gv === 'route') view.querySelectorAll('.rnode').forEach(li => { li.classList.remove('drawn'); li.style.setProperty('--d', (Number(li.dataset.k) * 45) + 'ms'); requestAnimationFrame(() => requestAnimationFrame(() => li.classList.add('drawn'))); });
    };
    let gv = 'route'; try { gv = localStorage.getItem('flow-graph-view') === 'all' ? 'all' : 'route'; } catch (e) { /* private mode */ }
    view.querySelectorAll('[data-gv]').forEach(b => b.onclick = () => show(b.dataset.gv));
    show(gv);
    view.querySelectorAll('details.rband').forEach(d => d.addEventListener('toggle', () => {
      if (d.open) d.querySelectorAll('.rnode').forEach(li => { li.classList.remove('drawn'); requestAnimationFrame(() => requestAnimationFrame(() => li.classList.add('drawn'))); });
    }));
    // CSP forbids inline style attributes, so the ring fill is set through the CSSOM.
    view.querySelectorAll('.tile .ring').forEach(r => r.style.setProperty('--p', r.dataset.p + '%'));
    view.querySelectorAll('.tile').forEach(a => a.onclick = e => {
      e.preventDefault();
      const sec = document.getElementById('topic-' + a.dataset.topic); if (sec) scrollToEl(sec);
    });
  }
  function scrollToEl(el) {
    const head = document.getElementById('bar').getBoundingClientRect().bottom;
    window.scrollTo({ top: window.scrollY + el.getBoundingClientRect().top - Math.max(0, head) - 12, behavior: REDUCED ? 'auto' : 'smooth' });
  }
  async function nodeView(nid) {
    const n = await api('/api/next/node?id=' + encodeURIComponent(nid) + guestQuery(false));
    const pg = n.page && n.page.status === 'ready' ? n.page : null;
    const stats = `读到过 ${n.met} 篇 · 用出来 ${n.used} 次${n.flags ? ' · 写作中被指出 ' + n.flags + ' 次' : ''}${n.evidence ? ' · 做题：' + esc(n.evidence) : ''}`;
    const choice = (q, i, kind) => `<div class="q gq" data-kind="${kind}" data-i="${i}"><div class="prompt">${esc(q.prompt)}</div>
      ${q.options.map((o, j) => `<button class="ans" data-o="${q.map ? q.map[j] : j}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}<div class="fb" aria-live="polite"></div></div>`;
    const reviewText = r => !r ? '' : r.is_due ? '按遗忘曲线，今天该复习这个点了' : `下次复习：${r.in_days} 天后（第 ${r.step + 1} / ${r.rungs} 轮）`;
    view.innerHTML = `<div><a class="link small" href="#/graph">← 知识图谱</a></div>
      <div class="node-head"><span class="kicker">${esc(n.topic)} · ${esc(n.level || '')}${n.focus ? ' · 你现在的重点' : ''}</span><h1 class="h1">${esc(n.title)}</h1>
        <div class="row"><span class="node-chip st st-${n.status}" id="nodeStatus">${esc(n.label)}</span>${n.practice.length ? `<button class="btn small" id="toPractice">做 ${n.practice.length} 题验证 ↓</button>` : ''}</div><div class="tiny muted">${stats}</div><div class="tiny muted" id="nodeReview">${esc(reviewText(n.review))}</div></div>
      <div class="lesson section stack-s">${aiMark('讲解和练习题由 AI 辅助编写')}
        <p class="goal">${esc(pg ? pg.goal : n.lesson)}</p>
        ${pg ? `<ol class="steps-list">${pg.steps.map(x => `<li>${esc(x)}</li>`).join('')}</ol>` : (n.example ? `<div class="text small">${esc(n.example)}</div>` : '')}
      </div>
      ${n.l1 ? `<div class="l1 section"><div class="kicker">中文思维陷阱</div><p class="small">${esc(n.l1.why)}</p>
        <div class="l1-rows"><div class="zh"><span class="tiny muted">中文</span>${esc(n.l1.zh)}</div><div class="bad"><span aria-label="常见错误">✗</span> ${esc(n.l1.wrong)}</div><div class="good"><span aria-label="正确">✓</span> ${esc(n.l1.right)}</div></div></div>` : ''}
      ${pg ? `<div class="section stack-s"><h2 class="h2">对比着看</h2>${aiVoiceNote('朗读由 AI 合成')}<div class="plist">${pg.contrast.map(([en, zh]) => `<div class="crow">${sayIcon(`data-say="${esc(en)}"`, '朗读')}<span><span class="en">${esc(en)}</span><span class="tiny muted">${esc(zh)}</span></span></div>`).join('')}</div></div>
      <div class="section stack-s"><h2 class="h2">常见错误</h2><div class="stack-s">${pg.pitfalls.map(([bad, good, why]) => `<div class="pit"><div class="bad"><span aria-label="错误">✗</span> ${esc(bad)}</div><div class="good"><span aria-label="正确">✓</span> ${esc(good)}</div><div class="tiny muted">${esc(why)}</div></div>`).join('')}</div></div>
      <div class="section stack-s"><div class="section-head"><h2 class="h2">先试一题</h2><span class="tiny muted">有提示，不计入验证</span></div>${choice(pg.guided, 0, 'guided')}</div>` : ''}
      ${n.practice.length ? `<div class="section stack-s" id="practice"><div class="section-head"><h2 class="h2">验证一下</h2><span class="tiny muted">${S.user ? '做对会点亮这个点；做错的会进错题本' : '登录后成绩会记进你的图谱'}</span></div>
        ${pg ? `<p class="small muted">做题前先问自己：${esc(pg.clue)}</p>` : ''}<div class="stack">${n.practice.map((q, i) => choice(q, i, 'check')).join('')}</div><div id="pscore" class="small"></div>
        <button class="btn" id="again" hidden>再来一组（题库 10 题，随机抽 4 题）</button></div>` : ''}
      <div class="section stack-s rel"><h2 class="h2">和它相连的点</h2>
        <div class="rel-flow">${n.prereq ? `<div class="rel-step"><span class="tiny muted">先学</span>${nodeChip(n.prereq)}</div><i class="rel-arrow" aria-hidden="true"></i>` : ''}
          <div class="rel-step me"><span class="tiny muted">现在</span><span class="node-chip st st-${n.status}">${esc(n.title)}</span></div>
          ${n.unlocks.length ? `<i class="rel-arrow" aria-hidden="true"></i><div class="rel-step"><span class="tiny muted">接下来</span><span class="chips">${n.unlocks.map(u => nodeChip(u)).join('')}</span></div>` : ''}</div>
        ${n.related.confusable.length ? `<div class="stack-s"><div class="kicker">容易和它混</div>${n.related.confusable.map(x => `<div class="confuse"><div class="row between">${nodeChip(x)}<a class="btn small" href="#/mix/pair/${encodeURIComponent(n.id + ',' + x.id)}">辨析练习</a></div><div class="tiny muted">${esc(x.how)}</div></div>`).join('')}</div>` : ''}
        ${n.related.together.length ? `<div class="stack-s"><div class="kicker">常和它一起出现</div><div class="chips">${n.related.together.map(x => nodeChip(x)).join('')}</div><span class="tiny muted">在同一篇材料里出现得最多的点，读到时可以留意它们怎么配合。</span></div>` : ''}</div>
      ${n.notes.length ? `<div class="stack-s section"><h2 class="h2">AI 在你写作里看到的</h2>${n.notes.map(x => `<div class="knote"><span class="small">${x.kind === 'flag' ? '需要留意：' : '用对了'}${esc((x.detail.split('|')[1] || ''))}</span><span class="tiny muted">${new Date(x.created * 1000).toLocaleDateString('zh-CN')}</span></div>`).join('')}</div>` : ''}
      ${n.examples.length ? `<div class="stack-s section"><h2 class="h2">在真实句子里看它</h2>${n.examples.map(x => `<a class="ex-quote" href="#/m/${encodeURIComponent(x.pack)}/read"><span>${esc(x.quote)}</span><div class="small muted">${esc(x.explanation)}</div></a>`).join('')}</div>` : ''}
      ${n.materials.length ? `<div class="section"><div class="section-head"><h2 class="h2">在文章里练它</h2></div><div class="grid-list">${n.materials.map(m => miniCard(m)).join('')}</div></div>` : ''}`;
    view.querySelectorAll('[data-say]').forEach(b => b.onclick = () => TTS.say(b.dataset.say));
    const jump = view.querySelector('#toPractice'); if (jump) jump.onclick = () => scrollToEl(view.querySelector('#practice'));
    const guided = pg ? pg.guided : null;
    let right = 0, answered = 0;
    view.querySelectorAll('.gq').forEach(box => box.querySelectorAll('.ans').forEach(b => b.onclick = async () => {
      if (box.dataset.done) return;
      const o = +b.dataset.o, fb = box.querySelector('.fb');
      let ok, answer, why;
      if (box.dataset.kind === 'guided') {  // learning support: checked here, never sent as evidence
        ok = o === guided.answer; answer = guided.answer; why = ok ? guided.explanation : '提示：' + guided.scaffold;
        if (!ok) { b.classList.add('wrong'); fb.textContent = why; return; }  // a hint and another go
      } else {
        const q = n.practice[+box.dataset.i];
        try { const r = await api('/api/next/node/answer', { question: q.id, choice: o }); ok = r.correct; answer = r.answer; why = r.explanation;
          if (r.label) { const st = view.querySelector('#nodeStatus'), was = st.className; st.className = 'node-chip st st-' + r.status; st.textContent = r.label;
            if (r.status === 'solid' && !/st-solid/.test(was)) { st.classList.add('lit-up'); toast('点亮了！「' + n.title + '」做题已验证'); } }
          if (r.review) view.querySelector('#nodeReview').textContent = ok ? reviewText(r.review) : '做错了：明天会再练一次这个点'; }
        catch (e) { toast(e.message); return; }
        answered++; if (ok) right++;
        const sc = view.querySelector('#pscore');
        if (answered === n.practice.length) {
          sc.textContent = `${n.practice.length} 题做对 ${right} 题。${right === n.practice.length ? (S.user ? '这个点可以算掌握了，到时间会提醒你再抽查一次。' : '这个点可以算掌握了。') : (S.user ? '错的题已经放进错题本，会按遗忘曲线再出现。' : '')}`;
          const again = view.querySelector('#again'); again.hidden = false; again.onclick = () => { const y = window.scrollY; route(true).then(() => window.scrollTo(0, y)); };
        }
      }
      box.dataset.done = '1';
      box.querySelectorAll('.ans').forEach(x => { x.disabled = true; if (+x.dataset.o === answer) x.classList.add('right'); });
      if (!ok) b.classList.add('wrong');
      fb.textContent = (ok ? '✓ ' : '✗ ') + (why || '') + (!ok && box.dataset.kind === 'check' && S.user ? ' 错题是最值钱的题：明天换一道题再考你。' : '');
      announce(ok ? '答对了' : '答错了');
    }));
  }
  /* ---------- grammar starting check: places the learner and lights the points they already know ---------- */
  async function placementView() {
    if (!S.meta) S.meta = await api('/api/next/meta');
    const t = await api('/api/next/placement');
    const items = t.items, per = t.per_band, answers = [];
    let i = 0;
    view.innerHTML = `<div class="place stack"><div><h1 class="h1">语法起点小测</h1>
        <p class="muted">16 道题，找到你的语法起点：会就选，不会就点「不会」，不用猜，一般 3–6 分钟。</p></div>
      <details class="basis"><summary>怎么测、测完有什么</summary><p class="small">从简单到难，每 4 题一档，题目明显变难、开始吃力时会自动结束。</p>
        <ul class="steps-list small"><li>做完给你一个起点等级，可以直接用它开始学</li><li>做对的语法点会点亮${S.user ? '' : '（登录后保存）'}，几天后再抽查一次</li><li>该补的点会排进今天的计划</li></ul></details>
      <p class="tiny muted">${esc(t.note)}</p>${aiMark('题目由 AI 辅助编写')}
      <button class="btn primary block" id="pStart">开始</button></div>`;
    document.getElementById('pStart').onclick = () => ask();
    function ask() {
      const q = items[i];
      view.innerHTML = `<div class="place stack"><div class="progress-line"><i id="pp"></i></div>
        <div class="row between"><span class="tiny muted">第 ${i + 1} 题 · 共最多 ${items.length} 题</span><span class="pill">${esc(q.band)}</span></div>
        <div class="q gq"><div class="prompt">${esc(q.prompt)}</div>
          ${q.options.map((o, j) => `<button class="ans" data-o="${q.map[j]}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}</div>
        <button class="btn ghost" id="pSkip">不会</button></div>`;
      const pp = document.getElementById('pp'); pp.style.width = (i / items.length * 100) + '%';
      requestAnimationFrame(() => requestAnimationFrame(() => { pp.style.width = ((i + 1) / items.length * 100) + '%'; }));
      enter(view.querySelector('.q'));
      const pick = (choice, btn) => {
        view.querySelectorAll('.ans, #pSkip').forEach(b => b.disabled = true);
        if (btn) btn.classList.add('chosen');
        answers.push({ question: q.id, choice });
        setTimeout(step, REDUCED ? 0 : 220);
      };
      view.querySelectorAll('.ans').forEach(b => b.onclick = () => pick(+b.dataset.o, b));
      document.getElementById('pSkip').onclick = () => pick(null, null);
      announce(`第 ${i + 1} 题`);
    }
    async function step() {
      i++;
      if (i % per === 0 || i === items.length) {  // a band is done: ask whether the check is decided
        let r;
        try { r = await api('/api/next/placement', { answers, final: i === items.length }); }
        catch (e) { toast(e.message); i--; answers.pop(); ask(); return; }
        if (r.done) return result(r);
      }
      ask();
    }
    function result(r) {
      const byId = Object.fromEntries(items.map(q => [q.id, q])), lv = (S.meta && S.meta.levels || []).find(l => l.id === r.level);
      const cur = (S.home && S.home.profile) || S.guest || null;
      view.innerHTML = `<div class="place stack"><div><span class="kicker">小测结果</span><h1 class="h1">建议从 ${esc(r.level)} 开始</h1>
          ${lv ? `<p class="muted">${esc(lv.label)}：${esc(lv.desc)}</p>` : ''}</div>
        <div class="pl-bands">${r.scores.map(s => `<div class="pl-band${s.right <= per / 2 ? ' low' : ''}"><b>${esc(s.band)}</b><span>${s.right} / ${s.of}</span></div>`).join('')}</div>
        <button class="btn primary block" id="pUse">${cur && cur.level === r.level ? `保持 ${esc(r.level)}，去学习` : `用 ${esc(r.level)} 开始学`}</button>
        ${r.gaps.length ? `<div class="section stack-s"><h2 class="h2">先补这 ${r.gaps.length} 个点</h2><p class="small muted">在你的起点以内做错了。${r.saved ? '已经标为“要留意”，每天的计划会先排一个来补。' : '登录后再测，它们会排进每天的计划。'}</p>
          <div class="plist">${r.gaps.map(g => `<a class="nrow st st-watch" href="#/graph/${encodeURIComponent(g.id)}"><i class="dot" aria-hidden="true"></i><span class="t"><b>${esc(g.title)}</b></span><span class="lv">${esc(g.band)}</span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div></div>` : ''}
        ${r.known.length ? `<p class="small section">${r.known.length} 个语法点做对了${r.saved ? '，已经在图谱里点亮，几天后会再抽查一次' : '；登录后再测一次，就会点亮在你的图谱里'}。</p>` : ''}
        <details class="section"><summary class="small">看每题的解析</summary><div class="stack-s">${r.results.map(x => { const q = byId[x.id]; if (!q) return '';
          const right = q.options[q.map.indexOf(x.answer)];
          return `<div class="pit"><div class="small">${esc(q.prompt)}</div><div class="${x.correct ? 'good' : 'bad'} small">${x.correct ? '✓ 答对' : '✗ 答案'}：${esc(right)}</div><div class="tiny muted">${esc(x.explanation)}</div></div>`; }).join('')}</div></details>
        <div class="row"><a class="link small" href="#/graph">看我的语法地图 →</a>${r.saved ? '<a class="link small" href="#/radar">语法这一项已记进能力雷达 →</a>' : ''}</div></div>`;
      enter(view.firstElementChild);
      announce('小测结束，建议从 ' + r.level + ' 开始');
      document.getElementById('pUse').onclick = async () => {
        if (!cur) { S.placed = r.level; location.hash = '#/welcome'; return; }  // first visit: the other questions still to come
        const prof = { ...cur, level: r.level, level_source: 'placed' };
        S.guest = prof; save('flow-next-guest', prof);
        if (S.user) { try { await api('/api/next/profile', prof); } catch (e) { toast(e.message); return; } }
        await refreshHome(); S.homeFresh = true; location.hash = '#/';
      };
    }
  }
  /* ---------- exam practice: a timed set at 中考 … 专八 / IELTS difficulty ---------- */
  const mmss = s => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  async function examView(pick) {
    const o = await api('/api/next/exam');
    // 考试冲刺 (42-sprint.js): with an exam set, the page opens on it; another exam opens in the list as before.
    let cur = null;
    // B9's batch 3 (the user, 2026-11-26; ui-refine/batch23/exam-*.png): the exams in one white card, a row each: the
    // name, 「约 N 分钟 ›」 on the right, a grey line on what it asks (and the last score); the chosen one opens under its row
    const examRow = e => `<a class="ex-row" href="#/exam/${e.id}" aria-pressed="${!!(cur && cur.id === e.id)}"><span class="l">${esc(e.title)}</span><span class="m">约 ${e.minutes} 分钟 ›</span>
        <span class="d">${esc(e.blurb)}${e.history.length ? ` · 上次 ${e.history[e.history.length - 1].pct}%` : ''}</span></a>`;
    const pickList = (list, after) => list.length ? `<div class="ex-list">${list.map(e => examRow(e) + (after && cur && cur.id === e.id ? after : '')).join('')}</div>` : '';
    if (o.goal && (!pick || pick === o.goal.exam) && o.exams.some(e => e.id === o.goal.exam)) return sprintHub(o, pickList);
    cur = o.exams.find(e => e.id === pick) || null;
    // The chosen exam opens right under its own row, inside the card (with eight exams, a block under the list was a
    // scroll away); its name is the row just above, so the block is named for a screen reader only.
    const detail = cur ? `<div class="stack-s exam-cur" id="examCur" role="region" aria-label="${esc(cur.title)}">
        <ul class="steps-list small"><li>词汇 10 题：${esc(cur.book_title)}里的词，选中文意思</li><li>语法 8 题：这个考试常考的语法点</li><li>阅读 2 篇短文，4 题</li></ul>
        ${cur.trend.length ? `<div class="stack-s"><span class="tiny muted">成绩走势</span>${trendHTML(cur.trend)}</div>` : ''}
        <button class="btn primary block" id="exStart">开始一套（约 ${cur.minutes} 分钟）</button>
        ${S.user ? (o.plan && o.plan.book === cur.book ? `<p class="tiny muted">你现在就在用「${esc(cur.book_title)}」背单词（${cur.words} 词）。</p>` :
          `<div class="row"><button class="btn small" id="exBook">改用「${esc(cur.book_title)}」背单词</button><span class="tiny muted">${cur.words} 词，按遗忘曲线每天背</span></div>`) :
          '<p class="tiny muted">登录后成绩会保存，语法错题进错题本，没认出的词可以一键加进单词本。</p>'}
        ${S.user ? `<button class="btn small" type="button" id="exGoal" data-tap="exam-goal">${o.goal ? '改成我的考试' : '设为我的考试'}</button>` : ''}
        ${typesHTML(cur.id, cur.types, o.types_note)}</div>` : '';
    // Signed in without an exam: a white card says what setting it gives, the page's one green button under it (an exam
    // chosen in the list has 开始一套 for that, and 设为我的考试 in its own block)
    const invite = S.user && !o.goal && !cur ? `<section class="ex-mine" aria-labelledby="exMineH"><div class="ex-mine-h"><h2 id="exMineH">我的考试</h2><span>还没设定</span></div>
        <b class="ex-mine-q">在准备哪个考试？</b><p>设好考试和日期，这一页就是你的备考主页：倒计时、每天该背多少词、成绩走势和题型专练。</p></section>
      <button class="btn primary block ex-go" type="button" id="exInvite" data-tap="exam-goal">设定我的考试</button>` : '';
    view.innerHTML = `<div class="ex-page"><h1 class="h1">考试练习</h1>
        <p class="ex-note">${esc(o.note)}</p>
      ${invite}${cur ? '' : '<p class="ex-h">选一个考试开始 · 每套约 12–20 分钟</p>'}
      ${pickList(o.exams, detail)}</div>`;
    drawTrends();
    const inv = document.getElementById('exInvite'); if (inv) inv.onclick = () => examGoalSheet(() => examView());
    if (!cur) return;
    requestAnimationFrame(() => { const d = document.getElementById('examCur'); if (d && d.getBoundingClientRect().bottom > innerHeight) d.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' }); });
    document.getElementById('exStart').onclick = () => examPaper(cur.id);
    const mine = document.getElementById('exGoal');
    if (mine) mine.onclick = async () => {
      try { await api('/api/next/exam/goal', { exam: cur.id, date: '' }); await refreshHome(); toast(`我的考试：${cur.short}。填上日期就能倒计时`); examView(cur.id); }
      catch (e) { toast(e.message); }
    };
    const book = document.getElementById('exBook');
    if (book) book.onclick = async () => {
      const p = o.plan || { daily_new: 10, retention: 0.9 };
      try { await api('/api/next/vocab/plan', { book: cur.book, daily_new: p.daily_new, retention: p.retention }); toast(`已改用「${cur.book_title}」，明天起每天背 ${p.daily_new} 个新词`); examView(pick); }
      catch (e) { toast(e.message); }
    };
  }
  async function examPaper(exam) {
    const p = await api('/api/next/exam/paper', { exam });
    const ans = { vocab: [], grammar: [], reading: [] };
    const started = Date.now();
    let n = 0;
    const q = (key, i, prompt, options, map, sub) => {
      const k = n++;
      return `<div class="q gq" data-key="${key}" data-i="${i}"><div class="prompt">${k + 1}. ${prompt}</div>${sub || ''}
        ${options.map((x, j) => `<button class="ans" data-o="${map ? map[j] : j}"><span class="k">${'ABCD'[j]}</span><span>${esc(x)}</span></button>`).join('')}</div>`;
    };
    const part = pt => {
      if (pt.key === 'vocab') return pt.items.map((x, i) => q('vocab', i, `<b class="en">${esc(x.word)}</b>`, x.options, null, x.phonetic ? `<div class="tiny muted">${esc(x.phonetic)}</div>` : '')).join('');
      if (pt.key === 'grammar') return pt.items.map((x, i) => q('grammar', i, esc(x.prompt), x.options, x.map)).join('');
      let i = 0;
      return pt.passages.map(ps => `<article class="stack-s"><h3 class="h3">${esc(ps.title)} ${aiTag()}</h3><div class="exam-passage">${esc(ps.body)}</div>
        ${ps.items.map(x => q('reading', i++, esc(x.prompt), x.options)).join('')}</article>`).join('');
    };
    const total = p.parts.reduce((s, pt) => s + (pt.items ? pt.items.length : pt.passages.reduce((a, ps) => a + ps.items.length, 0)), 0);
    view.innerHTML = `<div class="stack"><div class="exam-bar"><b>${esc(p.title)} · 练习</b><span class="clock" id="exClock" aria-live="off">0:00</span></div>
      ${p.parts.map(pt => `<section class="exam-part"><h2 class="h2">${esc(pt.title)}</h2><p class="tiny muted">${esc(pt.hint)}</p>${pt.key === 'grammar' ? aiMark('题目和解析由 AI 辅助编写') : ''}${part(pt)}</section>`).join('')}
      <button class="btn primary block" id="exDone">交卷</button><p class="tiny muted">建议 ${p.minutes} 分钟内完成；超时也可以交卷，只是会标出来。</p></div>`;
    const clock = document.getElementById('exClock');
    view.querySelector('.exam-bar').style.top = (bar.offsetHeight + 6) + 'px';  // just under the app's top bar, whatever its height
    const tick = setInterval(() => {
      if (!document.body.contains(clock)) { clearInterval(tick); return; }
      const s = Math.round((Date.now() - started) / 1000); clock.textContent = mmss(s); clock.classList.toggle('late', s > p.minutes * 60);
    }, 1000);
    view.querySelectorAll('.gq').forEach(box => box.querySelectorAll('.ans').forEach(b => b.onclick = () => {
      box.querySelectorAll('.ans').forEach(x => x.classList.toggle('chosen', x === b));
      ans[box.dataset.key][+box.dataset.i] = +b.dataset.o;
    }));
    let warned = false;
    document.getElementById('exDone').onclick = async () => {
      const done = ['vocab', 'grammar', 'reading'].reduce((s, k) => s + ans[k].filter(x => x !== undefined && x !== null).length, 0);
      const btn = document.getElementById('exDone');
      if (done < total && !warned) { warned = true; btn.textContent = `还有 ${total - done} 题没做，再点一次交卷`; return; }
      btn.disabled = true;
      const fill = (a, len) => Array.from({ length: len }, (_, i) => a[i] === undefined ? null : a[i]);
      const lens = { vocab: 0, grammar: 0, reading: 0 };
      p.parts.forEach(pt => { lens[pt.key] = pt.items ? pt.items.length : pt.passages.reduce((a, ps) => a + ps.items.length, 0); });
      try {
        const r = await api('/api/next/exam/submit', { paper: p.paper, seconds: Math.round((Date.now() - started) / 1000),
          answers: { vocab: fill(ans.vocab, lens.vocab), grammar: fill(ans.grammar, lens.grammar), reading: fill(ans.reading, lens.reading) } });
        clearInterval(tick); window.scrollTo(0, 0); examResult(p, r);
      } catch (e) { btn.disabled = false; toast(e.message); }
    };
  }
  function examResult(p, r) {
    const missed = r.vocab.filter(v => !v.correct), gmiss = r.grammar.filter(g => !g.correct);
    const nodes = [...new Map(gmiss.map(g => [g.node, g.node_title])).entries()];
    const late = r.seconds > r.minutes * 60;
    view.innerHTML = `<div class="stack"><div><span class="kicker">${esc(r.title)} · 练习结果</span><h1 class="h1">${r.total} 题做对 ${r.score} 题（${r.pct}%）</h1>
        <p class="muted small">用时 ${mmss(r.seconds)}${late ? `，比建议的 ${r.minutes} 分钟多了 ${mmss(r.seconds - r.minutes * 60)}` : `，在建议的 ${r.minutes} 分钟以内`}。</p></div>
      <div class="exam-score">${r.parts.map(x => `<div><span class="tiny muted">${esc(x.title)}</span><b>${x.right}/${x.of}</b></div>`).join('')}</div>
      ${r.history.length > 1 ? `<div class="stack-s"><span class="tiny muted">成绩走势</span>${trendHTML(r.history.map(x => ({ pct: x.pct, day: new Date(x.created * 1000).toISOString().slice(0, 10),
        parts: Object.fromEntries(x.parts.filter(t => t.of).map(t => [t.key, Math.round(100 * t.right / t.of)])) })))}</div>` : ''}
      ${missed.length ? `<div class="section stack-s"><h2 class="h2">没认出的 ${missed.length} 个词</h2>${aiVoiceNote('读音由 AI 合成')}<div class="plist">${missed.map(v => `<div class="crow">${sayIcon(`data-say="${esc(v.word)}"`, '朗读 ' + v.word)}<span><span class="en">${esc(v.word)}</span><span class="tiny muted">${esc(v.answer)}</span></span></div>`).join('')}</div>
        ${S.user ? '<button class="btn" id="exAdd">全部加进单词本</button>' : ''}</div>` : ''}
      ${nodes.length ? `<div class="section stack-s"><h2 class="h2">要补的语法点</h2><p class="small muted">${r.saved ? '错题已经放进错题本，这些点也排进了每天的计划。' : '登录后错题会进错题本。'}</p>
        <div class="plist">${nodes.map(([id, t]) => `<a class="nrow st st-watch" href="#/graph/${encodeURIComponent(id)}"><i class="dot" aria-hidden="true"></i><span class="t"><b>${esc(t)}</b></span><span></span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div></div>` : ''}
      <details class="section"><summary class="small">看语法和阅读的解析</summary><div class="stack-s">${aiMark('题目和解析由 AI 辅助编写')}
        ${r.grammar.map((g, i) => { const it = p.parts.find(x => x.key === 'grammar').items[i]; const right = it.options[it.map.indexOf(g.answer)];
          return `<div class="pit"><div class="small">${esc(it.prompt)}</div><div class="${g.correct ? 'good' : 'bad'} small">${g.correct ? '✓ 答对' : '✗ 答案'}：${esc(right)}</div><div class="tiny muted">${esc(g.explanation)}</div></div>`; }).join('')}
        ${(() => { const rp = p.parts.find(x => x.key === 'reading'); if (!rp) return ''; const items = rp.passages.flatMap(ps => ps.items);
          return r.reading.map((x, i) => `<div class="pit"><div class="small">${esc(items[i].prompt)}</div><div class="${x.correct ? 'good' : 'bad'} small">${x.correct ? '✓ 答对' : '✗ 答案'}：${esc(items[i].options[x.answer])}</div>${x.evidence ? `<div class="tiny muted">原文依据：${esc(x.evidence)}</div>` : ''}</div>`).join(''); })()}
      </div></details>
      <div class="row"><button class="btn primary" id="exAgain">再来一套</button><a class="btn ghost" href="#/exam/${esc(r.exam)}">回到考试练习</a></div></div>`;
    drawTrends();
    announce(`练习结果：${r.total} 题做对 ${r.score} 题`);
    // a word's own recording, as in the word books; the voice only for a word without one
    view.querySelectorAll('[data-say]').forEach(b => b.onclick = () => {
      const v = missed.find(x => x.word === b.dataset.say);
      if (v && v.audio && (v.audio.us || v.audio.uk)) CLIP.word({ text: v.word, audio: v.audio }); else TTS.word(b.dataset.say);
    });
    const add = document.getElementById('exAdd');
    if (add) add.onclick = async () => {
      add.disabled = true;
      try { const x = await api('/api/next/vocab/add', { items: missed.map(v => ({ word: v.word })) }); add.textContent = x.added ? `已加入 ${x.added} 个词` : '这些词都已经在单词本里了'; }
      catch (e) { add.disabled = false; toast(e.message); }
    };
    document.getElementById('exAgain').onclick = () => examPaper(r.exam);
  }
  /* ---------- 考试冲刺 (r27): my exam and its date, the countdown word plan, the score trend, question-type practice ---------- */
  // The data comes from exam_sprint.py. With an exam set, 考试练习 opens on it (sprintHub): the countdown and whether the
  // word plan keeps up, the trend of the full sets, the question types, the full set; the other exams fold away below.
  const mdDay = iso => { const [, m, d] = String(iso).split('-').map(Number); return `${m}月${d}日`; };
  const num = n => Number(n || 0).toLocaleString();
  const PART_TITLE = { vocab: '词汇', grammar: '语法', reading: '阅读' };
  function examLabel(p) {
    if (!p || !p.exam) return '未设置';
    const short = { zk: '中考', gk: '高考', cet4: '四级', cet6: '六级', ky: '考研', tem4: '专四', tem8: '专八', ielts: '雅思' }[p.exam] || p.exam;
    return `${short} · ${p.exam_date ? mdDay(p.exam_date) : '没填日期'}`;
  }
  // 今日: one line under the plan's title, never a card (the top of 今日 belongs to 看得见的进步).
  function sprintLine(h) {
    const s = h && h.sprint;
    if (!s || s.status === 'past') return '';
    const when = s.days == null ? '填上考试日期 ›' : s.days === 0 ? '今天考试，加油' : `还有 ${s.days} 天`;
    // (no plan yet: the plan's first step already says 选一本词书, so this line does not say it again)
    const pace = s.days ? { on_time: '背词跟得上', behind: '背词跟不上', other_book: '还没背这本考试词书', done: '词书背完了' }[s.status] : '';
    return `<a class="sprint-line small${s.status === 'behind' ? ' behind' : ''}" href="#/exam/${esc(s.exam)}" data-tap="home-sprint"><b>${esc(s.short)}</b><span>${when}</span>${pace ? `<span class="pace">${pace}</span>` : ''}</a>`;
  }

  // ---- the countdown word plan, said plainly ----
  function paceHTML(cd) {
    if (!cd) return '';
    const book = `《${esc(cd.book_title)}》`, btn = (n, label) => `<button class="btn primary small" type="button" data-daily="${n}" data-tap="exam-pace">${label}</button>`;
    const slow = cd.daily && cd.plan_days >= 7 && cd.week_avg < cd.daily * 0.7 ? `<p class="small">最近 7 天平均每天只学了 ${cd.week_avg} 个新词，比计划的 ${cd.daily} 个少：计划的数要每天学完才算数。</p>` : '';
    let head = '', body = '', act = '';
    if (cd.status === 'past') { head = '考试日期已经过了'; body = `<p class="small">${mdDay(cd.date)} 已经过了。下一个考试是什么？改一下考试和日期，倒计时就会重新算。</p>`; act = '<button class="btn small" type="button" data-goal-edit>改考试或日期</button>'; }
    else if (cd.status === 'today') { head = '今天就考试了，加油'; body = '<p class="small">今天不背新词了。看看错题本里最近的错题，放松一点，按平时的节奏去考。</p>'; act = '<a class="btn small" href="#/cards/mistake">看错题本</a>'; }
    else if (cd.status === 'done') { head = '背词节奏：词书背完了 ✓'; body = `<p class="small">${book}的 ${num(cd.size)} 个词都学过了。考前每天把到期的复习做完，记得更牢。</p>`; }
    else if (cd.status === 'no_date') {
      head = '还没填考试日期';
      body = `<p class="small">${book}还有 ${num(cd.left)} 个词没学${cd.daily && cd.finish ? `；按每天 ${cd.daily} 个，${mdDay(cd.finish)} 能学完` : ''}。填上考试日期，就能算出每天该背多少、跟不跟得上。</p>`;
      act = '<button class="btn primary small" type="button" data-goal-edit>填考试日期</button>';
    } else if (cd.status === 'no_plan' || cd.status === 'other_book') {
      head = cd.status === 'no_plan' ? '还没有背词计划' : `还没在背${book}`;
      body = `<p class="small">${cd.status === 'other_book' ? `你现在背的是《${esc(cd.plan_book_title)}》。` : ''}倒计时按${book}算：还有 ${num(cd.left)} 个词没学，要在 ${mdDay(cd.last_new)} 前（考前留 ${cd.review_days} 天复习）学完，每天要 ${cd.need} 个。</p>
        ${cd.too_many ? `<p class="small">每天 ${cd.need} 个太多了，记不住。建议每天 ${cd.suggest} 个，先背最常用的前 ${num(cd.suggest_reach)} 个（词书越靠前的词越常用）。</p>` : ''}`;
      act = btn(cd.suggest, `用${book}背，每天 ${cd.suggest} 个`);
    } else if (cd.status === 'on_time') {
      head = '背词节奏：跟得上 ✓';
      body = `<p class="small">${book}还有 ${num(cd.left)} 个词没学。每天 ${cd.daily} 个，${mdDay(cd.last_new)} 前能学完，考前留 ${cd.review_days} 天只复习。</p>${slow}`;
    } else {
      head = '背词节奏：跟不上';
      body = `<p class="small">${book}还有 ${num(cd.left)} 个词没学。现在每天 ${cd.daily} 个，到 ${mdDay(cd.last_new)}（考前留 ${cd.review_days} 天复习）只能学 ${num(cd.reach)} 个。</p>
        ${cd.too_many ? `<p class="small">全部学完每天要 ${cd.need} 个，太多了：一个月后每天要复习好几百个，记不住。建议每天 ${cd.suggest} 个，先背最常用的前 ${num(cd.suggest_reach)} 个（词书越靠前的词越常用）。</p>`
          : `<p class="small">要按时学完，每天需要 ${cd.need} 个。</p>`}${slow}`;
      act = btn(cd.suggest, `改成每天 ${cd.suggest} 个`);
    }
    return `<section class="card flat sp-pace st-${cd.status}" aria-labelledby="spPaceH"><h2 class="h3" id="spPaceH">${head}</h2>${body}${act ? `<div class="row">${act}</div>` : ''}</section>`;
  }
  function bindPace(cd, redraw) {
    view.querySelectorAll('[data-goal-edit]').forEach(b => b.onclick = () => examGoalSheet(redraw));
    view.querySelectorAll('[data-daily]').forEach(b => b.onclick = async () => {
      const n = Number(b.dataset.daily); b.disabled = true;
      try {
        await api('/api/next/vocab/plan', { book: cd.book, daily_new: n, retention: cd.retention || 0.9 });
        await refreshHome(); toast(`已改成《${cd.book_title}》每天 ${n} 个新词`); redraw();
      } catch (e) { b.disabled = false; toast(e.message); }
    });
  }

  // ---- 成绩走势: the total as one line, then 词汇 / 语法 / 阅读 as three small lines side by side ----
  function trendHTML(tr) {
    if (!tr || !tr.length) return '<p class="small muted">还没做过完整的一套。做完第一套，这里会出现分数；做满两套就能看出走势。</p>';
    const parts = ['vocab', 'grammar', 'reading'].filter(k => tr.some(t => t.parts && t.parts[k] != null));
    const first = tr[0], last = tr[tr.length - 1];
    if (tr.length === 1) return `<p class="small">第一套：总分 ${first.pct}%（${parts.map(k => `${PART_TITLE[k]} ${first.parts[k]}%`).join(' · ')}）。再做一套就能看出走势。</p>`;
    const line = (vals, kind, label) => `<div class="trend-chart ${kind}" data-v="${vals.join(',')}" role="img" aria-label="${esc(label)}"></div>`;
    const ofPart = k => tr.map(t => t.parts[k]).filter(v => v != null);
    return `<div class="trend"><div class="trend-head"><span class="small">总分</span><b>${first.pct}% → ${last.pct}%</b></div>
      ${line(tr.map(t => t.pct), 'big', `总分：第一套 ${first.pct}%，最近一套 ${last.pct}%，共 ${tr.length} 套`)}
      <div class="trend-parts">${parts.map(k => { const v = ofPart(k);
        return `<div class="tp"><span class="tiny muted">${PART_TITLE[k]}</span><b class="small">${v[0]} → ${v[v.length - 1]}</b>${line(v, 'small', `${PART_TITLE[k]}：从 ${v[0]}% 到 ${v[v.length - 1]}%`)}</div>`; }).join('')}</div>
      <p class="tiny muted">${tr.length} 套，从 ${mdDay(first.day)} 到 ${mdDay(last.day)}。分数只用来看自己的变化，不能换算成考试分数。</p></div>`;
  }
  // Drawn at the width the box really has (the page is laid out first), so dots stay round and lines stay thin.
  function drawTrends(root) {
    (root || view).querySelectorAll('.trend-chart').forEach(box => {
      const v = box.dataset.v.split(',').map(Number), big = box.classList.contains('big');
      const W = Math.max(60, Math.round(box.clientWidth)), H = big ? 112 : 40, L = big ? 34 : 4, R = 8, T = 8, B = big ? 10 : 6;
      const x = i => L + (v.length > 1 ? i * (W - L - R) / (v.length - 1) : (W - L - R) / 2), y = p => T + (1 - p / 100) * (H - T - B);
      const grid = big ? [0, 50, 100].map(p => `<line class="g" x1="${L}" x2="${W - R}" y1="${y(p)}" y2="${y(p)}"/><text x="${L - 6}" y="${y(p) + 4}" text-anchor="end">${p}%</text>`).join('') : '';
      const pts = v.map((p, i) => `${x(i).toFixed(1)},${y(p).toFixed(1)}`).join(' ');
      const dots = v.map((p, i) => `<circle class="${i === v.length - 1 ? 'last' : ''}" cx="${x(i).toFixed(1)}" cy="${y(p).toFixed(1)}" r="${big ? (i === v.length - 1 ? 5 : 3.5) : (i === v.length - 1 ? 3.5 : 2.2)}"/>`).join('');
      box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true" focusable="false">${grid}<polyline points="${pts}"/>${dots}</svg>`;
    });
  }
  let trendTimer = 0;
  addEventListener('resize', () => { clearTimeout(trendTimer); trendTimer = setTimeout(() => { if (view.querySelector('.trend-chart')) drawTrends(); }, 150); });

  // ---- 题型专练: the list on an exam ----
  function typesHTML(exam, types, note) {
    if (!types || !types.length) return '';
    return `<section class="section stack-s" aria-labelledby="spTypesH"><h2 class="h2" id="spTypesH">题型专练</h2><p class="tiny muted">${esc(note)}</p>
      <div class="mlist">${types.map(t => `<a class="mrow" href="#/exam/${esc(exam)}/${esc(t.id)}" data-tap="exam-type"><span class="t"><b>${esc(t.title)}</b>
        <span class="tiny muted">${t.items} 题，分 ${t.sets} 组${t.last ? ` · 上次 ${t.last.right}/${t.last.of}` : ' · 还没做'}</span></span><span class="go" aria-hidden="true">›</span></a>`).join('')}
        <a class="mrow" href="#/exam/${esc(exam)}/reading" data-tap="exam-reading"><span class="t"><b>阅读一篇</b><span class="tiny muted">这个考试难度的一篇原创短文，4 题；今日计划里的「考试小练」也会排到它</span></span><span class="go" aria-hidden="true">›</span></a></div></section>`;
  }

  // ---- the hub: 考试练习 when an exam is set ----
  function sprintHub(o, pickList) {
    const g = o.goal, cd = o.countdown, cur = o.exams.find(e => e.id === g.exam);
    const others = o.exams.filter(e => e.id !== g.exam);
    const when = !g.date ? '还没填考试日期' : cd && cd.days > 0 ? `${mdDay(g.date)} · 还有 ${cd.days} 天` : cd && cd.days === 0 ? `${mdDay(g.date)} · 就是今天` : `${mdDay(g.date)} · 已经过了`;
    view.innerHTML = `<div class="stack sprint"><div><span class="kicker">考试练习 · 我的考试</span><h1 class="h1">${esc(cur.title)}</h1>
        <p class="sp-when"><span class="small">${when}</span><button class="link small" type="button" data-goal-edit data-tap="exam-goal">改考试或日期</button></p></div>
      ${paceHTML(cd)}
      <section class="section stack-s" aria-labelledby="spTrendH"><h2 class="h2" id="spTrendH">成绩走势${cur.trend.length > 1 ? `<span class="tiny muted">（最近 ${cur.trend.length} 套）</span>` : ''}</h2>${trendHTML(cur.trend)}</section>
      ${typesHTML(cur.id, cur.types, o.types_note)}
      <section class="section stack-s" aria-labelledby="spFullH"><h2 class="h2" id="spFullH">完整一套</h2>
        <p class="small muted">词汇 10 题（${esc(cur.book_title)}）· 语法 8 题 · 阅读 2 篇 4 题，计时做完再看解析。${cd && cd.sprint ? '考前这几周，今日的计划里每周排一套。' : ''}</p>
        <button class="btn primary block" id="exStart">开始一套（约 ${cur.minutes} 分钟）</button><p class="tiny muted">${esc(o.note)}</p></section>
      ${others.length ? `<details class="section sp-others"><summary class="small">其他考试（${others.length} 个）</summary>${pickList(others)}</details>` : ''}</div>`;
    drawTrends();
    bindPace(cd, () => examView(g.exam));
    document.getElementById('exStart').onclick = () => examPaper(cur.id);
  }

  // ---- 我的考试: which exam and when (我的, 考试练习; 背词计划 sets it with its chips) ----
  async function examGoalSheet(onSaved) {
    const o = await api('/api/next/exam/goal');
    let exam = o.goal ? o.goal.exam : '';
    const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">我的考试</h2>
      <p class="muted small">设好考试和日期，「考试练习」会变成你的备考主页：倒计时、每天该背多少词、成绩走势和题型专练；考前最后四周，今日的计划会加上每周一套和这个考试的语法点。</p>
      <div class="chips" role="radiogroup" aria-label="在准备哪个考试">${[{ id: '', short: '不考试' }, ...o.exams].map(e => `<button class="chip" type="button" role="radio" data-exam="${e.id}" aria-checked="${e.id === exam}">${esc(e.short)}</button>`).join('')}</div>
      <div class="stack-s" id="egDate"><label class="small" for="egIn">考试日期（选填，不确定可以先空着）</label>
        <input type="date" id="egIn" min="${today}" value="${esc(o.goal && o.goal.date || '')}"></div>
      <p class="err" id="egErr" role="alert"></p>
      <div class="row"><button class="btn primary" type="button" id="egSave">保存</button><button class="btn ghost" type="button" data-close>取消</button></div></div>`, card => {
      const date = card.querySelector('#egDate'), sync = () => { date.hidden = !exam; };
      card.querySelectorAll('[data-exam]').forEach(b => b.onclick = () => { exam = b.dataset.exam; card.querySelectorAll('[data-exam]').forEach(x => x.setAttribute('aria-checked', String(x === b))); sync(); });
      sync();
      card.querySelector('#egSave').onclick = async e => {
        e.currentTarget.disabled = true;
        try {
          const r = await api('/api/next/exam/goal', { exam, date: exam ? card.querySelector('#egIn').value : '' });
          closeSheet(); await refreshHome();
          toast(r.goal ? `我的考试：${r.goal.short}${r.goal.date ? ' · ' + mdDay(r.goal.date) : ''}` : '已改成不考试');
          if (onSaved) onSaved();
        } catch (x) { e.currentTarget.disabled = false; card.querySelector('#egErr').textContent = x.message; }
      };
    });
  }

  // ---- 背词计划: the date under the exam chips, and how many words a day the date asks for ----
  function planExamRow(p) {
    const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    return `<div class="stack-s plan-exam" id="pxRow" hidden><label class="small" for="pxDate">考试日期（选填）</label>
      <input type="date" id="pxDate" min="${today}" value="${esc(p && p.exam_date || '')}"><span class="tiny muted" id="pxHint" aria-live="polite"></span></div>`;
  }
  function planExamHint(exam, date, b, chosen, daily, done) {
    if (!exam) return '';
    if (!date) return '填上日期，就能算出每天要背多少个新词才来得及。';
    const days = Math.round((new Date(date + 'T00:00:00') - new Date(new Date().toDateString())) / 864e5);
    if (days <= 0) return days === 0 ? '今天就考试了。' : '这个日期已经过了。';
    if (chosen !== exam) return `离考试还有 ${days} 天。倒计时按这个考试的词书算，你现在选的是另一本。`;
    const left = Math.max(0, (b.size || 0) - (b.skippable || 0) - done), study = Math.max(1, days - Math.min(7, Math.floor(days / 3))), need = Math.ceil(left / study);
    if (!left) return `离考试还有 ${days} 天，这本词书都学过了。`;
    return `离考试还有 ${days} 天，最后 ${days - study} 天留着复习，前 ${study} 天要学完剩下的 ${num(left)} 个词：每天需要 ${need} 个新词` +
      (daily >= need ? '，现在选的够了。' : need > 40 ? `。太多了，记不住：建议每天 40 个，先背最常用的前 ${num(40 * study)} 个。` : `；现在选的每天 ${daily} 个跟不上。`);
  }

  // ---- one question type: a set of original items, handed in once, then every answer with its reason ----
  const LETTERS = 'ABCDEFGHIJKLMNO', ROMAN = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x', 'xi', 'xii'], TFNG = ['TRUE', 'FALSE', 'NOT GIVEN'];
  const tapWords = line => line.split(/\s+/).filter(Boolean);
  async function examTypeView(exam, tid, setId) {
    const r = await api(`/api/next/exam/type?exam=${encodeURIComponent(exam)}&type=${encodeURIComponent(tid)}${setId ? '&set=' + encodeURIComponent(setId) : ''}`);
    const s = r.set, k = s.kind, n = s.items.length, ans = Array(n).fill(null);
    const label = (i, a) => a == null ? '' : k === 'bank' ? `${LETTERS[a]}. ${s.bank[a]}` : k === 'headings' ? `${ROMAN[a]}. ${s.bank[a]}` : k === 'match' ? `${LETTERS[a]} 段`
      : k === 'tfng' ? TFNG[a] : k === 'proof' ? a : s.items[i].options[a];
    const gapText = t => esc(t).replace(/\{(\d+)\}/g, (_, d) => k === 'bank' ? `<button class="gap" type="button" data-gap="${d - 1}" aria-label="第 ${d} 空，点这里选">(${d}) <span class="gv">＿＿＿</span></button>`
      : `<span class="gap ro" data-gap="${d - 1}">(${d}) <span class="gv">＿＿＿</span></span>`);
    const opts = (i, list, fmt) => `<div class="xt-opts">${list.map((x, j) => `<button class="ans" type="button" data-i="${i}" data-o="${j}"><span class="k">${fmt ? fmt(j) : LETTERS[j]}</span><span>${esc(x)}</span></button>`).join('')}</div>`;
    let body = '';
    if (k === 'cloze') body = `<div class="exam-passage xt-text">${gapText(s.text)}</div><div class="stack-s">${s.items.map((it, i) => `<div class="q gq xt-q" data-q="${i}"><div class="prompt">第 ${i + 1} 空</div>${opts(i, it.options)}</div>`).join('')}</div>`;
    if (k === 'bank') body = `<div class="xt-bank card sunk"><b class="small">选项（每个只用一次）</b><ol class="xt-banklist${s.bank.every(x => x.length <= 16) ? ' words' : ''}">${s.bank.map((x, j) => `<li data-b="${j}"><span class="k">${LETTERS[j]}</span><span>${esc(x)}</span></li>`).join('')}</ol></div>
      <div class="exam-passage xt-text${s.bank.some(x => x.length > 30) ? ' long' : ''}">${gapText(s.text)}</div>`;
    if (k === 'headings') body = `<div class="xt-bank card sunk"><b class="small">标题（每个只用一次，有几个用不上）</b><ol class="xt-banklist">${s.bank.map((x, j) => `<li data-b="${j}"><span class="k">${ROMAN[j]}</span><span>${esc(x)}</span></li>`).join('')}</ol></div>
      ${s.paras.map((p, i) => `<div class="xt-para"><div class="row"><b>${LETTERS[i]}</b><button class="gap" type="button" data-gap="${i}" aria-label="${LETTERS[i]} 段的标题，点这里选"><span class="gv">选标题</span></button></div><p class="exam-passage">${esc(p)}</p></div>`).join('')}`;
    if (k === 'match') body = `${s.paras.map((p, i) => `<p class="exam-passage xt-para"><b>${LETTERS[i]}</b> ${esc(p)}</p>`).join('')}
      <div class="stack-s">${s.items.map((it, i) => `<div class="q gq xt-q" data-q="${i}"><div class="prompt">${i + 1}. ${esc(it.prompt)}</div><div class="xt-letters">${s.paras.map((_, j) => `<button class="ans" type="button" data-i="${i}" data-o="${j}" aria-label="${LETTERS[j]} 段">${LETTERS[j]}</button>`).join('')}</div></div>`).join('')}</div>`;
    if (k === 'tfng') body = `<div class="exam-passage xt-text">${esc(s.text)}</div><div class="stack-s">${s.items.map((it, i) => `<div class="q gq xt-q" data-q="${i}"><div class="prompt">${i + 1}. ${esc(it.prompt)}</div><div class="xt-tf">${TFNG.map((x, j) => `<button class="ans" type="button" data-i="${i}" data-o="${j}">${x}</button>`).join('')}</div></div>`).join('')}</div>`;
    if (k === 'choice') body = `<div class="stack-s">${s.items.map((it, i) => `<div class="q gq xt-q" data-q="${i}"><div class="prompt">${i + 1}. ${esc(it.prompt)}</div>${opts(i, it.options)}</div>`).join('')}</div>`;
    // 阅读一篇 (考试小练, r28): a passage at the exam's level, then its questions
    if (k === 'reading') body = `<div class="exam-passage xt-text" lang="en">${esc(s.text)}</div><div class="stack-s">${s.items.map((it, i) => `<div class="q gq xt-q" data-q="${i}"><div class="prompt" lang="en">${i + 1}. ${esc(it.prompt)}</div>${opts(i, it.options)}</div>`).join('')}</div>`;
    if (k === 'proof') body = `<div class="stack-s">${s.lines.map((line, i) => `<div class="q gq xt-q xt-line" data-q="${i}"><div class="tiny muted">第 ${i + 1} 行</div><div class="xt-words">${tapWords(line).map((w, j) => `<button class="xw" type="button" data-i="${i}" data-w="${j}" aria-pressed="false">${esc(w)}</button>`).join('')}</div></div>`).join('')}</div>`;
    view.innerHTML = `<div class="stack xt"><div><span class="kicker">${esc(r.exam_title)} · ${k === 'reading' ? '考试小练' : '题型专练'}</span><h1 class="h1">${esc(r.title)}</h1>
        <p class="small">${esc(r.how)}</p><p class="tiny muted">${esc(r.note)}</p></div>
      ${k === 'reading' ? '' : aiMark('题目和解析由 AI 辅助编写')}
      <div class="row between"><span class="tiny muted">${[r.of > 1 ? `第 ${r.index} 组，共 ${r.of} 组` : '', s.title ? `<span lang="en">${esc(s.title)}</span>${k === 'reading' ? ' ' + aiTag() : ''}` : ''].filter(Boolean).join(' · ')}</span><span class="tiny muted" id="xtLeft">还有 ${n} 题</span></div>
      ${body}
      <button class="btn primary block" id="xtDone" type="button">交卷</button>
      <a class="link small" href="#/exam/${esc(exam)}">回到考试练习</a></div>`;
    const left = () => { const m = ans.filter(a => a == null).length; document.getElementById('xtLeft').textContent = m ? `还有 ${m} 题` : '都做完了'; };
    const fillGap = i => { const g = view.querySelector(`[data-gap="${i}"] .gv`); if (g) g.textContent = ans[i] == null ? (k === 'headings' ? '选标题' : '＿＿＿') : label(i, ans[i]); };
    view.querySelectorAll('.ans').forEach(b => b.onclick = () => {
      const i = +b.dataset.i; ans[i] = +b.dataset.o;
      view.querySelectorAll(`.ans[data-i="${i}"]`).forEach(x => x.classList.toggle('chosen', x === b));
      if (k === 'cloze') fillGap(i);
      left();
    });
    view.querySelectorAll('.xw').forEach(b => b.onclick = () => {
      const i = +b.dataset.i, on = !b.classList.contains('chosen');
      view.querySelectorAll(`.xw[data-i="${i}"]`).forEach(x => { x.classList.toggle('chosen', on && x === b); x.setAttribute('aria-pressed', String(on && x === b)); });
      ans[i] = on ? b.textContent : null; left();
    });
    // 选词填空、七选五、段落标题: tap a gap, pick from the options in a sheet (one already used shows where)
    const used = () => { view.querySelectorAll('.xt-banklist li').forEach(li => li.classList.toggle('used', ans.includes(+li.dataset.b))); };
    view.querySelectorAll('button.gap').forEach(g => g.onclick = () => {
      const i = +g.dataset.gap, fmt = j => k === 'headings' ? ROMAN[j] : LETTERS[j];
      openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">${k === 'headings' ? `${LETTERS[i]} 段的标题` : `第 ${i + 1} 空`}</h2>
        <div class="stack-s xt-pick">${s.bank.map((x, j) => { const at = ans.indexOf(j);
          return `<button class="ans${ans[i] === j ? ' chosen' : ''}" type="button" data-pick="${j}"><span class="k">${fmt(j)}</span><span>${esc(x)}${at >= 0 && at !== i ? `<span class="tiny muted">（已用在${k === 'headings' ? ` ${LETTERS[at]} 段` : `第 ${at + 1} 空`}）</span>` : ''}</span></button>`; }).join('')}</div>
        <div class="row">${ans[i] != null ? '<button class="btn ghost" type="button" id="xtClear">清空这一空</button>' : ''}<button class="btn ghost" type="button" data-close>取消</button></div></div>`, card => {
        card.querySelectorAll('[data-pick]').forEach(b => b.onclick = () => {
          const j = +b.dataset.pick, was = ans.indexOf(j);
          if (was >= 0 && was !== i) { ans[was] = null; fillGap(was); }  // one option, one gap: it moves here
          ans[i] = j; fillGap(i); used(); left(); closeSheet();
          const nextGap = view.querySelector(`button.gap[data-gap="${i + 1}"]`); if (nextGap && ans[i + 1] == null) nextGap.focus({ preventScroll: true });
        });
        const cl = card.querySelector('#xtClear'); if (cl) cl.onclick = () => { ans[i] = null; fillGap(i); used(); left(); closeSheet(); };
      });
    });
    let warned = false;
    document.getElementById('xtDone').onclick = async e => {
      const btn = e.currentTarget, m = ans.filter(a => a == null).length;
      if (m && !warned) { warned = true; btn.textContent = `还有 ${m} 题没做，再点一次交卷`; return; }
      btn.disabled = true;
      let out;
      try { out = await api('/api/next/exam/type', { exam, type: tid, set: s.id, answers: ans }); }
      catch (x) { btn.disabled = false; toast(x.message); return; }
      window.scrollTo(0, 0); typeResult(r, ans, out, label);
    };
  }
  function typeResult(r, ans, out, label) {
    const s = r.set, k = s.kind;
    const what = i => k === 'cloze' || k === 'bank' ? `第 ${i + 1} 空` : k === 'headings' ? `${LETTERS[i]} 段` : k === 'proof' ? `第 ${i + 1} 行` : `${i + 1}. ${s.items[i].prompt}`;
    const right = (it, i) => k === 'proof' ? `${it.wrong} → ${it.fix || '删去'}` : label(i, it.answer);
    const text = k === 'match' || k === 'headings' ? s.paras.map((p, i) => `${LETTERS[i]}  ${p}`).join('\n\n') : k === 'proof' ? s.lines.join('\n')
      : s.text ? s.text.replace(/\{(\d+)\}/g, (_, d) => `(${d}) ${label(d - 1, out.items[d - 1].answer)}`) : '';  // 单选题 have no passage
    view.innerHTML = `<div class="stack xt"><div><span class="kicker">${esc(r.exam_title)} · ${esc(r.title)}</span><h1 class="h1">${out.of} 题做对 ${out.right} 题</h1>
        <p class="small muted">${out.saved ? '结果已记下，题型列表会显示上次的成绩。' : '登录后会记下每次的成绩。'}每题都写了答案在原文里的依据。</p></div>
      <div class="stack-s">${out.items.map((it, i) => `<div class="pit"><div class="small">${esc(what(i))}</div>
        <div class="${it.correct ? 'ok' : 'no'} small">${it.correct ? '✓ 答对' : '✗ 答错了，答案是'}：${esc(right(it, i))}${!it.correct && ans[i] != null ? `<span class="tiny muted">（你选的：${esc(k === 'proof' ? ans[i] : label(i, ans[i]))}）</span>` : ''}</div>
        <div class="tiny muted">${esc(it.why)}</div></div>`).join('')}</div>
      ${text ? `<details class="section"><summary class="small">看原文${k === 'cloze' || k === 'bank' ? '（空里填的是答案）' : ''}</summary><div class="exam-passage xt-text">${esc(text)}</div></details>` : ''}
      <div class="row"><button class="btn primary" id="xtNext" type="button">${k === 'reading' ? '再读一篇' : '再做一组'}</button><a class="btn ghost" href="#/exam/${esc(r.exam)}">回到考试练习</a></div></div>`;
    announce(`${out.of} 题做对 ${out.right} 题`);
    document.getElementById('xtNext').onclick = () => { window.scrollTo(0, 0); examTypeView(r.exam, r.type, out.next); };
  }
  /* ---------- mixed grammar rounds: several points interleaved (today's review, a confusable pair, a whole topic) ---------- */
  // Questions on different points mixed together make the learner decide which rule applies first: that decision is
  // what real use asks for, and it is what one-point-at-a-time practice never trains.
  async function mixView(kind, arg) {
    const q = kind === 'pair' ? '?pair=' + encodeURIComponent(arg) : kind === 'topic' ? '?topic=' + encodeURIComponent(arg) : kind === 'exam' ? '?exam=' + encodeURIComponent(arg) : kind === 'more' ? '?n=4' : guestQuery(true);  // more: 4 questions once 今日's plan is done (r28)
    const m = await api('/api/next/mix' + q);
    const TITLE = { due: '今天的语法复习', practice: '语法混合练习', pair: '辨析练习', topic: '这一类混着练', exam: '考点语法' };
    const intro = m.kind === 'due' ? `${m.nodes.length} 个点混在一起出题：先想清楚这题考的是哪条规则，再选。${m.left ? `还有 ${m.left} 个点明天接着练。` : ''}`
      : m.kind === 'pair' ? '两个容易混的点交替出题，做的时候先判断是哪一个。'
      : m.kind === 'practice' ? '今天没有到期要复习的点。先混着练几个你这个级别的，做对的会点亮。'
      : m.kind === 'exam' ? '这个考试常考的语法点混在一起出题，要你标出来的和到期该复习的排在前面。' : '这一类里的每个点各出一题。';
    const items = m.items, before = Object.fromEntries(m.nodes.map(n => [n.id, n.status])), after = {}, per = {};
    let i = 0, right = 0, streak = 0;
    view.innerHTML = `<div class="stack mix"><div><span class="kicker">${esc(TITLE[m.kind])}</span><h1 class="h1">${m.kind === 'pair' ? esc(m.nodes.map(n => n.title).join(' vs ')) : `${items.length} 道题，${m.nodes.length} 个点`}</h1>
        <p class="muted small">${esc(intro)}</p>${aiMark('题目和讲解由 AI 辅助编写')}</div>
      ${m.note ? `<div class="howto"><b>怎么区分</b><span class="small">${esc(m.note)}</span></div>` : ''}
      <div class="mix-dots" aria-hidden="true">${items.map(() => '<i></i>').join('')}</div>
      <div id="mixQ"></div></div>`;
    const dots = [...view.querySelectorAll('.mix-dots i')];
    function ask() {
      // answering, on a phone: no tabs, like review (80-flat.css body.reviewing), so the question and its four answers fit
      // one screen on the smallest iPhone (UI audit 2026-11-25: 17–133 px past it); route() takes the class off again
      document.body.classList.add('reviewing');
      const it = items[i], box = document.getElementById('mixQ');
      dots.forEach((d, k) => d.classList.toggle('now', k === i));
      box.innerHTML = `<div class="q gq enter"><div class="tiny muted">第 ${i + 1} / ${items.length} 题</div><div class="prompt">${esc(it.prompt)}</div>
        ${it.options.map((o, j) => `<button class="ans" data-o="${it.map[j]}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}<div class="fb" aria-live="polite"></div></div>`;
      box.querySelectorAll('.ans').forEach(b => b.onclick = () => answer(it, b, box));
      keys4(box);
    }
    function keys4(box) {
      document.onkeydown = e => { const k = Number(e.key); if (k >= 1 && k <= 4 && !e.metaKey && !e.ctrlKey) { const b = box.querySelectorAll('.ans')[k - 1]; if (b && !b.disabled) b.click(); } };
    }
    async function answer(it, b, box) {
      box.querySelectorAll('.ans').forEach(x => { x.disabled = true; });
      let r;
      try { r = await api('/api/next/node/answer', { question: it.id, choice: Number(b.dataset.o), from: m.kind === 'exam' ? 'exam' : 'mix' }); }
      catch (e) { toast(e.message); box.querySelectorAll('.ans').forEach(x => { x.disabled = false; }); return; }
      box.querySelectorAll('.ans').forEach(x => { if (Number(x.dataset.o) === r.answer) x.classList.add('right'); });
      if (!r.correct) b.classList.add('wrong');
      const p = per[it.node] = per[it.node] || { right: 0, of: 0 }; p.of++;
      if (r.correct) { right++; p.right++; streak++; } else streak = 0;
      if (r.status) after[it.node] = { status: r.status, label: r.label };
      dots[i].classList.add(r.correct ? 'ok' : 'no');
      box.querySelector('.fb').innerHTML = `<div class="${r.correct ? 'ok' : 'bad'}">${r.correct ? '✓ 对了' : '✗ 这题选错了'}${streak >= 3 ? ` · 连对 ${streak} 题` : ''}</div>
        <div class="small">${esc(r.explanation || '')}</div><div class="tiny muted">考的是：<a class="link" href="#/graph/${encodeURIComponent(it.node)}">${esc(it.node_title)}</a></div>
        <button class="btn primary block" id="mixNext">${i + 1 < items.length ? '下一题' : '看结果'}</button>`;
      announce(r.correct ? '答对了' : '答错了');
      const nx = document.getElementById('mixNext');
      nx.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' });  // the explanation and the next button, above the tab bar
      nx.onclick = () => { i++; if (i < items.length) ask(); else done(); };
      document.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); nx.click(); } };
      nx.focus({ preventScroll: true });
    }
    function done() {
      document.onkeydown = null; document.body.classList.remove('reviewing');
      const all = right === items.length, rows = m.nodes.filter(n => per[n.id]);
      const lit = rows.filter(n => before[n.id] !== 'solid' && (after[n.id] || {}).status === 'solid');
      const msg = all ? `全对！${S.user ? '这几个点都往后推了，到时间再抽查。' : ''}`
        : `${items.length - right} 题没做对。${S.user ? '它们明天会换一道题再来——错题是最值钱的题，弄懂一个就少一个。' : ''}`;
      view.innerHTML = `<div class="stack mix-done">${right * 2 >= items.length ? `<div class="done-burst${all ? ' all' : ''}" aria-hidden="true">${doneRing}</div>` : ''}
        <div class="tc"><span class="kicker">${esc(TITLE[m.kind])}</span><h1 class="h1">${items.length} 题做对 ${right} 题</h1><p class="small">${esc(msg)}</p>
        ${lit.length ? `<p class="small cheer">新点亮了 ${lit.length} 个点：${esc(lit.map(n => n.title).join('、'))}</p>` : ''}</div>
        <div class="plist">${rows.map((n, k) => { const a = after[n.id] || n, pr = per[n.id];
          return `<a class="nrow st st-${a.status} pop-in" data-k="${k}" href="#/graph/${encodeURIComponent(n.id)}"><i class="dot" aria-hidden="true"></i><span class="t"><b>${esc(n.title)}</b><span class="tiny muted">${esc(a.label || '')}</span></span><span class="lv">${pr.right}/${pr.of}</span><span class="go" aria-hidden="true">›</span></a>`; }).join('')}</div>
        ${S.user ? '' : '<p class="muted small">登录后，做对的点会点亮在你的语法地图里，错的会按遗忘曲线回来。</p>'}
        <div class="row center"><a class="btn" href="#/graph">语法地图</a>${m.kind === 'due' || m.kind === 'exam' ? '<a class="btn primary" href="#/">回到今日</a>' : '<button class="btn primary" id="mixAgain">再来一轮</button>'}</div></div>`;
      view.querySelectorAll('.pop-in').forEach(el => el.style.setProperty('--d', (Number(el.dataset.k) * 90 + 200) + 'ms'));
      const again = document.getElementById('mixAgain'); if (again) again.onclick = () => mixView(kind, arg);
      announce(`${items.length} 题做对 ${right} 题`);
      if (S.user) refreshHome().catch(() => {});
    }
    if (!items.length) {
      document.getElementById('mixQ').innerHTML = '<div class="empty"><p>这里暂时没有题。</p><a class="btn" href="#/graph">回到语法地图</a></div>';
      return;
    }
    ask();
  }
  /* ---------- easy reading: a lot of easy text, read fast, no tasks ---------- */
  async function easyView() {
    const d = await api('/api/next/easy' + guestQuery(true)), st = d.stats;
    view.innerHTML = `<div class="stack"><div><h1 class="h1">轻松读</h1>
        <p class="muted small">读得多，比读得难更重要。${esc(d.note)}</p></div>
      ${st ? `<div class="easy-stats"><div><b>${st.week_words.toLocaleString()}</b><span class="tiny muted">这周读了（词）</span></div>
        <div><b>${st.avg_wpm || '—'}</b><span class="tiny muted">阅读速度（词/分钟）</span></div><div><b>${st.reads}</b><span class="tiny muted">一共读了（篇）</span></div></div>
        ${st.first_wpm && st.avg_wpm > st.first_wpm ? `<p class="small cheer">比刚开始快了 ${st.avg_wpm - st.first_wpm} 词/分钟。</p>` : ''}` : '<p class="muted small">登录后会记下你读了多少、读得多快。</p>'}
      <div class="section stack-s"><div class="row between"><h2 class="h2">今天可以读</h2><span class="pill">${esc(d.target)}</span></div>
        <div class="grid-list">${d.items.map(m => `<a class="card flat mini" href="#/easy/${encodeURIComponent(m.id)}"><span class="t">${esc(m.title)}</span>
          ${m.level !== d.target ? `<span class="meta"><span class="pill">${m.level}</span></span>` : ''}<span class="p">${esc(m.preview_en)}</span><span class="tiny muted">${m.words} 词 · 约 ${Math.max(1, Math.round(m.words / 120))} 分钟${m.ai ? ' ' + aiTag() : ''}</span></a>`).join('') || '<div class="empty"><p>这个难度的材料都读过了，明天会有新的。</p></div>'}</div></div>
      <p class="tiny muted">怎么读：不查词也能猜个大概就继续往下读；实在影响理解再点词。读完选一下难不难就行。</p></div>`;
  }
  async function easyRead(id) {
    const m = await api('/api/next/material?id=' + encodeURIComponent(id) + guestQuery(false));
    const ls = m.sentences, t0 = Date.now();
    let looked = 0;
    view.innerHTML = `<div><a class="link small" href="#/easy">← 轻松读</a></div>
      <div class="study-head"><span class="kicker">轻松读 · ${esc(m.level)} · ${ls.join(' ').split(/\s+/).length} 词</span><h1 class="h1">${esc(m.title_en || m.title)}</h1>
        ${m.title_en ? `<div class="muted small">${esc(m.title)}</div>` : ''}${aiNote(m) === null ? '' : aiMark(aiNote(m))}</div>
      <div class="reader easy-reader" id="easyText" lang="en">${ls.map((s, k) => `<span class="s">${wordSpans(s, () => 'w', ` data-s="${k}"`)}</span> `).join('')}</div>
      <div class="section stack-s" id="easyEnd"><div class="kicker">读完了，觉得怎么样？</div>
        <div class="choice three">${[['easy', '太简单'], ['ok', '刚好'], ['hard', '有点难']].map(([v, l]) => `<button class="opt" data-r="${v}"><span class="l">${l}</span></button>`).join('')}</div>
        <span class="tiny muted">选“太简单”，下一篇会难一点；选“有点难”，会简单一点。</span></div>`;
    document.getElementById('easyText').onclick = e => {
      const w = e.target.closest('.w'); if (!w || String(getSelection()).trim()) return;
      looked++; lookupSheet(w.dataset.w, ls[Number(w.dataset.s)], id, false);
    };
    view.querySelectorAll('[data-r]').forEach(b => b.onclick = async () => {
      view.querySelectorAll('[data-r]').forEach(x => { x.disabled = true; x.setAttribute('aria-pressed', String(x === b)); });
      const seconds = Math.max(5, Math.round((Date.now() - t0) / 1000));
      let r; try { r = await api('/api/next/easy/done', { pack: id, seconds, rating: b.dataset.r }); }
      catch (e) { toast(e.message); view.querySelectorAll('[data-r]').forEach(x => { x.disabled = false; }); return; }
      const st = r.stats;
      document.getElementById('easyEnd').insertAdjacentHTML('beforeend', `<div class="easy-done pop-in"><div class="easy-stats"><div><b>${r.words}</b><span class="tiny muted">读了（词）</span></div>
          <div><b>${r.wpm || '—'}</b><span class="tiny muted">词/分钟</span></div><div><b>${looked}</b><span class="tiny muted">查了（次）</span></div></div>
        <p class="small cheer">${st ? `这周已经读了 ${st.week_words.toLocaleString()} 词。` : ''}${looked <= 3 ? '几乎没查词就读完了，这正是轻松读要的感觉。' : '这篇查得有点多：觉得吃力的话，选“有点难”，下一篇就会简单一点。'}</p>
        <div class="row"><a class="btn primary" href="#/easy">再读一篇</a><a class="btn ghost" href="#/">回到今日</a></div></div>`);
      if (S.user) refreshHome().catch(() => {});
    });
  }
  /* ---------- words Chinese speakers mix up: how to tell them apart, and interleaved practice ---------- */
  async function confuseView() {
    const d = await api('/api/next/words/confuse');
    const LV = ['A2', 'B1', 'B2', 'C1'];
    view.innerHTML = `<div class="stack"><div><h1 class="h1">词汇辨析</h1>
        <p class="muted small">中文里是一个词，英语里是几个：借 = borrow / lend，看 = look / see / watch。选几组混着练，错的会进复习。</p></div>
      <button class="btn primary block" id="cfMix" disabled>混合练习选中的组</button>
      ${LV.map(lv => { const gs = d.groups.filter(g => g.level === lv); return gs.length ? `<section class="stack-s section"><h2 class="h2">${lv}</h2>
        <div class="cf-list">${gs.map(g => `<label class="cf-row${g.tries ? ' tried' : ''}"><input type="checkbox" value="${esc(g.id)}"><span class="t"><b class="en">${esc(g.words.join(' / '))}</b>
          <span class="tiny muted">${esc(g.how)}</span></span><span class="tiny muted">${g.tries ? `${g.right}/${g.tries}` : ''}</span><a class="btn small" href="#/words/confuse/${encodeURIComponent(g.id)}">练</a></label>`).join('')}</div></section>` : ''; }).join('')}</div>`;
    const boxes = [...view.querySelectorAll('.cf-row input')], go = document.getElementById('cfMix');
    const upd = () => { const n = boxes.filter(b => b.checked).length; go.disabled = n < 2; go.textContent = n < 2 ? '选两组以上，混合练习' : `混合练习选中的 ${n} 组`; };
    boxes.forEach(b => b.onchange = () => { if (boxes.filter(x => x.checked).length > 6) { b.checked = false; toast('一次最多混 6 组'); } upd(); });
    go.onclick = () => { location.hash = '#/words/confuse/' + boxes.filter(b => b.checked).map(b => b.value).join(','); };
    upd();
  }
  async function confuseRound(groups) {
    const d = await api('/api/next/words/confuse/round?groups=' + encodeURIComponent(groups));
    const items = d.items; let i = 0, right = 0;
    // On a phone the round is one screen, like 复习: no tabs below, the question at the bottom where the thumb is, and
    // 怎么区分 open for the first question only, then one line to tap open again (语流 B8's audit: 119-213 px past the
    // screen on an iPhone SE, the last answer under the tabs)
    document.body.classList.add('reviewing');
    view.innerHTML = `<div class="stack mix confuse"><div><a class="link small" href="#/words/confuse">← 词汇辨析</a></div>
      <div><span class="kicker">词汇辨析</span><h1 class="h1">${esc(d.groups.map(g => g.words.join(' / ')).join(' · '))}</h1></div>
      <details class="cf-how" id="cfHow" open><summary data-tap="confuse-how"><b>怎么区分</b></summary><div class="stack-s">
      ${d.groups.map(g => `<div class="howto"><b class="en">${esc(g.words.join(' / '))}</b><span class="small">${esc(g.how)}</span></div>`).join('')}</div></details>
      <div class="cf-q"><div class="mix-dots" aria-hidden="true">${items.map(() => '<i></i>').join('')}</div><div id="mixQ"></div></div></div>`;
    const dots = [...view.querySelectorAll('.mix-dots i')];
    const ask = () => {
      const it = items[i], box = document.getElementById('mixQ');
      if (i === 1) document.getElementById('cfHow').open = false;  // read once; a tap brings it back
      dots.forEach((x, k) => x.classList.toggle('now', k === i));
      box.innerHTML = `<div class="q gq enter"><div class="tiny muted">第 ${i + 1} / ${items.length} 题</div><div class="prompt">${esc(it.prompt)}</div>
        ${it.options.map((o, j) => `<button class="ans" data-o="${j}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}<div class="fb" aria-live="polite"></div></div>`;
      // The first question shows 怎么区分 open, unless that runs past the screen (an iPhone SE, or Safari with its bars
      // showing: 375×553 was 62-69 px over, 语流 B8 on r33): then it starts folded too, one tap away, and the question fits
      if (i === 0 && innerWidth < 760 && document.body.classList.contains('reviewing') && document.scrollingElement.scrollHeight > innerHeight) document.getElementById('cfHow').open = false;
      box.querySelectorAll('.ans').forEach(b => b.onclick = () => {
        const ok = Number(b.dataset.o) === it.answer; haptic(ok ? 'success' : 'warning');
        box.querySelectorAll('.ans').forEach((x, j) => { x.disabled = true; if (j === it.answer) x.classList.add('right'); });
        if (!ok) b.classList.add('wrong'); else right++;
        dots[i].classList.add(ok ? 'ok' : 'no');
        api('/api/next/words/confuse/answer', { item: it.id, correct: ok }).catch(() => {});
        box.querySelector('.fb').innerHTML = `<div class="${ok ? 'ok' : 'bad'}">${ok ? '✓ 对了' : '✗ 选错了'}</div><div class="small">${esc(it.explanation)}</div>
          <button class="btn primary block" id="mixNext">${i + 1 < items.length ? '下一题' : '看结果'}</button>`;
        const nx = document.getElementById('mixNext'); nx.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' });
        nx.onclick = () => { i++; if (i < items.length) ask(); else done(); };
        announce(ok ? '答对了' : '答错了');
      });
    };
    const done = () => {
      document.body.classList.remove('reviewing');
      view.innerHTML = `<div class="stack mix-done">${right * 2 >= items.length ? `<div class="done-burst${right === items.length ? ' all' : ''}" aria-hidden="true">${doneRing}</div>` : ''}
        <div class="tc"><span class="kicker">词汇辨析</span><h1 class="h1">${items.length} 题做对 ${right} 题</h1>
        <p class="small">${right === items.length ? '全对！这几组你已经分得很清楚了。' : S.user ? `错的 ${items.length - right} 组已经放进复习，下次会换一道题考你。` : '登录后，错的会进复习，下次换一道题考你。'}</p></div>
        <div class="row center"><a class="btn" href="#/words/confuse">选别的组</a><button class="btn primary" id="cfAgain">再来一轮</button></div></div>`;
      document.getElementById('cfAgain').onclick = () => confuseRound(groups);
      announce(`${items.length} 题做对 ${right} 题`);
    };
    ask();
  }
  /* ---------- 雅思口语练习 (ielts_speaking): Part 1 questions and Part 2 cue cards, on the four criteria ---------- */
  // Every band shown is the AI's estimate for practice, and each page with one says so (d.notice).
  const IELTS_BACK = '<div><a class="link small" href="#/speak/ielts">← 雅思口语</a></div>';
  const bandTxt = b => (b == null ? '—' : b.toFixed(1));
  async function ieltsView() {
    const d = await api('/api/next/ielts');
    const row = (href, title, sub, last) => `<a class="nrow ${last != null ? 'st st-solid' : 'st st-untouched'}" href="${href}"><i class="dot" aria-hidden="true"></i>
        <span class="t"><b>${esc(title)}</b><span class="tiny muted">${esc(sub)}${last != null ? ` · 上次约 ${bandTxt(last)}` : ''}</span></span><span></span><span class="go" aria-hidden="true">›</span></a>`;
    view.innerHTML = `<div><a class="link small" href="#/speak">← 口语路线</a></div>
      <div class="stack"><div><h1 class="h1">雅思口语</h1>
        <p class="muted small">像考场一样开口说：Part 1 日常问答；Part 2 话题卡，准备 1 分钟，说 1–2 分钟。</p>
        <details class="basis"><summary>怎么评分</summary><p class="small">说完按雅思口语的四项标准（流利与连贯、词汇、语法、发音）给出估计分和改法。</p></details>
        <p class="tiny ielts-note">${esc(d.notice)}</p></div>
      <section class="stack-s"><h2 class="h2">Part 1 · 日常问答</h2><p class="tiny muted">每个话题 4 个问题，大约 3 分钟。考官不打断你，每句下面可以看「这句可以更好」。</p>
        <div class="plist">${d.part1.map(x => row(`#/speak/ielts/p1-${x.id}`, x.title, x.title_en, x.last)).join('')}</div></section>
      <section class="stack-s"><h2 class="h2">Part 2 · 话题卡</h2><p class="tiny muted">准备 1 分钟（可以记关键词），时间到自动开始录音，最多说 2 分钟。</p>
        <div class="plist">${d.part2.map(x => row(`#/speak/ielts/p2-${x.id}`, x.title, x.task, x.last)).join('')}</div></section></div>`;
  }
  async function ieltsPractice(key) {
    const d = await api('/api/next/ielts');
    const m = /^p([12])-([a-z-]+)$/.exec(key || ''), list = m && (m[1] === '1' ? d.part1 : d.part2), x = list && list.find(t => t.id === m[2]);
    if (!x) { view.innerHTML = '<div class="empty"><p>没有这个练习。</p><a class="btn" href="#/speak/ielts">雅思口语</a></div>'; return; }
    return m[1] === '1' ? ieltsPart1(d, x) : ieltsPart2(d, x);
  }
  // The feedback of either part: overall estimate, the four criteria (a bar each, what went well, what to do next),
  // what was said, a model answer to listen to, and the corrections (already in the mistake book).
  function ieltsFeedbackHTML(r, said) {
    return `<div class="result enter stack ielts-fb">${aiMark('估计分、点评和示范回答由 AI 生成，不是官方成绩')}
        <div class="card ielts-top"><div class="ielts-overall"><b>${r.overall == null ? '—' : '约 ' + bandTxt(r.overall)}</b><span class="small">总体估计</span></div>
          <p class="tiny ielts-note">${esc(r.notice)}</p>${r.summary ? `<p class="small">${esc(r.summary)}</p>` : ''}</div>
        <div class="stack-s ielts-crit">${r.criteria.map(c => `<div class="crit">
            <div class="ab"><span class="nm">${esc(c.title)}</span><span class="vbar"><i data-w="${c.band == null ? 0 : Math.round(c.band / 9 * 100)}"></i></span><span class="lv">${bandTxt(c.band)}</span></div>
            ${c.band == null && c.id === 'p' ? '<div class="tiny muted">这次是打字作答，不评发音。</div>' : ''}
            ${c.good ? `<div class="tiny"><span class="ok-mark" aria-hidden="true">✓</span> ${esc(c.good)}</div>` : ''}${c.next ? `<div class="tiny"><span class="up" aria-hidden="true">↑</span> ${esc(c.next)}</div>` : ''}</div>`).join('')}</div>
        ${said}
        ${r.model ? `<details class="card flat fold" open><summary><b class="small">示范回答${r.model_q ? '：' + esc(r.model_q) : ''}</b></summary><div class="stack-s">
          <div class="row"><button class="btn small" id="ieModel" type="button" aria-label="朗读示范（AI 朗读）">${ICON.speak.replace('<svg', '<svg width="16" height="16"')}<span>朗读</span></button><span class="tiny muted">AI 写的示范，学说法，不用背 · ${aiVoiceNote('AI 朗读', 'span', 'in')}</span></div>
          <p class="text ielts-model">${esc(r.model)}</p></div></details>` : ''}
        ${r.fixes.length ? `<div class="stack-s"><b>要改的地方</b>${fixesHTML(r.fixes)}</div>` : ''}
        <div class="row"><button class="btn" id="ieAgain" type="button">再练一次</button><a class="btn primary" href="#/speak/ielts">换一个</a></div></div>`;
  }
  function bindIeltsFeedback(out, r, again) {
    requestAnimationFrame(() => requestAnimationFrame(() => out.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
    const md = out.querySelector('#ieModel'); if (md) md.onclick = () => TTS.say(r.model);
    out.querySelector('#ieAgain').onclick = () => { TTS.stop(); scrollTo({ top: 0 }); again(); };
    bringIntoView(out);
    if (S.user) refreshHome().catch(() => {});
  }
  const ieltsSay = t => { if (TTS.can()) TTS.say(t); };  // WeChat has no browser voice; the server voice (when on) works there

  /* Part 1: the examiner's four questions in order. Each answer: what the AI heard and, folded, a better way to say it. */
  function ieltsPart1(d, x) {
    const answers = [];
    let q = 0;
    view.innerHTML = `${IELTS_BACK}<div class="stack"><div><span class="kicker">雅思口语 Part 1 · 练习</span><h1 class="h1">${esc(x.title)}</h1><div class="title-en">${esc(x.title_en)}</div>
        <div class="ai-line">${aiVoiceNote('考官的声音由 AI 合成', 'span')}</div><p class="small">考官一题一题问，不会打断你。每题说 2–4 句：先直接回答，再加一个理由或例子。可以说，也可以打字（打字不评发音）。</p></div>
      <div class="chat" id="chat"></div>
      <div id="ieIn" class="stack-s" hidden><div class="tiny muted" id="ieQn"></div>
        <div class="chat-in"><textarea id="ieText" rows="2" maxlength="600" lang="en" enterkeyhint="send" placeholder="用英文回答，或者点录音键说出来"></textarea>${recBtn('ieMic', '说出来')}<button class="btn primary" id="ieSend">发送</button></div>
        <div class="row between"><span class="tiny muted">说完再点一次录音键停止，最长 45 秒</span><button class="btn small ghost" id="ieEnd">结束并看反馈</button></div></div>
      <div><button class="btn primary block" id="ieStart">开始</button></div><div id="ieOut"></div></div>`;
    const chat = view.querySelector('#chat'), box = view.querySelector('#ieIn');
    const bubble = (role, text, extra) => { chat.insertAdjacentHTML('beforeend', `<div class="msg ${role}"><div class="b">${esc(text)}</div>${extra || ''}</div>`); chat.lastElementChild.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' }); };
    const busy = on => ['#ieSend', '#ieEnd', '#ieMic'].forEach(s => { const b = view.querySelector(s); if (b) b.disabled = on; });
    const ask = () => {
      const t = x.questions[q]; bubble('ai', t, `<span class="tiny muted who">考官 · 第 ${q + 1} / ${x.questions.length} 题</span>`); ieltsSay(t);
      view.querySelector('#ieQn').textContent = `第 ${q + 1} / ${x.questions.length} 题`;
    };
    view.querySelector('#ieStart').onclick = e => {
      if (!S.user) { needLogin('登录后可以练雅思口语，AI 会听你的回答并给估计分。'); return; }
      e.currentTarget.parentNode.remove(); box.hidden = false; ask();
      if (!TOUCH) view.querySelector('#ieText').focus({ preventScroll: true });
    };
    async function feedback() {
      MIC.stop(); box.hidden = true; TTS.stop();
      const out = view.querySelector('#ieOut'); out.innerHTML = '<div class="card sunk small row"><span class="spin"></span><span>考官在看你的回答，给四项估计分（约 10–20 秒）</span></div>';
      try {
        const r = (await api('/api/next/ielts', { step: 'part1', topic: x.id, answers, request_id: rid('ie') })).result;
        const said = `<details class="card flat fold"><summary><b class="small">你的回答（${r.answered} 题）</b></summary><div class="stack-s">${answers.map(a => `<div class="small"><div class="muted">${esc(x.questions[a.q])}</div><div class="text">${esc(a.text)}</div></div>`).join('')}</div></details>`;
        out.innerHTML = ieltsFeedbackHTML(r, said);
        bindIeltsFeedback(out, r, () => ieltsPart1(d, x));
      } catch (e) {
        out.innerHTML = `<div class="card sunk stack-s"><span class="small">${esc(e.message)}</span><button class="btn small" id="ieRetry">再试一次</button></div>`;
        out.querySelector('#ieRetry').onclick = feedback;
      }
    }
    async function send(text, blob) {
      busy(true);
      let r;
      try { r = (await api('/api/next/ielts', { step: 'answer', topic: x.id, q, request_id: rid('ie'), ...(blob ? { audio: await MIC.payload(blob) } : { text }) })).result; }
      catch (e) { toast(e.message); busy(false); if (text) view.querySelector('#ieText').value = text; return; }
      busy(false);
      const said = (r.heard || text || '').trim() || '[听不清]';
      bubble('me', said, r.better ? `<details class="better"><summary class="tiny">这句可以更好 ${aiTag()}</summary><div class="small text">${esc(r.better.text)}</div>${r.better.why ? `<div class="tiny muted">${esc(r.better.why)}</div>` : ''}</details>` : '');
      answers.push({ q, text: said.slice(0, 1200), note: r.note || '', spoken: !!blob });
      q += 1;
      if (q >= x.questions.length) { bubble('ai', 'Thank you. That\'s the end of Part 1.'); feedback(); return; }
      ask();
    }
    view.querySelector('#ieSend').onclick = () => { const t = view.querySelector('#ieText'), v = t.value.trim(); if (!v) return; t.value = ''; send(v); };
    view.querySelector('#ieText').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); view.querySelector('#ieSend').click(); } });
    const mic = view.querySelector('#ieMic'); mic.onclick = () => MIC.toggle(mic, 45, b => send('', b));
    view.querySelector('#ieEnd').onclick = () => { if (!answers.length) { toast('先回答一题再看反馈'); return; } feedback(); };
  }

  /* Part 2: the cue card. 开始准备 asks for the microphone inside the tap (WeChat and iPhones allow it only there), one
     minute to prepare with a box for notes, then the recording starts by itself and stops at two minutes. The microphone
     stays open from 开始准备 to the end of the talk (nothing plays meanwhile) and is let go the moment the talk ends, so
     the feedback and the model answer are heard on the loudspeaker (micOpen / micClose, 70-learner.js). */
  const LONGREC = {
    stream: null, mr: null, chunks: [], t0: 0,
    async open() {
      try { this.stream = await micOpen(); } catch (e) { throw new Error(e.message + '；也可以打字作答'); }
    },
    start(onStop) {
      const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
      // a low bitrate keeps two minutes of speech under the 1.4 MB a recording may be
      const opts = Object.assign(type ? { mimeType: type } : {}, { audioBitsPerSecond: 32000 });
      let mr; try { mr = recorderFor(this.stream, opts, 130); } catch (e) { mr = new MediaRecorder(this.stream); }
      this.mr = mr; this.chunks = []; this.t0 = Date.now();
      mr.ondataavailable = e => { if (e.data && e.data.size) this.chunks.push(e.data); };
      mr.onstop = () => { const secs = Math.round((Date.now() - this.t0) / 1000), blob = new Blob(this.chunks, { type: mr.mimeType || type || 'audio/webm' }); this.close(); onStop(blob, secs); };
      mr.start(1000);
    },
    stop() { if (this.mr && this.mr.state === 'recording') this.mr.stop(); else this.close(); },
    close() { if (this.stream) micClose(this.stream); this.stream = null; },
  };
  function ieltsPart2(d, x) {
    let timer = 0;
    const alive = () => document.body.contains(card);  // left the page: let go of the microphone
    view.innerHTML = `${IELTS_BACK}<div class="stack"><div><span class="kicker">雅思口语 Part 2 · 练习</span><h1 class="h1">${esc(x.title)}</h1></div>
      <div class="cue" id="cue" lang="en"><b>${esc(x.task)}</b><div class="small">You should say:</div><ul>${x.points.map(p => `<li>${esc(p)}</li>`).join('')}</ul><div class="small">${esc(x.last_point)}</div></div>
      <div id="p2" class="stack-s"><p class="small">点「开始准备」：1 分钟准备，可以在下面记几个关键词；时间到自动开始录音，最多说 2 分钟，到时间自动停。也可以提前开始、提前结束。尽量说满 1 分钟以上。</p>
        <button class="btn primary block" id="p2Start">开始准备</button><button class="btn small ghost" id="p2Type" type="button">不方便说话？打字作答（不评发音）</button></div>
      <div id="ieOut"></div></div>`;
    const card = view.querySelector('#cue'), stage = view.querySelector('#p2'), out = view.querySelector('#ieOut');
    const meter = (label, s, total, cls) => `<div class="p2-clock ${cls}" role="timer" aria-live="off"><span class="lbl">${label}</span><b id="p2T">${mmss(Math.max(0, s))}</b><span class="vbar"><i id="p2Bar" style="width:${Math.round((total - s) / total * 100)}%"></i></span></div>`;
    const tick = (s, total) => { const t = view.querySelector('#p2T'), b = view.querySelector('#p2Bar'); if (t) t.textContent = mmss(Math.max(0, s)); if (b) b.style.width = Math.round((total - s) / total * 100) + '%'; };
    async function submit(body) {
      stage.innerHTML = '<div class="card sunk small row"><span class="spin"></span><span>AI 在听你的回答，按四项标准估计分数（约 20–40 秒）</span></div>';
      try {
        const r = (await api('/api/next/ielts', { step: 'part2', card: x.id, request_id: rid('ie'), ...body })).result;
        stage.innerHTML = ''; if (body.text) draftDone('ielts-p2-' + x.id);
        const cov = r.covered ? `<div class="tiny muted">话题卡的 4 个要点：${r.covered.map((c, k) => `<span class="${c ? 'ok-mark' : 'bad-mark'}">${c ? '✓' : '✗'}</span> ${esc(k < 3 ? x.points[k] : 'explain…')}`).join('　')}</div>` : '';
        const said = `<details class="card flat fold"><summary><b class="small">你说的${r.spoken ? '（AI 转写' + (r.seconds ? ' · ' + mmss(r.seconds) : '') + '）' : ''}</b></summary><div class="stack-s"><p class="text">${esc(r.transcript || '（没听清）')}</p>${cov}</div></details>`;
        out.innerHTML = ieltsFeedbackHTML(r, said);
        bindIeltsFeedback(out, r, () => ieltsPart2(d, x));
      } catch (e) {
        stage.innerHTML = `<div class="card sunk stack-s"><span class="small">${esc(e.message)}</span><button class="btn small" id="p2Retry">再试一次</button></div>`;
        stage.querySelector('#p2Retry').onclick = () => submit(body);
      }
    }
    function talk() {
      clearInterval(timer);
      let left = d.talk;
      const notes = view.querySelector('#p2Notes'), kept = notes ? notes.value : '';
      stage.innerHTML = `${meter('<span class="dot rec-dot" aria-hidden="true"></span>正在录音', left, d.talk, 'talk')}
        ${kept ? `<div class="card sunk tiny p2-kept">你的笔记：${esc(kept)}</div>` : ''}<button class="btn primary block" id="p2Done">说完了</button>`;
      LONGREC.start(async (blob, secs) => {
        clearInterval(timer);
        if (!alive()) return;
        if (secs < 5 || blob.size < 2000) { stage.innerHTML = '<p class="small">录音太短了。</p><button class="btn primary" id="p2Re">重新开始</button>'; stage.querySelector('#p2Re').onclick = () => ieltsPart2(d, x); return; }
        let audio; try { audio = await MIC.payload(blob); } catch (e) { stage.innerHTML = `<p class="small">${esc(e.message)}</p>`; return; }
        submit({ audio, seconds: secs });
      });
      timer = setInterval(() => { if (!alive()) { clearInterval(timer); LONGREC.stop(); return; } left -= 1; tick(left, d.talk); if (left <= 0) LONGREC.stop(); }, 1000);
      stage.querySelector('#p2Done').onclick = () => LONGREC.stop();
      card.scrollIntoView({ block: 'start', behavior: REDUCED ? 'auto' : 'smooth' });  // the card in view while speaking
    }
    stage.querySelector('#p2Start').onclick = async e => {
      if (!S.user) { needLogin('登录后可以练雅思口语，AI 会听你的回答并给估计分。'); return; }
      const b = e.currentTarget;
      if (!micReady(() => b.click())) return;
      b.disabled = true;
      try { await LONGREC.open(); } catch (err) { b.disabled = false; toast(err.message); return; }
      let left = d.prep;
      stage.innerHTML = `${meter('准备', left, d.prep, 'prep')}
        <textarea id="p2Notes" rows="3" maxlength="300" lang="en" placeholder="记几个关键词，例如：cooking · grandma · 3 months · saves money" autocapitalize="off" spellcheck="false"></textarea>
        <button class="btn block" id="p2Go">提前开始说</button>`;
      stage.querySelector('#p2Go').onclick = talk;
      timer = setInterval(() => { if (!alive()) { clearInterval(timer); LONGREC.close(); return; } left -= 1; tick(left, d.prep); if (left <= 0) talk(); }, 1000);
    };
    stage.querySelector('#p2Type').onclick = () => {
      if (!S.user) { needLogin('登录后可以练雅思口语，AI 会看你的回答并给估计分。'); return; }
      stage.innerHTML = `<textarea id="p2Txt" data-draft="ielts-p2-${esc(x.id)}" rows="8" maxlength="3000" lang="en" placeholder="像说话一样写下你的回答（至少 20 个英文词）"></textarea>
        <div class="row between"><span class="tiny muted">打字作答不评发音，其他三项照常估计</span><button class="btn primary" id="p2Send">提交</button></div>`;
      stage.querySelector('#p2Send').onclick = () => { const v = stage.querySelector('#p2Txt').value.trim(); if ((v.match(/[A-Za-z]+/g) || []).length < 20) { toast('至少写 20 个英文词'); return; } submit({ text: v }); };
    };
  }
  /* ---------- the speaking route: role-play scenes from ordering a coffee to answering a sceptical boss ---------- */
  async function speakView() {
    const d = await api('/api/next/speak' + guestQuery(true));
    const LV = { A2: '入门', B1: '中级', B2: '中高级', C1: '高级' };
    view.innerHTML = `<div class="stack"><div><h1 class="h1">口语路线</h1>
        <p class="muted small">AI 扮演店员、房东、面试官……你用英文完成任务，说或打字都行。</p>
        <details class="basis"><summary>怎么练</summary><p class="small">每说一句，AI 会顺手纠正一处，并按你的回答放慢或加深一点；结束时告诉你哪里说得好、哪里要改。练过的情景过两周会回来：第 2 轮多一条要求，第 3 轮换角色。</p></details></div>
      ${d.next ? (n => `<a class="btn primary block" href="#/speak/${encodeURIComponent(d.next)}">下一个：${esc(n.title)}${n.rounds ? ` · 第 ${n.round} 轮` : ''}<span aria-hidden="true">→</span></a>`)(d.items.find(x => x.id === d.next)) : ''}${aiMark('对话里的角色由 AI 扮演').replace('class="ai-line"', 'class="ai-line route-ai"')}
      <p class="small muted">${d.round_two ? `${d.total} 个情景都练过了，现在是复练：练过的情景会多一条要求，或者换角色再演一次。` : `已完成 ${d.done} / ${d.total} 个情景`}</p>
      <a class="card flat ielts-entry" href="#/speak/ielts" data-tap="speak-ielts"><span class="stack-xs"><b>雅思口语 · Part 1 和 Part 2</b>
        <span class="tiny muted">考官提问、话题卡计时，按四项标准给 AI 估计分（练习用，不是官方成绩）</span></span><span class="go" aria-hidden="true">›</span></a>
      ${['A2', 'B1', 'B2', 'C1'].map(lv => { const xs = d.items.filter(x => x.level === lv); return xs.length ? `<section class="stack-s section"><h2 class="h2">${lv} · ${LV[lv]}</h2>
        <div class="plist">${xs.map(x => `<a class="nrow ${x.done ? 'st st-solid' : 'st st-untouched'}" href="#/speak/${encodeURIComponent(x.id)}"><i class="dot" aria-hidden="true"></i>
          <span class="t"><b>${esc(x.title)}</b><span class="tiny muted">你：${esc(x.me)} · AI：${esc(x.ai)}${x.rounds ? ` · 练过 ${x.rounds} 轮` : ''}</span></span><span></span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div></section>` : ''; }).join('')}</div>`;
  }
  async function speakScene(sid) {
    const d = await api('/api/next/speak' + guestQuery(true)), x = d.items.find(s => s.id === sid);
    if (!x) { view.innerHTML = '<div class="empty"><p>没有这个情景。</p><a class="btn" href="#/speak">口语路线</a></div>'; return; }
    const hist = [], paced = { easier: 0, harder: 0 };
    // round 2, 3…: one more requirement (even rounds) or the roles swapped (odd rounds from 3); scenarios.mode_of
    const swap = x.mode === 'swap', again = x.rounds > 0;
    const goals = swap ? x.swap_goals : x.goals;
    view.innerHTML = `<div><a class="link small" href="#/speak">← 口语路线</a></div>
      <div class="stack"><div><span class="kicker">情景对话 · ${esc(x.level)}${again ? ` · 第 ${x.round} 轮` : ''}</span><h1 class="h1">${esc(x.title)}</h1><div class="title-en">${esc(x.title_en)}</div>
        <div class="ai-line">${aiTag()}<span>角色、纠正和声音都由 AI 生成</span>${aiVoiceNote('AI 朗读', 'span')}</div><p class="small">${swap ? `这一轮换过来：你扮演${esc(x.ai)}，AI 扮演${esc(x.me)}。情景还是：${esc(x.brief)}` : esc(x.brief)}</p></div>
      <div class="scene-goals"><div class="kicker">你的任务${swap ? `（你是${esc(x.ai)}）` : ''}</div><ol class="steps-list small">${goals.map(g => `<li>${esc(g)}</li>`).join('')}
        ${x.mode === 'challenge' ? `<li class="round-extra"><b>这一轮多一条：</b>${esc(x.challenge)}</li>` : ''}</ol></div>
      ${swap ? '' : `<details class="useful"><summary class="small">用得上的说法（${x.useful.length}）</summary><div class="plist">${x.useful.map(u => `<div class="crow">${sayIcon(`data-say="${esc(u.text)}"`, '朗读')}<span><span class="en">${esc(u.text)}</span><span class="tiny muted">${esc(u.meaning)}</span></span></div>`).join('')}</div></details>`}
      <div class="chat" id="chat" data-ex-block></div>
      <div id="dlgIn" class="stack-s" hidden><div class="tiny muted" id="dlgHint"></div>
        <div class="chat-in"><textarea id="dlgText" rows="2" maxlength="480" lang="en" enterkeyhint="send" placeholder="用英文回答，或者点录音键说出来"></textarea>${recBtn('dlgMic', '说出来')}<button class="btn primary" id="dlgSend" data-own-wait>发送</button></div>
        <div class="row between"><span class="tiny muted" id="dlgCount"></span><button class="btn small ghost" id="dlgEnd">结束并看反馈</button></div></div>
      <div class="dlg-go"><button class="btn primary block" id="dlgStart">开始对话</button></div><div id="dlgOut"></div></div>`;
    view.querySelectorAll('[data-say]').forEach(b => b.onclick = () => TTS.say(b.dataset.say));
    const chat = view.querySelector('#chat');
    const bubble = (role, text, extra) => { chat.insertAdjacentHTML('beforeend', `<div class="msg ${role}"><div class="b">${esc(text)}</div>${extra || ''}</div>`); chat.lastElementChild.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' }); };
    // 8 lines a round (output_service.DIALOG_LINES): then only 结束并看反馈, which the server takes whatever the length
    const FULL = 8, full = () => mine() >= FULL;
    const busy = on => { ['#dlgSend', '#dlgEnd', '#dlgMic', '#dlgText'].forEach(s => { const b = view.querySelector(s); if (b) b.disabled = (on && s !== '#dlgText') || (s !== '#dlgEnd' && full()); }); };  // the box only when the round is full
    const showInput = () => { const box = view.querySelector('#dlgIn'); if (box && !box.hidden) box.scrollIntoView({ block: 'end', behavior: REDUCED ? 'auto' : 'smooth' }); };
    const mine = () => hist.filter(h => h.role === 'me').length;
    async function turn(body) {
      busy(true);
      try { return (await api('/api/next/dialog', { scenario: sid, history: hist, request_id: rid('sp'), ...body })).result; }
      catch (e) { toast(e.message); return null; } finally { busy(false); }
    }
    view.querySelector('#dlgStart').onclick = async e => {
      if (!S.user) { needLogin('登录后可以和 AI 做情景对话。'); return; }
      const btn = e.currentTarget; btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
      const r = await turn({}); if (!r) { btn.disabled = false; btn.textContent = '开始对话'; return; }
      btn.parentNode.remove();
      chat.insertAdjacentHTML('beforeend', `<div class="scene small"><span data-ex>${esc(r.scene)}</span>${r.role ? `（AI 扮演：${esc(r.role)}）` : ''}</div>`);
      bubble('ai', r.reply); speakReply(r.reply, r.voice); hist.push({ role: 'ai', text: r.reply });
      view.querySelector('#dlgIn').hidden = false; showInput(); if (!TOUCH) view.querySelector('#dlgText').focus({ preventScroll: true });
    };
    // The AI's line in its role's voice (r.voice, scenarios.voice_for), which the server began making along with the reply
    // (声音接力), so it is usually there at once. SV.say waits for it with 「正在准备朗读…」 rather than switch to the browser
    // voice for being a few seconds late (the owner hears that as a robot); the browser voice only when the server cannot
    // give it, and one line says why. Played as SV plays (#78): Web Audio where it can, so an iPhone keeps the first word.
    function speakReply(text, voice) {
      if (!voice || !SV.on()) { TTS.say(text); return; }
      SV.say(text, null, { voice, title: '语流 · 口语情景' });
    }
    // 说完就显示进度: from the moment an answer is sent, a line at the end of the chat says what is happening and for how
    // long (the seconds are not read aloud); a recording that did not get through stays to be sent again, not said twice.
    function waiting(spoken) {
      const el = document.createElement('div'), t0 = Date.now();
      el.className = 'dlg-wait small muted'; el.setAttribute('role', 'status');
      el.innerHTML = `<span class="spin" aria-hidden="true"></span><span>${spoken ? '正在听你说的…' : '对方正在回…'}</span> <span class="secs" aria-hidden="true">0 秒</span>`;
      const secs = el.querySelector('.secs'), timer = setInterval(() => { secs.textContent = Math.floor((Date.now() - t0) / 1000) + ' 秒'; }, 1000);
      chat.append(el); el.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' });
      return {
        done() { clearInterval(timer); el.remove(); },
        failed(again) {
          clearInterval(timer);
          el.innerHTML = '<span>这段录音没有发出去。</span> <button class="btn small" type="button" data-own-wait>重发这段录音</button>';
          el.querySelector('button').onclick = () => { el.remove(); again(); };
        },
      };
    }
    async function send(text, blob) {
      if (full()) return;
      const w = waiting(!!blob);
      let body;
      try { body = blob ? { audio: await MIC.payload(blob) } : { text }; } catch (e) { w.done(); toast(e.message); return; }
      const r = await turn(body);
      if (!r) {
        if (blob) { w.failed(() => send('', blob)); return; }
        w.done(); const box = view.querySelector('#dlgText'); if (box && !box.value) box.value = text;  // typed: back in the box
        return;
      }
      w.done();
      const me = r.heard || text;
      // 按回答调难度 (scenarios.pace): the AI's next line follows this answer's length and mistakes; say so in one line
      const pace = r.pace === 'easier' ? '放慢了一点' : r.pace === 'harder' ? '加深了一点' : '';
      if (pace) paced[r.pace] += 1;
      bubble('me', me, (r.correction ? `<div class="fix tiny"><del>${esc(r.correction.original)}</del> → <b>${esc(r.correction.better)}</b> <span class="muted" data-ex>${esc(r.correction.why)}</span></div>` : '')
        + (pace ? `<div class="pace tiny muted" data-pace="${r.pace}">↳ AI 按你的回答${pace}</div>` : ''));
      hist.push({ role: 'me', text: me });
      bubble('ai', r.reply); speakReply(r.reply, r.voice); hist.push({ role: 'ai', text: r.reply });
      const hint = view.querySelector('#dlgHint');
      hint.innerHTML = (r.hint ? esc('提示：' + r.hint) : '') + (r.say ? `<span class="say-line">${r.hint ? '' : '提示：'}可以说 <b lang="en">${esc(r.say)}</b>${sayIcon('id="dlgSay"', '朗读这句')}</span>` : '');
      const sb = hint.querySelector('#dlgSay'); if (sb) sb.onclick = () => TTS.say(r.say);
      const n = mine(); view.querySelector('#dlgCount').textContent = n >= FULL ? `这一轮说满 ${FULL} 句了，点「结束并看反馈」`
        : n < 4 ? `已经说了 ${n} 句，说到 4 句左右就可以看反馈` : `已经说了 ${n} 句，可以看反馈了`;
      busy(false); showInput();
    }
    view.querySelector('#dlgSend').onclick = () => { const t = view.querySelector('#dlgText'); const v = t.value.trim(); if (!v) return; t.value = ''; send(v); };
    view.querySelector('#dlgText').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); view.querySelector('#dlgSend').click(); } });
    const mic = view.querySelector('#dlgMic'); mic.dataset.ownWait = ''; mic.onclick = () => MIC.toggle(mic, 30, b => send('', b));
    view.querySelector('#dlgEnd').onclick = async e => {
      if (mine() < 1) { toast('先说一两句再看反馈'); return; }
      const btn = e.currentTarget; btn.innerHTML = '<span class="spin"></span>';
      const r = await turn({ end: true }); if (!r) { btn.textContent = '结束并看反馈'; return; }
      view.querySelector('#dlgIn').hidden = true; TTS.stop();
      view.querySelector('#dlgOut').innerHTML = `<div class="result enter stack" data-ex-block>${aiMark('总结和建议由 AI 生成，仅供参考')}<div class="card verdict"><span class="dot"></span><div data-ex>${esc(r.summary)}</div></div>
        ${r.good.length ? `<div class="stack-s"><b>说得好的句子</b>${r.good.map(g => `<div class="small text">${esc(g)}</div>`).join('')}</div>` : ''}
        ${r.fixes.length ? `<div class="stack-s"><b>要改的地方</b>${fixesHTML(r.fixes)}</div>` : ''}
        ${r.challenge ? `<div class="round-extra small"><b>这一轮的要求：</b>${esc(r.challenge)}${typeof r.challenge_met === 'boolean' ? (r.challenge_met ? ' <span class="ok-mark">✓ 做到了</span>' : ' <span class="muted">· 这次还没做到，下一轮再试</span>') : ''}</div>` : ''}
        ${paced.easier || paced.harder ? `<p class="tiny muted">这一轮 AI 按你的回答${paced.easier ? `放慢了 ${paced.easier} 次` : ''}${paced.easier && paced.harder ? '、' : ''}${paced.harder ? `加深了 ${paced.harder} 次` : ''}。</p>` : ''}
        ${r.expressions.length ? `<div class="stack-s"><b>可以学的表达</b>${r.expressions.map((ex, k) => `<div class="row between small"><span><b>${esc(ex.text)}</b> <span class="muted">${esc(ex.meaning)}</span></span><button class="btn small" data-kx="${k}">收藏</button></div>`).join('')}</div>` : ''}
        <p class="small cheer">${mine() >= 4 ? '完整完成了一个情景。' : ''}敢开口就是进步：说错的地方，正是下次能说对的地方。</p>
        <div class="row"><button class="btn" id="dlgAgain">再练一次</button><a class="btn primary" href="#/speak">下一个情景</a></div></div>`;
      view.querySelectorAll('[data-kx]').forEach(b => b.onclick = () => { const ex = r.expressions[Number(b.dataset.kx)]; saveCard({ text: ex.text, meaning: ex.meaning, context: '', pack: null }, b); });
      view.querySelector('#dlgAgain').onclick = () => { scrollTo({ top: 0 }); speakScene(sid); };
      bringIntoView(view.querySelector('#dlgOut'));
      if (S.user) refreshHome().catch(() => {});
    };
  }
  /* ---------- my progress: this month against the last, and milestones that only count up ---------- */
  async function growthView(month) {
    if (!S.user) return needLogin('登录后可以看到每个月的进步。');
    const d = await api('/api/next/growth' + (month ? '?month=' + encodeURIComponent(month) : ''));
    // The page in four blocks (B9, 2026-11-26; the user on the mock-ups: 完全做，按照现在的效果图): one sentence for the month,
    // the other seven figures a row each, the three milestones nearest to done (the rest folded under them), the way to
    // 周报. The theme colour marks what grew and the bars; the month is changed with the two arrows on the right.
    const n = d.now, b = d.before, num = v => v == null ? '—' : v.toLocaleString();
    const more = k => b[k] == null || n[k] == null ? '' : n[k] > b[k] ? `多 ${(n[k] - b[k]).toLocaleString()}` : n[k] < b[k] ? `上月 ${b[k].toLocaleString()}` : '';
    const row = (k, icon, label, text) => `<div class="gtile grow-row">${fi(icon)}<span class="t">${label}</span><b>${n[k] == null ? '—' : text(num(n[k]))}</b><span class="d tiny muted">${more(k)}</span></div>`;
    const thisMonth = new Date(); const cur = `${thisMonth.getFullYear()}-${String(thisMonth.getMonth() + 1).padStart(2, '0')}`;
    const ym = d.month.split('-').map(Number), nextYm = ym[1] === 12 ? `${ym[0] + 1}-01` : `${ym[0]}-${String(ym[1] + 1).padStart(2, '0')}`, atNow = d.month >= cur;
    const arrow = p => `<svg viewBox="0 0 12 12" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${p}"/></svg>`;
    const days = n.days == null || b.days == null ? '' : n.days > b.days ? `<span class="up">比上个月多 ${n.days - b.days} 天</span>` : n.days < b.days ? `上个月 ${b.days} 天` : '和上个月一样';
    const mile = (m, k) => `<div class="mile${m.done ? ' done' : ''} pop-in" data-k="${k}"><div class="r"><b>${m.done ? '<span class="mi" aria-hidden="true">✓</span>' : ''}${esc(m.title)}</b><span class="tiny muted">${m.have.toLocaleString()} / ${m.need.toLocaleString()} ${esc(m.unit)}</span></div>
      <span class="vbar"><i data-w="${Math.min(100, Math.round(m.have / m.need * 100))}"></i></span></div>`;
    const open = d.milestones.filter(m => !m.done).sort((x, y) => y.have / y.need - x.have / x.need), near = open.slice(0, 3);
    const rest = d.milestones.filter(m => near.indexOf(m) < 0);
    view.innerHTML = `<div class="stack grow-page"><div><h1 class="h1">我的进步</h1>
        <div class="grow-top"><span class="small muted">${d.month === cur ? '只和自己的上个月比' : `<a class="link" href="#/growth">回到本月</a>`}</span>
          <span class="grow-mon"><a href="#/growth/${encodeURIComponent(d.prev)}" aria-label="上个月">${arrow('M7.5 2.5 4 6l3.5 3.5')}</a><b>${esc(d.label)}</b>${atNow ? `<span class="off" aria-hidden="true">${arrow('M4.5 2.5 8 6 4.5 9.5')}</span>` : `<a href="#/growth/${encodeURIComponent(nextYm)}" aria-label="下个月">${arrow('M4.5 2.5 8 6 4.5 9.5')}</a>`}</span></div></div>
      <section class="card flat gtile grow-hero"><p class="tiny muted">${d.month === cur ? '这个月' : esc(d.label)}</p><h2>${n.days == null ? '还没有记录' : `学了 ${n.days} 天`}</h2>${days ? `<p class="small muted">${days}</p>` : ''}</section>
      <section class="card flat grow-rows">${row('words_read', 'read', '读了', v => v + ' 词')}${row('materials', 'layers', '学完的材料', v => v + ' 篇')}${row('wpm', 'gauge', '阅读速度', v => '每分钟 ' + v + ' 词')}
        ${row('reviews', 'again', '复习', v => v + ' 次')}${row('new_words', 'spark', '新学的词', v => v + ' 个')}${row('grammar_checks', 'graph', '语法做题', v => v + ' 题')}${row('speaking', 'mic', '开口说', v => v + ' 次')}</section>
      <section class="card flat grow-miles"><div class="row between"><h2>${near.length ? '快到的里程碑' : '里程碑'}</h2><span class="small muted">已达成 ${d.reached} / ${d.total}</span></div>
        <div class="miles">${near.map(mile).join('')}</div>
        ${rest.length ? `<details class="grow-all"${near.length ? '' : ' open'}><summary>全部 ${d.total} 个<svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 4.5 6 8l3.5-3.5"/></svg></summary><div class="miles">${rest.map((m, k) => mile(m, k + near.length)).join('')}</div></details>` : ''}</section>
      <a class="grow-link" href="#/report">${fi('week')}<b>周报</b><span class="go">最近 7 天 ›</span></a>
      <p class="tiny muted grow-note">${esc(d.note)}</p></div>`;
    view.querySelectorAll('.pop-in').forEach(el => el.style.setProperty('--d', Math.min(10, Number(el.dataset.k)) * 60 + 'ms'));
    requestAnimationFrame(() => requestAnimationFrame(() => view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
  }
  /* ---------- ability radar: six skills against the learner's own goals, and what moved ---------- */
  const DIM_TEST = { vocab: '#/vocab/test', grammar: '#/placement', reading: '#/radar/test/reading', listening: '#/radar/test/listening', speaking: '#/radar/test/speaking', writing: '#/radar/test/writing' };
  const CONF = { high: '测评', medium: '估计', low: '粗略估计' };
  // The radar as one part (B9, 2026-11-26; the user: 没测过雷达图就显示 0，点雷达图上面的字就可以对这个模块进行测试): the web is
  // three soft fills, no hairlines; the learner's shape is in the theme colour; the six names around it are links, and a tap on a name
  // starts that skill's check (DIM_TEST). Nothing measured yet: a dot at the centre (all 0) and every name says 去测.
  // A skill with no score last time keeps today's place in the dashed outline (no spike to the centre).
  // opts.prev: last time's scores by id, drawn as a dashed outline. The names sit by percentages, so the part scales with its box.
  function radarChart(dims, opts) {
    const o = opts || {}, W = 320, H = 300, CX = 160, CY = 150, R = 92, n = dims.length;
    const at = (k, r) => { const a = -Math.PI / 2 + k * 2 * Math.PI / n; return [CX + r * Math.cos(a), CY + r * Math.sin(a)]; };
    const ring = r => dims.map((d, k) => at(k, r).map(x => x.toFixed(1)).join(',')).join(' ');
    const shape = vals => vals.map((v, k) => at(k, R * Math.max(0, Math.min(100, v == null ? 0 : v)) / 100).map(x => x.toFixed(1)).join(',')).join(' ');
    const any = dims.some(d => d.score != null);
    // a dot on each skill that has a score: with one or two of the six, the shape alone is only a spoke
    const dots = dims.map((d, k) => { if (d.score == null) return ''; const q = at(k, R * Math.max(0, Math.min(100, d.score)) / 100); return `<circle class="dt" cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" r="3.2"/>`; }).join('');
    // where each name sits is in 89-radar.css (.rdr-ax.k0 … .k5): the page's rules allow no style attribute in markup
    const names = dims.map((d, k) => {
      const has = d.score != null, say = !has ? '还没测，点一下去测' : d.assessed ? d.score + ' 分，点一下' + (d.due ? '再测' : '重测') : '按平时练习估计 ' + d.score + ' 分，点一下去测';
      return `<a class="rdr-ax k${k}" href="${DIM_TEST[d.id]}" data-tap="radar-name" aria-label="${esc(d.label)}，${say}">${esc(d.label)}<small${has ? '' : ' class="go"'}>${has ? d.score : '去测'}</small></a>`;
    }).join('');
    return `<div class="rdr" role="group" aria-label="能力雷达：${dims.map(d => d.label + (d.score == null ? '还没测' : ' ' + d.score + ' 分')).join('，')}">
      <svg viewBox="0 0 ${W} ${H}" aria-hidden="true"><polygon class="w1" points="${ring(R)}"/><polygon class="w2" points="${ring(R * 2 / 3)}"/><polygon class="w1" points="${ring(R / 3)}"/>
      ${o.prev ? `<polygon class="prev" points="${shape(dims.map(d => o.prev[d.id] == null ? d.score : o.prev[d.id]))}"/>` : ''}
      <g class="cur">${any ? `<polygon class="area" points="${shape(dims.map(d => d.score))}"/>${dots}` : `<circle class="zero" cx="${CX}" cy="${CY}" r="4"/>`}</g></svg>${names}</div>`;
  }
  function spark(vals) {
    const xs = vals.filter(v => v != null); if (xs.length < 2) return '';
    const pts = vals.map((v, k) => v == null ? null : `${(k / (vals.length - 1) * 60).toFixed(1)},${(18 - v / 100 * 16).toFixed(1)}`).filter(Boolean).join(' ');
    return `<svg class="spark" viewBox="0 0 60 20" aria-hidden="true"><polyline points="${pts}"/></svg>`;
  }
  async function radarView() {
    if (!S.user) return needLogin('登录后可以设定目标、做能力测评，看到自己每一项离目标还差多少。');
    const r = await api('/api/next/radar');
    const prev = r.before ? (r.history.find(h => h.created === r.before) || {}).scores : null;
    const known = r.dims.filter(d => d.score != null);
    // One screen first (the user: 一个屏幕能展示的内容就展示掉): the title, the radar with its six names, the one green
    // button. What the page also had (goals, each skill's detail, the estimate from practice) comes below, nothing dropped.
    // 测过 means a check was done (d.assessed); a score can also be an estimate from practice, and the line in the card says so
    const tested = r.dims.filter(d => d.assessed).length, left = r.dims.length - tested, guessed = known.some(d => !d.assessed);
    const head = !tested ? '还没测过' : left ? `测过 ${tested} 项，还差 ${left} 项` : r.due.length ? `有 ${r.due.length} 项该重测了` : '六项都测过了';
    const goText = !tested ? '六项都测一遍' : left ? `测剩下的 ${left} 项` : '再测一次';
    view.innerHTML = `<div class="stack radar-page"><div><h1 class="h1">能力雷达</h1><p class="muted small" id="radarHead">${head} · 点一项的名字，测这一项</p></div>
      <section class="card flat radar-card">${radarChart(r.dims, { prev })}
        <p class="tiny muted radar-key">外圈是你定的目标${guessed ? '，没测的先按平时练习估计' : ''}${prev ? '，虚线是上次' : ''}</p></section>
      <a class="btn primary block radar-go" id="radarGo" href="#/radar/test" data-tap="radar-go">${goText}</a>
      <p class="tiny muted radar-note">每项 3–8 分钟，可以分几次测。</p>
      ${r.goals_chosen ? '' : `<a class="card flat place-cta" href="#/radar/goals"><b>先定一个目标</b><span class="small muted">每一项想到什么水平？现在先按比你的水平高一级来算，可以随时改。</span></a>`}
      <section class="card flat radar-each"><div class="row between"><h2>每一项</h2><a class="radar-goals" href="#/radar/goals" data-tap="radar-goals">调整目标 ›</a></div>${r.dims.map((d, k) => { const delta = d.score != null && d.prev_score != null ? d.score - d.prev_score : null;
        return `<div class="rdim pop-in" data-k="${k}"><div class="row between"><b>${esc(d.label)}</b><span class="tiny muted">目标 ${esc(d.goal)}</span></div>
          ${d.score == null ? `<div class="small muted">还没有数据 · <a class="link" href="${DIM_TEST[d.id]}">测一测</a></div>` : `
          <div class="rbar"><span class="vbar"><i data-w="${d.score}"></i></span><b class="num">${d.score}</b>${delta ? `<span class="${delta > 0 ? 'up' : 'down'}">${delta > 0 ? '+' : ''}${delta}</span>` : ''}${spark(r.history.map(h => h.scores[d.id]))}</div>
          <div class="tiny muted">现在约 ${esc(d.level)} · ${CONF[d.confidence] || ''}${d.assessed ? '（' + new Date(d.assessed * 1000).toLocaleDateString('zh-CN') + ' 测评）' : '（来自平时练习）'}
            · <a class="link" href="${DIM_TEST[d.id]}">${!d.assessed ? '去测' : d.due ? '该测了' : '重测'}</a>${r.gap === d.id ? `<a class="link rgap" href="${d.href}">差距最大：${esc(d.tip)}</a>` : ''}</div>`}</div>`; }).join('')}
        ${r.gap ? `<p class="small muted radar-gap">${esc(r.dims.find(d => d.id === r.gap).label)}离目标最远，每天的计划会多安排这方面的练习。</p>` : ''}</section>
      <p class="muted small radar-about">${esc(r.note)}</p>
      <details class="card flat fold" id="abFold"><summary><b>按平时练习估计</b><span class="tiny muted">近 45 天 · 8 项，含翻译和发音</span></summary><div id="abSlot"><p class="muted small"><span class="spin"></span></p></div></details></div>`;
    view.querySelectorAll('.pop-in').forEach(el => el.style.setProperty('--d', Number(el.dataset.k) * 60 + 'ms'));
    // What used to be the 能力画像 card on 我的: loaded when it is opened.
    const fold = document.getElementById('abFold');
    fold.addEventListener('toggle', () => {
      if (!fold.open || fold.dataset.done) return;
      fold.dataset.done = '1';
      api('/api/next/ability').then(ab => {
        const slot = document.getElementById('abSlot'); if (!slot) return;
        slot.innerHTML = abilityHTML(ab);
        requestAnimationFrame(() => requestAnimationFrame(() => slot.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
      }).catch(e => { const slot = document.getElementById('abSlot'); if (slot) slot.innerHTML = `<p class="muted small">${esc(e.message)}</p>`; delete fold.dataset.done; });
    });
    requestAnimationFrame(() => requestAnimationFrame(() => { view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; }); const g = view.querySelector('.rdr .cur'); if (g) g.classList.add('on'); }));
  }
  async function radarGoals() {
    if (!S.user) return needLogin('登录后可以设定目标。');
    const r = await api('/api/next/radar'), g = { ...r.goals }, LV = { A2: '入门', B1: '中级', B2: '中高级', C1: '高级' };
    const draw = () => {
      view.innerHTML = `<div class="stack"><div><a class="link small" href="#/radar">← 能力雷达</a></div><div><span class="kicker">设定目标</span><h1 class="h1">每一项想到什么水平？</h1>
          <p class="muted small">目标就是雷达图上的 100 分。可以每项不一样，比如“口语到 B1，阅读到 B2”。</p></div>
        <div class="row"><span class="small muted">全部设为</span>${r.goal_levels.map(l => `<button class="chip" data-all="${l}">${l}</button>`).join('')}</div>
        ${r.dims.map(d => `<div class="stack-s goal-row"><b>${esc(d.label)}</b><div class="chips">${r.goal_levels.map(l => `<button class="chip" data-d="${d.id}" data-l="${l}" aria-pressed="${g[d.id] === l}">${l} ${LV[l]}</button>`).join('')}</div></div>`).join('')}
        <button class="btn primary block" id="gSave">保存目标</button></div>`;
      view.querySelectorAll('[data-d]').forEach(b => b.onclick = () => { g[b.dataset.d] = b.dataset.l; draw(); });
      view.querySelectorAll('[data-all]').forEach(b => b.onclick = () => { r.dims.forEach(d => { g[d.id] = b.dataset.all; }); draw(); });
      document.getElementById('gSave').onclick = async e => { e.currentTarget.disabled = true; try { await api('/api/next/radar/goals', { goals: g }); toast('目标已保存'); location.hash = '#/radar'; } catch (x) { toast(x.message); e.currentTarget.disabled = false; } };
    };
    draw();
  }
  async function radarTests() {
    if (!S.user) return needLogin('登录后可以做能力测评。');
    const r = await api('/api/next/radar');
    const MIN = { vocab: 3, grammar: 5, reading: 6, listening: 8, speaking: 3, writing: 10 };
    view.innerHTML = `<div class="stack"><div><a class="link small" href="#/radar">← 能力雷达</a></div><div><span class="kicker">能力测评</span><h1 class="h1">选一项，测 3–10 分钟</h1>
        <p class="muted small">不用一次测完。建议每 4 周测一轮，雷达图会把两次的变化画出来。</p></div>
      <div class="plist">${r.dims.map(d => `<a class="nrow ${d.due ? 'st st-untouched' : 'st st-solid'}" href="${DIM_TEST[d.id]}"><i class="dot" aria-hidden="true"></i>
        <span class="t"><b>${esc(d.label)}</b><span class="tiny muted">约 ${MIN[d.id]} 分钟 · ${d.assessed ? '上次 ' + new Date(d.assessed * 1000).toLocaleDateString('zh-CN') : '还没测过'}${d.due ? ' · 该测了' : ''}</span></span><span></span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div>
      <p class="tiny muted">词汇用「测词汇量」，语法用起点小测；阅读和听力各有 2–3 段短文；口语录一段回答、写作写一小段，由 AI 按 CEFR 描述评分。</p></div>`;
  }
  async function assessComprehension(kind) {
    if (!S.user) return needLogin('登录后可以做能力测评。');
    const t = await api('/api/next/assess/test?kind=' + kind), answers = [];
    let k = 0, plays = 0;
    const name = kind === 'reading' ? '阅读' : '听力';
    const show = () => {
      const p = t.passages[k]; plays = 0;
      // a title for a screen reader (the page has no visible one: the passage's own heading, or none for 听力; B8 audit)
      view.innerHTML = `<div class="stack"><h1 class="sr-only">${name}测评</h1><div class="row between"><span class="kicker">${name}测评 · 第 ${k + 1} / ${t.passages.length} 段</span><span class="pill">${esc(p.level)}</span></div>
        ${kind === 'reading' ? `<h2 class="h2">${esc(p.title)} ${aiTag()}</h2><div class="exam-passage">${esc(p.body)}</div>` :
          `<p class="small muted">听一段录音，然后回答两道题。最多听两遍，听的时候看不到原文。 ${aiTag()} ${aiVoiceNote('录音由 AI 合成', 'span', 'in')}</p><button class="btn primary block" id="aPlay">▶ 播放录音</button><p class="tiny muted" id="aNote" role="status" hidden></p><p class="tiny muted" id="aPlays"></p>`}
        <div id="aQs" ${kind === 'listening' ? 'hidden' : ''}>${p.questions.map(q => `<div class="q gq" data-i="${q.i}"><div class="prompt">${esc(q.prompt)}</div>
          ${q.options.map((o, j) => `<button class="ans" data-o="${j}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}</div>`).join('')}
          <button class="btn primary block" id="aNext" disabled>${k + 1 < t.passages.length ? '下一段' : '交卷，看结果'}</button></div></div>`;
      const chosen = {};
      view.querySelectorAll('.gq').forEach(box => box.querySelectorAll('.ans').forEach(b => b.onclick = () => {
        box.querySelectorAll('.ans').forEach(x => x.classList.toggle('chosen', x === b)); chosen[box.dataset.i] = Number(b.dataset.o);
        document.getElementById('aNext').disabled = Object.keys(chosen).length < p.questions.length;
      }));
      const play = document.getElementById('aPlay');
      // The recording is loaded before the tap, so the tap itself starts the sound (WeChat's browser allows only that).
      const voices = p.audio.voices || [];
      const loading = voices.length ? NAR.load(p.pack, voices.includes(S.voice) ? S.voice : voices[0], p.audio.version) : Promise.resolve(false);
      let loaded = null; loading.then(ok => { loaded = ok; });
      if (play) play.onclick = async () => {
        if (plays >= 2) return; plays++; play.disabled = true; play.textContent = '正在播放…';
        let over = false;
        const done = () => {
          if (over || !play.isConnected) return; over = true;
          play.disabled = plays >= 2; play.textContent = plays >= 2 ? '已经听了两遍' : '▶ 再听一遍'; document.getElementById('aQs').hidden = false; document.getElementById('aPlays').textContent = `已听 ${plays} / 2 遍`;
        };
        if (loaded === true || (loaded === null && await loading)) { NAR.play(0, null, null, done); return; }
        // No recording: the server's natural voice, sentence by sentence (the first is ready in a moment, not the whole
        // passage at once), never the browser voice unless the server cannot say it, and then the reason is shown.
        // Nothing is kept (key ''): a check is heard from the start. ✕ on the player counts as a play heard.
        const note = document.getElementById('aNote');
        LONG.start({ key: '', texts: splitSentences(p.body.replace(/^(?:[A-Z][a-z]+(?: [A-Z][a-z]+)?|[A-Z]):\s+/gm, '')), nm: null, pack: p.pack, title: '能力测评 · 听力',
          onState: (state, i, why) => { if (note.isConnected) { note.textContent = why || ''; note.hidden = !why; } if (state === 'idle') done(); },
          onDone: done }, 0);
      };
      document.getElementById('aNext').onclick = async () => {
        NAR.stop(); TTS.stop(); LONG.stop();
        p.questions.forEach(q => answers.push({ pack: p.pack, i: q.i, choice: chosen[q.i] }));
        if (++k < t.passages.length) { window.scrollTo(0, 0); show(); return; }
        let r; try { r = await api('/api/next/assess/comprehension', { kind, answers }); } catch (e) { toast(e.message); return; }
        assessResult(name, r.recorded, `<div class="stack-s">${Object.entries(r.levels).map(([lv, x]) => `<div class="row between small"><span>${lv} 难度</span><span>${x.right} / ${x.of}</span></div>`).join('')}</div>`);
      };
    };
    if (!t.passages.length) { view.innerHTML = '<div class="empty"><p>暂时没有合适的测评材料。</p><a class="btn" href="#/radar/test">返回</a></div>'; return; }
    show();
  }
  async function assessJudged(kind) {
    if (!S.user) return needLogin('登录后可以做能力测评。');
    const t = await api('/api/next/assess/task?kind=' + kind), name = kind === 'speaking' ? '口语' : '写作';
    view.innerHTML = `<div class="stack"><div><a class="link small" href="#/radar/test">← 能力测评</a></div>
      <div><span class="kicker">${name}测评 · ${esc(t.level)}</span><h1 class="h1">${esc(t.question)}</h1><p class="small">${esc(t.task)}</p><p class="tiny muted">${esc(t.limit)}。AI 按 CEFR 描述从四个方面评分，不看话题难易${kind === 'speaking' ? '，口音不扣分' : ''}。</p></div>
      ${kind === 'speaking' ? `<div class="row center">${recBtn('aMic', '开始回答', true)}<span class="small" id="aState">点录音键开始说，说完再点一下结束</span></div>` :
        `<textarea id="aText" data-draft="assess-${kind}-${draftHash(t.question)}" aria-label="你的英文回答" rows="9" lang="en" placeholder="用英文写……" autocapitalize="sentences" spellcheck="false"></textarea><div class="row between"><span class="tiny muted" id="aCount">0 词</span><button class="btn primary" id="aGo">提交</button></div>`}
      <div id="aOut"></div></div>`;
    const send = async body => {
      const out = document.getElementById('aOut'); out.innerHTML = '<p class="loading"><span class="spin"></span> AI 正在评估…</p>';
      try {
        const x = (await api('/api/next/assess/' + kind, { question: t.question, request_id: rid('as'), ...body })).result;
        if (body.text) draftDone(`assess-${kind}-${draftHash(t.question)}`);
        const DIMN = kind === 'speaking' ? { fluency: '流利度', accuracy: '准确度', range: '词汇句式', pronunciation: '发音清晰度' } : { content: '内容切题', organization: '结构衔接', accuracy: '语言准确', range: '词汇句式' };
        assessResult(name, x.recorded, `${aiMark('评分和建议由 AI 估计，仅供参考')}${x.transcript ? `<div class="small"><span class="muted">AI 听到的：</span>${esc(x.transcript)}</div>` : ''}
          <div class="ab-list">${Object.entries(x.scores).map(([k2, v]) => `<div class="ab"><span class="nm">${DIMN[k2] || k2}</span><span class="vbar"><i data-w="${v * 20}"></i></span><span class="lv">${v} / 5</span></div>`).join('')}</div>
          <div class="stack-s" data-ex-block>${x.strength ? `<div class="small"><span class="ok">做得好：</span><span data-ex>${esc(x.strength)}</span></div>` : ''}${(x.next || []).map(s => `<div class="small">· <span data-ex>${esc(s)}</span></div>`).join('')}</div>`);
      } catch (e) { out.innerHTML = ''; toast(e.message); }
    };
    if (kind === 'speaking') {
      const mic = document.getElementById('aMic'), st = document.getElementById('aState');
      mic.onclick = () => { st.textContent = MIC.busy() ? '' : '正在录音，说完再点一下'; MIC.toggle(mic, 75, async blob => {
        st.textContent = ''; let audio;
        try { audio = await MIC.payload(blob); } catch (e) { toast(e.message); return; }  // too long: said, not lost silently
        send({ audio });
      }); };
    } else {
      const ta = document.getElementById('aText'), cnt = document.getElementById('aCount');
      ta.oninput = () => { cnt.textContent = (ta.value.match(/[A-Za-z]+(?:'[A-Za-z]+)?/g) || []).length + ' 词'; };
      document.getElementById('aGo').onclick = () => send({ text: ta.value });
    }
  }
  function assessResult(name, rec, detail) {
    view.innerHTML = `<div class="stack"><div class="done-burst" aria-hidden="true">${doneRing}</div>
      <div class="tc"><span class="kicker">${esc(name)}测评结果</span><h1 class="h1">${rec ? `约 ${esc(rec.level)} · ${rec.score} 分` : '已完成'}</h1>
        ${rec ? `<p class="small muted">目标 ${esc(rec.goal)} = 100 分。这是一次测评的估计，和平时练习结合起来看更准。</p>` : ''}</div>
      ${detail}<div class="row center"><a class="btn" href="#/radar/test">测别的项目</a><a class="btn primary" href="#/radar">看雷达图</a></div></div>`;
    requestAnimationFrame(() => requestAnimationFrame(() => view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
    if (S.user) refreshHome().catch(() => {});
  }
  /* ---------- 操作指南: the same source as the PDF (flow/public/guide/guide.md, rendered by user_guide.py) ---------- */
  async function guideView(id) {
    if (!S.guide) S.guide = await api('/api/next/guide');
    const g = S.guide;
    if (tipSeen('guide') === false) TIPS.mark('guide');  // found it: 「第一次用？看操作指南」 is not needed any more
    // 全英文界面: the guide stays Chinese for now (its English is 第 3 段): one line says so, and the chapters are left as they are
    view.innerHTML = `<h1 class="h1">操作指南</h1>${uiLang() === 'en' ? '<p class="small" lang="en">The guide is in Chinese for now.</p>' : ''}<p class="muted small">${esc(g.updated)}</p>
      <div class="row">${g.pdf ? `<a class="btn small primary" href="${g.pdf}" download="语流操作指南.pdf">下载 PDF 版</a>` : ''}<a class="btn small" href="#/practice">去练习</a></div>
      <label class="field section"><span class="sr-only">在指南里搜索</span><input class="guide-search" id="gq" type="search" placeholder="搜一搜：比如 复习、录音、提醒" autocomplete="off"></label>
      <nav class="card flat guide-toc" id="gtoc" aria-label="指南目录" data-zh>${g.chapters.map((ch, k) => `<a href="#/guide/${ch.id}" data-ch="${ch.id}"><span class="n">${k + 1}</span><span>${esc(ch.title)}</span></a>`).join('')}</nav>
      <p class="muted small" id="gnone" hidden>没有找到，换个词试试，或者看看「常见问题」。</p>
      <div class="guide-body" data-zh>${g.chapters.map((ch, k) => `<section id="g-${ch.id}" data-ch="${ch.id}"><h2>${k + 1}. ${esc(ch.title)}</h2>${ch.html}</section>`).join('')}</div>
      <div class="section row"><a class="btn small" href="#/guide">回到目录</a>${g.pdf ? `<a class="btn small" href="${g.pdf}" download="语流操作指南.pdf">下载 PDF 版</a>` : ''}</div>`;
    const q = document.getElementById('gq'), none = document.getElementById('gnone');
    q.oninput = () => {
      const t = q.value.trim().toLowerCase();
      let shown = 0;
      g.chapters.forEach(ch => {
        const hit = !t || ch.text.toLowerCase().includes(t) || ch.title.toLowerCase().includes(t);
        view.querySelectorAll(`[data-ch="${ch.id}"]`).forEach(el => { el.hidden = !hit; });
        if (hit) shown++;
      });
      none.hidden = shown > 0;
    };
    // #/guide/<id> (a link from anywhere, or opened directly): to that chapter. The page keeps settling after it is drawn
    // (the router's own scroll, pictures, the enter animation), so it is put there again a few times until the reader
    // scrolls themselves.
    if (id) {
      const sec = document.getElementById('g-' + id);
      if (sec) {
        let mine = true; const off = () => { mine = false; };
        ['wheel', 'touchstart', 'keydown'].forEach(t => addEventListener(t, off, { once: true, passive: true }));
        const go = () => { if (mine && sec.isConnected) sec.scrollIntoView({ block: 'start' }); };
        requestAnimationFrame(go); [120, 400, 1000].forEach(ms => setTimeout(go, ms));
      }
    }
  }

  /* ---------- 练习: every kind of practice in one place, grouped by skill, with one suggestion on top ---------- */
  // B9's batch 1 (the user, 2026-11-26 15:3x; ui-refine/batch1/practice-*.png): the suggestion is a white card with the
  // page's one green button under it; each group a white card, two columns, one row per practice (44 high, an icon in
  // front, 99-icons.css); something due shows a small ink dot, the number said to a screen reader. A row shows its name
  // only; the line on what it is for stays where it says what AI does. What has an entry of its own elsewhere is not
  // repeated here (今天的材料 is 今日; 周报 and 我的进步 are in 我的; 能力雷达 is its own tab).
  // Each practice: [href, title, one line on what it is for, icon (00-icons.js), 'due' for the word review's count].
  const PRACTICE = [
    ['语法', 'right', [
      ['#/graph', '知识图谱', '44 个语法点按顺序连成路线，点亮一个学一个', 'graph'],
      ['#/mix', '混合练习', '几个语法点打乱一起练，记得更牢', 'shuffle']]],
    ['听和读', 'left', [
      ['#/easy', '轻松读', '读比你低一级的短文，练速度、攒阅读量', 'read'],
      ['#/library', '全部材料', '按话题和级别挑一篇来学', 'layers'],
      ['#/import', '我的文章', '贴一段任何英文，变成可以学的材料', 'docpen']]],
    ['说和写', 'right', [
      ['#/speak', '口语路线', '12 个生活和校园情景，和 AI 对话', 'chat'],
      ['#/sounds', '发音入门', '中国学习者容易混的音，听辨再跟读', 'mic']]],
    ['单词', 'left', [
      ['#/review', '复习单词', '到期的单词和短语，一张张过', 'stack', 'due'],
      ['#/words/confuse', '词汇辨析', '最容易混的词放在一起练', 'venn'],
      ['#/vocab/plan', '背词计划', '换词书、改每天学多少', 'cal'],
      ['#/vocab/test', '测词汇量', '5 分钟估一估你认识多少词', 'gauge']]],
    ['考试和测评', 'right', [
      ['#/exam', '考试练习', '中考高考、四六级、考研、专四专八、雅思，限时做', 'exam'],
      ['#/placement', '语法起点小测', '16 题定出你的语法起点', 'flag']]]];
  // A row: the icon, the name, a dot when something is due (its number in the row's name for a screen reader)
  function practiceRow([href, title, line, icon], n, tap) {
    return `<a class="pc-row" href="${href}"${tap ? ` data-tap="${tap}"` : ''}${n ? ` aria-label="${title}，有 ${n} 项到期"` : ''}>${fi(icon)}
      <span class="pc-name">${title}${/AI/.test(line) ? `<span class="pc-sub">${line}</span>` : ''}</span>${n ? '<i class="pc-dot" aria-hidden="true"></i>' : ''}</a>`;
  }
  const practiceGroup = (name, rows) => `<section class="pc-card" aria-label="${name}"><h2 class="pc-h">${name}</h2>${rows}</section>`;
  // 复习 (the user, 2026-11-25: 「单词复习不要和其他的东西混在一起，其他东西复习单独开个板块」): the mistakes, sentence
  // patterns and whole sentences due again (#/review/other, B2's review-split), with 错题本 beside it; the 「练习」 tab
  // carries their dot (02-shell.js setDueBadge). Nothing due: the row stays, so the way in is always there.
  function reviewGroup(st) {
    if (!S.user) return '';
    const n = st ? st.other_due || 0 : 0;
    return practiceGroup('复习', practiceRow(['#/review/other', '错题和句型', '', 'retry'], n, 'practice-review-other') + practiceRow(['#/cards/mistake', '错题本', '', 'bookx'], 0));
  }
  async function practiceView() {
    const st = S.home && S.home.stats, due = st ? (st.due || 0) + (st.new || 0) : 0;
    const col = side => (side === 'left' ? reviewGroup(st) : '') + PRACTICE.filter(g => g[1] === side)
      .map(([name, , items]) => practiceGroup(name, items.map(x => practiceRow(x, x[4] === 'due' ? due : 0)).join(''))).join('');
    view.innerHTML = `<h1 class="h1">练习</h1>
      <div id="pSuggest">${practiceTip(null, due)}</div>
      <div class="pc-cols"><div class="pc-col">${col('left')}</div><div class="pc-col">${col('right')}</div></div>
      ${tipSeen('guide') === false ? '<a class="guide-cta link" href="#/guide" data-tip-seen="guide">第一次用？看操作指南 ›</a>' : ''}`;  // 一次性 (08-tips.js)
    if (S.user) api('/api/next/radar').then(r => {
      const el = document.getElementById('pSuggest'); if (el && r && r.gap) el.innerHTML = practiceTip(r, due);
    }).catch(() => { /* the plain suggestion stays */ });
  }
  // 今天建议: the skill furthest from the learner's goal (能力雷达), else the words due, else today's plan. A white card
  // (its icon the one accent tile on the page) and the page's one green button under it.
  const TIP_ICON = { '#/library': 'layers', '#/easy': 'read', '#/vocab/plan': 'cal', '#/mix': 'shuffle', '#/speak': 'chat', '#/': 'docpen', '#/review': 'stack' };
  function practiceTip(radar, due) {
    const d = radar && radar.dims.find(x => x.id === radar.gap);
    const [href, head, sub, go, icon] = d ? [d.href, d.tip, `${d.label}离你的目标最远，先练它`, `去练${d.label}`, TIP_ICON[d.href] || 'target']
      : due ? ['#/review', `有 ${due} 个词等你复习`, '先复习再学新的，记得最牢。', '开始复习', 'stack']
      : ['#/', '先做今天的计划', '今日页已经按你的水平排好了顺序。', '打开今日', 'target'];
    return `<section class="pc-tip" aria-labelledby="pcTipH"><div class="pc-tip-t"><h2 class="pc-tip-h" id="pcTipH">今天建议</h2><b class="pc-tip-b">${esc(head)}</b><span class="pc-tip-s">${esc(sub)}</span></div>
      <span class="pc-tip-i" aria-hidden="true">${fi(icon)}</span></section>
      <a class="btn primary block pc-go" href="${esc(href)}" data-tap="practice-tip">${esc(go)}</a>`;
  }
  /* ---------- cards ---------- */
  /* ---------- words: one FSRS memory queue for word books, saved words/expressions and imports ---------- */
  function highlight(ctx, text) {
    if (!ctx) return '';
    const i = ctx.toLowerCase().indexOf(text.toLowerCase());
    return i < 0 ? esc(ctx) : esc(ctx.slice(0, i)) + '<mark>' + esc(ctx.slice(i, i + text.length)) + '</mark>' + esc(ctx.slice(i + text.length));
  }
  // A sentence with the word (as it appears there) turned into a gap, or highlighted once revealed.
  function gapped(sentence, form, open) {
    const re = new RegExp(`(^|[^A-Za-z])(${form.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})(?![A-Za-z])`, 'i');
    const m = re.exec(sentence); if (!m) return esc(sentence);
    const at = m.index + m[1].length, w = sentence.slice(at, at + m[2].length);
    return esc(sentence.slice(0, at)) + (open ? `<span class="gap open">${esc(w)}</span>` : `<span class="gap" aria-label="空格">${' '.repeat(Math.max(4, w.length))}</span>`) + esc(sentence.slice(at + w.length));
  }
  const pct = r => r == null ? '' : Math.round(r * 100) + '%';
  const SOURCE = { book: '词书', saved: '收藏', import: '导入' };
  // By calendar day, not "within 24 hours": a card due tomorrow morning is not "later today".
  function dueText(t) {
    const ms = t * 1000; if (ms <= Date.now()) return '该复习了';
    const day = x => { const d = new Date(x); d.setHours(0, 0, 0, 0); return d.getTime(); };
    const n = Math.round((day(ms) - day(Date.now())) / 864e5);
    return n === 0 ? '今天晚些时候复习' : n === 1 ? '明天复习' : `${n} 天后复习`;
  }
  const WEEKDAY = '日一二三四五六';
  // The 单词 page's tool row: [link or button id, label, icon paths].
  const WORD_TOOLS = [['#/vocab/plan', '背词计划', 'cal'], ['#/words/confuse', '词汇辨析', 'venn'], ['#/vocab/test', '测词汇量', 'gauge'], ['imp', '导入', 'inbox']];  // B9's icons (00-icons.js)
  // 「认识」放在 (我的 → 使用习惯; a trial student and the owner, 2026-11-25): on the right by default, as in most word apps;
  // the buttons of the review and of the vocabulary test, their keys (1 2 3, and ← → by their place on screen) and the
  // swipe all follow it: the side 「认识」 is on is the way to swipe for it. Kept on this device, like 单词读音方式.
  // 复习时的轻触震动 (语流 C1; the iOS app's own setting turns it off): a light tap where the app can, nothing in a browser.
  // Turning a card is a light 'select'; a rating says how it went (success, a light tap for 模糊, warning — never error,
  // a word forgotten is no fault); 撤销 and 太简单了 a light tap.
  // 复习进度的实时活动 (语流 C1; the iOS app, off unless the learner turns it on): the lock screen and the Dynamic Island
  // say 「复习单词 done / total」 while a round of words goes on; ended (the last numbers kept a minute) when the round is
  // over or the page is left. Words only. Nothing in a browser; an app without it answers nothing.
  let ACTIVITY = null;
  function activity(kind, done, total) {
    try {
      if (!(window.FlowApp && FlowApp.has && FlowApp.has('activity'))) return;
      if (kind === 'end' && !ACTIVITY) return;
      ACTIVITY = kind === 'end' ? null : { done, total };
      FlowApp.call('activity.' + kind, { done, total }).catch(() => {});
    } catch (e) { /* no app */ }
  }
  function activityEnd() { if (ACTIVITY) activity('end', ACTIVITY.done, ACTIVITY.total); }
  function haptic(kind) { try { if (window.FlowApp && FlowApp.has && FlowApp.has('haptic')) FlowApp.call('app.haptic', { kind }).catch(() => {}); } catch (e) { /* no app */ } }
  const KNOW = {
    side() { try { return localStorage.getItem('flow-know-side') === 'left' ? 'left' : 'right'; } catch (e) { return 'right'; } },
    set(v) { try { if (v === 'left') localStorage.setItem('flow-know-side', 'left'); else localStorage.removeItem('flow-know-side'); } catch (e) { /* private mode */ } prefSave('know', v === 'left' ? 'left' : 'right'); },  // also with the account (07-prefs.js)
    // the choices in their order on screen, from the 「认识」 end of the list
    order(list) { return this.side() === 'right' ? list.slice().reverse() : list.slice(); },
    // what a swipe does, for onSwipe(right, left): 「认识」's side gets know
    swipe(know, other) { return this.side() === 'right' ? [know, other] : [other, know]; },
    // keys by place: 1 2 3 left to right, ← the leftmost, → the rightmost
    keys(acts) { const m = {}; acts.forEach((f, k) => { m[k + 1] = f; }); m.ArrowLeft = acts[0]; m.ArrowRight = acts[acts.length - 1]; return m; },
    // 点卡片作答 (the owner, 2026-11-25): the card's left, middle and right thirds answer like the buttons below them, so
    // 认识 is on its side too. On by default where a finger points; with a mouse a click into the card (to select a word)
    // should not answer, so there it is off until chosen in 我的 → 使用习惯.
    tap() { try { const v = localStorage.getItem('flow-tap-zones'); return v ? v === '1' : matchMedia('(pointer: coarse)').matches; } catch (e) { return false; } },
    setTap(on) { try { localStorage.setItem('flow-tap-zones', on ? '1' : '0'); } catch (e) { /* private mode */ } prefSave('tap', on ? 'on' : 'off'); },
    // 复习卡 简洁 / 详细 (words-modes-plan.md; the owner, 2026-11-25): new words and reviews apart, new words detailed (the
    // first look is the one to take in), reviews simple (quick). Only what is shown changes: the front asks the same
    // (detailed adds a grey line of tags and history, nothing of the answer), so a rating means the same in both.
    view(kind) { const d = kind === 'new' ? 'detailed' : 'simple'; try { const v = localStorage.getItem('flow-card-view-' + kind); return v === 'simple' || v === 'detailed' ? v : d; } catch (e) { return d; } },
    setView(kind, v) { try { localStorage.setItem('flow-card-view-' + kind, v); } catch (e) { /* private mode */ } prefSave(kind === 'new' ? 'card_new' : 'card_review', v); },
  };
  // 这次什么时候复习 (a trial student, 2026-11-25: not everyone is free at the same hour every day): a time today or
  // tomorrow for the next reminder only (vocab_service.set_once), then every day at the usual hour again. Opened from the
  // plan page, the end of a review and 今日's finished plan (语流 08).
  const ONCE_SLOTS = [[0, 12, 30, '今天中午 12:30'], [0, 18, 0, '今天傍晚 18:00'], [0, 21, 0, '今晚 21:00'], [1, 8, 0, '明早 8:00'], [1, 12, 30, '明天中午 12:30'], [1, 20, 0, '明晚 20:00']];
  function onceLabel(sec) {
    const d = new Date(sec * 1000), t = new Date();
    return `${d.toDateString() === t.toDateString() ? '今天' : '明天'} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
  }
  // 语流 20's iOS app (shared notes ios-app.md): its local notifications follow the reminder; the page tells it whenever
  // the reminder changes (the app also asks for it when it opens). Not in the app: nothing.
  const appNotify = r => { try { if (window.FlowApp && FlowApp.has('notify')) FlowApp.notify.sync(r); } catch (e) { /* the app's own business */ } };
  // the device the app runs on, and where its notifications are turned on (FlowApp.platform; 语流 22's desktop app, 2026-11-25)
  const APP_PLACES = { ios: ['这台 iPhone', 'iPhone 的「设置 → 语流 → 通知」'], android: ['这台手机', '手机的「设置 → 应用 → 语流 → 通知」'],
    windows: ['这台电脑', 'Windows 的「设置 → 系统 → 通知」'], macos: ['这台 Mac', 'Mac 的「系统设置 → 通知」'] };
  const appPlace = () => APP_PLACES[(window.FlowApp && FlowApp.platform) || 'ios'] || ['这台设备', '系统设置里的「通知」'];
  // Every bridge call answers a Promise (native-bridge.md 2: iOS can only answer asynchronously): whether the app's
  // reminder is on is awaited, never compared as it comes (语流 20, 2026-11-25: 「已开启」 never showed in the apps).
  // permission() is the app's reminder: 'undetermined' again after off(); ask() true turns it on again.
  const appOn = async () => { try { return (await Promise.resolve(FlowApp.notify.permission())) === 'granted'; } catch (e) { return false; } };
  // the app's row on the plan page: off, a button to turn it on; on, said so, with 关闭 where the app can (notify.off: iOS,
  // Android) or the system's settings where it opens them (notify.settings); neither: the system's settings say how
  function appRowHTML(on) {
    const [place] = appPlace(), at = `在${place}${/[A-Za-z]$/.test(place) ? ' ' : ''}上`;
    if (!on) return `<button class="btn small" type="button" id="rApp">到点用 App 通知提醒</button><span class="muted tiny" id="rAppNote">${at}，按上面的时间弹通知，不用邮箱</span>`;
    return `<span class="small" id="rAppOn">已开启：${at}到点用 App 通知提醒</span>${typeof FlowApp.notify.off === 'function' ? '<button class="link small hit44" type="button" id="rAppOff">关闭</button>'
      : typeof FlowApp.notify.settings === 'function' ? '<button class="link small hit44" type="button" id="rAppSet">通知设置</button>' : ''}`;
  }
  async function remindOnce(after) {
    if (!S.user) return needLogin('登录后才能设复习提醒。');
    let r, forecast; try { const o = await api('/api/next/vocab'); r = o.reminder; forecast = o.forecast; } catch (e) { toast(e.message); return; }
    const now = Date.now(), slot = ([d, h, m]) => { const x = new Date(); x.setDate(x.getDate() + d); x.setHours(h, m, 0, 0); return x.getTime(); };
    const picks = ONCE_SLOTS.filter(s => slot(s) > now + 30 * 60000).slice(0, 4);
    const last = new Date(); last.setDate(last.getDate() + 1); last.setHours(23, 59, 0, 0);
    const local = ms => { const d = new Date(ms); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); };
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">今天或明天什么时候有空复习？</h2>
      <p class="muted small">选一个时间，下一次提醒就在那时候；之后回到每天 ${r.hour}:00。</p>
      <div class="chips" id="oncePicks" role="group" aria-labelledby="sheetTitle">${picks.map(s => `<button class="chip" type="button" data-at="${slot(s) / 1000}" aria-pressed="${r.once === slot(s) / 1000}">${s[3]}</button>`).join('')}</div>
      <div class="row"><label class="small" for="onceOwn">自己选时间：</label><input id="onceOwn" type="datetime-local" min="${local(now + 10 * 60000)}" max="${local(last.getTime())}"><button class="btn small" type="button" id="onceGo">好</button></div>
      <div id="onceDone" aria-live="polite"></div>
      ${r.once ? `<button class="link small" type="button" id="onceOff">取消这次（${onceLabel(r.once)}），按每天 ${r.hour}:00</button>` : ''}
      <button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      const done = card.querySelector('#onceDone');
      const pick = async at => {
        try {
          const x = await api('/api/next/vocab/reminder/once', { at });
          appNotify({ ...x, forecast });
          done.innerHTML = `<p class="small" id="onceOk"><b>好，${onceLabel(x.once)}提醒你复习。</b>${x.has_email ? '到时发邮件提醒（有词要复习才发）。' : '账号还没绑定邮箱，可以'}<a class="btn small" href="/api/next/vocab/reminder.ics?at=${x.once}">加到手机日历</a></p>`;
          if (after) after(x);
        } catch (e) { toast(e.message); }
      };
      card.querySelectorAll('[data-at]').forEach(b => b.onclick = () => { card.querySelectorAll('[data-at]').forEach(y => y.setAttribute('aria-pressed', String(y === b))); pick(Number(b.dataset.at)); });
      card.querySelector('#onceGo').onclick = () => { const v = card.querySelector('#onceOwn').value; if (!v) { toast('先选一个时间'); return; } pick(Math.round(new Date(v).getTime() / 1000)); };
      const off = card.querySelector('#onceOff');
      if (off) off.onclick = async () => { try { const x = await api('/api/next/vocab/reminder/once', { at: null }); appNotify({ ...x, forecast }); toast(`好，按每天 ${x.hour}:00 提醒`); off.remove(); if (after) after(x); } catch (e) { toast(e.message); } };
    });
  }
  function dayLabel(iso) { const [y, m, d] = iso.split('-').map(Number); return (y !== new Date().getFullYear() ? y + '年' : '') + m + '月' + d + '日'; }

  async function vocabView(q, page, f) {
    if (!S.user) {
      view.innerHTML = `<h1 class="h1">单词</h1><div class="empty"><div class="big">☆</div><p>选一本词书，每天学几个新词，系统按遗忘曲线安排复习；<br>读文章时点词收藏的单词和表达，也会一起复习。</p>
        <div class="row center"><button class="btn primary" id="lg">登录 / 注册</button><a class="btn" href="#/vocab/test">先测测词汇量</a></div></div>`;
      document.getElementById('lg').onclick = () => openLogin(); return;
    }
    q = q || ''; page = page || 1; f = f || '';
    const [o, list] = await Promise.all([api('/api/next/vocab'), api('/api/next/cards?q=' + encodeURIComponent(q) + '&page=' + page + '&f=' + f)]);
    const n = o.due + o.new;
    const start = new Date(); start.setHours(0, 0, 0, 0);
    const maxF = Math.max(1, ...o.forecast), maxC = Math.max(1, ...o.calendar.map(d => d.n));
    // r28: under a cap (单词每天, or the day's plan) the card shows today's share; what is beyond it waits (later)
    const capLine = o.cap ? ` · 单词每天 ${o.cap} 分钟` : '';
    const bk = o.book, nb = bk && bk.next;
    let rested = false; try { rested = !!(bk && localStorage.getItem('flow-book-rest-' + bk.id)); } catch (e) { /* private mode */ }
    // B9's 第一批 (the user, 2026-11-26: 「可以，第二批第三批一起做」; ui-refine/batch1/spec.md, README 「单词」): white blocks
    // (titles inside, a grey line on the right), one full-width main button, the word book a block of its own, four equal
    // tool tiles, the stats a fold, a three-way switch by the search, one word a row. Every entry and state of before stays.
    const row = (icon, label, val) => `<div class="wp-row">${fi(icon)}<span>${label}</span><b>${val}</b></div>`;
    const note = (o.catch_up ? `<p class="wp-note" id="catchUp">补积压：还剩 ${o.catch_up.left} 个，大约 ${o.catch_up.days} 天补完。最容易忘的排在前面，补完之前先不加新词。</p>`
      : o.new_paused ? '<p class="wp-note" id="newPaused">到期的词比较多，今天先复习，新词明天继续。</p>' : '');
    const book = o.book ? `<a class="wp-blk wp-book" href="#/vocab/plan">${fiTile('book')}
        <span class="wp-bk"><span class="wp-bk-t"><b>《${esc(o.book.title)}》</b><span class="wp-num">${o.book.started} / ${o.book.size - (o.book.skipped || 0)}</span></span>
          <span class="vbar"><i data-w="${o.book.started / Math.max(1, o.book.size - (o.book.skipped || 0)) * 100}"></i></span>
          <span class="wp-bk-s">${o.plan ? `每天 ${o.plan.daily_new} 个新词 · ` : ''}${o.book.finish ? '预计 ' + dayLabel(o.book.finish) + '学完' : '已全部学过'}${o.book.skipped ? ` · 跳过 ${o.book.skipped} 个常用词` : ''}${o.plan ? ` · 目标记住率 ${Math.round(o.plan.retention * 100)}%` : ''}</span>
          <span class="wp-link">换词书或改计划 ›</span></span></a>` : '';
    const soon = bk && !bk.done && bk.soon ? `<p class="wp-note" id="bookSoon">《${esc(bk.title)}》还剩 ${bk.left} 个新词，大约 ${bk.days} 天背完。${nb ? `接下来推荐《${esc(nb.title)}》：你学过的词会跳过，还剩约 ${nb.new.toLocaleString()} 个新词。` : ''}</p>` : '';
    const done = !bk || !bk.done || rested ? '' : `<section class="wp-blk stack-s" id="bookDone"><h2 class="wp-blk-t">《${esc(bk.title)}》背完了</h2>
        <p class="wp-note">${bk.exam_first ? '离考试还有一段时间，先把学过的词复习牢，考完再换下一本。' : nb ? `接下来推荐《${esc(nb.title)}》：你学过的词会跳过，还剩约 ${nb.new.toLocaleString()} 个新词。` : '可以在背词计划里换一本接着背。'}</p>
        <div class="row">${nb && !bk.exam_first ? `<button class="btn small" id="bookNext">换成《${esc(nb.title)}》</button><button class="btn small" id="bookRest">先只复习</button>`
          : bk.exam_first ? `<button class="btn small" id="bookRest">先只复习到考试</button>${nb ? `<button class="btn small" id="bookNext">换成《${esc(nb.title)}》</button>` : ''}`
          : '<a class="btn small" href="#/vocab/plan">换一本</a><button class="btn small" id="bookRest">先只复习</button>'}</div></section>`;
    // today: what is due (复习, 新词, about how long), the one main button under it; done, or more waiting for later days
    const today = o.plan
      ? `<div class="vtoday wp-top"><section class="wp-blk wp-today">
          ${n ? `<div class="wp-blk-h"><h2 class="wp-blk-t">今天要背</h2><span class="wp-blk-r">约 ${o.minutes} 分钟</span></div>${row('again', '复习', o.due + ' 个')}${row('spark', '新词', o.new + ' 个')}
                 ${o.cap || o.done_today ? `<p class="wp-note">${[o.cap ? `单词每天 ${o.cap} 分钟` : '', o.done_today ? `今天已完成 ${o.done_today} 次` : ''].filter(Boolean).join(' · ')}</p>` : ''}`
            : o.later ? `<div class="wp-blk-h"><h2 class="wp-blk-t">今天的单词做完了</h2></div><p class="wp-note" id="laterLine">还有 ${o.later} 个复习留到之后几天，想多背可以继续${capLine}</p>`
            : `<div class="wp-blk-h"><h2 class="wp-blk-t">今天的都完成了</h2></div><p class="wp-note">已完成 ${o.done_today} 次 · 明天预计 ${o.forecast[1]} 个复习</p>`}
          ${note}</section>
          ${n ? '<a class="btn primary wp-go" href="#/review">开始背单词</a>' : o.later ? '<a class="btn primary wp-go" href="#/review/more" id="moreRev">继续复习</a>' : '<button class="btn primary wp-go" type="button" id="moreNew">再学 10 个</button>'}
          ${book}${soon}${done}</div>`
      : `<section class="wp-blk wp-today stack-s"><h2 class="wp-blk-t">开始背单词</h2><p class="wp-lead">选一本词书，每天几个新词，按遗忘曲线复习</p>
          <p class="wp-note">例句来自你读的文章，还能听原文录音。不选词书也可以：读文章时点词收藏，收藏的词同样按遗忘曲线复习。</p>
          ${n ? `<div class="wp-row">${fi('again')}<span>收藏的词：复习 ${o.due} · 待学 ${o.new}</span><a class="wp-link" href="#/review">开始复习 ›</a></div>` : ''}</section>
        <a class="btn primary wp-go" href="#/vocab/plan">选词书</a><p class="tc"><a class="wp-link" href="#/vocab/test">先测词汇量（约 3 分钟）›</a></p>`;
    let statsOpen = false; try { statsOpen = localStorage.getItem('flow-words-stats') === 'open'; } catch (e) { /* private mode */ }
    const est = o.plan && o.plan.estimate;
    const TAP = { '#/vocab/plan': 'words-plan', '#/words/confuse': 'words-confuse', '#/cards/mistake': 'words-mistake', '#/vocab/test': 'words-test', imp: 'words-import' };
    // no words yet (a new account): the block above says how to start; counts of 0, a search box and filters wait for words
    const none = !o.total;
    view.innerHTML = `<div class="wp-head"><h1 class="h1">单词</h1>${none ? '' : `<span class="wp-sub">共 ${o.total} 个 · 已掌握 ${o.mastered}</span>`}</div>
      ${today}
      <nav class="tools wp-tools" aria-label="单词工具">${WORD_TOOLS.map(([to, label, icon]) => `${to[0] === '#' ? `<a href="${to}" data-tap="${TAP[to]}">` : `<button type="button" id="${to}" data-tap="${TAP[to]}">`}
        ${fi(icon)}<span>${label}</span>${to[0] === '#' ? '</a>' : '</button>'}`).join('')}</nav>
      ${none ? '' : `<details class="fold wp-stats" id="vStats"${statsOpen ? ' open' : ''}><summary data-tap="words-stats">${fi('bars')}<b>统计和复习预测</b><span class="wp-r">在学 ${o.learning} · 已掌握 ${o.mastered}${est ? ` · 词汇量约 ${est.toLocaleString()}` : ''}</span></summary>
        <div class="stack-s wp-stats-in">
        <div class="stat-grid"><div class="card sunk stat"><b>${o.mastered}</b><span class="tiny muted">已掌握</span></div><div class="card sunk stat"><b>${o.learning}</b><span class="tiny muted">学习中</span></div>
          <div class="card sunk stat"><b>${est ? est.toLocaleString() : '—'}</b><span class="tiny muted">${est ? '词汇量估计' : '<a class="link" href="#/vocab/test">测词汇量</a>'}</span></div></div>
        <div class="row between"><b class="small">未来 7 天的复习量</b><span class="tiny muted">按你的记忆情况算出</span></div>
        ${o.forecast.some(Boolean) ? `<div class="forecast" aria-label="未来 7 天复习量">${o.forecast.map((v, k) => { const d = new Date(start.getTime() + k * 864e5); return `<div><span class="n">${v || ''}</span><i data-h="${v / maxF * 100}"></i><span class="tiny muted">${k === 0 ? '今天' : k === 1 ? '明天' : '周' + '日一二三四五六'[d.getDay()]}</span></div>`; }).join('')}</div>`
          : '<p class="muted tiny">开始学习后，这里会显示每天大约要复习多少个。</p>'}
        <div class="cal" aria-label="最近 5 周每天复习次数">${o.calendar.map(d => `<i class="l${d.n ? Math.min(4, Math.ceil(d.n / maxC * 4)) : 0}" title="${d.day}：${d.n} 次"></i>`).join('')}</div></div></details>
      <div class="wp-search"><form class="searchrow" id="sf" role="search"><input type="search" name="q" aria-label="搜索单词、意思或原句" enterkeyhint="search" placeholder="搜单词、意思${TOUCH ? '' : '（按 / 跳到这里）'}" value="${esc(q)}"></form>
        <div class="seg wp-filt" role="group" aria-label="筛选">${[['', '全部'], ['word', '单词'], ['phrase', '表达']].map(([k, l]) => `<button type="button" data-f="${k}" aria-pressed="${f === k}">${l}</button>`).join('')}</div></div>
      <div id="listSlot">${listHTML(list, q, page, f)}</div>`}
      ${o.total ? '<p class="tc"><button class="link small wp-link" type="button" id="wbExport" data-tap="words-export">导出单词本：Excel 表格或 Anki ›</button></p>' : ''}`;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; });
      view.querySelectorAll('.forecast i').forEach(i => { i.style.height = Math.max(3, i.dataset.h) + '%'; });
    }));
    // Filters, search and pages swap only the list: the rest of the page stays put (no reload flash, no lost scroll).
    const mn = document.getElementById('moreNew');
    if (mn) mn.onclick = async () => {  // today's words are done and the learner wants more: one extra batch now
      mn.disabled = true;
      try { const r = await api('/api/next/vocab/more', { n: 10 }); if (r.added) location.hash = '#/review/more'; else { toast('词书里的词都学过了'); } }
      catch (e) { toast(e.message); mn.disabled = false; }
    };
    const bn = document.getElementById('bookNext');
    if (bn) bn.onclick = async () => {  // the next book, with the plan's pace kept; studied words stay and are skipped
      bn.disabled = true;
      try { await api('/api/next/vocab/plan', { book: nb.id, daily_new: o.plan.daily_new, retention: o.plan.retention }); toast(`已换成《${nb.title}》`); refreshHome().catch(() => {}); vocabView(); }
      catch (e) { toast(e.message); bn.disabled = false; }
    };
    const br = document.getElementById('bookRest');
    if (br) br.onclick = () => { try { localStorage.setItem('flow-book-rest-' + bk.id, '1'); } catch (e) { /* private mode */ } const d = document.getElementById('bookDone'); if (d) d.remove(); };
    const st = { q, page, f };
    const reload = async () => {
      const slot = document.getElementById('listSlot'); slot.classList.add('busy');
      try { const l = await api('/api/next/cards?q=' + encodeURIComponent(st.q) + '&page=' + st.page + '&f=' + st.f); slot.innerHTML = listHTML(l, st.q, st.page, st.f); bindList(); }
      catch (e) { toast(e.message); } finally { slot.classList.remove('busy'); }
    };
    const bindList = () => {
      view.querySelectorAll('#listSlot [data-card]').forEach(b => b.onclick = () => cardSheet(Number(b.dataset.card), reload));
      const pv = document.getElementById('pv'), nx = document.getElementById('nx');
      if (pv) pv.onclick = () => { st.page--; reload().then(() => bringIntoView(document.getElementById('sf'))); };
      if (nx) nx.onclick = () => { st.page++; reload().then(() => bringIntoView(document.getElementById('sf'))); };
      const sc = document.getElementById('sfClear'), sa = document.getElementById('sfAll');
      if (sc) sc.onclick = () => { const i = document.querySelector('#sf input'); if (i) { i.value = ''; if (!TOUCH) i.focus(); } st.q = ''; st.page = 1; reload(); };
      if (sa) sa.onclick = () => { st.f = ''; st.page = 1; view.querySelectorAll('[data-f]').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.f === ''))); reload(); };
    };
    if (!none) document.getElementById('sf').onsubmit = e => { e.preventDefault(); st.q = e.target.q.value.trim(); st.page = 1; reload(); };
    view.querySelectorAll('[data-f]').forEach(b => b.onclick = () => { st.f = b.dataset.f; st.page = 1; view.querySelectorAll('[data-f]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); reload(); });
    document.getElementById('imp').onclick = importSheet;
    const wx = document.getElementById('wbExport'); if (wx) wx.onclick = dataSheet;
    const vs = document.getElementById('vStats');
    if (vs) vs.addEventListener('toggle', () => { try { localStorage.setItem('flow-words-stats', vs.open ? 'open' : ''); } catch (e) { /* private mode */ } });
    bindList();
  }
  // 错题本 (练习 → 复习 → 错题本; review-split-plan.md, 语流 B9 and A0): the mistakes on a page of their own under 练习 —
  // not the word page with a filter — with a way to review the ones due (#/review/other), a search, and nothing else
  async function mistakeView(q, page) {
    if (!S.user) return needLogin('登录后才能看错题本。');
    q = q || ''; page = page || 1;
    const st = { q, page };
    const [list, ov] = await Promise.all([api('/api/next/cards?f=mistake&q=' + encodeURIComponent(q) + '&page=' + page), api('/api/next/vocab')]);
    const due = (ov.other || {}).mistakes || 0;  // the mistakes due: this page is about mistakes (the patterns are counted on 练习)
    // B9's 第三批 (the user, 2026-11-26 17:4x: 「完全做，按照现在的效果图」; ui-refine/batch23 「错题本」): ‹ 练习; a white block
    // of what is due (N 道, about how long); the one main button under it when some are due; the search; one mistake a row
    const oc = ov.other || {}, mins = due && oc.due ? Math.max(1, Math.round((oc.minutes || 0) * due / oc.due)) : 0;
    const body = l => l.items.length ? listHTML(l, st.q, st.page, '', true)
      : `<div class="empty"><p>${st.q ? `没找到「${esc(st.q)}」。可以换个写法，或者搜中文。` : '还没有错题。理解题答错、写作和口语里被改出的错误、读不准的发音、做错的语法题和辨析题，都会自动收进来。'}</p>${st.q ? '<div class="row center"><button class="btn small" type="button" id="sfClear">清除搜索</button></div>' : ''}</div>`;
    view.innerHTML = `<div><a class="link small hit44 wp-back" href="#/practice">‹ 练习</a></div>
      <div class="wp-head"><h1 class="h1">错题本</h1><span class="wp-sub">共 ${list.total} 道 · 做错的题都在这里</span></div>
      ${list.total || q || due ? `<section class="wp-blk"><div class="wp-blk-h"><h2 class="wp-blk-t">到期要复习的</h2>${due ? `<span class="wp-blk-r">约 ${mins} 分钟</span>` : ''}</div>
        <p class="wp-big">${due ? `${due} 道` : '现在没有到期的'}</p><p class="wp-note">到期了会在「错题和句型复习」里再考你</p></section>` : ''}
      ${due ? `<a class="btn primary wp-go" href="#/review/other" id="mbReview">复习到期的 ${due} 道</a>` : ''}
      ${list.total || q ? `<form class="searchrow wp-msearch" id="sf" role="search"><input type="search" name="q" aria-label="搜索错题" enterkeyhint="search" placeholder="搜索错题" value="${esc(q)}"></form>` : ''}
      <div id="listSlot">${body(list)}</div>`;
    const reload = async () => {
      const slot = document.getElementById('listSlot'); slot.classList.add('busy');
      try { const l = await api('/api/next/cards?f=mistake&q=' + encodeURIComponent(st.q) + '&page=' + st.page); slot.innerHTML = body(l); bind(); }
      catch (e) { toast(e.message); } finally { slot.classList.remove('busy'); }
    };
    const bind = () => {
      view.querySelectorAll('#listSlot [data-card]').forEach(b => b.onclick = () => cardSheet(Number(b.dataset.card), reload));
      const pv = document.getElementById('pv'), nx = document.getElementById('nx'), sc = document.getElementById('sfClear');
      if (pv) pv.onclick = () => { st.page--; reload(); };
      if (nx) nx.onclick = () => { st.page++; reload(); };
      if (sc) sc.onclick = () => { const i = document.querySelector('#sf input'); if (i) i.value = ''; st.q = ''; st.page = 1; reload(); };
    };
    const sf = document.getElementById('sf'); if (sf) sf.onsubmit = e => { e.preventDefault(); st.q = e.target.q.value.trim(); st.page = 1; reload(); };
    bind();
  }
  function listHTML(list, q, page, f, mistakes) {
    const pages = Math.max(1, Math.ceil(list.total / list.per));
    // nothing found: say what was searched, and a way out (清除搜索; with a filter on, the search across all of them) (语流 B9)
    const FILT = { word: '单词', phrase: '表达', mistake: '错题' };
    const none = q ? `没找到「${esc(q)}」${f && FILT[f] ? `（只在「${FILT[f]}」里找了）` : ''}。可以换个写法，或者搜中文意思。` : { word: '还没有单词。选一本词书，或者读文章时点词收藏。', phrase: '还没有收藏的表达。读文章时选中一段文字，或在「地道表达」里点 ☆。',
      mistake: '还没有错题。理解题答错、写作和口语里被改出的错误，都会自动收进来。' }[f] || '还没有单词。选一本词书，或者学一篇材料时点词收藏。';
    const sub = c => c.source === 'mistake' ? '错题 · ' + ({ fix: '改错', question: '理解题', sound: '发音' }[c.kind] || '') + (c.context ? ' · ' + esc(c.context) : '')
      : esc(c.meaning || c.context || SOURCE[c.source] || '');
    // one word a row (B9's 第一批): the English left in the serif, its meaning grey on the right; how well it is held is in
    // its sheet (a tap on the row)
    // 错题本 (mistakes): two lines — the question (serif), its kind and where it came from — and on the right 待学 or when it is due
    const MK = { fix: '改错', question: '理解题', sound: '发音' };
    const mrow = c => `<button class="xrow" type="button" data-card="${c.id}"><span class="t"><span class="x">${esc(c.text)}</span><span class="m">${[MK[c.kind] || '错题', c.context ? esc(c.context) : ''].filter(Boolean).join(' · ')}</span></span><span class="st">${c.state === 'new' ? '待学' : dueText(c.due)} ›</span></button>`;
    return `${list.items.length ? `<div class="xlist wp-list${mistakes ? ' wp-mlist' : ''}" id="clist">${list.items.map(c => mistakes ? mrow(c) : `<button class="xrow" type="button" data-card="${c.id}"><span class="x">${esc(c.text)}</span><span class="m"${c.source === 'mistake' ? '' : ' data-zh'}>${sub(c)}</span></button>`).join('')}</div>`
        : `<div class="empty"><p>${none}</p>${q ? `<div class="row center">${f && FILT[f] ? '<button class="btn small" type="button" id="sfAll">在全部里找</button>' : ''}<button class="btn small" type="button" id="sfClear">清除搜索</button></div>` : ''}</div>`}
      ${pages > 1 ? `<div class="pager"><button class="btn small" id="pv" ${page <= 1 ? 'disabled' : ''}>上一页</button><span class="muted small">${page} / ${pages}</span><button class="btn small" id="nx" ${page >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}`;
  }

  // Memory curve: recall chance from the last review onwards, with today and the target retention marked.
  function curveSVG(c, retention) {
    if (!c.stability || !c.last) return '';
    const W = 300, H = 110, P = 22, now = (Date.now() / 1000 - c.last) / 86400, span = Math.max(14, now * 1.4, (c.due - c.last) / 86400 * 1.6);
    const x = t => P + t / span * (W - P - 6), y = r => 8 + (1 - r) * (H - 30);
    let d = ''; for (let k = 0; k <= 60; k++) { const t = span * k / 60; d += (k ? 'L' : 'M') + x(t).toFixed(1) + ' ' + y(recallAt(c.stability, t)).toFixed(1); }
    const dueT = (c.due - c.last) / 86400;
    return `<svg class="curve" viewBox="0 0 ${W} ${H}" role="img" aria-label="记忆曲线：此刻记得的概率 ${pct(c.recall)}">
      <line class="target" x1="${P}" x2="${W - 6}" y1="${y(retention)}" y2="${y(retention)}"/><text class="lbl" x="${W - 8}" y="${y(retention) - 4}" text-anchor="end">目标 ${Math.round(retention * 100)}%</text>
      <path class="line" d="${d}"/>
      <line class="due" x1="${x(dueT)}" x2="${x(dueT)}" y1="6" y2="${H - 22}"/><text class="lbl" x="${Math.max(x(dueT), P + 58)}" y="${H - 8}" text-anchor="${x(dueT) < P + 58 ? 'start' : 'middle'}">下次复习</text>
      <circle class="now" cx="${x(Math.min(now, span))}" cy="${y(recallAt(c.stability, Math.min(now, span)))}" r="4.5"/><text class="lbl" x="${P}" y="${H - 8}">上次复习</text></svg>`;
  }
  function examplesHTML(c, open) {
    const list = [];
    if (c.context) list.push({ text: c.context, form: c.source === 'mistake' ? ((c.extra || {}).from || c.text) : c.text, pack: c.pack, title: c.source === 'mistake' ? '你当时写的' : '你收藏时的原句', audio: 0, mine: true });
    (c.examples || []).forEach(e => list.push(e));
    // many speakers in a list that can scroll: a faint 「AI」 on each (aiBadge); the grey line is the card's (aiVoiceNote)
    return list.length ? `<div class="exs">${list.map((e, k) => `<div class="ex"><button class="icon-btn has-ai" type="button" data-exp="${k}" aria-label="播放例句（AI 朗读）">${ICON.speak}${aiBadge()}</button>
      <div><div class="text">${open === false ? gapped(e.text, e.form || c.text, false) : gapped(e.text, e.form || c.text, true)}</div>${e.zh && open !== false ? `<div class="tiny muted" data-zh>${esc(e.zh)}</div>` : ''}
      ${e.pack ? `<a class="tiny muted link" href="#/m/${encodeURIComponent(e.pack)}/read">${e.mine ? esc(e.title) : '出自《' + esc(e.title) + '》'}${e.audio ? ' · 原文录音' : ''}</a>` : e.ai ? aiTag() : `<span class="tiny muted">${esc(e.title)}</span>`}</div></div>`).join('')}</div>` : '';
  }
  function wordHead(word, phonetic) {
    return `<div class="wd-head"><div class="word tapsay" id="sheetTitle">${esc(word)}</div><div class="ph">${esc(phonetic || '')}<button class="icon-btn say-btn" id="sayW" type="button" aria-label="播放读音（AI 朗读）">${ICON.speak}</button></div>${aiVoiceNote('读音由 AI 合成')}</div>`;
  }
  function rootsHTML(c) {
    return c.roots && c.roots.length ? `<div class="roots">${c.roots.map(r => `<span class="root"><span class="k">${esc(r.kind)}</span> <b>${esc(r.part)}</b> ${esc(r.meaning)}</span>`).join('')}</div>` : '';
  }
  function bindExamples(root, c) {
    const list = []; if (c.context) list.push({ text: c.context, audio: 0 }); (c.examples || []).forEach(e => list.push(e));
    root.querySelectorAll('[data-exp]').forEach(b => b.onclick = () => CLIP.sentence(list[Number(b.dataset.exp)]));
  }
  // 常用搭配和近义、易混词 (words-modes-plan.md 第 4 步; B7's word_extras: AI 生成, checked, nothing taken down): a fold like 易混
  // on the 详细 back and in a word's sheet, marked 「AI 生成」 where it shows; each item has 「这条不对」 (hidden for this
  // learner from then on, a note to 语流's admins with no name, an undo; 放回 in the word's sheet)
  function extrasHTML(c) {
    const xs = (c && c.extras) || []; if (!xs.length) return '';
    // the user, 2026-11-26 (「视觉压力小」): no new box or line, no coloured tag — 「AI 生成」 in grey words; a few of each, the rest folded
    const li = x => `<li data-xid="${x.id}"><b>${esc(x.en)}</b>${x.zh ? ` <span data-zh>${esc(x.zh)}</span>` : ''}${x.diff ? `<span class="xd" data-zh> · ${esc(x.diff)}</span>` : ''}</li>`;
    const col = xs.filter(x => x.kind === 'colloc'), near = xs.filter(x => x.kind === 'near'), SHOW = { colloc: 3, near: 2 };
    const part = (g, kind, title) => g.length ? `<div class="xtra-h" data-xk="${kind}">${title}</div><ul class="xtra" data-xk="${kind}">${g.map(li).join('')}</ul>` : '';
    const more = col.slice(SHOW.colloc).length + near.slice(SHOW.near).length;
    return `<section class="xtra-wrap" aria-label="常用搭配和近义、易混词（AI 生成）"><p class="xtra-ai">常用搭配和近义、易混词 · AI 生成，仅供参考</p>
      ${part(col.slice(0, SHOW.colloc), 'colloc', '常用搭配')}${part(near.slice(0, SHOW.near), 'near', '近义和易混词')}
      ${more ? `<details class="xtra-more"><summary>更多 ${more} 条</summary>${part(col.slice(SHOW.colloc), 'colloc', '常用搭配')}${part(near.slice(SHOW.near), 'near', '近义和易混词')}</details>` : ''}
      <div class="xtra-foot"><button class="link small xbad-open" type="button">有不对的？</button><a class="link small" href="#/guide/ai-service">AI 服务说明</a></div></section>`;
  }
  function bindExtras(root, c) {
    const b = root.querySelector('.xbad-open'); if (b) b.onclick = e => { e.stopPropagation(); extraBad(c, root); };
  }
  // 「有不对的？」: one quiet way in; the sheet asks which item, a note if they like, no name shown to the admins
  function extraBad(c, root) {
    const xs = c.extras || []; if (!xs.length) return;
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">哪一条不对？</h2>
      <div class="xpicks" role="radiogroup" aria-labelledby="sheetTitle">${xs.map(x => `<label class="xpick"><input type="radio" name="xpick" value="${x.id}"><span><b>${esc(x.en)}</b>${x.zh ? ' ' + esc(x.zh) : ''}</span></label>`).join('')}</div>
      <label class="stack-s"><span class="small">哪里不对？（可以不写）</span><textarea id="xNote" rows="2" maxlength="100" placeholder="比如：意思不对、不常这样说（不用写你的名字）"></textarea></label>
      <p class="tiny muted">留言会给语流的管理员看，不显示你的名字。标了以后这条不再给你看，在这个词的详情里可以放回。</p>
      <button class="btn primary xgo" id="xGo" type="button" disabled>提交</button><button class="link small xcancel" data-close type="button">取消</button></div>`, card => {
      const go = card.querySelector('#xGo');
      card.querySelectorAll('[name=xpick]').forEach(r => { r.onchange = () => { go.disabled = false; }; });
      go.onclick = async () => {
        const pick = card.querySelector('[name=xpick]:checked'); if (!pick) return;
        const id = +pick.value, x = xs.find(y => y.id === id);
        go.disabled = true;
        try {
          await api('/api/next/vocab/extra-flag', { id, note: card.querySelector('#xNote').value });
          closeSheet(); extraGone(c, id, root);
          undoBar(`已标为不对：「${x.en}」不再给你看`, async () => {
            try { await api('/api/next/vocab/extra-unflag', { id }); c.extras = [...(c.extras || []), x]; toast('已放回'); } catch (y) { toast(y.message); }
          });
        } catch (y) { toast(y.message); go.disabled = false; }
      };
    });
  }
  function extraGone(c, id, root) {  // the item leaves the card at once; an empty group, then the whole fold, go too
    c.extras = (c.extras || []).filter(y => y.id !== id);
    const li = root.querySelector(`li[data-xid="${id}"]`); if (!li) return;
    const ul = li.parentNode; li.remove();
    if (!ul.children.length) { const h = root.querySelector(`.xtra-h[data-xk="${ul.dataset.xk}"]`); if (h) h.remove(); ul.remove(); }
    if (!(c.extras || []).length) { const w = root.querySelector('.xtra-wrap'); if (w) w.remove(); }
  }
  // a line at the bottom for six seconds with 撤销 (like 「已标为太简单」 on the review page)
  function undoBar(text, onUndo) {
    document.querySelectorAll('.easy-bar').forEach(b => b.remove());
    const b = document.createElement('div'); b.className = 'easy-bar'; b.setAttribute('role', 'status');
    b.innerHTML = `<span>${esc(text)}</span><button class="link small" type="button">撤销</button>`;
    document.body.appendChild(b);
    const gone = setTimeout(() => b.remove(), 6000);
    b.querySelector('button').onclick = () => { clearTimeout(gone); b.remove(); onUndo(); };
  }
  async function cardSheet(id, after) {
    openSheet(`<p class="loading"><span class="spin"></span></p>`);
    let d; try { d = await api('/api/next/vocab/card?id=' + id); } catch (e) { openSheet(`<p class="err">${esc(e.message)}</p>`); return; }
    const c = d.card;
    const tl = { again: '忘了', hard: '模糊', good: '记得', easy: '很熟', known: '熟知', lookup: '读文章时查过' };
    openSheet(`<div class="stack">
      ${wordHead(c.text, c.phonetic)}
      ${c.source === 'mistake' && (c.extra || {}).from ? `<div class="fixline"><del>${esc(c.extra.from)}</del> → <ins>${esc(c.text)}</ins></div>` : ''}
      ${c.meaning ? `<div class="mean" data-zh>${esc(c.meaning).replace(/；|;/g, '<br>')}</div>` : ''}${rootsHTML(c)}
      <div class="wd-meta">${[c.known ? '熟知' : c.state === 'new' ? '待学' : `${c.mastered ? '已掌握 · ' : ''}<span title="此刻记得的概率">记得 ${pct(c.recall)}</span>`,
        c.stability ? `记忆稳定性 ${c.stability < 1 ? '不到 1 天' : Math.round(c.stability) + ' 天'}` : '', c.state !== 'new' && !c.known ? dueText(c.due) : ''].filter(Boolean).join(' · ')}</div>
      ${curveSVG(c, d.retention)}
      <div id="exSlot">${examplesHTML(c) || (c.kind === 'word' && S.user ? '<p class="muted tiny"><span class="spin"></span> 正在找例句…</p>' : '')}</div>
      <div id="xtraSlot">${extrasHTML(c)}</div>
      ${(d.marked || []).length ? `<div class="xtra-marked tiny muted">你标为不对的：${d.marked.map(m => `<span><b>${esc(m.en)}</b> <button class="link small" type="button" data-xback="${m.id}" aria-label="放回 ${esc(m.en)}">放回</button></span>`).join('　')}</div>` : ''}
      ${d.history.length ? `<div class="tiny muted">复习记录：${d.history.slice(-8).map(h => `${new Date(h.created * 1000).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })} ${tl[h.rating] || h.rating}`).join(' · ')}</div>` : ''}
      <div class="row"><button class="btn" id="known">${c.known ? '取消熟知，继续复习' : '标为熟知，不再复习'}</button><button class="btn ghost" id="del">删除</button><button class="btn ghost" data-close>关闭</button></div></div>`, card => {
      card.querySelectorAll('#sayW, .tapsay').forEach(b => { b.onclick = () => CLIP.word(c); });
      bindExamples(card, c);
      bindExtras(card, c);
      card.querySelectorAll('[data-xback]').forEach(b => { b.onclick = async () => {  // 放回: shown again, the sheet drawn again
        b.disabled = true;
        try { await api('/api/next/vocab/extra-unflag', { id: +b.dataset.xback }); toast('已放回'); cardSheet(id, after); } catch (e) { toast(e.message); b.disabled = false; }
      }; });
      if (c.kind === 'word' && S.user && !(c.examples || []).length) {
        api('/api/next/vocab/examples', { words: [c.text.toLowerCase()], request_id: rid('ve') }).then(r => {
          const ex = (r.examples || {})[c.text.toLowerCase()], slot = card.querySelector('#exSlot');
          if (!slot || !document.contains(slot)) return;
          if (ex && ex.length) c.examples = ex;
          slot.innerHTML = examplesHTML(c) || '<p class="muted tiny">暂时没有例句。</p>'; bindExamples(slot, c);
        }).catch(() => { const slot = card.querySelector('#exSlot'); if (slot) slot.innerHTML = examplesHTML(c); });
      }
      card.querySelector('#known').onclick = async () => { try { await api('/api/next/vocab/known', { id: c.id, known: !c.known }); closeSheet(); toast(c.known ? '已恢复复习' : '已标为熟知'); refreshHome().catch(() => {}); if (after) after(); } catch (e) { toast(e.message); } };
      const delB = card.querySelector('#del'); if (delB) delB.setAttribute('aria-label', '删除 ' + c.text);
      card.querySelector('#del').onclick = async () => { if (!confirm('删除这个词和它的复习记录？')) return; try { await api('/api/next/cards/delete', { id: c.id }); closeSheet(); if (after) after(); } catch (e) { toast(e.message); } };
    });
    CLIP.word(c);
  }
  function importSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">导入词表</h2>
      <p class="muted small">每行一个单词或短语（也可以用逗号分开），一次最多 500 个。词典里有的会自动配上释义和例句；已经在复习里的会跳过。适合导入老师给的或自己整理的词表。</p>
      <textarea id="impText" data-draft="words-import" rows="8" placeholder="abandon&#10;make ends meet&#10;serendipity"></textarea>
      <div class="row"><button class="btn primary" id="impGo">导入</button><button class="btn ghost" data-close>取消</button></div></div>`, card => {
      card.querySelector('#impGo').onclick = async e => {
        e.currentTarget.disabled = true;
        try { const r = await api('/api/next/vocab/import', { text: card.querySelector('#impText').value }); draftDone('words-import'); closeSheet(); toast(`导入了 ${r.added} 个${r.skipped ? `，跳过 ${r.skipped} 个已有的` : ''}`); refreshHome().catch(() => {}); vocabView(); }
        catch (x) { toast(x.message); e.currentTarget.disabled = false; }
      };
    });
  }

  async function planView() {
    if (!S.user) return needLogin('登录后才能制定背词计划。');
    const o = await api('/api/next/vocab');
    const cur = o.plan || { book: o.suggested_book, daily_new: 10, retention: 0.9 };
    let book = cur.book, daily = cur.daily_new, ret = cur.retention, wm = cur.word_minutes || 0;
    // 考试冲刺: the chip pressed is the exam being prepared for (saved with the plan), with its date (42-sprint.js).
    const prof = (S.home && S.home.profile) || {}, exam0 = prof.exam || '', date0 = prof.exam_date || '';
    let examSel = exam0;
    // One book in the picker: title, word count and what it is for; a data book (专四、专八…) also says how it was made.
    const bookCard = b => `<div class="bookcell"><button class="card flat bookc" data-book="${esc(b.id)}" aria-pressed="${b.id === book}">
        <span class="bk-top"><b>${esc(b.title)}</b><span class="bk-tags">${b.id === o.suggested_book ? '<span class="pill green">推荐</span>' : ''}<span class="pill bk-on">已选</span><span class="tiny muted bk-n">${(b.count || b.size || 0).toLocaleString()} 词</span></span></span>
        ${b.blurb ? `<span class="small">${esc(b.blurb)}</span>` : ''}${b.range ? `<span class="tiny muted">词频第 ${b.range} 位</span>` : ''}</button>
        ${b.basis ? `<details class="basis"><summary>这份词书怎么来的</summary><p class="tiny muted">${esc(b.basis)}</p></details>` : ''}</div>`;
    view.innerHTML = `<h1 class="h1">背词计划</h1><span class="muted small">随时可以改，已学的进度不会丢。</span>
      <div class="section stack-s"><h2 class="h2">词书</h2>
        ${(o.exam_goals || []).length ? `<div class="stack-s"><span class="small" id="goalQ">你在准备什么考试？点一下就选好对应的词书。</span>
          <div class="chips" id="goal" role="group" aria-labelledby="goalQ">${[{ title: '不考试', book: '' }, ...o.exam_goals].map(g => `<button class="chip" data-goal="${esc(g.book)}" data-exam="${g.exam ? esc(g.book) : ''}" aria-pressed="false">${esc(g.title)}</button>`).join('')}</div>${planExamRow(prof)}</div>` : ''}
        <div class="card flat booksel stack-s"><div class="row between"><span class="small" id="bookNow" aria-live="polite"></span>
          <button class="link small" id="moreBooks" type="button" aria-expanded="false" aria-controls="allBooks">换一本（共 ${o.books.length} 本）</button></div><div id="bookSelInfo"></div></div>
        <div class="bookgroups" id="allBooks" hidden><span class="muted tiny">按词频的词书从你的水平往上走；其他词书按考试或用途分组，点一本就选中。</span>${(o.groups || [...new Set(o.books.map(b => b.group))]).map(g => `<section class="bookgroup" aria-label="${esc(g)}"><div class="kicker">${esc(g)}</div><div class="books">${o.books.filter(b => b.group === g).map(bookCard).join('')}</div></section>`).join('')}</div>
        <section class="bookgroup" aria-label="自己的词表"><div class="kicker">自己的词表</div><div class="books"><button class="card flat bookc" id="impBook" type="button"><b>导入老师给的词表</b><span class="small">把手上的词表粘贴进来，和词书一起按遗忘曲线复习。</span><span class="tiny muted">导入词表 →</span></button></div></section></div>
      <div class="section stack-s"><h2 class="h2">每天新词</h2><div class="chips" id="dn">${o.daily_new_options.map(v => `<button class="chip" data-v="${v}" aria-pressed="${v === daily}">${v} 个</button>`).join('')}</div>
        <div class="row"><label class="small" for="dnOwn">自己定：</label><input id="dnOwn" type="number" inputmode="numeric" min="1" max="200" step="1" class="num-in" value="${o.daily_new_options.includes(daily) ? '' : daily}" placeholder="1–200"><span class="small muted">个 / 天</span></div>
        <span class="muted tiny" id="dnHint"></span><button class="btn small" type="button" id="dnTen" hidden>改成每天 10 个</button><span class="muted tiny">学完当天的，复习页还可以「再学 10 个」，不用改计划。</span></div>
      <div class="section stack-s"><h2 class="h2">单词每天</h2><div class="chips" id="wm"><button class="chip" data-m="0" aria-pressed="${!wm}">${o.word_auto ? `跟着每天计划（${o.word_auto} 分钟）` : '不限时间'}</button>${(o.word_minutes_options || []).map(v => `<button class="chip" data-m="${v}" aria-pressed="${v === wm}">${v} 分钟</button>`).join('')}</div>
        <span class="muted tiny" id="wmHint"></span><button class="btn small" type="button" id="wmFit" hidden></button>
        <span class="muted tiny">做到这个时间，今天的单词就算完成；剩下的复习按遗忘风险留到之后几天，想多背随时可以继续。</span></div>
      <div class="section stack-s"><h2 class="h2">目标记住率</h2><div class="chips" id="rt">${o.retention_options.map(v => `<button class="chip" data-v="${v}" aria-pressed="${v === ret}">${Math.round(v * 100)}%</button>`).join('')}</div>
        <span class="muted tiny">系统会在你记住的概率降到这个数时安排复习。越高记得越牢，但每天复习更多；90% 是比较均衡的选择。</span></div>
      ${o.plan && o.plan.estimate ? `<label class="section checkline"><input type="checkbox" id="skipKnown" ${o.plan.skip_rank ? 'checked' : ''}>跳过测试显示你已经认识的常用词${o.plan.test_skip ? `（词频前 ${o.plan.test_skip} 位）` : ''}，按词频的词书不受影响</label>` : ''}
      <div class="section row savebar"><button class="btn primary" id="savePlan">${o.plan ? '保存' : '开始背'}</button><a class="btn ghost" href="#/cards">取消</a></div>
      <div class="section card flat stack-s" id="remind"><h2 class="h2">复习提醒</h2>
        <span class="muted tiny">遗忘曲线最怕"到期没人提醒"。选一个每天方便的时间：</span>
        <div class="row"><select id="rHour" aria-label="提醒时间">${Array.from({ length: 18 }, (_, k) => k + 6).map(h => `<option value="${h}" ${h === o.reminder.hour ? 'selected' : ''}>每天 ${h}:00</option>`).join('')}</select></div>
        <label class="checkline"><input type="checkbox" id="rMail" ${o.reminder.enabled ? 'checked' : ''} ${o.reminder.has_email ? '' : 'disabled'}><span>到点发邮件提醒（只在有词要复习时发）${o.reminder.has_email ? '' : '<br><span class="muted tiny">账号还没绑定邮箱：可以在<a class="link" href="#/me">「我的」</a>里绑定，或者先用下面的日历提醒。</span>'}</span></label>
        <div class="row"><a class="btn small" id="rCal" href="/api/next/vocab/reminder.ics?hour=${o.reminder.hour}">加到手机日历</a><span class="muted tiny">日历每天到点提醒，不依赖任何 App</span></div>
        ${window.FlowApp && FlowApp.has && FlowApp.has('notify') ? `<div class="row" id="rAppRow">${appRowHTML(false)}</div>` : ''}
        <div class="row between" id="onceRow"><span class="small" id="onceNow">${o.reminder.once ? `下一次：${onceLabel(o.reminder.once)}（只管这一次）` : '哪天这个点没空，可以只改下一次的时间。'}</span><button class="btn small" type="button" id="onceBtn">这次什么时候复习</button></div></div>`;
    const meta = id => o.books.find(b => b.id === id) || {};
    // Days left: words not yet studied, minus the ones this plan skips (everyday words; for exam and data books, what the test showed you know).
    const hint = () => {
      const sk = document.getElementById('skipKnown'), b = meta(book);
      const skip = book === 'core' || (sk ? sk.checked : true) ? (b.skippable || 0) : 0;
      const done = o.book && o.book.id === book ? o.book.started : 0;
      const days = Math.ceil(Math.max(0, (b.size || 0) - skip - done) / daily);
      document.getElementById('bookNow').textContent = b.title ? `已选《${b.title}》，${(b.count || b.size || 0).toLocaleString()} 词` : '还没选词书';
      document.getElementById('bookSelInfo').innerHTML = b.title ? `${b.blurb ? `<span class="small">${esc(b.blurb)}</span>` : ''}${book === o.suggested_book ? ' <span class="pill green">推荐</span>' : ''}
        ${b.basis ? `<details class="basis"><summary>这份词书怎么来的</summary><p class="tiny muted">${esc(b.basis)}</p></details>` : ''}` : '<span class="small muted">点上面的考试，或点「换一本」挑一本。</span>';
      const px = document.getElementById('pxRow');
      if (px) { px.hidden = !examSel; document.getElementById('pxHint').textContent = planExamHint(examSel, document.getElementById('pxDate').value, meta(examSel), book, daily, o.book && o.book.id === examSel ? o.book.started : 0); }
      // a month in: the same numbers as the day's estimate (vocab_service: reviews by target retention, answers, pace)
      const L = o.load || { answer_seconds: 9.5, per_review: 1.2, per_new: 3, month_reviews_per_new: {} };
      const month = Math.round(daily * (L.month_reviews_per_new[String(ret)] || 6));
      const mins = Math.max(1, Math.round((month * L.per_review + daily * L.per_new) * L.answer_seconds / 60));
      // half an hour or more a day: the number as it is, and the way out (10 new words a day), one tap away
      const heavy = b.title && mins >= 30, ten = heavy && daily > 10;
      // 单词每天 (r28): the new words a day that cap keeps up with, a month in; the book's days at that pace
      const cap = wm || o.word_auto, perNew = L.per_new + (L.month_reviews_per_new[String(ret)] || 6) * L.per_review;
      const fit = cap ? Math.max(1, Math.floor(cap * 60 / L.answer_seconds / perNew)) : 0, slow = cap && daily > fit;
      const capDays = cap ? Math.ceil(Math.max(0, (b.size || 0) - skip - done) / Math.min(daily, fit)) : days;
      document.getElementById('dnHint').textContent = !b.title ? '先在上面选一本词书。' : `学完《${b.title}》大约需要 ${capDays} 天${skip ? `（跳过 ${skip} 个常用词）` : ''}；每天 ${daily} 个新词，一个月后每天大约要复习 ${month} 个${heavy && !cap
        ? `。按现在的设置，一个月后每天大约要 ${mins} 分钟${ten ? '。时间紧的话，可以改成每天 10 个新词' : ''}。` : `，连新词约 ${mins} 分钟。`}`;
      document.getElementById('dnTen').hidden = !ten || !!cap;
      document.getElementById('wmHint').textContent = !cap ? '不限时间：每天到期的复习和新词都排进今天。'
        : `按单词每天 ${cap} 分钟，每天大约能学 ${fit} 个新词${slow ? `。每天 ${daily} 个新词，一个月后单词每天约 ${mins} 分钟，比 ${cap} 分钟多：可以把单词时间改长，或者新词改成 ${fit} 个` : ''}。`;
      const wf = document.getElementById('wmFit'); wf.hidden = !slow; wf.textContent = `新词改成每天 ${fit} 个`; wf.dataset.n = fit;
    };
    // The exam chips follow the chosen book: its exam, or 「不考试」 for a book by frequency; another book (学术、商务…) lights none.
    const syncGoal = () => view.querySelectorAll('[data-goal]').forEach(x => x.setAttribute('aria-pressed', String(examSel ? x.dataset.exam === examSel : x.dataset.goal ? x.dataset.goal === book : meta(book).group === '按词频')));
    const choose = id => { book = id; view.querySelectorAll('[data-book]').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.book === id))); syncGoal(); hint(); };
    view.querySelectorAll('[data-book]').forEach(b => b.onclick = () => choose(b.dataset.book));
    view.querySelectorAll('[data-goal]').forEach(b => b.onclick = () => { examSel = b.dataset.exam || ''; choose(b.dataset.goal || o.suggested_book); });
    const pxDate = document.getElementById('pxDate'); if (pxDate) pxDate.oninput = hint;
    const more = document.getElementById('moreBooks'), all = document.getElementById('allBooks');
    more.onclick = () => { const open = all.hidden; all.hidden = !open; more.setAttribute('aria-expanded', String(open)); more.textContent = open ? '收起' : `换一本（共 ${o.books.length} 本）`; };
    syncGoal();
    const pick = (sel, set) => view.querySelectorAll(sel + ' [data-v]').forEach(b => b.onclick = () => { set(Number(b.dataset.v)); view.querySelectorAll(sel + ' [data-v]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); hint(); });
    pick('#dn', v => { daily = v; document.getElementById('dnOwn').value = ''; }); pick('#rt', v => { ret = v; });
    view.querySelectorAll('#wm [data-m]').forEach(b => b.onclick = () => { wm = Number(b.dataset.m); view.querySelectorAll('#wm [data-m]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); hint(); });
    document.getElementById('wmFit').onclick = e => {  // the new words a day that fit the time, one tap away
      const v = Number(e.currentTarget.dataset.n), chip = view.querySelector(`#dn [data-v="${v}"]`);
      if (chip) chip.click(); else { daily = v; document.getElementById('dnOwn').value = v; view.querySelectorAll('#dn [data-v]').forEach(x => x.setAttribute('aria-pressed', 'false')); hint(); }
    };
    document.getElementById('dnTen').onclick = () => { const t = view.querySelector('#dn [data-v="10"]'); if (t) t.click(); };
    document.getElementById('dnOwn').oninput = e => {
      const v = Math.round(Number(e.target.value));
      if (v >= 1 && v <= 200) { daily = v; view.querySelectorAll('#dn [data-v]').forEach(x => x.setAttribute('aria-pressed', String(Number(x.dataset.v) === v))); hint(); }
    };
    const skBox = document.getElementById('skipKnown'); if (skBox) skBox.onchange = hint;
    document.getElementById('impBook').onclick = importSheet;
    hint();
    const rHour = document.getElementById('rHour'), rMail = document.getElementById('rMail'), rCal = document.getElementById('rCal');
    const saveRemind = async () => { rCal.href = '/api/next/vocab/reminder.ics?hour=' + rHour.value; try { appNotify({ ...(await api('/api/next/vocab/reminder', { enabled: rMail.checked, hour: Number(rHour.value) })), forecast: o.forecast }); toast(rMail.checked ? `每天 ${rHour.value}:00 会提醒你` : '提醒时间已更新'); } catch (x) { toast(x.message); rMail.checked = false; } };
    rHour.onchange = saveRemind; rMail.onchange = saveRemind;
    const bindApp = () => {  // the app (iOS, Android, desktop): ask once for notifications, then schedule them from the reminder
      const row = document.getElementById('rAppRow'); if (!row) return;
      const redo = async () => { const on = await appOn(); if (!document.contains(row)) return; row.innerHTML = appRowHTML(on); bindApp(); };
      const on = document.getElementById('rApp');
      if (on) on.onclick = async () => {
        let ok = false; try { ok = await Promise.resolve(FlowApp.notify.ask()); } catch (e) { ok = false; }
        if (!ok) { toast(`通知没有打开：可以到${appPlace()[1]}里打开`); return; }
        try { const v = await api('/api/next/vocab'); appNotify({ ...v.reminder, forecast: v.forecast }); toast(`好，每天 ${v.reminder.hour}:00 用 App 通知提醒你（有词要复习的日子）`); } catch (e) { toast(e.message); }
        redo();
      };
      const off = document.getElementById('rAppOff');
      if (off) off.onclick = async () => { try { await Promise.resolve(FlowApp.notify.off()); toast('App 通知提醒关了；邮件和日历提醒照旧'); } catch (e) { toast(e.message || '没有关掉，再试一次'); } redo(); };
      const set = document.getElementById('rAppSet');
      if (set) set.onclick = () => { try { FlowApp.notify.settings(); } catch (e) { toast(`可以到${appPlace()[1]}里改`); } };
    };
    bindApp();
    const appRow = document.getElementById('rAppRow');  // drawn as off at first; then as the app says (asynchronously)
    if (appRow) appOn().then(on => { if (on && document.contains(appRow)) { appRow.innerHTML = appRowHTML(true); bindApp(); } });
    document.getElementById('onceBtn').onclick = () => remindOnce(x => { document.getElementById('onceNow').textContent = x.once ? `下一次：${onceLabel(x.once)}（只管这一次）` : '哪天这个点没空，可以只改下一次的时间。'; });
    document.getElementById('savePlan').onclick = async e => {
      const btn = e.currentTarget; btn.disabled = true;
      const sk = document.getElementById('skipKnown');
      const date = examSel && pxDate ? pxDate.value : '';
      try {
        await api('/api/next/vocab/plan', { book, daily_new: daily, retention: ret, word_minutes: wm, ...(sk ? { skip_known: sk.checked } : {}) });
        if (examSel !== exam0 || date !== date0) await api('/api/next/exam/goal', { exam: examSel, date });
        await refreshHome(); toast('计划已保存'); location.hash = '#/cards';
      }
      catch (x) { toast(x.message); btn.disabled = false; }
    };
  }

  async function vocabTest() {
    const t = await api('/api/next/vocab/test');
    const items = t.items, answers = {}; let i = 0;
    function show() {
      document.body.classList.add('reviewing');
      if (i >= items.length) return finish();
      view.innerHTML = `<h1 class="sr-only">测词汇量</h1><div class="bar-progress"><i id="rp"></i></div><div class="review vtest enter"><p class="muted small">认识这个词吗？看到能想起大概意思就算认识。<br>有几个是编出来的假词，用来校正估计。</p>
        <div class="wordbig">${esc(items[i])}</div>
        <div class="choice two">${KNOW.order([['1', 'good', '认识'], ['0', '', '不认识']]).map(([a, cls, t], k) => `<button class="${cls}" data-a="${a}">${t}<small>${k ? '→' : '←'}</small></button>`).join('')}</div>
        <p class="muted tiny tc">${i + 1} / ${items.length}</p></div>`;
      document.getElementById('rp').style.width = (i / items.length * 100) + '%';
      view.querySelectorAll('[data-a]').forEach(b => b.onclick = () => answer(b.dataset.a === '1'));
      document.onkeydown = e => { if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); answer((e.key === 'ArrowRight') === (KNOW.side() === 'right')); } };
    }
    function answer(yes) { answers[items[i]] = yes; haptic('select'); i++; show(); }
    async function finish() {
      document.onkeydown = null; swipeOff(); document.body.classList.remove('reviewing');
      view.innerHTML = `<p class="loading"><span class="spin"></span> 正在估算…</p>`;
      const r = await api('/api/next/vocab/test', { answers });
      if (!S.user) save('flow-next-guest-test', { answers, at: Date.now() });  // kept, and saved to the account after signing in
      const o = S.user ? await api('/api/next/vocab') : null;
      const titles = r.titles || {}, title = titles[r.suggest] || r.suggest;
      view.innerHTML = `<div class="card done-card enter stack"><div class="kicker">词汇量估计</div><div class="huge">${r.estimate.toLocaleString()}</div>
        <p class="muted small">${r.guessing ? '你选了不少假词，估计可能偏高，已经按比例扣除。' : '按词频分段抽样估算，误差约几百词。'}</p>
        <div class="vt-bands">${Object.entries(r.bands).map(([k, v]) => `<div class="row between small"><span>${esc(titles[k] || k)}</span><span class="vbar"><i data-w="${v * 100}"></i></span><span class="muted">${Math.round(v * 100)}%</span></div>`).join('')}</div>
        <p>${r.ceiling ? `常用的 2 万词你几乎都认识，超出了这个测试能测的范围。建议用《${esc(title)}》这类考试词表${o && o.books.some(b => b.group === '英语专业') ? '，或在「背词计划」里选英语专业的词书' : ''}，也可以导入自己的词表。` : `建议从《${esc(title)}》开始。`}</p>
        ${S.user ? '' : '<p class="muted small">结果已经记下，登录后会存到你的账号。</p>'}
        <div class="row center"><button class="btn primary" id="useBook">用《${esc(title)}》开始</button><button class="btn" id="retest">重新测</button><a class="btn ghost" href="#/cards">返回单词</a></div></div>`;
      document.getElementById('retest').onclick = () => vocabTest();
      requestAnimationFrame(() => requestAnimationFrame(() => view.querySelectorAll('.vbar i').forEach(x => { x.style.width = x.dataset.w + '%'; })));
      document.getElementById('useBook').onclick = async () => {
        if (!S.user) return needLogin('登录后可以按测试结果制定背词计划。');
        try { const cur = (o && o.plan) || {}; await api('/api/next/vocab/plan', { book: r.suggest, daily_new: cur.daily_new || 10, retention: cur.retention || 0.9 });
          await api('/api/next/vocab/test', { answers }); await refreshHome(); location.hash = '#/cards'; } catch (e) { toast(e.message); }
      };
    }
    swipeOn(() => { if (i >= items.length) return null; const [right, left] = KNOW.swipe(() => answer(true), () => answer(false)); return { right, left }; });  // as on the buttons
    show();
  }

  /* ---------- review: recognise -> recall -> spell as an item gets stronger ---------- */
  // Swiping a card (the review, the vocabulary test): right and left call what acts() returns at that moment
  // ({ right, left }, either may be missing). The whole screen takes the swipe, not only the card: on a wide screen (an
  // iPad sideways) the card is a column in the middle and the thumb rests beside it, or below it. Not from a link or a
  // field, and not while a sheet is open. A swipe is mostly sideways, without a strict
  // height limit (on a big screen it drifts). Leaving the page takes it off (swipeOff, in route()).
  let SWIPED = 0, SCROLLED = 0;  // when a swipe last answered; when the page last scrolled (the tap that stops a scroll answers nothing)
  addEventListener('scroll', () => { SCROLLED = Date.now(); }, { passive: true });  // when a swipe last answered: the click a browser may still send after it is not a tap on the card
  function swipeOn(acts) {
    let sx = null;
    const cardEl = () => view.querySelector('.review');
    const settle = () => { const card = cardEl(); if (card) card.style.transform = ''; };
    document.ontouchstart = e => {
      // The card's own buttons count (on a phone the answer buttons are where the thumb rests; a finger that moves does
      // not press them); links, fields and buttons elsewhere (撤销) are left to themselves.
      const t = e.target, off = t.closest('a,input,select,textarea,label,.sheet') || (t.closest('button') && !t.closest('.review'));
      sx = e.touches.length === 1 && sheetEl.hidden && !isTyping(e) && !off ? [e.touches[0].clientX, e.touches[0].clientY] : null;
    };
    document.ontouchmove = e => {
      if (!sx || !acts()) return; const t = e.touches[0], dx = t.clientX - sx[0], card = cardEl();
      if (card && Math.abs(dx) > Math.abs(t.clientY - sx[1])) card.style.transform = `translateX(${dx * 0.35}px) rotate(${dx * 0.02}deg)`;
    };
    document.ontouchend = e => {
      settle(); const a = acts();
      if (!sx || !a) return; const t = e.changedTouches[0], dx = t.clientX - sx[0], dy = t.clientY - sx[1]; sx = null;
      if (Math.abs(dx) > 80 && Math.abs(dx) > Math.abs(dy) * 1.4) { const f = dx > 0 ? a.right : a.left; if (f) { SWIPED = Date.now(); f(); } }
    };
    document.ontouchcancel = () => { sx = null; settle(); };  // the browser took the gesture (a scroll, the system): the card goes back
  }
  function swipeOff() { document.ontouchstart = document.ontouchmove = document.ontouchend = document.ontouchcancel = null; view.onclick = view.onpointerdown = null; activityEnd(); }
  // goOn: 继续复习 past today's share (r28: a day of words has a cap in minutes), or the extra new words of 再学 10 个
  // part 'other': 其他复习 (练习 → 复习; review-split-plan.md): mistakes, saved sentences and patterns, apart from the words
  // The word in one place and on one line (the owner, 2026-11-26: 「单词要固定在一个位置…最好是一行展示完毕，字体太大就按设备
  //尺寸缩放」): the box keeps the height of one line at the full size, so what is under it stays put too; a word wider than
  // the screen gets a smaller size, down to 60% of it, and only past that wraps (a long phrase)
  function fitWords(root) {
    root.querySelectorAll('.review:not(.vtest) .wordbig').forEach(el => {
      el.style.fontSize = ''; el.style.minHeight = ''; el.classList.add('one-line');
      const full = parseFloat(getComputedStyle(el).fontSize), w = el.clientWidth;
      if (!w || !full) return;
      el.style.minHeight = Math.ceil(full * 1.15) + 'px';
      if (el.scrollWidth <= w) return;
      const least = Math.round(full * 0.6);
      let size = Math.max(least, Math.floor(full * w / el.scrollWidth));
      el.style.fontSize = size + 'px';
      while (el.scrollWidth > w && size > least) { size -= 1; el.style.fontSize = size + 'px'; }  // a pixel of rounding left over
      if (el.scrollWidth > w) el.classList.remove('one-line');
    });
  }
  if (!fitWords.on) {
    fitWords.on = true;
    let t; window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(() => fitWords(view), 120); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => fitWords(view)).catch(() => {});
  }
  async function reviewView(goOn, part) {
    if (!S.user) return needLogin('登录后才能复习。');
    document.body.classList.add('reviewing');
    const other = part === 'other', CACHE = other ? 'flow-next-review-other' : 'flow-next-review-cache';
    // this page's address: a learner who leaves while an answer is being saved gets nothing drawn over the next page
    const HERE = location.hash;
    const R = '/api/next/review' + (other ? '?part=other' : goOn ? '?more=1' : '');
    const NAME = other ? '复习错题和句型' : '复习单词';
    const seenOld = !!(load('flow-next-review-cache') || load('flow-next-swipe-tip'));  // this device reviewed before (the cache is saved just below)
    let first, offline = false;
    try { await OUTBOX.flush(); first = await api(R); save(CACHE, { at: Date.now(), q: first }); }
    catch (e) {
      const cached = load(CACHE);
      if (!e.network || !cached || Date.now() - cached.at > 2 * 86400000) throw e;
      const done = new Set(OUTBOX.list().map(x => x.body.id)); offline = true;
      first = { ...cached.q, items: cached.q.items.filter(x => !done.has(x.id)) };
    }
    if (offline) toast('现在没有网络：先用缓存的复习，联网后自动同步');
    // the file each word will play (CLIP.wordSrc: its own small clip on an iPhone or iPad, its sprite elsewhere)
    prefetchAudio(first.items.flatMap(x => [CLIP.wordSrc(x), ...(x.examples || []).filter(e => e.audio).map(e => `/audio/${S.voice}/${encodeURIComponent(e.pack)}.json?v=${e.audio}`)]));
    const lacking = first.items.filter(x => x.kind === 'word' && !(x.examples || []).length).map(x => x.text.toLowerCase()).slice(0, 8);
    if (lacking.length && !offline) api('/api/next/vocab/examples', { words: lacking, request_id: rid('ve') }).then(r => {
      Object.entries(r.examples || {}).forEach(([w, ex]) => items.forEach(x => { if (x.text.toLowerCase() === w && !(x.examples || []).length) x.examples = ex; }));
    }).catch(() => {});
    const items = first.items.slice(), seen = new Set(items.map(x => x.id));
    let i = 0, doneN = 0, left = first, farthest = 0; const tally = { again: 0, hard: 0, good: 0, easy: 0, known: 0 };
    const OUTCOME = { passed: '过关！这张错题卡完成了，不会再出现', reread: '这题先放下：回原文把那一段再读一遍更有用', later: '后天带着原文再做一次',
      tomorrow: '今天先到这儿，明天再见它', 'once-more': '答对了，下次再换一道题确认一次' };
    // Progress counts cards, not answers: a card shown again to consolidate it does not grow the total.
    const uniq = new Set(items.map(x => x.id)), doneIds = new Set();
    // How long the rest will take, from this session's own pace (about 9 seconds a card until there is one).
    const started = Date.now(); let spent = 0;
    const eta = () => { const rest = uniq.size - doneIds.size; if (rest < 3) return ''; const per = doneN ? spent / doneN : 9000; return ` · 约 ${Math.max(1, Math.round(rest * per / 60000))} 分钟`; };
    // A full batch of the most urgent 40 out of more: said as such (先做 40 个（还有 N 个）), with a place to stop after it.
    const batchN = first.batch || 40, beyond = Math.max(0, (first.due || 0) + (first.new || 0) - first.items.length);
    const pos = () => c.repeat ? '再巩固一次' : `${beyond ? `先做 ${uniq.size} 个（还有 ${beyond} 个） · ` : ''}${Math.min(uniq.size, doneIds.size + 1)} / ${uniq.size}${c.source === 'book' && c.state === 'new' ? ' · 新词' : ''}${eta()}`;
    const foot = () => `<p class="muted tiny tc rfoot">${pos()}</p>`;
    // The buttons at the bottom, in one place on both sides of the card (the user, 2026-11-25: 「把操作的按钮全都放在底部」;
    // AnkiDroid and AnkiMobile keep them there): what is above scrolls when the answer is long, they stay (80-flat.css).
    const actions = (html, over) => `<div class="ractions">${over || ''}${html}${foot()}</div>`;
    // the word itself plays too (like the speaker beside its phonetics); a tap on it answers nothing
    const sayBtn = (label, big) => `<button class="icon-btn ${big ? 'big' : 'say-btn'}" id="sayW" type="button" aria-label="${label}（AI 朗读）">${ICON.speak}</button>`;
    // the word's own letters play it (not the whole row: a tap beside it is a tap on the card, 「点哪儿都行」)
    const wordHTML = (cls) => `<div class="wordbig${cls || ''}"><span class="tapsay">${esc(c.text)}</span></div><div class="ph">${esc(c.phonetic || '')}${sayBtn('播放读音')}</div>`;
    let undo = null;  // the latest rating, while it can be taken back (撤销)
    // the answer shown and not yet rated: 撤销 turns the card back (a slip on the front, a tap or a button, sent nothing)
    let peek = null;
    // 太简单 (语流 B9, A0): a small button at the top right on both sides of a word card, out of the three parts' way;
    // the card leaves at once, 撤销 for six seconds at the bottom
    // voice: this side plays the word (or its examples) — 「读音由 AI 合成」, one grey line under the progress bar (aiVoiceNote)
    const top = voice => `<h1 class="sr-only">${NAME}</h1><div class="rtop"><a class="link small hit44" href="#/cards">结束</a><div class="bar-progress"><i id="rp"></i></div>${peek ? '<button class="link small undo" id="undo" type="button" aria-label="撤销：回到这一张的正面">↶ 撤销</button>' : undo ? `<button class="link small undo" id="undo" type="button" aria-label="撤销上一张：${esc(undo.c.text)}">↶ 撤销</button>` : '<button class="link small undo" id="undo" type="button" disabled aria-label="撤销（还没有可撤销的）">↶ 撤销</button>'}${viewBtn()}</div>${sub(voice)}`;
    // the line under the bar (B9, 2026-11-26: the top bar is 结束 · 进度条 · 撤销 · 简|详 only, so the bar keeps its width):
    // 「读音由 AI 合成」 on the left, a grey 「太简单」 on the right for a word to recall
    const sub = voice => { const easy = c && c.kind === 'word' && !['fix', 'question', 'sound'].includes(c.mode);
      return voice || easy ? `<div class="rsub">${voice ? aiVoiceNote('读音由 AI 合成', 'p', 'rvoice') : '<span></span>'}${easy ? '<button class="link small easy-btn" id="easyBtn" type="button" aria-label="太简单，以后不用再背">太简单</button>' : ''}</div>` : ''; };
    const badge = res => { if (!other && res && res.due != null) tabCount('dueBadge', res.due + res.new, '单词'); };  // 02-shell.js
    // Touch: swipe the card right for "I know it" (or the main button), left for "I don't".
    let swipe = null;
    const onSwipe = (right, left2) => { swipe = { right, left: left2 }; };
    if (!items.length) {
      document.body.classList.remove('reviewing');
      view.innerHTML = `<div class="empty"><div class="big">✓</div><p>${other ? '现在没有要复习的错题和句型。' : '现在没有要复习的单词。'}</p><div class="row center">${other ? '<a class="btn" href="#/practice">练习</a>' : '<a class="btn" href="#/cards">单词</a>'}<a class="btn primary" href="#/">回到今日</a></div></div>`; return;
    }
    let c, t0, claim;
    const bar = () => {
      fitWords(view);
      const rp = document.getElementById('rp'); if (rp) rp.style.width = (doneIds.size / Math.max(1, uniq.size) * 100) + '%';
      const u = document.getElementById('undo'); if (u) u.onclick = takeBack;
      const eb = document.getElementById('easyBtn'); if (eb) eb.onclick = () => known();
      document.querySelectorAll('#vmode [data-v]').forEach(x => { x.onclick = () => { if ((x.dataset.v === 'detailed') !== detailed()) flipView(); }; });
    };
    const keys = map => { document.onkeydown = e => { if (!sheetEl.hidden || e.metaKey || e.ctrlKey || e.altKey) return; if (e.target.matches && e.target.matches('input,textarea')) { if (e.key === 'Enter' && map.Enter && ['spellIn', 'fixIn'].includes(e.target.id)) { e.preventDefault(); map.Enter(); } return; } const f = map[e.key] || map[e.key.toLowerCase()]; if (f) { e.preventDefault(); f(); } }; };
    swipeOn(() => swipe);
    // the swipe tip, once; where the zones' first-time guide comes it says this too
    // once per account (08-tips.js: put away on another device, or by seeing the 新手引导 through, it is not said again)
    if (TOUCH && tipSeen('swipe-tip', 'flow-next-swipe-tip') === false && !(KNOW.tap() && tipSeen('review-zones', 'flow-tap-guide') === false)) { TIPS.mark('swipe-tip'); setTimeout(() => toast(KNOW.side() === 'right' ? '小技巧：右滑「认识」，左滑「不认识」' : '小技巧：左滑「认识」，右滑「不认识」'), 600); }
    // A saved sentence pattern: the frame's fixed words become gaps in its example, so the front does not give it away.
    const frameCloze = (example, frame) => {
      const fixed = (frame.match(/[A-Za-z']+/g) || []).filter(w => !/^(A|B|C|sb|sth|do|doing|done|adj|n|v|X|Y)$/.test(w)).map(w => w.toLowerCase());
      let k = 0; const want = fixed.slice();
      return esc(example).replace(/[A-Za-z']+/g, w => (k < want.length && w.toLowerCase() === want[k]) ? (k++, `<span class="gap">${' '.repeat(Math.max(3, w.length))}</span>`) : w);
    };
    const sentenceOf = x => x.context && x.context.toLowerCase().includes(x.text.toLowerCase()) ? { text: x.context, form: x.text } : (x.examples && x.examples[0]) || null;
    const meaningHTML = x => x.meaning ? `<div class="mean-q" data-zh>${esc(x.meaning).replace(/；|;/g, '<br>')}</div>` : '';

    // Mistakes come back on the forgetting curve too: answer the question again, fix the phrase, say the sound.
    function mistakeAsk() {
      const ex = c.extra || {}, src = { reading: '理解题', writing: '写作', speaking: '口语', translation: '翻译', pronunciation: '发音', vocabulary: '词汇辨析', grammar: '语法' }[c.skill] || '错题';
      const tag = `<span class="pill amber rtag">错题 · ${esc(src)}</span>`;
      let body = '';
      if (c.mode === 'question' && c.variant) {
        // A grammar mistake comes back as a different question on the same point: the rule is practised, not one answer.
        const v = c.variant;
        body = `${tag}<div class="tiny muted">${v.kind === 'word' ? '同一组易混词，换一道题：' + esc(c.text) : '同一个语法点，换一道题' + (c.node ? '：' + esc(c.node.title) : '')}</div><div class="prompt-q">${esc(v.prompt)}</div>
          <div class="qopts">${v.options.map((o, k) => `<button class="qopt" data-o="${v.map ? v.map[k] : k}">${esc(o)}</button>`).join('')}</div>`;
      } else if (c.mode === 'question') {
        // A reading question comes back with its part of the text: it is answered by reading, not by remembering.
        const opts = ex.options || [], ps = c.passage;
        body = `${tag}${ps ? `<div class="passage-q"><div class="tiny muted">原文片段${ps.title ? ' · ' + esc(ps.title) : ''}</div><p class="ptext" id="ptext">${ps.start ? '… ' : ''}${esc(ps.text)}${ps.end ? ' …' : ''}</p></div>` : ''}
          <div class="prompt-q">${esc(c.text)}</div><div class="qopts">${opts.map((o, k) => `<button class="qopt" data-o="${k}">${esc(o)}</button>`).join('')}</div>`;
      } else if (c.mode === 'fix') {
        // Just the sentence the mistake was in (older cards kept the whole paragraph), with the wrong part underlined.
        const sent = c.context && ex.from ? (splitSentences(c.context).find(x => x.toLowerCase().includes(ex.from.toLowerCase())) || '') : '';
        const ctx = sent ? highlight(sent, ex.from) : '';
        body = `${tag}<div class="muted small">上次这样写：</div><div class="cloze fixq">${ctx || `<mark>${esc(ex.from || '')}</mark>`}</div>
          ${c.node ? `<div>${nodeChip({ id: c.node.id, title: c.node.title, status: 'watch' })}</div>` : ''}
          <input id="fixIn" class="spell" lang="en" enterkeyhint="done" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" placeholder="划线部分应该怎么写？">
          <div class="row center"><button class="btn primary" id="fixGo">确定</button><button class="btn ghost" id="fixNo">想不起来</button></div>`;
      } else {
        body = `${tag}<div class="wordbig">${esc(c.text)}</div><div class="row center">${sayBtn('听', true)}</div>
          ${c.meaning ? `<div class="mean-q small" data-zh>${esc(c.meaning)}</div>` : ''}
          <div class="row center">${recBtn('sndMic', '读一遍', true)}<span class="muted tiny" id="sndOut">${S.user ? '点录音键读一遍，AI 听你读得准不准' : ''}</span></div>
          ${actions(`<div class="choice">${KNOW.order([['读准了', 'good', 'good'], ['还不稳', '', 'hard'], ['不会读', 'again', 'again']]).map(([t, cls, r]) => `<button class="${cls}" data-self="${r}">${t}</button>`).join('')}</div>`)}`;
      }
      // A question or a sentence to fix has no word to put in the middle of the screen: it starts at the top.
      view.innerHTML = `${top(c.mode === 'sound')}<div class="review enter${c.mode === 'sound' ? '' : ' q'}">${body}${c.mode === 'sound' ? '' : foot()}</div>`;
      bar(); swipe = null;
      const after = (r, html) => {
        const ms = Date.now() - t0;
        view.querySelector('.review').insertAdjacentHTML('beforeend', `<div class="stack-s enter">${html}<div class="row center"><button class="btn primary" id="go">下一个</button></div></div>`);
        document.getElementById('go').onclick = () => rate(r, ms); keys({ Enter: () => rate(r, ms), ' ': () => rate(r, ms) });
      };
      if (c.mode === 'question' && c.variant) {
        view.querySelectorAll('[data-o]').forEach(b => b.onclick = async () => {
          view.querySelectorAll('[data-o]').forEach(x => { x.disabled = true; });
          let r;
          if (c.variant.kind === 'word') {  // a word group: checked here, the answer recorded for the group's progress
            r = { correct: Number(b.dataset.o) === c.variant.answer, answer: c.variant.answer, explanation: c.variant.explanation };
            api('/api/next/words/confuse/answer', { item: c.variant.id, correct: r.correct, from: 'review' }).catch(() => {});
          } else {
            try { r = await api('/api/next/node/answer', { question: c.variant.id, choice: Number(b.dataset.o), from: 'review' }); }
            catch (e) { toast(e.message); view.querySelectorAll('[data-o]').forEach(x => { x.disabled = false; }); return; }
          }
          view.querySelectorAll('[data-o]').forEach(x => { if (Number(x.dataset.o) === r.answer) x.classList.add('right'); });
          if (!r.correct) b.classList.add('wrong');
          after(r.correct ? 'good' : 'again', `<div class="${r.correct ? 'ok' : 'bad'}">${r.correct ? '✓ 换了一道题也答对了' : '这题没答对'}</div><div class="small" data-zh>${esc(r.explanation || '')}</div>
            ${!r.correct && c.variant.kind === 'word' ? `<div class="tiny muted" data-zh>${esc(c.meaning || '')}</div>` : ''}
            ${!r.correct && c.node ? `<a class="link small" href="#/graph/${encodeURIComponent(c.node.id)}">回到「${esc(c.node.title)}」看一遍讲解 →</a>` : ''}`);
        });
        keys({ 1: () => view.querySelector('.qopt:nth-child(1)').click(), 2: () => view.querySelector('.qopt:nth-child(2)').click(), 3: () => view.querySelector('.qopt:nth-child(3)').click(), 4: () => view.querySelector('.qopt:nth-child(4)').click() });
      } else if (c.mode === 'question') {
        view.querySelectorAll('[data-o]').forEach(b => b.onclick = () => {
          const k = Number(b.dataset.o), ok = k === ex.answer, ps = c.passage;
          view.querySelectorAll('[data-o]').forEach(x => { x.disabled = true; if (Number(x.dataset.o) === ex.answer) x.classList.add('right'); });
          if (!ok) b.classList.add('wrong');
          const pt = document.getElementById('ptext'); if (pt && ps && ps.evidence) pt.innerHTML = (ps.start ? '… ' : '') + highlight(ps.text, ps.evidence) + (ps.end ? ' …' : '');
          after(ok ? 'good' : 'again', `<div class="${ok ? 'ok' : 'bad'}">${ok ? '✓ 这次答对了，这道题过关' : '还是没答对'}</div>${ex.evidence && !(pt && ps) ? `<div class="small"><span class="muted">原文依据：</span>${esc(ex.evidence)}</div>` : ''}
            ${!ok && c.pack ? `<a class="link small" href="#/m/${encodeURIComponent(c.pack)}/read">回原文把这一段再读一遍 →</a>` : ''}`);
        });
        keys({ 1: () => view.querySelector('[data-o="0"]').click(), 2: () => view.querySelector('[data-o="1"]').click(), 3: () => view.querySelector('[data-o="2"]').click(), 4: () => view.querySelector('[data-o="3"]').click() });
      } else if (c.mode === 'fix') {
        const inp = document.getElementById('fixIn'); setTimeout(() => inp.focus(), 50);
        const norm = s => s.toLowerCase().replace(/[^a-z' ]+/g, ' ').replace(/\s+/g, ' ').trim();
        const done = v => {
          view.querySelectorAll('#fixGo,#fixNo').forEach(b => b.remove()); inp.disabled = true;
          const ok = !!v && norm(v) === norm(c.text);
          if (ok || !v) return after(ok ? 'good' : 'again', `<div class="${ok ? 'ok' : 'bad'}">${ok ? '✓ 改对了' : '应该是'}：<b>${esc(c.text)}</b></div>${c.meaning ? `<div class="small" data-zh>${esc(c.meaning)}</div>` : ''}`);
          // Not the same words: often a correct other wording. The learner compares and decides; no loop over one word.
          const ms = Date.now() - t0;
          view.querySelector('.review').insertAdjacentHTML('beforeend', `<div class="stack-s enter"><div class="small"><span class="muted">你写的：</span>${esc(v)}</div>
            <div class="small"><span class="muted">参考改法：</span><b>${esc(c.text)}</b></div>${c.meaning ? `<div class="small muted" data-zh>${esc(c.meaning)}</div>` : ''}
            <div class="row center"><button class="btn" id="fixSame">我写的也对</button><button class="btn primary" id="fixMiss">没写对，记下了</button></div></div>`);
          document.getElementById('fixSame').onclick = () => rate('good', ms); document.getElementById('fixMiss').onclick = () => rate('again', ms);
        };
        document.getElementById('fixGo').onclick = () => done(inp.value.trim());
        document.getElementById('fixNo').onclick = () => done('');
        keys({ Enter: () => done(inp.value.trim()) });
      } else {
        document.getElementById('sayW').onclick = () => CLIP.word(c); CLIP.word(c);
        const mic = document.getElementById('sndMic'), out = document.getElementById('sndOut');
        mic.onclick = () => MIC.toggle(mic, 4, async blob => {
          out.innerHTML = '<span class="spin"></span>';
          try { const x = (await api('/api/next/say', { text: c.text, audio: await MIC.payload(blob), request_id: rid('sy') })).result; out.innerHTML = aiTag() + ' ' + (x.ok ? '<span class="ok-mark">✓ 这次读准了</span>' : `<span class="bad-mark">AI 听成了「${esc(x.heard || '?')}」</span><div class="tiny muted">${esc(x.tip || x.note || '')}</div>`) + (x.tentative ? '<div class="tiny muted">AI 的判断只作参考，不会进错题本</div>' : ''); }
          catch (e) { out.textContent = e.message; }
        });
        view.querySelectorAll('[data-self]').forEach(b => b.onclick = () => rate(b.dataset.self, Date.now() - t0));
        onSwipe(...KNOW.swipe(() => rate('good', Date.now() - t0), () => rate('again', Date.now() - t0)));
      }
    }
    function ask(quiet) {
      if (location.hash !== HERE) return;
      if (i >= items.length) return more();
      c = items[i]; claim = null; t0 = Date.now(); view.onclick = view.onpointerdown = null;
      if (['fix', 'question', 'sound'].includes(c.mode)) return mistakeAsk();
      const sent = sentenceOf(c), pattern = c.kind !== 'word' && /^句型｜例：/.test(c.meaning || '');
      // Nothing to recall from (an imported phrase with no meaning or sentence): show it and ask whether it is known.
      const m = (c.mode === 'recall' || c.mode === 'cloze') && !c.meaning && !sent ? 'recognize' : c.mode;
      let body = '', choices = '';
      if (m === 'recognize') {
        body = wordHTML(c.kind === 'word' ? '' : ' phrase') + (detailed() ? `<div class="detail-line">${esc(metaLine())}</div>` : '');
        choices = ['认识', '模糊', '不认识'];
      } else if (m === 'spell') {
        body = `<div class="muted small">听发音，拼出这个词</div><div class="row center">${sayBtn('再听一次', true)}</div>${meaningHTML(c)}
          ${sent ? `<div class="cloze">${gapped(sent.text, sent.form, false)}</div>` : ''}
          <input id="spellIn" class="spell" lang="en" enterkeyhint="done" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" aria-label="拼写" placeholder="输入单词">`;
      } else if (pattern) {
        body = `<div class="hint">回忆这个句型</div><div class="cloze">${frameCloze(c.meaning.replace(/^句型｜例：/, ''), c.text)}</div>`;
        choices = ['想起来了', '有点模糊', '想不起来'];
      } else {
        body = `${meaningHTML(c) || '<div class="hint">回忆这个表达</div>'}${sent ? `<div class="cloze">${gapped(sent.text, sent.form, false)}</div>` : `<div class="cloze"><span class="gap">？</span></div>`}
          ${c.kind === 'word' ? `<div class="muted tiny">首字母 ${esc(c.text[0])} · ${c.text.length} 个字母</div>` : ''}`;
        choices = ['想起来了', '有点模糊', '想不起来'];
      }
      view.innerHTML = `${top(m === 'recognize' || m === 'spell')}<div class="review enter">${body}
        ${m === 'spell' ? `<div class="row center"><button class="btn primary" id="check">确定</button><button class="btn ghost" id="giveup">不会</button></div>${foot()}`
          : actions(`<div class="choice">${KNOW.order(choices.map((t, k) => [t, ['good', '', 'again'][k], ['know', 'fuzzy', 'forgot'][k]])).map(([t, cls, how], k) => `<button class="${cls}" data-claim="${how}">${t}${TOUCH ? '' : `<small>${['←', '↓', '→'][k]}</small>`}</button>`).join('')}</div>`)}</div>`;
      // 「认识」 moved to the right (2026-11-25): said once to those who reviewed before, so a habit does not answer wrong
      if (m !== 'spell' && first.veteran && seenOld && KNOW.side() === 'right' && tipSeen('know-side', 'flow-know-tip') === false) {
        (view.querySelector('.review .ph') || view.querySelector('.review')).insertAdjacentHTML(view.querySelector('.review .ph') ? 'afterend' : 'afterbegin', `<div class="know-tip" id="knowTip" role="note"><span class="small">「认识」换到右边了，想换回去：我的 → 使用习惯</span><button class="btn small" type="button" id="knowTipOk">知道了</button></div>`);
        document.getElementById('knowTipOk').onclick = () => { TIPS.mark('know-side'); const t = document.getElementById('knowTip'); if (t) t.remove(); };
      }
      bar(); swipe = null;
      sayable();
      if (!quiet && (m === 'recognize' || m === 'spell')) CLIP.word(c);
      if (m === 'spell') {
        const inp = document.getElementById('spellIn'); setTimeout(() => inp.focus(), 50);
        const check = () => { const v = inp.value.trim(); if (!v) return; spellResult(v); };
        document.getElementById('check').onclick = check; document.getElementById('giveup').onclick = () => spellResult('');
        keys({ Enter: check });
      } else {
        view.querySelectorAll('[data-claim]').forEach(b => b.onclick = () => reveal(b.dataset.claim));
        const fronts = [...view.querySelectorAll('[data-claim]')].map(b => () => reveal(b.dataset.claim));
        keys({ ...KNOW.keys(fronts), ArrowDown: fronts[1], ' ': fronts[1], e: () => c.kind === 'word' && known() });  // ← 不会 · ↓ or space 模糊 · → 会 (by place) · E 太简单
        if (KNOW.tap()) tapZones([...view.querySelectorAll('.ractions [data-claim]')]);
        onSwipe(...KNOW.swipe(() => reveal('know'), () => reveal('forgot')));
      }
    }
    // One rule on every side of the card (the owner, 2026-11-26: 「一以贯之的用户操作习惯，不要反直觉」): the page is the
    // buttons below it, part for part — three on the front (不会 · 模糊 · 会), two on the back (记错了 · 没错), and when the
    // back has one button the whole page is it (下一个). 「认识」's side (KNOW) sets which end is which, for taps, swipes and
    // keys alike. What can be tapped (the word, a speaker, 再看, 撤销, links, the top line) does its own thing first; a
    // finger that moved, a swipe just done, or a tap in the first moment after the card turned (a double tap) answers nothing.
    // the part tapped lights up for a moment with the word it stands for (不认识, 模糊, 认识 …): an answer is seen to be taken
    function flash(r, n, k, btn) {
      const f = document.createElement('div'), tone = btn.classList.contains('good') ? 'good' : btn.classList.contains('again') ? 'again' : 'mid';
      f.className = 'zone-flash ' + tone; f.textContent = btn.firstChild.textContent.replace(/，.*$/, '');
      Object.assign(f.style, { left: (r.left + r.width * k / n) + 'px', width: (r.width / n) + 'px', top: Math.max(0, r.top) + 'px', height: Math.min(innerHeight, r.bottom) - Math.max(0, r.top) + 'px' });
      document.body.appendChild(f); setTimeout(() => f.remove(), REDUCED ? 250 : 520);
    }
    let turned = 0;
    function tapZones(btns, back) {
      if (!btns.length) return;
      const card = view.querySelector('.review'); if (!card) return;
      card.classList.add('zoned'); turned = Date.now();  // a new card or a turned one: the next 600 ms are not an answer
      const skip = '.tapsay,#sayW,[data-exp],a,button,input,summary,details,.ractions,.know-tip,.rtop,.rsub,.rvoice,.sheet';
      let down = null;
      view.onpointerdown = e => { down = [e.clientX, e.clientY]; };
      view.onclick = e => {
        const d = down; down = null;
        if (!card.isConnected) { view.onclick = view.onpointerdown = null; return; }  // the card is gone (rated, the round over)
        if (Date.now() - turned < 600 || Date.now() - SCROLLED < 300) return;  // a double tap, or the tap that ends a scroll
        const g = card.querySelector('.zone-guide'); if (g) { g.remove(); return; }  // the first tap puts the guide away, answers nothing
        if (e.target.closest(skip) || !d || Math.hypot(e.clientX - d[0], e.clientY - d[1]) > 10 || Date.now() - SWIPED < 350) return;
        const r = card.getBoundingClientRect(), n = btns.length;
        const k = Math.min(n - 1, Math.max(0, Math.floor((e.clientX - r.left) / (r.width / n))));
        flash(r, n, k, btns[k]); btns[k].click();
      };
      // the first time on each side: its parts drawn over the card, a tap puts it away (and answers nothing); once per
      // account (08-tips.js), so another phone does not draw it again
      const tip = back ? 'review-zones-back' : 'review-zones', local = back ? 'flow-tap-guide-back' : 'flow-tap-guide';
      const draw = () => {
        if (!card.isConnected || card.querySelector('.know-tip, #zoneGuide')) return;
        const swipe = KNOW.side() === 'right' ? ['右滑', '左滑'] : ['左滑', '右滑'];
        const say = !back ? `点左、中、右也能作答，和下面的按钮一样；也可以${swipe[0]}「认识」，${swipe[1]}「不认识」。点单词只是播放。点一下收起`
          : `翻面也是这三块：${swipe[0]}或点${KNOW.side() === 'right' ? '右' : '左'}边是没错，另一边是记错了，中间是模糊。翻面前选的那个加了框，回车或空格就是它。点一下收起`;
        card.insertAdjacentHTML('beforeend', `<div class="zone-guide n${btns.length}" id="zoneGuide" aria-hidden="true">${btns.map(b => `<span>${esc(b.firstChild.textContent)}</span>`).join('')}<p>${say}</p></div>`);
        const gd = document.getElementById('zoneGuide'), ra = card.querySelector('.ractions');
        if (ra) gd.style.bottom = (card.getBoundingClientRect().bottom - ra.getBoundingClientRect().top) + 'px';  // the buttons stay in view below it
        // shown once: seen now. It lets taps through (pointer-events: none), so the word still plays and the buttons answer;
        // a tap on the page itself only puts it away (above)
        TIPS.mark(tip); TIPS.mark('swipe-tip');
      };
      // not known on this phone yet (a new device): drawn over the card, it can come when the answer does without moving
      // anything; known: now or never
      const seen = tipSeen(tip, local);
      if (seen === false) draw(); else if (seen === null) TIPS.load().then(() => { if (tipSeen(tip, local) === false) draw(); });
    }
    // the speaker and the word play it; the examples' speakers are bound by bindExamples
    function sayable() {
      view.querySelectorAll('#sayW, .review .tapsay').forEach(b => { b.onclick = () => CLIP.word(c); });
    }
    function answerHTML() {
      if (!detailed()) return `${wordHTML()}
        ${c.meaning ? `<div class="mean-a" data-zh>${esc(c.meaning).replace(/；|;/g, '<br>')}</div>` : ''}${rootsHTML(c)}${examplesHTML({ ...c, examples: (c.examples || []).slice(0, 2) })}`;
      // 详细 (B9's sheet, words-modes/): the meaning by part of speech, the roots, the examples as many as 简洁 shows (two)
      // and the rest one tap away, the confusable group (词汇辨析) with how to tell them apart, a grey line of how well it is held
      const pos = (c.meaning || '').split(/；|;/).map(x => x.trim()).filter(Boolean).map(x => { const m = x.match(/^([a-z]+\.)\s*(.*)$/);
        return m ? `<b>${esc(m[1])}</b><span>${esc(m[2])}</span>` : `<span class="all">${esc(x)}</span>`; }).join('');  // a grid: the 词性 column as wide as its widest (B9, r36 audit)
      const g = (c.confuse || [])[0], n = (c.context ? 1 : 0) + (c.examples || []).length, open = 2;
      return `${wordHTML()}${pos ? `<div class="mean-a mean-pos" data-zh>${pos}</div>` : ''}${rootsHTML(c)}
        <div class="ex-wrap${n > open ? ' fold' : ''}">${examplesHTML(c)}${n > open ? `<button class="ex-more" type="button" id="exMore">再看 ${n - open} 句 ⌄</button>` : ''}</div>
        ${g ? `<details class="conf-wrap"><summary class="conf-line"><span>易混：${g.words.map(w => `<b>${esc(w)}</b>`).join(' / ')}</span><span class="how">怎么区分 ›</span></summary><p class="small" data-zh>${esc(g.how)}</p></details>` : ''}
        ${extrasHTML(c)}
        <div class="mem-line">${esc(memLine())}</div>`;
    }
    // 简洁 / 详细 for this card (KNOW.view): words only, new words and reviews apart; the switch at the top changes it for
    // that kind and keeps it; the card is drawn again in place (not an answer, the clock runs on)
    function detailed() { return !!c && c.kind === 'word' && KNOW.view(c.state === 'new' ? 'new' : 'review') === 'detailed'; }
    function viewBtn() {
      if (!c || c.kind !== 'word' || ['fix', 'question', 'sound'].includes(c.mode)) return '';
      const d = detailed();
      return `<div class="vt" id="vmode" role="radiogroup" aria-label="复习卡">${[['simple', '简', '简洁'], ['detailed', '详', '详细']].map(([v, t, l]) => `<button type="button" role="radio" data-v="${v}" aria-label="${l}" aria-checked="${(v === 'detailed') === d}"${(v === 'detailed') === d ? ' class="on"' : ''}>${t}</button>`).join('')}</div>`;
    }
    function flipView() {
      KNOW.setView(c.state === 'new' ? 'new' : 'review', detailed() ? 'simple' : 'detailed');
      if (view.querySelector('.open-card') && claim) reveal(claim, true);
      else { const t = t0; ask(true); t0 = t; }
    }
    const TAGS = { zk: '中考', gk: '高考', cet4: '四级', cet6: '六级', ky: '考研', tem4: '专四', tem8: '专八', ielts: '雅思', toefl: '托福', gre: 'GRE' };
    const ago = s => { const d = Math.floor((Date.now() / 1000 - s) / 86400); return d <= 0 ? '今天' : d === 1 ? '昨天' : d + ' 天前'; };
    // 详细's grey line on the front: which exams list it, how common it is, how many times seen — nothing of its meaning
    function metaLine() {
      const r = c.rank || 0, freq = !r ? '' : r <= 2000 ? '最常用' : r <= 5000 ? '常用' : r <= 10000 ? '较常用' : '';
      const seen = c.state === 'new' || !c.reps ? '新词' : `第 ${c.reps + 1} 次见${c.last ? ' · 上次 ' + ago(c.last) : ''}`;
      return [...(c.tags || []).map(t => TAGS[t]).filter(Boolean).slice(0, 3), freq, seen].filter(Boolean).join(' · ');
    }
    function memLine() {
      if (c.state === 'new' || !c.reps) return '新词 · 第一次见';
      const r = c.recall == null ? null : c.recall;
      return `记得的把握：${r == null ? '—' : r >= 0.9 ? '高' : r >= 0.7 ? '中' : '低'} · 复习过 ${c.reps} 次${c.lapses ? `，忘过 ${c.lapses} 次` : ''}`;
    }
    function reveal(how, quiet) {
      claim = how; const ms = Date.now() - t0; peek = { t0 };
      if (!quiet) haptic('select');
      // The back has the front's three parts too, the same width, place and colour (the owner: 「只做了一个界面的三分点」):
      // left 记错了 (again), middle 模糊 (hard), right 没错 (good). The one the front chose is framed: ↵ and space take it, and
      // the back can still change it (认识 thought, the answer seen, it was wrong: the left). After 不认识 the right says
      // 其实认识 — a slip on the front, mended — never 记住了: what is rated is what was recalled before the answer.
      const right = how === 'forgot' ? '其实认识' : '没错';
      const want = { know: 'good', fuzzy: 'hard', forgot: 'again' }[how];
      const next = KNOW.order([[right, 'good', 'good'], ['模糊', 'hard', ''], [how === 'forgot' ? '不认识' : '记错了', 'again', 'again']]);
      view.innerHTML = `${top(true)}<div class="review open-card">${answerHTML()}
        ${actions(`<div class="choice">${next.map(([t, r, cls], k) => `<button class="${cls}${r === want ? ' def' : ''}" data-rate="${r}"${r === want ? ' aria-describedby="defNote"' : ''}>${t}${TOUCH ? '' : `<small>${['←', '↓', '→'][k]}</small>`}</button>`).join('')}</div><span class="sr-only" id="defNote">翻面前选的就是这一个，回车或空格就是它</span>`)}</div>`;
      bar(); bindExamples(view, c); bindExtras(view, c); sayable();
      const em = document.getElementById('exMore'); if (em) em.onclick = () => { em.closest('.ex-wrap').classList.remove('fold'); em.remove(); };
      if (!quiet && c.mode !== 'recognize') CLIP.word(c);
      view.querySelectorAll('[data-rate]').forEach(b => b.onclick = () => rate(b.dataset.rate, ms));
      const acts = next.map(([, r]) => () => rate(r, ms));
      keys({ ...KNOW.keys(acts), ArrowDown: acts[1], Enter: () => rate(want, ms), ' ': () => rate(want, ms), x: () => rate('again', ms), e: () => known() });
      onSwipe(...KNOW.swipe(() => rate('good', ms), () => rate('again', ms)));  // the same way as on the front
      if (KNOW.tap()) tapZones([...view.querySelectorAll('.ractions [data-rate]')], true);
    }
    function spellResult(v) {
      const ms = Date.now() - t0, want = c.text.toLowerCase(), got = v.toLowerCase();
      const dist = (a, b) => { const d = Array.from({ length: a.length + 1 }, (_, k) => [k]); for (let j = 1; j <= b.length; j++) d[0][j] = j;
        for (let k = 1; k <= a.length; k++) for (let j = 1; j <= b.length; j++) d[k][j] = Math.min(d[k - 1][j] + 1, d[k][j - 1] + 1, d[k - 1][j - 1] + (a[k - 1] === b[j - 1] ? 0 : 1)); return d[a.length][b.length]; };
      const r = !got ? 'again' : got === want ? 'good' : (want.length > 4 && dist(got, want) === 1) ? 'hard' : 'again';
      const msg = r === 'good' ? '<div class="ok">✓ 拼对了</div>' : r === 'hard' ? `<div class="warn">差一点：你写的是 <s>${esc(v)}</s></div>` : got ? `<div class="bad">你写的是 <s>${esc(v)}</s></div>` : '';
      view.innerHTML = `${top(true)}<div class="review open-card">${answerHTML()}${actions('<div class="choice one"><button class="primary" id="go">下一个</button></div>')}</div>`;
      const ph = view.querySelector('.open-card .ph'); if (ph && msg) ph.insertAdjacentHTML('afterend', msg);  // under the word: the word keeps its place
      bar(); bindExamples(view, c); bindExtras(view, c); sayable(); CLIP.word(c);
      const em = document.getElementById('exMore'); if (em) em.onclick = () => { em.closest('.ex-wrap').classList.remove('fold'); em.remove(); };
      document.getElementById('go').onclick = () => rate(r, ms); keys({ Enter: () => rate(r, ms), ' ': () => rate(r, ms) });
      onSwipe(...KNOW.swipe(() => rate(r, ms), null));
    }
    let busy = false;
    async function rate(r, ms) {
      if (busy) return; busy = true; document.onkeydown = null; peek = null; view.onclick = view.onpointerdown = null;  // one answer per card
      try {
        const body = { id: c.id, rating: r, mode: c.mode, ms: Math.min(ms, 3599999), at: Math.floor(Date.now() / 1000) };
        const before = { c, r, i, had: doneIds.has(c.id), left, inserted: -1, offline: false, body };
        let res;
        try { res = await api('/api/next/review', body); }
        catch (e) {
          if (!e.network) throw e;
          OUTBOX.push({ path: '/api/next/review', body }); before.offline = true;  // offline: keep going, sync later
          const learning = c.state !== 'review' || r === 'again';
          res = { card: { ...c, state: learning && r !== 'easy' ? (c.state === 'review' ? 'relearning' : 'learning') : 'review' }, due: left ? left.due : 0, new: left ? left.new : 0 };
          if (r === 'good' && c.state === 'learning' && (c.step || 0) >= 1) res.card.state = 'review';
          res.card.step = (c.step || 0) + 1;
        }
        tally[r]++; doneN++; left = res; i++; doneIds.add(c.id); badge(res); spent += Math.min(ms, 60000); undo = before;
        haptic(r === 'again' ? 'warning' : r === 'hard' ? 'tap' : 'success');
        if (!other) activity('review', doneIds.size, uniq.size);
        const n = res.card;
        if (res.outcome && OUTCOME[res.outcome]) toast(OUTCOME[res.outcome]);
        if ((r === 'good' || r === 'easy') && n.due) farthest = Math.max(farthest, Math.round((n.due * 1000 - Date.now()) / 86400000));
        // Only what is due again within minutes (a miss, or a fuzzy new card) comes back in this session, a few cards later;
        // a card answered right waits for its next step (10 minutes, then days) and is picked up by "继续" or the next session.
        const soon = n.due ? n.due * 1000 - Date.now() < 5 * 60000 : r === 'again';
        // At most one more try in this session; a card missed again waits for tomorrow (the server moves it there too).
        const parked = ['tomorrow', 'later', 'passed', 'reread'].includes(res.outcome) || (c.tries || 0) >= 1;
        if ((n.state === 'learning' || n.state === 'relearning') && soon && !parked) {
          const again = { ...c, ...n, mode: c.kind === 'word' ? 'recognize' : c.mode, repeat: true, tries: (c.tries || 0) + 1 };
          before.inserted = Math.min(items.length, i + 4); items.splice(before.inserted, 0, again);
        }
        const el = view.querySelector('.review'); if (el) el.classList.add('out');
        setTimeout(ask, REDUCED ? 0 : 180);
      } catch (e) { toast(e.message); keys({}); }
      finally { busy = false; }
    }
    // 撤销: the latest rating taken back (a slip of the finger); the same card comes up again to answer.
    async function takeBack() {
      if (peek && !busy) { const t = peek.t0; peek = null; ask(true); t0 = t; haptic('tap'); return; }  // the front again; the time runs on
      const u = undo; if (!u || busy) return; busy = true;
      try {
        let res = u.left;
        if (u.offline) OUTBOX.unpush({ path: '/api/next/review', body: u.body });
        else res = await api('/api/next/review/undo', { id: u.c.id });
        tally[u.r]--; doneN--; if (!u.had) doneIds.delete(u.c.id);
        if (u.inserted >= 0) items.splice(u.inserted, 1);
        i = u.i; left = res; undo = null; badge(res);
        toast('已撤销，再答一次这一张'); haptic('tap'); ask();
      } catch (e) { undo = null; toast(e.message); const b = document.getElementById('undo'); if (b) b.remove(); }
      finally { busy = false; }
    }
    async function known() {
      if (busy) return; busy = true; peek = null; view.onclick = view.onpointerdown = null;
      const was = { c, i };
      try { const res = await api('/api/next/vocab/known', { id: c.id, known: true }); tally.known++; doneN++; i++; doneIds.add(c.id); left = res; haptic('tap'); easyBar(was); ask(); }
      catch (e) { toast(e.message); } finally { busy = false; }
    }
    // 「已标为太简单，不再复习 · 撤销」 at the bottom for six seconds; 撤销 brings the card back to be answered
    function easyBar(was) {
      document.querySelectorAll('.easy-bar').forEach(x => x.remove());
      const b = document.createElement('div'); b.className = 'easy-bar'; b.setAttribute('role', 'status');
      b.innerHTML = `<span>已标为太简单，「${esc(was.c.text)}」不再复习</span><button class="link small" type="button">撤销</button>`;
      document.body.appendChild(b);
      const gone = setTimeout(() => b.remove(), 6000);
      b.querySelector('button').onclick = async () => {
        clearTimeout(gone); b.remove();
        try { left = (await api('/api/next/vocab/known', { id: was.c.id, known: false })); tally.known--; doneN--; doneIds.delete(was.c.id); items.splice(i, 0, was.c); haptic('tap'); toast('已撤销，再答一次这一张'); ask(); }
        catch (e) { toast(e.message); }
      };
    }
    async function more() {
      document.onkeydown = null;
      try {
        const q = await api(R);
        const fresh = q.items.filter(x => !seen.has(x.id) || (x.state !== 'new' && x.due * 1000 <= Date.now()));
        const extra = fresh.filter(x => !items.slice(i).some(y => y.id === x.id));
        // this batch's own cards due again (a miss, a learning step) are finished first; after a full batch, the next
        // one waits behind a place to stop
        const back = extra.filter(x => seen.has(x.id)), next = extra.filter(x => !seen.has(x.id));
        const go = back.length ? back : uniq.size >= batchN ? [] : next;
        if (go.length) { go.forEach(x => { seen.add(x.id); uniq.add(x.id); items.push(x); }); return ask(); }
        left = q;
      } catch (e) { /* show the summary anyway */ }
      refreshHome().catch(() => {});
      if (location.hash !== HERE) return;
      swipeOff(); document.body.classList.remove('reviewing');
      undo = null;
      const rated = tally.again + tally.hard + tally.good + tally.easy, mins = Math.max(1, Math.round((Date.now() - started) / 60000));
      view.innerHTML = `<h1 class="sr-only">${NAME}</h1><div class="card done-card enter">${doneRing}<h2 class="h2">这一轮复习了 ${doneIds.size} 个</h2>
        <p class="small rsum">用时约 ${mins} 分钟${rated ? ` · 记住了 ${Math.round((tally.good + tally.easy) / rated * 100)}%` : ''}<span id="tmr"></span></p>${doneN > doneIds.size ? `<p class="muted tiny">共作答 ${doneN} 次，其中 ${doneN - doneIds.size} 次是再巩固</p>` : ''}
        <p class="muted small">记得 ${tally.good + tally.easy} · 模糊 ${tally.hard} · 忘了 ${tally.again}${tally.known ? ' · 熟知 ' + tally.known : ''}。</p>
        <p class="small cheer">${tally.good + tally.easy ? `记得的都往后推了${farthest > 1 ? `，最远的要 ${farthest} 天后才再见` : ''}。` : ''}${tally.again ? `忘了的 ${tally.again} 个明天再来：忘了再想起来，正是记牢的过程。` : tally.good + tally.easy ? '这一轮全都记得，很稳。' : ''}</p>
        ${left && !(left.due + left.new) && left.later ? `<p class="small stop-ok" id="capDone"><b>今天的单词做完了。</b>还有 ${left.later} 个复习留到之后几天，最容易忘的排在前面。想多背可以继续。</p>` : ''}
        ${left && (left.due + left.new) ? (uniq.size >= batchN
          ? `<p class="small stop-ok" id="stopOk"><b>今天做到这里也行。</b>最要紧的 ${uniq.size} 个已经复习过了，还有 ${left.due + left.new} 个，之后几天接着来，最容易忘的排在前面。</p>`
          : `<p class="small">还有 ${left.due + left.new} 个可以继续。</p>`) : ''}
        <div class="row center">${left && (left.due + left.new) && uniq.size >= batchN
          ? `<button class="btn" id="again">再做 ${Math.min(batchN, left.due + left.new)} 个</button><a class="btn primary" href="#/">今天就到这里</a>`
          : `${left && !(left.due + left.new) && left.later ? '<button class="btn" id="againMore">继续复习</button>' : (other ? '<a class="btn" href="#/practice">练习</a>' : '<a class="btn" href="#/cards">单词</a>')}${left && (left.due + left.new) ? '<button class="btn primary" id="again">继续</button>' : '<a class="btn primary" href="#/">回到今日</a>'}`}</div>
        ${left && !(left.due + left.new) && !left.later ? '<div class="row center"><button class="btn ghost small" id="moreNew">还想多背：再学 10 个新词</button></div>' : ''}
        ${left && !(left.due + left.new) ? '<div class="row center"><button class="link small hit44" type="button" id="onceAsk">今天或明天什么时候有空复习？</button></div>' : ''}</div>`;
      api('/api/next/vocab').then(o => { const t = document.getElementById('tmr'); if (t && o.forecast && o.forecast[1] != null) t.textContent = ` · 明天大约复习 ${o.forecast[1]} 个`; }).catch(() => {});
      const ag = document.getElementById('again'); if (ag) ag.onclick = () => reviewView(goOn);
      const am = document.getElementById('againMore'); if (am) am.onclick = () => reviewView(true);
      const oa = document.getElementById('onceAsk'); if (oa) oa.onclick = () => remindOnce();
      const mn = document.getElementById('moreNew');
      if (mn) mn.onclick = async () => { mn.disabled = true; try { const r = await api('/api/next/vocab/more', { n: 10 }); if (r.added) reviewView(true); else { toast('词书里的词都学过了'); } } catch (e) { toast(e.message); mn.disabled = false; } };
    }
    ask();
  }

  /* ---------- learner model: ability profile, daily path, level suggestion ---------- */
  const LV_W = { A2: 25, B1: 50, B2: 75, C1: 100 };
  // Practice evidence of the last 45 days, skill by skill: shown folded at the foot of the ability radar.
  function abilityHTML(ab) {
    const ev = s => s.id === 'vocab' ? (s.size ? `词汇量约 ${s.size.toLocaleString()}` : (s.count ? `已掌握 ${s.count} 词` : '测一次词汇量'))
      : s.id === 'grammar' ? (s.count ? `${s.count} 个知识点用对或做对${s.watch ? ` · ${s.watch} 个要留意` : ''}` : '读和写的时候会点亮')
      : s.count ? `${s.count} 次练习 · 平均 ${Math.round((s.avg || 0) * 100)}%` : '还没练过';
    return `<div class="ab-list" id="ability">${ab.skills.map(s => `<div class="ab ${s.level ? '' : 'none'}"><span class="nm">${esc(s.label)}</span><span class="vbar"><i data-w="${s.level ? LV_W[s.level] : 3}"></i></span>
        <span class="lv">${s.level || '—'}</span><span class="tiny muted ev">${esc(ev(s))}</span></div>`).join('')}</div>
      <p class="muted small">不用专门测：做理解题、听写、跟读和写作时自动记下。做一次测评会更准。</p>`;
  }
  function suggestHTML(sg) {
    return sg ? `<div class="card sunk section suggest row between"><div class="small">${esc(sg.reason)}</div>
      <div class="row"><button class="btn small primary" id="sgYes" data-tap="notice-level">换到 ${esc(sg.to)}</button><button class="btn small ghost" id="sgNo">先不用</button></div></div>` : '';
  }
  function bindSuggest(h, after) {
    const y = document.getElementById('sgYes'), n = document.getElementById('sgNo');
    if (y) y.onclick = async () => { try { await api('/api/next/profile', { ...h.profile, level: h.suggest.to }); toast('已换到 ' + h.suggest.to + '，推荐会跟着变'); await refreshHome(); S.homeFresh = true; route(); } catch (e) { toast(e.message); } };
    if (n) n.onclick = () => { save('flow-next-suggest-skip', Date.now()); if (after) after(); else n.closest('.suggest').remove(); };
  }

  /* ---------- the microphone is open only while a recording runs ----------
     While it is open an iPhone sends every sound to the earpiece, quietly (the audio session turns to play-and-record),
     so each recorder takes it with micOpen() at the tap and lets go with micClose() the moment the recording ends: the
     examiner and the AI then speak through the loudspeaker again. The first time on a device a short sheet says why the
     microphone is asked for; a home-screen app on an iPhone asks again after every launch (an iOS rule, not ours). */
  const MIC_SEEN = 'flow-mic-explained', MIC_HOW = '打开方法见操作指南「常见问题」里的「录音、跟读用不了？」';
  function micSession(type) {  // tells iOS (16.4+) what the page does, so sound leaves the earpiece once recording ends
    try {
      if (typeof AUDIO !== 'undefined' && AUDIO && typeof AUDIO.session === 'function') AUDIO.session(type);  // 语流 11's helper (01-audio-offline.js), once it is in
      else if (navigator.audioSession && 'type' in navigator.audioSession) navigator.audioSession.type = type;
    } catch (e) { /* older iOS, other browsers: nothing to switch */ }
  }
  function micReady(go) {  // true: record now; false: the sheet is up, and its button calls go() (a fresh tap, which iPhones and WeChat need)
    let seen = true;
    try { seen = localStorage.getItem(MIC_SEEN) === '1'; } catch (e) { /* storage blocked: do not ask every time */ }
    if (seen) return true;
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">要用一下麦克风</h2>
      <p class="small">说出来的回答要录音。麦克风只在你点录音键以后、说话的这几秒打开，说完马上关；录音只在批改时发给 AI，服务器上不留。</p>
      <p class="small muted">接下来系统会问能不能用麦克风，请选「允许」。${APP_REC() ? '在语流 App 里只问这一次。' : '放在 iPhone 主屏上的语流，每次重新打开后第一次录音，系统都会再问一次，这是 iOS 的规定。'}</p>
      <div class="row"><button class="btn primary" id="micGo" type="button">好，开始录音</button><button class="btn ghost" type="button" data-close>先不用</button></div></div>`, card => {
      card.querySelector('#micGo').onclick = () => { try { localStorage.setItem(MIC_SEEN, '1'); } catch (e) { /* asked again next time */ } closeSheet(); go(); };
    });
    return false;
  }
  // In 语流's iOS app the app records (16 kHz mono; WAV, or AAC past 40 s so it stays under 1.4 MB): micOpen() gives a stand-in stream after iOS's
  // own question, and recorderFor() a stand-in MediaRecorder the three recorders use as before (ios/README.md).
  const APP_REC = () => !!(window.FlowApp && FlowApp.has && FlowApp.has('rec'));
  // where the microphone is turned on, by platform (docs/native-bridge.md, section 1)
  const APP_MIC = { ios: ' iPhone 的「设置 → 语流 → 麦克风」', android: '手机的「设置 → 应用 → 语流 → 权限 → 麦克风」',
    harmony: '手机的「设置 → 应用和元服务 → 语流 → 麦克风」',  // HarmonyOS 5 (语流 C4, checked on its 5.0.1 emulator)
    windows: ' Windows 的「设置 → 隐私和安全性 → 麦克风」', macos: ' Mac 的「系统设置 → 隐私与安全性 → 麦克风」' };
  const APP_MIC_ANY = '系统设置里找到语流，把麦克风';  // a platform not listed: no other system's path
  class AppRecorder {
    constructor(max) { this.max = max || 120; this.state = 'inactive'; this.mimeType = ''; this.ondataavailable = null; this.onstop = null; this.off = null; }
    start() {
      this.state = 'recording';
      FlowApp.rec.start({ max: this.max }).then(x => {
        if (x && x.ok) { this.mimeType = x.format === 'm4a' ? 'audio/mp4' : 'audio/wav'; return; }
        toast((x && x.message) || '录音没能开始'); this.done(null);
      }, () => this.done(null));
      this.off = FlowApp.on('rec', d => {  // max reached, or cut short (a call, the app left): what was said is kept
        if (d.state === 'cut') toast('录音被打断了，已经说的这段先用上');
        if (d.state === 'done' || d.state === 'cut') this.stop();
      });
    }
    stop() {
      if (this.state !== 'recording') return;
      this.state = 'stopping';
      FlowApp.rec.stop().then(x => this.done(x && x.ok ? x : null), () => this.done(null));
    }
    done(x) {
      if (this.off) { this.off(); this.off = null; }
      this.state = 'inactive';
      if (x) {
        this.mimeType = x.mime_type;
        const bin = atob(x.data), bytes = new Uint8Array(bin.length);
        for (let k = 0; k < bin.length; k++) bytes[k] = bin.charCodeAt(k);
        if (this.ondataavailable) this.ondataavailable({ data: new Blob([bytes], { type: x.mime_type }) });
      }
      if (this.onstop) this.onstop();
    }
  }
  function recorderFor(stream, opts, maxSecs) { return stream && stream.app ? new AppRecorder(maxSecs) : new MediaRecorder(stream, opts); }
  async function micOpen() {  // the stream; throws an Error whose message is for the learner
    if (APP_REC()) {  // asked inside the tap, as with getUserMedia
      if (!(await FlowApp.rec.ask())) throw new Error('没有拿到麦克风权限，到' + (APP_MIC[FlowApp.platform] || APP_MIC_ANY) + '打开');
      LONG.other();
      return { app: true, getTracks: () => [] };
    }
    if (!navigator.mediaDevices || !window.MediaRecorder) throw new Error('这个浏览器不支持录音，换 Safari 或 Chrome 试试');
    micSession('play-and-record');
    try { return await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) { micSession('playback'); throw new Error('没有拿到麦克风权限，' + MIC_HOW); }
  }
  function micClose(stream) {
    if (stream) stream.getTracks().forEach(t => t.stop());
    if (!(stream && stream.app)) micSession('playback');  // in the app its own audio session is the app's (B3's review of #152, 8)
  }

  /* ---------- microphone: one spoken answer, sent to the AI as {mime_type, data} ---------- */
  const MIC = {
    mr: null, timer: 0,
    MAX: 1400000, FULL: 1340000,  // bytes a recording may be (base64 1.87 MB, under the server's 2.2 MB: app.py AUDIO_PATHS); a long one stops at FULL
    busy() { return !!(this.mr && this.mr.state === 'recording'); },
    stop() { if (this.busy()) this.mr.stop(); },
    async toggle(btn, maxSecs, onDone) {
      if (this.busy()) { this.mr.stop(); return; }
      if (!micReady(() => this.toggle(btn, maxSecs, onDone))) return;
      LONG.other(); TTS.stop(); NAR.stop(); CLIP.stop();  // a whole text being read waits, paused where it was
      let stream;
      try { stream = await micOpen(); } catch (e) { toast(e.message); return; }
      const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
      // A long answer (the ability test's 75 s, a retell's 2 minutes) at a speech bitrate: by default an iPhone records
      // AAC at about 185 kb/s (1.7 MB in 75 s) and Chrome Opus at 128 kb/s (1.9 MB in 2 minutes), over the 1.4 MB a
      // recording may be; at 48 kb/s two minutes are about 0.7 MB. If a browser keeps its own rate, the recording stops
      // by itself just under the limit and what was said is sent, never lost. Short ones (words, a sentence) keep the default.
      const long = maxSecs > 30, opts = Object.assign(type ? { mimeType: type } : {}, long ? { audioBitsPerSecond: 48000 } : {});
      // In 语流's iOS app the app records (WAV, AAC past 40 s: always under the limit; recorderFor), the rest as before.
      let mr; try { mr = recorderFor(stream, opts, maxSecs); } catch (e) { mr = new MediaRecorder(stream, type ? { mimeType: type } : undefined); }
      const chunks = []; let size = 0, full = false;
      this.mr = mr;
      mr.ondataavailable = e => {
        if (!e.data || !e.data.size) return;
        chunks.push(e.data); size += e.data.size;
        if (long && size > this.FULL && mr.state === 'recording') { full = true; mr.stop(); }
      };
      mr.onstop = () => {
        micClose(stream); clearTimeout(this.timer); btn.classList.remove('on'); btn.setAttribute('aria-pressed', 'false');
        if (full) toast('录音到了长度上限，已经停下，先交这一段');
        if (chunks.length) onDone(new Blob(chunks, { type: mr.mimeType || type || 'audio/webm' }));
      };
      if (long) mr.start(1000); else mr.start();
      btn.classList.add('on'); btn.setAttribute('aria-pressed', 'true');
      this.timer = setTimeout(() => this.stop(), maxSecs * 1000);
    },
    async payload(blob) {
      if (blob.size > this.MAX) throw new Error('录音太长了，请在 1 分钟内说完再交');
      const data = await new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1]); r.onerror = no; r.readAsDataURL(blob); });
      return { mime_type: /wav/.test(blob.type) ? 'audio/wav' : /mp4|m4a|aac/.test(blob.type) ? 'audio/mp4' : /ogg/.test(blob.type) ? 'audio/ogg' : 'audio/webm', data };
    },
  };
  // The record key is 语流's own mark: the rounded square with four sound waves (B9, 2026-11-26; the user: 我们这个语流
  // 的logo是很像一个录音键的……点的时候……波动动画，而不是这种默认的这种录音按钮). Small beside a field or a sentence (a soft patch
  // of the theme colour), large where speaking is the whole task (the mark itself); while it records (.on, set by
  // MIC.toggle) the four waves move and two rings stand round it (97-rec-key.css).
  const REC_MARK = '<svg class="rec-mark" viewBox="0 0 32 32" aria-hidden="true"><rect x="5.5" y="13" width="3" height="6" rx="1.5"/><rect x="11.5" y="8" width="3" height="16" rx="1.5"/><rect x="17.5" y="10.5" width="3" height="11" rx="1.5"/><rect x="23.5" y="14" width="3" height="4" rx="1.5"/></svg>';
  const recBtn = (id, label, big) => `<button class="icon-btn rec${big ? ' big' : ''}" id="${id}" type="button" aria-label="${label || '录音'}" aria-pressed="false">${REC_MARK}</button>`;
  const fixesHTML = fs => fs && fs.length ? `<div class="stack-s">${fs.map(f => `<div class="change"><span class="ft"><del>${esc(f.from)}</del> → <ins>${esc(f.to)}</ins></span><span class="why" data-ex>${esc(f.why)}</span></div>`).join('')}
    <div class="tiny muted">这些已经放进错题本，会按遗忘曲线回来让你再改一次。</div></div>` : '';

  /* ---------- 我的文章: paste any English text and study it with Flow's tools ---------- */
  async function importView() {
    if (!S.user) return needLogin('登录后可以导入自己想读的英文文章，用点词、AI 讲解、生词复习来学。');
    const d = await api('/api/next/import');
    if (!S.meta) S.meta = await api('/api/next/meta');
    view.innerHTML = `<h1 class="h1">我的文章</h1><span class="muted small">论文、新闻、小说章节都可以：贴进来，就能点词查义、AI 讲解句子、听写跟读、把生词加入复习。只有你自己看得到。</span>
      <form class="card flat section stack" id="impF"><input name="title" type="text" maxlength="80" placeholder="标题（可不填）" aria-label="标题">
        <textarea name="text" data-draft="import" rows="8" lang="en" aria-label="英文正文" placeholder="粘贴英文正文（200–8000 个字符）"></textarea>
        <select name="theme" aria-label="话题"><option value="">话题：按内容自动判断</option>${S.meta.themes.map(t => `<option value="${t.id}">话题：${esc(t.label)}</option>`).join('')}</select>
        <div class="row between"><span class="muted tiny" id="impN">0 字符</span><button class="btn primary">保存并开始学</button></div></form>
      <div class="section stack-s"><div class="row between"><h2 class="h2">已保存</h2><span class="muted tiny">${d.items.length} / ${d.max}</span></div>
      ${d.items.length ? `<div class="grid-list">${d.items.map(a => `<div class="card flat stack-s imp"><div class="row between"><b>${esc(a.title)}</b><span class="pill">${esc(a.level)}</span></div>
        <div class="muted small">${esc(a.preview)}…</div><div class="row"><a class="btn small primary" href="#/m/${encodeURIComponent(a.id)}/read">学这篇</a>
        ${a.enriched ? '<span class="pill green">已出题</span>' : `<button class="btn small" data-enrich="${esc(a.id)}">✦ AI 出题和挑表达</button>`}
        <button class="btn small ghost" data-del="${esc(a.id)}">删除</button></div></div>`).join('')}</div>` : '<div class="empty"><p>还没有导入的文章。</p></div>'}</div>`;
    const f = document.getElementById('impF');
    f.text.oninput = () => { document.getElementById('impN').textContent = f.text.value.length + ' 字符'; };
    f.onsubmit = async e => {
      e.preventDefault(); const b = f.querySelector('button'); b.disabled = true;
      try { const r = await api('/api/next/import', { title: f.title.value, text: f.text.value, theme: f.theme.value }); draftDone('import'); toast(r.existing ? '这篇已经导入过了' : `已保存，估计难度 ${r.level}`); location.hash = `#/m/${encodeURIComponent(r.id)}/read`; }
      catch (x) { toast(x.message); b.disabled = false; }
    };
    view.querySelectorAll('[data-enrich]').forEach(b => b.onclick = async () => {
      b.disabled = true; b.innerHTML = '<span class="spin"></span> 正在出题…';
      try { await api('/api/next/import/enrich', { id: b.dataset.enrich, request_id: rid('ie') }); delete MAT[b.dataset.enrich]; toast('已生成导读、理解题和表达'); importView(); }
      catch (x) { toast(x.message); b.disabled = false; b.textContent = '✦ AI 出题和挑表达'; }
    });
    view.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => { if (!confirm('删除这篇文章？')) return; try { await api('/api/next/import/delete', { id: b.dataset.del }); importView(); } catch (x) { toast(x.message); } });
  }

  /* ---------- 发音入门: minimal pairs, tell them apart, then say them ---------- */
  async function soundsView(setId) {
    if (!S.sounds) S.sounds = (await api('/api/next/sounds')).sets;
    const sets = S.sounds;
    if (!setId) {
      view.innerHTML = `<h1 class="h1">发音入门</h1><span class="muted small">中国学习者最容易混的 ${sets.length} 组音。先听辨，再跟读；读不准的会进错题本。</span>
        <div class="grid-list section">${sets.map(s => `<a class="card flat mini" href="#/sounds/${esc(s.id)}"><span class="t">${esc(s.title)}</span><span class="pill">${s.pairs.length} 对</span>
          <span class="p">${esc(s.pairs.slice(0, 3).map(p => p[0].word + ' / ' + p[1].word).join('　'))}</span></a>`).join('')}</div>`;
      return;
    }
    const s = sets.find(x => x.id === setId); if (!s) { location.hash = '#/sounds'; return; }
    view.innerHTML = `<a class="link small" href="#/sounds">← 全部</a><h1 class="h1">${esc(s.title)}</h1><div class="card sunk small stack-s"><span>${esc(s.tip)}</span>${s.listen ? `<span class="muted">${esc(s.listen)}</span>` : ''}</div>
      <div class="section row between"><h2 class="h2">先听，再跟读</h2><button class="btn small primary" id="quiz">听辨练习</button></div>
      <p class="muted tiny">${aiVoiceNote('读音由 AI 合成。', 'span', 'in')}点 ▶ 听，点录音键读这个词（再点一次停止）；${S.user ? 'AI 会告诉你目标音发得对不对。' : '登录后 AI 会告诉你目标音发得对不对。'}</p>
      <div class="stack-s pairs">${s.pairs.map((p, i) => `<div class="card flat pair">${p.map((w, j) => `<div class="pw"><span class="wd"><b>${esc(w.word)}</b>${w.phonetic ? `<span class="ph">${esc(w.phonetic)}</span>` : ''}</span>
        ${sayIcon(`data-play="${i}-${j}"`, '听 ' + w.word)}${recBtn(`r${i}-${j}`, '跟读 ' + w.word)}<span class="tiny res" id="o${i}-${j}"></span></div>`).join('')}</div>`).join('')}</div>`;
    const word = (i, j) => s.pairs[i][j];
    view.querySelectorAll('[data-play]').forEach(b => b.onclick = () => { const [i, j] = b.dataset.play.split('-').map(Number); CLIP.word({ text: word(i, j).word, audio: word(i, j).audio }); });
    s.pairs.forEach((p, i) => p.forEach((w, j) => {
      const btn = document.getElementById(`r${i}-${j}`), out = document.getElementById(`o${i}-${j}`);
      btn.onclick = () => MIC.toggle(btn, 4, async blob => {
        if (!S.user) { needLogin('登录后 AI 会听你的发音。'); return; }
        out.innerHTML = '<span class="spin"></span>';
        try {
          const x = (await api('/api/next/say', { text: w.word, audio: await MIC.payload(blob), request_id: rid('sy') })).result;
          out.innerHTML = aiTag() + ' ' + (x.ok ? `<span class="ok-mark">✓ 读对了</span>` : `<span class="bad-mark">听着像 ${esc(x.heard || '?')}</span>`)
            + (x.tentative ? '<div class="tiny muted">AI 的判断只作参考，不会进错题本</div>' : '');  // a reference verdict (FLOW_SAY_COUNTS off, or nothing heard): not filed as a mistake
          if (!x.ok) toast(x.confirmed ? '两次都没读准，已放进错题本：' + (x.tip || x.note)
            : x.tentative ? `AI 听成了「${x.heard || '?'}」，可以再读一遍` : `AI 听成了「${x.heard || '?'}」，再读一遍确认一下`);  // a reference never asks to confirm
        } catch (e) { out.textContent = ''; toast(e.message); }
      });
    }));
    document.getElementById('quiz').onclick = () => soundQuiz(s);
  }
  function soundQuiz(s) {
    // Each pair in turn (shuffled), never the same pair twice in a row.
    const deck = []; while (deck.length < 10) { const sh = s.pairs.slice().sort(() => Math.random() - 0.5); if (deck.length && sh[0] === deck[deck.length - 1]) sh.push(sh.shift()); deck.push(...sh); }
    const rounds = deck.slice(0, 10).map(p => ({ p, k: Math.random() < 0.5 ? 0 : 1 }));
    let i = 0, right = 0; const missed = [];
    const play = () => { const r = rounds[i]; CLIP.word({ text: r.p[r.k].word, audio: r.p[r.k].audio }); };
    function show() {
      if (i >= rounds.length) {
        if (S.user) api('/api/next/skill', { kind: 'discriminate', score: right / rounds.length }).catch(() => {});
        view.innerHTML = `<div class="card done-card enter">${doneRing}<h2 class="h2">听对了 ${right} / ${rounds.length}</h2><p class="muted small">${right >= 8 ? '耳朵已经分得清了，去跟读几遍吧。' : '再多听几遍对比。' + esc(s.listen || '')}</p>
          ${missed.length ? `<div class="small">听错的：${missed.map(x => `<b>${esc(x)}</b>`).join('、')}</div>` : ''}
          <div class="row center"><a class="btn" href="#/sounds/${esc(s.id)}">回到这组</a><button class="btn primary" id="again">再练一轮</button></div></div>`;
        document.getElementById('again').onclick = () => soundQuiz(s); return;
      }
      const r = rounds[i];
      view.innerHTML = `<div class="rtop"><a class="link small" href="#/sounds/${esc(s.id)}">结束</a><div class="bar-progress"><i id="rp"></i></div></div>${aiVoiceNote('读音由 AI 合成', 'p', 'tc rvoice')}<div class="review enter"><p class="muted small">听到的是哪一个？${TOUCH ? '' : '（← → 选，空格再听）'}</p>
        <div><button class="icon-btn big" id="pl" type="button" aria-label="再听一次（AI 朗读）">${ICON.speak}</button></div>
        <div class="choice two">${r.p.map((w, k) => `<button data-k="${k}">${esc(w.word)}</button>`).join('')}</div><p class="muted tiny tc">${i + 1} / ${rounds.length}</p></div>`;
      document.getElementById('rp').style.width = (i / rounds.length * 100) + '%';
      document.getElementById('pl').onclick = play; play();
      document.onkeydown = e => { if (e.key === ' ') { e.preventDefault(); play(); } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); const b = view.querySelector(`[data-k="${e.key === 'ArrowLeft' ? 0 : 1}"]`); if (b && !b.disabled) b.click(); } };
      view.querySelectorAll('[data-k]').forEach(b => b.onclick = () => {
        const ok = Number(b.dataset.k) === r.k; if (ok) right++; else missed.push(r.p[r.k].word);
        b.classList.add(ok ? 'good' : 'again'); if (!ok) view.querySelector(`[data-k="${r.k}"]`).classList.add('good');
        view.querySelectorAll('[data-k]').forEach(x => x.disabled = true);
        setTimeout(() => { i++; show(); }, ok ? 500 : 1100);
      });
    }
    show();
  }

  /* ---------- weekly report, with a picture to share ---------- */
  async function reportView() {
    if (!S.user) return needLogin('登录后可以看周报。');
    const r = await api('/api/next/report');
    const arrow = s => s.now == null ? '—' : `${Math.round(s.now * 100)}%${s.before != null ? (s.now > s.before + 0.02 ? ' ↑' : s.now < s.before - 0.02 ? ' ↓' : '') : ''}`;
    // 周报 in blocks (B9, 2026-11-26; the user on the mock-ups: 完全做，按照现在的效果图): the six figures as one sentence with
    // seven dots (as many filled as days studied), then a block a subject with its title inside, the things to open as
    // rows, and the one full-width button. The theme colour: the days, the bars, what went up, the small texts to tap.
    const days = Math.max(0, Math.min(7, r.days || 0));
    view.innerHTML = `<div class="stack rep-page"><div><h1 class="h1">周报</h1><span class="muted small">${esc(r.from)} – ${esc(r.to)} · 最近 7 天</span></div>
      <section class="card flat rep-hero"><p class="tiny muted">这 7 天</p><h2>学了 ${r.days} 天，约 ${r.minutes} 分钟</h2>
        <p class="small muted">学完 ${r.materials} 篇 · 新学 ${r.learned} 个词 · 输出练习 ${r.outputs} 次 · ${r.mastered} 个词进入长期记忆</p>
        <div class="rep-days" aria-hidden="true">${[0, 1, 2, 3, 4, 5, 6].map(k => `<i${k < days ? ' class="on"' : ''}></i>`).join('')}</div></section>
      ${weekPairHTML(r.progress)}
      <section class="card flat rep-blk"><h2>各项练习的平均分</h2><div class="ab-list rep-skills">${r.skills.filter(s => s.count || s.before != null).map(s => `<div class="ab"><span class="nm">${esc(s.label)}</span>
        <span class="vbar"><i data-w="${Math.max(3, (s.now || 0) * 100)}"></i></span><span class="lv">${arrow(s)}</span><span class="tiny muted ev">${s.count} 次</span></div>`).join('') || '<p class="muted small">这 7 天还没有练习记录。</p>'}</div></section>
      ${weekMoreHTML(r)}
      ${r.focus || r.watch.length ? `<section class="card flat rep-blk"><h2>接下来的重点</h2>${r.focus ? `<p class="rep-p">${esc(r.focus)}</p>` : ''}
        ${r.watch.length ? `<p class="small muted rep-watch">写作里要留意：${r.watch.map(n => nodeChip({ id: n.id, title: n.title, status: 'watch' })).join(' ')}</p>` : ''}</section>` : ''}
      <button class="btn primary block rep-go" id="share" data-tap="share-week">分享这 7 天的学习</button></div>`;
    requestAnimationFrame(() => requestAnimationFrame(() => view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
    document.getElementById('share').onclick = () => shareSheet([{ label: '这 7 天', draw: () => shareImage(r) }], '分享这 7 天的学习');
    const w = r.progress && r.progress.waiting, tryBtn = document.getElementById('wpTry');
    if (w && tryBtn) tryBtn.onclick = () => { S.tryNode = { pack: w.pack, title: w.title, fixed: wpPut(w.sentence, w.from, w.to) }; };
  }
  /* ---------- 这周的一次进步 (r29 第 3 项, the user's pick 2026-11-26) ----------
     One grammar point: the sentence the AI corrected before and one the learner wrote right since (dates, which
     practice, with or without a hint); with none yet, the last correction and 现在用它写一句 (仿写 on that text, the point
     named on the page: tryHintHTML); then 还要接着练, only points that keep coming back, only when the records may pick. */
  function wpPut(s, from, to) {  // s with its first `from` (any case) put right
    const i = from ? s.toLowerCase().indexOf(from.toLowerCase()) : -1;
    return i < 0 ? s : s.slice(0, i) + to + s.slice(i + from.length);
  }
  function wpFixed(b) {  // the sentence as written, the part changed struck out and the correction after it (words both share stay plain)
    const s = b.sentence || '', f = b.from || '', i = f ? s.toLowerCase().indexOf(f.toLowerCase()) : -1;
    if (i < 0) return `${esc(s)}<br>${f ? `<s>${esc(f)}</s> → ` : '→ '}<ins>${esc(b.to)}</ins>`;
    const fw = s.slice(i, i + f.length).split(' '), tw = (b.to || '').split(' ');
    let a = 0;
    while (a < fw.length - 1 && a < tw.length - 1 && fw[a].toLowerCase() === tw[a].toLowerCase()) a++;
    return `${esc(s.slice(0, i))}${esc(fw.slice(0, a).join(' '))}${a ? ' ' : ''}<s>${esc(fw.slice(a).join(' '))}</s> <ins>${esc(tw.slice(a).join(' '))}</ins>${esc(s.slice(i + f.length))}`;
  }
  function wpMark(s, part) {  // the corrected form where the learner used it
    const i = part ? s.toLowerCase().indexOf(part.toLowerCase()) : -1;
    return i < 0 ? esc(s) : `${esc(s.slice(0, i))}<b>${esc(s.slice(i, i + part.length))}</b>${esc(s.slice(i + part.length))}`;
  }
  function weekPairHTML(g) {
    if (!g) return '';
    const p = g.pair, w = g.waiting, rec = g.recurring;
    const help = { 1: '看了提示', 0: '没看提示，自己写的' }, how = { 1: '看了提示后', 0: '自己' };
    const line = xs => xs.filter(Boolean).map(esc).join(' · ');
    const top = p ? `<div class="card flat wp stack-s"><b class="wp-t">${esc(p.title)}</b>
        <span class="small muted">${line([p.before.date, p.before.label, 'AI 帮你改过'])}</span><p class="wp-s" lang="en">${wpFixed(p.before)}</p>
        <span class="small muted">${line([p.after.date, p.after.label, help[p.after.assisted]])}</span><p class="wp-s" lang="en">${wpMark(p.after.sentence, p.before.to)}</p>
        <p class="small wp-end">之前要 AI 改，这周${how[p.after.assisted] || ''}用对了一次。</p></div>`
      : w ? `<div class="card flat wp stack-s"><b class="wp-t">这周还看不出来</b>
        <p class="small">${esc(w.date)}的${esc(w.label)}里，「${esc(w.title)}」要 AI 帮你改。这周还没有再用到它，看不出有没有进步。</p>
        <span class="small muted">那时写的</span><p class="wp-s" lang="en">${wpFixed(w)}</p>
        <p class="small wp-end">下次写到「${esc(w.title)}」的时候，再试一次。</p>
        ${w.pack ? `<a class="btn block" id="wpTry" href="#/m/${encodeURIComponent(w.pack)}/output" data-tap="week-try">现在用它写一句 →</a>` : ''}</div>`
      : `<div class="card flat wp stack-s"><b class="wp-t">这周还看不出来</b><p class="small">写作、翻译或仿写被 AI 改过以后，下次你自己写对了，这里会放一组前后对照。</p></div>`;
    const more = rec ? `<div class="card flat stack-s"><b>还要接着练</b>${rec.length ? rec.map(x => `<p class="small wp-rec">${esc(x.title)}：两周里在 ${x.outputs} 次不同的练习里出现过，明天的语法复习先练它。</p>`).join('')
      : '<p class="small wp-rec">这周没有反复出现的问题。</p>'}<span class="tiny muted">偶尔出一次的小错，当场提示过就算了，不放在这里。</span></div>` : '';
    return `<section class="section stack-s" aria-labelledby="wpH"><h2 class="h2" id="wpH">这周的一次进步</h2>${top}${more}</section>`;
  }
  function tryHintHTML(pid) {  // 仿写 opened from 现在用它写一句: the point to try, and the sentence as the AI put it right then
    const t = S.tryNode;
    return t && t.pack === pid ? `<div class="small try-node">这次试着用上「${esc(t.title)}」。那时 AI 帮你改成：<span lang="en">${esc(t.fixed)}</span></div>` : '';
  }
  function weekMoreHTML(r) {
    const e = r.easy || {}, sp = r.speaking || {}, ra = r.radar || { moves: [] };
    const speed = e.wpm ? `，平均每分钟 ${e.wpm} 词${e.wpm_before ? (e.wpm > e.wpm_before ? `（前 7 天 ${e.wpm_before}，快了）` : `（前 7 天 ${e.wpm_before}）`) : ''}` : '';
    const mv = m => m.before == null ? '' : m.now > m.before ? `<span class="up">↑${m.now - m.before}</span>` : m.now < m.before ? `<span class="down">↓${m.before - m.now}</span>` : '';
    const rl = r.relisten || {};
    // 能力 as six small figures (the radar itself is one tap away), then what the week had to open: a row each, the whole row a link
    return `${rl.count ? `<section class="card flat rep-blk"><h2>复听</h2><p class="rep-p">把几天前学过的文章重听了 ${rl.count} 次，平均听懂${esc(rl.label)}。</p></section>` : ''}
      <section class="card flat rep-blk"><div class="row between"><h2>能力</h2><a class="rep-more" href="#/radar">看雷达 ›</a></div>
        ${ra.moves.length ? `<div class="rep-ab">${ra.moves.map(m => `<div><span class="tiny muted">${esc(m.label)}</span><b>${m.now}</b>${mv(m)}</div>`).join('')}</div>
          <span class="tiny muted">100 分 = 达到你定的目标${ra.goals_chosen ? '' : '（还没定目标，先按默认目标算）'}。这 7 天做了 ${ra.tests_week} 次测评。</span>`
          : '<p class="rep-p">还没有雷达数据。做几次小测评，就能看到六项能力离目标还差多少。</p><div><a class="btn small" href="#/radar/test">去测一测</a></div>'}</section>
      <section class="card flat rep-rows">
        <a class="rep-row" href="#/easy">${fiTile('read')}<span class="t"><b>轻松读</b><span class="small muted">${e.texts ? `读了 ${e.texts} 篇，一共 ${e.words} 个词${speed}。` : '这 7 天还没读。每天读一篇比你低一级的短文，阅读速度会慢慢提上来。'}</span></span><span class="go" aria-hidden="true">›</span></a>
        <a class="rep-row" href="#/speak">${fiTile('chat')}<span class="t"><b>口语情景</b><span class="small muted">${sp.scenes_week ? `这 7 天练了 ${sp.scenes_week} 个情景，` : '这 7 天还没练情景对话，'}一共完成 ${sp.scenes_done || 0} / ${sp.scenes_total || 12} 个。</span></span><span class="go" aria-hidden="true">›</span></a>
        <a class="rep-row" href="#/cards/mistake">${fiTile('bookx')}<span class="t"><b>错题</b><span class="small muted">新进错题本 ${r.mistakes_new} 个，改对 ${r.mistakes_fixed} 个。</span></span><span class="go" aria-hidden="true">›</span></a></section>`;
  }
  function shareImage(r) {
    const rows = r.skills.filter(s => s.now != null).slice(0, 5).length;
    const W = 1080, H = (rows ? 900 + rows * 70 + 170 : 860) + 230, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    const g = cv.getContext('2d'), green = '#1f9d55', ink = '#1b1d1a', muted = '#6f7369';
    g.fillStyle = '#fbfaf6'; g.fillRect(0, 0, W, H);
    const font = (s, w) => `${w || 600} ${s}px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`;
    g.fillStyle = ink; g.font = font(56, 800); g.fillText('这 7 天的学习', 80, 170);  // the brand is in the footer, with the QR code
    g.fillStyle = muted; g.font = font(30, 400); g.fillText(`${r.from} – ${r.to}`, 80, 250);
    const stats = [[r.days, '学习天数'], [r.minutes, '分钟'], [r.materials, '篇材料'], [r.learned, '个新词'], [r.mastered, '个词记牢了'], [r.outputs, '次输出练习']];
    stats.forEach(([v, l], k) => {
      const x = 80 + (k % 3) * 320, y = 320 + Math.floor(k / 3) * 220;
      g.fillStyle = '#ffffff'; g.fillRect(x, y, 290, 190); g.fillStyle = green; g.font = font(84, 800); g.fillText(String(v), x + 30, y + 110);
      g.fillStyle = muted; g.font = font(30, 500); g.fillText(l, x + 30, y + 160);
    });
    let y = 820; g.fillStyle = ink; g.font = font(36, 700); if (rows) g.fillText('各项练习', 80, y); y += 30;
    r.skills.filter(s => s.now != null).slice(0, 5).forEach(s => {
      y += 70; g.fillStyle = ink; g.font = font(32, 500); g.fillText(s.label, 80, y);
      g.fillStyle = '#e7e3d8'; g.fillRect(240, y - 24, 600, 22); g.fillStyle = green; g.fillRect(240, y - 24, 600 * s.now, 22);
      g.fillStyle = muted; g.fillText(Math.round(s.now * 100) + '%', 870, y);
    });
    brandFoot(g, W, H, habitNote(false, true));  // logo, the weeks that reached the goal, and the QR code back to the site (86-share.js)
    return cv.toDataURL('image/png');
  }

  /* ---------- library ---------- */
  // The pill on a row says only what the page above does not (B9's audit P2-E7): 一读 always; under the 精选 filter
  // nothing more, since every row is one; under 全部材料 a light 精选 (not the black one, the strongest thing on the page)
  // or 简版. The 「AI 生成」 tag stays on every row (B7).
  function libTag(m, f) {
    if (m.daily) return ['一读', 'amber'];
    if (f.featured === '1') return false;
    return m.featured ? ['精选', ''] : null;
  }
  async function libraryView(f) {
    let saved = null; try { saved = JSON.parse(sessionStorage.getItem('flow-next-lib') || 'null'); } catch (e) { /* private mode */ }
    f = f || saved || { level: hasProfile() ? level() : '', theme: '', page: 1, featured: '1' };
    try { sessionStorage.setItem('flow-next-lib', JSON.stringify(f)); } catch (e) { /* private mode */ }
    const d = await api(libraryPath(f));  // the same address a touch of the link already preloaded
    const pages = Math.max(1, Math.ceil(d.total / d.per));
    // The page in the order a learner picks (B9, 2026-11-26; the user on the mock-ups: 完全做，按照现在的效果图, and on the
    // filter row: 留空太多 / 这里按照舒服的方式改): two ways out on top (轻松读, 我的文章), the serial stories as cards
    // to swipe sideways, then 单篇: its count and the two small filters on one line, the level as a switch under it.
    const LV = ['', 'A2', 'B1', 'B2', 'C1'];
    view.innerHTML = `<h1 class="h1">全部材料</h1>
      <div class="lib-two"><a class="lib-way" href="#/easy">${fi('read')}<b>轻松读</b><span class="tiny muted">低一级</span></a><a class="lib-way" href="#/import">${fi('docpen')}<b>我的文章</b><span class="tiny muted">导入</span></a></div>
      ${d.series && d.series.length ? `<section class="lib-sec"><h2 class="lib-cap">连载故事</h2><div class="lib-sers">${d.series.map(s => `<a class="lib-ser" href="#/series/${encodeURIComponent(s.id)}">
        <b>${uiLang() === 'en' && !s.title_en ? esc(s.title) : `《${esc(s.title)}》`}</b><span class="en" lang="en">${esc(s.title_en)}</span><span class="tiny muted">${esc(s.level)} · 共 ${s.of} 集 ${aiTag()}</span>
        <span class="lib-bar" aria-hidden="true"><i data-w="${Math.round((s.done || 0) / s.of * 100)}"></i></span>
        <span class="tiny muted">${s.done ? (s.next ? `读到第 ${s.done} 集 · 继续第 ${s.next_part} 集` : '读完了') : '从第 1 集开始'}</span></a>`).join('')}</div></section>` : ''}
      <section class="lib-sec"><div class="lib-caprow"><h2 class="lib-cap">单篇 · ${d.total} 篇</h2><span class="lib-filt">
          <select id="ft" aria-label="话题"><option value="">全部话题</option>${Object.entries(d.themes).map(([k, v]) => `<option value="${k}" ${f.theme === k ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select>
          <select id="ff" aria-label="范围"><option value="1" ${f.featured === '1' ? 'selected' : ''}>精选</option><option value="" ${f.featured !== '1' ? 'selected' : ''}>全部材料</option></select></span></div>
        <div class="seg lib-lv" id="fl" role="radiogroup" aria-label="难度">${LV.map(l => `<button type="button" role="radio" aria-checked="${(f.level || '') === l}" data-l="${l}">${l || '全部'}</button>`).join('')}</div>
        <div class="mlist" id="lib">${d.items.map(m => mrow(m, libTag(m, f))).join('') || '<div class="empty">这个筛选下还没有材料。</div>'}</div></section>
      ${pages > 1 ? `<div class="pager lib-pager"><button class="icon-btn" id="pv" type="button" aria-label="上一页" ${f.page <= 1 ? 'disabled' : ''}><svg viewBox="0 0 12 12" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7.5 2.5 4 6l3.5 3.5"/></svg></button><span class="muted small">${f.page} / ${pages}</span><button class="icon-btn" id="nx" type="button" aria-label="下一页" ${f.page >= pages ? 'disabled' : ''}><svg viewBox="0 0 12 12" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 2.5 8 6 4.5 9.5"/></svg></button></div>` : ''}`;
    view.querySelectorAll('.lib-bar i').forEach(i => { i.style.width = i.dataset.w + '%'; });
    const again = nf => libraryView(nf).then(() => enter(document.getElementById('lib')));
    document.getElementById('ff').onchange = e => again({ ...f, featured: e.target.value, page: 1 });
    document.getElementById('fl').querySelectorAll('button').forEach(b => b.onclick = () => { if (b.dataset.l !== (f.level || '')) again({ ...f, level: b.dataset.l, page: 1 }); });
    document.getElementById('ft').onchange = e => again({ ...f, theme: e.target.value, page: 1 });
    const pv = document.getElementById('pv'), nx = document.getElementById('nx');
    if (pv) pv.onclick = () => { scrollTo(0, 0); again({ ...f, page: f.page - 1 }); };
    if (nx) nx.onclick = () => { scrollTo(0, 0); again({ ...f, page: f.page + 1 }); };
  }

  /* ---------- a serial story: its episodes in order, and where to carry on ---------- */
  async function seriesView(sid) {
    const s = await api('/api/next/series?id=' + encodeURIComponent(sid));
    const next = s.episodes.find(e => e.id === s.next);
    view.innerHTML = `<div><a class="link small" href="#/library">← 全部材料</a></div>
      <div><span class="kicker">连载故事 · ${esc(s.level)} · 共 ${s.of} 集</span><h1 class="h1">${esc(s.title)}</h1><div class="title-en">${esc(s.title_en)}</div>
        <p class="muted small" data-zh>${esc(s.blurb)}</p>${aiCheckLink(aiMark('经规范检查'))}</div>
      ${next ? `<a class="btn primary block" href="#/m/${encodeURIComponent(next.id)}">${s.done ? `继续：第 ${next.part} 集` : '从第 1 集开始'}<span aria-hidden="true">→</span></a>` : '<p class="small">六集都读完了。可以回到任意一集，再听一遍或者重写输出任务。</p>'}
      <div class="serial section">${s.episodes.map(e => `<a class="ep${e.read ? ' done' : ''}${e.id === s.next ? ' next' : ''}" href="#/m/${encodeURIComponent(e.id)}">
        <span class="n" aria-hidden="true">${e.read ? '✓' : e.part}</span><span class="t"><b>${esc(e.title.replace(/^.*?[：:]/, ''))}</b><span class="tiny muted">${esc(e.preview.replace(/^连载第\s*\d+\s*集(（完）)?[：:]\s*/, ''))}</span></span>
        <span class="tiny muted">${e.minutes} 分钟</span></a>`).join('')}</div>
      <p class="tiny muted section">每集约 300 词，C1 难度，原创连载。每集都有听、读、理解和输出四步，读完理解题就算读过这一集。</p>`;
  }
  /* ---------- 我的 → 使用习惯 (the user, 2026-11-26: 「这些用户习惯的设置都可以放在一起……只有两个的话……点一下右边，
     点一下左边……字体标准大号、特大号……做成那种滑动线条，放在最底部」 and 「能做成一个页面就不要做成两个界面」; B9's
     spec, today-regroup/final): one screen with no sheets: the two-choice settings as switches in two columns (点哪边就是
     哪个), then 字号和行距 together at the bottom (行距's switch by the title, the size a slider, a sample that follows both). Each takes effect at once and is kept with
     the account (07-prefs.js; 主题色 07-accent.js; 今日的样子 is 今日's own switch). ---------- */
  // 我的's row: the gist of what is chosen (今日的样子, 主题色, 字号)
  function habitsLabel() {
    const tv = typeof todayView === 'function' && S.user && S.home && S.home.profile ? (todayView() === 'cards' ? '今日卡片' : '今日列表') : '';
    const sz = (TEXT_SIZES.find(x => x[0] === TEXT.size) || TEXT_SIZES[0])[1];
    return [tv, accentLabel(), '字号' + sz].filter(Boolean).join(' · ');
  }
  function habitsView() {
    const two = (a, b) => [a, b];
    const blocks = [];
    // 今日的样子: the same setting as the switch on 今日 (B1), for a learner with a plan
    if (typeof todayView === 'function' && typeof setTodayView === 'function' && S.user && S.home && S.home.profile)
      blocks.push(['today', '今日的样子', two(['list', '列表'], ['cards', '卡片']), todayView()]);
    blocks.push(['accent', '主题色', ACCENTS, accentNow()]);
    blocks.push(['card_new', '新词卡', two(['simple', '简洁'], ['detailed', '详细']), KNOW.view('new')]);
    blocks.push(['card_review', '复习卡', two(['simple', '简洁'], ['detailed', '详细']), KNOW.view('review')]);
    blocks.push(['know', '背单词「认识」在', two(['left', '左边'], ['right', '右边']), KNOW.side()]);
    blocks.push(['tap', '点卡片作答', two(['on', '开'], ['off', '关']), KNOW.tap() ? 'on' : 'off']);  // until chosen: this device's own (a finger on, a mouse off)
    const at = Math.max(0, TEXT_SIZES.findIndex(x => x[0] === TEXT.size));
    // 界面语言 on the title row's right (语流 E1, 07-lang.js): 中文 | English
    view.innerHTML = `<div class="hb-top"><h1 class="h1 hb-h"><a class="hb-back" href="#/me" aria-label="返回我的">‹</a>使用习惯</h1>${typeof langSwitchHTML === 'function' ? langSwitchHTML() : ''}</div>
      <div class="hb-grid">${blocks.map(([key, name, opts, cur]) => `<div class="hb-card"><span class="hb-name" id="hb-${key}">${esc(name)}</span>
        <div class="hb-seg" role="radiogroup" aria-labelledby="hb-${key}">${opts.map(([v, l]) => `<button type="button" role="radio" data-hb="${key}" data-v="${v}" aria-checked="${v === cur}">${key === 'accent' ? `<i class="hb-dot" data-c="${v}" aria-hidden="true"></i>` : ''}${esc(l)}</button>`).join('')}</div></div>`).join('')}</div>
      <div class="hb-card hb-size"><div class="hb-row"><span class="hb-name"><span id="hbSizeN">字号</span> · <b id="hbSizeV">${TEXT_SIZES[at][1]}</b></span>
          <span class="hb-lh"><span class="hb-name" id="hb-lh">行距</span><span class="hb-seg" role="radiogroup" aria-labelledby="hb-lh">${TEXT_LH.map(([v, l]) => `<button type="button" role="radio" data-hb="lh" data-v="${v}" aria-checked="${v === TEXT.lh}">${esc(l)}</button>`).join('')}</span></span></div>
        <div class="hb-slide"><span class="hb-a" aria-hidden="true">A</span>
          <div class="hb-track"><i aria-hidden="true"></i><i aria-hidden="true"></i><i aria-hidden="true"></i><input class="hb-range" id="hbSize" type="range" min="0" max="2" step="1" value="${at}" aria-labelledby="hbSizeN" aria-valuetext="${TEXT_SIZES[at][1]}"></div>
          <span class="hb-a big" aria-hidden="true">A</span></div>
        <div class="hb-ticks" aria-hidden="true">${TEXT_SIZES.map(([, l]) => `<span>${l}</span>`).join('')}</div>
        <p class="text hb-sample" lang="en">The first time you switch on a pair of noise-cancelling headphones, the world goes quiet.</p></div>`;
    if (typeof langSwitchWire === 'function') langSwitchWire(view);
    view.querySelectorAll('[data-hb]').forEach(b => b.onclick = async () => {
      if (b.getAttribute('aria-checked') === 'true') return;
      const key = b.dataset.hb, v = b.dataset.v, seg = b.parentNode;
      seg.querySelectorAll('[role=radio]').forEach(x => x.setAttribute('aria-checked', String(x === b)));
      if (key === 'today') setTodayView(v);
      else if (key === 'accent') { await setAccent(v); seg.querySelectorAll('[role=radio]').forEach(x => x.setAttribute('aria-checked', String(x.dataset.v === accentNow()))); }  // back, if it could not be saved
      else if (key === 'card_new' || key === 'card_review') KNOW.setView(key === 'card_new' ? 'new' : 'review', v);
      else if (key === 'know') { KNOW.set(v); TIPS.mark('know-side'); }  // chosen here: 「『认识』换到右边了」 is not needed (08-tips.js)
      else if (key === 'tap') KNOW.setTap(v === 'on');
      else if (key === 'lh') { TEXT.lh = v; save('flow-next-text', TEXT); applyText(); prefSave('lh', v); }
    });
    // 字号: three stops; the sample follows while it moves, the choice is kept when let go
    const r = document.getElementById('hbSize');
    const shown = () => { const s = TEXT_SIZES[Number(r.value)]; r.setAttribute('aria-valuetext', s[1]); document.getElementById('hbSizeV').textContent = s[1]; r.parentNode.dataset.at = r.value; };
    r.oninput = () => { TEXT.size = TEXT_SIZES[Number(r.value)][0]; applyText(); shown(); };
    r.onchange = () => { save('flow-next-text', TEXT); prefSave('size', TEXT.size); };
    shown();
  }
  /* ---------- me: one grouped list, like a phone's settings; each row opens a page or a sheet ---------- */
  // A row: a link (to starts with # or /) or a button (to is its id); the value sits on the right, greyed.
  // icon (00-icons.js): the soft square in front, as 设置's rows have it
  function grow(to, label, value, vid, tapKey, icon) {
    const tag = /^(#|\/|https?:)/.test(to) ? 'a' : 'button';
    return `<${tag} class="grow${icon ? ' gi' : ''}" ${tag === 'a' ? `href="${to}"` : `type="button" id="${to}"`}${tapKey ? ` data-tap="${tapKey}"` : ''}>${icon ? fiTile(icon) : ''}<span class="t">${label}</span><span class="v small muted"${vid ? ` id="${vid}"` : ''}>${value || ''}</span><span class="go" aria-hidden="true">›</span></${tag}>`;
  }
  // 全英文界面: rows about agreeing and privacy stay in Chinese in English mode too (data-zh, docs/english-ui.md)
  const zhRow = html => html.replace('class="grow"', 'class="grow" data-zh');
  // 帮助 → 更多: the two rows that are not looked at every week (简洁化, the user's pick 2026-11-25)
  function moreSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">更多</h2><div class="glist">${grow('/about', '认识语流', '一页看完语流能帮你做什么', '', 'me-about')}${grow('/survey', '匿名问卷', '你想要什么样的英语学习网站', '', 'me-survey')}
      ${S.user ? grow('meTour', '再看一遍新手引导', '底下五个地方各是做什么的', '', 'me-tour') : ''}${grow('meTips', '重新显示使用提示', '比如「点词查词」，用到时再说一次', '', 'me-tips')}</div>
      <button class="btn ghost" data-close type="button">关闭</button></div>`, card => {
      const t = card.querySelector('#meTour'); if (t) t.onclick = () => { closeSheet(); tourAgain(); };  // 08-tour.js
      card.querySelector('#meTips').onclick = async () => {  // 08-tips.js
        try { await TIPS.reset(); closeSheet(); toast('使用提示会在用到时再出现一次'); } catch (e) { toast(e.message); }
      };
    });
  }
  // 我的 → 内测版: this 内测 version's number and when it went up, and what changed in it (the ledger's beta entry)
  function betaInfo() {
    fetch('/api/deploy-status', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(d => {
      const el = document.getElementById('meBetaVer'), t = d && d.started ? new Date(d.started) : null;
      if (el && d && d.tag) el.textContent = ` 现在是 ${d.tag}${t && !isNaN(t) ? `（${t.getMonth() + 1} 月 ${t.getDate()} 日 ${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')} 更新）` : ''}。`;
    }).catch(() => {});
    fetch('/api/next/updates', { credentials: 'same-origin' }).then(r => (r.ok ? r.json() : null)).then(x => {
      // the ledger's beta entry (语流 A3, updates_service): {changed, new, better, fixed}, each a list of {text, link?} —
      // 「用法变了」 (changed) first and marked; a link is always inside the site (#/…)
      const b = x && x.beta, el = document.getElementById('meBetaNew'); if (!el || !b) return;
      const item = (v, changed) => { const t = typeof v === 'string' ? v : (v && v.text) || '', link = v && typeof v === 'object' && /^#\//.test(v.link || '') ? v.link : '';
        return t ? `<li${changed ? ' class="beta-changed"' : ''}>${changed ? '<b>用法变了：</b>' : ''}${esc(t)}${link ? ` <a class="link" href="${esc(link)}">去看看</a>` : ''}</li>` : ''; };
      const lines = [...(b.changed || []).map(v => item(v, true)), ...[...(b.new || []), ...(b.better || []), ...(b.fixed || [])].map(v => item(v, false))].filter(Boolean).slice(0, 5);
      if (!lines.length) return;
      el.innerHTML = `<div class="small"><b>这一版内测改了什么</b></div><ul class="small">${lines.join('')}</ul>`; el.hidden = false;
    }).catch(() => {});
  }
  // 语流's own app with a settings page of its own (iOS 专属功能: 锁屏听读、小组件、Siri…, ios-27-features.md; 语流 C1,
  // 2026-11-25): one row in 设置 opens it (FlowApp.call('app.settings')). Shown only where the app says it has one.
  const APP_SETTINGS = { ios: ['iOS 专属功能', '锁屏、小组件、Siri 等'], android: ['安卓专属功能', ''], windows: ['Windows 专属功能', ''], macos: ['Mac 专属功能', ''] };
  const appSettings = () => { try { return window.FlowApp && FlowApp.has && FlowApp.has('settings') ? APP_SETTINGS[FlowApp.platform] || ['App 专属功能', ''] : null; } catch (e) { return null; } };
  // 「AI 用量」 (2026-11-26, the owner in A0: a learner sees their own AI use of the day): ai_quota.today (语流 B7 #405),
  // read fresh each time (not the data layer's copy: an AI answer a moment ago changed it).
  const aiRowLabel = a => a.stopped === 'paused' ? '暂停中' : a.stopped === 'day_full' || a.stopped === 'site' ? '今天已满'
    : a.limit == null ? '不限次数' : a.remaining > 0 ? `还能用 ${a.remaining} 次` : '今天已用完';
  function fillAiRow() {
    const put = t => { const v = document.getElementById('meAiV'); if (v) v.textContent = t; };
    request('/api/account/ai', undefined, true).then(r => put(aiRowLabel(r.j))).catch(() => put(''));
  }
  async function aiUsageSheet() {
    let a;
    try { a = (await request('/api/account/ai')).j; } catch (e) { toast(e.message); return; }
    const until = a.paused_until ? new Date(a.paused_until * 1000) : null;
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">AI 用量</h2>
      <div class="aiq-num"><b>${a.used}</b><span class="muted">${a.limit != null ? ` / ${a.limit} 次` : ' 次'}</span><span class="small muted">今天</span></div>
      ${a.limit ? `<progress class="aiq-bar${a.level !== 'ok' ? ' low' : ''}" max="${a.limit}" value="${Math.min(a.used, a.limit)}" aria-label="今天用了 ${a.used} 次，共 ${a.limit} 次"></progress>` : ''}
      <p class="small">${esc(a.note)}${until ? `预计 ${until.getMonth() + 1} 月 ${until.getDate()} 日恢复。` : ''}${a.stopped === 'paused' ? ' <a class="link" href="#/feedback" data-close>去问题反馈</a>' : ''}</p>
      ${a.by_kind && a.by_kind.length ? `<ul class="aiq-kinds">${a.by_kind.map(k => `<li><span>${esc(k.label)}</span><span class="muted">${k.count} 次</span></li>`).join('')}</ul>` : ''}
      <p class="tiny muted">用到 AI 的批改、讲解、出题和对话，每次算一次；大家共用的讲解和例句、没有成功的那次不算。AI 朗读另有字数上限，不算在这里。${a.adjusted ? '你的额度由管理员调整过。' : ''}</p>
      <button class="btn ghost" data-close type="button">完成</button></div>`);
    const v = document.getElementById('meAiV'); if (v) v.textContent = aiRowLabel(a);
  }
  // 我的 (B9's batch 1, the user 2026-11-26 15:3x; ui-refine/batch1/me-*.png and spec.md): a white card with who you are
  // and one line on this week; 进步 as three tiles; 设置 one white card, an icon in front of each row and its value on
  // the right; 账号和隐私 and 帮助 each a fold that opens in place (D2's fold rules: the name in ink, what is inside on the
  // right, never 「8 项」). #/me/account and #/me/help open their fold (the guide's and the mails' links); a fold
  // opened stays open on the way back from a page it led to.
  const ME_OPEN = {};
  const ME_FOLDS = { account: ['shield', '账号和隐私', '导出、注销、数据存放'], help: ['help', '帮助', '指南、隐私说明、反馈'] };
  function meFold(id, rows, foot) {
    const [icon, name, inside] = ME_FOLDS[id];
    return `<details class="me-fold" id="meFold-${id}" data-fold="${id}"${ME_OPEN[id] ? ' open' : ''}><summary class="fold-s"><span class="fold-r">${fi(icon)}<span class="fold-n">${name}</span><span class="fold-v">${inside}</span>
      <svg class="fold-a" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9.5 6 6 6-6"/></svg></span></summary>
      <div class="fold-b"><div class="glist">${rows.join('')}</div>${foot ? `<p class="tiny muted gfoot">${foot}</p>` : ''}</div></details>`;
  }
  const meTile = (href, icon, name, line, vid, tap) => `<a class="me-tile" href="${href}" data-tap="${tap}">${fiTile(icon)}<b>${name}</b><span class="me-tv"${vid ? ` id="${vid}"` : ''}>${line}</span></a>`;
  // 错题本's tile: how many there are (the list's own count, asked for after the page is drawn)
  function fillMistakeTile() {
    api('/api/next/cards?f=mistake&page=1').then(r => { const el = document.getElementById('meMistakeV'); if (el) el.textContent = r.total ? `${r.total} 道` : '还没有'; }).catch(() => {});
  }
  // 提醒和每周邮件 (B9: 「每天提醒」「每周进度邮件」 as one row): the two, each to its own sheet
  function remindMailSheet(minutes) {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">提醒和每周邮件</h2><div class="glist">${grow('rmDay', '每天提醒', '加到手机日历')}${grow('rmMail', '每周进度邮件', weeklyMailLabel(), '', 'me-weekly-mail')}</div>
      <button class="btn ghost" data-close type="button">关闭</button></div>`, card => {
      card.querySelector('#rmDay').onclick = () => remindSheet(minutes);
      card.querySelector('#rmMail').onclick = weeklyMailSheet;  // 11-progress.js
    });
  }
  async function meView(fold) {
    if (!S.meta) S.meta = await api('/api/next/meta');
    if (ME_FOLDS[fold]) ME_OPEN[fold] = true;  // #/me/account, #/me/help
    const p = (S.home && S.home.profile) || S.guest || {}, u = S.user, st = S.home && S.home.stats;
    const lv = S.meta.levels.find(l => l.id === p.level);
    // 学英语为了什么: every goal chosen, the main one first (2026-11-26; an older profile has goal only)
    const goalNames = ((p.goals && p.goals.length ? p.goals : p.goal ? [p.goal] : [])).map(id => (S.meta.goals.find(g => g.id === id) || {}).label).filter(Boolean);
    const installed = HOME_APP;  // the home-screen app, an install, or one of Flow's apps: nothing to add to the desktop
    const days = st ? (st.habit ? st.habit.done : st.week.filter(d => d.active).length) : 0;
    const app = appSettings();
    const settings = [grow('#/welcome/edit', '学习目标和水平', [goalNames.length && esc(goalNames.join('、')), p.target && '目标 ' + p.target, lv && (p.target ? '现在 ' : '') + lv.id].filter(Boolean).join(' · ') || '未设置', '', 'me-level', 'target'),
      u ? grow('meExam', '我的考试', examLabel(p), 'meExamV', 'me-exam', 'cap') : '', u ? grow('meHabit', '每周目标', `每周 ${(st && st.habit && st.habit.goal) || 4} 天`, 'meHabitV', 'me-habit', 'calok') : '',
      grow('meVoice', '朗读声音', VOICE_LABELS[S.voice] || VOICE_LABELS['us-f'], 'meVoiceV', 'me-voice', 'voice'), WORD_CLIPS ? grow('meSound', '单词读音方式', soundLabel(), 'meSoundV', 'me-sound', 'book') : '',
      grow('#/me/habits', '使用习惯', habitsLabel(), '', 'me-habits', 'sliders'),  // 今日的样子、主题色、卡片、「认识」、字号 (81-habits.js)
      u ? grow('meRemind', '提醒和每周邮件', weeklyMailLabel(), 'meMailV', 'me-remind', 'bell') : grow('meRemind', '每天提醒', '', '', 'me-remind', 'bell'),
      u && !u.teacher ? grow('meClass', '班级', '<span class="spin"></span>', 'meClassV', 'me-class', 'people') : '',
      u ? grow('meAi', 'AI 用量', '<span class="spin"></span>', 'meAiV', 'me-ai', 'gauge') : '',
      installed ? '' : grow('meInstall', '添加到桌面', '', '', 'me-install', 'layers'),
      app ? grow('meApp', app[0], app[1], '', 'me-app-settings', 'spark') : '',
      // 按我的学习记录推荐: the switch on its row and the grey line under it (the user's pick, 2026-11-26; 81-privacy.js)
      u && S.home && S.home.profile ? personalizeRow() + `<p class="tiny muted me-pfoot">${PERSONALIZE_FOOT}</p>` : ''];
    const groups = [
      // 内测版 (flow.jasa.hk) only: what the line under the top bar said, kept here (the line can be closed): the
      // version and what changed in it (/api/deploy-status, /api/next/updates), 去正式版 (not in Flow's apps: it would
      // open the system browser), feedback
      BETA && ['内测版', [grow('#/feedback', '问题反馈', '', '', 'me-beta-feedback'),
        IN_FLOW_APP ? '' : grow(MAIN_SITE + '/', '去正式版', 'flowlang.cn', '', 'me-beta-main'), '<div class="beta-new" id="meBetaNew" hidden></div>'],
        '这里是语流的内测版（flow.jasa.hk），新功能先在这里试。账号和数据都和正式版分开，内测期间可能会清空。<span id="meBetaVer"></span>'],
      // 安卓 App 1.0.4+ (81-privacy.js appPrivacy): 撤回同意 and the system permissions, for the app stores
      // and the two lists the stores ask for (隐私和数据, #342), a tap from 我的
      appPrivacy() && ['隐私', [zhRow(grow('#/guide/info-list', '个人信息收集清单', '', '', 'me-info-list')), zhRow(grow('#/guide/sharing-list', '第三方信息共享清单', '', '', 'me-sharing-list')),
        zhRow(grow('meWithdraw', '撤回同意', '', '', 'me-withdraw')), grow('mePerms', '系统权限', '麦克风、通知', '', 'me-permissions')],
        '<span data-zh>撤回同意以后，App 清掉这台手机上的登录和缓存，回到第一次打开时的样子。服务器上的账号和学习记录还在：要停下来，请在「账号和隐私 → 数据存放」里撤回；要删除，请注销账号。</span>'],
    ].filter(Boolean);
    const sec = (h, body, foot) => `<section class="me-sec" aria-label="${h}"><h2 class="me-h">${h}</h2>${body}${foot ? `<p class="tiny muted gfoot">${foot}</p>` : ''}</section>`;
    view.innerHTML = `<section class="me-card me-head">${u ? `<span class="avatar" aria-hidden="true">${esc([...u.username][0].toUpperCase())}</span>` : ''}
        <div class="t"><h1 class="me-name">${u ? esc(u.username) : '我的'}${BETA ? ' <span class="beta-pill" aria-label="内测版">内测</span>' : ''}</h1>
          <span class="me-line">${lv ? `${esc(lv.label)}（${lv.id}）` : '还没有设置水平'} · 每天 ${p.minutes || 10} 分钟</span>
          ${st ? `<span class="me-line">这周学了 ${days} 天 · 学完 ${st.materials_done} 篇 · ${st.cards} 个词</span>` : u ? '' : '<span class="me-line">登录后才能保存进度、收藏表达和使用 AI。</span>'}</div>
        ${u ? '' : '<button class="btn primary small" id="lg" type="button">登录 / 注册</button>'}</section>
      ${u ? '<div id="meTeach"></div>' : ''}
      ${u ? sec('进步', `<div class="me-tiles">${meTile('#/growth', 'trend', '我的进步', st && st.habit ? `达标 ${st.habit.weeks || 0} 周` : '', '', 'me-growth')}${meTile('#/report', 'week', '周报', '最近 7 天', '', 'me-report')}${meTile('#/cards/mistake', 'bookx', '错题本', '', 'meMistakeV', 'me-mistake')}</div>`) : ''}
      ${sec('设置', `<div class="glist me-list">${settings.join('')}</div>`)}
      ${groups.map(([h, rows, foot]) => sec(h, `<div class="glist">${rows.join('')}</div>`, foot)).join('')}
      <div class="me-folds">${u ? meFold('account', [grow('bindMail', '邮箱', '<span class="spin"></span>', 'acctEmail'), grow('chPw', '修改密码'), grow('outAll', '退出所有设备'),
        zhRow(grow('meAge', '年龄段', ageLabel(u && u.age), 'meAgeV', 'me-age')), zhRow(grow('meStorage', '数据存放', '已同意 · 香港')), zhRow(grow('#/guide/terms', '用户协议', '和隐私说明一起同意')), zhRow(grow('#/guide/privacy', '隐私说明', '', '', 'me-privacy')),
        grow('meData', '导出我的数据', '', '', 'me-data'), grow('meDelete', '注销账号', '', '', 'me-delete')],
        '绑定邮箱后，可以用验证码登录，忘记密码时自己找回。30 天内来过就一直保持登录；在别人的手机或电脑上用完，记得退出。') : ''}
      ${meFold('help', [grow('#/guide', '操作指南', '', '', 'me-guide'), grow('#/updates', '更新记录', '', '', 'me-updates'), grow('#/feedback', '问题反馈', '', '', 'me-feedback'), zhRow(grow('#/guide/privacy', '隐私说明', '', '', 'me-privacy')), grow('meMore', '更多', '认识语流、匿名问卷、新手引导', '', 'me-more')])}</div>
      ${appPrivacy() ? '<p class="tiny muted me-beian"><span id="meBeian" hidden></span></p>' : ''}
      ${u ? '<div class="me-out"><button class="grow danger" id="out" type="button"><span class="t">退出登录</span></button></div>' : ''}`;
    view.querySelectorAll('details.me-fold').forEach(d => d.addEventListener('toggle', () => { ME_OPEN[d.dataset.fold] = d.open; }));
    const opened = ME_FOLDS[fold] && document.getElementById('meFold-' + fold);
    if (opened) requestAnimationFrame(() => opened.scrollIntoView({ block: 'start', behavior: 'auto' }));
    const lg = document.getElementById('lg'); if (lg) lg.onclick = () => openLogin();
    document.getElementById('meVoice').onclick = voiceSheet;
    if (document.getElementById('meSound')) document.getElementById('meSound').onclick = soundSheet;
    const mh = document.getElementById('meHabit'); if (mh) mh.onclick = habitSheet;
    const me = document.getElementById('meExam'); if (me) me.onclick = () => examGoalSheet(() => meView());
    document.getElementById('meRemind').onclick = () => (u ? remindMailSheet : remindSheet)(p.minutes || 10);
    if (u) fillMailRow();  // 11-progress.js
    const mai = document.getElementById('meAi'); if (mai) { mai.onclick = aiUsageSheet; fillAiRow(); }
    personalizeWire();  // the switch and 「了解更多」 (81-privacy.js)
    const mi = document.getElementById('meInstall'); if (mi) mi.onclick = installSheet;
    const mw = document.getElementById('meWithdraw'); if (mw) mw.onclick = withdrawInApp;  // 81-privacy.js
    const mpm = document.getElementById('mePerms'); if (mpm) mpm.onclick = permissionsSheet;
    fillBeian();
    const ma = document.getElementById('meApp'); if (ma) ma.onclick = () => FlowApp.call('app.settings').catch(() => toast('打不开 App 的设置页，把语流 App 更新到最新版再试'));
    document.getElementById('meMore').onclick = moreSheet;
    if (BETA) betaInfo();
    if (u) {
      fillMistakeTile();
      const mc = document.getElementById('meClass'); if (mc) mc.onclick = () => classSheet();  // a 老师账号 has no 班级 row
      meClass();
      const b = document.getElementById('bindMail'); b.disabled = true;
      api('/api/account').then(a => {
        const el = document.getElementById('acctEmail'); if (!el) return;
        el.textContent = a.email || '还没有绑定';
        if (a.mail_enabled) { b.disabled = false; b.setAttribute('aria-label', a.email ? '邮箱：' + a.email + '，点这里更换' : '绑定邮箱'); b.onclick = () => bindEmailSheet(a.email); }
        else if (!a.email) el.textContent += '（邮件服务暂未开启）';
      }).catch(() => { const el = document.getElementById('acctEmail'); if (el) el.textContent = ''; });
      document.getElementById('chPw').onclick = () => changePasswordSheet();
      document.getElementById('outAll').onclick = () => signOutEverywhere();
      document.getElementById('meData').onclick = dataSheet;
      document.getElementById('meAge').onclick = () => ageSheet(false);
      document.getElementById('meStorage').onclick = storageSheet;
      document.getElementById('meDelete').onclick = deleteAccountSheet;
      document.getElementById('out').onclick = async () => { await OUTBOX.flush(); try { await api('/api/logout', {}); } catch (e) { /* ignore */ } snapClear(); S.user = null; S.csrf = ''; await refreshHome(); toast('已退出'); route(); };
    }
  }
  // 字号和行距: the reading text (a material, the listening lines, review sentences, questions, the guide, meanings)
  // larger and with more room between lines; menus and buttons stay as they are (applyText, 02-shell.js). Set in
  // 我的 → 使用习惯 (81-habits.js) and kept with the account (07-prefs.js).
  const TEXT_SIZES = [['m', '标准'], ['l', '大'], ['xl', '特大']], TEXT_LH = [['n', '标准'], ['w', '宽松']];
  // iPhones and iPads: how words, examples and short sentences are played (01-audio-offline.js AUDIO / CLIP), and the
  // silence in front of a word in 标准. Kept on this phone: the app on the home screen keeps its own, and has no address
  // bar for ?audio= and ?lead= (the owner compares the two ways on an iPhone before the default is chosen).
  const SOUND_MODES = [['auto', '连续', '从第一个音开始放；连着点单词时，灵动岛会一直显示「语流 · 单词」，停下 20 秒后收起。（默认）'],
    ['compat', '标准', '每个词是一个前面留了一点静音的小音频，大部分单词不会出现在灵动岛上。「连续」没有声音时选这个。']];
  const soundLabel = () => AUDIO.mode() === 'compat' ? `标准 · 前面 ${AUDIO.lead()} 秒` : '连续';
  function soundSheet() {
    const leadChips = () => AUDIO.LEADS.map(v => `<button class="chip" type="button" data-lead="${v}" aria-pressed="${AUDIO.lead() === v}">${v} 秒${v === AUDIO.LEAD_DEFAULT ? '（默认）' : ''}</button>`).join('');
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">单词读音方式</h2>
      <div class="choice" role="radiogroup" aria-labelledby="sheetTitle">${SOUND_MODES.map(([k, t, d]) => `<button class="opt" type="button" role="radio" data-sound="${k}" aria-checked="${AUDIO.mode() === k}" aria-pressed="${AUDIO.mode() === k}"><b>${t}</b><span class="small muted">${d}</span></button>`).join('')}</div>
      <div class="stack-s" id="leadBox"><b class="small" id="leadTitle">「标准」时单词前面留的静音</b><div class="chips" role="group" aria-labelledby="leadTitle">${leadChips()}</div>
      <p class="tiny muted">开头还被吞，就选长一点；开头都全，可以选短一点，出现在灵动岛上的单词会更少。</p></div>
      <p class="muted small">两种方式在静音键打开时都能听到。只影响这台手机。</p><button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      const shown = () => { const v = document.getElementById('meSoundV'); if (v) v.textContent = soundLabel(); };
      card.querySelectorAll('[data-sound]').forEach(b => b.onclick = () => {
        AUDIO.setMode(b.dataset.sound);
        card.querySelectorAll('[data-sound]').forEach(x => { x.setAttribute('aria-checked', String(x === b)); x.setAttribute('aria-pressed', String(x === b)); });
        shown(); toast('单词读音方式：' + soundLabel());
      });
      card.querySelectorAll('[data-lead]').forEach(b => b.onclick = () => {
        AUDIO.setLead(Number(b.dataset.lead));
        card.querySelectorAll('[data-lead]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
        shown(); toast(`「标准」时单词前面留 ${AUDIO.lead()} 秒静音`);
      });
    });
  }
  function voiceSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">朗读声音</h2>${voiceChips(null)}
      <p class="muted small">语流里的读音和朗读都是 AI 合成的，不是真人录的：精选材料和单词用 Kokoro，其余（AI 的回复、口语情景、没有录音的句子）用 CosyVoice，都是自然人声。放声音的地方写着一行小灰字「读音由 AI 合成」或「朗读由 AI 合成」，喇叭多的列表里每个喇叭右上角有一个淡淡的「AI」。学一篇材料时，也可以在「听」这一步随时切换声音。</p><button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      card.querySelectorAll('[data-voice]').forEach(b => b.onclick = async () => {
        await setVoice(b.dataset.voice);
        card.querySelectorAll('[data-voice]').forEach(x => { x.setAttribute('aria-pressed', String(x === b)); x.setAttribute('aria-checked', String(x === b)); });
        const v = document.getElementById('meVoiceV'); if (v) v.textContent = VOICE_LABELS[b.dataset.voice];
        toast('朗读声音：' + VOICE_LABELS[b.dataset.voice]);
      });
    });
  }
  function remindSheet(minutes) {
    const ics = h => `/api/next/vocab/reminder.ics?kind=plan&hour=${h}&minutes=${minutes}`;
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">每天提醒</h2>
      <p class="muted small">加到手机日历：每天到点提醒你打开今天的计划。不用装 App、不用邮箱，iPhone 和安卓都能用。</p>
      <div class="row"><select id="mHour" aria-label="提醒时间">${Array.from({ length: 18 }, (_, k) => k + 6).map(h => `<option value="${h}" ${h === 20 ? 'selected' : ''}>每天 ${h}:00</option>`).join('')}</select>
        <a class="btn primary" id="mCal" href="${ics(20)}">加到手机日历</a></div>
      <p class="tiny muted">打开下载的文件，选「添加到日历」即可；不想要了就在日历里删掉这个日程。</p><button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      const hour = card.querySelector('#mHour'), cal = card.querySelector('#mCal');
      hour.onchange = () => { cal.href = ics(hour.value); };
    });
  }
  /* ---------- on the home screen: two steps for the phone in hand, or one tap where the browser offers it ---------- */
  const STANDALONE = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const IN_WECHAT = /MicroMessenger/i.test(navigator.userAgent);  // WeChat cannot install; its own bar says how to leave it
  function installKind() {
    const ua = navigator.userAgent, ipad = /iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);  // iPadOS says Mac
    if (IN_WECHAT && !/iPhone|iPod/.test(ua) && !ipad) return 'wechat';
    if (/iPhone|iPod/.test(ua) || ipad) return /CriOS|FxiOS|EdgiOS|OPiOS|MicroMessenger|QQ\//.test(ua) ? 'ios-other' : ipad ? 'ipad' : 'iphone';
    if (installPrompt) return 'prompt';
    if (/Android/i.test(ua)) return 'android';
    // HarmonyOS NEXT (鸿蒙 5 and up: 华为浏览器 and other ArkWeb browsers) says OpenHarmony and no Android; without this it
    // was told to use Chrome or Edge, as on a computer. HarmonyOS 4 and before say Android and keep the Android steps.
    return /OpenHarmony/i.test(ua) ? 'harmony' : 'desktop';
  }
  addEventListener('appinstalled', () => { save('flow-installed', Date.now()); installPrompt = null; const n = document.getElementById('installNudge'); if (n) n.remove(); });
  // The 今日 notice: a phone browser (not WeChat, not already on the home screen) of a learner who has studied once.
  function installNudgeDue(h) {
    return !!(S.user && TOUCH && !IN_WECHAT && !STANDALONE() && !load('flow-installed') && h.stats && (h.stats.materials_done || 0) >= 1
      && Date.now() - (load('flow-install-later') || 0) > 30 * 864e5);
  }
  function installSheet() {
    const k = installKind(), share = '<svg class="ishare" viewBox="0 0 24 24" aria-label="分享按钮"><path d="M12 15V3M8 7l4-4 4 4"/><path d="M7 10H6v10h12V10h-1"/></svg>';
    const steps = {
      iphone: [`点屏幕<b>底部中间</b>的分享按钮 ${share}`, '往下滑，点「<b>添加到主屏幕</b>」，再点右上角的「添加」'],
      ipad: [`点<b>右上角</b>的分享按钮 ${share}`, '往下滑，点「<b>添加到主屏幕</b>」，再点「添加」'],
      'ios-other': ['苹果手机要用 <b>Safari</b> 才能放到桌面：点下面的「复制网址」，打开 Safari，粘贴并前往', `在 Safari 里点底部中间的分享按钮 ${share}，选「<b>添加到主屏幕</b>」`],
      wechat: ['微信里不能放到桌面：点右上角「<b>···</b>」，选「<b>在浏览器打开</b>」', '在浏览器里打开「我的 → 添加到桌面」，按那里的两步做'],
      android: ['点浏览器右上角的 <b>⋮</b>（有的浏览器在底部，是 <b>≡</b>）', '选「<b>添加到主屏幕</b>」或「<b>安装应用</b>」（有的手机叫「添加到桌面」）'],
      harmony: ['点浏览器的菜单按钮（华为浏览器在底部，是 <b>≡</b>）', '找到「<b>添加到桌面</b>」点一下（有的版本叫「添加至桌面」）'],
      desktop: ['用 Chrome 或 Edge 打开语流，点地址栏右边的「安装」图标', '装好以后，可以从开始菜单或程序坞打开'],
    }[k];
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">把语流放到桌面</h2>
      <p class="muted small">像 App 一样从桌面一点就开，界面全屏；听过的音频会缓存下来，网络差的时候也能复习。</p>
      ${k === 'prompt' ? '<button class="btn primary" id="doInstall" type="button">安装到桌面</button>' : `<ol class="isteps">${steps.map(x => `<li>${x}</li>`).join('')}</ol>`}
      ${k === 'ios-other' ? '<button class="btn" id="copyUrl" type="button">复制网址</button>' : ''}
      <button class="btn ghost" data-close type="button">${k === 'prompt' ? '取消' : '知道了'}</button></div>`, card => {
      const di = card.querySelector('#doInstall');
      if (di) di.onclick = async () => {
        const p = installPrompt; if (!p) return closeSheet();
        let ok = false; p.prompt(); try { ok = (await p.userChoice).outcome === 'accepted'; } catch (e) { /* dismissed */ }
        installPrompt = null; closeSheet();
        if (ok) { save('flow-installed', Date.now()); toast('放好了，在桌面上找「语流」'); }
        route(true);
      };
      const cu = card.querySelector('#copyUrl');
      if (cu) cu.onclick = () => { const u = location.origin + '/'; (navigator.clipboard ? navigator.clipboard.writeText(u) : Promise.reject()).then(() => toast('网址已复制，去 Safari 粘贴打开'), () => prompt('复制这个网址，到 Safari 里打开', u)); };
    });
  }

  // Binding an email: the current password, then a 6-digit code sent to the new address (as at sign-up).
  function bindEmailSheet(cur) {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">${cur ? '更换' : '绑定'}邮箱</h2>
      <p class="muted small">先输入当前密码确认是你本人，再把发到新邮箱的 6 位验证码填回来。</p>
      <form id="bm" class="stack" novalidate><label class="field">邮箱<input name="email" type="email" autocomplete="email" inputmode="email" autocapitalize="off" spellcheck="false" required></label>
        ${pwField('当前密码', 'password', 'current-password')}
        <div class="code-row"><label class="field">验证码<input name="code" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="6" required></label>
          <button class="btn small" type="button" data-send>发送验证码</button></div>
        <button class="btn primary" type="submit">完成绑定</button></form>
      <p class="err" id="bmErr" role="alert"></p><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      bindEyes(card);
      const form = card.querySelector('#bm'), err = card.querySelector('#bmErr'), send = card.querySelector('[data-send]');
      send.onclick = async () => {
        err.textContent = ''; send.disabled = true;
        try { const r = await api('/api/account/email/request', { email: form.email.value.trim(), password: form.password.value, mode: 'code' }); toast(r.message || '验证码已发送'); countdown(send); form.code.focus(); }
        catch (x) { fieldError(form, err, { message: x.message, field: x.field || 'email' }); send.disabled = false; }
      };
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        if (!/^\d{6}$/.test(form.code.value.trim())) return fieldError(form, err, { message: '请先发送验证码，再填邮件里的 6 位数字', field: 'code' });
        const b = form.querySelector('[type=submit]'); b.disabled = true;
        try { await api('/api/account/email/confirm', { email: form.email.value.trim(), code: form.code.value.trim() }); closeSheet(); toast('邮箱已绑定，忘记密码时可以自己找回了'); await refreshHome(); route(true); }
        catch (x) { fieldError(form, err, x); b.disabled = false; }
      };
    });
  }
  // A new password ends every session, this one too: sign in again with it.
  function changePasswordSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">修改密码</h2>
      <p class="muted small">改好以后，所有手机和电脑上的登录都会退出，用新密码重新登录就行。</p>
      <form id="cp" class="stack" novalidate>${pwField('原密码', 'old', 'current-password')}${pwField('新密码', 'new', 'new-password', '至少 10 位，最好是一句只有你知道的话')}
        ${pwField('再输一次新密码', 'again', 'new-password')}<button class="btn primary" type="submit">保存新密码</button></form>
      <p class="err" id="cpErr" role="alert"></p><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      bindEyes(card);
      const form = card.querySelector('#cp'), err = card.querySelector('#cpErr');
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        if (form.new.value.length < 10) return fieldError(form, err, { message: '新密码至少 10 位', field: 'new' });
        if (form.new.value !== form.again.value) return fieldError(form, err, { message: '两次输入的新密码不一样', field: 'again' });
        const b = form.querySelector('[type=submit]'); b.disabled = true;
        try {
          await api('/api/password', { old_password: form.old.value, new_password: form.new.value });
          S.user = null; S.csrf = ''; closeSheet(); await refreshHome(); route();
          openLogin('密码已修改，请用新密码登录。', 'pw');
        } catch (x) { fieldError(form, err, { message: x.message, field: /原密码/.test(x.message) ? 'old' : /新密码/.test(x.message) ? 'new' : '' }); b.disabled = false; }
      };
    });
  }
  // 我的数据 (account_data.py): the word book for Excel/WPS/Numbers or for Anki, or every record of the account. Plain
  // links: the server sends them as files. WeChat does not save files, so there the way out is the phone's browser.
  const EXPORTS = [['/api/next/export/cards.csv', '单词本 · Excel 表格', '.csv', 'export-csv'],
    ['/api/next/export/cards-anki.txt', '单词本 · 导入 Anki', '.txt', 'export-anki'],
    ['/api/next/export/records.json', '全部学习记录', '.json', 'export-json']];
  function dataSheet() {
    const n = S.home && S.home.stats ? S.home.stats.cards : null;
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">导出我的数据</h2>
      ${IN_WECHAT ? '<p class="small card sunk">微信里不能保存文件：点右上角「…」，选「在浏览器打开」，再到「我的 → 导出我的数据」。</p>' : ''}
      <div class="glist">${EXPORTS.map(([href, label, ext, tap], k) => `<a class="grow" href="${href}" download data-tap="${tap}"><span class="t">${label}</span><span class="v small muted">${k < 2 && n != null ? n + ' 条 · ' : ''}${ext}</span><span class="go" aria-hidden="true">↓</span></a>`).join('')}</div>
      <p class="tiny muted">表格用 Excel、WPS 或 Numbers 直接打开：英文、中文意思、原文例句、来源和复习情况各占一列。Anki：在电脑上「文件 → 导入」选这个文件，正面是英文，背面是中文意思和原文例句。全部学习记录是一个 JSON 文件，有单词本、每次复习、学过的材料、测评和设置，留底或换地方用。</p>
      <button class="btn ghost" data-close type="button">完成</button></div>`);
  }
  // 注销账号: what goes (all of it, for good), a copy first if wanted, the password once more. Afterwards this phone
  // forgets the account too.
  function deleteAccountSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">注销账号</h2>
      <p class="small">注销后，这个账号和它的全部学习记录都会删除，<b>不能恢复</b>：单词本和复习安排、学过的材料、测评和能力雷达、写作和口语的批改记录、发过的问题反馈和截图。同样的用户名和邮箱以后可以重新注册，但会从头开始。</p>
      <p class="small">想留一份？<button class="link" id="dlFirst" type="button">先导出单词本和学习记录</button></p>
      <form id="da" class="stack" novalidate>${pwField('输入密码确认', 'password', 'current-password')}
        <button class="btn danger-btn" type="submit">永久注销这个账号</button></form>
      <p class="err" id="daErr" role="alert"></p><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      bindEyes(card);
      card.querySelector('#dlFirst').onclick = dataSheet;
      const form = card.querySelector('#da'), err = card.querySelector('#daErr');
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        if (!form.password.value) return fieldError(form, err, { message: '请输入密码', field: 'password' });
        const b = form.querySelector('[type=submit]'); b.disabled = true;
        try {
          await api('/api/account/delete', { password: form.password.value });
          forgetAccountHere(); S.user = null; S.csrf = ''; closeSheet(); await refreshHome();
          location.hash = '#/'; route(); toast('账号已注销，学习记录已全部删除');
        } catch (x) { fieldError(form, err, { message: x.message, field: 'password' }); b.disabled = false; }
      };
    });
  }
  // What this phone kept for the account: the copies (snapClear) and the small notes of where the learner was.
  // The phone's own choices (voice, text size, 复读) stay.
  function forgetAccountHere() {
    snapClear();
    try {
      ['flow-habit-lastweek', 'flow-habit-cheered', 'flow-next-mail-nudge', 'flow-next-suggest-skip', 'flow-words-stats'].forEach(k => localStorage.removeItem(k));
      Object.keys(localStorage).filter(k => k.startsWith('flow-next-steps-')).forEach(k => localStorage.removeItem(k));
    } catch (e) { /* private mode */ }
  }
  // A lost phone, a shared computer: end the account's sessions everywhere, this one included.
  function signOutEverywhere() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">退出所有设备？</h2>
      <p class="small">所有手机、平板和电脑上的语流都会退出登录，包括这一台。学习记录不会丢，重新登录就回来了。</p>
      <button class="btn primary" id="soAll" type="button">退出所有设备</button><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      card.querySelector('#soAll').onclick = async e => {
        e.currentTarget.disabled = true;
        await OUTBOX.flush(); try { await api('/api/logout', { all: true }); } catch (x) { /* signed out already */ } snapClear();
        S.user = null; S.csrf = ''; closeSheet(); await refreshHome(); toast('已在所有设备上退出'); route();
      };
    });
  }


  /* ---------- 年龄段和监护人同意 (privacy_service.py): a band, never a birthday; under 14, a guardian's agreement ---------- */
  const AGE_BANDS = [['u14', '不满 14 岁'], ['14-17', '14–17 岁'], ['18+', '18 岁及以上']];
  const GUARD_WHY = '你的账号和学习数据存放在香港的服务器上，你写的作文和说的录音会交给 AI 批改（录音不保存），所以需要家长知道。';
  const PRIVACY = '/#/guide/privacy';
  function ageLabel(a) { const x = AGE_BANDS.find(b => b[0] === a); return x ? x[1] : '没填'; }
  // The three bands as chips (radio buttons) and, for 不满 14 岁 without an agreement on record, the box to tick.
  function ageFields(cur, onRecord) {
    return `<fieldset class="agefs"><legend>年龄段<span class="hint">只用来保护未成年人的信息，不问生日。</span></legend>
      <div class="chips" role="radiogroup" aria-label="年龄段">${AGE_BANDS.map(([k, l]) => `<label class="chip agechip"><input type="radio" name="age" value="${k}"${cur === k ? ' checked' : ''}><span>${l}</span></label>`).join('')}</div>
      <div class="guard" ${cur === 'u14' && !onRecord ? '' : 'hidden'}><label class="checkline"><input type="checkbox" name="guardian"><span>我已经告诉家长（或监护人），他们同意我用语流，也同意我的账号和学习数据存放在香港的服务器上</span></label>
        <span class="hint">${GUARD_WHY}<a class="link" href="${PRIVACY}" target="_blank" rel="noopener">看隐私说明</a></span></div></fieldset>`;
  }
  function bindAge(root, onRecord) {
    const g = root.querySelector('.guard'), radios = root.querySelectorAll('input[name=age]');
    const show = () => radios.forEach(x => x.parentNode.dataset.on = String(x.checked));  // the chips' look (no :has)
    radios.forEach(r => { r.onchange = () => { if (r.checked) g.hidden = !(r.value === 'u14' && !onRecord); show(); }; });
    show();
  }
  function readAge(root) {
    const r = root.querySelector('input[name=age]:checked'), g = root.querySelector('input[name=guardian]');
    return { age: r ? r.value : '', guardian: !!(g && g.checked) };
  }
  // The same check the server makes, said at once: '' when fine. need: under 14, the tick is required here.
  function ageProblem(a, need, onRecord) {
    if (!a.age) return '请选一个年龄段';
    if (need && a.age === 'u14' && !a.guardian && !onRecord) return '不满 14 岁需要先告诉家长（或监护人）并得到同意，勾选后才能继续';
    return '';
  }
  // An account without a band (made before 2026-11-24, or by an older page) is asked once, the next time it opens the
  // site; the sheet stays until a band is chosen. locked: no 关闭, the scrim, Esc and a swipe down do nothing.
  let ageAsked = false;
  function askAgeOnce() {
    if (!S.user || S.user.age || ageAsked || !sheetEl.hidden || S.user.storage !== 'ok' || S.user.terms !== 'ok') return;  // the consents first (storageView)
    ageAsked = true; ageSheet(true);
  }
  function ageSheet(locked) {
    const u = S.user; if (!u) return;
    openSheet(`<div class="stack"${locked ? ' data-lock' : ''}><h2 class="h2" id="sheetTitle">${locked ? '补充一个问题：你现在多大？' : '年龄段'}</h2>
      <form id="ageF" class="stack" novalidate>${ageFields(u.age, u.guardian)}
        <p class="small muted">不满 14 岁、还没告诉家长的，可以先选；学材料、背单词、做题都照常，要交给 AI 批改的作文和录音等家长同意以后再用。</p>
        <button class="btn primary" type="submit">好了</button></form>
      <p class="err" id="ageErr" role="alert"></p>${locked ? '' : '<button class="btn ghost" data-close type="button">取消</button>'}</div>`, card => {
      const form = card.querySelector('#ageF'), err = card.querySelector('#ageErr');
      bindAge(card, u.guardian);
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        const a = readAge(form), p = ageProblem(a, false, u.guardian);
        if (p) { err.textContent = p; const r = form.querySelector('input[name=age]'); if (r) r.focus(); return; }
        try { Object.assign(S.user, await api('/api/account/age', a)); closeSheet(); toast(S.user.age === 'u14' && !S.user.guardian ? '好了。家长同意以后，在「我的 → 年龄段」里勾选' : '好了，谢谢'); const v = document.getElementById('meAgeV'); if (v) v.textContent = ageLabel(S.user.age); }
        catch (x) { err.textContent = x.message; }
      };
    });
  }
  // A feature that hands the learner's own words or voice to AI answered 403 code 'guardian' (privacy_service.gate).
  function guardianSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">先告诉家长</h2>
      <p class="small">这一步会把你写的或说的交给 AI 处理。不满 14 岁，需要先告诉家长（或监护人），得到同意以后再用。学材料、背单词、做题不受影响。</p>
      <form id="guardF" class="stack" novalidate><label class="checkline"><input type="checkbox" name="guardian"><span>我已经告诉家长（或监护人），他们同意我用语流，也同意我的账号和学习数据存放在香港的服务器上</span></label>
        <a class="link small" href="${PRIVACY}" target="_blank" rel="noopener">看隐私说明：数据存在哪里、交给哪家 AI</a>
        <button class="btn primary" type="submit">继续</button></form>
      <p class="err" id="guardErr" role="alert"></p><button class="btn ghost" data-close type="button">先不用</button></div>`, card => {
      const form = card.querySelector('#guardF'), err = card.querySelector('#guardErr');
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        if (!form.guardian.checked) { err.textContent = '勾选以后才能继续'; form.guardian.focus(); return; }
        try { Object.assign(S.user, await api('/api/account/age', { age: 'u14', guardian: true })); closeSheet(); toast('好了，再点一次刚才的按钮'); }
        catch (x) { err.textContent = x.message; }
      };
    });
  }

  /* ---------- 数据存放在香港的单独同意 (privacy_service.py, 2026-11-25): its own tick at sign-up; an older account is asked
     once on a page of its own; 不同意 or 撤回 pauses the account (only agree again, export, delete, sign out) ---------- */
  // The wording is privacy_service.STORAGE_VERSION: change it, change that version too (语流 23 reviewed this one).
  const STORAGE_TEXT = '我同意语流在香港的服务器上存放和处理我的账号和学习数据';
  const STORAGE_WHY = '语流的网站和数据库都在香港的服务器上运行。你的账号、学习记录、写的作文和练习的文字、问题反馈都存在那里。你说的录音不保存，但批改时会经过香港的服务器转给 AI。这些数据由语流的运营者处理，只用来给你提供学习服务。香港在中国内地以外，所以单独问你。';
  const STORAGE_RIGHTS = '你可以随时在「我的 → 账号和隐私」里导出数据、注销账号或撤回同意；有问题请用「我的 → 帮助 → 问题反馈」，或写信到 i@jasa.hk。';
  // A tick is ticked by its box or its words, at once; only a document's name opens it (docOver, over the page: the form
  // underneath keeps what was typed and ticked). The box takes a 44px tap (.tickbox); the names are not .link, so 99-tap.css
  // puts no wider tap area of theirs over the box (the user, 2026-11-25: 「一般都是直接勾选」).
  const tickbox = name => `<span class="tickbox"><input type="checkbox" name="${name}"></span>`;
  const docLink = (href, id, text) => `<a class="doc-link" href="${href}" data-doc="${id}">${text}</a>`;
  function storageField(folded) {
    const why = `${STORAGE_WHY}不满 14 岁的，要家长（或监护人）也同意。${STORAGE_RIGHTS}${docLink(PRIVACY, 'privacy', '看隐私说明')}`;
    return `<div class="storagefs"><label class="checkline">${tickbox('storage')}<span>${STORAGE_TEXT}</span></label>
      ${folded ? `<details class="sto-why"><summary class="hint">为什么单独问这个</summary><span class="hint">${why}</span></details>` : `<span class="hint">${why}</span>`}</div>`;
  }
  async function storageAnswer(agree) {
    const r = await api('/api/account/storage', { agree });
    Object.assign(S.user, r); S.homeFresh = false; await refreshHome();
  }
  // #/ and every page but the guide, while the account has not agreed: one short page (asked) or the paused page.
  // The 用户协议 and 隐私和数据 tick (privacy_service.TERMS_TEXT): on its own only where the storage is agreed already
  // (a new version of the two texts); both names open the full text.
  const TERMS = '/#/guide/terms';
  // One tick for both (the owner chose D2's plan B, 2026-11-26): it opens with the separate consent to the storage in Hong
  // Kong, in bold, then the two texts it needs; one grey line under it says why and how to withdraw. Never ticked
  // beforehand; both answers are still kept apart (privacy_service: storage and terms, each with its time), and the one
  // for Hong Kong is still withdrawn on its own (我的 → 账号和隐私 → 数据存放). 不满 14 岁: the guardian keeps a tick of its own.
  const CONSENT_LEAD = '我单独同意语流把我的账号和学习数据存放在香港的服务器上';
  function consentField() {
    return `<div class="storagefs"><label class="checkline">${tickbox('consent')}<span><b>${CONSENT_LEAD}</b>，并已阅读同意${docLink(TERMS, 'terms', '《用户协议》')}和${docLink(PRIVACY, 'privacy', '《隐私和数据》')}。</span></label>
      <span class="hint">账号本身就存在那里，不同意就注册不了；以后可以在「我的 → 账号和隐私 → 数据存放」撤回。</span></div>`;
  }
  function termsField() {
    return `<div class="storagefs"><label class="checkline">${tickbox('terms')}<span>我已阅读并同意${docLink(TERMS, 'terms', '《用户协议》')}和${docLink(PRIVACY, 'privacy', '《隐私和数据》')}</span></label></div>`;
  }
  // a document's full text over the page (the guide's chapter), 返回 to the form as it was; its links to other chapters stay
  // in this layer, so nothing typed is lost (in the apps too, where a new tab would leave the page)
  const DOC_NAME = { terms: '语流用户协议', privacy: '隐私和数据' };
  function docOver(id) {
    const back = document.activeElement, el = document.createElement('div');
    el.className = 'doc-over'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true');
    const frame = (title, body) => {
      el.setAttribute('aria-label', title);
      el.innerHTML = `<div class="doc-bar"><button class="btn small" type="button" data-doc-close>← 返回</button><b>${esc(title)}</b></div>
        <div class="guide-body doc-body">${body}</div><div class="doc-foot"><button class="btn primary block" type="button" data-doc-close>返回</button></div>`;
      el.scrollTop = 0;
    };
    // just this chapter (/api/next/guide?chapter=, open before any agreement too), kept for the page's life; shown at
    // once as 「正在打开」, and a failure says so with 再试一次, never a page that keeps retrying
    const show = async cid => {
      const name = DOC_NAME[cid] || '操作指南';
      S.docs = S.docs || {};
      if (!S.docs[cid]) frame(name, '<p class="muted">正在打开…</p>');
      try {
        const ch = S.docs[cid] || (S.docs[cid] = (await api('/api/next/guide?chapter=' + encodeURIComponent(cid))).chapter);
        if (el.isConnected) frame(ch.title, ch.html);
        const at = ch.anchor && el.querySelector('#g-' + CSS.escape(ch.anchor)); if (at) at.scrollIntoView({ block: 'start' });
      } catch (x) {
        frame(name, `<p>暂时打不开。请检查网络后再试一次；也可以稍后在「操作指南」里看《语流用户协议》和《隐私和数据》两章。</p><button class="btn" type="button" data-doc-retry="${esc(cid)}">再试一次</button>`);
      }
      const f = el.querySelector('[data-doc-close]'); if (f) f.focus();
    };
    const close = () => { el.remove(); document.removeEventListener('keydown', key, true); if (back && back.focus) back.focus(); };
    // over the sign-up sheet: Esc closes this layer only, and Tab stays here (the sheet would pull focus back into itself)
    const key = e => { if (e.key === 'Escape') { e.stopImmediatePropagation(); e.preventDefault(); close(); } else if (e.key === 'Tab') e.stopImmediatePropagation(); };
    el.onclick = e => {
      if (e.target.closest('[data-doc-close]')) return close();
      const again = e.target.closest('[data-doc-retry]'); if (again) return show(again.dataset.docRetry);
      const a = e.target.closest('a[href]'); if (!a) return;
      const h = a.getAttribute('href'), m = h.match(/^\/?#\/guide\/([\w-]+)/);
      if (m) { e.preventDefault(); show(m[1]); } else if (h.startsWith('#') || h.startsWith('/#')) e.preventDefault(); else { a.target = '_blank'; a.rel = 'noopener'; }
    };
    document.addEventListener('keydown', key, true);
    document.body.appendChild(el); show(id);
  }
  document.addEventListener('click', e => {
    const a = e.target.closest && e.target.closest('a[data-doc]');
    if (a) { e.preventDefault(); docOver(a.dataset.doc); }
  });
  // #/ and every page but the guide, while an answer is missing: the storage in Hong Kong (asked, or paused) and/or the
  // current 用户协议 and 隐私和数据 (never agreed, or a new version since). One page, one button.
  async function storageView() {
    const paused = S.user.storage === 'no', needStorage = S.user.storage !== 'ok', needTerms = S.user.terms !== 'ok';
    const termsOnly = needTerms && !needStorage;
    const quiet = `<a class="doc-link" href="/api/next/export/records.json" download>导出我的数据</a> · <button class="doc-link" id="stoDel" type="button">注销账号</button> · <button class="doc-link" id="stoOut" type="button">退出登录</button>`;
    // 视觉压力小 (A0, feedback #1): one line saying why learning waits, the tick and one button, the rest in small type;
    // the long note on the storage folds under 「为什么单独问这个」 (unchanged, one tap away)
    const until = S.user.storage_until ? `${esc(S.user.storage_until)} 以前` : '30 天内';
    view.innerHTML = `<div class="stack storage-page"><div><span class="kicker">${termsOnly ? '用户协议和隐私说明' : '数据存放'}</span><h1 class="h1">${paused ? '这个账号已暂停' : '补一个同意'}</h1></div>
      <p>${paused ? `你还没有同意把账号和学习数据存放在香港的服务器上，所以学习先停着。数据都还在，${until}同意就能接着学。`
        : termsOnly ? '我们更新了《用户协议》和《隐私和数据》，勾选同意后继续。' : '语流的账号和学习数据都存在香港的服务器上，在中国内地以外，所以单独问你一次。'}</p>
      <form class="card flat stack-s" id="stoF" novalidate>${needTerms && needStorage ? consentField() : needTerms ? termsField() : ''}${needStorage && !needTerms ? storageField(true) : ''}
        <button class="btn primary" type="submit">${paused ? '同意，继续学习' : termsOnly ? '继续' : '同意并继续'}</button><p class="err" id="stoErr" role="alert"></p></form>
      ${paused ? '<p class="tiny muted">暂停期间不发邮件，班级的数字里也不算你；30 天后还没有同意，语流会删除这个账号和数据，备份里的副本 14 天内清除。</p>'
        : termsOnly ? '' : '<p class="tiny muted">不同意的话，这个账号会暂停、不能学习；30 天内可以回来同意或导出数据，30 天后删除这个账号和数据。</p>'}
      <p class="tiny muted sto-quiet">${termsOnly || paused ? '不想同意：' : `<button class="doc-link" id="stoNo" type="button">不同意</button> · `}${quiet}</p>
      ${termsOnly || paused ? '' : '<p class="tiny muted">退出登录后，也可以不登录先看看语流：那时的进度只存在这台设备上。</p>'}</div>`;
    const f = document.getElementById('stoF'), err = document.getElementById('stoErr');
    f.onsubmit = async e => {
      e.preventDefault(); err.textContent = '';
      const both = needTerms && needStorage;  // the one tick for both (consentField)
      if (both && !f.consent.checked) return fieldError(f, err, { message: '请先勾选同意：数据存放在香港，以及《用户协议》和《隐私和数据》', field: 'consent' });
      if (!both && needTerms && !f.terms.checked) return fieldError(f, err, { message: '请先勾选同意《用户协议》和《隐私和数据》', field: 'terms' });
      if (!both && needStorage && !f.storage.checked) return fieldError(f, err, { message: '勾选同意以后才能继续', field: 'storage' });
      const b = f.querySelector('[type=submit]'); b.disabled = true;
      try {
        if (needTerms) Object.assign(S.user, await api('/api/account/terms', { agree: true }));
        if (needStorage) await storageAnswer(true); else { S.homeFresh = false; await refreshHome(); }
        toast('好了，谢谢'); route();
      } catch (x) { err.textContent = x.message; b.disabled = false; }
    };
    const no = document.getElementById('stoNo');
    if (no) no.onclick = async () => { no.disabled = true; try { await storageAnswer(false); route(); } catch (x) { err.textContent = x.message; no.disabled = false; } };
    document.getElementById('stoDel').onclick = deleteAccountSheet;
    document.getElementById('stoOut').onclick = async () => { try { await api('/api/logout', {}); } catch (x) { /* signed out already */ } snapClear(); S.user = null; S.csrf = ''; await refreshHome(); route(); };
  }
  // 安卓 App 1.0.4 and later (语流 C2, #332; docs/native-bridge.md §10, for the Chinese app stores): the app asks the
  // 用户协议 and 隐私和数据 itself on first opening. 我的 shows a 「隐私」 group only where the app has 'privacy':
  // 撤回同意 (the app explains, clears this phone and asks again: four steps at most) and 系统权限 (the microphone
  // and notifications, as the phone has them, each opening its page in the phone's settings).
  const appPrivacy = () => { try { return !!(window.FlowApp && FlowApp.has && FlowApp.has('privacy')); } catch (e) { return false; } };
  const PERM = { granted: '已允许', denied: '已拒绝', undetermined: '还没问过' };
  function withdrawInApp() { FlowApp.call('privacy.withdraw').catch(() => toast('打不开撤回同意，把语流 App 更新到最新版再试')); }
  function permissionsSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">系统权限</h2>
      <p class="small">语流只用这两项，都是第一次用到时才问。点一下，打开手机设置里对应的那一页，随时可以改。</p>
      <div class="glist">${grow('permMic', '麦克风', '…', 'permMicV')}${grow('permNotify', '通知', '…', 'permNotifyV')}</div>
      <p class="tiny muted">麦克风：只在跟读、口语对话和发音练习录音时用；录音只在批改的那一次交给 AI，不保存。通知：只在你打开「到点用 App 通知提醒」以后，到点提醒复习单词。</p>
      <button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      const fill = () => FlowApp.call('privacy.permissions').then(p => {
        [['mic', 'permMicV'], ['notify', 'permNotifyV']].forEach(([k, id]) => { const v = card.querySelector('#' + id); if (v) v.textContent = PERM[p && p[k]] || '—'; });
      }).catch(() => {});
      fill();
      card.querySelector('#permMic').onclick = () => FlowApp.call('privacy.settings', { what: 'mic' }).catch(() => {});
      card.querySelector('#permNotify').onclick = () => FlowApp.call('privacy.settings', { what: 'notify' }).catch(() => {});
      // back from the phone's settings: the state as it is now (nothing to do once the sheet is closed)
      const again = () => { if (!card.isConnected) document.removeEventListener('visibilitychange', again); else if (document.visibilityState === 'visible') fill(); };
      document.addEventListener('visibilitychange', again);
    });
  }
  // 「APP 备案号」 under 帮助, once the app has one (privacy.state().beian; empty until the filing is done)
  function fillBeian() {
    const el = document.getElementById('meBeian');
    if (!el || !appPrivacy()) return;
    FlowApp.call('privacy.state').then(st => {
      const no = st && String(st.beian || '').trim();
      if (!no || !el.isConnected) return;
      el.innerHTML = `APP 备案号：<a class="link" href="https://beian.miit.gov.cn/" target="_blank" rel="noopener">${esc(no)}</a>`; el.hidden = false;
    }).catch(() => {});
  }
  // 我的 → 设置 → 按我的学习记录推荐 (next_service.personal; 个保法第二十四条, 算法推荐规定第十七条: an option not aimed
  // at the person, that really switches it off). On by default; off, 今日 recommends by the chosen level only.
  // The user's pick (2026-11-26, as mainstream apps do it): a switch on the right of the row, one tap and it is in force;
  // the grey line under the group says what off means, with 「了解更多」 for the sheet, which keeps the words and the link
  // to the 隐私说明 and has no buttons of its own any more.
  const personalizeOn = () => !(S.home && S.home.profile && S.home.profile.personalize === false);
  function personalizeRow() {
    return `<label class="grow gswitch gi" for="mePersSw">${fiTile('compass')}<span class="t">按我的学习记录推荐</span><input type="checkbox" class="sw-in" id="mePersSw" role="switch"${personalizeOn() ? ' checked' : ''} aria-describedby="mePersFoot"><span class="sw" aria-hidden="true"></span></label>`;
  }
  const PERSONALIZE_FOOT = '<span id="mePersFoot">关掉「按我的学习记录推荐」以后，推荐只按你选的水平和新旧排，不看你的学习记录。</span><button class="link tiny" type="button" id="mePersInfo">了解更多</button>';
  function personalizeWire() {
    const sw = document.getElementById('mePersSw');
    if (sw) sw.onchange = async () => {
      const want = sw.checked; sw.disabled = true;
      try {
        const r = await api('/api/next/personalize', { on: want });
        if (S.home && S.home.profile) S.home.profile.personalize = r.personalize;
        S.homeFresh = false;  // 今日 is asked again, ranked the new way
        sw.checked = r.personalize !== false;
      } catch (e) { sw.checked = !want; toast(e.message); }  // as it was: the switch shows what is in force
      sw.disabled = false;
    };
    const more = document.getElementById('mePersInfo'); if (more) more.onclick = personalizeSheet;
  }
  function personalizeSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">按我的学习记录推荐</h2>
      <div class="pers-text"><p class="small">打开时，语流按你的学习记录给你挑内容：今日的「今天这篇」和「也可以读」（看你学过哪些、哪些语法要补、收藏和在背的词）、今日好句、今日计划里练哪一项，以及级别建议和周报里的建议。</p>
      <p class="small">关掉以后马上生效，只按你自己选的水平推荐：精选的在前，新的在前，不再看你的学习记录。复习单词和错题、复听和「接着学」还是按你学过的安排，那是在复习你自己的内容。</p></div>
      <a class="link small" href="#/guide/personalize" data-doc="personalize">用到了哪些记录（隐私说明）</a>
      <button class="btn ghost" data-close type="button">完成</button></div>`);
  }
  // 我的 → 账号和隐私 → 数据存放: what was agreed, and 撤回同意 (the account is paused at once).
  function storageSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">数据存放</h2>
      <p class="small">你已经同意语流在香港的服务器上存放和处理你的账号和学习数据。${STORAGE_WHY}</p>
      <a class="link small" href="${PRIVACY}" target="_blank" rel="noopener">看隐私说明：存了什么、存多久、怎么删</a>
      <div id="stoW" class="stack-s"><button class="btn" id="stoWithdraw" type="button">撤回同意</button></div>
      <p class="err" id="stoErr" role="alert"></p><button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      const box = card.querySelector('#stoW'), err = card.querySelector('#stoErr');
      card.querySelector('#stoWithdraw').onclick = () => {
        box.innerHTML = `<p class="small">撤回以后，这个账号马上暂停：不能学习，不再收邮件，班级的数字里也不算你。30 天内可以重新同意或导出数据；30 天后，语流会删除这个账号和数据。</p>
          <div class="row"><button class="btn danger-btn" id="stoYes" type="button">确定撤回</button><button class="btn ghost" id="stoKeep" type="button">不撤回</button></div>`;
        box.querySelector('#stoKeep').onclick = closeSheet;
        box.querySelector('#stoYes').onclick = async e => {
          e.target.disabled = true;
          try { await storageAnswer(false); closeSheet(); route(); } catch (x) { err.textContent = x.message; e.target.disabled = false; }
        };
      };
    });
  }
  /* ---------- 班级试用 (class_service.py): join a class with the teacher's code, leave at any time; a teacher sees the whole class's numbers only ---------- */
  // What a teacher sees and does not, said the same way before joining and on the teacher's own page.
  const CLASS_SEES = ['最近 7 天全班几人在学', '全班最常错的 5 个语法点'];
  const CLASS_NOT = ['你的名字、作业、答题和学习记录', '你一个人学了多少、错了什么'];
  const classLink = code => `${location.origin}/#/invite/${encodeURIComponent(code)}`;
  function classTerms(min) {
    return `<div class="cls-terms"><div><b>老师能看到</b><ul>${CLASS_SEES.map(x => `<li class="yes">${x}</li>`).join('')}</ul></div>
      <div><b>老师看不到</b><ul>${CLASS_NOT.map(x => `<li class="no">${x}</li>`).join('')}</ul></div></div>
      <p class="tiny muted">不满 ${min || 5} 人的班不出任何数字。随时可以退出，退出后老师的汇总里就不再算你。</p>`;
  }
  // 我的 → 班级: the class row's value, and the teacher's own group, filled in once /api/next/class answers.
  function meClass() {
    api('/api/next/class').then(k => {
      S.myClass = k;
      const v = document.getElementById('meClassV'); if (v) v.textContent = k.member ? k.member.name : '未加入';
      const at = document.getElementById('meTeach');
      if (at && k.teaching.length) at.innerHTML = `<section class="gsec" aria-label="我的班级"><h2 class="ghead">我的班级</h2><div class="glist">${k.teaching.map(t => grow(`#/class/${t.id}`, esc(t.name), t.active ? '全班汇总' : '已停用', '', 'me-class-teach')).join('')}</div>
        <p class="tiny muted gfoot">你是这些班的老师：这里只有全班的数字，看不到任何学生的名字、作业和记录。</p></section>`;
    }).catch(() => { const v = document.getElementById('meClassV'); if (v) v.textContent = ''; });
  }
  async function classSheet(code) {
    if (!S.user) return needLogin('登录后才能加入班级');
    let k = S.myClass;
    try { k = await api('/api/next/class'); S.myClass = k; } catch (e) { if (!k) return toast(e.message); }
    if (k.member) return classMemberSheet(k);
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">加入班级</h2>
      <p class="small">老师给你邀请码，加入后老师能看到全班的学习情况，但看不到你一个人的。</p>${classTerms(k.min)}
      <form id="clsF" class="stack" novalidate><div class="code-row"><label class="field">邀请码<input name="code" type="text" autocomplete="off" autocapitalize="characters" spellcheck="false" maxlength="12" placeholder="6 位，字母和数字" value="${esc(code || '')}" required></label>
        <button class="btn small" type="submit">查找</button></div></form>
      <div id="clsFound" class="stack-s" hidden></div>
      <p class="err" id="clsErr" role="alert"></p><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      const form = card.querySelector('#clsF'), err = card.querySelector('#clsErr'), found = card.querySelector('#clsFound');
      const look = async () => {
        err.textContent = ''; found.hidden = true;
        const c = form.code.value.trim();
        if (!c) return fieldError(form, err, { message: '请输入老师给你的邀请码', field: 'code' });
        try {
          const r = await api('/api/next/class/find', { code: c });
          // 年龄段 first, and under 14 a guardian's agreement (privacy_service): asked here when not on record yet
          const needAge = !S.user.age || (S.user.age === 'u14' && !S.user.guardian);
          found.innerHTML = `<div class="card sunk cls-found"><b>${esc(r.name)}</b><span class="small muted">老师 ${esc(r.teacher)}</span></div>
            ${r.teaching ? '<p class="small muted">你是这个班的老师，不用加入；在「我的班级」里看全班汇总。</p>' : `${needAge ? ageFields(S.user.age, S.user.guardian) : ''}<button class="btn primary" id="clsJoin" type="button">加入这个班</button>`}`;
          found.hidden = false;
          if (needAge) bindAge(found, S.user.guardian);
          const j = found.querySelector('#clsJoin');
          if (j) j.onclick = async () => {
            const a = needAge ? readAge(found) : {}, p = needAge ? ageProblem(a, true, S.user.guardian) : '';
            if (p) { err.textContent = p; return; }
            j.disabled = true;
            try { S.myClass = await api('/api/next/class/join', { code: c, ...a }); if (needAge) Object.assign(S.user, { age: a.age, guardian: S.user.guardian || a.guardian }); closeSheet(); toast(`已加入「${r.name}」`); const v = document.getElementById('meClassV'); if (v) v.textContent = r.name; if (location.hash.startsWith('#/invite')) location.replace('#/me'); }
            catch (x) { err.textContent = x.message; j.disabled = false; }
          };
        } catch (x) { fieldError(form, err, { message: x.message, field: 'code' }); }
      };
      form.onsubmit = e => { e.preventDefault(); look(); };
      if (code) look();
    });
  }
  function classMemberSheet(k) {
    const m = k.member;
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">我的班级</h2>
      <div class="card sunk cls-found"><b>${esc(m.name)}</b><span class="small muted">老师 ${esc(m.teacher || '还没有指定')} · ${esc(m.joined)} 加入</span></div>
      ${m.active ? '' : '<p class="small">这个班级已经停用：老师不再看到汇总。你可以退出。</p>'}${classTerms(k.min)}
      <div id="clsLeave" class="stack-s"><button class="btn" id="clsOut" type="button">退出班级</button></div>
      <p class="err" id="clsErr" role="alert"></p><button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      const box = card.querySelector('#clsLeave'), err = card.querySelector('#clsErr');
      card.querySelector('#clsOut').onclick = () => {
        box.innerHTML = `<p class="small">退出后，老师的汇总里马上不再算你；你自己的学习记录都还在。以后想回来，再输入一次邀请码就行。</p>
          <div class="row"><button class="btn danger-btn" id="clsOutYes" type="button">确定退出</button><button class="btn ghost" id="clsOutNo" type="button">不退出</button></div>`;
        box.querySelector('#clsOutNo').onclick = closeSheet;
        box.querySelector('#clsOutYes').onclick = async e => {
          e.target.disabled = true;
          try { S.myClass = await api('/api/next/class/leave', {}); closeSheet(); toast(`已退出「${m.name}」`); const v = document.getElementById('meClassV'); if (v) v.textContent = '未加入'; }
          catch (x) { err.textContent = x.message; e.target.disabled = false; }
        };
      };
    });
  }
  // #/invite/<code>: the link a teacher sends: 我的, with the sheet open and the code filled in. (#/join is 认识语流's sign-up.)
  async function joinRoute(code) {
    S.invite = code;  // a sign-up from here counts against the class's allowance, not the school network's (auth_service)
    await meView();
    if (!S.user) return openLogin('登录后就能加入班级（还没有账号可以先注册）');
    classSheet(code);
  }

  /* ---------- 老师模式 (teacher_service.py): a 老师账号 signs up with a one-use link; its home lists and makes its classes ---------- */
  const TEACH_SEES = ['全班最近 7 天几人在学，和近 4 周每周的人数', '全班最常错的 5 个语法点（点进去是讲解和练习）'];
  const TEACH_NOT = ['任何学生的名字、作业、答题和学习记录', '某一个学生学了多少、错了什么'];
  function teachTerms(min) {
    return `<div class="cls-terms"><div><b>你能看到</b><ul>${TEACH_SEES.map(x => `<li class="yes">${x}</li>`).join('')}</ul></div>
      <div><b>你看不到</b><ul>${TEACH_NOT.map(x => `<li class="no">${x}</li>`).join('')}</ul></div></div>
      <p class="tiny muted">班里不满 ${min || 5} 人时不显示任何数字；学生退出后马上不再计入。学生加入前会先看到这些。</p>`;
  }
  const TEACH_LINK_KEY = 'flow-teacher-link';
  function teachIntro(title) { return `<div><span class="kicker">老师</span><h1 class="h1">${title}</h1></div>`; }
  function teachWhat() {
    return `<div class="card flat stack-s"><b>老师账号能做什么</b><ul class="cls-list"><li>自己建班级，拿到 6 位邀请码、加入链接和二维码，发给学生</li>
      <li>看全班汇总：最近 7 天几人在学、近 4 周每周人数、全班最常错的 5 个语法点</li><li>看不到任何学生的名字、作业、答题和学习记录</li></ul>
      <a class="link small" href="#/guide/teacher">老师操作说明</a></div>`;
  }
  // #/teacher/<token>: the 老师注册链接. The token leaves the address bar at once (kept for this tab only), so it is not
  // left in the history or a screenshot; the sign-up sheet sends it with the form.
  async function teacherSignup(token) {
    if (token) { try { sessionStorage.setItem(TEACH_LINK_KEY, token); } catch (e) { /* the sheet still has it */ } history.replaceState(null, '', location.pathname + location.search + '#/teacher'); }
    else { try { token = sessionStorage.getItem(TEACH_LINK_KEY) || ''; } catch (e) { token = ''; } }
    if (S.user && S.user.teacher) { try { sessionStorage.removeItem(TEACH_LINK_KEY); } catch (e) { /* nothing kept */ } location.replace('#/teach'); return; }
    const page = body => { view.innerHTML = `<div class="stack cls-page">${teachIntro('注册老师账号')}${body}${teachWhat()}</div>`; };
    if (!token) return page('<div class="card flat"><p>老师账号要用语流发给你的「老师注册链接」注册，一条链接只能注册一个老师账号。还没有链接，请联系语流。在登录框里直接注册，得到的是学生账号。</p></div>');
    if (S.user) {
      page(`<div class="card flat stack-s"><p>这台设备上现在登录着一个学生账号。老师账号要另外注册：先退出这个账号，再用这条链接注册。退出不会删掉学生账号里的任何东西。</p>
        <div class="row"><button class="btn primary" id="tOut" type="button">退出登录，注册老师账号</button></div></div>`);
      document.getElementById('tOut').onclick = async e => {
        e.target.disabled = true; await OUTBOX.flush(); try { await api('/api/logout', {}); } catch (x) { /* signed out already */ }
        snapClear(); S.user = null; S.csrf = ''; await refreshHome(); route();
      };
      return;
    }
    let ok;
    try { ok = await api('/api/teacher/check', { token }); }
    catch (x) { return page(`<div class="card flat"><p>${esc(x.message)}</p></div>`); }
    page(`<div class="card flat stack-s"><p>这是语流发给你的老师注册链接，有效到 ${esc(ok.expires)}（北京时间），只能注册一个老师账号。</p>
      <button class="btn primary" id="tReg" type="button">注册老师账号</button>
      <p class="tiny muted">已经有老师账号了？<button class="link small" type="button" id="tLogin">直接登录</button></p></div>`);
    const open = () => openLogin('用这条链接注册的是老师账号。注册时要验证邮箱，忘记密码时用它找回。', 'reg', { teacher: token });
    document.getElementById('tReg').onclick = open;
    document.getElementById('tLogin').onclick = () => openLogin('');
    open();
  }
  // #/teach (and #/ for a teacher account): its classes, and a new one.
  async function teachHome() {
    if (!S.user) {
      view.innerHTML = `<div class="stack cls-page">${teachIntro('我的班级')}<div class="card flat stack-s"><p>登录老师账号后，这里是你的班级。</p><button class="btn primary" id="lg" type="button">登录</button></div>${teachWhat()}</div>`;
      document.getElementById('lg').onclick = () => openLogin(); return;
    }
    const k = await api('/api/next/class'); S.myClass = k;
    if (!S.user.teacher && !k.teaching.length) { location.replace('#/'); return; }  // a 学生账号 has no teacher page
    const rows = k.teaching.map(t => `<a class="card flat cls-row" href="#/class/${t.id}"><span class="stack-s"><b>${esc(t.name)}</b><span class="small muted">邀请码 ${esc(t.code)}</span></span>
      <span class="small${t.active && t.ready ? '' : ' muted'}">${!t.active ? '已停用' : t.ready ? '看全班汇总 ›' : `还不到 ${k.min} 人 ›`}</span></a>`).join('');
    view.innerHTML = `<div class="stack cls-page">${teachIntro('我的班级')}${S.user.teacher ? '<span class="small muted">老师账号</span>' : ''}
      ${rows ? `<div class="stack-s">${rows}</div>` : '<div class="card flat"><p>还没有班级。先建一个，拿到邀请码发给学生。</p></div>'}
      ${S.user.teacher ? `<form class="card flat stack-s" id="tNew" novalidate><h2 class="h2">新建班级</h2>
        <label class="field">班级名<input name="name" type="text" maxlength="30" placeholder="比如 大学英语（2）班" autocomplete="off" required><span class="hint">2–30 个字。建好以后可以改名。</span></label>
        <button class="btn primary" type="submit">新建班级</button><p class="err" id="tErr" role="alert"></p></form>` : ''}
      <div class="card flat stack-s">${teachTerms(k.min)}</div>
      <p class="small"><a class="link" href="#/guide/teacher">老师操作说明</a></p>
      <p class="tiny muted">想看看学生用的语流，点下面的「练习」「单词」随便用；老师账号不能加入班级，自己学的也不算进任何班级的数字。</p></div>`;
    const f = document.getElementById('tNew');
    if (f) f.onsubmit = async e => {
      e.preventDefault(); const err = document.getElementById('tErr'); err.textContent = '';
      const name = f.name.value.trim();
      if (name.length < 2 || name.length > 30) return fieldError(f, err, { message: '班级名写 2–30 个字', field: 'name' });
      const b = f.querySelector('[type=submit]'); b.disabled = true;
      try { const r = await api('/api/next/class/create', { name }); S.myClass = r; toast('班级建好了：把邀请码发给学生'); location.hash = `#/class/${r.created}`; }
      catch (x) { fieldError(f, err, { message: x.message, field: 'name' }); b.disabled = false; }
    };
  }

  /* ---------- the teacher's page: #/class/<id> ---------- */
  async function classView(id) {
    if (!S.user) { view.innerHTML = '<div class="empty"><p>登录老师的语流账号后，才能看班级汇总。</p><button class="btn primary" id="lg">登录</button></div>'; document.getElementById('lg').onclick = () => openLogin(); return; }
    const k = await api(`/api/next/class/teach?id=${encodeURIComponent(id)}`);
    const weeks = k.weeks || [], top = Math.max(1, k.members || 1);
    const body = !k.active ? '<div class="card flat"><p>这个班级已经停用：不能再加入，这里也不再显示汇总。需要重新启用，请联系语流。</p></div>'
      : !k.ready ? `<div class="card flat stack-s"><b>班里还不到 ${k.min} 人</b><p class="small muted">满 ${k.min} 人后，这里显示全班的汇总：最近 7 天几人在学、全班最常错的 5 个语法点。为了保护每个学生，人少的时候不出任何数字。</p></div>`
      : `<div class="card flat stack-s cls-now"><div class="cls-big"><b>${k.active_7d}</b><span>/ ${k.members} 人</span></div><span class="small muted">近 7 天在学</span>
          <div class="cls-weeks" role="img" aria-label="近 4 周每周在学人数：${weeks.map(w => w.studied).join('、')}">${weeks.map((w, i) => `<div class="w${i === weeks.length - 1 ? ' now' : ''}"><div class="col"><i data-h="${Math.max(3, Math.round(w.studied / top * 100))}"></i></div><b>${w.studied}</b><span>${esc(w.label)}</span></div>`).join('')}</div>
          <p class="tiny muted">${esc(k.rule)}</p></div>
        <div class="card flat stack-s"><h2 class="h2">近 7 天全班最常错的 5 个语法点</h2>
          ${k.points.length ? `<ol class="cls-points">${k.points.map(p => `<li><a href="#/graph/${encodeURIComponent(p.node)}" data-tap="class-point"><span class="t">${esc(p.title)}</span><span class="small muted">${p.learners} 人错过</span><span class="go small">讲解 ›</span></a></li>`).join('')}</ol>
            <p class="tiny muted">做语法题、考试练习答错的，和 AI 批改写作时因为这个语法点改过的，都算。点进去是这个语法点的讲解和练习，上课可以直接用。</p>`
            : '<p class="small muted">近 7 天全班还没有做错的语法点（也可能还没人做语法题）。</p>'}</div>`;
    view.innerHTML = `<div class="stack cls-page"><div><a class="kicker link" href="#/teach">‹ 我的班级</a><h1 class="h1">${esc(k.name)}</h1><span class="small muted">${k.ready ? `${k.members} 人 · ` : ''}全班汇总，只有数字 · <button class="link small" id="clsRename" type="button">改名</button></span></div>
      ${body}
      <div class="card flat stack-s"><h2 class="h2">邀请学生</h2>
        <div class="cls-code" aria-label="邀请码">${esc(k.code)}</div>
        <p class="small muted">学生在「我的 → 设置 → 班级」输入邀请码，或打开下面的链接加入。加入前会先告诉他们你能看到什么、看不到什么。</p>
        <div class="row"><button class="btn" id="clsCopy" type="button">复制链接</button><button class="btn ghost" id="clsQr" type="button">二维码</button></div>
        <canvas id="clsQrC" width="240" height="240" hidden aria-label="加入班级的二维码"></canvas></div>
      <p class="tiny muted">这里只有全班的数字，看不到任何学生的名字、作业和记录；退出班级的学生马上不再计入。</p></div>`;
    view.querySelectorAll('.cls-weeks i').forEach(i => { i.style.height = i.dataset.h + '%'; });  // CSP: no inline style attributes
    document.getElementById('clsRename').onclick = async () => {
      const name = (prompt('新的班级名（2–30 个字）', k.name) || '').trim();
      if (!name || name === k.name) return;
      try { await api('/api/next/class/rename', { id: k.id, name }); toast('已改名'); route(true); } catch (x) { toast(x.message); }
    };
    const link = classLink(k.code);
    document.getElementById('clsCopy').onclick = () => (navigator.clipboard ? navigator.clipboard.writeText(link) : Promise.reject()).then(() => toast('链接已复制，发给学生就行'), () => prompt('复制这个链接发给学生', link));
    document.getElementById('clsQr').onclick = e => {
      const cv = document.getElementById('clsQrC'); cv.hidden = !cv.hidden; e.target.textContent = cv.hidden ? '二维码' : '收起二维码';
      if (!cv.hidden) QR.draw(cv.getContext('2d'), link, 0, 0, 240);
    };
  }
  /* ---------- 问题反馈: what happened, the page it happened on, and up to three screenshots ---------- */
  // Anyone can send one, signed in or not (the server limits guests by a hashed address). The report carries the page
  // the learner came from, the site's version, the phone and browser, and the last few script errors: a page that
  // broke often says why in the console (ERRS, kept by 84-field.js). Read and closed in the operator console; nothing is
  // sent back.
  const FB_KINDS = [['display', '页面显示不对'], ['broken', '功能用不了'], ['content', '内容有错'], ['idea', '建议'], ['other', '其他']];
  const ASSET = (((document.querySelector('script[src*="next.js"]') || {}).src || '').split('v=')[1] || '').slice(0, 20);

  // A phone screenshot is large (1290 × 2796 on an iPhone): drawn at most 1600 px on its long side and sent as JPEG
  // under 650 KB, so three fit in one request. Read as a data: URL (the page's CSP allows data: images, not blob:).
  function shrinkShot(file) {
    return new Promise((ok, no) => {
      if (file.type && !/^image\//.test(file.type)) return no(new Error('只能添加图片'));
      const fr = new FileReader();
      fr.onerror = () => no(new Error('读不出这张图片，请换一张'));
      fr.onload = () => {
        const img = new Image();
        img.onerror = () => no(new Error('这个文件打不开，请换一张截图'));
        img.onload = () => {
          const k = Math.min(1, 1600 / Math.max(img.naturalWidth, img.naturalHeight, 1));
          const cv = document.createElement('canvas');
          cv.width = Math.max(1, Math.round(img.naturalWidth * k)); cv.height = Math.max(1, Math.round(img.naturalHeight * k));
          const g = cv.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, cv.width, cv.height); g.drawImage(img, 0, 0, cv.width, cv.height);
          for (const q of [0.82, 0.7, 0.55, 0.4]) { const d = cv.toDataURL('image/jpeg', q); if (d.length * 0.75 <= 650000) return ok(d); }
          no(new Error('这张图太大了，请裁小一点'));
        };
        img.src = fr.result;
      };
      fr.readAsDataURL(file);
    });
  }

  async function feedbackView() {
    const from = S.prevRoute && !/^feedback/.test(S.prevRoute) ? '#/' + S.prevRoute : '';
    let kind = 'display';
    const shots = [];
    view.innerHTML = `<div class="stack"><div><h1 class="h1">问题反馈</h1><span class="muted small">页面显示不对、功能用不了、内容有错，或者有建议，都可以告诉我们。</span></div>
      <form class="card stack fb" id="fbForm" novalidate>
        <div class="chips" role="radiogroup" aria-label="反馈类型">${FB_KINDS.map(([k, l]) => `<button type="button" class="chip" role="radio" data-k="${k}" aria-checked="${k === kind}">${l}</button>`).join('')}</div>
        <label class="stack-s" for="fbText"><b>发生了什么</b><span class="tiny muted">在哪个页面、点了什么、看到了什么。</span></label>
        <textarea id="fbText" data-draft="feedback" rows="5" maxlength="1000" placeholder="比如：在「单词」页往下滑，底部的按钮跑到了屏幕中间。"></textarea>
        <div class="row between"><span class="tiny err" id="fbErr" role="alert"></span><span class="tiny muted" id="fbCount">0 / 1000</span></div>
        <div class="stack-s"><b>截图 <span class="tiny muted">可选，最多 3 张</span></b>
          <div class="fb-shots" id="fbShots"></div>
          <div><label class="btn" id="fbAdd">添加截图<input type="file" id="fbFile" accept="image/*" multiple class="sr-only"></label></div></div>
        ${S.user ? '' : `<label class="stack-s" for="fbContact"><b>联系方式 <span class="tiny muted">可不填</span></b></label>
        <input type="text" id="fbContact" maxlength="100" autocomplete="email" placeholder="邮箱或微信，方便我们问你细节">`}
        <label class="sr-only" aria-hidden="true">网址<input name="website" id="fbHp" tabindex="-1" autocomplete="off"></label>
        <p class="tiny muted">会一起发送：${from ? '你刚才在的页面、' : ''}网站版本、手机和浏览器型号${S.user ? '、你的账号' : ''}。截图只有管理员能看。</p>
        <button class="btn primary block" id="fbSend" type="submit">提交</button>
      </form></div>`;
    const form = document.getElementById('fbForm'), ta = document.getElementById('fbText'), box = document.getElementById('fbShots');
    const file = document.getElementById('fbFile'), add = document.getElementById('fbAdd'), send = document.getElementById('fbSend');
    const say = m => { document.getElementById('fbErr').textContent = m || ''; };
    form.querySelectorAll('[data-k]').forEach(b => b.onclick = () => {
      kind = b.dataset.k; form.querySelectorAll('[data-k]').forEach(x => x.setAttribute('aria-checked', String(x === b)));
    });
    ta.oninput = () => { document.getElementById('fbCount').textContent = `${ta.value.length} / 1000`; say(''); };
    const drawShots = () => {
      box.innerHTML = shots.map((d, k) => `<div class="fb-shot"><img src="${d}" alt="截图 ${k + 1}"><button type="button" data-rm="${k}" aria-label="去掉截图 ${k + 1}">×</button></div>`).join('');
      box.querySelectorAll('[data-rm]').forEach(b => b.onclick = () => { shots.splice(Number(b.dataset.rm), 1); drawShots(); });
      add.hidden = shots.length >= 3;
    };
    file.onchange = async () => {
      const list = [...file.files].slice(0, 3 - shots.length); file.value = '';
      add.classList.add('busy');
      for (const f of list) { try { shots.push(await shrinkShot(f)); say(''); } catch (x) { say(x.message); } }
      add.classList.remove('busy'); drawShots();
    };
    form.onsubmit = async e => {
      e.preventDefault();
      const text = ta.value.trim();
      if (text.length < 4) { say('请写几句发生了什么（至少 4 个字）'); ta.focus(); return; }
      send.disabled = true; send.textContent = '正在提交…';
      const c = document.getElementById('fbContact');
      try {
        await api('/api/feedback', { kind, text, contact: c ? c.value.trim() : '', page: from, images: shots, website: document.getElementById('fbHp').value,
          device: { ua: navigator.userAgent, w: innerWidth, h: innerHeight, dpr: devicePixelRatio || 1, lang: navigator.language || '', asset: ASSET,
            theme: matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light', standalone: STANDALONE(), wechat: IN_WECHAT, errors: ERRS.slice() } });
        draftDone('feedback');
        view.innerHTML = `<div class="card done-card enter stack fb-done"><div class="big" aria-hidden="true">✓</div><h1 class="h1">已收到，谢谢！</h1>
          <p class="muted">${shots.length ? `连同 ${shots.length} 张截图一起收到了。` : ''}我们会尽快看，修好后会在新版本里更新。</p>
          <div class="row center"><a class="btn primary" href="${esc(from || '#/me')}">${from ? '回到刚才的页面' : '返回「我的」'}</a><button class="btn ghost" id="fbMore" type="button">再提一个</button></div></div>`;
        document.getElementById('fbMore').onclick = () => feedbackView();
      } catch (x) { say(x.message); send.disabled = false; send.textContent = '提交'; }
    };
  }
  /* ---------- 更新记录 (#/updates, 我的 → 帮助): what each 语流 release changed, in plain words (updates_service.py) ---------- */
  // One card per release, newest first, every change a learner can notice: 用法变了 first and marked (a button moved, a
  // consent to give), then 新功能 / 改进 / 修好的问题; a sentence with a page to see gets 「去看看」. On the 内测版 a 「内测中」
  // card first: what is on this site and not on 语流 yet. The data is corpus_data/updates.json, written with each release.
  const UPD_GROUPS = [['changed', '用法变了'], ['new', '新功能'], ['better', '改进'], ['fixed', '修好的问题']];
  function updItem(i) {
    return `<li>${esc(i.text)}${i.link ? ` <a class="link upd-go" href="${esc(i.link)}" data-tap="updates-go">去看看</a>` : ''}</li>`;
  }
  function updGroups(e) {
    return UPD_GROUPS.filter(([k]) => e[k] && e[k].length)
      .map(([k, l]) => `<div class="upd-g${k === 'changed' ? ' upd-changed' : ''}"><h3 class="upd-h">${k === 'changed' ? '⚠︎ ' : ''}${l}</h3><ul class="upd-l">${e[k].map(updItem).join('')}</ul></div>`).join('')
      + (e.note ? `<p class="small muted upd-note">${esc(e.note)}</p>` : '');
  }
  async function updatesView() {
    const d = await api('/api/next/updates');
    if (d.released[0]) save('flow-update-seen', d.released[0].id);  // read here: 今日 no longer offers the card for it
    view.innerHTML = `<div class="stack upd-page"><div><h1 class="h1">更新记录</h1><span class="muted small">语流每一次更新改了什么，新的在上面。标着「用法变了」的，是要换个方式用的地方。</span></div>
      ${d.beta ? `<section class="card stack-s upd upd-beta" aria-label="内测中"><div class="row between"><h2 class="h2">内测中</h2><span class="pill">只在内测版</span></div>
        <span class="small muted">已经能在这里试，还没上正式版。</span>${updGroups(d.beta)}</section>` : ''}
      ${d.released.length ? d.released.map(e => `<section class="card stack-s upd" aria-label="${esc(e.label)}"><h2 class="h2">${esc(e.label)}</h2>${updGroups(e)}</section>`).join('')
        : '<p class="muted">还没有更新记录。</p>'}
      <p class="tiny muted">发现哪里不对，可以在<a class="link" href="#/feedback">问题反馈</a>里告诉我们。</p></div>`;
  }
  // 「语流更新了」 at the very top of 今日, in the place of the operators' 公告 (10-welcome-today.js): a 公告 goes first; with
  // none, the first time a learner who has studied before opens a new release, its two or three highlights and
  // 「查看全部变化」. Either button, or opening 更新记录, marks that release seen on this phone (flow-update-seen), so one
  // release shows once. A phone new to 语流 just notes it: nothing has changed for it.
  function updateCardDue(h) {
    const u = h.update; if (!u || !u.highlights || !u.highlights.length) return false;
    if (uiLang() === 'en') return false;  // 全英文界面: what changed is written in Chinese only, so the card waits (更新记录 still has it)
    const seen = load('flow-update-seen');
    if (seen === u.id) return false;
    const st = h.stats, studied = !!st && (st.materials_done > 0 || st.cards > 0 || (st.week || []).some(d => d.active));
    if (seen == null && !studied) { save('flow-update-seen', u.id); return false; }
    return true;
  }
  function updateCardHTML(h) {
    if (!updateCardDue(h)) return '';
    const u = h.update;
    return `<div class="card sunk section notice announce upd-card stack-s" id="updCard" role="status"><b>语流更新了<span class="tiny muted"> · ${esc(u.label)}</span></b>
      <ul class="upd-l small">${u.highlights.map(s => `<li>${esc(s)}</li>`).join('')}</ul>
      <div class="row"><a class="btn small primary" href="#/updates" id="updAll" data-tap="today-updates">查看全部变化</a><button class="btn small ghost" id="updOk" type="button">知道了</button></div></div>`;
  }
  function bindUpdateCard(h) {
    const box = document.getElementById('updCard'); if (!box) return;
    const seen = () => save('flow-update-seen', h.update.id);
    document.getElementById('updOk').onclick = () => { seen(); box.remove(); };
    document.getElementById('updAll').addEventListener('click', seen);
  }
  /* ---------- what this browser tells the site about the site itself (field_service.py) ---------- */
  // Page errors (a script that broke, a promise nobody caught, a picture or sound that did not load, a request that
  // failed, a sound the browser would not play) and, once per visit, how long until the first page was on screen and
  // where the time went. No account and no address go with them; each problem is sent once per visit, 20 at most.
  // The last few errors also go with a 问题反馈 report (ERRS).
  // t0: when this script began to run (after it was downloaded and compiled); hidden: the page was opened out of sight
  // (a tab in the background, a link WeChat loaded ahead): its time on screen is not a wait, so the console leaves it
  // out. page: which page this visit opened on (a link to a material waits for that material, not for 今日).
  const FIELD = { q: [], seen: new Set(), sent: 0, firstView: null, openSent: false, t: 0, t0: performance.now(),
    hidden: document.visibilityState === 'hidden', page: (s => (!s ? 'today' : s === 'm' ? 'material' : 'other'))((location.hash.split('/')[1] || '')) };
  const ERRS = [];
  function beacon(url, data) {
    const body = JSON.stringify(data);
    try { if (navigator.sendBeacon && navigator.sendBeacon(url, body)) return; } catch (e) { /* fall back to fetch */ }
    try { fetch(url, { method: 'POST', body, keepalive: true, credentials: 'same-origin', headers: { 'Content-Type': 'application/json' } }).catch(() => {}); } catch (e) { /* not counted */ }
  }
  function noteIssue(kind, message, source) {
    try {
      const page = location.hash.split('?')[0] || '#/', msg = String(message || '').slice(0, 200), src = String(source || '').slice(0, 120);
      if (kind === 'js' || kind === 'promise') { ERRS.push((msg + (src ? ' @ ' + src : '')).slice(0, 200)); if (ERRS.length > 5) ERRS.shift(); }
      const key = [kind, page, msg, src].join('|');
      if (!msg || FIELD.seen.has(key) || FIELD.sent + FIELD.q.length >= 20) return;
      FIELD.seen.add(key); FIELD.q.push({ kind, page, message: msg, source: src });
      clearTimeout(FIELD.t); FIELD.t = setTimeout(flushIssues, 5000);
    } catch (e) { /* the report must never break the page */ }
  }
  function flushIssues() {
    if (!FIELD.q.length) return;
    const items = FIELD.q.splice(0); FIELD.sent += items.length;
    beacon('/api/next/issues', { items, asset: ASSET, standalone: STANDALONE() });
  }
  // Script errors, and pictures, sounds and scripts that did not load: those do not bubble, hence the capture phase.
  addEventListener('error', e => {
    const t = e && e.target;
    if (t && t !== window && t.tagName) {
      const src = String(t.currentSrc || t.src || t.href || '').replace(location.origin, '').split('?')[0];
      if (src && !src.startsWith('blob:') && !src.startsWith('data:')) noteIssue('resource', `${t.tagName.toLowerCase()} 没加载出来：${src}`);
      return;
    }
    if (e && e.message) noteIssue('js', e.message, `${String(e.filename || '').split('/').pop().split('?')[0]}:${e.lineno || 0}`);
  }, true);
  addEventListener('unhandledrejection', e => { const r = e && e.reason; if (!(r && r.network)) noteIssue('promise', (r && r.message) || String(r)); });

  // Opening time: navigation timing (when the browser has it) and the moment the first page was drawn.
  function navTiming() {
    const n = performance.getEntriesByType && performance.getEntriesByType('navigation')[0];
    if (n) return n;
    const t = performance.timing; if (!t || !t.navigationStart) return null;  // older in-app browsers
    const o = {}; ['fetchStart', 'domainLookupStart', 'domainLookupEnd', 'connectStart', 'connectEnd', 'secureConnectionStart', 'requestStart', 'responseStart', 'responseEnd']
      .forEach(k => { o[k] = t[k] ? t[k] - t.navigationStart : 0; });
    return o;
  }
  function sendOpenTime() {
    if (FIELD.openSent) return; FIELD.openSent = true;
    try {
      const n = navTiming(); if (!n) return;
      const res = (performance.getEntriesByType && performance.getEntriesByType('resource')) || [];
      const first = re => res.filter(r => re.test(r.name)).sort((a, b) => a.startTime - b.startTime)[0];
      const home = first(/\/api\/next\/home/), js = first(/\/next\.js/), c = navigator.connection || {};
      const ms = x => (x == null || !isFinite(x) || x < 0 ? null : Math.round(x)), fv = FIELD.firstView;
      beacon('/api/next/opentime', {
        domain: location.host, first_view: ms(fv), waited: ms(performance.now()),
        startup: ms(n.fetchStart), dns: ms(n.domainLookupEnd - n.domainLookupStart), connect: ms(n.connectEnd - n.connectStart),
        tls: n.secureConnectionStart > 0 ? ms(n.connectEnd - n.secureConnectionStart) : null,
        ttfb: ms(n.responseStart - n.requestStart), html: ms(n.responseEnd - n.responseStart),
        scripts: js ? ms(js.responseEnd - n.responseEnd) : null, boot: ms(FIELD.t0 - (js ? js.responseEnd : n.responseEnd)),
        home_api: home ? ms(home.duration) : null,
        render: fv != null && home ? ms(fv - home.responseEnd) : null,
        repeat: !!(navigator.serviceWorker && navigator.serviceWorker.controller), snap: DATA.fromSnap, standalone: STANDALONE(),
        hidden: FIELD.hidden, page: FIELD.page,
        net: c.effectiveType || '', tz: (Intl.DateTimeFormat().resolvedOptions().timeZone || '').slice(0, 40) });
    } catch (e) { /* not counted */ }
  }
  function firstViewDrawn() {
    if (FIELD.firstView != null) return;
    FIELD.firstView = performance.now();
    setTimeout(sendOpenTime, 1500);
  }
  // Leaving (or switching away): what is queued goes now; a visit that leaves before anything showed counts too.
  addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') { flushIssues(); sendOpenTime(); } });
  addEventListener('pagehide', () => { flushIssues(); sendOpenTime(); });
  /* ---------- 分享卡片: a picture of what was learned, to keep or to send ---------- */
  // A learned expression (with the sentence it came in) or the week, drawn on a canvas as a 1080 px picture with a QR code
  // back to the site. In WeChat a long press saves or sends it; other phones get the system's share sheet; computers a
  // download. Nothing leaves the phone until the learner sends it.
  const SHARE_URL = 'https://flowlang.cn/?f=card';
  const shareFont = (s, w, serif) => `${w || 500} ${s}px ${serif ? "'Flow Serif', Georgia, 'Songti SC', serif" : "-apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif"}`;
  // Lines no wider than max: English breaks between words, Chinese between characters.
  function wrapLines(g, text, max) {
    const parts = String(text || '').match(/[　-〿㐀-鿿＀-￯]|[^\s　-〿㐀-鿿＀-￯]+\s*|\s+/g) || [];
    const lines = []; let line = '';
    parts.forEach(p => { if (line && g.measureText(line + p).width > max) { lines.push(line.trimEnd()); line = p.trimStart(); } else line += p; });
    if (line.trim()) lines.push(line.trimEnd());
    return lines;
  }
  function brandFoot(g, W, H, note) {
    const green = '#1f9d55';
    g.fillStyle = green; g.beginPath(); g.roundRect ? g.roundRect(80, H - 260, 84, 84, 22) : g.rect(80, H - 260, 84, 84); g.fill();
    g.strokeStyle = '#fff'; g.lineWidth = 8; g.lineCap = 'round';
    [[101, 37, 79], [117, 21, 95], [133, 29, 87], [149, 37, 71]].forEach(([x, a, b]) => { g.beginPath(); g.moveTo(x, H - 260 + a); g.lineTo(x, H - 260 + b); g.stroke(); });
    g.fillStyle = '#1b1d1a'; g.font = shareFont(40, 700); g.fillText('语流 Flow', 184, H - 222);
    g.fillStyle = '#6f7369'; g.font = shareFont(28, 400); g.fillText('每天一篇，学了就能用', 184, H - 180);
    if (note) { g.fillStyle = green; g.font = shareFont(28, 600); g.fillText(note, 80, H - 110); }
    QR.draw(g, SHARE_URL, W - 300, H - 300, 220, '#13261b', '#ffffff');
    g.fillStyle = '#6f7369'; g.font = shareFont(24, 400); g.textAlign = 'center'; g.fillText('扫码一起学', W - 190, H - 52); g.textAlign = 'left';
  }
  // The week, said only when there is something to say: the weeks that reached the goal (counted up, never a run that
  // breaks), or the days of this one. Shared right after studying (studiedNow), today counts even before 今日 is
  // fetched again. The week's card has its days already (weeksOnly; its seven days are not the calendar week either).
  function habitNote(studiedNow, weeksOnly) {
    const hb = S.user && S.home && S.home.stats && S.home.stats.habit;
    if (!hb) return '';
    const t = (hb.days || []).find(d => d.today), done = hb.done + (studiedNow && t && !t.active ? 1 : 0);
    const weeks = (hb.weeks || 0) + (done >= hb.goal && !hb.met ? 1 : 0);
    return weeks > 1 ? `一共有 ${weeks} 周达成了学习目标` : done > 0 && !weeksOnly ? `这周学了 ${done} 天` : '';
  }
  // A learned expression: big, its meaning, the sentence it came in, and where from.
  function sentenceCard(x, from, title) {
    const W = 1080, H = 1440, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    const g = cv.getContext('2d'), green = '#1f9d55', ink = '#1b1d1a', muted = '#6f7369';
    const bg = g.createLinearGradient(0, 0, 0, H); bg.addColorStop(0, '#f6fbf7'); bg.addColorStop(1, '#e6f2ea'); g.fillStyle = bg; g.fillRect(0, 0, W, H);
    // measured first (each block with its own font), then drawn as one block centred above the footer
    let size = 84, big;
    do { g.font = shareFont(size, 700, true); big = wrapLines(g, x.text, W - 160).slice(0, 4); size -= 6; } while (big.length > 3 && size > 48);
    size += 6;
    g.font = shareFont(38, 500); const mean = x.meaning ? wrapLines(g, x.meaning, W - 160).slice(0, 3) : [];
    g.font = shareFont(34, 400, true); const quote = from ? wrapLines(g, from, W - 200).slice(0, 4) : [];
    const height = 60 + big.length * size * 1.25 + (mean.length ? 20 + mean.length * 56 : 0) + (quote.length ? 56 + quote.length * 50 : 0) + (title ? 70 : 0);
    let y = Math.max(150, Math.round((H - 330 - height) / 2) + 40);
    g.fillStyle = green; g.font = shareFont(32, 700); g.fillText('今天学会的一句', 80, y); y += 60 + size;
    g.fillStyle = ink; g.font = shareFont(size, 700, true); big.forEach((l, k) => { if (k) y += size * 1.25; g.fillText(l, 80, y); });
    if (mean.length) { y += 76; g.fillStyle = '#3c4038'; g.font = shareFont(38, 500); mean.forEach((l, k) => { if (k) y += 56; g.fillText(l, 80, y); }); }
    if (quote.length) {
      y += 90; g.fillStyle = green; g.fillRect(80, y - 36, 6, (quote.length - 1) * 50 + 48);
      g.fillStyle = '#3c4038'; g.font = shareFont(34, 400, true); quote.forEach((l, k) => { if (k) y += 50; g.fillText(l, 110, y); });
    }
    if (title) { y += 70; g.fillStyle = muted; g.font = shareFont(28, 400); g.fillText(`出自《${title}》`, 80, y); }
    brandFoot(g, W, H, habitNote(true));
    return cv.toDataURL('image/png');
  }
  // The preview, and the ways out: a long press in WeChat, the share sheet where there is one, else a download.
  function shareSheet(pictures, title) {
    let k = 0;
    const filesOK = !IN_WECHAT && !!(navigator.canShare && window.File);
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">${esc(title)}</h2>
      ${pictures.length > 1 ? `<div class="chips share-pick" role="radiogroup" aria-label="选一句">${pictures.map((p, i) => `<button class="chip" type="button" role="radio" data-pic="${i}" aria-checked="${i === 0}">${esc(p.label)}</button>`).join('')}</div>` : ''}
      <img class="share-img" id="shareImg" alt="分享图片预览">
      <p class="small muted">${IN_WECHAT ? '长按图片，选「保存图片」或「发送给朋友」。' : '长按图片可以保存；也可以用下面的按钮。'}</p>
      <div class="row">${filesOK ? '<button class="btn primary" id="shareGo" type="button">分享…</button>' : ''}${IN_WECHAT ? '' : '<a class="btn" id="shareSave" download="语流-学习卡片.png">保存图片</a>'}<button class="btn ghost" data-close type="button">关闭</button></div></div>`, card => {
      const show = () => {
        const url = pictures[k].url || (pictures[k].url = pictures[k].draw());
        card.querySelector('#shareImg').src = url;
        const a = card.querySelector('#shareSave'); if (a) a.href = url;
      };
      card.querySelectorAll('[data-pic]').forEach(b => b.onclick = () => { k = Number(b.dataset.pic); card.querySelectorAll('[data-pic]').forEach(x => x.setAttribute('aria-checked', String(x === b))); show(); });
      const go = card.querySelector('#shareGo');
      if (go) go.onclick = async () => {
        try {
          const bin = atob(pictures[k].url.split(',')[1]), u = new Uint8Array(bin.length);  // a data: URL, read without fetch (the page's CSP)
          for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
          const file = new File([u], '语流-学习卡片.png', { type: 'image/png' });
          if (navigator.canShare({ files: [file] })) await navigator.share({ files: [file], title: '语流 Flow' }); else toast('这个浏览器不能直接分享，长按图片保存吧');
        } catch (e) { if (e && e.name !== 'AbortError') toast('没有分享出去，长按图片保存吧'); }
      };
      show();
    });
  }
  // From a material: up to three of its expressions, each with the sentence of the text it is in.
  function shareFromMaterial(m) {
    const xs = (m.expressions || []).slice(0, 3); if (!xs.length) return toast('这篇没有可以分享的表达');
    const ls = m.sentences || [];
    shareSheet(xs.map(x => ({ label: x.text, draw: () => sentenceCard(x, ls.find(s => s.toLowerCase().includes(x.text.toLowerCase())) || '', m.title) })), '分享今天学会的一句');
  }
  /* ---------- boot ---------- */
  // 从提醒邮件点进来 (r29): a mail's link carries ?from=remind&k=review|once|weekly. Counted per day and kind only
  // (/api/next/tap: no account, D2), then taken off the address so a link passed on or bookmarked does not carry it.
  function remindOpen() {
    const q = new URLSearchParams(location.search);
    if (q.get('from') !== 'remind') return;
    const keys = { review: 'remind-review', once: 'remind-once', weekly: 'remind-weekly' };  // flow_admin.TAP_LABEL
    const key = Object.prototype.hasOwnProperty.call(keys, q.get('k')) ? keys[q.get('k')] : 'remind-other';
    try { navigator.sendBeacon('/api/next/tap', JSON.stringify({ k: key })); } catch (x) { /* not counted */ }
    q.delete('from'); q.delete('k');
    const rest = q.toString();
    try { history.replaceState(null, '', location.pathname + (rest ? '?' + rest : '') + location.hash); } catch (x) { /* the address stays */ }
  }
  (async function boot() {
    remindOpen();
    wechatBar();
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
    // The copy of the last 今日 kept on the phone (05-data.js): the page is drawn from it at once, then from the
    // server's answer, quietly, if anything changed. Offline, the copy stays on screen. The first visit waits.
    const snap = snapGet(), drawn = () => { SPLASH.done(); firstViewDrawn(); prefetchTabs(); keepTodayOffline(); };
    if (snap && snap.home && snap.home.session) {
      S.home = snap.home; S.user = snap.home.session.user || null; S.csrf = ''; DATA.fromSnap = true; S.homeFresh = true; setDueBadge();
      const drawnFor = location.hash;
      route().then(drawn);
      try { if (await refreshHome()) redrawQuietly(drawnFor); } catch (e) { DATA.ok(); }
      TIPS.load();  // 使用提示 this account put away, kept on the phone before a page needs them (08-tips.js)
    } else {
      try { await refreshHome(); S.homeFresh = true; } catch (e) { DATA.ok(); /* offline: route() asks again and offers a retry */ }
      TIPS.load();
      route().then(drawn);  // the opening time ends when the first page is drawn
    }
    OUTBOX.flush();
  })();
})();
