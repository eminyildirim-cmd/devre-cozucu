"""
Netlist okuyucu (parser).

Netlist, devreyi metin olarak tarif eder. Desteklenen elemanlar:

    Pasif Elemanlar:
        R1  1  2  1k              -> 1 kΩ direnç
        C1  2  0  10u             -> 10 µF kapasitör
        L1  2  3  5m              -> 5 mH bobin

    Bağımsız Kaynaklar:
        V1  1  0  5               -> DC 5 V gerilim kaynağı
        V2  1  0  AC 10 45        -> AC 10 V (tepe), 45° fazlı kaynak
        I1  0  2  2m              -> 2 mA akım kaynağı (0 -> 2 yönünde)
        I2  0  2  AC 5m -90       -> AC 5 mA, -90° fazlı kaynak

    Bağımlı Kaynaklar (SPICE standardı):
        E1  out+ out- in+ in- kazanc   -> VCVS: Gerilim Kontrollü Gerilim Kaynağı: V(out) = kazanc · V(in)
        G1  out+ out- in+ in- gm       -> VCCS: Gerilim Kontrollü Akım Kaynağı:    I(out) = gm · V(in)
        H1  out+ out- Vsens r          -> CCVS: Akım Kontrollü Gerilim Kaynağı:   V(out) = r · I(Vsens)
        F1  out+ out- Vsens beta       -> CCCS: Akım Kontrollü Akım Kaynağı:      I(out) = beta · I(Vsens)

    Simülasyon Komutları:
        .ac 1k                    -> 1 kHz AC analizi

Düğüm "0" veya "gnd" toprak kabul edilir.
'*' ile başlayan satırlar ve ';' sonrası yorumdur.
"""

from dataclasses import dataclass

TOPRAK_ISIMLERI = {"0", "gnd", "GND"}

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
    """'1k' -> 1000.0, '4.7u' -> 4.7e-6, '2meg' -> 2e6, '10' -> 10.0"""
    s = metin.strip().lower()
    i = 0
    while i < len(s) and (s[i].isdigit() or s[i] in ".+-e"):
        if s[i] == "e" and not (i + 1 < len(s) and (s[i + 1].isdigit() or s[i + 1] in "+-")):
            break
        i += 1
    sayi_kismi, ek = s[:i], s[i:]
    if not sayi_kismi:
        raise ValueError(f"Geçersiz değer: '{metin}'")
    sayi = float(sayi_kismi)

    if ek.startswith("meg"):
        return sayi * ONEKLER["meg"]
    if ek and ek[0] in ONEKLER:
        return sayi * ONEKLER[ek[0]]
    return sayi


@dataclass
class Eleman:
    isim: str               # "R1", "C1", "L1", "V1", "I1", "E1", "G1", "H1", "F1"
    tur: str                # "R", "C", "L", "V", "I", "E", "G", "H", "F"
    dugum_p: str            # + düğüm
    dugum_n: str            # - düğüm
    deger: float            # R, C, L, V/I DC değeri veya bağımlı kaynak kazancı (μ, gm, r, β)
    ac_genlik: float = 0.0  # AC tepe genliği
    ac_faz: float = 0.0     # AC faz açısı (derece)
    kontrol_p: str = ""     # E ve G için kontrol + düğümü
    kontrol_n: str = ""     # E ve G için kontrol - düğümü
    kontrol_kaynak: str = ""  # H ve F için kontrol gerilim kaynağı adı

    def __str__(self):
        if self.tur in ("E", "G"):
            tur_ad = "VCVS" if self.tur == "E" else "VCCS"
            return f"{self.isim} ({self.dugum_p} → {self.dugum_n}) = {self.deger:g} × V({self.kontrol_p},{self.kontrol_n}) [{tur_ad}]"
        elif self.tur in ("H", "F"):
            tur_ad = "CCVS" if self.tur == "H" else "CCCS"
            return f"{self.isim} ({self.dugum_p} → {self.dugum_n}) = {self.deger:g} × I({self.kontrol_kaynak}) [{tur_ad}]"
        elif self.tur in ("V", "I") and self.ac_genlik > 0:
            faz_str = f"∠{self.ac_faz:g}°" if self.ac_faz != 0 else ""
            return f"{self.isim} ({self.dugum_p} → {self.dugum_n}) = DC {self.deger:g}, AC {self.ac_genlik:g}{faz_str}"
        return f"{self.isim} ({self.dugum_p} → {self.dugum_n}) = {self.deger:g}"


