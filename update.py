"""Build a fresh, source-labelled London cinema snapshot for the static site."""

from __future__ import annotations

import argparse
import json
import logging
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent
TORONTO = ZoneInfo("America/Toronto")
USER_AGENT = "Mozilla/5.0 (compatible; LondonMovieNights/1.0; public listings)"
HORIZON_DAYS = 14
THEATRES = [
    {
        "id": "silvercity",
        "name": "SilverCity London",
        "url": "https://www.cineplex.com/theatre/silvercity-london-cinemas",
        "cineplex_id": 7422,
    },
    {
        "id": "westmount",
        "name": "Westmount VIP",
        "url": "https://www.cineplex.com/theatre/cineplex-odeon-westmount-cinemas-and-vip",
        "cineplex_id": 7112,
    },
    {
        "id": "landmark",
        "name": "Landmark London",
        "url": "https://www.landmarkcinemas.com/showtimes/london",
    },
    {
        "id": "imagine",
        "name": "Imagine Cinemas London",
        "url": "https://imaginecinemas.com/cinema/london/",
    },
    {
        "id": "hyland",
        "name": "Hyland Cinema",
        "url": "https://www.hylandcinema.com/movie-calendar",
    },
]


def title_key(title: str) -> str:
    title = re.sub(r"\s*[–—-]?\s*the imax experience.*$", "", title, flags=re.I)
    title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    title = title.lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", title).strip()


def clock_time(value: str) -> str | None:
    match = re.search(r"\b(\d{1,2}):(\d{2})\s*([ap]m)\b", value, re.I)
    if not match:
        return None
    hour = int(match.group(1)) % 12 + (12 if match.group(3).lower() == "pm" else 0)
    return f"{hour:02d}:{match.group(2)}"


def https_url(value: str | None, base: str = "") -> str | None:
    if not value:
        return None
    url = urljoin(base, value)
    return url if urlparse(url).scheme == "https" else None


def screening(
    day: str,
    time: str,
    title: str,
    theatre: str,
    booking_url: str | None,
    detail_url: str,
    *,
    format_name: str = "",
    genres: list[str] | None = None,
    sold_out: bool = False,
) -> dict:
    return {
        "date": day,
        "time": time,
        "title": title.strip(),
        "key": title_key(title),
        "theatre": theatre,
        "bookingUrl": booking_url,
        "detailUrl": detail_url,
        "format": format_name.strip(),
        "genres": genres or [],
        "soldOut": sold_out,
    }


def status(theatre: dict, state: str, checked_at: str, dates: list[str], note: str = "") -> dict:
    if state == "unavailable":
        note = "Listings could not be checked. Open the cinema for current times."
    elif state == "partial":
        note = "Some dates could not be checked. Confirm times on the cinema site."
    return {
        "id": theatre["id"],
        "name": theatre["name"],
        "url": theatre["url"],
        "status": state,
        "checkedAt": checked_at,
        "datesChecked": sorted(set(dates)),
        "note": note,
    }


def parse_cineplex(data: object, theatre: dict, allowed_days: set[str]) -> list[dict]:
    if not isinstance(data, list):
        raise ValueError("Cineplex showtimes response is not a list")
    result = []
    for venue in data:
        if venue.get("theatreId") != theatre["cineplex_id"]:
            continue
        for day_item in venue.get("dates", []):
            day = str(day_item.get("startDate", ""))[:10]
            if day not in allowed_days:
                continue
            for movie in day_item.get("movies", []):
                name = movie.get("name", "").strip()
                if not name:
                    continue
                detail = https_url(movie.get("detailPageUrl"), "https://www.cineplex.com") or theatre["url"]
                genres = movie.get("genres") or []
                for experience in movie.get("experiences", []):
                    kind = [x for x in experience.get("experienceTypes", []) if x not in {"Regular", "Recliner"}]
                    format_name = " · ".join(kind[:2])
                    for session in experience.get("sessions", []):
                        when = str(session.get("showStartDateTime", ""))
                        if not when.startswith(day) or len(when) < 16 or session.get("isInThePast"):
                            continue
                        result.append(
                            screening(
                                day,
                                when[11:16],
                                name,
                                theatre["id"],
                                https_url(session.get("deeplinkUrl")) if session.get("isShowtimeEnabledOnline") else None,
                                detail,
                                format_name=format_name,
                                genres=genres,
                                sold_out=bool(session.get("isSoldOut")),
                            )
                        )
    return result


