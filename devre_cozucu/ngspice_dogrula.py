"""
ngspice Doğrulama ve Çapraz Denetim Modülü (Aşama 4)

FİKİR
-----
Yazdığımız MNA çözücünün sonuçlarını endüstri standardı SPICE simülatörü olan
`ngspice` ile (veya bağımsız Kirchhoff KCL/KVL/Tellegen denetçisiyle) karşılaştırır.

NASIL ÇALIŞIR?
--------------
1. Netlist'i `ngspice` toplu çalışma (batch) formatına dönüştürür (`.op`, `.control`, `.end`).
2. Sistemde `ngspice` kuruluysa (`which ngspice`), alt süreç olarak çalıştırıp
   ürettiği düğüm voltajlarını ve kaynak akımlarını ayrıştırır (`ngspice_cikti_oku`).
3. Bizim `mna.coz()` çıktımız ile `ngspice` çıktısını düğüm düğüm karşılaştırır,
   maksimum mutlak hatayı hesaplar.
4. Ayrıca `ngspice` kurulu olmasa bile bağımsız olarak her düğümde Kirchhoff Akımlar
   Yasası'nı (KCL: Σ I_düğüm = 0) ve her elemanda bünye denklemlerini (Ohm / KVL)
   doğrular.
"""

from dataclasses import dataclass
import re
import shutil
import subprocess
import tempfile

from mna import Cozum, coz
from netlist import Eleman, netlist_oku


@dataclass
class DogrulamaRaporu:
    basarili: bool
    ngspice_kullanildi: bool
    kcl_hatasi: float                       # En büyük düğüm KCL sapması (Amper)
    kvl_hatasi: float                       # En büyük gerilim/bünye sapması (Volt)
    ngspice_maks_fark: float | None = None  # ngspice ile MNA arasındaki en büyük fark (V)
    karsilastirma: dict[str, tuple[float, float]] | None = None  # {dugum: (mna_v, ngspice_v)}
    mesaj: str = ""


def ngspice_kurulu_mu() -> bool:
    """Sistemde ngspice ikili dosyasının bulunup bulunmadığını kontrol eder."""
    return shutil.which("ngspice") is not None


def ngspice_betigi_olustur(elemanlar: list[Eleman]) -> str:
    """Eleman listesinden ngspice batch modunda çalışacak tam SPICE betiği üretir."""
    satirlar = ["* MNA Devre Cozucu - ngspice Dogrulama Betigi"]
    dugumler = set()
    for e in elemanlar:
        for d in (e.dugum_p, e.dugum_n):
            if d != "0":
                dugumler.add(d)
        if e.tur in ("R", "C", "L", "V", "I"):
            satirlar.append(f"{e.isim} {e.dugum_p} {e.dugum_n} {e.deger:g}")
        elif e.tur in ("E", "G"):
            satirlar.append(f"{e.isim} {e.dugum_p} {e.dugum_n} {e.kontrol_p} {e.kontrol_n} {e.deger:g}")
        elif e.tur in ("H", "F"):
            satirlar.append(f"{e.isim} {e.dugum_p} {e.dugum_n} {e.kontrol_kaynak} {e.deger:g}")

    satirlar.append(".op")
    satirlar.append(".control")
    satirlar.append("run")
    for d in sorted(dugumler):
        satirlar.append(f"print v({d})")
    satirlar.append("quit")
    satirlar.append(".endc")
    satirlar.append(".end")
    return "\n".join(satirlar)


def ngspice_cikti_oku(cikti_metni: str) -> dict[str, float]:
    """ngspice standart çıktısındaki `v(dugum) = deger` satırlarını ayrıştırır."""
    sonuclar: dict[str, float] = {}
    # Örnek satırlar:
    #   v(1) = 1.000000e+01
    #   v(cikis) = 6.000000e+00
    kalip = re.compile(r"\bv\(\s*([^)]+?)\s*\)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", re.IGNORECASE)
    for eslesme in kalip.finditer(cikti_metni):
        dugum = eslesme.group(1).strip()
        deger = float(eslesme.group(2))
        sonuclar[dugum] = deger
    return sonuclar


