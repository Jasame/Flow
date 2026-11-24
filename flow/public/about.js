/* 认识语流 (/about): the motion and the small demos on the introduction page. No libraries, no build step.
   Loaded in <head> so html.js is set before the first paint (about.css hides the parts that come in as you scroll only
   then); everything else waits for the page. Motion uses transform and opacity; with prefers-reduced-motion every part
   is shown at once, nothing moves by itself, and the demos still work when tapped. */
'use strict';
document.documentElement.classList.add('js');
(function () {
  const RM = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
  const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const IO = window.IntersectionObserver;

  /* ---------- parts come in as they are scrolled to ---------- */
  function reveal() {
    $$('[data-d]').forEach(el => el.style.setProperty('--d', el.dataset.d));
    const els = $$('.rv, .display, .stage');
    if (!IO || RM) { els.forEach(el => el.classList.add('in')); counters(document); return; }
    const io = new IO(entries => entries.forEach(e => {
      if (!e.isIntersecting) return;
      e.target.classList.add('in'); io.unobserve(e.target);
      counters(e.target);
      e.target.dispatchEvent(new CustomEvent('in'));
    }), { rootMargin: '0px 0px -8% 0px', threshold: 0.12 });
    els.forEach(el => io.observe(el));
  }
  // The big numbers count up once, the first time they are seen.
  function counters(root) {
    $$('[data-count]', root).forEach(b => {
      if (b.dataset.done) return; b.dataset.done = '1';
      const to = Number(b.dataset.count); if (RM) { b.textContent = to; return; }
      const t0 = performance.now(), dur = 1300;
      const tick = now => { const k = clamp((now - t0) / dur, 0, 1); b.textContent = Math.round(to * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(tick); };
      b.textContent = '0'; requestAnimationFrame(tick);
    });
  }

  /* ---------- infinite motion stops when its part is off screen (battery, smoothness) ---------- */
  function pauseOffscreen() {
    if (!IO) return;
    const io = new IO(es => es.forEach(e => { e.target.classList.toggle('paused', !e.isIntersecting); e.target.classList.toggle('in-view', e.isIntersecting); }), { rootMargin: '80px 0px' });
    $$('.hero, .ai, .final, .memory').forEach(s => io.observe(s));
  }

  /* ---------- on scroll: reading line, the top bar, parallax and the memory curve ---------- */
  let curveDraw = null;
  function scrolling() {
    const line = $('#readline'), top = $('#top'), par = $$('.parallax');
    let queued = false;
    const frame = () => {
      queued = false;
      const y = window.scrollY, vh = window.innerHeight, max = document.documentElement.scrollHeight - vh;
      if (line) line.style.transform = `scaleX(${max > 0 ? clamp(y / max, 0, 1) : 0})`;
      if (top) top.classList.toggle('scrolled', y > 8);
      if (!RM) par.forEach(el => {
        const r = el.getBoundingClientRect(); if (r.bottom < -200 || r.top > vh + 200) return;
        const d = (r.top + r.height / 2 - vh / 2) * Number(el.dataset.speed || 0);
        el.style.transform = `translate3d(0,${d.toFixed(1)}px,0)`;
      });
      if (curveDraw) curveDraw(vh);
    };
    const ask = () => { if (!queued) { queued = true; requestAnimationFrame(frame); } };
    window.addEventListener('scroll', ask, { passive: true });
    window.addEventListener('resize', ask);
    frame();
  }

  /* ---------- the four steps: the phone beside them shows the step being read (wide screens) ---------- */
  function story() {
    const steps = $$('.step'), layers = $$('.layer'), tabs = $$('.stage-tabs span'), ind = $('.stage-ind');
    if (!steps.length) return;
    const show = i => {
      steps.forEach((s, j) => s.classList.toggle('on', j === i));
      layers.forEach(l => l.classList.toggle('on', Number(l.dataset.i) === i));
      tabs.forEach(t => t.classList.toggle('on', Number(t.dataset.i) === i));
      if (ind) ind.style.setProperty('--i', i);
    };
    show(0);
    if (!IO) return;
    const io = new IO(es => es.forEach(e => { if (e.isIntersecting) show(Number(e.target.dataset.step)); }), { rootMargin: '-45% 0px -45% 0px' });
    steps.forEach(s => io.observe(s));
  }

  /* ---------- tap a word: the real dictionary entry (语流's own dictionary, copied for this page) ---------- */
  const TAG = { zk: '中考', gk: '高考', cet4: '四级', cet6: '六级', ky: '考研', ielts: '雅思', toefl: '托福', gre: 'GRE' };
  const DICT = {"first":{"w":"first","p":"[fɜːst]","m":"adv. 首先, 第一, 优先；adj. 第一的；num. 第一；n. 开始, 第一","t":["zk","gk"]},"time":{"w":"time","p":"[taɪm]","m":"n. 时间, 时候, 次, 倍, 时代, 时机；v. 计时, 安排……的时间","t":["zk","gk","ielts"]},"switch":{"w":"switch","p":"[swɪtʃ]","m":"n. 开关, 转换, 转变；v. 转换, 切换, 改变, 交换","t":["gk","cet4","cet6","ky","toefl","ielts"]},"pair":{"w":"pair","p":"[peə]","m":"n. 一双, 一对, 一副；v. (使)成对","t":["zk","gk","ielts"]},"noise":{"w":"noise","p":"[nɔɪz]","m":"n. 噪音, 杂音, 响声, 喧闹；vt. 谣传；vi. 喧闹","t":["zk","gk","ielts"]},"cancelling":{"w":"cancel","p":"[ˈkæns(ə)l]","l":"cancel","m":"v. 取消, 删去, 抵消；n. 取消","t":["zk","gk","cet4","cet6","ky","toefl","ielts"]},"headphones":{"w":"headphone","p":"[ˈhedfəʊn]","l":"headphone","m":"n. 戴在头上的收话器, 耳机","t":[]},"train":{"w":"train","p":"[treɪn]","m":"n. 火车, 列车, 一连串；v. 训练, 培训","t":["zk","gk","ielts"]},"effect":{"w":"effect","p":"[ɪˈfekt]","m":"n. 结果, 影响, 效果, 印象；vt. 实行, 引起, 完成","t":["gk","cet4","cet6","ky","toefl","ielts"],"c":[{"words":["affect","effect"],"how":"affect 通常是动词“影响”；effect 通常是名词“影响、效果”（have an effect on）。"}]},"feels":{"w":"feel","p":"[fiːl]","l":"feel","m":"v. 感觉, 觉得, 摸, 认为；n. 感觉, 手感","t":["zk","gk","ielts"]},"almost":{"w":"almost","p":"[ˈɔːlməʊst]","m":"adv. 几乎, 差不多","t":["zk","gk"]},"like":{"w":"like","p":"[laɪk]","m":"prep. 像, 如同, 比如；v. 喜欢, 想要；conj. 好像；n. 爱好（likes）","t":["zk","gk"]},"magic":{"w":"magic","p":"[ˈmædʒɪk]","m":"n. 魔术, 魔法；adj. 魔术的, 有魔力的, 不可思议的","t":["zk","gk","cet4","cet6","ky","toefl","ielts"]},"low":{"w":"low","p":"[ləʊ]","m":"adj. 低的, 矮的, 少的, 低落的, 小声的；adv. 低, 向下；n. 低点, 最低水平","t":["zk","gk","gre"]},"roar":{"w":"roar","p":"[rɔː]","m":"n. 吼, 咆哮, 轰鸣；vi. 吼, 大声说出, 叫喊, 喧闹；vt. 呼喊, 使轰鸣","t":["cet4","cet6","ky","toefl","ielts"]},"engine":{"w":"engine","p":"[ˈendʒɪn]","m":"n. 引擎, 发动机, 机车；vt. 安装发动机于","t":["gk","cet4","cet6","ky","ielts"]},"simply":{"w":"simply","p":"[ˈsɪmplɪ]","m":"adv. 简单地, 只是, 简直, 简朴地, 坦白地","t":["gk"]},"drains":{"w":"drain","p":"[dreɪn]","l":"drain","m":"v. 排水, 流走, 耗尽, 喝光, 使疲惫；n. 下水道, 排水管, 消耗（brain drain 人才外流）","t":["cet4","cet6","ky","toefl","ielts","gre"]},"away":{"w":"away","p":"[əˈweɪ]","m":"adv. 离开, 在远处, 不在, 去掉","t":["zk","gk"]}};
  const SOUND = {};  // lemma -> {us: [sprite, start, end]} from /api/next/lookup (open to guests), for the 🔊 button
  let player = null;
  function lookup() {
    const sent = $('#demoSentence'), card = $('#lookCard'); if (!sent || !card) return;
    const text = sent.textContent;
    // A word and the punctuation after it stay on one line; the words likely above a B1 reader's level are dotted, as
    // on the learning site (the material's own list).
    const HARD = ['cancelling', 'headphones', 'magic', 'roar', 'drains'];
    sent.innerHTML = text.replace(/([A-Za-z]+)([^\sA-Za-z]*)/g, (all, word, tail) => {
      const k = word.toLowerCase();
      const w = DICT[k] ? `<button type="button" class="wd rd${HARD.includes(k) ? ' hard' : ''}" data-k="${k}">${word}</button>` : `<span class="rd">${word}</span>`;
      return `<span class="nw">${w}${esc(tail)}</span>`;
    });
    let auto = null, current = '';
    const open = (btn, byHand) => {
      if (byHand && auto) { clearTimeout(auto.t); auto.stop = true; $$('.rd.lit', sent).forEach(x => x.classList.remove('lit')); }
      const k = btn.dataset.k, e = DICT[k]; if (!e) return;
      $$('.wd.sel', sent).forEach(x => x.classList.remove('sel')); btn.classList.add('sel');
      $('#lcWord').textContent = e.w;
      $('#lcPh').textContent = e.p + (e.l ? ` · 原形 ${e.l}` : '');
      $('#lcMean').innerHTML = e.m.split('；').map(s => { const m = s.match(/^([a-z]+\.)\s*(.*)$/); return `<div>${m ? `<i>${esc(m[1])}</i>${esc(m[2])}` : esc(s)}</div>`; }).join('');
      const tags = e.t.map(t => TAG[t]).filter(Boolean);
      $('#lcTags').innerHTML = tags.length ? tags.map(t => `<span>${t}</span>`).join('') : '';
      const cf = $('#lcConfuse');
      if (e.c && e.c.length) { cf.hidden = false; cf.innerHTML = `<b>容易混：${esc(e.c[0].words.join(' / '))}</b> ${esc(e.c[0].how)}`; } else cf.hidden = true;
      $('#lcSrc').innerHTML = esc(text).replace(new RegExp(`\\b(${btn.textContent})\\b`), '<mark>$1</mark>');
      const first = card.hidden; card.hidden = false;
      if (!first && current !== k && !RM) { card.classList.remove('swap'); void card.offsetWidth; card.classList.add('swap'); }
      current = k; $('#lookHint').hidden = true;
      sound(e.l || e.w);
      if (byHand && window.innerWidth < 900) { const r = card.getBoundingClientRect(); if (r.bottom > window.innerHeight) card.scrollIntoView({ behavior: RM ? 'auto' : 'smooth', block: 'nearest' }); }
    };
    sent.addEventListener('click', ev => { const b = ev.target.closest('.wd'); if (b) open(b, true); });
    $('#lcClose').onclick = () => { card.hidden = true; $$('.wd.sel', sent).forEach(x => x.classList.remove('sel')); current = ''; };
    $('#lcSay').onclick = () => say(current && (DICT[current].l || DICT[current].w));
    // First time the demo is seen: read the sentence along, word by word (伴读), then "tap" drains.
    const demo = () => {
      const drains = $('.wd[data-k="drains"]', sent);
      if (RM) { open(drains, false); return; }
      const words = $$('.rd', sent); auto = { i: 0, stop: false };
      const step = () => {
        if (auto.stop) return;
        if (auto.i > 0) words[auto.i - 1].classList.remove('lit');
        if (auto.i >= words.length) { auto.t = setTimeout(() => { if (!auto.stop && !current) open(drains, false); }, 350); return; }
        words[auto.i++].classList.add('lit'); auto.t = setTimeout(step, 150);
      };
      auto.t = setTimeout(step, 500);
    };
    const host = $('.look-demo');
    if (IO && host) { const io = new IO(es => { if (es[0].isIntersecting) { io.disconnect(); demo(); } }, { threshold: 0.45 }); io.observe(host); } else demo();
  }
  function sound(word) {
    if (!word || SOUND[word] !== undefined || !window.fetch) return;
    SOUND[word] = null;
    fetch('/api/next/lookup?w=' + encodeURIComponent(word), { credentials: 'same-origin' }).then(r => r.ok ? r.json() : null)
      .then(d => { SOUND[word] = (d && d.entry && d.entry.audio) || {}; }).catch(() => { SOUND[word] = {}; });
  }
  // The recorded pronunciation when we have it (one file holds about 100 words: play from start to end), else the
  // browser's voice. play() is called inside the tap, as phones and WeChat require.
  function say(word) {
    if (!word) return;
    const btn = $('#lcSay'), au = SOUND[word] || {}, w = au.us || au.uk, ac = au.us ? 'us' : 'uk';
    const done = () => btn.classList.remove('playing');
    btn.classList.add('playing');
    const voice = () => {
      if (!window.speechSynthesis) { done(); return; }
      try { speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(word); u.lang = 'en-US'; u.rate = .9; u.onend = done; u.onerror = done; speechSynthesis.speak(u); } catch (e) { done(); }
    };
    if (!w) { voice(); return; }
    if (!player) player = new Audio();
    const a = player, from = w[1], to = w[2];
    let fell = false;
    const fall = () => { if (fell) return; fell = true; a.pause(); voice(); };
    a.onerror = fall;
    a.ontimeupdate = () => { if (a.currentTime >= to) { a.pause(); done(); } };
    a.onended = done;
    const src = `/audio/words/${ac}/${w[0]}.mp4`;
    if (a.dataset.src !== src) { a.dataset.src = src; a.src = src; a.muted = true; a.addEventListener('loadedmetadata', () => { try { a.currentTime = from; } catch (e) { /* not seekable yet */ } a.muted = false; }, { once: true }); }
    else { try { a.currentTime = from; } catch (e) { /* ignore */ } }
    a.play().catch(fall);
  }

  /* ---------- the memory curve: drawn as you scroll down to it ---------- */
  function curve() {
    const line = $('#memLine'), area = $('#memArea'), dots = $('#memDots'), forget = $('#memForget'), fig = $('#curve');
    if (!line || !fig) return;
    const X = t => 48 + Math.sqrt(t / 60) * 572, Y = R => 24 + (1 - R) * 1100;  // time on a square-root scale: the early reviews get room
    const R = (t, s) => Math.pow(1 + 19 / 81 * t / s, -0.5);  // FSRS's forgetting curve: 90% when t equals the stability s
    const reviews = [1, 4, 12, 32], stab = [1, 3, 8, 20, 60];
    let d = '', start = 0, k = 0;
    for (let t = 0; t <= 60.001; t += 0.25) {
      while (k < reviews.length && t >= reviews[k]) { d += ` L${X(reviews[k]).toFixed(1)} ${Y(1).toFixed(1)}`; start = reviews[k]; k++; }
      d += `${d ? ' L' : 'M'}${X(t).toFixed(1)} ${Y(R(t - start, stab[k])).toFixed(1)}`;
    }
    line.setAttribute('d', d);
    area.setAttribute('d', d + ` L${X(60)} 256 L${X(0)} 256 Z`);
    let f = ''; for (let t = 0; t <= 60.001; t += 0.5) f += `${f ? ' L' : 'M'}${X(t).toFixed(1)} ${Y(R(t, 1)).toFixed(1)}`;
    if (forget) forget.setAttribute('d', f);
    const gaps = ['1 天后', '再 3 天', '再 8 天', '再 20 天'];
    dots.innerHTML = reviews.map((t, i) => `<g class="mem-dot" data-t="${t}"><circle cx="${X(t)}" cy="${Y(0.9)}" r="5"/><text x="${X(t)}" y="${Y(0.9) + 24}" text-anchor="middle">${gaps[i]}</text></g>`).join('');
    const len = line.getTotalLength ? line.getTotalLength() : 2000;
    line.style.strokeDasharray = `${len} ${len}`;
    const dotEls = $$('.mem-dot', dots);
    const set = p => {
      line.style.strokeDashoffset = String(len * (1 - p));
      area.style.opacity = String(0.08 * p);
      dotEls.forEach(g => g.classList.toggle('on', p * 60 >= Number(g.dataset.t) + 0.4));
      if (forget) forget.style.opacity = String(0.55 * clamp(p * 3, 0, 1));
    };
    if (RM) { set(1); return; }
    set(0);
    curveDraw = vh => { const r = fig.getBoundingClientRect(); set(clamp((vh * 0.92 - r.top) / (vh * 0.62), 0, 1)); };
  }

  /* ---------- AI: original and the easier version (examples) ---------- */
  function levels() {
    const t = $('#lvlText'), bs = $$('.lvl-b'); if (!t || !bs.length) return;
    const V = ['What is surprising is that the headphones are not blocking that sound so much as fighting it with more sound.',
      'The surprising part is this: the headphones do not just block the sound. They fight it with more sound.'];
    let touched = false;
    const pick = (i, byHand) => {
      if (byHand) touched = true;
      bs.forEach(b => b.setAttribute('aria-pressed', String(Number(b.dataset.v) === i)));
      if (RM) { t.textContent = V[i]; return; }
      t.classList.add('fade'); setTimeout(() => { t.textContent = V[i]; t.classList.remove('fade'); }, 220);
    };
    bs.forEach(b => b.onclick = () => pick(Number(b.dataset.v), true));
    const card = $('#aiLevel'); if (card && !RM) card.addEventListener('in', () => setTimeout(() => { if (!touched) pick(1); }, 2200));
  }

  /* ---------- the knowledge graph (a drawing: four levels, points lighting up) ---------- */
  function graph() {
    const svg = $('.kg'), card = $('#graphCard'); if (!svg) return;
    const cols = [['入门', 5], ['进阶', 6], ['中高级', 6], ['高级', 5]], N = [];
    let seed = 7; const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280;
    cols.forEach(([, n], c) => { for (let i = 0; i < n; i++) N.push({ c, x: 70 + c * 127 + (rnd() - .5) * 34, y: 70 + i * (200 / (n - 1 || 1)) + (rnd() - .5) * 18 }); });
    const E = [];
    N.forEach((a, i) => N.forEach((b, j) => { if (b.c === a.c + 1 && Math.abs(a.y - b.y) < 62 && rnd() > .25) E.push([i, j]); }));
    N.forEach((a, i) => { const nb = N[i + 1]; if (nb && nb.c === a.c && rnd() > .55) E.push([i, i + 1]); });
    const state = N.map(n => n.c === 0 ? (rnd() > .2 ? 'ok' : 'used') : n.c === 1 ? (rnd() > .5 ? 'used' : rnd() > .4 ? 'ok' : 'warn') : n.c === 2 ? (rnd() > .55 ? 'read' : rnd() > .7 ? 'warn' : '') : (rnd() > .8 ? 'read' : ''));
    $('.kg-edges', svg).innerHTML = E.map(([i, j]) => `<path d="M${N[i].x.toFixed(1)} ${N[i].y.toFixed(1)} L${N[j].x.toFixed(1)} ${N[j].y.toFixed(1)}" data-a="${i}" data-b="${j}"/>`).join('');
    $('.kg-nodes', svg).innerHTML = cols.map(([label], c) => `<text x="${70 + c * 127}" y="32" text-anchor="middle">${label}</text>`).join('') +
      N.map((n, i) => `<circle cx="${n.x.toFixed(1)}" cy="${n.y.toFixed(1)}" r="9" data-i="${i}"/>`).join('');
    $$('.kg-edges path', svg).forEach(p => { const l = p.getTotalLength ? p.getTotalLength() : 140; p.style.setProperty('--len', l.toFixed(1)); });
    const nodes = $$('.kg-nodes circle', svg), edges = $$('.kg-edges path', svg);
    const lit = new Set();
    const light = i => {
      const s = state[i]; if (!s) return;
      lit.add(i); nodes[i].classList.add(s);
      edges.forEach(e => { if (lit.has(Number(e.dataset.a)) && lit.has(Number(e.dataset.b))) e.classList.add('on'); });
      if (!RM) { nodes[i].classList.add('pop'); setTimeout(() => nodes[i].classList.remove('pop'), 380); }
    };
    const order = N.map((n, i) => i).filter(i => state[i]);
    const go = () => { if (RM) { order.forEach(light); return; } order.forEach((i, k) => setTimeout(() => light(i), 300 + k * 150)); };
    if (card && IO && !RM) card.addEventListener('in', go, { once: true }); else go();
  }

  /* ---------- the ability radar (a drawing) ---------- */
  function radar() {
    const svg = $('.radar'); if (!svg) return;
    const names = ['听力', '阅读', '词汇', '语法', '口语', '写作'], me = [.72, .82, .7, .64, .5, .62], cx = 150, cy = 150, R = 100;
    const pt = (i, r) => { const a = -Math.PI / 2 + i * Math.PI / 3; return [cx + Math.cos(a) * R * r, cy + Math.sin(a) * R * r]; };
    const poly = r => names.map((n, i) => pt(i, typeof r === 'number' ? r : r[i]).map(v => v.toFixed(1)).join(',')).join(' ');
    $('.rd-grid', svg).innerHTML = [.25, .5, .75, 1].map(r => `<polygon points="${poly(r)}"/>`).join('') + names.map((n, i) => { const [x, y] = pt(i, 1); return `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}"/>`; }).join('');
    $('.rd-goal', svg).setAttribute('points', poly(1));
    $('.rd-me', svg).setAttribute('points', poly(me));
    const low = me.indexOf(Math.min(...me));
    $('.rd-labels', svg).innerHTML = names.map((n, i) => { const [x, y] = pt(i, 1.24); return `<text x="${x.toFixed(1)}" y="${(y + 5).toFixed(1)}" text-anchor="middle" class="${i === low ? 'gap' : ''}">${n}${i === low ? `<tspan x="${x.toFixed(1)}" dy="17" class="gap-t">差距最大</tspan>` : ''}</text>`; }).join('') +
      (() => { const [x, y] = pt(low, me[low]); return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4"/>`; })();
  }

  /* ---------- word books: the real list (vocab_service.registry(), 2026-11-24) ---------- */
  const SHELF = [
    ['按词频', '从你的水平往上走：按词频排位，基础词汇是最常用的 2000 个词。', [['基础词汇', 1751, '最常用的词，读懂日常文章的地基'], ['进阶词汇', 2538, '读懂一般报刊、课本文章需要的常用词'], ['高阶词汇', 2531, '读懂深度文章和学术入门材料的常见词'], ['精通词汇', 4266, '面向英语专业和高阶考试的较低频词'], ['拓展词汇', 6238, '更少见的词，适合继续扩充词汇量']]],
    ['中学英语', '取自开源英汉词典 ECDICT（MIT 许可）中标为中考、高考的词，按词频排序。', [['中考词汇', 1580, '中考英语词汇，常用词在前'], ['高考词汇', 3647, '高考英语词汇（含中考词），常用词在前']]],
    ['大学英语', '常用词在前，先背最可能遇到的。', [['四级词汇', 3818, '大学英语四级考试大纲词汇'], ['六级词汇', 5362, '大学英语六级考试大纲词汇'], ['考研词汇', 4785, '全国硕士研究生招生考试英语大纲词汇']]],
    ['英语专业', '按《高等学校英语专业英语教学大纲》的认知词汇量要求，由 Flow 自编。不是官方词表。', [['专四词汇', 6161, '约 6200 词，覆盖四级词汇，常用词在前', '自编 · 非官方词表'], ['专八词汇', 4892, '专四之外再加约 4900 词，覆盖六级、考研词汇', '自编 · 非官方词表']]],
    ['出国留学', '常用词在前，先背最可能遇到的。', [['雅思词汇', 4705, 'IELTS 常考词汇'], ['托福词汇', 6828, 'TOEFL 常考词汇'], ['GRE 词汇', 7365, 'GRE 常考词汇，难度最高']]],
    ['学术与职场', '改编自 New Academic Word List 1.2 和 Business Service List 1.2（CC BY-SA 4.0 许可），改编后同样以 CC BY-SA 4.0 发布。', [['学术英语', 946, '大学课程和学术论文里最常用的学术词'], ['商务英语', 1721, '商务文件、财经新闻和职场里最常用的词']]],
  ];
  function shelf() {
    const tabs = $('#shelfTabs'), panel = $('#shelfPanel'), basis = $('#shelfBasis'); if (!tabs || !panel) return;
    const max = Math.max(...SHELF.flatMap(g => g[2].map(b => b[1])));
    tabs.innerHTML = SHELF.map((g, i) => `<button type="button" class="tab" role="tab" id="shelfTab${i}" aria-controls="shelfPanel" aria-selected="${i === 0}" tabindex="${i === 0 ? 0 : -1}" data-i="${i}">${g[0]}<small>${g[2].length}</small></button>`).join('');
    const pick = (i, focus) => {
      const g = SHELF[i];
      $$('.tab', tabs).forEach((t, j) => { t.setAttribute('aria-selected', String(j === i)); t.tabIndex = j === i ? 0 : -1; });
      panel.setAttribute('aria-labelledby', 'shelfTab' + i);
      panel.innerHTML = g[2].map((b, k) => `<div class="book" data-k="${k}"><b>${b[0]}</b><span class="cnt">${b[1].toLocaleString('en-US')}<small>词</small></span><p>${b[2]}</p><div class="bar"><i></i></div>${b[3] ? `<span class="flag">${b[3]}</span>` : ''}</div>`).join('');
      $$('.book', panel).forEach((el, k) => { el.style.setProperty('--i', k); $('.bar i', el).style.setProperty('--w', (g[2][k][1] / max).toFixed(3)); });
      requestAnimationFrame(() => requestAnimationFrame(() => $$('.bar', panel).forEach(b => b.classList.add('go'))));
      basis.textContent = g[1];
      if (focus) { const t = $(`#shelfTab${i}`); t.focus(); t.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: RM ? 'auto' : 'smooth' }); }
    };
    tabs.addEventListener('click', e => { const t = e.target.closest('.tab'); if (t) pick(Number(t.dataset.i)); });
    tabs.addEventListener('keydown', e => {
      const t = e.target.closest('.tab'); if (!t) return;
      const cur = Number(t.dataset.i);
      const n = SHELF.length, to = e.key === 'ArrowRight' ? (cur + 1) % n : e.key === 'ArrowLeft' ? (cur + n - 1) % n : e.key === 'Home' ? 0 : e.key === 'End' ? n - 1 : -1;
      if (to >= 0) { e.preventDefault(); pick(to, true); }
    });
    pick(0);
  }

  /* ---------- exam cards: their timers run once ---------- */
  function timers() {
    $$('.exam').forEach((ex, i) => {
      const t = $('.timer', ex), to = [.62, .48, .74, .56, .38, .7, .52, .66][i % 8];
      const run = () => {
        if (RM) { t.style.setProperty('--t', to); return; }
        const t0 = performance.now() + i * 120, dur = 1600;
        const tick = now => { const k = clamp((now - t0) / dur, 0, 1); t.style.setProperty('--t', (to * (1 - Math.pow(1 - k, 3))).toFixed(3)); if (k < 1) requestAnimationFrame(tick); };
        requestAnimationFrame(tick);
      };
      if (IO && !RM) ex.addEventListener('in', run, { once: true }); else run();
    });
  }

  /* ---------- questions open and close smoothly ---------- */
  function faq() {
    if (RM || !Element.prototype.animate) return;
    $$('.qa').forEach(d => {
      const s = $('summary', d), a = $('.qa-a', d);
      s.addEventListener('click', e => {
        e.preventDefault();
        if (d.dataset.busy) return; d.dataset.busy = '1';
        const opening = !d.open;
        if (opening) d.open = true;
        const h = a.scrollHeight;
        const anim = a.animate([{ height: (opening ? 0 : h) + 'px', opacity: opening ? 0 : 1 }, { height: (opening ? h : 0) + 'px', opacity: opening ? 1 : 0 }], { duration: 380, easing: 'cubic-bezier(.2,.7,.2,1)' });
        anim.onfinish = anim.oncancel = () => { if (!opening) d.open = false; delete d.dataset.busy; };
      });
    });
  }

  /* ---------- each phone's status bar takes the colour at the top of its screenshot (light or dark) ---------- */
  function statusBars() {
    const cv = document.createElement('canvas'); cv.width = cv.height = 1;
    const cx = cv.getContext && cv.getContext('2d', { willReadFrequently: true }); if (!cx) return;
    $$('.phone .screen').forEach(sc => {
      const img = $('img', sc); if (!img) return;
      const paint = () => {
        try {
          cx.clearRect(0, 0, 1, 1); cx.drawImage(img, 0, 0, img.naturalWidth, 4, 0, 0, 1, 1);
          const d = cx.getImageData(0, 0, 1, 1).data; sc.style.backgroundColor = `rgb(${d[0]},${d[1]},${d[2]})`;
        } catch (e) { /* the page's own colour stays */ }
      };
      if (img.complete && img.naturalWidth) paint();
      img.addEventListener('load', paint);  // again when light/dark switches the picture
    });
  }

  function hero() {
    const h = $('.hero .display');
    if (h) requestAnimationFrame(() => setTimeout(() => h.classList.add('in'), 60));
  }

  /* ---------- the buttons that lead into the site are counted: per day and button only, nothing about who
     (the same count as the learning site's entry points, flow_admin.TAP_LABEL) ---------- */
  function taps() {
    document.addEventListener('click', e => {
      const t = e.target.closest && e.target.closest('[data-tap]'); if (!t || !navigator.sendBeacon) return;
      try { navigator.sendBeacon('/api/next/tap', JSON.stringify({ k: t.dataset.tap })); } catch (x) { /* not counted */ }
    }, true);
  }

  function start() {
    taps(); hero(); reveal(); pauseOffscreen(); statusBars(); story(); lookup(); curve(); levels(); graph(); radar(); shelf(); timers(); faq(); scrolling();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
