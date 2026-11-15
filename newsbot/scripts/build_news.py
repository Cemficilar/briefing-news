#!/usr/bin/env python3
"""Baut data/news.json aus kostenlosen RSS-Feeds (nur Python-Standardbibliothek)."""
import json, re, html, sys, os, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")
WINDOW_H = 48
MAX_ITEMS = 12
UA = "Mozilla/5.0 (compatible; BriefingBot/1.0)"

def gn(q, days=2):
    return "https://news.google.com/rss/search?q=" + urllib.parse.quote(q + f" when:{days}d") + "&hl=de&gl=DE&ceid=DE:de"

# kind "gn" = Google News (Quelle steckt im Titel/<source>, keine Textvorschau)
CATS = [
 {"id":"krypto","title":"Krypto","icon":"bitcoin","tint":"orange",
  "more":[{"name":"CoinDesk","url":"https://www.coindesk.com/"},{"name":"BTC-ECHO","url":"https://www.btc-echo.de/"}],
  "feeds":[("Cointelegraph","https://cointelegraph.com/rss",None),
           ("Decrypt","https://decrypt.co/feed",None),
           ("Google News",gn("Bitcoin OR Ethereum OR Krypto"),"gn")]},
 {"id":"etfs","title":"ETFs","icon":"chart","tint":"green",
  "more":[{"name":"ETF.com","url":"https://www.etf.com/"},{"name":"justETF News","url":"https://www.justetf.com/de/news/"}],
  "feeds":[("Google News",gn('ETF OR "MSCI World" OR "Spot-ETF" OR Indexfonds'),"gn"),
           ("Google News",gn('ETF inflows OR outflows OR "ETF" Bitcoin OR iShares OR Vanguard'),"gn")]},
 {"id":"ipos","title":"Große Börsengänge","icon":"bell","tint":"indigo",
  "more":[{"name":"Renaissance Capital IPO Center","url":"https://www.renaissancecapital.com/IPO-Center/News"},{"name":"IPOScoop","url":"https://www.iposcoop.com/category/ipo-buzz/"}],
  "days":7,
  "feeds":[("Google News",gn("Börsengang OR IPO (Anthropic OR OpenAI OR SpaceX OR Stripe OR Databricks OR Milliarden)",7),"gn")]},
 {"id":"stoerungen","title":"Störungen","icon":"warning","tint":"red",
  "more":[{"name":"Downdetector Deutschland","url":"https://downdetector.de/"},{"name":"Microsoft 365 Status","url":"https://status.cloud.microsoft/"}],
  "feeds":[("Google News",gn("Störung OR Ausfall OR outage (Microsoft OR AWS OR Google OR Cloudflare OR Amazon OR Apple OR WhatsApp OR Netflix OR Telekom OR Starlink)"),"gn"),
           ("Google News",gn("global outage OR massive outage OR Flugausfall Systemausfall"),"gn")]},
 {"id":"ki","title":"KI","icon":"sparkles","tint":"purple",
  "more":[{"name":"The Neuron","url":"https://www.theneuron.ai/"},{"name":"heise KI","url":"https://www.heise.de/thema/Kuenstliche-Intelligenz"}],
  "feeds":[("TechCrunch","https://techcrunch.com/category/artificial-intelligence/feed/",None),
           ("The Verge","https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",None),
           ("heise online","https://www.heise.de/rss/heise-atom.xml","kiflt"),
           ("Google News",gn('KI OR "künstliche Intelligenz" OR OpenAI OR Anthropic OR Gemini'),"gn")]},
 {"id":"politik-de","title":"Deutschland","icon":"building","tint":"blue",
  "more":[{"name":"tagesschau Inland","url":"https://www.tagesschau.de/inland"},{"name":"Bundestag Textarchiv","url":"https://www.bundestag.de/dokumente/textarchiv"}],
  "feeds":[("tagesschau","https://www.tagesschau.de/inland/index~rss2.xml",None),
           ("SPIEGEL","https://www.spiegel.de/politik/deutschland/index.rss",None),
           ("ZEIT ONLINE","https://newsfeed.zeit.de/politik/index",None),
           ("Google News",gn("Bundesregierung OR Bundestag OR Merz OR Bundeshaushalt"),"gn")]},
 {"id":"global","title":"Global","icon":"globe","tint":"teal",
  "more":[{"name":"Al Jazeera News","url":"https://www.aljazeera.com/news/"},{"name":"BBC World","url":"https://www.bbc.com/news/world"}],
  "feeds":[("BBC News","https://feeds.bbci.co.uk/news/world/rss.xml",None),
           ("tagesschau","https://www.tagesschau.de/ausland/index~rss2.xml",None),
           ("Al Jazeera","https://www.aljazeera.com/xml/rss/all.xml",None),
           ("Google News",gn("Welt Nachrichten Krieg OR Gipfel OR Wahl OR Krise"),"gn")]},
]

KI_WORDS = re.compile(r"\b(KI|AI|künstliche|OpenAI|Anthropic|Claude|ChatGPT|Gemini|LLM|Nvidia|Sprachmodell)\b", re.I)
HIGH_WORDS = re.compile(r"eilmeldung|breaking|rekordhoch|crash|rücktritt|resign|börsengang|\bipo\b|zinserhöhung|notstand|landesweit", re.I)
NOISE = re.compile(r"aktie prognose|aktienprognose|kursziel|jetzt kaufen|horoskop|gewinnspiel|rabatt|angebot:|\bdeal\b|bester preis", re.I)
STOP = set("der die das und für mit von den dem des ein eine einer nach über wird sind ist auf bei aus the and for with that this from after over into will have has says say new about than more".split())

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()

