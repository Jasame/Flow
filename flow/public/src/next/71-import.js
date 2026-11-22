  /* ---------- 我的文章: paste any English text and study it with Flow's tools ---------- */
  async function importView() {
    if (!S.user) return needLogin('登录后可以导入自己想读的英文文章，用点词、AI 讲解、生词复习来学。');
    const d = await api('/api/next/import');
    if (!S.meta) S.meta = await api('/api/next/meta');
    view.innerHTML = `<h1 class="h1">我的文章</h1><span class="muted small">论文、新闻、小说章节都可以：贴进来，就能点词查义、AI 讲解句子、听写跟读、把生词加入复习。只有你自己看得到。</span>
      <form class="card flat section stack" id="impF"><input name="title" type="text" maxlength="80" placeholder="标题（可不填）" aria-label="标题">
        <textarea name="text" rows="8" lang="en" aria-label="英文正文" placeholder="粘贴英文正文（200–8000 个字符）"></textarea>
        <select name="theme" aria-label="话题"><option value="">话题：按内容自动判断</option>${S.meta.themes.map(t => `<option value="${t.id}">话题：${esc(t.label)}</option>`).join('')}</select>
        <div class="row between"><span class="muted tiny" id="impN">0 字符</span><button class="btn primary">保存并开始学</button></div></form>
      <div class="section stack-s"><div class="row between"><h2 class="h2">已保存</h2><span class="muted tiny">${d.items.length} / ${d.max}</span></div>
      ${d.items.length ? `<div class="grid-list">${d.items.map(a => `<div class="card flat stack-s imp"><div class="row between"><b>${esc(a.title)}</b><span class="pill">${esc(a.level)}</span></div>
        <div class="muted small">${esc(a.preview)}…</div><div class="row"><a class="btn small primary" href="#/m/${encodeURIComponent(a.id)}/read">学这篇</a>
        ${a.enriched ? '<span class="pill green">已出题</span>' : `<button class="btn small" data-enrich="${esc(a.id)}">✦ AI 出题和挑表达</button>`}
        <button class="btn small ghost" data-del="${esc(a.id)}">删除</button></div></div>`).join('')}</div>` : '<div class="empty"><p>还没有导入的文章。</p></div>'}</div>`;
    const f = document.getElementById('impF');
    f.text.oninput = () => { document.getElementById('impN').textContent = f.text.value.length + ' 字符'; };
    f.onsubmit = async e => {
      e.preventDefault(); const b = f.querySelector('button'); b.disabled = true;
      try { const r = await api('/api/next/import', { title: f.title.value, text: f.text.value, theme: f.theme.value }); toast(r.existing ? '这篇已经导入过了' : `已保存，估计难度 ${r.level}`); location.hash = `#/m/${encodeURIComponent(r.id)}/read`; }
      catch (x) { toast(x.message); b.disabled = false; }
    };
    view.querySelectorAll('[data-enrich]').forEach(b => b.onclick = async () => {
      b.disabled = true; b.innerHTML = '<span class="spin"></span> 正在出题…';
      try { await api('/api/next/import/enrich', { id: b.dataset.enrich, request_id: rid('ie') }); delete MAT[b.dataset.enrich]; toast('已生成导读、理解题和表达'); importView(); }
      catch (x) { toast(x.message); b.disabled = false; b.textContent = '✦ AI 出题和挑表达'; }
    });
    view.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => { if (!confirm('删除这篇文章？')) return; try { await api('/api/next/import/delete', { id: b.dataset.del }); importView(); } catch (x) { toast(x.message); } });
  }

