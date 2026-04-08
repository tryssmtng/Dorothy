# Xposed Module Development — Procedural Memory

> Xposed hooks REGULAR Java se ALAG hain. In rules ko KABHI mat bhoolna.

## Hook Semantics (CRITICAL)
- `param.result = null` for void methods = **INTENTIONAL.** Ye "skip this method" matlab hai. Fix mat karo.
- `param.result = param.args[0]` for verifyChain = **STANDARD PATTERN.** JustTrustMe, TrustMeAlready, SSLUnpinning — sab yehi karte hain.
- `beforeHookedMethod` with `param.result = X` = "skip original, return X"
- `afterHookedMethod` with `param.result = X` = "override return value"
- Hooks fire in **LIFO order** — last loaded hook fires FIRST.

## Working Code = SACRED
- **THEORETICAL bugs fix mat karo.** Sirf PROVEN bugs fix karo (device pe crash hua, error log mein dikha).
- "Code review mein bug dikha" = HYPOTHESIS, not fact. **Reproduce karo pehle.**
- Static analysis ALONE se Xposed code mein "bug" bolna ALLOWED NAHI. Calling code grep karo, 3 open-source implementations check karo.

## SSL Bypass Patterns
- OkHttp `check()` — return value caller use NAHI karta. null return = SAFE.
- TrustManagerImpl `verifyChain` — Android internals mein loose type contract. `param.args[0]` return = SAFE.
- Before changing ANY SSL hook → check JustTrustMe source, TrustMeAlready source, SSLUnpinning source.

## Module Loading
- Modules Zygote fork pe load hote hain → **REBOOT chahiye** new hooks ke liye.
- `force-stop` se hooks reload NAHI hote.
- Module loading silent crash → CrashGuard/NativeHide ke baad check karo.
- LIFO ordering conflicts: 2 modules same method hook karein → later-loaded fires FIRST.

## Detection Bypass Rules
- BugsMirror `Defender.nEnable()` = **NEVER HOOK.** Native init method — hook karne se app crash.
- DetectionLibHide DEXSCAN se BugsMirror exclude karo (PATTERN_EXCLUDE_PREFIXES).
- ExitBlocker window = check ki target app ka detection KITNE seconds baad trigger hota hai.

## Build & Test
- Build: project root se `./gradlew assembleDebug` or panel se APK download
- Install: `adb install -r app.apk` → `adb reboot` → verify
- Logs: `adb logcat -s "Cloak-*"` for all Cloak module logs
- Hook verification: check `hook_status.json` for module count
