# chora-instagram-stories

Chora Store icin otomatik Instagram Hikaye yayin sistemi.

- `images/<YYYY-MM-DD>/` - o gunun 4 hikaye gorseli + `manifest.json` (slot -> dosya adi eslesmesi). Bu klasor, Cowork tarafinda calisan gunluk uretim adimiyla (generate_daily_stories.py + push_to_github.py) otomatik pushlanir.
- `scripts/publish_instagram.py` - GitHub Actions icinde calisir, gunde 4 kez (08/12/16/20 Istanbul) tetiklenip o slota ait gorseli Instagram Story olarak yayinlar (Graph API).
- `.github/workflows/publish-stories.yml` - zamanlanmis is akisi (GitHub web arayuzunden eklendi, PAT'nin workflow yazma izni olmadigi icin).

Gerekli repo secret: `FB_ACCESS_TOKEN` (Meta System User erisim tokeni, instagram_basic + instagram_content_publish izinleriyle).