def collect_cineplex(theatres: list[dict], days: list[date], checked_at: str) -> tuple[list[dict], list[dict]]:
    all_screenings: list[dict] = []
    all_statuses: list[dict] = []
    allowed_days = {day.isoformat() for day in days}
    with sync_playwright() as playwright:
        launch_args = {"headless": True}
        if __import__("sys").platform == "win32":
            launch_args["channel"] = "chrome"
        browser = playwright.chromium.launch(**launch_args)
        context = browser.new_context(locale="en-CA", timezone_id="America/Toronto", viewport={"width": 390, "height": 844})
        consent_handled = False
        for theatre in theatres:
            completed: list[str] = []
            errors: list[str] = []
            page = context.new_page()
            try:
                page.goto(theatre["url"], wait_until="domcontentloaded", timeout=30000)
                if not consent_handled:
                    consent = page.locator("#onetrust-accept-btn-handler")
                    try:
                        consent.wait_for(state="visible", timeout=8000)
                        consent.click(timeout=5000)
                        consent_handled = True
                    except PlaywrightTimeout:
                        pass
                with page.expect_response(lambda response: "/theatrical/api/v1/showtimes" in response.url and response.ok, timeout=25000) as initial:
                    page.get_by_test_id("get-tickets-button").first.click(timeout=20000)
                first_data = initial.value.json()
                all_screenings.extend(parse_cineplex(first_data, theatre, allowed_days))
                first_dates = [str(d.get("startDate", ""))[:10] for v in first_data for d in v.get("dates", [])]
                completed.extend(d for d in first_dates if d in allowed_days)
                for day in days:
                    iso_day = day.isoformat()
                    if iso_day in completed:
                        continue
                    logging.info("Cineplex %s checking %s", theatre["id"], iso_day)
                    try:
                        page.get_by_test_id("select-date").click(timeout=12000)
                        full_date = f"{day.strftime('%B')} {day.day}, {day.year}"
                        choice = page.get_by_role("dialog").get_by_text(full_date, exact=True)
                        try:
                            choice.first.wait_for(state="visible", timeout=7000)
                        except PlaywrightTimeout:
                            page.keyboard.press("Escape")
                            continue
                        with page.expect_response(lambda response: "/theatrical/api/v1/showtimes" in response.url and response.ok, timeout=20000) as selected:
                            choice.first.click(timeout=12000)
                        all_screenings.extend(parse_cineplex(selected.value.json(), theatre, allowed_days))
                        completed.append(iso_day)
                    except (PlaywrightTimeout, ValueError) as exc:
                        errors.append(f"{iso_day}: {type(exc).__name__}")
                        logging.warning("Cineplex %s %s: %s", theatre["id"], iso_day, str(exc)[:400])
                        page.keyboard.press("Escape")
            except Exception as exc:
                logging.warning("Cineplex %s: %s", theatre["id"], exc)
                errors.append(type(exc).__name__)
            finally:
                page.close()
            state = "ok" if completed and not errors else "partial" if completed else "unavailable"
            all_statuses.append(status(theatre, state, checked_at, completed, "; ".join(errors[:3])))
            logging.info("%s: %s, %d dates", theatre["id"], state, len(completed))
        browser.close()
    return all_screenings, all_statuses


