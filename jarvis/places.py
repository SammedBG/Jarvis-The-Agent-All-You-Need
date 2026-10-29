"""
places.py - find nearby places (restaurants, cafes, etc.) using Google
Places, Foursquare, or OpenStreetMap Overpass as a fallback.

Configuration (read-only .env):
    GOOGLE_PLACES_KEY = ...    # preferred (Google Places API New, searchNearby)
    FOURSQUARE_KEY = ...       # fallback
    # otherwise OSM Overpass is used, which has no ratings/reviews

Everything is read-only; nothing is written except the saved home_location
(via jarvis/tasks get_setting/set_setting under key 'home_location').
"""
from __future__ import annotations
from langchain_core.tools import tool

import json
import math
import os
import re
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .cache import get_state, set_state, clear_state

BASE_DIR = Path(__file__).resolve().parent.parent
LOCATION_KEY = "home_location"

# known data-source hints surfaced to the user inline; do not invent reviews etc.
CUISE_HINTS = {
    "veg": "vegetarian", "veg.": "vegetarian", "veg food": "vegetarian",
    "vegetarian": "vegetarian", "vegan": "vegan", "halal": "halal",
    "keto": "keto", "jain": "jain",
}


def _settings():
    from jarvis.app_briefing import get_setting, set_setting
    return get_setting, set_setting


@tool
def get_my_location() -> str:
    """Return the saved location (lat, lon, label) or a notice if none saved."""
    try:
        get_setting, _ = _settings()
        raw = get_setting(LOCATION_KEY, "").strip()
        if raw:
            v = json.loads(raw)
            return f"Saved location: {v.get('label','(label unknown)')} " \
                   f"({round(v['lat'], 2)}, {round(v['lon'], 2)})."
    except Exception:
        pass
    try:
        set_state("places_location_asked", True)
    except Exception:
        pass
    return ("No location saved. Ask the user once: 'Which area and city are you in?' "
            "Do NOT guess a location. Do NOT call save_location until the user "
            "replies with an area or city name.")


@tool
def save_location(label: str) -> str:
    """Geocode `label` and store it. Mostly read-only toward the user."""
    label_raw = (label or "").strip()
    label_is_url = bool(re.match(r"https?://", label_raw, re.I))
    if label_is_url:
        label = "Pinned location"
    else:
        label = label_raw
    if len(label) < 2:
        return "I need: a place name like 'Marine Drive, Mumbai'."
    lat, lon = _geocode(label_raw)
    if lat is None:
        return "Could not find that place in any geocoder. Try a fuller address."
    try:
        _, set_setting = _settings()
        set_setting(LOCATION_KEY, json.dumps({"label": label, "lat": lat, "lon": lon}))
    except Exception as e:
        return f"Saved in-memory, but DB write failed: {e}"
    # location is now saved: reset the ask-once flag so the next search proceeds
    try:
        set_state("places_location_asked", False)
    except Exception:
        pass
    return f"Saved location {label} (this is stored; coords rounded on display: " \
           f"{round(lat, 2)}, {round(lon, 2)})."


def _parse_maps_url(url: str):
    """Parse coordinates from a Google Maps URL, following safe redirects."""
    try:
        from urllib.parse import urlparse
    except Exception:
        return None
    u = (url or "").strip()
    if not re.match(r"https?://", u, re.I):
        return None
    host = urlparse(u).hostname or ""
    allowed_hosts = {"maps.app.goo.gl", "goo.gl", "www.google.com", "maps.google.com", "google.com"}
    # short links only: follow redirects, but only Google hosts allowed
    if host in {"maps.app.goo.gl", "goo.gl"}:
        try:
            r = requests.get(u, headers={"User-Agent": "JARVIS-assistant/1.0 (personal use)"},
                             timeout=10, allow_redirects=True)
            final_host = (urlparse(r.url).hostname or "")
            if final_host not in allowed_hosts and not final_host.endswith("google.com"):
                return None
            u = r.url or u
        except Exception:
            return None
    for pat in (r"/maps/search/([^/]+)", r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)"):
        m = re.search(pat, u)
        if m:
            try:
                lat = float(m.group(1))
                lon = float(m.group(2))
            except Exception:
                continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                return None
            return lat, lon
    # fallback: extract numeric tokens and use first valid pair
    nums = re.findall(r"-?\d+(?:\.\d+)?", u)
    if len(nums) >= 2:
        try:
            lat = float(nums[0]); lon = float(nums[1])
        except Exception:
            return None
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    return None