def strip(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()

def ptime(s):
    if not s: return None
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try: d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception: return None
    if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
    return d

def tag(e):  # Namespace entfernen
    return e.tag.split("}")[-1]

def parse(xml, feed_name, kind, feed_name_filter=None):
    root = ET.fromstring(xml)
    out = []
    for it in root.iter():
        if tag(it) not in ("item", "entry"): continue
        f = {tag(c): c for c in it}
        title = strip(f["title"].text) if "title" in f else ""
        link = ""
        if "link" in f:
            link = (f["link"].get("href") or f["link"].text or "").strip()
        t = None
        for k in ("pubDate", "published", "updated", "date"):
            if k in f and f[k].text:
                t = ptime(f[k].text.strip()); break
        desc = ""
        for k in ("description", "summary", "content"):
            if k in f and f[k].text: desc = strip(f[k].text); break
        src = feed_name
        if kind == "gn":
            desc = ""
            if "source" in f and f["source"].text: src = strip(f["source"].text)
            if " - " in title:
                title, tail = title.rsplit(" - ", 1)
                if src == feed_name: src = tail
        if not title or not link or not t or NOISE.search(title): continue
        if kind == "gn" and feed_name_filter and not feed_name_filter.search(title): continue
        if kind == "kiflt" and not KI_WORDS.search(title + " " + desc): continue
        out.append({"title": title, "url": link, "time": t, "summary": desc, "source": src})
    return out

def toks(t):
    return {w for w in re.findall(r"[a-zäöüß0-9]{4,}", t.lower()) if w not in STOP}

def cluster(items):
    items.sort(key=lambda x: x["time"], reverse=True)
    groups = []
    for it in items:
        ts = toks(it["title"]); it["_t"] = ts
        for g in groups:
            u = ts | g["_t"]
            j = len(ts & g["_t"]) / len(u) if u else 0
            if j >= 0.4 or len(ts & g["_t"]) >= 4:
                g["members"].append(it); g["_t"] |= ts; break
        else:
            groups.append({"_t": set(ts), "members": [it]})
    return groups

def build_item(g):
    m = g["members"]
    best = next((x for x in m if x["summary"]), m[0])
    seen, sources = set(), []
    for x in sorted(m, key=lambda x: x["time"]):
        key = x["source"].lower()
        if key in seen: continue
        seen.add(key); sources.append({"name": x["source"], "url": x["url"]})
    n = len(sources)
    summ = best["summary"]
    if len(summ) > 240: summ = summ[:237].rsplit(" ", 1)[0] + "…"
    if not summ:
        summ = ("Berichtet von " + ", ".join(s["name"] for s in sources[:4]) + ".") if n > 1 else f"Meldung von {sources[0]['name']}."
    imp = "high" if (n >= 3 or HIGH_WORDS.search(best["title"])) else ("medium" if n == 2 else "low")
    d = {"title": best["title"], "summary": summ,
         "time": max(x["time"] for x in m).astimezone(TZ).isoformat(timespec="seconds"),
         "importance": imp, "sources": sources, "verified": n >= 2}
    if n == 1: d["singleSource"] = True
    return d

def main():
    now = datetime.now(timezone.utc)
    cats, ok, fail = [], 0, 0
    for c in CATS:
        days = c.get("days", 2)
        cutoff = now - timedelta(hours=days * 24)
        items = []
        for name, url, kind in c["feeds"]:
            try:
                got = parse(fetch(url), name, kind, KI_WORDS if (c["id"] == "ki" and kind == "gn") else None)
                items += [x for x in got if cutoff <= x["time"] <= now + timedelta(hours=1)]
                ok += 1
            except Exception as e:
                fail += 1
                print(f"! {c['id']}: {name} fehlgeschlagen: {e}", file=sys.stderr)
        res = [build_item(g) for g in cluster(items)]
        w = {"high": 0, "medium": 1, "low": 2}
        # Höchstens 3 'high' pro Kategorie, Rest zurückstufen
        res.sort(key=lambda d: (w[d["importance"]], -datetime.fromisoformat(d["time"]).timestamp()))
        for i, d in enumerate([r for r in res if r["importance"] == "high"][3:]): d["importance"] = "medium"
        res.sort(key=lambda d: (w[d["importance"]], -datetime.fromisoformat(d["time"]).timestamp()))
        cats.append({"id": c["id"], "title": c["title"], "icon": c["icon"], "tint": c["tint"],
                     "items": res[:MAX_ITEMS], "more": c["more"]})
    total = sum(len(c["items"]) for c in cats)
    print(f"Feeds ok: {ok}, fehlgeschlagen: {fail}, Meldungen: {total}")
    if total < 5 or ok == 0:
        print("Zu wenige Daten – bestehende news.json bleibt unverändert.", file=sys.stderr); sys.exit(0)
    out = {"schema": 1, "generatedAt": now.astimezone(TZ).isoformat(timespec="seconds"), "windowHours": WINDOW_H,
           "note": "Automatisch aus RSS-Feeds erstellt. Uhrzeiten in MEZ.", "categories": cats}
    path = os.path.join(os.path.dirname(__file__), "..", "data", "news.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
