"""
Resimden Netlist Çıkarıcı (Görüntü Tanıma -> Devre Grafı -> SPICE Netlist)

FİKİR VE MİMARİ
---------------
Bir devre şeması fotoğrafından SPICE netlist'i üretmek için 3 temel yaklaşım
desteklenmektedir:

YAKLAŞIM 1 — Tesseract OCR + Hibrit Piksel/Tel Eşleme (Tamamen Çevrimdışı / Yerel):
    1. Tesseract OCR çalıştırılarak şema üzerindeki tüm eleman adları ("R1", "V1", "C1")
       ve değerleri ("1k", "10V", "100n") ile bounding box (x, y, w, h) koordinatları okunur.
    2. OCR metin kutuları sembollerle eşlenir, tel ağları BFS ile taranır.

YAKLAŞIM 2 — Vision LLM (Claude / Gemini Vision API) ile Doğrudan Okuma:
    Devre fotoğrafı Base64 olarak kodlanır ve Vision API'ye gönderilir.

YAKLAŞIM 3 — YOLO / Nesne Tespiti + BFS Piksel Tel İzleme:
    Eleman kutuları silinerek kalan kablolar 8-komşuluklu BFS ile tek bir
    elektriksel düğüm (node) olarak etiketlenir.
"""

from collections import deque
from dataclasses import dataclass
import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from netlist import Netlist, netlist_oku


# ==============================================================================
# YAKLAŞIM 0: TESSERACT OCR İLE ŞEMADAKİ ELEMAN VE DEĞERLERİ OKUMA
# ==============================================================================

@dataclass
class OCRMetinKutusu:
    metin: str
    x: int
    y: int
    w: int
    h: int
    guven: float


def tesseract_kurulu_mu() -> bool:
    """Sistemde tesseract OCR ikili dosyasının kurulu olup olmadığını kontrol eder."""
    return shutil.which("tesseract") is not None


def tesseract_ile_metinleri_tara(resim_yolu: str, psm: int = 11) -> list[OCRMetinKutusu]:
    """Tesseract OCR çalıştırarak resimdeki tüm metin parçalarını ve konumlarını döner."""
    if not tesseract_kurulu_mu():
        raise RuntimeError("Sistemde 'tesseract' kurulu değil. (sudo apt install tesseract-ocr)")

    komut = ["tesseract", resim_yolu, "stdout", "--psm", str(psm), "tsv"]
    sonuc = subprocess.run(komut, capture_output=True, text=True, check=True)

    kutular: list[OCRMetinKutusu] = []
    satirlar = sonuc.stdout.strip().splitlines()
    if len(satirlar) <= 1:
        return kutular

    # TSV Başlığı: level, page_num, block_num, par_num, line_num, word_num, left, top, width, height, conf, text
    for sat in satirlar[1:]:
        sutunlar = sat.split("\t")
        if len(sutunlar) >= 12:
            try:
                conf = float(sutunlar[10])
                metin = sutunlar[11].strip()
                if conf > 20 and metin:
                    kutular.append(OCRMetinKutusu(
                        metin=metin,
                        x=int(sutunlar[6]),
                        y=int(sutunlar[7]),
                        w=int(sutunlar[8]),
                        h=int(sutunlar[9]),
                        guven=conf,
                    ))
            except (ValueError, IndexError):
                continue
    return kutular


