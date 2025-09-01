# lpg_precheck_pro.py
# -*- coding: utf-8 -*-

import os, io, re, math, json, sys, webbrowser, requests, shutil, textwrap
from typing import Dict, List, Tuple, Optional

# ===================== YOUR KEYS =====================
W3W_API_KEY    = "83M2SBJ6"       # what3words key
OPENAI_API_KEY = "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"
MAPBOX_TOKEN   = "pk.eyJ1IjoiamF5a2F5NzkiLCJhIjoiY21leWdlZWFiMDc5azJrcXQ2MzMxenFhaCJ9.lmrkdvXhjfU6-UC8ICxG7w"

# ===================== Console style =====================
RED, YEL, BLU, GRN, CYA, MAG, DIM, RST = "\033[91m","\033[93m","\033[94m","\033[92m","\033[96m","\033[95m","\033[2m","\033[0m"
BOLD = "\033[1m"
clear = lambda: os.system("cls" if os.name == "nt" else "clear")
hr = lambda: print(f"{BLU}{'—'*100}{RST}")
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
def strip_ansi(text: str) -> str: return ANSI_ESCAPE.sub('', text or "")

# ======== Terminal helpers & two-column layout ========
def term_width(max_width=120) -> int:
    return max(60, min(shutil.get_terminal_size(fallback=(100, 30)).columns, max_width))

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub('', text or "")

def _wrap_ansi(block: str, width: int) -> list[str]:
    """Wrap text that may contain ANSI; measure using visible width."""
    lines_out = []
    for para in (block or "").split("\n"):
        raw = para.rstrip()
        if not raw:
            lines_out.append("")
            continue
        words = raw.split(" ")
        line = ""
        for w in words:
            test = (line + " " + w).strip() if line else w
            if len(strip_ansi(test)) <= width:
                line = test
            else:
                if line:
                    lines_out.append(line)
                line = w
        if line:
            lines_out.append(line)
    return lines_out

def two_column_print(
    left: str,
    right: str,
    total_width: int | None = None,
    gutter: int = 5,
    right_ratio: float = 0.75,
):
    """Render two columns; widths based on visible text (ANSI safe)."""
    total_width = total_width or term_width(120)
    total_width = max(60, total_width)
    col_r = int((total_width - gutter) * right_ratio)
    col_l = max(20, total_width - gutter - col_r)

    L = _wrap_ansi(left,  col_l)
    R = _wrap_ansi(right, col_r)
    n = max(len(L), len(R))
    L += [""] * (n - len(L))
    R += [""] * (n - len(R))

    for a, b in zip(L, R):
        pad = max(0, col_l - len(strip_ansi(a)))
        print(a + " " * pad + " " * gutter + b)


# ===================== CoP thresholds & vehicle =====================
CoP = {
    "to_building_m": 3.0, "to_boundary_m": 3.0, "to_ignition_m": 3.0, "to_drain_m": 3.0,
    "overhead_info_m": 10.0, "overhead_block_m": 5.0, "rail_attention_m": 30.0,
    "poi_radius_m": 400.0, "wind_stagnant_mps": 1.0, "slope_attention_pct": 3.0,
    "approach_grade_warn_pct": 18.0, "route_vs_crowfly_ratio_warn": 1.7,
}
TANKER = {"max_height_m": 3.6, "max_width_m": 2.55, "gross_weight_t": 18.0}

# ===================== Optional libs for PDF/Map =====================
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_OK = True
except Exception:
    PIL_OK = False
    Image = ImageDraw = ImageFont = None

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    RL_OK = True
except Exception:
    RL_OK = False

# ===================== Geo helpers =====================
def meters_per_degree(lat_deg: float) -> Tuple[float,float]:
    lat = math.radians(lat_deg)
    return (111132.92 - 559.82*math.cos(2*lat) + 1.175*math.cos(4*lat),
            111412.84*math.cos(lat) - 93.5*math.cos(3*lat))
def ll_to_xy(lat0, lon0, lat, lon): mlat,mlon=meters_per_degree(lat0); return (lon-lon0)*mlon,(lat-lat0)*mlat
def dist_pts(lat0, lon0, pts): 
    if not pts: return None
    mlat,mlon=meters_per_degree(lat0)
    return min(math.hypot((lo-lon0)*mlon,(la-lat0)*mlat) for la,lo in pts)
def dist_line(lat0, lon0, line):
    if not line or len(line)<2: return None
    px,py=0.0,0.0
    verts=[ll_to_xy(lat0,lon0,la,lo) for la,lo in line]
    best=None
    for (ax,ay),(bx,by) in zip(verts,verts[1:]):
        apx,apy=px-ax,py-ay; abx,aby=bx-ax,by-ay; ab2=abx*abx+aby*aby
        t=0.0 if ab2==0 else max(0.0,min(1.0,(apx*abx+apy*aby)/ab2))
        cx,cy=ax+t*abx,ay+t*aby
        d=math.hypot(px-cx,py-cy)
        best=d if best is None else min(best,d)
    return best
def dist_poly(lat0,lon0,poly): return dist_line(lat0,lon0,poly+poly[:1])
def _dist_m(lat0, lon0, lat1, lon1):
    mlat,mlon=meters_per_degree(lat0)
    return math.hypot((lon1-lon0)*mlon,(lat1-lat0)*mlat)

# ===================== APIs =====================
def w3w(words:str)->Tuple[Optional[float],Optional[float]]:
    try:
        r=requests.get("https://api.what3words.com/v3/convert-to-coordinates",
                       params={"words":words,"key":W3W_API_KEY},timeout=15)
        if r.status_code==200:
            c=r.json().get("coordinates",{})
            return c.get("lat"), c.get("lng")
    except Exception: pass
    return None,None

def reverse_geocode(lat,lon)->Dict:
    try:
        r=requests.get("https://nominatim.openstreetmap.org/reverse",
                       params={"lat":lat,"lon":lon,"format":"jsonv2"},
                       headers={"User-Agent":"LPG-Precheck"},timeout=15)
        if r.status_code==200:
            j=r.json(); a=j.get("address") or {}
            return {"display_name":j.get("display_name"),
                    "road":a.get("road"),"postcode":a.get("postcode"),
                    "city":a.get("town") or a.get("city") or a.get("village"),
                    "county":a.get("county"),
                    "state_district":a.get("state_district"),
                    "local_authority": a.get("municipality") or a.get("county") or a.get("state_district")}
    except Exception: pass
    return {}

