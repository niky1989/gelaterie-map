# -*- coding: utf-8 -*-
"""Misura quanto dista ogni gelateria dal comune che dichiara.

Il controllo sui confini provinciali non basta: se il geocodificatore del
Gambero Rosso aggancia il comune sbagliato ma dentro la stessa provincia,
il punto resta "dentro" e passa liscio. Qui si confronta con il centro del
comune, preso da Nominatim.
"""
import json, math, os, re, subprocess, sys, time, urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, 'comuni_cache.json')

def comune_di(indirizzo):
    """'via B. Gemona, 5 – Cordovado (PN)' -> ('Cordovado', 'PN')"""
    m = re.search(r'–\s*(.+?)\s*\(([A-Z]{2})\)\s*$', indirizzo)
    return (m.group(1), m.group(2)) if m else (None, None)

def nominatim(params):
    url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(params)
    out = subprocess.run(['curl', '-s', '-m', '30', '-A',
                          'mappa-gelaterie-personale/1.0 (uso privato)', url],
                         capture_output=True, text=True).stdout
    return json.loads(out) if out.strip() else []

def distanza(a, b):
    R = 6371.0
    dlat = math.radians(b[0] - a[0]); dlon = math.radians(b[1] - a[1])
    h = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[0]))
         * math.cos(math.radians(b[0])) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))

cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
gel = json.load(open(os.path.join(BASE, 'gelaterie.json')))

coppie = sorted({comune_di(x['a']) for x in gel} - {(None, None)})
print('%d comuni diversi da cercare' % len(coppie), file=sys.stderr)
for i, (com, pr) in enumerate(coppie):
    k = '%s (%s)' % (com, pr)
    if k in cache:
        continue
    res = nominatim({'city': com, 'country': 'Italia', 'format': 'json', 'limit': 1})
    if not res:
        res = nominatim({'q': '%s, %s, Italia' % (com, pr), 'format': 'json', 'limit': 1})
        time.sleep(1.1)
    cache[k] = [float(res[0]['lat']), float(res[0]['lon'])] if res else None
    time.sleep(1.1)
    if i % 25 == 0:
        json.dump(cache, open(CACHE, 'w'), ensure_ascii=False)
        print('  %d/%d' % (i, len(coppie)), file=sys.stderr)
json.dump(cache, open(CACHE, 'w'), ensure_ascii=False)

sospetti, senza = [], []
for x in gel:
    com, pr = comune_di(x['a'])
    c = cache.get('%s (%s)' % (com, pr))
    if not c:
        senza.append(x['n'])
        continue
    d = distanza((x['lat'], x['lng']), tuple(c))
    if d > 8:
        sospetti.append((d, x, com))

print('\n%d schede, %d comuni non trovati, %d oltre gli 8 km dal comune\n'
      % (len(gel), len(senza), len(sospetti)))
for d, x, com in sorted(sospetti, reverse=True):
    print('%6.1f km  %-36s %-24s %s%s'
          % (d, x['n'][:36], com[:24], x['a'][:46],
             '  [approssimata]' if x['ap'] else ''))
if senza:
    print('\ncomuni non trovati:', ', '.join(sorted(set(senza))[:20]))
