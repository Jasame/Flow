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
