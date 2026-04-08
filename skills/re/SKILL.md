---
name: re
description: "Reverse engineering — APK analysis, binary RE, native library analysis, protocol RE, malware analysis. Use when: reverse engineer, decompile, disassemble, binary, native, smali, protocol, malware."
argument-hint: "[action: decompile/analyze/trace/patch] [target file or package]"
---

# /re — Reverse Engineering Skill

> APK analysis, native RE, protocol RE, smali patching, binary analysis.
> FRIDA FIRST for dynamic analysis. Static analysis gives the map, dynamic gives the truth.

---

## Phase 1 — APK Analysis

### Decompilation Pipeline

```bash
# === JADX — Java/Kotlin source (primary tool) ===
jadx -d jadx_output target.apk --deobf --show-bad-code
# --deobf: rename obfuscated classes to readable names
# --show-bad-code: show decompilation errors inline (don't skip)

# === APKTOOL — Resources + Smali ===
apktool d target.apk -o apktool_output
# Key outputs:
#   apktool_output/smali/          — Dalvik bytecode
#   apktool_output/res/            — decoded resources
#   apktool_output/AndroidManifest.xml  — permissions, components
#   apktool_output/lib/            — native libraries

# === DEX2JAR — Alternative Java source ===
d2j-dex2jar target.apk -o target.jar
# Open target.jar in JD-GUI or fernflower

# === Quick inspection without full decompile ===
unzip -l target.apk                        # List contents
unzip -p target.apk classes.dex | xxd | head  # Quick hex look
aapt dump badging target.apk               # Package info, permissions
aapt dump permissions target.apk           # Declared permissions
```

### What to Map First

| Target | Command | Why |
|--------|---------|-----|
| Entry points | Grep `<activity.*MAIN` in Manifest | Find main activity |
| Permissions | Grep `uses-permission` in Manifest | Understand app capabilities |
| Services | Grep `<service` in Manifest | Background components |
| Receivers | Grep `<receiver` in Manifest | Broadcast handlers |
| Native libs | `ls apktool_output/lib/arm64-v8a/` | Identify security SDKs |
| Security classes | Grep `Security\|Root\|Tamper\|Integrity` in jadx output | Anti-tamper code |
| JNI calls | Grep `native ` in jadx output | Java-to-native bridge |
| Obfuscation | Check for single-letter class/method names | Proguard/R8/DexGuard |

### Multi-DEX Handling

```bash
# List all DEX files
unzip -l target.apk | grep '\.dex$'
# Output: classes.dex, classes2.dex, classes3.dex, ...

# Decompile specific DEX
jadx -d output_dex2 --input-file <(unzip -p target.apk classes2.dex)

# Or extract all
unzip target.apk 'classes*.dex' -d dex_files/
```

---

## Phase 2 — Native Library Analysis

### Initial Reconnaissance

```bash
# === File type and architecture ===
file lib/arm64-v8a/libtarget.so
# Expected: ELF 64-bit LSB shared object, ARM aarch64

# === Dynamic symbols (exported functions) ===
readelf -sW lib/arm64-v8a/libtarget.so | grep -E "FUNC.*GLOBAL" | head -30

# === All symbols including local ===
nm -D lib/arm64-v8a/libtarget.so | head -50

# === Section headers ===
readelf -S lib/arm64-v8a/libtarget.so

# === Dependencies (linked libraries) ===
readelf -d lib/arm64-v8a/libtarget.so | grep NEEDED

# === Strings — security-related ===
strings lib/arm64-v8a/libtarget.so | grep -iE "root|frida|xposed|magisk|hook|tamper|debug|su|detect|integrity|emulator"

# === JNI function exports ===
nm -D lib/arm64-v8a/libtarget.so | grep "Java_"
# Format: Java_com_package_ClassName_methodName

# === Init/Constructor functions ===
readelf -d lib/arm64-v8a/libtarget.so | grep INIT
nm -D lib/arm64-v8a/libtarget.so | grep -E "JNI_OnLoad|init"
```

