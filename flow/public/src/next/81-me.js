  /* ---------- me: one grouped list, like a phone's settings; each row opens a page or a sheet ---------- */
  // A row: a link (to starts with # or /) or a button (to is its id); the value sits on the right, greyed.
  function grow(to, label, value, vid) {
    const tag = to[0] === '#' || to[0] === '/' ? 'a' : 'button';
    return `<${tag} class="grow" ${tag === 'a' ? `href="${to}"` : `type="button" id="${to}"`}><span class="t">${label}</span><span class="v small muted"${vid ? ` id="${vid}"` : ''}>${value || ''}</span><span class="go" aria-hidden="true">›</span></${tag}>`;
  }
  async function meView() {
    if (!S.meta) S.meta = await api('/api/next/meta');
    const p = (S.home && S.home.profile) || S.guest || {}, u = S.user, st = S.home && S.home.stats;
    const lv = S.meta.levels.find(l => l.id === p.level), goal = S.meta.goals.find(g => g.id === p.goal);
    const installed = matchMedia('(display-mode: standalone)').matches || navigator.standalone;
    const groups = [
      u && ['进步', [grow('#/radar', '能力雷达', '离目标还差多少'), grow('#/growth', '我的进步', '每月对比和里程碑'), grow('#/report', '这周的报告'), grow('#/cards/mistake', '错题本')]],
      ['设置', [grow('#/welcome/edit', '学习目标和水平', [goal && esc(goal.label), lv && lv.id].filter(Boolean).join(' · ') || '未设置'),
        grow('meVoice', '朗读声音', VOICE_LABELS[S.voice] || VOICE_LABELS['us-f'], 'meVoiceV'), grow('meRemind', '每天提醒', '加到手机日历'),
        installed ? '' : grow('meInstall', '添加到桌面', '像 App 一样打开')]],
      u && ['账号', [grow('bindMail', '邮箱', '<span class="spin"></span>', 'acctEmail'), grow('chPw', '修改密码'), grow('outAll', '退出所有设备')],
        '绑定邮箱后，可以用验证码登录，忘记密码时自己找回。30 天内来过就一直保持登录；在别人的手机或电脑上用完，记得退出。'],
      ['帮助', [grow('#/guide', '操作指南', '每个页面怎么用'), grow('/survey', '匿名问卷', '你想要什么样的英语学习网站'), grow('/?classic=1', '经典版', 'AI 私教、诊断测评')]],
    ].filter(Boolean);
    view.innerHTML = `<div class="card flat me-head"><div class="me-id">${u ? `<span class="avatar" aria-hidden="true">${esc([...u.username][0].toUpperCase())}</span>` : ''}
        <div class="t"><h1 class="h1">${u ? esc(u.username) : '我的'}</h1><span class="small muted">${lv ? `${esc(lv.label)}（${lv.id}）` : '还没有设置水平'} · 每天 ${p.minutes || 10} 分钟</span></div></div>
        ${st ? `<div class="me-nums">${[[st.week.filter(d => d.active).length, '本周学习天数'], [st.materials_done, '学完的材料'], [st.cards, '单词与表达']].map(([n, l]) => `<div><b>${n}</b><span class="tiny muted">${l}</span></div>`).join('')}</div>`
          : u ? '' : `<div class="stack-s"><span class="muted small">登录后才能保存进度、收藏表达和使用 AI。</span><div><button class="btn primary small" id="lg">登录 / 注册</button></div></div>`}</div>
      ${groups.map(([h, rows, foot]) => `<section class="gsec" aria-label="${h}"><h2 class="ghead">${h}</h2><div class="glist">${rows.join('')}</div>${foot ? `<p class="tiny muted gfoot">${foot}</p>` : ''}</section>`).join('')}
      ${u ? '<div class="glist gsec"><button class="grow danger" id="out" type="button"><span class="t">退出登录</span></button></div>' : ''}`;
    const lg = document.getElementById('lg'); if (lg) lg.onclick = () => openLogin();
    document.getElementById('meVoice').onclick = voiceSheet;
    document.getElementById('meRemind').onclick = () => remindSheet(p.minutes || 10);
    const mi = document.getElementById('meInstall'); if (mi) mi.onclick = installSheet;
    if (u) {
      const b = document.getElementById('bindMail'); b.disabled = true;
      api('/api/account').then(a => {
        const el = document.getElementById('acctEmail'); if (!el) return;
        el.textContent = a.email || '还没有绑定';
        if (a.mail_enabled) { b.disabled = false; b.setAttribute('aria-label', a.email ? '邮箱：' + a.email + '，点这里更换' : '绑定邮箱'); b.onclick = () => bindEmailSheet(a.email); }
        else if (!a.email) el.textContent += '（邮件服务暂未开启）';
      }).catch(() => { const el = document.getElementById('acctEmail'); if (el) el.textContent = ''; });
      document.getElementById('chPw').onclick = () => changePasswordSheet();
      document.getElementById('outAll').onclick = () => signOutEverywhere();
      document.getElementById('out').onclick = async () => { try { await api('/api/logout', {}); } catch (e) { /* ignore */ } S.user = null; S.csrf = ''; await refreshHome(); toast('已退出'); route(); };
    }
  }
  function voiceSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">朗读声音</h2>${voiceChips(null)}
      <p class="muted small">精选材料用真人声（Kokoro）朗读。学一篇材料时，也可以在「听」这一步随时切换。</p><button class="btn ghost" data-close type="button">完成</button></div>`, card => {
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
  function installSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">添加到手机桌面</h2>
      <p class="muted small">像 App 一样从桌面打开，界面全屏；听过的音频会缓存下来，网络差的时候也能复习。</p>
      ${installPrompt ? '<button class="btn primary" id="doInstall" type="button">添加到桌面</button>' : /iPhone|iPad|iPod/.test(navigator.userAgent)
        ? '<p class="small">iPhone：用 Safari 打开，点底部的「分享」按钮，再选「添加到主屏幕」。</p>' : '<p class="small">安卓：在浏览器菜单里选「添加到主屏幕」或「安装应用」。</p>'}
      <button class="btn ghost" data-close type="button">${installPrompt ? '取消' : '知道了'}</button></div>`, card => {
      const di = card.querySelector('#doInstall');
      if (di) di.onclick = async () => { installPrompt.prompt(); try { await installPrompt.userChoice; } catch (e) { /* dismissed */ } installPrompt = null; closeSheet(); meView(); };
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
  // A lost phone, a shared computer: end the account's sessions everywhere, this one included.
  function signOutEverywhere() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">退出所有设备？</h2>
      <p class="small">所有手机、平板和电脑上的语流都会退出登录，包括这一台。学习记录不会丢，重新登录就回来了。</p>
      <button class="btn primary" id="soAll" type="button">退出所有设备</button><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      card.querySelector('#soAll').onclick = async e => {
        e.currentTarget.disabled = true;
        try { await api('/api/logout', { all: true }); } catch (x) { /* signed out already */ }
        S.user = null; S.csrf = ''; closeSheet(); await refreshHome(); toast('已在所有设备上退出'); route();
      };
    });
  }


