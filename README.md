# Devre Çözücü (Circuit Solver) — MNA

Devre Analizi ve *Circuits & Systems* çalışmaları için geliştirilmiş, **Değiştirilmiş Düğüm Analizi (Modified Nodal Analysis - MNA)** tabanlı devre simülatörü.

SPICE formatında netlist dosyalarını okuyarak DC, AC (fazör), Geçici (transient) ve Laplace sembolik transfer fonksiyonu analizlerini adım adım damga (stamp) yöntemiyle çözer.

---

## 🚀 Özellikler

* **DC Analizi:**
  * Direnç (`R`), Bağımsız Gerilim Kaynakları (`V`), Bağımsız Akım Kaynakları (`I`).
  * Süper düğüm desteği (kaynak akımlarını ekstra bilinmeyen olarak matrise ekler).
  * Tellegen güç dengesi doğrulaması ($\sum P = 0$).
* **AC (Fazör) Analizi:**
  * Kapasitör (`C`) ve Bobin (`L`) admittans damgaları ($Y_C = j\omega C$, $Y_L = 1/j\omega L$).
  * AC genlik ve faz açısı (`AC <genlik> <faz>`).
  * Karmaşık lineer sistem çözümü: $A(\omega) \cdot x(\omega) = z(\omega)$.
  * Kutupsal (Polar: $|V|\angle\theta^\circ$), Kartezyen ($a+jb$) ve RMS gösterimi.
  * Aktif güç ($P$), Reaktif güç ($Q$) ve AC Tellegen güç dengesi ($\sum S = 0$).
* **Bağımlı Kaynaklar (Tüm 4 Tür):**
  * **VCVS (`E`):** Gerilim Kontrollü Gerilim Kaynağı ($V = \mu \cdot V_{in}$) — İdeal ve kazançlı Op-Amp modelleri.
  * **VCCS (`G`):** Gerilim Kontrollü Akım Kaynağı ($I = g_m \cdot V_{in}$) — BJT ve MOSFET küçük işaret modelleri.
  * **CCVS (`H`):** Akım Kontrollü Gerilim Kaynağı ($V = r \cdot I_{sens}$).
  * **CCCS (`F`):** Akım Kontrollü Akım Kaynağı ($I = \beta \cdot I_{sens}$) — BJT akım kazancı modelleri.
* **Geçici (Transient) Analiz:**
  * Sayısal integrasyon (Yamuk Kuralı - Trapezoidal Companion Model).
  * Sabit zaman adımı ile tek seferlik matris çarpanlarına ayırma ve ultra hızlı simülasyon.
  * Basamak ve Sinüzoidal (`SIN(...)`) kaynak desteği.
  * Konsolda doğrudan **ASCII dalga şekli çizimi**.
  * Harici kütüphane gerektirmeyen vektörel **SVG grafik çıktısı**.
* **Laplace / Sembolik Transfer Fonksiyonu $H(s)$:**
  * Sembolik s-domeni MNA matrisi ve rasyonel polinom aritmetiği ile analitik transfer fonksiyonu $H(s) = \frac{N(s)}{D(s)}$ türetimi.
  * Otomatik **Kutup ve Sıfır (Poles & Zeros)** tespiti.
  * **Kararlılık analizi** (Sol yarı s-düzlemi kontrolü).
  * DC Kazancı ($H(0)$ ve dB değeri).
  * 2. dereceden filtre parametreleri: Doğal frekans ($\omega_0$), sönüm oranı ($\zeta$), kalite faktörü ($Q$).

---

## 🛠️ Kurulum ve Gereksinimler

Proje yalnızca Python 3 ve `numpy` gerektirir:

```bash
pip install numpy
```

---

## 💻 Kullanım

### 1. DC Analizi
```bash
python3 devre_cozucu/main.py devre_cozucu/ornekler/gerilim_bolucu.cir
```
Op-Amp Evirmeyen Yükselteç devresi örneği:
```bash
python3 devre_cozucu/main.py devre_cozucu/ornekler/opamp_evirmeyen_kuvvetlendirici.cir
```

### 2. AC Fazör Analizi
```bash
# RC Alçak Geçiren Filtre analizi:
python3 devre_cozucu/main.py devre_cozucu/ornekler/rc_alcak_geciren.cir

# RLC Rezonans analizi ve AC MNA matrisi:
python3 devre_cozucu/main.py devre_cozucu/ornekler/rlc_rezonans.cir --matris
```

### 3. Geçici (Transient) Analiz
```bash
# RC devresi basamak yanıtı (Terminalde ASCII grafik):
python3 devre_cozucu/main.py devre_cozucu/ornekler/rc_basamak.cir --ciz 2

# RLC az sönümlü salınım ve SVG dosya çıktısı:
python3 devre_cozucu/main.py devre_cozucu/ornekler/rlc_basamak.cir --ciz 3 --svg rlc.svg
```

### 4. Laplace Sembolik Transfer Fonksiyonu $H(s)$
```bash
# RC Filtre transfer fonksiyonu ve kutup-sıfır analizi:
python3 devre_cozucu/main.py devre_cozucu/ornekler/rc_alcak_geciren.cir --laplace 2

# RLC 2. derece transfer fonksiyonu, rezonans, Q ve sönüm:
python3 devre_cozucu/main.py devre_cozucu/ornekler/rlc_rezonans.cir --laplace 3
```

---

## 🧪 Testleri Çalıştırma

Tüm 29 birim testi çalıştırmak için:
```bash
python3 -m unittest discover -s devre_cozucu -v
```

---

## 📁 Proje Yapısı

```text
├── devre_cozucu/
│   ├── netlist.py          # Netlist ayrıştırıcı (parser)
│   ├── mna.py              # DC ve AC MNA çözücü motoru
│   ├── transient.py        # Geçici analiz ve grafik çizici
│   ├── laplace.py          # s-domeni sembolik transfer fonksiyonu ve kutup-sıfır motoru
│   ├── main.py             # Komut satırı arayüzü ve raporlama
│   ├── test_mna.py         # Otomatik birim testler (29 test)
│   └── ornekler/           # Örnek SPICE devre dosyaları (.cir)
│       ├── gerilim_bolucu.cir
│       ├── kopru.cir
│       ├── super_dugum.cir
│       ├── rc_alcak_geciren.cir
│       ├── rlc_rezonans.cir
│       ├── opamp_evirmeyen_kuvvetlendirici.cir
│       ├── rc_basamak.cir
│       └── rlc_basamak.cir
├── memory.md               # Proje yol haritası ve ilerleme notları
└── README.md
```
