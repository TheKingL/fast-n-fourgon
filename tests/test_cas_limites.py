"""1.3 Cas limites et hypothèses de données manquantes.

Mêmes tests que la partie correspondante de data_analysis/milestone4.ipynb.
"""
import numpy as np
import pandas as pd

from moteur import L, P, lignes_test, m

q = m.quarantaine


def test_ligne_trop_lourde_exclue():
    lourdes = q[q["weight"] > m.POIDS_MAX]
    assert len(lourdes) == 1, f"{len(lourdes)} ligne(s) de plus de 24,5 t"
    cles = ["need_date", "supplier_id", "material", "plant", "unloading_point"]
    assert lourdes[cles].merge(L[cles]).empty, "la ligne lourde est livrée"


def test_poids_manquant_camion_reserve():
    reserves, lignes_r = P[P["reserve"]], L[L["reserve"]]
    assert len(reserves) == q["weight"].isna().sum() == len(lignes_r)
    assert (lignes_r.groupby("camion_id").size() == 1).all()
    assert (lignes_r["date_livraison"] == lignes_r["need_date"]).all()
    attendu = [m.cout_transport(m.POIDS_PAR_DEFAUT, m.distances[s]) for s in reserves["supplier_id"]]
    assert np.allclose(reserves["cout"], attendu)


def test_distance_manquante():
    camions = P[P["supplier_id"].isin(m.SANS_DISTANCE)]
    assert len(camions) > 0, "aucun fournisseur sans distance dans le planning"
    poids = camions["poids"].fillna(m.POIDS_PAR_DEFAUT)
    assert np.allclose(camions["cout"], [m.cout_transport(w, m.DISTANCE_PAR_DEFAUT) for w in poids])
    assert m.sortie1.loc[m.sortie1["Fournisseur"].isin(m.SANS_DISTANCE), "Distance"].isna().all()


def test_semaine_ajoutee_avant_le_planning():
    avant = P[P["date"] < m.DEBUT]
    assert len(avant) > 0
    assert (avant["date"] >= m.DEBUT_LIVRAISONS).all(), "camion avant le premier jour de livraison"
    assert not avant["reserve"].any()
    premiere = L[L["camion_id"].isin(avant["camion_id"])].groupby("camion_id")["need_date"].min()
    assert (premiere >= m.DEBUT).all(), "besoin hors planning dans un camion de la semaine ajoutée"


def test_quantite_nulle_exclue():
    brut = pd.read_csv(m.DATA / "bronze" / "released_schedule.csv")
    assert (brut["schedule_quantity"] <= 0).any(), "le cas n'existe pas dans les données brutes"
    assert (L["schedule_quantity"] > 0).all()
    assert (m.sortie2["Quantité"] > 0).all()


def test_couple_a_une_seule_ligne():
    assert len(m.consolider_couple(lignes_test(("2026-11-18", 500, 2)), (0,))) == 1
    nb_lignes = m.besoins.groupby(["plant", "supplier_id"]).size()
    seuls = nb_lignes[nb_lignes == 1].index
    assert len(seuls) > 0
    for plant, supplier in seuls:
        camions = P[(P["plant"] == plant) & (P["supplier_id"] == supplier) & ~P["reserve"]]
        assert len(camions) == 1 and camions["nb_lignes"].iloc[0] == 1, (plant, supplier)
