"""
MNA — Modified Nodal Analysis (Değiştirilmiş Düğüm Analizi)

FİKİR
-----
Klasik düğüm analizinde her düğüme KCL yazarız: "çıkan akımların toplamı = 0".
Bilinmeyenler düğüm voltajlarıdır. Ama gerilim kaynağının akımı voltajla ifade
edilemez (I = ? ; kaynak her akımı verebilir). Klasik çözüm "süper düğüm"dür.

MNA daha sistematik bir yol izler: her gerilim kaynağının akımını da EKSTRA
BİLİNMEYEN yapar ve her kaynak için bir ekstra denklem ekler: V(+) - V(-) = E.

Sonuçta n düğüm (toprak hariç) ve m gerilim kaynağı için (n+m)×(n+m) sistem:

        ┌       ┐ ┌   ┐   ┌   ┐
        │ G   B │ │ v │   │ i │      v : düğüm voltajları      (n tane)
        │       │ │   │ = │   │      j : V-kaynak akımları     (m tane)
        │ C   D │ │ j │   │ e │      i : düğümlere basılan akım kaynakları
        └       ┘ └   ┘   └   ┘      e : gerilim kaynaklarının değerleri

    G : iletkenlik/admittans matrisi
    B : hangi kaynak hangi düğüme bağlı (+1 / -1)
    C = Bᵀ (bağımsız kaynaklar için)
    D = 0  (bağımsız kaynaklar için; bağımlı kaynaklarda dolacak)

"STAMP" (DAMGA) YÖNTEMİ
-----------------------
Her eleman matrise kendi küçük katkısını "damgalar", birbirinden bağımsız olarak.
Devreyi bilmeye gerek yok; elemanları tek tek dolaşıp topla. SPICE'ın kalbi budur.

AC (FAZÖR) ANALİZİ
------------------
AC kararlı durumda gerilim ve akımlar karmaşık fazörler (phasor) ile ifade edilir:
    v(t) = Vm · cos(ωt + φ)  ->  V = Vm · e^(jφ)
    ω = 2πf  (açısal frekans, rad/s)

Pasif iki uçlu elemanların (R, C, L) ortak damgası admittans (Y = 1/Z) ile yazılır:
    • Direnç (R)   : Y = 1 / R
    • Kapasitör (C): Z = 1/(jωC)  ->  Y = jωC
    • Bobin (L)    : Z = jωL      ->  Y = 1/(jωL) = -j / (ωL)

Her pasif eleman (a → b) admittans matrisine şu damgayı basar:
    A[a, a] += Y
    A[b, b] += Y
    A[a, b] -= Y
    A[b, a] -= Y

İŞARET KURALI (SPICE ile aynı)
------------------------------
Gerilim kaynağı akımı j: kaynağın İÇİNDEN + uçtan - uca akan akım.
Yani güç veren (normal çalışan) bir kaynak için j NEGATİF çıkar.
Güç: S = (1/2) · V · I* (tepe fazörleri ile emilen karmaşık güç).
     P = Re(S) -> Aktif güç (W)
     Q = Im(S) -> Reaktif güç (VAR)
"""

from dataclasses import dataclass, field
import cmath
import math

import numpy as np

from netlist import Eleman


@dataclass
class Cozum:
    """DC analizi çözüm sonuçları."""
    dugum_voltajlari: dict[str, float]      # {"1": 5.0, "2": 2.5, "0": 0.0}
    eleman_akimlari: dict[str, float]       # + uçtan - uca, elemanın içinden
    eleman_gerilimleri: dict[str, float]    # V(+) - V(-)
    eleman_gucleri: dict[str, float]        # emilen güç (pasif işaret kuralı); negatif = güç veriyor
    # Eğitim amaçlı: kurulan sistem
    A: np.ndarray = field(repr=False, default=None)
    z: np.ndarray = field(repr=False, default=None)
    bilinmeyenler: list[str] = field(default_factory=list)


@dataclass
class ACCozum:
    """AC fazör analizi çözüm sonuçları."""
    frekans: float                          # Frekans f (Hz)
    omega: float                            # Açısal frekans ω = 2πf (rad/s)
    dugum_voltajlari: dict[str, complex]    # Karmaşık fazör gerilimleri: V(+)
    eleman_akimlari: dict[str, complex]     # + uçtan - uca karmaşık fazör akımları
    eleman_gerilimleri: dict[str, complex]  # V(+) - V(-) fazör gerilimleri
    eleman_gucleri: dict[str, complex]      # S = (1/2) · V · I* (karmaşık güç, VA)
    # Eğitim amaçlı: kurulan sistem
    A: np.ndarray = field(repr=False, default=None)
    z: np.ndarray = field(repr=False, default=None)
    bilinmeyenler: list[str] = field(default_factory=list)

    @property
    def aktif_gucler(self) -> dict[str, float]:
        """P = Re(S) [Watt] — dirençlerde harcanan ortalama aktif güç."""
        return {k: v.real for k, v in self.eleman_gucleri.items()}

    @property
    def reaktif_gucler(self) -> dict[str, float]:
        """Q = Im(S) [VAR] — C (negatif) ve L'de (pozitif) depolanan reaktif güç."""
        return {k: v.imag for k, v in self.eleman_gucleri.items()}


