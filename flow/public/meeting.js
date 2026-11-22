'use strict';

// Extend the existing app shell, review hub and report with one guided path.
let meetingToday = null;
let meetingScreen = null;
let meetingPending = null;
const meetingDrafts = new Map();
const meetingPendingKey = 'flow-meeting-save';
const meetingTopics = [
  [1, 'meeting-update', '汇报项目进度'],
  [3, 'explain-delay', '解释为什么要延期'],
  [4, 'suggest-next-step', '提出一个下一步建议']
];

function meetingRead(key) {
  try { return JSON.parse(sessionStorage.getItem(key)); }
  catch { return null; }
}

function meetingStore(key, value) {
  try {
    if (value === null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, JSON.stringify(value));
  } catch {}
}

function meetingTrialHref(day) {
  return '/?trial=' + Number(day) + '#try-meeting/' + Number(day);
}

function meetingGetPending() {
  const saved = meetingPending || meetingRead(meetingPendingKey);
  return saved?.answer && saved?.requestId ? {...saved, day: saved.day || 1} : null;
}

function meetingSetPending(value) {
  meetingPending = value;
  meetingStore(meetingPendingKey, value);
}

function meetingAuthContext() {
  return ['#meeting/save', '#meeting'].includes(window.location.hash) ? meetingGetPending() : null;
}

function meetingReset() {
  meetingToday = null;
  meetingScreen = null;
  meetingDrafts.clear();
  meetingSetPending(null);
  for (const [day] of meetingTopics) meetingStore('flow-meeting-trial-' + day, null);
}

let meetingVisitor = null;
function meetingVisitorId() {
  if (!meetingVisitor) {
    meetingVisitor = meetingRead('flow-meeting-visit') || flowRequestId();
    meetingStore('flow-meeting-visit', meetingVisitor);
  }
  return meetingVisitor;
}

function meetingPersistTrial(screen) {
  if (!screen.preview) return;
  const {draft, result, frame, example, editing} = screen;
  meetingStore('flow-meeting-trial-' + screen.task.day, {draft, result, frame, example, editing});
}

const meetingWorkspaceLinks = [
  ['home', 'AI 私教', '按目标安排练习，继续上次的对话。'],
  ['studio', '语料库', '选一篇材料，练听、说、读、写。'],
  ['vocab', 'AI 词汇', '学词义和搭配，把词用进句子。'],
  ['learn', '语法学习', '按知识点读讲解、做练习。'],
  ['review', '复习中心', '回练到期的词汇和语法。'],
  ['report', '学习档案', '回看自己的作答和修订。'],
  ['graph', '知识图谱', '查看词汇、语法和材料之间的联系。'],
  ['quiz', '诊断测评', '了解当前基础和下一步。'],
  ['practice', '专项练习', '集中练习需要巩固的技能。']
];