### JNI RegisterNatives Tracing

When native methods aren't exported with standard `Java_` prefix, the app uses `RegisterNatives` to bind them at runtime. Trace with Frida:

```javascript
// Trace RegisterNatives to find dynamically registered JNI functions
Java.perform(function() {
    var RegisterNatives = null;
    var envPtr = Java.vm.tryGetEnv();

    // Hook art::JNI::RegisterNatives
    var artModule = Process.findModuleByName('libart.so');
    if (artModule) {
        var symbols = artModule.enumerateSymbols();
        for (var i = 0; i < symbols.length; i++) {
            if (symbols[i].name.indexOf('RegisterNatives') !== -1 &&
                symbols[i].name.indexOf('CheckJNI') === -1) {
                RegisterNatives = symbols[i].address;
                break;
            }
        }
    }

    if (RegisterNatives) {
        Interceptor.attach(RegisterNatives, {
            onEnter: function(args) {
                var clazz = args[1];
                var methods = args[2];
                var nMethods = args[3].toInt32();

                var env = Java.vm.getEnv();
                var className = env.getClassName(clazz);

                console.log('\n[JNI] RegisterNatives for: ' + className);
                console.log('[JNI] Method count: ' + nMethods);

                for (var j = 0; j < nMethods; j++) {
                    var methodPtr = methods.add(j * Process.pointerSize * 3);
                    var name = methodPtr.readPointer().readCString();
                    var sig = methodPtr.add(Process.pointerSize).readPointer().readCString();
                    var fnPtr = methodPtr.add(Process.pointerSize * 2).readPointer();
                    var module = Process.findModuleByAddress(fnPtr);
                    var moduleName = module ? module.name : 'unknown';
                    var offset = module ? '0x' + fnPtr.sub(module.base).toString(16) : fnPtr.toString();

                    console.log('[JNI]   ' + name + sig + ' -> ' + moduleName + '+' + offset);
                }
            }
        });
        console.log('[JNI] RegisterNatives hook installed');
    } else {
        console.log('[JNI] RegisterNatives not found in libart.so');
    }
});
```

---

## Phase 3 — Protocol Reverse Engineering

### Network Capture via Frida

```javascript
Java.perform(function() {
    // === OkHttp Request/Response interceptor ===
    try {
        var OkHttpClient = Java.use('okhttp3.OkHttpClient');
        var Builder = Java.use('okhttp3.OkHttpClient$Builder');
        var Interceptor = Java.use('okhttp3.Interceptor');

        // Hook newCall to log all requests
        var RealCall = Java.use('okhttp3.RealCall');
        RealCall.execute.implementation = function() {
            var request = this.request();
            console.log('\n[HTTP] ' + request.method() + ' ' + request.url().toString());

            // Log headers
            var headers = request.headers();
            for (var i = 0; i < headers.size(); i++) {
                console.log('[HTTP]   ' + headers.name(i) + ': ' + headers.value(i));
            }

            // Log body if present
            var body = request.body();
            if (body) {
                var buffer = Java.use('okio.Buffer').$new();
                body.writeTo(buffer);
                console.log('[HTTP]   Body: ' + buffer.readUtf8());
            }

            var response = this.execute();
            console.log('[HTTP]   -> ' + response.code() + ' ' + response.message());

            return response;
        };
    } catch(e) {
        console.log('[HTTP] OkHttp not found, trying HttpURLConnection...');
    }

    // === HttpURLConnection fallback ===
    try {
        var URL = Java.use('java.net.URL');
        URL.openConnection.overload().implementation = function() {
            var conn = this.openConnection();
            console.log('[HTTP] URLConnection: ' + this.toString());
            return conn;
        };
    } catch(e) {}

    // === WebSocket monitoring ===
    try {
        var WebSocket = Java.use('okhttp3.internal.ws.RealWebSocket');
        WebSocket.send.overload('java.lang.String').implementation = function(text) {
            console.log('[WS] SEND: ' + text);
            return this.send(text);
        };
    } catch(e) {}
});
```

