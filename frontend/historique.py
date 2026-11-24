"""Historisation des runs, en fichiers CSV plats dans ``data/historique/`` :

- ``runs.csv`` : une ligne par run (identifiant, date, source, période planifiée, lignes, coût, économie, camions,
  durée) ;
- ``metriques.csv`` : une ligne par (run, catégorie, métrique, valeur) ;
- ``runs/<run_id>/`` : le schedule d'entrée et les sorties du run (sorties 1, 2 et 3, bilan).

Pour passer à une base de données (SQLite, Postgres...), seul ce module change.
"""
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Final

import pandas as pd

from backend.config import DATA
from backend.resultats import Resultats
from backend.sorties import construire_sortie3

from .moteur import Metriques, periode

DOSSIER: Final[Path] = DATA / "historique"
"""Dossier de l'historique."""
RUNS: Final[Path] = DOSSIER / "runs.csv"
"""Index des runs."""
METRIQUES: Final[Path] = DOSSIER / "metriques.csv"
"""Métriques de tous les runs, en format long."""
FICHIERS: Final[Path] = DOSSIER / "runs"
"""Un sous-dossier par run, avec son schedule et ses sorties."""

COLONNES_RUNS: Final[list[str]] = ["run_id", "horodatage", "source", "debut", "fin", "semaines", "lignes", "camions",
                                   "cout_total", "economie_pct", "duree_s", "statut"]
"""Colonnes de ``runs.csv``."""
COLONNES_METRIQUES: Final[list[str]] = ["run_id", "horodatage", "categorie", "metrique", "valeur"]
"""Colonnes de ``metriques.csv``."""
FICHIERS_RUN: Final[dict[str, str]] = {"schedule.csv": "Schedule d'entrée", "sortie1_profils.csv": "Sortie 1 : profils",
                                       "sortie2_camions.csv": "Sortie 2 : camions",
                                       "sortie3_savings.csv": "Sortie 3 : savings par couple",
                                       "bilan.csv": "Bilan des économies"}
"""Fichiers gardés pour chaque run : nom -> libellé."""


def enregistrer_run(source: str, schedule: pd.DataFrame, r: Resultats, metriques: Metriques, duree_s: float) -> str:
    """Ajoute un run à l'historique.

    Args:
        source: nom du fichier schedule.
        schedule: schedule d'entrée.
        r: résultats du moteur.
        metriques: métriques du run (voir ``moteur.toutes_metriques``).
        duree_s: durée du calcul, en secondes.

    Returns:
        L'identifiant du run (``AAAAMMJJ-HHMMSS-xxxx``).
    """
    FICHIERS.mkdir(parents=True, exist_ok=True)
    maintenant = datetime.now()
    run_id = maintenant.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    horodatage = maintenant.isoformat(timespec="seconds")

    debut, fin, semaines = periode(r)
    ligne = pd.DataFrame([{
        "run_id": run_id, "horodatage": horodatage, "source": source, "debut": f"{debut:%Y-%m-%d}",
        "fin": f"{fin:%Y-%m-%d}", "semaines": semaines, "lignes": len(schedule),
        "camions": len(r.planning_complet), "cout_total": metriques["Coût"]["coût total (€)"],
        "economie_pct": metriques["Coût"]["économie vs baseline (%)"], "duree_s": round(duree_s, 1), "statut": "ok",
    }], columns=COLONNES_RUNS)
    # réécrit en entier (petit fichier) : un index créé avant l'ajout d'une colonne reste lisible
    anciens = pd.read_csv(RUNS) if RUNS.exists() else pd.DataFrame(columns=COLONNES_RUNS)
    pd.concat([anciens.reindex(columns=COLONNES_RUNS), ligne], ignore_index=True).to_csv(RUNS, index=False)

    lignes_metriques = pd.DataFrame([
        {"run_id": run_id, "horodatage": horodatage, "categorie": categorie, "metrique": nom, "valeur": valeur}
        for categorie, groupe in metriques.items() for nom, valeur in groupe.items()], columns=COLONNES_METRIQUES)
    lignes_metriques.to_csv(METRIQUES, mode="a", header=not METRIQUES.exists(), index=False)

    dossier = FICHIERS / run_id
    dossier.mkdir()
    schedule.to_csv(dossier / "schedule.csv", index=False, date_format="%Y-%m-%d")
    r.sortie1.to_csv(dossier / "sortie1_profils.csv", index=False)
    r.sortie2.to_csv(dossier / "sortie2_camions.csv", index=False, date_format="%Y-%m-%d")
    construire_sortie3(r.camions_base, r.planning_complet).to_csv(dossier / "sortie3_savings.csv", index=False)
    r.bilan.to_csv(dossier / "bilan.csv", index=False)
    return run_id


