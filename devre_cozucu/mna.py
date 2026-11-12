"""
MNA — Modified Nodal Analysis (Değiştirilmiş Düğüm Analizi)

FİKİR
-----
Klasik düğüm analizinde her düğüme KCL yazarız: "çıkan akımların toplamı = 0".
Gerilim kaynaklarının akımı bilinmeyen olduğu için, MNA bu akımları EKSTRA
BİLİNMEYEN yapar ve gerilim tanımlayıcı her eleman için ek denklem ekler.

Sistem denklemi:
        ┌       ┐ ┌   ┐   ┌   ┐
        │ G   B │ │ v │   │ i │      v : düğüm voltajları      (n tane)
        │       │ │   │ = │   │      j : gerilim kaynağı akımları (m tane)
        │ C   D │ │ j │   │ e │      i : düğümlere basılan akım kaynakları
        └       ┘ └   ┘   └   ┘      e : kaynak gerilimleri

DESTEKLENEN ELEMANLAR VE DAMGALARI:
-----------------------------------
1. Direnç (R)   : Admittans Y = 1/R
2. Kapasitör (C): AC admittans Y = jωC (DC'de açık devre)
3. Bobin (L)    : AC admittans Y = 1/(jωL) (DC'de kısa devre: 0V gerilim kaynağı)
4. Bağımsız V/I : V ek bilinmeyen j ekler; I sağ tarafa (z) basar.
5. Bağımlı Kaynaklar:
   • VCVS (E): V(out) = μ · V(in)       -> Gerilim kontrollü gerilim kaynağı
   • VCCS (G): I(out) = gm · V(in)      -> Gerilim kontrollü akım kaynağı
   • CCVS (H): V(out) = r · I(Vsens)    -> Akım kontrollü gerilim kaynağı
   • CCCS (F): I(out) = β · I(Vsens)    -> Akım kontrollü akım kaynağı
"""

from dataclasses import dataclass, field
import cmath
import math

import numpy as np

from netlist import Eleman


@dataclass
class Cozum:
    """DC analizi çözüm sonuçları."""
    dugum_voltajlari: dict[str, float]
    eleman_akimlari: dict[str, float]
    eleman_gerilimleri: dict[str, float]
    eleman_gucleri: dict[str, float]
    A: np.ndarray = field(repr=False, default=None)
    z: np.ndarray = field(repr=False, default=None)
    bilinmeyenler: list[str] = field(default_factory=list)


@dataclass
class ACCozum:
    """AC fazör analizi çözüm sonuçları."""
    frekans: float
    omega: float
    dugum_voltajlari: dict[str, complex]
    eleman_akimlari: dict[str, complex]
    eleman_gerilimleri: dict[str, complex]
    eleman_gucleri: dict[str, complex]
    A: np.ndarray = field(repr=False, default=None)
    z: np.ndarray = field(repr=False, default=None)
    bilinmeyenler: list[str] = field(default_factory=list)

    @property
    def aktif_gucler(self) -> dict[str, float]:
        return {k: v.real for k, v in self.eleman_gucleri.items()}

    @property
    def reaktif_gucler(self) -> dict[str, float]:
        return {k: v.imag for k, v in self.eleman_gucleri.items()}


class DevreHatasi(Exception):
    pass


def polar(z: complex) -> tuple[float, float]:
    genlik, rad = cmath.polar(z)
    derece = math.degrees(rad)
    return genlik, derece


# ==============================================================================
# DC ÇÖZÜCÜ
# ==============================================================================

