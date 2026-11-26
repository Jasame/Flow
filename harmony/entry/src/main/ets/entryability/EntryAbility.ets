import { AbilityConstant, UIAbility, Want } from '@kit.AbilityKit';
import { window } from '@kit.ArkUI';
import { AppState } from '../common/AppState';
import { Site } from '../common/Site';
import { Reminders } from '../notify/Reminders';
import { Recorder } from '../rec/Recorder';
import { FlowAudio } from '../audio/FlowAudio';
import { ConsentGate } from '../common/ConsentGate';

/** A reminder's path ("#/review", "#/"), from its tap (wantAgent parameters). */
function pathOf(want: Want): string | undefined {
  const p = want.parameters ? want.parameters['flow.path'] : undefined;
  return typeof p === 'string' && (p as string).startsWith('#/') ? p as string : undefined;
}

export default class EntryAbility extends UIAbility {
  onCreate(want: Want, launchParam: AbilityConstant.LaunchParam): void {
    AppState.context = this.context;
    // the test switch (docs/native-bridge.md §9): `hdc shell aa start -a EntryAbility -b <bundle> --pb flow.mute true`
    const m = want.parameters ? want.parameters['flow.mute'] : undefined;
    if ((m === true || m === 'true') && (Site.beta || Site.debug)) {
      Site.mute = true;
    }
    AppState.startPath = pathOf(want);
    Reminders.init();
    Recorder.init();
    FlowAudio.init();
    // 不同意 and 撤回同意 (common/ConsentGate.ets): reading and recording stop, reminders and reading places go
    ConsentGate.onClear = [
      () => FlowAudio.forget(),
      () => Recorder.cancel(),
      () => Reminders.forget(),
    ];
  }

  onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): void {
    const p = pathOf(want);
    if (p) {
      AppState.open(p);
    }
  }

  onWindowStageCreate(windowStage: window.WindowStage): void {
    windowStage.loadContent('pages/Index', (err) => {
      if (err && err.code) {
        AppState.warn('loadContent: ' + JSON.stringify(err));
      }
    });
  }

  onForeground(): void {
    AppState.foreground();
  }

  onBackground(): void {
    AppState.background();
  }
}
