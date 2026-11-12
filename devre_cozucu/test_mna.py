"""Testler:  python3 -m unittest -v"""
import math
import os
import unittest

import numpy as np

from laplace import coz_laplace
from mna import DevreHatasi, coz, coz_ac, polar
from netlist import deger_oku, netlist_oku
from ngspice_dogrula import dogrula, ngspice_betigi_olustur, ngspice_cikti_oku
from resimden_netlist import _netlist_blogunu_ayikla, ornek_sema_olustur, resimden_cozume
from transient import ascii_ciz, coz_tran, svg_kaydet


def cozumle_dc(metin):
    return coz(netlist_oku(metin))


def cozumle_ac(metin, frekans=None):
    return coz_ac(netlist_oku(metin), frekans=frekans)


def cozumle_tran(metin, tstep, tstop):
    return coz_tran(netlist_oku(metin), tstep, tstop)


def cozumle_laplace(metin, cikis_dugumu):
    return coz_laplace(netlist_oku(metin), cikis_dugumu=cikis_dugumu)


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
        self.assertAlmostEqual(c.eleman_akimlari["V1"], -10 / 3000)

    def test_akim_kaynagi_paralel_direnc(self):
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
        c = cozumle_dc("V1 1 0 12\nR1 1 2 1k\nL1 2 3 10m\nR2 3 0 2k\nC1 3 0 10u")
        self.assertAlmostEqual(c.dugum_voltajlari["2"], 8.0)
        self.assertAlmostEqual(c.dugum_voltajlari["3"], 8.0)
        self.assertAlmostEqual(c.eleman_akimlari["C1"], 0.0)
        self.assertAlmostEqual(c.eleman_akimlari["L1"], 4e-3)


class BagimliKaynaklar(unittest.TestCase):
    def test_vcvs_e_kaynagi(self):
        netlist = "V1 1 0 2\nE1 2 0 1 0 3\nR1 2 0 1k"
        c = cozumle_dc(netlist)
        self.assertAlmostEqual(c.dugum_voltajlari["1"], 2.0)
        self.assertAlmostEqual(c.dugum_voltajlari["2"], 6.0)
        self.assertAlmostEqual(c.eleman_akimlari["R1"], 6e-3)
        self.assertAlmostEqual(sum(c.eleman_gucleri.values()), 0, places=12)

    def test_vccs_g_kaynagi(self):
        netlist = "V1 1 0 2.5\nG1 0 2 1 0 4m\nR1 2 0 500"
        c = cozumle_dc(netlist)
        self.assertAlmostEqual(c.dugum_voltajlari["2"], 5.0)
        self.assertAlmostEqual(sum(c.eleman_gucleri.values()), 0, places=12)

    def test_ccvs_h_kaynagi(self):
        netlist = "V1 1 0 10\nR1 1 0 1k\nH1 2 0 V1 500\nR2 2 0 1k"
        c = cozumle_dc(netlist)
        self.assertAlmostEqual(c.dugum_voltajlari["2"], -5.0)
        self.assertAlmostEqual(sum(c.eleman_gucleri.values()), 0, places=12)

    def test_cccs_f_kaynagi(self):
        netlist = "V1 1 0 5\nR1 1 0 1k\nF1 0 2 V1 2\nR2 2 0 100"
        c = cozumle_dc(netlist)
        self.assertAlmostEqual(c.dugum_voltajlari["2"], -1.0)
        self.assertAlmostEqual(sum(c.eleman_gucleri.values()), 0, places=12)


