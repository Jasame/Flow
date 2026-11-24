  /* ---------- 班级试用 (class_service.py): join a class with the teacher's code, leave at any time; a teacher sees the whole class's numbers only ---------- */
  // What a teacher sees and does not, said the same way before joining and on the teacher's own page.
  const CLASS_SEES = ['最近 7 天全班几人在学', '全班最常错的 5 个语法点'];
  const CLASS_NOT = ['你的名字、作业、答题和学习记录', '你一个人学了多少、错了什么'];
  const classLink = code => `${location.origin}/#/invite/${encodeURIComponent(code)}`;
  function classTerms(min) {
    return `<div class="cls-terms"><div><b>老师能看到</b><ul>${CLASS_SEES.map(x => `<li class="yes">${x}</li>`).join('')}</ul></div>
      <div><b>老师看不到</b><ul>${CLASS_NOT.map(x => `<li class="no">${x}</li>`).join('')}</ul></div></div>
      <p class="tiny muted">不满 ${min || 5} 人的班不出任何数字。随时可以退出，退出后老师的汇总里就不再算你。</p>`;
  }
  // 我的 → 班级: the class row's value, and the teacher's own group, filled in once /api/next/class answers.
  function meClass() {
    api('/api/next/class').then(k => {
      S.myClass = k;
      const v = document.getElementById('meClassV'); if (v) v.textContent = k.member ? k.member.name : '未加入';
      const at = document.getElementById('meTeach');
      if (at && k.teaching.length) at.innerHTML = `<section class="gsec" aria-label="我的班级"><h2 class="ghead">我的班级</h2><div class="glist">${k.teaching.map(t => grow(`#/class/${t.id}`, esc(t.name), t.active ? '全班汇总' : '已停用', '', 'me-class-teach')).join('')}</div>
        <p class="tiny muted gfoot">你是这些班的老师：这里只有全班的数字，看不到任何学生的名字、作业和记录。</p></section>`;
    }).catch(() => { const v = document.getElementById('meClassV'); if (v) v.textContent = ''; });
  }
  async function classSheet(code) {
    if (!S.user) return needLogin('登录后才能加入班级');
    let k = S.myClass;
    try { k = await api('/api/next/class'); S.myClass = k; } catch (e) { if (!k) return toast(e.message); }
    if (k.member) return classMemberSheet(k);
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">加入班级</h2>
      <p class="small">老师给你邀请码，加入后老师能看到全班的学习情况，但看不到你一个人的。</p>${classTerms(k.min)}
      <form id="clsF" class="stack" novalidate><div class="code-row"><label class="field">邀请码<input name="code" type="text" autocomplete="off" autocapitalize="characters" spellcheck="false" maxlength="12" placeholder="6 位，字母和数字" value="${esc(code || '')}" required></label>
        <button class="btn small" type="submit">查找</button></div></form>
      <div id="clsFound" class="stack-s" hidden></div>
      <p class="err" id="clsErr" role="alert"></p><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      const form = card.querySelector('#clsF'), err = card.querySelector('#clsErr'), found = card.querySelector('#clsFound');
      const look = async () => {
        err.textContent = ''; found.hidden = true;
        const c = form.code.value.trim();
        if (!c) return fieldError(form, err, { message: '请输入老师给你的邀请码', field: 'code' });
        try {
          const r = await api('/api/next/class/find', { code: c });
          // 年龄段 first, and under 14 a guardian's agreement (privacy_service): asked here when not on record yet
          const needAge = !S.user.age || (S.user.age === 'u14' && !S.user.guardian);
          found.innerHTML = `<div class="card sunk cls-found"><b>${esc(r.name)}</b><span class="small muted">老师 ${esc(r.teacher)}</span></div>
            ${r.teaching ? '<p class="small muted">你是这个班的老师，不用加入；在「我的 → 我的班级」里看全班汇总。</p>' : `${needAge ? ageFields(S.user.age, S.user.guardian) : ''}<button class="btn primary" id="clsJoin" type="button">加入这个班</button>`}`;
          found.hidden = false;
          if (needAge) bindAge(found, S.user.guardian);
          const j = found.querySelector('#clsJoin');
          if (j) j.onclick = async () => {
            const a = needAge ? readAge(found) : {}, p = needAge ? ageProblem(a, true, S.user.guardian) : '';
            if (p) { err.textContent = p; return; }
            j.disabled = true;
            try { S.myClass = await api('/api/next/class/join', { code: c, ...a }); if (needAge) Object.assign(S.user, { age: a.age, guardian: S.user.guardian || a.guardian }); closeSheet(); toast(`已加入「${r.name}」`); const v = document.getElementById('meClassV'); if (v) v.textContent = r.name; if (location.hash.startsWith('#/invite')) location.replace('#/me'); }
            catch (x) { err.textContent = x.message; j.disabled = false; }
          };
        } catch (x) { fieldError(form, err, { message: x.message, field: 'code' }); }
      };
      form.onsubmit = e => { e.preventDefault(); look(); };
      if (code) look();
    });
  }
  function classMemberSheet(k) {
    const m = k.member;
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">我的班级</h2>
      <div class="card sunk cls-found"><b>${esc(m.name)}</b><span class="small muted">老师 ${esc(m.teacher || '还没有指定')} · ${esc(m.joined)} 加入</span></div>
      ${m.active ? '' : '<p class="small">这个班级已经停用：老师不再看到汇总。你可以退出。</p>'}${classTerms(k.min)}
      <div id="clsLeave" class="stack-s"><button class="btn" id="clsOut" type="button">退出班级</button></div>
      <p class="err" id="clsErr" role="alert"></p><button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      const box = card.querySelector('#clsLeave'), err = card.querySelector('#clsErr');
      card.querySelector('#clsOut').onclick = () => {
        box.innerHTML = `<p class="small">退出后，老师的汇总里马上不再算你；你自己的学习记录都还在。以后想回来，再输入一次邀请码就行。</p>
          <div class="row"><button class="btn danger-btn" id="clsOutYes" type="button">确定退出</button><button class="btn ghost" id="clsOutNo" type="button">不退出</button></div>`;
        box.querySelector('#clsOutNo').onclick = closeSheet;
        box.querySelector('#clsOutYes').onclick = async e => {
          e.target.disabled = true;
          try { S.myClass = await api('/api/next/class/leave', {}); closeSheet(); toast(`已退出「${m.name}」`); const v = document.getElementById('meClassV'); if (v) v.textContent = '未加入'; }
          catch (x) { err.textContent = x.message; e.target.disabled = false; }
        };
      };
    });
  }
  // #/invite/<code>: the link a teacher sends: 我的, with the sheet open and the code filled in. (#/join is 认识语流's sign-up.)
  async function joinRoute(code) {
    await meView();
    if (!S.user) return openLogin('登录后就能加入班级（还没有账号可以先注册）');
    classSheet(code);
  }

  /* ---------- the teacher's page: #/class/<id> ---------- */
  async function classView(id) {
    if (!S.user) { view.innerHTML = '<div class="empty"><p>登录老师的语流账号后，才能看班级汇总。</p><button class="btn primary" id="lg">登录</button></div>'; document.getElementById('lg').onclick = () => openLogin(); return; }
    const k = await api(`/api/next/class/teach?id=${encodeURIComponent(id)}`);
    const weeks = k.weeks || [], top = Math.max(1, k.members || 1);
    const body = !k.active ? '<div class="card flat"><p>这个班级已经停用：不能再加入，这里也不再显示汇总。需要重新启用，请联系语流。</p></div>'
      : !k.ready ? `<div class="card flat stack-s"><b>班里还不到 ${k.min} 人</b><p class="small muted">满 ${k.min} 人后，这里显示全班的汇总：最近 7 天几人在学、全班最常错的 5 个语法点。为了保护每个学生，人少的时候不出任何数字。</p></div>`
      : `<div class="card flat stack-s cls-now"><div class="cls-big"><b>${k.active_7d}</b><span>/ ${k.members} 人</span></div><span class="small muted">近 7 天在学</span>
          <div class="cls-weeks" role="img" aria-label="近 4 周每周在学人数：${weeks.map(w => w.studied).join('、')}">${weeks.map((w, i) => `<div class="w${i === weeks.length - 1 ? ' now' : ''}"><div class="col"><i data-h="${Math.max(3, Math.round(w.studied / top * 100))}"></i></div><b>${w.studied}</b><span>${esc(w.label)}</span></div>`).join('')}</div>
          <p class="tiny muted">${esc(k.rule)}</p></div>
        <div class="card flat stack-s"><h2 class="h2">近 7 天全班最常错的 5 个语法点</h2>
          ${k.points.length ? `<ol class="cls-points">${k.points.map(p => `<li><a href="#/graph/${encodeURIComponent(p.node)}" data-tap="class-point"><span class="t">${esc(p.title)}</span><span class="small muted">${p.learners} 人错过</span><span class="go small">讲解 ›</span></a></li>`).join('')}</ol>
            <p class="tiny muted">做语法题、考试练习答错的，和 AI 批改写作时因为这个语法点改过的，都算。点进去是这个语法点的讲解和练习，上课可以直接用。</p>`
            : '<p class="small muted">近 7 天全班还没有做错的语法点（也可能还没人做语法题）。</p>'}</div>`;
    view.innerHTML = `<div class="stack cls-page"><div><span class="kicker">我的班级</span><h1 class="h1">${esc(k.name)}</h1><span class="small muted">${k.ready ? `${k.members} 人 · ` : ''}全班汇总，只有数字</span></div>
      ${body}
      <div class="card flat stack-s"><h2 class="h2">邀请学生</h2>
        <div class="cls-code" aria-label="邀请码">${esc(k.code)}</div>
        <p class="small muted">学生在「我的 → 班级」输入邀请码，或打开下面的链接加入。加入前会先告诉他们你能看到什么、看不到什么。</p>
        <div class="row"><button class="btn" id="clsCopy" type="button">复制链接</button><button class="btn ghost" id="clsQr" type="button">二维码</button></div>
        <canvas id="clsQrC" width="240" height="240" hidden aria-label="加入班级的二维码"></canvas></div>
      <p class="tiny muted">这里只有全班的数字，看不到任何学生的名字、作业和记录；退出班级的学生马上不再计入。</p></div>`;
    view.querySelectorAll('.cls-weeks i').forEach(i => { i.style.height = i.dataset.h + '%'; });  // CSP: no inline style attributes
    const link = classLink(k.code);
    document.getElementById('clsCopy').onclick = () => (navigator.clipboard ? navigator.clipboard.writeText(link) : Promise.reject()).then(() => toast('链接已复制，发给学生就行'), () => prompt('复制这个链接发给学生', link));
    document.getElementById('clsQr').onclick = e => {
      const cv = document.getElementById('clsQrC'); cv.hidden = !cv.hidden; e.target.textContent = cv.hidden ? '二维码' : '收起二维码';
      if (!cv.hidden) QR.draw(cv.getContext('2d'), link, 0, 0, 240);
    };
  }
