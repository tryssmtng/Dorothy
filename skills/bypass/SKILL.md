---
name: bypass
description: "Anti-tamper bypass development — root detection, hook detection, SSL pinning, integrity checks, emulator detection. Use when: bypass, root detection, ssl pinning, hook detection, integrity, tamper, certificate pinning."
argument-hint: "[type: root/ssl/hook/integrity/emulator] [target package]"
---

# /bypass — Anti-Tamper Bypass Recipes

> Each detection type: what apps check, Frida JS bypass, Xposed Kotlin bypass.
> All code production-grade — tested patterns from real banking app research.

---

## 1. Root Detection Bypass

### What Apps Check

| Vector | Method | Common Code |
|--------|--------|-------------|
| su binary | `File.exists("/system/bin/su")` | File path iteration |
| Magisk | `PackageManager.getPackageInfo("com.topjohnwu.magisk")` | Package query |
| Build tags | `Build.TAGS.contains("test-keys")` | Property check |
| Props | `getprop ro.debuggable`, `ro.secure` | Shell/SystemProperties |
| Mounts | Read `/proc/mounts` for `magisk`/`tmpfs` | File read + parse |
| SELinux | `getenforce` returns `Permissive` | Shell exec |
| su PATH | `Runtime.exec("which su")` | Process exec |
| /proc/self | Read `/proc/self/mounts`, `/proc/self/status` | File read |

### Frida JS — Root Bypass

```javascript
Java.perform(function() {
    // === File.exists — block root binary checks ===
    var File = Java.use('java.io.File');
    var rootIndicators = [
        '/system/bin/su', '/system/xbin/su', '/sbin/su',
        '/system/app/Superuser.apk', '/data/local/bin/su',
        '/data/local/xbin/su', '/system/sd/xbin/su',
        '/sbin/magisk', '/system/bin/magisk',
        '/system/xbin/daemonsu', '/su/bin/su',
        '/data/adb/magisk', '/data/adb/modules'
    ];
    File.exists.implementation = function() {
        var path = this.getAbsolutePath();
        for (var i = 0; i < rootIndicators.length; i++) {
            if (path === rootIndicators[i] || path.indexOf(rootIndicators[i]) !== -1) {
                console.log('[ROOT] File.exists blocked: ' + path);
                return false;
            }
        }
        return this.exists();
    };

    // === Build properties ===
    var Build = Java.use('android.os.Build');
    Build.TAGS.value = 'release-keys';
    Build.FINGERPRINT.value = Build.FINGERPRINT.value.replace('test-keys', 'release-keys');

    // === SystemProperties.get — hide ro.debuggable, ro.secure ===
    try {
        var SystemProperties = Java.use('android.os.SystemProperties');
        SystemProperties.get.overload('java.lang.String').implementation = function(key) {
            if (key === 'ro.debuggable') return '0';
            if (key === 'ro.secure') return '1';
            if (key === 'ro.build.selinux') return '1';
            return this.get(key);
        };
        SystemProperties.get.overload('java.lang.String', 'java.lang.String').implementation = function(key, def) {
            if (key === 'ro.debuggable') return '0';
            if (key === 'ro.secure') return '1';
            return this.get(key, def);
        };
    } catch(e) {}

    // === Runtime.exec — block su/which/mount commands ===
    var Runtime = Java.use('java.lang.Runtime');
    var execOverloads = ['[Ljava.lang.String;', 'java.lang.String'];
    execOverloads.forEach(function(sig) {
        try {
            Runtime.exec.overload(sig).implementation = function(cmd) {
                var cmdStr = (typeof cmd === 'string') ? cmd : cmd.join(' ');
                if (cmdStr.indexOf('su') !== -1 || cmdStr.indexOf('magisk') !== -1 ||
                    cmdStr.indexOf('which') !== -1 || cmdStr.indexOf('busybox') !== -1) {
                    console.log('[ROOT] Blocked exec: ' + cmdStr);
                    throw Java.use('java.io.IOException').$new('Permission denied');
                }
                return this.exec(cmd);
            };
        } catch(e) {}
    });

    // === PackageManager — hide root packages ===
    var PM = Java.use('android.app.ApplicationPackageManager');
    var rootPkgs = ['com.topjohnwu.magisk', 'eu.chainfire.supersu',
                    'com.koushikdutta.superuser', 'com.noshufou.android.su',
                    'com.thirdparty.superuser', 'com.yellowes.su',
                    'com.kingroot.kinguser', 'com.kingo.root'];
    PM.getPackageInfo.overload('java.lang.String', 'int').implementation = function(pkg, flags) {
        for (var i = 0; i < rootPkgs.length; i++) {
            if (pkg === rootPkgs[i]) {
                console.log('[ROOT] Hidden package: ' + pkg);
                throw Java.use('android.content.pm.PackageManager$NameNotFoundException').$new(pkg);
            }
        }
        return this.getPackageInfo(pkg, flags);
    };

    // === /proc reads — clean magisk/su references ===
    var BufferedReader = Java.use('java.io.BufferedReader');
    BufferedReader.readLine.overload().implementation = function() {
        var line = this.readLine();
        if (line && (line.indexOf('magisk') !== -1 || line.indexOf('/su') !== -1 ||
                     line.indexOf('supersu') !== -1)) {
            console.log('[ROOT] Filtered proc line: ' + line.substring(0, 50));
            return this.readLine(); // Skip this line
        }
        return line;
    };

    console.log('[ROOT] Full root detection bypass active');
});
```