def open_meteo(lat,lon)->Dict:
    try:
        r=requests.get("https://api.open-meteo.com/v1/forecast",
                       params={"latitude":lat,"longitude":lon,
                               "current":"windspeed_10m,winddirection_10m"},timeout=12)
        cur=r.json().get("current",{}) if r.status_code==200 else {}
        spd,deg=cur.get("windspeed_10m"),cur.get("winddirection_10m")
        comp=["N","NE","E","SE","S","SW","W","NW"][round((deg or 0)%360/45)%8] if deg is not None else None
        return {"speed_mps":spd,"deg":deg,"compass":comp}
    except Exception: return {"speed_mps":None,"deg":None,"compass":None}

def open_elevations(points):
    try:
        locs="|".join(f"{la},{lo}" for la,lo in points)
        r=requests.get("https://api.open-elevation.com/api/v1/lookup",
                       params={"locations":locs},timeout=15)
        if r.status_code==200:
            return [it.get("elevation") for it in r.json().get("results",[])]
    except Exception: pass
    return [None]*len(points)

def slope_aspect(lat,lon,dx=20.0)->Dict:
    z=open_elevations([
        (lat,lon),
        (lat+dx/meters_per_degree(lat)[0],lon),
        (lat,lon+dx/meters_per_degree(lat)[1]),
        (lat-dx/meters_per_degree(lat)[0],lon),
        (lat,lon-dx/meters_per_degree(lat)[1]),
    ])
    if any(v is None for v in z): return {"elev_m":z[0] if z else None,"grade_pct":None,"aspect_deg":None}
    zc,zn,ze,zs,zw=z; dz_dy=(zn-zs)/(2*dx); dz_dx=(ze-zw)/(2*dx)
    grade=math.hypot(dz_dx,dz_dy)*100.0
    aspect=(math.degrees(math.atan2(dz_dx,dz_dy))+360)%360
    return {"elev_m":zc,"grade_pct":round(grade,1),"aspect_deg":round(aspect,0)}

OVERPASS="https://overpass-api.de/api/interpreter"; UA={"User-Agent":"LPG-Precheck-Pro/1.9"}
def overpass(lat,lon,r)->Dict:
    q=f"""
    [out:json][timeout:60];
    (
      way(around:{r},{lat},{lon})["building"];
      relation(around:{r},{lat},{lon})["building"];
      way(around:{r},{lat},{lon})["highway"];
      node(around:{r},{lat},{lon})["man_made"="manhole"];
      node(around:{r},{lat},{lon})["manhole"];
      way(around:{r},{lat},{lon})["waterway"="drain"];
      way(around:{r},{lat},{lon})["tunnel"="culvert"];
      way(around:{r},{lat},{lon})["power"="line"];
      node(around:{r},{lat},{lon})["power"~"tower|pole"];
      way(around:{r},{lat},{lon})["railway"]["railway"!="abandoned"]["railway"!="disused"];
      way(around:{r},{lat},{lon})["waterway"~"river|stream|ditch"];
      way(around:{r},{lat},{lon})["natural"="water"];
      way(around:{r},{lat},{lon})["landuse"];
      way(around:{r},{lat},{lon})["maxheight"];
      way(around:{r},{lat},{lon})["maxwidth"];
      way(around:{r},{lat},{lon})["maxweight"];
      way(around:{r},{lat},{lon})["hgv"];
      way(around:{r},{lat},{lon})["access"];
      way(around:{r},{lat},{lon})["oneway"];
      way(around:{r},{lat},{lon})["surface"];
      way(around:{r},{lat},{lon})["smoothness"];
    );
    out tags geom;
    """
    try:
        r=requests.post(OVERPASS,data={"data":q},headers=UA,timeout=90)
        r.raise_for_status(); return r.json()
    except Exception as e:
        print(f"{YEL}⚠ Overpass: {e}{RST}"); return {"elements":[]}

def parse_osm(lat0,lon0,data)->Dict:
    bpolys, roads, drains, manholes, plines, pnodes, rails, wlines, wpolys, land_polys = [],[],[],[],[],[],[],[],[],[]
    rest_ways, surf_ways = [],[]
    for el in data.get("elements",[]):
        t=el.get("type"); tags=el.get("tags",{}) or {}; geom=el.get("geometry")
        coords=[(g["lat"],g["lon"]) for g in (geom or [])]
        if tags.get("building") and t in ("way","relation"): bpolys.append(coords)
        elif tags.get("highway") and t=="way":
            roads.append(coords)
            if any(k in tags for k in ("maxheight","maxwidth","maxweight","hgv","access","oneway")):
                rest_ways.append({"tags":tags,"coords":coords})
            if "surface" in tags or "smoothness" in tags:
                surf_ways.append({"tags":tags,"coords":coords})
        elif t=="way" and (tags.get("waterway")=="drain" or tags.get("tunnel")=="culvert"): drains.append(coords)
        elif t=="node" and (tags.get("man_made")=="manhole" or "manhole" in tags): manholes.append((el.get("lat"),el.get("lon")))
        elif t=="way" and tags.get("power")=="line": plines.append(coords)
        elif t=="node" and tags.get("power") in ("tower","pole"): pnodes.append((el.get("lat"),el.get("lon")))
        elif t=="way" and tags.get("railway") and tags.get("railway") not in ("abandoned","disused"): rails.append(coords)
        elif t=="way" and tags.get("waterway") in ("river","stream","ditch"): wlines.append(coords)
        elif t=="way" and tags.get("natural")=="water": wpolys.append(coords)
        elif t in ("way","relation") and tags.get("landuse"): land_polys.append({"tag":tags.get("landuse"),"coords":coords})
    d_build=min([dist_poly(lat0,lon0,p) for p in bpolys] or [None])
    d_road =min([dist_line(lat0,lon0,l) for l in roads] or [None])
    d_drain=min([dist_line(lat0,lon0,l) for l in drains]+([dist_pts(lat0,lon0,manholes)] if manholes else []) or [None])
    d_over =min([dist_line(lat0,lon0,l) for l in plines]+([dist_pts(lat0,lon0,pnodes)] if pnodes else []) or [None])
    d_rail =min([dist_line(lat0,lon0,l) for l in rails] or [None])
    d_water=min([dist_line(lat0,lon0,l) for l in wlines]+[dist_poly(lat0,lon0,p) for p in wpolys] or [None])
    land_counts={}
    for lp in land_polys:
        tag=lp["tag"]; land_counts[tag]=land_counts.get(tag,0)+1
    if land_counts:
        top=max(land_counts,key=lambda k:land_counts[k])
        if top in ("residential","commercial","retail"): land_class="Domestic/Urban"
        elif top in ("industrial","industrial;retail"):   land_class="Industrial"
        else: land_class="Rural/Agricultural"
    else:
        land_class = "Domestic/Urban" if len(bpolys)>80 else ("Rural/Agricultural" if len(bpolys)<20 else "Mixed")
    return {
        "d_building_m": round(d_build,1) if d_build is not None else None,
        "d_road_m":     round(d_road,1)  if d_road  is not None else None,
        "d_drain_m":    round(d_drain,1) if d_drain is not None else None,
        "d_overhead_m": round(d_over,1)  if d_over  is not None else None,
        "d_rail_m":     round(d_rail,1)  if d_rail  is not None else None,
        "d_water_m":    round(d_water,1) if d_water is not None else None,
        "land_class": land_class,
        "counts": {"buildings":len(bpolys),"roads":len(roads),"drains":len(drains),"manholes":len(manholes),
                   "power_lines":len(plines),"power_structs":len(pnodes),"rail_lines":len(rails),
                   "water_lines":len(wlines),"water_polys":len(wpolys)},
        "restrictions": rest_ways, "surfaces": surf_ways, "nearest_road_line": roads[0] if roads else None
    }

