#!/usr/bin/env python3
"""
DataImpulse Residential Proxy v10.1
HARAMI PROXY - Residential IPs from 195+ countries

Features:
- Country/State/City targeting
- Sticky sessions (30 min)
- Auto-rotation
- SOCKS5 support

Usage:
    python3 dataimpulse_proxy.py get                     # Get proxy string (random country)
    python3 dataimpulse_proxy.py get india               # Get India proxy
    python3 dataimpulse_proxy.py get us sticky           # US with sticky session
    python3 dataimpulse_proxy.py curl <url>              # Curl with proxy
    python3 dataimpulse_proxy.py test                    # Test proxy connection
    python3 dataimpulse_proxy.py countries               # List country codes
"""

import requests
import sys
import random
import string
import subprocess
import json

# ═══════════════════════════════════════════════════════════════════════════════
# CREDENTIALS (from environment variables)
# ═══════════════════════════════════════════════════════════════════════════════
import os
PROXY_LOGIN = os.getenv("DATAIMPULSE_USER", "")
PROXY_PASS = os.getenv("DATAIMPULSE_PASS", "")
PROXY_HOST = "gw.dataimpulse.com"
PROXY_PORT_HTTP = 823
PROXY_PORT_SOCKS5 = 824

# ═══════════════════════════════════════════════════════════════════════════════
# COUNTRY CODES (ISO 3166-1 alpha-2)
# ═══════════════════════════════════════════════════════════════════════════════
COUNTRY_CODES = {
    # Common
    'india': 'in', 'us': 'us', 'usa': 'us', 'uk': 'gb', 'germany': 'de',
    'france': 'fr', 'russia': 'ru', 'china': 'cn', 'japan': 'jp',
    'australia': 'au', 'canada': 'ca', 'brazil': 'br', 'mexico': 'mx',

    # Asia
    'indonesia': 'id', 'malaysia': 'my', 'singapore': 'sg', 'thailand': 'th',
    'vietnam': 'vn', 'philippines': 'ph', 'pakistan': 'pk', 'bangladesh': 'bd',
    'korea': 'kr', 'taiwan': 'tw', 'hongkong': 'hk', 'uae': 'ae',
    'saudi': 'sa', 'turkey': 'tr', 'israel': 'il', 'iran': 'ir',

    # Europe
    'spain': 'es', 'italy': 'it', 'netherlands': 'nl', 'poland': 'pl',
    'sweden': 'se', 'norway': 'no', 'denmark': 'dk', 'finland': 'fi',
    'belgium': 'be', 'austria': 'at', 'switzerland': 'ch', 'portugal': 'pt',
    'greece': 'gr', 'czech': 'cz', 'romania': 'ro', 'ukraine': 'ua',
    'hungary': 'hu', 'ireland': 'ie',

    # Africa
    'nigeria': 'ng', 'southafrica': 'za', 'egypt': 'eg', 'kenya': 'ke',
    'morocco': 'ma', 'ghana': 'gh',

    # Americas
    'argentina': 'ar', 'chile': 'cl', 'colombia': 'co', 'peru': 'pe',
    'venezuela': 've',
}

