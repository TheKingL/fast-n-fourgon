"""Chemins des fichiers et paramètres du moteur."""
from pathlib import Path

import pandas as pd

# ---------- Fichiers ----------
RACINE = Path(__file__).resolve().parent.parent
DATA = RACINE / "data"
SILVER_CLEAN_PATH = DATA / "silver" / "released_schedule_cleaned.csv"
QUARANTAINE_PATH = DATA / "silver" / "released_schedule_quarantine.csv"
BASELINE_PATH = DATA / "baseline" / "baseline_camion.csv"   # baseline du milestone 2 : une ligne par camion
RATE_SHEET_PATH = DATA / "bronze" / "rate_sheet.csv"
DISTANCES_PATH = DATA / "bronze" / "distances.csv"
SORTIE = DATA / "gold"

# ---------- Paramètres du moteur ----------
POIDS_MAX = 24500                 # kg par camion
VOLUME_MAX = 110.4                # m³ par camion
FENETRE = pd.Timedelta(days=7)    # avance maximale d'une livraison sur le besoin
JOURS_FIXES_MAX = 2               # un couple livre 1 ou 2 jours fixes par semaine
SEUIL_LISSAGE = 0.35              # écart max toléré entre un jour et la moyenne de la semaine
MIN_CAMIONS_SEMAINE = 5           # semaines plus petites (moins d'un camion par jour) : pas contrôlées
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]

# ---------- Coût de transport ----------
FREIGHT_VALUE_MARGIN = 2.3923     # +239,23 %
DIESEL_SURCHARGE = 1.1943
