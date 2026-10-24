# android-emulator: reference tables

All commands assume `adb` = `~/Android/Sdk/platform-tools/adb -s emulator-5554` (or
`export ANDROID_SERIAL=emulator-5554`). Commands marked ✓ were tested on this AVD (API 36).

## Key events (`adb shell input keyevent <NAME|code>`, or `emu-key.sh NAME`)

| Name | Code | Use |
|---|---|---|
| HOME | 3 | launcher ✓ |
| BACK | 4 | back ✓ |
| ENTER | 66 | submit / newline ✓ |
| DEL / FORWARD_DEL | 67 / 112 | backspace / delete |
| TAB | 61 | next field |
| APP_SWITCH | 187 | recents |
| MENU | 82 | menu |
| SEARCH | 84 | search |
| WAKEUP / SLEEP / POWER | 224 / 223 / 26 | screen on / off / toggle ✓ (WAKEUP) |
| DPAD_UP/DOWN/LEFT/RIGHT/CENTER | 19/20/21/22/23 | focus navigation |
| MOVE_HOME / MOVE_END | 122 / 123 | caret to start / end of field ✓ |
| VOLUME_UP / VOLUME_DOWN / VOLUME_MUTE | 24 / 25 / 164 | volume |
| CAMERA / NOTIFICATION | 27 / 83 | camera / notification shade |

- Select all: `adb shell input keycombination KEYCODE_CTRL_LEFT KEYCODE_A` ✓ (used by `emu-type.sh --clear`).
- Open the notification shade: `adb shell cmd statusbar expand-notifications`; collapse it with `collapse` ✓.

## `input`

| Command | Notes |
|---|---|
| `input tap X Y` ✓ | |
| `input swipe X1 Y1 X2 Y2 [ms]` ✓ | Same start and end points with ms≥600 is a long-press |
| `input draganddrop X1 Y1 X2 Y2 [ms]` | Drag |
| `input text <escaped>` ✓ | Spaces as `%s`, shell metacharacters backslash-escaped. Use `emu-type.sh` |
| `input keycombination K1 K2` ✓ | Chords |

## Activity manager (`am`)

| Command | Notes |
|---|---|
| `am start -W -n pkg/.Activity` ✓ | `-W` waits and prints LaunchState/TotalTime |
| `am start -W -a android.intent.action.VIEW -d URI [pkg]` ✓ | Deep link (https, tel:, geo:, custom schemes) |
| `am start -n pkg/.A --es key val --ei n 1 --ez flag true` | Intent extras |
| `am start -S …` | Force-stop before starting |
| `am force-stop pkg` ✓ | |
| `am kill pkg` | Kill a background process only |
| `am broadcast -a ACTION [-n pkg/.Receiver]` | Broadcast |
| `am instrument -w pkg.test/androidx.test.runner.AndroidJUnitRunner` | Run instrumentation tests (or `./gradlew connectedDebugAndroidTest`) |
| `cmd package resolve-activity --brief -c android.intent.category.LAUNCHER pkg` ✓ | Find the launcher activity |

## Package manager (`pm`) and `install`

| Command | Notes |
|---|---|
| `pm list packages [-3] [-f] [filter]` ✓ | `-3` third-party only, `-f` shows the APK path |
| `pm path pkg` ✓ | Is it installed? |
| `install -r -g -t app.apk` | Replace, grant all runtime permissions, allow test-only |
| `install-multiple base.apk split_*.apk` | Split APKs |
| `pm clear pkg` | Wipes this app's data |
| `pm grant/revoke pkg PERMISSION` ✓ | Runtime permissions |
| `pm reset-permissions` | Reset all runtime grants |
| `dumpsys package pkg \| grep -E 'versionName\|versionCode\|granted=true'` | Version and permissions |
| `uninstall [-k] pkg` | `-k` keeps data |

## Inspecting state (`dumpsys`)

