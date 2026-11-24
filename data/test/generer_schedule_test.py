"""Génère un schedule de test (``schedule_test.csv``) à partir du schedule du projet, avec des modifications connues.

Lancement, depuis la racine du dépôt : ``python data/test/generer_schedule_test.py``
Le résultat est toujours le même (graine fixe), pour que les tests puissent s'appuyer dessus.

Modifications par rapport à ``data/bronze/released_schedule.csv`` :

1. Demande de l'usine PLT_002 augmentée de 20 % (quantité et poids).
2. Fournisseur SUP_00091 retiré (il ne livre plus).
3. Nouveau fournisseur SUP_00200, absent du fichier des distances : il reprend les besoins de SUP_00080,
   livrés à PLT_003 (test du tarif par défaut > 650 km et du flag NO_DISTANCE).
4. Une semaine de plus : les besoins de la semaine du 14/12 sont recopiés sur la semaine du 21/12.
5. Problèmes de qualité ajoutés : 25 poids manquants, 3 volumes manquants, 40 quantités mises à 0,
   1 ligne de 31 t (plus lourde qu'un camion).
"""
from pathlib import Path

import numpy as np
import pandas as pd

RACINE = Path(__file__).resolve().parents[2]
ENTREE = RACINE / "data" / "bronze" / "released_schedule.csv"
SORTIE = Path(__file__).resolve().parent / "schedule_test.csv"
GRAINE = 42


def generer() -> pd.DataFrame:
    """Construit le schedule de test.

    Returns:
        Le schedule modifié, au format de ``released_schedule.csv``.
    """
    alea = np.random.default_rng(GRAINE)
    s = pd.read_csv(ENTREE, encoding="utf-8-sig")
    colonnes = list(s.columns)
    s["date"] = pd.to_datetime(s["date"])

    # 1. PLT_002 : +20 % de demande
    plt2 = s["plant"] == "PLT_002"
    s.loc[plt2, "schedule_quantity"] = (s.loc[plt2, "schedule_quantity"] * 1.2).round()
    s.loc[plt2, "weight"] = (s.loc[plt2, "weight"] * 1.2).round(3)

    # 2. SUP_00091 ne livre plus
    s = s[s["supplier_id"] != "SUP_00091"]

    # 3. Nouveau fournisseur sans distance connue
    nouveau = s[s["supplier_id"] == "SUP_00080"].assign(supplier_id="SUP_00200", plant="PLT_003")

    # 4. Une semaine de plus : la semaine du 14/12 recopiée sur celle du 21/12
    semaine = s[(s["date"] >= "2026-12-14") & (s["date"] <= "2026-12-18")]
    semaine_suivante = semaine.assign(date=semaine["date"] + pd.Timedelta(days=7))

    s = pd.concat([s, nouveau, semaine_suivante], ignore_index=True)

    # 5. Problèmes de qualité, sur des lignes de besoin réelles (quantité > 0)
    utiles = s.index[s["schedule_quantity"] > 0]
    choisies = alea.choice(utiles, size=25 + 3 + 40 + 1, replace=False)
    sans_poids, sans_volume, a_zero, trop_lourde = np.split(choisies, [25, 28, 68])
    s.loc[sans_poids, "weight"] = np.nan
    s.loc[sans_volume, "volume"] = np.nan
    s.loc[a_zero, ["schedule_quantity", "weight"]] = 0
    s.loc[trop_lourde, "weight"] = 31000.0

    s = s.sort_values(["date", "plant", "supplier_id", "material"]).reset_index(drop=True)
    s["date"] = s["date"].dt.strftime("%Y-%m-%d")
    return s[colonnes]


if __name__ == "__main__":
    schedule = generer()
    schedule.to_csv(SORTIE, index=False)
    print(f"{SORTIE.relative_to(RACINE)} : {len(schedule)} lignes, {schedule['supplier_id'].nunique()} fournisseurs, "
          f"du {schedule['date'].min()} au {schedule['date'].max()}")
