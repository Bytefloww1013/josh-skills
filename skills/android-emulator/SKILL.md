---
name: android-emulator
description: Drive the headless Android 16 (API 36) emulator on homelab through adb. Use it to start, stop or check the emulator; take screenshots; read the UI hierarchy; tap, swipe or type; install, launch or debug apps (logcat, crashes); change device settings, deep links, rotation, GPS or network; or build an Android project and run it on the emulator. Use it whenever a task mentions the Android emulator, AVD agent36, adb, emulator-5554, or testing an app on Android on this server.
---

# Android emulator on homelab

You run on homelab as user `josh` with a local shell. The emulator is a regular
`systemd --user` stack. You control it with `adb`. A human can watch it in a browser
through noVNC.

| Item | Value |
|---|---|
| AVD | `agent36`: Pixel 6 profile, Android 16 / API 36, `google_apis/x86_64`, 4 GB guest RAM, KVM, SwiftShader GPU |
| SDK | `ANDROID_HOME=~/Android/Sdk` (adb: `~/Android/Sdk/platform-tools/adb`) |
| adb serial | `emulator-5554` (console 127.0.0.1:5554, adb 127.0.0.1:5555, all loopback) |
| Display | Xvfb `:99`, x11vnc on 127.0.0.1:5900 |
| Human view | http://100.123.49.43:6080/vnc.html?autoconnect=true (Tailscale only) |
| VNC password | stored in `~/emulator-access.txt` (mode 600). **Never print, log, or paste it.** To share access, give the file *path* |
| Services | `android-xvfb` → `android-emulator` → `android-x11vnc` → `android-novnc` (`systemctl --user`) |

Helper scripts live in `~/skills/android-emulator/scripts/` (below `S=~/skills/android-emulator/scripts`).
They all read `ADB_SERIAL` (default `emulator-5554`) and `ANDROID_HOME` (default `~/Android/Sdk`),
print `--help`, and exit non-zero with a clear message on failure.
For longer command tables see [reference.md](reference.md).

## 1. Lifecycle

```bash
~/emulator-status.sh     # service states + "Android booted: 1|no"
~/emulator-start.sh      # starts all 4 services, waits up to 3 min for boot (≈30 s warm)
~/emulator-stop.sh       # stops everything (adb emu kill)
~/emulator-restart.sh    # stop + start
```

- The emulator is **off by default** to save RAM. If it was off when you started, run
  `~/emulator-stop.sh` when you finish.
- `stop` may log a qemu core dump or "failed" state in the journal. That is harmless:
  the script runs `reset-failed` afterwards.
- `-no-snapshot` is set, so every start is a cold boot. Apps and data on `/data` persist across restarts.

## 2. Readiness

Always wait before acting. This also covers the moment right after start:

```bash
$S/emu-wait-ready.sh [timeout=180]   # online + sys.boot_completed=1 + package manager up, then wakes & unlocks
```

The manual equivalent:

```bash
adb -s emulator-5554 wait-for-device
until [ "$(adb -s emulator-5554 shell getprop sys.boot_completed | tr -d '\r')" = 1 ]; do sleep 2; done
```

## 3. The observe → act → verify loop

Never tap blind. Every step follows the same three moves:

1. **Observe.** Run `$S/emu-ui-list.sh` to list visible elements with their centre coordinates, text,
   description, resource-id and whether they are clickable. If you can read images, also run
   `$S/emu-screenshot.sh /tmp/s.png` and look at the PNG.
2. **Act.** Tap by meaning, not by pixel: `$S/emu-tap-text.sh "Wi-Fi"`. Fall back to raw coordinates
   from the list (`adb shell input tap X Y`) only when the element has no text, description or id.
3. **Verify.** Observe again and confirm the expected screen or text appeared before the next step.
   Use `--wait N` on tap-text for screens that load slowly.

Before long UI sessions, turn animations off. They make uiautomator flaky and screenshots blurry:

```bash
for k in window_animation_scale transition_animation_scale animator_duration_scale; do
  adb shell settings put global $k 0; done        # restore with 1 when done
```

### Scripts

