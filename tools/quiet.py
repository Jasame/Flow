"""Browsers the tools start make no sound (the owner's rule, 2026-11-25: what runs in the background stays silent).

    from quiet import silent
    with sync_playwright() as pw:
        silent(pw)          # then launch and open pages as usual

silent(pw) wraps pw's BrowserType.launch and each launched Browser's new_context / new_page, so the tools need no change
where they open browsers (ui_test.py alone has 21 launches and 48 contexts):
- Chrome starts with --mute-audio: nothing Chrome itself plays reaches the speakers;
- every context and page, Chrome or WebKit (which has no such switch), gets MUTE_JS before any page script:
  - a media element is at volume 0 once it starts playing (the app never sets .volume; it sets .muted itself, which is
    left alone),
  - Web Audio reaches the speakers only through a gain of 0,
  - every sentence of the browser voice is spoken at volume 0: on a Mac speechSynthesis is the system's speech engine,
    which --mute-audio does not reach.
Playback itself still happens (play(), paused, currentTime, ended, the voice's start and end events), so every check of
it holds. A test's own init script added later (a fake voice, a speech counter) wraps these and stays silent. The blank
sentence the app speaks on the first tap to unlock the voice is at volume 0 anyway. From 语流 08's tested snippet,
plus Web Audio.
"""

MUTE_ARGS = ['--mute-audio']

MUTE_JS = """(() => {
  document.addEventListener('play', e => { try { e.target.volume = 0; } catch (err) {} }, true);
  const AN = window.AudioNode && AudioNode.prototype;
  if (AN && window.AudioDestinationNode) {
    const connect = AN.connect, quiet = new WeakMap();
    AN.connect = function (dest, ...rest) {
      if (!(dest instanceof AudioDestinationNode)) return connect.call(this, dest, ...rest);
      let g = quiet.get(dest);
      if (!g) { g = dest.context.createGain(); g.gain.value = 0; connect.call(g, dest); quiet.set(dest, g); }
      connect.call(this, g, ...rest);
      return dest;
    };
  }
  if (window.speechSynthesis) {
    const speak = speechSynthesis.speak.bind(speechSynthesis);
    speechSynthesis.speak = u => { try { u.volume = 0; } catch (e) {} return speak(u); };
  }
})();"""


def _quiet_browser(browser):
    new_context, new_page = browser.new_context, browser.new_page

    def quiet_context(*a, **kw):
        ctx = new_context(*a, **kw)
        ctx.add_init_script(MUTE_JS)
        return ctx

    def quiet_page(*a, **kw):
        page = new_page(*a, **kw)
        page.add_init_script(MUTE_JS)  # before its first navigation: the blank page it starts on plays nothing
        return page
    browser.new_context, browser.new_page = quiet_context, quiet_page
    return browser


def silent(pw):
    """Every browser pw launches from now on is muted (see the module's note). Returns pw."""
    for name, args in (('chromium', MUTE_ARGS), ('webkit', []), ('firefox', [])):
        browser_type = getattr(pw, name, None)
        if browser_type is None or getattr(browser_type, '_flow_quiet', False):
            continue
        launch = browser_type.launch

        def quiet_launch(*a, _launch=launch, _args=args, **kw):
            if _args:
                kw['args'] = list(_args) + [x for x in (kw.get('args') or []) if x not in _args]
            return _quiet_browser(_launch(*a, **kw))
        browser_type.launch = quiet_launch
        browser_type._flow_quiet = True
    return pw
