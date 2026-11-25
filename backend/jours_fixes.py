"""Bloc 1 : jours fixes.

Chaque couple fournisseur × usine est consolidé pour chacun des 25 profils possibles
(1 jour fixe : 5 profils ; 2 jours fixes : 10 profils ; 3 jours fixes : 10 profils). On garde ensuite, par couple,
le profil le moins cher parmi ceux qui sont vraiment utilisés : un couple à 2 ou 3 jours fixes doit livrer
au moins une semaine sur tous ses jours fixes (C11).
"""
import itertools
from collections.abc import Iterable, Sequence
from typing import NamedTuple

import pandas as pd

from . import donnees
from .charge import charge_depuis_camions
from .config import FENETRE, JOURS, JOURS_FIXES_MAX, POIDS_MAX, VOLUME_MAX
from .couts import cout_camion
from .typage import Charge, Choix, CleScenario, Profil

PROFILS: list[Profil] = [p for n in range(1, JOURS_FIXES_MAX + 1) for p in itertools.combinations(range(5), n)]
"""Les 25 profils de jours fixes : ``(0,)`` ... ``(4,)``, puis ``(0, 1)`` ... ``(3, 4)``, puis ``(0, 1, 2)`` ... ``(2, 3, 4)``."""
REFERENCE: Profil = (0, 1, 2, 3, 4)
"""Profil de l'algorithme de base du milestone 2 (sans jours fixes) : livraison possible les 5 jours."""
VARIANTES: dict[str, list[Profil]] = {"1 jour fixe": [p for p in PROFILS if len(p) == 1],
                                      "1 ou 2 jours fixes": [p for p in PROFILS if len(p) <= 2],
                                      "1 à 3 jours fixes": PROFILS}
"""Variantes du moteur comparées dans le bilan : nom -> profils autorisés."""


class Ligne(NamedTuple):
    """Une ligne de besoin, telle que la lit la consolidation."""

    id_besoin: int
    """Index de la ligne dans ``besoins``."""
    need_date: pd.Timestamp
    """Date du besoin."""
    weight: float
    """Poids, en kg."""
    volume: float
    """Volume, en m³."""


def nom_profil(profil: Profil) -> str:
    """Donne le nom d'un profil en clair.

    Args:
        profil: numéros des jours fixes, par exemple ``(0, 3)``.

    Returns:
        Les jours en toutes lettres, par exemple ``"Lundi + Jeudi"``.
    """
    return " + ".join(JOURS[j] for j in profil)


def date_camion(besoin: pd.Timestamp, profil: Profil) -> pd.Timestamp:
    """Choisit le jour de départ du camion qui livre un besoin.

    C'est le dernier jour fixe du profil avant ou égal au besoin, toujours à moins de 7 jours du besoin.
    Pour les premiers besoins, il peut tomber dans la semaine ajoutée avant le planning (à partir du lundi 02/11).

    Args:
        besoin: date du besoin.
        profil: jours fixes du couple.

    Returns:
        La date du camion.
    """
    return max(besoin - pd.Timedelta(days=(besoin.day_of_week - j) % 7) for j in profil)


def profil_utilise(dates: Iterable[pd.Timestamp], profil: Profil) -> bool:
    """Vérifie qu'un couple livre au moins une semaine sur tous ses jours fixes (C11).

    Un couple au profil « mardi + vendredi » doit avoir au moins une semaine avec un camion le mardi et un camion
    le vendredi ; sinon il n'utilise jamais vraiment ses 2 jours. Un profil d'un seul jour est toujours utilisé.

    Args:
        dates: dates des camions du couple.
        profil: jours fixes du couple.

    Returns:
        True si une semaine au moins compte un camion sur chacun des jours fixes.
    """
    jours_par_semaine: dict[tuple[int, int], set[int]] = {}
    for d in dates:
        iso = d.isocalendar()
        jours_par_semaine.setdefault((iso.year, iso.week), set()).add(d.day_of_week)
    return any(set(profil) <= jours for jours in jours_par_semaine.values())


def consolider_couple(lignes: pd.DataFrame, profil: Profil) -> pd.DataFrame:
    """Regroupe les besoins d'un couple dans des camions, avec des jours fixes.

    Le premier besoin restant ouvre un camion à son jour fixe ; on y ajoute les besoins suivants tant qu'ils
    sont à moins de 7 jours du camion et qu'ils tiennent en poids (24,5 t) et en volume (110,4 m³).

    Args:
        lignes: besoins du couple triés par date puis poids décroissant, avec ``need_date``, ``weight`` et
            ``volume`` ; l'index identifie la ligne.
        profil: jours fixes du couple.

    Returns:
        Une ligne par camion : ``date``, ``poids``, ``volume`` et ``lignes`` (index des lignes chargées).
    """
    restantes = [Ligne(*l) for l in zip(lignes.index, lignes["need_date"], lignes["weight"], lignes["volume"])]
    camions = []
    while restantes:
        date = date_camion(restantes[0].need_date, profil)
        poids, volume, i = 0.0, 0.0, 0
        contenu: list[int] = []
        while i < len(restantes):
            ligne = restantes[i]
            if ligne.need_date > date + FENETRE:
                break                                   # hors fenêtre de 7 jours : camion fermé
            if poids + ligne.weight > POIDS_MAX or volume + ligne.volume > VOLUME_MAX:
                i += 1                                  # ne rentre pas : ligne suivante
                continue
            poids, volume = poids + ligne.weight, volume + ligne.volume
            contenu.append(ligne.id_besoin)
            restantes.pop(i)
            i = 0
        camions.append({"date": date, "poids": poids, "volume": volume, "lignes": contenu})
    return pd.DataFrame(camions)


