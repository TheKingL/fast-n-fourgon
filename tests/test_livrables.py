"""1.5 Format des livrables (`data/gold`).

Mêmes tests que la partie correspondante de data_analysis/milestone4.ipynb.
"""
import numpy as np
import pandas as pd
import pytest

from moteur import J, L, P, lignes_test, m

SORTIE1 = m.SORTIE / "sortie1_profils.csv"
SORTIE2 = m.SORTIE / "sortie2_camions.csv"
COLONNES_SORTIE1 = ["Fournisseur", "Usine", "Distance", "Livraisons / sem. actuelles", "Fréquence cible", "Jours",
                    "Camions / sem.", "Remplissage poids"]
COLONNES_SORTIE2 = ["camion_id", "usine", "fournisseur", "date_livraison", "jour", "Material", "Quai", "Besoins regroupés",
                    "nb_lignes", "Quantité", "Poids (kg)", "reserve"]


def lire_sortie1():
    assert SORTIE1.exists(), f"{SORTIE1} absent : lancer python main.py"
    return pd.read_csv(SORTIE1)


def lire_sortie2():
    assert SORTIE2.exists(), f"{SORTIE2} absent : lancer python main.py"
    return pd.read_csv(SORTIE2, parse_dates=["date_livraison"], date_format="%Y-%m-%d")


def test_sortie1_structure():
    s1 = lire_sortie1()
    assert list(s1.columns) == COLONNES_SORTIE1
    assert not s1.duplicated(["Fournisseur", "Usine"]).any(), "couple en double"
    assert len(s1) == m.besoins.groupby(["plant", "supplier_id"]).ngroups


def test_sortie1_valeurs():
    s1 = lire_sortie1()
    assert s1["Fournisseur"].str.fullmatch(r"SUP_\d{5}").all()
    assert s1["Usine"].str.fullmatch(r"PLT_\d{3}").all()
    sans = s1["Fournisseur"].isin(m.SANS_DISTANCE)
    assert s1.loc[sans, "Distance"].isna().all() and (s1.loc[~sans, "Distance"] > 0).all()
    assert (s1["Livraisons / sem. actuelles"] > 0).all()
    assert s1["Fréquence cible"].isin(range(1, m.JOURS_FIXES_MAX + 1)).all()
    jours = s1["Jours"].str.split(" + ", regex=False)
    assert jours.map(lambda j: set(j) <= set(m.JOURS)).all(), "jour inconnu"
    assert jours.map(lambda j: [m.JOURS.index(x) for x in j] == sorted({m.JOURS.index(x) for x in j})).all()
    assert (jours.map(len) == s1["Fréquence cible"]).all(), "nombre de jours différent de la fréquence"
    assert (s1["Camions / sem."] > 0).all()
    assert s1["Remplissage poids"].between(0, 1, inclusive="right").all()


def test_sortie2_structure():
    s2 = lire_sortie2()
    assert list(s2.columns) == COLONNES_SORTIE2
    assert pd.api.types.is_integer_dtype(s2["camion_id"]) and pd.api.types.is_integer_dtype(s2["nb_lignes"])
    assert pd.api.types.is_datetime64_any_dtype(s2["date_livraison"]) and s2["date_livraison"].notna().all()
    assert (s2["jour"] == s2["date_livraison"].dt.day_of_week.map(dict(enumerate(m.JOURS)))).all()
    assert s2["usine"].str.fullmatch(r"PLT_\d{3}").all() and s2["fournisseur"].str.fullmatch(r"SUP_\d{5}").all()
    assert s2["Material"].str.fullmatch(r"MAT_\d{6}").all() and s2["Quai"].str.fullmatch(r"ULP_\d{4}").all()
    assert (s2["Quantité"] > 0).all() and (s2["nb_lignes"] >= 1).all()
    assert s2["reserve"].dtype == bool
    assert s2.loc[s2["reserve"], "Poids (kg)"].isna().all()
    assert (s2.loc[~s2["reserve"], "Poids (kg)"] >= 0).all()
    assert not s2.duplicated(["camion_id", "Material", "Quai"]).any()


def test_sortie2_besoins_regroupes():
    s2 = lire_sortie2()
    erreurs = []
    for i, (besoins, livraison, nb) in enumerate(zip(s2["Besoins regroupés"], s2["date_livraison"], s2["nb_lignes"])):
        dates = pd.to_datetime(besoins.split(", "), format="%Y-%m-%d")
        if not (1 <= len(dates) <= nb and dates.is_unique and dates.is_monotonic_increasing):
            erreurs.append((i, besoins, "liste mal formée"))
        elif dates.min() < livraison or (dates.max() - livraison).days > 7:
            erreurs.append((i, besoins, f"hors fenêtre de la livraison du {livraison:%d/%m}"))
    assert not erreurs, erreurs[:5]


def test_livrables_a_jour():
    pd.testing.assert_frame_equal(lire_sortie1(), m.sortie1, check_dtype=False)
    pd.testing.assert_frame_equal(lire_sortie2(), m.sortie2, check_dtype=False)
