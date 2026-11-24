"""1.1 Tests unitaires des fonctions.

Mêmes tests que la partie correspondante de data_analysis/milestone4.ipynb.
"""
import numpy as np
import pandas as pd
import pytest

from moteur import J, L, P, lignes_test, m


@pytest.mark.parametrize("valeur, tranches, attendu", [
    (30, m.TRANCHES_KM, "30"),        # borne exacte
    (30.1, m.TRANCHES_KM, "50"),      # juste au-dessus : tranche suivante
    (650, m.TRANCHES_KM, "650"),      # dernière borne
    (651, m.TRANCHES_KM, ">650"),     # au-delà de la grille
    (0, m.TRANCHES_KG, "50"),         # poids nul : première tranche
    (4000, m.TRANCHES_KG, "4000"),
    (4000.5, m.TRANCHES_KG, ">4000"),
])
def test_tranche(valeur, tranches, attendu):
    assert m.tranche(valeur, tranches) == attendu


def test_cout_transport_exemple_rate_sheet():
    assert m.cout_transport(1000, 300) == 335.34


def test_cout_transport_croissant():
    poids = m.TRANCHES_KG + [m.POIDS_PAR_DEFAUT]
    distances = m.TRANCHES_KM + [m.DISTANCE_PAR_DEFAUT]
    grille = np.array([[m.cout_transport(w, d) for w in poids] for d in distances])
    assert (np.diff(grille, axis=1) >= 0).all(), "le prix baisse quand le poids augmente"
    assert (np.diff(grille, axis=0) >= 0).all(), "le prix baisse quand la distance augmente"


def test_cout_camion_valeurs_par_defaut():
    avec_distance = next(s for s in m.distances.index if s not in m.SANS_DISTANCE)
    sans_distance = m.SANS_DISTANCE[0]
    assert m.tranche(m.POIDS_PAR_DEFAUT, m.TRANCHES_KG) == ">4000"
    assert m.tranche(m.DISTANCE_PAR_DEFAUT, m.TRANCHES_KM) == ">650"
    assert m.cout_camion(np.nan, avec_distance) == m.cout_transport(m.POIDS_PAR_DEFAUT, m.distances[avec_distance])
    assert m.cout_camion(1000, sans_distance) == m.cout_transport(1000, m.DISTANCE_PAR_DEFAUT)


@pytest.mark.parametrize("besoin, profil, attendu", [
    ("2026-11-18", (0,), "2026-11-16"),     # besoin mercredi, livraison le lundi -> lundi 16/11
    ("2026-11-20", (0, 3), "2026-11-19"),   # besoin vendredi, livraison lundi + jeudi -> jeudi 19/11
    ("2026-11-09", (3,), "2026-11-05"),     # besoin du 1er jour, jeudi précédent : semaine ajoutée avant le planning
])
def test_date_camion(besoin, profil, attendu):
    assert m.date_camion(J(besoin), profil) == J(attendu)


@pytest.mark.parametrize("profil", m.PROFILS, ids=m.nom_profil)
def test_date_camion_regle_generale(profil):
    for besoin in pd.date_range(m.DEBUT, m.FIN):
        date = m.date_camion(besoin, profil)
        assert date <= besoin, f"{besoin:%d/%m} : livré en retard"
        assert (besoin - date).days <= 7, f"{besoin:%d/%m} : plus de 7 jours d'avance"
        assert date.day_of_week in profil, f"{besoin:%d/%m} : départ hors des jours fixes"
        assert date >= m.DEBUT_LIVRAISONS, f"{besoin:%d/%m} : départ avant le premier jour de livraison"


@pytest.mark.parametrize("date, profil, attendu", [
    ("2026-11-16", (0, 3), "2026-11-19"),   # lundi -> jeudi de la même semaine
    ("2026-11-19", (0, 3), "2026-11-23"),   # jeudi -> lundi suivant
    ("2026-11-16", (0,), "2026-11-23"),     # un seul jour fixe : la semaine suivante
])
def test_prochain_jour_fixe(date, profil, attendu):
    assert m.prochain_jour_fixe(J(date), profil) == J(attendu)


@pytest.mark.parametrize("profil, attendu", [((2,), "Mercredi"), ((0, 3), "Lundi + Jeudi")])
def test_nom_profil(profil, attendu):
    assert m.nom_profil(profil) == attendu


