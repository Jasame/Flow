import { abilityAccessCtrl, bundleManager, Permissions as Perm, Want } from '@kit.AbilityKit';
import { notificationManager } from '@kit.NotificationKit';
import { preferences } from '@kit.ArkData';
import { deviceInfo } from '@kit.BasicServicesKit';
import { AppState } from './AppState';

const MIC: Perm = 'ohos.permission.MICROPHONE';

/**
 * The microphone and the notifications, as the other apps answer them (docs/native-bridge.md §4, §5):
 * 'granted' | 'denied' | 'undetermined'. The system asks once; after a no, the system's own sheet that lets the learner
 * turn it on there (requestPermissionOnSetting) is offered instead, and only in a tap.
 */
export class Permissions {
  private static store(): preferences.Preferences | undefined {
    const ctx = AppState.context;
    return ctx ? preferences.getPreferencesSync(ctx, { name: 'flow-perm' }) : undefined;
  }

  private static asked(p: string): boolean {
    const s = Permissions.store();
    return s ? s.getSync('asked:' + p, false) as boolean : false;
  }

  private static markAsked(p: string): void {
    const s = Permissions.store();
    if (s) {
      s.putSync('asked:' + p, true);
      s.flush();
    }
  }

  private static tokenId(): number {
    const info = bundleManager.getBundleInfoForSelfSync(bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_APPLICATION);
    return info.appInfo.accessTokenId;
  }

  static micGranted(): boolean {
    try {
      const at = abilityAccessCtrl.createAtManager();
      return at.checkAccessTokenSync(Permissions.tokenId(), MIC) === abilityAccessCtrl.GrantStatus.PERMISSION_GRANTED;
    } catch (e) {
      return false;
    }
  }

  static async mic(): Promise<string> {
    if (Permissions.micGranted()) {
      return 'granted';
    }
    return Permissions.asked(MIC) ? 'denied' : 'undetermined';
  }

  /** In a tap: the system's question the first time; after a no, its sheet to turn it on. → true when allowed. */
  static async askMic(): Promise<boolean> {
    if (Permissions.micGranted()) {
      return true;
    }
    const ctx = AppState.context;
    if (!ctx) {
      return false;
    }
    const at = abilityAccessCtrl.createAtManager();
    try {
      if (!Permissions.asked(MIC)) {
        Permissions.markAsked(MIC);
        const r = await at.requestPermissionsFromUser(ctx, [MIC]);
        return r.authResults.length > 0 && r.authResults[0] === 0;
      }
      const again = await at.requestPermissionOnSetting(ctx, [MIC]);
      return again.length > 0 && again[0] === abilityAccessCtrl.GrantStatus.PERMISSION_GRANTED;
    } catch (e) {
      AppState.warn('mic: ' + JSON.stringify(e));
      return false;
    }
  }

  static notifyAllowed(): boolean {
    try {
      return notificationManager.isNotificationEnabledSync();
    } catch (e) {
      return false;
    }
  }

  /** The system's question (only once); later the system's own sheet. → allowed now. */
  static async askNotify(): Promise<boolean> {
    if (Permissions.notifyAllowed()) {
      return true;
    }
    const ctx = AppState.context;
    if (!ctx) {
      return false;
    }
    try {
      Permissions.markAsked('notify');
      await notificationManager.requestEnableNotification(ctx);
    } catch (e) {
      // refused, or asked before: the settings
    }
    return Permissions.notifyAllowed();
  }

  static notifyAskedBefore(): boolean {
    return Permissions.asked('notify');
  }

  /** This app's notification settings (notify.settings()). */
  static openNotifySettings(): void {
    const ctx = AppState.context;
    if (!ctx) {
      return;
    }
    // the app's page in 设置: HarmonyOS 5.0.0 (API 12) has no openNotificationSettings, it came with API 13
    const appPage = () => {
      try {
        const bundle = bundleManager.getBundleInfoForSelfSync(bundleManager.BundleFlag.GET_BUNDLE_INFO_DEFAULT).name;
        const want: Want = {
          bundleName: 'com.huawei.hmos.settings', abilityName: 'com.huawei.hmos.settings.MainAbility',
          uri: 'application_info_entry', parameters: { 'pushParams': bundle },
        };
        ctx.startAbility(want).catch(() => {});
      } catch (e) {
        AppState.warn('settings: ' + JSON.stringify(e));
      }
    };
    if (deviceInfo.sdkApiVersion < 13) {
      appPage();
      return;
    }
    try {
      notificationManager.openNotificationSettings(ctx).catch(appPage);
    } catch (e) {
      appPage();
    }
  }
}