function meetingGuestHome() {
  document.documentElement.classList.remove('flow-auth');
  document.title = '语流 Flow · 你的长期 AI 英语私教';
  app.innerHTML = `<main class="meeting-landing meeting-guest-home">
    <header>${brand}<div class="meeting-guest-tools"><a class="jasa-back" href="https://jasa.hk/" aria-label="返回 Jasa Studio"><span aria-hidden="true">←</span><span class="jb-long">Jasa Studio</span><span class="jb-short">Studio</span></a><a class="text-button" href="/?account=1#login">登录</a></div></header>
    <section class="card meeting-focus">
      <div class="meeting-focus-copy">
      <h1>你的长期 AI 英语私教</h1>
      <p>用语料、词汇和语法练习打基础，让私教根据你的目标和学习记录安排下一步。</p>
      <p class="meeting-beta">测试期间，所有内容和功能均免费。</p>
      <div class="meeting-home-actions"><a class="meeting-cta" href="${meetingTrialHref(1)}">先试一道练习</a>
      <a class="text-button" href="/?account=1#home">登录，进入学习空间</a></div>
      </div>
      <figure class="meeting-preview">
        <figcaption>登录后的“今日学习”<span>示例</span></figcaption>
        <div class="mp-card mp-due"><strong>复习到期内容</strong><span>现在有 1 项词汇或语法可以回练。</span><em>开始复习</em></div>
        <div class="mp-card"><strong>7 天练习英文进度汇报</strong><span>2 / 7 项已完成</span><b class="mp-bar" aria-hidden="true"><i></i></b></div>
        <ol class="mp-plan">
          <li><b aria-hidden="true">1</b><span>单项训练：听力理解</span><small>5 分钟</small></li>
          <li><b aria-hidden="true">2</b><span>到期复习：不定代词与单数</span><small>5 分钟</small></li>
          <li><b aria-hidden="true">3</b><span>验证理解：不定代词与单数</span><small>5 分钟</small></li>
        </ol>
      </figure>
    </section>
    <nav class="meeting-trial-links" aria-label="公开练习"><h2>先试一道练习</h2>
    <p class="muted">不用登录，用英文写一到三句，约 3 分钟。</p>
    <ul>${meetingTopics.map(([day, , title]) => `<li><a href="${meetingTrialHref(day)}"><strong>${title}</strong><span>不用登录 · 约 3 分钟</span></a></li>`).join('')}</ul></nav>
    <nav class="meeting-workspace-links" aria-label="学习空间"><h2>学习空间 <span class="meeting-login-tag">登录后可用</span></h2>
    <p class="muted">登录后进入所选模块，学习进度会同步到你的账号。</p>
    <ul>${meetingWorkspaceLinks.map(([route, title, detail]) => `<li><a href="/?account=1#${route}"><strong>${title}</strong><span>${detail}</span></a></li>`).join('')}</ul></nav>
  </main>`;
}


function meetingCurrent(owner, serial, screen) {
  return user?.id === owner && navigationSerial === serial &&
    (screen ? meetingScreen === screen && (screen.preview ? window.location.hash === '#try-meeting/' + screen.task.day : view === 'meeting') : true);
}

function meetingDate(value) {
  return value ? Number(value.slice(5, 7)) + ' 月 ' + Number(value.slice(8)) + ' 日' : '';
}

function meetingHomeAction(d) {
  const progress = d.meeting;
  if (progress.completed && progress.next) {
    return {title: progress.next.title, reason: '继续会议英语训练。先想一想上次的表达，再做今天的情境题。', action: 'data-view="meeting"', button: '继续今天的练习'};
  }
  if (d.review_due) {
    return {title: '复习到期内容', reason: '现在有 ' + d.review_due + ' 项词汇或语法可以回练。', action: 'data-flow35-review="1"', button: '开始复习'};
  }
  if (d.recommendation) {
    return {title: d.recommendation.title, reason: d.recommendation.reason, action: 'data-meeting-detour="1"', button: '开始推荐练习'};
  }
  if (d.mission) {
    return {title: d.mission.title, reason: d.mission.reason, action: 'data-meeting-mission="1"', button: '继续私教任务'};
  }
  if (!d.profile && !progress.completed) {
    return {title: '用英语汇报项目进度', reason: '用三句话讲清已经做了什么、卡在哪里、接下来怎么做。约 3 分钟。', action: 'data-view="meeting"', button: '开始 3 分钟练习'};
  }
  if (!d.profile) {
    return {title: '做一次英语小练习', reason: progress.unlock ? '会议英语下一课安排在 ' + meetingDate(progress.unlock) + '。现在可以先练词汇或语法。' : '从词汇或语法开始，留下今天的一条练习记录。', action: 'data-view="journey"', button: '开始小练习'};
  }
  return {title: '继续你的英语练习', reason: progress.unlock ? '会议英语下一课安排在 ' + meetingDate(progress.unlock) + '。' : '根据已有的学习记录安排一个小练习。', action: 'data-view="journey"', button: '开始小练习'};
}