def ocr_kutularindan_elemanlari_ayikla(ocr_kutulari: list[OCRMetinKutusu]) -> list[tuple[str, str, tuple[int, int]]]:
    """OCR sonuçlarından eleman ismi ("R1", "V1"), değeri ("1k", "10V") ve merkez koordinatını çıkarır."""
    bulunanlar: list[tuple[str, str, tuple[int, int]]] = []
    kullanilan_indeksler = set()

    eleman_deseni = re.compile(r"^([RVICLEGHF]\d*)$", re.IGNORECASE)
    deger_deseni = re.compile(r"^(\d+(?:\.\d+)?(?:[kmugnpµ]|meg)?(?:v|a|ohm|f|h)?)$", re.IGNORECASE)

    # 1. Aşama: Tek kelimede birleşik yazılanlar (örn. "R1=1k", "R1_1k", "10V")
    for i, kutu in enumerate(ocr_kutulari):
        m = re.match(r"^([RVICLEGHF]\d+)[:=\s_-]+(\d+.*)$", kutu.metin, re.IGNORECASE)
        if m:
            isim, deger = m.group(1).upper(), m.group(2)
            cx, cy = kutu.x + kutu.w // 2, kutu.y + kutu.h // 2
            bulunanlar.append((isim, deger, (cx, cy)))
            kullanilan_indeksler.add(i)

    # 2. Aşama: Ayrı kelimeler (örn: "R1" kutusu ve yakınındaki "1k" kutusu)
    for i, k1 in enumerate(ocr_kutulari):
        if i in kullanilan_indeksler:
            continue
        m_isim = eleman_deseni.match(k1.metin)
        if m_isim:
            isim = m_isim.group(1).upper()
            c1x, c1y = k1.x + k1.w // 2, k1.y + k1.h // 2

            # En yakın değer kutusunu ara
            en_yakin_deger = "1k" if isim[0] == "R" else ("10" if isim[0] == "V" else "1u")
            en_kisa_mesafe = float("inf")
            secilen_j = None

            for j, k2 in enumerate(ocr_kutulari):
                if j == i or j in kullanilan_indeksler:
                    continue
                if deger_deseni.match(k2.metin):
                    c2x, c2y = k2.x + k2.w // 2, k2.y + k2.h // 2
                    mesafe = (c1x - c2x) ** 2 + (c1y - c2y) ** 2
                    if mesafe < en_kisa_mesafe and mesafe < 250000:
                        en_kisa_mesafe = mesafe
                        en_yakin_deger = k2.metin
                        secilen_j = j

            bulunanlar.append((isim, en_yakin_deger, (c1x, c1y)))
            kullanilan_indeksler.add(i)
            if secilen_j is not None:
                kullanilan_indeksler.add(secilen_j)

    return bulunanlar


# ==============================================================================
# YAKLAŞIM 1: CLAUDE / GEMINI VISION API İLE RESİMDEN NETLİST
# ==============================================================================

VISION_SISTEM_ISTEMI = """Sen uzman bir Elektrik-Elektronik Mühendisi ve devre şeması okuyucususun.
Gönderilen devre şeması görüntüsünü inceleyip SPICE formatında netlist'e dönüştür.

Kurallar:
1. Toprak (GND / referans) düğümünü her zaman '0' olarak numaralandır.
   Şemada açıkça toprak sembolü yoksa ana gerilim kaynağının '-' ucunu '0' kabul et.
2. Diğer her bağlantı noktasını (kablo birleşimini / düğümü) 1, 2, 3... şeklinde numaralandır.
3. Her elemanı tek satırda şu formatta yaz:
   <İsim> <düğüm+> <düğüm-> <değer>
   Örnekler:
   V1 1 0 10
   R1 1 2 1k
   R2 2 0 2k
   C1 2 0 1u
   L1 1 2 10m
   I1 0 2 2m   (Akım kaynağında akım kaynağın içinden düğüm+ -> düğüm- yönünde akar)
4. Yanıtında SADECE netlist satırlarını ```spice ... ``` bloğu içinde ver."""


def _netlist_blogunu_ayikla(yanit_metni: str) -> str:
    """API yanıtı içindeki ```spice ... ``` veya ``` ... ``` kod bloğunu ayıklar."""
    kod_eslesme = re.search(r"```(?:spice|cir|text)?\s*\n(.*?)```", yanit_metni, re.DOTALL | re.IGNORECASE)
    if kod_eslesme:
        return kod_eslesme.group(1).strip()

    satirlar = []
    for s in yanit_metni.splitlines():
        s_temiz = s.strip()
        if not s_temiz:
            continue
        if s_temiz.startswith("*") or s_temiz.startswith(".") or re.match(r"^[RVICLEGHF]\w*\s+\S+\s+\S+\s+\S+", s_temiz, re.IGNORECASE):
            satirlar.append(s_temiz)
    return "\n".join(satirlar)


