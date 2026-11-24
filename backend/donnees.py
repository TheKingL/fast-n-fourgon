"""Données d'entrée du moteur : besoins à consolider, camions réservés, baseline, horizon du planning.

Les données sont chargées par ``charger`` (à partir d'un schedule nettoyé et de sa baseline) ; à l'import,
le module charge les fichiers du projet (``data/silver`` et ``data/baseline``). Les autres modules lisent
toujours ces valeurs par ``donnees.<nom>`` au moment du calcul : un nouveau ``charger`` change donc
l'entrée de tout le moteur.

- ``besoins`` : lignes de besoin à consolider (silver + lignes de la quarantaine dont le poids est connu) ;
- ``lignes_reserves`` / ``camions_reserves`` : lignes sans poids ou sans volume, livrées chacune par un camion réservé ;
- ``camions_base`` : baseline du milestone 2, la référence des économies ;
- horizon du planning : ``DEBUT``, ``FIN``, ``SEMAINES``, ``USINES``...
"""
import numpy as np
import pandas as pd

from .config import BASELINE_PATH, POIDS_MAX, QUARANTAINE_PATH, SILVER_CLEAN_PATH
from .couts import cout_camion

silver: pd.DataFrame
"""Besoins nettoyés (silver clean)."""
quarantaine: pd.DataFrame
"""Lignes mises en quarantaine au nettoyage (colonne ``flags`` = raison)."""
N_SILVER: int
"""Nombre de lignes du silver clean."""
besoins: pd.DataFrame
"""Besoins à consolider, triés par couple, date puis poids décroissant. L'index identifie la ligne (``L<index>``)."""
lignes_reserves: pd.DataFrame
"""Lignes sans poids ou sans volume : chacune est livrée par son propre camion réservé, le jour du besoin
(identifiant ``Q<numero>``)."""
camions_reserves: pd.DataFrame
"""Un camion réservé par ligne sans poids ou sans volume ; poids inconnu -> tarif ``> 4 000 kg``, sinon son poids."""
COUT_RESERVE: float
"""Coût total des camions réservés, en € (le même pour toutes les versions du planning)."""
NB_RESERVE: int
"""Nombre de camions réservés."""
camions_base: pd.DataFrame
"""Camions de la baseline, hors camions réservés, avec leur coût (colonne ``cout``)."""
COUT_BASELINE: float
"""Coût de la baseline hors camions réservés, en €."""
DEBUT: pd.Timestamp
"""Premier jour du planning des besoins."""
DEBUT_LIVRAISONS: pd.Timestamp
"""Premier jour où un camion peut partir : une semaine est ajoutée avant le planning, pour que les premiers besoins
partent eux aussi un jour fixe (le dernier jour fixe avant un besoin est toujours à moins de 7 jours)."""
FIN: pd.Timestamp
"""Dernier jour de l'horizon du planning."""
SEMAINES: list[int]
"""Numéros de semaine ISO de l'horizon, dans l'ordre, semaine ajoutée avant le planning comprise."""
NB_SEMAINES: int
"""Nombre de semaines de l'horizon."""
CONTROLE: list[int]
"""Positions (dans ``SEMAINES``) des semaines contrôlées pour le lissage : toutes sauf la semaine ajoutée avant le
planning (elle ne reçoit que quelques livraisons anticipées, jamais le lundi) et la dernière, incomplètes."""
USINES: list[str]
"""Codes des usines."""
IDS_ATTENDUS: set[str]
"""Identifiants de toutes les lignes qui doivent être livrées (``L...`` consolidées, ``Q...`` réservées)."""


