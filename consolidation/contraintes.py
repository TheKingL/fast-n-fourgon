"""Vérification des contraintes C1 à C10 et cohérence du planning final.

Chaque fonction cX retourne les cas qui violent la contrainte (table vide = contrainte respectée).
"""
import numpy as np
import pandas as pd

from .charge import charges_camions, ecart, hors_tolerance
from .config import FENETRE, JOURS_FIXES_MAX, POIDS_MAX, VOLUME_MAX
from .couts import cout_camion, cout_total
from .donnees import CONTROLE, DEBUT, FIN, NB_RESERVE, SEMAINES, USINES, besoins


def optimises(planning):
    # Camions construits par le moteur (sans les camions réservés de la quarantaine)
    return planning[~planning["reserve"]]


def c1_poids(planning, lignes):
    p = optimises(planning)
    return p[p["poids"] > POIDS_MAX + 1e-6]


def c2_volume(planning, lignes):
    return planning[planning["volume"] > VOLUME_MAX + 1e-6]


def c3_exhaustivite(planning, lignes, ids_attendus):
    # Lignes sans camion, livrées deux fois, ou absentes
    sans_camion = lignes[lignes["camion_id"].isna()].assign(probleme="sans camion")
    doublons = lignes[lignes["id_ligne"].duplicated(keep=False)].assign(probleme="livrée plusieurs fois")
    absentes = pd.DataFrame({"id_ligne": sorted(set(ids_attendus) - set(lignes["id_ligne"])), "probleme": "absente"})
    inconnues = lignes[~lignes["id_ligne"].isin(ids_attendus)].assign(probleme="ligne inconnue")
    return pd.concat([sans_camion, doublons, absentes, inconnues], ignore_index=True)


def c4_un_couple(planning, lignes):
    nb_couples = lignes.groupby("camion_id")[["plant", "supplier_id"]].nunique().max(axis=1)
    return nb_couples[nb_couples > 1].rename("couples").reset_index()


def c5_retard(planning, lignes):
    return lignes[lignes["date_livraison"] > lignes["need_date"]]


def c6_avance(planning, lignes):
    return lignes[lignes["need_date"] - lignes["date_livraison"] > FENETRE]


def c7_jours_ouvres(planning, lignes):
    d = planning["date"]
    return planning[(d.dt.day_of_week >= 5) | (d < DEBUT) | (d > FIN)]


def c8_jours_fixes(planning, lignes):
    p = optimises(planning)
    mauvais_profil = ~p["profil"].map(len).between(1, JOURS_FIXES_MAX)
    hors_profil = np.array([not dem and d.day_of_week not in prof
                            for d, prof, dem in zip(p["date"], p["profil"], p["demarrage"])], dtype=bool)
    return p[mauvais_profil | hors_profil]


def c9_un_camion_par_jour(planning, lignes):
    # Jours où un couple a 2 camions ou plus. 'justifie' = le besoin d'un seul jour du couple dépasse
    # 24,5 t : 2 camions sont alors inévitables
    par_jour = optimises(planning).groupby(["plant", "supplier_id", "date"]).size()
    trop = par_jour[par_jour > 1].rename("camions").reset_index()
    besoin_jour = lignes.dropna(subset=["weight"]).groupby(["plant", "supplier_id", "need_date"])["weight"].sum()
    impossibles = set(besoin_jour[besoin_jour > POIDS_MAX].index.droplevel("need_date"))
    trop["justifie"] = [(p, s) in impossibles for p, s in zip(trop["plant"], trop["supplier_id"])]
    return trop


def c10_lissage(planning, lignes):
    # Semaines hors tolérance, par usine (tous les camions reçus, démarrage et réservés compris)
    lignes_hors = []
    for plant, charge in charges_camions(planning).items():
        hors = hors_tolerance(charge)
        for w in CONTROLE:
            if hors[w]:
                lignes_hors.append({"plant": plant, "semaine": SEMAINES[w], "ecart": ecart(charge[w]),
                                    "camions_par_jour": charge[w].astype(int).tolist()})
    return pd.DataFrame(lignes_hors)


