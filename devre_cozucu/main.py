"""
Devre Çözücü — MNA (Modified Nodal Analysis)

Kullanım:
    # 1. DC analizi ve doğrulama:
    python3 main.py ornekler/gerilim_bolucu.cir --dogrula
    python3 main.py ornekler/kopru.cir --matris

    # 2. AC (Fazör) analizi:
    python3 main.py ornekler/rc_alcak_geciren.cir --ac 1k
    python3 main.py ornekler/rlc_rezonans.cir --ac 5032.9 --matris

    # 3. Geçici (Transient) analizi:
    python3 main.py ornekler/rc_basamak.cir --tran 10u 5m --ciz 2
    python3 main.py ornekler/rlc_basamak.cir --tran 1u 2m --ciz 2 3 --svg rlc.svg

    # 4. Laplace (s-Domeni) Transfer Fonksiyonu H(s):
    python3 main.py ornekler/rc_alcak_geciren.cir --laplace 2
    python3 main.py ornekler/rlc_rezonans.cir --laplace 3

    # 5. Resimden Netlist (Görüntü İşleme / Vision API):
    python3 main.py --ornek-sema gerilim_bolucu --dogrula
    python3 main.py --resim sema_fotografi.jpg
"""

import argparse
import os
import sys

import numpy as np

from laplace import TransferFonksiyonu, coz_laplace
from mna import ACCozum, Cozum, DevreHatasi, coz, coz_ac, polar
from netlist import deger_oku, netlist_oku
from ngspice_dogrula import dogrula
from resimden_netlist import ornek_sema_olustur, resimden_cozume
from transient import ascii_ciz, coz_tran, svg_kaydet