| Script | Purpose |
|---|---|
| `emu-wait-ready.sh [secs]` | Block until the device is fully usable |
| `emu-screenshot.sh [out.png]` | PNG via `exec-out screencap -p`, validated, prints the path (default `/tmp/emu-screenshot-<ts>.png`) |
| `emu-ui-dump.sh [out.xml\|-]` | uiautomator XML (retries "could not get idle state"); `-` writes to stdout |
| `emu-ui-list.sh [--all] [file.xml]` | Compact element list: `cx,cy text= desc= id= Class clickable` |
| `emu-tap-text.sh "Q" [--exact] [--index N] [--wait S] [--dry-run]` | Find an element and tap its bounds centre. Match order: exact text → exact content-desc → resource-id (full or short, e.g. `search_bar_title`) → case-insensitive substring. Exit 1 if not found, listing the visible labels |
| `emu-type.sh "text" [--clear] [--enter]` | Types into the **focused** field. Escapes spaces and every shell metacharacter (`' " & ( ) $ ; \| * < > \` ~ # % ! ? \\ @`), chunks long strings. ASCII only |
| `emu-key.sh KEY [KEY…]` | Key events. `KEYCODE_` prefix optional: `HOME BACK ENTER APP_SWITCH DEL TAB WAKEUP POWER MENU` |
| `emu-launch.sh <pkg> [activity] [--restart]` | Resolve the launcher activity, `am start -W`, wait for focus. Exit 3 = launched but another window has focus |
| `emu-logcat.sh <pkg> [lines] [--level W] [--follow]` | Logs for the app's pid, plus the app's entries in the crash buffer |

Example: open Settings, search, and verify the result:

```bash
$S/emu-launch.sh com.android.settings --restart
$S/emu-tap-text.sh "Search settings" --wait 5     # opens the search field (it gains focus)
$S/emu-type.sh "dark theme" --enter
$S/emu-ui-list.sh | grep -i "dark theme"          # verify
```

### Raw input (when there's nothing to match on)

```bash
adb shell input tap 540 1200
adb shell input swipe 540 1800 540 600 300        # scroll down (x1 y1 x2 y2 ms)
adb shell input swipe 500 500 500 500 800          # long-press
adb shell input keyevent KEYCODE_APP_SWITCH        # recents
```

The screen is 1080×2400 in portrait. The XML bounds `[x1,y1][x2,y2]` use the same pixels.

## 4. Apps

```bash
adb shell pm list packages -3                     # user-installed (drop -3 for all)
adb install -r -g app.apk                         # -r replace/keep data, -g grant runtime perms
$S/emu-launch.sh com.example.app                  # or: adb shell am start -W -n com.example.app/.MainActivity
adb shell monkey -p com.example.app -c android.intent.category.LAUNCHER 1   # launch without knowing the activity
adb shell am force-stop com.example.app
adb shell pm clear com.example.app                # wipe THIS app's data
adb uninstall com.example.app
adb shell pm grant  com.example.app android.permission.ACCESS_FINE_LOCATION
adb shell pm revoke com.example.app android.permission.ACCESS_FINE_LOCATION
adb shell dumpsys window | grep -m1 mCurrentFocus  # what's in front right now
```

Deep links and intents:

```bash
adb shell am start -W -a android.intent.action.VIEW -d "https://example.com"
adb shell am start -W -a android.intent.action.VIEW -d "myapp://route/42" com.example.app
```

On first launch Chrome shows FirstRunActivity. Dismiss it with tap-text (`"Use without an account"`, `"No thanks"`, …).

## 5. Logs and crashes

```bash
$S/emu-logcat.sh com.example.app 300 --level W    # app-only (by pid) + its crash-buffer entries
adb logcat -c                                     # clear before reproducing a bug
adb logcat -d -b crash                            # all Java/native crashes
adb logcat -d -s MyTag:D '*:S'                    # one tag
adb logcat -d --pid=$(adb shell pidof -s com.example.app) -t 200
adb shell dumpsys activity processes | grep -i anr  # ANRs; traces in /data/anr (root-only)
```

Always use `-d` (dump and exit) or a `timeout`. A bare `adb logcat` never returns.

## 6. Files, settings, device state

```bash
adb push local.txt /sdcard/Download/      ;  adb pull /sdcard/Download/x.txt ./
adb shell svc power stayon true                   # keep the screen on (restore with false)
adb shell cmd uimode night yes|no                 # dark mode
adb shell settings put system accelerometer_rotation 0
adb shell settings put system user_rotation 1     # 0 portrait, 1 landscape, 2, 3; then verify:
adb shell dumpsys window | grep -m1 -o 'mRotation=[^ }]*'   # note: the launcher stays portrait
adb emu geo fix -122.084 37.422                   # GPS (longitude FIRST, then latitude)
adb emu network speed gsm|edge|umts|lte|full ; adb emu network delay none|gprs|umts
adb shell svc wifi disable|enable ; adb shell svc data disable|enable   # offline testing
adb emu power capacity 15                         # battery level
```