| Query | Command |
|---|---|
| Focused window ✓ | `dumpsys window \| grep -m1 mCurrentFocus` |
| Resumed activity ✓ | `dumpsys activity activities \| grep -m1 -E 'topResumedActivity\|ResumedActivity'` |
| Rotation ✓ | `dumpsys window \| grep -m1 -o 'mRotation=[^ }]*'` |
| Screen size and density ✓ | `wm size`, `wm density` |
| Memory of an app | `dumpsys meminfo pkg` |
| Device RAM ✓ | `dumpsys meminfo \| grep -E 'Total RAM\|Free RAM'` |
| Battery ✓ | `dumpsys battery` |
| Notifications ✓ | `dumpsys notification --noredact \| grep -E 'pkg=\|android.title'` |
| Keyboard shown? ✓ | `dumpsys input_method \| grep -m1 mInputShown` |

## Settings

| Setting | Command |
|---|---|
| Animations off/on ✓ | `settings put global {window,transition}_animation_scale 0\|1`, `settings put global animator_duration_scale 0\|1` |
| Stay awake ✓ | `svc power stayon true\|false` |
| Dark mode ✓ | `cmd uimode night yes\|no` |
| Rotation lock ✓ | `settings put system accelerometer_rotation 0` + `settings put system user_rotation 0-3` |
| Screen timeout | `settings put system screen_off_timeout 600000` (ms) |
| Font scale | `settings put system font_scale 1.3` |
| Per-app locale | `cmd locale set-app-locales pkg --locales de-DE` (there's no system-wide shell command on API 36; use the Settings UI) |
| Wi-Fi / mobile data ✓ | `svc wifi enable\|disable`, `svc data enable\|disable` |
| Airplane mode ✓ | `cmd connectivity airplane-mode enable\|disable` |
| Clipboard ✓ | No `cmd clipboard` shell implementation on API 36. Type text with `emu-type.sh` instead |

## Emulator console (`adb emu …`, loopback 127.0.0.1:5554)

| Command | Effect |
|---|---|
| `emu avd name` ✓ | → `agent36` |
| `emu geo fix <lon> <lat> [alt]` ✓ | Set GPS (longitude first!) |
| `emu network speed gsm\|edge\|umts\|lte\|full` ✓ | Bandwidth |
| `emu network delay none\|gprs\|umts` ✓ | Latency |
| `emu power capacity N` / `emu power ac off` ✓ | Battery |
| `emu sms send 5551234 "hello"` | Incoming SMS |
| `emu gsm call 5551234` / `emu gsm cancel 5551234` | Incoming call |
| `emu rotate` | Rotate 90° |
| `emu kill` | Hard stop. Prefer `~/emulator-stop.sh` |

## Capture

| Command | Notes |
|---|---|
| `exec-out screencap -p > s.png` ✓ | Use `exec-out`, not `shell` (avoids CRLF corruption). Or `emu-screenshot.sh` |
| `shell screenrecord --time-limit 15 /sdcard/r.mp4` then `pull` ✓ | Video, max 180 s |
| `exec-out uiautomator dump /dev/tty` | Unreliable; use `emu-ui-dump.sh` (dumps to /sdcard, cats it back) |

## uiautomator XML attributes useful for matching

`text`, `content-desc`, `resource-id` (`pkg:id/name`), `class`, `clickable`, `enabled`,
`focused`, `checked`, `selected`, `scrollable`, `bounds="[x1,y1][x2,y2]"`.
Tap centre = ((x1+x2)/2, (y1+y2)/2). If a label isn't clickable itself, tapping its centre
usually hits the clickable parent row. `emu-tap-text.sh` prefers clickable matches.

## Paths

| Path | What |
|---|---|
| `~/Android/Sdk` | SDK: platform-tools, emulator, build-tools 34/35/36, cmdline-tools, system-images/android-36 |
| `~/.android/avd/agent36.avd` | AVD data. **Do not delete** |
| `~/.android/adbkey*` | adb auth keys. **Do not delete** |
| `~/.config/systemd/user/android-*.service` | Service units. Don't edit |
| `~/emulator-{start,stop,restart,status}.sh` | Lifecycle scripts |
| `~/emulator-access.txt` | noVNC URL and password (600). Don't print it |
