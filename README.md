# RadarFlat

**Tutti gli appartamenti di Praga su una pagina.** Un robot raccoglie tre volte al giorno gli annunci di appartamenti in affitto e in vendita a Praga, toglie i doppioni (lo stesso appartamento pubblicato su più portali) e li mostra su un sito Jekyll con foto, mappa, filtri e scheda dettagliata.

Sito: <https://radarflat.pacificit.solutions> — italiano, inglese e ceco.

## Cosa fa il sito

- filtri per prezzo, superficie, disposizione (1+kk … 6+), quartiere o distretto Praha 1–10, dotazioni (ascensore, balcone, terrazza, cantina, parcheggio, arredato, animali, senza agenzia)
- solo nuovi (48 ore), solo ribassi di prezzo, solo sotto la media di zona
- prezzo al m² e confronto con la mediana del quartiere
- storico prezzo di ogni annuncio, data di prima apparizione
- mappa con prezzi (Leaflet + OpenStreetMap), filtro "solo l'area visibile"
- scheda con tutte le foto, dettagli, descrizione originale, link all'annuncio e agli stessi appartamenti su altri siti
- filtri condivisibili via URL

## Fonti

| Sito | Metodo | Note |
|---|---|---|
| Bezrealitky.cz | dati Next.js delle pagine pubbliche `/vypis/…` e delle schede | privati senza agenzia; l'API GraphQL è vietata dal robots.txt e non viene usata |
| Reality.iDNES.cz | HTML delle pagine di ricerca e delle schede | |
| RealityMix.cz | HTML delle pagine di ricerca e delle schede | |
| Sreality.cz | API JSON della ricerca | **spento**: il robots.txt di Sreality vieta tutti i crawler tranne i motori di ricerca |

Il robot rispetta `robots.txt`, si identifica come `RadarFlatBot`, aspetta 3–6 secondi tra una richiesta e l'altra sullo stesso sito e si ferma su un sito appena riceve un blocco. Le foto **non vengono copiate**: sono mostrate dal sito originale e ogni scheda porta all'annuncio.

Per accendere Sreality comunque (decisione tua): in `config/sources.yaml` metti `enabled: true` e `respect_robots_txt: false` sotto `sreality`.

## Uso

```bash
pip install -r requirements.txt
python -m radarflat crawl                          # tutte le fonti attive
python -m radarflat crawl --sources idnes --details 20
python -m radarflat publish                        # rigenera site/data da state/
python -m pytest -q
```

## Automatico (GitHub Actions)

`.github/workflows/crawl.yml` gira alle 04:17, 11:17 e 17:17 UTC (o a mano da **Actions → Crawl & publish → Run workflow**): crawl, salva `state/` e `site/data/` nel repo, costruisce il sito Jekyll e lo pubblica su GitHub Pages.

Impostazioni una tantum del repository:
1. **Settings → Pages → Build and deployment → Source: GitHub Actions**
2. **Settings → Pages → Custom domain:** `radarflat.pacificit.solutions`, poi **Enforce HTTPS** quando il certificato è pronto
3. DNS su Cloudflare: `CNAME radarflat → anomaly73bit.github.io`

## Struttura

```
radarflat/
  sources/        un adattatore per sito (bezrealitky, idnes, realitymix, sreality)
  geo.py          quartieri di Praga → distretti Praha 1–10, lettura indirizzi
  model.py        record normalizzato e conversioni
  pipeline.py     crawl → stato → schede → doppioni → JSON per il sito
config/sources.yaml   fonti attive, pause, schede per giro
state/                tutti gli annunci attivi con storico prezzi (listings.jsonl), log dei giri
site/                 sito Jekyll (layout, pagine it/en/cs, assets, data/*.json generati)
```

`site/data/listings.json` è l'elenco compatto per filtri e mappa; `site/data/d/xx.json` sono le schede complete divise in 256 file.
