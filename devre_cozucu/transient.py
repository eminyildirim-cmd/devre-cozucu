"""
Geçici (Transient) Analiz Çözücüsü — Zaman Domeni Simülasyonu

FİKİR VE YÖNTEM:
----------------
Zaman domeninde diferansiyel denklemler:
    Kapasitör: i_C(t) = C · dv_C/dt
    Bobin    : v_L(t) = L · di_L/dt

Bu diferansiyel denklemleri çözmek için sayısal integrasyon (Companion Model) kullanılır.
Kullanılan yöntem: Yamuk Kuralı (Trapezoidal Rule).

EŞDEĞER DAMGALAR (Companion Stamp, h = Δt):
-------------------------------------------
1. Kapasitör (C):
   i_C(t) = G_eq · v_C(t) - I_hist
   G_eq   = (2 · C) / h
   I_hist = G_eq · v_C(t - h) + i_C(t - h)

   Admittans matrisine (A) G_eq damgalanır.
   Sağ taraf vektörüne (z) I_hist eklenir:
       z[a] += I_hist
       z[b] -= I_hist

2. Bobin (L):
   i_L(t) = G_eq · v_L(t) + I_hist
   G_eq   = h / (2 · L)
   I_hist = i_L(t - h) + G_eq · v_L(t - h)

   Admittans matrisine (A) G_eq damgalanır.
   Sağ taraf vektörüne (z) I_hist eklenir:
       z[a] -= I_hist
       z[b] += I_hist
"""

from dataclasses import dataclass
import math

import numpy as np

from mna import DevreHatasi
from netlist import Eleman


@dataclass
class TranCozum:
    """Zaman domeninde geçici analiz sonuçları."""
    zaman: np.ndarray                       # t = [0, h, 2h, ... t_dur]
    dugum_voltajlari: dict[str, np.ndarray] # {"1": array([...]), ...}
    eleman_akimlari: dict[str, np.ndarray]  # {"R1": array([...]), ...}
    adimi: float                            # h = Δt
    durma_zamani: float                     # t_dur


def kaynak_degeri(e: Eleman, t: float) -> float:
    """Kaynağın t anındaki anlık değerini hesaplar."""
    if e.dalga_tipi == "SIN":
        offset, genlik, f = e.dalga_param
        return offset + genlik * math.sin(2.0 * math.pi * f * t + math.radians(e.ac_faz))
    elif e.dalga_tipi == "DC":
        return e.deger
    return e.deger


