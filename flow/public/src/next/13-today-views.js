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
  function stepsHTML(f) {
    return `<ol class="tv-steps">${f.must.map((s, k) => `<li><a class="tv-step${s.done ? ' done' : ''}${s === f.next ? ' next' : ''}" href="${esc(s.href)}">`
      + `<span class="n" aria-hidden="true">${s.done ? '✓' : k + 1}</span><span class="t">${esc(s.key === 'read' && f.art ? f.art.title : s.title)}</span>`
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
    const WK = '一二三四五六日';
    const cards = {
      week: () => w && `<p class="tv-lb">这周</p><h2 class="tv-big">${esc(w.title)}</h2>${w.sub ? `<p class="tv-sub">${esc(w.sub)}</p>` : ''}
        <div class="tv-wk7 tv-mid" aria-hidden="true">${w.days.map((d, k) => `<span><i class="${d.active ? 'on' : ''}${d.today ? ' today' : ''}"></i>${WK[k]}</span>`).join('')}</div>
        <button class="tv-act" type="button" id="tvWeek" data-tap="home-week">看明细</button>`,
      plan: () => `${backHTML(f.p, f.next)}<h1 class="tv-lb" id="tpTitle">${f.next ? '今天的计划' : '今天的计划完成了'}</h1><p class="tv-big">${esc(f.left)}</p>
        <p class="tv-sub"><span class="tp-count" role="img" aria-label="今天的计划，已完成 ${f.p.done} 步，共 ${f.p.total} 步"><span aria-hidden="true">${f.p.total} 步，${f.next ? `做完 ${f.p.done} 步了` : '都做完了'}</span></span></p>
        ${sprintLine(h)}<div class="tv-st">${stepsHTML(f)}</div>${f.p.note ? `<p class="tiny muted tp-note">${esc(f.p.note)}</p>` : ''}${overLineHTML(f.p, f.next)}
        ${f.next ? '' : `<a class="link small hit44 tv-also" href="#/mix/more" data-tap="home-more-grammar">做 4 道语法题</a>`}${goHTML(f)}`,
      line: () => l && `<p class="tv-lb">今日好句</p><p class="tv-quote lc-en${l.say.length > 100 ? ' long' : ''}" lang="en">${lineEnHTML(l)}</p><p class="tv-p lc-zh">${esc(l.zh)}</p>
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
      const room = tb - (dk.getBoundingClientRect().top + scrollY) - 44;  // measured from the page's top: 今日 opens there
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
    const onResize = () => { if (!dk.isConnected) return removeEventListener('resize', onResize); const k = at(); fit(); dk.scrollLeft = left(k); paint(); };
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
        const r = t.getBoundingClientRect();
        drag.on = true; drag.slot = document.createElement('li'); drag.slot.className = 'tv-slot'; drag.slot.setAttribute('aria-hidden', 'true');
        grid.insertBefore(drag.slot, t);
        t.classList.add('lift'); t.style.left = r.left + 'px'; t.style.top = r.top + 'px'; t.style.width = r.width + 'px'; t.style.height = r.height + 'px';
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
