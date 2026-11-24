  /* ---------- 内测版: flow.jasa.hk, a second site with its own data, where new versions run before 语流 gets them ---------- */
  // The server says which site the page is on (<html data-channel>, app.CHANNEL). 语流 itself is flowlang.cn. On the
  // 内测版: a line under the top bar on every page, 「内测」 in the tab's title, a note in the sign-in sheet (95-channel.css),
  // and once per phone a sheet saying where 语流 is. Until 2026-11-24 this address was 语流 itself, so what this phone
  // kept for an account from then (instant-page copies, materials kept for offline study, the review queue, answers not
  // sent yet) is cleared before the page starts: none of it belongs to this site's accounts.
  const BETA = document.documentElement.dataset.channel === 'beta';
  const MAIN_SITE = 'https://flowlang.cn';
  const BETA_BEFORE = (() => {
    if (!BETA || load('flow-channel') === 'beta') return null;
    let before = false;
    try {
      before = Object.keys(localStorage).some(k => k.startsWith('flow-'));
      ['flow-snap', 'flow-offline', 'flow-next-outbox', 'flow-next-review-cache', 'flow-habit-lastweek', 'flow-habit-cheered'].forEach(k => localStorage.removeItem(k));
    } catch (e) { /* private mode */ }
    save('flow-channel', 'beta');
    return before;
  })();
  if (BETA) {
    document.title = '内测 · ' + document.title;
    document.getElementById('bar').insertAdjacentHTML('afterend', `<p class="beta-bar" id="betaBar" role="note"><b>内测版</b><span>先试新功能，账号和数据与正式版分开</span><a href="${MAIN_SITE}/" data-tap="beta-main">去正式版 flowlang.cn</a></p>`);
  }
  // Once per phone, after the first page is up.
  if (BETA_BEFORE !== null) setTimeout(() => openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">这里是语流内测版</h2>
    ${BETA_BEFORE ? '<p><b>语流的网址改成了 flowlang.cn。</b></p><p class="small">你的账号和学习记录都在 flowlang.cn，用原来的用户名和密码登录就行（换了网址，要重新登录一次）。加到了手机桌面的话，也请在 flowlang.cn 重新添加一次。</p>'
      : '<p>语流正式版的网址是 <b>flowlang.cn</b>。</p>'}
    <p class="small muted">这里（flow.jasa.hk）用来先试还没正式上线的新功能。账号和数据都和正式版分开，内测期间可能会清空。</p>
    <a class="btn primary" href="${MAIN_SITE}/" data-tap="beta-main">去正式版 flowlang.cn</a>
    <button class="btn ghost" data-close type="button">留在内测版</button></div>`), 700);
