# -*- coding: utf-8 -*-
"""Controlla che ogni gelateria cada dentro la provincia che dichiara.

Le coordinate arrivano dal Gambero Rosso e non sono sempre giuste: dove
l'indirizzo contiene un nome che somiglia a un comune (per esempio
"via B. Gemona" a Cordovado) il loro geocodificatore aggancia il comune
sbagliato. Il confronto con i confini provinciali ISTAT trova questi casi
senza bisogno di rete.
"""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))

# Il file dei confini ha ancora le province sarde di prima del 2016.
EQUIVALENTI = {'SU': {'VS', 'CI', 'SU'}, 'SS': {'SS', 'OT'}, 'NU': {'NU', 'OG'}}

def dentro(anello, x, y):
    d = False
    n = len(anello)
    for i in range(n):
        x1, y1 = anello[i][0], anello[i][1]
        x2, y2 = anello[(i + 1) % n][0], anello[(i + 1) % n][1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            d = not d
    return d

def dentro_geometria(geom, x, y):
    poligoni = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
    for poly in poligoni:
        if dentro(poly[0], x, y) and not any(dentro(buco, x, y) for buco in poly[1:]):
            return True
    return False

prov = json.load(open(os.path.join(BASE, 'provinces.geojson')))['features']
per_sigla = {}
for f in prov:
    per_sigla.setdefault(f['properties']['prov_acr'], []).append(f)

gel = json.load(open(os.path.join(BASE, 'gelaterie.json')))
fuori = []
for x in gel:
    sigle = EQUIVALENTI.get(x['p'], {x['p']})
    feature = [f for s in sigle for f in per_sigla.get(s, [])]
    if not feature:
        fuori.append((x, 'sigla sconosciuta'))
        continue
    if not any(dentro_geometria(f['geometry'], x['lng'], x['lat']) for f in feature):
        # in quale provincia cade davvero?
        vera = next((f['properties']['prov_acr'] for f in prov
                     if dentro_geometria(f['geometry'], x['lng'], x['lat'])), 'nessuna (mare?)')
        fuori.append((x, vera))

print('%d schede controllate, %d fuori provincia\n' % (len(gel), len(fuori)))
for x, vera in sorted(fuori, key=lambda t: t[0]['p']):
    print('%-38s %-28s dichiara %s, cade in %s%s'
          % (x['n'][:38], x['ci'][:28], x['p'], vera, '  [approssimata]' if x['ap'] else ''))