def coz(elemanlar: list[Eleman]) -> Cozum:
    """DC MNA analizi yapar (R, V, I, C, L, E, G, H, F)."""
    # 1) Düğümleri belirle (0 hariç)
    dugumler: list[str] = []
    for e in elemanlar:
        for d in (e.dugum_p, e.dugum_n, e.kontrol_p, e.kontrol_n):
            if d and d != "0" and d not in dugumler:
                dugumler.append(d)
    indeks = {d: i for i, d in enumerate(dugumler)}

    # 2) Ekstra akım değişkeni gerektiren elemanlar: V, L (DC'de kısa devre), E (VCVS), H (CCVS)
    v_benzeri = [e for e in elemanlar if e.tur in ("V", "L", "E", "H")]
    v_indeks = {e.isim.upper(): i for i, e in enumerate(v_benzeri)}

    n = len(dugumler)
    m = len(v_benzeri)
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

    # 3) Eleman damgaları
    k = 0
    for e in elemanlar:
        a, b = e.dugum_p, e.dugum_n

        if e.tur == "R":
            g = 1.0 / e.deger
            ekle(a, a, +g)
            ekle(b, b, +g)
            ekle(a, b, -g)
            ekle(b, a, -g)

        elif e.tur == "C":
            # DC kararlı durumda açık devre
            pass

        elif e.tur == "I":
            ekle_z(a, -e.deger)
            ekle_z(b, +e.deger)

        elif e.tur in ("V", "L"):
            voltaj = e.deger if e.tur == "V" else 0.0
            col = n + k
            ekle(a, col, +1.0)
            ekle(b, col, -1.0)
            ekle(col, a, +1.0)
            ekle(col, b, -1.0)
            ekle_z(col, voltaj)
            k += 1

        elif e.tur == "E":  # VCVS: V(a) - V(b) = mu * [V(ca) - V(cb)]
            col = n + k
            ca, cb = e.kontrol_p, e.kontrol_n
            mu = e.deger
            ekle(a, col, +1.0)
            ekle(b, col, -1.0)
            ekle(col, a, +1.0)
            ekle(col, b, -1.0)
            ekle(col, ca, -mu)
            ekle(col, cb, +mu)
            k += 1

        elif e.tur == "G":  # VCCS: I(a->b) = gm * [V(ca) - V(cb)]
            ca, cb = e.kontrol_p, e.kontrol_n
            gm = e.deger
            ekle(a, ca, +gm)
            ekle(a, cb, -gm)
            ekle(b, ca, -gm)
            ekle(b, cb, +gm)

        elif e.tur == "H":  # CCVS: V(a) - V(b) = r * I(Vsens)
            col = n + k
            v_ref = e.kontrol_kaynak.upper()
            if v_ref not in v_indeks:
                raise DevreHatasi(f"CCVS '{e.isim}': Kontrol kaynağı '{e.kontrol_kaynak}' bulunamadı.")
            col_v = n + v_indeks[v_ref]
            r = e.deger
            ekle(a, col, +1.0)
            ekle(b, col, -1.0)
            ekle(col, a, +1.0)
            ekle(col, b, -1.0)
            ekle(col, col_v, -r)
            k += 1

        elif e.tur == "F":  # CCCS: I(a->b) = beta * I(Vsens)
            v_ref = e.kontrol_kaynak.upper()
            if v_ref not in v_indeks:
                raise DevreHatasi(f"CCCS '{e.isim}': Kontrol kaynağı '{e.kontrol_kaynak}' bulunamadı.")
            col_v = n + v_indeks[v_ref]
            beta = e.deger
            ekle(a, col_v, +beta)
            ekle(b, col_v, -beta)

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
            i = 0.0
        elif e.tur == "I":
            i = e.deger
        elif e.tur in ("V", "L", "E", "H"):
            i = float(x[n + k])
            k += 1
        elif e.tur == "G":
            v_ctrl = V[e.kontrol_p] - V[e.kontrol_n]
            i = e.deger * v_ctrl
        elif e.tur == "F":
            col_v = n + v_indeks[e.kontrol_kaynak.upper()]
            i_ctrl = float(x[col_v])
            i = e.deger * i_ctrl

        gerilim[e.isim] = vab
        akim[e.isim] = i
        guc[e.isim] = vab * i

    return Cozum(V, akim, gerilim, guc, A, z, bilinmeyenler)


# ==============================================================================
# AC (FAZÖR) ÇÖZÜCÜ
# ==============================================================================

