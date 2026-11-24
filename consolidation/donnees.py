"""Données d'entrée (milestones 1 et 2) : besoins à consolider, camions réservés, baseline, horizon du planning.

Chargées une fois à l'import : ce sont les entrées fixes du moteur, utilisées par tous les autres modules.
"""
import numpy as np
import pandas as pd

from .config import BASELINE_PATH, POIDS_MAX, QUARANTAINE_PATH, SILVER_CLEAN_PATH
from .couts import cout_camion

silver = pd.read_csv(SILVER_CLEAN_PATH, parse_dates=["need_date"])
quarantaine = pd.read_csv(QUARANTAINE_PATH, parse_dates=["need_date"])
N_SILVER = len(silver)
sans_poids = quarantaine["weight"].isna()
a_consolider = ~sans_poids & (quarantaine["weight"] <= POIDS_MAX)   # la ligne de plus de 24,5 t est exclue

# Besoins à consolider : silver + lignes de la quarantaine dont le poids est connu
besoins = (pd.concat([silver, quarantaine.loc[a_consolider, silver.columns]], ignore_index=True)
           .sort_values(["plant", "supplier_id", "need_date", "weight"], ascending=[True, True, True, False])
           [["need_date", "supplier_id", "material", "plant", "unloading_point", "schedule_quantity", "weight", "volume"]])

# Lignes sans poids : un camion réservé par ligne, le jour du besoin
lignes_reserves = quarantaine[sans_poids].drop(columns="flags").reset_index(drop=True)
lignes_reserves["numero"] = range(1, len(lignes_reserves) + 1)
lignes_reserves["id_ligne"] = "Q" + lignes_reserves["numero"].astype(str)
lignes_reserves["date_livraison"], lignes_reserves["avance_jours"] = lignes_reserves["need_date"], 0
camions_reserves = pd.DataFrame({
    "numero": lignes_reserves["numero"], "plant": lignes_reserves["plant"], "supplier_id": lignes_reserves["supplier_id"],
    "date": lignes_reserves["need_date"], "demarrage": False, "nb_lignes": 1, "poids": np.nan,
    "volume": lignes_reserves["volume"], "cout": [cout_camion(np.nan, s) for s in lignes_reserves["supplier_id"]],
    "motif": "poids inconnu"})
COUT_RESERVE, NB_RESERVE = camions_reserves["cout"].sum(), len(camions_reserves)


def avec_reserves(camions):
    return pd.concat([camions, camions_reserves.drop(columns="numero")], ignore_index=True)


# Baseline du milestone 2 (sans ses camions réservés, comptés à part : les mêmes pour toutes les versions)
camions_base = pd.read_csv(BASELINE_PATH, parse_dates=["date"])
assert camions_base["reserve"].sum() == NB_RESERVE
camions_base = camions_base[~camions_base["reserve"]].copy()
camions_base["cout"] = [cout_camion(p, s) for p, s in zip(camions_base["poids"], camions_base["supplier_id"])]
COUT_BASELINE = camions_base["cout"].sum()

# Horizon du planning
DEBUT, FIN = besoins["need_date"].min(), besoins["need_date"].max()   # lundi 09/11 -> vendredi 18/12
SEMAINES = sorted(besoins["need_date"].dt.isocalendar().week.unique())
NB_SEMAINES = len(SEMAINES)
CONTROLE = list(range(NB_SEMAINES - 1))   # la dernière semaine est incomplète : pas contrôlée
USINES = sorted(besoins["plant"].unique())
IDS_ATTENDUS = {f"L{i}" for i in besoins.index} | set(lignes_reserves["id_ligne"])
