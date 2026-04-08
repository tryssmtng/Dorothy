# Frida Instrumentation — Procedural Memory

> Frida setup aur usage ke rules. Cross-project applicable.

## Setup
- **Mac:** `pip install frida-tools` (v17.6.2)
- **Android:** Push `frida-server-17.6.2-android-arm64` to `/data/local/tmp/`, chmod 755, run as root
- **Connect:** `-D <adb-device-id>` (NOT `-H` — frida-server loopback only)

## Spawn vs Attach
- **Spawn:** `frida -D <device> -f <pkg> -l script.js` — changes linker namespace (app .so may fail)
- **Attach:** `frida -D <device> -n <process> -l script.js` — timing-critical
- **Key limitation:** Spawn mode breaks `System.loadLibrary()` for app .so files
- When to use: Spawn for early hooks (before app init). Attach for runtime hooks (after app running).

## Flutter Apps (BoringSSL)
- Flutter strips symbols → `dlsym()` returns NULL for `ssl_crypto_x509_session_verify_cert_chain`
- Need **memory pattern scan** approach (like rawan.js) — not dlsym
- Java SSL hooks DON'T work for Flutter (Dart uses BoringSSL directly)

## Common Patterns
- SSL pinning bypass: Hook `X509TrustManager.checkServerTrusted` → empty implementation
- Root detection: Hook `java.io.File.exists` for su paths → return false
- Method tracing: `Java.enumerateLoadedClasses` → find target → hook methods

## Gotchas
- Frida port (27042) can be detected by apps → use non-default port
- Some apps check `/proc/self/maps` for frida — need frida-gadget approach
- USB connection detected via `/sys/class/android_usb/` — ADB over WiFi safer
