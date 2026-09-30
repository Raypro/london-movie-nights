import unittest

from update import THEATRES, clock_time, hyland_ticket_map, parse_cineplex, parse_hyland_calendar, parse_imagine, title_key


class ParserTests(unittest.TestCase):
    def test_title_variants_group(self):
        self.assertEqual(title_key("Avengers Endgame: Encore – The IMAX Experience®"), title_key("Avengers Endgame: Encore"))
        self.assertEqual(title_key("Coyote vs. ACME"), title_key("Coyote vs ACME"))

    def test_clock_time(self):
        self.assertEqual(clock_time("12:05pm"), "12:05")
        self.assertEqual(clock_time("12:05 AM"), "00:05")

    def test_cineplex_sessions_keep_format_and_deep_link(self):
        data = [{"theatreId": 7422, "dates": [{"startDate": "2026-10-01T00:00:00", "movies": [{
            "name": "Resident Evil", "genres": ["Horror"], "detailPageUrl": "https://www.cineplex.com/movie/resident-evil-2026",
            "experiences": [{"experienceTypes": ["IMAX", "Recliner"], "sessions": [{
                "showStartDateTime": "2026-10-01T19:30:00", "deeplinkUrl": "https://apis.cineplex.com/deeplink?s=1",
                "isShowtimeEnabledOnline": True, "isSoldOut": False, "isInThePast": False
            }]}]
        }]}]}]
        found = parse_cineplex(data, THEATRES[0], {"2026-10-01"})
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]["time"], found[0]["format"]), ("19:30", "IMAX"))
        self.assertTrue(found[0]["bookingUrl"].startswith("https://"))

    def test_imagine_rejects_wrong_date_ticket(self):
        html = '''<div id="theater-schedule"><div class="movie-showtime"><h2 class="movie-title">Other Mommy</h2>
        <span class="genre">Horror</span><div class="performances"><div class="type"><div class="type-title">RECLINERS</div>
        <a class="movie-performance" href="https://omniwebticketing8.com/?schdate=2026-10-01&amp;perfix=1">7:00PM</a>
        <a class="movie-performance" href="https://omniwebticketing8.com/?schdate=2026-10-02&amp;perfix=2">9:00PM</a>
        </div></div></div></div>'''
        found = parse_imagine(html, "2026-10-01", THEATRES[3])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["time"], "19:00")

    def test_hyland_calendar_and_exact_ticket_mapping(self):
        calendar = '''<table><td id="u7_bundle_movie_calendar-2026-10-09"><div class="view-item-u7_bundle_movie_calendar">
        <div class="view-data-node-data-field-movie-showtime-field-movie-showtime-value"><span class="date-display-single">7:00pm</span></div>
        <div class="view-data-node-node-data-field-movie-ref-title"><a href="/movie/scream">Scream</a></div>
        </div></td></table>'''
        found = parse_hyland_calendar(calendar, {"2026-10-09"}, THEATRES[4])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["detailUrl"], "https://www.hylandcinema.com/movie/scream")
        detail = '''<div class="sh_wrapper"><div class="showtime_time"><span class="date-display-single">7:00pm</span></div>
        <div class="sh_buy_tickets_link"><a href="https://omniwebticketing6.com/hyland/?schdate=2026-10-09&amp;perfix=10">Buy tickets</a></div></div>'''
        tickets = hyland_ticket_map(detail)
        self.assertEqual(tickets[("2026-10-09", "19:00")], "https://omniwebticketing6.com/hyland/?schdate=2026-10-09&perfix=10")


if __name__ == "__main__":
    unittest.main()
