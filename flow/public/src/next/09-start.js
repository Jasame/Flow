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
    const st = { goal: cur.goal || '', exam: cur.exam || '', date: cur.exam_date || '', target: cur.target || '', level: cur.level || '',
                 minutes: cur.minutes || 10, themes: (cur.themes || []).slice(), days: cur.weekly_goal || 0 };
    let picked = !!cur.target;  // a target chosen by hand is not replaced by the suggestion
    // 一周学几天 (r28 第 6 段, 每周目标): 5 for an exam, 4 otherwise (save_profile's default) until chosen by hand
    let dayPicked = !!cur.weekly_goal;
    const daysFor = () => (st.goal === 'exam' ? 5 : 4);
    const suggest = () => M.target_for[st.goal === 'exam' && st.exam ? st.exam : st.goal] || 'B1';
    const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    const radio = (attr, v, on, inner, cls = 'chip') => `<button class="${cls}" type="button" role="radio" data-${attr}="${esc(v)}" aria-checked="${on}">${inner}</button>`;
    document.body.classList.toggle('onboarding', !edit);
    view.innerHTML = `<div class="stack wg">
      <div>${edit ? '<span class="kicker">学习目标和水平</span>' : ''}<h1 class="h1">你学英语主要为了什么？</h1><p class="muted small">选一个，之后在「我的」里随时能改。</p></div>
      <div class="wg-goals" role="radiogroup" aria-label="学英语主要为了什么">${[...M.goals].sort((a, b) => (b.id === 'exam') - (a.id === 'exam')).map(g => radio('goal', g.id, g.id === st.goal,
        `<span class="l">${esc(g.label)}</span><span class="d">${esc((M.goal_hints || {})[g.id] || '')}</span>`, 'opt')).join('')}</div>
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
        ${edit ? '<a class="btn ghost block" href="#/me">取消</a>' : S.user ? '' : '<button class="link small tc" id="wgLogin" type="button" data-tap="welcome-login">已有账号？登录</button>'}</div>
      ${edit ? '' : '<p class="tiny tc about-line"><a class="link" href="/about" data-tap="welcome-about">第一次来？先花一分钟看看语流能帮你做什么</a></p>'}</div>`;  // 认识语流 (#32)
    const sync = () => {
      if (!picked) st.target = suggest();
      if (!dayPicked) st.days = daysFor();
      view.querySelectorAll('[data-days]').forEach(b => b.setAttribute('aria-checked', String(Number(b.dataset.days) === st.days)));
      view.querySelectorAll('[data-goal]').forEach(b => b.setAttribute('aria-checked', String(b.dataset.goal === st.goal)));
      view.querySelectorAll('[data-exam]').forEach(b => b.setAttribute('aria-checked', String(b.dataset.exam === st.exam)));
      view.querySelectorAll('[data-target]').forEach(b => { b.setAttribute('aria-checked', String(b.dataset.target === st.target)); b.querySelector('.rec').hidden = !st.goal || b.dataset.target !== suggest(); });
      document.getElementById('wgExam').hidden = st.goal !== 'exam';
      document.getElementById('wgDate').hidden = st.goal !== 'exam' || !st.exam;
      document.getElementById('wgGo').disabled = !st.goal;
      // with an exam and no word plan yet, starting makes one on the exam's book (save_profile): said here first
      const e = st.goal === 'exam' && M.exams.find(x => x.id === st.exam), plan = document.getElementById('wgPlan');
      const hasPlan = !!(S.home && S.home.stats && S.home.stats.vocab_plan);
      plan.hidden = !e || hasPlan;
      if (e && !hasPlan) plan.textContent = S.user ? `${edit ? '保存' : '开始学习'}后会为你建好《${e.book_title}》每天 10 个新词，可以在「单词」里改。`
        : `登录后会为你建好《${e.book_title}》每天 10 个新词的背词计划，可以在「单词」里改。`;
      const need = document.getElementById('wgNeed'); need.textContent = st.goal ? '' : '先选一个目标'; need.hidden = !!st.goal;
    };
    view.querySelectorAll('[data-goal]').forEach(b => b.onclick = () => { st.goal = b.dataset.goal; sync(); });
    view.querySelectorAll('[data-exam]').forEach(b => b.onclick = () => { st.exam = b.dataset.exam; sync(); });
    view.querySelectorAll('[data-target]').forEach(b => b.onclick = () => { st.target = b.dataset.target; picked = true; sync(); });
    view.querySelectorAll('[data-days]').forEach(b => b.onclick = () => { st.days = Number(b.dataset.days); dayPicked = true; sync(); });
    view.querySelectorAll('[data-level]').forEach(b => b.onclick = () => { st.level = b.dataset.level; view.querySelectorAll('[data-level]').forEach(x => x.setAttribute('aria-checked', String(x === b))); });
    view.querySelectorAll('[data-min]').forEach(b => b.onclick = () => { st.minutes = Number(b.dataset.min); view.querySelectorAll('[data-min]').forEach(x => x.setAttribute('aria-checked', String(x === b))); });
    view.querySelectorAll('[data-theme]').forEach(b => b.onclick = () => { const t = b.dataset.theme; st.themes = st.themes.includes(t) ? st.themes.filter(x => x !== t) : st.themes.concat(t); b.setAttribute('aria-pressed', String(st.themes.includes(t))); });
    const login = document.getElementById('wgLogin'); if (login) login.onclick = () => openLogin();
    sync();
    document.getElementById('wgGo').onclick = async e => {
      const btn = e.currentTarget; btn.disabled = true;
      const exam = st.goal === 'exam' ? st.exam : '', date = exam ? document.getElementById('wgDateIn').value : '';
      // the level: from the starting check if it was just taken; from 我的 as chosen (or kept); otherwise one band below the target
      const level = S.placed ? S.placed : edit ? st.level || below(st.target) : below(st.target);
      const source = S.placed ? 'placed' : edit && st.level === cur.level ? (cur.level_source || 'self') : edit && st.level ? 'self' : 'guess';
      const prof = { goal: st.goal, target: st.target, level, level_source: source, themes: st.themes, minutes: st.minutes, exam, exam_date: date, weekly_goal: st.days };
      let made = null;
      if (S.user) { try { made = (await api('/api/next/profile', prof)).plan_made; } catch (x) { btn.disabled = false; toast(x.message); return; } }
      S.placed = ''; S.guest = { ...(S.guest || {}), ...prof }; save('flow-next-guest', S.guest);
      document.body.classList.remove('onboarding');
      await refreshHome(); S.homeFresh = true;
      if (made) toast(`已为你建好《${made.title}》每天 ${made.daily_new} 个新词`); else if (edit) toast('已保存');
      location.hash = edit ? '#/me' : '#/';
    };
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
