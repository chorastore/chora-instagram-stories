#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chora Store - Instagram Hikaye Yayinlayici (GitHub Actions icinde calisir)

Gunde 13 kez (08:00-20:00 Istanbul, saat basi) tetiklenir. Her calistirmada:
  1. FB_ACCESS_TOKEN (repo secret) ile Instagram Business hesabinin ID'sini bulur.
  2. images/<bugun>/manifest.json dosyasindan slot -> gorsel eslemesini okur.
  3. publish_state.json dosyasindan bugun ICIN HANGI SLOTLARIN ZATEN
     paylasildigini okur.
  4. "Vadesi gelmis" (saati gecmis) ama HENUZ paylasilmamis TUM slotlari
     bulur ve sirayla (arka arkaya, aralarinda kisa bekleme ile) paylasir.
     Bu CATCH-UP mantigi sayesinde:
       - GitHub Actions'in zamanlanmis tetikleyicisi saatlerce hic
         ateslenmese bile (bilinen bir GitHub guvenilirlik sorunu -
         2026-08-27 sabahi 08/09/10/11 slotlarinin hicbiri tetiklenmedi),
         bir sonraki calistirmada kacan slotlarin hepsi telafi edilir.
       - Onceki tasarimda kullanilan "su anki saat TAM olarak slot saatine
         esit mi" kontrolu, cron gecikmesi saat sinirini asinca (orn. 20:00
         hedefi 22:12'de tetiklenirse) sessizce hicbir sey paylasmiyordu.
         Artik "saati gelmis mi" (<=) kontrolu kullanildigi icin bu durum da
         otomatik telafi ediliyor.
  5. Her basarili slot sonrasi publish_state.json guncellenip repoya geri
     push edilir (actions/checkout'un birakip gitCredentiallari + workflow'a
     eklenen `permissions: contents: write` sayesinde), boylece ayni slot
     iki kez paylasilmaz (harici bir cron servisi de ayni workflow'u
     tetikliyor olsa bile idempotent kalir).
  6. raw.githubusercontent.com uzerinden herkese acik image_url ile Instagram
     Graph API /media -> /media_publish akisini calistirip Story'yi yayinlar.

Not: Instagram Graph API, Story'lere tiklanabilir link sticker eklemeyi
programatik olarak desteklemiyor - bu adim yalniz gorseli paylasir.
"""
import os
import json
import time
import datetime
import subprocess
import urllib.request
import urllib.parse
import urllib.error

FB_TOKEN = os.environ["FB_ACCESS_TOKEN"]
REPO = "chorastore/chora-instagram-stories"
BRANCH = "main"
GRAPH = "https://graph.facebook.com/v21.0"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
STATE_PATH = os.path.join(REPO_ROOT, "publish_state.json")

SLOT_HOURS = {
    8: "1",    # story_1 - Worn
    9: "7",    # story_7 - Lifestyle
    10: "5",   # story_5 - Lifestyle
    11: "8",   # story_8 - Lifestyle
    12: "2",   # story_2 - Lifestyle
    13: "9",   # story_9 - Lifestyle
    14: "6",   # story_6 - Lifestyle
    15: "10",  # story_10 - Lifestyle
    16: "3",   # story_3 - Lifestyle
    17: "11",  # story_11 - Lifestyle
    18: "12",  # story_12 - Lifestyle
    19: "13",  # story_13 - Lifestyle
    20: "4",   # story_4 - Worn
}
# Gunde 13 slot: 08:00'den 20:00'e kadar saat basi (Umut'un 2026-08-17 karari).


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


def load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"UYARI: publish_state.json okunamadi, bos state ile devam ediliyor: {e}")
        return {}


def save_and_push_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    def run(cmd):
        return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)

    run(["git", "config", "user.name", "chora-story-bot"])
    run(["git", "config", "user.email", "actions@users.noreply.github.com"])
    run(["git", "add", "publish_state.json"])
    diff = run(["git", "diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        return  # degisiklik yok
    commit = run(["git", "commit", "-m", "state: publish_state.json guncellendi"])
    if commit.returncode != 0:
        print(f"UYARI: git commit basarisiz: {commit.stderr}")
        return
    pull = run(["git", "pull", "--rebase", "origin", BRANCH])
    if pull.returncode != 0:
        print(f"UYARI: git pull --rebase basarisiz: {pull.stderr}")
    push = run(["git", "push", "origin", BRANCH])
    if push.returncode != 0:
        print(f"UYARI: publish_state.json push edilemedi (bir sonraki run yine de dogru calisir, sadece state gecici olarak local kalir): {push.stderr}")
    else:
        print("publish_state.json repoya push edildi.")


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

    manifest_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/images/{today}/manifest.json"
    try:
        with urllib.request.urlopen(manifest_url, timeout=30) as r:
            manifest = json.loads(r.read().decode())
    except Exception as e:
        print(f"Manifest bulunamadi ({manifest_url}): {e}")
        return

    state = load_state()
    posted_today = set(state.get(today, []))

    due_slots = [
        (hour, key) for hour, key in sorted(SLOT_HOURS.items())
        if hour <= now.hour and key not in posted_today and key in manifest and manifest[key]
    ]

    if not due_slots:
        print(f"Su an ({now.strftime('%H:%M')} Istanbul) icin bekleyen/eksik slot yok.")
        return

    ig_user_id = get_ig_user_id()
    print(f"IG business account: {ig_user_id}")
    if len(due_slots) > 1:
        print(f"UYARI: {len(due_slots)} slot birden telafi ediliyor (kacan tetiklemeler): "
              f"{[k for _, k in due_slots]}")

    for idx, (hour, slot) in enumerate(due_slots):
        filenames = manifest[slot] if isinstance(manifest[slot], list) else [manifest[slot]]
        filenames = [f for f in filenames if f]
        if not filenames:
            posted_today.add(slot)
            continue

        print(f"Slot {slot} (saat {hour:02d}:00 icin) - {len(filenames)} gorsel paylasilacak.")
        for i, filename in enumerate(filenames):
            image_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/images/{today}/{urllib.parse.quote(filename)}"
            publish_one(ig_user_id, image_url)
            if i < len(filenames) - 1:
                time.sleep(15)

        posted_today.add(slot)
        state[today] = sorted(posted_today, key=lambda s: int(s))
        save_and_push_state(state)

        if idx < len(due_slots) - 1:
            time.sleep(20)  # ardisik slotlar arasinda kisa bekleme


if __name__ == "__main__":
    main()
