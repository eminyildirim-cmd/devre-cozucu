"""
Resimden Netlist Çıkarıcı (Görüntü Tanıma -> Devre Grafı -> SPICE Netlist)

FİKİR VE MİMARİ
---------------
Bir devre şeması fotoğrafından SPICE netlist'i üretmek için literatürde ve
endüstride iki temel yaklaşım kullanılır. Bu modül her ikisini de içerir:

YAKLAŞIM 1 — Vision LLM (Claude / Gemini Vision API) ile Doğrudan Okuma:
    Devre fotoğrafı (el çizimi veya kitap şeması) Base64 olarak kodlanır ve
    yapılandırılmış bir mühendislik istemiyle (prompt) Vision API'ye gönderilir.
    Model elemanları, düğümleri ve kaynak yönlerini okuyup SPICE formatında döner.
    (Standart kütüphane `urllib.request` kullanır; ek paket kurulumu gerektirmez).

YAKLAŞIM 2 — YOLO / Nesne Tespiti + Piksel Tabanlı Tel İzleme (BFS Graf Çıkarımı):
    Akademik çalışmalarda (örn. CGHD veri seti + YOLO) kullanılan klasik boru hattı:
    1. Eleman Tespiti: Görüntüdeki elemanların sınıfları, değerleri ve sınır kutuları
       (bounding box: x1, y1, x2, y2) ile uç (terminal) noktaları belirlenir.
    2. Eleman Maskeleme: İkili (siyah-beyaz) görüntüde eleman kutularının içi silinir;
       böylece geriye YALNIZCA bağlantı kabloları (teller) kalır.
    3. Bağlı Bileşen Analizi (BFS / Flood-Fill): Kalan siyah tel pikselleri üzerinde
       Genişlik Öncelikli Arama (BFS) yapılarak birbirine bağlı her tel kümesi
       tek bir "elektriksel düğüm" (node) olarak numaralandırılır.
    4. Toprak (GND) Eşleştirme: Toprak sembolünün değdiği düğüm '0' yapılır.
    5. Netlist Üretimi: Her elemanın + ve - uçlarının hangi düğüm kümesine değdiği
       bulunarak `<İsim> <düğüm+> <düğüm-> <değer>` satırları oluşturulur.
"""

from collections import deque
from dataclasses import dataclass
import base64
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request

import numpy as np
from PIL import Image, ImageDraw

from netlist import Netlist, netlist_oku


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

    # Kod bloğu yoksa yorum veya eleman satırlarını süz
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
# YAKLAŞIM 2: YOLO KUTULARI + PİKSEL İZLEME (BFS) İLE GRAF VE NETLİST ÇIKARIMI
# ==============================================================================

