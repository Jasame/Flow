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
    // One clear first action: the plan's next step (signed in), or today's article (guest). Under it a short list of
    // steps, at most one notice, and a few materials as one-line rows.
    let top = '', readId = '';
    if (path) {
      // 按时间打包 (r28): 必做 fits the day's minutes and is what the ring and the button count; 还有时间的话 folds below
      // (not counted); 本周任务 is the week's exam set, any day of the week. An older server sends no group: all 必做.
      const p = h.path, must = p.steps.filter(s => (s.group || 'must') === 'must'), extra = p.steps.filter(s => s.group === 'extra'), wk = p.steps.filter(s => s.group === 'week');
      const nextK = must.findIndex(s => !s.done), next = must[nextK], read = must.find(s => s.key === 'read');
      readId = read ? decodeURIComponent(read.href.split('/')[2] || '') : '';
      const art = [pick, h.resume, ...h.today].find(m => m && m.id === readId);
      // 再学一篇 (r27): the next recommendation itself, not the whole library (that only when there is none)
      const more1 = h.today.find(m => m && m.id !== readId && (!(m.steps || []).includes('check') || m.redo));  // 精读重学 counts: it is what 今日 recommends once a level is done
      // the line past the day's minutes goes under the button, so it never pushes 开始 / 继续 off the first screen
      top = `<section class="today-plan" aria-labelledby="tpTitle">${backHTML(p, next)}
        <div class="tp-head"><h1 class="tp-t" id="tpTitle">${next ? '今天的计划' : '今天的计划完成了'}</h1><span class="muted small">${planHeadText(p)}</span>
          <span class="tp-count" role="img" aria-label="今天的计划，已完成 ${p.done} 步，共 ${p.total} 步"><span aria-hidden="true">${p.done} / ${p.total}</span></span>${sprintLine(h)}</div>
        ${next ? `<a class="btn primary block go-next" href="${esc(next.href)}" data-tap="home-start">${p.done ? '继续' : '开始'}今天的练习<span aria-hidden="true">→</span></a>${overLineHTML(p, next)}`
          : `<div class="tp-done">${doneRing}<span>都完成了。${more1 ? `想多学一点，下一篇是《${esc(more1.title)}》。` : '想多学一点，就再挑一篇。'}多学的照样算进「这周进步」。</span></div>
            <div class="tp-more"><a class="btn primary block go-next" href="${more1 ? '#/m/' + encodeURIComponent(more1.id) : '#/library'}" data-tap="home-more-one">再学一篇<span aria-hidden="true">→</span></a>
            <a class="btn ghost block" href="#/mix/more" data-tap="home-more-grammar">做 4 道语法题</a>
            <button class="link small hit44 tp-remind" type="button" id="remindOnce" data-tap="home-remind-once">今天或明天什么时候有空复习？</button></div>`}
        <div class="plist">${must.map((s, k) => planRowHTML(s, String(k + 1), s === next, s.key === 'read' ? art : null)).join('')}</div>
        ${p.note ? `<p class="tiny muted tp-note">${esc(p.note)}</p>` : ''}
        ${extra.length ? `<details class="tp-extra"${next ? '' : ' open'}><summary><span>还有时间的话</span><span class="tiny muted">${extra.length} 项 · 不算进今天的计划</span></summary>
          <div class="plist">${extra.map(s => planRowHTML(s, '+', false, null, 'home-extra')).join('')}</div></details>` : ''}
        ${wk.length ? `<div class="tp-week"><div class="tp-week-head"><h2 class="h3">本周任务</h2><span class="tiny muted">这周哪天做都行，不占每天的时间</span></div>
          <div class="plist">${wk.map(s => planRowHTML(s, '周', false, null, 'home-week-task')).join('')}</div></div>` : ''}</section>`;
    } else if (pick) {
      top = `<div class="hello"><h1 class="h1">今天学一篇，用上一句。</h1><span class="muted small">按「${esc(h.level_label)}（${h.level}）」为你挑选 · <a class="link" href="#/welcome/edit">调整</a></span></div>
        <article class="card hero"><div class="meta">${kindPill(pick)}<span class="pill green">今日推荐</span><span class="pill">${pick.level}</span><span class="pill">${esc(pick.theme_label)}</span></div>
        <h2 class="title">${esc(pick.title)}</h2>${pick.title_en ? `<div class="title-en">${esc(pick.title_en)}</div>` : ''}<p class="preview">${esc(pick.preview)}</p>${reasonsHTML(pick)}
        <span class="muted small">${pick.words} 词 · 约 ${pick.minutes} 分钟 · 听、读、理解、用出来${pick.ai ? ' ' + aiTag() : ''}</span>
        <a class="btn primary block go-next" href="#/m/${encodeURIComponent(pick.id)}">开始学习<span aria-hidden="true">→</span></a></article>`;
    } else top = '<div class="empty">今天没有可推荐的材料了。</div>';
    const resume = h.resume && h.resume.id !== readId ? h.resume : null, news = h.news && h.news.id !== readId ? h.news : null;
    const more = h.today.filter(m => m.id !== readId && (path || m !== pick) && (!resume || m.id !== resume.id) && (!news || m.id !== news.id)).slice(0, 3);
    // 好句 and 一读 come first, except on a screen too short for them and the plan's button together (a phone held
    // sideways): there the plan comes first, so its next step is still on the first screen.
    // The day back after days away (r28 第 2 段) starts with 欢迎回来 and the plan too: getting going comes first.
    const short = (innerHeight < 500 && innerWidth > innerHeight) || !!(path && h.path.back);
    view.innerHTML = `<div class="greet-row"><span class="kicker greet">${greeting()}${name ? `，<span class="nm">${esc(name)}</span>` : ''}</span>
        ${st && st.habit ? '' : st ? `<span class="wk" title="本周学了 ${weekN} 天"><span class="tiny muted">本周 ${weekN} 天</span><span class="week" aria-hidden="true">${st.week.map(d => `<span class="${d.active ? 'on' : ''}"></span>`).join('')}</span></span>` : ''}</div>
      ${announceHTML(h) || updateCardHTML(h)}${trialSurveyHTML(h)}
      ${short ? '' : lineCardHTML(h) + newsCardHTML(news) + mineRowHTML(h)}
      ${top}
      ${short ? lineCardHTML(h) + newsCardHTML(news) + mineRowHTML(h) : ''}
      ${weekCardSlot()}
      <div id="notice"></div>
      ${S.user && !path ? vocabHome(st) : ''}
      <section class="section" aria-labelledby="mTitle"><div class="section-head"><h2 class="h2" id="mTitle">也可以读</h2><a class="link small hit44" href="#/welcome/edit">按 ${h.level} 挑选 · 调整</a></div>${featLeftHTML(h)}
        <div class="mlist">${resume ? mrow(resume, ['继续', 'green'], `#/m/${encodeURIComponent(resume.id)}/${nextStep(resume.steps)}`, 'home-resume') : ''}${more.map(m => mrow(m, null, '', 'home-pick')).join('')}
          <a class="mrow more" href="#/library" data-tap="home-more"><span class="t"><b>更多材料</b><span class="tiny muted">按话题和级别挑一篇</span></span><span class="go" aria-hidden="true">›</span></a></div></section>`;
    fillNotice(h);
    bindAnnounce(h); bindUpdateCard(h); bindTrialSurvey();  // 「语流更新了」 where a 公告 would be (83-updates.js)
    bindLine(h);  // 今日好句 (12-daily-line.js)
    const ro = document.getElementById('remindOnce'); if (ro) ro.onclick = () => remindOnce();  // 这次什么时候复习 (50-words.js)
    mountWeekCards(view);  // 这周进步 (11-progress.js)
    if (st && st.habit) cheerWeek(st.habit);
    const nextRead = readId || (pick && pick.id);
    if (nextRead) setTimeout(() => preloadMaterial(nextRead), 600);  // after the page is drawn, not before
  }
  // The plan's line under its title: 必做's real minutes before it starts, what is left once it has, and the day's
  // minutes from the learner's own records once it is done (time_budget, r28). An older server: the minutes chosen.
  function planHeadText(p) {
    if (p.must_minutes == null) return `${p.total} 步 · 约 ${p.minutes} 分钟`;
    if (p.done >= p.total) return p.studied ? `今天学了约 ${p.studied} 分钟` : '都做完了';
    return p.done ? `还要约 ${p.left_minutes} 分钟` : `必做 ${p.total} 步 · 约 ${p.must_minutes} 分钟`;  // done / total beside it (.tp-count)
  }
  // 练我自己的材料 (r29, the user's pick 2026-11-26: a third row under 今日好句 and 今日一读, the same look): the learner's own
  // article to go on with (next_service.mine), or a way to paste one in. Signed in only: a guest has no articles.
  function mineRowHTML(h) {
    if (!S.user || !h.mine) return '';
    const m = h.mine.item;
    const href = m ? `#/m/${encodeURIComponent(m.id)}${m.started ? '/' + nextStep(m.steps) : ''}` : '#/import';
    return `<a class="card news-card mine-card" href="${href}" data-tap="home-mine"><span class="lc-head"><span class="lc-title nc-title">我的材料</span></span>
      <b class="nc-h">${m ? `${m.started ? '继续' : '练'}《${esc(m.title)}》` : '贴课本或讲义进来练'}</b>
      <span class="small muted nc-p">${m ? `${esc(m.level || '')} · ${m.words} 词 · 你自己贴进来的` : '课本、讲义、面试题都行，用语流的四步来练'}</span></a>`;
  }
  // A step of the plan as a row: its number (+ for 还有时间的话, 周 for 本周任务), what to do and about how long.
  // 本周任务's row is .wtask, never .week: .week is the week-days bar (10-pages.css .week span = a 6 px grey bar), which
  // turned the row's title block and its › into grey bars and pushed the subtitle out of the card (feedback, 2026-11-25).
  // ui_test progress group checks the rows.
  function planRowHTML(s, num, isNext, a, tap) {
    const mins = s.minutes && !s.done ? `约 ${s.minutes} 分钟` : '';
    const sub = a ? [`${a.redo ? '精读重学 · ' : ''}今天这篇 · ${a.level} · ${a.theme_label}`, s.mode_label, mins] : [s.sub, mins];
    return `<a class="prow${s.done ? ' done' : ''}${isNext ? ' next' : ''}${s.group === 'extra' ? ' extra' : s.group === 'week' ? ' wtask' : ''}" href="${esc(s.href)}"${tap ? ` data-tap="${tap}"` : ''}>
      <span class="num">${s.done ? '✓' : num}</span><span class="t"><b>${esc(a ? a.title : s.title)}</b><span class="muted tiny">${esc(sub.filter(Boolean).join(' · '))}</span></span>
      <span class="go" aria-hidden="true">›</span></a>`;
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