def algorithme_de_base() -> pd.DataFrame:
    """Consolide tous les couples sans jours fixes (algorithme de base du milestone 2), pour le bilan.

    Returns:
        Une ligne par camion, avec ``plant``, ``supplier_id``, ``profil`` et ``cout`` en plus des colonnes
        de ``consolider_couple``.
    """
    morceaux = []
    for (plant, supplier), lignes_couple in donnees.besoins.groupby(["plant", "supplier_id"]):
        morceaux.append(consolider_couple(lignes_couple, REFERENCE).assign(plant=str(plant), supplier_id=str(supplier)))
    camions_algo = pd.concat(morceaux, ignore_index=True)
    camions_algo["profil"] = [REFERENCE] * len(camions_algo)
    camions_algo["cout"] = [cout_camion(p, s) for p, s in zip(camions_algo["poids"], camions_algo["supplier_id"])]
    return camions_algo


class Scenarios:
    """Toutes les options du moteur : les camions de chaque couple pour chaque profil.

    Le calcul (15 consolidations par couple) est fait une fois à la construction ; le lissage et le
    report réutilisent ensuite ces résultats.

    Attributes:
        camions: camions de chaque scénario ``(usine, fournisseur, profil)`` (voir ``consolider_couple``,
            avec la colonne ``cout`` en plus).
        cout: coût total de chaque scénario, en €.
        nb_camions: nombre de camions de chaque scénario.
        charge: charge de l'usine due à chaque scénario.
        max_jour: nombre maximal de camions un même jour pour chaque scénario.
        utilise: True si le couple livre au moins une semaine sur tous les jours du profil (C11).
    """

    def __init__(self) -> None:
        """Consolide chaque couple de ``donnees.besoins`` pour chacun des ``PROFILS``."""
        self.camions: dict[CleScenario, pd.DataFrame] = {}
        for (plant, supplier), lignes_couple in donnees.besoins.groupby(["plant", "supplier_id"]):
            plant, supplier = str(plant), str(supplier)
            for profil in PROFILS:
                camions = consolider_couple(lignes_couple, profil)
                camions["cout"] = [cout_camion(p, supplier) for p in camions["poids"]]
                self.camions[(plant, supplier, profil)] = camions

        self.cout: dict[CleScenario, float] = {cle: c["cout"].sum() for cle, c in self.camions.items()}
        self.nb_camions: dict[CleScenario, int] = {cle: len(c) for cle, c in self.camions.items()}
        self.charge: dict[CleScenario, Charge] = {
            (p, s, prof): charge_depuis_camions(c.assign(plant=p), p) for (p, s, prof), c in self.camions.items()}
        self.max_jour: dict[CleScenario, int] = {
            cle: int(c.groupby("date").size().max()) for cle, c in self.camions.items()}
        self.utilise: dict[CleScenario, bool] = {
            (p, s, prof): profil_utilise(c["date"], prof) for (p, s, prof), c in self.camions.items()}

    def autorises(self, plant: str, supplier: str, profils_variante: Sequence[Profil]) -> list[Profil]:
        """Donne les profils autorisés pour un couple : profil utilisé (C11) et 1 camion par jour (C9).

        Un profil de 2 ou 3 jours où le couple ne livre jamais sur tous ses jours la même semaine est exclu.
        Les profils d'un seul jour sont toujours utilisés, donc il reste au moins un profil.

        Args:
            plant: code de l'usine.
            supplier: identifiant du fournisseur.
            profils_variante: profils autorisés par la variante.

        Returns:
            Les profils utilisés de la variante qui respectent C9 ; si aucun ne respecte C9 (besoin d'un seul
            jour > 24,5 t), tous les profils utilisés de la variante.
        """
        utilises = [p for p in profils_variante if self.utilise[(plant, supplier, p)]]
        assert utilises, f"aucun profil utilisé pour {plant} / {supplier}"
        ok = [p for p in utilises if self.max_jour[(plant, supplier, p)] <= 1]
        return ok if ok else utilises

    def choix_moins_cher(self, profils_variante: Sequence[Profil]) -> Choix:
        """Choisit le profil le moins cher de chaque couple parmi les profils autorisés.

        À coût égal : le moins de camions, puis le moins de jours fixes.

        Args:
            profils_variante: profils autorisés par la variante.

        Returns:
            Le profil retenu pour chaque couple.
        """
        choix: Choix = {}
        for cle in sorted((k for k in self.camions if k[2] in self.autorises(k[0], k[1], profils_variante)),
                          key=lambda k: (k[0], k[1], round(self.cout[k], 2), self.nb_camions[k], len(k[2]), k[2])):
            choix.setdefault(cle[:2], cle[2])
        return choix

    def cout_choix(self, choix: Choix) -> float:
        """Calcule le coût total d'un choix de profils.

        Args:
            choix: profil retenu pour chaque couple.

        Returns:
            La somme des coûts des scénarios retenus, en €.
        """
        return sum(self.cout[(p, s, prof)] for (p, s), prof in choix.items())

    def camions_en_trop_evitables(self, choix: Choix) -> int:
        """Compte les couples qui ont 2 camions un même jour alors qu'un autre profil l'éviterait (C9).

        Args:
            choix: profil retenu pour chaque couple.

        Returns:
            Le nombre de couples du choix dont le profil met 2 camions un même jour, alors qu'au moins un profil
            utilisé (C11), parmi tous les ``PROFILS``, n'en met jamais 2.
        """
        return sum(self.max_jour[(p, s, prof)] > 1 and self.max_jour[(p, s, self.autorises(p, s, PROFILS)[0])] <= 1
                   for (p, s), prof in choix.items())
