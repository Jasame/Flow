  /* ---------- 今日的样子 (r39, the user's picks 2026-11-26, B9's v3): 列表 (the default) or 卡片 ---------- */
  // One order for both (the user: 「列表按什么顺序，卡片就按什么顺序」): 这周, 今天的计划, then what is not counted in the
  // plan. The list draws 这周 and the plan as two white blocks, the one green button under them, and folds the rest
  // under 还有时间的话; the cards draw one white card each, side by side, 今天的计划 in the middle when 今日 opens.
  // The same parts in both: a white block, a step row (number, title, time; the next one in ink), one green button.
  // The choice is kept with the account (POST /api/next/today-view); the switch on 今日 and 我的 → 使用习惯 (B5) call
  // setTodayView. Only learners with a plan have it: a guest's 今日 is one article.
  const TODAY_ORDER = ['week', 'plan', 'line', 'mine', 'news', 'extra'];
  const TODAY_NAMES = { week: '这周', plan: '今天的计划', line: '今日好句', mine: '我的材料', news: '今日一读', extra: '还有时间的话' };
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
    const rows = [], l = h.line, m = h.mine;
    if (l) rows.push(`<div class="line-row" id="lineCard"><button class="tv-row named" id="lcFold" type="button" aria-expanded="false" aria-controls="lcBody" data-tap="line-fold">`
      + `<span class="t">今日好句</span><span class="m">${esc(l.source)}</span></button><div class="lc-body tv-line" id="lcBody">${lineBodyHTML(l)}</div></div>`);
    if (S.user && m) {
      const it = m.item, href = it ? `#/m/${encodeURIComponent(it.id)}${it.started ? '/' + nextStep(it.steps) : ''}` : '#/import';
      rows.push(`<a class="tv-row named" href="${href}" data-tap="home-mine"><span class="t">我的材料</span><span class="m">${it ? `${it.started ? '继续' : '练'}《${esc(it.title)}》` : '贴课本或讲义进来练'}</span></a>`);
    }
    if (news) rows.push(`<a class="tv-row named" href="#/m/${encodeURIComponent(news.id)}" data-tap="home-news"><span class="t">今日一读</span><span class="m">${aiTag()}${news.minutes ? ` · 约 ${news.minutes} 分钟` : ''}</span></a>`);
    f.extra.forEach(s => rows.push(extraRowHTML(s, 'home-extra')));
    return rows;
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
          <div class="tv-card tv-more">${rows.join('')}</div></details>` : ''}${weekTasksHTML(f)}</section>`
    };
    return TODAY_ORDER.filter(k => blocks[k]).map(k => blocks[k]()).join('');
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
        <div class="tv-foot">${aiVoiceNote('朗读由 AI 合成', 'p', 'tv-ai')}<div class="tv-pair"><button class="tv-act" type="button" id="lcSay" data-tap="line-say">听一遍</button>`
        + `<button class="tv-act tv-icon" type="button" id="lcKeep" data-tap="line-keep" aria-label="收藏这一句">${ICON.star}</button></div></div>`,
      mine: () => m && `<p class="tv-lb">我的材料</p><h2 class="tv-ttl">${it ? esc(it.title) : '贴课本或讲义进来练'}</h2>
        <p class="tv-sub">${it ? [it.level, it.words ? it.words + ' 词' : '', it.started ? `学了 ${(it.steps || []).length} / 4 步` : '还没开始'].filter(Boolean).map(esc).join(' · ') : '课本、讲义、面试题都行，用语流的四步来练'}</p>
        ${it && it.started ? `<div class="tv-bar" aria-hidden="true"><i style="width:${Math.round((it.steps || []).length / 4 * 100)}%"></i></div>` : ''}
        <a class="tv-act" href="${it ? `#/m/${encodeURIComponent(it.id)}${it.started ? '/' + nextStep(it.steps) : ''}` : '#/import'}" data-tap="home-mine">${it ? (it.started ? '接着学' : '开始练') : '去粘贴'}</a>`,
      news: () => news && `<p class="tv-lb">今日一读 · ${aiTag()}</p><h2 class="tv-ttl">${esc(news.title)}</h2>
        <p class="tv-sub">${[news.level, news.theme_label, news.minutes ? `约 ${news.minutes} 分钟` : ''].filter(Boolean).map(esc).join(' · ')}</p>${news.preview ? `<p class="tv-p tv-clamp">${esc(news.preview)}</p>` : ''}
        <a class="tv-act" href="#/m/${encodeURIComponent(news.id)}" data-tap="home-news">读这篇</a>`,
      extra: () => extra.length && `<p class="tv-lb">还有时间的话</p><h2 class="tv-big">还可以再练 ${extra.length} 项</h2><p class="tv-sub">不算进今天的计划</p>
        <div class="tv-rows">${extra.map(s => extraRowHTML(s, s.group === 'week' ? 'home-week-task' : 'home-extra')).join('')}</div>`
    };
    const list = TODAY_ORDER.map(k => ({ k, html: cards[k] && cards[k]() })).filter(c => c.html);
    const n = list.length, start = Math.max(0, list.findIndex(c => c.k === 'plan'));
    const html = `<div class="tv-deckbox"><button class="tv-arrow prev" type="button" aria-label="上一张" tabindex="-1">‹</button>
      <div class="tv-deck" id="tvDeck" role="list" aria-label="今日，${n} 张卡片，左右翻" tabindex="0">${list.map((c, k) =>
        `<section class="tv-dc tv-${c.k}${c.k === 'plan' ? ' today-plan' : ''}"${c.k === 'line' ? ' id="lineCard"' : ''} role="listitem" aria-label="第 ${k + 1} 张，共 ${n} 张，${TODAY_NAMES[c.k]}" data-card="${c.k}">${c.html}</section>`).join('')}</div>
      <button class="tv-arrow next" type="button" aria-label="下一张" tabindex="-1">›</button></div>
      <div class="tv-dots" aria-hidden="true">${list.map((c, k) => `<i class="${k === start ? 'on' : ''}"></i>`).join('')}</div>`;
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
    // where card k sits in the middle (one card a screen on a phone, two or three side by side on a computer)
    const step = () => cards[0].offsetWidth + (parseFloat(getComputedStyle(dk).columnGap) || 0);
    const pad = () => parseFloat(getComputedStyle(dk).paddingLeft) || 0;
    const left = k => pad() + k * step() + cards[0].offsetWidth / 2 - dk.clientWidth / 2;
    const at = () => Math.max(0, Math.min(cards.length - 1, Math.round((dk.scrollLeft + dk.clientWidth / 2 - pad() - cards[0].offsetWidth / 2) / step())));
    let frame = 0;
    const paint = () => {
      frame = 0;
      const k = at();
      dots.forEach((x, i) => x.classList.toggle('on', i === k));
      if (calm || dk.clientWidth > cards[0].offsetWidth * 1.6) return;  // side by side on a wide screen: all in full view, none smaller
      const s = step(), mid = dk.scrollLeft + dk.clientWidth / 2;
      cards.forEach((c, i) => { const d = Math.min(1, Math.abs(pad() + i * s + c.offsetWidth / 2 - mid) / s); c.style.transform = d > 0.01 ? `scale(${1 - 0.04 * d})` : ''; c.style.opacity = d > 0.01 ? String(1 - 0.35 * d) : ''; });
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
    const onResize = () => { if (!dk.isConnected) return removeEventListener('resize', onResize); const k = at(); fit(); dk.scrollLeft = left(k); paint(); };
    addEventListener('resize', onResize);
  }
