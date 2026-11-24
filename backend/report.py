"""Bloc 4 : report des lignes sur le jour fixe suivant, puis planning final (camions optimisés + camions réservés)."""
import itertools
from typing import Any, TypedDict

import pandas as pd

from .config import JOURS, POIDS_MAX, VOLUME_MAX
from .couts import cout_camion
from .donnees import besoins, camions_reserves, lignes_reserves
from .jours_fixes import Scenarios, nom_profil
from .typage import Choix, Profil


class CamionEnCours(TypedDict):
    """Un camion d'un couple pendant le report (son contenu peut encore changer)."""

    date: pd.Timestamp
    """Jour du camion."""
    demarrage: bool
    """True pour un camion de démarrage (hors jours fixes, première semaine)."""
    lignes: list[int]
    """Index (dans ``besoins``) des lignes chargées."""


def prochain_jour_fixe(date: pd.Timestamp, profil: Profil) -> pd.Timestamp:
    """Donne le premier jour du profil strictement après une date.

    Args:
        date: date d'un camion.
        profil: jours fixes du couple.

    Returns:
        La date du jour fixe suivant.
    """
    return min(date + pd.Timedelta(days=(j - date.day_of_week - 1) % 7 + 1) for j in profil)


def construire_planning(scenarios: Scenarios, choix: Choix) -> pd.DataFrame:
    """Rassemble les camions d'un choix de profils.

    Args:
        scenarios: les scénarios de tous les couples.
        choix: profil retenu pour chaque couple.

    Returns:
        Une ligne par camion, avec ``plant``, ``supplier_id``, ``profil`` et la liste de ses ``lignes``.
    """
    morceaux = []
    for (p, s), prof in choix.items():
        camions = scenarios.camions[(p, s, prof)].assign(plant=p, supplier_id=s)   # copie : le scénario ne change pas
        camions["profil"] = [prof] * len(camions)
        morceaux.append(camions)
    return pd.concat(morceaux, ignore_index=True)


