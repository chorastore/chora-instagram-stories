#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chora Store - Bugunun hikaye gorsellerini GitHub deposuna pushlar
(chorastore/chora-instagram-stories), boylece Instagram Graph API'nin
Story yayinlamak icin istedigi herkese acik image_url saglanmis olur
(raw.githubusercontent.com uzerinden).

Slot 1/2/4 (08:00 / 12:00 / 20:00) icin tek gorsel; slot 3 (16:00, "Last
Chance") icin ARKA ARKAYA paylasilacak 3 farkli gorsel bekler:

    story_1_<...>.png
    story_2_<...>.png
    story_3_1_<...>.jpg
    story_3_2_<...>.jpg
    story_3_3_<...>.jpg
    story_4_<...>.png

manifest.json'da slot "3" anahtari artik TEK dosya adi degil, sirayla
paylasilacak 3 dosya adindan olusan bir LISTE olarak yazilir; digerleri
eskisi gibi tek dosya adi (string).

generate_daily_stories.py'den SONRA (ve slot 3 icin Canva'dan indirilen 3
gorsel gunun klasorune kaydedildikten SONRA) calistirilmali.

Kullanim: python3 push_to_github.py "<chora_dir_bash_path>"
"""
import os
import re
import sys
import glob
import json
import shutil
import subprocess
import datetime


def find_chora_dir():
    if len(sys.argv) > 1:
        return sys.argv[1]
    if os.environ.get("CHORA_DIR"):
        return os.environ["CHORA_DIR"]
    candidates = glob.glob("/sessions/*/mnt/Chora Store Folio*")
    if candidates:
        return candidates[0]
    raise SystemExit("Chora Store Folio klasoru bulunamadi.")


CHORA_DIR = find_chora_dir()
STORY_ROOT = os.path.join(CHORA_DIR, "Instagram Hikayeleri")
PAT_PATH = os.path.join(STORY_ROOT, "_script", "github_pat.txt")
REPO_URL_TMPL = "https://x-access-token:{pat}@github.com/chorastore/chora-instagram-stories.git"
WORKDIR = "/tmp/chora-instagram-stories-repo"


def run(cmd, cwd=None):
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def istanbul_today():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=3)).strftime("%Y-%m-%d")


STORY_RE = re.compile(r"^story_(\d)(?:_(\d))?_.+\.(png|jpg|jpeg)$", re.IGNORECASE)


def build_manifest(files):
    """Dosya adlarindan slot -> gorsel esleme (manifest) uretir.
    Slot 1/2/4: tek dosya adi (string). Slot 3: sira numarasina gore
    siralanmis dosya adlarindan olusan bir liste (arka arkaya paylasim).

    Ayni slota (veya slot 3'te ayni sira numarasina) birden fazla dosya
    denk gelirse (ör. onceki test/dev calistirmalarindan kalan eski
    dosyalar), dosyalar silinip/yeniden adlandirilamadigi icin hata
    vermek yerine EN YENI (mtime'i en buyuk) dosya secilir; digerleri
    yok sayilir ve konsola not dusulur."""
    singles = {}  # slot -> (mtime, fname)
    slot3 = {}    # sub_i -> (mtime, fname)
    unmatched = []
    ignored = []
    for p in files:
        fname = os.path.basename(p)
        m = STORY_RE.match(fname)
        if not m:
            unmatched.append(fname)
            continue
        slot, sub, _ext = m.group(1), m.group(2), m.group(3)
        mtime = os.path.getmtime(p)
        if slot == "3":
            sub_i = int(sub) if sub else 1
            prev = slot3.get(sub_i)
            if prev is None or mtime > prev[0]:
                if prev is not None:
                    ignored.append(prev[1])
                slot3[sub_i] = (mtime, fname)
            else:
                ignored.append(fname)
        else:
            prev = singles.get(slot)
            if prev is None or mtime > prev[0]:
                if prev is not None:
                    ignored.append(prev[1])
                singles[slot] = (mtime, fname)
            else:
                ignored.append(fname)

    if unmatched:
        raise SystemExit(f"Taninmayan dosya adi(lar): {unmatched}")
    for slot in ("1", "2", "4"):
        if slot not in singles:
            raise SystemExit(f"Slot {slot} icin gorsel bulunamadi.")
    if not slot3:
        raise SystemExit("Slot 3 (16:00, Last Chance) icin hic gorsel bulunamadi.")

    if ignored:
        print(f"Not: ayni slota ait eski/fazla dosya(lar) yok sayildi (en yeni kullanildi): {sorted(ignored)}")

    manifest = {slot: fname for slot, (_, fname) in singles.items()}
    manifest["3"] = [slot3[k][1] for k in sorted(slot3)]
    return manifest


def main():
    if not os.path.exists(PAT_PATH):
        raise SystemExit(
            f"GitHub PAT bulunamadi: {PAT_PATH}\n"
            "Once bu dosyaya (tek satir, bosluksuz) GitHub fine-grained personal "
            "access token'ini kaydet."
        )
    with open(PAT_PATH, "r", encoding="utf-8") as f:
        pat = f.read().strip()

    today_local = datetime.date.today().isoformat()  # generate_daily_stories.py ile ayni klasor adi
    src_dir = os.path.join(STORY_ROOT, today_local)
    if not os.path.isdir(src_dir):
        raise SystemExit(f"Bugunku gorsel klasoru yok: {src_dir}")

    files = sorted(
        glob.glob(os.path.join(src_dir, "story_*.png"))
        + glob.glob(os.path.join(src_dir, "story_*.jpg"))
        + glob.glob(os.path.join(src_dir, "story_*.jpeg"))
    )
    if not files:
        raise SystemExit(f"Gunun klasorunde story_*.png/jpg gorseli bulunamadi: {src_dir}")

    manifest = build_manifest(files)
    files_by_name = {os.path.basename(p): p for p in files}

    repo_url = REPO_URL_TMPL.format(pat=pat)

    if os.path.isdir(os.path.join(WORKDIR, ".git")):
        run(["git", "-C", WORKDIR, "remote", "set-url", "origin", repo_url])
        run(["git", "-C", WORKDIR, "fetch", "origin", "main"])
        run(["git", "-C", WORKDIR, "reset", "--hard", "origin/main"])
    else:
        shutil.rmtree(WORKDIR, ignore_errors=True)
        run(["git", "clone", repo_url, WORKDIR])

    # Actions workflow'u "bugun"u Istanbul saatinden hesapliyor; repo klasoru da
    # ayni tarihi kullanmali (sandbox'in kendi yerel tarihiyle farkli olabilir).
    repo_date = istanbul_today()
    dest_dir = os.path.join(WORKDIR, "images", repo_date)
    os.makedirs(dest_dir, exist_ok=True)

    for fname in files_by_name:
        shutil.copy2(files_by_name[fname], os.path.join(dest_dir, fname))

    with open(os.path.join(dest_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    run(["git", "-C", WORKDIR, "config", "user.email", "bot@chorastore.com"])
    run(["git", "-C", WORKDIR, "config", "user.name", "Chora Story Bot"])
    run(["git", "-C", WORKDIR, "add", f"images/{repo_date}"])

    result = subprocess.run(["git", "-C", WORKDIR, "diff", "--cached", "--quiet"])
    if result.returncode == 0:
        print("Degisiklik yok (bugun icin zaten pushlanmis olabilir), push atlaniyor.")
        return

    run(["git", "-C", WORKDIR, "commit", "-m", f"Add stories for {repo_date}"])
    run(["git", "-C", WORKDIR, "push", "origin", "main"])
    n_slot3 = len(manifest["3"])
    print(f"Pushlandi: images/{repo_date}/ ({len(files_by_name)} gorsel + manifest.json, slot 3'te {n_slot3} gorsel)")


if __name__ == "__main__":
    main()
