# -*- coding: utf-8 -*-
"""Legge raw.txt (scaricato da gamberorosso.it), ripara i caratteri rovinati,
geocodifica le schede senza coordinate e scrive gelaterie.json."""
import json, os, re, subprocess, sys, time, urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, 'geocode_cache.json')
CORREZIONI = os.path.join(BASE, 'correzioni.json')

ABBREV = [
    ('v.le ', 'viale '), ('p.zza ', 'piazza '), ('p.za ', 'piazza '),
    ('c.so ', 'corso '), ('v.lo ', 'vicolo '), ('l.go ', 'largo '),
    ('l.mare ', 'lungomare '), ('p.le ', 'piazzale '), ('p.tta ', 'piazzetta '),
    ('c.da ', 'contrada '), ('s.da prov.le ', 'strada provinciale '),
    ('s.s. ', 'strada statale '), ('l. Arno ', 'lungarno '),
]

def ripara(s):
    # Il sito serve alcuni apostrofi come byte 0x92 (Windows-1252): arrivano come '?'.
    s = re.sub(r'(?<=[A-Za-zàèéìòù])\?(?=[A-Za-zàèéìòù])', "'", s)
    s = s.replace(' ? ', ' – ')
    return re.sub(r'\s{2,}', ' ', s).strip()

def spezza_indirizzo(addr):
    """'via L. Serra, 3 – Bologna (BO)' -> ('via L. Serra, 3', 'Bologna')"""
    if '–' in addr:
        via, coda = addr.rsplit('–', 1)
    else:
        via, coda = addr, ''
    citta = re.sub(r'\s*\([A-Z]{2}\)\s*$', '', coda).strip()
    via = via.strip().rstrip(',')
    low = via.lower()
    for a, b in ABBREV:
        if low.startswith(a):
            via = b + via[len(a):]
            break
    return via, citta

def nominatim(params):
    # curl e non urllib: il Python di sistema non ha i certificati radice.
    url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(params)
    out = subprocess.run(['curl', '-s', '-m', '30', '-A',
                          'mappa-gelaterie-personale/1.0 (uso privato)', url],
                         capture_output=True, text=True).stdout
    return json.loads(out) if out.strip() else []

def geocodifica(addr, cache):
    if addr in cache:
        return cache[addr]
    via, citta = spezza_indirizzo(addr)
    tentativi = [
        {'street': via, 'city': citta, 'country': 'Italia', 'format': 'json', 'limit': 1},
        {'city': citta, 'country': 'Italia', 'format': 'json', 'limit': 1},
    ]
    for i, p in enumerate(tentativi):
        try:
            res = nominatim(p)
        except Exception as e:
            print('  errore rete:', e, file=sys.stderr)
            res = []
        time.sleep(1.1)          # Nominatim: massimo una richiesta al secondo
        if res:
            out = {'lat': float(res[0]['lat']), 'lng': float(res[0]['lon']),
                   'preciso': i == 0}
            cache[addr] = out
            return out
    cache[addr] = None
    return None

def main():
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    # Alcune coordinate del Gambero Rosso sono sbagliate: le loro, non nostre.
    # Vedi correzioni.json, e controlla_posizioni.py / controlla_comuni.py per
    # come si ritrovano.
    corr = json.load(open(CORREZIONI)) if os.path.exists(CORREZIONI) else {}
    righe = open(os.path.join(BASE, 'raw.txt'), encoding='utf-8').read().splitlines()
    out, mancanti = [], 0
    for r in righe:
        if not r.strip():
            continue
        c = r.split('\\t')
        pid, nome, path, lat, lng, coni, reg, prov, citta, addr, premio = (c + [''] * 11)[:11]
        nome, addr, premio = ripara(nome), ripara(addr), ripara(premio)
        preciso = True
        if lat and lng:
            lat, lng = float(lat), float(lng)
        else:
            mancanti += 1
            print('geocodifico %-40s %s' % (nome[:40], addr))
            g = geocodifica(addr, cache)
            json.dump(cache, open(CACHE, 'w'), ensure_ascii=False)
            if not g:
                print('  NON TROVATO', file=sys.stderr)
                continue
            lat, lng, preciso = g['lat'], g['lng'], g['preciso']
        c = corr.get(pid)
        if c:
            lat, lng, preciso = c['lat'], c['lng'], not c['ap']
        out.append({
            'n': nome, 'c': int(coni), 'lat': round(lat, 5), 'lng': round(lng, 5),
            'r': reg, 'p': prov.upper(), 'ci': citta, 'a': addr,
            'u': 'https://www.gamberorosso.it/luoghi/locali/' + path,
            'pr': premio, 'ap': 0 if preciso else 1,
        })
    json.dump(out, open(os.path.join(BASE, 'gelaterie.json'), 'w'),
              ensure_ascii=False, separators=(',', ':'))
    print('scritte %d schede (%d geocodificate a mano, %d corrette a mano)'
          % (len(out), mancanti, len([k for k in corr if not k.startswith('_')])))

main()
