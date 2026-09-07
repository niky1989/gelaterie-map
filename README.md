# Mappa Gelaterie d'Italia 2027

Sito privato con la mappa delle gelaterie premiate dalla guida *Gelaterie
d'Italia 2027* del Gambero Rosso. Gira su Docker, non chiama niente
all'esterno: dati e geometria della mappa stanno dentro l'immagine.

## Come si mette in produzione

In Portainer: **Stacks → Add stack → Repository**, si incolla l'indirizzo di
questo repository e si preme *Deploy*. Da li' in poi ogni aggiornamento e' il
pulsante **"Pull and redeploy"**: non c'e' piu' niente da incollare.

Poi `http://<indirizzo-del-server>:8092`. Se la 8092 e' occupata si cambia il
numero a sinistra in `ports:`.

**Non spuntare "Re-pull image"**: serve agli stack che usano un'immagine presa
da un registro, qui l'immagine si costruisce da questi file. Non porta niente
e butta la cache, allungando il deploy.

Essendo il sito fatto di soli file statici, lo stesso repository si puo'
pubblicare anche con **GitHub Pages** senza cambiare nulla: i percorsi sono
relativi e funzionano anche in sottocartella.

### La via di scorta

`docker-compose.incorporato.yml` contiene tutto il sito compresso e in base64,
da incollare a mano nell'editor di Portainer. Serve solo se la strada di
GitHub non e' percorribile (per esempio un server che non arriva a internet).
Si rigenera con `python3 build.py`. E' il metodo usato fino al 7 settembre
2026: funziona, ma ogni consegna sono 260 KB di testo da incollare, ed e'
lento proprio per quello.

## Com'e' fatto

```
docker-compose.yml       lo stack, otto righe
Dockerfile               due righe: nginx piu' la copia di site/
nginx.conf               solo per accendere la compressione
site/index.html          tutto il sito: HTML, CSS e JavaScript, senza librerie
site/data/gelaterie.json 580 schede: nome, coni, coordinate, indirizzo, premio
site/data/mappa.json     confini di regioni e province, gia' proiettati in SVG
data/                    gli script che hanno prodotto i due JSON
build.py                 la via di scorta col base64 (vedi sopra)
```

`data/provinces.geojson` non sta nel repository: pesa 5 MB e serve solo a
rigenerare `mappa.json`. Si riprende con il comando scritto in `.gitignore`.

La mappa e' **SVG disegnato a mano**, non un servizio di mappe: niente strade,
niente etichette, niente tessere da scaricare. Si sposta col trascinamento, si
ingrandisce con la rotellina o con due dita.

## I dati

Presi dalla pagina <https://www.gamberorosso.it/guide/gelaterie-ditalia/2027/>
il 5 settembre 2026.

- **580 schede.** La pagina in cima dichiara 581: i filtri per regione ne
  contano 580 in totale, quindi manca una scheda anche a loro.
- **Punteggio**: 77 tre coni, 321 due coni, 166 un cono, 16 senza punteggio
  (segnalate in guida ma senza coni assegnati).
- **Coordinate**: 529 arrivano dal Gambero Rosso. Le altre 51 non le
  pubblicavano; sono state ricavate dall'indirizzo con Nominatim
  (OpenStreetMap). Di queste, 20 sono finite sul centro del comune invece che
  sul civico: nella scheda compare l'avviso *"posizione approssimata"*.

### Se un domani esce la guida 2028

Il recupero **non e' automatizzabile con un semplice script**: il sito e'
protetto da Cloudflare e risponde 403 a `curl`. I dati sono stati raccolti
dentro un browser vero, pagina per pagina (`?_paged=1..30`) piu' una visita a
ognuna delle 580 schede per le coordinate. Il risultato e' congelato in
`data/raw.txt`; da li' in poi tutto e' ripetibile:

```bash
cd data
python3 build_data.py     # ripara i caratteri, geocodifica, scrive gelaterie.json
python3 build_mappa.py    # ricostruisce mappa.json dai confini ISTAT
cd .. && python3 build.py # rigenera docker-compose.yml
```

`geocode_cache.json` evita di ripetere le chiamate a Nominatim: cancellarlo
solo se serve davvero rifarle (una richiesta al secondo, per educazione).

## La mappa, nel dettaglio

Confini da [openpolis/geojson-italy](https://github.com/openpolis/geojson-italy)
(fonte ISTAT).

Regioni e province **devono combaciare al pixel** anche a forte ingrandimento.
Semplificare i due file separatamente avrebbe prodotto due linee sfalsate lungo
gli stessi confini. Per questo `build_mappa.py` lavora come TopoJSON: spezza i
contorni delle province in archi, semplifica ogni arco **una volta sola**, e
ricompone tutto da quegli archi. Un arco condiviso da due province della stessa
regione e' un confine di provincia (linea tenue); tutti gli altri sono confine
di regione o costa (linea marcata).

Il file di openpolis ha ancora le province sarde di prima del 2016. Sono
accorpate a quelle di oggi (OT→SS, OG→NU, VS e CI→SU): i confini interni
spariscono da soli, perche' la classificazione guarda chi possiede l'arco.
Risultato: 107 province, quelle attuali.

## Cose che non sono state provate

- **L'immagine Docker non e' mai stata costruita qui**: su questa macchina non
  c'e' Docker. Lo yml e' pero' verificato per davvero — `build.py` esegue i
  comandi di ricostruzione dei quattro file e confronta i byte con gli
  originali, e i comandi che scrivono la configurazione di nginx sono stati
  eseguiti per controllare il file prodotto. La build su Portainer resta
  l'ultima prova.
- Il sito e' stato provato su Chromium (schermo largo e telefono simulato).
  Su Safari no.