def get_nearest_hospital_osm(lat: float, lon: float) -> dict:
    base = "https://overpass-api.de/api/interpreter"
    headers = {"User-Agent": "LPG-Precheck-Pro/OSM-Hospital-Search"}
    radii = [2000, 5000, 10000, 20000, 50000]
    def query_osm(r, a_and_e_only=True):
        emergency_filter = (
            '["amenity"="hospital"]["emergency"~"yes|designated|24_7|24/7"]'
            ';node(around:{r},{lat},{lon})["healthcare"="hospital"]["emergency"~"yes|designated|24_7|24/7"]'
            ';node(around:{r},{lat},{lon})["emergency_service"="yes"]'
        )
        any_hospital = '["amenity"="hospital"]'
        filt = emergency_filter if a_and_e_only else any_hospital
        q = f"""
[out:json][timeout:60];
(
  node(around:{r},{lat},{lon}){filt};
  way(around:{r},{lat},{lon}){filt};
  relation(around:{r},{lat},{lon}){filt};
);
out tags center;
""".strip()
        try:
            resp = requests.post(base, data={"data": q}, headers=headers, timeout=60)
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except Exception:
            return []
    best=None
    for r in radii:
        els=query_osm(r,True)
        for el in els:
            tags=el.get("tags",{}) or {}
            if el.get("type")=="node": la,lo=el.get("lat"),el.get("lon")
            else:
                cen=el.get("center") or {}; la,lo=cen.get("lat"),cen.get("lon")
            if la is None or lo is None: continue
            d=_dist_m(lat,lon,la,lo)
            name=tags.get("name") or "Unnamed hospital"
            phone=tags.get("phone") or tags.get("contact:phone") or tags.get("contact:telephone")
            cand={"name":name,"distance_m":d,"lat":la,"lon":lo,"phone":phone,"tags":tags,"emergency":True}
            if (best is None) or (d<best["distance_m"]): best=cand
        if best: return best
    fallback=None
    els=query_osm(50000,False)
    for el in els:
        tags=el.get("tags",{}) or {}
        if el.get("type")=="node": la,lo=el.get("lat"),el.get("lon")
        else:
            cen=el.get("center") or {}; la,lo=cen.get("lat"),cen.get("lon")
        if la is None or lo is None: continue
        d=_dist_m(lat,lon,la,lo)
        name=tags.get("name") or "Unnamed hospital"
        phone=tags.get("phone") or tags.get("contact:phone") or tags.get("contact:telephone")
        cand={"name":name,"distance_m":d,"lat":la,"lon":lo,"phone":phone,"tags":tags,"emergency":False}
        if (fallback is None) or (d<fallback["distance_m"]): fallback=cand
    return fallback or {}

def approach_grade(lat,lon,road_line,N=6)->Dict:
    if not road_line: return {"avg_pct":None,"max_pct":None}
    mlat,mlon=meters_per_degree(lat)
    best,pt=None,None
    for la,lo in road_line:
        d=math.hypot((lo-lon)*mlon,(la-lat)*mlat)
        if best is None or d<best: best,pt=d,(la,lo)
    if pt is None: return {"avg_pct":None,"max_pct":None}
    pts=[(lat+(pt[0]-lat)*i/N, lon+(pt[1]-lon)*i/N) for i in range(N+1)]
    z=open_elevations(pts)
    if any(v is None for v in z): return {"avg_pct":None,"max_pct":None}
    grades=[]
    for i in range(N):
        run=math.hypot((pts[i+1][1]-pts[i][1])*mlon,(pts[i+1][0]-pts[i][0])*mlat)
        rise=z[i+1]-z[i]; grades.append(abs(rise/max(run,1e-3))*100.0)
    return {"avg_pct":round(sum(grades)/len(grades),1), "max_pct":round(max(grades),1)}

def osrm_ratio(lat,lon)->Optional[float]:
    try:
        r1=requests.get(f"https://router.project-osrm.org/nearest/v1/driving/{lon},{lat}",timeout=12)
        if r1.status_code!=200: return None
        snap_lon,snap_lat = r1.json()["waypoints"][0]["location"]
        r2=requests.get(f"https://router.project-osrm.org/route/v1/driving/{snap_lon},{snap_lat};{lon},{lat}",
                        params={"overview":"false"},timeout=15)
        if r2.status_code!=200: return None
        dist=float(r2.json()["routes"][0]["distance"])
        crow=math.hypot(lat-snap_lat,lon-snap_lon)*111000.0
        if crow<50 or dist<10: return None
        return dist/crow
    except Exception: return None

def parse_num(s):
    if not s: return None
    s=str(s).lower().strip()
    for u in ("m","meter","metre","meters","metres","t","ton","tonne","tonnes"):
        if s.endswith(u): s=s[:-len(u)].strip()
    try: return float(s.replace(",","."))        
    except: return None