@dataclass
class TespitEdilenEleman:
    """Görüntü üzerinde (YOLO veya şema okuyucu tarafından) tespit edilen devre elemanı.

    Alanlar:
        isim  : Eleman adı ("R1", "V1", "GND" vb.)
        deger : Eleman değeri ("1k", "10", "100n" vb.; GND için "")
        kutu  : Sınır kutusu (x1, y1, x2, y2) piksel koordinatları
        uc_p  : + ucun (veya 1. terminalin) görüntünün teliyle buluştuğu (x, y) koordinatı
        uc_n  : - ucun (veya 2. terminalin) görüntünün teliyle buluştuğu (x, y) koordinatı
    """
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
    """Şema görüntüsü ve tespit edilen eleman kutularından BFS tel takibiyle SPICE netlist üretir.

    Algoritma Adımları:
        1. Görüntüyü gri tonlamaya çevir ve eşikleme (thresholding) ile siyah pikselleri (telleri) bul.
        2. Eleman sınır kutularının (bounding box) içini maskele (sil) ki elemanın kendi çizimi
           iki ucunu kısa devre etmesin.
        3. Geriye kalan tel pikselleri üzerinde BFS (8-komşuluklu bağlı bileşen analizi) çalıştırarak
           her bağımsız tel ağını numaralandır (1, 2, 3...).
        5. GND sembolünün bağlı olduğu tel ağını '0' (toprak) olarak işaretle.
        6. Her elemanın uc_p ve uc_n koordinatlarının hangi tel ağına değdiğini bularak
           SPICE netlist satırlarını oluştur.
    """
    img = Image.open(resim_yolu).convert("L")
    gri = np.array(img)
    # Siyah çizgiler = True (1), Beyaz arka plan = False (0)
    tel_maskesi = gri < esik

    # Adım 2: Eleman kutularının içini temizle (yalnızca bağlantı telleri kalsın)
    for el in eleman_kutulari:
        x1, y1, x2, y2 = el.kutu
        tel_maskesi[max(0, y1):min(tel_maskesi.shape[0], y2),
                    max(0, x1):min(tel_maskesi.shape[1], x2)] = False

    # Adım 3: Bağlı Bileşen Analizi (BFS ile Tel / Düğüm Takibi)
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

    # Adım 4: Toprak (GND) düğümünü bul
    toprak_etiketleri = set()
    devre_elemanlari = []
    for el in eleman_kutulari:
        if el.isim.upper() in ("GND", "0", "TOPRAK"):
            etiket = _en_yakin_dugumu_bul(etiket_haritasi, el.uc_p)
            if etiket > 0:
                toprak_etiketleri.add(etiket)
        else:
            devre_elemanlari.append(el)

    # Eğer açıkça GND sembolü yoksa ilk gerilim kaynağının '-' ucunu toprak kabul et
    if not toprak_etiketleri:
        for el in devre_elemanlari:
            if el.isim[0].upper() == "V" and el.uc_n is not None:
                etiket = _en_yakin_dugumu_bul(etiket_haritasi, el.uc_n)
                if etiket > 0:
                    toprak_etiketleri.add(etiket)
                    break

    # Ham küme etiketlerini temiz SPICE düğüm numaralarına (0, 1, 2...) dönüştür
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

    # Adım 5: SPICE Netlist satırlarını üret
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
    """Test ve doğrulama için gerçek bir devre şeması görüntüsü (PNG) çizer
    ve üzerindeki elemanların koordinat kutularını (YOLO çıktısı formatında) döner.
    """
    img = Image.new("RGB", (500, 360), "white")
    ciz = ImageDraw.Draw(img)
    siyah = (0, 0, 0)
    mavi = (30, 64, 175)
    kirmizi = (185, 28, 28)

    if devre_tipi == "gerilim_bolucu":
        # Teller (Siyah çizgiler, kalınlık=3)
        # Üst tel: V1 üst ucundan (100, 120) -> (100, 60) -> R1 sol ucuna (180, 60)
        ciz.line([(100, 120), (100, 60), (180, 60)], fill=siyah, width=3)
        # Ara tel (Düğüm 2): R1 sağ ucundan (280, 60) -> (380, 60) -> R2 üst ucuna (380, 120)
        ciz.line([(280, 60), (380, 60), (380, 120)], fill=siyah, width=3)
        # Alt tel (Toprak - Düğüm 0): V1 alt ucundan (100, 220) -> (100, 290) -> (380, 290) -> R2 alt ucuna (380, 220)
        ciz.line([(100, 220), (100, 290), (380, 290), (380, 220)], fill=siyah, width=3)
        # Toprak bağlantı teli: (240, 290) -> (240, 315)
        ciz.line([(240, 290), (240, 315)], fill=siyah, width=3)

        # Eleman Sembolleri ve Etiketleri
        # V1: (70, 125) - (130, 215)
        ciz.ellipse([75, 130, 125, 210], outline=mavi, width=2)
        ciz.text((88, 155), "V1\n10V", fill=kirmizi)

        # R1: (185, 40) - (275, 80)
        ciz.rectangle([185, 42, 275, 78], outline=mavi, width=2)
        ciz.text((210, 50), "R1 1k", fill=kirmizi)

        # R2: (355, 125) - (405, 215)
        ciz.rectangle([360, 125, 400, 215], outline=mavi, width=2)
        ciz.text((365, 160), "R2\n2k", fill=kirmizi)

        # GND sembolü: (220, 316) - (260, 345)
        ciz.line([(225, 318), (255, 318)], fill=mavi, width=3)
        ciz.line([(230, 325), (250, 325)], fill=mavi, width=2)
        ciz.line([(235, 332), (245, 332)], fill=mavi, width=2)

        img.save(dosya_yolu)

        return [
            TespitEdilenEleman("V1", "10", (70, 122, 130, 218), uc_p=(100, 120), uc_n=(100, 220)),
            TespitEdilenEleman("R1", "1k", (182, 38, 278, 82), uc_p=(180, 60), uc_n=(280, 60)),
            TespitEdilenEleman("R2", "2k", (355, 122, 405, 218), uc_p=(380, 120), uc_n=(380, 220)),
            TespitEdilenEleman("GND", "", (220, 316, 260, 345), uc_p=(240, 314)),
        ]

    elif devre_tipi == "rc_filtre":
        # Üst tel: Vin (100, 120) -> (100, 60) -> R1 (180, 60)
        ciz.line([(100, 120), (100, 60), (180, 60)], fill=siyah, width=3)
        # Sağ üst tel: R1 (280, 60) -> (380, 60) -> C1 (380, 130)
        ciz.line([(280, 60), (380, 60), (380, 130)], fill=siyah, width=3)
        # Alt tel: Vin (100, 220) -> (100, 290) -> (380, 290) -> C1 (380, 210)
        ciz.line([(100, 220), (100, 290), (380, 290), (380, 210)], fill=siyah, width=3)
        ciz.line([(240, 290), (240, 315)], fill=siyah, width=3)

        ciz.ellipse([75, 130, 125, 210], outline=mavi, width=2)
        ciz.text((82, 155), "Vin\nAC 10", fill=kirmizi)
        ciz.rectangle([185, 42, 275, 78], outline=mavi, width=2)
        ciz.text((210, 50), "R1 1k", fill=kirmizi)
        ciz.line([(360, 160), (400, 160)], fill=mavi, width=4)
        ciz.line([(360, 180), (400, 180)], fill=mavi, width=4)
        ciz.text((405, 160), "C1 1u", fill=kirmizi)
        ciz.line([(225, 318), (255, 318)], fill=mavi, width=3)

        img.save(dosya_yolu)

        return [
            TespitEdilenEleman("Vin", "AC 10 0", (70, 122, 130, 218), uc_p=(100, 120), uc_n=(100, 220)),
            TespitEdilenEleman("R1", "1k", (182, 38, 278, 82), uc_p=(180, 60), uc_n=(280, 60)),
            TespitEdilenEleman("C1", "1u", (355, 132, 405, 208), uc_p=(380, 130), uc_n=(380, 210)),
            TespitEdilenEleman("GND", "", (220, 316, 260, 345), uc_p=(240, 314)),
        ]

    raise ValueError(f"Bilinmeyen örnek şema tipi: {devre_tipi}")


