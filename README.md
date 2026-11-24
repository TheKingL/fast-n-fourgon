# Moteur de consolidation des livraisons

Le moteur regroupe les livraisons de chaque couple fournisseur × usine dans le moins de camions possible :
1 à 3 jours fixes de livraison par semaine (un couple à 2 ou 3 jours livre au moins une semaine sur tous ses jours ;
les premiers besoins peuvent partir dans la semaine qui précède le planning), au plus 24,5 t et 110,4 m³ par camion, jamais de retard,
au plus 7 jours d'avance, et une charge équilibrée sur les jours de la semaine pour chaque usine.

## Installation

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Lancement

Depuis la racine du dépôt :

```powershell
python main.py          # calcule, écrit les sorties dans data/gold/ et affiche le résumé
python main.py 254      # idem, en détaillant le camion n° 254
```

Fichiers écrits dans `data/gold/` :

| Fichier | Contenu |
|---|---|
| `sortie1_profils.csv` | le profil de livraison (jours fixes) à appliquer pour chaque couple |
| `sortie2_camions.csv` | les materials chargés dans chaque camion |
| `bilan.csv` | les économies de chaque étape du moteur par rapport à la baseline |
| `alertes.csv` | les cas où une règle ne peut pas être respectée (2 camions un même jour pour un couple, camion réservé hors jours fixes), avec leur cause et l'action à mener |

## Structure

```
main.py            flux d'exécution : executer() -> exporter() -> afficher()
backend/
  config.py        chemins des fichiers et paramètres (capacités, fenêtre, seuil de lissage...)
  typage.py        alias de types : Profil, Couple, Choix, Charge...
  formatage.py     mise en forme des nombres (format français)
  couts.py         grille tarifaire, distances, coût d'un camion
  donnees.py       besoins à consolider, camions réservés, baseline, horizon du planning
  charge.py        camions reçus par jour et par usine, tolérance de lissage
  contraintes.py   vérification des contraintes C1 à C11 et cohérence du planning
  jours_fixes.py   bloc 1 : consolidation de chaque couple pour chaque profil (classe Scenarios)
  lissage.py       blocs 2 et 3 : équilibre des usines et lissage
  report.py        bloc 4 : report sur le jour fixe suivant, planning final
  sorties.py       bilan, sortie 1, sortie 2, export CSV
  resultats.py     dataclass Resultats, retournée par main.executer()
data/              bronze (brut), silver (nettoyé), baseline, gold (sorties)
data_analysis/     notebooks des milestones 1 à 4 (milestone4 = tests du moteur)
```

Toutes les fonctions sont typées et documentées : leur docstring décrit les paramètres et le résultat.

## Utilisation depuis un front end ou des tests

`main.executer()` fait tout le calcul sans rien écrire ni afficher, et retourne un objet `Resultats` :

```python
import main

r = main.executer()        # environ 8 secondes : à appeler une fois puis à réutiliser
r.planning_complet         # une ligne par camion (date, usine, fournisseur, poids, coût...)
r.lignes_complet           # une ligne par ligne de besoin livrée (camion, date de livraison, avance)
r.sortie1, r.sortie2       # les deux sorties
r.bilan, r.par_usine       # économies totales et par usine
r.controle_contraintes     # nombre de violations de chaque contrainte
```

Les fonctions du backend s'appellent aussi directement :

```python
from backend.couts import cout_transport
from backend.sorties import detail_camion

cout_transport(1000, 300)            # 335.34 € : 1 000 kg à 300 km
resume, table = detail_camion(r.sortie2, 254)
```

Le script ou le notebook doit être lancé depuis la racine du dépôt ; depuis `data_analysis/`, ajouter
`sys.path.insert(0, "..")` avant les imports.