home = async function meetingHome() {
  const owner = user.id;
  const serial = navigationSerial;
  // A late private-tutor response must never replace the Today page.
  ++coachEpoch;
  clearTimeout(coachPollTimer);
  const d = await api('meeting/today');
  if (!meetingCurrent(owner, serial) || view !== 'home') return;
  meetingToday = d;
  const recommended = meetingHomeAction(d);
  const progress = d.meeting;
  const pathStatus = progress.completed + ' / ' + progress.days.length + ' 项已完成';
  shell(`<div class="meeting-today">
    <div class="pagehead"><h1>今日学习</h1><p class="muted">从一件今天能练完的事开始。</p></div>
    <section class="card meeting-focus">
      <div><h2>${esc(recommended.title)}</h2><p>${esc(recommended.reason)}</p>
      <button class="btn" ${recommended.action}>${recommended.button}</button></div>
    </section>
    <div class="meeting-secondary">
      <section class="card"><h2>${esc(progress.title)}</h2><p>${pathStatus}${progress.unlock ? ' · 下一课安排在 ' + meetingDate(progress.unlock) : ''}</p>
      <progress value="${progress.completed}" max="${progress.days.length}" aria-label="会议英语训练进度"></progress>
      <button class="text-button" data-meeting-plan="1">查看 7 天安排</button></section>
      <section class="card"><h2>AI 私教</h2><p>${d.profile ? '继续上次的对话，或调整学习目标。' : '想按自己的目标学习，可以先做起点检查。'}</p>
      ${d.profile ? '<button class="text-button" data-meeting-coach="1">打开私教对话</button>' : '<button class="text-button" data-coach-assess="1">做起点检查</button>'}</section>
    </div>
  </div>`);
};

function meetingRender(content, preview = false) {
  if (preview) {
    document.documentElement.classList.remove('flow-auth');
    document.title = '英文会议练习 · 语流 Flow';
    app.innerHTML = '<main class="meeting-landing meeting-try"><a class="meeting-brand" href="/">语流 Flow</a>' + content + '</main>';
  } else {
    shell('<div class="meeting-workspace">' + content + '</div>');
  }
}

function meetingPlan(progress) {
  return `<section class="card meeting-plan"><h2>训练安排</h2>
    <ol>${progress.days.map(item => {
      const status = item.completed ? '已完成' : progress.next?.day === item.day ? '可开始' : '后续安排';
      return `<li><span>${esc(item.title)}</span><small>${status}</small></li>`;
    }).join('')}</ol>
    <nav aria-label="公开练习"><h3>练习其他场景</h3>
    <ul>${meetingTopics.map(([, slug, title]) => `<li><a href="/practice/${slug}/">${title}</a></li>`).join('')}</ul></nav></section>`;
}

function meetingTipHTML(result) {
  if (!result) return '';
  return `<div class="meeting-tip">
    ${result.tip?.quote ? `<blockquote lang="en">${esc(result.tip.quote)}</blockquote>` : ''}
    <p>${esc(result.next)}</p>
  </div>`;
}

function meetingFeedbackHTML(result) {
  return `<section class="meeting-feedback" aria-label="练习反馈">
    <h2 tabindex="-1">回看你的表达</h2>
    <ul>${result.checks.map(check => `<li><span>${esc(check.label)}</span><strong>${check.found ? '匹配到片段' : '请结合原句核对'}</strong>
      ${check.quote ? `<q lang="en">${esc(check.quote)}</q>` : ''}</li>`).join('')}</ul>
    ${meetingTipHTML(result)}<p class="small muted">${esc(result.method)}</p>
  </section>`;
}