def restriction_notes(ways)->List[str]:
    out=[]
    for w in ways:
        t=w.get("tags",{})
        h=parse_num(t.get("maxheight")); wdt=parse_num(t.get("maxwidth")); wt=parse_num(t.get("maxweight"))
        if h is not None and h<TANKER["max_height_m"]: out.append(f"maxheight {h} m")
        if wdt is not None and wdt<TANKER["max_width_m"]: out.append(f"maxwidth {wdt} m")
        if wt is not None and wt<TANKER["gross_weight_t"]: out.append(f"maxweight {wt} t")
        if (t.get("hgv") or "").lower() in ("no","destination"): out.append(f"hgv={t.get('hgv').lower()}")
        if (t.get("access") or "").lower() in ("no","private"): out.append(f"access={t.get('access').lower()}")
        if (t.get("oneway") or "").lower()=="yes": out.append("oneway")
    seen=set(); out2=[]
    for s in out:
        if s not in seen: seen.add(s); out2.append(s)
    return out2

def surface_info(ways)->Dict:
    risky=0; samples=[]
    for w in ways:
        t=w.get("tags",{})
        surf=(t.get("surface") or "").lower()
        smooth=(t.get("smoothness") or "").lower()
        if any(k in surf for k in ("gravel","ground","dirt","grass","unpaved","compacted","sand")): risky+=1
        if any(k in smooth for k in ("bad","very_bad","horrible","impassable")): risky+=1
        if surf or smooth: samples.append(f"{surf or 'n/a'}/{smooth or 'n/a'}")
    return {"risky_count":risky,"samples":samples[:8]}

def flood_risk(feats, slope, elev)->Dict:
    d=feats.get("d_water_m"); g=slope.get("grade_pct") or 0.0; z=elev or 0.0
    level="Low"; why=[]
    if d is None: why.append("No mapped watercourse nearby")
    else:
        if d<50: level="High"; why.append(f"Watercourse within {d} m")
        elif d<150: level="Medium"; why.append(f"Watercourse at {d} m")
        else: why.append(f"Watercourse at {d} m")
    if g>=6: why.append(f"Steep local slope {g}% (runoff/flow)")
    if z and z<10: why.append(f"Low elevation {int(z)} m a.s.l.")
    return {"level":level, "why":why}

def risk_score(feats, wind, slope, appr, rr, notes, surf, flood)->Dict:
    score=0.0; why=[]
    def add(x,msg): nonlocal score; score+=x; why.append((x,msg))
    def penal(dist, lim, msg, base=18, per=6, cap=40):
        if dist is None or dist>=lim: return
        pts=min(cap, base + per*(lim-dist)); add(pts, f"{msg} below {lim} m (≈ {dist} m)")
    penal(feats["d_building_m"],CoP["to_building_m"],"Building separation")
    penal(feats["d_road_m"],CoP["to_ignition_m"],"Ignition proxy (road/path)")
    penal(feats["d_drain_m"],CoP["to_drain_m"],"Drain/manhole separation")
    d_ov=feats.get("d_overhead_m")
    if d_ov is not None and d_ov<CoP["overhead_block_m"]: add(28,f"Overhead within {CoP['overhead_block_m']} m (≈ {d_ov} m)")
    elif d_ov is not None and d_ov<CoP["overhead_info_m"]: add(10,f"Overhead within {CoP['overhead_info_m']} m (≈ {d_ov} m)")
    d_rail=feats.get("d_rail_m")
    if d_rail is not None and d_rail<CoP["rail_attention_m"]: add(10,f"Railway within {CoP['rail_attention_m']} m (≈ {d_rail} m)")
    if feats.get("d_water_m") is not None and feats["d_water_m"]<50: add(8,"Watercourse within 50 m")
    spd=wind.get("speed_mps")
    if spd is not None and spd<CoP["wind_stagnant_mps"]: add(6,f"Low wind {spd:.1f} m/s")
    g=slope.get("grade_pct")
    if g is not None and g>=CoP["slope_attention_pct"]: add(12 if g>=6 else 8, f"Local slope {g:.1f}%")
    if appr.get("max_pct") is not None and appr["max_pct"]>=CoP["approach_grade_warn_pct"]: add(12,f"Steep approach (max {appr['max_pct']}%)")
    if rr is not None and rr>CoP["route_vs_crowfly_ratio_warn"]: add(10,f"Route length ≫ crow-fly ({rr:.2f}×)")
    if notes: add(min(12, 4*len(notes)),"Access restrictions: "+", ".join(notes))
    if surf.get("risky_count",0)>0: add(min(10,2*surf['risky_count']), f"Surface flags={surf['risky_count']}")
    if flood["level"]=="High": add(12,"Flood susceptibility high")
    elif flood["level"]=="Medium": add(6,"Flood susceptibility medium")
    score=round(min(100.0,score),1)
    status="PASS" if score<20 else ("ATTENTION" if score<50 else "BLOCKER")
    why.sort(key=lambda x:-x[0])
    return {"score":score,"status":status,"explain":why}

# ===================== Static map =====================
def fetch_map(lat, lon, zoom=17, size=(1000, 750)):
    if not PIL_OK: return None
    if MAPBOX_TOKEN:
        w,h=size
        marker=f"pin-l+f30({lon},{lat})"; style="light-v11"
        url=(f"https://api.mapbox.com/styles/v1/mapbox/{style}/static/"
             f"{marker}/{lon},{lat},{zoom},0/{w}x{h}?access_token={MAPBOX_TOKEN}")
        try:
            r=requests.get(url,timeout=15); r.raise_for_status()
            return Image.open(io.BytesIO(r.content)).convert("RGBA")
        except Exception: pass
    urls=[
        f"https://staticmap.openstreetmap.de/staticmap.php?center={lat},{lon}&zoom={zoom}&size={size[0]}x{size[1]}&markers={lat},{lon},red-pushpin",
        f"https://staticmap.komoot.io/?type=roadmap&size={size[0]}x{size[1]}&zoom={zoom}&markers={lon},{lat}",
    ]
    for url in urls:
        try:
            r=requests.get(url,timeout=15); r.raise_for_status()
            return Image.open(io.BytesIO(r.content)).convert("RGBA")
        except Exception: continue
    return None

