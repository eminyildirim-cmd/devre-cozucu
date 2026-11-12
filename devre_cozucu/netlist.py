"""
Netlist okuyucu (parser).

Netlist, devreyi metin olarak tarif eder. Her satır bir eleman:

    <İsim> <düğüm+> <düğüm-> <değer> [AC <genlik> [faz]]

    R1  1  2  1k          -> 1 ile 2 arasında 1 kΩ direnç
    C1  2  0  10u         -> 2 ile 0 arasında 10 µF kapasitör
    L1  2  3  5m          -> 2 ile 3 arasında 5 mH indüktör (bobin)
    V1  1  0  5           -> DC 5 V gerilim kaynağı
    V2  1  0  AC 10       -> 10 V tepe genlikli, 0° fazlı AC gerilim kaynağı
    V3  1  0  AC 10 45    -> 10 V tepe genlikli, 45° fazlı AC gerilim kaynağı
    I1  0  2  2m          -> 2 mA akım kaynağı; 0'dan 2'ye akar (2'ye akım basar)
    I2  0  2  AC 5m -90   -> 5 mA, -90° fazlı AC akım kaynağı

Simülasyon komutları:
    .ac 1k                -> 1 kHz frekansta AC analizi
    .ac freq=1000         -> 1000 Hz frekansta AC analizi

Elemanın türü ismin ilk harfinden anlaşılır (SPICE geleneği):
    R = direnç, C = kapasitör, L = bobin/indüktör
    V = bağımsız gerilim kaynağı, I = bağımsız akım kaynağı

Düğüm "0" veya "gnd" toprak (referans, 0 V) kabul edilir.
'*' ile başlayan satırlar ve ';' sonrası yorumdur.
"""

from dataclasses import dataclass
import re

TOPRAK_ISIMLERI = {"0", "gnd", "GND"}

# SI önekleri. SPICE'ta 'M' = mili, 'MEG' = mega; karışıklık olmasın diye ikisini de destekliyoruz.
ONEKLER = {
    "t": 1e12,
    "g": 1e9,
    "meg": 1e6,
    "k": 1e3,
    "m": 1e-3,
    "u": 1e-6,
    "µ": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
    "f": 1e-15,
}


def deger_oku(metin: str) -> float:
    """'1k' -> 1000.0, '4.7u' -> 4.7e-6, '2meg' -> 2e6, '10' -> 10.0

    Sondaki birim harfleri yok sayılır: '1kohm', '5V', '2mA', '10uF', '5mH' de çalışır.
    """
    s = metin.strip().lower()
    # Sayısal kısmı ayır
    i = 0
    while i < len(s) and (s[i].isdigit() or s[i] in ".+-e"):
        # 'e' üs gösterimi olabilir (1e3), ama 'e' ardından rakam/işaret gelmeli
        if s[i] == "e" and not (i + 1 < len(s) and (s[i + 1].isdigit() or s[i + 1] in "+-")):
            break
        i += 1
    sayi_kismi, ek = s[:i], s[i:]
    if not sayi_kismi:
        raise ValueError(f"Geçersiz değer: '{metin}'")
    sayi = float(sayi_kismi)

    # Önce 3 harfli 'meg', sonra tek harfli önekler
    if ek.startswith("meg"):
        return sayi * ONEKLER["meg"]
    if ek and ek[0] in ONEKLER:
        return sayi * ONEKLER[ek[0]]
    return sayi  # önek yok (örn. '5', '5v', '10ohm')


@dataclass
class Eleman:
    isim: str               # "R1", "C1", "L1", "V1", "I1"
    tur: str                # "R", "C", "L", "V", "I"
    dugum_p: str            # + düğüm (veya 1. uç)
    dugum_n: str            # - düğüm (veya 2. uç)
    deger: float            # R (Ω), C (F), L (H) veya DC değer (V/A)
    ac_genlik: float = 0.0  # AC tepe genliği (V veya A)
    ac_faz: float = 0.0     # AC faz açısı (derece, varsayılan 0°)

    def __str__(self):
        if self.tur in ("V", "I") and self.ac_genlik > 0:
            faz_str = f"∠{self.ac_faz:g}°" if self.ac_faz != 0 else ""
            return f"{self.isim} ({self.dugum_p} → {self.dugum_n}) = DC {self.deger:g}, AC {self.ac_genlik:g}{faz_str}"
        return f"{self.isim} ({self.dugum_p} → {self.dugum_n}) = {self.deger:g}"