def _geocode(label: str):
    """Return (lat, lon) via a cascading geocoder with graceful fallbacks."""
    s = " ".join((label or "").strip().split())
    # Google Maps URL support
    coords = _parse_maps_url(s)
    if coords:
        return coords
    # Direct lat, lon input.
    m = re.match(r"^(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)$", s)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except ValueError:
            pass
    queries = [s]
    if "," in s:
        parts = [p.strip() for p in s.split(",") if p.strip()]
        if len(parts) > 1:
            queries.append(", ".join(parts[:-1]))
        if len(parts) >= 2:
            queries.append(", ".join(parts[:2]))

    UA = "JARVIS-assistant/1.0 (personal use)"
    key = os.getenv("GOOGLE_PLACES_KEY", "").strip()
    if key:
        try:
            params = {"address": queries[0], "key": key}
            r = requests.get("https://maps.googleapis.com/maps/api/geocode/json", params, timeout=10)
            j = r.json()
            if j.get("results"):
                loc = j["results"][0]["geometry"]["location"]
                return float(loc["lat"]), float(loc["lon"])
        except Exception:
            pass

    country = "IN" if s.lower().endswith(("india",)) else None
    for q in queries:
        # Nominatim
        for _ in range(2):
            try:
                _rate_limit_1s()
                params = {"q": q, "format": "json", "limit": 1}
                if country:
                    params["countrycodes"] = country
                r = requests.get("https://nominatim.openstreetmap.org/search",
                                  params=params, headers={"User-Agent": UA}, timeout=10)
                if r.status_code in (429, 502, 503, 504):
                    import time as _t
                    _t.sleep(1.2)
                    continue
                r.raise_for_status()
                j = r.json()
                if isinstance(j, list) and j:
                    return float(j[0]["lat"]), float(j[0]["lon"])
                break
            except Exception:
                import time as _t
                _t.sleep(0.5)
                break
        # Photon
        try:
            _rate_limit_1s()
            r = requests.get("https://photon.komoot.io/api/", params={"q": q, "limit": 1},
                              headers={"User-Agent": UA}, timeout=10)
            r.raise_for_status()
            j = r.json()
            feats = j.get("features") if isinstance(j, dict) else None
            if isinstance(feats, list) and feats:
                c = (feats[0].get("geometry") or {}).get("coordinates") or []
                if len(c) == 2:
                    return float(c[1]), float(c[0])
        except Exception:
            pass
        # Open-Meteo
        try:
            _rate_limit_1s()
            r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                              params={"name": q, "count": 1, "language": "en", "format": "json"},
                              headers={"User-Agent": UA}, timeout=10)
            r.raise_for_status()
            j = r.json()
            res = j.get("results") if isinstance(j, dict) else None
            if isinstance(res, list) and res:
                return float(res[0]["latitude"]), float(res[0]["longitude"])
        except Exception:
            pass
    return (None, None)

def _saved_coords() -> tuple[float, float, str] | None:
    try:
        get_setting, _ = _settings()
        raw = get_setting(LOCATION_KEY, "").strip()
        if raw:
            v = json.loads(raw)
            return float(v["lat"]), float(v["lon"]), v.get("label", "")
    except Exception:
        pass
    return None


def _score(place: dict) -> float:
    """score = rating * log(1 + review_count) - distance penalty (km)."""
    rating = float(place.get("rating") or 0.0)
    count = int(place.get("review_count") or 0)
    dist = float(place.get("distance_m") or 0.0)
    penalty = (dist / 1000.0) * 0.5
    return rating * math.log1p(count) - penalty


def score_places(places: list[dict], radius_m: int = 3000,
                 open_now: bool = True, min_rating: float = 4.0,
                 min_reviews: int = 50) -> list[dict]:
    """Filter + rank. Pure function, easy to test. `open_now=True` drops
    places that explicitly report closed."""
    out = []
    for p in (places or []):
        dist = float(p.get("distance_m") or 0.0)
        if dist > radius_m:
            continue
        if open_now is True and p.get("open_now") is False:
            continue
        rating = float(p.get("rating") or 0.0)
        count = int(p.get("review_count") or 0)
        has_ratings = p.get("rating") is not None or p.get("review_count") is not None
        if has_ratings:
            if rating < min_rating or count < min_reviews:
                continue
        p = dict(p)  # don't mutate caller
        p["score"] = _score(p)
        out.append(p)
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