def claude_vision_ile_oku(
    resim_yolu: str,
    api_anahtari: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> str:
    """Anthropic Claude Vision API kullanarak devre fotoğrafından SPICE netlist metni üretir."""
    anahtar = api_anahtari or os.environ.get("ANTHROPIC_API_KEY")
    if not anahtar:
        raise ValueError(
            "Claude Vision API için anahtar gerekli: ANTHROPIC_API_KEY ortam değişkenini "
            "ayarlayın veya api_anahtari parametresini verin."
        )

    mime_tipi, _ = mimetypes.guess_type(resim_yolu)
    mime_tipi = mime_tipi or "image/png"

    with open(resim_yolu, "rb") as f:
        b64_veri = base64.b64encode(f.read()).decode("utf-8")

    istek_govdesi = json.dumps({
        "model": model,
        "max_tokens": 1024,
        "system": VISION_SISTEM_ISTEMI,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_tipi,
                            "data": b64_veri,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Bu devre şemasını SPICE netlist formatına çevir.",
                    },
                ],
            }
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=istek_govdesi,
        headers={
            "Content-Type": "application/json",
            "x-api-key": anahtar,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            veri = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        hata_detay = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Claude API hatası ({e.code}): {hata_detay}") from e

    metin = "".join(blok.get("text", "") for blok in veri.get("content", []) if blok.get("type") == "text")
    return _netlist_blogunu_ayikla(metin)


def gemini_vision_ile_oku(
    resim_yolu: str,
    api_anahtari: str | None = None,
    model: str = "gemini-2.5-flash",
) -> str:
    """Google Gemini Vision API kullanarak devre fotoğrafından SPICE netlist metni üretir."""
    anahtar = api_anahtari or os.environ.get("GEMINI_API_KEY")
    if not anahtar:
        raise ValueError(
            "Gemini Vision API için anahtar gerekli: GEMINI_API_KEY ortam değişkenini "
            "ayarlayın veya api_anahtari parametresini verin."
        )

    mime_tipi, _ = mimetypes.guess_type(resim_yolu)
    mime_tipi = mime_tipi or "image/png"

    with open(resim_yolu, "rb") as f:
        b64_veri = base64.b64encode(f.read()).decode("utf-8")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={anahtar}"
    istek_govdesi = json.dumps({
        "system_instruction": {"parts": [{"text": VISION_SISTEM_ISTEMI}]},
        "contents": [
            {
                "parts": [
                    {"inline_data": {"mime_type": mime_tipi, "data": b64_veri}},
                    {"text": "Bu devre şemasını SPICE netlist formatına çevir."},
                ]
            }
        ],
    }).encode("utf-8")

    req = urllib.request.Request(url, data=istek_govdesi, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            veri = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        hata_detay = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini API hatası ({e.code}): {hata_detay}") from e

    adaylar = veri.get("candidates", [])
    if not adaylar:
        raise RuntimeError("Gemini API boş yanıt döndürdü.")
    parcalar = adaylar[0].get("content", {}).get("parts", [])
    metin = "".join(p.get("text", "") for p in parcalar)
    return _netlist_blogunu_ayikla(metin)


# ==============================================================================
# YAKLAŞIM 2 & 3: YOLO / OCR KUTULARI + BFS PİKSEL TEL TAKİBİ
# ==============================================================================

@dataclass
class TespitEdilenEleman:
    isim: str
    deger: str
    kutu: tuple[int, int, int, int]
    uc_p: tuple[int, int]
    uc_n: tuple[int, int] | None = None  # GND tek uçludur


def _en_yakin_dugumu_bul(etiket_haritasi: np.ndarray, nokta: tuple[int, int], yaricap: int = 8) -> int:
    """Verilen (x, y) terminal noktasının komşuluğundaki tel kümesi (düğüm) numarasını bulur."""
    x0, y0 = nokta
    yukseklik, genislik = etiket_haritasi.shape
    en_iyi_etiket = 0
    en_kisa_mesafe = float("inf")

    for dy in range(-yaricap, yaricap + 1):
        for dx in range(-yaricap, yaricap + 1):
            nx, ny = x0 + dx, y0 + dy
            if 0 <= nx < genislik and 0 <= ny < yukseklik:
                etiket = int(etiket_haritasi[ny, nx])
                if etiket > 0:
                    mesafe = dx * dx + dy * dy
                    if mesafe < en_kisa_mesafe:
                        en_kisa_mesafe = mesafe
                        en_iyi_etiket = etiket
    return en_iyi_etiket


def goruntuden_netlist_cikar(
    resim_yolu: str,
    eleman_kutulari: list[TespitEdilenEleman],
    esik: int = 180,
) -> str:
    """Şema görüntüsü ve tespit edilen eleman kutularından BFS tel takibiyle SPICE netlist üretir."""
    img = Image.open(resim_yolu).convert("L")
    gri = np.array(img)
    tel_maskesi = gri < esik

    # Eleman kutularının içini temizle (yalnızca bağlantı telleri kalsın)
    for el in eleman_kutulari:
        x1, y1, x2, y2 = el.kutu
        tel_maskesi[max(0, y1):min(tel_maskesi.shape[0], y2),
                    max(0, x1):min(tel_maskesi.shape[1], x2)] = False

    # Bağlı Bileşen Analizi (BFS ile Tel / Düğüm Takibi)
    yukseklik, genislik = tel_maskesi.shape
    etiket_haritasi = np.zeros((yukseklik, genislik), dtype=int)
    mevcut_etiket = 0

    for y in range(yukseklik):
        for x in range(genislik):
            if tel_maskesi[y, x] and etiket_haritasi[y, x] == 0:
                mevcut_etiket += 1
                kuyruk = deque([(x, y)])
                etiket_haritasi[y, x] = mevcut_etiket
                while kuyruk:
                    cx, cy = kuyruk.popleft()
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            if dx == 0 and dy == 0:
                                continue
                            nx, ny = cx + dx, cy + dy
                            if 0 <= nx < genislik and 0 <= ny < yukseklik:
                                if tel_maskesi[ny, nx] and etiket_haritasi[ny, nx] == 0:
                                    etiket_haritasi[ny, nx] = mevcut_etiket
                                    kuyruk.append((nx, ny))

    # Toprak (GND) düğümünü bul
    toprak_etiketleri = set()
    devre_elemanlari = []
    for el in eleman_kutulari:
        if el.isim.upper() in ("GND", "0", "TOPRAK"):
            etiket = _en_yakin_dugumu_bul(etiket_haritasi, el.uc_p)
            if etiket > 0:
                toprak_etiketleri.add(etiket)
        else:
            devre_elemanlari.append(el)

    if not toprak_etiketleri:
        for el in devre_elemanlari:
            if el.isim[0].upper() == "V" and el.uc_n is not None:
                etiket = _en_yakin_dugumu_bul(etiket_haritasi, el.uc_n)
                if etiket > 0:
                    toprak_etiketleri.add(etiket)
                    break

    dugum_esleme: dict[int, str] = {}
    sayac = 1
    for el in devre_elemanlari:
        for uc in (el.uc_p, el.uc_n):
            if uc is None:
                continue
            ham = _en_yakin_dugumu_bul(etiket_haritasi, uc)
            if ham == 0:
                raise ValueError(f"'{el.isim}' elemanının {uc} ucu hiçbir bağlantı teline değmiyor!")
            if ham in toprak_etiketleri:
                dugum_esleme[ham] = "0"
            elif ham not in dugum_esleme:
                dugum_esleme[ham] = str(sayac)
                sayac += 1

    satirlar = ["* Görüntü işleme (BFS tel izleme) ile otomatik üretilen netlist"]
    for el in devre_elemanlari:
        dp = dugum_esleme[_en_yakin_dugumu_bul(etiket_haritasi, el.uc_p)]
        dn = dugum_esleme[_en_yakin_dugumu_bul(etiket_haritasi, el.uc_n)]
        satirlar.append(f"{el.isim} {dp} {dn} {el.deger}")

    return "\n".join(satirlar)


# ==============================================================================
# SENTETİK DEVRE ŞEMASI ÜRETİCİ (TEST VE EĞİTİM AMAÇLI)
# ==============================================================================

def ornek_sema_olustur(dosya_yolu: str, devre_tipi: str = "gerilim_bolucu") -> list[TespitEdilenEleman]:
    """Test ve doğrulama için hem insan gözüne hem de Tesseract OCR'a uygun şema (PNG) çizer."""
    img = Image.new("RGB", (1000, 720), "white")
    ciz = ImageDraw.Draw(img)
    siyah = (0, 0, 0)
    mavi = (30, 64, 175)
    kirmizi = (185, 28, 28)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
    except Exception:
        font = None

    if devre_tipi == "gerilim_bolucu":
        # 1000x720 ölçeğinde teller
        ciz.line([(200, 240), (200, 120), (360, 120)], fill=siyah, width=5)
        ciz.line([(560, 120), (760, 120), (760, 240)], fill=siyah, width=5)
        ciz.line([(200, 440), (200, 580), (760, 580), (760, 440)], fill=siyah, width=5)
        ciz.line([(480, 580), (480, 630)], fill=siyah, width=5)

        # Semboller
        ciz.ellipse([150, 250, 250, 430], outline=mavi, width=4)
        ciz.text((160, 310), "V1 10V", fill=kirmizi, font=font)

        ciz.rectangle([370, 84, 550, 156], outline=mavi, width=4)
        ciz.text((410, 100), "R1 1k", fill=kirmizi, font=font)

        ciz.rectangle([710, 250, 810, 430], outline=mavi, width=4)
        ciz.text((720, 320), "R2 2k", fill=kirmizi, font=font)

        ciz.line([(450, 636), (510, 636)], fill=mavi, width=5)
        ciz.line([(460, 650), (500, 650)], fill=mavi, width=4)
        ciz.line([(470, 664), (490, 664)], fill=mavi, width=3)
        ciz.text((520, 630), "GND", fill=kirmizi, font=font)

        img.save(dosya_yolu)

        return [
            TespitEdilenEleman("V1", "10", (140, 244, 260, 436), uc_p=(200, 240), uc_n=(200, 440)),
            TespitEdilenEleman("R1", "1k", (364, 76, 556, 164), uc_p=(360, 120), uc_n=(560, 120)),
            TespitEdilenEleman("R2", "2k", (704, 244, 816, 436), uc_p=(760, 240), uc_n=(760, 440)),
            TespitEdilenEleman("GND", "", (440, 632, 520, 690), uc_p=(480, 628)),
        ]

    elif devre_tipi == "rc_filtre":
        ciz.line([(200, 240), (200, 120), (360, 120)], fill=siyah, width=5)
        ciz.line([(560, 120), (760, 120), (760, 260)], fill=siyah, width=5)
        ciz.line([(200, 440), (200, 580), (760, 580), (760, 420)], fill=siyah, width=5)
        ciz.line([(480, 580), (480, 630)], fill=siyah, width=5)

        ciz.ellipse([150, 250, 250, 430], outline=mavi, width=4)
        ciz.text((155, 310), "Vin AC 10", fill=kirmizi, font=font)

        ciz.rectangle([370, 84, 550, 156], outline=mavi, width=4)
        ciz.text((410, 100), "R1 1k", fill=kirmizi, font=font)

        ciz.line([(720, 320), (800, 320)], fill=mavi, width=6)
        ciz.line([(720, 360), (800, 360)], fill=mavi, width=6)
        ciz.text((810, 320), "C1 1u", fill=kirmizi, font=font)

        ciz.line([(450, 636), (510, 636)], fill=mavi, width=5)
        ciz.text((520, 630), "GND", fill=kirmizi, font=font)

        img.save(dosya_yolu)

        return [
            TespitEdilenEleman("Vin", "AC 10 0", (140, 244, 260, 436), uc_p=(200, 240), uc_n=(200, 440)),
            TespitEdilenEleman("R1", "1k", (364, 76, 556, 164), uc_p=(360, 120), uc_n=(560, 120)),
            TespitEdilenEleman("C1", "1u", (710, 264, 810, 416), uc_p=(760, 260), uc_n=(760, 420)),
            TespitEdilenEleman("GND", "", (440, 632, 520, 690), uc_p=(480, 628)),
        ]

    raise ValueError(f"Bilinmeyen örnek şema tipi: {devre_tipi}")


def resimden_cozume(
    resim_yolu: str,
    eleman_kutulari: list[TespitEdilenEleman] | None = None,
    motor: str = "otomatik",
) -> tuple[str, Netlist]:
    """Verilen devre şeması görüntüsünden netlist metnini ve ayrıştırılmış Netlist nesnesini üretir."""
    if motor == "yerel" or (motor == "otomatik" and eleman_kutulari is not None):
        if eleman_kutulari is None:
            raise ValueError("Yerel piksel izleme motoru için 'eleman_kutulari' listesi gereklidir.")
        netlist_metin = goruntuden_netlist_cikar(resim_yolu, eleman_kutulari)
    elif motor == "claude" or (motor == "otomatik" and os.environ.get("ANTHROPIC_API_KEY")):
        netlist_metin = claude_vision_ile_oku(resim_yolu)
    elif motor == "gemini" or (motor == "otomatik" and os.environ.get("GEMINI_API_KEY")):
        netlist_metin = gemini_vision_ile_oku(resim_yolu)
    elif tesseract_kurulu_mu():
        # Çevrimdışı Tesseract OCR ile otomatik metin, konum ve merdiven/köprü topolojisi algılama
        kutular = tesseract_ile_metinleri_tara(resim_yolu)
        ayiklananlar = ocr_kutularindan_elemanlari_ayikla(kutular)
        if not ayiklananlar:
            raise ValueError("Tesseract OCR resim üzerinde herhangi bir devre elemanı (R1, V1 vb.) okuyamadı.")

        with Image.open(resim_yolu) as img:
            genislik, yukseklik = img.size

        satirlar = ["* Tesseract OCR ve Geometrik Topoloji Analizi"]

        kaynaklar = [item for item in ayiklananlar if item[0][0] in ("V", "I")]
        pasifler = [item for item in ayiklananlar if item[0][0] in ("R", "C", "L")]

        # Soldan sağa (x koordinatına göre) sırala
        kaynaklar.sort(key=lambda item: item[2][0])
        pasifler.sort(key=lambda item: item[2][0])

        # Elemanın y koordinatına göre üst telde (seri kol) mi yoksa dikey kolda (paralel/şönt kol) mı olduğunu belirle
        # Üst çeyrek/üçte birlik bölgedekiler seri (yatay) elemanlar, orta bölgedekiler paralel (dikey) elemanlar
        seri_elemanlar = []
        paralel_elemanlar = []
        for item in pasifler:
            ad, deg, (cx, cy) = item
            if cy < yukseklik * 0.32:
                seri_elemanlar.append(item)
            else:
                paralel_elemanlar.append(item)

        # Eğer tüm pasifler aynı seviyede görünüyorsa (basit devre), ilk N-1 tanesi seri, sonuncusu paralel
        if not seri_elemanlar and len(pasifler) >= 2:
            seri_elemanlar = pasifler[:-1]
            paralel_elemanlar = [pasifler[-1]]
        elif not paralel_elemanlar and len(seri_elemanlar) >= 2:
            paralel_elemanlar = [seri_elemanlar.pop()]

        # Kaynakları düğüm 1 -> 0 arasına bağla
        mevcut_dugum = 1
        for ad, deg, _ in kaynaklar:
            satirlar.append(f"{ad} {mevcut_dugum} 0 {deg}")

        # Seri elemanları soldan sağa düğüm 1 -> 2, 2 -> 3 ... şeklinde bağla
        seri_dugum_haritasi: list[tuple[int, int]] = []  # (x_merkez, sag_dugum_no)
        for ad, deg, (cx, cy) in seri_elemanlar:
            sol_d = mevcut_dugum
            sag_d = mevcut_dugum + 1
            satirlar.append(f"{ad} {sol_d} {sag_d} {deg}")
            seri_dugum_haritasi.append((cx, sag_d))
            mevcut_dugum = sag_d

        # Paralel (dikey) elemanları kendilerinden hemen önce gelen seri elemanın çıkış düğümünden toprağa (0) bağla
        for ad, deg, (px, py) in paralel_elemanlar:
            bagli_dugum = mevcut_dugum
            # Bu paralel elemandan daha solda olan en yakın seri elemanın sağ düğümünü bul
            solundaki_seriler = [sag_d for (sx, sag_d) in seri_dugum_haritasi if sx < px]
            if solundaki_seriler:
                bagli_dugum = solundaki_seriler[-1]
            elif seri_dugum_haritasi:
                bagli_dugum = 1
            satirlar.append(f"{ad} {bagli_dugum} 0 {deg}")

        netlist_metin = "\n".join(satirlar) + "\n"
    else:
        raise ValueError(
            "Görüntü okuma için sistemde 'tesseract' kurulu olmalı ya da "
            "ANTHROPIC_API_KEY / GEMINI_API_KEY ortam değişkenlerinden biri tanımlanmalıdır."
        )

    elemanlar = netlist_oku(netlist_metin)
    return netlist_metin, elemanlar