def charger(silver_clean: pd.DataFrame, lignes_quarantaine: pd.DataFrame, baseline: pd.DataFrame) -> None:
    """Charge les données d'entrée du moteur.

    Args:
        silver_clean: lignes saines (voir ``nettoyage.nettoyer``).
        lignes_quarantaine: lignes en quarantaine, avec la colonne ``flags``.
        baseline: camions de la baseline, réservés compris (voir ``baseline.construire_baseline``).
    """
    global silver, quarantaine, N_SILVER, besoins, lignes_reserves, camions_reserves, COUT_RESERVE, NB_RESERVE
    global camions_base, COUT_BASELINE, DEBUT, DEBUT_LIVRAISONS, FIN, SEMAINES, NB_SEMAINES, CONTROLE, USINES, IDS_ATTENDUS

    silver, quarantaine = silver_clean, lignes_quarantaine
    N_SILVER = len(silver)
    poids = quarantaine["weight"]
    # Poids ou volume inconnu : impossible de garantir que la ligne tient avec d'autres -> camion réservé
    a_reserver = poids.isna() | (quarantaine["volume"].isna() & (poids <= POIDS_MAX))
    a_consolider = ~a_reserver & (poids <= POIDS_MAX)   # la ligne de plus de 24,5 t est exclue

    # Besoins à consolider : silver + lignes de la quarantaine dont le poids est connu
    besoins = (pd.concat([silver, quarantaine.loc[a_consolider, silver.columns]], ignore_index=True)
               .sort_values(["plant", "supplier_id", "need_date", "weight"], ascending=[True, True, True, False])
               [["need_date", "supplier_id", "material", "plant", "unloading_point", "schedule_quantity", "weight",
                 "volume"]])

    # Lignes sans poids ou sans volume : un camion réservé par ligne, le jour du besoin
    lignes_reserves = quarantaine[a_reserver].drop(columns="flags").reset_index(drop=True)
    lignes_reserves["numero"] = range(1, len(lignes_reserves) + 1)
    lignes_reserves["id_ligne"] = "Q" + lignes_reserves["numero"].astype(str)
    lignes_reserves["date_livraison"], lignes_reserves["avance_jours"] = lignes_reserves["need_date"], 0
    camions_reserves = pd.DataFrame({
        "numero": lignes_reserves["numero"], "plant": lignes_reserves["plant"],
        "supplier_id": lignes_reserves["supplier_id"], "date": lignes_reserves["need_date"], "nb_lignes": 1, "poids": lignes_reserves["weight"].astype(float), "volume": lignes_reserves["volume"],
        "cout": [cout_camion(p, s) for p, s in zip(lignes_reserves["weight"], lignes_reserves["supplier_id"])],
        "motif": np.where(lignes_reserves["weight"].isna(), "poids inconnu", "volume inconnu")})
    COUT_RESERVE, NB_RESERVE = float(camions_reserves["cout"].sum()), len(camions_reserves)

    # Baseline (sans ses camions réservés, comptés à part : les mêmes pour toutes les versions)
    assert baseline["reserve"].sum() == NB_RESERVE
    camions_base = baseline[~baseline["reserve"]].copy()
    camions_base["cout"] = [cout_camion(p, s) for p, s in zip(camions_base["poids"], camions_base["supplier_id"])]
    COUT_BASELINE = float(camions_base["cout"].sum())

    # Horizon du planning
    DEBUT, FIN = besoins["need_date"].min(), besoins["need_date"].max()
    DEBUT_LIVRAISONS = DEBUT - pd.Timedelta(days=7)
    SEMAINES = sorted({int(w) for w in besoins["need_date"].dt.isocalendar().week}
                      | {int(DEBUT_LIVRAISONS.isocalendar().week)})
    NB_SEMAINES = len(SEMAINES)
    CONTROLE = list(range(1, NB_SEMAINES - 1))   # semaine ajoutée et dernière semaine incomplètes : pas contrôlées
    USINES = sorted(besoins["plant"].unique())
    IDS_ATTENDUS = {f"L{i}" for i in besoins.index} | set(lignes_reserves["id_ligne"])


def charger_fichiers() -> None:
    """Charge les données du projet : ``data/silver`` (milestone 1) et ``data/baseline`` (milestone 2)."""
    charger(pd.read_csv(SILVER_CLEAN_PATH, parse_dates=["need_date"]),
            pd.read_csv(QUARANTAINE_PATH, parse_dates=["need_date"]),
            pd.read_csv(BASELINE_PATH, parse_dates=["date"]))


def avec_reserves(camions: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les camions réservés à une liste de camions.

    Args:
        camions: une ligne par camion (au moins ``plant``, ``supplier_id``, ``date``, ``cout``).

    Returns:
        Les camions suivis des camions réservés, avec un nouvel index.
    """
    return pd.concat([camions, camions_reserves.drop(columns="numero")], ignore_index=True)


charger_fichiers()
