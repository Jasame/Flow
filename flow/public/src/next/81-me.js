  /* ---------- me ---------- */
  async function meView() {
    if (!S.meta) S.meta = await api('/api/next/meta');
    const p = (S.home && S.home.profile) || S.guest || {};
    const lv = S.meta.levels.find(l => l.id === p.level), goal = S.meta.goals.find(g => g.id === p.goal);
    const themes = S.meta.themes.filter(t => (p.themes || []).includes(t.id)).map(t => t.label);
    const st = S.home && S.home.stats;
    view.innerHTML = `<h1 class="h1">${S.user ? esc(S.user.username) : '我的'}</h1>
      ${S.user ? '' : `<div class="card sunk stack-s"><b>还没有登录</b><span class="muted small">登录后才能保存进度、收藏表达和使用 AI。</span><div><button class="btn primary small" id="lg">登录 / 注册</button></div></div>`}
      ${st ? `<div class="stat-grid"><div class="card flat stat"><b>${st.week.filter(d => d.active).length}</b><span class="tiny muted">本周学习天数</span></div><div class="card flat stat"><b>${st.materials_done}</b><span class="tiny muted">学完的材料</span></div><div class="card flat stat"><b>${st.cards}</b><span class="tiny muted">单词与表达</span></div></div>` : ''}
      <div class="card flat stack-s"><div class="row between"><b>学习设置</b><a class="link small" href="#/welcome/edit">修改</a></div>
        <div class="small">水平：${lv ? esc(lv.label) + '（' + lv.id + '）' : '未设置'}</div><div class="small">目标：${goal ? esc(goal.label) : '未设置'}</div>
        <div class="small">话题：${themes.length ? esc(themes.join('、')) : '随机'}</div><div class="small">每天：${p.minutes || 10} 分钟</div>
        <div class="small">朗读声音：</div>${voiceChips(null)}<p class="muted tiny">精选材料用真人声（Kokoro）朗读，可以随时在「听」这一步切换。</p></div>
      <div class="card flat stack-s" id="remind"><b>每天提醒</b><span class="muted small">加到手机日历：每天到点提醒你打开今天的计划。不用装 App、不用邮箱，iPhone 和安卓都能用。</span>
        <div class="row"><select id="mHour" aria-label="提醒时间">${Array.from({ length: 18 }, (_, k) => k + 6).map(h => `<option value="${h}" ${h === 20 ? 'selected' : ''}>每天 ${h}:00</option>`).join('')}</select>
        <a class="btn small" id="mCal" href="/api/next/vocab/reminder.ics?kind=plan&hour=20&minutes=${p.minutes || 10}">加到手机日历</a></div>
        <span class="tiny muted">打开下载的文件，选「添加到日历」即可；不想要了就在日历里删掉这个日程。</span></div>
      ${matchMedia('(display-mode: standalone)').matches || navigator.standalone ? '' : `<div class="card flat stack-s" id="install"><b>添加到手机桌面</b>
        <span class="muted small">像 App 一样从桌面打开，界面全屏；听过的音频会缓存下来，网络差的时候也能复习。</span>
        ${installPrompt ? '<div><button class="btn small primary" id="doInstall">添加到桌面</button></div>' : /iPhone|iPad|iPod/.test(navigator.userAgent)
          ? '<span class="small">iPhone：用 Safari 打开，点底部的「分享」按钮，再选「添加到主屏幕」。</span>' : '<span class="small">安卓：在浏览器菜单里选「添加到主屏幕」或「安装应用」。</span>'}</div>`}
      ${S.user ? `<div class="card flat stack-s" id="acct"><b>账号与安全</b>
        <div class="row between"><span class="small">邮箱</span><span class="small muted" id="acctEmail"><span class="spin"></span></span></div>
        <span class="muted tiny">绑定后可以用验证码登录、忘记密码时自己找回，也能收复习提醒和周报。</span>
        <div class="row wrap acct-actions"><button class="btn small" id="bindMail" hidden>绑定邮箱</button><button class="btn small" id="chPw">修改密码</button><button class="btn small ghost" id="outAll">退出所有设备</button></div>
        <span class="muted tiny">30 天内来过就一直保持登录。在别人的手机或电脑上用完，记得退出登录。</span></div>` : ''}
      ${S.user ? '<a class="card flat place-cta" href="#/radar"><b>能力雷达：离目标还差多少</b><span class="small muted">听力、阅读、词汇、语法、口语、写作六项，对照你自己定的目标；定期测一测，看哪一项长了。</span></a>' : ''}
      ${S.user ? '<div id="abSlot"><div class="card flat"><p class="loading"><span class="spin"></span></p></div></div>' : ''}
      <div class="card flat list">
        ${S.user ? '<a href="#/growth">我的进步：每月对比和里程碑 <span>→</span></a><a href="#/report">这周的学习报告 <span>→</span></a><a href="#/cards/mistake">错题本 <span>→</span></a>' : ''}
        <a href="#/practice">全部练习：听读、口语、单词、语法、考试 <span>→</span></a>
        <a href="#/guide">操作指南：每个页面怎么用 <span>→</span></a>
        <a href="/survey">参与匿名问卷：你想要什么样的英语学习网站 <span>→</span></a>
        <a href="/?classic=1">经典版（AI 私教、诊断测评、内容管理）<span>→</span></a>
        ${S.user ? '<button id="out">退出登录 <span>→</span></button>' : ''}</div>`;
    const lg = document.getElementById('lg'); if (lg) lg.onclick = () => openLogin();
    const mHour = document.getElementById('mHour'), mCal = document.getElementById('mCal');
    mHour.onchange = () => { mCal.href = `/api/next/vocab/reminder.ics?kind=plan&hour=${mHour.value}&minutes=${p.minutes || 10}`; };
    const slot = document.getElementById('abSlot');
    if (slot) api('/api/next/ability').then(ab => { slot.innerHTML = abilityHTML(ab); requestAnimationFrame(() => requestAnimationFrame(() => slot.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; }))); }).catch(() => { slot.innerHTML = ''; });
    if (S.user) api('/api/account').then(a => {
      const el = document.getElementById('acctEmail'), b = document.getElementById('bindMail'); if (!el) return;
      el.textContent = a.email || '还没有绑定';
      if (a.mail_enabled) { b.hidden = false; b.textContent = a.email ? '更换邮箱' : '绑定邮箱'; b.onclick = () => bindEmailSheet(a.email); }
      else el.textContent += a.email ? '' : '（邮件服务暂未开启）';
    }).catch(() => { const el = document.getElementById('acctEmail'); if (el) el.textContent = ''; });
    const di = document.getElementById('doInstall'); if (di) di.onclick = async () => { installPrompt.prompt(); try { await installPrompt.userChoice; } catch (e) { /* dismissed */ } installPrompt = null; meView(); };
    view.querySelectorAll('[data-voice]').forEach(b => b.onclick = async () => { await setVoice(b.dataset.voice); view.querySelectorAll('[data-voice]').forEach(x => { x.setAttribute('aria-pressed', String(x === b)); x.setAttribute('aria-checked', String(x === b)); }); toast('朗读声音：' + VOICE_LABELS[b.dataset.voice]); });
    const chPw = document.getElementById('chPw'); if (chPw) chPw.onclick = () => changePasswordSheet();
    const outAll = document.getElementById('outAll'); if (outAll) outAll.onclick = () => signOutEverywhere();
    const out = document.getElementById('out');
    if (out) out.onclick = async () => { try { await api('/api/logout', {}); } catch (e) { /* ignore */ } S.user = null; S.csrf = ''; await refreshHome(); toast('已退出'); route(); };
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