def draw_ring_card(lat, zoom=17, size=(1000,750)):
    if not PIL_OK: return None
    img=Image.new("RGBA",size,(245,247,250,255)); d=ImageDraw.Draw(img)
    cx,cy=size[0]//2,size[1]//2
    for r,col in ((3,(220,0,0,180)),(6,(255,140,0,160))):
        px=40 if r==3 else 80; d.ellipse((cx-px,cy-px,cx+px,cy+px),outline=col,width=4)
    d.text((20,20),"Map unavailable — reference rings (3 m / 6 m)", fill=(80,80,80))
    d.text((20,size[1]-40),f"Lat {lat:.5f}  |  N ↑", fill=(80,80,80))
    return img

def overlay_rings(img, lat, zoom):
    if not PIL_OK or img is None: return img
    def mpp(lat,zoom): return 156543.03392*math.cos(math.radians(lat))/(2**zoom)
    scale=mpp(lat,zoom); cx,cy=img.width//2,img.height//2; d=ImageDraw.Draw(img,"RGBA")
    for r,col in ((3,(220,0,0,180)),(6,(255,140,0,160))):
        px=max(1,int(r/scale)); d.ellipse((cx-px,cy-px,cx+px,cy+px),outline=col,width=4)
    return img

def save_map_card(words, lat, lon):
    map_img = fetch_map(lat,lon) or draw_ring_card(lat)
    if map_img is None: return None
    map_img = overlay_rings(map_img, lat, 17)
    out=f"map_{words.replace('.','_')}.png"
    try: map_img.save(out); return out
    except Exception: return None

def open_pdf(path):
    try:
        if os.name=="nt": os.startfile(path)  # type: ignore
        elif sys.platform=="darwin": os.system(f'open "{path}"')
        else: os.system(f'xdg-open "{path}"')
    except Exception: webbrowser.open_new(path)

# ===================== AI commentary =====================
def make_offline_sections(ctx: Dict) -> Dict[str,str]:
    feats,wind,slope,appr,rr,flood,hospital,risk = (ctx.get(k,{}) for k in
        ["features","wind","slope","approach","route_ratio","flood","hospital","risk"])
    hosp_line = f"{hospital.get('name','n/a')} ({(hospital.get('distance_m',0)/1000):.1f} km)" if hospital else "n/a"
    S1=(f"Local gradient {slope.get('grade_pct','n/a')}% (aspect {int(slope.get('aspect_deg') or 0)}°). "
        f"Separations: building {feats.get('d_building_m')} m, road {feats.get('d_road_m')} m, "
        f"drain {feats.get('d_drain_m')} m, overhead {feats.get('d_overhead_m')} m. "
        f"Wind {(wind.get('speed_mps') or 0):.1f} m/s from {wind.get('compass') or 'n/a'}. "
        f"Heuristic {risk.get('score','?')}/100 → {risk.get('status','?')}.")
    S2=(f"Flood susceptibility {flood.get('level')} ({'; '.join(flood.get('why',[]))}). "
        f"Watercourse distance ~{feats.get('d_water_m','n/a')} m; drains/manholes {feats.get('d_drain_m','n/a')} m. "
        f"Land use {feats.get('land_class','n/a')}.")
    S3=(f"Approach grades avg {appr.get('avg_pct','?')}% / max {appr.get('max_pct','?')}%. " +
        (f"Route sanity {rr:.2f}× crow-fly. " if rr else "") +
        f"Nearest A&E: {hosp_line}. Validate height/width/weight/HGV/access restrictions and surfaces for mini-bulk delivery.")
    S4=("Overall: suitable with routine controls" if risk.get('status')=='PASS' else "Overall: attention required. "
        "Priorities: confirm separations to CoP1, manage pooling pathways, validate approach under wet/icy conditions, "
        "maintain signage/controls.")
    return {"Safety Risk Profile":S1,"Environmental Considerations":S2,"Access & Logistics":S3,"Overall Site Suitability":S4}

def ai_sections(context: Dict) -> Dict[str,str]:
    """
    Ask the model for four sections and parse them into a dict.
    If the API call fails, fall back to make_offline_sections(context).
    """
    if not OPENAI_API_KEY:
        return make_offline_sections(context)

    prompt = f"""
You are an LPG siting assessor. Produce FOUR sections ONLY, for this site:

[1] Safety Risk Profile
[2] Environmental Considerations
[3] Access & Logistics
[4] Overall Site Suitability

Guidance:
- Be numeric, site-specific, and practical (no textbook content).
- Use the provided distances, wind, slope, approach grades, route ratio, flood points, land use, and nearest A&E.
- Note that very low wind (< 1 m/s) means stagnation risk (do NOT suggest windbreaks).
- Include clear implications + recommended mitigations (signage, access controls, confirm separations to CoP1, drainage measures, etc.).
- Length target: ~350–500 words total across all sections (roughly 25–35 lines of prose).
- DO NOT repeat section titles in the body; put all content on lines after each title.
- Output format MUST be exactly:

[1] Safety Risk Profile
...body text for section 1 (no heading repeated)...
[2] Environmental Considerations
...body text for section 2...
[3] Access & Logistics
...body text for section 3...
[4] Overall Site Suitability
...body text for section 4...

Context:
{json.dumps(context, ensure_ascii=False)}
""".strip()

    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type":"application/json"},
            json={
                "model":"gpt-4o-mini",
                "temperature":0.2,
                "max_tokens":1400,
                "messages":[
                    {"role":"system","content":"You are an LPG safety and logistics assessor."},
                    {"role":"user","content":prompt}
                ],
            },
            timeout=60
        )
        if r.status_code != 200:
            return make_offline_sections(context)

        text = r.json()["choices"][0]["message"]["content"].strip()

        sections = {k:"" for k in [
            "Safety Risk Profile",
            "Environmental Considerations",
            "Access & Logistics",
            "Overall Site Suitability"
        ]}
        current=None
        mapping={"[1]":"Safety Risk Profile","[2]":"Environmental Considerations","[3]":"Access & Logistics","[4]":"Overall Site Suitability"}

        for raw in text.splitlines():
            line = raw.rstrip()
            if not line:
                if current:
                    sections[current] += "\n"
                continue
            started = False
            for key, name in mapping.items():
                if line.strip().startswith(key):
                    current = name
                    remainder = line.strip()[len(key):].strip(":-—– \t")
                    if remainder:
                        sections[current] += remainder + "\n"
                    started = True
                    break
            if not started and current:
                sections[current] += line + "\n"

        # Fallback fill if any empty
        fb=make_offline_sections(context)
        for k in sections:
            if not sections[k].strip():
                sections[k]=fb[k]
        return sections
    except Exception:
        return make_offline_sections(context)

