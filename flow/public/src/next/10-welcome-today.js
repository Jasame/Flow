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
    if (!h.stats || (h.stats.materials_done || 0) < 3) return `<a class="card sunk section notice guide-hint" href="#/guide" data-tap="notice-guide"><span class="stack-s"><b>第一次用？看操作指南</b><span class="small muted">每个页面怎么用、按哪里，一步一步讲清楚。</span></span><span class="go" aria-hidden="true">›</span></a>`;
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