function meetingTaskHTML(screen) {
  const {task, preview, progress, result, frame, example, draft, editing} = screen;
  const isFinal = task.day === 7 && !preview;
  const count = preview ? '公开练习' : '第 ' + task.day + ' 天';
  const previousChecks = !preview && task.day > 1 && !isFinal && !result ? progress.recent?.feedback.checks : null;
  const revisit = previousChecks?.find(check => !check.found);
  return `<section class="card meeting-exercise">
    <p class="small muted">${count} · 约 3 分钟</p>
    <h1>${esc(task.title)}</h1><p class="meeting-context">${esc(task.context)}</p>
    <ul class="meeting-objectives">${task.checks.map(check => `<li>${esc(check)}</li>`).join('')}</ul>
    ${revisit ? `<p class="meeting-notice">回想上一次怎么表达「${esc(revisit.label)}」，再开始这次的任务。</p>` : ''}
    ${result && !editing ? `<blockquote class="meeting-answer" lang="en">${esc(result.answer)}</blockquote>${meetingFeedbackHTML(result.feedback)}
      <div class="actions">
        ${preview || progress.last ? '<button class="btn" data-meeting-revise="1">改一句再试</button>' : ''}
        ${preview ? '<button class="btn secondary" data-meeting-save="1">保存这次练习</button>' : ''}
        ${!preview ? '<button class="btn' + (isFinal ? '' : ' secondary') + '" data-view="' + (isFinal ? 'report' : 'home') + '">' + (isFinal ? '在档案里看前后对比' : '回到今日学习') + '</button>' : ''}
      </div>
      ${preview ? `<nav class="meeting-more-trials" aria-label="再试一个场景"><h2>再试一个场景</h2><ul>${meetingTopics.filter(([day]) => day !== task.day).map(([day, slug, title]) => `<li><a href="${meetingTrialHref(day)}">${title}</a></li>`).join('')}</ul></nav>
      <p class="small muted">${task.day === 1 ? '保存后即可计入第 1 天。下一课练「说清楚卡在哪里」。' : '保存后可在学习档案里看到这次回答。7 天训练从「汇报项目进度」开始。'}</p>` : ''}
      ${!preview && progress.unlock ? `<p class="meeting-notice">下一课安排在 ${meetingDate(progress.unlock)}。回来练「${esc(progress.next_title)}」。</p>` : ''}`
      : `<form id="meeting-form">
        <label for="meeting-answer">用英文写一到三句</label>
        ${meetingTipHTML(result?.feedback)}
        <textarea id="meeting-answer" name="answer" lang="en" maxlength="1200" rows="5" required autocomplete="off">${esc(draft)}</textarea>
        ${frame ? `<div class="meeting-example"><strong>可以这样起句</strong><p lang="en">${esc(frame)}</p></div>` : ''}
        ${example ? `<div class="meeting-example"><strong>完整示例</strong><p lang="en">${esc(example)}</p></div>` : ''}
        <div class="actions"><button type="submit" class="btn">检查我的表达</button>
        ${example ? '' : `<button type="button" class="text-button" data-meeting-hint="${frame ? 'example' : 'frame'}">${frame ? '看完整示例' : '给我一个句型'}</button>`}</div>
        <p class="small muted">${preview ? '练习会暂存在此标签页，确认保存后才会写入学习档案。' : '先独立写，卡住时可以查看句型。'}${isFinal ? '这次会与第一天的同类练习一起保存。' : ''}</p>
      </form>`}
    <p id="meeting-error" role="alert"></p>
  </section>`;
}

function meetingShowScreen(screen, focus = false) {
  meetingScreen = screen;
  meetingPersistTrial(screen);
  const back = screen.preview ? '' : '<button class="back-link" data-view="home">← 今日学习</button>';
  meetingRender(back + meetingTaskHTML(screen) + (screen.progress ? meetingPlan(screen.progress) : ''), screen.preview);
  if (focus) app.querySelector(screen.editing ? '#meeting-answer' : '.meeting-feedback h2')?.focus?.();
}

function meetingConfirmSave(pending, progress) {
  const joins = pending.day === 1 && !progress.completed;
  meetingScreen = null;
  meetingRender(`<section class="card meeting-exercise">
    <h1>保存这次练习</h1>
    <p>${joins ? '这次将作为第 1 天的记录。下一课练「说清楚卡在哪里」。' : '这次会保存到学习档案的额外练习中。你可以继续原有训练。'}</p>
    <blockquote class="meeting-answer" lang="en">${esc(pending.answer)}</blockquote>
    <div class="actions"><button class="btn" data-meeting-confirm="1">保存到当前账号</button>
    <a href="${meetingTrialHref(pending.day)}">返回我的答案</a></div>
    <p id="meeting-error" role="alert"></p>
  </section>`);
}