def bicimle(deger: float, birim: str) -> str:
    """0.0025 A -> '2.5 mA' gibi okunaklı yazım."""
    if abs(deger) < 1e-18:
        return f"0 {birim}"
    isaret = "-" if deger < 0 else ""
    d = abs(deger)
    for olcek, onek in [(1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""),
                        (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p")]:
        if d >= olcek * 0.9999:
            return f"{isaret}{d / olcek:.4g} {onek}{birim}"
    return f"{deger:.4g} {birim}"


def fazor_bicimle(z: complex, birim: str) -> str:
    genlik, faz = polar(z)
    genlik_str = bicimle(genlik, birim)
    faz_str = f"{faz:+.2f}°"
    kart_str = f"{z.real:.3g}{z.imag:+.3g}j"
    return f"{genlik_str:>11} ∠{faz_str:<8} ({kart_str})"


def matris_yazdir_dc(c: Cozum):
    print("\n── MNA sistemi:  A · x = z ─────────────────────────")
    w = max(len(s) for s in c.bilinmeyenler) + 2
    print(" " * 4 + "".join(f"{s:>{w + 4}}" for s in c.bilinmeyenler) + f"{'z':>{w + 2}}")
    for i, satir in enumerate(c.A):
        hucreler = "".join(f"{v:>{w + 4}.4g}" for v in satir)
        print(f"  [{hucreler}  |{c.z[i]:>{w}.4g} ]   x{i} = {c.bilinmeyenler[i]}")


def matris_yazdir_ac(c: ACCozum):
    print(f"\n── AC MNA sistemi:  A(ω) · x(ω) = z(ω)  [f = {bicimle(c.frekans, 'Hz')}, ω = {bicimle(c.omega, 'rad/s')}] ──")
    w = max(len(s) for s in c.bilinmeyenler) + 2
    print(" " * 4 + "".join(f"{s:>{w + 12}}" for s in c.bilinmeyenler) + f"{'z':>{w + 8}}")
    for i, satir in enumerate(c.A):
        hucreler = "".join(f"{v.real:.2g}{v.imag:+.2g}j".rjust(w + 12) for v in satir)
        z_str = f"{c.z[i].real:.2g}{c.z[i].imag:+.2g}j".rjust(w + 8)
        print(f"  [{hucreler}  |{z_str} ]   x{i} = {c.bilinmeyenler[i]}")


def rapor_dc(elemanlar, c: Cozum, matris=False):
    if matris:
        matris_yazdir_dc(c)

    print("\n── Düğüm voltajları (toprağa göre) ─────────────────")
    for d, v in c.dugum_voltajlari.items():
        if d != "0":
            print(f"  V({d}) = {bicimle(v, 'V')}")

    print("\n── Elemanlar ───────────────────────────────────────")
    print(f"  {'İsim':<8}{'Düğümler':<12}{'Gerilim':>12}{'Akım (+→-)':>14}{'Güç':>14}   Durum")
    for e in elemanlar:
        p = c.eleman_gucleri[e.isim]
        durum = "güç veriyor" if p < -1e-15 else ("güç tüketiyor" if p > 1e-15 else "—")
        print(
            f"  {e.isim:<8}{e.dugum_p + ' → ' + e.dugum_n:<12}"
            f"{bicimle(c.eleman_gerilimleri[e.isim], 'V'):>12}"
            f"{bicimle(c.eleman_akimlari[e.isim], 'A'):>14}"
            f"{bicimle(p, 'W'):>14}   {durum}"
        )

    toplam = sum(c.eleman_gucleri.values())
    verilen = -sum(p for p in c.eleman_gucleri.values() if p < 0)
    print(f"\n  Güç dengesi (Tellegen): Σ P = {toplam:.3e} W  "
          f"{'✓' if abs(toplam) <= 1e-9 * max(1.0, verilen) else '✗ HATA'}")


def rapor_ac(elemanlar, c: ACCozum, matris=False):
    if matris:
        matris_yazdir_ac(c)

    print(f"\n── AC Düğüm Voltajları (f = {bicimle(c.frekans, 'Hz')}, ω = {bicimle(c.omega, 'rad/s')}) ──")
    for d, v in c.dugum_voltajlari.items():
        if d != "0":
            v_rms = abs(v) / np.sqrt(2)
            print(f"  V({d}) = {fazor_bicimle(v, 'V')}  [RMS: {bicimle(v_rms, 'V')}]")

    print("\n── Elemanlar (Fazör Gerilim & Akım) ────────────────")
    print(f"  {'İsim':<8}{'Düğümler':<10}{'Gerilim (Tepe ∠ Faz)':<32}{'Akım (Tepe ∠ Faz)':<32}")
    for e in elemanlar:
        v = c.eleman_gerilimleri[e.isim]
        i = c.eleman_akimlari[e.isim]
        print(f"  {e.isim:<8}{e.dugum_p + ' → ' + e.dugum_n:<10}{fazor_bicimle(v, 'V'):<32}{fazor_bicimle(i, 'A'):<32}")

    print("\n── Eleman Güçleri (S = P + jQ) ─────────────────────")
    print(f"  {'İsim':<8}{'Görünür (|S|)':>14}{'Aktif (P)':>14}{'Reaktif (Q)':>14}   Karakter")
    for e in elemanlar:
        s = c.eleman_gucleri[e.isim]
        p = s.real
        q = s.imag
        if e.tur == "R":
            karakter = "omik (aktif tüketim)"
        elif e.tur == "C":
            karakter = "kapasitif (Q < 0 basar)"
        elif e.tur == "L":
            karakter = "endüktif (Q > 0 çeker)"
        elif p < -1e-15:
            karakter = "kaynak (aktif güç üretiyor)"
        else:
            karakter = "—"

        print(
            f"  {e.isim:<8}"
            f"{bicimle(abs(s), 'VA'):>14}"
            f"{bicimle(p, 'W'):>14}"
            f"{bicimle(q, 'VAR'):>14}   {karakter}"
        )

    toplam_s = sum(c.eleman_gucleri.values())
    print(f"\n  AC Güç dengesi (Tellegen): Σ S = {toplam_s.real:+.3e} W  {toplam_s.imag:+.3e}j VAR  "
          f"{'✓' if abs(toplam_s) <= 1e-9 else '✗ HATA'}")


def rapor_tran(c, ciz_dugumler=None, svg_dosya=None):
    print(f"\n── Geçici (Transient) Analiz Sonuçları ─────────────────")
    print(f"  Zaman Aralığı : 0 -> {bicimle(c.durma_zamani, 's')}")
    print(f"  Zaman Adımı   : {bicimle(c.adimi, 's')} ({len(c.zaman)} adım)")

    secilenler = []
    if ciz_dugumler:
        for cd in ciz_dugumler:
            d_norm = cd.replace("V(", "").replace(")", "").strip()
            if d_norm in c.dugum_voltajlari:
                secilenler.append(d_norm)
    if not secilenler:
        secilenler = [d for d in c.dugum_voltajlari if d != "0"][:2]

    for d in secilenler:
        print("\n" + ascii_ciz(c.zaman, c.dugum_voltajlari[d], etiket=f"V({d})"))

    if svg_dosya:
        y_dict = {f"V({d})": c.dugum_voltajlari[d] for d in secilenler}
        svg_kaydet(c.zaman, y_dict, svg_dosya, baslik="Geçici Analiz (Transient Simulation)")
        print(f"\n  ✓ Vektörel grafik kaydedildi: {svg_dosya}")


def rapor_laplace(tf: TransferFonksiyonu, cikis_dugumu: str):
    print(f"\n── Sembolik Laplace Transfer Fonksiyonu: H(s) = V({cikis_dugumu})/V_in ──")
    print(tf)

    print("── Kutup - Sıfır Analizi ──────────────────────────")
    if tf.kutuplar:
        k_str = ", ".join(f"{p.real:.4g}{p.imag:+.4g}j" if abs(p.imag) > 1e-6 else f"{p.real:.4g}" for p in tf.kutuplar)
        print(f"  Kutuplar (Poles) : {k_str}")
    else:
        print("  Kutuplar         : Yok")

    if tf.sifirlar:
        s_str = ", ".join(f"{z.real:.4g}{z.imag:+.4g}j" if abs(z.imag) > 1e-6 else f"{z.real:.4g}" for z in tf.sifirlar)
        print(f"  Sıfırlar (Zeros) : {s_str}")
    else:
        print("  Sıfırlar         : Yok")

    if tf.dc_kazanci is not None:
        print(f"  DC Kazancı H(0)  : {tf.dc_kazanci:.4g} ({(20 * np.log10(abs(tf.dc_kazanci)) if tf.dc_kazanci != 0 else -np.inf):.2f} dB)")

    kararlilik_str = "KARARLI (Tüm kutuplar sol yarı s-düzleminde)" if tf.kararli else "KARARSIZ (Sağ yarı düzlemde kutup var)"
    print(f"  Kararlılık       : {kararlilik_str}")

    if tf.omega_0 is not None:
        print("\n── 2. Dereceden Sistem Parametreleri ──────────────")
        print(f"  Doğal Frekans (ω0): {tf.omega_0:.4g} rad/s (f0 ≈ {tf.omega_0 / (2 * np.pi):.4g} Hz)")
        print(f"  Sönüm Oranı (ζ)   : {tf.sonum_orani_zeta:.4g}")
        if tf.kalite_faktoru_Q is not None:
            print(f"  Kalite Faktörü (Q): {tf.kalite_faktoru_Q:.4g}")


def main():
    ap = argparse.ArgumentParser(description="Devre çözücü (DC, AC Fazör, Geçici, Laplace ve Resimden Netlist)")
    ap.add_argument("dosya", nargs="?", default=None, help="netlist dosyası (.cir)")
    ap.add_argument("--resim", metavar="GORUNTU", default=None,
                    help="Devre şeması görüntüsünden (Vision API ile) netlist çıkar ve çöz")
    ap.add_argument("--ornek-sema", choices=["gerilim_bolucu", "rc_filtre"], default=None,
                    help="Örnek devre şeması görüntüsü (PNG) çiz, piksel izleme (BFS) ile netlist'e çevir ve çöz")
    ap.add_argument("--dogrula", action="store_true",
                    help="Çözümü ngspice ve bağımsız KCL/KVL denetçisi ile doğrula")
    ap.add_argument("--ac", nargs="?", const="1k", default=None,
                    help="AC fazör analizi yap (opsiyonel frekans, örn: --ac 1k)")
    ap.add_argument("--tran", nargs=2, metavar=("TSTEP", "TSTOP"), default=None,
                    help="Geçici analiz yap (adım ve süre, örn: --tran 10u 5m)")
    ap.add_argument("--laplace", metavar="CIKIS_DUGUMU", default=None,
                    help="Sembolik Laplace transfer fonksiyonu H(s) türet (örn: --laplace 2)")
    ap.add_argument("--ciz", nargs="*", default=None,
                    help="Grafiği çizilecek düğüm voltajları (örn: --ciz 2 3)")
    ap.add_argument("--svg", default=None,
                    help="Grafiği SVG dosyası olarak kaydet (örn: --svg cikis.svg)")
    ap.add_argument("--matris", action="store_true", help="kurulan MNA matrisini göster")
    args = ap.parse_args()

    try:
        if args.ornek_sema is not None:
            ornek_klasor = os.path.join(os.path.dirname(__file__), "ornekler")
            os.makedirs(ornek_klasor, exist_ok=True)
            png_yolu = os.path.join(ornek_klasor, f"sema_{args.ornek_sema}.png")
            kutular = ornek_sema_olustur(png_yolu, args.ornek_sema)
            netlist_metin, elemanlar = resimden_cozume(png_yolu, kutular, motor="yerel")
            kaynak_etiket = f"{png_yolu} [Görüntüden BFS Tel İzleme]"
            print(f"── Şema Görüntüsünden Çıkarılan Netlist ({png_yolu}) ──")
            print(netlist_metin)
            print()
        elif args.resim is not None:
            netlist_metin, elemanlar = resimden_cozume(args.resim)
            kaynak_etiket = f"{args.resim} [Vision API]"
            print(f"── Görüntüden Çıkarılan Netlist ({args.resim}) ──")
            print(netlist_metin)
            print()
        elif args.dosya is not None:
            with open(args.dosya, encoding="utf-8") as f:
                elemanlar = netlist_oku(f.read())
            kaynak_etiket = args.dosya
        else:
            ap.error("Lütfen bir netlist dosyası (.cir), --resim veya --ornek-sema belirtin.")
            return

        # Mod tespiti
        if args.laplace is not None:
            mod = "LAPLACE"
        elif args.tran is not None or elemanlar.tran is not None:
            mod = "TRAN"
            if args.tran is not None:
                tstep = deger_oku(args.tran[0])
                tstop = deger_oku(args.tran[1])
            else:
                tstep, tstop = elemanlar.tran
        elif args.ac is not None or elemanlar.frekans is not None or any(e.ac_genlik > 0 or e.tur in ("C", "L") for e in elemanlar):
            mod = "AC"
            frekans = deger_oku(args.ac) if args.ac is not None else (elemanlar.frekans or 1000.0)
        else:
            mod = "DC"

        print(f"Devre: {kaynak_etiket}  ({len(elemanlar)} eleman, Mod: {mod})")
        for e in elemanlar:
            print(f"  {e}")

        if mod == "LAPLACE":
            tf = coz_laplace(elemanlar, cikis_dugumu=args.laplace)
            rapor_laplace(tf, args.laplace)
        elif mod == "TRAN":
            c_tran = coz_tran(elemanlar, tstep, tstop)
            rapor_tran(c_tran, args.ciz, args.svg)
        elif mod == "AC":
            c_ac = coz_ac(elemanlar, frekans=frekans)
            rapor_ac(elemanlar, c_ac, args.matris)
        else:
            c_dc = coz(elemanlar)
            rapor_dc(elemanlar, c_dc, args.matris)
            if args.dogrula:
                dr = dogrula(elemanlar, c_dc)
                print(f"\n── Doğrulama Raporu (Aşama 4) ─────────────────────")
                print(f"  {dr.mesaj}")

    except (ValueError, DevreHatasi, OSError, RuntimeError) as hata:
        print(f"Hata: {hata}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    np.set_printoptions(precision=4, suppress=True)
    main()
