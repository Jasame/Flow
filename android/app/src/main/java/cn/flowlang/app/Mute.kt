package cn.flowlang.app

/**
 * The test switch (docs/native-bridge.md §9: tests make no sound). On: the whole-text player and the phone's voice at
 * volume 0, the page's <audio>, Web Audio and speechSynthesis silent, reminders without a sound. Turned on by the UI tests,
 * or with `adb shell am start … --ez flow.mute true` on a debug or beta build. The app is otherwise the same.
 */
object Mute {
    @Volatile var on = false
}