# ---- providers -------------------------------------------------------------

def _provider_names() -> list[str]:
    if os.getenv("GOOGLE_PLACES_KEY"):
        return ["google"]
    if os.getenv("FOURSQUARE_KEY"):
        return ["foursquare"]
    return ["osm"]


def _google_fetch(query: str, lat: float, lon: float, radius_m: int) -> list[dict]:
    key = os.getenv("GOOGLE_PLACES_KEY", "").strip()
    body = {
        "textQuery": query,
        "languageMask": "en",
        "maxResultCount": 10,
        "locationBias": {
            "circle": {"center": {"latitude": lat, "longitude": lon},
                       "radius": float(radius_m)},
        },
        "rankPreference": "POPULARITY",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,"
                            "places.location,places.rating,places.userRatingCount,"
                            "places.priceLevel,places.currentOpeningHours.openNow,"
                            "places.id",
    }
    r = requests.post("https://places.googleapis.com/v1/places:searchText",
                      json=body, headers=headers, timeout=25)
    r.raise_for_status()
    j = r.json()
    out = []
    for pl in j.get("places", []) or []:
        loc = (pl.get("location") or {})
        addr = pl.get("formattedAddress", "")
        maps = _maps_link(pl.get("id"), loc.get("latitude"), loc.get("longitude"), pl.get("displayName", {}).get("text"))
        out.append(_normalize("google",
            pl.get("displayName", {}).get("text", "(unnamed)"),
            rating=pl.get("rating"),
            count=pl.get("userRatingCount"),
            price=pl.get("priceLevel"),
            lat=float(loc.get("latitude") or lat),
            lon=float(loc.get("longitude") or lon),
            addr=addr,
            open_now=pl.get("currentOpeningHours", {}).get("openNow"),
            maps=maps,
        ))
    return out


def _foursquare_fetch(query: str, lat: float, lon: float, radius_m: int) -> list[dict]:
    key = os.getenv("FOURSQUARE_KEY", "").strip()
    params = {"query": query, "ll": f"{lat},{lon}", "radius": int(radius_m), "limit": 10}
    r = requests.get("https://api.foursquare.com/v3/places/search",
                     params=params, headers={"Authorization": key, "Accept": "application/json"},
                     timeout=25)
    r.raise_for_status()
    j = r.json()
    out = []
    for pl in j.get("results", []) or []:
        loc = pl.get("location") or {}
        stats = pl.get("stats") or {}
        fsq_id = pl.get("fsq_id")
        addr = ", ".join(filter(None, [
            loc.get("formatted_address") or loc.get("address"),
            loc.get("locality"),
        ]))
        open_hours = ((pl.get("hours") or {}).get("open_now"))
        maps = _maps_link(None, loc.get("latitude", lat), loc.get("longitude", lon),
                          pl.get("name"), fsq_id=fsq_id)
        out.append(_normalize("foursquare",
            pl.get("name", "(unnamed)"),
            rating=pl.get("rating"),
            count=stats.get("total_ratings"),
            price=None,
            lat=float(loc.get("latitude", lat)),
            lon=float(loc.get("longitude", lon)),
            addr=addr or "(no address)",
            open_now=open_hours,
            maps=maps,
        ))
    return out


