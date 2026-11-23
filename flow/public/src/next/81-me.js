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
      ${S.user ? `<div class="card flat stack-s" id="acct"><div class="row between"><b>邮箱</b><span class="small muted" id="acctEmail"><span class="spin"></span></span></div>
        <span class="muted tiny">绑定后可以收复习提醒和周报、用验证码登录、找回密码。</span><div><button class="btn small" id="bindMail" hidden>绑定邮箱</button></div></div>` : ''}
      ${S.user ? '<div id="abSlot"><div class="card flat"><p class="loading"><span class="spin"></span></p></div></div>' : ''}
      <div class="card flat list">
        ${S.user ? '<a href="#/growth">我的进步：每月对比和里程碑 <span>→</span></a><a href="#/report">这周的学习报告 <span>→</span></a><a href="#/cards/mistake">错题本 <span>→</span></a>' : ''}
        <a href="#/easy">轻松读：读得多、读得快 <span>→</span></a>
        <a href="#/speak">口语路线：12 个情景对话 <span>→</span></a>
        <a href="#/words/confuse">词汇辨析：中国学习者最常混的词 <span>→</span></a>
        <a href="#/sounds">发音入门：容易混的音 <span>→</span></a>
        <a href="#/import">我的文章：导入任何英文来学 <span>→</span></a>
        <a href="#/graph">我的知识图谱 <span>→</span></a>
        <a href="#/placement">语法起点小测：重新定水平 <span>→</span></a>
        <a href="#/exam">考试练习：四六级、考研、雅思 <span>→</span></a>
        <a href="#/library">全部材料 <span>→</span></a>
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
    const out = document.getElementById('out');
    if (out) out.onclick = async () => { try { await api('/api/logout', {}); } catch (e) { /* ignore */ } S.user = null; S.csrf = ''; await refreshHome(); toast('已退出'); route(); };
  }

  function bindEmailSheet(cur) {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">${cur ? '更换' : '绑定'}邮箱</h2>
      <p class="muted small">先发一封验证邮件到新邮箱；邮件里有一串验证令牌，复制回来粘贴到这里就完成了（30 分钟内有效）。</p>
      <form id="bm1" class="stack" novalidate><label class="field">邮箱<input name="email" type="email" autocomplete="email" inputmode="email" required></label>
        <label class="field">当前密码（确认是你本人）<input name="password" type="password" autocomplete="current-password" required></label>
        <button class="btn primary" type="submit">发送验证邮件</button></form>
      <form id="bm2" class="stack" novalidate hidden><label class="field">验证令牌<input name="token" type="text" autocomplete="one-time-code" autocapitalize="off" spellcheck="false" required></label>
        <button class="btn primary" type="submit">完成绑定</button></form>
      <p class="err" id="bmErr" role="alert"></p><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      const f1 = card.querySelector('#bm1'), f2 = card.querySelector('#bm2'), err = card.querySelector('#bmErr');
      f1.onsubmit = async e => {
        e.preventDefault(); err.textContent = ''; const b = f1.querySelector('button'); b.disabled = true;
        try { await api('/api/account/email/request', { email: f1.email.value.trim(), password: f1.password.value }); f1.hidden = true; f2.hidden = false; f2.token.focus(); toast('验证邮件已发出，请查看邮箱'); }
        catch (x) { err.textContent = x.message; b.disabled = false; }
      };
      f2.onsubmit = async e => {
        e.preventDefault(); err.textContent = ''; const b = f2.querySelector('button'); b.disabled = true;
        try { await api('/api/account/email/confirm', { token: f2.token.value.trim() }); closeSheet(); toast('邮箱已绑定'); meView(); }
        catch (x) { err.textContent = x.message; b.disabled = false; }
      };
    });
  }