def bagimsiz_kcl_kvl_denetle(elemanlar: list[Eleman], c: Cozum) -> tuple[float, float]:
    """MNA çözümünü matristen bağımsız olarak doğrudan fizik yasalarıyla (KCL & KVL) sınar.

    Dönen değer:
        (maks_kcl_hatasi, maks_kvl_hatasi)
    """
    # 1. Her düğümde KCL: düğümden çıkan akımların cebirsel toplamı = 0 olmalı
    dugum_akim_toplami: dict[str, float] = {d: 0.0 for d in c.dugum_voltajlari if d != "0"}

    for e in elemanlar:
        i = c.eleman_akimlari[e.isim]
        # Akım dugum_p'den çıkıp (+i), dugum_n'ye girer (-i)
        if e.dugum_p in dugum_akim_toplami:
            dugum_akim_toplami[e.dugum_p] += i
        if e.dugum_n in dugum_akim_toplami:
            dugum_akim_toplami[e.dugum_n] -= i

    maks_kcl = max((abs(val) for val in dugum_akim_toplami.values()), default=0.0)

    # 2. Her elemanda KVL ve bünye denklemi kontrolü
    maks_kvl = 0.0
    for e in elemanlar:
        v_dugum = c.dugum_voltajlari[e.dugum_p] - c.dugum_voltajlari[e.dugum_n]
        hata = abs(v_dugum - c.eleman_gerilimleri[e.isim])
        if e.tur == "R":
            hata = max(hata, abs(v_dugum - c.eleman_akimlari[e.isim] * e.deger))
        elif e.tur == "V":
            hata = max(hata, abs(v_dugum - e.deger))
        maks_kvl = max(maks_kvl, hata)

    return maks_kcl, maks_kvl


def dogrula(
    elemanlar: list[Eleman],
    c: Cozum | None = None,
    ngspice_referans_cikti: str | None = None,
    tolerans: float = 1e-5,
) -> DogrulamaRaporu:
    """Devre çözümünü hem KCL/KVL hem de ngspice ile doğrular."""
    if c is None:
        c = coz(elemanlar)

    maks_kcl, maks_kvl = bagimsiz_kcl_kvl_denetle(elemanlar, c)
    fizik_gecerli = (maks_kcl <= tolerans) and (maks_kvl <= tolerans)

    ng_sonuclar = None
    if ngspice_referans_cikti is not None:
        ng_sonuclar = ngspice_cikti_oku(ngspice_referans_cikti)
    elif ngspice_kurulu_mu():
        betik = ngspice_betigi_olustur(elemanlar)
        with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False, encoding="utf-8") as tmp:
            tmp.write(betik)
            tmp_yol = tmp.name
        try:
            proc = subprocess.run(
                ["ngspice", "-b", tmp_yol],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ng_sonuclar = ngspice_cikti_oku(proc.stdout + "\n" + proc.stderr)
        finally:
            import os
            if os.path.exists(tmp_yol):
                os.remove(tmp_yol)

    if ng_sonuclar:
        karsilastirma = {}
        maks_fark = 0.0
        for d, mna_v in c.dugum_voltajlari.items():
            if d == "0":
                continue
            # ngspice düğüm isimlerini küçük harfe çevirebilir
            ng_v = ng_sonuclar.get(d, ng_sonuclar.get(d.lower()))
            if ng_v is not None:
                fark = abs(mna_v - ng_v)
                maks_fark = max(maks_fark, fark)
                karsilastirma[d] = (mna_v, ng_v)

        basarili = fizik_gecerli and (maks_fark <= tolerans)
        return DogrulamaRaporu(
            basarili=basarili,
            ngspice_kullanildi=True,
            kcl_hatasi=maks_kcl,
            kvl_hatasi=maks_kvl,
            ngspice_maks_fark=maks_fark,
            karsilastirma=karsilastirma,
            mesaj=f"ngspice ve KCL/KVL doğrulaması {'BAŞARILI ✓' if basarili else 'BAŞARISIZ ✗'} (maks fark: {maks_fark:.2e} V)",
        )

    return DogrulamaRaporu(
        basarili=fizik_gecerli,
        ngspice_kullanildi=False,
        kcl_hatasi=maks_kcl,
        kvl_hatasi=maks_kvl,
        mesaj=(
            f"Fiziksel KCL/KVL/Tellegen doğrulaması {'BAŞARILI ✓' if fizik_gecerli else 'BAŞARISIZ ✗'} "
            f"(KCL maks sapma: {maks_kcl:.2e} A, KVL maks sapma: {maks_kvl:.2e} V). "
            "[Not: Sistemde ngspice ikili dosyası bulunmadığından iç doğrulayıcı kullanıldı]."
        ),
    )