async function meetingOpen({plan = false} = {}) {
  const owner = user.id;
  const serial = navigationSerial;
  const progress = await api('meeting');
  if (!meetingCurrent(owner, serial) || view !== 'meeting') return;
  const pending = meetingAuthContext();
  if (pending && !plan) return meetingConfirmSave(pending, progress);
  const task = progress.next;
  if (task && !plan) {
    const draft = meetingDrafts.get(task.day) || '';
    meetingShowScreen({task, progress, draft, editing: true});
    if (task.day === 1) api('meeting/start', {}).catch(() => {});
    return;
  }
  if (progress.last && progress.recent && !plan) {
    meetingShowScreen({task: progress.last, progress, draft: progress.recent.answer, result: progress.recent, editing: false});
    return;
  }
  meetingScreen = null;
  meetingRender(`<button class="back-link" data-view="home">← 今日学习</button>
    <section class="card meeting-exercise"><h1>${esc(progress.title)}</h1>
    <p>${progress.unlock ? '下一课安排在 ' + meetingDate(progress.unlock) + '。' : '已完成 ' + progress.completed + ' / ' + progress.days.length + ' 项。'}</p>
    ${task ? '<button class="btn" data-meeting-open="1">开始练习</button>' : progress.unlock ? '<button class="btn secondary" data-view="home">看看今天还能练什么</button>' : '<button class="btn" data-view="report">看两次汇报对比</button>'}
    </section>${meetingPlan(progress)}`);
}

async function meetingPreviewFromHash() {
  const hash = window.location.hash;
  const match = /^#try-meeting\/(1|3|4)$/.exec(hash);
  if (!match) return false;
  const {previews} = await api('meeting/previews');
  if (window.location.hash !== hash) return true;
  const task = previews.find(item => item.day === Number(match[1]));
  if (!task) return false;
  const saved = meetingRead('flow-meeting-trial-' + task.day);
  meetingShowScreen({editing: true, draft: '', ...saved, task, preview: true});
  api('meeting/preview', {day: task.day, action: 'open', visitor: meetingVisitorId()}).catch(() => {});
  return true;
}

window.addEventListener('popstate', () => {
  if (window.location.hash.startsWith('#try-meeting/') ||
      !user && (meetingAuthContext() || document.querySelector('.meeting-try,.meeting-guest-home'))) boot();
});

function meetingReportHTML(progress) {
  if (!progress.first && !progress.samples?.length) return '';
  const sample = (title, item) => `<article><h3>${esc(title)}</h3><p class="small muted">${esc(item.day)} · ${item.assisted ? '有提示、练习反馈或修订' : '首次作答 · 未查看本任务提示'}</p>
    <blockquote class="meeting-answer" lang="en">${esc(item.answer)}</blockquote>
    <ul>${item.feedback.checks.map(check => `<li>${esc(check.label)} · ${check.found ? '匹配到片段' : '请结合原句核对'}</li>`).join('')}</ul></article>`;
  return `<section class="card meeting-report"><h2>会议英语 · 汇报练习档案</h2>
    ${progress.first ? `<div class="meeting-comparison">${sample('第一次汇报', progress.first)}
      ${progress.retest ? sample('换个项目再汇报', progress.retest) : '<p>完成最后一天的练习后，这里会展示你在另一场会议中的第一次回答。</p>'}</div>` : ''}
    ${progress.samples?.length ? `<details open><summary>已保存的额外练习（${progress.samples.length}）</summary>
      <div class="meeting-comparison">${progress.samples.map(item => sample(item.title, item)).join('')}</div></details>` : ''}
    <p class="small muted">请结合原文判断意思是否说清楚。</p>
    <button class="text-button" data-view="meeting">${progress.retest ? '查看训练记录' : '打开 7 天训练'}</button></section>`;
}

