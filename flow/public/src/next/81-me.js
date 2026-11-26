  /* ---------- me: one grouped list, like a phone's settings; each row opens a page or a sheet ---------- */
  // A row: a link (to starts with # or /) or a button (to is its id); the value sits on the right, greyed.
  // icon (00-icons.js): the soft square in front, as 设置's rows have it
  function grow(to, label, value, vid, tapKey, icon) {
    const tag = /^(#|\/|https?:)/.test(to) ? 'a' : 'button';
    return `<${tag} class="grow${icon ? ' gi' : ''}" ${tag === 'a' ? `href="${to}"` : `type="button" id="${to}"`}${tapKey ? ` data-tap="${tapKey}"` : ''}>${icon ? fiTile(icon) : ''}<span class="t">${label}</span><span class="v small muted"${vid ? ` id="${vid}"` : ''}>${value || ''}</span><span class="go" aria-hidden="true">›</span></${tag}>`;
  }
  // 全英文界面: rows about agreeing and privacy stay in Chinese in English mode too (data-zh, docs/english-ui.md)
  const zhRow = html => html.replace('class="grow"', 'class="grow" data-zh');
  // 帮助 → 更多: the two rows that are not looked at every week (简洁化, the user's pick 2026-11-25)
  function moreSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">更多</h2><div class="glist">${grow('/about', '认识语流', '一页看完语流能帮你做什么', '', 'me-about')}${grow('/survey', '匿名问卷', '你想要什么样的英语学习网站', '', 'me-survey')}
      ${S.user ? grow('meTour', '再看一遍新手引导', '底下五个地方各是做什么的', '', 'me-tour') : ''}${grow('meTips', '重新显示使用提示', '比如「点词查词」，用到时再说一次', '', 'me-tips')}</div>
      <button class="btn ghost" data-close type="button">关闭</button></div>`, card => {
      const t = card.querySelector('#meTour'); if (t) t.onclick = () => { closeSheet(); tourAgain(); };  // 08-tour.js
      card.querySelector('#meTips').onclick = async () => {  // 08-tips.js
        try { await TIPS.reset(); closeSheet(); toast('使用提示会在用到时再出现一次'); } catch (e) { toast(e.message); }
      };
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
  // 语流's own app with a settings page of its own (iOS 专属功能: 锁屏听读、小组件、Siri…, ios-27-features.md; 语流 C1,
  // 2026-11-25): one row in 设置 opens it (FlowApp.call('app.settings')). Shown only where the app says it has one.
  const APP_SETTINGS = { ios: ['iOS 专属功能', '锁屏、小组件、Siri 等'], android: ['安卓专属功能', ''], windows: ['Windows 专属功能', ''], macos: ['Mac 专属功能', ''] };
  const appSettings = () => { try { return window.FlowApp && FlowApp.has && FlowApp.has('settings') ? APP_SETTINGS[FlowApp.platform] || ['App 专属功能', ''] : null; } catch (e) { return null; } };
  // 「AI 用量」 (2026-11-26, the owner in A0: a learner sees their own AI use of the day): ai_quota.today (语流 B7 #405),
  // read fresh each time (not the data layer's copy: an AI answer a moment ago changed it).
  const aiRowLabel = a => a.stopped === 'paused' ? '暂停中' : a.stopped === 'day_full' || a.stopped === 'site' ? '今天已满'
    : a.limit == null ? '不限次数' : a.remaining > 0 ? `还能用 ${a.remaining} 次` : '今天已用完';
  function fillAiRow() {
    const put = t => { const v = document.getElementById('meAiV'); if (v) v.textContent = t; };
    request('/api/account/ai', undefined, true).then(r => put(aiRowLabel(r.j))).catch(() => put(''));
  }
  async function aiUsageSheet() {
    let a;
    try { a = (await request('/api/account/ai')).j; } catch (e) { toast(e.message); return; }
    const until = a.paused_until ? new Date(a.paused_until * 1000) : null;
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">AI 用量</h2>
      <div class="aiq-num"><b>${a.used}</b><span class="muted">${a.limit != null ? ` / ${a.limit} 次` : ' 次'}</span><span class="small muted">今天</span></div>
      ${a.limit ? `<progress class="aiq-bar${a.level !== 'ok' ? ' low' : ''}" max="${a.limit}" value="${Math.min(a.used, a.limit)}" aria-label="今天用了 ${a.used} 次，共 ${a.limit} 次"></progress>` : ''}
      <p class="small">${esc(a.note)}${until ? `预计 ${until.getMonth() + 1} 月 ${until.getDate()} 日恢复。` : ''}${a.stopped === 'paused' ? ' <a class="link" href="#/feedback" data-close>去问题反馈</a>' : ''}</p>
      ${a.by_kind && a.by_kind.length ? `<ul class="aiq-kinds">${a.by_kind.map(k => `<li><span>${esc(k.label)}</span><span class="muted">${k.count} 次</span></li>`).join('')}</ul>` : ''}
      <p class="tiny muted">用到 AI 的批改、讲解、出题和对话，每次算一次；大家共用的讲解和例句、没有成功的那次不算。AI 朗读另有字数上限，不算在这里。${a.adjusted ? '你的额度由管理员调整过。' : ''}</p>
      <button class="btn ghost" data-close type="button">完成</button></div>`);
    const v = document.getElementById('meAiV'); if (v) v.textContent = aiRowLabel(a);
  }
  // 我的 (B9's batch 1, the user 2026-11-26 15:3x; ui-refine/batch1/me-*.png and spec.md): a white card with who you are
  // and one line on this week; 进步 as three tiles; 设置 one white card, an icon in front of each row and its value on
  // the right; 账号和隐私 and 帮助 each a fold that opens in place (D2's fold rules: the name in ink, what is inside on the
  // right, never 「8 项」). #/me/account and #/me/help open their fold (the guide's and the mails' links); a fold
  // opened stays open on the way back from a page it led to.
  const ME_OPEN = {};
  const ME_FOLDS = { account: ['shield', '账号和隐私', '导出、注销、数据存放'], help: ['help', '帮助', '指南、隐私说明、反馈'] };
  function meFold(id, rows, foot) {
    const [icon, name, inside] = ME_FOLDS[id];
    return `<details class="me-fold" id="meFold-${id}" data-fold="${id}"${ME_OPEN[id] ? ' open' : ''}><summary class="fold-s"><span class="fold-r">${fi(icon)}<span class="fold-n">${name}</span><span class="fold-v">${inside}</span>
      <svg class="fold-a" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9.5 6 6 6-6"/></svg></span></summary>
      <div class="fold-b"><div class="glist">${rows.join('')}</div>${foot ? `<p class="tiny muted gfoot">${foot}</p>` : ''}</div></details>`;
  }
  const meTile = (href, icon, name, line, vid, tap) => `<a class="me-tile" href="${href}" data-tap="${tap}">${fiTile(icon)}<b>${name}</b><span class="me-tv"${vid ? ` id="${vid}"` : ''}>${line}</span></a>`;
  // 错题本's tile: how many there are (the list's own count, asked for after the page is drawn)
  function fillMistakeTile() {
    api('/api/next/cards?f=mistake&page=1').then(r => { const el = document.getElementById('meMistakeV'); if (el) el.textContent = r.total ? `${r.total} 道` : '还没有'; }).catch(() => {});
  }
  // 提醒和每周邮件 (B9: 「每天提醒」「每周进度邮件」 as one row): the two, each to its own sheet
  function remindMailSheet(minutes) {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">提醒和每周邮件</h2><div class="glist">${grow('rmDay', '每天提醒', '加到手机日历')}${grow('rmMail', '每周进度邮件', weeklyMailLabel(), '', 'me-weekly-mail')}</div>
      <button class="btn ghost" data-close type="button">关闭</button></div>`, card => {
      card.querySelector('#rmDay').onclick = () => remindSheet(minutes);
      card.querySelector('#rmMail').onclick = weeklyMailSheet;  // 11-progress.js
    });
  }
  async function meView(fold) {
    if (!S.meta) S.meta = await api('/api/next/meta');
    if (ME_FOLDS[fold]) ME_OPEN[fold] = true;  // #/me/account, #/me/help
    const p = (S.home && S.home.profile) || S.guest || {}, u = S.user, st = S.home && S.home.stats;
    const lv = S.meta.levels.find(l => l.id === p.level);
    // 学英语为了什么: every goal chosen, the main one first (2026-11-26; an older profile has goal only)
    const goalNames = ((p.goals && p.goals.length ? p.goals : p.goal ? [p.goal] : [])).map(id => (S.meta.goals.find(g => g.id === id) || {}).label).filter(Boolean);
    const installed = HOME_APP;  // the home-screen app, an install, or one of Flow's apps: nothing to add to the desktop
    const days = st ? (st.habit ? st.habit.done : st.week.filter(d => d.active).length) : 0;
    const app = appSettings();
    const settings = [grow('#/welcome/edit', '学习目标和水平', [goalNames.length && esc(goalNames.join('、')), p.target && '目标 ' + p.target, lv && (p.target ? '现在 ' : '') + lv.id].filter(Boolean).join(' · ') || '未设置', '', 'me-level', 'target'),
      u ? grow('meExam', '我的考试', examLabel(p), 'meExamV', 'me-exam', 'cap') : '', u ? grow('meHabit', '每周目标', `每周 ${(st && st.habit && st.habit.goal) || 4} 天`, 'meHabitV', 'me-habit', 'calok') : '',
      grow('meVoice', '朗读声音', VOICE_LABELS[S.voice] || VOICE_LABELS['us-f'], 'meVoiceV', 'me-voice', 'voice'), WORD_CLIPS ? grow('meSound', '单词读音方式', soundLabel(), 'meSoundV', 'me-sound', 'book') : '',
      grow('#/me/habits', '使用习惯', habitsLabel(), '', 'me-habits', 'sliders'),  // 今日的样子、主题色、卡片、「认识」、字号 (81-habits.js)
      u ? grow('meRemind', '提醒和每周邮件', weeklyMailLabel(), 'meMailV', 'me-remind', 'bell') : grow('meRemind', '每天提醒', '', '', 'me-remind', 'bell'),
      u && !u.teacher ? grow('meClass', '班级', '<span class="spin"></span>', 'meClassV', 'me-class', 'people') : '',
      u ? grow('meAi', 'AI 用量', '<span class="spin"></span>', 'meAiV', 'me-ai', 'gauge') : '',
      installed ? '' : grow('meInstall', '添加到桌面', '', '', 'me-install', 'layers'),
      app ? grow('meApp', app[0], app[1], '', 'me-app-settings', 'spark') : '',
      // 按我的学习记录推荐: the switch on its row and the grey line under it (the user's pick, 2026-11-26; 81-privacy.js)
      u && S.home && S.home.profile ? personalizeRow() + `<p class="tiny muted me-pfoot">${PERSONALIZE_FOOT}</p>` : ''];
    const groups = [
      // 内测版 (flow.jasa.hk) only: what the line under the top bar said, kept here (the line can be closed): the
      // version and what changed in it (/api/deploy-status, /api/next/updates), 去正式版 (not in Flow's apps: it would
      // open the system browser), feedback
      BETA && ['内测版', [grow('#/feedback', '问题反馈', '', '', 'me-beta-feedback'),
        IN_FLOW_APP ? '' : grow(MAIN_SITE + '/', '去正式版', 'flowlang.cn', '', 'me-beta-main'), '<div class="beta-new" id="meBetaNew" hidden></div>'],
        '这里是语流的内测版（flow.jasa.hk），新功能先在这里试。账号和数据都和正式版分开，内测期间可能会清空。<span id="meBetaVer"></span>'],
      // 安卓 App 1.0.4+ (81-privacy.js appPrivacy): 撤回同意 and the system permissions, for the app stores
      // and the two lists the stores ask for (隐私和数据, #342), a tap from 我的
      appPrivacy() && ['隐私', [zhRow(grow('#/guide/info-list', '个人信息收集清单', '', '', 'me-info-list')), zhRow(grow('#/guide/sharing-list', '第三方信息共享清单', '', '', 'me-sharing-list')),
        zhRow(grow('meWithdraw', '撤回同意', '', '', 'me-withdraw')), grow('mePerms', '系统权限', '麦克风、通知', '', 'me-permissions')],
        '<span data-zh>撤回同意以后，App 清掉这台手机上的登录和缓存，回到第一次打开时的样子。服务器上的账号和学习记录还在：要停下来，请在「账号和隐私 → 数据存放」里撤回；要删除，请注销账号。</span>'],
    ].filter(Boolean);
    const sec = (h, body, foot) => `<section class="me-sec" aria-label="${h}"><h2 class="me-h">${h}</h2>${body}${foot ? `<p class="tiny muted gfoot">${foot}</p>` : ''}</section>`;
    view.innerHTML = `<section class="me-card me-head">${u ? `<span class="avatar" aria-hidden="true">${esc([...u.username][0].toUpperCase())}</span>` : ''}
        <div class="t"><h1 class="me-name">${u ? esc(u.username) : '我的'}${BETA ? ' <span class="beta-pill" aria-label="内测版">内测</span>' : ''}</h1>
          <span class="me-line">${lv ? `${esc(lv.label)}（${lv.id}）` : '还没有设置水平'} · 每天 ${p.minutes || 10} 分钟</span>
          ${st ? `<span class="me-line">这周学了 ${days} 天 · 学完 ${st.materials_done} 篇 · ${st.cards} 个词</span>` : u ? '' : '<span class="me-line">登录后才能保存进度、收藏表达和使用 AI。</span>'}</div>
        ${u ? '' : '<button class="btn primary small" id="lg" type="button">登录 / 注册</button>'}</section>
      ${u ? '<div id="meTeach"></div>' : ''}
      ${u ? sec('进步', `<div class="me-tiles">${meTile('#/growth', 'trend', '我的进步', st && st.habit ? `达标 ${st.habit.weeks || 0} 周` : '', '', 'me-growth')}${meTile('#/report', 'week', '周报', '最近 7 天', '', 'me-report')}${meTile('#/cards/mistake', 'bookx', '错题本', '', 'meMistakeV', 'me-mistake')}</div>`) : ''}
      ${sec('设置', `<div class="glist me-list">${settings.join('')}</div>`)}
      ${groups.map(([h, rows, foot]) => sec(h, `<div class="glist">${rows.join('')}</div>`, foot)).join('')}
      <div class="me-folds">${u ? meFold('account', [grow('bindMail', '邮箱', '<span class="spin"></span>', 'acctEmail'), grow('chPw', '修改密码'), grow('outAll', '退出所有设备'),
        zhRow(grow('meAge', '年龄段', ageLabel(u && u.age), 'meAgeV', 'me-age')), zhRow(grow('meStorage', '数据存放', '已同意 · 香港')), zhRow(grow('#/guide/terms', '用户协议', '和隐私说明一起同意')), zhRow(grow('#/guide/privacy', '隐私说明', '', '', 'me-privacy')),
        grow('meData', '导出我的数据', '', '', 'me-data'), grow('meDelete', '注销账号', '', '', 'me-delete')],
        '绑定邮箱后，可以用验证码登录，忘记密码时自己找回。30 天内来过就一直保持登录；在别人的手机或电脑上用完，记得退出。') : ''}
      ${meFold('help', [grow('#/guide', '操作指南', '', '', 'me-guide'), grow('#/updates', '更新记录', '', '', 'me-updates'), grow('#/feedback', '问题反馈', '', '', 'me-feedback'), zhRow(grow('#/guide/privacy', '隐私说明', '', '', 'me-privacy')), grow('meMore', '更多', '认识语流、匿名问卷、新手引导', '', 'me-more')])}</div>
      ${appPrivacy() ? '<p class="tiny muted me-beian"><span id="meBeian" hidden></span></p>' : ''}
      ${u ? '<div class="me-out"><button class="grow danger" id="out" type="button"><span class="t">退出登录</span></button></div>' : ''}`;
    view.querySelectorAll('details.me-fold').forEach(d => d.addEventListener('toggle', () => { ME_OPEN[d.dataset.fold] = d.open; }));
    const opened = ME_FOLDS[fold] && document.getElementById('meFold-' + fold);
    if (opened) requestAnimationFrame(() => opened.scrollIntoView({ block: 'start', behavior: 'auto' }));
    const lg = document.getElementById('lg'); if (lg) lg.onclick = () => openLogin();
    document.getElementById('meVoice').onclick = voiceSheet;
    if (document.getElementById('meSound')) document.getElementById('meSound').onclick = soundSheet;
    const mh = document.getElementById('meHabit'); if (mh) mh.onclick = habitSheet;
    const me = document.getElementById('meExam'); if (me) me.onclick = () => examGoalSheet(() => meView());
    document.getElementById('meRemind').onclick = () => (u ? remindMailSheet : remindSheet)(p.minutes || 10);
    if (u) fillMailRow();  // 11-progress.js
    const mai = document.getElementById('meAi'); if (mai) { mai.onclick = aiUsageSheet; fillAiRow(); }
    personalizeWire();  // the switch and 「了解更多」 (81-privacy.js)
    const mi = document.getElementById('meInstall'); if (mi) mi.onclick = installSheet;
    const mw = document.getElementById('meWithdraw'); if (mw) mw.onclick = withdrawInApp;  // 81-privacy.js
    const mpm = document.getElementById('mePerms'); if (mpm) mpm.onclick = permissionsSheet;
    fillBeian();
    const ma = document.getElementById('meApp'); if (ma) ma.onclick = () => FlowApp.call('app.settings').catch(() => toast('打不开 App 的设置页，把语流 App 更新到最新版再试'));
    document.getElementById('meMore').onclick = moreSheet;
    if (BETA) betaInfo();
    if (u) {
      fillMistakeTile();
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
  // larger and with more room between lines; menus and buttons stay as they are (applyText, 02-shell.js). Set in
  // 我的 → 使用习惯 (81-habits.js) and kept with the account (07-prefs.js).
  const TEXT_SIZES = [['m', '标准'], ['l', '大'], ['xl', '特大']], TEXT_LH = [['n', '标准'], ['w', '宽松']];
  // iPhones and iPads: how words, examples and short sentences are played (01-audio-offline.js AUDIO / CLIP), and the
  // silence in front of a word in 标准. Kept on this phone: the app on the home screen keeps its own, and has no address
  // bar for ?audio= and ?lead= (the owner compares the two ways on an iPhone before the default is chosen).
  const SOUND_MODES = [['auto', '连续', '从第一个音开始放；连着点单词时，灵动岛会一直显示「语流 · 单词」，停下 20 秒后收起。（默认）'],
    ['compat', '标准', '每个词是一个前面留了一点静音的小音频，大部分单词不会出现在灵动岛上。「连续」没有声音时选这个。']];
  const soundLabel = () => AUDIO.mode() === 'compat' ? `标准 · 前面 ${AUDIO.lead()} 秒` : '连续';
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
    if (/Android/i.test(ua)) return 'android';
    // HarmonyOS NEXT (鸿蒙 5 and up: 华为浏览器 and other ArkWeb browsers) says OpenHarmony and no Android; without this it
    // was told to use Chrome or Edge, as on a computer. HarmonyOS 4 and before say Android and keep the Android steps.
    return /OpenHarmony/i.test(ua) ? 'harmony' : 'desktop';
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
      harmony: ['点浏览器的菜单按钮（华为浏览器在底部，是 <b>≡</b>）', '找到「<b>添加到桌面</b>」点一下（有的版本叫「添加至桌面」）'],
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


