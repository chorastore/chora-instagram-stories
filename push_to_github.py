#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chora Store - Bugunun hikaye gorsellerini GitHub deposuna pushlar
(chorastore/chora-instagram-stories), boylece Instagram Graph API'nin
Story yayinlamak icin istedigi herkese acik image_url saglanmis olur
(raw.githubusercontent.com uzerinden).

Herhangi bir slot (1/2/3/4) TEK gorsel de olabilir, sirayla ARKA ARKAYA
paylasilacak birden fazla gorsel de (ör. 16:00 "Last Chance" formatinda
3 farkli urun, ya da bir baska slota gecici olarak tasinmis 3'lu bir seri):

    story_1_<...>.png              (tek gorsel)
    story_2_<...>.png              (tek gorsel)
    story_3_1_<...>.jpg            (arka arkaya 1/3)
    story_3_2_<...>.jpg            (arka arkaya 2/3)
    story_3_3_<...>.jpg            (arka arkaya 3/3)
    story_4_<...>.png              (tek gorsel)

Dosya adindaki ikinci sayi (ör. "_1_", "_2_", "_3_") sira numarasidir; hic
yoksa o slot icin tek gorsel demektir. manifest.json'da HER slot degeri
sirayla paylasilacak dosya adlarindan olusan bir LISTE olarak yazilir
(tek gorsel olan slotlar icin tek elemanli liste).

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
    """Dosya adlarindan slot -> gorsel(ler) esleme (manifest) uretir.
    Her slot degeri, sira numarasina gore siralanmis dosya adlarindan
    olusan bir LISTE'dir (tek gorselli slotlar icin tek elemanli liste).

    Ayni slot+sira numarasina birden fazla dosya denk gelirse (ör. onceki
    test/dev calistirmalarindan kalan eski dosyalar), dosyalar silinip/
    yeniden adlandirilamadigi icin hata vermek yerine EN YENI (mtime'i en
    buyuk) dosya secilir; digerleri yok sayilir ve konsola not dusulur."""
    slots = {}  # slot -> {sub_i: (mtime, fname)}
    unmatched = []
    ignored = []
    for p in files:
        fname = os.path.basename(p)
        m = STORY_RE.match(fname)
        if not m:
            unmatched.append(fname)
            continue
        slot, sub, _ext = m.group(1), m.group(2), m.group(3)
        sub_i = int(sub) if sub else 1
        mtime = os.path.getmtime(p)
        bucket = slots.setdefault(slot, {})
        prev = bucket.get(sub_i)
        if prev is None or mtime > prev[0]:
            if prev is not None:
                ignored.append(prev[1])
            bucket[sub_i] = (mtime, fname)
        else:
            ignored.append(fname)

    if unmatched:
        raise SystemExit(f"Taninmayan dosya adi(lar): {unmatched}")
    for slot in ("1", "2", "4"):
        if slot not in slots:
            raise SystemExit(f"Slot {slot} icin gorsel bulunamadi.")
    if "3" not in slots:
        # Last Chance (16:00) icin Canva'dan indirilen gorsel(ler) henuz
        # gunun klasorune eklenmemis olabilir (bu adim manuel/yari-otomatik).
        # Bu durumda push'u DURDURMAYIZ: slot "3" manifestten eksik birakilir,
        # publish_instagram.py bu durumda otomatik olarak baska bir slotun
        # gorselini (ör. story_1) yedek olarak 16:00'da paylasir.
        print(
            "Not: Slot 3 (16:00, Last Chance) icin gorsel yok - manifestte \"3\" anahtari "
            "olmayacak. publish_instagram.py bu durumda otomatik yedek (baska bir slotun "
            "gorseli) kullanacak."
        )

    if ignored:
        print(f"Not: ayni slot+sira numarasina ait eski/fazla dosya(lar) yok sayildi (en yeni kullanildi): {sorted(ignored)}")

    manifest = {slot: [bucket[k][1] for k in sorted(bucket)] for slot, bucket in slots.items()}
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
    slot_summary = ", ".join(f"slot {s}: {len(v)} gorsel" for s, v in sorted(manifest.items()))
    print(f"Pushlandi: images/{repo_date}/ ({len(files_by_name)} dosya + manifest.json - {slot_summary})")


if __name__ == "__main__":
    main()
