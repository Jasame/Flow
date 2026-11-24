/* xmc.hk/flow · 语流 Flow 运营后台。数据来自 /flow/api/（只在 xmc.hk 的 Cloudflare Access 后面可达）。 */
(function () {
  'use strict';
  var API = '/flow/api';
  var main = document.getElementById('main');
  var ST = { tab: 'overview', filters: { role: '', level: '', flow: '' }, page: 1, q: '', def: null, me: null };
  // 管理员 sees everything and may change things; 只看数据 sees the numbers only (the server enforces it, the page just
  // leaves out what would answer 403).
  function isAdmin() { return !ST.me || ST.me.role === 'admin'; }
  function when(t) { return t ? new Date(t * 1000).toLocaleString('zh-CN', { hour12: false }) : '—'; }
  var DIST = ['#d4553f', '#e79a4a', '#c9c9c2', '#7cc79c', '#1f9d55'];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function n(v) { return Number(v || 0).toLocaleString('zh-CN'); }
  function pct(a, b) { return b ? Math.round(100 * a / b) : 0; }
  function getJSON(path) {
    return fetch(API + path, { credentials: 'same-origin' }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
        return j;
      });
    });
  }
  function postJSON(path, body) {
    return fetch(API + path, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'xmc' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status)); return j; }); });
  }
  function fail(e) { main.innerHTML = '<div class="card"><p class="err">' + esc(e.message) + '</p><p class="muted">Flow 服务没有启动管理端口，或 nginx 的 /flow/api/ 转发没有配置。</p></div>'; }

  function bars(options, total, opts) {
    opts = opts || {};
    if (total == null) total = options.reduce(function (a, o) { return a + o.count; }, 0);
    var max = Math.max.apply(null, options.map(function (o) { return o.count; }).concat([1]));
    var list = opts.sort ? options.slice().sort(function (a, b) { return b.count - a.count; }) : options;
    return '<div class="bars">' + list.map(function (o) {
      return '<div class="bar' + (o.count === max && o.count > 0 ? ' top' : '') + '"><span class="bar-label">' + esc(o.label) + '</span>' +
        '<span class="bar-val">' + n(o.count) + ' · ' + pct(o.count, total) + '%</span>' +
        '<div class="bar-track"><div class="bar-fill" style="width:' + pct(o.count, max) + '%"></div></div></div>';
    }).join('') + '</div>';
  }

  // how long ago: 刚刚 / 5 分钟前 / 3 小时前 / 昨天 / 4 天前 / 11月2日
  function rel(t) {
    if (!t) return '—';
    var s = Date.now() / 1000 - t;
    if (s < 120) return '刚刚';
    if (s < 3600) return Math.round(s / 60) + ' 分钟前';
    var d0 = new Date(); d0.setHours(0, 0, 0, 0);
    var days = Math.ceil((d0.getTime() / 1000 - t) / 86400);
    if (t >= d0.getTime() / 1000) return Math.round(s / 3600) + ' 小时前';
    if (days <= 1) return '昨天';
    if (days < 30) return days + ' 天前';
    return new Date(t * 1000).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' });
  }
  function relDay(iso) { return iso ? rel(new Date(iso + 'T12:00:00+08:00').getTime() / 1000).replace(/\d+ (分钟|小时)前|刚刚/, '今天') : '—'; }
  function busy(b, p) { b.disabled = true; return p.then(function (r) { b.disabled = false; return r; }, function (e) { b.disabled = false; alert(e.message); throw e; }); }
  var LEVEL = { A2: 'A2 入门', B1: 'B1 中级', B2: 'B2 中高级', C1: 'C1 高级' };

  /* ---------- 概览：几个最重要的数字，和要处理的事 ---------- */
  function overview() {
    getJSON('/overview').then(function (d) {
      var ai = d.ai, max = Math.max.apply(null, ai.week.map(function (x) { return x.count; }).concat([1])), lim = ai.limits || {};
      var todo = [];
      if (isAdmin() && d.feedback_open) todo.push(['#feedback', '待处理的问题反馈', n(d.feedback_open) + ' 条']);
      if (isAdmin() && d.errors_24h) todo.push(['#errors', '近 24 小时服务器出错', n(d.errors_24h) + ' 次']);
      if (d.daily.status === 'failed' || d.daily.status === 'interrupted') todo.push(['#tasks', '今日热点没有生成成功', '去重新生成']);
      if (d.task === 'running') todo.push(['#tasks', '例句预生成正在运行', '看进度']);
      if (d.backup && !d.backup.ok) todo.push(['#tasks', '最近一次备份失败', when(d.backup.created)]);
      if (ai.users_at_limit) todo.push(['#ai', '今天有账号用满了 AI 次数', n(ai.users_at_limit) + ' 个']);
      var info = [];
      if (d.announce) info.push(['#announce', '学员正在看到公告', esc(d.announce.text.slice(0, 24)) + (d.announce.text.length > 24 ? '…' : '')]);
      if (d.hidden_materials) info.push(['#content', '已下架的材料', n(d.hidden_materials) + ' 篇']);
      if (isAdmin() && d.disabled) info.push(['#learners/f=disabled', '已停用的账号', n(d.disabled) + ' 个']);
      var li = function (x) { return '<li><a href="' + x[0] + '"><b>' + x[1] + '</b><span class="muted">' + x[2] + ' →</span></a></li>'; };
      main.innerHTML =
        '<div class="head-row"><div><h1>语流 Flow 概览</h1><p class="muted">flowlang.cn · ' + (d.server ? '数据来自' + esc(d.server) + ' · ' : '') + '更新于 ' + new Date(d.generated_at * 1000).toLocaleString('zh-CN') + '</p></div>' +
        '<div class="toolbar"><button class="btn" id="reload">刷新</button></div></div>' +
        '<div class="kpi-grid k5">' +
          kpi('注册用户', n(d.users), '填了学习档案 ' + n(d.profiles) + ' 人 · 还没开始学 ' + n(d.never_started) + ' 人') +
          kpi('近 7 天活跃', n(d.active_7d), '近 24 小时 ' + n(d.active_1d) + ' 人 · <a href="#funnel" style="color:var(--accent)">看留存 →</a>') +
          kpi('今日 AI 调用', n(ai.today), ai.site_limit ? ('全站上限 ' + n(ai.site_limit) + ' · 已用 ' + pct(ai.today, ai.site_limit) + '%') : '全站不设上限') +
          kpi('问卷回答', n(d.survey_responses), '<a href="#survey" style="color:var(--accent)">查看统计 →</a>') +
          (isAdmin() && d.feedback_open != null ? kpi('待处理反馈', n(d.feedback_open), '<a href="#feedback" style="color:var(--accent)">去处理 →</a>') : kpi('员工账号', n(d.admins), 'AI 次数不限')) +
        '</div>' +
        '<div class="grid2">' +
          '<section class="card"><h2>要处理的事</h2>' + (todo.length ? '<ul class="todo">' + todo.map(li).join('') + '</ul>' : '<p class="ok-line">都处理好了。</p>') +
            (info.length ? '<h2 style="margin-top:18px">正在生效</h2><ul class="todo">' + info.map(li).join('') + '</ul>' : '') + '</section>' +
          '<section class="card"><h2>近 7 天 AI 调用</h2>' +
            '<div class="spark">' + ai.week.map(function (x) { return '<div title="' + esc(x.day + '：' + x.count) + '" style="height:' + Math.max(3, pct(x.count, max)) + '%"></div>'; }).join('') + '</div>' +
            '<div class="spark-days">' + ai.week.map(function (x) { return '<span>' + esc(x.day.slice(5)) + '</span>'; }).join('') + '</div>' +
            '<dl class="kv" style="margin-top:14px"><dt>模型</dt><dd>' + esc(ai.model || '未配置') + '</dd>' +
            '<dt>每账号每日上限</dt><dd>' + (ai.user_limit ? n(ai.user_limit) + ' 次（员工账号不受限）' : '不限') + (lim.user_limit_source === 'console' ? ' <span class="pill">后台设置</span>' : '') + '</dd>' +
            '<dt>全站每日上限</dt><dd>' + (ai.site_limit ? n(ai.site_limit) + ' 次' : '不限') + (lim.site_limit_source === 'console' ? ' <span class="pill">后台设置</span>' : '') + '</dd>' +
            '<dt>重置时间</dt><dd>每天北京时间 08:00（UTC 0 点）</dd></dl>' +
            '<p><a class="btn" href="#ai">看明细' + (isAdmin() ? '、改额度' : '') + '</a></p></section>' +
          '<section class="card"><h2>备份和每日热点</h2><dl class="kv">' +
            '<dt>最近备份</dt><dd>' + (d.backup ? (d.backup.ok ? '成功 · ' : '<span class="err">失败</span> · ') + esc(when(d.backup.created)) : '还没有备份记录') + '</dd>' +
            '<dt>今日热点</dt><dd>' + esc(DAILY[d.daily.status] || d.daily.status) +
              (d.daily.enabled ? '' : '（服务器没有开启联网检索，FLOW_AI_GROUNDING）') + (d.daily.error ? '<div class="muted">' + esc(d.daily.error) + '</div>' : '') + '</dd>' +
            '<dt>最近几天</dt><dd>' + (d.daily.latest.length ? d.daily.latest.map(function (x) { return esc(x.day.slice(5)); }).join('、') : '—') + '</dd>' +
          '</dl><p><a class="btn" href="#tasks">后台任务 →</a></p></section>' +
        '</div>';
      document.getElementById('reload').onclick = overview;
    }).catch(fail);
  }
  var DAILY = { complete: '已生成', running: '正在生成', failed: '生成失败', interrupted: '中断了', waiting: '还没生成', disabled: '没有开启' };
  function kpi(label, val, sub) { return '<div class="kpi"><div class="kpi-label">' + label + '</div><div class="kpi-val">' + val + '</div><div class="kpi-sub">' + sub + '</div></div>'; }

  /* ---------- 问卷统计 ---------- */
  function filterSelect(id, q) {
    if (!q) return '';
    return '<label class="muted" style="font-size:12.5px">' + esc(q.label.replace(/[？?].*$/, '')) + ' <select data-filter="' + id + '"><option value="">全部</option>' +
      q.options.map(function (o) { return '<option' + (ST.filters[id] === o ? ' selected' : '') + '>' + esc(o) + '</option>'; }).join('') + '</select></label>';
  }
  function surveyStats() {
    var qs = Object.keys(ST.filters).filter(function (k) { return ST.filters[k]; }).map(function (k) { return k + '=' + encodeURIComponent(ST.filters[k]); }).join('&');
    Promise.all([ST.def ? Promise.resolve(ST.def) : getJSON('/survey/definition'), getJSON('/survey/summary' + (qs ? '?' + qs : ''))]).then(function (res) {
      var def = ST.def = res[0], s = res[1];
      var byId = {}; def.sections.forEach(function (sec) { sec.questions.forEach(function (q) { byId[q.id] = q; }); });
      var max = Math.max.apply(null, s.by_day.map(function (x) { return x.count; }).concat([1]));
      var html =
        '<div class="head-row"><div><h1>' + esc(s.survey.title) + '</h1><p class="muted">匿名问卷 · 共 ' + n(s.total) + ' 份有效回答' +
          (s.hidden ? '（另有 ' + n(s.hidden) + ' 份已隐藏）' : '') + (s.median_seconds ? ' · 中位用时 ' + Math.round(s.median_seconds / 60 * 10) / 10 + ' 分钟' : '') + '</p></div>' +
        '<div class="toolbar"><a class="btn" href="https://flowlang.cn/survey" target="_blank" rel="noopener">问卷链接</a><button class="btn" id="copyLink">复制链接</button>' + (isAdmin() ? '<a class="btn primary" href="' + API + '/survey/export.csv">导出 CSV</a>' : '') + '</div></div>' +
        '<div class="card toolbar">' + filterSelect('role', byId.role) + filterSelect('level', byId.level) + filterSelect('flow', byId.flow) +
          (qs ? '<button class="btn" id="clearF">清除筛选</button>' : '') + '</div>';
      if (!s.total) {
        main.innerHTML = html + '<div class="card empty">' + (qs ? '这个筛选条件下还没有回答。' : '还没有人填写。把问卷链接 https://flowlang.cn/survey 发出去吧。') + '</div>';
        bindStats(); return;
      }
      if (s.by_day.length > 1) {
        html += '<section class="card"><h2>每日回收</h2><div class="spark">' + s.by_day.slice(-30).map(function (x) { return '<div title="' + esc(x.day + '：' + x.count) + '" style="height:' + Math.max(3, pct(x.count, max)) + '%"></div>'; }).join('') + '</div></section>';
      }
      var cards = s.questions.map(function (q) {
        var head = '<h2>' + esc(q.label) + '</h2><p class="muted" style="margin:-8px 0 12px;font-size:12px">' + n(q.answered) + ' 人作答' + (q.type === 'multi' ? ' · 多选，比例按作答人数计' : '') + '</p>';
        if (q.type === 'single' || q.type === 'multi') return '<section class="card">' + head + bars(q.options, q.answered, { sort: q.type === 'multi' }) + '</section>';
        if (q.type === 'matrix') {
          var rows = q.rows.slice().sort(function (a, b) { return (b.average || 0) - (a.average || 0); });
          return '<section class="card">' + head + '<div class="bars">' + rows.map(function (r) {
            var tot = r.distribution.reduce(function (a, b) { return a + b; }, 0) || 1;
            return '<div class="bar"><span class="bar-label">' + esc(r.label) + '</span><span class="bar-val">平均 ' + (r.average == null ? '—' : r.average.toFixed(2)) + ' / 5</span>' +
              '<div class="dist">' + r.distribution.map(function (c, i) { return '<i style="width:' + (100 * c / tot) + '%;background:' + DIST[i] + '" title="' + (i + 1) + ' 分：' + c + ' 人"></i>'; }).join('') + '</div></div>';
          }).join('') + '</div><div class="legend">' + DIST.map(function (c, i) { return '<span style="--c:' + c + '">' + (i + 1) + ' 分</span>'; }).join('') + '</div></section>';
        }
        return '<section class="card" style="grid-column:1/-1">' + head + (q.samples.length ? '<div class="quotes">' + q.samples.map(function (x) {
          return '<div class="quote">' + esc(x.text) + '<small>#' + x.id + ' · ' + esc(x.day) + '</small></div>'; }).join('') + '</div>' : '<p class="muted">暂无</p>') +
          (q.answered > q.samples.length ? '<p class="muted" style="margin-top:8px;font-size:12px">只显示最近 ' + q.samples.length + ' 条，完整内容见「逐条回答」或导出 CSV。</p>' : '') + '</section>';
      });
      main.innerHTML = html + '<div class="grid2">' + cards.join('') + '</div>';
      bindStats();
    }).catch(fail);
  }
  function bindStats() {
    main.querySelectorAll('[data-filter]').forEach(function (el) {
      el.onchange = function () { ST.filters[el.dataset.filter] = el.value; surveyStats(); };
    });
    var c = document.getElementById('clearF'); if (c) c.onclick = function () { ST.filters = { role: '', level: '', flow: '' }; surveyStats(); };
    var cp = document.getElementById('copyLink');
    if (cp) cp.onclick = function () {
      var url = 'https://flowlang.cn/survey';
      (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject()).then(function () { cp.textContent = '已复制'; }, function () { prompt('复制问卷链接', url); });
    };
  }

  /* ---------- 逐条回答 ---------- */
  function fmt(q, v) {
    if (v == null || v === '') return '<span class="muted">未填</span>';
    if (Array.isArray(v)) return esc(v.join('；'));
    if (typeof v === 'object') return (q && q.rows ? q.rows : Object.keys(v)).map(function (r) { return esc(r) + '：' + (v[r] || '—'); }).join('<br>');
    return esc(v);
  }
  function responses() {
    Promise.all([ST.def ? Promise.resolve(ST.def) : getJSON('/survey/definition'), getJSON('/survey/responses?page=' + ST.page + '&q=' + encodeURIComponent(ST.q))]).then(function (res) {
      var def = ST.def = res[0], d = res[1];
      var qs = []; def.sections.forEach(function (s) { qs = qs.concat(s.questions); });
      var pages = Math.max(1, Math.ceil(d.total / d.per_page));
      main.innerHTML =
        '<div class="head-row"><div><h1>逐条回答</h1><p class="muted">共 ' + n(d.total) + ' 条（含已隐藏）。隐藏的回答不计入统计，也不导出。</p></div>' +
        '<form class="toolbar" id="searchF"><input class="input" id="q" type="search" placeholder="搜索回答内容" value="' + esc(ST.q) + '"><button class="btn">搜索</button></form></div>' +
        (d.items.length ? '<div class="resp">' + d.items.map(function (r) {
          return '<article class="resp-item' + (r.hidden ? ' hidden' : '') + '"><div class="resp-head"><b>#' + r.id + '</b>' +
            '<span class="muted">' + esc(new Date(r.created * 1000).toLocaleString('zh-CN')) + ' · 用时 ' + Math.round((r.seconds || 0) / 60 * 10) / 10 + ' 分钟</span>' +
            '<span>' + (r.hidden ? '<span class="pill off">已隐藏</span> ' : '') + '<button class="btn" data-hide="' + r.id + '" data-v="' + (r.hidden ? 0 : 1) + '">' + (r.hidden ? '恢复' : '隐藏（无效回答）') + '</button></span></div>' +
            '<dl class="resp-grid">' + qs.map(function (q) { return '<dt>' + esc(q.label) + '</dt><dd>' + fmt(q, r.answers[q.id]) + '</dd>'; }).join('') + '</dl></article>';
        }).join('') + '</div>' : '<div class="card empty">没有找到回答。</div>') +
        (pages > 1 ? '<div class="pager"><button class="btn" id="prev"' + (ST.page <= 1 ? ' disabled' : '') + '>上一页</button><span class="muted num">' + ST.page + ' / ' + pages + '</span><button class="btn" id="next"' + (ST.page >= pages ? ' disabled' : '') + '>下一页</button></div>' : '');
      document.getElementById('searchF').onsubmit = function (e) { e.preventDefault(); ST.q = document.getElementById('q').value.trim(); ST.page = 1; responses(); };
      var p = document.getElementById('prev'), nx = document.getElementById('next');
      if (p) p.onclick = function () { ST.page--; responses(); };
      if (nx) nx.onclick = function () { ST.page++; responses(); };
      main.querySelectorAll('[data-hide]').forEach(function (b) {
        b.onclick = function () {
          b.disabled = true;
          postJSON('/survey/hide', { id: Number(b.dataset.hide), hidden: b.dataset.v === '1' }).then(responses).catch(function (e) { alert(e.message); b.disabled = false; });
        };
      });
    }).catch(fail);
  }

  /* ---------- 学习数据 ---------- */
  var BOOK = { core: '基础', mid: '进阶', high: '高阶', adv: '精通', ext: '拓展', zk: '中考', gk: '高考', cet4: '四级', cet6: '六级', ky: '考研', tem4: '专四', tem8: '专八', ielts: '雅思', toefl: '托福', gre: 'GRE', nawl: '学术英语', bsl: '商务英语' };
  var STEP = { listen: '听', read: '读', check: '理解题', output: '用出来（AI 改写）' };
  var AIK = { 'next-rewrite': '仿写改写', 'next-explain': '句子讲解', 'next-variant': '难度改写', 'next-shadow': '跟读点评', 'next-examples': 'AI 例句',
    'next-retell': '复述', 'next-dialog': '情景对话', 'next-essay': '短文批改', 'next-translate': '翻译批改', 'next-transsrc': '翻译原句', 'next-say': '发音检查', 'next-enrich': '导入文章出题' };
  var RATE = { again: '忘了', hard: '模糊', good: '记得', easy: '很熟', known: '标为熟知', used: '写作用对', misused: '写作用错', lookup: '阅读时查词' };
  function learningView() {
    getJSON('/learning').then(function (d) {
      var max = Math.max.apply(null, d.active_days.map(function (x) { return x.count; }).concat([1]));
      var c = d.cohort, f = d.funnel_7d;
      var list = function (obj, names) {
        var keys = Object.keys(obj || {}); if (!keys.length) return '<p class="muted">暂无数据</p>';
        return bars(keys.map(function (k) { return { label: names[k] || k, count: obj[k] }; }), null, { sort: true });
      };
      main.innerHTML =
        '<div class="head-row"><div><h1>学习数据</h1><p class="muted">按北京时间统计 · 更新于 ' + new Date(d.generated_at * 1000).toLocaleString('zh-CN') + '</p></div>' +
        '<div class="toolbar"><button class="btn" id="reload">刷新</button></div></div>' +
        '<div class="kpi-grid">' +
          kpi('今天在学', n(d.active_today), '近 7 天 ' + n(d.active_7d) + ' 人 · 近 30 天 ' + n(d.active_30d) + ' 人') +
          kpi('次日回来', c.joined ? pct(c.d1, c.joined) + '%' : '—', '近 30 天开始学习的 ' + n(c.joined) + ' 人；一周内回来 ' + (c.joined ? pct(c.week, c.joined) + '%' : '—')) +
          kpi('近 7 天复习', n(d.reviews_7d), d.true_retention == null ? '还没有隔天的复习' : '隔天复习记得的比例 ' + Math.round(d.true_retention * 100) + '%（目标约 90%）') +
          kpi('开了背词计划', n(Object.keys(d.vocab_plans).reduce(function (a, k) { return a + d.vocab_plans[k]; }, 0)), '开启复习提醒 ' + n(d.reminders_on) + ' 人 · 全站单词卡 ' + n(d.cards_total)) +
        '</div>' +
        '<section class="card"><h2>近 14 天每天在学的人数</h2>' +
          '<div class="spark">' + d.active_days.map(function (x) { return '<div title="' + esc(x.day + '：' + x.count + ' 人') + '" style="height:' + Math.max(3, pct(x.count, max)) + '%"></div>'; }).join('') + '</div>' +
          '<div class="spark-days">' + d.active_days.map(function (x, i) { return '<span>' + (i % 2 ? '' : esc(x.day.slice(5))) + '</span>'; }).join('') + '</div></section>' +
        '<div class="grid2">' +
          '<section class="card"><h2>近 7 天学习步骤</h2><p class="muted">每篇材料完成到哪一步（次数）。从「读」到「用出来」掉得越多，越说明后面的步骤需要更好的引导。</p>' +
            bars(['listen', 'read', 'check', 'output'].map(function (k) { return { label: STEP[k], count: f[k] || 0 }; }), null, {}) + '</section>' +
          '<section class="card"><h2>近 7 天复习的选择</h2>' + list(d.ratings_7d, RATE) + '</section>' +
          '<section class="card"><h2>词书选择</h2>' + list(d.vocab_plans, BOOK) + '</section>' +
          '<section class="card"><h2>近 7 天新加的词</h2>' + list(d.words_added_7d, { book: '词书每日新词', saved: '读文章时收藏', import: '自己导入' }) + '</section>' +
          '<section class="card"><h2>近 7 天 AI 功能使用</h2>' + list(d.ai_7d, AIK) + '</section>' +
          '<section class="card"><h2>近 7 天最多人学的材料</h2>' + (d.top_materials_7d.length ? bars(d.top_materials_7d.map(function (m) { return { label: m.title, count: m.learners }; }), null, {}) : '<p class="muted">暂无数据</p>') +
            '<p class="muted">共 ' + n(d.materials) + ' 篇精选材料</p></section>' +
        '</div>';
      document.getElementById('reload').onclick = learningView;
    }).catch(fail);
  }

  // 页面报错: what learners' browsers reported (field_service.py), grouped by problem; which phones and releases.
  function clientIssues(c) {
    if (!c) return '';
    return '<div class="head-row fd-gap"><div><h1>页面报错</h1><p class="muted">学员的浏览器上报的问题（近 ' + c.days + ' 天，共 ' + n(c.total) + ' 次）：脚本出错、资源没加载出来、请求失败、声音放不出来。不记账号和地址。</p></div></div>' +
      (c.groups.length ? '<section class="card"><table class="cmp fd-issues"><thead><tr><th>问题</th><th>页面</th><th class="num">次数</th><th>手机和浏览器</th><th>版本</th></tr></thead><tbody>' +
        c.groups.map(function (g) {
          return '<tr><td><span class="pill">' + esc(g.kind_label) + '</span> ' + esc(g.message) + (g.source ? '<div class="muted small">' + esc(g.source) + '</div>' : '') + '</td>' +
            '<td>' + esc(g.page) + '</td><td class="num">' + n(g.count) + '<div class="muted small">' + g.days + ' 天</div></td>' +
            '<td class="small">' + g.platforms.map(function (x) { return esc(x[0]) + ' ' + n(x[1]); }).join('<br>') + '</td>' +
            '<td class="small">' + g.releases.map(function (x) { return esc(x[0]); }).join('、') + '</td></tr>';
        }).join('') + '</tbody></table></section>' : '<section class="card"><p>没有页面报错。</p></section>');
  }

  // 打开速度: how long learners waited for the first page (field_service.speed), and where the time went.
  var SP = { days: 7 };
  function speedView() {
    getJSON('/speed?days=' + SP.days).then(function (d) {
      var o = d.overall, sec = function (v) { return v == null ? '—' : (v / 1000).toFixed(1) + ' 秒'; };
      var PH = { startup: '打开前（跳转、唤醒、后台脚本）', dns: '查域名', connect: '建立连接', tls: '加密握手', ttfb: '服务器响应', html: '下载页面', scripts: '等脚本下载完', boot: '运行脚本', home_api: '取首页数据', render: '画出页面' };
      // one bar per set of medians: every visit, then the slowest quarter (where a slow opening really waits)
      var bar = function (ph) {
        return '<div class="sp-bar">' + Object.keys(PH).map(function (k, i) {
          var v = ph[k]; return v ? '<i style="flex:' + v + ' 1 0;--k:' + i + '" title="' + esc(PH[k] + ' ' + sec(v)) + '"></i>' : '';
        }).join('') + '</div><div class="sp-legend">' + Object.keys(PH).map(function (k, i) {
          return '<span style="--k:' + i + '"><i></i>' + PH[k] + ' ' + sec(ph[k]) + '</span>';
        }).join('') + '</div>';
      };
      var table = function (title, rows) {
        return '<section class="card"><h2>' + title + '</h2><table class="cmp"><thead><tr><th></th><th class="num">打开次数</th><th class="num">中位数</th><th class="num">75%</th><th class="num">90%</th><th class="num">没等到就离开</th></tr></thead><tbody>' +
          rows.map(function (r) { return '<tr><td>' + esc(r.group) + '</td><td class="num">' + n(r.visits) + '</td><td class="num">' + sec(r.p50) + '</td><td class="num">' + sec(r.p75) + '</td><td class="num">' + sec(r.p90) + '</td><td class="num">' + r.left_pct + '%</td></tr>'; }).join('') +
          '</tbody></table></section>';
      };
      main.innerHTML = '<div class="head-row"><div><h1>打开速度</h1><p class="muted">学员打开网站后，多久看到第一个页面（每次打开记一次，不记账号和地址）。「75%」表示四分之三的人在这个时间内看到了页面。</p></div>' +
        '<div class="toolbar"><select id="spDays"><option value="7"' + (SP.days === 7 ? ' selected' : '') + '>近 7 天</option><option value="30"' + (SP.days === 30 ? ' selected' : '') + '>近 30 天</option></select></div></div>' +
        '<div class="kpi-grid">' + kpi('打开次数', n(o.visits), '近 ' + d.days + ' 天') + kpi('中位数', sec(o.p50), '一半的人在这个时间内看到页面') + kpi('90% 的人', sec(o.p90), '慢的那一成要等这么久') + kpi('没等到就离开', o.left_pct + '%', n(o.left) + ' 次，页面还没出来就关了') + '</div>' +
        (o.visits ? '<section class="card"><h2>时间花在哪（各段的中位数）</h2>' + bar(d.phases) +
          (d.slow_visits ? '<h2>最慢的四分之一（' + n(d.slow_visits) + ' 次）时间花在哪</h2>' + bar(d.phases_slow || {}) : '') + '<p class="muted small">「打开前」慢，多半是手机或微信自己（检查链接、从后台唤醒、启动后台脚本）；「运行脚本」慢，是手机性能不够；「查域名」「建立连接」「加密握手」慢，多半是网络线路的问题；「服务器响应」「取首页数据」慢，是服务器的问题；「等脚本下载完」慢，是网页太大或网络带宽不够。' + (d.hidden_visits ? '另有 ' + n(d.hidden_visits) + ' 次是在后台打开的（比如微信预先加载了链接），没有人在等，不算进这一页的任何数字。' : '') + '</p></section>' +
          table('按访问的网址', d.by.domain) + table('按手机', d.by.platform) + table('按浏览器（微信、Safari…）', d.by.browser) +
          table('先显示上次的内容 / 等服务器的回答', d.by.snap || []) + table('先打开的页面', d.by.page || []) + table('第一次打开 / 再次打开', d.by.repeat) + table('从桌面打开 / 在浏览器里', d.by.standalone) + table('按网络（安卓浏览器会告诉）', d.by.net) +
          table('按天', d.daily.map(function (x) { return Object.assign({ group: x.day }, x); })) : '<section class="card"><p class="muted">还没有数据：发版后学员打开网站就会开始记录。</p></section>');
      document.getElementById('spDays').onchange = function (e) { SP.days = Number(e.target.value); speedView(); };
    }).catch(fail);
  }

  function errorsView() {
    getJSON('/errors').then(function (d) {
      var t = function (s) { return new Date(s * 1000).toLocaleString('zh-CN'); };
      main.innerHTML =
        '<div class="head-row"><div><h1>服务器错误</h1><p class="muted">学习者看到「服务暂时异常」的请求，按出错位置分组（近 ' + d.days + ' 天，只记路径，不记提交的内容）</p></div>' +
        '<div class="toolbar"><button class="btn" id="reload">刷新</button></div></div>' +
        '<div class="kpi-grid">' + kpi('近 24 小时', n(d.last_24h), '次') + kpi('近 ' + d.days + ' 天', n(d.total), '次，' + n(d.groups.length) + ' 处代码') + '</div>' +
        (d.groups.length ? d.groups.map(function (g) {
          return '<section class="card"><h2>' + esc(g.kind) + '：' + esc(g.message || '') + '</h2>' +
            '<p class="muted">' + n(g.count) + ' 次 · 最近 ' + esc(t(g.last)) + ' · 最早 ' + esc(t(g.first)) + '</p>' +
            '<p>' + g.paths.map(esc).join('<br>') + '</p>' +
            '<details><summary>最近一次的调用栈</summary><pre class="trace">' + esc(g.trace) + '</pre></details></section>';
        }).join('') : '<section class="card"><p>没有错误。</p></section>') + clientIssues(d.client);
      document.getElementById('reload').onclick = errorsView;
    }).catch(fail);
  }

  /* ---------- 学员（只有管理员）：每个账号一行，点开看详情、做操作 ---------- */
  var LR = { q: '', filter: 'all', sort: 'recent', page: 1, shown: false };
  function learnersView() {
    var qs = '?q=' + encodeURIComponent(LR.q) + '&filter=' + LR.filter + '&sort=' + LR.sort + '&page=' + LR.page;
    return getJSON('/learners' + qs).then(function (d) {
      var pages = Math.max(1, Math.ceil(d.total / d.per_page));
      main.innerHTML =
        '<div class="head-row"><div><h1>学员</h1><p class="muted">每个账号一行：最近什么时候来、学了几天、学到哪。点一行看详情：学习日历、词书、错得最多的词、考试练习、AI 用量，以及重设密码、停用、改水平等操作。</p></div>' +
        '<div class="toolbar"><form class="toolbar" id="lrF"><input class="input" id="lrQ" type="search" placeholder="用户名或编号" value="' + esc(LR.q) + '"><button class="btn">搜索</button></form>' +
        '<a class="btn" href="' + API + '/export/learners.csv">导出 CSV</a></div></div>' +
        '<div class="card toolbar" style="justify-content:space-between"><div class="chips">' + d.filters.map(function (f) {
          return '<button type="button" class="chip" data-lf="' + f.key + '" aria-pressed="' + (LR.filter === f.key) + '">' + esc(f.label) + '<b>' + n(f.count) + '</b></button>';
        }).join('') + '</div><label class="muted small">排序 <select id="lrSort">' + [['recent', '最近来过'], ['days', '学习天数'], ['joined', '注册时间'], ['ai', '近 7 天 AI']].map(function (o) {
          return '<option value="' + o[0] + '"' + (LR.sort === o[0] ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('') + '</select></label></div>' +
        '<section class="card">' + (d.items.length ? '<div class="tbl-wrap"><table class="cmp"><thead><tr><th>学员</th><th>水平</th><th>最近来</th><th class="num">学习天数</th>' +
          '<th class="num opt">材料</th><th class="opt">词书</th><th class="num opt">复习·7天</th><th class="num opt">AI·7天</th><th class="opt">注册</th></tr></thead><tbody>' +
          d.items.map(function (r) {
            return '<tr class="click' + (r.disabled ? ' dim' : '') + '" data-uid="' + r.id + '" tabindex="0"><td><b>' + esc(r.username) + '</b> ' +
              (r.staff ? '<span class="pill blue">员工</span> ' : '') + (r.disabled ? '<span class="pill danger">已停用</span>' : '') +
              '<span class="sub">#' + r.id + ' · ' + (r.has_email ? esc(r.email) : '没有绑定邮箱') + '</span></td>' +
              '<td>' + (r.level ? esc(r.level) : '<span class="muted">未填</span>') + (r.goal ? '<span class="sub">' + esc(r.goal) + '</span>' : '') + '</td>' +
              '<td>' + esc(rel(r.last_seen)) + (r.last_study ? '<span class="sub">学习 ' + esc(relDay(r.last_study)) + '</span>' : '') + '</td>' +
              '<td class="num">' + n(r.days_total) + '<span class="sub">近 7 天 ' + r.days_7d + '</span></td>' +
              '<td class="num opt">' + n(r.materials) + '<span class="sub">学完 ' + n(r.materials_done) + '</span></td>' +
              '<td class="opt">' + (r.book ? esc(r.book) + '<span class="sub">每天 ' + r.daily_new + ' 个 · 已加 ' + n(r.book_words) + '</span>' : '<span class="muted">—</span>') + '</td>' +
              '<td class="num opt">' + n(r.reviews_7d) + '</td><td class="num opt">' + n(r.ai_7d) + '</td>' +
              '<td class="opt">' + (r.joined ? esc(new Date(r.joined * 1000).toLocaleDateString('zh-CN')) + (r.joined_known ? '' : '<span class="sub">（按开始学习）</span>') : '<span class="muted">早于记录</span>') + '</td></tr>';
          }).join('') + '</tbody></table></div>' : '<p class="muted">没有找到。</p>') + '</section>' +
        (pages > 1 ? '<div class="pager"><button class="btn" id="lrPrev"' + (LR.page <= 1 ? ' disabled' : '') + '>上一页</button><span class="muted num">' + LR.page + ' / ' + pages + '</span><button class="btn" id="lrNext"' + (LR.page >= pages ? ' disabled' : '') + '>下一页</button></div>' : '');
      LR.shown = true;
      document.getElementById('lrF').onsubmit = function (e) { e.preventDefault(); LR.q = document.getElementById('lrQ').value.trim(); LR.page = 1; learnersView(); };
      document.getElementById('lrSort').onchange = function (e) { LR.sort = e.target.value; learnersView(); };
      main.querySelectorAll('[data-lf]').forEach(function (b) { b.onclick = function () { LR.filter = b.dataset.lf; LR.page = 1; learnersView(); }; });
      var pv = document.getElementById('lrPrev'), nx = document.getElementById('lrNext');
      if (pv) pv.onclick = function () { LR.page--; learnersView(); };
      if (nx) nx.onclick = function () { LR.page++; learnersView(); };
      main.querySelectorAll('tr[data-uid]').forEach(function (tr) {
        var open = function () { location.hash = '#learners/' + tr.dataset.uid; };
        tr.onclick = open;
        tr.onkeydown = function (e) { if (e.key === 'Enter') open(); };
      });
    }).catch(fail);
  }

  var drawer = document.getElementById('drawer'), drawerBg = document.getElementById('drawerBg');
  function closeDrawer(nav) {
    if (drawer.hidden) return;
    drawer.hidden = drawerBg.hidden = true; drawer.innerHTML = ''; drawer.dataset.uid = '';
    document.body.style.overflow = '';
    if (nav !== false && /^#learners\/\d+/.test(location.hash)) history.replaceState(null, '', '#learners');
  }
  drawerBg.onclick = function () { closeDrawer(); };
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeDrawer(); });

  function cal(days) {
    var lv = function (x) { var t = x.steps + x.reviews; return x.future ? 'fut' : !t ? '' : t < 3 ? 'l1' : t < 10 ? 'l2' : 'l3'; };
    return '<div class="cal-wrap"><div class="cal-days"><span>一</span><span></span><span>三</span><span></span><span>五</span><span></span><span>日</span></div><div class="cal">' + days.map(function (x) {
      return '<i class="' + lv(x) + '" title="' + esc(x.day + (x.future ? '' : '：学材料 ' + x.steps + ' 步，复习 ' + x.reviews + ' 次')) + '"></i>';
    }).join('') + '</div></div>';
  }
  function openLearner(id) {
    drawer.hidden = drawerBg.hidden = false;
    document.body.style.overflow = 'hidden';
    if (String(drawer.dataset.uid) !== String(id)) drawer.scrollTop = 0;  // another learner starts at the top; the same one (after an action) stays put
    drawer.dataset.uid = id;
    drawer.innerHTML = '<div class="dr-head"><h2 id="drawerTitle">正在加载…</h2><button class="btn" type="button" data-close>关闭</button></div>';
    drawer.querySelector('[data-close]').onclick = function () { closeDrawer(); };
    getJSON('/learner?id=' + encodeURIComponent(id)).then(function (d) { drawLearner(d); }).catch(function (e) {
      drawer.innerHTML = '<div class="dr-head"><h2 id="drawerTitle">' + esc(e.message) + '</h2><button class="btn" type="button" data-close>关闭</button></div>';
      drawer.querySelector('[data-close]').onclick = function () { closeDrawer(); };
    });
  }
  function drawLearner(d) {
    var a = d.account, p = d.profile, st = d.study, v = d.vocab, ai = d.ai;
    var aiMax = Math.max.apply(null, ai.days.map(function (x) { return x.count; }).concat([1]));
    var book = v && v.book, bookPct = book ? pct(book.started, book.size) : 0;
    drawer.innerHTML =
      '<div class="dr-head"><div><h2 id="drawerTitle">' + esc(a.username) + '</h2><div class="dr-pills"><span class="pill off">#' + a.id + '</span>' +
        (a.staff ? '<span class="pill blue">员工账号 · AI 不限次数</span>' : '') + (a.disabled ? '<span class="pill danger">已停用</span>' : '') +
        (a.locked_until ? '<span class="pill warn">密码错太多次，暂停到 ' + esc(when(a.locked_until)) + '</span>' : '') +
        (p ? '<span class="pill">' + esc(LEVEL[p.level] || p.level) + '</span>' : '<span class="pill off">还没填学习档案</span>') + '</div></div>' +
        '<button class="btn" type="button" data-close>关闭</button></div>' +
      '<div class="dr-body">' +
        '<section class="card"><dl class="kv">' +
          '<dt>邮箱</dt><dd>' + (a.has_email ? esc(a.email) + '（打码显示）' : '没有绑定，忘了密码只能由管理员生成重设链接') + '</dd>' +
          '<dt>注册</dt><dd>' + (a.joined ? esc(when(a.joined)) + (a.joined_known ? '' : '（没有注册时间，按开始学习算）') : '早于记录') + '</dd>' +
          '<dt>最近打开</dt><dd>' + esc(rel(a.last_open)) + ' · 登录着的设备 ' + n(a.sessions) + ' 台</dd>' +
          (p ? '<dt>学习目标</dt><dd>' + esc(p.goal) + ' · 每天 ' + n(p.minutes) + ' 分钟 · 每周 ' + n(p.weekly_goal) + ' 天' + (p.themes.length ? ' · ' + p.themes.map(esc).join('、') : '') + '</dd>' : '') +
        '</dl></section>' +
        (isAdmin() ? '<section class="card dr-actions"><h3>操作</h3>' +
          '<div class="toolbar"><button class="btn" data-act="reset">生成重设密码链接</button><button class="btn" data-act="signout"' + (a.sessions ? '' : ' disabled') + '>退出所有设备</button>' +
            '<button class="btn" data-act="staff">' + (a.staff ? '取消员工账号' : '设为员工账号') + '</button>' +
            '<button class="btn danger" data-act="disable">' + (a.disabled ? '恢复账号' : '停用账号') + '</button></div>' +
          '<div class="toolbar">' + (p ? '<span class="inline-form"><label class="muted small">水平 <select id="drLevel">' + Object.keys(LEVEL).map(function (k) {
              return '<option value="' + k + '"' + (p.level === k ? ' selected' : '') + '>' + LEVEL[k] + '</option>'; }).join('') + '</select></label><button class="btn" data-act="level">保存</button></span>' : '') +
            (v && v.plan ? '<span class="inline-form"><label class="muted small">每天新词 <input class="input" id="drDaily" type="number" min="1" max="200" value="' + v.plan.daily_new + '"></label><button class="btn" data-act="daily">保存</button></span>' : '') + '</div>' +
          '<div id="drOut" hidden></div>' +
          '<p class="muted small" style="margin:0">每个操作都会记进「操作记录」。停用：马上退出所有设备，不能再登录，学习记录都保留；恢复后照常使用。</p></section>' : '') +
        '<section class="card"><h3>学习日历（近 12 周）</h3>' + cal(st.calendar) +
          '<p class="muted small" style="margin:10px 0 0">一共学了 ' + n(st.days_total) + ' 天（近 7 天 ' + st.days_7d + ' 天，近 30 天 ' + st.days_30d + ' 天）· 学材料 ' + n(st.steps) + ' 步 · 复习 ' + n(st.reviews) + ' 次' +
          (st.first ? ' · 第一次学习 ' + esc(st.first) + ' · 最近 ' + esc(st.last) : '') + '</p></section>' +
        '<section class="card"><h3>单词</h3>' + (v ? (book ? '<div><b>' + esc(book.title) + '</b> <span class="muted">已学 ' + n(book.started) + ' / ' + n(book.size) + ' 词' + (book.skipped ? '（跳过已会的 ' + n(book.skipped) + '）' : '') + '</span></div><div class="prog"><i style="width:' + bookPct + '%"></i></div>' +
            '<p class="muted small" style="margin:0">' + (v.plan ? '每天 ' + v.plan.daily_new + ' 个新词 · 记住率目标 ' + Math.round(v.plan.retention * 100) + '%' + (v.plan.estimate ? ' · 测出的词汇量约 ' + n(v.plan.estimate) : '') : '') + (book.finish ? ' · 按现在的速度 ' + esc(book.finish) + ' 学完' : '') + '</p>' : '<p class="muted">没有开背词计划。</p>') +
          '<dl class="kv" style="margin-top:10px"><dt>单词卡</dt><dd>' + n(v.total) + ' 张 · 已掌握 ' + n(v.mastered) + ' · 在学 ' + n(v.learning) + (v.due != null ? ' · 今天要复习 ' + n(v.due) : '') + '</dd>' +
          '<dt>来源</dt><dd>' + (Object.keys(d.card_sources).map(function (k) { return esc(k) + ' ' + n(d.card_sources[k]); }).join(' · ') || '—') + '</dd>' +
          '<dt>近 30 天复习</dt><dd>' + (Object.keys(d.ratings_30d).map(function (k) { return esc(k) + ' ' + n(d.ratings_30d[k]); }).join(' · ') || '没有') +
            (d.retention_30d != null ? '<div class="muted small">隔天复习记得的比例 ' + Math.round(d.retention_30d * 100) + '%</div>' : '') + '</dd></dl>' +
          (d.mistakes.length ? '<h3 style="margin-top:12px">忘得最多的词</h3><div class="words">' + d.mistakes.map(function (w) { return '<span title="' + esc(w.meaning) + '">' + esc(w.text) + '<small>忘 ' + w.lapses + '</small></span>'; }).join('') + '</div>' : '')
          : '<p class="muted">还没有单词卡。</p>') + '</section>' +
        '<section class="card"><h3>最近学的材料</h3>' + (d.materials.length ? '<table class="cmp"><tbody>' + d.materials.map(function (m) {
          return '<tr><td>' + esc(m.title) + '<span class="sub">' + esc(m.level) + ' · ' + esc(rel(m.last)) + '</span></td><td class="num">' + ['listen', 'read', 'check', 'output'].map(function (k) {
            return '<span class="pill' + (m.steps.indexOf(k) >= 0 ? '' : ' off') + '">' + { listen: '听', read: '读', check: '理解', output: '用出来' }[k] + '</span>'; }).join(' ') + '</td></tr>';
        }).join('') + '</tbody></table>' : '<p class="muted">还没学过材料。</p>') + '</section>' +
        (d.exams.length ? '<section class="card"><h3>考试练习</h3><table class="cmp"><tbody>' + d.exams.map(function (x) {
          return '<tr><td>' + esc(x.title) + '<span class="sub">' + esc(when(x.created)) + ' · 用时 ' + Math.round(x.seconds / 60) + ' 分钟</span></td><td class="num"><b>' + x.pct + '%</b><span class="sub">' + x.score + ' / ' + x.total + '</span></td>' +
            '<td class="small">' + x.parts.map(function (pt) { return esc(pt.title) + ' ' + pt.right + '/' + pt.of; }).join('<br>') + '</td></tr>';
        }).join('') + '</tbody></table></section>' : '') +
        '<section class="card"><h3>AI 用量</h3><div class="spark" style="height:44px">' + ai.days.map(function (x) { return '<div title="' + esc(x.day + '：' + x.count + ' 次') + '" style="height:' + Math.max(3, pct(x.count, aiMax)) + '%"></div>'; }).join('') + '</div>' +
          '<p class="muted small">近 14 天每天的次数（UTC 日）· ' + (ai.remaining == null ? '今天不限次数' : '今天还剩 ' + n(ai.remaining) + ' 次') + '</p>' +
          (ai.kinds.length ? '<table class="cmp"><thead><tr><th>近 30 天</th><th class="num">成功</th><th class="num">失败</th></tr></thead><tbody>' + ai.kinds.map(function (k) {
            return '<tr><td>' + esc(k.label) + '</td><td class="num">' + n(k.complete) + '</td><td class="num">' + (k.failed ? '<span class="err">' + n(k.failed) + '</span>' : 0) + '</td></tr>'; }).join('') + '</tbody></table>' : '') + '</section>' +
        (d.feedback.length ? '<section class="card"><h3>提过的反馈</h3><ul class="todo">' + d.feedback.map(function (f) {
          return '<li><a href="#feedback"><span>' + esc(f.kind) + ' · ' + esc(f.text) + '</span><span class="muted">' + (f.status === 'new' ? '待处理' : '已处理') + ' · ' + esc(rel(f.created)) + '</span></a></li>'; }).join('') + '</ul></section>' : '') +
        (d.log.length ? '<section class="card"><h3>管理员对这个账号做过的事</h3><table class="cmp"><tbody>' + d.log.map(function (r) {
          return '<tr><td>' + esc(when(r.created)) + '<span class="sub">' + esc(r.email) + '</span></td><td>' + esc(r.action_label) + (r.detail ? '<span class="sub">' + esc(r.detail) + '</span>' : '') + '</td></tr>'; }).join('') + '</tbody></table></section>' : '') +
      '</div>';
    drawer.querySelector('[data-close]').onclick = function () { closeDrawer(); };
    drawer.querySelector('[data-close]').focus();
    var act = function (name, fn) { var b = drawer.querySelector('[data-act="' + name + '"]'); if (b) b.onclick = function () { fn(b); }; };
    var after = function (r) { openLearner(a.id); if (LR.shown && ST.tab === 'learners') learnersView(); return r; };
    act('reset', function (b) {
      if (!confirm('给「' + a.username + '」生成重设密码的链接？\n\n先确认对方是本人。链接 24 小时内有效、只能用一次；生成新链接后，旧链接作废。')) return;
      busy(b, postJSON('/users/reset-link', { user: a.username })).then(function (r) {
        var out = document.getElementById('drOut'); out.hidden = false;
        out.innerHTML = '<p><input class="input acc-link" id="accLink" readonly value="' + esc(r.link) + '"> <button class="btn" id="accCopy" type="button">复制</button></p>' +
          '<p class="muted small">' + r.hours + ' 小时内有效，只能用一次。请当面或私信发给本人，不要发到群里。这个链接只显示这一次。</p>';
        document.getElementById('accCopy').onclick = function () {
          var i = document.getElementById('accLink'); i.select();
          (navigator.clipboard ? navigator.clipboard.writeText(i.value) : Promise.reject()).then(function () { document.getElementById('accCopy').textContent = '已复制'; }, function () { document.execCommand('copy'); });
        };
      });
    });
    act('signout', function (b) {
      if (!confirm('让「' + a.username + '」在所有设备上退出登录？\n\n手机丢了、账号借给了别人时用。对方用密码或邮箱验证码可以再登录。')) return;
      busy(b, postJSON('/learner/signout', { id: a.id })).then(function (r) { alert('已退出 ' + r.sessions_ended + ' 台设备。'); after(); });
    });
    act('staff', function (b) {
      if (!confirm(a.staff ? '取消「' + a.username + '」的员工账号？之后 AI 次数按普通学员的每日上限算。' : '把「' + a.username + '」设为员工账号？\n\n员工账号用 AI 不受每日次数限制，也不算进学员统计（漏斗、留存）。只给自己人。')) return;
      busy(b, postJSON('/learner/staff', { id: a.id, staff: !a.staff })).then(after);
    });
    act('disable', function (b) {
      if (!a.disabled && !confirm('停用「' + a.username + '」？\n\n马上在所有设备上退出，之后不能再登录（会提示账号已停用）。学习记录都保留，随时可以恢复。')) return;
      busy(b, postJSON('/learner/disable', { id: a.id, disabled: !a.disabled })).then(after);
    });
    act('level', function (b) {
      var lv = document.getElementById('drLevel').value; if (lv === p.level) return;
      if (!confirm('把「' + a.username + '」的水平改成 ' + LEVEL[lv] + '？今日推荐和练习会按新水平挑。')) return;
      busy(b, postJSON('/learner/level', { id: a.id, level: lv })).then(after);
    });
    act('daily', function (b) {
      var k = Number(document.getElementById('drDaily').value);
      if (!(k >= 1 && k <= 200) || k === v.plan.daily_new) return;
      busy(b, postJSON('/learner/daily-new', { id: a.id, daily_new: k })).then(after);
    });
  }

  /* ---------- 发版对比：发版前后各几天的日均数字，和几个入口的点击次数 ---------- */
  function compareView() {
    getJSON('/releases').then(function (rel) {
      var at = ST.at || (rel.items[0] && rel.items[0].at) || null, days = ST.days || 14;
      var pick = '<form class="toolbar" id="cmpF"><label class="muted">发版 <select id="cmpRel"><option value="">按日期</option>' + rel.items.map(function (r) {
          return '<option value="' + r.at + '"' + (Number(r.at) === Number(at) ? ' selected' : '') + '>' + esc(r.tag) + ' · ' + esc(when(r.at)) + '</option>'; }).join('') + '</select></label>' +
        '<label class="muted">或日期 <input class="input" type="date" id="cmpDay"></label>' +
        '<label class="muted">前后各 <select id="cmpDays">' + [7, 14, 30].map(function (x) { return '<option' + (x === days ? ' selected' : '') + '>' + x + '</option>'; }).join('') + '</select> 天</label></form>';
      var head = '<div class="head-row"><div><h1>发版对比</h1><p class="muted">发版前后各 ' + days + ' 天的日均数字（北京时间）。发版后不满 ' + days + ' 天的，按已经过去的天数算。</p></div>' + pick + '</div>';
      if (!at) { main.innerHTML = head + '<section class="card"><p>还没有记下发版时间。下一次发版后会自动记下；也可以先选一个日期。</p></section>'; return bindCmp(); }
      return getJSON('/compare?at=' + at + '&days=' + days).then(function (d) {
        var ch = function (b, a) { if (b == null || a == null) return '—'; if (!b) return a ? '新出现' : '—'; var p = Math.round(100 * (a - b) / b); return '<span class="' + (p > 0 ? 'up' : p < 0 ? 'down' : '') + '">' + (p > 0 ? '+' : '') + p + '%</span>'; };
        main.innerHTML = head +
          '<section class="card"><h2>' + esc(when(d.at)) + ' 前后</h2><p class="muted">发版后已经过了 ' + d.after_days + ' 天。人少的时候，几个人的变化就会让比例跳得很大；「新学员一周内回来的比例」要等发版满一周才准。</p>' +
          '<table class="cmp"><thead><tr><th></th><th class="num">发版前</th><th class="num">发版后</th><th class="num">变化</th></tr></thead><tbody>' + d.metrics.map(function (m) {
            return '<tr><td>' + esc(m.label) + '</td><td class="num">' + (m.before == null ? '—' : m.before) + '</td><td class="num">' + (m.after == null ? '—' : m.after) + '</td><td class="num">' + ch(m.before, m.after) + '</td></tr>'; }).join('') +
          '</tbody></table></section>' +
          '<section class="card"><h2>入口点击（合计次数）</h2><p class="muted">学习网站上几个入口被点了多少次，只按天计数，不记是谁。发版当天前后都不算。</p>' + (d.taps.length ?
          '<table class="cmp"><thead><tr><th></th><th class="num">发版前</th><th class="num">发版后</th><th class="num">变化</th></tr></thead><tbody>' + d.taps.map(function (t) {
            return '<tr><td>' + esc(t.label) + '</td><td class="num">' + n(t.before) + '</td><td class="num">' + n(t.after) + '</td><td class="num">' + ch(t.before, t.after) + '</td></tr>'; }).join('') +
          '</tbody></table>' : '<p class="muted">还没有点击记录。</p>') + '</section>';
        bindCmp();
      });
    }).catch(fail);
    function bindCmp() {
      var f = document.getElementById('cmpF'); if (!f) return;
      document.getElementById('cmpRel').onchange = function (e) { ST.at = e.target.value || null; compareView(); };
      document.getElementById('cmpDay').onchange = function (e) { if (e.target.value) { ST.at = new Date(e.target.value + 'T00:00:00+08:00').getTime() / 1000; compareView(); } };
      document.getElementById('cmpDays').onchange = function (e) { ST.days = Number(e.target.value); compareView(); };
    }
  }

  /* ---------- 操作记录：管理员改了什么、导出了什么 ---------- */
  /* ---------- 问题反馈（只有管理员）：学员在「我的 → 问题反馈」提交的说明和截图 ---------- */
  var FB = { status: 'new', page: 1 };
  function fbBadge(k) {
    var b = document.getElementById('fbBadge');
    if (b) { b.textContent = k > 99 ? '99+' : String(k || 0); b.hidden = !k; }
    var g = document.getElementById('fbBadgeG');
    if (g) { g.textContent = k > 99 ? '99+' : String(k || 0); g.hidden = !k; }
  }
  function feedbackView() {
    getJSON('/feedback?status=' + FB.status + '&page=' + FB.page).then(function (d) {
      fbBadge(d.counts.new);
      var dev = function (v) {
        var bits = [];
        if (v.w) bits.push(v.w + '×' + v.h + (v.dpr ? ' @' + v.dpr + 'x' : ''));
        bits.push(v.theme === 'dark' ? '深色' : '浅色');
        if (v.standalone) bits.push('从桌面打开');
        if (v.wechat) bits.push('在微信里');
        if (v.asset) bits.push('页面 ' + v.asset);
        return bits.join(' · ');
      };
      var filters = [['new', '待处理', d.counts.new], ['done', '已处理', d.counts.done], ['all', '全部', d.counts.new + d.counts.done]];
      main.innerHTML = '<div class="head-row"><div><h1>问题反馈</h1><p class="muted">学员在「我的 → 问题反馈」提交的说明和截图。处理完点「标记已处理」，会记进操作记录。</p></div>' +
        '<div class="toolbar">' + filters.map(function (f) {
          return '<button type="button" class="btn' + (FB.status === f[0] ? ' primary' : '') + '" data-fs="' + f[0] + '">' + f[1] + ' ' + n(f[2]) + '</button>';
        }).join('') + '</div></div>' +
        (d.items.length ? d.items.map(function (x) {
          var v = x.device || {};
          return '<section class="card fb-item"><div class="fb-head"><b>' + esc(x.kind_label) + '</b><span class="pill' + (x.status === 'new' ? '' : ' off') + '">' + esc(x.status_label) + '</span>' +
            '<span class="muted">#' + x.id + ' · ' + when(x.created) + ' · ' + esc(x.who) + (x.release ? ' · ' + esc(x.release) : '') + '</span></div>' +
            '<p class="fb-text">' + esc(x.text) + '</p>' +
            (x.images.length ? '<div class="fb-imgs">' + x.images.map(function (nm) {
              var u = API + '/feedback/image?id=' + x.id + '&n=' + encodeURIComponent(nm);
              return '<a href="' + u + '" target="_blank" rel="noopener" title="看原图"><img src="' + u + '" alt="截图" loading="lazy"></a>';
            }).join('') + '</div>' : '') +
            '<dl class="fb-meta"><dt>页面</dt><dd>' + (x.page ? '<a href="https://flowlang.cn/' + esc(x.page) + '" target="_blank" rel="noopener">' + esc(x.page) + '</a>' : '—') + '</dd>' +
            '<dt>设备</dt><dd>' + esc(dev(v)) + '<div class="muted small fb-ua">' + esc(v.ua || '') + '</div></dd>' +
            (x.contact ? '<dt>联系方式</dt><dd>' + esc(x.contact) + '</dd>' : '') +
            (v.errors && v.errors.length ? '<dt>页面报错</dt><dd><code class="fb-err">' + v.errors.map(esc).join('<br>') + '</code></dd>' : '') +
            (x.status === 'done' ? '<dt>处理</dt><dd>' + esc(x.handled_by || '—') + ' · ' + when(x.handled_at) + '</dd>' : '') + '</dl>' +
            '<div class="toolbar"><button type="button" class="btn' + (x.status === 'new' ? ' primary' : '') + '" data-fb="' + x.id + '" data-to="' + (x.status === 'new' ? 'done' : 'new') + '">' +
            (x.status === 'new' ? '标记已处理' : '重新打开') + '</button></div></section>';
        }).join('') : '<section class="card"><p class="muted">' + (FB.status === 'new' ? '没有待处理的反馈。' : '还没有反馈。') + '</p></section>') +
        (d.pages > 1 ? '<div class="toolbar"><button type="button" class="btn" id="fbPrev"' + (FB.page <= 1 ? ' disabled' : '') + '>上一页</button><span class="muted">' + FB.page + ' / ' + d.pages +
          '</span><button type="button" class="btn" id="fbNext"' + (FB.page >= d.pages ? ' disabled' : '') + '>下一页</button></div>' : '');
      main.querySelectorAll('[data-fs]').forEach(function (b) { b.onclick = function () { FB.status = b.dataset.fs; FB.page = 1; feedbackView(); }; });
      var pv = document.getElementById('fbPrev'), nx = document.getElementById('fbNext');
      if (pv) pv.onclick = function () { FB.page--; feedbackView(); };
      if (nx) nx.onclick = function () { FB.page++; feedbackView(); };
      main.querySelectorAll('[data-fb]').forEach(function (b) {
        b.onclick = function () {
          b.disabled = true;
          postJSON('/feedback/status', { id: Number(b.dataset.fb), status: b.dataset.to }).then(feedbackView).catch(function (e) { alert(e.message); b.disabled = false; });
        };
      });
    }).catch(fail);
  }

  /* ---------- 留存和漏斗：注册以后走到了哪一步；按开始学习的那周，之后几周还有多少人在学 ---------- */
  var FN = { days: 0 };
  function funnelView() {
    Promise.all([getJSON('/funnel?days=' + FN.days), getJSON('/cohorts')]).then(function (res) {
      var f = res[0], co = res[1], first = (f.steps[0] && f.steps[0].count) || 0;
      main.innerHTML =
        '<div class="head-row"><div><h1>留存和漏斗</h1><p class="muted">' + esc(f.note) + '</p></div>' +
        '<div class="toolbar"><select id="fnDays">' + [[0, '全部账号'], [90, '近 90 天注册'], [30, '近 30 天注册'], [7, '近 7 天注册']].map(function (o) {
          return '<option value="' + o[0] + '"' + (FN.days === o[0] ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('') + '</select></div></div>' +
        '<div class="kpi-grid k3">' +
          kpi('次日回来', f.next_day_of ? pct(f.next_day, f.next_day_of) + '%' : '—', '开始学习第二天又来学的人：' + n(f.next_day) + ' / ' + n(f.next_day_of)) +
          kpi('开了背词计划', n(f.planned), '占注册的 ' + pct(f.planned, first) + '%') +
          kpi('还在观察', n(f.waiting.week1 + f.waiting.week2), '开始学习还不满一两周，回没回来还不知道') +
        '</div>' +
        '<section class="card"><h2>注册以后走到了哪一步</h2><p class="muted">每一步只算走过上一步的人。右边是占注册的比例，和比上一步留下的比例。</p><div class="funnel">' +
          f.steps.map(function (st, i) {
            var prev = i ? f.steps[i - 1].count : st.count;
            return '<div class="fn-row"><span>' + esc(st.label) + '</span><div class="fn-bar"><i style="width:' + pct(st.count, first) + '%"></i></div>' +
              '<span class="fn-val"><b>' + n(st.count) + '</b> · ' + pct(st.count, first) + '%' + (i ? '<small>比上一步 ' + pct(st.count, prev) + '%</small>' : '<small>&nbsp;</small>') + '</span></div>';
          }).join('') + '</div>' +
          (f.unknown_joined ? '<p class="muted small">另有 ' + n(f.unknown_joined) + ' 个账号不知道什么时候注册的（r26 之前注册、也没学过），没算进来。</p>' : '') + '</section>' +
        '<section class="card"><h2>每周留存</h2><p class="muted">' + esc(co.note) + '</p><div class="tbl-wrap"><table class="cmp"><thead><tr><th>开始学习的那周</th><th class="num">人数</th><th class="c">第 1 周</th><th class="c">第 2 周</th><th class="c">第 3 周</th><th class="c">第 4 周</th></tr></thead><tbody>' +
          co.weeks.map(function (w) {
            return '<tr><td>' + esc(w.week.slice(5)) + ' 起</td><td class="num">' + n(w.n) + '</td>' + w.cells.map(function (c) {
              return c.pct == null ? '<td class="heat none">—</td>' : '<td class="heat" style="--h:' + Math.round(c.pct * 0.7) + '" title="' + c.back + ' / ' + c.of + ' 人">' + c.pct + '%</td>';
            }).join('') + '</tr>';
          }).join('') + '</tbody></table></div></section>';
      document.getElementById('fnDays').onchange = function (e) { FN.days = Number(e.target.value); funnelView(); };
    }).catch(fail);
  }

  /* ---------- 材料：每篇多少人学、学到哪一步、轻松读的难度评价；管理员可以下架 ---------- */
  var CT = { days: 0, level: '', q: '', only: '', limit: 60 };
  function contentView() {
    getJSON('/content?days=' + CT.days).then(function (d) {
      var items = d.items.filter(function (m) {
        return (!CT.level || m.level === CT.level) && (!CT.q || (m.title + ' ' + m.id).toLowerCase().indexOf(CT.q.toLowerCase()) >= 0) &&
          (CT.only !== 'used' || m.learners) && (CT.only !== 'unused' || !m.learners) && (CT.only !== 'hidden' || m.hidden);
      });
      var shown = items.slice(0, CT.limit);
      var er = function (e) { var t = (e.easy || 0) + (e.ok || 0) + (e.hard || 0); return t ? '<span title="容易 / 正好 / 难">' + (e.easy || 0) + ' / ' + (e.ok || 0) + ' / ' + (e.hard || 0) + '</span>' : '<span class="muted">—</span>'; };
      main.innerHTML =
        '<div class="head-row"><div><h1>材料</h1><p class="muted">学员在书库、今日、练习里能看到的材料。「学过的人」是做过任何一步的人数；「学完」是做到「用出来」的比例；轻松读的评价是读完后选的「容易 / 正好 / 难」。</p></div>' +
        '<div class="toolbar">' + (isAdmin() ? '<a class="btn" href="' + API + '/export/materials.csv">导出 CSV</a>' : '') + '</div></div>' +
        '<div class="kpi-grid k3">' + kpi('材料', n(d.total), Object.keys(d.levels).sort().map(function (k) { return k + ' ' + d.levels[k]; }).join(' · ')) +
          kpi('有人学过', n(d.used), CT.days ? '近 ' + CT.days + ' 天' : '全部时间') + kpi('已下架', n(d.hidden), '学员的列表里看不到，已学的记录保留') + '</div>' +
        '<form class="card toolbar" id="ctF"><input class="input" id="ctQ" type="search" placeholder="标题或编号" value="' + esc(CT.q) + '">' +
          '<select id="ctLevel"><option value="">全部级别</option>' + ['A2', 'B1', 'B2', 'C1'].map(function (k) { return '<option' + (CT.level === k ? ' selected' : '') + '>' + k + '</option>'; }).join('') + '</select>' +
          '<select id="ctDays">' + [[0, '全部时间'], [30, '近 30 天'], [7, '近 7 天']].map(function (o) { return '<option value="' + o[0] + '"' + (CT.days === o[0] ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('') + '</select>' +
          '<select id="ctOnly">' + [['', '全部材料'], ['used', '有人学过'], ['unused', '没人学过'], ['hidden', '已下架']].map(function (o) { return '<option value="' + o[0] + '"' + (CT.only === o[0] ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('') + '</select>' +
          '<button class="btn">筛选</button><span class="muted small">' + n(items.length) + ' 篇</span></form>' +
        '<section class="card"><div class="tbl-wrap"><table class="cmp"><thead><tr><th>材料</th><th class="num">学过的人</th><th class="num opt">听</th><th class="num opt">读</th><th class="num opt">理解</th><th class="num opt">用出来</th><th class="num">学完</th><th class="num opt">轻松读评价</th>' + (isAdmin() ? '<th></th>' : '') + '</tr></thead><tbody>' +
          shown.map(function (m) {
            return '<tr class="' + (m.hidden ? 'dim' : '') + '"><td><b>' + esc(m.title) + '</b> ' + (m.hidden ? '<span class="pill danger">已下架</span>' : '') +
              '<span class="sub">' + esc(m.level) + ' · ' + esc(m.theme) + ' · ' + esc(m.origin) + ' · ' + esc(m.id) + (m.hidden && m.hidden_info && m.hidden_info.reason ? ' · 下架原因：' + esc(m.hidden_info.reason) : '') + '</span></td>' +
              '<td class="num">' + n(m.learners) + '</td>' + ['listen', 'read', 'check', 'output'].map(function (k) { return '<td class="num opt">' + n(m.steps[k]) + '</td>'; }).join('') +
              '<td class="num">' + (m.completion == null ? '—' : m.completion + '%') + '</td><td class="num opt">' + er(m.easy_read) + '</td>' +
              (isAdmin() ? '<td><button class="btn' + (m.hidden ? '' : ' danger') + '" data-hide="' + esc(m.id) + '" data-v="' + (m.hidden ? 0 : 1) + '">' + (m.hidden ? '恢复' : '下架') + '</button></td>' : '') + '</tr>';
          }).join('') + '</tbody></table></div>' +
          (items.length > shown.length ? '<div class="more-row"><button class="btn" id="ctMore">再显示 ' + Math.min(60, items.length - shown.length) + ' 篇（还有 ' + n(items.length - shown.length) + '）</button></div>' : '') + '</section>';
      document.getElementById('ctF').onsubmit = function (e) {
        e.preventDefault(); CT.q = document.getElementById('ctQ').value.trim(); CT.level = document.getElementById('ctLevel').value; CT.only = document.getElementById('ctOnly').value; CT.limit = 60;
        var days = Number(document.getElementById('ctDays').value); CT.days = days; contentView();
      };
      ['ctLevel', 'ctDays', 'ctOnly'].forEach(function (id) { document.getElementById(id).onchange = function () { document.getElementById('ctF').requestSubmit(); }; });
      var more = document.getElementById('ctMore'); if (more) more.onclick = function () { CT.limit += 60; contentView(); };
      main.querySelectorAll('[data-hide]').forEach(function (b) {
        b.onclick = function () {
          var hide = b.dataset.v === '1', reason = '';
          if (hide) { reason = prompt('下架这篇材料？学员的书库、今日推荐、练习里都不再出现；正在学或学过的人还能从历史打开，学习记录都保留。\n\n下架原因（可以不填）：', ''); if (reason === null) return; }
          else if (!confirm('恢复这篇材料？学员的列表里会重新出现。')) return;
          busy(b, postJSON('/material/hide', { pack: b.dataset.hide, hidden: hide, reason: reason })).then(contentView);
        };
      });
    }).catch(fail);
  }

  /* ---------- 词书和考试 ---------- */
  function booksView() {
    getJSON('/books').then(function (d) {
      var b = d.books, ex = d.exams;
      main.innerHTML =
        '<div class="head-row"><div><h1>词书和考试</h1><p class="muted">每本词书有多少人在背、平均背到哪（「已学」是复习过至少一次或标为熟知的词）；考试练习的次数、平均分和各部分的正确率。员工账号不算。</p></div></div>' +
        '<section class="card"><h2>词书（' + n(b.learners) + ' 人开了背词计划）</h2><div class="tbl-wrap"><table class="cmp"><thead><tr><th>词书</th><th class="num">词数</th><th class="num">在背的人</th><th class="num">平均已学</th><th class="num">平均完成</th><th class="num opt">最多完成</th><th class="num opt">平均每天新词</th></tr></thead><tbody>' +
          b.items.map(function (x) {
            return '<tr class="' + (x.learners ? '' : 'dim') + '"><td>' + esc(x.title) + '<span class="sub">' + esc(x.group) + '</span></td><td class="num">' + n(x.size) + '</td><td class="num">' + n(x.learners) + '</td>' +
              '<td class="num">' + (x.avg_words == null ? '—' : n(x.avg_words)) + '</td><td class="num">' + (x.avg_pct == null ? '—' : x.avg_pct + '%') + '</td>' +
              '<td class="num opt">' + (x.best_pct == null ? '—' : x.best_pct + '%') + '</td><td class="num opt">' + (x.avg_daily_new == null ? '—' : x.avg_daily_new) + '</td></tr>';
          }).join('') + '</tbody></table></div></section>' +
        '<section class="card"><h2>考试练习</h2><p class="muted">' + esc(ex.note) + '</p>' + (ex.items.length ? '<div class="tbl-wrap"><table class="cmp"><thead><tr><th>考试</th><th class="num">做了几套</th><th class="num">人数</th><th class="num">平均分</th><th class="num opt">最高</th><th class="num opt">平均用时</th><th>各部分正确率</th><th class="opt">最近</th></tr></thead><tbody>' +
          ex.items.map(function (x) {
            return '<tr><td>' + esc(x.title) + '</td><td class="num">' + n(x.papers) + '</td><td class="num">' + n(x.learners) + '</td><td class="num"><b>' + x.avg_pct + '%</b></td><td class="num opt">' + x.best_pct + '%</td>' +
              '<td class="num opt">' + x.avg_minutes + ' 分钟</td><td class="small">' + x.parts.map(function (pt) { return esc(pt.title) + ' ' + (pt.pct == null ? '—' : pt.pct + '%'); }).join(' · ') + '</td><td class="opt">' + esc(rel(x.last)) + '</td></tr>';
          }).join('') + '</tbody></table></div>' : '<p class="muted">还没有人做过考试练习。</p>') + '</section>';
    }).catch(fail);
  }

  /* ---------- 公告：学员打开「今日」时在最上面看到的一句话 ---------- */
  var LINKS = [['', '不带链接'], ['#/guide', '操作指南'], ['#/library', '书库'], ['#/cards', '单词'], ['#/vocab/plan', '词书计划'], ['#/practice', '练习'], ['#/exam', '考试练习'], ['#/report', '这周的报告'], ['#/feedback', '问题反馈'], ['#/me', '我的']];
  function linkName(l) { var x = LINKS.filter(function (k) { return k[0] === l; })[0]; return x ? x[1] : l; }
  function announceView() {
    getJSON('/announcements').then(function (d) {
      var cur = d.current;
      main.innerHTML =
        '<div class="head-row"><div><h1>公告</h1><p class="muted">一句话，学员（包括没登录的）打开「今日」时在最上面看到，点「知道了」就不再显示这一条。同一时间只有一条：发新的，旧的就结束。适合说维护时间、新功能、活动。</p></div></div>' +
        '<section class="card"><h2>现在学员看到的</h2>' + (cur ? '<div class="ann-preview"><span><b>' + esc(cur.text) + '</b>' + (cur.link ? ' <span class="muted small">→ ' + esc(linkName(cur.link)) + '</span>' : '') + '</span><span class="muted small">知道了</span></div>' +
          (isAdmin() ? '<p><button class="btn danger" data-end="' + cur.id + '">现在结束这条</button></p>' : '') : '<p class="muted">现在没有公告。</p>') + '</section>' +
        (isAdmin() ? '<section class="card"><h2>发一条新公告</h2><form class="form" id="anF">' +
          '<label><span>内容（4–120 个字，一句话说清楚）</span><textarea id="anText" maxlength="120" required placeholder="例如：今晚 23:00–23:10 升级，期间可能打不开"></textarea></label>' +
          '<div class="row"><label><span>点了去哪</span><select id="anLink">' + LINKS.map(function (l) { return '<option value="' + l[0] + '">' + l[1] + '</option>'; }).join('') + '</select></label>' +
          '<label><span>显示多久</span><select id="anDays">' + [1, 3, 7, 14, 30].map(function (k) { return '<option value="' + k + '"' + (k === 7 ? ' selected' : '') + '>' + k + ' 天</option>'; }).join('') + '</select></label></div>' +
          '<div class="row"><button class="btn primary">发布</button><span class="muted small" id="anCount">0 / 120</span></div></form></section>' : '') +
        '<section class="card"><h2>发过的公告</h2>' + (d.items.length ? '<div class="tbl-wrap"><table class="cmp"><thead><tr><th>内容</th><th>时间</th><th>状态</th><th class="opt">谁发的</th></tr></thead><tbody>' + d.items.map(function (x) {
          var state = x.active ? '<span class="pill">显示中</span>' : x.ended ? '<span class="pill off">已结束</span>' : x.ends < Date.now() / 1000 ? '<span class="pill off">到期</span>' : '<span class="pill off">被新公告替换</span>';
          return '<tr><td>' + esc(x.text) + (x.link ? '<span class="sub">→ ' + esc(linkName(x.link)) + '</span>' : '') + '</td><td class="small">' + esc(when(x.starts)) + '<br>到 ' + esc(when(x.ended || x.ends)) + '</td><td>' + state + '</td><td class="opt small">' + esc(x.by) + '</td></tr>';
        }).join('') + '</tbody></table></div>' : '<p class="muted">还没有发过。</p>') + '</section>';
      var end = main.querySelector('[data-end]');
      if (end) end.onclick = function () { if (confirm('现在结束这条公告？学员就看不到了。')) busy(end, postJSON('/announcements/end', { id: Number(end.dataset.end) })).then(announceView); };
      var f = document.getElementById('anF');
      if (f) {
        var t = document.getElementById('anText');
        t.oninput = function () { document.getElementById('anCount').textContent = t.value.trim().length + ' / 120'; };
        f.onsubmit = function (e) {
          e.preventDefault();
          if (!confirm('发布这条公告？所有学员打开「今日」都会看到' + (cur ? '；现在这条会结束' : '') + '。')) return;
          busy(f.querySelector('button'), postJSON('/announcements/create', { text: t.value, link: document.getElementById('anLink').value, days: Number(document.getElementById('anDays').value) })).then(announceView);
        };
      }
    }).catch(fail);
  }

  /* ---------- AI 用量、费用、模型和质量 ---------- */
  var AIV = { days: 14, sample: '' };
  function yuan(v) { return v == null ? '—' : '¥' + (v >= 100 ? Math.round(v).toLocaleString('zh-CN') : v >= 1 ? v.toFixed(2) : v.toFixed(3)); }
  function ktok(v) { return v >= 10000 ? (v / 1000).toFixed(0) + 'K' : v >= 1000 ? (v / 1000).toFixed(1) + 'K' : n(v); }
  function aiView() {
    getJSON('/ai?days=' + AIV.days).then(function (d) {
      var lim = d.limits, cs = d.costs || { kinds: [], models: [], by_day: [], total: {}, budget: {}, prices: {}, platforms: {}, choices: [] }, tot = cs.total || {}, bud = cs.budget || {};
      var max = Math.max.apply(null, d.by_day.map(function (x) { return x.count; }).concat([1]));
      var cmax = Math.max.apply(null, cs.by_day.map(function (x) { return x.cost; }).concat([0.0001]));
      var src = function (k) { return lim[k + '_source'] === 'console' ? '后台设置（服务器配置是 ' + (lim[k + '_server'] ? n(lim[k + '_server']) + ' 次' : '不限') + '）' : '服务器配置'; };
      var CH = cs.choices || [], label = function (name) { var c = CH.filter(function (x) { return x.name === name; })[0]; return c ? c.label : name; };
      var SRC = { console: '后台', server: '服务器', 'default': '默认' };
      var options = function (cur) { return CH.map(function (c) { return '<option value="' + esc(c.name) + '"' + (c.name === cur ? ' selected' : '') + '>' + esc(c.label) + '</option>'; }).join(''); };
      var routeCell = function (k) {
        if (!k.route) return '—';
        if (!isAdmin()) return esc(label(k.route)) + '<span class="sub">' + esc(SRC[k.source] || '') + '</span>';
        return '<select data-route="' + esc(k.kind) + '">' + options(k.route) + '</select>';
      };
      var PF = cs.platforms || {}, bl = PF.bailian || {};
      var budPill = bud.level === 'over' ? '<span class="pill danger">超过预算</span>' : bud.level === 'warn' ? '<span class="pill warn">已到 80%</span>' : '';
      var ev = d.evals || [], ev0 = ev[0];
      main.innerHTML =
        '<div class="head-row"><div><h1>AI 用量、费用和质量</h1><p class="muted">' + esc(d.note) + ' 费用、token 按北京时间算。</p></div>' +
        '<div class="toolbar"><select id="aiDays"><option value="14"' + (d.days === 14 ? ' selected' : '') + '>近 14 天</option><option value="30"' + (d.days === 30 ? ' selected' : '') + '>近 30 天</option></select>' +
        (isAdmin() ? '<a class="btn" href="' + API + '/export/ai.csv">导出 CSV</a>' : '') + '</div></div>' +
        '<div class="kpi-grid">' +
          kpi('今天的费用（估算）', yuan(cs.today) + ' ' + budPill, bud.daily ? '每日预算 ' + yuan(bud.daily) + ' · 已用 ' + bud.pct + '%' : '没有设每日预算') +
          kpi('近 ' + cs.days + ' 天费用', yuan(tot.cost), n(tot.ok) + ' 次成功 · 失败 ' + n(tot.failed) + ' 次') +
          kpi('输入命中缓存', tot.cache_pct == null ? '—' : tot.cache_pct + '%', '百炼：命中的部分按输入价的 20% 算；提示词要 1024 token 以上才会命中') +
          kpi('备用线路答的', n((tot.backup || 0) + (tot.fallback || 0)) + ' 次', '网关换线 ' + n(tot.backup || 0) + ' · Flow 换到主模型 ' + n(tot.fallback || 0)) + '</div>' +
        '<section class="card"><h2>每个任务用哪个模型</h2>' +
          '<p class="muted small">这里列的是 AI 网关（xmc.hk/api-admin）里给学员用的模型名：<code>' + esc(cs.default_model || '—') + '</code> 是 Gemini（默认），flow-text- 开头的是阿里云百炼企业账号上的模型（通义千问、DeepSeek 等），各自配了 Gemini 备用。评测和例句预生成会自动改问 flow-eval- / flow-batch- 同名模型（站长的学生账号）。两条都不通时，Flow 再换主模型。录音、联网检索一直用 Gemini，不在这里。' +
          (isAdmin() ? '改了马上生效，记进操作记录。换之前先看下面「每晚小评测」和抽样，效果不降再换；正式版上换之前先问过站长。' : '') + '</p>' +
          (isAdmin() && CH.length > 1 ? '<div class="toolbar" style="margin:8px 0"><select id="allRoute">' + options(cs.default_model) + '</select><button class="btn" id="allGo">所有任务都用这个</button></div>' : '') +
          '<table class="cmp"><thead><tr><th>任务</th><th>模型</th><th class="num">次数</th><th class="num opt">失败</th><th class="num opt">备用答</th><th class="num opt">输入 / 命中 / 输出 token</th><th class="num">费用</th><th class="num opt">平均</th></tr></thead><tbody>' +
          cs.kinds.map(function (k) {
            return '<tr' + (k.calls ? '' : ' class="dim"') + '><td>' + esc(k.label) + (k.group === 'grading' ? '<span class="sub">批改</span>' : k.group === 'content' ? '<span class="sub">内容，全站共用</span>' : '') + '</td><td>' + routeCell(k) + '</td>' +
              '<td class="num">' + n(k.calls) + '</td><td class="num opt">' + (k.failed ? '<span class="down">' + n(k.failed) + '</span>' : '0') + '</td><td class="num opt">' + n(k.backup + k.fallback) + '</td>' +
              '<td class="num opt">' + ktok(k.prompt) + ' / ' + ktok(k.cached) + ' / ' + ktok(k.completion) + (k.estimated ? '<span class="sub">含估算 ' + n(k.estimated) + ' 次</span>' : '') + '</td>' +
              '<td class="num">' + yuan(k.cost) + '</td><td class="num opt">' + (k.seconds == null ? '—' : k.seconds + ' 秒') + '</td></tr>';
          }).join('') + '</tbody></table></section>' +
        '<div class="grid2">' +
          '<section class="card"><h2>每天的费用</h2><div class="spark">' + cs.by_day.map(function (x) { return '<div title="' + esc(x.day + '：' + yuan(x.cost) + '，' + x.calls + ' 次') + '" style="height:' + Math.max(3, pct(x.cost, cmax)) + '%"></div>'; }).join('') + '</div>' +
            '<div class="spark-days">' + cs.by_day.map(function (x, i) { return '<span>' + (i % (cs.days > 14 ? 5 : 2) ? '' : esc(x.day.slice(5))) + '</span>'; }).join('') + '</div></section>' +
          '<section class="card"><h2>按模型</h2>' + (cs.models.length ? '<table class="cmp"><thead><tr><th>实际回答的模型</th><th class="num">次数</th><th class="num opt">token</th><th class="num">费用</th></tr></thead><tbody>' + cs.models.map(function (m) {
              return '<tr><td>' + esc(m.name) + '<span class="sub">' + esc([m.label, m.platform].filter(Boolean).join(' · ') || '没有单价，费用按 0 算') + (m.estimated ? ' · token 是估算' : '') + '</span></td><td class="num">' + n(m.calls) + '</td><td class="num opt">' + ktok(m.prompt + m.completion) + '</td><td class="num">' + yuan(m.cost) + '</td></tr>'; }).join('') + '</tbody></table>' : '<p class="muted">这段时间没有记录。</p>') + '</section>' +
        '</div>' +
        '<div class="grid2">' +
          '<section class="card"><h2>每日预算和单价</h2><dl class="kv"><dt>每日预算</dt><dd>' + (bud.daily ? yuan(bud.daily) : '不设') + '</dd>' +
            '<dt>到预算时</dt><dd>80% 和 100% 各给管理员发一封邮件；超过后暂停例句预生成和每晚小评测，第二天恢复。学员的请求不受影响。</dd>' +
            Object.keys(PF).map(function (k) { return '<dt>' + esc(PF[k].label) + '折扣</dt><dd>' + (PF[k].discount === 1 ? '按标价' : '标价 × ' + PF[k].discount) + '</dd>'; }).join('') +
            Object.keys(cs.prices || {}).map(function (f) { var p = cs.prices[f]; return '<dt>' + esc(p.label) + '</dt><dd><code>' + esc(f) + '</code> 标价：输入 ' + p['in'] + ' · 命中缓存 ' + p.cached + ' · 输出 ' + p.out + ' 元 / 百万 token' + (p.custom ? ' <span class="pill blue">手动设置</span>' : '') + (p.note ? '<div class="muted small">' + esc(p.note) + '</div>' : '') + '</dd>'; }).join('') + '</dl>' +
            (isAdmin() ? '<form class="form" id="budF" style="margin-top:12px"><div class="row"><label><span>每日预算（元，0 = 不设）</span><input class="input" id="budD" type="number" min="0" max="100000" step="0.5" value="' + (bud.daily || 0) + '"></label>' +
              '<label><span>百炼折扣（标价的几成，0.65 = 六五折）</span><input class="input" id="budB" type="number" min="0.05" max="1" step="0.01" value="' + (bl.discount || 1) + '"></label>' +
              '<label class="chk"><input type="checkbox" id="budN"' + (d.nightly ? ' checked' : '') + '> 每晚小评测（约 17 次调用）</label></div>' +
              '<div class="row"><button class="btn primary">保存</button></div></form>' : '') + '</section>' +
          '<section class="card"><h2>每晚小评测 ' + (d.nightly ? '' : '<span class="pill off">已关闭</span>') + '</h2>' +
            '<p class="muted small">每天凌晨 2–5 点用固定的题考一遍：错句要改对、对的句子不能改、写作分数要分得出好坏、讲解和例句要能直接给学员看。用的是网站当时的模型设置，不碰学员数据。</p>' +
            (ev.length ? '<table class="cmp"><thead><tr><th>日期</th><th class="num">通过</th><th class="opt">没过的题</th><th class="num opt">费用</th></tr></thead><tbody>' + ev.map(function (r) {
              return '<tr><td>' + esc(r.day.slice(5)) + '</td><td class="num"><span class="' + (r.passed < r.total ? 'down' : 'up') + '">' + n(r.passed) + ' / ' + n(r.total) + '</span></td>' +
                '<td class="opt small">' + (r.failed.length ? r.failed.map(function (f) { return esc(f.id) + '：' + esc((f.why || []).join('；')); }).join('<br>') : '—') + '</td><td class="num opt">' + yuan(r.cost) + '</td></tr>'; }).join('') + '</tbody></table>' : '<p class="muted">还没有跑过。</p>') + '</section>' +
        '</div>' +
        '<div class="grid2">' +
          '<section class="card"><h2>批改结果（只看数字）</h2><p class="muted small">学员写的内容不在后台显示，这里只有统计：判对、改动、平均分的走向突然变了，多半是模型变了。</p>' +
            ((d.quality || []).length ? '<table class="cmp"><thead><tr><th>任务</th><th class="num">次数</th><th class="num opt">失败</th><th>情况</th></tr></thead><tbody>' + d.quality.map(function (q) {
              return '<tr><td>' + esc(q.label) + '</td><td class="num">' + n(q.done) + '</td><td class="num opt">' + (q.failed ? n(q.failed) + (q.unusable ? '<span class="sub">回答不完整 ' + n(q.unusable) + '</span>' : '') : '0') + '</td><td class="small">' + (q.notes.map(esc).join('<br>') || '—') + '</td></tr>'; }).join('') + '</tbody></table>' : '<p class="muted">这段时间没有批改。</p>') + '</section>' +
          '<section class="card"><h2>抽样看内容</h2><p class="muted small">讲解、例句、难度改写这些是全站共用的（第一个人用时 AI 写，之后大家看同一份）。随机抽几条看看' + (isAdmin() ? '；写得不好的点「让 AI 重写」，下一个用到的人会拿到新写的' : '') + '。</p>' +
            '<div class="chips" style="margin:8px 0">' + (d.sample_kinds || []).map(function (k) { return '<button class="chip" data-sample="' + esc(k.kind) + '" aria-pressed="' + (AIV.sample === k.kind) + '">' + esc(k.label) + '</button>'; }).join('') + '</div><div id="samples"></div></section>' +
        '</div>' +
        '<div class="grid2">' +
          '<section class="card"><h2>按功能（学习页面的请求）</h2>' + (d.kinds.length ? '<table class="cmp"><thead><tr><th></th><th class="num">成功</th><th class="num">失败</th><th class="num">失败率</th><th class="num opt">平均等待</th></tr></thead><tbody>' + d.kinds.map(function (k) {
            return '<tr><td>' + esc(k.label) + '</td><td class="num">' + n(k.complete) + '</td><td class="num">' + n(k.failed) + '</td><td class="num">' + (k.fail_pct == null ? '—' : '<span class="' + (k.fail_pct >= 10 ? 'down' : '') + '">' + k.fail_pct + '%</span>') + '</td><td class="num opt">' + (k.seconds == null ? '—' : k.seconds + ' 秒') + '</td></tr>';
          }).join('') + '</tbody></table>' : '<p class="muted">这段时间没有 AI 请求。</p>') + '</section>' +
          '<section class="card"><h2>每日次数额度</h2><div class="spark" style="height:44px">' + d.by_day.map(function (x) { return '<div title="' + esc(x.day + '：' + x.count + ' 次') + '" style="height:' + Math.max(3, pct(x.count, max)) + '%"></div>'; }).join('') + '</div>' +
            '<dl class="kv"><dt>今天</dt><dd>' + n(d.today) + ' 次' + (lim.site_limit ? '（全站上限 ' + n(lim.site_limit) + '，已用 ' + pct(d.today, lim.site_limit) + '%）' : '') + ' · 用满的账号 ' + n(d.users_at_limit) + ' 个</dd>' +
            '<dt>每账号每天</dt><dd>' + (lim.user_limit ? n(lim.user_limit) + ' 次' : '不限') + ' · ' + src('user_limit') + '</dd>' +
            '<dt>全站每天</dt><dd>' + (lim.site_limit ? n(lim.site_limit) + ' 次' : '不限') + ' · ' + src('site_limit') + '</dd>' +
            (lim.updated ? '<dt>上次修改</dt><dd>' + esc(when(lim.updated)) + ' · ' + esc(lim.by || '') + '</dd>' : '') + '</dl>' +
            (isAdmin() ? '<form class="form" id="limF" style="margin-top:14px"><div class="row"><label><span>每账号每天（次）</span><input class="input" id="limU" type="number" min="0" max="1000000" placeholder="服务器配置" value="' + (lim.user_limit_source === 'console' ? lim.user_limit : '') + '"></label>' +
              '<label><span>全站每天（次）</span><input class="input" id="limS" type="number" min="0" max="1000000" placeholder="服务器配置" value="' + (lim.site_limit_source === 'console' ? lim.site_limit : '') + '"></label></div>' +
              '<p class="muted small" style="margin:0">马上生效，不用重启。0 表示不限；留空表示用服务器 /etc/flow.env 里的值。员工账号不受每账号上限限制。每天北京时间 08:00 重置。</p>' +
              '<div class="row"><button class="btn primary">保存</button></div></form>' : '') + '</section>' +
          (d.top ? '<section class="card"><h2>用得最多的账号</h2>' + (d.top.length ? '<table class="cmp"><tbody>' + d.top.map(function (u) {
            return '<tr class="click" data-uid="' + u.id + '"><td>' + esc(u.username) + (u.staff ? ' <span class="pill blue">员工</span>' : '') + '</td><td class="num">' + n(u.count) + ' 次</td></tr>'; }).join('') + '</tbody></table>' : '<p class="muted">没有。</p>') + '</section>' : '') +
          (d.failures && d.failures.length ? '<section class="card"><h2>最近失败的请求</h2><table class="cmp"><tbody>' + d.failures.map(function (f) {
            return '<tr><td>' + esc(f.kind) + '<span class="sub">' + esc(when(f.created)) + '</span></td><td class="small">' + esc(f.error) + '</td></tr>'; }).join('') + '</tbody></table></section>' : '') +
        '</div>';
      document.getElementById('aiDays').onchange = function (e) { AIV.days = Number(e.target.value); aiView(); };
      main.querySelectorAll('tr[data-uid]').forEach(function (tr) { tr.onclick = function () { location.hash = '#learners/' + tr.dataset.uid; }; });
      main.querySelectorAll('select[data-route]').forEach(function (sel) {
        sel.onchange = function () {
          var k = sel.dataset.route, task = (cs.kinds.filter(function (x) { return x.kind === k; })[0] || {}).label || k, body = { routes: {} };
          body.routes[k] = sel.value;
          if (!confirm('「' + task + '」改用 ' + label(sel.value) + '？马上生效。')) { aiView(); return; }
          sel.disabled = true;
          postJSON('/settings/ai-routes', body).then(aiView, function (e) { alert(e.message); aiView(); });
        };
      });
      var allGo = document.getElementById('allGo');
      if (allGo) allGo.onclick = function () {
        var v = document.getElementById('allRoute').value;
        if (!confirm('所有文字任务都改用 ' + label(v) + '？马上生效，每个任务单独的设置会清掉。')) return;
        busy(allGo, postJSON('/settings/ai-routes', { routes: { '*': v } })).then(aiView);
      };
      var bf = document.getElementById('budF');
      if (bf) bf.onsubmit = function (e) {
        e.preventDefault();
        var v = Number(document.getElementById('budD').value || 0), night = document.getElementById('budN').checked, disc = Number(document.getElementById('budB').value || 1);
        if (!(v >= 0)) { alert('预算请填 0 或正数。'); return; }
        if (!(disc > 0 && disc <= 1)) { alert('折扣请填 0–1 之间的小数，比如 0.65。'); return; }
        busy(bf.querySelector('button'), postJSON('/settings/ai-budget', { daily: v, nightly: night, discounts: { bailian: disc } })).then(aiView);
      };
      var f = document.getElementById('limF');
      if (f) f.onsubmit = function (e) {
        e.preventDefault();
        var val = function (id) { var v = document.getElementById(id).value.trim(); return v === '' ? null : Number(v); };
        var body = { user_limit: val('limU'), site_limit: val('limS') };
        if ([body.user_limit, body.site_limit].some(function (v) { return v != null && !(Number.isInteger(v) && v >= 0); })) { alert('请填 0 或正整数；留空表示用服务器配置。'); return; }
        if (!confirm('把 AI 每日额度改成：每账号 ' + (body.user_limit == null ? '服务器配置' : body.user_limit || '不限') + '，全站 ' + (body.site_limit == null ? '服务器配置' : body.site_limit || '不限') + '？马上生效。')) return;
        busy(f.querySelector('button'), postJSON('/settings/ai-limits', body)).then(aiView);
      };
      main.querySelectorAll('[data-sample]').forEach(function (b) { b.onclick = function () { AIV.sample = b.dataset.sample; main.querySelectorAll('[data-sample]').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); }); aiSamples(); }; });
      if (AIV.sample) aiSamples();
    }).catch(fail);
  }

  function sampleOut(kind, o) {
    if (kind === 'next-explain') return '<div>' + esc(o.translation) + '</div>' + (o.structure ? '<div class="muted small">' + esc(o.structure) + '</div>' : '') +
      '<ul class="small">' + (o.points || []).map(function (p) { return '<li><b>' + esc(p.text) + '</b>：' + esc(p.note) + (p.node_title ? ' <span class="pill off">' + esc(p.node_title) + '</span>' : '') + '</li>'; }).join('') + '</ul>' +
      (o.pattern ? '<div class="small">句型：<b>' + esc(o.pattern.frame) + '</b> — ' + esc(o.pattern.example || '') + '</div>' : '');
    if (kind === 'next-variant') return '<div class="small">' + esc(o.body) + '</div>' + ((o.notes || []).length ? '<div class="muted small">' + o.notes.map(function (x) { return esc(x.text + ' ' + (x.meaning || '')); }).join(' · ') + '</div>' : '');
    if (kind === 'next-examples') return '<div>' + esc(o.sentence) + '</div><div class="muted small">' + esc(o.translation) + '</div>';
    if (kind === 'next-transsrc') return '<div>' + esc(o.zh) + '</div>';
    if (kind === 'next-dialog') return '<div class="muted small">' + esc(o.scene) + (o.role ? ' · AI 扮演：' + esc(o.role) : '') + '</div><div>' + esc(o.reply) + '</div>';
    return '<div class="small">' + esc(o.body) + '</div><ol class="small">' + (o.questions || []).map(function (q) { return '<li>' + esc(q) + '</li>'; }).join('') + '</ol><div class="muted small">' + esc(o.source || '') + '</div>';
  }
  function aiSamples() {
    var box = document.getElementById('samples');
    if (!box || !AIV.sample) return;
    box.innerHTML = '<p class="muted">正在抽…</p>';
    getJSON('/ai/samples?n=5&kind=' + encodeURIComponent(AIV.sample)).then(function (d) {
      box.innerHTML = (d.items.length ? d.items.map(function (x, i) {
        return '<div class="card flat" style="margin:8px 0;padding:10px 12px"><div class="small"><b>' + esc(x.title || '') + '</b>' + (x.level ? ' · ' + esc(x.level) : '') + (x.source ? '<div class="muted">原句：' + esc(x.source) + '</div>' : '') + '</div>' +
          sampleOut(d.kind, x.output) + '<div class="row between small muted" style="margin-top:6px"><span>' + esc(when(x.created)) + '</span>' +
          (isAdmin() && d.redo ? '<button class="btn" data-redo="' + i + '">让 AI 重写</button>' : '') + '</div></div>';
      }).join('') : '<p class="muted">这一类还没有内容。</p>') + '<p><button class="btn" id="sampleMore">再抽几条</button></p>';
      document.getElementById('sampleMore').onclick = aiSamples;
      box.querySelectorAll('[data-redo]').forEach(function (b) {
        b.onclick = function () {
          var x = d.items[Number(b.dataset.redo)];
          if (!confirm('把这条「' + d.label + '」删掉，让 AI 在下次有人用到时重写？会用 1 次 AI。')) return;
          busy(b, postJSON('/ai/samples/redo', { kind: d.kind, key: x.key })).then(function () { b.textContent = '已删掉，下次重写'; b.disabled = true; });
        };
      });
    }).catch(function (e) { box.innerHTML = '<p class="err">' + esc(e.message) + '</p>'; });
  }

  /* ---------- 后台任务：例句预生成、每日热点、备份 ---------- */
  var TK = { timer: null };
  var TASK_STATE = { idle: ['还没运行过', 'off'], running: ['正在运行', ''], waiting: ['等半价时段', 'off'], done: ['做完了', ''], left: ['停在中途（到了请求上限或连续失败）', 'warn'], budget: ['今天的 AI 预算用完了，明天再跑', 'warn'], stopped: ['已停止', 'off'], 'no-model': ['服务器没有配置 AI 模型', 'danger'], failed: ['出错了', 'danger'], ended: ['已结束', 'off'] };
  function tasksView() {
    clearTimeout(TK.timer);
    getJSON('/tasks').then(function (d) {
      var ex = d.examples, pg = ex.progress || {}, tk = ex.task || {}, st = TASK_STATE[ex.state] || [ex.state, 'off'], dl = d.daily;
      main.innerHTML =
        '<div class="head-row"><div><h1>后台任务</h1><p class="muted">在服务器上跑的活：给词书里还没有例句的词提前写好 AI 例句、每天的热点材料、数据库备份。</p></div>' +
        '<div class="toolbar"><button class="btn" id="reload">刷新</button></div></div>' +
        '<section class="card"><h2>例句预生成 <span class="pill ' + st[1] + '">' + esc(st[0]) + '</span></h2>' +
          '<p class="muted">学员打开一张没有例句的单词卡时，要等几秒让 AI 现写。这里提前把例句写好存起来，学员打开就有。已经有例句的词会跳过，所以随时可以停、下次接着做。用的是网站自己的 AI 额度，不算进任何学员的次数。</p>' +
          (pg.total != null ? '<div class="prog"><i style="width:' + pct(pg.looked || 0, pg.total || 1) + '%"></i></div>' +
            '<dl class="kv"><dt>进度</dt><dd>看了 ' + n(pg.looked) + ' / ' + n(pg.total) + ' 个词 · 请求 ' + n(pg.calls) + ' 次 · 写好 ' + n(pg.made) + ' 条例句' + (pg.left != null && ex.state !== 'running' ? ' · 还剩 ' + n(pg.left) + ' 个词没有例句' : '') + '</dd>' +
            (tk.started ? '<dt>开始</dt><dd>' + esc(when(tk.started)) + ' · ' + esc(tk.by || '') + (tk.books && tk.books.length ? ' · 词书 ' + tk.books.map(esc).join('、') : ' · 全部词书') + (tk.max_calls ? ' · 最多 ' + n(tk.max_calls) + ' 次请求' : '') + (tk.offpeak ? ' · 只在半价时段' : '') + '</dd>' : '') +
            (ex.state === 'waiting' && pg.until ? '<dt>等到</dt><dd>' + esc(when(pg.until)) + '（半价时段开始）</dd>' : '') + '</dl>' : '') +
          (ex.log.length ? '<details' + (ex.state === 'running' ? ' open' : '') + '><summary class="muted small">运行记录（最后几行）</summary><pre class="logtail">' + esc(ex.log.join('\n')) + '</pre></details>' : '') +
          (isAdmin() ? (ex.state === 'running' || ex.state === 'waiting' ? '<p><button class="btn danger" id="exStop">停止</button></p>' :
            '<form class="form" id="exF" style="margin-top:12px"><div class="row"><label><span>词书</span><select id="exBook"><option value="">全部词书（考试词书优先）</option>' + d.books.map(function (b) {
              return '<option value="' + esc(b.id) + '">' + esc(b.group + ' · ' + b.title) + '</option>'; }).join('') + '</select></label>' +
              '<label><span>最多请求几次（0 = 不限）</span><input class="input" id="exMax" type="number" min="0" max="100000" value="0"></label></div>' +
              '<label class="chk"><input type="checkbox" id="exOff" checked> 用的模型有忙时价时（百炼上的 DeepSeek：北京时间 8–22 点），等到半价时段再跑</label>' +
              '<p class="muted small" style="margin:0">一次请求写 16 个词。先试一小批（比如 20 次）看看例句质量，再放开跑。今天的 AI 预算用完时会自动停下。</p>' +
              '<div class="row"><button class="btn primary">开始</button></div></form>') : '') + '</section>' +
        '<div class="grid2">' +
          '<section class="card"><h2>今日热点 <span class="pill ' + (dl.status === 'complete' ? '' : dl.status === 'failed' || dl.status === 'interrupted' ? 'danger' : 'off') + '">' + esc(DAILY[dl.status] || dl.status) + '</span></h2>' +
            '<p class="muted">每天自动联网检索一条新闻，改写成一篇学习材料（未经人工审核）。每天最多试两轮。</p><dl class="kv">' +
            '<dt>今天</dt><dd>' + esc(dl.day) + ' · 试了 ' + n(dl.attempts) + ' 次' + (dl.error ? '<div class="muted small">' + esc(dl.error) + '</div>' : '') + '</dd>' +
            '<dt>最近几天</dt><dd>' + (dl.latest && dl.latest.length ? dl.latest.map(function (x) { return esc(x.day.slice(5)); }).join('、') : '—') + '</dd></dl>' +
            (isAdmin() ? '<p>' + (dl.status === 'failed' || dl.status === 'interrupted' ? '<button class="btn primary" id="dailyAgain">重新生成</button>' :
              '<button class="btn" id="dailyRun"' + (dl.status === 'complete' || dl.status === 'running' ? ' disabled' : '') + '>现在生成</button>') + '</p>' : '') + '</section>' +
          '<section class="card"><h2>数据库备份</h2>' + (d.backup ? '<dl class="kv"><dt>最近一次</dt><dd>' + (d.backup.ok ? '成功' : '<span class="err">失败</span>') + ' · ' + esc(when(d.backup.created)) + '</dd>' +
            (d.backup.size ? '<dt>大小</dt><dd>' + n(Math.round(d.backup.size / 1048576)) + ' MB</dd>' : '') + (d.backup.error ? '<dt>原因</dt><dd>' + esc(d.backup.error) + '</dd>' : '') + '</dl>' : '<p class="muted">还没有备份记录。</p>') +
            '<p class="muted small">每天自动备份（flow-backup.timer）。</p></section>' +
        '</div>';
      document.getElementById('reload').onclick = tasksView;
      var stop = document.getElementById('exStop');
      if (stop) stop.onclick = function () { if (confirm('停止例句预生成？已经写好的都保留，下次从没写的词接着做。')) busy(stop, postJSON('/tasks/examples/stop', {})).then(tasksView); };
      var f = document.getElementById('exF');
      if (f) f.onsubmit = function (e) {
        e.preventDefault();
        var book = document.getElementById('exBook').value, max = Number(document.getElementById('exMax').value || 0);
        if (!confirm('开始例句预生成（' + (book ? '词书 ' + book : '全部词书') + (max ? '，最多 ' + max + ' 次请求' : '，不限次数') + '）？会用网站的 AI 额度。')) return;
        busy(f.querySelector('button'), postJSON('/tasks/examples/start', { books: book ? [book] : [], max_calls: max, offpeak: document.getElementById('exOff').checked })).then(tasksView);
      };
      var again = document.getElementById('dailyAgain'), run = document.getElementById('dailyRun');
      if (again) again.onclick = function () { busy(again, postJSON('/daily/run', { again: true })).then(function (r) { again.textContent = r.message; again.disabled = true; }); };
      if (run) run.onclick = function () { busy(run, postJSON('/daily/run', {})).then(function (r) { run.textContent = r.message; run.disabled = true; }); };
      if (ex.state === 'running' || ex.state === 'waiting') TK.timer = setTimeout(function () { if (ST.tab === 'tasks' && !document.hidden) tasksView(); }, 5000);
    }).catch(fail);
  }

  function logView() {
    getJSON('/log').then(function (d) {
      main.innerHTML =
        '<div class="head-row"><div><h1>操作记录</h1><p class="muted">管理员在后台做的每一件事都记在这里：谁、什么时候、对哪一项、结果。停用和恢复账号、退出所有设备、改水平和每日新词、员工账号、下架材料、AI 额度、例句预生成、公告、热点、导出、重设密码链接（链接本身不记录）。</p></div>' +
        '<div class="toolbar"><button class="btn" id="reload">刷新</button></div></div>' +
        (ST.me && !ST.me.roles_set ? '<section class="card"><p><b>现在所有能登录后台的人都是管理员。</b>想让一部分人只看数据：在服务器的 /etc/flow.env 里加一行 <code>FLOW_ADMIN_EMAILS=你的邮箱,另一个管理员的邮箱</code>，再重启 flow。不在名单里的人只能看数字（数据、内容、AI 用量、后台任务），看不到学员个人、问卷原文、错误详情，也不能做任何操作。</p></section>' : '') +
        '<section class="card">' + (d.items.length ? '<div class="tbl-wrap"><table class="cmp"><thead><tr><th>时间</th><th>谁</th><th>做了什么</th><th>对象</th><th>结果</th></tr></thead><tbody>' + d.items.map(function (r) {
          return '<tr><td>' + esc(when(r.created)) + '</td><td>' + esc(r.email) + '<div class="muted">' + esc(r.role_label) + '</div></td><td>' + esc(r.action_label) + '</td><td>' + esc(r.target) + '</td><td>' + esc(r.detail) + '</td></tr>'; }).join('') +
          '</tbody></table></div>' : '<p class="muted">还没有记录。</p>') + '</section>';
      document.getElementById('reload').onclick = logView;
    }).catch(fail);
  }

  /* ---------- 路由：#tab 或 #tab/参数（#learners/12 打开 12 号学员；#learners/f=disabled 先筛选） ---------- */
  var VIEWS = { overview: overview, learning: learningView, funnel: funnelView, compare: compareView, speed: speedView, survey: surveyStats, responses: responses,
    learners: learnersView, feedback: feedbackView, content: contentView, books: booksView, announce: announceView, ai: aiView, tasks: tasksView, errors: errorsView, log: logView };
  var ADMIN_TABS = ['responses', 'learners', 'feedback', 'errors', 'log'];
  var GROUP_HOME = { data: 'overview', people: 'learners', content: 'content', ops: 'ai' };
  function route() {
    var h = (location.hash || '#overview').slice(1), cut = h.indexOf('/');
    var tab = cut < 0 ? h : h.slice(0, cut), arg = cut < 0 ? '' : h.slice(cut + 1);
    if (tab === 'accounts') tab = 'learners';  // the old 账号 tab is part of 学员 now
    if (!VIEWS[tab]) tab = 'overview';
    if (!isAdmin() && ADMIN_TABS.indexOf(tab) >= 0) tab = 'overview';
    var same = tab === ST.tab && ST.drawn;
    ST.tab = tab;
    clearTimeout(TK.timer);
    var link = document.querySelector('.adm-tabs a[data-tab="' + tab + '"]'), group = link ? link.dataset.group : 'data';
    document.querySelectorAll('.adm-tabs a').forEach(function (a) {
      a.classList.toggle('off', a.dataset.group !== group);
      if (a.dataset.tab === tab) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    document.querySelectorAll('.adm-groups a').forEach(function (a) {
      if (a.dataset.group === group) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
    });
    if (tab === 'learners') {
      if (/^f=/.test(arg)) { LR.filter = arg.slice(2); LR.page = 1; same = false; history.replaceState(null, '', '#learners'); arg = ''; }
      if (/^\d+$/.test(arg)) { if (!same) learnersView(); ST.drawn = true; openLearner(arg); return; }
      closeDrawer(false);
      if (same && LR.shown) return;  // the drawer was closed: the list is still there
    } else closeDrawer(false);
    if (/^\d+$/.test(arg) === false && tab !== 'learners') LR.shown = false;
    main.innerHTML = '<p class="muted">正在加载…</p>';
    ST.drawn = true;
    VIEWS[tab]();
  }
  document.getElementById('themeBtn').onclick = function () {
    var next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('xmc-theme', next); } catch (e) { /* ignore */ }
  };
  // Who is signed in (Cloudflare Access) and with which role; which server the data comes from (香港 or 杭州), on
  // every tab: the two panels look alike, the data must not.
  function whoAmI() {
    return getJSON('/me').then(function (me) {
      ST.me = me;
      var w = document.getElementById('who');
      if (w) { w.textContent = (me.email || '未识别的账号') + ' · ' + me.label; w.hidden = false; }
      var el = document.getElementById('srv');
      if (el && me.server) { el.textContent = '数据来自' + me.server; el.hidden = false; }
      document.querySelectorAll('.adm-tabs [data-admin], .adm-groups [data-admin]').forEach(function (a) { a.hidden = !isAdmin(); });
      if (isAdmin()) getJSON('/feedback?status=new&page=1').then(function (d) { fbBadge(d.counts.new); }).catch(function () { /* an older Flow */ });
    }).catch(function () { /* an older Flow without /me: everything as before */ });
  }
  window.addEventListener('hashchange', route);
  whoAmI().then(route);
})();