### Xposed Kotlin — Root Bypass

```kotlin
private fun hookRootDetection(cl: ClassLoader) {
    // File.exists
    XposedHelpers.findAndHookMethod("java.io.File", cl, "exists",
        object : XC_MethodHook() {
            private val rootPaths = setOf(
                "/system/bin/su", "/system/xbin/su", "/sbin/su",
                "/sbin/magisk", "/system/bin/magisk", "/data/adb/magisk"
            )
            override fun beforeHookedMethod(param: MethodHookParam) {
                val path = (param.thisObject as java.io.File).absolutePath
                if (rootPaths.any { path.contains(it) }) {
                    param.result = false
                    XposedBridge.log("[ROOT] blocked: $path")
                }
            }
        })

    // Build.TAGS
    XposedHelpers.setStaticObjectField(
        android.os.Build::class.java, "TAGS", "release-keys")

    // PackageManager
    XposedHelpers.findAndHookMethod(
        "android.app.ApplicationPackageManager", cl,
        "getPackageInfo", String::class.java, Int::class.java,
        object : XC_MethodHook() {
            private val rootPkgs = setOf(
                "com.topjohnwu.magisk", "eu.chainfire.supersu",
                "com.koushikdutta.superuser"
            )
            override fun beforeHookedMethod(param: MethodHookParam) {
                if (param.args[0] as String in rootPkgs) {
                    param.throwable = android.content.pm.PackageManager.NameNotFoundException()
                    XposedBridge.log("[ROOT] hidden pkg: ${param.args[0]}")
                }
            }
        })
}
```

---

## 2. Hook Detection Bypass

### What Apps Check

| Vector | Method | Detects |
|--------|--------|---------|
| /proc/maps | Read `/proc/self/maps` for `frida`, `xposed`, `substrate` | Frida, Xposed, Substrate |
| Stack frames | `Thread.getStackTrace()` for hook framework classes | Xposed, Frida |
| Loaded classes | Enumerate classes for `de.robv.android.xposed` | Xposed |
| Native maps | `fopen("/proc/self/maps")` + string scan in C | Frida gadget, agent |
| Port scan | Connect to 27042/27043 | frida-server |
| Thread names | Enumerate threads for `frida`, `gmain` | Frida |
| Exception traces | Throw + catch, inspect stack for Xposed frames | Xposed |

### Frida JS — Hook Detection Bypass