### Encryption/Crypto Tracing

```javascript
Java.perform(function() {
    // === Cipher operations ===
    var Cipher = Java.use('javax.crypto.Cipher');

    Cipher.getInstance.overload('java.lang.String').implementation = function(transformation) {
        console.log('[CRYPTO] Cipher.getInstance: ' + transformation);
        return this.getInstance(transformation);
    };

    Cipher.init.overload('int', 'java.security.Key').implementation = function(opmode, key) {
        var mode = (opmode === 1) ? 'ENCRYPT' : 'DECRYPT';
        var keyBytes = key.getEncoded();
        console.log('[CRYPTO] Cipher.init ' + mode + ' key=' + bytesToHex(keyBytes));
        return this.init(opmode, key);
    };

    Cipher.doFinal.overload('[B').implementation = function(input) {
        console.log('[CRYPTO] doFinal input (' + input.length + ' bytes): ' + bytesToHex(input.slice(0, 32)));
        var result = this.doFinal(input);
        console.log('[CRYPTO] doFinal output (' + result.length + ' bytes): ' + bytesToHex(result.slice(0, 32)));
        return result;
    };

    // === SecretKeySpec ===
    var SecretKeySpec = Java.use('javax.crypto.spec.SecretKeySpec');
    SecretKeySpec.$init.overload('[B', 'java.lang.String').implementation = function(key, algorithm) {
        console.log('[CRYPTO] SecretKeySpec(' + algorithm + '): ' + bytesToHex(key));
        return this.$init(key, algorithm);
    };

    // === MessageDigest (hashing) ===
    var MessageDigest = Java.use('java.security.MessageDigest');
    MessageDigest.digest.overload('[B').implementation = function(input) {
        var result = this.digest(input);
        var algo = this.getAlgorithm();
        console.log('[CRYPTO] ' + algo + ' digest: ' + bytesToHex(result));
        return result;
    };

    function bytesToHex(bytes) {
        var hex = '';
        for (var i = 0; i < Math.min(bytes.length, 32); i++) {
            var b = (bytes[i] & 0xff).toString(16);
            hex += (b.length === 1 ? '0' : '') + b;
        }
        if (bytes.length > 32) hex += '...';
        return hex;
    }
});
```

---

## Phase 4 — Smali Patching

### When to Use

- Small targeted changes (flip a boolean, change a string)
- When Frida/Xposed isn't persistent enough
- Modifying APK for distribution/testing

### Workflow

```bash
# 1. Decompile
apktool d target.apk -o patch_dir

# 2. Find target smali
grep -rn "isRooted\|checkRoot\|detectRoot" patch_dir/smali/

# 3. Edit smali (example: force method to return false)
# Original:
#   invoke-virtual {p0}, Lcom/target/Security;->isRooted()Z
#   move-result v0
#
# Patched: insert before move-result
#   const/4 v0, 0x0
#   return v0

# 4. Rebuild
apktool b patch_dir -o patched.apk

# 5. Sign
# Generate key (one-time):
keytool -genkey -v -keystore test.keystore -alias test -keyalg RSA -keysize 2048 -validity 10000
# Sign:
jarsigner -verbose -sigalg SHA1withRSA -digestalg SHA1 -keystore test.keystore patched.apk test
# Or use apksigner:
apksigner sign --ks test.keystore patched.apk

# 6. Align
zipalign -v 4 patched.apk patched-aligned.apk

# 7. Install
adb install -r patched-aligned.apk
```

### Common Smali Patches

