# Android Device Testing — Procedural Memory

> Ye procedures Malik ne ek baar bataye hain. KABHI mat bhoolna. Har Android session mein apply karo.

## ADB & Device Interaction
- **UI interaction = UI dump se EXACT coordinates.** `adb shell uiautomator dump` → parse XML → extract bounds → calculate tap coordinates. NEVER guess coordinates.
- **Screenshot verify:** Har important action ke baad `adb shell screencap` le ke verify karo.
- **Device connect:** `adb devices` se pehle check karo. WiFi ADB = `adb connect <ip>:5555`.

## APK Install & Hooks
- **REBOOT MANDATORY after APK install** jab native hooks (Xposed/LSPosed) hain. Bina reboot ke naye hooks LOAD NAHI HOTE. Ye Zygote fork pe depend karta hai.
- Install sequence: `adb install -r app.apk` → `adb reboot` → wait for boot → verify hooks loaded.
- **Force-stop se hooks reload NAHI hote** — sirf reboot se hote hain (Xposed hooks Zygote pe load hote hain).

## Testing Workflow
1. Build APK locally (or panel se download)
2. `adb install -r <apk>`
3. `adb reboot` (MANDATORY for hook changes)
4. Wait for device boot complete
5. Open target app → check logcat for hook logs
6. Verify via `adb logcat | grep "Cloak"` or app's log viewer

## Logcat
- Filter: `adb logcat -s "TAG"` for specific tags
- Save: `adb logcat > /tmp/logcat.txt`
- Clear: `adb logcat -c` before test run

## SharedPreferences
- Read: `adb shell cat /data/data/<pkg>/shared_prefs/<file>.xml`
- **Heredoc escaping strips quotes** → XML invalid. ALWAYS `cat` verify after write.

## Device Issues
- Phone stuck → hard reboot (power 10-15 sec hold)
- OEM battery optimization kills sockets → need constant network traffic
- ADB offline → `adb kill-server && adb start-server`
