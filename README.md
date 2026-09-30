# London Movie Nights

Mobile showtimes for five London, Ontario cinemas at **movies.gorevault.ca**.

## What updates automatically

The GitHub Actions workflow checks the two London Cineplex theatres, Imagine Cinemas London, and Hyland Cinema at 8:23 am and 6:23 pm Toronto time. It deploys a static snapshot to GitHub Pages. Landmark blocks automated access from the updater, so its row links to the cinema's live page and is always labelled as unverified. A failed full refresh leaves the previous site online; the page warns when data is older than 30 hours.

The site lists the next 14 local dates. It only calls a film "booked in London" when a dated local screening was collected. Cinema ticketing remains on the cinema's own website.

## Update the horror watchlist

Edit `picks.json` with a title, optional aliases, a verified Canadian release date (or `null` for a local repertory screening), a short note, and a source link. The updater keeps picks within 90 days ahead or 30 days after release, plus any pick with a collected local screening. New notable titles need occasional manual review.

## Run locally

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe update.py
.\.venv\Scripts\python.exe validate.py site/data.json
py -3.12 -m http.server 8765 --directory site
```

Open `http://localhost:8765` to view the page. The frontend uses only local HTML, CSS, JavaScript, and the generated JSON snapshot.

## Domain

GitHub Pages serves `movies.gorevault.ca`. The `movies` Cloudflare DNS record points to `raypro.github.io` in DNS-only mode. The existing `gorevault.ca` hostname and Cloudflare Access application are separate.
