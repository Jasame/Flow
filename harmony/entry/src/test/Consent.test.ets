import { describe, it, expect } from '@ohos/hypium';
import { Consent } from '../main/ets/common/Consent';

interface Answer403 {
  error: string;
  code: string;
}

/** The first start's rules (common/Consent.ets), the same as Android's ConsentTest where both have them. */
export default function consentTest() {
  describe('Consent', () => {
    it('stateFromTheAnswerAndTheVersion', 0, () => {
      expect(Consent.state('', false, '2026-11-25/2026-11-25')).assertEqual(Consent.ASK);
      expect(Consent.state('2026-11-25/2026-11-25', false, '2026-11-25/2026-11-25')).assertEqual(Consent.AGREED);
      // a newer 用户协议 or 隐私和数据 in this build: asked again; 基本模式 stays 基本模式 until then
      expect(Consent.state('2026-11-01/2026-11-01', false, '2026-11-25/2026-11-25')).assertEqual(Consent.ASK);
      expect(Consent.state('', true, '2026-11-25/2026-11-25')).assertEqual(Consent.BASIC);
    });

    it('signInRoutes', 0, () => {
      expect(Consent.signIn('/api/login')).assertTrue();
      expect(Consent.signIn('/api/register/')).assertTrue();
      expect(Consent.signIn('/api/auth/code')).assertTrue();
      expect(Consent.signIn('/api/teacher/check')).assertTrue();
      expect(Consent.signIn('/api/me')).assertFalse();
      expect(Consent.signIn('/api/login/extra')).assertFalse();
    });

    it('signInAnswerIsThePagesError', 0, () => {
      const a = JSON.parse(Consent.SIGN_IN_ANSWER) as Answer403;
      expect(a.code).assertEqual('app-consent');
      expect(a.error.indexOf('《隐私和数据》') >= 0).assertTrue();
    });

    it('listsOnlyWhenBothAreThere', 0, () => {
      expect(Consent.hasLists('<h3 id="g-info-list">a</h3><h3 id="g-sharing-list">b</h3>')).assertTrue();
      expect(Consent.hasLists('<h3 id="g-info-list">a</h3>')).assertFalse();
    });

    it('parseTheBuildsFile', 0, () => {
      const ok = '{"version":"v1","docs":{"terms":{"title":"T","html":"<p>t</p>"},' +
        '"privacy":{"title":"P","html":"<p>p</p>"}}}';
      const d = Consent.parse(ok);
      expect(d !== null).assertTrue();
      expect(d!.version).assertEqual('v1');
      expect(d!.titles.get('privacy')).assertEqual('P');
      expect(d!.html.get('terms')).assertEqual('<p>t</p>');
      expect(Consent.parse('{"version":"v1","docs":{"terms":{"title":"T","html":"x"}}}') === null).assertTrue();
      expect(Consent.parse('not json') === null).assertTrue();
      expect(Consent.missing().html.get('privacy')!.length > 0).assertTrue();
    });

    it('questionText', 0, () => {
      const first = Consent.question('', true, false);
      expect(first.startsWith(Consent.BODY)).assertTrue();
      expect(first.endsWith(Consent.TAIL_FIRST)).assertTrue();
      expect(first.indexOf(Consent.LISTS_LINE) < 0).assertTrue();
      const why = Consent.question(Consent.WHY_MIC, false, true);
      expect(why.startsWith(Consent.WHY_MIC + '\n\n')).assertTrue();
      expect(why.endsWith(Consent.TAIL_BASIC)).assertTrue();
      expect(why.indexOf(Consent.LISTS_LINE) > 0).assertTrue();
    });

    it('partsKeepTheTextAndLinkTheTitles', 0, () => {
      const text = Consent.question('', true, true);
      const parts = Consent.parts(text, true);
      expect(parts.map((p: string[]) => p[0]).join('')).assertEqual(text);
      const links = parts.filter((p: string[]) => p[1] !== '');
      expect(links.every((p: string[]) => p[0].startsWith('《'))).assertTrue();
      expect(links.some((p: string[]) => p[1] === 'flow-doc:privacy#g-sharing-list')).assertTrue();
      expect(links.some((p: string[]) => p[1] === 'flow-doc:terms')).assertTrue();
      // without the lists in this build, their names stay plain text
      expect(Consent.parts(text, false).some((p: string[]) => p[1].indexOf('#') >= 0)).assertFalse();
    });

    it('docLinks', 0, () => {
      const a = Consent.docLink('flow-doc:privacy#g-info-list');
      expect(a![0]).assertEqual('privacy');
      expect(a![1]).assertEqual('g-info-list');
      expect(Consent.docLink('flow-doc:nope')![0]).assertEqual('terms');
      // only a plain part name reaches the page's script
      expect(Consent.docLink("flow-doc:privacy#g-a');alert(1)//")![1]).assertEqual('');
      expect(Consent.docLink('https://flowlang.cn/') === null).assertTrue();
    });

    it('pageHasTheBody', 0, () => {
      const p = Consent.page('<p>x</p>');
      expect(p.indexOf('<body><p>x</p></body>') > 0).assertTrue();
      expect(p.indexOf('prefers-color-scheme:dark') > 0).assertTrue();
    });
  });
}
