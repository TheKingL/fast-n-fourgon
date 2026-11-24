"""Coût de transport : grille tarifaire (rate sheet), distances fournisseurs et coût d'un camion.

La grille et les distances sont des données de référence, chargées une fois à l'import.
"""
import pandas as pd

from .config import DIESEL_SURCHARGE, DISTANCES_PATH, FREIGHT_VALUE_MARGIN, RATE_SHEET_PATH

couts = pd.read_csv(RATE_SHEET_PATH, index_col="km_max")
TRANCHES_KM = [int(km) for km in couts.index if not km.startswith(">")]    # 30, 50, ..., 650
TRANCHES_KG = [int(kg) for kg in couts.columns if not kg.startswith(">")]  # 50, 100, ..., 4000
distances = pd.read_csv(DISTANCES_PATH, encoding="utf-8-sig").set_index("supplier_id")["distance"]

# Données manquantes : estimations hautes (comme dans la baseline du milestone 2)
DISTANCE_PAR_DEFAUT = TRANCHES_KM[-1] + 1  # 651 km -> tranche "> 650 km"
POIDS_PAR_DEFAUT = TRANCHES_KG[-1] + 1     # 4 001 kg -> tranche "> 4 000 kg"
SANS_DISTANCE = sorted(distances.index[distances.isna()])
distance_brute = distances.copy()          # NaN = distance inconnue (affichée telle quelle dans la sortie 1)
distances = distances.fillna(DISTANCE_PAR_DEFAUT)


def tranche(valeur, tranches):
    # Première tranche >= valeur (on majore), sinon la tranche '>max'
    for borne in tranches:
        if valeur <= borne:
            return str(borne)
    return f">{tranches[-1]}"


def cout_transport(poids, distance):
    # Prix d'un camion en € = coût de la grille × (1 + marge) × diesel
    cout_base = couts.loc[tranche(distance, TRANCHES_KM), tranche(poids, TRANCHES_KG)]
    return float(round(cout_base * (1 + FREIGHT_VALUE_MARGIN) * DIESEL_SURCHARGE, 2))


def cout_camion(poids, supplier_id):
    # Coût d'un camion ; poids inconnu (camion réservé) -> tranche > 4 000 kg
    return cout_transport(POIDS_PAR_DEFAUT if pd.isna(poids) else poids, distances[supplier_id])


def cout_total(planning):
    # Objectif à minimiser : somme des coûts des camions
    return sum(cout_camion(p, s) for p, s in zip(planning["poids"], planning["supplier_id"]))
