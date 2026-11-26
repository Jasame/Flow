import { abilityAccessCtrl, bundleManager, Permissions as Perm, Want } from '@kit.AbilityKit';
import { notificationManager } from '@kit.NotificationKit';
import { preferences } from '@kit.ArkData';
import { BusinessError, deviceInfo } from '@kit.BasicServicesKit';
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
      await notificationManager.requestEnableNotification(ctx);
      Permissions.markAsked('notify');
    } catch (e) {
      // 1600004: the learner said no (it counts as asked: from now on the page points to the settings). Anything else
      // (1600013 a dialog already up, 1600001/1600003 the service): not asked yet, the next tap asks again.
      const code = (e as BusinessError).code;
      AppState.warn('notify ask: ' + code);
      if (code === 1600004) {
        Permissions.markAsked('notify');
      }
    }
    return Permissions.notifyAllowed();
  }

  static notifyAskedBefore(): boolean {
    return Permissions.asked('notify');
  }

  /** This app's page in 设置 (应用和元服务 → 语流): the microphone is on it, and 通知 (privacy.settings). */
  static openAppSettings(): void {
    const ctx = AppState.context;
    if (!ctx) {
      return;
    }
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
  }

  /** privacy.permissions: notifications as the phone has them for this app ('granted' | 'undetermined' | 'denied'). */
  static notifyState(): string {
    if (Permissions.notifyAllowed()) {
      return 'granted';
    }
    return Permissions.notifyAskedBefore() ? 'denied' : 'undetermined';
  }

  /** This app's notification settings (notify.settings()). */
  static openNotifySettings(): void {
    const ctx = AppState.context;
    if (!ctx) {
      return;
    }
    // the app's page in 设置: HarmonyOS 5.0.0 (API 12) has no openNotificationSettings, it came with API 13
    const appPage = () => Permissions.openAppSettings();
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