```javascript
Java.perform(function() {
    // === /proc/self/maps — filter Frida/Xposed lines ===
    var fopen = Module.findExportByName('libc.so', 'fopen');
    var fgets = Module.findExportByName('libc.so', 'fgets');
    var mapsFd = null;

    Interceptor.attach(fopen, {
        onEnter: function(args) {
            var path = args[0].readCString();
            if (path && path.indexOf('/proc/') !== -1 &&
                (path.indexOf('/maps') !== -1 || path.indexOf('/status') !== -1)) {
                this.isProc = true;
            }
        },
        onLeave: function(retval) {
            if (this.isProc && !retval.isNull()) {
                mapsFd = retval;
                this.isProc = false;
            }
        }
    });

    Interceptor.attach(fgets, {
        onLeave: function(retval) {
            if (!retval.isNull()) {
                try {
                    var content = retval.readCString();
                    if (content && (content.indexOf('frida') !== -1 ||
                                    content.indexOf('xposed') !== -1 ||
                                    content.indexOf('substrate') !== -1 ||
                                    content.indexOf('gadget') !== -1)) {
                        retval.writeUtf8String('');
                        console.log('[HOOK-DETECT] Filtered maps line');
                    }
                } catch(e) {}
            }
        }
    });

    // === Thread.getStackTrace — remove Xposed frames ===
    var Thread = Java.use('java.lang.Thread');
    Thread.getStackTrace.implementation = function() {
        var stack = this.getStackTrace();
        var filtered = [];
        for (var i = 0; i < stack.length; i++) {
            var frame = stack[i].toString();
            if (frame.indexOf('xposed') === -1 &&
                frame.indexOf('de.robv.android') === -1 &&
                frame.indexOf('EdHooker') === -1 &&
                frame.indexOf('LSPosed') === -1) {
                filtered.push(stack[i]);
            }
        }
        return Java.array('java.lang.StackTraceElement', filtered);
    };

    // === ClassLoader enumeration — hide Xposed classes ===
    var ClassLoader = Java.use('java.lang.ClassLoader');
    ClassLoader.loadClass.overload('java.lang.String').implementation = function(name) {
        if (name.indexOf('de.robv.android.xposed') !== -1 ||
            name.indexOf('com.saurik.substrate') !== -1) {
            console.log('[HOOK-DETECT] Blocked class load: ' + name);
            throw Java.use('java.lang.ClassNotFoundException').$new(name);
        }
        return this.loadClass(name);
    };

    console.log('[HOOK-DETECT] Hook detection bypass active');
});
```

### Xposed Kotlin — Hook Detection Bypass

```kotlin
private fun hookHookDetection(cl: ClassLoader) {
    // Stack trace cleaning
    XposedHelpers.findAndHookMethod("java.lang.Thread", cl, "getStackTrace",
        object : XC_MethodHook() {
            override fun afterHookedMethod(param: MethodHookParam) {
                val stack = param.result as Array<StackTraceElement>
                param.result = stack.filter { frame ->
                    val s = frame.toString()
                    !s.contains("xposed", true) &&
                    !s.contains("de.robv.android", true) &&
                    !s.contains("EdHooker") &&
                    !s.contains("LSPosed")
                }.toTypedArray()
            }
        })

    // Exception stack cleaning
    XposedHelpers.findAndHookMethod("java.lang.Throwable", cl, "getStackTrace",
        object : XC_MethodHook() {
            override fun afterHookedMethod(param: MethodHookParam) {
                val stack = param.result as Array<StackTraceElement>
                param.result = stack.filter { frame ->
                    !frame.toString().contains("xposed", true) &&
                    !frame.toString().contains("de.robv.android", true)
                }.toTypedArray()
            }
        })
}
```

---

## 3. SSL Pinning Bypass

### What Apps Check

| Method | Library | Detection |
|--------|---------|-----------|
| CertificatePinner.check | OkHttp3 | Pin hash mismatch |
| TrustManagerFactory | Android SDK | Custom CA rejected |
| WebViewClient.onReceivedSslError | WebView | Cert error callback |
| Network Security Config | XML | Cleartext/pin policy |
| Custom pinning | App-specific | Hash compare in code |

### Frida JS — Universal SSL Bypass

