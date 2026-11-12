"""Testler:  python3 -m unittest -v"""
import math
import unittest

import numpy as np

from mna import DevreHatasi, coz, coz_ac, polar
from netlist import deger_oku, netlist_oku


def cozumle_dc(metin):
    return coz(netlist_oku(metin))


def cozumle_ac(metin, frekans=None):
    return coz_ac(netlist_oku(metin), frekans=frekans)


class DegerOkuma(unittest.TestCase):
    def test_onekler(self):
        for metin, beklenen in [("1k", 1e3), ("4.7u", 4.7e-6), ("2meg", 2e6), ("10", 10),
                                ("3m", 3e-3), ("1e3", 1e3), ("5V", 5), ("2mA", 2e-3),
                                ("100n", 1e-7), ("1kohm", 1e3), ("2.2e-3", 2.2e-3),
                                ("10uF", 10e-6), ("5mH", 5e-3)]:
            self.assertAlmostEqual(deger_oku(metin), beklenen, msg=metin)

    def test_gecersiz(self):
        with self.assertRaises(ValueError):
            deger_oku("abc")


class DCCozum(unittest.TestCase):
    def test_gerilim_bolucu(self):
        c = cozumle_dc("V1 1 0 10\nR1 1 2 1k\nR2 2 0 2k")
        self.assertAlmostEqual(c.dugum_voltajlari["2"], 20 / 3)
        self.assertAlmostEqual(c.eleman_akimlari["R1"], 10 / 3000)
        self.assertAlmostEqual(c.eleman_akimlari["V1"], -10 / 3000)  # SPICE işaret kuralı

    def test_akim_kaynagi_paralel_direnc(self):
        # 2 mA, 0'dan 1'e basıyor, 1k üzerinden -> V(1) = 2 V
        c = cozumle_dc("I1 0 1 2m\nR1 1 0 1k")
        self.assertAlmostEqual(c.dugum_voltajlari["1"], 2.0)

    def test_akim_bolucu(self):
        c = cozumle_dc("I1 0 1 3\nR1 1 0 1\nR2 1 0 2")
        self.assertAlmostEqual(c.eleman_akimlari["R1"], 2.0)
        self.assertAlmostEqual(c.eleman_akimlari["R2"], 1.0)

    def test_super_dugum(self):
        c = cozumle_dc("V1 1 0 10\nR1 1 2 2\nV2 2 3 4\nR2 2 0 4\nR3 3 0 8\nI1 0 3 1")
        self.assertAlmostEqual(c.dugum_voltajlari["2"], 6.5 / 0.875)
        self.assertAlmostEqual(c.dugum_voltajlari["2"] - c.dugum_voltajlari["3"], 4)

    def test_tellegen_dc(self):
        c = cozumle_dc("V1 1 0 12\nR1 1 2 1k\nR2 2 3 2k\nR3 1 4 3k\nR4 4 0 1k\n"
                       "R5 2 4 4.7k\nR6 2 0 10k\nI1 0 3 2m")
        self.assertAlmostEqual(sum(c.eleman_gucleri.values()), 0, places=12)

    def test_isimli_dugumler_ve_gnd(self):
        c = cozumle_dc("Vin giris gnd 9\nRa giris cikis 1k\nRb cikis GND 2k")
        self.assertAlmostEqual(c.dugum_voltajlari["cikis"], 6.0)

    def test_dc_kararli_durum_kapasitor_ve_bobin(self):
        # DC'de C açık devre (I=0), L kısa devre (V=0)
        c = cozumle_dc("V1 1 0 12\nR1 1 2 1k\nL1 2 3 10m\nR2 3 0 2k\nC1 3 0 10u")
        # L1 kısa devre olduğundan V(2) = V(3) = 12 * 2k / 3k = 8V
        self.assertAlmostEqual(c.dugum_voltajlari["2"], 8.0)
        self.assertAlmostEqual(c.dugum_voltajlari["3"], 8.0)
        self.assertAlmostEqual(c.eleman_akimlari["C1"], 0.0)
        self.assertAlmostEqual(c.eleman_akimlari["L1"], 4e-3)