def resimden_cozume(
    resim_yolu: str,
    eleman_kutulari: list[TespitEdilenEleman] | None = None,
    motor: str = "otomatik",
) -> tuple[str, Netlist]:
    """Verilen devre şeması görüntüsünden netlist metnini ve ayrıştırılmış Netlist nesnesini üretir.

    motor:
        - 'yerel'   : Eleman kutuları + BFS piksel tel takibi kullanır (API anahtarı gerekmez).
        - 'claude'  : Claude Vision API kullanır (ANTHROPIC_API_KEY gerekir).
        - 'gemini'  : Gemini Vision API kullanır (GEMINI_API_KEY gerekir).
        - 'otomatik': eleman_kutulari verilmişse 'yerel', aksi halde ortamda bulunan API anahtarını kullanır.
    """
    if motor == "yerel" or (motor == "otomatik" and eleman_kutulari is not None):
        if eleman_kutulari is None:
            raise ValueError("Yerel piksel izleme motoru için 'eleman_kutulari' listesi gereklidir.")
        netlist_metin = goruntuden_netlist_cikar(resim_yolu, eleman_kutulari)
    elif motor == "claude" or (motor == "otomatik" and os.environ.get("ANTHROPIC_API_KEY")):
        netlist_metin = claude_vision_ile_oku(resim_yolu)
    elif motor == "gemini" or (motor == "otomatik" and os.environ.get("GEMINI_API_KEY")):
        netlist_metin = gemini_vision_ile_oku(resim_yolu)
    else:
        raise ValueError(
            "Görüntü okuma için ya 'eleman_kutulari' (YOLO çıktısı) verilmeli ya da "
            "ANTHROPIC_API_KEY / GEMINI_API_KEY ortam değişkenlerinden biri tanımlanmalıdır."
        )

    elemanlar = netlist_oku(netlist_metin)
    return netlist_metin, elemanlar