class DevreHatasi(Exception):
    pass


def polar(z: complex) -> tuple[float, float]:
    """Karmaşık fazörü (genlik, derece_cinsinden_faz) olarak döner."""
    genlik, rad = cmath.polar(z)
    derece = math.degrees(rad)
    return genlik, derece


# ==============================================================================
# DC ÇÖZÜCÜ
# ==============================================================================

def coz(elemanlar: list[Eleman]) -> Cozum:
    """DC MNA analizi yapar.

    R, V, I elemanlarını ve DC kararlı durumda C (açık devre), L (kısa devre) çözer.
    """
    dugumler: list[str] = []
    for e in elemanlar:
        for d in (e.dugum_p, e.dugum_n):
            if d != "0" and d not in dugumler:
                dugumler.append(d)
    indeks = {d: i for i, d in enumerate(dugumler)}

    v_kaynaklari = [e for e in elemanlar if e.tur == "V"]
    # DC'de bobin (L) ideal kısa devredir (0 V gerilim kaynağı gibi davranır)
    bobinler = [e for e in elemanlar if e.tur == "L"]
    v_benzeri = v_kaynaklari + bobinler

    n, m = len(dugumler), len(v_benzeri)
    N = n + m

    A = np.zeros((N, N), dtype=float)
    z = np.zeros(N, dtype=float)

    def ekle(satir: str | int, sutun: str | int, deger: float):
        r = indeks.get(satir) if isinstance(satir, str) else satir
        c = indeks.get(sutun) if isinstance(sutun, str) else sutun
        if r is not None and c is not None:
            A[r, c] += deger

    def ekle_z(satir: str | int, deger: float):
        r = indeks.get(satir) if isinstance(satir, str) else satir
        if r is not None:
            z[r] += deger

    k = 0  # v_benzeri sayacı
    for e in elemanlar:
        a, b = e.dugum_p, e.dugum_n

        if e.tur == "R":
            g = 1.0 / e.deger
            ekle(a, a, +g)
            ekle(b, b, +g)
            ekle(a, b, -g)
            ekle(b, a, -g)

        elif e.tur == "C":
            # DC'de kapasitör açık devre; iletkenlik g = 0, matrise katkı yapmaz
            pass

        elif e.tur == "I":
            ekle_z(a, -e.deger)
            ekle_z(b, +e.deger)

        elif e.tur in ("V", "L"):
            # V için gerilim = e.deger, L için gerilim = 0 (kısa devre)
            voltaj = e.deger if e.tur == "V" else 0.0
            col = n + k
            ekle(a, col, +1.0)
            ekle(b, col, -1.0)
            ekle(col, a, +1.0)
            ekle(col, b, -1.0)
            ekle_z(col, voltaj)
            k += 1

    bilinmeyenler = [f"V({d})" for d in dugumler] + [f"I({e.isim})" for e in v_benzeri]

    try:
        x = np.linalg.solve(A, z)
    except np.linalg.LinAlgError:
        raise DevreHatasi(
            "Matris tekil (singular) — devre çözülemiyor. Olası nedenler:\n"
            "  • Toprağa hiçbir yoldan bağlanmayan (yüzen) bir düğüm/bölüm var\n"
            "  • Paralel bağlı iki ideal gerilim kaynağı (veya V-kaynağı döngüsü)\n"
            "  • Seri bağlı iki ideal akım kaynağı (veya I-kaynağı kesim kümesi)"
        )

    V = {"0": 0.0}
    V.update({d: float(x[indeks[d]]) for d in dugumler})

    akim, gerilim, guc = {}, {}, {}
    k = 0
    for e in elemanlar:
        vab = V[e.dugum_p] - V[e.dugum_n]
        if e.tur == "R":
            i = vab / e.deger
        elif e.tur == "C":
            i = 0.0  # DC kararlı durumda kapasitör akımı sıfırdır
        elif e.tur == "I":
            i = e.deger
        else:  # V veya L
            i = float(x[n + k])
            k += 1
        gerilim[e.isim] = vab
        akim[e.isim] = i
        guc[e.isim] = vab * i

    return Cozum(V, akim, gerilim, guc, A, z, bilinmeyenler)


# ==============================================================================
# AC (FAZÖR) ÇÖZÜCÜ
# ==============================================================================

