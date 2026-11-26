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
  const INTRO = { el: null, steps: [], i: 0, done: null, prev: null, st: null, again: false, busy: false, tab: null, demo: 0, res: 0 };
  // how it moves (B9 and A0, 2026-11-26: 「新手引导是要有流畅的动画的哦」): both steps at once, fast then slow
  const INTRO_EASE = 'cubic-bezier(.2,.8,.2,1)', INTRO_MS = 300;
  // where it was left (this browser): the step's id and whose it was
  const introWho = () => (S.user ? 'u' + S.user.id : 'guest');
  function introLeftAt() { const a = load('flow-intro-at'); return a && a.who === introWho() ? a.id : ''; }
  const introTour = s => !s.setup;  // a step of the places: picture, title, sentence, and the one shared button

  // opts: { setup: from 欢迎, again: 我的 → 帮助, from: a step's id to go on from }; done(result, step, again)
  function introStart(opts, done) {
    if (INTRO.el) return;
    const steps = INTRO.steps = introSteps(!!opts.setup);
    INTRO.done = done; INTRO.again = !!opts.again; INTRO.prev = document.activeElement;
    INTRO.i = Math.max(0, steps.findIndex(s => s.id === opts.from)); INTRO.tab = null; INTRO.busy = false;
    INTRO.st = INTRO.st || { goals: [], exam: '', target: '', days: 0, picked: false, dayPicked: false };
    const el = INTRO.el = document.createElement('div');
    el.className = 'intro'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); el.setAttribute('aria-labelledby', 'introT'); el.tabIndex = -1;
    // the tab bar's own icons and names, in its place at the bottom (nothing to tap: it only shows where things are)
    const tabs = [...document.querySelectorAll('.tabs a')].map(a => `<span class="intro-tab">${a.querySelector('svg') ? a.querySelector('svg').outerHTML : ''}<span>${esc(a.textContent.trim())}</span></span>`).join('');
    el.innerHTML = `<div class="intro-top"><button class="intro-back" type="button" data-intro="back" aria-label="上一步" data-tap="intro-back"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg></button>
        <span class="intro-prog" aria-hidden="true"><i></i></span>
        <button class="intro-skip" type="button" data-intro="skip" data-tap="intro-skip">跳过</button></div>
      <div class="intro-stage"><div class="intro-go"><button class="btn primary block intro-next" type="button" data-intro="next" data-tap="intro-next">下一步</button></div></div>
      <div class="intro-tabs" aria-hidden="true"><span class="intro-pill"></span>${tabs}</div>`;
    document.body.appendChild(el); document.body.classList.add('introing');
    el.addEventListener('click', introClick);
    el.addEventListener('keydown', introKey);
    introDragWire(el.querySelector('.intro-stage'));
    addEventListener('resize', introLayout);
    introLayout();
    const page = introMake(INTRO.i);
    el.querySelector('.intro-stage').insertBefore(page, el.querySelector('.intro-go'));
    introSettle(page, true);
    requestAnimationFrame(() => requestAnimationFrame(() => { if (INTRO.el === el) el.classList.add('in'); }));
  }
  function introClick(e) {
    const b = e.target.closest('[data-intro]'); if (!b || b.disabled) return;
    const a = b.dataset.intro;
    if (a === 'skip') introEnd('skip');
    else if (a === 'back') introBack();
    else if (a === 'next') introNext();
    else if (a === 'login' || a === 'reg') { introEnd('later'); openLogin('', a === 'reg' ? 'reg' : ''); }
  }
  function introKey(e) {
    const el = INTRO.el; if (!el) return;
    if (e.key === 'Escape') { e.preventDefault(); introEnd('skip'); return; }
    const ask = INTRO.steps[INTRO.i].ask;
    if (!ask && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) { e.preventDefault(); if (e.key === 'ArrowRight') introNext(); else introBack(); return; }
    if (e.key !== 'Tab') return;  // the focus stays in it while it is open
    const bs = [...el.querySelectorAll('.intro-top button, .intro-step.cur button, .intro-go.show button')].filter(b => !b.hidden && !b.disabled && b.offsetParent !== null);
    if (!bs.length) return;
    const k = bs.indexOf(document.activeElement);
    e.preventDefault(); bs[(k + (e.shiftKey ? bs.length - 1 : 1) + bs.length) % bs.length].focus();
  }

  // The places' steps keep their picture, title and sentence in one block from the same height, and share one button
  // under it, so the button never moves from step to step (the user: where the eye and the thumb already are): the
  // block's height is the tallest of them on this screen, the block and the button together in the middle.
  function introLayout() {
    const el = INTRO.el; if (!el) return;
    const stage = el.querySelector('.intro-stage'), probe = document.createElement('div');
    probe.className = 'intro-step intro-place intro-probe'; probe.setAttribute('aria-hidden', 'true');
    probe.innerHTML = INTRO.steps.filter(introTour).map(s => introStepHTML(s)).join('');
    stage.appendChild(probe);
    INTRO.res = Math.max(...[...probe.querySelectorAll('.intro-body')].map(b => b.offsetHeight), 0);
    probe.remove();
    const top = Math.max(12, Math.round((stage.clientHeight - (INTRO.res + 24 + 52)) / 2 - innerHeight * 0.04));
    stage.style.setProperty('--gtop', top + 'px');
    el.querySelector('.intro-go').style.top = top + INTRO.res + 24 + 'px';
  }
  // one step's page (not yet the current one: no ids, not wired)
  function introMake(i) {
    const s = INTRO.steps[i], page = document.createElement('section');
    page.className = 'intro-step' + (s.ask ? ' ask' : '') + (introTour(s) ? ' intro-place' : '');
    page.dataset.k = String(i);
    page.innerHTML = introStepHTML(s);
    introArtPrep(page);
    return page;
  }
  // the lines of a picture are drawn: each stroke from nothing to its whole length (stroke-dashoffset, on this small
  // picture only; B9), its group's delay after the one before
  function introArtPrep(page) {
    if (REDUCED) return;
    page.querySelectorAll('.intro-art .fr, .intro-art .hl, .intro-art .lns, .intro-art .axis, .intro-art .arr').forEach(x => {
      let len = 0; try { len = Math.ceil(x.getTotalLength()); } catch (e) { len = 0; }
      if (!len) return;
      const g = x.closest('.d1, .d2, .d3'), k = g ? Number(g.className.baseVal.match(/\bd(\d)\b/)[1]) : 0;
      x.style.strokeDasharray = `${len} ${len + 40}`; x.style.strokeDashoffset = String(len + 20);
      x.style.setProperty('--dl', 60 + k * 70 + 'ms'); x.classList.add('draw');
    });
  }
  // the step now on screen: its ids and wiring, the top bar, the tab bar's mark, the shared button, the focus
  function introSettle(page, first) {
    const el = INTRO.el, steps = INTRO.steps, s = steps[INTRO.i], n = steps.length, last = INTRO.i === n - 1;
    save('flow-intro-at', { id: s.id, who: introWho() });  // closed here, the next opening goes on from this step
    el.querySelectorAll('.intro-step').forEach(p => { if (p !== page) p.remove(); });
    page.classList.add('cur', 'seen'); page.removeAttribute('aria-hidden');
    page.style.transition = page.style.transform = page.style.opacity = '';
    el.querySelectorAll('#introT, #introD').forEach(x => x.removeAttribute('id'));
    const t = page.querySelector('.intro-t'), d = page.querySelector('.intro-d');
    if (t) t.id = 'introT'; if (d) d.id = 'introD';
    if (s.ask && !page.dataset.wired) { introWire(page, s); page.dataset.wired = '1'; }
    // the top: back from the second step on (not back into the choices once they are saved: 我的 → 学习目标 changes
    // them); how far along, a bar (no numbers to count down)
    el.querySelector('.intro-back').hidden = INTRO.i === 0 || !introCanGo(INTRO.i - 1);
    introBars(INTRO.i, null, 0);
    // the shared button: on the places' steps; its label on the last
    const go = el.querySelector('.intro-go'), tour = introTour(s);
    go.classList.toggle('show', tour);
    go.querySelector('button').textContent = last ? (INTRO.again ? '看完了' : '开始学习') : '下一步';
    go.querySelector('button').tabIndex = tour ? 0 : -1;
    // the focus: on the dialog when it opens (a screen reader hears its name; no ring drawn on a button), then on the
    // step's button, so 下一步 is one Enter away
    const b = tour ? go.querySelector('button') : page.querySelector('.intro-next');
    if (first) el.focus({ preventScroll: true }); else if (b) b.focus({ preventScroll: true });
    if (!first || INTRO.i) announce(`第 ${INTRO.i + 1} 步，共 ${n} 步：${t ? t.textContent : ''}。${d ? d.textContent : ''}`);
    introDemo(page);
  }
  // the progress bar and the tab bar's mark: at step i, or part of the way (p, 0–1) to step j while a finger drags
  function introBars(i, j, p) {
    const el = INTRO.el, steps = INTRO.steps, n = steps.length;
    const prog = el.querySelector('.intro-prog i'), pill = el.querySelector('.intro-pill'), tabs = el.querySelector('.intro-tabs');
    const dragging = j != null;
    prog.style.transition = pill.style.transition = dragging ? 'none' : '';
    prog.style.transform = `scaleX(${(i + 1 + (dragging ? (j - i) * p : 0)) / n})`;
    const on = steps[i].tab == null ? null : steps[i].tab, to = dragging && steps[j].tab != null ? steps[j].tab : null;
    if (dragging) {  // the mark between two places follows the finger
      if (on != null && on >= 0 && to != null && to >= 0) pill.style.transform = `translateX(${(on + (to - on) * p) * 100}%)`;
      return;
    }
    tabs.classList.toggle('show', on != null);
    tabs.classList.toggle('sweep', on === -1);
    tabs.classList.toggle('reveal', INTRO.tab === -1 && on != null && on >= 0); INTRO.tab = on;
    pill.style.transform = `translateX(${Math.max(0, on || 0) * 100}%)`;
    tabs.querySelectorAll('.intro-tab').forEach((x, k) => x.classList.toggle('on', on === k));
  }
  // what a picture shows (单词's card swiped, 能力's shape growing, a row opening, a bar growing): once after it is
  // drawn, then gently again every few seconds while the step stays
  const INTRO_DEMO = {
    swipe: l => [{ transform: 'none' }, { transform: `translateX(${l ? -14 : 14}px) rotate(${l ? -4 : 4}deg)`, offset: 0.4 }, { transform: `translateX(${l ? -14 : 14}px) rotate(${l ? -4 : 4}deg)`, offset: 0.6 }, { transform: 'none' }],
    'grow-in': () => [{ transform: 'scale(.82)' }, { transform: 'none' }],
    'grow-x': () => [{ transform: 'scaleX(.55)' }, { transform: 'none' }],
    open: () => [{ transform: 'scaleY(.7)', opacity: 0.6 }, { transform: 'none', opacity: 1 }],
  };
  function introDemo(page) {
    clearInterval(INTRO.demo); INTRO.demo = 0;
    if (REDUCED || !page.querySelector('.intro-art')) return;
    const parts = Object.keys(INTRO_DEMO).map(k => [k, page.querySelector('.intro-art .' + k)]).filter(x => x[1] && x[1].animate);
    if (!parts.length) return;
    const play = () => parts.forEach(([k, x]) => x.animate(INTRO_DEMO[k](x.classList.contains('l')), { duration: k === 'swipe' ? 1300 : 700, easing: INTRO_EASE }));
    INTRO.demo = setInterval(() => { if (INTRO.el && page.isConnected) play(); else clearInterval(INTRO.demo); }, 4000);
  }
  // can a step be reached from this one: not past the choices before they are made (下一步 saves them), not back into
  // them once saved
  function introGoalsOk() { const st = INTRO.st; return st.goals.length > 0 && (!st.goals.includes('exam') || !!st.exam); }
  function introCanGo(j) {
    const steps = INTRO.steps, s = steps[INTRO.i], t = steps[j];
    if (!t || j === INTRO.i) return false;
    if (j > INTRO.i) return s.id === 'goals' ? introGoalsOk() : s.id !== 'aim';
    return !(t.setup && !s.setup && hasProfile());
  }

  // to step j: both at once, the one on screen out to one side and the new one in from the other, sliding and fading
  // (300 ms, fast then slow); from where a finger left them (from: the offset in px), or from the start
  function introGo(j, from) {
    if (!INTRO.el || INTRO.busy || j < 0 || j >= INTRO.steps.length || j === INTRO.i) return;
    const stage = INTRO.el.querySelector('.intro-stage'), cur = stage.querySelector('.intro-step.cur'), dir = j > INTRO.i ? 1 : -1, W = stage.clientWidth;
    let nb = from && from.nb;
    if (!nb) {
      nb = introMake(j); nb.setAttribute('aria-hidden', 'true');
      stage.insertBefore(nb, stage.querySelector('.intro-go'));
      introPlace(nb, dir * W, 0);
      nb.offsetWidth;  // eslint-disable-line no-unused-expressions -- its start position drawn before it moves
      nb.classList.add('seen');
    }
    const moved = from ? Math.abs(from.dx) : 0, v = from ? Math.abs(from.v) : 0;
    const ms = REDUCED ? 0 : Math.round(Math.max(160, Math.min(INTRO_MS, v > 0.5 ? (W - moved) / v : INTRO_MS * (1 - moved / W) + 80)));
    const go = INTRO.el.querySelector('.intro-go'), keep = introTour(INTRO.steps[INTRO.i]) && introTour(INTRO.steps[j]);
    if (!keep) go.classList.remove('show');  // (the shared button stays put between two places' steps)
    INTRO.busy = true;
    introPlace(cur, -dir * W, 0, ms); introPlace(nb, 0, 1, ms);
    INTRO.i = j; introBars(j, null, 0);
    setTimeout(() => { INTRO.busy = false; if (INTRO.el) introSettle(nb, false); }, ms + 20);
  }
  function introPlace(x, px, o, ms) {
    x.style.transition = ms ? `transform ${ms}ms ${INTRO_EASE}, opacity ${ms}ms ${INTRO_EASE}` : 'none';
    x.style.transform = `translateX(${Math.round(px)}px)`; x.style.opacity = String(o);
  }
  function introBack() { if (introCanGo(INTRO.i - 1)) introGo(INTRO.i - 1); }

  // a finger: sideways (past 8 px; up and down still scrolls a list), the step follows it 1:1 with the next one beside
  // it; let go past a third of the screen, or with speed, and it turns, else it springs back. Nothing to turn to (the
  // first, the last, the choices not made): it gives a third of the way, then springs back.
  function introDragWire(stage) {
    let d = null;
    const W = () => stage.clientWidth;
    stage.addEventListener('touchstart', e => {
      if (INTRO.busy || e.touches.length > 1) { d = null; return; }
      const p = e.touches[0]; d = { x0: p.clientX, y0: p.clientY, lock: '', dx: 0, dir: 0, nb: null, can: false, pts: [[p.clientX, performance.now()]] };
    }, { passive: true });
    stage.addEventListener('touchmove', e => {
      if (!d || INTRO.busy) return;
      const p = e.touches[0], dx = p.clientX - d.x0, dy = p.clientY - d.y0;
      if (!d.lock) { if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return; d.lock = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y'; }
      if (d.lock !== 'x') return;
      if (e.cancelable) e.preventDefault();
      d.pts.push([p.clientX, performance.now()]); if (d.pts.length > 6) d.pts.shift();
      const dir = dx < 0 ? 1 : -1;
      if (dir !== d.dir) {  // which side: the step it would turn to, drawn beside this one
        if (d.nb) d.nb.remove();
        d.dir = dir; d.j = INTRO.i + dir; d.can = introCanGo(d.j); d.nb = null;
        if (d.can) {
          d.nb = introMake(d.j); d.nb.setAttribute('aria-hidden', 'true'); d.nb.classList.add('seen');
          stage.insertBefore(d.nb, stage.querySelector('.intro-go'));
        }
      }
      const cur = stage.querySelector('.intro-step.cur'), w = W(), p01 = Math.min(1, Math.abs(dx) / w);
      d.dx = d.can ? dx : dx / 3;
      introPlace(cur, d.dx, d.can ? 1 - 0.7 * p01 : 1);
      if (d.nb) introPlace(d.nb, d.dir * w + dx, 0.3 + 0.7 * p01);
      if (d.can) introBars(INTRO.i, d.j, p01);
    }, { passive: false });
    const end = cancel => {
      if (!d || d.lock !== 'x') { d = null; return; }
      const a = d.pts[0], b = d.pts[d.pts.length - 1], v = b[1] > a[1] ? (b[0] - a[0]) / (b[1] - a[1]) : 0, w = W();
      const turn = !cancel && d.can && (Math.abs(d.dx) > w * 0.3 || (Math.abs(v) > 0.5 && Math.sign(v) === -d.dir));
      const cur = stage.querySelector('.intro-step.cur'), x = d;
      d = null;
      if (turn) { introGo(x.j, { nb: x.nb, dx: x.dx, v }); return; }
      // back to where it was (a little give past it from the edge)
      const ms = REDUCED ? 0 : 280;
      cur.style.transition = `transform ${ms}ms cubic-bezier(.34,1.3,.64,1), opacity ${ms}ms ${INTRO_EASE}`;
      cur.style.transform = 'translateX(0px)'; cur.style.opacity = '1';
      if (x.nb) { introPlace(x.nb, x.dir * w, 0, ms); setTimeout(() => x.nb.remove(), ms + 20); }
      introBars(INTRO.i, null, 0);
    };
    stage.addEventListener('touchend', () => end(false));
    stage.addEventListener('touchcancel', () => end(true));
  }
  function introStepHTML(s) {
    const next = (label, dis) => `<button class="btn primary block intro-next" type="button" data-intro="next" data-tap="intro-next"${dis ? ' disabled' : ''}>${label}</button>`;
    if (s.id === 'hello') {
      return `<div class="intro-body"><div class="intro-mark" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>
        <h2 class="intro-t intro-big">欢迎来到语流</h2>
        <p class="intro-d">每天十来分钟，听、读、说、背单词，跟着计划一点点往前走。先用半分钟定个目标。</p>
        ${next('开始')}
        ${S.user ? '' : `<div class="intro-acct"><button type="button" data-intro="reg" data-tap="intro-reg">注册账号</button><button type="button" data-intro="login" data-tap="intro-login">已有账号？登录</button></div>`}</div>`;
    }
    const M = S.meta || {}, st = INTRO.st;
    if (s.id === 'goals') {
      const goals = [...(M.goals || [])].sort((a, b) => (b.id === 'exam') - (a.id === 'exam'));
      return `<div class="intro-body wg"><h2 class="intro-t">你学英语主要为了什么？</h2>
        <p class="intro-d">可以多选，最多 3 个，第一个选的算主要目标。</p>
        <div class="intro-opts wg-goals" role="group" aria-label="学英语为了什么，可以多选">${goals.map(g => `<button class="opt" type="button" data-ig="${esc(g.id)}" aria-pressed="${st.goals.includes(g.id)}">
          <span class="l">${esc(g.label)}</span><span class="d">${esc((M.goal_hints || {})[g.id] || '')}</span><span class="main" hidden>主要</span><svg class="ck" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-6.5"/></svg></button>`).join('')}</div>
        <div class="intro-exam" id="introExam" hidden><h3 class="intro-h" id="introExamH">准备哪个考试？</h3>
          <div class="chips" role="radiogroup" aria-labelledby="introExamH">${(M.exams || []).map(x => `<button class="chip" type="button" role="radio" data-ie="${esc(x.id)}" aria-checked="${x.id === st.exam}">${esc(x.short)}</button>`).join('')}</div></div>
        ${next('下一步', !st.goals.length)}<p class="intro-need" id="introNeed" aria-live="polite">${st.goals.length ? '' : '先选一个'}</p></div>`;
    }
    if (s.id === 'aim') {
      return `<div class="intro-body wg"><h2 class="intro-t">想达到什么水平？</h2>
        <p class="intro-d">按你的目标推荐了一档，可以改。现在的水平不用先测，以后在「能力」里测一下更准。</p>
        <div class="intro-opts wg-targets" role="radiogroup" aria-label="想达到什么水平">${(M.targets || []).map(x => `<button class="opt" type="button" role="radio" data-it="${esc(x.id)}" aria-checked="false">
          <b>${esc(x.id)}</b><span class="d">${esc(x.label)}</span><span class="rec" hidden>推荐</span></button>`).join('')}</div>
        <h3 class="intro-h" id="introDaysH">一周大概能学几天？</h3>
        <div class="chips intro-days" role="radiogroup" aria-labelledby="introDaysH">${[2, 3, 4, 5, 6, 7].map(d => `<button class="chip" type="button" role="radio" data-id="${d}" aria-checked="false">${d} 天</button>`).join('')}</div>
        ${next('下一步')}</div>`;
    }
    return `<div class="intro-body">${s.wait ? introWait(s.wait) : `<div class="intro-art" aria-hidden="true">${s.art}</div>`}
      <h2 class="intro-t">${esc(s.t)}</h2><p class="intro-d">${esc(s.d)}</p></div>`;
  }
  // the steps that ask: the same choices and rules as the one-page form (09-start.js welcome)
  function introWire(page, s) {
    const M = S.meta || {}, st = INTRO.st;
    page.addEventListener('click', e => {
      const b = e.target.closest('.opt, .chip');
      if (b && !REDUCED && b.animate) b.animate([{ transform: 'none' }, { transform: 'scale(.95)', offset: 0.35 }, { transform: 'none' }], { duration: 260, easing: 'cubic-bezier(.34,1.4,.64,1)' });
    });
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
  async function introNext() {
    const s = INTRO.steps[INTRO.i];
    if (!INTRO.el || INTRO.busy) return;
    if (INTRO.i === INTRO.steps.length - 1) { introEnd('done'); return; }
    if (s.id === 'goals' && !introGoalsOk()) return;
    if (s.id === 'aim') {  // the profile, as the one-page form saves it; then 今日 is drawn under the steps still to come
      const st = INTRO.st, exam = st.goals.includes('exam') ? st.exam : '';
      const prof = { goal: st.goals[0], goals: st.goals, target: st.target, level: S.placed || below(st.target), level_source: S.placed ? 'placed' : 'guess',
                     themes: [], minutes: 10, exam, exam_date: '', weekly_goal: st.days };
      const b = INTRO.el.querySelector('.intro-step.cur .intro-next'); INTRO.busy = true; if (b) b.disabled = true;
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
    clearInterval(INTRO.demo); INTRO.demo = 0; INTRO.busy = false; removeEventListener('resize', introLayout);
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
    // (placed by the outer two, coachPlace; the ring breathes and the card grows inside them)
    el.innerHTML = `<div class="coach-at" aria-hidden="true"><div class="coach-ring"></div></div>
      <div class="coach-tipat"><div class="coach-tip" role="note"><b>${esc(title)}</b><p>${esc(text)}</p><button class="coach-x" type="button" data-tap="coach-ok">知道了</button></div></div>`;
    document.body.appendChild(el); document.body.classList.add('coaching'); COACH.at = at;
    el.querySelector('.coach-x').onclick = () => { COACH.then = ''; coachEnd(); };
    at.addEventListener('click', coachEnd, { once: true });
    addEventListener('resize', coachPlace); addEventListener('scroll', coachPlace, { passive: true });
    coachPlace();
    requestAnimationFrame(() => requestAnimationFrame(() => { if (COACH.el === el) el.classList.add('in'); }));
    announce(`${title}。${text}`);
    return true;
  }
  // the ring follows the button with transform only (08-intro.css): its size once, its place as the page scrolls; the
  // card grows from the side of the button (its transform-origin there)
  function coachPlace() {
    const el = COACH.el; if (!el) return;
    if (!COACH.at.isConnected) { coachEnd(); return; }
    const at = el.querySelector('.coach-at'), tipat = el.querySelector('.coach-tipat'), tip = el.querySelector('.coach-tip'), r = COACH.at.getBoundingClientRect();
    const pad = 6, gap = 14, W = innerWidth, H = innerHeight, w = tip.offsetWidth, h = tip.offsetHeight;
    at.style.width = r.width + 2 * pad + 'px'; at.style.height = r.height + 2 * pad + 'px';
    at.style.transform = `translate(${Math.round(r.left - pad)}px,${Math.round(r.top - pad)}px)`;
    const left = Math.min(Math.max(16, r.left + r.width / 2 - w / 2), W - w - 16), below = r.bottom + pad + gap + h <= H - 8;
    const top = below ? r.bottom + pad + gap : Math.max(8, r.top - pad - gap - h);
    tipat.style.transform = `translate(${Math.round(left)}px,${Math.round(top)}px)`;
    tip.style.transformOrigin = `${Math.round(Math.min(w - 16, Math.max(16, r.left + r.width / 2 - left)))}px ${below ? '0' : '100%'}`;
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