_TITLE_RX = re.compile(
    r'^\s*(?:#{1,6}\s*)?(?:\[\s*\d+\s*\])?\s*(safety\s*risk\s*profile|environmental\s*considerations|access\s*&\s*logistics|overall\s*site\s*suitability)\s*[:\-–—]*\s*$',
    flags=re.I
)

def _tidy_sections(sections: dict) -> dict:
    """Remove any leading title line from each section body and trim extra blank lines."""
    clean={}
    for heading, body in (sections or {}).items():
        lines=[ln.rstrip() for ln in (body or "").splitlines()]
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines and _TITLE_RX.match(lines[0]):
            lines = lines[1:]
            while lines and not lines[0].strip():
                lines.pop(0)
        clean[heading]="\n".join(lines).strip()
    return clean

# ===================== PDF (same as before) =====================
def pdf_report(words, addr, la_name, hospital_line, lat, lon,
               wind, slope, appr, rr, flood, feats,
               cop_report_lines, risk, breakdown_lines, sections,
               map_path, out_path):
    """
    Clean, paginated PDF report (no grey boxes), parity with console,
    and a blank line before each AI section header.
    """
    if not RL_OK:
        return None

    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics

    W, H = A4
    M = 38               # page margin
    LEAD = 12            # default line height
    y = H - 46           # initial cursor Y
    PAGE_BOTTOM = 40     # bottom guard so we don't print off-page

    blue = colors.HexColor("#1f4e79")
    grey = colors.HexColor("#555555")

    c = canvas.Canvas(out_path, pagesize=A4)

    # ---------- helpers ----------
    def new_page():
        nonlocal y
        c.showPage()
        y = H - 46

    def ensure(h):
        """Ensure there is 'h' pts remaining; else start new page."""
        nonlocal y
        if y - h < PAGE_BOTTOM:
            new_page()

    def text_line(txt, col=colors.black, font="Helvetica", size=10):
        nonlocal y
        t = strip_ansi(txt or "")
        ensure(size + 3)
        c.setFillColor(col)
        c.setFont(font, size)
        c.drawString(M, y, t)
        y -= (size + 3)
        c.setFillColor(colors.black)

    def header(txt, size=16, col=blue):
        nonlocal y
        ensure(size + 6)
        c.setFillColor(col)
        c.setFont("Helvetica-Bold", size)
        c.drawString(M, y, strip_ansi(txt))
        y -= (size + 6)
        c.setFillColor(colors.black)

    def section(txt, size=12, col=blue):
        nonlocal y
        ensure(size + 8)
        y -= 4
        c.setFillColor(col)
        c.setFont("Helvetica-Bold", size)
        c.drawString(M, y, strip_ansi(txt))
        y -= (size + 2)
        c.setFillColor(colors.black)

    def wrap_paragraph(text, width=W-2*M, font="Helvetica", size=10, leading=LEAD):
        """Simple word wrap for a paragraph block with pagination."""
        nonlocal y
        text = strip_ansi(text or "")
        c.setFont(font, size)

        for para in text.split("\n"):
            para = para.rstrip()
            if not para:
                ensure(leading)
                y -= leading
                continue

            words = para.split()
            line = ""
            for w in words:
                test = (line + " " + w).strip() if line else w
                if pdfmetrics.stringWidth(test, font, size) <= width:
                    line = test
                else:
                    ensure(leading)
                    c.drawString(M, y, line)
                    y -= leading
                    line = w
            if line:
                ensure(leading)
                c.drawString(M, y, line)
                y -= leading

    def bullet_list(items, bullet="•", font="Helvetica", size=10, leading=LEAD):
        nonlocal y
        for it in (items or []):
            s = f"{bullet} {strip_ansi(it)}"
            ensure(leading)
            c.setFont(font, size)
            c.drawString(M, y, s)
            y -= leading

    # ---------- title & header ----------
    header(f"LPG Pre-Check — ///{words}")

    # address lines (be defensive with keys)
    addr_line = ", ".join([p for p in [addr.get('road'), addr.get('city'), addr.get('postcode')] if p])
    if addr_line:
        text_line(addr_line, grey)
    if addr.get("display_name"):
        text_line(addr["display_name"], grey)
    text_line(f"Local authority: {la_name or 'n/a'}", grey)
    text_line(f"Nearest Hospital (A&E): {hospital_line}", grey)

    # map (scaled)
    if map_path:
        try:
            ir = ImageReader(map_path)
            from PIL import Image as PILImage
            iw, ih = PILImage.open(map_path).size
            maxw, maxh = W - 2*M, 260
            sc = min(maxw/iw, maxh/ih)
            ensure(ih*sc + 12)
            c.drawImage(ir, M, y - ih*sc, width=iw*sc, height=ih*sc)
            y -= ih*sc + 12
        except Exception:
            pass

    # ---------- KEY METRICS ----------
    section("Key Metrics")
    wind_txt  = f"{(wind.get('speed_mps') or 0):.1f} m/s from {wind.get('compass') or 'n/a'}"
    slope_txt = f"{slope.get('grade_pct','n/a')}% (aspect {int(slope.get('aspect_deg') or 0)}°)"
    appr_txt  = f"avg {appr.get('avg_pct','?')}% / max {appr.get('max_pct','?')}%"
    rr_txt    = f"{rr:.2f}× crow-fly" if rr else "n/a"
    flood_txt = f"{flood['level']} — " + "; ".join(flood["why"])
    text_line(f"Wind (10 m): {wind_txt}")
    text_line(f"Local slope: {slope_txt}")
    text_line(f"Approach grade: {appr_txt}")
    text_line(f"Route sanity: {rr_txt}")
    text_line(f"Flood susceptibility: {flood_txt}")

    # ---------- SEPARATIONS ----------
    section("Separations (~%d m)" % int(CoP["poi_radius_m"]))
    def fmt(v): return f"{v:.1f} m" if isinstance(v, (int, float)) else "n/a"
    bullet_list([
        f"Building:       {fmt(feats.get('d_building_m'))}",
        f"Road/footpath:  {fmt(feats.get('d_road_m'))}",
        f"Drain/manhole:  {fmt(feats.get('d_drain_m'))}",
        f"Overhead:       {fmt(feats.get('d_overhead_m'))}",
        f"Railway:        {fmt(feats.get('d_rail_m'))}",
        f"Watercourse:    {fmt(feats.get('d_water_m'))}",
    ])
    text_line(f"Land use: {feats.get('land_class','n/a')}")

    # ---------- COUNTS ----------
    counts = feats["counts"]
    section("Counts")
    bullet_list([
        f"Buildings:  {counts['buildings']}",
        f"Roads:      {counts['roads']}",
        f"Drains:     {counts['drains']}",
        f"Manholes:   {counts['manholes']}",
        f"Power:      {counts['power_lines']}/{counts['power_structs']}",
        f"Rail:       {counts['rail_lines']}",
    ])

    # ---------- ACCESS & SURFACE ----------
    if feats.get("restrictions"):
        section("Access Restrictions")
        bullet_list([str(n) for n in restriction_notes(feats["restrictions"])])
    if (feats.get("surfaces") is not None) and (feats.get("surfaces") != []):
        s = surface_info(feats["surfaces"])
        if s.get("risky_count", 0) > 0:
            section("Surface Flags")
            bullet_list([f"{s['risky_count']} ({', '.join(s['samples'])})"])

    # ---------- CoP1 checks ----------
    section("CoP1-style separation checks (screening)")
    bullet_list(cop_report_lines)

    # ---------- Risk score ----------
    section("Risk score breakdown")
    text_line(f"Total: {risk['score']}/100 → {risk['status']}")
    bullet_list(breakdown_lines)

    # ---------- AI sections (add a blank line before each header) ----------
    for head in [
        "Safety Risk Profile",
        "Environmental Considerations",
        "Access & Logistics",
        "Overall Site Suitability"
    ]:
        # add a blank line (no page break)
        ensure(LEAD)
        y -= LEAD

        section(head)
        wrap_paragraph(sections.get(head, ""))

    c.showPage()
    c.save()
    return out_path