| Goal | Original Smali | Patched Smali |
|------|---------------|---------------|
| Force return false | `invoke-virtual ... isRooted()Z` | Insert `const/4 v0, 0x0` + `return v0` before move-result |
| Force return true | `invoke-virtual ... verify()Z` | Insert `const/4 v0, 0x1` + `return v0` |
| Skip method call | `invoke-virtual {p0}, Lcom/sec/Check;->run()V` | Delete the line or `nop` |
| Change string | `const-string v0, "real_value"` | `const-string v0, "spoofed_value"` |
| Remove if-branch | `if-eqz v0, :cond_fail` | `goto :cond_pass` |

---

## Phase 5 — Binary Patching Concepts

### When Needed

- Native .so files with integrity checks
- Encrypted/packed DEX that must be modified
- ELF header manipulation

### Approach

```bash
# 1. Identify target function offset
readelf -sW libtarget.so | grep target_function
# Note: Sym.Value = offset from base

# 2. Disassemble the function region
objdump -d --start-address=0xOFFSET --stop-address=0xOFFSET+0x100 libtarget.so

# 3. Find the instruction to patch
# Example: BNE (branch if not equal) -> NOP or B (unconditional branch)
# ARM64 NOP = 0x1F2003D5
# ARM64 B (unconditional) = calculate offset

# 4. Patch with Python
python3 -c "
import struct
with open('libtarget.so', 'rb') as f:
    data = bytearray(f.read())
offset = 0xABCD  # Your target offset
# NOP the instruction
data[offset:offset+4] = struct.pack('<I', 0xD503201F)  # ARM64 NOP
with open('libtarget_patched.so', 'wb') as f:
    f.write(data)
print('Patched at offset 0x%x' % offset)
"

# 5. Replace in APK
cp libtarget_patched.so apktool_output/lib/arm64-v8a/libtarget.so
apktool b apktool_output -o patched.apk
```

### ARM64 Instruction Reference (Common Patches)

| Instruction | Hex (LE) | Use Case |
|-------------|----------|----------|
| NOP | `1F 20 03 D5` | Remove any instruction |
| RET | `C0 03 5F D6` | Force function return |
| MOV X0, #0 | `00 00 80 D2` | Return 0 (false) |
| MOV X0, #1 | `20 00 80 D2` | Return 1 (true) |
| MOV W0, #0 | `00 00 80 52` | Return 0 (32-bit) |
| MOV W0, #1 | `20 00 80 52` | Return 1 (32-bit) |
| B (unconditional) | Calculate offset | Skip code blocks |
| CBNZ -> CBZ | Flip bit 24 | Invert branch condition |

---

## Tool Reference

| Tool | Purpose | Install |
|------|---------|---------|
| jadx | APK to Java decompilation | `brew install jadx` |
| apktool | APK decode/rebuild/smali | `brew install apktool` |
| dex2jar | DEX to JAR conversion | `brew install dex2jar` |
| Frida | Dynamic instrumentation | `pip install frida-tools` |
| readelf | ELF binary analysis | Built-in (binutils) |
| nm | Symbol listing | Built-in |
| objdump | Disassembly | Built-in (binutils) |
| strings | Extract printable strings | Built-in |
| Ghidra | Full disassembler/decompiler | Download from NSA GitHub |
| radare2 | CLI disassembler | `brew install radare2` |
| apksigner | APK signing | Android SDK |
| zipalign | APK alignment | Android SDK |

---

## Iron Rules

1. **Static FIRST** — jadx gives you class names, method sigs, string references for targeted dynamic analysis
2. **FRIDA FIRST for dynamic** — map the kill chain before writing any bypass
3. **RegisterNatives tracing** — when `nm` shows no `Java_` exports, the app uses dynamic registration
4. **Multi-DEX awareness** — security code often lives in secondary DEX files
5. **Native strings** — `strings` on .so files reveals detection keywords, URLs, SDK identifiers
6. **Smali patching = last resort** — Frida/Xposed preferred because they don't modify the APK
7. **Session eb966f16 lesson** — 12hrs wasted guessing. 10 min Frida mapping would have saved the day
