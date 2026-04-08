---
name: android-sec
description: "Android security testing — full app analysis, static+dynamic, anti-tamper mapping, bypass development, Xposed module creation. Use when: android security, app bypass, root bypass, anti-tamper, xposed module, banking app, security SDK."
argument-hint: "[action: analyze/bypass/test] [target package name]"
---

# /android-sec — Android Security Testing

> Full-stack Android security analysis. Static + Dynamic + Bypass + Deploy.
> FRIDA FIRST — always map before writing code. Session eb966f16 lesson: 12hrs wasted on guesswork.

---

## STEP 0 — Target Reconnaissance

```bash
# 1. Pull APK from device
adb -s <device-id> shell pm path <package.name>
adb -s <device-id> pull <apk-path> target.apk

# 2. Get app info
adb -s <device-id> shell dumpsys package <package.name> | grep -E "versionName|versionCode|targetSdk|flags"

# 3. Check if app is running
adb -s <device-id> shell ps -A | grep <package.name>

# 4. Check for native libraries
unzip -l target.apk | grep '\.so$'
```

---

## Phase 1 — Static Analysis

### APK Decompilation

```bash
# jadx — primary decompiler (Java/Kotlin source)
jadx -d output_dir target.apk --deobf

# apktool — resource extraction + smali
apktool d target.apk -o apktool_output

# Key directories to examine:
# output_dir/sources/ — decompiled Java
# apktool_output/smali/ — Dalvik bytecode
# apktool_output/lib/ — native libraries
# apktool_output/res/ — resources
# apktool_output/AndroidManifest.xml — permissions, components
```

### What to Look For

| Target | Where | Grep Pattern |
|--------|-------|-------------|
| Security classes | `sources/` | `isRooted`, `detectRoot`, `checkIntegrity`, `SecurityCheck` |
| Obfuscated guards | `sources/` | Single-letter classes with `System.exit`, `Process.kill` |
| JNI security | `sources/` | `native `, `System.loadLibrary`, `JNI_OnLoad` |
| Certificate pinning | `sources/` | `CertificatePinner`, `TrustManager`, `X509`, `ssl` |
| SDK artifacts | `lib/arm64-v8a/` | `libmgsec.so`, `libshield.so`, `libapp_protect.so` |
| Debug detection | `sources/` | `isDebuggerConnected`, `TracerPid`, `Debug.` |
| Emulator detection | `sources/` | `Build.FINGERPRINT`, `ro.hardware`, `goldfish`, `generic` |

### Native Library Analysis

```bash
# List exports from security .so
readelf -sW lib/arm64-v8a/libsecurity.so | grep -E "FUNC.*GLOBAL"

# Find suspicious strings
strings lib/arm64-v8a/libsecurity.so | grep -iE "root|frida|xposed|magisk|su|hook|tamper|debug"

# Check JNI functions
nm -D lib/arm64-v8a/libsecurity.so | grep -i "Java_"
```

---

## Phase 2 — Dynamic Analysis (FRIDA FIRST)

### Kill Chain Mapping

Use the multi-layer mapping script from `/frida` skill. Run it FIRST before any bypass attempt.

```bash
# Start frida-server
adb -s <device-id> shell "su -c '/data/local/tmp/frida-server &'"

# Attach with kill chain mapper
frida -D <device-id> -n <process-name> -l kill-chain-mapper.js

# Or spawn if you need early hooks
frida -D <device-id> -f <package.name> -l kill-chain-mapper.js
```

### Logcat Analysis

```bash
# Filter for security-related logs
adb -s <device-id> logcat -s "SecurityCheck:*" "RootDetect:*" "IntegrityCheck:*"

# Broad security filter
adb -s <device-id> logcat | grep -iE "root|tamper|integrity|security|detect|hook|frida|xposed"

# Crash analysis
adb -s <device-id> logcat -b crash
```

### Strace (Native Level)

```bash
# Trace syscalls for security checks (run as root)
adb -s <device-id> shell "su -c 'strace -f -e trace=openat,access,stat -p $(pidof <package.name>)'" 2>&1 | grep -iE "su|magisk|xposed|frida"
```

---

## Phase 3 — Anti-Tamper Identification

### Classification Table

| Layer | Detection | Trigger | Kill Method | Priority |
|-------|-----------|---------|-------------|----------|
| 1 | Root binaries | File.exists(/su) | System.exit | HIGH |
| 2 | Magisk packages | PackageManager query | finish() | HIGH |
| 3 | Hook framework | /proc/maps scan | abort() | CRITICAL |
| 4 | SSL pinning | Certificate mismatch | IOException | MEDIUM |
| 5 | Debug detection | TracerPid != 0 | tgkill | HIGH |
| 6 | Integrity check | DEX CRC mismatch | native exit | CRITICAL |
| 7 | Emulator check | Build props | Block features | LOW |
| 8 | Native tampering | .so hash check | JNI abort | CRITICAL |

Fill this table for EVERY target app using Frida mapping results. Order by kill priority.

---

## Phase 4 — Xposed Module Development

### Lazy Hook Pattern (MANDATORY)