class Netlist(list):
    def __init__(self, elemanlar=None, frekans: float | None = None):
        super().__init__(elemanlar or [])
        self.frekans = frekans


DESTEKLENEN_TURLER = {"R", "V", "I", "C", "L", "E", "G", "H", "F"}


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
            raise ValueError(f"Satır {satir_no}: En az 4 alan bekleniyordu: '{satir}'")

        isim = parcalar[0]
        tur = isim[0].upper()
        if tur not in DESTEKLENEN_TURLER:
            raise ValueError(f"Satır {satir_no}: '{tur}' türü desteklenmiyor. (Desteklenenler: {', '.join(sorted(DESTEKLENEN_TURLER))})")
        if isim.upper() in isimler:
            raise ValueError(f"Satır {satir_no}: '{isim}' ismi iki kez kullanılmış")
        isimler.add(isim.upper())

        dp = dugum_normalle(parcalar[1])
        dn = dugum_normalle(parcalar[2])

        kontrol_p = ""
        kontrol_n = ""
        kontrol_kaynak = ""
        deger = 0.0
        ac_genlik = 0.0
        ac_faz = 0.0

        if tur in ("R", "C", "L"):
            if len(parcalar) != 4:
                raise ValueError(f"Satır {satir_no}: {tur} elemanı için 4 alan bekleniyordu (isim d+ d- deger): '{satir}'")
            deger = deger_oku(parcalar[3])
            if deger <= 0:
                tur_ad = "direnç" if tur == "R" else ("kapasitans" if tur == "C" else "indüktans")
                raise ValueError(f"Satır {satir_no}: {tur_ad} pozitif olmalı")

        elif tur in ("E", "G"):
            # Format: E1 out+ out- in+ in- kazanc  (6 alan)
            if len(parcalar) != 6:
                raise ValueError(f"Satır {satir_no}: {tur} (VCVS/VCCS) için 6 alan bekleniyordu (isim d+ d- in+ in- kazanc): '{satir}'")
            kontrol_p = dugum_normalle(parcalar[3])
            kontrol_n = dugum_normalle(parcalar[4])
            deger = deger_oku(parcalar[5])

        elif tur in ("H", "F"):
            # Format: H1 out+ out- Vkontrol kazanc  (5 alan)
            if len(parcalar) != 5:
                raise ValueError(f"Satır {satir_no}: {tur} (CCVS/CCCS) için 5 alan bekleniyordu (isim d+ d- Vkontrol kazanc): '{satir}'")
            kontrol_kaynak = parcalar[3]
            deger = deger_oku(parcalar[4])

        elif tur in ("V", "I"):
            kalan = parcalar[3:]
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
                        ac_faz = float(kalan[idx])
                        idx += 1
                else:
                    deger = deger_oku(kalan[idx])
                    idx += 1

        e = Eleman(
            isim=isim,
            tur=tur,
            dugum_p=dp,
            dugum_n=dn,
            deger=deger,
            ac_genlik=ac_genlik,
            ac_faz=ac_faz,
            kontrol_p=kontrol_p,
            kontrol_n=kontrol_n,
            kontrol_kaynak=kontrol_kaynak,
        )
        elemanlar.append(e)

    if not elemanlar:
        raise ValueError("Netlist boş")
    if not any("0" in (e.dugum_p, e.dugum_n) for e in elemanlar):
        raise ValueError("Devrede toprak düğümü (0 veya gnd) yok")

    return Netlist(elemanlar, frekans=devre_frekans)
