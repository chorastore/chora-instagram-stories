#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chora Store - Bugunun 4 hikaye gorselini GitHub deposuna pushlar
(chorastore/chora-instagram-stories), boylece Instagram Graph API'nin
Story yayinlamak icin istedigi herkese acik image_url saglanmis olur
(raw.githubusercontent.com uzerinden).

generate_daily_stories.py'den SONRA calistirilmali.

Kullanim: python3 push_to_github.py "<chora_dir_bash_path>"
"""
import os
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

    pngs = sorted(glob.glob(os.path.join(src_dir, "story_*.png")))
    if len(pngs) != 4:
        raise SystemExit(f"4 gorsel bekleniyordu, {len(pngs)} bulundu: {pngs}")

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

    manifest = {}
    for i, p in enumerate(pngs, start=1):
        fname = os.path.basename(p)
        shutil.copy2(p, os.path.join(dest_dir, fname))
        manifest[str(i)] = fname

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
    print(f"Pushlandi: images/{repo_date}/ (4 gorsel + manifest.json)")


if __name__ == "__main__":
    main()