```kotlin
class TargetModule : IXposedHookLoadPackage {
    override fun handleLoadPackage(lpparam: XC_LoadPackage.LoadPackageParam) {
        if (lpparam.packageName != "target.package.name") return

        // NEVER hook obfuscated classes directly here — they need Context
        // ALWAYS defer to Application.onCreate
        XposedHelpers.findAndHookMethod(
            "android.app.Application",
            lpparam.classLoader,
            "onCreate",
            object : XC_MethodHook() {
                override fun afterHookedMethod(param: MethodHookParam) {
                    val app = param.thisObject as Application
                    val cl = app.classLoader

                    // NOW it's safe to load obfuscated classes — Context is ready
                    hookRootDetection(cl)
                    hookIntegrityCheck(cl)
                    hookDebugDetection(cl)
                    hookSSLPinning(cl)

                    XposedBridge.log("[TargetModule] All hooks installed after onCreate")
                }
            }
        )
    }

    private fun hookRootDetection(cl: ClassLoader) {
        try {
            val securityClass = XposedHelpers.findClassIfExists("com.target.SecurityManager", cl)
                ?: return

            XposedHelpers.findAndHookMethod(securityClass, "isRooted",
                object : XC_MethodHook() {
                    override fun beforeHookedMethod(param: MethodHookParam) {
                        param.result = false
                        XposedBridge.log("[TargetModule] isRooted -> false")
                    }
                })
        } catch (e: Exception) {
            XposedBridge.log("[TargetModule] hookRootDetection failed: ${e.message}")
        }
    }

    private fun hookIntegrityCheck(cl: ClassLoader) {
        try {
            val integrityClass = XposedHelpers.findClassIfExists("com.target.IntegrityChecker", cl)
                ?: return

            XposedHelpers.findAndHookMethod(integrityClass, "verifySignature",
                Context::class.java,
                object : XC_MethodHook() {
                    override fun beforeHookedMethod(param: MethodHookParam) {
                        param.result = true
                        XposedBridge.log("[TargetModule] verifySignature -> true")
                    }
                })
        } catch (e: Exception) {
            XposedBridge.log("[TargetModule] hookIntegrityCheck failed: ${e.message}")
        }
    }

    private fun hookDebugDetection(cl: ClassLoader) {
        try {
            XposedHelpers.findAndHookMethod("android.os.Debug", cl, "isDebuggerConnected",
                object : XC_MethodHook() {
                    override fun beforeHookedMethod(param: MethodHookParam) {
                        param.result = false
                    }
                })
        } catch (e: Exception) {
            XposedBridge.log("[TargetModule] hookDebugDetection failed: ${e.message}")
        }
    }

    private fun hookSSLPinning(cl: ClassLoader) {
        try {
            val pinnerClass = XposedHelpers.findClassIfExists("okhttp3.CertificatePinner", cl)
                ?: return

            XposedHelpers.findAndHookMethod(pinnerClass, "check",
                String::class.java, java.util.List::class.java,
                object : XC_MethodHook() {
                    override fun beforeHookedMethod(param: MethodHookParam) {
                        param.result = null // void return — skip check
                        XposedBridge.log("[TargetModule] SSL pin bypassed: ${param.args[0]}")
                    }
                })
        } catch (e: Exception) {
            XposedBridge.log("[TargetModule] hookSSLPinning failed: ${e.message}")
        }
    }
}
```

---

## Phase 5 — Deploy & Verify Protocol

```bash
# 1. Build module APK (from Android Studio or command line)
./gradlew assembleRelease

# 2. Get hash of built APK
sha256sum app/build/outputs/apk/release/app-release.apk

# 3. Push to device
adb -s <device-id> install -r app/build/outputs/apk/release/app-release.apk

# 4. Verify hash matches on device
adb -s <device-id> shell "sha256sum $(pm path <module.package> | cut -d: -f2)"

# 5. Enable module in LSPosed/EdXposed manager
# (usually requires UI interaction or adb shell command)

# 6. Reboot
adb -s <device-id> reboot
adb -s <device-id> wait-for-device

# 7. Verify module loads
adb -s <device-id> logcat -s "LSPosed:*" "EdXposed:*" "Xposed:*" | head -20

# 8. Verify hooks fire
adb -s <device-id> logcat | grep "\[TargetModule\]"

# 9. Open target app and verify it runs
adb -s <device-id> shell am start -n <package.name>/<main.activity>
```

---

## Known Security SDK Bypass Approaches

| SDK | Detection Focus | Bypass Strategy |
|-----|----------------|-----------------|
| **MGS (Meituan)** | Root + hook + Frida + emulator | Hook `libmgsec.so` JNI calls, patch native return values |
| **Arxan** | Code integrity + debug + tamper | Intercept integrity check functions in JNI_OnLoad, force returns |
| **DexGuard** | String + class encryption + root | Let decryption run, then hook decrypted classes post-init |
| **Promon SHIELD** | Thread-based monitoring + native | Kill monitoring threads, hook `pthread_create` to filter |
| **Bangcle/SecNeo** | Packed DEX + integrity | Wait for unpack, hook after ClassLoader switch |

---

## Iron Rules

1. **FRIDA FIRST** — map all layers before writing a single line of bypass code
2. **ONE module per app** — never split bypass across multiple modules
3. **Lazy hooks ALWAYS** — defer to Application.onCreate, never hook in handleLoadPackage directly
4. **Verify binary hash** — sha256sum on device MUST match build output
5. **Logcat confirms** — if logs don't show hooks firing, the module is NOT working
6. **Kill chain order** — bypass the layer that fires FIRST, then work outward
7. **Static THEN dynamic** — jadx first gives you class names for targeted Frida hooks
