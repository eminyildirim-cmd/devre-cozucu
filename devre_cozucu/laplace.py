"""
Laplace (s-Domeni) Sembolik Transfer Fonksiyonu Çözücüsü

FİKİR VE YÖNTEM:
----------------
Laplace domeninde (s-domeni) diferansiyel denklemler cebirsel denklemlere dönüşür:
    • Direnç (R)   : Z(s) = R,       Y(s) = 1/R
    • Kapasitör (C): Z(s) = 1/(s·C), Y(s) = s·C
    • Bobin (L)    : Z(s) = s·L,     Y(s) = 1/(s·L)

MNA denklemi:
    A(s) · X(s) = Z(s)

Burada A(s) matrisinin elemanları s'in rasyonel polinomlarıdır:
    P(s) / Q(s)

Sistem Gauss Eliminasyonu ile sembolik olarak çözülerek çıkış düğümünün
giriş gerilimine oranı olan transfer fonksiyonu elde edilir:
    H(s) = V_out(s) / V_in(s) = N(s) / D(s)

KUTUP-SIFIR VE KARARLILIK ANALİZİ:
----------------------------------
    • Sıfırlar (Zeros)  : N(s) = 0 kökleri
    • Kutuplar (Poles)  : D(s) = 0 kökleri
    • Kararlılık        : Tüm kutupların reel kısımları < 0 ise sistem KARARLIDIR (asymptotic stability).
    • DC Kazancı        : s -> 0 iken H(0)
    • İkinci Dereceden Sistem Parametreleri: Doğal frekans ω0, sönüm oranı ζ, kalite faktörü Q.
"""

from dataclasses import dataclass
import math

import numpy as np

from mna import DevreHatasi
from netlist import Eleman


class RasyonelPolinom:
    """s'e bağlı rasyonel fonksiyon: P(s) / Q(s)"""
    def __init__(self, num, den=None):
        if den is None:
            den = np.poly1d([1.0])
        elif isinstance(den, (int, float)):
            den = np.poly1d([float(den)])
        elif isinstance(den, list):
            den = np.poly1d(den)

        if isinstance(num, (int, float)):
            num = np.poly1d([float(num)])
        elif isinstance(num, list):
            num = np.poly1d(num)

        if len(den.coeffs) > 0 and not math.isclose(den.coeffs[0], 0, abs_tol=1e-15):
            lead = den.coeffs[0]
            self.num = num / lead
            self.den = den / lead
        else:
            self.num = num
            self.den = den

    def is_zero(self) -> bool:
        return len(self.num.coeffs) == 0 or np.allclose(self.num.coeffs, 0, atol=1e-14)

    def __pos__(self):
        return self

    def __neg__(self):
        return RasyonelPolinom(-self.num, self.den)

    def __add__(self, other):
        if isinstance(other, (int, float)):
            other = RasyonelPolinom(other)
        n = self.num * other.den + other.num * self.den
        d = self.den * other.den
        return RasyonelPolinom(n, d)

    def __sub__(self, other):
        if isinstance(other, (int, float)):
            other = RasyonelPolinom(other)
        n = self.num * other.den - other.num * self.den
        d = self.den * other.den
        return RasyonelPolinom(n, d)

    def __mul__(self, other):
        if isinstance(other, (int, float)):
            other = RasyonelPolinom(other)
        return RasyonelPolinom(self.num * other.num, self.den * other.den)

    def __truediv__(self, other):
        if isinstance(other, (int, float)):
            other = RasyonelPolinom(other)
        return RasyonelPolinom(self.num * other.den, self.den * other.num)


def polinom_sade_lestir(p_n: np.poly1d, p_d: np.poly1d) -> tuple[np.poly1d, np.poly1d]:
    """Ortak s^k çarpanlarını ve ortak kökleri (s - r) sadeleştirir."""
    c_n = list(p_n.coeffs)
    c_d = list(p_d.coeffs)

    # 1. Ortak s^k (sonda sıfır olan) katsayıları yok et
    while len(c_n) > 1 and len(c_d) > 1 and abs(c_n[-1]) < 1e-11 and abs(c_d[-1]) < 1e-11:
        c_n.pop()
        c_d.pop()

    # 2. Ortak kökleri iptal et
    r_n = list(np.poly1d(c_n).roots)
    r_d = list(np.poly1d(c_d).roots)

    kalan_n = []
    for rn in r_n:
        eslesti = False
        for i, rd in enumerate(r_d):
            if np.isclose(rn, rd, atol=1e-4, rtol=1e-4):
                r_d.pop(i)
                eslesti = True
                break
        if not eslesti:
            kalan_n.append(rn)

    lead_d = c_d[0] if len(c_d) > 0 and c_d[0] != 0 else 1.0
    lead_n = c_n[0] if len(c_n) > 0 else 1.0
    gain = lead_n / lead_d

    num_poly = np.poly1d(kalan_n, True) * gain if kalan_n else np.poly1d([gain])
    den_poly = np.poly1d(r_d, True) if r_d else np.poly1d([1.0])

    # Paydanın başkatsayısını 1 yap
    lead = den_poly.coeffs[0]
    num_poly = num_poly / lead
    den_poly = den_poly / lead

    return num_poly, den_poly