def charger_runs() -> pd.DataFrame:
    """Lit l'index des runs, du plus récent au plus ancien.

    Returns:
        Une ligne par run (colonnes ``COLONNES_RUNS``) ; table vide s'il n'y a pas encore de run.
    """
    if not RUNS.exists():
        return pd.DataFrame(columns=COLONNES_RUNS).astype(
            {"horodatage": "datetime64[ns]", "debut": "datetime64[ns]", "fin": "datetime64[ns]"})
    runs = pd.read_csv(RUNS).reindex(columns=COLONNES_RUNS)       # colonnes absentes d'un ancien index : vides
    for colonne in ("horodatage", "debut", "fin"):
        runs[colonne] = pd.to_datetime(runs[colonne], errors="coerce")
    return runs.sort_values("horodatage", ascending=False).reset_index(drop=True)


def charger_metriques() -> pd.DataFrame:
    """Lit les métriques de tous les runs.

    Returns:
        Une ligne par (run, catégorie, métrique) ; table vide s'il n'y a pas encore de run.
    """
    if not METRIQUES.exists():
        return pd.DataFrame(columns=COLONNES_METRIQUES).astype({"horodatage": "datetime64[ns]", "valeur": float})
    return pd.read_csv(METRIQUES, parse_dates=["horodatage"])


def metriques_run(run_id: str) -> dict[str, float]:
    """Donne les métriques d'un run, à plat.

    Args:
        run_id: identifiant du run.

    Returns:
        Nom de la métrique -> valeur (vide si le run n'existe pas).
    """
    m = charger_metriques()
    m = m[m["run_id"] == run_id]
    return dict(zip(m["metrique"], m["valeur"].astype(float)))


def periode_run(run_id: str) -> tuple[pd.Timestamp, pd.Timestamp, int] | None:
    """Donne la période planifiée d'un run enregistré.

    Args:
        run_id: identifiant du run.

    Returns:
        ``(premier jour, dernier jour, nombre de semaines)``, ou None si inconnue (run enregistré avant
        l'ajout de la période).
    """
    runs = charger_runs()
    ligne = runs[runs["run_id"] == run_id]
    if ligne.empty or pd.isna(ligne["debut"].iloc[0]):
        return None
    return ligne["debut"].iloc[0], ligne["fin"].iloc[0], int(ligne["semaines"].iloc[0])


def charger_fichier_run(run_id: str, nom: str) -> pd.DataFrame | None:
    """Relit un fichier gardé pour un run.

    Args:
        run_id: identifiant du run.
        nom: nom du fichier (une clé de ``FICHIERS_RUN``).

    Returns:
        Le contenu du fichier, ou None s'il n'existe pas.
    """
    chemin = FICHIERS / run_id / nom
    return pd.read_csv(chemin) if chemin.exists() else None


def supprimer_run(run_id: str) -> None:
    """Retire un run de l'historique (index, métriques et fichiers).

    Args:
        run_id: identifiant du run.
    """
    for chemin in (RUNS, METRIQUES):
        if chemin.exists():
            table = pd.read_csv(chemin)
            table[table["run_id"] != run_id].to_csv(chemin, index=False)
    shutil.rmtree(FICHIERS / run_id, ignore_errors=True)
