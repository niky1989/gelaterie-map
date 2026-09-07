# -*- coding: utf-8 -*-
"""Per le schede sospette confronta il punto del Gambero Rosso con quello
che si ottiene geocodificando l'indirizzo completo, provincia compresa."""
import json, math, os, re, subprocess, time, urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
ABBREV = [('v.le ','viale '),('p.zza ','piazza '),('c.so ','corso '),('v.lo ','vicolo '),
          ('l.go ','largo '),('l.mare ','lungomare '),('p.le ','piazzale '),
          ('p.tta ','piazzetta '),('c.da ','contrada '),('s.da prov.le ','strada provinciale '),
          ('s.s. ','strada statale '),('l. Arno ','lungarno ')]

def pezzi(ind):
    m = re.search(r'–\s*([^–]+?)\s*\(([A-Z]{2})\)\s*$', ind)
    com, pr = (m.group(1), m.group(2)) if m else (None, None)
    via = ind.rsplit('–', 1)[0].strip().rstrip(',') if '–' in ind else ind
    low = via.lower()
    for a, b in ABBREV:
        if low.startswith(a):
            via = b + via[len(a):]; break
    return via, com, pr

def cerca(params):
    url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(params)
    out = subprocess.run(['curl','-s','-m','30','-A',
                          'mappa-gelaterie-personale/1.0 (uso privato)', url],
                         capture_output=True, text=True).stdout
    time.sleep(1.1)
    return json.loads(out) if out.strip() else []

def dist(a, b):
    R=6371.0; dlat=math.radians(b[0]-a[0]); dlon=math.radians(b[1]-a[1])
    h=(math.sin(dlat/2)**2+math.cos(math.radians(a[0]))*math.cos(math.radians(b[0]))
       *math.sin(dlon/2)**2)
    return 2*R*math.asin(math.sqrt(h))

NOMI = [l.split('  ',1)[0].strip() for l in open(os.path.join(BASE,'sospetti.txt'))
        if l.strip()]
gel = json.load(open(os.path.join(BASE,'gelaterie.json')))
esito = []
for nome in NOMI:
    x = next((g for g in gel if g['n'].strip() == nome), None)
    if not x:
        print('?? non trovata:', nome); continue
    via, com, pr = pezzi(x['a'])
    p = (x['lat'], x['lng'])
    ind = cerca({'street': via, 'city': com, 'county': pr, 'country':'Italia',
                 'format':'json','limit':1})
    if not ind:
        ind = cerca({'q': '%s, %s, %s, Italia' % (via, com, pr), 'format':'json','limit':1})
    centro = cerca({'q': '%s, provincia di %s, Italia' % (com, pr), 'format':'json','limit':1})
    d_ind = dist(p, (float(ind[0]['lat']), float(ind[0]['lon']))) if ind else None
    d_com = dist(p, (float(centro[0]['lat']), float(centro[0]['lon']))) if centro else None
    esito.append((nome, com, pr, d_ind, d_com,
                  ind[0]['display_name'][:60] if ind else '-'))

print('\n%-34s %-20s %9s %9s  %s' % ('gelateria','comune','da via','da com.','via trovata'))
for nome, com, pr, d_ind, d_com, dn in sorted(
        esito, key=lambda t: -(t[3] if t[3] is not None else (t[4] or 0))):
    print('%-34s %-20s %9s %9s  %s'
          % (nome[:34], ('%s (%s)' % (com, pr))[:20],
             '-' if d_ind is None else '%.1f km' % d_ind,
             '-' if d_com is None else '%.1f km' % d_com, dn))
