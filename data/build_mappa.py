# -*- coding: utf-8 -*-
"""Da provinces.geojson costruisce la geometria SVG della mappa.

Confini di regione e di provincia devono combaciare al pixel anche a forte
ingrandimento: per questo NON si semplificano i due file separatamente. Si
spezzano i contorni delle province in archi (come fa TopoJSON), si semplifica
ogni arco una volta sola e si ricompone tutto da quegli archi. Un arco
condiviso da due province della stessa regione e' un confine di provincia;
tutti gli altri (fra regioni diverse, o sul mare) sono confine di regione.
"""
import json, math, os
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
LARGHEZZA = 1000.0      # unita' del viewBox
TOLLERANZA = 0.30       # semplificazione, nelle stesse unita'
GRIGLIA = 0.02          # arrotondamento per far coincidere i punti condivisi
MIN_AREA = 0.25         # isole piu' piccole di cosi' sparirebbero comunque

# Il file di openpolis ha ancora le province sarde di prima del 2016. Le
# accorpo a quelle di oggi: cosi' i confini interni fra i pezzi accorpati
# spariscono da soli, perche' la classificazione guarda i proprietari.
FUSIONI = {'OT': 'SS', 'OG': 'NU', 'VS': 'SU', 'CI': 'SU'}
NOMI_FUSI = {'SU': 'Sud Sardegna'}

# I dati di Gambero Rosso usano queste sigle per le regioni.
SIGLE_REGIONE = {
    'Trentino-Alto Adige/S\u00fcdtirol': ('trentino-alto-adige', 'Trentino-Alto Adige'),
    "Valle d'Aosta/Vall\u00e9e d'Aoste": ('valle-daosta', "Valle d'Aosta"),
    'Friuli-Venezia Giulia': ('friuli-venezia-giulia', 'Friuli-Venezia Giulia'),
    'Emilia-Romagna': ('emilia-romagna', 'Emilia-Romagna'),
}
def sigla_regione(nome):
    if nome in SIGLE_REGIONE:
        return SIGLE_REGIONE[nome]
    return nome.lower().replace(' ', '-'), nome

def mercatore(lon, lat):
    return math.radians(lon), math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

def dp(punti, tol):
    """Douglas-Peucker, estremi sempre conservati."""
    if len(punti) < 3:
        return punti
    ax, ay = punti[0]; bx, by = punti[-1]
    dx, dy = bx - ax, by - ay
    lung2 = dx * dx + dy * dy
    peggio, idx = -1.0, 0
    for i in range(1, len(punti) - 1):
        px, py = punti[i]
        if lung2 == 0:
            d = (px - ax) ** 2 + (py - ay) ** 2
        else:
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / lung2))
            d = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
        if d > peggio:
            peggio, idx = d, i
    if peggio > tol * tol:
        return dp(punti[:idx + 1], tol)[:-1] + dp(punti[idx:], tol)
    return [punti[0], punti[-1]]

def area(punti):
    a = 0.0
    for i in range(len(punti) - 1):
        a += punti[i][0] * punti[i + 1][1] - punti[i + 1][0] * punti[i][1]
    return abs(a) / 2

# --- lettura e proiezione ------------------------------------------------
prov = json.load(open(os.path.join(BASE, 'provinces.geojson')))['features']
grezzi = []          # (indice provincia, anello di coppie proiettate)
for i, f in enumerate(prov):
    g = f['geometry']
    poligoni = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
    for poly in poligoni:
        for anello in poly:
            grezzi.append((i, [mercatore(x, y) for x, y in anello]))

xs = [p[0] for _, a in grezzi for p in a]
ys = [p[1] for _, a in grezzi for p in a]
minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
scala = LARGHEZZA / (maxx - minx)
ALTEZZA = round((maxy - miny) * scala, 1)

def su_schermo(p):
    return (round((p[0] - minx) * scala / GRIGLIA) * GRIGLIA,
            round((maxy - p[1]) * scala / GRIGLIA) * GRIGLIA)

anelli = []
for i, a in grezzi:
    pts = [su_schermo(p) for p in a]
    puliti = [pts[0]]
    for p in pts[1:]:
        if p != puliti[-1]:
            puliti.append(p)
    if len(puliti) < 4 or area(puliti) < MIN_AREA:
        continue
    if puliti[0] != puliti[-1]:
        puliti.append(puliti[0])
    anelli.append((i, puliti))