def _osm_fetch(query: str, lat: float, lon: float, radius_m: int) -> list[dict]:
    # Map user query to OSM amenity/shop categories heuristically; "" -> all.
    amenity_map = {
        "cafe": "cafe", "coffee": "cafe", "restaurant": "restaurant",
        "pharmacy": "pharmacy", "atm": "atm", "petrol": "fuel",
        "gas": "fuel", "supermarket": "supermarket", "bar": "bar", "bakery": "bakery",
        "pizza": "restaurant", "burger": "fast_food", "mosque": "place_of_worship",
        "temple": "place_of_worship", "hospital": "hospital", "park": "park",
        "parking": "parking", "bank": "bank", "laundry": "laundry",
        "gym": "gym", "salon": "hairdresser", "hospital": "hospital",
        "metro": "metro", "subway": "metro", "underground": "metro",
        "train station": "train_station", "railway station": "train_station",
        "bus station": "bus_station", "bus stop": "bus_stop",
        "station": "train_station",
        "movie theater": "cinema", "cinema": "cinema", "theater": "cinema",
        "theatre": "cinema", "multiplex": "cinema",
    }
    railway_station_kw = {"metro", "subway", "underground", "train station",
                          "railway station", "bus station", "bus stop", "station"}
    q = (query or "").lower()
    amenity = "restaurant"
    is_station_query = any(k in q for k in railway_station_kw)
    # token-level + relaxed matching: ensures "veg restaurant"/"restaurants"/etc match
    for k in amenity_map:
        if k in q:
            amenity = amenity_map[k]
            break
    else:
        # fuzzy amenity extraction - 1-2 letter typos handled
        import difflib
        for tok in q.split():
            matches = difflib.get_close_matches(tok, list(amenity_map), n=1, cutoff=0.75)
            if matches:
                amenity = amenity_map[matches[0]]
                break

    # Broader fallback terms if the specific amenity returns nothing
    fallback_amenities = {"restaurant": ["cafe", "fast_food", "food_court"],
                          "cafe": ["restaurant", "fast_food"],
                          "pharmacy": [],
                          "atm": ["bank"],
                          "petrol": ["fuel"],
                          "fuel": ["petrol"],
                          "supermarket": ["convenience"],
                          "bar": ["pub"],
                          "bakery": ["cafe"],
                          "hospital": ["clinic"],
                          "gym": ["fitness_centre"],
                          "salon": ["beauty_salon"],
                          "metro": ["train_station"],
                          "train_station": ["metro", "bus_station"],
                          "cinema": ["theatre"]}.get(amenity, [])

    _OSM_ENDPOINTS = ["https://overpass-api.de/api/interpreter",
                      "https://overpass.kumi.systems/api/interpreter",
                      "https://overpass.private.coffee/api/interpreter"]

    # Build Overpass filter clauses. For station queries, also search railway and
    # public_transport tags so metro/train/bus stations are found.
    def _build_filters(am: str, r_m: int) -> str:
        if is_station_query:
            clauses = [
                f'nwr["amenity"="{am}"](around:{int(r_m)},{lat},{lon});',
                f'nwr["railway"="station"](around:{int(r_m)},{lat},{lon});',
                f'nwr["public_transport"="stop_position"](around:{int(r_m)},{lat},{lon});',
                f'nwr["public_transport"="station"](around:{int(r_m)},{lat},{lon});',
                f'node["highway"="bus_stop"](around:{int(r_m)},{lat},{lon});',
            ]
        else:
            clauses = [f'nwr["amenity"="{am}"](around:{int(r_m)},{lat},{lon});']
        return f'[out:json][timeout:4];({"".join(clauses)});out center body;'

    # Try primary amenity at requested radius, then broader fallbacks, then larger radius.
    # Overpass endpoints fail fast (4s timeout); Nominatim is the reliable fallback.
    overpass_dead = False
    for r_m in (radius_m, min(radius_m * 2, 50000)):
        if overpass_dead:
            break
        for am in [amenity] + fallback_amenities:
            if overpass_dead:
                break
            subql = _build_filters(am, r_m)
            for ep in _OSM_ENDPOINTS:
                try:
                    _rate_limit_1s()
                    r = requests.post(ep, data=subql, timeout=4,
                                      headers={"User-Agent": "JARVIS-assistant/1.0"})
                    if r.status_code in (429, 502, 503, 504):
                        overpass_dead = True
                        break
                    r.raise_for_status()
                    j = r.json()
                    out = []
                    for el in ((j.get("elements") or [])[:25]):
                        tags = el.get("tags") or {}
                        name = tags.get("name")
                        if not name:
                            continue
                        elat = el.get("lat") or el.get("center", {}).get("lat")
                        elon = el.get("lon") or el.get("center", {}).get("lon")
                        if elat is None or elon is None:
                            continue
                        # For station queries, keep only actual station/transport results
                        if is_station_query:
                            railway = (tags.get("railway") or "").lower()
                            pt = (tags.get("public_transport") or "").lower()
                            highway = (tags.get("highway") or "").lower()
                            amenity = (tags.get("amenity") or "").lower()
                            is_transport = (
                                railway in ("station", "halt", "tram_stop") or
                                pt in ("station", "stop_position") or
                                highway == "bus_stop" or
                                amenity in ("metro", "ticket_office")
                            )
                            if not is_transport:
                                continue
                        dist_m = _haversine(lat, lon, float(elat), float(elon))
                        out.append(_normalize(
                            "osm",
                            name,
                            rating=None,
                            count=None,
                            price=None,
                            lat=float(elat), lon=float(elon),
                            addr=tags.get("addr:full") or tags.get("addr:street") or "(no address)",
                            open_now=None,
                            maps=_osm_maps_url(lat, lon, name),
                            dist_m=dist_m,
                        ))
                    if out:
                        return out
                except Exception:
                    overpass_dead = True
                    break

    # Overpass unreachable or empty: fall back to Nominatim place search
    UA = "JARVIS-assistant/1.0 (personal use)"
    try:
        _rate_limit_1s()
        search_q = f"{amenity} near {lat},{lon}"
        if is_station_query:
            search_q = f"{q} near {lat},{lon}"
        r = requests.get("https://nominatim.openstreetmap.org/search",
                          params={"q": search_q,
                                  "format": "json", "limit": 10},
                          headers={"User-Agent": UA}, timeout=8)
        if r.status_code not in (429, 502, 503, 504):
            r.raise_for_status()
            j = r.json()
            out = []
            for item in (j or [])[:10]:
                name = item.get("display_name", "").split(",")[0] or "(unnamed)"
                try:
                    elat = float(item["lat"]); elon = float(item["lon"])
                except Exception:
                    continue
                # For station queries, keep only actual station/transport results
                if is_station_query:
                    display = item.get("display_name", "").lower()
                    osm_class = (item.get("class", "") or "").lower()
                    osm_type = (item.get("type", "") or "").lower()
                    is_transport = (
                        osm_class in ("railway", "station", "public_transport", "highway") or
                        any(k in display.split() for k in ("metro", "station", "subway",
                                                           "train", "bus-stop", "bus_stop"))
                    )
                    if not is_transport:
                        continue
                out.append(_normalize(
                    "osm",
                    name,
                    rating=None,
                    count=None,
                    price=None,
                    lat=elat, lon=elon,
                    addr=item.get("display_name", "(no address)"),
                    open_now=None,
                    maps=_osm_maps_url(lat, lon, name),
                    dist_m=_haversine(lat, lon, elat, elon),
                ))
            if out:
                return out
    except Exception:
        pass
    return []


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371000
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1); dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def _sanitize_place_text(s) -> str:
    s = (s or "").strip()
    s = "".join(ch for ch in s if ch.isprintable() or ch in "- ")
    s = " ".join(s.split())
    return (s or "(unnamed)")[:80]