`adb emu …` talks to the emulator console on 127.0.0.1:5554. The adb server authenticates it for you.

## 7. Build and install from source

Projects go under `~/Android/<project>` (the SDK is `~/Android/Sdk`, so don't build inside it).
The Gradle cache is `~/.gradle`.

```bash
cd ~/Android/MyApp
echo "sdk.dir=$HOME/Android/Sdk" > local.properties   # if missing
./gradlew assembleDebug --console=plain               # first build downloads deps; be patient
adb install -r -g app/build/outputs/apk/debug/app-debug.apk
# or: ./gradlew installDebug   (uses $ANDROID_SERIAL; export ANDROID_SERIAL=emulator-5554)
$S/emu-launch.sh com.example.myapp --restart && $S/emu-screenshot.sh
```

Gradle and the emulator compete for 15 GB RAM. If memory is tight, use
`./gradlew --no-daemon -Dorg.gradle.jvmargs=-Xmx2g`.

## 8. Optional: mobile-mcp (MCP route)

If your agent harness supports MCP, the stdio server `mobile-mcp` (tested: v1.0.8) wraps the same adb device.
It provides list-elements, tap, swipe, type, screenshot, launch/terminate/install, logs and crashes:

```json
{ "mcpServers": { "mobile-mcp": { "command": "npx", "args": ["-y", "@mobilenext/mobile-mcp@latest"],
  "env": { "ANDROID_HOME": "/home/josh/Android/Sdk" } } }
```

Pick `emulator-5554` from `mobile_list_available_devices`. The scripts above remain the fallback and need no network access.

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `device offline` / not in `adb devices` | `adb kill-server && adb start-server`, then `emu-wait-ready.sh`; still offline → `~/emulator-restart.sh` |
| `device unauthorized` | `adb kill-server` (re-reads `~/.android/adbkey`); if it persists, restart the emulator. Never delete `~/.android/adbkey*` |
| Emulator won't boot / service flapping | `journalctl --user -u android-emulator -n 80 --no-pager`; `~/emulator-status.sh` |
| `/dev/kvm` permission denied | `ls -l /dev/kvm` and `id` must show the `kvm` group. If `id` has it but the service doesn't, the user manager is stale: a human must restart `user@1000` (don't do it yourself mid-task) |
| noVNC shows a black screen | Display asleep: `adb shell input keyevent KEYCODE_WAKEUP`; else `systemctl --user restart android-x11vnc` (view-only service; Android keeps running) |
| noVNC page unreachable | `systemctl --user status android-novnc`. It binds only to the Tailscale IP, so check `tailscale status` |
| `could not get idle state` (uiautomator) | Animations or a live wallpaper are busy. Disable animations (§3); `emu-ui-dump.sh` already retries |
| `emu-tap-text.sh` not found but it's visible in the screenshot | Element drawn in a WebView/Canvas without accessibility text. Use coordinates from the screenshot, or `--wait` if still loading |
| Typing goes nowhere | No field has focus (e.g. after ENTER submitted). Tap the field first, then `emu-type.sh` |
| Low memory / host swapping | `free -h`. The emulator uses ≈4–5 GB. Stop it when idle, use `--no-daemon` for Gradle, and don't start a second AVD |
| Slow or janky UI | SwiftShader is software rendering. Prefer UI-dump-driven steps over timing-based waits |

## 10. Safety rules

- **Never** wipe or recreate the AVD (`-wipe-data`, deleting `~/.android/avd`, `avdmanager delete`)
  or delete SDK packages. Uninstall or clear only apps your task installed or owns.
- **Never** expose adb, the emulator console or gRPC beyond localhost. That means no `adb tcpip`,
  no `-grpc`, no `adb -a`, and no port forwarding to 0.0.0.0. Don't edit the systemd unit files.
- Don't touch other services, Docker containers, Tailscale, webmin or 9router on this host.
  The emulator stack is the only thing this skill controls.
- Keep resources bounded: one emulator only (≈5 GB RAM total). Stop it when you're done
  if it was off when you began.
- Never print the VNC password or other secrets (`~/emulator-access.txt`, `~/.vnc/passwd`).
- Restore global settings you changed (animations, stay-awake, dark mode, rotation) when finished,
  unless the task says otherwise.
