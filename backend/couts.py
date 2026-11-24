"""Coût de transport : grille tarifaire (rate sheet), distances des fournisseurs et coût d'un camion.

La grille et les distances sont des données de référence, chargées une seule fois à l'import du module.
Les données manquantes sont remplacées par des estimations hautes (comme dans la baseline du milestone 2) :
distance inconnue -> tranche ``> 650 km``, poids inconnu -> tranche ``> 4 000 kg``.
"""
from typing import cast

import pandas as pd

from .config import DIESEL_SURCHARGE, DISTANCES_PATH, FREIGHT_VALUE_MARGIN, RATE_SHEET_PATH

couts: pd.DataFrame = pd.read_csv(RATE_SHEET_PATH, index_col="km_max")
"""Grille tarifaire : une ligne par tranche de distance, une colonne par tranche de poids (coût de base en €)."""
TRANCHES_KM: list[int] = [int(km) for km in couts.index if not km.startswith(">")]    # 30, 50, ..., 650
"""Bornes supérieures des tranches de distance, en km."""
TRANCHES_KG: list[int] = [int(kg) for kg in couts.columns if not kg.startswith(">")]  # 50, 100, ..., 4000
"""Bornes supérieures des tranches de poids, en kg."""

distances: pd.Series = pd.read_csv(DISTANCES_PATH, encoding="utf-8-sig").set_index("supplier_id")["distance"]

DISTANCE_PAR_DEFAUT: int = TRANCHES_KM[-1] + 1  # 651 km -> tranche "> 650 km"
"""Distance utilisée quand celle du fournisseur est inconnue (tombe dans la dernière tranche)."""
POIDS_PAR_DEFAUT: int = TRANCHES_KG[-1] + 1     # 4 001 kg -> tranche "> 4 000 kg"
"""Poids utilisé quand celui du camion est inconnu (camion réservé)."""
SANS_DISTANCE: list[str] = sorted(distances.index[distances.isna()])
"""Fournisseurs dont la distance est inconnue."""
distance_brute: pd.Series = distances.copy()
"""Distance de chaque fournisseur telle que fournie (NaN = inconnue), affichée dans la sortie 1."""
distances = distances.fillna(DISTANCE_PAR_DEFAUT)
"""Distance de chaque fournisseur, utilisée pour le coût (distance inconnue -> ``DISTANCE_PAR_DEFAUT``)."""


def tranche(valeur: float, tranches: list[int]) -> str:
    """Trouve la tranche de la grille tarifaire qui s'applique à une valeur.

    On majore : la tranche retenue est la première dont la borne est supérieure ou égale à la valeur.

    Args:
        valeur: distance (km) ou poids (kg).
        tranches: bornes des tranches, croissantes (``TRANCHES_KM`` ou ``TRANCHES_KG``).

    Returns:
        Le libellé de la tranche dans la grille, par exemple ``"50"``, ou ``">650"`` au-delà de la dernière borne.
    """
    for borne in tranches:
        if valeur <= borne:
            return str(borne)
    return f">{tranches[-1]}"


def cout_transport(poids: float, distance: float) -> float:
    """Calcule le prix d'un camion : coût de la grille × (1 + marge) × surcharge diesel.

    Args:
        poids: poids chargé, en kg.
        distance: distance du fournisseur, en km.

    Returns:
        Le prix du camion en €, arrondi au centime.
    """
    cout_base = cast(float, couts.loc[tranche(distance, TRANCHES_KM), tranche(poids, TRANCHES_KG)])
    return float(round(cout_base * (1 + FREIGHT_VALUE_MARGIN) * DIESEL_SURCHARGE, 2))


def cout_camion(poids: float, supplier_id: str) -> float:
    """Calcule le prix d'un camion d'un fournisseur.

    Args:
        poids: poids chargé, en kg ; NaN pour un camion réservé (poids inconnu -> ``POIDS_PAR_DEFAUT``).
        supplier_id: identifiant du fournisseur (sa distance est lue dans ``distances``).

    Returns:
        Le prix du camion en €.
    """
    return cout_transport(POIDS_PAR_DEFAUT if pd.isna(poids) else poids, distances[supplier_id])


def cout_total(planning: pd.DataFrame) -> float:
    """Calcule le coût total d'un planning, l'objectif que le moteur minimise.

    Args:
        planning: une ligne par camion, avec les colonnes ``poids`` et ``supplier_id``.

    Returns:
        La somme des prix des camions, en €.
    """
    return sum(cout_camion(p, s) for p, s in zip(planning["poids"], planning["supplier_id"]))
