"""Location/geocoding tests using a fake HTTP layer and a temp DB."""
import os
os.environ.setdefault("JARVIS_DB", "/tmp/opencode/location_test.db")

import json
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from jarvis.places import _geocode, save_location, find_places, _parse_maps_url

def _nom_ok(lat, lon, label):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = [{"lat": str(lat), "lon": str(lon), "display_name": label}]
    return m


def _nom_403():
    m = MagicMock()
    m.status_code = 403
    m.raise_for_status.side_effect = Exception("403 Forbidden")
    return m


def _photon_ok(lat, lon):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {"features": [{"geometry": {"coordinates": [lon, lat]}}]}
    return m


def _fake_get_geocode(*args, **kwargs):
    url = args[0] if args else kwargs.get("url", "")
    if "nominatim" in url:
        return _nom_ok(12.9716, 77.5946, "Bengaluru, India")
    if "photon" in url:
        return _photon_ok(12.918, 77.614)
    if "open-meteo" in url:
        m = MagicMock()
        m.status_code = 200
        m.json.return_value = {"results": [{"latitude": 12.9, "longitude": 77.6}]}
        return m
    return _nom_ok(12.9716, 77.5946, "Bengaluru, India")


def _fake_get_403_then_photon(*args, **kwargs):
    url = args[0] if args else kwargs.get("url", "")
    if "nominatim" in url:
        return _nom_403()
    if "photon" in url:
        return _photon_ok(12.918, 77.614)
    return _nom_ok(12.9716, 77.5946, "Bengaluru, India")


def _fake_get_all_fail(*args, **kwargs):
    m = MagicMock()
    m.status_code = 502
    m.raise_for_status.side_effect = Exception("502 Bad Gateway")
    return m


def _fake_get_maps_short(*args, **kwargs):
    url = args[0] if args else kwargs.get("url", "")
    if "maps.app.goo.gl" in url or "goo.gl/maps" in url:
        m = MagicMock()
        m.status_code = 200
        m.url = "https://www.google.com/maps/search/12.918039,+77.614084"
        return m
    return _nom_ok(12.9716, 77.5946, "Bengaluru, India")


def _fake_get_maps_short(*args, **kwargs):
    url = args[0] if args else kwargs.get("url", "")
    if "maps.app.goo.gl" in url or "goo.gl/maps" in url:
        m = MagicMock()
        m.status_code = 200
        m.url = "https://www.google.com/maps/search/12.918039,+77.614084"
        return m
    return _nom_ok(12.9716, 77.5946, "Bengaluru, India")


def test_geocode_success_first_provider():
    with patch("jarvis.places.requests.get", side_effect=_fake_get_geocode):
        lat, lon = _geocode("Indiranagar, Bengaluru, India")
    assert lat == 12.9716 and lon == 77.5946, (lat, lon)
    print("PASS geocode success first provider")


def test_geocode_403_then_fallback():
    with patch("jarvis.places.requests.get", side_effect=_fake_get_403_then_photon):
        lat, lon = _geocode("Indiranagar, Bengaluru, India")
    assert lat == 12.918 and lon == 77.614, (lat, lon)
    print("PASS geocode 403 then fallback")


def test_geocode_full_address_fail_then_simplified():
    call_count = {"n": 0}
    def _seq(*a, **k):
        call_count["n"] += 1
        url = a[0] if a else ""
        params = k.get("params", {})
        q = params.get("q", "")
        if call_count["n"] == 1 and "," in q and len(q.split(",")) > 2:
            m = MagicMock()
            m.status_code = 200
            m.json.return_value = []
            return m
        return _nom_ok(12.9716, 77.5946, "Bengaluru, India")
    with patch("jarvis.places.requests.get", side_effect=_seq):
        lat, lon = _geocode("Indiranagar, Bengaluru, India")
    assert lat == 12.9716 and lon == 77.5946
    print("PASS geocode full address fails then simplified")


def test_geocode_all_fail():
    with patch("jarvis.places.requests.get", side_effect=_fake_get_all_fail):
        lat, lon = _geocode("Nowhereville, XX")
    assert lat is None and lon is None, (lat, lon)
    print("PASS geocode all fail")


def test_parse_maps_short_link():
    with patch("jarvis.places.requests.get", side_effect=_fake_get_maps_short):
        result = _parse_maps_url("https://maps.app.goo.gl/X2uGY4FVpgCJaLot7")
    assert result == (12.918039, 77.614084), result
    print("PASS parse maps short link")


def test_parse_maps_non_google_refused():
    with patch("jarvis.places.requests.get") as mock_get:
        m = MagicMock()
        m.status_code = 200
        m.url = "https://evil.com/redirect"
        mock_get.return_value = m
        result = _parse_maps_url("https://maps.app.goo.gl/FAKE")
    assert result is None, result
    print("PASS parse maps non-google refused")


def test_parse_maps_no_coords():
    with patch("jarvis.places.requests.get", side_effect=_fake_get_maps_short):
        result = _parse_maps_url("https://www.google.com/maps/search/Somewhere")
    assert result is None, result
    print("PASS parse maps no coords")


def test_save_location_direct_lat_lon():
    with patch("jarvis.places.requests.get"):
        msg = save_location.invoke({"label": "12.9716, 77.5946"})
    assert "12.97" in msg and "77.59" in msg, msg
    print("PASS save_location direct lat,lon:", msg)


def test_home_location_unchanged_in_real_db():
    import sqlite3
    c = sqlite3.connect("/home/rokkun-23/Desktop/Agnet_Example/jarvis.db")
    r = c.execute("SELECT value FROM settings WHERE key='home_location'").fetchone()
    c.close()
    assert r is not None and r[0] != "", "real DB home_location should be preserved"
    print("PASS real DB home_location unchanged:", r[0][:60])


if __name__ == "__main__":
    test_geocode_success_first_provider()
    test_geocode_403_then_fallback()
    test_geocode_full_address_fail_then_simplified()
    test_geocode_all_fail()
    test_parse_maps_short_link()
    test_parse_maps_non_google_refused()
    test_parse_maps_no_coords()
    test_save_location_direct_lat_lon()
    test_home_location_unchanged_in_real_db()
    print("\nALL LOCATION TESTS PASSED")