# ===================== Console report (two columns, coloured groups) =====================
def console_report(words, addr, la_name, hospital_line, lat, lon, wind, slope, appr, rr, flood, feats, cop_report_lines, notes, surf, risk, breakdown_lines, sections):
    clear()
    print(f"{BLU}{'='*100}{RST}")
    print(f"{GRN}LPG Customer Tank — Location Intelligence Pre-Check (Deep Mode){RST}")
    print(f"{BLU}{'='*100}{RST}\n")
    print(f"{CYA}Location:{RST} ///{words}   lat {lat:.6f}, lon {lon:.6f}")
    al=", ".join([p for p in [addr.get('road'),addr.get('city'),addr.get('postcode')] if p])
    if al: print(f"{DIM}{al}{RST}")
    if addr.get("display_name"): print(f"{DIM}{addr['display_name']}{RST}")
    print(f"{DIM}Local authority: {la_name or 'n/a'}{RST}")
    print(f"{DIM}Nearest Hospital (A&E): {hospital_line}{RST}")
    hr()

    wind_txt = f"{(wind.get('speed_mps') or 0):.1f} m/s from {wind.get('compass') or 'n/a'} ({wind.get('deg') or 'n/a'}°)"
    slope_txt = f"{slope.get('grade_pct','n/a')}% towards {int(slope.get('aspect_deg') or 0)}°"
    appr_txt  = f"avg {appr.get('avg_pct','?')}% / max {appr.get('max_pct','?')}%"
    rr_txt    = f"OSRM route ≈ {rr:.2f}× crow-fly" if rr else "n/a"
    flood_txt = f"{flood['level']} — {'; '.join(flood['why'])}"
    counts    = feats["counts"]

    def _fmt_m(v): return f"{v:.1f} m" if isinstance(v,(int,float)) else "n/a"
    SEP_COL = CYA
    sep_lines = [
        f"{SEP_COL}•{RST}  Building:       {_fmt_m(feats.get('d_building_m'))}",
        f"{SEP_COL}•{RST}  Road/footpath:  {_fmt_m(feats.get('d_road_m'))}",
        f"{SEP_COL}•{RST}  Drain/manhole:  {_fmt_m(feats.get('d_drain_m'))}",
        f"{SEP_COL}•{RST}  Overhead:       {_fmt_m(feats.get('d_overhead_m'))}",
        f"{SEP_COL}•{RST}  Railway:        {_fmt_m(feats.get('d_rail_m'))}",
        f"{SEP_COL}•{RST}  Watercourse:    {_fmt_m(feats.get('d_water_m'))}",
    ]
    sep_block = f"{SEP_COL}{BOLD}Separations (~{int(CoP['poi_radius_m'])} m):{RST}\n" + "\n".join(sep_lines) + "\n"

    COP_COL = MAG
    cop_header = f"{COP_COL}{BOLD}CoP1 separation checks (screening):{RST}"
    cop_items  = "\n".join(f"{COP_COL}•{RST}  {l}" for l in cop_report_lines)
    cop_block  = f"{cop_header}\n{cop_items}\n"

    counts = feats["counts"]
    cnt_lines = [
        f"• Buildings:  {counts['buildings']}",
        f"• Roads:      {counts['roads']}",
        f"• Drains:     {counts['drains']}",
        f"• Manholes:   {counts['manholes']}",
        f"• Power:      {counts['power_lines']}/{counts['power_structs']}",
        f"• Rail:       {counts['rail_lines']}",
    ]
    counts_block = f"Counts:\n" + "\n".join(cnt_lines) + "\n"

    notes_block = (
        "Access restrictions:\n" + "\n".join(f"• {n}" for n in notes) + "\n"
    ) if notes else ""

    left_summary = (
        f"Wind (10 m): {wind_txt}\n"
        f"Local slope: {slope_txt}\n"
        f"Approach: {appr_txt}\n"
        f"Route sanity: {rr_txt}\n"
        f"Flood: {flood_txt}\n\n"
        + sep_block +
        f"  Land use: {feats.get('land_class','n/a')}\n"
        + counts_block
        + notes_block
        + (f"Surface flags: {surf['risky_count']} ({', '.join(surf['samples'])})\n" if surf.get('risky_count',0)>0 else "")
        + "\n" + cop_block +
        f"\nRisk score: {risk['score']}/100 → {risk['status']}\n"
        "Top factors:\n" + "\n".join("  • "+b for b in breakdown_lines)
    )

    ai_right = (
        f"[1] Safety Risk Profile\n{sections.get('Safety Risk Profile','')}\n\n"
        f"[2] Environmental Considerations\n{sections.get('Environmental Considerations','')}\n\n"
        f"[3] Access & Logistics\n{sections.get('Access & Logistics','')}\n\n"
        f"[4] Overall Site Suitability\n{sections.get('Overall Site Suitability','')}\n"
    )

    two_column_print(
        left_summary,
        ai_right,
        total_width=term_width(120),
        gutter=5,
        right_ratio=0.65,   # a bit wider for the AI text
    )

    hr()