def polinom_str(p: np.poly1d) -> str:
    """np.poly1d nesnesini okunaklı 's' değişkenli metne dönüştürür."""
    coeffs = p.coeffs
    deg = len(coeffs) - 1
    if deg == 0:
        return f"{coeffs[0]:.4g}"

    parcalar = []
    for i, c in enumerate(coeffs):
        kuvvet = deg - i
        if math.isclose(c, 0, abs_tol=1e-12):
            continue
        isaret = " - " if c < 0 else (" + " if parcalar else "")
        mutlak_c = abs(c)
        c_str = "" if math.isclose(mutlak_c, 1.0, abs_tol=1e-12) and kuvvet > 0 else f"{mutlak_c:.4g}"

        if kuvvet == 0:
            parcalar.append(f"{isaret}{mutlak_c:.4g}")
        elif kuvvet == 1:
            parcalar.append(f"{isaret}{c_str}s")
        else:
            parcalar.append(f"{isaret}{c_str}s^{kuvvet}")

    return "".join(parcalar) if parcalar else "0"


@dataclass
class TransferFonksiyonu:
    pay: np.poly1d
    payda: np.poly1d
    kutuplar: list[complex]
    sifirlar: list[complex]
    kararli: bool
    dc_kazanci: float | None
    omega_0: float | None = None
    kalite_faktoru_Q: float | None = None
    sonum_orani_zeta: float | None = None

    def __str__(self) -> str:
        s_pay = polinom_str(self.pay)
        s_payda = polinom_str(self.payda)
        cizgi_uzunluk = max(len(s_pay), len(s_payda)) + 4
        cizgi = "─" * cizgi_uzunluk
        return f"\n         {s_pay:^{cizgi_uzunluk}}\n  H(s) = {cizgi}\n         {s_payda:^{cizgi_uzunluk}}\n"


