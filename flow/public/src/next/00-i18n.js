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
