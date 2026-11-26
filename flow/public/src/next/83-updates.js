  /* ---------- 更新记录 (#/updates, 我的 → 帮助): what each 语流 release changed, in plain words (updates_service.py) ---------- */
  // One card per release, newest first, every change a learner can notice: 用法变了 first and marked (a button moved, a
  // consent to give), then 新功能 / 改进 / 修好的问题; a sentence with a page to see gets 「去看看」. On the 内测版 a 「内测中」
  // card first: what is on this site and not on 语流 yet. The data is corpus_data/updates.json, written with each release.
  const UPD_GROUPS = [['changed', '用法变了'], ['new', '新功能'], ['better', '改进'], ['fixed', '修好的问题']];
  function updItem(i) {
    return `<li>${esc(i.text)}${i.link ? ` <a class="link upd-go" href="${esc(i.link)}" data-tap="updates-go">去看看</a>` : ''}</li>`;
  }
  function updGroups(e) {
    return UPD_GROUPS.filter(([k]) => e[k] && e[k].length)
      .map(([k, l]) => `<div class="upd-g${k === 'changed' ? ' upd-changed' : ''}"><h3 class="upd-h">${k === 'changed' ? '⚠︎ ' : ''}${l}</h3><ul class="upd-l">${e[k].map(updItem).join('')}</ul></div>`).join('')
      + (e.note ? `<p class="small muted upd-note">${esc(e.note)}</p>` : '');
  }
  async function updatesView() {
    const d = await api('/api/next/updates');
    if (d.released[0]) save('flow-update-seen', d.released[0].id);  // read here: 今日 no longer offers the card for it
    view.innerHTML = `<div class="stack upd-page"><div><h1 class="h1">更新记录</h1><span class="muted small">语流每一次更新改了什么，新的在上面。标着「用法变了」的，是要换个方式用的地方。</span></div>
      ${d.beta ? `<section class="card stack-s upd upd-beta" aria-label="内测中"><div class="row between"><h2 class="h2">内测中</h2><span class="pill">只在内测版</span></div>
        <span class="small muted">已经能在这里试，还没上正式版。</span>${updGroups(d.beta)}</section>` : ''}
      ${d.released.length ? d.released.map(e => `<section class="card stack-s upd" aria-label="${esc(e.label)}"><h2 class="h2">${esc(e.label)}</h2>${updGroups(e)}</section>`).join('')
        : '<p class="muted">还没有更新记录。</p>'}
      <p class="tiny muted">发现哪里不对，可以在<a class="link" href="#/feedback">问题反馈</a>里告诉我们。</p></div>`;
  }
  // 「语流更新了」 at the very top of 今日, in the place of the operators' 公告 (10-welcome-today.js): a 公告 goes first; with
  // none, the first time a learner who has studied before opens a new release, its two or three highlights and
  // 「查看全部变化」. Either button, or opening 更新记录, marks that release seen on this phone (flow-update-seen), so one
  // release shows once. A phone new to 语流 just notes it: nothing has changed for it.
  function updateCardDue(h) {
    const u = h.update; if (!u || !u.highlights || !u.highlights.length) return false;
    if (uiLang() === 'en') return false;  // 全英文界面: what changed is written in Chinese only, so the card waits (更新记录 still has it)
    const seen = load('flow-update-seen');
    if (seen === u.id) return false;
    const st = h.stats, studied = !!st && (st.materials_done > 0 || st.cards > 0 || (st.week || []).some(d => d.active));
    if (seen == null && !studied) { save('flow-update-seen', u.id); return false; }
    return true;
  }
  function updateCardHTML(h) {
    if (!updateCardDue(h)) return '';
    const u = h.update;
    return `<div class="card sunk section notice announce upd-card stack-s" id="updCard" role="status"><b>语流更新了<span class="tiny muted"> · ${esc(u.label)}</span></b>
      <ul class="upd-l small">${u.highlights.map(s => `<li>${esc(s)}</li>`).join('')}</ul>
      <div class="row"><a class="btn small primary" href="#/updates" id="updAll" data-tap="today-updates">查看全部变化</a><button class="btn small ghost" id="updOk" type="button">知道了</button></div></div>`;
  }
  function bindUpdateCard(h) {
    const box = document.getElementById('updCard'); if (!box) return;
    const seen = () => save('flow-update-seen', h.update.id);
    document.getElementById('updOk').onclick = () => { seen(); box.remove(); };
    document.getElementById('updAll').addEventListener('click', seen);
  }
