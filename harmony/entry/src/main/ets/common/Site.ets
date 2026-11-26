import BuildProfile from 'BuildProfile';
import { url } from '@kit.ArkTS';

/**
 * The one site this app opens: https://flow.jasa.hk (product beta, 「语流内测」) or https://flowlang.cn (product prod,
 * 「语流」), from the product's buildProfileFields (build-profile.json5). Only this origin gets window.FlowApp.
 */
export class Site {
  static readonly origin: string = String(BuildProfile.FLOW_SITE).replace(new RegExp('/+$'), '');
  static readonly beta: boolean = String(BuildProfile.FLOW_BETA) === 'true';
  static readonly version: string = BuildProfile.VERSION_NAME;
  /** The commit (7 characters) CI built it from; "dev" when built on a Mac. */
  static readonly build: string = String(BuildProfile.FLOW_BUILD);
  static readonly debug: boolean = BuildProfile.DEBUG;
  /** ArkWeb's own user agent with " FlowHarmony/<version>" at the end; set when the web view is attached. */
  static userAgent: string = 'FlowHarmony/' + BuildProfile.VERSION_NAME;
  /** The test switch (docs/native-bridge.md §9): no sound at all. `--pb flow.mute true` on a debug or beta build. */
  static mute: boolean = false;

  static parse(u: string): url.URL | undefined {
    try {
      return url.URL.parseURL(u);
    } catch (e) {
      return undefined;
    }
  }

  static host(): string {
    const p = Site.parse(Site.origin);
    return p ? p.hostname.toLowerCase() : '';
  }

  /** https on the site's own host and port only. */
  static isOwn(u: string | undefined | null): boolean {
    if (!u) {
      return false;
    }
    const p = Site.parse(u);
    if (!p) {
      return false;
    }
    return p.protocol === 'https:' && p.hostname.toLowerCase() === Site.host() && (p.port === '' || p.port === '443');
  }

  /** "/audio/us-f/x.mp4?v=3" → "https://<site>/audio/us-f/x.mp4?v=3"; a full https address on the site is kept. */
  static abs(path: string): string {
    if (path.startsWith('https://')) {
      return path;
    }
    return path.startsWith('/') ? Site.origin + path : Site.origin + '/' + path;
  }

  /** A path on the site to open, from a reminder ("#/review" or "/#/review"); anything else: the start page. */
  static startUrl(path: string | undefined): string {
    if (path && path.startsWith('#/')) {
      return Site.origin + '/' + path;
    }
    if (path && path.startsWith('/') && !path.startsWith('//')) {
      return Site.origin + path;
    }
    return Site.origin + '/';
  }
}
