# Devre Çözücü — Yol Haritası ve Proje Hafızası

> **Not:** Bu dosya `~/.claude/projects/.../memory/devre-cozucu-yol-haritasi.md` hafıza dosyası ile senkronizedir. Proje dizininde de doğrudan görebilmeniz için buraya eklenmiştir.

## Proje Amacı
Devre Analizi dersi ve Circuits & Systems uzmanlaşması kapsamında:
**Devre fotoğrafı → netlist / graf → MNA çözücü → düğüm voltajları, akımlar, güç dengesi.**

---

## Yol Haritası ve İlerleme Durumu

### [x] Aşama 1: DC MNA Çözücü (Tamamlandı)
* `R`, `V`, `I` elemanları için damga (stamp) yöntemi.
* Süper düğüm (bağımsız gerilim kaynakları) desteği.
* Güç dengesi (Tellegen teoremi $\sum P = 0$) kontrolü.
* 13 birim test.

---

### [ ] Aşama 2: AC (Fazör), C/L, Bağımlı Kaynaklar ve Geçici Analiz (Devam Ediyor)
* [x] **2.1 AC (Fazör) MNA Çözücü (Tamamlandı):**
  * `C` (Kapasitör) ve `L` (Bobin) admittans damgaları ($Y_C = j\omega C$, $Y_L = \frac{1}{j\omega L}$).
  * AC gerilim ve akım kaynakları (genlik + faz açısı: `AC <genlik> <faz>`).
  * Netlist frekans komutu (`.ac <frekans>`).
  * Karmaşık lineer sistem çözümü: $A(\omega) \cdot x(\omega) = z(\omega)$.
  * Kutupsal (Polar: $|V|\angle\theta^\circ$) ve Kartezyen ($a+jb$) gösterim.
  * RMS değerleri ($V_{rms} = |V|/\sqrt{2}$).
  * Karmaşık güç hesabı: $S = \frac{1}{2} V I^* = P + jQ$ (Aktif Watt + Reaktif VAR).
  * Tellegen AC güç dengesi doğrulandı ($\sum S = 0$).
  * RC Alçak Geçiren Filtre ve Seri RLC Rezonans örnekleri eklendi.
* [x] **2.2 Bağımlı Kaynaklar (Tamamlandı):**
  * VCVS (`E`): Gerilim kontrollü gerilim kaynağı ($V = \mu \cdot V_{in}$).
  * VCCS (`G`): Gerilim kontrollü akım kaynağı ($I = g_m \cdot V_{in}$).
  * CCVS (`H`): Akım kontrollü gerilim kaynağı ($V = r \cdot I_{sens}$).
  * CCCS (`F`): Akım kontrollü akım kaynağı ($I = \beta \cdot I_{sens}$).
  * Op-Amp (İşlemsel Kuvvetlendirici) evirmeyen yükselteç devresi örneği eklendi ($A_v = 10$).
  * Toplam birim test sayısı: **23/23 Başarılı**.
* [ ] **2.3 Geçici (Transient) Analiz (Sıradaki Adım):**
  * Zaman domeninde sayısal çözümleme ($t = 0 \to t_{dur}$) ve dalga şekli grafikleri (`matplotlib`).
* [ ] **2.4 Laplace / SymPy:**
  * Sembolik transfer fonksiyonu $H(s)$ ve kutup-sıfır analizi.

---

### [ ] Aşama 3: Resimden Netlist (Görüntü İşleme / OCR)
* Claude Vision API ile devre şemasından netlist prototipi.
* İsteğe bağlı YOLO devre elemanı tespiti (CGHD veri seti).

---

### [ ] Aşama 4: ngspice ile Doğrulama
* Çözücünün ürettiği sonuçların `ngspice` simülatörü ile otomatik çapraz doğrulanması.
