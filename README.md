# Fast-n-Fourgon : moteur de consolidation des livraisons

[![CI](https://github.com/TheKingL/fast-n-fourgon/actions/workflows/ci.yml/badge.svg)](https://github.com/TheKingL/fast-n-fourgon/actions/workflows/ci.yml)

Le moteur regroupe les livraisons de chaque couple fournisseur × usine dans le moins de camions possible :
1 à 3 jours fixes de livraison par semaine (un couple à 2 ou 3 jours livre au moins une semaine sur tous ses jours ;
les premiers besoins peuvent partir dans la semaine qui précède le planning), au plus 24,5 t et 110,4 m³ par camion, jamais de retard,
au plus 7 jours d'avance, et une charge équilibrée sur les jours de la semaine pour chaque usine.

## Installation

```powershell
git clone git@github.com:TheKingL/fast-n-fourgon.git
cd fast-n-fourgon
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

`requirements-dev.txt` installe l'application (`requirements.txt` : moteur et dashboard), plus les outils de tests, de
lint et des notebooks. Pour seulement faire tourner l'application, `pip install -r requirements.txt` suffit : c'est ce
qu'installent l'image Docker et `lancer_dashboard.bat`.

## Lancement

Depuis la racine du dépôt :

```powershell
python main.py                          # calcule, écrit les sorties dans data/gold/ et affiche le résumé
python main.py 254                      # idem, en détaillant le camion n° 254
python main.py --schedule planning.csv  # nettoie et consolide un autre schedule brut
```

Sans `--schedule`, le moteur lit les fichiers déjà préparés par les notebooks (`data/silver`, `data/baseline`).
Avec `--schedule`, il fait tout le chemin depuis le fichier brut : nettoyage, baseline, consolidation.
Sur `data/bronze/released_schedule.csv`, les deux donnent exactement les mêmes résultats.

Fichiers écrits dans `data/gold/` :

| Fichier | Contenu |
|---|---|
| `sortie1_profils.csv` | le profil de livraison (jours fixes) à appliquer pour chaque couple |
| `sortie2_camions.csv` | les materials chargés dans chaque camion |
| `bilan.csv` | les économies de chaque étape du moteur par rapport à la baseline |
| `alertes.csv` | les cas où une règle ne peut pas être respectée (2 camions un même jour pour un couple, camion réservé hors jours fixes), avec leur cause et l'action à mener |

## Dashboard (Streamlit)

Double-clic sur `lancer_dashboard.bat`, ou depuis la racine du dépôt :

```powershell
streamlit run frontend/app.py
```

Trois pages :

- **Analyse** : on choisit un schedule (celui du projet ou un CSV importé), on lance le moteur, on voit les
  résultats (coût, économie, camions, charge des usines, sorties 1, 2 et 3, contraintes) et l'écart avec le
  dernier run ; « Exporter l'analyse » télécharge les trois sorties et la synthèse, en classeur Excel (une feuille
  par sortie) ou en CSV zippés (format Excel français ou format `data/gold`) ; « Enregistrer dans
  l'historique » garde le run ;
- **Historique** : évolution des métriques run après run (avec un mode base 100), comparaison de deux runs,
  journal, fichiers de chaque run ;
- **Mapping** : table de correspondance fournisseur -> distance, pour compléter les distances manquantes (sinon
  chiffrées au tarif « > 650 km »). Les saisies sont gardées dans `data/mapping/distances_saisies.csv` (local à
  chaque poste, ignoré par git) sans modifier `data/bronze/distances.csv`, et le moteur les utilise à l'analyse
  suivante (`main.py` compris) ; le fichier des distances complété peut être téléchargé.

L'onglet Qualité des données liste aussi, fournisseur par fournisseur, les lignes sans poids ou sans volume
(impossibles à consolider), pour savoir quels fournisseurs renseignent mal leurs envois.

Le moteur tourne sur le schedule choisi : nettoyage (milestone 1), baseline (milestone 2), puis consolidation.
Un CSV importé doit avoir les colonnes de `data/bronze/released_schedule.csv`. Le résultat d'un même fichier est
gardé en cache tant que le serveur tourne. Les runs sont gardés dans `data/historique/` (local à chaque poste,
ignoré par git).

## Docker

Le dashboard tourne aussi dans un conteneur, sans installer Python : il suffit de Docker (Docker Desktop sous Windows et
macOS). Le CI publie l'image sur `ghcr.io/thekingl/fast-n-fourgon` à chaque push sur `main`, pour PC (amd64) et Mac
Apple Silicon (arm64).

```bash
docker run -d --name fast-n-fourgon -p 8501:8501 -v fast-n-fourgon-historique:/app/data/historique \n  -v fast-n-fourgon-mapping:/app/data/mapping ghcr.io/thekingl/fast-n-fourgon:latest
```

Le dashboard est alors sur <http://localhost:8501> ; `docker stop fast-n-fourgon` l'arrête, `docker start fast-n-fourgon`
le relance. Depuis le dépôt, `docker compose up -d` fait la même chose (`docker compose up -d --build` pour construire
l'image depuis les sources, `docker compose down` pour l'arrêter).

- **Historique** : les runs enregistrés vont dans le volume `fast-n-fourgon-historique` (monté sur
  `/app/data/historique`), qui survit à l'arrêt et à la suppression du conteneur.
- **Mapping** : les distances saisies vont dans le volume `fast-n-fourgon-mapping` (monté sur `/app/data/mapping`).
- **Exports** : « Exporter l'analyse » et les boutons « Télécharger » passent par le navigateur, comme en local.
- **Moteur en ligne de commande** : les CSV de sortie arrivent dans le dossier monté sur `/app/data/gold` (ici
  `sorties/`, à créer avant ; sous Linux, ajouter `--user "$(id -u):$(id -g)"` s'il n'appartient pas à l'uid 1000) :

  ```bash
  docker run --rm -v "${PWD}/sorties:/app/data/gold" ghcr.io/thekingl/fast-n-fourgon python main.py
  docker run --rm -v "${PWD}/sorties:/app/data/gold" -v "${PWD}:/travail" ghcr.io/thekingl/fast-n-fourgon python main.py --schedule /travail/planning.csv
  ```

- **Sans accès à ghcr.io** : chaque [release](https://github.com/TheKingL/fast-n-fourgon/releases) contient l'image en
  archive, à charger avec `docker load -i fast-n-fourgon-<version>-linux-amd64.tar.gz` (`arm64` pour un Mac Apple
  Silicon), puis la commande `docker run` ci-dessus avec le tag `<version>` à la place de `latest`.

L'image (`Dockerfile`) part de `python:3.12-slim` en deux étages : les dépendances de `requirements.txt` sont installées
dans un venv allégé (sans pip, ni les tests embarqués des librairies, ni les modules de pyarrow inutilisés), puis
copiées avec le code. Elle pèse environ 160 Mo à télécharger (555 Mo sur disque), tourne avec un utilisateur sans droits
root (uid 1000) et à l'heure de Paris (`-e TZ=...` pour changer), et Docker surveille l'état du dashboard
(`HEALTHCHECK`).

## Tests et lint

Depuis la racine du dépôt, avec `requirements-dev.txt` installé :

```powershell
pytest          # tests du moteur (dossier tests/), quelques secondes
ruff check .    # lint du code Python (configuration dans pyproject.toml)
```

Les tests sont ceux du notebook `data_analysis/milestone4.ipynb` (lancés là-bas avec ipytest). Les notebooks ne sont
pas lintés.

## CI et releases

Le workflow `.github/workflows/ci.yml` (GitHub Actions) tourne à chaque push sur `main` :

1. **lint** : `ruff check .` et hadolint sur le `Dockerfile` ;
2. **tests** : `pytest` ;
3. **image** : construction de l'image, puis un smoke test avant toute publication. Le moteur tourne dans le conteneur,
   `tests/smoke_image.py` déroule le dashboard (analyse du schedule du projet, exports, historique) et le serveur doit
   répondre. L'image est ensuite publiée pour amd64 et arm64 sur
   [ghcr.io/thekingl/fast-n-fourgon](https://github.com/TheKingL/fast-n-fourgon/pkgs/container/fast-n-fourgon), avec les
   tags `latest`, `v1.0.<numéro du run>` et `sha-<commit>` ;
4. **release** : une [release](https://github.com/TheKingL/fast-n-fourgon/releases) `v1.0.<numéro du run>` avec
   l'image en archive pour chaque architecture (`docker load`) et leurs empreintes (`SHA256SUMS`).

Sur une pull request vers `main`, seuls le lint et les tests tournent.

## Structure

```
main.py            flux d'exécution : executer() -> exporter() -> afficher()
backend/
  config.py        chemins des fichiers et paramètres (capacités, fenêtre, seuil de lissage...)
  typage.py        alias de types : Profil, Couple, Choix, Charge...
  formatage.py     mise en forme des nombres (format français)
  couts.py         grille tarifaire, distances, coût d'un camion
  nettoyage.py     milestone 1 : schedule brut -> lignes saines + quarantaine (flags)
  baseline.py      milestone 2 : camions de la situation actuelle (la référence des économies)
  donnees.py       entrée du moteur : besoins à consolider, camions réservés, baseline, horizon (charger())
  charge.py        camions reçus par jour et par usine, tolérance de lissage
  contraintes.py   vérification des contraintes C1 à C11 et cohérence du planning
  jours_fixes.py   bloc 1 : consolidation de chaque couple pour chaque profil (classe Scenarios)
  lissage.py       blocs 2 et 3 : équilibre des usines et lissage
  report.py        bloc 4 : report sur le jour fixe suivant, planning final
  sorties.py       bilan, sortie 1, sortie 2, sortie 3 (saving par couple), export CSV
  resultats.py     dataclass Resultats, retournée par main.executer()
frontend/          dashboard Streamlit
  app.py           point d'entrée et navigation
  vues/            les deux pages : analyse.py, historique.py
  moteur.py        lecture du schedule, appel du moteur, métriques d'un run
  historique.py    historisation des runs (data/historique/)
  comparaison.py   comparaison des métriques de deux runs
  export.py        export des 3 sorties : classeur Excel ou CSV zippés
  graphiques.py    graphiques Plotly
  composants.py    bandeau, titres de section, pastilles
  style.py         palette et feuille de style
.streamlit/        thème du dashboard
lancer_dashboard.bat  lancement du dashboard
data/              bronze (brut), silver (nettoyé), baseline, gold (sorties)
data_analysis/     notebooks des milestones 1 à 4 (milestone4 = tests du moteur)
tests/             les tests du milestone 4 (pytest) et le smoke test de l'image Docker (smoke_image.py)
requirements.txt   dépendances de l'application ; requirements-dev.txt : tests, lint et notebooks en plus
pyproject.toml     configuration de pytest et de ruff
Dockerfile         image Docker du dashboard ; .dockerignore : ce qui entre dans l'image
compose.yaml       lancement de l'image avec docker compose (port 8501, volume de l'historique)
.github/           CI (workflows/ci.yml) et modèle des notes de release
```

Toutes les fonctions sont typées et documentées : leur docstring décrit les paramètres et le résultat.

## Utilisation depuis un front end ou des tests

`main.executer()` fait tout le calcul sans rien écrire ni afficher, et retourne un objet `Resultats` :

```python
import main

r = main.executer()        # données du projet ; environ 8 secondes : à appeler une fois puis à réutiliser
r = main.executer(df)      # un schedule brut (DataFrame au format de released_schedule.csv)
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
