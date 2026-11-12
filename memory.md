# Devre Çözücü — Yol Haritası ve Proje Hafızası

> **Not:** Bu dosya `~/.claude/projects/.../memory/devre-cozucu-yol-haritasi.md` hafıza dosyası ile senkronizedir. Proje dizininde de doğrudan görebilmeniz için buraya eklenmiştir.

## Proje Amacı
Devre Analizi dersi ve Circuits & Systems uzmanlaşması kapsamında:
**Devre fotoğrafı → netlist / graf → MNA çözücü → düğüm voltajları, akımlar, güç dengesi, transfer fonksiyonu.**

---

## Yol Haritası ve İlerleme Durumu

### [x] Aşama 1: DC MNA Çözücü (Tamamlandı)
* `R`, `V`, `I` elemanları için damga (stamp) yöntemi.
* Süper düğüm (bağımsız gerilim kaynakları) desteği.
* Güç dengesi (Tellegen teoremi $\sum P = 0$) kontrolü.
* 13 birim test.

---

### [x] Aşama 2: AC (Fazör), C/L, Bağımlı Kaynaklar, Geçici Analiz ve Laplace (Tamamlandı)
* [x] **2.1 AC (Fazör) MNA Çözücü:**
  * `C` (Kapasitör) ve `L` (Bobin) admittans damgaları ($Y_C = j\omega C$, $Y_L = \frac{1}{j\omega L}$).
  * AC gerilim ve akım kaynakları (genlik + faz açısı: `AC <genlik> <faz>`).
  * Netlist frekans komutu (`.ac <frekans>`).
  * Karmaşık lineer sistem çözümü: $A(\omega) \cdot x(\omega) = z(\omega)$.
  * Kutupsal (Polar: $|V|\angle\theta^\circ$) ve Kartezyen ($a+jb$) gösterim, RMS değerleri.
  * Karmaşık güç hesabı: $S = P + jQ$ ve Tellegen AC güç dengesi ($\sum S = 0$).
* [x] **2.2 Bağımlı Kaynaklar:**
  * VCVS (`E`): Gerilim kontrollü gerilim kaynağı ($V = \mu \cdot V_{in}$).
  * VCCS (`G`): Gerilim kontrollü akım kaynağı ($I = g_m \cdot V_{in}$).
  * CCVS (`H`): Akım kontrollü gerilim kaynağı ($V = r \cdot I_{sens}$).
  * CCCS (`F`): Akım kontrollü akım kaynağı ($I = \beta \cdot I_{sens}$).
  * İdeal ve kazançlı Op-Amp modelleri ($A_v = 10$).
* [x] **2.3 Geçici (Transient) Analiz:**
  * Sayısal integrasyon (Yamuk Kuralı - Trapezoidal Companion Model).
  * Sabit zaman adımı ile ultra hızlı simülasyon.
  * Konsolda doğrudan **ASCII dalga şekli çizimi**.
  * Harici kütüphane gerektirmeyen vektörel **SVG grafik kaydetme**.
* [x] **2.4 Laplace / Sembolik Transfer Fonksiyonu $H(s)$:**
  * s-domeni sembolik MNA matrisi $A(s) \cdot X(s) = Z(s)$.
  * Rasyonel polinom aritmetiği ve Gauss eliminasyonu ile $H(s) = N(s)/D(s)$ türetimi.
  * Otomatik kutup-sıfır analizi (Poles & Zeros).
  * Kararlılık denetimi (sol yarı s-düzlemi kontrolü).
  * DC kazancı ($H(0)$ ve dB cinsinden karşılığı).
  * 2. dereceden sistem parametreleri: doğal frekans ($\omega_0$), sönüm oranı ($\zeta$), kalite faktörü ($Q$).
* **Toplam Birim Test Sayısı: 29/29 Başarılı.**

---

### [ ] Aşama 3: Resimden Netlist (Sıradaki Aşama)
* Claude Vision API ile el çizimi / ders kitabı devre şeması fotoğrafından netlist prototipi.
* İsteğe bağlı YOLO ile devre elemanları ve bağlantı düğümleri tespiti (CGHD veri seti).
* Görüntüden elde edilen netlist'in otomatik olarak MNA çözücüye beslenmesi.

---

### [ ] Aşama 4: ngspice ile Doğrulama
* Çözücünün ürettiği sonuçların `ngspice` simülatörü ile otomatik çapraz doğrulanması.