def coz_tran(elemanlar: list[Eleman], tstep: float, tstop: float, uic: bool = True) -> TranCozum:
    """Geçici analiz yapar."""
    if tstep <= 0 or tstop <= tstep:
        raise ValueError(f"Geçersiz zaman parametreleri: tstep={tstep}, tstop={tstop}")

    h = tstep
    adim_sayisi = int(math.ceil(tstop / h)) + 1
    zaman = np.linspace(0.0, tstop, adim_sayisi)

    # 1) Düğümler ve ek bilinmeyenler
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

    A = np.zeros((N, N), dtype=float)

    def ekle_A(satir: str | int, sutun: str | int, deger: float):
        r = indeks.get(satir) if isinstance(satir, str) else satir
        c = indeks.get(sutun) if isinstance(sutun, str) else sutun
        if r is not None and c is not None:
            A[r, c] += deger

    # 2) Sabit MNA Matrisi A'nın Kurulması
    k = 0
    kapasitorler = [e for e in elemanlar if e.tur == "C"]
    bobinler = [e for e in elemanlar if e.tur == "L"]

    for e in elemanlar:
        a, b = e.dugum_p, e.dugum_n

        if e.tur == "R":
            g = 1.0 / e.deger
            ekle_A(a, a, +g)
            ekle_A(b, b, +g)
            ekle_A(a, b, -g)
            ekle_A(b, a, -g)

        elif e.tur == "C":
            g_eq = (2.0 * e.deger) / h
            ekle_A(a, a, +g_eq)
            ekle_A(b, b, +g_eq)
            ekle_A(a, b, -g_eq)
            ekle_A(b, a, -g_eq)

        elif e.tur == "L":
            g_eq = h / (2.0 * e.deger)
            ekle_A(a, a, +g_eq)
            ekle_A(b, b, +g_eq)
            ekle_A(a, b, -g_eq)
            ekle_A(b, a, -g_eq)

        elif e.tur == "V":
            col = n + k
            ekle_A(a, col, +1.0)
            ekle_A(b, col, -1.0)
            ekle_A(col, a, +1.0)
            ekle_A(col, b, -1.0)
            k += 1

        elif e.tur == "E":  # VCVS
            col = n + k
            ca, cb = e.kontrol_p, e.kontrol_n
            mu = e.deger
            ekle_A(a, col, +1.0)
            ekle_A(b, col, -1.0)
            ekle_A(col, a, +1.0)
            ekle_A(col, b, -1.0)
            ekle_A(col, ca, -mu)
            ekle_A(col, cb, +mu)
            k += 1

        elif e.tur == "G":  # VCCS
            ca, cb = e.kontrol_p, e.kontrol_n
            gm = e.deger
            ekle_A(a, ca, +gm)
            ekle_A(a, cb, -gm)
            ekle_A(b, ca, -gm)
            ekle_A(b, cb, +gm)

        elif e.tur == "H":  # CCVS
            col = n + k
            v_ref = e.kontrol_kaynak.upper()
            if v_ref not in v_indeks:
                raise DevreHatasi(f"CCVS '{e.isim}': Kontrol kaynağı '{e.kontrol_kaynak}' bulunamadı.")
            col_v = n + v_indeks[v_ref]
            r = e.deger
            ekle_A(a, col, +1.0)
            ekle_A(b, col, -1.0)
            ekle_A(col, a, +1.0)
            ekle_A(col, b, -1.0)
            ekle_A(col, col_v, -r)
            k += 1

        elif e.tur == "F":  # CCCS
            v_ref = e.kontrol_kaynak.upper()
            if v_ref not in v_indeks:
                raise DevreHatasi(f"CCCS '{e.isim}': Kontrol kaynağı '{e.kontrol_kaynak}' bulunamadı.")
            col_v = n + v_indeks[v_ref]
            beta = e.deger
            ekle_A(a, col_v, +beta)
            ekle_A(b, col_v, -beta)

    # 3) Başlangıç Durum Değişkenleri
    vc_prev = {e.isim: 0.0 for e in kapasitorler}
    ic_prev = {e.isim: 0.0 for e in kapasitorler}
    vl_prev = {e.isim: 0.0 for e in bobinler}
    il_prev = {e.isim: 0.0 for e in bobinler}

    dugum_voltajlari = {d: np.zeros(adim_sayisi) for d in dugumler}
    dugum_voltajlari["0"] = np.zeros(adim_sayisi)
    eleman_akimlari = {e.isim: np.zeros(adim_sayisi) for e in elemanlar}

    # t = 0 anındaki başlangıç gerilimleri (kaynaklar bağlı ise başlangıç değerleri)
    for e in elemanlar:
        if e.tur == "V":
            v0 = kaynak_degeri(e, 0.0)
            if e.dugum_p != "0":
                dugum_voltajlari[e.dugum_p][0] = v0

    # 4) Zaman Boyunca İlerleme (t_1 = h'den t_stop'a)
    for adim in range(1, adim_sayisi):
        t = zaman[adim]
        z = np.zeros(N, dtype=float)

        def ekle_z(satir: str | int, deger: float):
            r = indeks.get(satir) if isinstance(satir, str) else satir
            if r is not None:
                z[r] += deger

        # Bağımsız kaynaklar
        k = 0
        for e in elemanlar:
            if e.tur == "I":
                val = kaynak_degeri(e, t)
                ekle_z(e.dugum_p, -val)
                ekle_z(e.dugum_n, +val)
            elif e.tur == "V":
                val = kaynak_degeri(e, t)
                col = n + k
                ekle_z(col, val)
                k += 1
            elif e.tur in ("E", "H"):
                k += 1

        # Kapasitör geçmiş akımları: I_hist = G_eq · v_C(t-h) + i_C(t-h)
        for e in kapasitorler:
            g_eq = (2.0 * e.deger) / h
            i_hist = g_eq * vc_prev[e.isim] + ic_prev[e.isim]
            ekle_z(e.dugum_p, +i_hist)
            ekle_z(e.dugum_n, -i_hist)

        # Bobin geçmiş akımları: I_hist = i_L(t-h) + G_eq · v_L(t-h)
        for e in bobinler:
            g_eq = h / (2.0 * e.deger)
            i_hist = il_prev[e.isim] + g_eq * vl_prev[e.isim]
            ekle_z(e.dugum_p, -i_hist)
            ekle_z(e.dugum_n, +i_hist)

        # Çöz: A · x = z
        try:
            x = np.linalg.solve(A, z)
        except np.linalg.LinAlgError:
            raise DevreHatasi(f"Zaman t = {t:g}s anında MNA matrisi tekil, simülasyon devam edemiyor.")

        V_t = {"0": 0.0}
        for d in dugumler:
            val = float(x[indeks[d]])
            V_t[d] = val
            dugum_voltajlari[d][adim] = val

        # Eleman akımlarını ve durum değişkenlerini güncelle
        k = 0
        for e in elemanlar:
            vab = V_t[e.dugum_p] - V_t[e.dugum_n]

            if e.tur == "R":
                i = vab / e.deger
            elif e.tur == "C":
                g_eq = (2.0 * e.deger) / h
                i_hist = g_eq * vc_prev[e.isim] + ic_prev[e.isim]
                i = g_eq * vab - i_hist
                vc_prev[e.isim] = vab
                ic_prev[e.isim] = i
            elif e.tur == "L":
                g_eq = h / (2.0 * e.deger)
                i_hist = il_prev[e.isim] + g_eq * vl_prev[e.isim]
                i = g_eq * vab + i_hist
                vl_prev[e.isim] = vab
                il_prev[e.isim] = i
            elif e.tur == "I":
                i = kaynak_degeri(e, t)
            elif e.tur in ("V", "E", "H"):
                i = float(x[n + k])
                k += 1
            elif e.tur == "G":
                v_ctrl = V_t[e.kontrol_p] - V_t[e.kontrol_n]
                i = e.deger * v_ctrl
            elif e.tur == "F":
                col_v = n + v_indeks[e.kontrol_kaynak.upper()]
                i_ctrl = float(x[col_v])
                i = e.deger * i_ctrl

            eleman_akimlari[e.isim][adim] = i

    return TranCozum(zaman, dugum_voltajlari, eleman_akimlari, h, tstop)


