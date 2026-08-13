#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chora Store - Instagram Hikaye Yayinlayici (GitHub Actions icinde calisir)

Gunde 6 kez (08/10/12/14/16/20 Istanbul saati) tetiklenir. Her calistirmada:
  1. FB_ACCESS_TOKEN (repo secret) ile Instagram Business hesabinin ID'sini bulur.
  2. Su anki Istanbul saatine gore hangi "slot" (1,2,3,4,5,6,7,8,9) oldugunu belirler
     (bkz. SLOT_HOURS - saat -> slot anahtari eslemesi, dosya adlarindaki
     story_<slot>_... numarasiyla birebir eslesir).
  3. images/<bugun>/manifest.json dosyasindan o slota ait gorsel(ler)i bulur
     (bu dosya, ayri bir gunluk adimda generate_daily_stories.py + push_to_github.py
     tarafindan repoya pushlanir).
  4. raw.githubusercontent.com uzerinden herkese acik image_url ile Instagram
     Graph API /media -> /media_publish akisini calistirip Story'yi yayinlar.

Her slotun manifest degeri artik sirayla paylasilacak dosya adlarindan
olusan bir LISTE'dir (tek gorselli slotlar icin tek elemanli liste).
Liste birden fazla dosya iceriyorsa, bu gorseller ARKA ARKAYA (aralarinda
kisa bir bekleme ile) ayri ayri Story olarak yayinlanir.

16:00 (slot 3): workflow'un cron tetikleyicisi hala eski 4 slotluk halinde
(08/12/16/20 Istanbul, .github/workflows/publish-stories.yml - bu dosyayi
PAT'nin 'workflow' izni olmadigi icin bu script degistiremiyor). 2026-08-12'de
Umut'un karariyla 16:00 BILEREK BOS birakiliyor (manifest'te "3" anahtari
yok) - fallback/yedek gorsel KULLANILMIYOR, o saat sessizce atlaniyor. 09/10/
11/13/14 (slot 7/5/8/9/6) icin gorseller de hazir ama cron bu saatlerde
tetiklenmedigi surece hicbir zaman paylasilmayacak - ileride cron
'7 5,6,7,8,9,10,11,17 * * *' olarak guncellenirse (workflow dosyasi GitHub
web arayuzunden veya 'workflow' izinli bir token ile duzenlenerek) otomatik
olarak devreye girerler, script tarafinda baska bir degisiklik gerekmez.

Not: Instagram Graph API, Story'lere tiklanabilir link sticker eklemeyi
programatik olarak desteklemiyor - bu adim yalniz gorseli paylasir.
"""
import os
import json
import time
import datetime
import urllib.request
import urllib.parse
import urllib.error

FB_TOKEN = os.environ["FB_ACCESS_TOKEN"]
REPO = "chorastore/chora-instagram-stories"
BRANCH = "main"
GRAPH = "https://graph.facebook.com/v21.0"

SLOT_HOURS = {
    8: "1",   # story_1 - Worn
    10: "5",  # story_5 - Lifestyle
    12: "2",  # story_2 - Lifestyle
    14: "6",  # story_6 - Lifestyle
    16: "3",  # story_3 - Lifestyle (eskiden Last Chance, artik otomatik)
    20: "4",  # story_4 - Worn
}
# Not: story_7/8/9 (09:00/11:00/13:00) icin gorseller repoda hazir ama
# 2026-08-12'den itibaren cron/SLOT_HOURS'a dahil edilmiyor (Umut karari:
# gunde 6 slot - 08/10/12/14/16/20). Ileride eklenmek istenirse manifest'lerde
# zaten mevcutlar, sadece burada + workflow cron'unda saat eklemek yeterli.



def _read_http_error_body(e):
    try:
        return e.read().decode("utf-8", errors="replace")
    except Exception:
        return "(govde okunamadi)"


def api_get(path, params):
    qs = urllib.parse.urlencode(params)
    url = f"{GRAPH}/{path}?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"Graph API HATA govdesi (GET {path}): {_read_http_error_body(e)}")
        raise


def api_post(path, data):
    url = f"{GRAPH}/{path}"
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"Graph API HATA govdesi (POST {path}): {_read_http_error_body(e)}")
        raise


def istanbul_now():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=3)


def current_slot(now):
    """Slotlar artik bitisik saatlerde oldugu icin (08-14 arasi saat basi) TAM saat
    eslesmesi kullanilir - eski +-1 saat toleransi bitisik slotlari birbirine
    karistirirdi. Cron her hedef saatin birkac dakika sonrasinda tetiklendigi icin
    (bkz. workflow'daki '7 ...' offseti) now.hour tetiklenme aninda hedef saatle
    ayni olur."""
    return SLOT_HOURS.get(now.hour)


def get_ig_user_id():
    pages = api_get("me/accounts", {"access_token": FB_TOKEN})
    for p in pages.get("data", []):
        page_id = p["id"]
        info = api_get(page_id, {"fields": "instagram_business_account", "access_token": FB_TOKEN})
        if "instagram_business_account" in info:
            return info["instagram_business_account"]["id"]
    raise SystemExit(
        "Instagram Business Account bulunamadi. Facebook Sayfasi Instagram hesabina "
        "bagli mi ve sistem kullanicisinin bu sayfaya erisimi var mi kontrol et."
    )


def publish_one(ig_user_id, image_url):
    print(f"Paylasiliyor: {image_url}")
    created = api_post(f"{ig_user_id}/media", {
        "media_type": "STORIES",
        "image_url": image_url,
        "access_token": FB_TOKEN,
    })
    if "id" not in created:
        raise SystemExit(f"Media olusturulamadi: {created}")
    creation_id = created["id"]
    print(f"Media olusturuldu: {creation_id}")

    time.sleep(10)

    published = api_post(f"{ig_user_id}/media_publish", {
        "creation_id": creation_id,
        "access_token": FB_TOKEN,
    })
    print(f"Yayinlandi: {published}")


def main():
    now = istanbul_now()
    today = now.strftime("%Y-%m-%d")
    slot = current_slot(now)
    if slot is None:
        print(f"Su an ({now.strftime('%H:%M')} Istanbul) bir paylasim slotuna denk gelmiyor, cikiliyor.")
        return

    manifest_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/images/{today}/manifest.json"
    try:
        with urllib.request.urlopen(manifest_url, timeout=30) as r:
            manifest = json.loads(r.read().decode())
    except Exception as e:
        print(f"Manifest bulunamadi ({manifest_url}): {e}")
        return

    key = str(slot)
    if key not in manifest or not manifest[key]:
        print(f"Slot {slot} icin gorsel manifestte yok (bilerek bos birakilmis olabilir), atlaniyor.")
        return

    filenames = manifest[key] if isinstance(manifest[key], list) else [manifest[key]]
    if not filenames:
        print(f"Slot {slot} icin manifest listesi bos, atlaniyor.")
        return

    ig_user_id = get_ig_user_id()
    print(f"IG business account: {ig_user_id}")
    print(f"Slot {slot} icin {len(filenames)} gorsel arka arkaya paylasilacak.")

    for i, filename in enumerate(filenames):
        image_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/images/{today}/{filename}"
        publish_one(ig_user_id, image_url)
        if i < len(filenames) - 1:
            time.sleep(15)  # ardisik hikayeler arasinda kisa bekleme


if __name__ == "__main__":
    main()
