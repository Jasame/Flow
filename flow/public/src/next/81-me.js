  /* ---------- me: one grouped list, like a phone's settings; each row opens a page or a sheet ---------- */
  // A row: a link (to starts with # or /) or a button (to is its id); the value sits on the right, greyed.
  function grow(to, label, value, vid, tapKey) {
    const tag = /^(#|\/|https?:)/.test(to) ? 'a' : 'button';
    return `<${tag} class="grow" ${tag === 'a' ? `href="${to}"` : `type="button" id="${to}"`}${tapKey ? ` data-tap="${tapKey}"` : ''}><span class="t">${label}</span><span class="v small muted"${vid ? ` id="${vid}"` : ''}>${value || ''}</span><span class="go" aria-hidden="true">›</span></${tag}>`;
  }
  // 帮助 → 更多: the two rows that are not looked at every week (简洁化, the user's pick 2026-11-25)
  function moreSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">更多</h2><div class="glist">${grow('/about', '认识语流', '一页看完语流能帮你做什么', '', 'me-about')}${grow('/survey', '匿名问卷', '你想要什么样的英语学习网站', '', 'me-survey')}
      ${S.user ? grow('meTour', '再看一遍新手引导', '今日的几个主要按钮在哪', '', 'me-tour') : ''}</div>
      <button class="btn ghost" data-close type="button">关闭</button></div>`, card => {
      const t = card.querySelector('#meTour'); if (t) t.onclick = () => { closeSheet(); tourAgain(); };  // 08-tour.js
    });
  }
  // 我的 → 内测版: this 内测 version's number and when it went up, and what changed in it (the ledger's beta entry)
  function betaInfo() {
    fetch('/api/deploy-status', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(d => {
      const el = document.getElementById('meBetaVer'), t = d && d.started ? new Date(d.started) : null;
      if (el && d && d.tag) el.textContent = ` 现在是 ${d.tag}${t && !isNaN(t) ? `（${t.getMonth() + 1} 月 ${t.getDate()} 日 ${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')} 更新）` : ''}。`;
    }).catch(() => {});
    fetch('/api/next/updates', { credentials: 'same-origin' }).then(r => (r.ok ? r.json() : null)).then(x => {
      // the ledger's beta entry (语流 A3, updates_service): {changed, new, better, fixed}, each a list of {text, link?} —
      // 「用法变了」 (changed) first and marked; a link is always inside the site (#/…)
      const b = x && x.beta, el = document.getElementById('meBetaNew'); if (!el || !b) return;
      const item = (v, changed) => { const t = typeof v === 'string' ? v : (v && v.text) || '', link = v && typeof v === 'object' && /^#\//.test(v.link || '') ? v.link : '';
        return t ? `<li${changed ? ' class="beta-changed"' : ''}>${changed ? '<b>用法变了：</b>' : ''}${esc(t)}${link ? ` <a class="link" href="${esc(link)}">去看看</a>` : ''}</li>` : ''; };
      const lines = [...(b.changed || []).map(v => item(v, true)), ...[...(b.new || []), ...(b.better || []), ...(b.fixed || [])].map(v => item(v, false))].filter(Boolean).slice(0, 5);
      if (!lines.length) return;
      el.innerHTML = `<div class="small"><b>这一版内测改了什么</b></div><ul class="small">${lines.join('')}</ul>`; el.hidden = false;
    }).catch(() => {});
  }
  async function meView() {
    if (!S.meta) S.meta = await api('/api/next/meta');
    const p = (S.home && S.home.profile) || S.guest || {}, u = S.user, st = S.home && S.home.stats;
    const lv = S.meta.levels.find(l => l.id === p.level), goal = S.meta.goals.find(g => g.id === p.goal);
    const installed = HOME_APP;  // the home-screen app, an install, or one of Flow's apps: nothing to add to the desktop
    const groups = [
      u && ['进步', [grow('#/radar', '能力雷达', '', '', 'me-radar'), grow('#/growth', '我的进步', '', '', 'me-growth'), grow('#/report', '周报', '', '', 'me-report'), grow('#/cards/mistake', '错题本', '', '', 'me-mistake')]],
      ['设置', [grow('#/welcome/edit', '学习目标和水平', [goal && esc(goal.label), p.target && '目标 ' + p.target, lv && (p.target ? '现在 ' : '') + lv.id].filter(Boolean).join(' · ') || '未设置', '', 'me-level'),
        u ? grow('meExam', '我的考试', examLabel(p), 'meExamV', 'me-exam') : '', u ? grow('meHabit', '每周目标', `每周 ${(st && st.habit && st.habit.goal) || 4} 天`, 'meHabitV', 'me-habit') : '', u && !u.teacher ? grow('meClass', '班级', '<span class="spin"></span>', 'meClassV', 'me-class') : '', grow('meVoice', '朗读声音', VOICE_LABELS[S.voice] || VOICE_LABELS['us-f'], 'meVoiceV', 'me-voice'), WORD_CLIPS ? grow('meSound', '单词读音方式', soundLabel(), 'meSoundV', 'me-sound') : '', grow('meKnow', '「认识」放在', knowLabel(), 'meKnowV', 'me-know'), grow('meText', '外观', lookLabel(), 'meTextV', 'me-text'), grow('meRemind', '每天提醒', '', '', 'me-remind'),
        u ? grow('meMail', '每周进度邮件', weeklyMailLabel(), 'meMailV', 'me-weekly-mail') : '',
        installed ? '' : grow('meInstall', '添加到桌面', '', '', 'me-install')]],
      u && ['账号', [grow('bindMail', '邮箱', '<span class="spin"></span>', 'acctEmail'), grow('chPw', '修改密码'), grow('outAll', '退出所有设备'),
        grow('meAge', '年龄段', ageLabel(u && u.age), 'meAgeV', 'me-age'), grow('meStorage', '数据存放', '已同意 · 香港'), grow('#/guide/terms', '用户协议', '和隐私说明一起同意'), grow('meData', '导出我的数据', '', '', 'me-data'), grow('meDelete', '注销账号', '', '', 'me-delete')],
        '绑定邮箱后，可以用验证码登录，忘记密码时自己找回。30 天内来过就一直保持登录；在别人的手机或电脑上用完，记得退出。'],
      // 内测版 (flow.jasa.hk) only: what the line under the top bar said, kept here (the line can be closed): the
      // version and what changed in it (/api/deploy-status, /api/next/updates), 去正式版 (not in Flow's apps: it would
      // open the system browser), feedback
      BETA && ['内测版', [grow('#/feedback', '问题反馈', '', '', 'me-beta-feedback'),
        IN_FLOW_APP ? '' : grow(MAIN_SITE + '/', '去正式版', 'flowlang.cn', '', 'me-beta-main'), '<div class="beta-new" id="meBetaNew" hidden></div>'],
        '这里是语流的内测版（flow.jasa.hk），新功能先在这里试。账号和数据都和正式版分开，内测期间可能会清空。<span id="meBetaVer"></span>'],
      ['帮助', [grow('#/guide', '操作指南', '', '', 'me-guide'), grow('#/updates', '更新记录', '', '', 'me-updates'),grow('#/feedback', '问题反馈', '', '', 'me-feedback'), grow('#/guide/privacy', '隐私说明', '', '', 'me-privacy'), grow('meMore', '更多', '认识语流、匿名问卷、新手引导', '', 'me-more')]],
    ].filter(Boolean);
    view.innerHTML = `<div class="card flat me-head"><div class="me-id">${u ? `<span class="avatar" aria-hidden="true">${esc([...u.username][0].toUpperCase())}</span>` : ''}
        <div class="t"><h1 class="h1">${u ? esc(u.username) : '我的'}</h1><span class="small muted">${lv ? `${esc(lv.label)}（${lv.id}）` : '还没有设置水平'} · 每天 ${p.minutes || 10} 分钟</span></div></div>
        ${st ? `<div class="me-nums">${[[st.habit ? st.habit.done : st.week.filter(d => d.active).length, '本周学习天数'], [st.materials_done, '学完的材料'], [st.cards, '单词与表达']].map(([n, l]) => `<div><b>${n}</b><span class="tiny muted">${l}</span></div>`).join('')}</div>`
          : u ? '' : `<div class="stack-s"><span class="muted small">登录后才能保存进度、收藏表达和使用 AI。</span><div><button class="btn primary small" id="lg">登录 / 注册</button></div></div>`}</div>
      ${u ? '<div id="meTeach"></div>' : ''}
      ${groups.map(([h, rows, foot]) => `<section class="gsec" aria-label="${h}"><h2 class="ghead">${h}</h2><div class="glist">${rows.join('')}</div>${foot ? `<p class="tiny muted gfoot">${foot}</p>` : ''}</section>`).join('')}
      ${u ? '<div class="gsec me-out"><button class="grow danger" id="out" type="button"><span class="t">退出登录</span></button></div>' : ''}`;
    const lg = document.getElementById('lg'); if (lg) lg.onclick = () => openLogin();
    document.getElementById('meVoice').onclick = voiceSheet;
    if (document.getElementById('meSound')) document.getElementById('meSound').onclick = soundSheet;
    document.getElementById('meKnow').onclick = knowSheet;
    document.getElementById('meText').onclick = textSheet;
    const mh = document.getElementById('meHabit'); if (mh) mh.onclick = habitSheet;
    const me = document.getElementById('meExam'); if (me) me.onclick = () => examGoalSheet(() => meView());
    document.getElementById('meRemind').onclick = () => remindSheet(p.minutes || 10);
    const mm = document.getElementById('meMail'); if (mm) { mm.onclick = weeklyMailSheet; fillMailRow(); }  // 11-progress.js
    const mi = document.getElementById('meInstall'); if (mi) mi.onclick = installSheet;
    document.getElementById('meMore').onclick = moreSheet;
    if (BETA) betaInfo();
    if (u) {
      const mc = document.getElementById('meClass'); if (mc) mc.onclick = () => classSheet();  // a 老师账号 has no 班级 row
      meClass();
      const b = document.getElementById('bindMail'); b.disabled = true;
      api('/api/account').then(a => {
        const el = document.getElementById('acctEmail'); if (!el) return;
        el.textContent = a.email || '还没有绑定';
        if (a.mail_enabled) { b.disabled = false; b.setAttribute('aria-label', a.email ? '邮箱：' + a.email + '，点这里更换' : '绑定邮箱'); b.onclick = () => bindEmailSheet(a.email); }
        else if (!a.email) el.textContent += '（邮件服务暂未开启）';
      }).catch(() => { const el = document.getElementById('acctEmail'); if (el) el.textContent = ''; });
      document.getElementById('chPw').onclick = () => changePasswordSheet();
      document.getElementById('outAll').onclick = () => signOutEverywhere();
      document.getElementById('meData').onclick = dataSheet;
      document.getElementById('meAge').onclick = () => ageSheet(false);
      document.getElementById('meStorage').onclick = storageSheet;
      document.getElementById('meDelete').onclick = deleteAccountSheet;
      document.getElementById('out').onclick = async () => { await OUTBOX.flush(); try { await api('/api/logout', {}); } catch (e) { /* ignore */ } snapClear(); S.user = null; S.csrf = ''; await refreshHome(); toast('已退出'); route(); };
    }
  }
  // 字号和行距: the reading text (a material, the listening lines, review sentences, questions, the guide, meanings)
  // larger and with more room between lines; menus and buttons stay as they are. Kept on the phone (applyText, 02-shell.js).
  const TEXT_SIZES = [['m', '标准'], ['l', '大'], ['xl', '特大']], TEXT_LH = [['n', '标准'], ['w', '宽松']];
  function textLabel() { return [TEXT_SIZES.find(x => x[0] === TEXT.size)[1], TEXT.lh === 'w' ? '行距宽松' : ''].filter(Boolean).join(' · '); }
  const lookLabel = () => `${textLabel()} · ${accentLabel()}`;  // 外观: 字号、行距 and 主题色 (07-accent.js)
  function textSheet() {
    const chips = (list, key, cur) => list.map(([k, l]) => `<button class="chip" type="button" role="radio" data-${key}="${k}" aria-checked="${cur === k}">${l}</button>`).join('');
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">外观</h2>
      <div class="stack-s"><b>主题色</b><div class="chips" role="radiogroup" aria-label="主题色">${chips(ACCENTS, 'ac', accentNow())}</div>
        <span class="tiny muted">只换按钮、进度和链接的颜色；答对答错的颜色和标识不变。浅色、深色跟着手机的设置。${S.user ? '' : '登录后会记在账号上。'}</span></div>
      <div class="stack-s"><b>字号</b><div class="chips" role="radiogroup" aria-label="字号">${chips(TEXT_SIZES, 'ts', TEXT.size)}</div></div>
      <div class="stack-s"><b>行距</b><div class="chips" role="radiogroup" aria-label="行距">${chips(TEXT_LH, 'tl', TEXT.lh)}</div></div>
      <p class="text tsample">Reading a little every day is how a new language slowly becomes your own.</p>
      <p class="muted small">课文、听力句子、讲解和释义的字会变大，菜单和按钮不变。</p><button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      card.querySelectorAll('[data-ac]').forEach(b => b.onclick = async () => {
        card.querySelectorAll('[data-ac]').forEach(x => x.setAttribute('aria-checked', String(x === b)));
        await setAccent(b.dataset.ac);
        card.querySelectorAll('[data-ac]').forEach(x => x.setAttribute('aria-checked', String(x.dataset.ac === accentNow())));  // back, if it could not be saved
        const v = document.getElementById('meTextV'); if (v) v.textContent = lookLabel();
      });
      card.querySelectorAll('[data-ts], [data-tl]').forEach(b => b.onclick = () => {
        const k = 'ts' in b.dataset ? 'size' : 'lh'; TEXT[k] = b.dataset.ts || b.dataset.tl; save('flow-next-text', TEXT); applyText();
        card.querySelectorAll(k === 'size' ? '[data-ts]' : '[data-tl]').forEach(x => x.setAttribute('aria-checked', String(x === b)));
        const v = document.getElementById('meTextV'); if (v) v.textContent = lookLabel();
      });
    });
  }
  // iPhones and iPads: how words, examples and short sentences are played (01-audio-offline.js AUDIO / CLIP), and the
  // silence in front of a word in 标准. Kept on this phone: the app on the home screen keeps its own, and has no address
  // bar for ?audio= and ?lead= (the owner compares the two ways on an iPhone before the default is chosen).
  const SOUND_MODES = [['auto', '连续', '从第一个音开始放；连着点单词时，灵动岛会一直显示「语流 · 单词」，停下 20 秒后收起。（默认）'],
    ['compat', '标准', '每个词是一个前面留了一点静音的小音频，大部分单词不会出现在灵动岛上。「连续」没有声音时选这个。']];
  const soundLabel = () => AUDIO.mode() === 'compat' ? `标准 · 前面 ${AUDIO.lead()} 秒` : '连续';
  // 「认识」放在 (KNOW, 50-words.js): which side the 认识 button is on in the review and the vocabulary test
  const knowLabel = () => KNOW.side() === 'right' ? '右边' : '左边';
  function knowSheet() {
    const opts = [['right', '右边（默认）', '和大多数背词 App 一样，右手点着顺。往右滑是认识，往左滑是不认识。'], ['left', '左边', '往左滑是认识，往右滑是不认识。']];
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">「认识」放在</h2>
      <div class="choice two" role="radiogroup" aria-labelledby="sheetTitle">${opts.map(([k, t, d]) => `<button class="opt" type="button" role="radio" data-know="${k}" aria-checked="${KNOW.side() === k}" aria-pressed="${KNOW.side() === k}"><b>${t}</b><span class="small muted">${d}</span></button>`).join('')}</div>
      <p class="muted small">复习单词和测词汇量都跟着变：按钮的位置、滑动的方向，电脑上的按键（1 2 3 和 ← →）也按按钮在屏幕上的位置。只影响这台设备。</p>
      <h3 class="zones-h" id="zonesTitle">点卡片作答</h3>
      <div class="choice two" role="radiogroup" aria-labelledby="zonesTitle">${[[1, '开', '复习卡的左、中、右三块，和下面三个按钮一样（「认识」那边就是认识）。只翻面看答案，翻面后还是点按钮评分；点错了可以「撤销」。'], [0, '关', '只用下面的按钮、滑动和按键。']].map(([k, t, d]) => `<button class="opt" type="button" role="radio" data-zones="${k}" aria-checked="${KNOW.tap() === !!k}" aria-pressed="${KNOW.tap() === !!k}"><b>${t}</b><span class="small muted">${d}</span></button>`).join('')}</div>
      <p class="muted small">手机和平板默认开，用鼠标的电脑默认关。<button class="link small" type="button" id="zonesGuide">下次复习再看一次说明</button></p>
      <button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      card.querySelectorAll('[data-zones]').forEach(b => b.onclick = () => {
        KNOW.setTap(b.dataset.zones === '1');
        card.querySelectorAll('[data-zones]').forEach(x => { x.setAttribute('aria-checked', String(x === b)); x.setAttribute('aria-pressed', String(x === b)); });
        toast(KNOW.tap() ? '点卡片的左、中、右也能作答了' : '点卡片作答关了，只用按钮和滑动');
      });
      document.getElementById('zonesGuide').onclick = () => { try { localStorage.removeItem('flow-tap-guide'); } catch (e) { /* private mode */ } toast('下次复习时再看一次'); };
      card.querySelectorAll('[data-know]').forEach(b => b.onclick = () => {
        KNOW.set(b.dataset.know); save('flow-know-tip', 1);  // chosen here: the one-time tip of the move is not needed
        card.querySelectorAll('[data-know]').forEach(x => { x.setAttribute('aria-checked', String(x === b)); x.setAttribute('aria-pressed', String(x === b)); });
        const v = document.getElementById('meKnowV'); if (v) v.textContent = knowLabel();
        toast('「认识」放在' + knowLabel());
      });
    });
  }
  function soundSheet() {
    const leadChips = () => AUDIO.LEADS.map(v => `<button class="chip" type="button" data-lead="${v}" aria-pressed="${AUDIO.lead() === v}">${v} 秒${v === AUDIO.LEAD_DEFAULT ? '（默认）' : ''}</button>`).join('');
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">单词读音方式</h2>
      <div class="choice" role="radiogroup" aria-labelledby="sheetTitle">${SOUND_MODES.map(([k, t, d]) => `<button class="opt" type="button" role="radio" data-sound="${k}" aria-checked="${AUDIO.mode() === k}" aria-pressed="${AUDIO.mode() === k}"><b>${t}</b><span class="small muted">${d}</span></button>`).join('')}</div>
      <div class="stack-s" id="leadBox"><b class="small" id="leadTitle">「标准」时单词前面留的静音</b><div class="chips" role="group" aria-labelledby="leadTitle">${leadChips()}</div>
      <p class="tiny muted">开头还被吞，就选长一点；开头都全，可以选短一点，出现在灵动岛上的单词会更少。</p></div>
      <p class="muted small">两种方式在静音键打开时都能听到。只影响这台手机。</p><button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      const shown = () => { const v = document.getElementById('meSoundV'); if (v) v.textContent = soundLabel(); };
      card.querySelectorAll('[data-sound]').forEach(b => b.onclick = () => {
        AUDIO.setMode(b.dataset.sound);
        card.querySelectorAll('[data-sound]').forEach(x => { x.setAttribute('aria-checked', String(x === b)); x.setAttribute('aria-pressed', String(x === b)); });
        shown(); toast('单词读音方式：' + soundLabel());
      });
      card.querySelectorAll('[data-lead]').forEach(b => b.onclick = () => {
        AUDIO.setLead(Number(b.dataset.lead));
        card.querySelectorAll('[data-lead]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
        shown(); toast(`「标准」时单词前面留 ${AUDIO.lead()} 秒静音`);
      });
    });
  }
  function voiceSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">朗读声音</h2>${voiceChips(null)}
      <p class="muted small">语流里的读音和朗读都是 AI 合成的，不是真人录的：精选材料和单词用 Kokoro，其余（AI 的回复、口语情景、没有录音的句子）用 CosyVoice，都是自然人声。放声音的地方写着一行小灰字「读音由 AI 合成」或「朗读由 AI 合成」，喇叭多的列表里每个喇叭右上角有一个淡淡的「AI」。学一篇材料时，也可以在「听」这一步随时切换声音。</p><button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      card.querySelectorAll('[data-voice]').forEach(b => b.onclick = async () => {
        await setVoice(b.dataset.voice);
        card.querySelectorAll('[data-voice]').forEach(x => { x.setAttribute('aria-pressed', String(x === b)); x.setAttribute('aria-checked', String(x === b)); });
        const v = document.getElementById('meVoiceV'); if (v) v.textContent = VOICE_LABELS[b.dataset.voice];
        toast('朗读声音：' + VOICE_LABELS[b.dataset.voice]);
      });
    });
  }
  function remindSheet(minutes) {
    const ics = h => `/api/next/vocab/reminder.ics?kind=plan&hour=${h}&minutes=${minutes}`;
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">每天提醒</h2>
      <p class="muted small">加到手机日历：每天到点提醒你打开今天的计划。不用装 App、不用邮箱，iPhone 和安卓都能用。</p>
      <div class="row"><select id="mHour" aria-label="提醒时间">${Array.from({ length: 18 }, (_, k) => k + 6).map(h => `<option value="${h}" ${h === 20 ? 'selected' : ''}>每天 ${h}:00</option>`).join('')}</select>
        <a class="btn primary" id="mCal" href="${ics(20)}">加到手机日历</a></div>
      <p class="tiny muted">打开下载的文件，选「添加到日历」即可；不想要了就在日历里删掉这个日程。</p><button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      const hour = card.querySelector('#mHour'), cal = card.querySelector('#mCal');
      hour.onchange = () => { cal.href = ics(hour.value); };
    });
  }
  /* ---------- on the home screen: two steps for the phone in hand, or one tap where the browser offers it ---------- */
  const STANDALONE = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const IN_WECHAT = /MicroMessenger/i.test(navigator.userAgent);  // WeChat cannot install; its own bar says how to leave it
  function installKind() {
    const ua = navigator.userAgent, ipad = /iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);  // iPadOS says Mac
    if (IN_WECHAT && !/iPhone|iPod/.test(ua) && !ipad) return 'wechat';
    if (/iPhone|iPod/.test(ua) || ipad) return /CriOS|FxiOS|EdgiOS|OPiOS|MicroMessenger|QQ\//.test(ua) ? 'ios-other' : ipad ? 'ipad' : 'iphone';
    if (installPrompt) return 'prompt';
    return /Android/i.test(ua) ? 'android' : 'desktop';
  }
  addEventListener('appinstalled', () => { save('flow-installed', Date.now()); installPrompt = null; const n = document.getElementById('installNudge'); if (n) n.remove(); });
  // The 今日 notice: a phone browser (not WeChat, not already on the home screen) of a learner who has studied once.
  function installNudgeDue(h) {
    return !!(S.user && TOUCH && !IN_WECHAT && !STANDALONE() && !load('flow-installed') && h.stats && (h.stats.materials_done || 0) >= 1
      && Date.now() - (load('flow-install-later') || 0) > 30 * 864e5);
  }
  function installSheet() {
    const k = installKind(), share = '<svg class="ishare" viewBox="0 0 24 24" aria-label="分享按钮"><path d="M12 15V3M8 7l4-4 4 4"/><path d="M7 10H6v10h12V10h-1"/></svg>';
    const steps = {
      iphone: [`点屏幕<b>底部中间</b>的分享按钮 ${share}`, '往下滑，点「<b>添加到主屏幕</b>」，再点右上角的「添加」'],
      ipad: [`点<b>右上角</b>的分享按钮 ${share}`, '往下滑，点「<b>添加到主屏幕</b>」，再点「添加」'],
      'ios-other': ['苹果手机要用 <b>Safari</b> 才能放到桌面：点下面的「复制网址」，打开 Safari，粘贴并前往', `在 Safari 里点底部中间的分享按钮 ${share}，选「<b>添加到主屏幕</b>」`],
      wechat: ['微信里不能放到桌面：点右上角「<b>···</b>」，选「<b>在浏览器打开</b>」', '在浏览器里打开「我的 → 添加到桌面」，按那里的两步做'],
      android: ['点浏览器右上角的 <b>⋮</b>（有的浏览器在底部，是 <b>≡</b>）', '选「<b>添加到主屏幕</b>」或「<b>安装应用</b>」（有的手机叫「添加到桌面」）'],
      desktop: ['用 Chrome 或 Edge 打开语流，点地址栏右边的「安装」图标', '装好以后，可以从开始菜单或程序坞打开'],
    }[k];
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">把语流放到桌面</h2>
      <p class="muted small">像 App 一样从桌面一点就开，界面全屏；听过的音频会缓存下来，网络差的时候也能复习。</p>
      ${k === 'prompt' ? '<button class="btn primary" id="doInstall" type="button">安装到桌面</button>' : `<ol class="isteps">${steps.map(x => `<li>${x}</li>`).join('')}</ol>`}
      ${k === 'ios-other' ? '<button class="btn" id="copyUrl" type="button">复制网址</button>' : ''}
      <button class="btn ghost" data-close type="button">${k === 'prompt' ? '取消' : '知道了'}</button></div>`, card => {
      const di = card.querySelector('#doInstall');
      if (di) di.onclick = async () => {
        const p = installPrompt; if (!p) return closeSheet();
        let ok = false; p.prompt(); try { ok = (await p.userChoice).outcome === 'accepted'; } catch (e) { /* dismissed */ }
        installPrompt = null; closeSheet();
        if (ok) { save('flow-installed', Date.now()); toast('放好了，在桌面上找「语流」'); }
        route(true);
      };
      const cu = card.querySelector('#copyUrl');
      if (cu) cu.onclick = () => { const u = location.origin + '/'; (navigator.clipboard ? navigator.clipboard.writeText(u) : Promise.reject()).then(() => toast('网址已复制，去 Safari 粘贴打开'), () => prompt('复制这个网址，到 Safari 里打开', u)); };
    });
  }

  // Binding an email: the current password, then a 6-digit code sent to the new address (as at sign-up).
  function bindEmailSheet(cur) {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">${cur ? '更换' : '绑定'}邮箱</h2>
      <p class="muted small">先输入当前密码确认是你本人，再把发到新邮箱的 6 位验证码填回来。</p>
      <form id="bm" class="stack" novalidate><label class="field">邮箱<input name="email" type="email" autocomplete="email" inputmode="email" autocapitalize="off" spellcheck="false" required></label>
        ${pwField('当前密码', 'password', 'current-password')}
        <div class="code-row"><label class="field">验证码<input name="code" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="6" required></label>
          <button class="btn small" type="button" data-send>发送验证码</button></div>
        <button class="btn primary" type="submit">完成绑定</button></form>
      <p class="err" id="bmErr" role="alert"></p><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      bindEyes(card);
      const form = card.querySelector('#bm'), err = card.querySelector('#bmErr'), send = card.querySelector('[data-send]');
      send.onclick = async () => {
        err.textContent = ''; send.disabled = true;
        try { const r = await api('/api/account/email/request', { email: form.email.value.trim(), password: form.password.value, mode: 'code' }); toast(r.message || '验证码已发送'); countdown(send); form.code.focus(); }
        catch (x) { fieldError(form, err, { message: x.message, field: x.field || 'email' }); send.disabled = false; }
      };
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        if (!/^\d{6}$/.test(form.code.value.trim())) return fieldError(form, err, { message: '请先发送验证码，再填邮件里的 6 位数字', field: 'code' });
        const b = form.querySelector('[type=submit]'); b.disabled = true;
        try { await api('/api/account/email/confirm', { email: form.email.value.trim(), code: form.code.value.trim() }); closeSheet(); toast('邮箱已绑定，忘记密码时可以自己找回了'); await refreshHome(); route(true); }
        catch (x) { fieldError(form, err, x); b.disabled = false; }
      };
    });
  }
  // A new password ends every session, this one too: sign in again with it.
  function changePasswordSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">修改密码</h2>
      <p class="muted small">改好以后，所有手机和电脑上的登录都会退出，用新密码重新登录就行。</p>
      <form id="cp" class="stack" novalidate>${pwField('原密码', 'old', 'current-password')}${pwField('新密码', 'new', 'new-password', '至少 10 位，最好是一句只有你知道的话')}
        ${pwField('再输一次新密码', 'again', 'new-password')}<button class="btn primary" type="submit">保存新密码</button></form>
      <p class="err" id="cpErr" role="alert"></p><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      bindEyes(card);
      const form = card.querySelector('#cp'), err = card.querySelector('#cpErr');
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        if (form.new.value.length < 10) return fieldError(form, err, { message: '新密码至少 10 位', field: 'new' });
        if (form.new.value !== form.again.value) return fieldError(form, err, { message: '两次输入的新密码不一样', field: 'again' });
        const b = form.querySelector('[type=submit]'); b.disabled = true;
        try {
          await api('/api/password', { old_password: form.old.value, new_password: form.new.value });
          S.user = null; S.csrf = ''; closeSheet(); await refreshHome(); route();
          openLogin('密码已修改，请用新密码登录。', 'pw');
        } catch (x) { fieldError(form, err, { message: x.message, field: /原密码/.test(x.message) ? 'old' : /新密码/.test(x.message) ? 'new' : '' }); b.disabled = false; }
      };
    });
  }
  // 我的数据 (account_data.py): the word book for Excel/WPS/Numbers or for Anki, or every record of the account. Plain
  // links: the server sends them as files. WeChat does not save files, so there the way out is the phone's browser.
  const EXPORTS = [['/api/next/export/cards.csv', '单词本 · Excel 表格', '.csv', 'export-csv'],
    ['/api/next/export/cards-anki.txt', '单词本 · 导入 Anki', '.txt', 'export-anki'],
    ['/api/next/export/records.json', '全部学习记录', '.json', 'export-json']];
  function dataSheet() {
    const n = S.home && S.home.stats ? S.home.stats.cards : null;
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">导出我的数据</h2>
      ${IN_WECHAT ? '<p class="small card sunk">微信里不能保存文件：点右上角「…」，选「在浏览器打开」，再到「我的 → 导出我的数据」。</p>' : ''}
      <div class="glist">${EXPORTS.map(([href, label, ext, tap], k) => `<a class="grow" href="${href}" download data-tap="${tap}"><span class="t">${label}</span><span class="v small muted">${k < 2 && n != null ? n + ' 条 · ' : ''}${ext}</span><span class="go" aria-hidden="true">↓</span></a>`).join('')}</div>
      <p class="tiny muted">表格用 Excel、WPS 或 Numbers 直接打开：英文、中文意思、原文例句、来源和复习情况各占一列。Anki：在电脑上「文件 → 导入」选这个文件，正面是英文，背面是中文意思和原文例句。全部学习记录是一个 JSON 文件，有单词本、每次复习、学过的材料、测评和设置，留底或换地方用。</p>
      <button class="btn ghost" data-close type="button">完成</button></div>`);
  }
  // 注销账号: what goes (all of it, for good), a copy first if wanted, the password once more. Afterwards this phone
  // forgets the account too.
  function deleteAccountSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">注销账号</h2>
      <p class="small">注销后，这个账号和它的全部学习记录都会删除，<b>不能恢复</b>：单词本和复习安排、学过的材料、测评和能力雷达、写作和口语的批改记录、发过的问题反馈和截图。同样的用户名和邮箱以后可以重新注册，但会从头开始。</p>
      <p class="small">想留一份？<button class="link" id="dlFirst" type="button">先导出单词本和学习记录</button></p>
      <form id="da" class="stack" novalidate>${pwField('输入密码确认', 'password', 'current-password')}
        <button class="btn danger-btn" type="submit">永久注销这个账号</button></form>
      <p class="err" id="daErr" role="alert"></p><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      bindEyes(card);
      card.querySelector('#dlFirst').onclick = dataSheet;
      const form = card.querySelector('#da'), err = card.querySelector('#daErr');
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        if (!form.password.value) return fieldError(form, err, { message: '请输入密码', field: 'password' });
        const b = form.querySelector('[type=submit]'); b.disabled = true;
        try {
          await api('/api/account/delete', { password: form.password.value });
          forgetAccountHere(); S.user = null; S.csrf = ''; closeSheet(); await refreshHome();
          location.hash = '#/'; route(); toast('账号已注销，学习记录已全部删除');
        } catch (x) { fieldError(form, err, { message: x.message, field: 'password' }); b.disabled = false; }
      };
    });
  }
  // What this phone kept for the account: the copies (snapClear) and the small notes of where the learner was.
  // The phone's own choices (voice, text size, 复读) stay.
  function forgetAccountHere() {
    snapClear();
    try {
      ['flow-habit-lastweek', 'flow-habit-cheered', 'flow-next-mail-nudge', 'flow-next-suggest-skip', 'flow-words-stats'].forEach(k => localStorage.removeItem(k));
      Object.keys(localStorage).filter(k => k.startsWith('flow-next-steps-')).forEach(k => localStorage.removeItem(k));
    } catch (e) { /* private mode */ }
  }
  // A lost phone, a shared computer: end the account's sessions everywhere, this one included.
  function signOutEverywhere() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">退出所有设备？</h2>
      <p class="small">所有手机、平板和电脑上的语流都会退出登录，包括这一台。学习记录不会丢，重新登录就回来了。</p>
      <button class="btn primary" id="soAll" type="button">退出所有设备</button><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      card.querySelector('#soAll').onclick = async e => {
        e.currentTarget.disabled = true;
        await OUTBOX.flush(); try { await api('/api/logout', { all: true }); } catch (x) { /* signed out already */ } snapClear();
        S.user = null; S.csrf = ''; closeSheet(); await refreshHome(); toast('已在所有设备上退出'); route();
      };
    });
  }


