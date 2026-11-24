"""Charge des usines : camions reçus par jour, et contrôle de la tolérance de lissage (C10 et lissage)."""
import numpy as np

from .config import MIN_CAMIONS_SEMAINE, SEUIL_LISSAGE
from .donnees import CONTROLE, NB_SEMAINES, SEMAINES, USINES, camions_reserves


def case(date):
    # (n° de semaine dans l'horizon, jour de la semaine) d'une date
    return SEMAINES.index(date.isocalendar().week), date.day_of_week


def charge_depuis_camions(camions, plant):
    # Camions reçus par une usine : une ligne par semaine, une colonne par jour (lundi -> vendredi)
    charge = np.zeros((NB_SEMAINES, 5))
    for d in camions.loc[camions["plant"] == plant, "date"]:
        if d.isocalendar().week in SEMAINES and d.day_of_week < 5:
            charge[case(d)] += 1
    return charge


def charges_camions(camions):
    return {plant: charge_depuis_camions(camions, plant) for plant in USINES}


def ecart(charge_jours):
    # Écart du jour le plus éloigné de la moyenne, en % de la moyenne (0.35 = 35 %)
    charge_jours = np.asarray(charge_jours, dtype=float)
    moyenne = charge_jours.mean()
    return 0.0 if moyenne == 0 else float(np.abs(charge_jours - moyenne).max() / moyenne)


def hors_tolerance(charge_semaines, seuil=None):
    # C10 pour chaque semaine : un jour s'écarte-t-il de la moyenne de plus du seuil (et d'au moins 1 camion) ?
    seuil = SEUIL_LISSAGE if seuil is None else seuil
    moyenne = charge_semaines.mean(axis=1, keepdims=True)
    tolerance = np.maximum(seuil * moyenne, 1.0)
    depasse = (np.abs(charge_semaines - moyenne) > tolerance + 1e-9).any(axis=1)
    return depasse & (charge_semaines.sum(axis=1) >= MIN_CAMIONS_SEMAINE)


def nb_hors_tolerance(camions):
    return sum(int(hors_tolerance(charge[CONTROLE]).sum()) for charge in charges_camions(camions).values())


CHARGE_RESERVEE = charges_camions(camions_reserves)   # charge fixe, que le lissage ne déplace pas