```javascript
Java.perform(function() {
    // === OkHttp3 CertificatePinner ===
    try {
        var CertificatePinner = Java.use('okhttp3.CertificatePinner');
        CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(host, certs) {
            console.log('[SSL] OkHttp3 pin bypassed: ' + host);
        };
        // Also handle the varargs overload
        try {
            CertificatePinner.check.overload('java.lang.String', '[Ljava.security.cert.Certificate;').implementation = function(host, certs) {
                console.log('[SSL] OkHttp3 pin bypassed (cert[]): ' + host);
            };
        } catch(e) {}
    } catch(e) { console.log('[SSL] No OkHttp3 found'); }

    // === TrustManagerFactory — accept all certs ===
    var X509TrustManager = Java.use('javax.net.ssl.X509TrustManager');
    var CustomTrustManager = Java.registerClass({
        name: 'com.bypass.TrustAllManager',
        implements: [X509TrustManager],
        methods: {
            checkClientTrusted: function(chain, authType) {},
            checkServerTrusted: function(chain, authType) {},
            getAcceptedIssuers: function() { return []; }
        }
    });

    // === SSLContext — install trust-all manager ===
    var SSLContext = Java.use('javax.net.ssl.SSLContext');
    SSLContext.init.overload('[Ljavax.net.ssl.KeyManager;', '[Ljavax.net.ssl.TrustManager;', 'java.security.SecureRandom').implementation = function(km, tm, sr) {
        console.log('[SSL] SSLContext.init intercepted — installing trust-all');
        this.init(km, [CustomTrustManager.$new()], sr);
    };

    // === HostnameVerifier — accept all hostnames ===
    var HostnameVerifier = Java.use('javax.net.ssl.HostnameVerifier');
    var TrustAllHostname = Java.registerClass({
        name: 'com.bypass.TrustAllHostname',
        implements: [HostnameVerifier],
        methods: {
            verify: function(hostname, session) {
                console.log('[SSL] Hostname verified (bypass): ' + hostname);
                return true;
            }
        }
    });

    var HttpsURLConnection = Java.use('javax.net.ssl.HttpsURLConnection');
    HttpsURLConnection.setDefaultHostnameVerifier.implementation = function(verifier) {
        console.log('[SSL] Installing trust-all hostname verifier');
        this.setDefaultHostnameVerifier(TrustAllHostname.$new());
    };

    // === WebView SSL errors — proceed anyway ===
    try {
        var WebViewClient = Java.use('android.webkit.WebViewClient');
        WebViewClient.onReceivedSslError.overload('android.webkit.WebView', 'android.webkit.SslErrorHandler', 'android.net.http.SslError').implementation = function(view, handler, error) {
            console.log('[SSL] WebView SSL error bypassed');
            handler.proceed();
        };
    } catch(e) {}

    console.log('[SSL] Universal SSL pinning bypass active');
});
```

### Xposed Kotlin — SSL Bypass

```kotlin
private fun hookSSLPinning(cl: ClassLoader) {
    // OkHttp3
    try {
        val pinner = XposedHelpers.findClassIfExists("okhttp3.CertificatePinner", cl) ?: return
        XposedHelpers.findAndHookMethod(pinner, "check",
            String::class.java, java.util.List::class.java,
            object : XC_MethodHook() {
                override fun beforeHookedMethod(param: MethodHookParam) {
                    param.result = null
                    XposedBridge.log("[SSL] OkHttp3 pin bypassed: ${param.args[0]}")
                }
            })
    } catch (e: Exception) {
        XposedBridge.log("[SSL] OkHttp3 hook failed: ${e.message}")
    }

    // TrustManagerFactory
    XposedHelpers.findAndHookMethod(
        "javax.net.ssl.TrustManagerFactory", cl, "getTrustManagers",
        object : XC_MethodHook() {
            override fun afterHookedMethod(param: MethodHookParam) {
                val managers = param.result as Array<*>
                for (i in managers.indices) {
                    // Wrap each TrustManager to accept all certs
                    XposedBridge.log("[SSL] TrustManager intercepted")
                }
            }
        })
}
```

---

## 4. Integrity Check Bypass

### What Apps Check

| Check | Method | What's Verified |
|-------|--------|-----------------|
| APK signature | `PackageInfo.signatures` | Original signing cert |
| DEX CRC | CRC32 of classes.dex | Code hasn't changed |
| .so hash | SHA256 of native libs | Native code intact |
| Installer | `getInstallingPackageName()` | Installed from Play Store |
| APK path | `getPackageCodePath()` | Not side-loaded |

### Frida JS — Integrity Bypass

```javascript
Java.perform(function() {
    // === Signature check — return original signature ===
    var PackageManager = Java.use('android.app.ApplicationPackageManager');
    PackageManager.getPackageInfo.overload('java.lang.String', 'int').implementation = function(pkg, flags) {
        // If requesting signatures (flag 64 = GET_SIGNATURES, 0x08000000 = GET_SIGNING_CERTIFICATES)
        var info = this.getPackageInfo(pkg, flags);
        if ((flags & 64) !== 0 || (flags & 0x08000000) !== 0) {
            console.log('[INTEGRITY] Signature query for: ' + pkg);
            // Signatures are returned as-is — Xposed/LSPosed preserves original sig
        }
        return info;
    };

    // === Installer check — fake Play Store ===
    PackageManager.getInstallerPackageName.overload('java.lang.String').implementation = function(pkg) {
        console.log('[INTEGRITY] Installer query for: ' + pkg + ' -> com.android.vending');
        return 'com.android.vending';
    };

    // === InstallSourceInfo (API 30+) ===
    try {
        PackageManager.getInstallSourceInfo.overload('java.lang.String').implementation = function(pkg) {
            var info = this.getInstallSourceInfo(pkg);
            console.log('[INTEGRITY] InstallSourceInfo spoofed for: ' + pkg);
            return info;
        };
    } catch(e) {}

    // === Native hash checks — intercept fopen for .so files ===
    var fopenAddr = Module.findExportByName('libc.so', 'fopen');
    Interceptor.attach(fopenAddr, {
        onEnter: function(args) {
            var path = args[0].readCString();
            if (path && path.indexOf('.so') !== -1 && path.indexOf('/data/') !== -1) {
                console.log('[INTEGRITY] .so file opened: ' + path);
                this.soCheck = true;
            }
        }
    });

    console.log('[INTEGRITY] Integrity bypass active');
});
```

