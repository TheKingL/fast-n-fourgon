"""Chemins des fichiers et paramètres du moteur.

C'est le seul endroit à modifier pour changer une donnée d'entrée ou un paramètre métier
(capacité d'un camion, fenêtre d'avance, seuil de lissage...).
"""
from pathlib import Path
from typing import Final

import pandas as pd

# ---------- Fichiers ----------
RACINE: Final[Path] = Path(__file__).resolve().parent.parent
"""Racine du dépôt."""
DATA: Final[Path] = RACINE / "data"
"""Dossier des données (bronze, silver, baseline, gold)."""
SILVER_CLEAN_PATH: Final[Path] = DATA / "silver" / "released_schedule_cleaned.csv"
"""Besoins nettoyés (milestone 1)."""
QUARANTAINE_PATH: Final[Path] = DATA / "silver" / "released_schedule_quarantine.csv"
"""Lignes mises en quarantaine au nettoyage (poids manquant, poids trop élevé...)."""
BASELINE_PATH: Final[Path] = DATA / "baseline" / "baseline_camion.csv"
"""Baseline du milestone 2 : une ligne par camion."""
RATE_SHEET_PATH: Final[Path] = DATA / "bronze" / "rate_sheet.csv"
"""Grille tarifaire : coût par tranche de distance (lignes) et de poids (colonnes)."""
DISTANCES_PATH: Final[Path] = DATA / "bronze" / "distances.csv"
"""Distance de chaque fournisseur, en km."""
SORTIE: Final[Path] = DATA / "gold"
"""Dossier où sont écrits les fichiers de sortie."""

# ---------- Paramètres du moteur ----------
POIDS_MAX: Final[float] = 24500
"""Poids maximal d'un camion, en kg."""
VOLUME_MAX: Final[float] = 110.4
"""Volume maximal d'un camion, en m³."""
FENETRE: Final[pd.Timedelta] = pd.Timedelta(days=7)
"""Avance maximale d'une livraison sur le besoin."""
JOURS_FIXES_MAX: Final[int] = 2
"""Nombre maximal de jours fixes de livraison par semaine pour un couple (1 ou 2)."""
SEUIL_LISSAGE: Final[float] = 0.35
"""Écart maximal toléré entre la charge d'un jour et la moyenne de la semaine (0.35 = 35 %)."""
MIN_CAMIONS_SEMAINE: Final[int] = 5
"""Semaines plus petites (moins d'un camion par jour) : pas contrôlées pour le lissage."""
JOURS: Final[list[str]] = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]
"""Noms des jours ouvrés, indexés par numéro de jour (0 = lundi)."""

# ---------- Coût de transport ----------
FREIGHT_VALUE_MARGIN: Final[float] = 2.3923
"""Marge appliquée au coût de la grille (+239,23 %)."""
DIESEL_SURCHARGE: Final[float] = 1.1943
"""Coefficient de surcharge diesel."""
