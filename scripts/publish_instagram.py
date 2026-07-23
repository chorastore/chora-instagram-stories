#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chora Store - Instagram Hikaye Yayinlayici (GitHub Actions icinde calisir)

Gunde 4 kez (08 / 12 / 16 / 20 Istanbul saati) tetiklenir. Her calistirmada:
  1. FB_ACCESS_TOKEN (repo secret) ile Instagram Business hesabinin ID'sini bulur.
  2. Su anki Istanbul saatine gore hangi "slot" (1-4) oldugunu belirler.
  3. images/<bugun>/manifest.json dosyasindan o slota ait gorsel(ler)i bulur
     (bu dosya, ayri bir gunluk adimda generate_daily_stories.py + push_to_github.py
     tarafindan repoya pushlanir).
  4. raw.githubusercontent.com uzerinden herkese acik image_url ile Instagram
     Graph API /media -> /media_publish akisini calistirip Story'yi yayinlar.

Her slotun manifest degeri artik sirayla paylasilacak dosya adlarindan
olusan bir LISTE'dir (tek gorselli slotlar icin tek elemanli liste).
Liste birden fazla dosya iceriyorsa (ör. 16:00 "Last Chance" formatinda
3 farkli urun), bu gorseller ARKA ARKAYA (aralarinda kisa bir bekleme
ile) ayri ayri Story olarak yayinlanir.

Yedek davranis (fallback): Slot 3'un gorselleri Canva'dan indirilip gunun
klasorune eklenmesi yari-manuel bir adim oldugundan bazi gunler unutulabilir.
Bu durumda manifest'te "3" anahtari hic olmaz (push_to_github.py bunu
hataya dusurmeden atlar). 16:00 tetiklendiginde "3" yoksa, bu script o
saati BOS GECMEMEK icin FALLBACK_SLOTS sirasina gore ilk bulunan baska
slotun (varsayilan: story_1, sonra story_4, sonra story_2) gorselini
16:00'da paylasir.

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

SLOT_HOURS = {8: 1, 12: 2, 16: 3, 20: 4}

# Slot 3 (16:00, Last Chance) icin gorsel yoksa, o saati bos gecmemek adina
# sirasiyla denenecek yedek slotlar (ilk bulunan, tek gorsel olarak kullanilir).
FALLBACK_SLOTS_FOR_3 = ["1", "4", "2"]


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
    hour = now.hour
    for h, slot in SLOT_HOURS.items():
        if abs(hour - h) <= 1:
            return slot
    return None


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
    used_fallback = False
    if key not in manifest or not manifest[key]:
        if key == "3":
            for fb_key in FALLBACK_SLOTS_FOR_3:
                if manifest.get(fb_key):
                    print(
                        f"Slot 3 (16:00, Last Chance) icin gorsel yok - yedek olarak "
                        f"slot {fb_key}'un gorseli kullanilacak."
                    )
                    key = fb_key
                    used_fallback = True
                    break
            else:
                print(f"Slot {slot} icin gorsel yok ve yedek de bulunamadi, atlaniyor. Manifest: {manifest}")
                return
        else:
            print(f"Slot {slot} icin gorsel manifestte yok, atlaniyor. Manifest: {manifest}")
            return

    value = manifest[key]
    filenames = value if isinstance(value, list) else [value]
    if not filenames:
        print(f"Slot {slot} icin manifest listesi bos, atlaniyor.")
        return

    ig_user_id = get_ig_user_id()
    print(f"IG business account: {ig_user_id}")
    tag = " (yedek gorsel)" if used_fallback else ""
    print(f"Slot {slot} icin {len(filenames)} gorsel arka arkaya paylasilacak{tag}.")

    for i, filename in enumerate(filenames):
        image_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/images/{today}/{filename}"
        publish_one(ig_user_id, image_url)
        if i < len(filenames) - 1:
            time.sleep(15)  # ardisik hikayeler arasinda kisa bekleme


if __name__ == "__main__":
    main()
