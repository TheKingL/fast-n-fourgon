"""1.4 Exhaustivité des matériaux livrés et anticipation des besoins.

Mêmes tests que la partie correspondante de data_analysis/milestone4.ipynb.
"""
import numpy as np
import pandas as pd

from moteur import L, P, m

CLES = ["plant", "supplier_id", "material", "unloading_point"]
entree = pd.concat([m.besoins, m.lignes_reserves])                          # planning d'entrée : besoins à livrer
demande = entree.groupby(CLES)["schedule_quantity"].sum()                   # quantité demandée par material
livre = (m.sortie2.rename(columns={"usine": "plant", "fournisseur": "supplier_id", "Material": "material", "Quai": "unloading_point"})
         .groupby(CLES)["Quantité"].sum())                                  # quantité chargée dans les camions (sortie 2)


def test_aucune_ligne_oubliee_ni_doublee():
    assert L["id_ligne"].is_unique
    assert set(L["id_ligne"]) == m.IDS_ATTENDUS
    assert L["camion_id"].notna().all()
    assert m.sortie2["nb_lignes"].sum() == len(m.IDS_ATTENDUS)
    assert set(m.sortie2["camion_id"]) == set(P["camion_id"])


def test_quantite_exacte_par_material():
    assert set(demande.index) == set(livre.index), "material manquant ou inventé"
    ecarts = demande.sub(livre, fill_value=0).abs()
    assert (ecarts < 1e-6).all(), f"{(ecarts >= 1e-6).sum()} materials avec un écart"


def test_poids_total_conserve():
    poids_demande = m.besoins["weight"].sum()
    assert np.isclose(L["weight"].sum(), poids_demande)
    assert abs(m.sortie2["Poids (kg)"].sum() - poids_demande) <= 0.05 * len(m.sortie2)


def test_anticipation_des_besoins():
    avance = (L["need_date"] - L["date_livraison"]).dt.days
    assert (avance == L["avance_jours"]).all()
    assert avance.between(0, 7).all(), avance.describe().to_string()


def test_camion_dans_la_fenetre_de_ses_besoins():
    par_camion = L.groupby("camion_id").agg(premier=("need_date", "min"), dernier=("need_date", "max"),
                                            date=("date_livraison", "first"), nb_dates=("date_livraison", "nunique"))
    assert (par_camion["nb_dates"] == 1).all(), "un camion avec plusieurs dates de livraison"
    assert (par_camion["date"] <= par_camion["premier"]).all()
    assert ((par_camion["dernier"] - par_camion["date"]).dt.days <= 7).all()
    assert (par_camion["date"] == P.set_index("camion_id").loc[par_camion.index, "date"]).all()