@pytest.mark.parametrize("dates, profil, attendu", [
    (["2026-11-17", "2026-11-20"], (1, 4), True),                  # mardi + vendredi la même semaine
    (["2026-11-17", "2026-11-24"], (1, 4), False),                 # le vendredi n'est jamais utilisé
    (["2026-11-17", "2026-11-27"], (1, 4), False),                 # mardi et vendredi, mais jamais la même semaine
    (["2026-11-17", "2026-11-18", "2026-11-19"], (1, 2, 3), True), # 3 jours la même semaine
    (["2026-11-17", "2026-11-18"], (1, 2, 3), False),              # 3e jour jamais utilisé
    (["2026-11-18"], (2,), True),                                  # un seul jour : toujours utilisé
])
def test_profil_utilise(dates, profil, attendu):
    assert m.profil_utilise([J(d) for d in dates], profil) is attendu


def test_consolider_couple_regroupe_la_semaine():
    camions = m.consolider_couple(lignes_test(("2026-11-16", 500, 2), ("2026-11-17", 300, 1), ("2026-11-20", 200, 1)), (0,))
    assert len(camions) == 1
    assert camions["date"].iloc[0] == J("2026-11-16")
    assert camions["poids"].iloc[0] == 1000


@pytest.mark.parametrize("cas, lignes", [
    ("poids : 3 x 10 t", [("2026-11-16", 10000, 1), ("2026-11-17", 10000, 1), ("2026-11-18", 10000, 1)]),
    ("volume : 2 x 60 m3", [("2026-11-16", 100, 60), ("2026-11-17", 100, 60)]),
])
def test_consolider_couple_capacite(cas, lignes):
    camions = m.consolider_couple(lignes_test(*lignes), (0,))
    assert len(camions) == 2
    assert (camions["poids"] <= m.POIDS_MAX).all() and (camions["volume"] <= m.VOLUME_MAX).all()


@pytest.mark.parametrize("jours_apres, nb_camions", [(7, 1), (8, 2)])
def test_consolider_couple_fenetre_7_jours(jours_apres, nb_camions):
    second = J("2026-11-16") + pd.Timedelta(days=jours_apres)
    camions = m.consolider_couple(lignes_test(("2026-11-16", 100, 1), (second, 100, 1)), (0,))
    assert len(camions) == nb_camions


def test_consolider_couple_conserve_les_lignes():
    rng = np.random.default_rng(0)
    jours_ouvres = pd.date_range("2026-11-09", "2026-12-04", freq="B")
    lignes = lignes_test(*zip(rng.choice(jours_ouvres, 40), rng.uniform(100, 9000, 40), rng.uniform(1, 40, 40)))
    lignes = lignes.sort_values(["need_date", "weight"], ascending=[True, False])
    camions = m.consolider_couple(lignes, (1, 3))
    contenu = [l for c in camions["lignes"] for l in c]
    assert sorted(contenu) == sorted(lignes.index), "ligne perdue ou dupliquée"
    assert np.isclose(camions["poids"].sum(), lignes["weight"].sum())
    assert np.isclose(camions["volume"].sum(), lignes["volume"].sum())
    assert (camions["poids"] <= m.POIDS_MAX).all() and (camions["volume"] <= m.VOLUME_MAX).all()
    for c in camions.itertuples():
        besoins = lignes.loc[c.lignes, "need_date"]
        assert (besoins >= c.date).all() and (besoins <= c.date + m.FENETRE).all()


@pytest.mark.parametrize("semaine, attendu", [
    ([2, 2, 2, 2, 2], 0.0),
    ([3, 2, 2, 2, 1], 0.5),
    ([10, 0, 0, 0, 0], 4.0),
    ([0, 0, 0, 0, 0], 0.0),
])
def test_ecart(semaine, attendu):
    assert m.ecart(semaine) == pytest.approx(attendu)


@pytest.mark.parametrize("semaine, attendu", [
    ([2, 2, 2, 2, 2], False),    # parfaitement régulière
    ([3, 2, 2, 2, 1], False),    # écart d'un seul camion : toléré
    ([10, 0, 0, 0, 0], True),    # tout le même jour
    ([6, 1, 1, 1, 1], True),     # pic le lundi
    ([4, 0, 0, 0, 0], False),    # moins de 5 camions : pas contrôlée
])
def test_hors_tolerance(semaine, attendu):
    assert m.hors_tolerance(np.array([semaine], dtype=float)).tolist() == [attendu]


def test_dispersion():
    reguliere = np.full((m.NB_SEMAINES, 5), 2.0)
    assert m.dispersion(reguliere) == 0
    pic = reguliere.copy()
    pic[m.CONTROLE[0]] = [10, 0, 0, 0, 0]
    assert m.dispersion(pic) > 0
    for semaine in (0, m.NB_SEMAINES - 1):                  # semaine ajoutée et dernière semaine : non contrôlées
        non_controlee = reguliere.copy()
        non_controlee[semaine] = [10, 0, 0, 0, 0]
        assert m.dispersion(non_controlee) == 0
