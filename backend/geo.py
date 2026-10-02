"""Geography layer: police stations, tower areas, jurisdictions. Coordinates are approximate and the
jurisdiction polygons are synthetic (nearest-station Voronoi cells), good enough for a prototype map.
"""
import math
import re

# name -> (lat, lon, district, state)
_STATIONS = [
    ("Azadpur PS",           28.7070, 77.1730, "North",               "Delhi"),
    ("Okhla PS",             28.5430, 77.2740, "South East",          "Delhi"),
    ("Seelampur PS",         28.6740, 77.2670, "North East",          "Delhi"),
    ("Sector 62 PS Noida",   28.6270, 77.3650, "Gautam Buddh Nagar",  "Uttar Pradesh"),
    ("Karol Bagh PS",        28.6520, 77.1900, "Central",             "Delhi"),
    ("Mundka PS",            28.6830, 77.0300, "Outer",               "Delhi"),
    ("Anand Vihar PS",       28.6470, 77.3160, "Shahdara",            "Delhi"),
    ("Dwarka PS",            28.5920, 77.0460, "South West",          "Delhi"),
    ("Sadar Bazaar PS",      28.6600, 77.2100, "North",               "Delhi"),
    ("Nehru Place PS",       28.5490, 77.2510, "South East",          "Delhi"),
    ("Lajpat Nagar PS",      28.5680, 77.2430, "South East",          "Delhi"),
    ("Janakpuri PS",         28.6210, 77.0820, "West",                "Delhi"),
    ("Rohini PS",            28.7160, 77.1180, "Rohini",              "Delhi"),
    ("Sector 29 PS Gurugram", 28.4690, 77.0680, "Gurugram",           "Haryana"),
]

# tower location (as written in cdr.csv) -> (lat, lon, owning station, aliases found in free text)
_AREAS = {
    "Gurugram Sector 29":     (28.4690, 77.0680, "Sector 29 PS Gurugram", ["gurugram", "gurgaon", "sector 29"]),
    "Mundka Industrial Area": (28.6830, 77.0270, "Mundka PS",             ["mundka"]),
    "Karol Bagh":             (28.6510, 77.1900, "Karol Bagh PS",         ["karol bagh"]),
    "Seelampur":              (28.6700, 77.2700, "Seelampur PS",          ["seelampur"]),
    "Sadar Bazaar":           (28.6620, 77.2120, "Sadar Bazaar PS",       ["sadar bazaar", "sadar bazar"]),
    "Noida Sector 62":        (28.6270, 77.3650, "Sector 62 PS Noida",    ["noida", "sector 62"]),
    "Okhla Phase 2":          (28.5330, 77.2750, "Okhla PS",              ["okhla"]),
    "Janakpuri":              (28.6210, 77.0820, "Janakpuri PS",          ["janakpuri"]),
    "Rohini Sector 9":        (28.7160, 77.1180, "Rohini PS",             ["rohini"]),
    "Dwarka Sector 10":       (28.5810, 77.0580, "Dwarka PS",             ["dwarka"]),
    "Azadpur Mandi":          (28.7090, 77.1760, "Azadpur PS",            ["azadpur"]),
    "Nehru Place":            (28.5490, 77.2530, "Nehru Place PS",        ["nehru place"]),
    "Lajpat Nagar":           (28.5670, 77.2430, "Lajpat Nagar PS",       ["lajpat nagar"]),
    "Anand Vihar ISBT":       (28.6500, 77.3160, "Anand Vihar PS",        ["anand vihar"]),
}

