#!/usr/bin/env python3
"""
Genera docker-compose.incorporato.yml, con dentro tutto il sito in base64.

Via di scorta. Dal 7 settembre 2026 il sito si distribuisce da GitHub, e
Portainer si tira giu' i file da solo (vedi README): questo file serve solo se
quella strada non e' percorribile, per esempio se il server non arriva a
GitHub. Allora torna buono il vecchio metodo: tutto il sito compresso e in
base64 dentro al compose, da incollare a mano nell'editor di Portainer.

Uso:
    python3 build.py
"""

import base64
import gzip
import io
import os
import subprocess
import sys
import tempfile

QUI = os.path.dirname(os.path.abspath(__file__))
SITO = os.path.join(QUI, "site")
USCITA = os.path.join(QUI, "docker-compose.incorporato.yml")

# Due limiti diversi, e quello che conta non e' il primo.
#
# MAX_RIGA: Docker rifiuta le righe oltre i 65535 caratteri. In piu' l'editor
# di Portainer, dove lo yml va incollato, si impianta a colorare righe
# lunghissime. Meglio molte righe corte.
#
# MAX_RUN: Linux non accetta un singolo argomento di exec piu' lungo di
# 128 KiB (MAX_ARG_STRLEN). Un "RUN comando" e' un argomento solo, quello di
# /bin/sh -c: spezzarlo su piu' righe con la barra rovescia NON aiuta, perche'
# resta una stringa sola. Con mappa.json (208 KB in base64) la build falliva
# proprio li', mentre i file piu' piccoli passavano.
#
# Ma nemmeno spezzare troppo va bene: ogni RUN fa avviare un container,
# fotografare il filesystem e sigillare uno strato, e su un disco lento sono
# secondi. Con tredici RUN il deploy era piu' lento di Speaker Detect, che di
# roba da installare ne ha mille volte tanta ma sta in due strati. Quindi si
# riempie ogni comando fin quasi al limite, e i file piccoli viaggiano
# insieme a quelli grandi.
MAX_RIGA = 8000
MAX_RUN = 110000

# (file nel progetto, percorso dentro l'immagine, file temporaneo)
#
# L'ordine conta: Docker riusa la cache fino al primo blocco che cambia e
# ricostruisce tutto quello che viene dopo. Quindi prima i file che non
# cambiano quasi mai (i confini d'Italia non si spostano), per ultimo
# index.html, che si tocca a ogni giro. Al contrario, come era prima, una
# virgola nell'HTML mandava all'aria anche i 208 KB della mappa.
FILE = [
    ("data/mappa.json",     "/usr/share/nginx/html/data/mappa.json",      "/tmp/1.b64"),
    ("data/gelaterie.json", "/usr/share/nginx/html/data/gelaterie.json",  "/tmp/2.b64"),
    ("favicon.svg",         "/usr/share/nginx/html/favicon.svg",          "/tmp/3.b64"),
    ("index.html",          "/usr/share/nginx/html/index.html",           "/tmp/4.b64"),
]


def comprimi(dati):
    """gzip con data fissa: due build uguali devono dare lo stesso testo."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as f:
        f.write(dati)
    return buf.getvalue()


def pezzi_di(b64):
    """Il base64 tagliato in righe corte, digeribili dall'editor di Portainer."""
    return [b64[i:i + MAX_RIGA] for i in range(0, len(b64), MAX_RIGA)]


def istruzioni(elenco):
    """Da (nome, base64, destinazione, temporaneo) alle istruzioni RUN.

    I comandi si riempiono fino a MAX_RUN e i file si accodano l'uno all'altro
    nello stesso RUN se ci stanno: meno strati, deploy piu' svelto.
    """
    # ogni voce e' un pezzo di comando, in ordine
    passi = []
    for nome, b64, dest, tmp in elenco:
        for i, p in enumerate(pezzi_di(b64)):
            passi.append(('echo "%s" %s %s' % (p, '>' if i == 0 else '>>', tmp), nome))
        # Il file arriva dallo standard input e non come argomento: il base64 di
        # Linux accetta entrambi, quello di macOS solo lo standard input, e la
        # verifica qui sotto gira anche sul Mac dove il progetto si sviluppa.
        passi.append(('base64 -d < %s | gunzip > %s && rm %s' % (tmp, dest, tmp), nome))

    gruppi, corrente, lung = [], [], 0
    for cmd, nome in passi:
        costo = len(cmd) + 8
        if corrente and lung + costo > MAX_RUN:
            gruppi.append(corrente); corrente, lung = [], 0
        corrente.append((cmd, nome)); lung += costo
    if corrente:
        gruppi.append(corrente)

    testo = []
    for gruppo in gruppi:
        nomi = []
        for _, n in gruppo:
            if n not in nomi:
                nomi.append(n)
        righe = ['# --- %s ---' % ', '.join(nomi)]
        righe.append('RUN ' + gruppo[0][0] + (' \\' if len(gruppo) > 1 else ''))
        for i, (cmd, _) in enumerate(gruppo[1:], 1):
            coda = ' \\' if i < len(gruppo) - 1 else ''
            righe.append('    && ' + cmd + coda)
        testo.append("\n        ".join(righe))
    return "\n\n        ".join(testo), len(gruppi)


