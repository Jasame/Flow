  /* ---------- 新手引导 v2 (the user, 2026-11-26: 「把初次使用的引导做完善，动画流畅、好看、讲得详细」, 「视觉压力小」;
     19:5x 「现在先做」): one step at a time over the whole screen. A new learner starts with 欢迎, 学英语为了什么 (more than
     one) and 想到什么水平 (these save the profile, as the one-page form under it would); then one step per place of the
     app, in the order of the tab bar, a small copy of which sits where the real one is and walks along with the steps.
     跳过 at any time (during the first three the one-page form is under it); closed half way, the next opening goes on
     from that step (this browser); once per account (tour_service: the learner tour; a guest: this browser); 我的 → 帮助
     plays the places again. Only transform and opacity move; with the system's 「减少动态效果」 nothing moves. ---------- */
  // The pictures (B9, 2026-11-26): the real page made very simple, a few shapes, no words; the part meant in a thicker ink
  // line (the accent is the button's only, 08-intro.css). `ip` parts come in one after another (d1…d4).
  const INTRO_ART = {
    tabs: `<svg viewBox="0 0 280 200"><rect class="fr ip" x="70" y="4" width="140" height="192" rx="22"/>
      <rect class="bar ip d1" x="86" y="22" width="108" height="40" rx="12"/><path class="lns ip d2" d="M90 82h92M90 102h70M90 122h84"/>
      <g class="ip d3"><rect class="hl" x="80" y="152" width="120" height="32" rx="12"/>${[98, 119, 140, 161, 182].map(x => `<circle class="dot" cx="${x}" cy="168" r="4"/>`).join('')}</g></svg>`,
    practice: `<svg viewBox="0 0 280 200"><rect class="hl ip" x="40" y="6" width="200" height="46" rx="14"/><path class="lns ip d1" d="M58 24h70M58 38h46"/>
      <rect class="btn ip d1" x="40" y="60" width="200" height="22" rx="11"/>
      <g class="ip d2"><rect class="fr" x="40" y="94" width="96" height="100" rx="14"/><path class="lns" d="M56 116h48M56 140h60M56 164h40"/></g>
      <g class="ip d3"><rect class="fr" x="144" y="94" width="96" height="100" rx="14"/><path class="lns" d="M160 116h56M160 140h44M160 164h52"/></g></svg>`,
    exam: `<svg viewBox="0 0 280 200"><g class="ip"><rect class="fr" x="40" y="4" width="200" height="58" rx="14"/><path class="lns" d="M58 22h64"/><rect class="btn" x="56" y="36" width="168" height="16" rx="8"/></g>
      <g class="ip d1"><rect class="fr" x="40" y="72" width="200" height="124" rx="16"/><path class="lns" d="M58 92h96M58 168h80M58 186h60"/></g>
      <g class="ip d2 open"><rect class="hl" x="48" y="106" width="184" height="46" rx="12"/><path class="lns" d="M64 122h72M64 138h112"/></g></svg>`,
    radar: `<svg viewBox="0 0 280 200"><path class="fr ip" d="M140 18 200.6 53v70L140 158 79.4 123V53z"/>
      <path class="axis ip d1" d="M140 88V18M140 88l60.6-35M140 88l60.6 35M140 88v70M140 88l-60.6 35M140 88 79.4 53"/>
      <path class="hl grow-in ip d2" d="M140 49.5 188.5 60 176.4 109 140 137 112.7 103.8 100.6 65.3z"/>
      <rect class="btn ip d3" x="60" y="172" width="160" height="22" rx="11"/></svg>`,
    words: left => `<svg viewBox="0 0 280 200"><g class="ip"><rect class="fr" x="20" y="14" width="120" height="122" rx="16"/><path class="lns" d="M36 38h52M36 66h80M36 90h64"/><rect class="btn" x="36" y="108" width="88" height="16" rx="8"/></g>
      <g class="ip d1"><rect class="bar" x="20" y="148" width="120" height="44" rx="14"/><path class="lns" d="M38 170h56"/></g>
      <g class="ip d2"><g class="swipe${left ? ' l' : ''}"><rect class="hl" x="158" y="22" width="102" height="132" rx="16"/><path class="lns" d="M180 74h58M188 98h42"/></g></g>
      <path class="arr ip d3" d="${left ? 'M234 178h-48m8-8-8 8 8 8' : 'M186 178h48m-8-8 8 8-8 8'}"/></svg>`,
    me: `<svg viewBox="0 0 280 200"><g class="ip"><rect class="fr" x="40" y="4" width="200" height="46" rx="14"/><circle class="bar" cx="64" cy="27" r="12"/><path class="lns" d="M88 21h60M88 35h90"/></g>
      <g class="ip d1">${[40, 108, 176].map(x => `<rect class="fr" x="${x}" y="60" width="64" height="40" rx="12"/>`).join('')}</g>
      <g class="ip d2"><rect class="fr" x="40" y="110" width="200" height="48" rx="14"/><path class="lns" d="M58 126h84M58 142h104"/></g>
      <g class="ip d3"><rect class="hl" x="40" y="166" width="200" height="12" rx="6"/><rect class="hl" x="40" y="184" width="200" height="12" rx="6"/></g></svg>`,
    growth: `<svg viewBox="0 0 280 200"><g class="ip"><rect class="fr" x="40" y="4" width="200" height="66" rx="16"/><path class="lns" d="M60 24h40"/><rect class="hl" x="60" y="38" width="96" height="18" rx="9"/></g>
      <g class="ip d1"><rect class="fr" x="40" y="80" width="200" height="62" rx="14"/><path class="lns" d="M60 100h56M60 122h76M190 100h30M196 122h24"/></g>
      <g class="ip d2"><rect class="fr" x="40" y="152" width="200" height="44" rx="14"/><rect class="bar" x="58" y="168" width="164" height="12" rx="6"/><rect class="fill grow-x" x="58" y="168" width="112" height="12" rx="6"/></g></svg>`,
  };
  // 等合并 (A0, 19:5x): a step whose page is still in a pull request keeps its place, said plainly, until it is merged
  const introWait = pr => `<div class="intro-wait"><span>等 ${esc(pr)} 合并后补上</span></div>`;
  // the steps; setup: only when there is no profile yet; tab: which place of the tab bar (今日 练习 能力 单词 我的), -1 all
  function introSteps(setup) {
    const left = typeof KNOW === 'object' && KNOW.side() === 'left';
    const all = [
      { id: 'hello', setup: true },
      { id: 'goals', setup: true, ask: true },
      { id: 'aim', setup: true, ask: true },
      { id: 'tabs', tab: -1, t: '底下五个地方', d: '今日、练习、能力、单词、我的。每天打开先看「今日」，别的随时点过去。', art: INTRO_ART.tabs },
      { id: 'today', tab: 0, wait: '#442', t: '每天从「今日」开始', d: '今天的计划从上往下做，做完一项打一个勾；也能换成卡片的样子，长按调整顺序。' },
      { id: 'practice', tab: 1, t: '练习：想练哪样点哪样', d: '语法、听和读、说和写、单词、考试分成几块。最上面「今天建议」告诉你先练什么。', art: INTRO_ART.practice },
      { id: 'exam', tab: 1, t: '考试练习', d: '中考高考、四六级、考研、专四专八、雅思，每套 12–20 分钟限时做。设好「我的考试」就排在最前面。', art: INTRO_ART.exam },
      { id: 'radar', tab: 2, t: '能力：看看差在哪', d: '听力、阅读、词汇、语法、口语、写作六项，每项测 3–8 分钟。离目标最远的那项，每天会多练一点。', art: INTRO_ART.radar },
      { id: 'words', tab: 3, t: '单词和错题本', d: `每天要复习的和新词都在「单词」，${left ? '左' : '右'}滑认识。做错的题会进「错题本」，过几天再考你一次。`, art: INTRO_ART.words(left) },
      { id: 'me', tab: 4, t: '我的', d: '学习目标、朗读声音、提醒都在这里。「账号和隐私」「帮助」收在最下面，点开才展开。', art: INTRO_ART.me },
      { id: 'growth', tab: 4, t: '我的进步', d: '只和上个月的自己比：学了几天、读了多少词、快到哪个里程碑。在「我的」最上面点开。', art: INTRO_ART.growth },
      { id: 'report', tab: 4, wait: '#465', t: '周报', d: '最近 7 天学了什么、哪里进步了，一页看完。' },
      { id: 'habits', tab: 4, wait: '使用习惯', t: '使用习惯', d: '「认识」放哪边、字号、单词读音这些，在「我的 → 使用习惯」一处改。' },
    ];
    return setup ? all : all.filter(s => !s.setup);
  }
  const INTRO = { el: null, steps: [], i: 0, dir: 1, done: null, prev: null, st: null, again: false, busy: false };
  // where it was left (this browser): the step's id and whose it was
  const introWho = () => (S.user ? 'u' + S.user.id : 'guest');
  function introLeftAt() { const a = load('flow-intro-at'); return a && a.who === introWho() ? a.id : ''; }

  // opts: { setup: from 欢迎, again: 我的 → 帮助, from: a step's id to go on from }; done(result, step, again)
  function introStart(opts, done) {
    if (INTRO.el) return;
    const steps = INTRO.steps = introSteps(!!opts.setup);
    INTRO.done = done; INTRO.again = !!opts.again; INTRO.prev = document.activeElement;
    INTRO.i = Math.max(0, steps.findIndex(s => s.id === opts.from));
    INTRO.st = INTRO.st || { goals: [], exam: '', target: '', days: 0, picked: false, dayPicked: false };
    const el = INTRO.el = document.createElement('div');
    el.className = 'intro'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); el.setAttribute('aria-labelledby', 'introT'); el.tabIndex = -1;
    // the tab bar's own icons and names, in its place at the bottom (nothing to tap: it only shows where things are)
    const tabs = [...document.querySelectorAll('.tabs a')].map(a => `<span class="intro-tab">${a.querySelector('svg') ? a.querySelector('svg').outerHTML : ''}<span>${esc(a.textContent.trim())}</span></span>`).join('');
    el.innerHTML = `<div class="intro-top"><button class="intro-back" type="button" data-intro="back" aria-label="上一步" data-tap="intro-back"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg></button>
        <span class="intro-prog" aria-hidden="true"><i></i></span>
        <button class="intro-skip" type="button" data-intro="skip" data-tap="intro-skip">跳过</button></div>
      <div class="intro-stage"></div>
      <div class="intro-tabs" aria-hidden="true"><span class="intro-pill"></span>${tabs}</div>`;
    document.body.appendChild(el); document.body.classList.add('introing');
    el.addEventListener('click', introClick);
    el.addEventListener('keydown', introKey);
    // a swipe sideways goes on or back (not on the steps that ask something: a list there scrolls)
    let t0 = null;
    const stage = el.querySelector('.intro-stage');
    stage.addEventListener('touchstart', e => { const p = e.touches[0]; t0 = { x: p.clientX, y: p.clientY }; }, { passive: true });
    stage.addEventListener('touchend', e => {
      if (!t0) return; const p = e.changedTouches[0], dx = p.clientX - t0.x, dy = p.clientY - t0.y; t0 = null;
      if (Math.abs(dx) < 56 || Math.abs(dx) < Math.abs(dy) * 1.6 || INTRO.steps[INTRO.i].ask) return;
      if (dx < 0) introNext(); else introGo(INTRO.i - 1);
    }, { passive: true });
    introShow(true);
    requestAnimationFrame(() => requestAnimationFrame(() => { if (INTRO.el === el) el.classList.add('in'); }));
  }
  function introClick(e) {
    const b = e.target.closest('[data-intro]'); if (!b || b.disabled) return;
    const a = b.dataset.intro;
    if (a === 'skip') introEnd('skip');
    else if (a === 'back') introGo(INTRO.i - 1);
    else if (a === 'next') introNext();
    else if (a === 'login' || a === 'reg') { introEnd('later'); openLogin('', a === 'reg' ? 'reg' : ''); }
  }
  function introKey(e) {
    const el = INTRO.el; if (!el) return;
    if (e.key === 'Escape') { e.preventDefault(); introEnd('skip'); return; }
    const ask = INTRO.steps[INTRO.i].ask;
    if (!ask && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) { e.preventDefault(); if (e.key === 'ArrowRight') introNext(); else introGo(INTRO.i - 1); return; }
    if (e.key !== 'Tab') return;  // the focus stays in it while it is open
    const bs = [...el.querySelectorAll('.intro-top button, .intro-step:not(.out) button')].filter(b => !b.hidden && !b.disabled && b.offsetParent !== null);
    if (!bs.length) return;
    const k = bs.indexOf(document.activeElement);
    e.preventDefault(); bs[(k + (e.shiftKey ? bs.length - 1 : 1) + bs.length) % bs.length].focus();
  }

  // one step: its page drawn, the one before slid out (forward: to the left), the tab bar's mark moved under its place
  function introShow(first) {
    const el = INTRO.el, steps = INTRO.steps, s = steps[INTRO.i], n = steps.length, last = INTRO.i === n - 1;
    save('flow-intro-at', { id: s.id, who: introWho() });  // closed here, the next opening goes on from this step
    const stage = el.querySelector('.intro-stage'), old = stage.querySelector('.intro-step:not(.out)');
    // between two steps of the same kind (picture, title, sentence, button) only the picture and the words move: the
    // button stays where it is, its label changing (08-intro.css .same)
    stage.classList.toggle('same', !!old && !s.setup && !old.classList.contains('ask') && !old.querySelector('.intro-mark'));
    const page = document.createElement('section');
    page.className = 'intro-step' + (s.ask ? ' ask' : '') + (first ? '' : ' enter');
    page.style.setProperty('--dir', String(INTRO.dir));
    page.innerHTML = introStepHTML(s, last);
    stage.appendChild(page);
    if (s.ask) introWire(page, s);
    if (old) {
      old.style.setProperty('--dir', String(INTRO.dir)); old.classList.add('out'); old.setAttribute('aria-hidden', 'true');
      old.querySelectorAll('button').forEach(b => b.setAttribute('tabindex', '-1'));
      setTimeout(() => old.remove(), REDUCED ? 0 : 280);
    }
    requestAnimationFrame(() => requestAnimationFrame(() => { page.classList.remove('enter'); page.classList.add('seen'); }));
    // the top: back from the second step on; how far along, a bar (no numbers to count down)
    // (back into the steps that ask is not offered once the profile is saved: 我的 → 学习目标 changes it)
    el.querySelector('.intro-back').hidden = INTRO.i === 0 || (!s.setup && steps[INTRO.i - 1].setup && hasProfile());
    el.querySelector('.intro-prog i').style.transform = `scaleX(${(INTRO.i + 1) / n})`;
    // the tab bar: shown from the first place on; its mark under this step's place (all of them in turn on 底下五个地方)
    const tabs = el.querySelector('.intro-tabs'), pill = el.querySelector('.intro-pill'), on = s.tab == null ? null : s.tab;
    tabs.classList.toggle('show', on != null);
    tabs.classList.toggle('sweep', on === -1);
    pill.style.transform = `translateX(${Math.max(0, on || 0) * 100}%)`;
    tabs.querySelectorAll('.intro-tab').forEach((t, k) => t.classList.toggle('on', on === k));
    // the focus: on the dialog when it opens (a screen reader hears its name; no ring drawn on the button), then on each
    // step's button, so 下一步 is one Enter away
    const go = page.querySelector('.intro-next');
    if (first) el.focus({ preventScroll: true }); else if (go) go.focus({ preventScroll: true });
    if (!first || INTRO.i) announce(`第 ${INTRO.i + 1} 步，共 ${n} 步：${page.querySelector('.intro-t').textContent}。${(page.querySelector('.intro-d') || {}).textContent || ''}`);
  }
  function introStepHTML(s, last) {
    const next = (label, dis) => `<button class="btn primary block intro-next" type="button" data-intro="next" data-tap="intro-next"${dis ? ' disabled' : ''}>${label}</button>`;
    if (s.id === 'hello') {
      return `<div class="intro-body"><div class="intro-mark" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>
        <h2 class="intro-t intro-big" id="introT">欢迎来到语流</h2>
        <p class="intro-d" id="introD">每天十来分钟，听、读、说、背单词，跟着计划一点点往前走。先用半分钟定个目标。</p>
        ${next('开始')}
        ${S.user ? '' : `<div class="intro-acct"><button type="button" data-intro="reg" data-tap="intro-reg">注册账号</button><button type="button" data-intro="login" data-tap="intro-login">已有账号？登录</button></div>`}</div>`;
    }
    const M = S.meta || {}, st = INTRO.st;
    if (s.id === 'goals') {
      const goals = [...(M.goals || [])].sort((a, b) => (b.id === 'exam') - (a.id === 'exam'));
      return `<div class="intro-body wg"><h2 class="intro-t" id="introT">你学英语主要为了什么？</h2>
        <p class="intro-d" id="introD">可以多选，最多 3 个，第一个选的算主要目标。</p>
        <div class="intro-opts wg-goals" role="group" aria-labelledby="introT">${goals.map(g => `<button class="opt" type="button" data-ig="${esc(g.id)}" aria-pressed="${st.goals.includes(g.id)}">
          <span class="l">${esc(g.label)}</span><span class="d">${esc((M.goal_hints || {})[g.id] || '')}</span><span class="main" hidden>主要</span></button>`).join('')}</div>
        <div class="intro-exam" id="introExam" hidden><h3 class="intro-h" id="introExamH">准备哪个考试？</h3>
          <div class="chips" role="radiogroup" aria-labelledby="introExamH">${(M.exams || []).map(x => `<button class="chip" type="button" role="radio" data-ie="${esc(x.id)}" aria-checked="${x.id === st.exam}">${esc(x.short)}</button>`).join('')}</div></div>
        ${next('下一步', !st.goals.length)}<p class="intro-need" id="introNeed" aria-live="polite">${st.goals.length ? '' : '先选一个'}</p></div>`;
    }
    if (s.id === 'aim') {
      return `<div class="intro-body wg"><h2 class="intro-t" id="introT">想达到什么水平？</h2>
        <p class="intro-d" id="introD">按你的目标推荐了一档，可以改。现在的水平不用先测，以后在「能力」里测一下更准。</p>
        <div class="intro-opts wg-targets" role="radiogroup" aria-labelledby="introT">${(M.targets || []).map(x => `<button class="opt" type="button" role="radio" data-it="${esc(x.id)}" aria-checked="false">
          <b>${esc(x.id)}</b><span class="d">${esc(x.label)}</span><span class="rec" hidden>推荐</span></button>`).join('')}</div>
        <h3 class="intro-h" id="introDaysH">一周大概能学几天？</h3>
        <div class="chips intro-days" role="radiogroup" aria-labelledby="introDaysH">${[2, 3, 4, 5, 6, 7].map(d => `<button class="chip" type="button" role="radio" data-id="${d}" aria-checked="false">${d} 天</button>`).join('')}</div>
        ${next('下一步')}</div>`;
    }
    return `<div class="intro-body">${s.wait ? introWait(s.wait) : `<div class="intro-art" aria-hidden="true">${s.art}</div>`}
      <h2 class="intro-t" id="introT">${esc(s.t)}</h2><p class="intro-d" id="introD">${esc(s.d)}</p>
      ${next(last ? (INTRO.again ? '看完了' : '开始学习') : '下一步')}</div>`;
  }
  // the steps that ask: the same choices and rules as the one-page form (09-start.js welcome)
  function introWire(page, s) {
    const M = S.meta || {}, st = INTRO.st;
    const hasExam = () => st.goals.includes('exam');
    if (s.id === 'goals') {
      const sync = () => {
        page.querySelectorAll('[data-ig]').forEach(b => {
          const on = st.goals.includes(b.dataset.ig), main = on && st.goals.length > 1 && b.dataset.ig === st.goals[0];
          b.setAttribute('aria-pressed', String(on)); b.querySelector('.main').hidden = !main;
        });
        page.querySelectorAll('[data-ie]').forEach(b => b.setAttribute('aria-checked', String(b.dataset.ie === st.exam)));
        page.querySelector('#introExam').hidden = !hasExam();
        page.querySelector('.intro-next').disabled = !st.goals.length || (hasExam() && !st.exam);
        page.querySelector('#introNeed').textContent = !st.goals.length ? '先选一个' : hasExam() && !st.exam ? '再选一个考试' : '';
      };
      page.querySelectorAll('[data-ig]').forEach(b => b.onclick = () => {
        const g = b.dataset.ig;
        if (st.goals.includes(g)) st.goals = st.goals.filter(x => x !== g);
        else if (st.goals.length >= 3) { toast('最多选 3 个，先去掉一个再选'); return; }
        else st.goals = st.goals.concat(g);
        if (g === 'exam' && hasExam() && !st.exam && M.exams && M.exams.length === 1) st.exam = M.exams[0].id;
        sync();
      });
      page.querySelectorAll('[data-ie]').forEach(b => b.onclick = () => { st.exam = b.dataset.ie; sync(); });
      sync();
    } else if (s.id === 'aim') {
      const suggest = () => (M.target_for || {})[hasExam() && st.exam ? st.exam : st.goals[0]] || 'B1';
      if (!st.picked) st.target = suggest();
      if (!st.dayPicked) st.days = hasExam() ? 5 : 4;
      const sync = () => {
        page.querySelectorAll('[data-it]').forEach(b => { b.setAttribute('aria-checked', String(b.dataset.it === st.target)); b.querySelector('.rec').hidden = b.dataset.it !== suggest(); });
        page.querySelectorAll('[data-id]').forEach(b => b.setAttribute('aria-checked', String(Number(b.dataset.id) === st.days)));
      };
      page.querySelectorAll('[data-it]').forEach(b => b.onclick = () => { st.target = b.dataset.it; st.picked = true; sync(); });
      page.querySelectorAll('[data-id]').forEach(b => b.onclick = () => { st.days = Number(b.dataset.id); st.dayPicked = true; sync(); });
      sync();
    }
  }
  function introGo(i) {
    if (!INTRO.el || INTRO.busy || i < 0 || i >= INTRO.steps.length || i === INTRO.i) return;
    if (i < INTRO.i && INTRO.steps[i].setup && !INTRO.steps[INTRO.i].setup && hasProfile()) return;
    INTRO.dir = i > INTRO.i ? 1 : -1; INTRO.i = i; introShow(false);
  }
  async function introNext() {
    const s = INTRO.steps[INTRO.i];
    if (INTRO.i === INTRO.steps.length - 1) { introEnd('done'); return; }
    if (s.id === 'aim') {  // the profile, as the one-page form saves it; then 今日 is drawn under the steps still to come
      const st = INTRO.st, exam = st.goals.includes('exam') ? st.exam : '';
      const prof = { goal: st.goals[0], goals: st.goals, target: st.target, level: S.placed || below(st.target), level_source: S.placed ? 'placed' : 'guess',
                     themes: [], minutes: 10, exam, exam_date: '', weekly_goal: st.days };
      const b = INTRO.el.querySelector('.intro-step:not(.out) .intro-next'); INTRO.busy = true; if (b) b.disabled = true;
      try { await welcomeSave(prof, false); } catch (x) { INTRO.busy = false; if (b) b.disabled = false; toast(x.message); return; }
      INTRO.busy = false;
      if (location.hash !== '#/') location.hash = '#/';
    }
    introGo(INTRO.i + 1);
  }
  // result: 'done' (the last step), 'skip', or 'later' (to 登录 / 注册: the steps go on after it, from where they were)
  function introEnd(result) {
    const el = INTRO.el; if (!el) return;
    const s = INTRO.steps[INTRO.i], step = INTRO.i + 1;
    INTRO.el = null; el.classList.remove('in'); document.body.classList.remove('introing');
    setTimeout(() => el.remove(), REDUCED ? 0 : 300);
    if (result !== 'later') save('flow-intro-at', null);
    if (INTRO.prev && INTRO.prev.isConnected && result !== 'done') { try { INTRO.prev.focus({ preventScroll: true }); } catch (e) { /* gone */ } }
    const cb = INTRO.done; INTRO.done = null;
    if (cb) cb(result, step, s);
  }

  /* 带着做第一步: a soft ring around the button meant and a short line by it. The page stays usable: tapping that button
     is the next step (the ring goes, the page it opens may have one more); 知道了, or going elsewhere, ends it. */
  const COACH = { el: null, at: null, then: '' };
  function coach(sels, title, text) {
    coachEnd();
    const at = sels.map(q => document.querySelector(q)).find(x => x && x.getBoundingClientRect().width > 0);
    if (!at) return false;
    const fixed = getComputedStyle(at).position === 'fixed' || at.closest('.mini-player, .tabs');
    if (!fixed) at.scrollIntoView({ block: 'center', behavior: 'auto' });
    const el = COACH.el = document.createElement('div');
    el.className = 'coach';
    el.innerHTML = `<div class="coach-ring" aria-hidden="true"></div><div class="coach-tip" role="note"><b>${esc(title)}</b><p>${esc(text)}</p><button class="coach-x" type="button" data-tap="coach-ok">知道了</button></div>`;
    document.body.appendChild(el); document.body.classList.add('coaching'); COACH.at = at;
    el.querySelector('.coach-x').onclick = () => { COACH.then = ''; coachEnd(); };
    at.addEventListener('click', coachEnd, { once: true });
    addEventListener('resize', coachPlace); addEventListener('scroll', coachPlace, { passive: true });
    coachPlace();
    requestAnimationFrame(() => requestAnimationFrame(() => { if (COACH.el === el) el.classList.add('in'); }));
    announce(`${title}。${text}`);
    return true;
  }
  // the ring follows the button with transform only (08-intro.css): its size once, its place as the page scrolls
  function coachPlace() {
    const el = COACH.el; if (!el) return;
    if (!COACH.at.isConnected) { coachEnd(); return; }
    const ring = el.querySelector('.coach-ring'), tip = el.querySelector('.coach-tip'), r = COACH.at.getBoundingClientRect();
    const pad = 6, gap = 14, W = innerWidth, H = innerHeight, w = tip.offsetWidth, h = tip.offsetHeight;
    ring.style.width = r.width + 2 * pad + 'px'; ring.style.height = r.height + 2 * pad + 'px';
    ring.style.transform = `translate(${Math.round(r.left - pad)}px,${Math.round(r.top - pad)}px)`;
    const left = Math.min(Math.max(16, r.left + r.width / 2 - w / 2), W - w - 16);
    const top = r.bottom + pad + gap + h <= H - 8 ? r.bottom + pad + gap : Math.max(8, r.top - pad - gap - h);
    tip.style.transform = `translate(${Math.round(left)}px,${Math.round(top)}px)`;
  }
  function coachEnd() {
    const el = COACH.el; if (!el) return;
    COACH.el = null; COACH.at = null; document.body.classList.remove('coaching');
    removeEventListener('resize', coachPlace); removeEventListener('scroll', coachPlace);
    el.classList.remove('in'); setTimeout(() => el.remove(), REDUCED ? 0 : 300);
  }
  // after each page (02-shell.js, with tourMaybe): the page the first step opened gets its one ring
  function coachFollow() {
    if (COACH.el && !COACH.at.isConnected) coachEnd();
    if (!COACH.then) return;
    const want = COACH.then;
    if (want === 'step' && /^#\/m\/[^/]+(\/listen)?$/.test(location.hash)) {
      COACH.then = '';
      setTimeout(() => coach(['.mini-player #playAll', '#playAll'], '先听一遍', '点「播放全文」，跟着亮起来的句子听。听完点页面最下面的「听完了，去读」。'), REDUCED ? 0 : 450);
    } else if (want === 'step' && location.hash !== '#/') COACH.then = '';
  }
  // the steps over: on 今日, the plan's own button
  function introThen(result) {
    if (result !== 'done') return;
    COACH.then = 'step';
    const ring = () => { if (!coach(['#view .today-plan .go-next', '#view .go-next'], '从这里开始', '点它开始今天的第一项，做完会自动打勾。')) COACH.then = ''; };
    if (location.hash !== '#/') { location.hash = '#/'; setTimeout(ring, REDUCED ? 300 : 700); } else setTimeout(ring, REDUCED ? 0 : 380);
  }
