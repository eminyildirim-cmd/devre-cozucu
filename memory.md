# Devre Çözücü — Yol Haritası ve Proje Hafızası

> **Not:** Bu dosya `~/.claude/projects/.../memory/devre-cozucu-yol-haritasi.md` hafıza dosyası ile senkronizedir. Proje dizininde de doğrudan görebilmeniz için buraya eklenmiştir.

## Proje Amacı
Devre Analizi dersi ve Circuits & Systems uzmanlaşması kapsamında:
**Devre fotoğrafı → netlist / graf → MNA çözücü → düğüm voltajları, akımlar, güç dengesi, transfer fonksiyonu ve doğrulama.**

---

## Yol Haritası ve İlerleme Durumu

### [x] Aşama 1: DC MNA Çözücü (Tamamlandı)
* `R`, `V`, `I` elemanları için damga (stamp) yöntemi.
* Süper düğüm (bağımsız gerilim kaynakları) desteği.
* Güç dengesi (Tellegen teoremi $\sum P = 0$) kontrolü.

---

### [x] Aşama 2: AC (Fazör), C/L, Bağımlı Kaynaklar, Geçici Analiz ve Laplace (Tamamlandı)
* [x] **2.1 AC (Fazör) MNA Çözücü:**
  * `C` ve `L` admittans damgaları ($Y_C = j\omega C$, $Y_L = \frac{1}{j\omega L}$), karmaşık lineer sistem çözümü, polar/kartezyen/RMS çıktılar ve AC Tellegen güç dengesi ($\sum S = 0$).
* [x] **2.2 Bağımlı Kaynaklar:**
  * VCVS (`E`), VCCS (`G`), CCVS (`H`), CCCS (`F`) damgaları ve Op-Amp modelleri.
* [x] **2.3 Geçici (Transient) Analiz:**
  * Sayısal integrasyon (Yamuk Kuralı - Trapezoidal Companion Model), konsolda ASCII grafik ve vektörel SVG grafik kaydetme.
* [x] **2.4 Laplace / Sembolik Transfer Fonksiyonu $H(s)$:**
  * s-domeni rasyonel polinom aritmetiği ile $H(s) = N(s)/D(s)$ türetimi, kutup-sıfır (Poles & Zeros), kararlılık analizi, DC kazancı ve 2. derece parametreler ($\omega_0, Q, \zeta$).

---

### [x] Aşama 3: Resimden Netlist — Vision API + BFS Piksel Tel İzleme (Tamamlandı)
* `devre_cozucu/resimden_netlist.py`:
  * **Yaklaşım 1 (Vision API):** Anthropic Claude Vision (`ANTHROPIC_API_KEY`) ve Google Gemini Vision (`GEMINI_API_KEY`) ile devre fotoğrafından doğrudan SPICE netlist çıkarma (`--resim sema.jpg`).
  * **Yaklaşım 2 (YOLO Kutuları + BFS Piksel Tel Takibi):**
    1. Görüntüyü eşikleme (thresholding) ile ikili (siyah-beyaz) matrise dönüştürme.
    2. Eleman sınır kutularını (bounding box) maskeleyip yalnızca bağlantı kablolarını bırakma.
    3. 8-komşuluklu Genişlik Öncelikli Arama (BFS / Connected Components) ile her tel ağını tek bir elektriksel düğüm olarak etiketleme.
    4. Toprak (`GND`) sembolünü `0` düğümüne eşleme ve her elemanın `+`/`-` terminallerini düğümlerle birleştirerek otomatik SPICE netlist üretme.
  * **Sentetik Şema Üretici:** `Pillow` ile gerçek PNG devre şemaları (`sema_gerilim_bolucu.png`, `sema_rc_filtre.png`) çizip uçtan uca görüntüden MNA çözümüne (`--ornek-sema`) doğrulama.

---

### [x] Aşama 4: ngspice ve Fiziksel KCL/KVL Doğrulaması (Tamamlandı)
* `devre_cozucu/ngspice_dogrula.py`:
  * Otomatik `ngspice` toplu iş (batch `.op` / `.control`) betiği üretimi ve çıktı ayrıştırıcısı.
  * Sistemde `ngspice` kuruluysa doğrudan alt süreç olarak çalıştırıp düğüm voltajlarını çapraz karşılaştırma; kurulu değilse bağımsız Kirchhoff Akımlar Yasası ($\sum I = 0$) ve Kirchhoff Gerilimler Yasası / Ohm bünye denklemleriyle sıfır toleranslı doğrulama (`--dogrula`).

* **Toplam Birim Test Sayısı: 34/34 Başarılı.**
