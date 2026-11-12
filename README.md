# Devre Çözücü (Circuit Solver) — MNA

Devre Analizi ve *Circuits & Systems* çalışmaları için geliştirilmiş, **Değiştirilmiş Düğüm Analizi (Modified Nodal Analysis - MNA)** tabanlı devre simülatörü.

SPICE formatında netlist dosyalarını okuyarak DC ve AC (fazör) analizlerini adım adım damga (stamp) yöntemiyle çözer.

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
* **Bağımlı Kaynaklar (Geliştiriliyor):**
  * VCVS (`E`), VCCS (`G`), CCVS (`H`), CCCS (`F`).
* **Resimden Netlist (Geliştirilecek):**
  * Devre şeması fotoğrafından netlist üretimi ve ngspice doğrulaması.

---

## 🛠️ Kurulum ve Gereksinimler

Proje yalnızca Python 3 ve `numpy` gerektirir:

```bash
pip install numpy
```

---

## 💻 Kullanım

### 1. DC Analizi Çalıştırma
```bash
python3 devre_cozucu/main.py devre_cozucu/ornekler/gerilim_bolucu.cir
```
MNA matrisini de görmek için `--matris` parametresini ekleyebilirsiniz:
```bash
python3 devre_cozucu/main.py devre_cozucu/ornekler/kopru.cir --matris
```

### 2. AC Fazör Analizi Çalıştırma
```bash
# RC Alçak Geçiren Filtre analizi:
python3 devre_cozucu/main.py devre_cozucu/ornekler/rc_alcak_geciren.cir

# RLC Rezonans analizi ve AC MNA matrisi:
python3 devre_cozucu/main.py devre_cozucu/ornekler/rlc_rezonans.cir --matris
```

---

## 🧪 Testleri Çalıştırma

Tüm birim testleri çalıştırmak için:
```bash
python3 -m unittest discover -s devre_cozucu -v
```

---

## 📁 Proje Yapısı

```text
├── devre_cozucu/
│   ├── netlist.py          # Netlist ayrıştırıcı (parser)
│   ├── mna.py              # DC ve AC MNA çözücü motoru
│   ├── main.py             # Komut satırı arayüzü ve raporlama
│   ├── test_mna.py         # Otomatik birim testler (19 test)
│   └── ornekler/           # Örnek SPICE devre dosyaları (.cir)
│       ├── gerilim_bolucu.cir
│       ├── kopru.cir
│       ├── super_dugum.cir
│       ├── rc_alcak_geciren.cir
│       └── rlc_rezonans.cir
├── memory.md               # Proje yol haritası ve ilerleme notları
└── README.md
```