# ===================== Main =====================
def main():
    clear()
    words=input("Enter location (what3words, word.word.word): ").strip().lstrip("/")
    if words.count(".")!=2 or not all(p.isalpha() for p in words.split(".")):
        print(f"{RED}Invalid what3words format.{RST}"); return

    lat,lon = w3w(words)
    if lat is None: print(f"{RED}what3words lookup failed.{RST}"); return

    addr     = reverse_geocode(lat,lon)
    la_name  = addr.get("local_authority") or addr.get("county") or addr.get("state_district")
    wind     = open_meteo(lat,lon)
    slope    = slope_aspect(lat,lon,dx=20.0)
    osm      = overpass(lat,lon,int(CoP["poi_radius_m"]))
    feats    = parse_osm(lat,lon,osm)
    hospital = get_nearest_hospital_osm(lat,lon)
    hospital_line = "n/a"
    if hospital:
        hospital_line = f"{hospital['name']} ({hospital['distance_m']/1000:.1f} km)"
        if hospital.get("phone"): hospital_line += f"  Tel: {hospital['phone']}"
        feats["d_hospital_m"] = round(hospital["distance_m"],1)
    appr     = approach_grade(lat,lon,feats.get("nearest_road_line"),N=6)
    rr       = osrm_ratio(lat,lon)
    notes    = restriction_notes(feats.get("restrictions",[]))
    surf     = surface_info(feats.get("surfaces",[]))
    flood    = flood_risk(feats, slope, slope.get("elev_m"))
    risk     = risk_score(feats,wind,slope,appr,rr,notes,surf,flood)

    def pf(label, actual, req, mode=">="):
        if actual is None: return f"{label}: {YEL}Unknown{RST}"
        if mode==">=":
            return f"{label}: {(GRN+'PASS'+RST) if actual>=req else (RED+'FAIL'+RST)} — {actual:.1f} m {'≥' if actual>=req else '<'} {req:.1f} m"
        if mode=="not<":
            return f"{label}: {(RED+'FAIL'+RST) if actual<req else (GRN+'OK'+RST)} — {actual:.1f} m {'<' if actual<req else '≥'} {req:.1f} m"
        return f"{label}: n/a"

    cop_lines = [
        pf("Building separation",  feats.get("d_building_m"), CoP["to_building_m"], ">="),
        f"Boundary separation: {YEL}Not assessed{RST}",
        pf("Ignition proxy (road/footpath)", feats.get("d_road_m"), CoP["to_ignition_m"], ">="),
        pf("Drain/manhole",     feats.get("d_drain_m"), CoP["to_drain_m"], ">="),
    ]
    d_ov = feats.get("d_overhead_m")
    if d_ov is None:
        cop_lines.append("Overhead power: " + YEL + "Unknown" + RST)
    else:
        cop_lines.append(pf("Overhead (no-go band)", d_ov, CoP["overhead_block_m"], "not<"))
        if d_ov < CoP["overhead_info_m"]:
            cop_lines.append(f"Overhead (info band): {YEL}Attention{RST} — within {CoP['overhead_info_m']} m (≈ {d_ov:.1f} m)")
        else:
            cop_lines.append(f"Overhead (info band): {GRN}Outside attention band{RST} — {d_ov:.1f} m ≥ {CoP['overhead_info_m']} m")
    d_rail = feats.get("d_rail_m")
    if d_rail is None:
        cop_lines.append("Railway: " + GRN + "None mapped nearby" + RST)
    else:
        if d_rail < CoP["rail_attention_m"]:
            cop_lines.append(f"Railway: {YEL}Attention{RST} — {d_rail:.1f} m < {CoP['rail_attention_m']} m")
        else:
            cop_lines.append(f"Railway: {GRN}OK{RST} — {d_rail:.1f} m ≥ {CoP['rail_attention_m']} m")

    breakdown = [f"+{pts} {msg}" for pts,msg in risk["explain"]][:7]
    if len(breakdown)<7:
        if feats.get("d_building_m") and feats["d_building_m"]>=CoP["to_building_m"]:
            breakdown.append(f"+0 Adequate building separation ({feats['d_building_m']} m ≥ {CoP['to_building_m']} m)")
        if feats.get("d_overhead_m") and feats["d_overhead_m"]>=CoP["overhead_info_m"]:
            breakdown.append(f"+0 Overhead outside attention band ({feats['d_overhead_m']} m ≥ {CoP['overhead_info_m']} m)")
        if len(breakdown)>7: breakdown=breakdown[:7]

    ctx = {"words":words,"address":addr,"authority":la_name,"hospital":hospital,"wind":wind,"slope":slope,
           "features":feats,"approach":appr,"route_ratio":rr,"restrictions":notes,"surfaces":surf,
           "flood":flood,"risk":risk,"cop":CoP}
    sections = _tidy_sections(ai_sections(ctx))

    console_report(words, addr, la_name, hospital_line, lat, lon, wind, slope, appr, rr,
                   flood, feats, cop_lines, notes, surf, risk, breakdown, sections)

    gen=input(f"{YEL}Generate PDF report and open it? (y/n): {RST}").strip().lower()
    if gen in ("y","yes"):
        map_path = save_map_card(words, lat, lon)
        out = f"precheck_{words.replace('.','_')}.pdf"
        pdf = pdf_report(words, addr, la_name, hospital_line, lat, lon, wind, slope, appr, rr,
                         flood, feats, cop_lines, risk, breakdown, sections, map_path, out)
        if pdf:
            print(f"{GRN}PDF saved: {out}{RST}"); open_pdf(out)
        else:
            print(f"{RED}ReportLab not available; couldn’t build PDF.{RST}")

    again=input(f"{YEL}Check another location? (y/n): {RST}").strip().lower()
    if again in ("y","yes"):
        print(); main()

if __name__=="__main__":
    main()