def _rate_limit_1s() -> None:
    import time as _t
    global _LAST_NET
    if "_LAST_NET" not in globals():
        globals()["_LAST_NET"] = 0.0
    now = _t.time()
    wait = 1.0 - (now - globals()["_LAST_NET"])
    if wait > 0:
        _t.sleep(wait)
    globals()["_LAST_NET"] = _t.time()


def _normalize(source: str, name: str, rating, count, price, lat, lon, addr, open_now, maps, dist_m=None) -> dict:
    has_rating = rating is not None
    return {
        "source": source,
        "name": _sanitize_place_text(name),
        "rating": rating,
        "review_count": count if count is not None else (0 if has_rating else None),
        "price_level": price,
        "lat": lat,
        "lon": lon,
        "addr": _sanitize_place_text(addr),
        "open_now": open_now,
        "_maps": maps or "n/a",
        "distance_m": dist_m if dist_m is not None else 0.0,
    }


def _osm_maps_url(lat, lon, name) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}"


def _maps_link(place_id, lat, lon, name, fsq_id=None) -> str:
    if fsq_id:
        return f"https://foursquare.com/v/{fsq_id}"
    if place_id:
        return f"https://maps.google.com/?q=place_id:{place_id}"
    if lat is not None and lon is not None:
        return f"https://maps.google.com/maps?q={lat},{lon}"
    return "n/a"


def _detect_modifiers(query: str):
    """Return (reasonably-changed query, open_now_choice) based on keywords."""
    q = (query or "").strip()
    lower = q.lower()
    extra = []
    open_now = None
    cheap = any(w in lower for w in ("cheap", "budget", "affordable", "low cost"))
    if cheap:
        extra.append("cheap budget")
    if "veg" in lower or "vegetarian" in lower or "vegan" in lower:
        extra.append("vegetarian" if "vegetarian" in lower or "veg" in lower else "vegan")
    m = set(extra) - set(q.lower().split())
    new_q = q + (" " if extra else "") + " ".join(sorted(m))
    if "open now" in lower or "open 24" in lower or "right now" in lower:
        open_now = True
    return new_q, open_now