def reporter_lignes(camions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reporte des lignes sur le jour fixe suivant et regroupe les camions d'un même jour, couple par couple.

    1. Une ligne dont le besoin est après le jour fixe suivant passe dans le camion de ce jour, s'il a la place.
    2. Deux camions d'un couple le même jour sont fusionnés s'ils tiennent dans un seul.

    Pour chaque couple, le résultat n'est gardé que s'il ne coûte pas plus cher.

    Args:
        camions: une ligne par camion (voir ``construire_planning``).

    Returns:
        ``(camions après report, journal)`` ; le journal a une ligne par couple (``lignes_reportees``,
        ``camions_en_moins``, ``gain``, ``report_refuse_car_plus_cher``).
    """
    besoin, poids, volume = besoins["need_date"], besoins["weight"], besoins["volume"]

    def charge_ok(ls: list[int]) -> bool:
        """True si les lignes ``ls`` tiennent dans un camion (poids et volume)."""
        return poids[ls].sum() <= POIDS_MAX + 1e-9 and volume[ls].sum() <= VOLUME_MAX + 1e-9

    def en_cours(groupe: pd.DataFrame) -> list[CamionEnCours]:
        """Camions d'un couple, chacun avec sa propre liste de lignes (modifiable sans toucher au scénario)."""
        return [CamionEnCours(date=d, demarrage=dem, lignes=list(ls))
                for d, dem, ls in zip(groupe["date"], groupe["demarrage"], groupe["lignes"])]

    resultat: list[dict[str, Any]] = []
    journal: list[dict[str, Any]] = []
    for (plant, supplier), groupe in camions.groupby(["plant", "supplier_id"], sort=False):
        plant, supplier = str(plant), str(supplier)
        profil: Profil = groupe["profil"].iloc[0]

        def cout(ls: list[int]) -> float:
            """Prix d'un camion du couple qui transporte les lignes ``ls``."""
            return cout_camion(poids[ls].sum(), supplier)

        cam = en_cours(groupe.sort_values("date"))
        cout_avant: float = sum(cout(c["lignes"]) for c in cam)
        nb_avant, reportees = len(cam), 0
        for c in cam:                                               # 1) report vers le jour fixe suivant
            suivant = prochain_jour_fixe(c["date"], profil)
            cibles = [u for u in cam if u["date"] == suivant and not u["demarrage"]]
            for l in sorted((l for l in c["lignes"] if besoin[l] >= suivant), key=lambda l: -poids[l]):
                for u in cibles:
                    if charge_ok(u["lignes"] + [l]):
                        c["lignes"].remove(l)
                        u["lignes"].append(l)
                        reportees += 1
                        break
        for date in sorted({c["date"] for c in cam}):                # 2) regroupement des camions d'un même jour
            du_jour = [c for c in cam if c["date"] == date and c["lignes"]]
            for a, b in itertools.combinations(du_jour, 2):
                if a["lignes"] and b["lignes"] and charge_ok(a["lignes"] + b["lignes"]):
                    a["lignes"] += b["lignes"]
                    b["lignes"] = []
        apres = [c for c in cam if c["lignes"]]
        cout_apres: float = sum(cout(c["lignes"]) for c in apres)
        garde = cout_apres <= cout_avant + 0.005
        if not garde:
            apres = en_cours(groupe)
        journal.append({"plant": plant, "supplier_id": supplier, "lignes_reportees": reportees if garde else 0,
                        "camions_en_moins": nb_avant - len(apres),
                        "gain": round(cout_avant - cout_apres, 2) if garde else 0.0,
                        "report_refuse_car_plus_cher": not garde and reportees > 0})
        resultat += [{**c, "plant": plant, "supplier_id": supplier, "profil": profil} for c in apres]
    return pd.DataFrame(resultat), pd.DataFrame(journal)


def finaliser(camions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Numérote les camions et calcule leur contenu, leur coût et la date de livraison de chaque ligne.

    Args:
        camions: une ligne par camion, avec ``plant``, ``supplier_id``, ``date``, ``profil`` et ``lignes``.

    Returns:
        ``(planning, lignes)`` :

        - planning : une ligne par camion (``camion_id``, ``poids``, ``volume``, ``nb_lignes``, ``cout``,
          ``jours_fixes``, ``reserve`` = False...) ;
        - lignes : une ligne par besoin (``id_ligne``, ``camion_id``, ``date_livraison``, ``avance_jours``...).
    """
    camions = camions.sort_values(["plant", "date", "supplier_id"]).reset_index(drop=True)
    camions["camion_id"] = range(1, len(camions) + 1)
    affectation = camions[["camion_id", "date", "lignes"]].explode("lignes").set_index("lignes")
    lignes = besoins.join(affectation.rename(columns={"date": "date_livraison"}))
    lignes["avance_jours"] = (lignes["need_date"] - lignes["date_livraison"]).dt.days
    lignes.insert(0, "id_ligne", "L" + lignes.index.astype(str))
    contenu = lignes.groupby("camion_id").agg(poids=("weight", "sum"), volume=("volume", "sum"),
                                              nb_lignes=("weight", "size"))
    planning = camions.drop(columns=[c for c in ["lignes", "poids", "volume", "cout"] if c in camions]).join(contenu, on="camion_id")
    planning["cout"] = [cout_camion(p, s) for p, s in zip(planning["poids"], planning["supplier_id"])]
    planning["jours_fixes"] = planning["profil"].map(nom_profil)
    planning["reserve"] = False
    return planning, lignes


def ajouter_reserves(planning: pd.DataFrame, lignes_planning: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ajoute les camions réservés (lignes sans poids) au planning, numérotés à la suite des camions optimisés.

    Args:
        planning: planning des camions optimisés (voir ``finaliser``).
        lignes_planning: lignes livrées par ces camions.

    Returns:
        ``(planning complet, lignes complètes)``, avec la colonne ``reserve`` ; le planning a aussi
        les colonnes ``jour`` (nom du jour) et ``semaine`` (numéro ISO).
    """
    decalage = int(planning["camion_id"].max())
    reserves = camions_reserves.assign(camion_id=camions_reserves["numero"] + decalage, reserve=True, profil=None,
                                       jours_fixes="réservé : " + camions_reserves["motif"])
    planning_complet = (pd.concat([planning, reserves.drop(columns=["numero", "motif"])], ignore_index=True)
                        .sort_values(["plant", "date", "supplier_id"]).reset_index(drop=True))
    planning_complet["jour"] = planning_complet["date"].dt.day_of_week.map(dict(enumerate(JOURS)))
    planning_complet["semaine"] = planning_complet["date"].dt.isocalendar().week
    lignes_complet = pd.concat([lignes_planning.assign(reserve=False),
                                lignes_reserves.assign(camion_id=lignes_reserves["numero"] + decalage, reserve=True)
                                .drop(columns="numero")], ignore_index=True)
    return planning_complet, lignes_complet