def verifica(b64, originale, temporaneo):
    """Esegue davvero i comandi della build: che il giro torni, non che sembri."""
    with tempfile.TemporaryDirectory() as d:
        tmp = os.path.join(d, "b64")
        out = os.path.join(d, "out")
        parti = pezzi_di(b64)
        cmd = 'echo "%s" > "%s"' % (parti[0], tmp)
        for p in parti[1:]:
            cmd += ' && echo "%s" >> "%s"' % (p, tmp)
        r = subprocess.run(["/bin/sh", "-c", cmd], capture_output=True)
        if r.returncode != 0:
            raise SystemExit("ricostruzione fallita: " + r.stderr.decode())
        r = subprocess.run(["/bin/sh", "-c",
                            'base64 -d < "%s" | gunzip > "%s"' % (tmp, out)],
                           capture_output=True)
        if r.returncode != 0:
            raise SystemExit("decodifica fallita: " + r.stderr.decode())
        if open(out, "rb").read() != originale:
            raise SystemExit("il file ricostruito e' diverso dall'originale")


def genera():
    elenco, totale_originale, totale_b64 = [], 0, 0
    for nome, destinazione, temporaneo in FILE:
        dati = open(os.path.join(SITO, nome), "rb").read()
        b64 = base64.b64encode(comprimi(dati)).decode()
        verifica(b64, dati, temporaneo)
        elenco.append((nome, b64, destinazione, temporaneo))
        totale_originale += len(dati)
        totale_b64 += len(b64)
        print("%-22s %7d byte -> %6d in base64" % (nome, len(dati), len(b64)))
    corpo, nrun = istruzioni(elenco)
    corpo = "        " + corpo
    print("%-22s %7d byte -> %6d  in %d istruzioni RUN"
          % ("totale", totale_originale, totale_b64, nrun))
    return '''version: "3.8"

# Mappa delle gelaterie premiate dalla guida Gelaterie d'Italia 2027 del
# Gambero Rosso. Sito statico, nessuna chiamata verso l'esterno: i dati e la
# geometria della mappa sono dentro l'immagine.
#
# Generato da build.py: non modificare a mano, si riscrive tutto.

services:
  gelaterie:
    build:
      context: .
      dockerfile_inline: |
        FROM nginx:alpine

        # Compressione: i due JSON pesano mezzo mega in chiaro, un centinaio
        # di kilobyte compressi. Su rete locale non cambia la vita, ma il
        # primo caricamento da telefono si', e costa poche righe.
        # Niente printf con le sequenze tipo barra-rovescia-n: dentro un
        # Dockerfile se le prende il parser prima che le veda la shell.
        # E $$ perche' altrimenti compose sostituirebbe $uri con il vuoto.
        RUN C=/etc/nginx/conf.d/default.conf \\
            && echo 'server {'                                      >  $$C \\
            && echo '  listen 80;'                                  >> $$C \\
            && echo '  root /usr/share/nginx/html;'                 >> $$C \\
            && echo '  gzip on;'                                    >> $$C \\
            && echo '  gzip_min_length 1024;'                       >> $$C \\
            && echo '  gzip_types application/json image/svg+xml;'  >> $$C \\
            && echo '  location / { try_files $$uri $$uri/ =404; }' >> $$C \\
            && echo '}'                                             >> $$C \\
            && mkdir -p /usr/share/nginx/html/data

{corpo}

    container_name: mappa-gelaterie
    ports:
      # Cambiare solo il numero a sinistra se la 8092 e' gia' occupata.
      - "8092:80"
    restart: unless-stopped
'''.replace("{corpo}", corpo)


if __name__ == "__main__":
    testo = genera()
    troppo_lunga = [i + 1 for i, r in enumerate(testo.splitlines()) if len(r) > 65535]
    if troppo_lunga:
        raise SystemExit("righe oltre il limite di Docker: %s" % troppo_lunga)
    open(USCITA, "w").write(testo)
    print("\nscritto %s (%d KB)" % (USCITA, os.path.getsize(USCITA) // 1024))
