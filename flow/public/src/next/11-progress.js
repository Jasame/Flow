  /* ---------- 这周进步 (r27): the week so far, at the top of 今日; its details; the Sunday mail ---------- */
  // Four numbers from the learner's own records (progress_service.week): words remembered for the first time (a later
  // day's review still recalled them), texts finished, the share of questions answered right without a hint against
  // last week, and the weekly goal with the weeks reached so far (they only count up). A tap opens the details.
  const WEEKDAYS = '一二三四五六日';
  function accText(a) {
    const n = a.now, b = a.before;
    const value = n.rate != null ? n.rate + '%' : n.total ? `${n.right}/${n.total}` : '—';
    const sub = n.rate != null && b.rate != null ? (n.rate > b.rate ? `<span class="up">比上周 ↑${n.rate - b.rate}</span>` : n.rate < b.rate ? `比上周 ↓${b.rate - n.rate}` : '和上周持平')
      : n.rate == null ? (n.total ? `满 ${a.min} 题才算` : '这周还没做题') : b.total ? '上周题太少' : '上周没做题';
    return { value, sub };
  }
  function weekCardHTML(h) {
    const st = h && h.stats, p = st && st.progress, hb = st && st.habit;
    if (!S.user || !p || !hb) return '';
    const acc = accText(p.accuracy), weeks = hb.weeks || 0;
    const empty = !p.remembered.now && !p.finished.now && !p.accuracy.now.total && !hb.done;
    const tile = (cls, value, label, sub) => `<span class="wk-tile${cls ? ' ' + cls : ''}"><b>${value}</b><span class="tiny muted">${label}</span><span class="tiny sub">${sub}</span></span>`;
    const label = `这周进步：记住 ${p.remembered.now} 个新词，学完 ${p.finished.now} 篇，做题正确率 ${p.accuracy.now.rate != null ? p.accuracy.now.rate + '%' : '还不够算'}，`
      + `本周学了 ${hb.done} 天，目标 ${hb.goal} 天${weeks ? `，已达成 ${weeks} 周` : ''}。点开看明细`;
    return `<button class="card week-card" id="weekCard" type="button" data-tap="home-week" aria-label="${esc(label)}">
      <span class="wk-head"><b>这周进步</b><span class="tiny wk-total${weeks ? ' on' : ''}">${weeks ? `已达成 ${weeks} 周` : '看明细'}<span aria-hidden="true"> ›</span></span></span>
      <span class="wk-tiles">${tile('', p.remembered.now, '记住的新词', `上周 ${p.remembered.before}`)}${tile('', p.finished.now, '学完的文章', `上周 ${p.finished.before}`)}`
      + `${tile('', acc.value, '做题正确率', acc.sub)}${tile('goal' + (hb.met ? ' met' : ''), `${hb.done}<small>/${hb.goal}天</small>`, '每周目标', hb.met ? '达成 ✓' : `还差 ${hb.goal - hb.done} 天`)}</span>
      <span class="wk-foot"><span class="week" aria-hidden="true">${hb.days.map(d => `<span class="${d.active ? 'on' : ''}${d.today ? ' today' : ''}"></span>`).join('')}</span>
        <span class="tiny muted">${empty ? '做完今天的第一步，这里就开始记录' : '数字都来自你自己的学习记录'}</span></span></button>`;
  }
  function bindWeekCard() {
    const b = document.getElementById('weekCard'); if (b) b.onclick = weekSheet;
  }
  // After the goal changes (habitSheet): the card is drawn again from the new numbers.
  function refreshWeekCard() {
    const b = document.getElementById('weekCard'); if (!b || !S.home) return;
    b.outerHTML = weekCardHTML(S.home); bindWeekCard();
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
      <div class="row"><a class="btn primary" href="#/report" data-close>这周的报告</a><a class="btn" href="#/growth" data-close>我的进步</a><button class="btn ghost" data-close type="button">关闭</button></div></div>`, card => {
      card.querySelector('#wkGoal').onclick = habitSheet;
    });
  }
  // 我的 → 每周进度邮件: on by default for an account with an email; the mail's own link turns it off too.
  function weeklyMailLabel() {
    const m = S.home && S.home.stats && S.home.stats.progress && S.home.stats.progress.mail;
    return !m ? '' : !m.email ? '绑定邮箱后可以收' : m.on ? '每周日晚上 8 点' : '已关闭';
  }
  function weeklyMailSheet() {
    const p = S.home && S.home.stats && S.home.stats.progress, m = (p && p.mail) || { on: true, email: false };
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">每周进度邮件</h2>
      <p class="small">每周日晚上 8 点，把这周的进步发到你绑定的邮箱：记住的新词、学完的文章、做题正确率和每周目标。这周没学的话，会提醒你一下；连着几周没学就不再发。</p>
      ${m.email ? `<div class="chips" role="radiogroup" aria-label="收不收每周进度邮件">${[[true, '每周收'], [false, '不收']].map(([v, l]) => `<button class="chip" type="button" role="radio" data-mail="${v}" aria-checked="${m.on === v}">${l}</button>`).join('')}</div>
        <p class="tiny muted">每封邮件最下面也有退订链接。</p>`
        : `<p class="small muted">还没有绑定邮箱。</p><div><button class="btn small primary" id="wmBind" type="button">绑定邮箱</button></div>`}
      <button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      card.querySelectorAll('[data-mail]').forEach(b => b.onclick = async () => {
        try {
          const r = await api('/api/next/weekly-mail', { on: b.dataset.mail === 'true' });
          if (p) p.mail = r;
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