class DataImpulseProxy:
    """DataImpulse Residential Proxy Manager"""

    def __init__(self):
        self.login = PROXY_LOGIN
        self.password = PROXY_PASS
        self.host = PROXY_HOST
        self.port_http = PROXY_PORT_HTTP
        self.port_socks5 = PROXY_PORT_SOCKS5

    def _get_country_code(self, country):
        """Convert country name to ISO code"""
        if not country:
            return None
        country = country.lower().replace(' ', '')
        # Already a 2-letter code?
        if len(country) == 2:
            return country
        return COUNTRY_CODES.get(country, country)

    def _generate_session_id(self):
        """Generate random session ID for sticky sessions"""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

    def get_proxy_string(self, country=None, sticky=False, session_id=None, socks5=False):
        """
        Build proxy connection string

        Args:
            country: Country name or ISO code (e.g., 'india', 'in', 'us')
            sticky: If True, use sticky session (same IP for 30 min)
            session_id: Custom session ID for sticky session
            socks5: If True, use SOCKS5 port

        Returns:
            dict with proxy strings for different formats
        """
        # Build parameters
        params = []

        # Country
        if country:
            code = self._get_country_code(country)
            if code:
                params.append(f"cr.{code}")

        # Sticky session
        if sticky:
            sid = session_id or self._generate_session_id()
            params.append(f"sessid.{sid}")

        # Build username with params
        username = self.login
        if params:
            username = f"{self.login}__{';'.join(params)}"

        port = self.port_socks5 if socks5 else self.port_http
        protocol = "socks5" if socks5 else "http"

        # Different formats
        proxy_url = f"{protocol}://{username}:{self.password}@{self.host}:{port}"
        proxy_simple = f"{username}:{self.password}@{self.host}:{port}"

        return {
            'url': proxy_url,
            'simple': proxy_simple,
            'host': self.host,
            'port': port,
            'username': username,
            'password': self.password,
            'protocol': protocol,
            'country': country,
            'sticky': sticky,
            'session_id': session_id if sticky else None,

            # For different tools
            'curl': f"-x '{proxy_url}'",
            'requests': {'http': proxy_url, 'https': proxy_url},
            'env': f"export HTTP_PROXY='{proxy_url}' HTTPS_PROXY='{proxy_url}'",
            'sqlmap': f"--proxy='{proxy_url}'",
            'nuclei': f"-proxy '{proxy_url}'",
        }

    def test_proxy(self, country=None, sticky=False):
        """Test proxy connection and return IP info"""
        proxy = self.get_proxy_string(country, sticky)

        print(f"[*] Testing proxy: {proxy['simple'][:50]}...")

        try:
            # Test with ipify
            r = requests.get(
                'https://api.ipify.org?format=json',
                proxies=proxy['requests'],
                timeout=30
            )
            ip_data = r.json()

            # Get IP location
            r2 = requests.get(
                f"http://ip-api.com/json/{ip_data['ip']}",
                timeout=10
            )
            location = r2.json()

            return {
                'success': True,
                'ip': ip_data['ip'],
                'country': location.get('country', 'Unknown'),
                'country_code': location.get('countryCode', '??'),
                'city': location.get('city', 'Unknown'),
                'isp': location.get('isp', 'Unknown'),
                'proxy': proxy['simple']
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'proxy': proxy['simple']
            }

    def curl(self, url, country=None, sticky=False, extra_args=""):
        """Execute curl command through proxy"""
        proxy = self.get_proxy_string(country, sticky)

        cmd = f"curl -s {proxy['curl']} {extra_args} '{url}'"

        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            return {
                'success': True,
                'output': result.stdout,
                'error': result.stderr if result.stderr else None,
                'command': cmd
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'command': cmd
            }


def print_help():
    print("""
DataImpulse Residential Proxy v10.1 - HARAMI PROXY
===================================================

COMMANDS:

  Get proxy string:
    python3 dataimpulse_proxy.py get                    # Random country
    python3 dataimpulse_proxy.py get india              # India IP
    python3 dataimpulse_proxy.py get us                 # US IP
    python3 dataimpulse_proxy.py get us sticky          # US sticky (30 min same IP)
    python3 dataimpulse_proxy.py get india socks5       # India SOCKS5

  Test connection:
    python3 dataimpulse_proxy.py test                   # Test random
    python3 dataimpulse_proxy.py test india             # Test India

  Curl through proxy:
    python3 dataimpulse_proxy.py curl https://api.ipify.org
    python3 dataimpulse_proxy.py curl https://example.com india

  List countries:
    python3 dataimpulse_proxy.py countries

PROXY FORMAT:
  HTTP:   http://login__cr.in:pass@gw.dataimpulse.com:823
  SOCKS5: socks5://login__cr.in:pass@gw.dataimpulse.com:824

PARAMETERS:
  cr.XX        - Country (ISO 2-letter code)
  cr.us,in     - Multiple countries
  sessid.XXX   - Sticky session (30 min same IP)

INTEGRATION:
  # In Python
  from dataimpulse_proxy import DataImpulseProxy
  proxy = DataImpulseProxy()
  p = proxy.get_proxy_string('india', sticky=True)
  requests.get(url, proxies=p['requests'])

  # In Bash
  PROXY=$(python3 dataimpulse_proxy.py get india | grep "URL:" | awk '{print $2}')
  curl -x "$PROXY" https://example.com

  # For SQLMap
  sqlmap -u "URL" $(python3 dataimpulse_proxy.py get india | grep "SQLMap:" | cut -d':' -f2-)

  # For Nuclei
  nuclei -u "URL" $(python3 dataimpulse_proxy.py get india | grep "Nuclei:" | cut -d':' -f2-)
""")


