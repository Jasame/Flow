"""Rule 9 of the working agreement (tools/README.md; the owner, 2026-11-25: 「后台运行的应用不要播放系统声音」): what the
tools run on the owner's Mac makes no sound. Imported for its effect, before any browser starts: every Chromium that
Playwright launches from then on is muted (--mute-audio). A page's sound still plays as the page plays it (its timing,
its state, the media session), unheard, so the tests that check sound keep checking it.

    import silent  # noqa: F401  (rule 9: muted browsers)
"""
from playwright.sync_api import BrowserType

_launch = BrowserType.launch


def _muted(self, *args, **kw):
    if self.name == 'chromium':
        kw['args'] = [*(kw.get('args') or []), '--mute-audio']
    return _launch(self, *args, **kw)


BrowserType.launch = _muted
