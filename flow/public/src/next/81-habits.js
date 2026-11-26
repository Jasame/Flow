  /* ---------- 我的 → 使用习惯 (the user, 2026-11-26: 「这些用户习惯的设置都可以放在一起……只有两个的话……点一下右边，
     点一下左边……字体标准大号、特大号……做成那种滑动线条，放在最底部」 and 「能做成一个页面就不要做成两个界面」; B9's
     spec, today-regroup/final): one screen with no sheets: the two-choice settings as switches in two columns (点哪边就是
     哪个), the text size as a slider at the bottom with a sample under it. Each takes effect at once and is kept with
     the account (07-prefs.js; 主题色 07-accent.js; 今日的样子 is 今日's own switch). ---------- */
  function habitsView() {
    const two = (a, b) => [a, b];
    const blocks = [];
    // 今日的样子: the same setting as the switch on 今日 (B1), for a learner with a plan
    if (typeof todayView === 'function' && typeof setTodayView === 'function' && S.user && S.home && S.home.profile)
      blocks.push(['today', '今日的样子', two(['list', '列表'], ['cards', '卡片']), todayView()]);
    blocks.push(['accent', '主题色', ACCENTS, accentNow()]);
    blocks.push(['card_new', '新词卡', two(['simple', '简洁'], ['detailed', '详细']), KNOW.view('new')]);
    blocks.push(['card_review', '复习卡', two(['simple', '简洁'], ['detailed', '详细']), KNOW.view('review')]);
    blocks.push(['know', '背单词「认识」在', two(['left', '左边'], ['right', '右边']), KNOW.side()]);
    blocks.push(['lh', '行距', TEXT_LH, TEXT.lh]);
    const at = Math.max(0, TEXT_SIZES.findIndex(x => x[0] === TEXT.size));
    view.innerHTML = `<h1 class="h1 hb-h"><a class="hb-back" href="#/me" aria-label="返回我的">‹</a>使用习惯</h1>
      <div class="hb-grid">${blocks.map(([key, name, opts, cur]) => `<div class="hb-card"><span class="hb-name" id="hb-${key}">${esc(name)}</span>
        <div class="hb-seg" role="radiogroup" aria-labelledby="hb-${key}">${opts.map(([v, l]) => `<button type="button" role="radio" data-hb="${key}" data-v="${v}" aria-checked="${v === cur}">${key === 'accent' ? `<i class="hb-dot" data-c="${v}" aria-hidden="true"></i>` : ''}${esc(l)}</button>`).join('')}</div></div>`).join('')}</div>
      <div class="hb-card hb-size"><div class="hb-row"><span class="hb-name" id="hbSizeN">字号</span><b id="hbSizeV">${TEXT_SIZES[at][1]}</b></div>
        <div class="hb-slide"><span class="hb-a" aria-hidden="true">A</span>
          <div class="hb-track"><i aria-hidden="true"></i><i aria-hidden="true"></i><i aria-hidden="true"></i><input class="hb-range" id="hbSize" type="range" min="0" max="2" step="1" value="${at}" aria-labelledby="hbSizeN" aria-valuetext="${TEXT_SIZES[at][1]}"></div>
          <span class="hb-a big" aria-hidden="true">A</span></div>
        <div class="hb-ticks" aria-hidden="true">${TEXT_SIZES.map(([, l]) => `<span>${l}</span>`).join('')}</div>
        <p class="text hb-sample" lang="en">The first time you switch on a pair of noise-cancelling headphones, the world goes quiet.</p></div>`;
    view.querySelectorAll('[data-hb]').forEach(b => b.onclick = async () => {
      if (b.getAttribute('aria-checked') === 'true') return;
      const key = b.dataset.hb, v = b.dataset.v, seg = b.parentNode;
      seg.querySelectorAll('[role=radio]').forEach(x => x.setAttribute('aria-checked', String(x === b)));
      if (key === 'today') setTodayView(v);
      else if (key === 'accent') { await setAccent(v); seg.querySelectorAll('[role=radio]').forEach(x => x.setAttribute('aria-checked', String(x.dataset.v === accentNow()))); }  // back, if it could not be saved
      else if (key === 'card_new' || key === 'card_review') KNOW.setView(key === 'card_new' ? 'new' : 'review', v);
      else if (key === 'know') { KNOW.set(v); TIPS.mark('know-side'); }  // chosen here: 「『认识』换到右边了」 is not needed (08-tips.js)
      else if (key === 'lh') { TEXT.lh = v; save('flow-next-text', TEXT); applyText(); prefSave('lh', v); }
    });
    // 字号: three stops; the sample follows while it moves, the choice is kept when let go
    const r = document.getElementById('hbSize');
    const shown = () => { const s = TEXT_SIZES[Number(r.value)]; r.setAttribute('aria-valuetext', s[1]); document.getElementById('hbSizeV').textContent = s[1]; r.parentNode.dataset.at = r.value; };
    r.oninput = () => { TEXT.size = TEXT_SIZES[Number(r.value)][0]; applyText(); shown(); };
    r.onchange = () => { save('flow-next-text', TEXT); prefSave('size', TEXT.size); };
    shown();
  }
