"""Bloc 1 : jours fixes.

Chaque couple fournisseur × usine est consolidé pour chacun des 15 profils (1 ou 2 jours fixes par semaine) ;
on garde ensuite, par couple, le profil le moins cher.
"""
import itertools

import pandas as pd

from .charge import charge_depuis_camions
from .config import FENETRE, JOURS, JOURS_FIXES_MAX, POIDS_MAX, VOLUME_MAX
from .couts import cout_camion
from .donnees import DEBUT, besoins

PROFILS = [(j,) for j in range(5)] + list(itertools.combinations(range(5), JOURS_FIXES_MAX))
REFERENCE = (0, 1, 2, 3, 4)   # algorithme de base du milestone 2 (sans jours fixes) = livrer les 5 jours
VARIANTES = {"1 jour fixe": [p for p in PROFILS if len(p) == 1], "1 ou 2 jours fixes": PROFILS}


def nom_profil(profil):
    return " + ".join(JOURS[j] for j in profil)


def date_camion(besoin, profil):
    # Dernier jour du profil avant ou égal au besoin ; s'il tombe avant l'horizon -> date du besoin (démarrage)
    date = max(besoin - pd.Timedelta(days=(besoin.day_of_week - j) % 7) for j in profil)
    return (besoin, True) if date < DEBUT else (date, False)


def consolider_couple(lignes, profil):
    # Consolidation d'un couple avec des jours fixes (lignes triées par date, puis poids décroissant)
    restantes = list(lignes.itertuples())
    camions = []
    while restantes:
        date, demarrage = date_camion(restantes[0].need_date, profil)
        poids, volume, contenu, i = 0.0, 0.0, [], 0
        while i < len(restantes):
            ligne = restantes[i]
            if ligne.need_date > date + FENETRE:
                break                                   # hors fenêtre de 7 jours : camion fermé
            if poids + ligne.weight > POIDS_MAX or volume + ligne.volume > VOLUME_MAX:
                i += 1                                  # ne rentre pas : ligne suivante
                continue
            poids, volume = poids + ligne.weight, volume + ligne.volume
            contenu.append(ligne.Index)
            restantes.pop(i)
            i = 0
        camions.append({"date": date, "demarrage": demarrage, "poids": poids, "volume": volume, "lignes": contenu})
    return pd.DataFrame(camions)


def algorithme_de_base():
    # Camions de l'algorithme de base (sans jours fixes : livraison possible les 5 jours), pour le bilan
    camions_algo = pd.concat([consolider_couple(lignes_couple, REFERENCE).assign(plant=plant, supplier_id=supplier)
                              for (plant, supplier), lignes_couple in besoins.groupby(["plant", "supplier_id"])],
                             ignore_index=True)
    camions_algo["profil"] = [REFERENCE] * len(camions_algo)
    camions_algo["cout"] = [cout_camion(p, s) for p, s in zip(camions_algo["poids"], camions_algo["supplier_id"])]
    return camions_algo


class Scenarios:
    """Toutes les options : les camions de chaque couple × chaque profil, avec leur coût et leur charge."""

    def __init__(self):
        self.camions = {}
        for (plant, supplier), lignes_couple in besoins.groupby(["plant", "supplier_id"]):
            for profil in PROFILS:
                camions = consolider_couple(lignes_couple, profil)
                camions["cout"] = [cout_camion(p, supplier) for p in camions["poids"]]
                self.camions[(plant, supplier, profil)] = camions

        self.cout = {cle: c["cout"].sum() for cle, c in self.camions.items()}
        self.nb_camions = {cle: len(c) for cle, c in self.camions.items()}
        self.charge = {(p, s, prof): charge_depuis_camions(c[~c["demarrage"]].assign(plant=p), p)   # hors démarrage
                       for (p, s, prof), c in self.camions.items()}
        self.max_jour = {cle: int(c.groupby("date").size().max()) for cle, c in self.camions.items()}   # camions max un même jour

    def autorises(self, plant, supplier, profils_variante):
        # Profils de la variante qui ne mettent jamais 2 camions le même jour à ce couple (C9).
        # Si aucun ne le permet (besoin d'un seul jour > 24,5 t) : tous les profils de la variante
        ok = [p for p in profils_variante if self.max_jour[(plant, supplier, p)] <= 1]
        return ok if ok else list(profils_variante)

    def choix_moins_cher(self, profils_variante):
        # Profil le moins cher de chaque couple (à égalité : moins de camions, puis moins de jours)
        choix = {}
        for cle in sorted((k for k in self.camions if k[2] in self.autorises(k[0], k[1], profils_variante)),
                          key=lambda k: (k[0], k[1], round(self.cout[k], 2), self.nb_camions[k], len(k[2]), k[2])):
            choix.setdefault(cle[:2], cle[2])
        return choix

    def cout_choix(self, choix):
        return sum(self.cout[(p, s, prof)] for (p, s), prof in choix.items())
