  /* ---------- easy reading: a lot of easy text, read fast, no tasks ---------- */
  async function easyView() {
    const d = await api('/api/next/easy' + guestQuery(true)), st = d.stats;
    view.innerHTML = `<div class="stack"><div><span class="kicker">轻松读</span><h1 class="h1">读得多，比读得难更重要</h1>
        <p class="muted small">${esc(d.note)}</p></div>
      ${st ? `<div class="easy-stats"><div><b>${st.week_words.toLocaleString()}</b><span class="tiny muted">这周读了（词）</span></div>
        <div><b>${st.avg_wpm || '—'}</b><span class="tiny muted">阅读速度（词/分钟）</span></div><div><b>${st.reads}</b><span class="tiny muted">一共读了（篇）</span></div></div>
        ${st.first_wpm && st.avg_wpm > st.first_wpm ? `<p class="small cheer">比刚开始快了 ${st.avg_wpm - st.first_wpm} 词/分钟。</p>` : ''}` : '<p class="muted small">登录后会记下你读了多少、读得多快。</p>'}
      <div class="section stack-s"><div class="row between"><h2 class="h2">今天可以读</h2><span class="pill">${esc(d.target)}</span></div>
        <div class="grid-list">${d.items.map(m => `<a class="card flat mini" href="#/easy/${encodeURIComponent(m.id)}"><span class="t">${esc(m.title)}</span>
          ${m.level !== d.target ? `<span class="meta"><span class="pill">${m.level}</span></span>` : ''}<span class="p">${esc(m.preview_en)}</span><span class="tiny muted">${m.words} 词 · 约 ${Math.max(1, Math.round(m.words / 120))} 分钟${m.ai ? ' ' + aiTag() : ''}</span></a>`).join('') || '<div class="empty"><p>这个难度的材料都读过了，明天会有新的。</p></div>'}</div></div>
      <p class="tiny muted">怎么读：不查词也能猜个大概就继续往下读；实在影响理解再点词。读完选一下难不难就行。</p></div>`;
  }
  async function easyRead(id) {
    const m = await api('/api/next/material?id=' + encodeURIComponent(id) + guestQuery(false));
    const ls = m.sentences, t0 = Date.now();
    let looked = 0;
    view.innerHTML = `<div><a class="link small" href="#/easy">← 轻松读</a></div>
      <div class="study-head"><span class="kicker">轻松读 · ${esc(m.level)} · ${ls.join(' ').split(/\s+/).length} 词</span><h1 class="h1">${esc(m.title_en || m.title)}</h1>
        ${m.title_en ? `<div class="muted small">${esc(m.title)}</div>` : ''}${aiNote(m) === null ? '' : aiMark(aiNote(m))}</div>
      <div class="reader easy-reader" id="easyText" lang="en">${ls.map((s, k) => `<span class="s">${wordSpans(s, () => 'w', ` data-s="${k}"`)}</span> `).join('')}</div>
      <div class="section stack-s" id="easyEnd"><div class="kicker">读完了，觉得怎么样？</div>
        <div class="choice three">${[['easy', '太简单'], ['ok', '刚好'], ['hard', '有点难']].map(([v, l]) => `<button class="opt" data-r="${v}"><span class="l">${l}</span></button>`).join('')}</div>
        <span class="tiny muted">选“太简单”，下一篇会难一点；选“有点难”，会简单一点。</span></div>`;
    document.getElementById('easyText').onclick = e => {
      const w = e.target.closest('.w'); if (!w || String(getSelection()).trim()) return;
      looked++; lookupSheet(w.dataset.w, ls[Number(w.dataset.s)], id, false);
    };
    view.querySelectorAll('[data-r]').forEach(b => b.onclick = async () => {
      view.querySelectorAll('[data-r]').forEach(x => { x.disabled = true; x.setAttribute('aria-pressed', String(x === b)); });
      const seconds = Math.max(5, Math.round((Date.now() - t0) / 1000));
      let r; try { r = await api('/api/next/easy/done', { pack: id, seconds, rating: b.dataset.r }); }
      catch (e) { toast(e.message); view.querySelectorAll('[data-r]').forEach(x => { x.disabled = false; }); return; }
      const st = r.stats;
      document.getElementById('easyEnd').insertAdjacentHTML('beforeend', `<div class="easy-done pop-in"><div class="easy-stats"><div><b>${r.words}</b><span class="tiny muted">读了（词）</span></div>
          <div><b>${r.wpm || '—'}</b><span class="tiny muted">词/分钟</span></div><div><b>${looked}</b><span class="tiny muted">查了（次）</span></div></div>
        <p class="small cheer">${st ? `这周已经读了 ${st.week_words.toLocaleString()} 词。` : ''}${looked <= 3 ? '几乎没查词就读完了，这正是轻松读要的感觉。' : '这篇查得有点多：觉得吃力的话，选“有点难”，下一篇就会简单一点。'}</p>
        <div class="row"><a class="btn primary" href="#/easy">再读一篇</a><a class="btn ghost" href="#/">回到今日</a></div></div>`);
      if (S.user) refreshHome().catch(() => {});
    });
  }
