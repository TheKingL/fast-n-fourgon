"""1.2 Tests du respect des contraintes.

Mêmes tests que la partie correspondante de data_analysis/milestone4.ipynb.
"""
import pandas as pd
import pytest

from moteur import J, L, P, m

FONCTIONS = {code_c: fonction for code_c, _, _, fonction in m.CONTRAINTES}
DURES = [code_c for code_c, _, type_c, _ in m.CONTRAINTES if type_c == "dure"]


def violations(code_c, planning, lignes):
    # Violations d'une contrainte (pour C9 : seulement les cas évitables, sans cause justifiée)
    args = (planning, lignes, m.IDS_ATTENDUS) if code_c == "C3" else (planning, lignes)
    v = FONCTIONS[code_c](*args)
    return v[~v["justifie"]] if code_c == "C9" else v


# ---------- Erreurs introduites volontairement, une par contrainte ----------
opti = P[~P["reserve"]]
i0 = opti.index[0]                                                          # un camion optimisé quelconque
multi = L.groupby("camion_id").size().loc[lambda n: n > 1].index[0]         # un camion qui transporte plusieurs lignes
couples_c9 = set(map(tuple, m.c9_un_camion_par_jour(P, L)[["plant", "supplier_id"]].values))
i9 = next(i for i, r in opti.iterrows() if (r["plant"], r["supplier_id"]) not in couples_c9)
i8 = opti.index[0]
un_jour = opti[opti["profil"].map(len) == 1].iloc[0]                       # un couple à 1 jour fixe (pour C11)


def avec_erreur(code_c):
    # Copie du planning et des lignes avec une erreur qui viole la contrainte
    p, l = P.copy(), L.copy()
    if code_c == "C1":
        p.loc[i0, "poids"] = m.POIDS_MAX + 1                                    # camion de 24,5 t + 1 kg
    elif code_c == "C2":
        p.loc[i0, "volume"] = m.VOLUME_MAX + 1                                  # camion de 110,4 m³ + 1 m³
    elif code_c == "C3":
        l = l.drop(index=l.index[0])                                            # ligne oubliée
    elif code_c == "C4":
        l.loc[l.index[l["camion_id"] == multi][0], "supplier_id"] = "SUP_99999"  # ligne d'un autre fournisseur
    elif code_c == "C5":
        l.loc[l.index[0], "date_livraison"] = l.loc[l.index[0], "need_date"] + pd.Timedelta(days=1)   # 1 jour de retard
    elif code_c == "C6":
        l.loc[l.index[0], "date_livraison"] = l.loc[l.index[0], "need_date"] - pd.Timedelta(days=8)   # 8 jours d'avance
    elif code_c == "C7":
        p.loc[i0, "date"] = J("2026-11-21")                                     # camion un samedi
    elif code_c == "C8":
        date, profil = p.loc[i8, "date"], p.loc[i8, "profil"]                   # camion hors de ses jours fixes
        p.loc[i8, "date"] = date + pd.Timedelta(days=next(j for j in range(5) if j not in profil) - date.day_of_week)
    elif code_c == "C9":
        p = pd.concat([p, p.loc[[i9]]], ignore_index=True)                      # 2 camions le même jour sans raison
    elif code_c == "C11":                                                       # profil de 2 jours dont un jamais utilisé
        autre = next(j for j in range(5) if j not in un_jour["profil"])
        meme_couple = (p["plant"] == un_jour["plant"]) & (p["supplier_id"] == un_jour["supplier_id"]) & ~p["reserve"]
        p["profil"] = [tuple(sorted({*prof, autre})) if cible else prof for prof, cible in zip(p["profil"], meme_couple)]
    elif code_c == "C10":
        renfort = p[p["plant"] == m.USINES[0]].head(1).assign(date=J("2026-11-16"))
        p = pd.concat([p] + [renfort] * 15, ignore_index=True)                  # 15 camions de plus un lundi
    return p, l


@pytest.mark.parametrize("contrainte", DURES)
def test_contrainte_dure_respectee(contrainte):
    v = violations(contrainte, P, L)
    assert v.empty, f"{contrainte} : {len(v)} violation(s)\n{v.head()}"


def test_lissage_c10():
    hors = violations("C10", P, L)
    assert len(hors) <= 2, f"{len(hors)} semaines hors tolérance\n{hors}"


def test_c11_profil_utilise_une_semaine_complete():
    optimises = P[~P["reserve"]]
    assert (optimises["profil"].map(len) >= 2).any(), "aucun couple à plusieurs jours fixes : test sans objet"
    for (plant, supplier), camions in optimises.groupby(["plant", "supplier_id"]):
        profil = set(camions["profil"].iloc[0])
        jours_par_semaine = camions.groupby(camions["date"].dt.isocalendar().week)["date"].apply(
            lambda d: set(d.dt.day_of_week))
        assert any(profil <= jours for jours in jours_par_semaine), (plant, supplier, sorted(profil))


@pytest.mark.parametrize("contrainte", list(FONCTIONS))
def test_verification_detecte_erreur(contrainte):
    assert len(violations(contrainte, *avec_erreur(contrainte))) > len(violations(contrainte, P, L))


def test_planning_coherent():
    controles = m.valider_resultats(P, L)
    echecs = controles[controles["Résultat"] != "OK"].index.tolist()
    assert not echecs, echecs


def test_c9_doublons_justifies():
    doublons = m.c9_un_camion_par_jour(P, L)
    besoin_jour = L.dropna(subset=["weight"]).groupby(["plant", "supplier_id", "need_date"])["weight"].sum()
    couples_lourds = set(besoin_jour[besoin_jour > m.POIDS_MAX].index.droplevel("need_date"))
    optimises = P[~P["reserve"]].groupby(["plant", "supplier_id", "date"]).size()
    for r in doublons.itertuples():
        nb_optimises = optimises.get((r.plant, r.supplier_id, r.date), 0)
        assert nb_optimises <= 1 or (r.plant, r.supplier_id) in couples_lourds, (r.plant, r.supplier_id, r.date)
