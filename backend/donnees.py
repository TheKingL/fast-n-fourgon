"""Données d'entrée du moteur (milestones 1 et 2), chargées une seule fois à l'import du module.

- ``besoins`` : lignes de besoin à consolider (silver + lignes de la quarantaine dont le poids est connu) ;
- ``lignes_reserves`` / ``camions_reserves`` : lignes sans poids, livrées chacune par un camion réservé ;
- ``camions_base`` : baseline du milestone 2, la référence des économies ;
- horizon du planning : ``DEBUT``, ``FIN``, ``SEMAINES``, ``USINES``...
"""
import numpy as np
import pandas as pd

from .config import BASELINE_PATH, POIDS_MAX, QUARANTAINE_PATH, SILVER_CLEAN_PATH
from .couts import cout_camion

silver: pd.DataFrame = pd.read_csv(SILVER_CLEAN_PATH, parse_dates=["need_date"])
"""Besoins nettoyés au milestone 1."""
quarantaine: pd.DataFrame = pd.read_csv(QUARANTAINE_PATH, parse_dates=["need_date"])
"""Lignes mises en quarantaine au milestone 1 (colonne ``flags`` = raison)."""
N_SILVER: int = len(silver)
"""Nombre de lignes du fichier silver."""
sans_poids: pd.Series = quarantaine["weight"].isna()
"""Masque des lignes de la quarantaine sans poids."""
a_consolider: pd.Series = ~sans_poids & (quarantaine["weight"] <= POIDS_MAX)   # la ligne de plus de 24,5 t est exclue
"""Masque des lignes de la quarantaine à consolider : poids connu et au plus 24,5 t."""

besoins: pd.DataFrame = (
    pd.concat([silver, quarantaine.loc[a_consolider, silver.columns]], ignore_index=True)
    .sort_values(["plant", "supplier_id", "need_date", "weight"], ascending=[True, True, True, False])
    [["need_date", "supplier_id", "material", "plant", "unloading_point", "schedule_quantity", "weight", "volume"]])
"""Besoins à consolider, triés par couple, date puis poids décroissant. L'index identifie la ligne (``L<index>``)."""

lignes_reserves: pd.DataFrame = quarantaine[sans_poids].drop(columns="flags").reset_index(drop=True)
"""Lignes sans poids : chacune est livrée par son propre camion réservé, le jour du besoin (identifiant ``Q<numero>``)."""
lignes_reserves["numero"] = range(1, len(lignes_reserves) + 1)
lignes_reserves["id_ligne"] = "Q" + lignes_reserves["numero"].astype(str)
lignes_reserves["date_livraison"], lignes_reserves["avance_jours"] = lignes_reserves["need_date"], 0

camions_reserves: pd.DataFrame = pd.DataFrame({
    "numero": lignes_reserves["numero"], "plant": lignes_reserves["plant"], "supplier_id": lignes_reserves["supplier_id"],
    "date": lignes_reserves["need_date"], "nb_lignes": 1, "poids": np.nan,
    "volume": lignes_reserves["volume"], "cout": [cout_camion(np.nan, s) for s in lignes_reserves["supplier_id"]],
    "motif": "poids inconnu"})
"""Un camion réservé par ligne sans poids, chiffré au tarif ``> 4 000 kg``."""
COUT_RESERVE: float = camions_reserves["cout"].sum()
"""Coût total des camions réservés, en € (le même pour toutes les versions du planning)."""
NB_RESERVE: int = len(camions_reserves)
"""Nombre de camions réservés."""


def avec_reserves(camions: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les camions réservés à une liste de camions.

    Args:
        camions: une ligne par camion (au moins ``plant``, ``supplier_id``, ``date``, ``cout``).

    Returns:
        Les camions suivis des camions réservés, avec un nouvel index.
    """
    return pd.concat([camions, camions_reserves.drop(columns="numero")], ignore_index=True)


# Baseline du milestone 2 (sans ses camions réservés, comptés à part : les mêmes pour toutes les versions)
camions_base: pd.DataFrame = pd.read_csv(BASELINE_PATH, parse_dates=["date"])
assert camions_base["reserve"].sum() == NB_RESERVE
camions_base = camions_base[~camions_base["reserve"]].copy()
"""Camions de la baseline du milestone 2, hors camions réservés, avec leur coût recalculé (colonne ``cout``)."""
camions_base["cout"] = [cout_camion(p, s) for p, s in zip(camions_base["poids"], camions_base["supplier_id"])]
COUT_BASELINE: float = camions_base["cout"].sum()
"""Coût de la baseline hors camions réservés, en €."""

# Horizon du planning
DEBUT: pd.Timestamp = besoins["need_date"].min()   # lundi 09/11
"""Premier jour du planning des besoins."""
DEBUT_LIVRAISONS: pd.Timestamp = DEBUT - pd.Timedelta(days=7)   # lundi 02/11
"""Premier jour où un camion peut partir : une semaine est ajoutée avant le planning, pour que les premiers besoins
partent eux aussi un jour fixe (le dernier jour fixe avant un besoin est toujours à moins de 7 jours)."""
FIN: pd.Timestamp = besoins["need_date"].max()     # vendredi 18/12
"""Dernier jour de l'horizon du planning."""
SEMAINES: list[int] = sorted({int(w) for w in besoins["need_date"].dt.isocalendar().week}
                             | {int(DEBUT_LIVRAISONS.isocalendar().week)})
"""Numéros de semaine ISO de l'horizon, dans l'ordre, semaine ajoutée avant le planning comprise."""
NB_SEMAINES: int = len(SEMAINES)
"""Nombre de semaines de l'horizon."""
CONTROLE: list[int] = list(range(1, NB_SEMAINES - 1))   # semaine ajoutée et dernière semaine incomplètes : pas contrôlées
"""Positions (dans ``SEMAINES``) des semaines contrôlées pour le lissage : toutes sauf la semaine ajoutée avant le
planning (elle ne reçoit que quelques livraisons anticipées, jamais le lundi) et la dernière, incomplètes."""
USINES: list[str] = sorted(besoins["plant"].unique())
"""Codes des usines."""
IDS_ATTENDUS: set[str] = {f"L{i}" for i in besoins.index} | set(lignes_reserves["id_ligne"])
"""Identifiants de toutes les lignes qui doivent être livrées (``L...`` consolidées, ``Q...`` réservées)."""