def coz_ac(elemanlar: list[Eleman], frekans: float | None = None) -> ACCozum:
    """AC frekans domeninde (fazör) MNA analizi yapar.

    Parametreler:
        elemanlar : Netlist elemanları (R, C, L, V, I)
        frekans   : Devre çalışma frekansı (Hz). Belirtilmezse netlist'teki
                    .ac komutundan veya varsayılan 1000 Hz (1 kHz) alınır.

    Dönen değer:
        ACCozum : Karmaşık fazör gerilimleri, akımları ve güçleri.
    """
    if frekans is None:
        frekans = getattr(elemanlar, "frekans", None) or 1000.0

    if frekans <= 0:
        raise ValueError(f"AC frekansı pozitif olmalıdır: f = {frekans} Hz")

    omega = 2.0 * math.pi * frekans

    dugumler: list[str] = []
    for e in elemanlar:
        for d in (e.dugum_p, e.dugum_n):
            if d != "0" and d not in dugumler:
                dugumler.append(d)
    indeks = {d: i for i, d in enumerate(dugumler)}

    v_kaynaklari = [e for e in elemanlar if e.tur == "V"]
    n, m = len(dugumler), len(v_kaynaklari)
    N = n + m

    A = np.zeros((N, N), dtype=np.complex128)
    z = np.zeros(N, dtype=np.complex128)

    def ekle(satir: str | int, sutun: str | int, deger: complex):
        r = indeks.get(satir) if isinstance(satir, str) else satir
        c = indeks.get(sutun) if isinstance(sutun, str) else sutun
        if r is not None and c is not None:
            A[r, c] += deger

    def ekle_z(satir: str | int, deger: complex):
        r = indeks.get(satir) if isinstance(satir, str) else satir
        if r is not None:
            z[r] += deger

    # 1) Pasif Elemanların ve Kaynakların Damgalanması
    k = 0
    for e in elemanlar:
        a, b = e.dugum_p, e.dugum_n

        if e.tur in ("R", "C", "L"):
            # Admittans (Y = 1/Z) hesabı
            if e.tur == "R":
                Y = 1.0 / e.deger
            elif e.tur == "C":
                # Zc = 1 / (jωC)  =>  Yc = jωC
                Y = 1j * omega * e.deger
            elif e.tur == "L":
                # Zl = jωL  =>  Yl = 1 / (jωL) = -j / (ωL)
                Y = -1j / (omega * e.deger)

            ekle(a, a, +Y)
            ekle(b, b, +Y)
            ekle(a, b, -Y)
            ekle(b, a, -Y)

        elif e.tur == "I":
            # Fazör akımı: I = I_tepe · e^(j·faz)
            genlik = e.ac_genlik if e.ac_genlik != 0.0 else e.deger
            faz_rad = math.radians(e.ac_faz)
            i_fazor = cmath.rect(genlik, faz_rad)
            # a'dan çeker (-), b'ye basar (+)
            ekle_z(a, -i_fazor)
            ekle_z(b, +i_fazor)

        elif e.tur == "V":
            # Fazör gerilimi: V = V_tepe · e^(j·faz)
            genlik = e.ac_genlik if e.ac_genlik != 0.0 else e.deger
            faz_rad = math.radians(e.ac_faz)
            v_fazor = cmath.rect(genlik, faz_rad)

            col = n + k
            ekle(a, col, +1.0)
            ekle(b, col, -1.0)
            ekle(col, a, +1.0)
            ekle(col, b, -1.0)
            ekle_z(col, v_fazor)
            k += 1

    bilinmeyenler = [f"V({d})" for d in dugumler] + [f"I({e.isim})" for e in v_kaynaklari]

    # 2) Karmaşık Lineer Sistemi Çöz: A · x = z
    try:
        x = np.linalg.solve(A, z)
    except np.linalg.LinAlgError:
        raise DevreHatasi(
            "AC MNA matrisi tekil (singular) — devre bu frekansta çözülemiyor.\n"
            "Olası nedenler:\n"
            "  • Toprağa bağlı olmayan (yüzen) düğüm/bölüm\n"
            "  • Paralel ideal gerilim kaynakları veya ideal LC paralel rezonansı"
        )

    # 3) Fazör Düğüm Gerilimleri
    V = {"0": 0.0 + 0.0j}
    V.update({d: complex(x[indeks[d]]) for d in dugumler})

    # 4) Fazör Eleman Akımları, Gerilimleri ve Güçleri
    akim, gerilim, guc = {}, {}, {}
    k = 0
    for e in elemanlar:
        vab = V[e.dugum_p] - V[e.dugum_n]
        if e.tur == "R":
            i = vab / e.deger
        elif e.tur == "C":
            i = vab * (1j * omega * e.deger)
        elif e.tur == "L":
            i = vab / (1j * omega * e.deger)
        elif e.tur == "I":
            genlik = e.ac_genlik if e.ac_genlik != 0.0 else e.deger
            i = cmath.rect(genlik, math.radians(e.ac_faz))
        else:  # V
            i = complex(x[n + k])
            k += 1

        gerilim[e.isim] = vab
        akim[e.isim] = i
        # Tepe fazörleri ile karmaşık güç: S = 0.5 · V · I*
        # (Eğer RMS olsaydı doğrudan V · I* olurdu)
        guc[e.isim] = 0.5 * vab * np.conj(i)

    return ACCozum(frekans, omega, V, akim, gerilim, guc, A, z, bilinmeyenler)