class ACCozumTest(unittest.TestCase):
    def test_rc_alcak_geciren_kesim_frekansi(self):
        fc = 1.0 / (2 * math.pi * 1000 * 1e-6)
        netlist = "Vin 1 0 AC 10 0\nR1 1 2 1k\nC1 2 0 1u"
        c = cozumle_ac(netlist, frekans=fc)

        genlik, faz = polar(c.dugum_voltajlari["2"])
        self.assertAlmostEqual(genlik, 10.0 / math.sqrt(2), places=4)
        self.assertAlmostEqual(faz, -45.0, places=2)

    def test_rlc_seri_rezonans(self):
        f0 = 1.0 / (2 * math.pi * math.sqrt(10e-3 * 100e-9))
        netlist = f".ac {f0}\nVin 1 0 AC 10 0\nR1 1 2 10\nL1 2 3 10m\nC1 3 0 100n"
        c = cozumle_ac(netlist)

        i_r1 = c.eleman_akimlari["R1"]
        genlik_i, faz_i = polar(i_r1)
        self.assertAlmostEqual(genlik_i, 1.0, places=4)
        self.assertAlmostEqual(faz_i, 0.0, places=2)

        v_l = c.eleman_gerilimleri["L1"]
        v_c = c.eleman_gerilimleri["C1"]
        genlik_vl, faz_vl = polar(v_l)
        genlik_vc, faz_vc = polar(v_c)
        self.assertAlmostEqual(genlik_vl, genlik_vc, places=3)
        self.assertAlmostEqual(faz_vl, +90.0, places=2)
        self.assertAlmostEqual(faz_vc, -90.0, places=2)

    def test_tellegen_ac_guc_dengesi(self):
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
        c = cozumle_ac("V1 1 0 AC 10 60\nR1 1 0 2", frekans=1000)
        genlik, faz = polar(c.dugum_voltajlari["1"])
        self.assertAlmostEqual(genlik, 10.0)
        self.assertAlmostEqual(faz, 60.0)
        genlik_i, faz_i = polar(c.eleman_akimlari["R1"])
        self.assertAlmostEqual(genlik_i, 5.0)
        self.assertAlmostEqual(faz_i, 60.0)


class GeciciAnalizTest(unittest.TestCase):
    def test_rc_basamak_yaniti(self):
        netlist = "Vin 1 0 10\nR1 1 2 1k\nC1 2 0 1u"
        c = cozumle_tran(netlist, tstep=2e-6, tstop=5e-3)

        idx_1ms = int(round(1e-3 / 2e-6))
        v_1ms = c.dugum_voltajlari["2"][idx_1ms]
        beklenen_1ms = 10.0 * (1.0 - math.exp(-1.0))
        self.assertAlmostEqual(v_1ms, beklenen_1ms, delta=0.01)

        v_5ms = c.dugum_voltajlari["2"][-1]
        beklenen_5ms = 10.0 * (1.0 - math.exp(-5.0))
        self.assertAlmostEqual(v_5ms, beklenen_5ms, delta=0.01)

    def test_rl_basamak_yaniti(self):
        netlist = "Vin 1 0 10\nR1 1 2 100\nL1 2 0 100m"
        c = cozumle_tran(netlist, tstep=2e-6, tstop=5e-3)

        idx_1ms = int(round(1e-3 / 2e-6))
        i_1ms = c.eleman_akimlari["L1"][idx_1ms]
        self.assertAlmostEqual(i_1ms, 0.1 * (1.0 - math.exp(-1.0)), delta=0.001)

    def test_ascii_ve_svg_cizim(self):
        netlist = "Vin 1 0 10\nR1 1 2 1k\nC1 2 0 1u"
        c = cozumle_tran(netlist, tstep=50e-6, tstop=2e-3)
        cizim = ascii_ciz(c.zaman, c.dugum_voltajlari["2"], etiket="V(2)")
        self.assertIn("V(2)", cizim)
        self.assertIn("●", cizim)

        test_svg = "/tmp/test_grafik.svg"
        svg_kaydet(c.zaman, {"V(2)": c.dugum_voltajlari["2"]}, test_svg)
        self.assertTrue(os.path.exists(test_svg))
        os.remove(test_svg)


class LaplaceTest(unittest.TestCase):
    def test_laplace_rc_filtre(self):
        # R = 1k, C = 1u -> H(s) = 1000 / (s + 1000)
        netlist = "Vin 1 0 10\nR1 1 2 1k\nC1 2 0 1u"
        tf = cozumle_laplace(netlist, cikis_dugumu="2")

        self.assertEqual(len(tf.kutuplar), 1)
        self.assertAlmostEqual(tf.kutuplar[0].real, -1000.0, places=2)
        self.assertTrue(tf.kararli)
        self.assertAlmostEqual(tf.dc_kazanci, 1.0, places=4)

    def test_laplace_rlc_ikinci_derece(self):
        # R = 10, L = 10mH, C = 100nF -> H(s) = 1e9 / (s^2 + 1000s + 1e9)
        netlist = "Vin 1 0 10\nR1 1 2 10\nL1 2 3 10m\nC1 3 0 100n"
        tf = cozumle_laplace(netlist, cikis_dugumu="3")

        self.assertEqual(len(tf.kutuplar), 2)
        self.assertAlmostEqual(tf.kutuplar[0].real, -500.0, places=1)
        self.assertAlmostEqual(abs(tf.kutuplar[0].imag), 31618.82, delta=1.0)
        self.assertAlmostEqual(tf.omega_0, 31622.78, delta=1.0)
        self.assertAlmostEqual(tf.kalite_faktoru_Q, 31.62, delta=0.1)
        self.assertTrue(tf.kararli)
        self.assertAlmostEqual(tf.dc_kazanci, 1.0, places=4)

    def test_laplace_opamp_kazanc(self):
        # Av = 1 + 9k/1k = 10
        netlist = "Vin 1 0 1\nEopamp 3 0 1 2 100k\nRf 3 2 9k\nR1 2 0 1k"
        tf = cozumle_laplace(netlist, cikis_dugumu="3")
        self.assertAlmostEqual(tf.dc_kazanci, 10.0, places=2)


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