def coz_laplace(elemanlar: list[Eleman], cikis_dugumu: str, giris_kaynagi: str | None = None) -> TransferFonksiyonu:
    """Devrenin sembolik Laplace transfer fonksiyonunu H(s) = V_out(s) / V_in(s) hesaplar."""
    # Giriş kaynağını tespit et
    v_kaynaklari = [e for e in elemanlar if e.tur == "V"]
    if not v_kaynaklari:
        raise DevreHatasi("Transfer fonksiyonu analizi için devrede en az 1 adet bağımsız gerilim kaynağı (Vin) olmalıdır.")

    if giris_kaynagi is None:
        giris_elem = v_kaynaklari[0]
    else:
        bulunan = [e for e in v_kaynaklari if e.isim.upper() == giris_kaynagi.upper()]
        if not bulunan:
            raise DevreHatasi(f"Giriş kaynağı '{giris_kaynagi}' devrede bulunamadı.")
        giris_elem = bulunan[0]

    # Düğümleri belirle
    dugumler: list[str] = []
    for e in elemanlar:
        for d in (e.dugum_p, e.dugum_n, e.kontrol_p, e.kontrol_n):
            if d and d != "0" and d not in dugumler:
                dugumler.append(d)
    indeks = {d: i for i, d in enumerate(dugumler)}

    if cikis_dugumu not in indeks and cikis_dugumu != "0":
        raise DevreHatasi(f"Çıkış düğümü '{cikis_dugumu}' devrede mevcut değil. (Düğümler: {', '.join(dugumler)})")

    v_benzeri = [e for e in elemanlar if e.tur in ("V", "E", "H")]
    v_indeks = {e.isim.upper(): i for i, e in enumerate(v_benzeri)}

    n = len(dugumler)
    m = len(v_benzeri)
    N = n + m

    # A(s) matrisi ve z(s) vektörü
    A = [[RasyonelPolinom(0) for _ in range(N)] for _ in range(N)]
    b = [RasyonelPolinom(0) for _ in range(N)]

    s = RasyonelPolinom(np.poly1d([1.0, 0.0]))

    def ekle_A(satir: str | int, sutun: str | int, deger: RasyonelPolinom):
        r = indeks.get(satir) if isinstance(satir, str) else satir
        c = indeks.get(sutun) if isinstance(sutun, str) else sutun
        if r is not None and c is not None:
            A[r][c] = A[r][c] + deger

    def ekle_b(satir: str | int, deger: RasyonelPolinom):
        r = indeks.get(satir) if isinstance(satir, str) else satir
        if r is not None:
            b[r] = b[r] + deger

    k = 0
    for e in elemanlar:
        a, b_node = e.dugum_p, e.dugum_n

        if e.tur == "R":
            Y = RasyonelPolinom(1.0 / e.deger)
            ekle_A(a, a, +Y)
            ekle_A(b_node, b_node, +Y)
            ekle_A(a, b_node, -Y)
            ekle_A(b_node, a, -Y)

        elif e.tur == "C":
            # Yc(s) = s · C
            Y = s * RasyonelPolinom(e.deger)
            ekle_A(a, a, +Y)
            ekle_A(b_node, b_node, +Y)
            ekle_A(a, b_node, -Y)
            ekle_A(b_node, a, -Y)

        elif e.tur == "L":
            # Yl(s) = 1 / (s · L)
            Y = RasyonelPolinom(1.0) / (s * RasyonelPolinom(e.deger))
            ekle_A(a, a, +Y)
            ekle_A(b_node, b_node, +Y)
            ekle_A(a, b_node, -Y)
            ekle_A(b_node, a, -Y)

        elif e.tur == "V":
            col = n + k
            ekle_A(a, col, RasyonelPolinom(1.0))
            ekle_A(b_node, col, RasyonelPolinom(-1.0))
            ekle_A(col, a, RasyonelPolinom(1.0))
            ekle_A(col, b_node, RasyonelPolinom(-1.0))
            if e.isim.upper() == giris_elem.isim.upper():
                ekle_b(col, RasyonelPolinom(1.0))  # Vin(s) = 1 (Birim dürtü/transfer)
            k += 1

        elif e.tur == "E":  # VCVS
            col = n + k
            ca, cb = e.kontrol_p, e.kontrol_n
            mu = RasyonelPolinom(e.deger)
            ekle_A(a, col, RasyonelPolinom(1.0))
            ekle_A(b_node, col, RasyonelPolinom(-1.0))
            ekle_A(col, a, RasyonelPolinom(1.0))
            ekle_A(col, b_node, RasyonelPolinom(-1.0))
            ekle_A(col, ca, -mu)
            ekle_A(col, cb, +mu)
            k += 1

        elif e.tur == "G":  # VCCS
            ca, cb = e.kontrol_p, e.kontrol_n
            gm = RasyonelPolinom(e.deger)
            ekle_A(a, ca, +gm)
            ekle_A(a, cb, -gm)
            ekle_A(b_node, ca, -gm)
            ekle_A(b_node, cb, +gm)

        elif e.tur == "H":  # CCVS
            col = n + k
            v_ref = e.kontrol_kaynak.upper()
            col_v = n + v_indeks[v_ref]
            r_val = RasyonelPolinom(e.deger)
            ekle_A(a, col, RasyonelPolinom(1.0))
            ekle_A(b_node, col, RasyonelPolinom(-1.0))
            ekle_A(col, a, RasyonelPolinom(1.0))
            ekle_A(col, b_node, RasyonelPolinom(-1.0))
            ekle_A(col, col_v, -r_val)
            k += 1

        elif e.tur == "F":  # CCCS
            v_ref = e.kontrol_kaynak.upper()
            col_v = n + v_indeks[v_ref]
            beta = RasyonelPolinom(e.deger)
            ekle_A(a, col_v, +beta)
            ekle_A(b_node, col_v, -beta)

    # 3) Gauss Eliminasyonu ile Çöz
    for i in range(N):
        if A[i][i].is_zero():
            for row in range(i + 1, N):
                if not A[row][i].is_zero():
                    A[i], A[row] = A[row], A[i]
                    b[i], b[row] = b[row], b[i]
                    break
        pivot = A[i][i]
        for j in range(i, N):
            A[i][j] = A[i][j] / pivot
        b[i] = b[i] / pivot

        for row in range(i + 1, N):
            factor = A[row][i]
            if not factor.is_zero():
                for j in range(i, N):
                    A[row][j] = A[row][j] - factor * A[i][j]
                b[row] = b[row] - factor * b[i]

    # Geriye yerine koyma (Back-substitution)
    x = [RasyonelPolinom(0) for _ in range(N)]
    for i in range(N - 1, -1, -1):
        toplam = b[i]
        for j in range(i + 1, N):
            toplam = toplam - A[i][j] * x[j]
        x[i] = toplam

    # Çıkış düğümünün rasyonel fonksiyonu
    cikis_idx = indeks[cikis_dugumu]
    h_ras = x[cikis_idx]

    num_p, den_p = polinom_sade_lestir(h_ras.num, h_ras.den)

    # Kutuplar ve Sıfırlar
    kutuplar = list(den_p.roots)
    sifirlar = list(num_p.roots)

    # Kararlılık: Tüm kutupların reel kısımları kesin negatif mi?
    kararli = all(p.real < 1e-9 for p in kutuplar)

    # DC Kazancı: s -> 0
    try:
        val_n = num_p(0.0)
        val_d = den_p(0.0)
        dc_kazanci = float(val_n / val_d) if abs(val_d) > 1e-12 else None
    except Exception:
        dc_kazanci = None

    # İkinci dereceden sistem parametreleri: s^2 + 2ζω0 s + ω0^2
    omega_0, Q, zeta = None, None, None
    if len(den_p.coeffs) == 3:
        a2, a1, a0 = den_p.coeffs
        if a0 > 0:
            omega_0 = math.sqrt(a0)
            zeta = a1 / (2.0 * omega_0)
            Q = 1.0 / (2.0 * zeta) if zeta > 0 else None

    return TransferFonksiyonu(num_p, den_p, kutuplar, sifirlar, kararli, dc_kazanci, omega_0, Q, zeta)