def main():
    proxy = DataImpulseProxy()

    if len(sys.argv) < 2:
        print_help()
        return

    cmd = sys.argv[1].lower()

    if cmd == 'get':
        country = sys.argv[2] if len(sys.argv) > 2 else None
        sticky = 'sticky' in sys.argv
        socks5 = 'socks5' in sys.argv

        # Filter out flags from country
        if country in ['sticky', 'socks5']:
            country = None

        result = proxy.get_proxy_string(country, sticky, socks5=socks5)

        print("\n" + "="*60)
        print("PROXY CONFIGURATION")
        print("="*60)
        print(f"Country:  {country or 'Random'}")
        print(f"Sticky:   {'Yes (30 min same IP)' if sticky else 'No (rotating)'}")
        print(f"Protocol: {result['protocol'].upper()}")
        print("="*60)
        print(f"\nURL:      {result['url']}")
        print(f"Simple:   {result['simple']}")
        print(f"\nCurl:     curl {result['curl']} <url>")
        print(f"SQLMap:   sqlmap -u <url> {result['sqlmap']}")
        print(f"Nuclei:   nuclei -u <url> {result['nuclei']}")
        print(f"\nEnv:      {result['env']}")
        print("="*60)

    elif cmd == 'test':
        country = sys.argv[2] if len(sys.argv) > 2 else None
        sticky = 'sticky' in sys.argv

        result = proxy.test_proxy(country, sticky)

        if result['success']:
            print("\n" + "="*60)
            print("PROXY TEST - SUCCESS!")
            print("="*60)
            print(f"IP:       {result['ip']}")
            print(f"Country:  {result['country']} ({result['country_code']})")
            print(f"City:     {result['city']}")
            print(f"ISP:      {result['isp']}")
            print("="*60)
        else:
            print(f"\n[!] FAILED: {result['error']}")

    elif cmd == 'curl':
        if len(sys.argv) < 3:
            print("Usage: python3 dataimpulse_proxy.py curl <url> [country] [sticky]")
            return

        url = sys.argv[2]
        country = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] not in ['sticky'] else None
        sticky = 'sticky' in sys.argv

        result = proxy.curl(url, country, sticky)

        if result['success']:
            print(result['output'])
        else:
            print(f"[!] Error: {result['error']}")

    elif cmd == 'countries':
        print("\n" + "="*60)
        print("SUPPORTED COUNTRIES")
        print("="*60)

        # Group by region
        regions = {
            'Asia': ['india', 'china', 'japan', 'korea', 'indonesia', 'malaysia',
                    'singapore', 'thailand', 'vietnam', 'philippines', 'pakistan',
                    'bangladesh', 'taiwan', 'hongkong', 'uae', 'saudi', 'turkey', 'israel'],
            'Europe': ['uk', 'germany', 'france', 'russia', 'spain', 'italy',
                      'netherlands', 'poland', 'sweden', 'norway', 'denmark', 'finland',
                      'belgium', 'austria', 'switzerland', 'portugal', 'greece',
                      'czech', 'romania', 'ukraine', 'hungary', 'ireland'],
            'Americas': ['us', 'canada', 'mexico', 'brazil', 'argentina', 'chile',
                        'colombia', 'peru', 'venezuela'],
            'Africa': ['nigeria', 'southafrica', 'egypt', 'kenya', 'morocco', 'ghana'],
            'Oceania': ['australia'],
        }

        for region, countries in regions.items():
            print(f"\n{region}:")
            for c in countries:
                code = COUNTRY_CODES.get(c, c)
                print(f"  {c:15} = {code}")

        print("\n" + "="*60)
        print("Use any ISO 3166-1 alpha-2 code (e.g., 'in', 'us', 'de')")
        print("="*60)

    elif cmd in ['help', '--help', '-h']:
        print_help()

    else:
        print(f"Unknown command: {cmd}")
        print("Use 'help' for usage")


if __name__ == "__main__":
    main()