class ResimdenNetlistTest(unittest.TestCase):
    def test_gerilim_bolucu_semasindan_bfs_cozum(self):
        test_png = "/tmp/test_sema_gb.png"
        kutular = ornek_sema_olustur(test_png, "gerilim_bolucu")
        try:
            metin, nl = resimden_cozume(test_png, kutular, motor="yerel")
            self.assertIn("V1", metin)
            self.assertIn("R1", metin)
            self.assertIn("R2", metin)
            c = coz(nl)
            self.assertAlmostEqual(c.dugum_voltajlari["2"], 20.0 / 3.0, places=5)
        finally:
            if os.path.exists(test_png):
                os.remove(test_png)

    def test_rc_filtre_semasindan_ac_cozum(self):
        test_png = "/tmp/test_sema_rc.png"
        kutular = ornek_sema_olustur(test_png, "rc_filtre")
        try:
            _, nl = resimden_cozume(test_png, kutular, motor="yerel")
            fc = 1.0 / (2 * math.pi * 1000 * 1e-6)
            c = coz_ac(nl, frekans=fc)
            genlik, faz = polar(c.dugum_voltajlari["2"])
            self.assertAlmostEqual(genlik, 10.0 / math.sqrt(2), places=3)
            self.assertAlmostEqual(faz, -45.0, places=2)
        finally:
            if os.path.exists(test_png):
                os.remove(test_png)

    def test_vision_yanit_ayiklama(self):
        ornek_yanit = "İşte devrenin netlist karşılığı:\n```spice\n* Örnek\nV1 1 0 12\nR1 1 0 4k\n```\nBaşarılar!"
        ayiklanan = _netlist_blogunu_ayikla(ornek_yanit)
        nl = netlist_oku(ayiklanan)
        self.assertEqual(len(nl), 2)
        c = coz(nl)
        self.assertAlmostEqual(c.eleman_akimlari["R1"], 3e-3)


class NgspiceDogrulamaTest(unittest.TestCase):
    def test_kcl_kvl_ic_dogrulama(self):
        nl = netlist_oku("V1 1 0 10\nR1 1 2 2\nV2 2 3 4\nR2 2 0 4\nR3 3 0 8\nI1 0 3 1")
        rapor = dogrula(nl)
        self.assertTrue(rapor.basarili)
        self.assertLess(rapor.kcl_hatasi, 1e-12)
        self.assertLess(rapor.kvl_hatasi, 1e-12)

    def test_ngspice_betik_ve_cikti_karsilastirma(self):
        nl = netlist_oku("V1 1 0 10\nR1 1 2 1k\nR2 2 0 2k")
        betik = ngspice_betigi_olustur(nl)
        self.assertIn(".op", betik)
        self.assertIn("print v(1)", betik)
        self.assertIn("print v(2)", betik)

        sahte_ngspice_ciktisi = """
        Circuit: * MNA Devre Cozucu
        Doing analysis at TEMP = 27.000000 and TNOM = 27.000000
        v(1) = 1.000000e+01
        v(2) = 6.666667e+00
        """
        okunan = ngspice_cikti_oku(sahte_ngspice_ciktisi)
        self.assertAlmostEqual(okunan["1"], 10.0)
        self.assertAlmostEqual(okunan["2"], 6.666667)

        rapor = dogrula(nl, ngspice_referans_cikti=sahte_ngspice_ciktisi, tolerans=1e-5)
        self.assertTrue(rapor.basarili)
        self.assertTrue(rapor.ngspice_kullanildi)
        self.assertLess(rapor.ngspice_maks_fark, 1e-5)


if __name__ == "__main__":
    unittest.main()
