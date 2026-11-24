"""Blocs 2 et 3 : contrôle de l'équilibre des usines (C10) et lissage.

Le lissage change le profil de certains couples, au moindre surcoût, jusqu'à ce que les semaines
de chaque usine soient dans la tolérance (ou qu'aucun changement ne les améliore plus).
"""
from collections.abc import Sequence
from typing import Any, TypedDict

import pandas as pd

from . import donnees
from .charge import charge_reservee, hors_tolerance
from .jours_fixes import Scenarios, nom_profil
from .typage import Charge, Charges, Choix, Profil


class Changement(TypedDict):
    """Un changement de profil envisagé par le lissage."""

    cle: tuple[float, float]
    """Critère de choix, le plus petit gagne : ``(surcoût / dispersion gagnée, -dispersion gagnée)``."""
    supplier_id: str
    """Fournisseur du couple dont le profil change."""
    de: Profil
    """Profil actuel du couple."""
    vers: Profil
    """Nouveau profil."""
    surcout: float
    """Différence de coût, en € (négative si le changement est moins cher)."""
    charge: Charge
    """Charge de l'usine après le changement."""


def charges_choix(scenarios: Scenarios, choix: Choix, fond: Charges | None = None) -> Charges:
    """Calcule la charge de chaque usine pour un choix de profils.

    Args:
        scenarios: les scénarios de tous les couples.
        choix: profil retenu pour chaque couple.
        fond: charge de départ de chaque usine ; celle des camions réservés (``charge_reservee``) par défaut.

    Returns:
        La charge de chaque usine (camions réservés compris).
    """
    fond = charge_reservee() if fond is None else fond
    return {plant: fond[plant] + sum(scenarios.charge[(p, s, prof)] for (p, s), prof in choix.items() if p == plant)
            for plant in donnees.USINES}


def dispersion(charge: Charge) -> float:
    """Mesure le déséquilibre d'une usine sur les semaines contrôlées (le lissage cherche à la réduire).

    Args:
        charge: charge de l'usine, une ligne par semaine.

    Returns:
        La somme, sur les semaines contrôlées, des carrés des écarts de chaque jour à la moyenne de sa semaine.
    """
    charge = charge[donnees.CONTROLE]
    return float(((charge - charge.mean(axis=1, keepdims=True)) ** 2).sum())


def lisser_par_couple(scenarios: Scenarios, choix: Choix, plant: str, profils_variante: Sequence[Profil],
                      seuil: float | None = None,
                      fond: Charges | None = None) -> tuple[Choix, list[dict[str, Any]]]:
    """Lisse une usine en changeant le profil de ses couples, un changement à la fois.

    À chaque tour, on choisit le changement de profil qui réduit la dispersion au plus petit surcoût
    par unité de dispersion gagnée, jusqu'à ce qu'aucune semaine contrôlée ne soit hors tolérance
    ou qu'aucun changement ne réduise plus la dispersion.

    Args:
        scenarios: les scénarios de tous les couples.
        choix: profil actuel de chaque couple (pas modifié).
        plant: code de l'usine à lisser.
        profils_variante: profils autorisés par la variante.
        seuil: écart maximal toléré ; ``SEUIL_LISSAGE`` par défaut.
        fond: charge de départ de chaque usine ; camions réservés par défaut.

    Returns:
        ``(nouveau choix, journal)`` ; le journal a une entrée par changement de profil
        (``plant``, ``supplier_id``, ``de``, ``vers``, ``surcout``, ``semaines_hors_tolerance_apres``).
    """
    choix = dict(choix)
    charge = charges_choix(scenarios, choix, fond)[plant]
    journal: list[dict[str, Any]] = []
    while hors_tolerance(charge[donnees.CONTROLE], seuil).any():
        dispersion_actuelle = dispersion(charge)
        meilleur: Changement | None = None
        for (p, s), prof in choix.items():
            if p != plant:
                continue
            for prof2 in scenarios.autorises(p, s, profils_variante):     # jamais 2 camions le même jour
                if prof2 == prof:
                    continue
                nouvelle = charge - scenarios.charge[(p, s, prof)] + scenarios.charge[(p, s, prof2)]
                gain = dispersion_actuelle - dispersion(nouvelle)
                if gain <= 1e-9:
                    continue
                surcout = scenarios.cout[(p, s, prof2)] - scenarios.cout[(p, s, prof)]
                cle = (max(surcout, 0) / gain, -gain)
                if meilleur is None or cle < meilleur["cle"]:
                    meilleur = {"cle": cle, "supplier_id": s, "de": prof, "vers": prof2, "surcout": surcout,
                                "charge": nouvelle}
        if meilleur is None:
            break                                               # plus aucun changement n'améliore les semaines
        choix[(plant, meilleur["supplier_id"])] = meilleur["vers"]
        charge = meilleur["charge"]
        journal.append({"plant": plant, "supplier_id": meilleur["supplier_id"], "de": nom_profil(meilleur["de"]),
                        "vers": nom_profil(meilleur["vers"]), "surcout": round(meilleur["surcout"], 2),
                        "semaines_hors_tolerance_apres": int(hors_tolerance(charge[donnees.CONTROLE], seuil).sum())})
    return choix, journal


def lisser(scenarios: Scenarios, choix: Choix, profils_variante: Sequence[Profil], seuil: float | None = None,
           fond: Charges | None = None) -> tuple[Choix, pd.DataFrame]:
    """Lisse toutes les usines qui ont au moins une semaine hors tolérance.

    Args:
        scenarios: les scénarios de tous les couples.
        choix: profil de chaque couple avant lissage (pas modifié).
        profils_variante: profils autorisés par la variante.
        seuil: écart maximal toléré ; ``SEUIL_LISSAGE`` par défaut.
        fond: charge de départ de chaque usine ; camions réservés par défaut.

    Returns:
        ``(choix lissé, journal des changements de profil)``, voir ``lisser_par_couple``.
    """
    choix = dict(choix)
    fond = charge_reservee() if fond is None else fond      # calculée une fois pour toutes les usines
    journal: list[dict[str, Any]] = []
    for plant in donnees.USINES:
        if hors_tolerance(charges_choix(scenarios, choix, fond)[plant][donnees.CONTROLE], seuil).any():
            choix, journal_u = lisser_par_couple(scenarios, choix, plant, profils_variante, seuil, fond)
            journal += journal_u
    return choix, pd.DataFrame(journal)
