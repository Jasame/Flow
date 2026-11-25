#if BETA
import Foundation

/// Beta builds only (FLOW_BRIDGE_TEST=1, used by the UI tests): a page on the 内测版's origin with a button for each
/// native part, so the bridge can be tried before the site's own pages use it. It plays a real article's recording.
enum BridgeTestPage {
    static let html = #"""
    <!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>桥测试</title>
    <style>
    :root{color-scheme:light dark}
    body{font:16px -apple-system,system-ui;margin:0;padding:calc(env(safe-area-inset-top) + 8px) 16px calc(env(safe-area-inset-bottom) + 24px);background:#fbfaf6;color:#1d2420}
    h1{font-size:20px;margin:6px 0}
    .row{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0}
    button{flex:1 1 30%;padding:11px 8px;font-size:15px;border-radius:10px;border:1px solid #1f9d55;background:#fff;color:inherit}
    .out{font:14px ui-monospace,Menlo,monospace;white-space:pre-wrap;margin:4px 0;padding:8px;border-radius:8px;background:#eef3ef}
    @media (prefers-color-scheme:dark){body{background:#101412;color:#e6ece8} button{background:#1b221e} .out{background:#1b221e}}
    </style></head><body>
    <h1>语流 App 桥测试</h1>
    <p class="out" id="has">FlowApp: -</p>
    <p class="out" id="state">state: -</p>
    <p class="out" id="tick">t: -</p>
    <div class="row"><button id="play">播放全文</button><button id="pause">暂停</button><button id="resume">继续</button></div>
    <div class="row"><button id="prev">上一句</button><button id="next">下一句</button><button id="stop">停止</button></div>
    <div class="row"><button id="texts">朗读三句</button></div>
    <div class="row"><button id="lrate">锁屏 1.25×</button><button id="lrep">锁屏单句循环</button><button id="lback">锁屏退回 5 秒</button></div>
    <div class="row"><button id="lnorep">锁屏不循环</button><button id="settings">iOS 专属功能</button><button id="feats">开关状态</button><button id="featreset">开关复原</button></div>
    <div class="row"><button id="offplay">离线播放今天这篇</button></div>
    <div class="row"><button id="buzz">震一下</button><button id="frugal">省电状态</button></div>
    <p class="out" id="feel">feel: -</p>
    <div class="row"><button id="card">小组件数据</button><button id="act">实时活动 3/10</button><button id="actend">结束活动</button></div>
    <div class="row"><button id="acton">打开实时活动</button><button id="sample">小组件样例</button></div>
    <p class="out" id="glance">glance: -</p>
    <p class="out" id="hash">hash: -</p>
    <p class="out" id="feat">features: -</p>
    <p class="out" id="note">note: -</p>
    <div class="row"><button id="rec">录音两秒</button></div>
    <p class="out" id="recOut">rec: -</p>
    <div class="row"><button id="notify">排复习提醒</button><button id="offon">关了再开</button></div>
    <p class="out" id="notifyOut">notify: -</p>
    <p class="out" id="offonOut">offon: -</p>
    <script>
    'use strict';
    const $ = id => document.getElementById(id);
    const A = window.FlowApp;
    $('has').textContent = A ? `FlowApp: v${A.v} app ${A.app} (${A.features.join(' ')})` : 'FlowApp: none';
    const show = d => {
      $('state').textContent = `state: ${d.state} i: ${d.i} n: ${d.n == null ? '' : d.n} why: ${d.why || ''} rate: ${d.rate == null ? '' : d.rate} rep: ${d.rep == null ? '' : d.rep} loop: ${d.loop == null ? '' : d.loop}`;
      if (d.note) $('note').textContent = 'note: ' + d.note;
    };
    A.on('audio', show);
    A.on('audio-tick', d => { $('tick').textContent = `t: ${d.t.toFixed(1)} i: ${d.i}`; });
    A.on('rec', d => { $('recOut').textContent = `rec: ${d.state}` + (d.ms ? ` ${d.ms} ms` : ''); if (d.state === 'done' || d.state === 'cut') finishRec(); });
    const fail = e => { $('note').textContent = 'note: error ' + (e && e.message || e); };
    $('play').onclick = async () => {
      try {
        const id = 'v5-campus-a2-radio-host';
        const m = await (await fetch(`/api/next/material?id=${id}&level=A2`)).json();
        const v = m.audio.version, voice = 'us-f';
        const t = await (await fetch(`/audio/${voice}/${id}.json?v=${v}`)).json();
        const r = await A.audio.play({ key: 'listen:' + id, title: m.title, src: `/audio/${voice}/${id}.mp4?v=${v}`, sentences: t.sentences.map(s => [s.s, s.e]) });
        if (!r.ok) fail(r.why);
      } catch (e) { fail(e); }
    };
    $('pause').onclick = () => A.audio.pause().then(show, fail);
    $('resume').onclick = () => A.audio.resume().then(show, fail);
    $('prev').onclick = () => A.audio.step(-1).then(show, fail);
    $('next').onclick = () => A.audio.step(1).then(show, fail);
    $('stop').onclick = () => A.audio.stop().then(show, fail);
    $('texts').onclick = () => A.audio.play({ key: 'read:bridge-test', title: '三句话', voice: 'us-f',
      texts: ['Good morning, everyone.', 'This sentence is read by the app.', 'It keeps going with the screen locked.'] }).then(r => { if (!r.ok) fail(r.why); }, fail);
    const remote = (cmd, o) => A.call('audio.remote', { cmd, ...o }).then(show, fail);  // the lock screen's buttons (LockScreen27)
    $('lrate').onclick = () => remote('rate', { v: 1.25 });
    $('lrep').onclick = () => remote('repeat', { on: true });
    $('lnorep').onclick = () => remote('repeat', { on: false });
    $('lback').onclick = () => remote('back', { v: 5 });
    $('settings').onclick = () => A.call('app.settings').then(r => { $('feat').textContent = 'features: shown ' + (r && r.ok); }, fail);
    const feats = () => A.call('app.features').then(f => { $('feat').textContent = 'features: ' + Object.keys(f).sort().map(k => `${k}:${f[k] ? 1 : 0}`).join(' '); });
    feats();
    $('feats').onclick = feats;
    // every switch of 「iOS 专属功能」 back to how it comes (a test that stopped half way may have left one on)
    $('featreset').onclick = async () => {
      for (const id of Object.keys(await A.call('app.features'))) await A.call('app.feature', { id });
      feats();
    };
    $('buzz').onclick = () => A.call('app.haptic', { kind: 'success' }).then(r => { $('feel').textContent = 'feel: haptic ' + r.ok; }, fail);
    $('frugal').onclick = () => A.call('app.frugal').then(r => { $('feel').textContent = 'feel: frugal ' + r.on; }, fail);
    A.on('frugal', d => { $('feel').textContent = 'feel: frugal event ' + d.on; });
    $('card').onclick = () => A.call('app.today-card').then(c => {
      $('glance').textContent = c ? `glance: card ${c.state} due ${c.due} line ${c.line ? 'yes' : 'no'}` : 'glance: card none';
    }, fail);
    $('act').onclick = async () => {
      const r = await A.call('activity.review', { done: 3, total: 10 });
      $('glance').textContent = `glance: activity ${r.ok} ${r.why || ''} count ${await A.call('activity.count')}`;
    };
    $('sample').onclick = () => A.call('app.today-card-sample').then(() => { $('glance').textContent = 'glance: sample'; }, fail);
    $('acton').onclick = () => A.call('app.feature', { id: 'review-activity', on: true }).then(feats, fail);
    $('actend').onclick = async () => {
      await A.call('activity.end', { done: 10, total: 10 });
      $('glance').textContent = `glance: ended count ${await A.call('activity.count')}`;
    };
    const showHash = () => { $('hash').textContent = 'hash: ' + (location.hash || '-'); };
    addEventListener('hashchange', showHash); showHash();
    // 离线朗读包: today's text, its recording at an address that goes nowhere: only the app's own copy can play it
    $('offplay').onclick = async () => {
      try {
        const h = await (await fetch('/api/next/home')).json();
        const read = h.path && h.path.steps && h.path.steps.find(s => s.key === 'read');
        const id = read ? decodeURIComponent(read.href.split('/')[2] || '') : ((h.today || [])[0] || {}).id;
        const m = await (await fetch(`/api/next/material?id=${encodeURIComponent(id)}`)).json();
        const v = m.audio.version, voice = m.audio.voices.includes('us-f') ? 'us-f' : m.audio.voices[0];
        const t = await (await fetch(`/audio/${voice}/${encodeURIComponent(id)}.json?v=${v}`)).json();
        const r = await A.audio.play({ key: 'listen:' + id, title: m.title, sentences: t.sentences.map(s => [s.s, s.e]),
          src: `https://offline.invalid/audio/${voice}/${encodeURIComponent(id)}.mp4?v=${v}` });
        if (!r.ok) fail(r.why);
      } catch (e) { fail(e); }
    };
    let recording = false;
    async function finishRec() {
      if (!recording) return; recording = false;
      const r = await A.rec.stop();
      if (!r.ok) { $('recOut').textContent = 'rec: ' + (r.message || r.why); return; }
      const b = atob(r.data.slice(0, 64)), u32 = o => b.charCodeAt(o) | b.charCodeAt(o + 1) << 8 | b.charCodeAt(o + 2) << 16 | b.charCodeAt(o + 3) << 24;
      const head = b.slice(0, 4) + '/' + b.slice(8, 12), rate = r.mime_type === 'audio/wav' ? u32(24) : 0;
      $('recOut').textContent = `rec: ok ${r.mime_type} ${head} ${rate} Hz ${r.bytes} bytes ${r.ms} ms`;
    }
    $('rec').onclick = async () => {
      const r = await A.rec.start({ max: 2 });
      if (!r.ok) { $('recOut').textContent = 'rec: ' + (r.message || r.why); return; }
      recording = true;
    };
    $('notify').onclick = async () => {
      const ok = await A.notify.ask();
      const now = Date.now() / 1000;
      const r = await A.call('notify.test', { reminder: { hour: 20, once: now + 3600 }, due: 5, new: 3, minutes: 4,
        forecast: [8, 6, 0, 4, 3, 2, 1], plan: { daily_new: 0 }, total: 30, app: true });
      const p = r.pending || [];
      $('notifyOut').textContent = `notify: ${ok ? 'allowed' : 'not allowed'} ${r.permission} pending ${p.length}` + (p.length ? ` first ${p[0].id}` : '');
    };
    $('offon').onclick = async () => {  // 关闭, then 到点用 App 通知提醒 again (the plan page's row)
      await A.notify.off();
      const off = await A.notify.permission(), none = (await A.notify.pending()).length;
      const ok = await A.notify.ask();
      const on = await A.notify.permission();
      // the same counts again without `app`: whatever ask() left the app's switch at decides
      const r = await A.call('notify.test', { reminder: { hour: 20 }, due: 5, new: 3, minutes: 4,
        forecast: [8, 6, 0, 4, 3, 2, 1], plan: { daily_new: 0 }, total: 30 });
      $('offonOut').textContent = `offon: ${off} ${none} ${ok ? 'allowed' : 'not allowed'} ${on} ${(r.pending || []).length}`;
    };
    </script></body></html>
    """#
}
#endif