@tool
def find_places(query: str, radius_m: int = 3000, open_now: bool = True,
                min_rating: float = 4.0, min_reviews: int = 50, limit: int = 5) -> str:
    """Find nearby places using the right provider (Google, Foursquare, OSM).
    Ranking is done in Python (rating * log(1+reviews) -- distance penalty).
    Read-only."""
    q = (query or "").strip()
    if len(q) < 2:
        return "I need a query (e.g. 'find veg restaurants nearby')."
    coords = _saved_coords()
    if not coords:
        # Never ask twice in the same session; never ask for coordinates.
        already_asked = False
        try:
            already_asked = bool(get_state("places_location_asked", False))
            if not already_asked:
                set_state("places_location_asked", True)
        except Exception:
            pass
        if already_asked:
            return ("I still need your area and city to find nearby places. "
                    "Tell me the area/city and I'll search again.")
        return ("Which area and city are you in?")
    lat, lon, label = coords
    query2, detected_open = _detect_modifiers(q)
    applied_open = open_now if detected_open is None else detected_open
    lower_q = (q or "").lower()
    _station_kw = {"metro", "subway", "underground", "train station",
                   "railway station", "bus station", "bus stop", "station"}
    is_station_query = any(k in lower_q for k in _station_kw)
    if not isinstance(radius_m, (int, float)) or radius_m < 50 or radius_m > 50000:
        return "radius_m must be between 50 and 50000 meters."
    limit = max(1, min(int(limit), 10))
    provider = _provider_names()
    source = "none"
    places = []
    errors = []
    for prov_name in provider:
        provider_func = {"google": _google_fetch, "foursquare": _foursquare_fetch,
                          "osm": _osm_fetch}.get(prov_name)
        if not provider_func:
            continue
        try:
            places = provider_func(query2, lat, lon, radius_m)
        except Exception as e:
            errors.append(f"{prov_name}: {e}")
            continue
        if places:
            source = prov_name
            break
    if not places:
        if errors:
            # never surface raw errors
            return ("The free map service is busy, try again in a minute. "
                    "(Adding GOOGLE_PLACES_KEY or FOURSQUARE_KEY gives better uptime.)")
        if is_station_query:
            return (f"No station results found near {label}. "
                    f"The free map service may not have metro/train station data "
                    f"for this area. Try a bigger radius (e.g. {radius_m * 3} m) "
                    f"or add a GOOGLE_PLACES_KEY for better coverage.")
        return (f"No results within {radius_m} m. Try a bigger radius (e.g. "
                f"{radius_m * 3} m) or add a Foursquare/Google key for broader coverage.")
    ranked = score_places(places, radius_m, applied_open, min_rating, min_reviews)
    if not ranked:
        hint = ""
        if source == "osm":
            hint = (" (ratings are not available on OpenStreetMap; try adding "
                    "GOOGLE_PLACES_KEY to .env for rated results)")
        return (f"No places passed the filters (rating >= {min_rating}, reviews >= "
                f"{min_reviews}){hint}. Try lowering min_rating/min_reviews or "
                f"radius_m.")

    # build output with structured fields only; NEVER reviews
    lines = []
    src_note = (f"Source: {source} ({len(ranked)} picks)"
                + ("  -- NOTE: OpenStreetMap has no ratings/reviews;"
                    " results sorted by distance only." if source == "osm" else ""))
    lines.append(src_note)
    for p in ranked[:limit]:
        price = p.get("price_level")
        price_s = ("$" * max(1, min(int(price), 4))) if (isinstance(price, int) or str(price).isdigit()) else ""
        dist = int(p.get("distance_m", 0) or 0)
        rating = p.get("rating")
        status = "open" if p.get("open_now") is True else ("closed" if p.get("open_now") is False else "?")
        rating_s = "-" if rating is None else f"{rating}"
        count_s = "-" if p.get("review_count") is None else p.get("review_count")
        lines.append(
            f"{lines[-1] if False else ''}" if False else
            f"\u2022 {p['name']}  \u2014 {rating_s}⭐ ({count_s} reviews), "
            f"{dist}m, {status}{' ' + price_s if price_s else ''}\n"
            f"  {p['addr']}\n"
            f"  {p['_maps']}")
    out = "\n".join(lines)
    if len(out) > 1500:
        out = out[:1500] + "\n… (truncated)"
    return out