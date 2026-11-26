  /* ---------- 切换账号 (account_switch.py; the owner, 2026-11-26: 「按推荐定」; look by B9, words of the note by D2) ----------
     This device remembers up to 3 accounts; a tap switches without a password. The tokens stay in HttpOnly cookies: the
     page only ever sees names and roles. Switching is as signing out and in: what the account still had to send goes
     first (OUTBOX.flush), its copies, drafts and queue on this device go (snapClear), then the other one's home; the
     consent page comes first when that account has not agreed (the router, 81-privacy.js). Flow's apps hear of it
     (account.changed) to set their reminders, widgets and search index for the account now in use. */
  const SWITCH = { list: null };
  async function switchList() {
    try { SWITCH.list = (await request('/api/account/list', undefined, true)).j; } catch (e) { SWITCH.list = null; }
    return SWITCH.list;
  }
  // 我的: the first row of the account group, and with two or more accounts 「切换 ›」 by the name (B9: one tap closer)
  function fillSwitchRow() {
    switchList().then(d => {
      const n = d ? d.items.length : 1, v = document.getElementById('meSwitchV'), top = document.getElementById('meSwitchTop');
      if (v) v.textContent = n >= 2 ? `这台设备 ${n} 个账号` : '添加另一个账号';
      if (top) top.hidden = n < 2;
    });
  }
  const switchAvatar = name => esc([...String(name || '?')][0].toUpperCase());
  function accountChanged() {
    try { if (window.FlowApp && FlowApp.call) FlowApp.call('account.changed').catch(() => { /* an older app: it reads again when it comes back */ }); }
    catch (e) { /* no app */ }
  }
  // a line at the bottom, as the 撤销 bar looks (50-words.js undoBar), without a button
  function switchedBar(name) {
    document.querySelectorAll('.easy-bar').forEach(b => b.remove());
    const b = document.createElement('div'); b.className = 'easy-bar'; b.setAttribute('role', 'status');
    b.innerHTML = `<span>已切换到 ${esc(name)}</span>`;
    document.body.appendChild(b); setTimeout(() => b.remove(), 4000);
  }
  // signedOut: after 退出登录, the accounts still remembered, to pick one or none
  async function switchSheet(signedOut) {
    const d = await switchList();
    if (!d) { toast('读不到这台设备上的账号，请稍后再试'); return; }
    if (signedOut && !d.items.length) return;
    const row = x => `<div class="sw-row" role="listitem"><button class="sw-main" type="button" data-sw="${x.id}"${x.current ? ' aria-current="true"' : ''}>
        <span class="sw-av" aria-hidden="true">${switchAvatar(x.username)}</span><span class="sw-name">${esc(x.username)}</span><span class="sw-role">${x.teacher ? '老师' : '学生'}</span>
        ${x.current ? '<span class="sw-on"><span aria-hidden="true">✓</span><span class="sr-only">正在用</span></span>' : ''}</button>
        ${x.current ? '' : `<button class="sw-more" type="button" data-swm="${x.id}" aria-label="${esc(x.username)}：更多">⋯</button>`}</div>`;
    openSheet(`<div class="stack sw-sheet"><h2 class="h2" id="sheetTitle">${signedOut ? '选一个账号继续' : '切换账号'}</h2>
      <div class="sw-list" role="list">${d.items.map(row).join('')}
        <div class="sw-row" role="listitem"><button class="sw-main sw-add" type="button" id="swAdd"${d.full ? ' disabled' : ''}><span class="sw-av" aria-hidden="true">＋</span><span class="sw-name">添加账号</span></button></div></div>
      ${d.full ? '<p class="small muted sw-why">这台设备最多记住 3 个账号，先移除一个。</p>' : ''}
      ${d.staff ? '<p class="small muted sw-why">员工账号不进切换账号：添加别的账号时，这个员工账号会先退出。</p>' : ''}
      <p class="sw-note">这台设备记住的账号，拿到这台设备的人都能切进去。<br>公用电脑、借来的手机，用完请在这里移除。</p>
      ${signedOut ? '<button class="btn ghost" data-close type="button">不切换，先这样</button>' : ''}</div>`, card => {
      card.querySelectorAll('[data-sw]').forEach(b => b.onclick = () => {
        const x = d.items.find(i => String(i.id) === b.dataset.sw);
        if (x && !x.current) switchTo(x, b); else closeSheet();
      });
      card.querySelectorAll('[data-swm]').forEach(b => b.onclick = () => forgetSheet(d.items.find(i => String(i.id) === b.dataset.swm), signedOut));
      const add = card.querySelector('#swAdd'); if (add) add.onclick = () => addAccount(d);
    });
  }
  async function switchTo(x, b) {
    b.disabled = true;
    try {
      if (S.user) await OUTBOX.flush();  // what the account in use still had to send goes to it first
      await api('/api/account/switch', { id: x.id });
    } catch (e) { b.disabled = false; toast(e.message); if (e.code === 'switch_gone') switchSheet(!S.user); return; }
    await afterSwitch(x.username);
  }
  async function afterSwitch(name) {
    snapClear(); S.user = null; S.csrf = ''; S.home = null;  // the last account's copies, drafts and queue go (as 退出登录)
    closeSheet(); accountChanged();
    await refreshHome();
    if (location.hash && location.hash !== '#/') location.hash = '#/'; else route();
    switchedBar(name);
  }
  // 从这台设备移除: plain ink, not red (nothing is deleted)
  function forgetSheet(x, signedOut) {
    if (!x) return;
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">${esc(x.username)}</h2>
      <div class="glist"><button class="grow" type="button" id="swForget"><span class="t">从这台设备移除</span></button></div>
      <p class="small muted">只是这台设备忘掉这个账号，相当于它在这台设备上退出登录；账号和学习记录都不动，以后用密码还能登录。</p>
      <button class="btn ghost" type="button" id="swBack">返回</button></div>`, card => {
      card.querySelector('#swBack').onclick = () => switchSheet(signedOut);
      card.querySelector('#swForget').onclick = async e => {
        e.currentTarget.disabled = true;
        try { await api('/api/account/forget', { id: x.id }); toast(`这台设备不再记住 ${x.username}`); }
        catch (err) { toast(err.message); }
        fillSwitchRow(); switchSheet(signedOut);
      };
    });
  }
  // 添加账号: the first time a second account is added, asked once whether this is the learner's own device (D2)
  function addAccount(d) {
    const go = async () => {
      if (S.user) await OUTBOX.flush();
      openLogin(S.user ? '添加以后，现在这个账号也留在这台设备上，在「切换账号」里点一下就能回来。' : '', 'pw', { add: true });
    };
    if (d.items.length !== 1 || !S.user) return go();
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">是你自己的设备吗？</h2>
      <p>这台设备会记住两个账号，以后不用密码就能切换。拿到这台设备的人，也能切进这两个账号。</p>
      <button class="btn primary" type="button" id="swYes">是我的设备，添加</button><button class="btn ghost" data-close type="button">不添加</button></div>`, card => {
      card.querySelector('#swYes').onclick = go;
    });
  }