def coz_ac(elemanlar: list[Eleman], frekans: float | None = None) -> ACCozum:
    """AC frekans domeninde (fazör) MNA analizi yapar (R, C, L, V, I, E, G, H, F)."""
    if frekans is None:
        frekans = getattr(elemanlar, "frekans", None) or 1000.0

    if frekans <= 0:
        raise ValueError(f"AC frekansı pozitif olmalıdır: f = {frekans} Hz")

    omega = 2.0 * math.pi * frekans

    dugumler: list[str] = []
    for e in elemanlar:
        for d in (e.dugum_p, e.dugum_n, e.kontrol_p, e.kontrol_n):
            if d and d != "0" and d not in dugumler:
                dugumler.append(d)
    indeks = {d: i for i, d in enumerate(dugumler)}

    v_benzeri = [e for e in elemanlar if e.tur in ("V", "E", "H")]
    v_indeks = {e.isim.upper(): i for i, e in enumerate(v_benzeri)}

    n = len(dugumler)
    m = len(v_benzeri)
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

    k = 0
    for e in elemanlar:
        a, b = e.dugum_p, e.dugum_n

        if e.tur in ("R", "C", "L"):
            if e.tur == "R":
                Y = 1.0 / e.deger
            elif e.tur == "C":
                Y = 1j * omega * e.deger
            elif e.tur == "L":
                Y = -1j / (omega * e.deger)

            ekle(a, a, +Y)
            ekle(b, b, +Y)
            ekle(a, b, -Y)
            ekle(b, a, -Y)

        elif e.tur == "I":
            genlik = e.ac_genlik if e.ac_genlik != 0.0 else e.deger
            i_fazor = cmath.rect(genlik, math.radians(e.ac_faz))
            ekle_z(a, -i_fazor)
            ekle_z(b, +i_fazor)

        elif e.tur == "V":
            genlik = e.ac_genlik if e.ac_genlik != 0.0 else e.deger
            v_fazor = cmath.rect(genlik, math.radians(e.ac_faz))
            col = n + k
            ekle(a, col, +1.0)
            ekle(b, col, -1.0)
            ekle(col, a, +1.0)
            ekle(col, b, -1.0)
            ekle_z(col, v_fazor)
            k += 1

        elif e.tur == "E":  # VCVS
            col = n + k
            ca, cb = e.kontrol_p, e.kontrol_n
            mu = e.deger
            ekle(a, col, +1.0)
            ekle(b, col, -1.0)
            ekle(col, a, +1.0)
            ekle(col, b, -1.0)
            ekle(col, ca, -mu)
            ekle(col, cb, +mu)
            k += 1

        elif e.tur == "G":  # VCCS
            ca, cb = e.kontrol_p, e.kontrol_n
            gm = e.deger
            ekle(a, ca, +gm)
            ekle(a, cb, -gm)
            ekle(b, ca, -gm)
            ekle(b, cb, +gm)

        elif e.tur == "H":  # CCVS
            col = n + k
            v_ref = e.kontrol_kaynak.upper()
            if v_ref not in v_indeks:
                raise DevreHatasi(f"CCVS '{e.isim}': Kontrol kaynağı '{e.kontrol_kaynak}' bulunamadı.")
            col_v = n + v_indeks[v_ref]
            r = e.deger
            ekle(a, col, +1.0)
            ekle(b, col, -1.0)
            ekle(col, a, +1.0)
            ekle(col, b, -1.0)
            ekle(col, col_v, -r)
            k += 1

        elif e.tur == "F":  # CCCS
            v_ref = e.kontrol_kaynak.upper()
            if v_ref not in v_indeks:
                raise DevreHatasi(f"CCCS '{e.isim}': Kontrol kaynağı '{e.kontrol_kaynak}' bulunamadı.")
            col_v = n + v_indeks[v_ref]
            beta = e.deger
            ekle(a, col_v, +beta)
            ekle(b, col_v, -beta)

    bilinmeyenler = [f"V({d})" for d in dugumler] + [f"I({e.isim})" for e in v_benzeri]

    try:
        x = np.linalg.solve(A, z)
    except np.linalg.LinAlgError:
        raise DevreHatasi(
            "AC MNA matrisi tekil (singular) — devre bu frekansta çözülemiyor.\n"
            "Olası nedenler:\n"
            "  • Toprağa bağlı olmayan (yüzen) düğüm/bölüm\n"
            "  • Paralel ideal gerilim kaynakları veya ideal LC paralel rezonansı"
        )

    V = {"0": 0.0 + 0.0j}
    V.update({d: complex(x[indeks[d]]) for d in dugumler})

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
        elif e.tur in ("V", "E", "H"):
            i = complex(x[n + k])
            k += 1
        elif e.tur == "G":
            v_ctrl = V[e.kontrol_p] - V[e.kontrol_n]
            i = e.deger * v_ctrl
        elif e.tur == "F":
            col_v = n + v_indeks[e.kontrol_kaynak.upper()]
            i_ctrl = complex(x[col_v])
            i = e.deger * i_ctrl

        gerilim[e.isim] = vab
        akim[e.isim] = i
        guc[e.isim] = 0.5 * vab * np.conj(i)

    return ACCozum(frekans, omega, V, akim, gerilim, guc, A, z, bilinmeyenler)
