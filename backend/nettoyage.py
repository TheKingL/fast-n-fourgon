"""Nettoyage d'un schedule brut (pipeline du milestone 1) : bronze -> silver.

1. Nettoyage : retrait des lignes à quantité nulle, à date illisible et aux dates exclues (``DATES_EXCLUES``),
   ``date`` renommée ``need_date``, colonnes d'envoi (``transmission_date``, ``version_date``) supprimées.
2. Flags : chaque ligne reçoit la liste des problèmes détectés (poids ou volume manquant, fournisseur sans
   distance, ligne plus lourde ou plus volumineuse qu'un camion).
3. Séparation : les lignes sans flag forment le silver « clean », les autres la quarantaine.
"""
import pandas as pd

from .config import COLONNES_SCHEDULE, DATES_EXCLUES, POIDS_MAX, VOLUME_MAX
from . import couts

COLONNES_SILVER: list[str] = ["need_date", "supplier_id", "material", "plant", "unloading_point",
                              "schedule_quantity", "weight", "volume"]
"""Colonnes du silver clean (la quarantaine a en plus la colonne ``flags``)."""


def verifier_colonnes(schedule: pd.DataFrame) -> list[str]:
    """Liste les colonnes obligatoires absentes d'un schedule brut.

    Args:
        schedule: le schedule lu.

    Returns:
        Les colonnes de ``COLONNES_SCHEDULE`` absentes (liste vide = schedule exploitable).
    """
    return [c for c in COLONNES_SCHEDULE if c not in schedule.columns]


def flags(schedule: pd.DataFrame) -> pd.DataFrame:
    """Détecte les problèmes de qualité de chaque ligne.

    Args:
        schedule: schedule nettoyé (colonnes ``supplier_id``, ``weight``, ``volume``).

    Returns:
        Une colonne booléenne par flag : ``MISSING_WEIGHT``, ``MISSING_VOLUME``, ``NO_DISTANCE``,
        ``OVER_TRUCK_WEIGHT``, ``OVER_TRUCK_VOLUME``.
    """
    avec_distance = set(couts.distance_brute.index[couts.distance_brute.notna()])
    return pd.DataFrame({
        "MISSING_WEIGHT": schedule["weight"].isna(),
        "MISSING_VOLUME": schedule["volume"].isna(),
        "NO_DISTANCE": ~schedule["supplier_id"].isin(avec_distance),
        "OVER_TRUCK_WEIGHT": schedule["weight"] > POIDS_MAX,
        "OVER_TRUCK_VOLUME": schedule["volume"] > VOLUME_MAX,
    })


def nettoyer(schedule: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Nettoie un schedule brut et le sépare en lignes saines et lignes en quarantaine.

    Args:
        schedule: schedule brut, avec au moins les colonnes ``COLONNES_SCHEDULE`` (``date`` en texte ou en date).

    Returns:
        ``(clean, quarantaine)`` : les lignes sans flag (colonnes ``COLONNES_SILVER``) et les lignes flaggées
        (avec la colonne ``flags``, flags séparés par ``|``), chacune avec un index 0, 1, 2...

    Raises:
        ValueError: s'il manque une colonne obligatoire ou si aucune ligne ne reste après nettoyage.
    """
    manquantes = verifier_colonnes(schedule)
    if manquantes:
        raise ValueError(f"colonnes manquantes dans le schedule : {', '.join(manquantes)}")

    propre = schedule[COLONNES_SCHEDULE].copy()
    propre["date"] = pd.to_datetime(propre["date"], errors="coerce")
    for colonne in ["schedule_quantity", "weight", "volume"]:
        propre[colonne] = pd.to_numeric(propre[colonne], errors="coerce")

    # Partie 1 : nettoyage (une date illisible ne peut pas être planifiée : la ligne est retirée)
    propre = propre[propre["date"].notna()]
    propre = propre[propre["schedule_quantity"] > 0]
    propre = propre[~propre["date"].isin(pd.to_datetime(DATES_EXCLUES))]
    propre = propre.rename(columns={"date": "need_date"})
    if propre.empty:
        raise ValueError("aucune ligne de besoin après nettoyage (quantités nulles ou dates exclues)")

    # Partie 2 : flags
    detectes = flags(propre)
    liste_flags = detectes.apply(lambda ligne: [f for f, actif in ligne.items() if actif], axis=1)

    # Partie 3 : séparation clean / quarantaine
    a_flag = liste_flags.map(len) > 0
    clean = propre[~a_flag].reset_index(drop=True)
    quarantaine = propre[a_flag].assign(flags=liste_flags[a_flag].str.join("|")).reset_index(drop=True)
    assert len(clean) + len(quarantaine) == len(propre)
    return clean, quarantaine