def parse_imagine(html: str, day: str, theatre: dict) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    schedule = soup.select_one("#theater-schedule")
    if schedule is None:
        raise ValueError("Imagine schedule container missing")
    result = []
    for movie in schedule.select(".movie-showtime"):
        title_node = movie.select_one(".movie-title")
        if title_node is None:
            continue
        title = title_node.get_text(" ", strip=True)
        genre_node = movie.select_one(".genre")
        genres = [genre_node.get_text(" ", strip=True).strip(" ·") ] if genre_node else []
        for kind in movie.select(".performances .type"):
            format_node = kind.select_one(".type-title")
            format_name = format_node.get_text(" ", strip=True) if format_node else ""
            for link in kind.select("a.movie-performance[href]"):
                url = https_url(link.get("href"))
                if not url or parse_qs(urlparse(url).query).get("schdate") != [day]:
                    continue
                time = clock_time(link.get_text(" ", strip=True))
                if time:
                    result.append(screening(day, time, title, theatre["id"], url, theatre["url"], format_name=format_name, genres=genres))
    return result


def collect_imagine(theatre: dict, days: list[date], checked_at: str, http: requests.Session) -> tuple[list[dict], dict]:
    completed: list[str] = []
    errors: list[str] = []
    result: list[dict] = []
    try:
        response = http.get(theatre["url"], timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        option = soup.select_one('#showtimes-selector select[name="theatre"] option[value="78005"]')
        if not option:
            raise ValueError("Imagine London date selector missing")
        available = set(json.loads(option.get("data-available-dates", "[]")))
        for day in days:
            iso_day = day.isoformat()
            if iso_day not in available:
                continue
            try:
                page = http.get(theatre["url"], params={"date": iso_day}, timeout=20)
                page.raise_for_status()
                result.extend(parse_imagine(page.text, iso_day, theatre))
                completed.append(iso_day)
            except Exception as exc:
                errors.append(f"{iso_day}: {type(exc).__name__}")
    except Exception as exc:
        logging.warning("Imagine: %s", exc)
        errors.append(type(exc).__name__)
    state = "ok" if completed and not errors else "partial" if completed else "unavailable"
    logging.info("imagine: %s, %d dates", state, len(completed))
    return result, status(theatre, state, checked_at, completed, "; ".join(errors[:3]))


def parse_hyland_calendar(html: str, days: set[str], theatre: dict) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cells = soup.select('td[id^="u7_bundle_movie_calendar-"]')
    if not cells:
        raise ValueError("Hyland calendar cells missing")
    result = []
    for cell in cells:
        day = cell.get("id", "")[-10:]
        if day not in days:
            continue
        for event in cell.select(".view-item-u7_bundle_movie_calendar"):
            time_node = event.select_one(".view-data-node-data-field-movie-showtime-field-movie-showtime-value .date-display-single")
            title_link = event.select_one(".view-data-node-node-data-field-movie-ref-title a[href]")
            if not time_node or not title_link:
                continue
            time = clock_time(time_node.get_text(" ", strip=True))
            detail = https_url(title_link.get("href"), "https://www.hylandcinema.com")
            if time and detail:
                result.append(screening(day, time, title_link.get_text(" ", strip=True), theatre["id"], None, detail))
    return result


def hyland_ticket_map(html: str) -> dict[tuple[str, str], str]:
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    for row in soup.select(".sh_wrapper"):
        link = row.select_one(".sh_buy_tickets_link a[href]")
        time_node = row.select_one(".showtime_time .date-display-single")
        if not link or not time_node:
            continue
        url = https_url(link.get("href"))
        day = parse_qs(urlparse(url).query).get("schdate", [None])[0] if url else None
        time = clock_time(time_node.get_text(" ", strip=True))
        if day and time and url:
            result[(day, time)] = url
    return result


def collect_hyland(theatre: dict, days: list[date], checked_at: str, http: requests.Session) -> tuple[list[dict], dict]:
    months = sorted({day.strftime("%Y-%m") for day in days})
    allowed_days = {day.isoformat() for day in days}
    result: list[dict] = []
    errors: list[str] = []
    completed: list[str] = []
    for month in months:
        url = f"https://www.hylandcinema.com/movie-calendar/Hyland-Cinema/{month}"
        try:
            response = http.get(url, timeout=20)
            response.raise_for_status()
            parsed = parse_hyland_calendar(response.text, allowed_days, theatre)
            result.extend(parsed)
            completed.extend(day.isoformat() for day in days if day.strftime("%Y-%m") == month)
        except Exception as exc:
            logging.warning("Hyland %s: %s", month, exc)
            errors.append(f"{month}: {type(exc).__name__}")
    for detail in sorted({item["detailUrl"] for item in result}):
        try:
            response = http.get(detail, timeout=15)
            response.raise_for_status()
            tickets = hyland_ticket_map(response.text)
            for item in result:
                if item["detailUrl"] == detail:
                    item["bookingUrl"] = tickets.get((item["date"], item["time"]))
        except Exception:
            # The movie detail page itself remains a usable fallback.
            pass
    state = "ok" if completed and not errors else "partial" if completed else "unavailable"
    logging.info("hyland: %s, %d screenings", state, len(result))
    return result, status(theatre, state, checked_at, completed, "; ".join(errors[:3]))


def load_picks(path: Path, today: date, items: list[dict]) -> list[dict]:
    showing_keys = {item["key"] for item in items}
    picks = json.loads(path.read_text(encoding="utf-8"))
    result = []
    for pick in picks:
        keys = {title_key(x) for x in [pick["title"], *pick.get("aliases", [])]}
        release = date.fromisoformat(pick["canadianReleaseDate"]) if pick.get("canadianReleaseDate") else None
        if keys & showing_keys or (release and today - timedelta(days=30) <= release <= today + timedelta(days=90)):
            result.append({**pick, "keys": sorted(keys)})
    return result


def build_snapshot(today: date, *, output: Path = ROOT / "site" / "data.json") -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    days = [today + timedelta(days=offset) for offset in range(HORIZON_DAYS)]
    http = requests.Session()
    http.headers.update({"User-Agent": USER_AGENT})
    screenings: list[dict] = []
    cinemas: list[dict] = []
    try:
        cpx_screenings, cpx_cinemas = collect_cineplex(THEATRES[:2], days, now)
        screenings.extend(cpx_screenings)
        cinemas.extend(cpx_cinemas)
    except Exception as exc:
        logging.exception("Cineplex browser unavailable")
        cinemas.extend(status(t, "unavailable", now, [], type(exc).__name__) for t in THEATRES[:2])
    cinemas.append(status(THEATRES[2], "link_only", now, [], "Open Landmark for live showtimes"))
    for collector, theatre in [(collect_imagine, THEATRES[3]), (collect_hyland, THEATRES[4])]:
        entries, cinema = collector(theatre, days, now, http)
        screenings.extend(entries)
        cinemas.append(cinema)
    unique = {}
    for item in screenings:
        key = (item["date"], item["time"], item["key"], item["theatre"], item["format"])
        if key not in unique or (not unique[key]["bookingUrl"] and item["bookingUrl"]):
            unique[key] = item
    screenings = sorted(unique.values(), key=lambda x: (x["date"], x["title"].lower(), x["theatre"], x["time"], x["format"]))
    snapshot = {
        "generatedAt": now,
        "timeZone": "America/Toronto",
        "dates": [day.isoformat() for day in days],
        "cinemas": cinemas,
        "screenings": screenings,
        "picks": load_picks(ROOT / "picks.json", today, screenings),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    logging.info("Wrote %s: %d screenings", output, len(screenings))
    return snapshot


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="Override Toronto date for testing")
    parser.add_argument("--output", type=Path, default=ROOT / "site" / "data.json")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build_snapshot(args.date or datetime.now(TORONTO).date(), output=args.output)
