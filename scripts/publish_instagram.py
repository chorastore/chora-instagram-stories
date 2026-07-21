#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chora Store - Instagram Hikaye Yayinlayici (GitHub Actions icinde calisir)

Gunde 4 kez (08 / 12 / 16 / 20 Istanbul saati) tetiklenir. Her calistirmada:
  1. FB_ACCESS_TOKEN (repo secret) ile Instagram Business hesabinin ID'sini bulur.
  2. Su anki Istanbul saatine gore hangi "slot" (1-4) oldugunu belirler.
  3. images/<bugun>/manifest.json dosyasindan o slota ait gorseli bulur
     (bu dosya, ayri bir gunluk adimda generate_daily_stories.py + push_to_github.py
     tarafindan repoya pushlanir).
  4. raw.githubusercontent.com uzerinden herkese acik image_url ile Instagram
     Graph API /media -> /media_publish akisini calistirip Story'yi yayinlar.

Not: Instagram Graph API, Story'lere tiklanabilir link sticker eklemeyi
programatik olarak desteklemiyor - bu adim yalniz gorseli paylasir.

GUVENLIK: Bu script asla erisim tokenlerini (access_token) print/log etmez -
loglar bu public repoda herkese acik goruntulenebiliyor.
"""
import os
import json
import time
import datetime
import urllib.request
import urllib.parse

FB_TOKEN = os.environ["FB_ACCESS_TOKEN"]
REPO = "chorastore/chora-instagram-stories"
BRANCH = "main"
GRAPH = "https://graph.facebook.com/v21.0"

SLOT_HOURS = {8: 1, 12: 2, 16: 3, 20: 4}


def _redact(obj):
    """Deep-copy a dict/list, replacing any 'access_token' values before logging."""
    if isinstance(obj, dict):
        return {k: ("***REDACTED***" if k == "access_token" else _redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


def api_get(path, params):
    qs = urllib.parse.urlencode(params)
    url = f"{GRAPH}/{path}?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"DEBUG HTTPError {e.code} on GET {path}: {body}")
        raise


def api_post(path, data):
    url = f"{GRAPH}/{path}"
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode(errors="replace")
        print(f"DEBUG HTTPError {e.code} on POST {path}: {err_body}")
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
    print(f"DEBUG /me/accounts response (redacted): {_redact(pages)}")
    for p in pages.get("data", []):
        page_id = p["id"]
        page_token = p.get("access_token", FB_TOKEN)
        # Page-level fields like instagram_business_account must be read using
        # that page's own access token, not the top-level system user token.
        info = api_get(page_id, {"fields": "instagram_business_account", "access_token": page_token})
        print(f"DEBUG page {page_id} instagram_business_account lookup (redacted): {_redact(info)}")
        if "instagram_business_account" in info:
            return info["instagram_business_account"]["id"]
    raise SystemExit(
        "Instagram Business Account bulunamadi. Facebook Sayfasi Instagram hesabina "
        "bagli mi ve sistem kullanicisinin bu sayfaya erisimi var mi kontrol et."
    )


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
    if key not in manifest:
        print(f"Slot {slot} icin gorsel manifestte yok, atlaniyor. Manifest: {manifest}")
        return

    filename = manifest[key]
    image_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/images/{today}/{filename}"

    ig_user_id = get_ig_user_id()
    print(f"IG business account: {ig_user_id}")
    print(f"Paylasilacak gorsel (slot {slot}): {image_url}")

    created = api_post(f"{ig_user_id}/media", {
        "media_type": "STORIES",
        "image_url": image_url,
        "access_token": FB_TOKEN,
    })
    if "id" not in created:
        raise SystemExit(f"Media olusturulamadi: {_redact(created)}")
    creation_id = created["id"]
    print(f"Media olusturuldu: {creation_id}")

    time.sleep(10)

    published = api_post(f"{ig_user_id}/media_publish", {
        "creation_id": creation_id,
        "access_token": FB_TOKEN,
    })
    print(f"Yayinlandi (redacted): {_redact(published)}")


if __name__ == "__main__":
    main()
