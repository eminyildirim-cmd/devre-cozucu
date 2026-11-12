#!/usr/bin/env python3
"""
Web Tabanlı Devre Çözücü UI (Antigravity & Browser Arayüzü)

Kullanıcının tarayıcı üzerinden sürükle-bırak devre fotoğrafı yükleyebileceği,
Tesseract OCR + MNA analizini çalıştırıp düğüm gerilimlerini, akımları, güçleri
ve fiziksel doğrulama raporunu modern, şık bir arayüzde gösteren yerel web sunucusu.
Harici hiçbir paket (Flask, Django vb.) gerektirmez; standart kütüphane ile çalışır.
"""

import base64
import cgi
import http.server
import json
import os
import socketserver
import sys
import tempfile

# Proje yolunu ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mna import coz
from netlist import netlist_oku
from ngspice_dogrula import dogrula
from resimden_netlist import resimden_cozume

PORT = 8080

HTML_SABLON = """<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Devre Çözücü — MNA & OCR Görüntü Analizi</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0f172a;
            --surface: #1e293b;
            --border: #334155;
            --primary: #3b82f6;
            --primary-hover: #2563eb;
            --success: #10b981;
            --accent: #8b5cf6;
            --text: #f8fafc;
            --text-muted: #94a3b8;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', -apple-system, sans-serif;
        }

        body {
            background-color: var(--bg);
            color: var(--text);
            min-height: 100vh;
            padding: 2rem;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        .container {
            max-width: 950px;
            width: 100%;
        }

        header {
            text-align: center;
            margin-bottom: 2.5rem;
        }

        header h1 {
            font-size: 2.2rem;
            font-weight: 700;
            background: linear-gradient(135deg, #60a5fa, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }

        header p {
            color: var(--text-muted);
            font-size: 1rem;
        }

        .upload-card {
            background: var(--surface);
            border: 2px dashed var(--border);
            border-radius: 16px;
            padding: 3rem 2rem;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s ease;
            position: relative;
        }

        .upload-card:hover, .upload-card.dragover {
            border-color: var(--primary);
            background: rgba(59, 130, 246, 0.05);
        }

        .upload-icon {
            font-size: 3rem;
            margin-bottom: 1rem;
            color: var(--primary);
        }

        .upload-card h3 {
            font-size: 1.25rem;
            margin-bottom: 0.5rem;
        }

        .upload-card p {
            color: var(--text-muted);
            font-size: 0.9rem;
        }

        input[type="file"] {
            display: none;
        }

        .preview-area {
            display: none;
            margin-top: 1.5rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            align-items: center;
            gap: 1.5rem;
        }

        .preview-area img {
            max-width: 200px;
            max-height: 140px;
            object-fit: contain;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: #fff;
        }

        .preview-details {
            flex: 1;
        }

        .btn {
            background: var(--primary);
            color: white;
            border: none;
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 600;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            transition: background 0.2s;
            margin-top: 1rem;
        }

        .btn:hover {
            background: var(--primary-hover);
        }

        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .results {
            display: none;
            margin-top: 2rem;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }

        .card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 1.5rem;
        }

        .card-title {
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: #93c5fd;
        }

        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
        }

        @media (max-width: 768px) {
            .grid-2 {
                grid-template-columns: 1fr;
            }
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }

        th, td {
            padding: 0.75rem 1rem;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }

        th {
            color: var(--text-muted);
            font-weight: 500;
            background: rgba(255, 255, 255, 0.02);
        }

        .mono {
            font-family: 'JetBrains Mono', monospace;
        }

        pre {
            background: #090d16;
            padding: 1rem;
            border-radius: 8px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            overflow-x: auto;
            color: #38bdf8;
            border: 1px solid #1e293b;
        }

        .badge {
            display: inline-block;
            padding: 0.25rem 0.6rem;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 600;
        }

        .badge-success {
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .badge-source {
            background: rgba(239, 68, 68, 0.15);
            color: #f87171;
        }

        .badge-load {
            background: rgba(59, 130, 246, 0.15);
            color: #60a5fa;
        }

        .loading {
            display: none;
            text-align: center;
            padding: 2rem;
        }

        .spinner {
            border: 4px solid rgba(255, 255, 255, 0.1);
            border-left-color: var(--primary);
            border-radius: 50%;
            width: 36px;
            height: 36px;
            animation: spin 1s linear infinite;
            margin: 0 auto 1rem;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>⚡ Devre Çözücü — Akıllı Görüntü Analizi</h1>
            <p>Devre şeması fotoğrafını yükleyin; OCR ve MNA motoru devreyi anında çözsün.</p>
        </header>

        <div class="upload-card" id="dropZone" onclick="document.getElementById('fileInput').click()">
            <div class="upload-icon">📷</div>
            <h3>Devre Şeması Fotoğrafını Buraya Bırakın</h3>
            <p>veya dosya seçmek için tıklayın (PNG, JPG)</p>
            <input type="file" id="fileInput" accept="image/*">
        </div>

        <div class="preview-area" id="previewArea">
            <img id="imagePreview" src="" alt="Devre Önizleme">
            <div class="preview-details">
                <h4 id="fileName">devre.png</h4>
                <p id="fileSize" style="color: var(--text-muted); font-size: 0.85rem; margin-top: 4px;">1.2 MB</p>
                <button class="btn" id="solveBtn" onclick="devreyiCoz()">
                    <span>Devreyi Analiz Et & Çöz ⚡</span>
                </button>
            </div>
        </div>

        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p>Tesseract OCR taranıyor, elemanlar eşleştiriliyor ve MNA matrisi çözülüyor...</p>
        </div>

        <div class="results" id="results">
            <div class="card">
                <div class="card-title">🔍 Otomatik Çıkarılan SPICE Netlist'i</div>
                <pre id="netlistOutput"></pre>
            </div>

            <div class="grid-2">
                <div class="card">
                    <div class="card-title">⚡ Düğüm Gerilimleri (Node Voltages)</div>
                    <table id="voltagesTable">
                        <thead>
                            <tr>
                                <th>Düğüm</th>
                                <th>Gerilim</th>
                            </tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>

                <div class="card">
                    <div class="card-title">🛡️ Fiziksel Doğrulama Raporu</div>
                    <div style="margin-bottom: 1rem;">
                        <span class="badge badge-success" id="validationBadge">KCL & KVL SAĞLANDI ✓</span>
                    </div>
                    <p id="validationText" style="font-size: 0.9rem; line-height: 1.5; color: var(--text-muted);"></p>
                </div>
            </div>

            <div class="card">
                <div class="card-title">📊 Eleman Akımları ve Güç Dağılımı</div>
                <table id="elementsTable">
                    <thead>
                        <tr>
                            <th>Eleman</th>
                            <th>Uçlar (+ → -)</th>
                            <th>Gerilim (V)</th>
                            <th>Akım (I)</th>
                            <th>Güç (P)</th>
                            <th>Durum</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        const fileInput = document.getElementById('fileInput');
        const dropZone = document.getElementById('dropZone');
        const previewArea = document.getElementById('previewArea');
        const imagePreview = document.getElementById('imagePreview');
        const fileName = document.getElementById('fileName');
        const fileSize = document.getElementById('fileSize');
        const solveBtn = document.getElementById('solveBtn');
        const loading = document.getElementById('loading');
        const results = document.getElementById('results');

        let secilenDosya = null;

        fileInput.addEventListener('change', e => {
            if (e.target.files.length > 0) {
                dosyayiAyarla(e.target.files[0]);
            }
        });

        dropZone.addEventListener('dragover', e => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });

        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

        dropZone.addEventListener('drop', e => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                dosyayiAyarla(e.dataTransfer.files[0]);
            }
        });

        function dosyayiAyarla(dosya) {
            secilenDosya = dosya;
            fileName.textContent = dosya.name;
            fileSize.textContent = (dosya.size / (1024 * 1024)).toFixed(2) + ' MB';
            const reader = new FileReader();
            reader.onload = ev => {
                imagePreview.src = ev.target.result;
                previewArea.style.display = 'flex';
                results.style.display = 'none';
            };
            reader.readAsDataURL(dosya);
        }

        async function devreyiCoz() {
            if (!secilenDosya) return;
            solveBtn.disabled = true;
            loading.style.display = 'block';
            results.style.display = 'none';

            const formData = new FormData();
            formData.append('resim', secilenDosya);

            try {
                const yanit = await fetch('/api/coz', {
                    method: 'POST',
                    body: formData
                });
                const veri = await yanit.json();
                if (veri.hata) {
                    alert('Hata: ' + veri.hata);
                } else {
                    sonuclariGoster(veri);
                }
            } catch (err) {
                alert('İletişim hatası: ' + err);
            } finally {
                loading.style.display = 'none';
                solveBtn.disabled = false;
            }
        }

        function sonuclariGoster(veri) {
            document.getElementById('netlistOutput').textContent = veri.netlist;

            // Düğümler
            const vTable = document.querySelector('#voltagesTable tbody');
            vTable.innerHTML = '';
            for (const [dugum, voltaj] of Object.entries(veri.dugumler)) {
                const tr = document.createElement('tr');
                tr.innerHTML = `<td class="mono">V(${dugum})</td><td class="mono" style="color: #60a5fa; font-weight: 600;">${voltaj.toFixed(3)} V</td>`;
                vTable.appendChild(tr);
            }

            // Elemanlar
            const eTable = document.querySelector('#elementsTable tbody');
            eTable.innerHTML = '';
            for (const el of veri.elemanlar) {
                const tr = document.createElement('tr');
                const durumBadge = el.guc < 0 
                    ? '<span class="badge badge-source">Üretiyor (-P)</span>' 
                    : '<span class="badge badge-load">Tüketiyor (+P)</span>';
                tr.innerHTML = `
                    <td class="mono" style="font-weight: 600;">${el.ad}</td>
                    <td class="mono">${el.d_arti} → ${el.d_eksi}</td>
                    <td class="mono">${el.gerilim.toFixed(2)} V</td>
                    <td class="mono">${(el.akim * 1000).toFixed(2)} mA</td>
                    <td class="mono">${(el.guc * 1000).toFixed(2)} mW</td>
                    <td>${durumBadge}</td>
                `;
                eTable.appendChild(tr);
            }

            // Doğrulama
            document.getElementById('validationText').innerHTML = 
                `<strong>Tellegen Enerji Dengesi:</strong> Σ P = ${veri.tellegen.toExponential(2)} W<br>` +
                `<strong>KCL Sapması:</strong> ${veri.kcl_hatasi.toExponential(2)} A<br>` +
                `<strong>KVL Sapması:</strong> ${veri.kvl_hatasi.toExponential(2)} V<br><br>` +
                veri.dogrulama_mesaji;

            results.style.display = 'flex';
            results.scrollIntoView({ behavior: 'smooth' });
        }
    </script>
</body>
</html>
"""


class DevreHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_SABLON.encode("utf-8"))
        else:
            self.send_error(404, "Bulunamadi")

    def do_POST(self):
        if self.path == "/api/coz":
            try:
                ctype = self.headers.get("Content-Type", "")
                if "multipart/form-data" not in ctype:
                    self._json_cevap({"hata": "multipart/form-data bekleniyor"}, status=400)
                    return

                # FormData parçala
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": ctype},
                )

                if "resim" not in form:
                    self._json_cevap({"hata": "Resim yuklenmedi"}, status=400)
                    return

                resim_item = form["resim"]
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp.write(resim_item.file.read())
                    tmp_yolu = tmp.name

                try:
                    netlist_metin, elemanlar = resimden_cozume(tmp_yolu)
                    cozum = coz(elemanlar)
                    rapor = dogrula(elemanlar, cozum)

                    eleman_detaylari = []
                    for el in elemanlar:
                        v = cozum.eleman_gerilimleri.get(el.isim, 0.0)
                        i = cozum.eleman_akimlari.get(el.isim, 0.0)
                        p = cozum.eleman_gucleri.get(el.isim, 0.0)
                        eleman_detaylari.append({
                            "ad": el.isim,
                            "d_arti": el.dugum_p,
                            "d_eksi": el.dugum_n,
                            "gerilim": v,
                            "akim": i,
                            "guc": p,
                        })

                    cevap = {
                        "netlist": netlist_metin,
                        "dugumler": cozum.dugum_voltajlari,
                        "elemanlar": eleman_detaylari,
                        "tellegen": sum(cozum.eleman_gucleri.values()),
                        "kcl_hatasi": rapor.kcl_hatasi,
                        "kvl_hatasi": rapor.kvl_hatasi,
                        "dogrulama_mesaji": rapor.mesaj,
                    }
                    self._json_cevap(cevap)
                finally:
                    if os.path.exists(tmp_yolu):
                        os.remove(tmp_yolu)

            except Exception as e:
                self._json_cevap({"hata": str(e)}, status=500)
        else:
            self.send_error(404, "API rotasi bulunamadi")

    def _json_cevap(self, veri: dict, status: int = 200):
        icerik = json.dumps(veri).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(icerik)))
        self.end_headers()
        self.wfile.write(icerik)


def baslat():
    with socketserver.TCPServer(("", PORT), DevreHandler) as httpd:
        print(f"⚡ Devre Çözücü Web Uygulaması Başlatıldı: http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nSunucu kapatıldı.")


if __name__ == "__main__":
    baslat()