const meetingOldReport = learningReport;
learningReport = async function () {
  const owner = user.id;
  const serial = navigationSerial;
  const progress = api('meeting').catch(() => null);
  await meetingOldReport();
  const result = await progress;
  if ((result?.first || result?.samples?.length) && meetingCurrent(owner, serial) && view === 'report') {
    const starter = app.querySelector('.flow-starter');
    if (starter) {
      const heading = starter.querySelector('h2');
      if (heading) heading.textContent = '补充词汇或语法的独立练习记录';
      const message = starter.querySelector('p');
      if (message) message.textContent = '会议汇报已记录。可以再做一次词汇或语法练习，补充知识图谱的记录。';
    }
    app.querySelector('#main-content .pagehead')?.insertAdjacentHTML('afterend', meetingReportHTML(result));
  }
};

const meetingOldReview = reviewHub;
reviewHub = async function () {
  const owner = user.id;
  const serial = navigationSerial;
  const progress = api('meeting').catch(() => null);
  await meetingOldReview();
  const result = await progress;
  if (!result?.completed || !result.next || !meetingCurrent(owner, serial) || view !== 'review') return;
  app.querySelector('#main-content .pagehead')?.insertAdjacentHTML('afterend',
    `<section class="card meeting-report"><h2>会议英语回练</h2><p>下一项是「${esc(result.next.title)}」。</p><button class="btn" data-view="meeting">开始场景回练</button></section>`);
};

const meetingOldAdmin = admin;
admin = async function () {
  const owner = user.id;
  const serial = navigationSerial;
  const stats = api('meeting/stats').catch(() => null);
  await meetingOldAdmin();
  const d = await stats;
  if (!d || !meetingCurrent(owner, serial) || view !== 'admin') return;
  app.querySelector('#main-content .pagehead')?.insertAdjacentHTML('afterend', `<section class="card meeting-report">
    <h2>会议英语训练</h2><dl class="meeting-metrics">
    <div><dt>已登录用户完成首练 / 开始</dt><dd>${d.completed_first} / ${d.started}</dd></div>
    <div><dt>次日完成回练 / 首练已过一天</dt><dd>${d.next_day_returned} / ${d.next_day_eligible}</dd></div>
    <div><dt>完成复测 / 已有至少七个训练日</dt><dd>${d.completed_retest} / ${d.retest_eligible}</dd></div>
    <div><dt>所有要点均有匹配片段 / 本版无提示复测</dt><dd>${d.all_cues_found} / ${d.unassisted_retests}</dd></div>
    </dl><h3>最近 30 天访客练习</h3><p class="small muted">按浏览器标签页去重。统计开练、提交、重试和确认保存。</p><dl class="meeting-metrics">
    <div><dt>提交首练 / 打开练习</dt><dd>${d.guest.submitted} / ${d.guest.opened}</dd></div>
    <div><dt>反馈后重试 / 已提交</dt><dd>${d.guest.revised} / ${d.guest.submitted}</dd></div>
    <div><dt>确认保存 / 已提交</dt><dd>${d.guest.saved} / ${d.guest.submitted}</dd></div>
    </dl></section>`);
};

app.addEventListener('input', event => {
  if (event.target.id !== 'meeting-answer' || !meetingScreen) return;
  meetingScreen.draft = event.target.value;
  meetingScreen.requestId = null;
  if (meetingScreen.preview) meetingPersistTrial(meetingScreen);
  else meetingDrafts.set(meetingScreen.task.day, event.target.value);
});

function meetingError(message) {
  const target = app.querySelector('#meeting-error');
  if (target) target.textContent = message;
  else toast(message);
}