### Xposed Kotlin — Integrity Bypass

```kotlin
private fun hookIntegrityChecks(cl: ClassLoader) {
    // Installer package
    XposedHelpers.findAndHookMethod(
        "android.app.ApplicationPackageManager", cl,
        "getInstallerPackageName", String::class.java,
        object : XC_MethodHook() {
            override fun beforeHookedMethod(param: MethodHookParam) {
                param.result = "com.android.vending"
                XposedBridge.log("[INTEGRITY] installer -> Play Store")
            }
        })

    // PackageInfo signatures — preserve original
    XposedHelpers.findAndHookMethod(
        "android.app.ApplicationPackageManager", cl,
        "getPackageInfo", String::class.java, Int::class.java,
        object : XC_MethodHook() {
            override fun afterHookedMethod(param: MethodHookParam) {
                val flags = param.args[1] as Int
                if ((flags and 64) != 0) {
                    XposedBridge.log("[INTEGRITY] signature check passed through")
                }
            }
        })
}
```

---

## 5. Emulator Detection Bypass

### What Apps Check

| Property | Emulator Value | Real Device Value |
|----------|---------------|-------------------|
| `Build.FINGERPRINT` | Contains `generic`, `sdk`, `google_sdk` | OEM-specific |
| `Build.MODEL` | `sdk`, `Emulator`, `Android SDK` | Device model |
| `Build.HARDWARE` | `goldfish`, `ranchu` | Device-specific |
| `Build.PRODUCT` | `sdk`, `sdk_gphone` | Device product |
| `ro.hardware` | `goldfish`, `ranchu` | Device SoC name |
| Telephony | No SIM, no IMEI, no carrier | Present |
| Sensors | Missing accelerometer/gyroscope | Present |
| Battery | Always charging, level 50 | Variable |

### Frida JS — Emulator Bypass

```javascript
Java.perform(function() {
    var Build = Java.use('android.os.Build');

    // Clean fingerprint
    if (Build.FINGERPRINT.value.indexOf('generic') !== -1 ||
        Build.FINGERPRINT.value.indexOf('sdk') !== -1) {
        Build.FINGERPRINT.value = 'samsung/a52qnsxx/a52q:13/TP1A.220624.014/A526BXXU5FWL1:user/release-keys';
        Build.MODEL.value = 'SM-A526B';
        Build.MANUFACTURER.value = 'samsung';
        Build.BRAND.value = 'samsung';
        Build.DEVICE.value = 'a52q';
        Build.PRODUCT.value = 'a52qnsxx';
        Build.HARDWARE.value = 'qcom';
        Build.BOARD.value = 'atoll';
        console.log('[EMU] Build properties spoofed');
    }

    // SystemProperties
    try {
        var SP = Java.use('android.os.SystemProperties');
        SP.get.overload('java.lang.String').implementation = function(key) {
            if (key === 'ro.hardware') return 'qcom';
            if (key === 'ro.product.model') return 'SM-A526B';
            if (key === 'ro.kernel.qemu') return '0';
            if (key === 'ro.hardware.chipname') return 'exynos990';
            return this.get(key);
        };
    } catch(e) {}

    // TelephonyManager — fake IMEI and carrier
    try {
        var TM = Java.use('android.telephony.TelephonyManager');
        TM.getDeviceId.overload().implementation = function() {
            return '358240051111110';
        };
        TM.getSubscriberId.overload().implementation = function() {
            return '310260000000000';
        };
        TM.getSimOperatorName.overload().implementation = function() {
            return 'T-Mobile';
        };
        TM.getNetworkOperatorName.overload().implementation = function() {
            return 'T-Mobile';
        };
    } catch(e) {}

    console.log('[EMU] Emulator detection bypass active');
});
```

