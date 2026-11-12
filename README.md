# Devre Çözücü (Circuit Solver) — Görüntüden Graf ve MNA Simülatörü

Devre Analizi ve *Circuits & Systems* çalışmaları için geliştirilmiş, **Değiştirilmiş Düğüm Analizi (Modified Nodal Analysis - MNA)** tabanlı uçtan uca devre simülatörü.

Devre şeması görüntülerinden (PNG/JPG) veya SPICE `.cir` dosyalarından netlist okuyarak **DC**, **AC (fazör)**, **Geçici (transient)** ve **Laplace sembolik transfer fonksiyonu $H(s)$** analizlerini adım adım damga (stamp) yöntemiyle çözer ve doğrular.

---

## 🚀 Özellikler

* **1. DC Analizi (`mna.py`):**
  * Direnç (`R`), Bağımsız Gerilim Kaynakları (`V`), Bağımsız Akım Kaynakları (`I`), DC kararlı durumda `C` (açık devre) ve `L` (kısa devre).
  * Süper düğüm desteği ve Tellegen güç dengesi doğrulaması ($\sum P = 0$).
* **2. AC (Fazör) Analizi (`mna.py`):**
  * Kapasitör (`C`) ve Bobin (`L`) admittans damgaları ($Y_C = j\omega C$, $Y_L = 1/j\omega L$).
  * Karmaşık lineer sistem çözümü: $A(\omega) \cdot x(\omega) = z(\omega)$.
  * Kutupsal ($|V|\angle\theta^\circ$), Kartezyen ($a+jb$), RMS gösterimi; Aktif ($P$), Reaktif ($Q$) güç ve AC Tellegen dengesi ($\sum S = 0$).
* **3. Bağımlı Kaynaklar (`mna.py`):**
  * **VCVS (`E`)**, **VCCS (`G`)**, **CCVS (`H`)**, **CCCS (`F`)** — Op-Amp, BJT ve MOSFET küçük işaret modelleri.
* **4. Geçici (Transient) Analiz (`transient.py`):**
  * Sayısal integrasyon (Yamuk Kuralı - Trapezoidal Companion Model).
  * Konsolda doğrudan **ASCII dalga şekli çizimi** ve vektörel **SVG grafik çıktısı**.
* **5. Laplace / Sembolik Transfer Fonksiyonu $H(s)$ (`laplace.py`):**
  * Sembolik s-domeni MNA matrisi ve rasyonel polinom aritmetiği ile $H(s) = \frac{N(s)}{D(s)}$ türetimi.
  * Kutup-Sıfır (Poles & Zeros), kararlılık analizi, DC kazancı ve 2. derece filtre parametreleri ($\omega_0, \zeta, Q$).
* **6. Resimden Netlist (`resimden_netlist.py`):**
  * **BFS Piksel Tel İzleme (Connected Components):** Şema görüntüsü üzerindeki eleman kutularını maskeler, siyah bağlantı tellerini piksel piksel BFS ile takip ederek düğümleri (`0, 1, 2...`) çıkarır ve otomatik SPICE netlist'e dönüştürür.
  * **Vision API Desteği:** Anthropic Claude Vision (`ANTHROPIC_API_KEY`) ve Google Gemini Vision (`GEMINI_API_KEY`) ile el çizimi fotoğraflardan doğrudan SPICE netlist üretimi.
* **7. ngspice ve KCL/KVL Doğrulaması (`ngspice_dogrula.py`):**
  * Otomatik `ngspice` toplu iş betiği üretimi, çıktı karşılaştırması ve bağımsız Kirchhoff Akımlar/Gerilimler Yasası (KCL & KVL) denetçisi.

---

## 🛠️ Kurulum ve Gereksinimler

```bash
pip install numpy pillow
```

---

## 💻 Kullanım

### 1. DC Analizi ve Doğrulama
```bash
python3 devre_cozucu/main.py devre_cozucu/ornekler/gerilim_bolucu.cir --dogrula
python3 devre_cozucu/main.py devre_cozucu/ornekler/opamp_evirmeyen_kuvvetlendirici.cir
```

### 2. AC Fazör Analizi
```bash
python3 devre_cozucu/main.py devre_cozucu/ornekler/rc_alcak_geciren.cir
python3 devre_cozucu/main.py devre_cozucu/ornekler/rlc_rezonans.cir --matris
```

### 3. Geçici (Transient) Analiz
```bash
python3 devre_cozucu/main.py devre_cozucu/ornekler/rc_basamak.cir --ciz 2
python3 devre_cozucu/main.py devre_cozucu/ornekler/rlc_basamak.cir --ciz 3 --svg rlc.svg
```

### 4. Laplace Sembolik Transfer Fonksiyonu $H(s)$
```bash
python3 devre_cozucu/main.py devre_cozucu/ornekler/rc_alcak_geciren.cir --laplace 2
python3 devre_cozucu/main.py devre_cozucu/ornekler/rlc_rezonans.cir --laplace 3
```

### 5. Resimden Netlist ve Çözüm
```bash
# Örnek şema PNG'si oluşturup piksel tel takibi (BFS) ile netlist çıkar ve çöz:
python3 devre_cozucu/main.py --ornek-sema gerilim_bolucu --dogrula
python3 devre_cozucu/main.py --ornek-sema rc_filtre --ac 159.155

# Vision API ile dışarıdan bir devre fotoğrafını çözmek için:
python3 devre_cozucu/main.py --resim devre_fotografi.jpg
```

---

## 🧪 Testleri Çalıştırma

Tüm 34 birim testi çalıştırmak için:
```bash
python3 -m unittest discover -s devre_cozucu -v
```
