"""Charge des usines : nombre de camions reçus chaque jour, et contrôle de la tolérance de lissage.

Utilisé par la contrainte C10 (``contraintes``) et par le lissage (``lissage``).
Une charge est une matrice ``semaines × 5 jours`` (voir ``typage.Charge``).
"""
import numpy as np
import numpy.typing as npt
import pandas as pd

from .config import MIN_CAMIONS_SEMAINE, SEUIL_LISSAGE
from . import donnees
from .typage import Charge, Charges


def case(date: pd.Timestamp) -> tuple[int, int]:
    """Donne la case d'une date dans une matrice de charge.

    Args:
        date: un jour de l'horizon.

    Returns:
        ``(position de la semaine dans SEMAINES, jour de la semaine)``, 0 = lundi.
    """
    return donnees.SEMAINES.index(date.isocalendar().week), date.day_of_week


def charge_depuis_camions(camions: pd.DataFrame, plant: str) -> Charge:
    """Compte les camions reçus par une usine, jour par jour.

    Les camions du week-end ou hors de l'horizon ne sont pas comptés.

    Args:
        camions: une ligne par camion, avec les colonnes ``plant`` et ``date``.
        plant: code de l'usine.

    Returns:
        La charge de l'usine : une ligne par semaine, une colonne par jour (lundi -> vendredi).
    """
    charge = np.zeros((donnees.NB_SEMAINES, 5))
    for d in camions.loc[camions["plant"] == plant, "date"]:
        if d.isocalendar().week in donnees.SEMAINES and d.day_of_week < 5:
            charge[case(d)] += 1
    return charge


def charges_camions(camions: pd.DataFrame) -> Charges:
    """Calcule la charge de chaque usine.

    Args:
        camions: une ligne par camion, avec les colonnes ``plant`` et ``date``.

    Returns:
        La charge de chaque usine de ``USINES``.
    """
    return {plant: charge_depuis_camions(camions, plant) for plant in donnees.USINES}


def ecart(charge_jours: npt.ArrayLike) -> float:
    """Mesure le déséquilibre d'une semaine.

    Args:
        charge_jours: nombre de camions de chaque jour de la semaine.

    Returns:
        L'écart du jour le plus éloigné de la moyenne, en proportion de la moyenne (0.35 = 35 %) ;
        0 pour une semaine sans camion.
    """
    charge_jours = np.asarray(charge_jours, dtype=float)
    moyenne = charge_jours.mean()
    return 0.0 if moyenne == 0 else float(np.abs(charge_jours - moyenne).max() / moyenne)


def hors_tolerance(charge_semaines: Charge, seuil: float | None = None) -> npt.NDArray[np.bool_]:
    """Repère les semaines hors tolérance de lissage (contrainte C10).

    Une semaine est hors tolérance si un jour s'écarte de la moyenne de la semaine de plus de ``seuil``
    (et d'au moins 1 camion). Les semaines de moins de ``MIN_CAMIONS_SEMAINE`` camions ne sont pas contrôlées.

    Args:
        charge_semaines: charge d'une usine, une ligne par semaine.
        seuil: écart maximal toléré ; ``SEUIL_LISSAGE`` par défaut.

    Returns:
        Un booléen par semaine, True si la semaine est hors tolérance.
    """
    seuil = SEUIL_LISSAGE if seuil is None else seuil
    moyenne = charge_semaines.mean(axis=1, keepdims=True)
    tolerance = np.maximum(seuil * moyenne, 1.0)
    depasse = (np.abs(charge_semaines - moyenne) > tolerance + 1e-9).any(axis=1)
    return depasse & (charge_semaines.sum(axis=1) >= MIN_CAMIONS_SEMAINE)


def nb_hors_tolerance(camions: pd.DataFrame) -> int:
    """Compte les semaines hors tolérance, toutes usines confondues, sur les semaines contrôlées.

    Args:
        camions: une ligne par camion, avec les colonnes ``plant`` et ``date``.

    Returns:
        Le nombre de couples (usine, semaine) hors tolérance.
    """
    return sum(int(hors_tolerance(charge[donnees.CONTROLE]).sum()) for charge in charges_camions(camions).values())


def charge_reservee() -> Charges:
    """Calcule la charge des camions réservés : fixe, le lissage ne peut pas la déplacer.

    Returns:
        La charge de chaque usine due aux seuls camions réservés.
    """
    return charges_camions(donnees.camions_reserves)
