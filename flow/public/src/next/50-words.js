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