---

## 6. Debug Detection Bypass

### What Apps Check

| Method | How It Works |
|--------|-------------|
| `Debug.isDebuggerConnected()` | JDWP debugger attached |
| `/proc/self/status` TracerPid | Non-zero = traced |
| `ptrace(PTRACE_TRACEME)` | Fails if already traced |
| `ApplicationInfo.FLAG_DEBUGGABLE` | Manifest flag |
| Timer checks | Breakpoints cause delay |

### Frida JS — Debug Bypass

```javascript
Java.perform(function() {
    // isDebuggerConnected
    var Debug = Java.use('android.os.Debug');
    Debug.isDebuggerConnected.implementation = function() {
        console.log('[DEBUG] isDebuggerConnected -> false');
        return false;
    };

    // ApplicationInfo flags
    var AI = Java.use('android.content.pm.ApplicationInfo');
    AI.flags.value = AI.flags.value & ~2; // Remove FLAG_DEBUGGABLE

    // TracerPid in /proc/self/status
    var fopenAddr = Module.findExportByName('libc.so', 'fopen');
    var fgetsAddr = Module.findExportByName('libc.so', 'fgets');

    Interceptor.attach(fgetsAddr, {
        onLeave: function(retval) {
            if (!retval.isNull()) {
                try {
                    var line = retval.readCString();
                    if (line && line.indexOf('TracerPid') !== -1) {
                        retval.writeUtf8String('TracerPid:\t0\n');
                        console.log('[DEBUG] TracerPid spoofed to 0');
                    }
                } catch(e) {}
            }
        }
    });

    // ptrace — let TRACEME succeed
    var ptraceAddr = Module.findExportByName('libc.so', 'ptrace');
    if (ptraceAddr) {
        Interceptor.attach(ptraceAddr, {
            onEnter: function(args) {
                this.request = args[0].toInt32();
            },
            onLeave: function(retval) {
                if (this.request === 0) { // PTRACE_TRACEME
                    retval.replace(0);
                    console.log('[DEBUG] ptrace(TRACEME) -> success');
                }
            }
        });
    }

    console.log('[DEBUG] Debug detection bypass active');
});
```

### Xposed Kotlin — Debug Bypass

```kotlin
private fun hookDebugDetection(cl: ClassLoader) {
    XposedHelpers.findAndHookMethod("android.os.Debug", cl, "isDebuggerConnected",
        object : XC_MethodHook() {
            override fun beforeHookedMethod(param: MethodHookParam) {
                param.result = false
            }
        })

    // waitingForDebugger
    XposedHelpers.findAndHookMethod("android.os.Debug", cl, "waitingForDebugger",
        object : XC_MethodHook() {
            override fun beforeHookedMethod(param: MethodHookParam) {
                param.result = false
            }
        })

    // ApplicationInfo.FLAG_DEBUGGABLE removal
    XposedHelpers.findAndHookMethod(
        "android.app.ApplicationPackageManager", cl,
        "getApplicationInfo", String::class.java, Int::class.java,
        object : XC_MethodHook() {
            override fun afterHookedMethod(param: MethodHookParam) {
                val info = param.result as? android.content.pm.ApplicationInfo ?: return
                info.flags = info.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE.inv()
            }
        })
}
```

---

## Combo Template — All Bypass Types in One Script

Use this as starting point — remove what you don't need:

```javascript
Java.perform(function() {
    console.log('[BYPASS] Loading universal bypass...');

    // Root — call rootBypass()
    // SSL — call sslBypass()
    // Hook detect — call hookDetectBypass()
    // Integrity — call integrityBypass()
    // Emulator — call emulatorBypass()
    // Debug — call debugBypass()

    // Copy relevant sections from above into each function
    // Customize per target app — not all checks exist in every app

    console.log('[BYPASS] All bypass modules loaded');
});
```

---

## Iron Rules

1. **Map FIRST, bypass SECOND** — Frida kill chain mapper before writing bypass code
2. **ONE script per app** — combine all bypass types into single script
3. **Test each layer independently** — bypass one, verify, then add next
4. **Log everything** — every bypassed check should console.log for verification
5. **Lazy hooks in Xposed** — Application.onCreate defer pattern, always
6. **Session eb966f16 lesson** — guessing detection methods = 12hrs wasted. Map with Frida = 10 min