class ACCozumTest(unittest.TestCase):
    def test_rc_alcak_geciren_kesim_frekansi(self):
        # R = 1k, C = 1u -> fc = 1 / (2*pi*R*C) ≈ 159.15494 Hz
        # Kesim frekansında Vout = Vin / sqrt(2) ve faz -45 derece
        fc = 1.0 / (2 * math.pi * 1000 * 1e-6)
        netlist = f"Vin 1 0 AC 10 0\nR1 1 2 1k\nC1 2 0 1u"
        c = cozumle_ac(netlist, frekans=fc)

        genlik, faz = polar(c.dugum_voltajlari["2"])
        self.assertAlmostEqual(genlik, 10.0 / math.sqrt(2), places=4)
        self.assertAlmostEqual(faz, -45.0, places=2)

    def test_rlc_seri_rezonans(self):
        # L = 10mH, C = 100nF, R = 10 ohm
        # f0 = 1 / (2*pi*sqrt(L*C))
        f0 = 1.0 / (2 * math.pi * math.sqrt(10e-3 * 100e-9))
        netlist = f".ac {f0}\nVin 1 0 AC 10 0\nR1 1 2 10\nL1 2 3 10m\nC1 3 0 100n"
        c = cozumle_ac(netlist)

        # Rezonansta empedans saf omiktir -> I devrede 10 V / 10 ohm = 1 A ve faz 0 olmalı
        i_r1 = c.eleman_akimlari["R1"]
        genlik_i, faz_i = polar(i_r1)
        self.assertAlmostEqual(genlik_i, 1.0, places=4)
        self.assertAlmostEqual(faz_i, 0.0, places=2)

        # Rezonansta bobin ve kapasitör gerilimleri birbirine zıt fazlı ve eşit büyüklüktedir
        v_l = c.eleman_gerilimleri["L1"]
        v_c = c.eleman_gerilimleri["C1"]
        genlik_vl, faz_vl = polar(v_l)
        genlik_vc, faz_vc = polar(v_c)
        self.assertAlmostEqual(genlik_vl, genlik_vc, places=3)
        self.assertAlmostEqual(faz_vl, +90.0, places=2)
        self.assertAlmostEqual(faz_vc, -90.0, places=2)

    def test_tellegen_ac_guc_dengesi(self):
        # Seri-paralel AC devrede karmaşık güç toplamı (Tellegen) sıfır olmalı
        netlist = """
        .ac 1k
        Vin 1 0 AC 12 30
        R1 1 2 500
        L1 2 3 50m
        C1 3 0 2u
        R2 2 0 1k
        I1 0 3 AC 10m -45
        """
        c = cozumle_ac(netlist)
        toplam_s = sum(c.eleman_gucleri.values())
        self.assertAlmostEqual(toplam_s.real, 0.0, places=10)
        self.assertAlmostEqual(toplam_s.imag, 0.0, places=10)

    def test_faz_acisi_kaynak(self):
        # 10 V ∠ 60° gerilim kaynağı
        c = cozumle_ac("V1 1 0 AC 10 60\nR1 1 0 2", frekans=1000)
        genlik, faz = polar(c.dugum_voltajlari["1"])
        self.assertAlmostEqual(genlik, 10.0)
        self.assertAlmostEqual(faz, 60.0)
        genlik_i, faz_i = polar(c.eleman_akimlari["R1"])
        self.assertAlmostEqual(genlik_i, 5.0)
        self.assertAlmostEqual(faz_i, 60.0)


class Hatalar(unittest.TestCase):
    def test_yuzen_dugum(self):
        with self.assertRaises(DevreHatasi):
            cozumle_dc("V1 1 0 5\nR1 1 0 1k\nR2 2 3 1k")

    def test_paralel_gerilim_kaynaklari(self):
        with self.assertRaises(DevreHatasi):
            cozumle_dc("V1 1 0 5\nV2 1 0 3\nR1 1 0 1k")

    def test_seri_akim_kaynaklari(self):
        with self.assertRaises(DevreHatasi):
            cozumle_dc("I1 0 1 1\nI2 1 0 2\nR1 0 2 1")

    def test_toprak_yok(self):
        with self.assertRaises(ValueError):
            cozumle_dc("V1 1 2 5\nR1 1 2 1k")

    def test_desteklenmeyen_tur(self):
        with self.assertRaises(ValueError):
            cozumle_dc("V1 1 0 5\nQ1 1 0 1")

    def test_gecersiz_frekans(self):
        with self.assertRaises(ValueError):
            cozumle_ac("V1 1 0 AC 10\nR1 1 0 1k", frekans=-50)


if __name__ == "__main__":
    unittest.main()