CONTRAINTES = [
    ("C1", "Poids ≤ 24,5 t", "dure", c1_poids),
    ("C2", "Volume ≤ 110,4 m³", "dure", c2_volume),
    ("C3", "Chaque ligne livrée une fois, entière", "dure", c3_exhaustivite),
    ("C4", "Un seul couple par camion", "dure", c4_un_couple),
    ("C5", "Jamais de retard", "dure", c5_retard),
    ("C6", "Au plus 7 jours d'avance", "dure", c6_avance),
    ("C7", "Jour ouvré, dans l'horizon", "dure", c7_jours_ouvres),
    ("C8", "Jours fixes (1 ou 2 par couple)", "dure", c8_jours_fixes),
    ("C9", "Au plus 1 camion par couple et par jour", "dure", c9_un_camion_par_jour),
    ("C10", "Lissage (écart ≤ 35 %)", "souple", c10_lissage),
]


def verifier_contraintes(planning, lignes, ids_attendus):
    # Tableau de synthèse : nombre de violations de chaque contrainte
    resultats = []
    for code_c, nom, type_c, fonction in CONTRAINTES:
        args = (planning, lignes, ids_attendus) if fonction is c3_exhaustivite else (planning, lignes)
        violations = fonction(*args)
        remarque = ""
        if fonction is c9_un_camion_par_jour:
            remarque = f"{int(violations['justifie'].sum())} cas inévitables (besoin d'un jour > 24,5 t)"
            violations = violations[~violations["justifie"]]
        if fonction is c10_lissage:
            remarque = f"sur {len(USINES) * len(CONTROLE)} semaines contrôlées"
        nb = len(violations)
        statut = "respectée" if nb == 0 else ("violée" if type_c == "dure" else f"{nb} semaine(s) hors tolérance")
        resultats.append({"Contrainte": code_c, "Description": nom, "Type": type_c, "Violations": nb,
                          "Statut": statut, "Remarque": remarque})
    return pd.DataFrame(resultats).set_index("Contrainte")


def valider_resultats(planning, lignes):
    # Cohérence du planning final : contenu des camions, poids livré, coût
    opti, lignes_opti = optimises(planning), lignes[~lignes["reserve"]]
    contenu = lignes_opti.groupby("camion_id").agg(poids=("weight", "sum"), volume=("volume", "sum"), nb=("weight", "size"))
    p = opti.set_index("camion_id")
    controles = {
        "Chaque camion optimisé contient au moins une ligne": opti["camion_id"].isin(contenu.index).all(),
        "Poids de chaque camion = somme des poids de ses lignes": np.allclose(p["poids"], contenu.loc[p.index, "poids"]),
        "Volume de chaque camion = somme des volumes de ses lignes": np.allclose(p["volume"], contenu.loc[p.index, "volume"]),
        "Poids total livré = poids total des besoins": np.isclose(lignes_opti["weight"].sum(), besoins["weight"].sum()),
        "Un camion réservé par ligne sans poids": (lignes[lignes["reserve"]].groupby("camion_id").size() == 1).all()
                                                   and planning["reserve"].sum() == NB_RESERVE,
        "Coût de chaque camion = grille tarifaire": np.allclose(
            planning["cout"], [cout_camion(w, s) for w, s in zip(planning["poids"], planning["supplier_id"])]),
        "Coût total = somme des coûts des camions": np.isclose(planning["cout"].sum(), cout_total(planning)),
    }
    return pd.DataFrame({"Contrôle": list(controles),
                         "Résultat": ["OK" if v else "ÉCHEC" for v in controles.values()]}).set_index("Contrôle")


def valider(planning_complet, lignes_complet, ids_attendus):
    # Contrôles du planning final ; s'arrête si le planning est incohérent ou viole une contrainte dure
    controle_contraintes = verifier_contraintes(planning_complet, lignes_complet, ids_attendus)
    validation = valider_resultats(planning_complet, lignes_complet)
    assert (validation["Résultat"] == "OK").all(), "le planning final est incohérent"
    assert (controle_contraintes.loc[controle_contraintes["Type"] == "dure", "Violations"] == 0).all(), \
        "une contrainte dure est violée"
    return controle_contraintes, validation