class Netlist(list):
    """Elemanlar listesi ve devrenin simülasyon parametreleri (örn. AC frekansı).

    Normal bir Python listesi gibi davranır, geriye dönük tam uyumludur.
    """
    def __init__(self, elemanlar=None, frekans: float | None = None):
        super().__init__(elemanlar or [])
        self.frekans = frekans


DESTEKLENEN_TURLER = {"R", "V", "I", "C", "L"}


def dugum_normalle(d: str) -> str:
    return "0" if d in TOPRAK_ISIMLERI else d


def netlist_oku(metin: str) -> Netlist:
    elemanlar = []
    isimler = set()
    devre_frekans: float | None = None

    for satir_no, satir in enumerate(metin.splitlines(), start=1):
        satir = satir.split(";")[0].strip()
        if not satir or satir.startswith("*"):
            continue

        # SPICE komutları: .ac 1k, .ac freq=1000, .freq 50
        if satir.startswith("."):
            kucuk = satir.lower()
            if kucuk.startswith(".ac") or kucuk.startswith(".freq"):
                parcalar = kucuk.split()
                for p in parcalar[1:]:
                    if p in ("lin", "dec", "oct"):
                        continue
                    if "=" in p:
                        p = p.split("=")[1]
                    try:
                        devre_frekans = deger_oku(p)
                        break
                    except ValueError:
                        continue
            continue

        parcalar = satir.split()
        if len(parcalar) < 4:
            raise ValueError(f"Satır {satir_no}: En az 4 alan bekleniyordu (isim d+ d- değer): '{satir}'")

        isim, dp, dn = parcalar[0], parcalar[1], parcalar[2]
        tur = isim[0].upper()
        if tur not in DESTEKLENEN_TURLER:
            raise ValueError(f"Satır {satir_no}: '{tur}' türü henüz desteklenmiyor (R, C, L, V, I var)")
        if isim.upper() in isimler:
            raise ValueError(f"Satır {satir_no}: '{isim}' ismi iki kez kullanılmış")
        isimler.add(isim.upper())

        dp_norm = dugum_normalle(dp)
        dn_norm = dugum_normalle(dn)

        # Değer ve AC parametrelerinin ayrıştırılması
        kalan = parcalar[3:]
        deger = 0.0
        ac_genlik = 0.0
        ac_faz = 0.0

        if tur in ("R", "C", "L"):
            if len(kalan) != 1:
                raise ValueError(f"Satır {satir_no}: {tur} elemanı için yalnızca tek bir değer bekleniyordu: '{satir}'")
            deger = deger_oku(kalan[0])
            if deger <= 0:
                tur_ad = "direnç" if tur == "R" else ("kapasitans" if tur == "C" else "indüktans")
                raise ValueError(f"Satır {satir_no}: {tur_ad} pozitif olmalı")

        elif tur in ("V", "I"):
            # Olası formatlar:
            # 1) V1 1 0 10             -> DC 10 (AC analizde de 10 V kabul edilebilir)
            # 2) V1 1 0 AC 10          -> AC 10, faz 0
            # 3) V1 1 0 AC 10 45       -> AC 10, faz 45
            # 4) V1 1 0 DC 5 AC 10 30  -> DC 5, AC 10, faz 30
            # 5) V1 1 0 5 AC 10 30     -> DC 5, AC 10, faz 30
            idx = 0
            while idx < len(kalan):
                token = kalan[idx].upper()
                if token == "DC":
                    idx += 1
                    if idx < len(kalan):
                        deger = deger_oku(kalan[idx])
                        idx += 1
                elif token == "AC":
                    idx += 1
                    if idx < len(kalan):
                        ac_genlik = deger_oku(kalan[idx])
                        idx += 1
                    if idx < len(kalan) and kalan[idx].upper() not in ("DC", "AC"):
                        # Sonraki token faz açısıdır (örn. 45 veya -90)
                        ac_faz = float(kalan[idx])
                        idx += 1
                else:
                    # 'DC' veya 'AC' anahtar kelimesi olmadan doğrudan sayı geldiyse
                    deger = deger_oku(kalan[idx])
                    idx += 1

        e = Eleman(
            isim=isim,
            tur=tur,
            dugum_p=dp_norm,
            dugum_n=dn_norm,
            deger=deger,
            ac_genlik=ac_genlik,
            ac_faz=ac_faz,
        )
        elemanlar.append(e)

    if not elemanlar:
        raise ValueError("Netlist boş")
    if not any("0" in (e.dugum_p, e.dugum_n) for e in elemanlar):
        raise ValueError("Devrede toprak düğümü (0 veya gnd) yok")

    return Netlist(elemanlar, frekans=devre_frekans)