app.addEventListener('submit', async event => {
  const form = event.target;
  if (form.id !== 'meeting-form' || !meetingScreen) return;
  event.preventDefault();
  const submitButton = form.querySelector('[type="submit"]');
  if (submitButton.disabled) return;
  const screen = meetingScreen;
  const owner = user?.id;
  const serial = navigationSerial;
  const answer = screen.draft.trim();
  submitButton.disabled = true;
  form.querySelector('textarea').readOnly = true;
  const originalLabel = submitButton.textContent;
  submitButton.textContent = '正在检查…';
  const hintButton = form.querySelector('[data-meeting-hint]');
  if (hintButton) hintButton.disabled = true;
  meetingError('');
  try {
    if (screen.preview) {
      const result = await api('meeting/preview', {day: screen.task.day, answer, visitor: meetingVisitorId(), revision: Boolean(screen.result)});
      if (meetingCurrent(owner, serial, screen)) {
        meetingShowScreen({...screen, result: {answer, feedback: result.feedback, requestId: flowRequestId()}, editing: false}, true);
      }
    } else {
      const id = screen.requestId ||= flowRequestId();
      const result = await api('meeting/submit', {day: screen.task.day, answer, request_id: id});
      if (!meetingCurrent(owner, serial, screen)) return;
      meetingDrafts.delete(screen.task.day);
      meetingShowScreen({...screen, draft: answer, result: result.attempt, progress: result.progress, editing: false}, true);
    }
  } catch (error) {
    if (meetingCurrent(owner, serial, screen)) meetingError(error.message);
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = originalLabel;
    form.querySelector('textarea').readOnly = false;
    if (hintButton) hintButton.disabled = false;
  }
});

app.addEventListener('click', async event => {
  const button = event.target.closest('button');
  if (!button || button.disabled) return;
  const screen = meetingScreen;
  const owner = user?.id;
  const serial = navigationSerial;
  try {
    if (button.dataset.meetingCoach) {
      await coachLoad();
    } else if (button.dataset.meetingDetour) {
      await flow35RunStep(meetingToday.recommendation);
    } else if (button.dataset.meetingMission) {
      const id = meetingToday.mission.id;
      await coachLoad();
      if (meetingCurrent(owner, serial) && view === 'home') {
        app.querySelectorAll('[data-coach-mission]').forEach(item => {
          if (item.dataset.coachMission === id) item.click();
        });
      }
    } else if (button.dataset.meetingPlan) {
      view = 'meeting';
      ++navigationSerial;
      history.pushState({view}, '', '#meeting');
      await meetingOpen({plan: true});
      window.scrollTo(0, 0);
    } else if (button.dataset.meetingOpen) {
      await meetingOpen();
    } else if (screen && button.dataset.meetingRevise) {
      meetingShowScreen({...screen, editing: true, requestId: null}, true);
    } else if (screen && button.dataset.meetingHint) {
      const form = button.closest('form');
      const submit = form.querySelector('[type="submit"]');
      submit.disabled = button.disabled = true;
      try {
        const hint = await api(screen.preview ? 'meeting/preview' : 'meeting/hint', {
          day: screen.task.day, action: 'hint', level: button.dataset.meetingHint
        });
        if (meetingCurrent(owner, serial, screen)) meetingShowScreen({...screen, ...hint}, true);
      } finally {
        submit.disabled = button.disabled = false;
      }
    } else if (screen?.preview && button.dataset.meetingSave) {
      meetingSetPending({day: screen.task.day, answer: screen.result.answer, requestId: screen.result.requestId || flowRequestId()});
      history.pushState({view: 'meeting'}, '', '#meeting/save');
      if (user) await navigate('meeting');
      else auth();
    } else if (user && button.dataset.meetingConfirm) {
      const pending = meetingAuthContext();
      if (!pending) return;
      button.disabled = true;
      try {
        const result = await api('meeting/save-preview', {
          day: pending.day, answer: pending.answer, request_id: pending.requestId, visitor: meetingVisitorId()
        });
        if (!meetingCurrent(owner, serial) || view !== 'meeting') return;
        meetingSetPending(null);
        history.replaceState({view: 'meeting'}, '', '#meeting');
        toast('练习已保存');
        await navigate(result.joined ? 'meeting' : 'report');
      } finally {
        button.disabled = false;
      }
    }
  } catch (error) {
    meetingError(error.message);
  }
});
