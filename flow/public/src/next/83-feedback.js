  /* ---------- 问题反馈: what happened, the page it happened on, and up to three screenshots ---------- */
  // Anyone can send one, signed in or not (the server limits guests by a hashed address). The report carries the page
  // the learner came from, the site's version, the phone and browser, and the last few script errors: a page that
  // broke often says why in the console (ERRS, kept by 84-field.js). Read and closed in the operator console; nothing is
  // sent back.
  const FB_KINDS = [['display', '页面显示不对'], ['broken', '功能用不了'], ['content', '内容有错'], ['idea', '建议'], ['other', '其他']];
  const ASSET = (((document.querySelector('script[src*="next.js"]') || {}).src || '').split('v=')[1] || '').slice(0, 20);

  // A phone screenshot is large (1290 × 2796 on an iPhone): drawn at most 1600 px on its long side and sent as JPEG
  // under 650 KB, so three fit in one request. Read as a data: URL (the page's CSP allows data: images, not blob:).
  function shrinkShot(file) {
    return new Promise((ok, no) => {
      if (file.type && !/^image\//.test(file.type)) return no(new Error('只能添加图片'));
      const fr = new FileReader();
      fr.onerror = () => no(new Error('读不出这张图片，请换一张'));
      fr.onload = () => {
        const img = new Image();
        img.onerror = () => no(new Error('这个文件打不开，请换一张截图'));
        img.onload = () => {
          const k = Math.min(1, 1600 / Math.max(img.naturalWidth, img.naturalHeight, 1));
          const cv = document.createElement('canvas');
          cv.width = Math.max(1, Math.round(img.naturalWidth * k)); cv.height = Math.max(1, Math.round(img.naturalHeight * k));
          const g = cv.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, cv.width, cv.height); g.drawImage(img, 0, 0, cv.width, cv.height);
          for (const q of [0.82, 0.7, 0.55, 0.4]) { const d = cv.toDataURL('image/jpeg', q); if (d.length * 0.75 <= 650000) return ok(d); }
          no(new Error('这张图太大了，请裁小一点'));
        };
        img.src = fr.result;
      };
      fr.readAsDataURL(file);
    });
  }

  async function feedbackView() {
    const from = S.prevRoute && !/^feedback/.test(S.prevRoute) ? '#/' + S.prevRoute : '';
    let kind = 'display';
    const shots = [];
    view.innerHTML = `<div class="stack"><div><h1 class="h1">问题反馈</h1><span class="muted small">页面显示不对、功能用不了、内容有错，或者有建议，都可以告诉我们。</span></div>
      <form class="card stack fb" id="fbForm" novalidate>
        <div class="chips" role="radiogroup" aria-label="反馈类型">${FB_KINDS.map(([k, l]) => `<button type="button" class="chip" role="radio" data-k="${k}" aria-checked="${k === kind}">${l}</button>`).join('')}</div>
        <label class="stack-s" for="fbText"><b>发生了什么</b><span class="tiny muted">在哪个页面、点了什么、看到了什么。</span></label>
        <textarea id="fbText" rows="5" maxlength="1000" placeholder="比如：在「单词」页往下滑，底部的按钮跑到了屏幕中间。"></textarea>
        <div class="row between"><span class="tiny err" id="fbErr" role="alert"></span><span class="tiny muted" id="fbCount">0 / 1000</span></div>
        <div class="stack-s"><b>截图 <span class="tiny muted">可选，最多 3 张</span></b>
          <div class="fb-shots" id="fbShots"></div>
          <div><label class="btn" id="fbAdd">添加截图<input type="file" id="fbFile" accept="image/*" multiple class="sr-only"></label></div></div>
        ${S.user ? '' : `<label class="stack-s" for="fbContact"><b>联系方式 <span class="tiny muted">可不填</span></b></label>
        <input type="text" id="fbContact" maxlength="100" autocomplete="email" placeholder="邮箱或微信，方便我们问你细节">`}
        <label class="sr-only" aria-hidden="true">网址<input name="website" id="fbHp" tabindex="-1" autocomplete="off"></label>
        <p class="tiny muted">会一起发送：${from ? '你刚才在的页面、' : ''}网站版本、手机和浏览器型号${S.user ? '、你的账号' : ''}。截图只有管理员能看。</p>
        <button class="btn primary block" id="fbSend" type="submit">提交</button>
      </form></div>`;
    const form = document.getElementById('fbForm'), ta = document.getElementById('fbText'), box = document.getElementById('fbShots');
    const file = document.getElementById('fbFile'), add = document.getElementById('fbAdd'), send = document.getElementById('fbSend');
    const say = m => { document.getElementById('fbErr').textContent = m || ''; };
    form.querySelectorAll('[data-k]').forEach(b => b.onclick = () => {
      kind = b.dataset.k; form.querySelectorAll('[data-k]').forEach(x => x.setAttribute('aria-checked', String(x === b)));
    });
    ta.oninput = () => { document.getElementById('fbCount').textContent = `${ta.value.length} / 1000`; say(''); };
    const drawShots = () => {
      box.innerHTML = shots.map((d, k) => `<div class="fb-shot"><img src="${d}" alt="截图 ${k + 1}"><button type="button" data-rm="${k}" aria-label="去掉截图 ${k + 1}">×</button></div>`).join('');
      box.querySelectorAll('[data-rm]').forEach(b => b.onclick = () => { shots.splice(Number(b.dataset.rm), 1); drawShots(); });
      add.hidden = shots.length >= 3;
    };
    file.onchange = async () => {
      const list = [...file.files].slice(0, 3 - shots.length); file.value = '';
      add.classList.add('busy');
      for (const f of list) { try { shots.push(await shrinkShot(f)); say(''); } catch (x) { say(x.message); } }
      add.classList.remove('busy'); drawShots();
    };
    form.onsubmit = async e => {
      e.preventDefault();
      const text = ta.value.trim();
      if (text.length < 4) { say('请写几句发生了什么（至少 4 个字）'); ta.focus(); return; }
      send.disabled = true; send.textContent = '正在提交…';
      const c = document.getElementById('fbContact');
      try {
        await api('/api/feedback', { kind, text, contact: c ? c.value.trim() : '', page: from, images: shots, website: document.getElementById('fbHp').value,
          device: { ua: navigator.userAgent, w: innerWidth, h: innerHeight, dpr: devicePixelRatio || 1, lang: navigator.language || '', asset: ASSET,
            theme: matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light', standalone: STANDALONE(), wechat: IN_WECHAT, errors: ERRS.slice() } });
        view.innerHTML = `<div class="card done-card enter stack fb-done"><div class="big" aria-hidden="true">✓</div><h1 class="h1">已收到，谢谢！</h1>
          <p class="muted">${shots.length ? `连同 ${shots.length} 张截图一起收到了。` : ''}我们会尽快看，修好后会在新版本里更新。</p>
          <div class="row center"><a class="btn primary" href="${esc(from || '#/me')}">${from ? '回到刚才的页面' : '返回「我的」'}</a><button class="btn ghost" id="fbMore" type="button">再提一个</button></div></div>`;
        document.getElementById('fbMore').onclick = () => feedbackView();
      } catch (x) { say(x.message); send.disabled = false; send.textContent = '提交'; }
    };
  }