# ==============================================================================
# ÇİZİM VE GÖRSELLEŞTİRME YARDIMCILARI
# ==============================================================================

def ascii_ciz(t: np.ndarray, y: np.ndarray, etiket: str = "V(out)", genislik: int = 55, yukseklik: int = 12) -> str:
    """Terminalde gösterilmek üzere ASCII dalga şekli çizer."""
    y_min, y_max = float(np.min(y)), float(np.max(y))
    if math.isclose(y_min, y_max, abs_tol=1e-12):
        y_max += 1.0
        y_min -= 1.0

    izgara = [[" " for _ in range(genislik)] for _ in range(yukseklik)]
    adim = max(1, len(t) // genislik)
    t_secilmis = t[::adim][:genislik]
    y_secilmis = y[::adim][:genislik]

    for col, val in enumerate(y_secilmis):
        oran = (val - y_min) / (y_max - y_min)
        row = yukseklik - 1 - int(oran * (yukseklik - 1))
        row = max(0, min(yukseklik - 1, row))
        izgara[row][col] = "●"

    satirlar = [f"┌─ {etiket} (ASCII Grafiği) " + "─" * max(2, genislik - len(etiket) - 15) + "┐"]
    for r in range(yukseklik):
        etiket_y = f"{y_max - r * (y_max - y_min) / (yukseklik - 1):>8.2g} │"
        satirlar.append(etiket_y + "".join(izgara[r]) + "│")
    satirlar.append(" " * 9 + "└" + "─" * genislik + "┘")
    satirlar.append(f"{'t=0':>12}" + f"{t[-1]:>{genislik - 4}.2g} s")
    return "\n".join(satirlar)


def svg_kaydet(t: np.ndarray, y_dict: dict[str, np.ndarray], dosya_yolu: str, baslik: str = "Geçici Analiz"):
    """Sonuçları yüksek çözünürlüklü vektörel SVG grafiği olarak kaydeder."""
    renkler = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2"]
    genislik, yukseklik = 800, 450
    kenar_l, kenar_r, kenar_t, kenar_b = 70, 40, 50, 50
    grafik_w = genislik - kenar_l - kenar_r
    grafik_h = yukseklik - kenar_t - kenar_b

    t_min, t_max = float(t[0]), float(t[-1])
    tum_y = np.concatenate(list(y_dict.values()))
    y_min, y_max = float(np.min(tum_y)), float(np.max(tum_y))
    if math.isclose(y_min, y_max, abs_tol=1e-12):
        y_max += 1.0
        y_min -= 1.0

    def t_to_x(val):
        return kenar_l + (val - t_min) / (t_max - t_min) * grafik_w

    def y_to_y(val):
        return kenar_t + (y_max - val) / (y_max - y_min) * grafik_h

    svg_parcalar = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {genislik} {yukseklik}" style="background:#ffffff; font-family:sans-serif;">',
        f'<text x="{genislik/2}" y="30" text-anchor="middle" font-size="18" font-weight="bold" fill="#1e293b">{baslik}</text>',
        f'<rect x="{kenar_l}" y="{kenar_t}" width="{grafik_w}" height="{grafik_h}" fill="#f8fafc" stroke="#cbd5e1"/>',
    ]

    for i in range(5):
        gy = kenar_t + i * grafik_h / 4
        y_val = y_max - i * (y_max - y_min) / 4
        svg_parcalar.append(f'<line x1="{kenar_l}" y1="{gy}" x2="{kenar_l+grafik_w}" y2="{gy}" stroke="#e2e8f0" stroke-dasharray="4"/>')
        svg_parcalar.append(f'<text x="{kenar_l - 10}" y="{gy + 4}" text-anchor="end" font-size="11" fill="#64748b">{y_val:.2g}V</text>')

    for i in range(5):
        gx = kenar_l + i * grafik_w / 4
        t_val = t_min + i * (t_max - t_min) / 4
        svg_parcalar.append(f'<line x1="{gx}" y1="{kenar_t}" x2="{gx}" y2="{kenar_t+grafik_h}" stroke="#e2e8f0" stroke-dasharray="4"/>')
        svg_parcalar.append(f'<text x="{gx}" y="{kenar_t + grafik_h + 20}" text-anchor="middle" font-size="11" fill="#64748b">{t_val:.2g}s</text>')

    for idx, (isim, y) in enumerate(y_dict.items()):
        renk = renkler[idx % len(renkler)]
        adim = max(1, len(t) // 400)
        noktalar = [f"{t_to_x(t[i]):.1f},{y_to_y(y[i]):.1f}" for i in range(0, len(t), adim)]
        svg_parcalar.append(f'<polyline fill="none" stroke="{renk}" stroke-width="2.2" points="{" ".join(noktalar)}"/>')
        lx = kenar_l + idx * 100 + 10
        ly = kenar_t - 15
        svg_parcalar.append(f'<line x1="{lx}" y1="{ly}" x2="{lx+20}" y2="{ly}" stroke="{renk}" stroke-width="3"/>')
        svg_parcalar.append(f'<text x="{lx+25}" y="{ly+4}" font-size="12" fill="#334155">{isim}</text>')

    svg_parcalar.append('</svg>')
    with open(dosya_yolu, "w", encoding="utf-8") as f:
        f.write("\n".join(svg_parcalar))