BBOX = (28.38, 76.96, 28.78, 77.46)  # south, west, north, east


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def haversine_km(a, b, c, d):
    p = math.pi / 180
    h = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def _clip(poly, a, b, c):
    """Keep the part of poly where a*x + b*y <= c (Sutherland-Hodgman, one half-plane)."""
    out = []
    for i, p in enumerate(poly):
        q = poly[(i + 1) % len(poly)]
        fp, fq = a * p[0] + b * p[1] - c, a * q[0] + b * q[1] - c
        if fp <= 0:
            out.append(p)
        if (fp < 0 < fq) or (fq < 0 < fp):
            t = fp / (fp - fq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def _cells():
    k = math.cos(math.radians(28.6))  # flatten lon so bisectors are roughly right
    pts = {n: (lon * k, lat) for n, lat, lon, *_ in _STATIONS}
    s, w, n_, e = BBOX
    cells = {}
    for name, (x, y) in pts.items():
        poly = [(w * k, s), (e * k, s), (e * k, n_), (w * k, n_)]
        for other, (ox, oy) in pts.items():
            if other == name:
                continue
            a, b = ox - x, oy - y
            c = (ox * ox + oy * oy - x * x - y * y) / 2
            poly = _clip(poly, a, b, c)
        # back to [lon, lat] GeoJSON ring
        ring = [[round(px / k, 5), round(py, 5)] for px, py in poly]
        cells[name] = ring + [ring[0]]
    return cells


_CELLS = _cells()

STATIONS = {}
for _n, _lat, _lon, _d, _st in _STATIONS:
    _id = slug(_n.replace(" PS", ""))
    STATIONS[_id] = dict(id=_id, name=_n, short=_n.replace(" PS", "").replace("PS ", ""), lat=_lat, lon=_lon,
                              district=_d, state=_st, areas=[], jurisdiction=_CELLS[_n])
_BY_NAME = {s["name"].lower(): s["id"] for s in STATIONS.values()}

AREAS = {}
for _name, (_lat, _lon, _stn, _al) in _AREAS.items():
    sid = slug(_stn.replace(" PS", ""))
    AREAS[slug(_name)] = dict(id=slug(_name), name=_name, lat=_lat, lon=_lon, station=sid, aliases=_al)
    STATIONS[sid]["areas"].append(slug(_name))
_AREA_BY_NAME = {a["name"].lower(): a["id"] for a in AREAS.values()}
_ALIASES = sorted(((al, a["id"]) for a in AREAS.values() for al in a["aliases"] + [a["name"].lower()]), key=lambda x: -len(x[0]))


def station_id(x):
    """Accepts an id ('okhla'), a name ('Okhla PS') or any casing/spacing of those. None if unknown."""
    if not x:
        return None
    s = slug(x)
    if s in STATIONS:
        return s
    if x.strip().lower() in _BY_NAME:
        return _BY_NAME[x.strip().lower()]
    for sid, st in STATIONS.items():  # 'Okhla' / 'okhla ps'
        if s in (slug(st["short"]), slug(st["name"])):
            return sid
    return None


def area_id(text):
    """Map a free-text place ('Azadpur Mandi', 'near the market in Mundka') to an area id, or None."""
    if not text:
        return None
    t = text.lower()
    if t.strip() in _AREA_BY_NAME:
        return _AREA_BY_NAME[t.strip()]
    for al, aid in _ALIASES:
        if re.search(rf"\b{re.escape(al)}\b", t):
            return aid
    return None


def areas_in(text):
    """Every distinct area mentioned in a text, in order of first appearance."""
    t = (text or "").lower()
    found = {}
    for al, aid in _ALIASES:
        m = re.search(rf"\b{re.escape(al)}\b", t)
        if m and aid not in found:
            found[aid] = m.start()
    return [a for a, _ in sorted(found.items(), key=lambda x: x[1])]


def station_of_area(aid):
    return AREAS[aid]["station"] if aid in AREAS else None


def nearest_station(lat, lon):
    return min(STATIONS.values(), key=lambda s: haversine_km(lat, lon, s["lat"], s["lon"]))["id"]


def meta():
    return dict(bbox=BBOX, center=[28.60, 77.15], note="Coordinates approximate; jurisdictions are synthetic nearest-station cells.",
                stations=list(STATIONS.values()), areas=list(AREAS.values()),
                districts=sorted({s["district"] for s in STATIONS.values()}), states=sorted({s["state"] for s in STATIONS.values()}))