# --- chi possiede ogni segmento -----------------------------------------
padroni = defaultdict(set)
for i, a in anelli:
    for k in range(len(a) - 1):
        padroni[frozenset((a[k], a[k + 1])) if a[k] != a[k + 1] else None].add(i)
padroni.pop(None, None)

def chiave(p, q):
    return frozenset((p, q))

# Un punto e' un nodo se i segmenti che vi arrivano non hanno tutti gli stessi
# proprietari, o se non sono esattamente due: li' un arco finisce.
incidenti = defaultdict(list)
for k, own in padroni.items():
    p, q = tuple(k) if len(k) == 2 else (tuple(k)[0], tuple(k)[0])
    incidenti[p].append(frozenset(own)); incidenti[q].append(frozenset(own))
nodi = {p for p, lst in incidenti.items() if len(lst) != 2 or lst[0] != lst[1]}

# --- taglio degli anelli in archi ---------------------------------------
archi = {}          # chiave canonica -> lista di punti semplificata
def registra(punti):
    k = tuple(punti)
    kr = tuple(reversed(punti))
    if k in archi:
        return k, False
    if kr in archi:
        return kr, True
    archi[k] = dp(list(punti), TOLLERANZA)
    return k, False

catene = []         # (indice provincia, [(chiave arco, rovesciato)])
for i, a in anelli:
    tagli = [k for k in range(len(a) - 1) if a[k] in nodi]
    pezzi = []
    if not tagli:
        pezzi.append(list(a))
    else:
        for j in range(len(tagli)):
            s, e = tagli[j], tagli[(j + 1) % len(tagli)]
            if j == len(tagli) - 1:
                pezzo = a[s:-1] + a[:e + 1]
            else:
                pezzo = a[s:e + 1]
            if len(pezzo) > 1:
                pezzi.append(pezzo)
    catene.append((i, [registra(p) for p in pezzi]))

# --- classificazione: confine di provincia o di regione ------------------
regione_di = [f['properties']['reg_name'] for f in prov]
sigla_prov = [FUSIONI.get(f['properties']['prov_acr'], f['properties']['prov_acr'])
              for f in prov]
classe = {}
for k in archi:
    own = padroni.get(chiave(k[0], k[1]), set())
    province_vere = {sigla_prov[i] for i in own}
    regioni = {regione_di[i] for i in own}
    if len(province_vere) == 1 and len(own) > 1:
        classe[k] = 'niente'          # confine sparito con l'accorpamento
    elif len(province_vere) == 2 and len(regioni) == 1:
        classe[k] = 'prov'
    else:
        classe[k] = 'reg'

# --- uscita --------------------------------------------------------------
def d_di(punti, chiudi):
    out = ['M%g %g' % punti[0]]
    for p in punti[1:]:
        out.append('L%g %g' % p)
    if chiudi:
        out.append('Z')
    return ''.join(out)

per_provincia = defaultdict(list)
for i, pezzi in catene:
    pts = []
    for k, rov in pezzi:
        seg = archi[k][::-1] if rov else archi[k]
        pts.extend(seg if not pts else seg[1:])
    if len(pts) > 2:
        per_provincia[sigla_prov[i]].append(d_di(pts, True))

nomi, regioni_di_sigla = {}, {}
for i, f in enumerate(prov):
    s_ = sigla_prov[i]
    nomi.setdefault(s_, NOMI_FUSI.get(s_, f['properties']['prov_name']))
    regioni_di_sigla.setdefault(s_, f['properties']['reg_name'])

province_out = []
for s_, pezzi in per_provincia.items():
    sig, nome_reg = sigla_regione(regioni_di_sigla[s_])
    province_out.append({'a': s_, 'n': nomi[s_], 'r': sig, 'rn': nome_reg,
                         'd': ''.join(pezzi)})
province_out.sort(key=lambda x: x['a'])

confini_regione = ''.join(d_di(archi[k], False) for k in archi if classe[k] == 'reg')
confini_prov = ''.join(d_di(archi[k], False) for k in archi if classe[k] == 'prov')

mappa = {'w': LARGHEZZA, 'h': ALTEZZA,
         'proj': {'minx': minx, 'maxy': maxy, 'k': scala},
         'province': province_out, 'regioni': confini_regione,
         'confini_provincia': confini_prov}
json.dump(mappa, open(os.path.join(BASE, 'mappa.json'), 'w'), separators=(',', ':'))
print('province %d, altezza %s, file %d KB'
      % (len(province_out), ALTEZZA,
         os.path.getsize(os.path.join(BASE, 'mappa.json')) // 1024))
