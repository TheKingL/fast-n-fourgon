"""Vérification des contraintes C1 à C11 et cohérence du planning final.

Chaque fonction ``cX_...`` reçoit le planning (une ligne par camion) et les lignes livrées
(une ligne par ligne de besoin), et retourne les cas qui violent la contrainte :
une table vide signifie que la contrainte est respectée.
"""
from collections.abc import Callable

import numpy as np
import pandas as pd

from . import donnees
from .charge import charges_camions, ecart, hors_tolerance
from .config import FENETRE, JOURS_FIXES_MAX, POIDS_MAX, VOLUME_MAX
from .couts import cout_camion, cout_total
from .jours_fixes import profil_utilise


def optimises(planning: pd.DataFrame) -> pd.DataFrame:
    """Garde les camions construits par le moteur (sans les camions réservés de la quarantaine).

    Args:
        planning: une ligne par camion, avec la colonne booléenne ``reserve``.

    Returns:
        Les camions non réservés.
    """
    return planning[~planning["reserve"]]


def c1_poids(planning: pd.DataFrame, lignes: pd.DataFrame) -> pd.DataFrame:
    """C1 : un camion ne dépasse pas 24,5 t.

    Returns:
        Les camions optimisés trop lourds.
    """
    p = optimises(planning)
    return p[p["poids"] > POIDS_MAX + 1e-6]


def c2_volume(planning: pd.DataFrame, lignes: pd.DataFrame) -> pd.DataFrame:
    """C2 : un camion ne dépasse pas 110,4 m³.

    Returns:
        Les camions trop volumineux.
    """
    return planning[planning["volume"] > VOLUME_MAX + 1e-6]


def c3_exhaustivite(planning: pd.DataFrame, lignes: pd.DataFrame, ids_attendus: set[str]) -> pd.DataFrame:
    """C3 : chaque ligne de besoin est livrée, une seule fois, entière.

    Args:
        planning: une ligne par camion.
        lignes: une ligne par ligne livrée, avec ``id_ligne`` et ``camion_id``.
        ids_attendus: identifiants de toutes les lignes qui doivent être livrées.

    Returns:
        Les lignes en défaut, avec la colonne ``probleme`` : sans camion, livrée plusieurs fois, absente
        ou ligne inconnue.
    """
    sans_camion = lignes[lignes["camion_id"].isna()].assign(probleme="sans camion")
    doublons = lignes[lignes["id_ligne"].duplicated(keep=False)].assign(probleme="livrée plusieurs fois")
    absentes = pd.DataFrame({"id_ligne": sorted(set(ids_attendus) - set(lignes["id_ligne"])), "probleme": "absente"})
    inconnues = lignes[~lignes["id_ligne"].isin(ids_attendus)].assign(probleme="ligne inconnue")
    return pd.concat([sans_camion, doublons, absentes, inconnues], ignore_index=True)


def c4_un_couple(planning: pd.DataFrame, lignes: pd.DataFrame) -> pd.DataFrame:
    """C4 : un camion ne transporte qu'un seul couple fournisseur × usine.

    Returns:
        Les camions qui mélangent plusieurs couples (colonnes ``camion_id``, ``couples``).
    """
    nb_couples = lignes.groupby("camion_id")[["plant", "supplier_id"]].nunique().max(axis=1)
    return nb_couples[nb_couples > 1].rename("couples").reset_index()


def c5_retard(planning: pd.DataFrame, lignes: pd.DataFrame) -> pd.DataFrame:
    """C5 : jamais de retard (livraison au plus tard le jour du besoin).

    Returns:
        Les lignes livrées après leur besoin.
    """
    return lignes[lignes["date_livraison"] > lignes["need_date"]]


def c6_avance(planning: pd.DataFrame, lignes: pd.DataFrame) -> pd.DataFrame:
    """C6 : au plus 7 jours d'avance sur le besoin.

    Returns:
        Les lignes livrées trop tôt.
    """
    return lignes[lignes["need_date"] - lignes["date_livraison"] > FENETRE]


def c7_jours_ouvres(planning: pd.DataFrame, lignes: pd.DataFrame) -> pd.DataFrame:
    """C7 : livraison un jour ouvré, dans l'horizon du planning (semaine ajoutée avant le planning comprise).

    Returns:
        Les camions du week-end, d'avant le lundi 02/11 ou d'après la fin du planning.
    """
    d = planning["date"]
    return planning[(d.dt.day_of_week >= 5) | (d < donnees.DEBUT_LIVRAISONS) | (d > donnees.FIN)]


def c8_jours_fixes(planning: pd.DataFrame, lignes: pd.DataFrame) -> pd.DataFrame:
    """C8 : chaque couple a 1 à 3 jours fixes, et tous ses camions partent un de ces jours, sans exception.

    Returns:
        Les camions optimisés avec un profil invalide ou partis hors de leurs jours fixes.
    """
    p = optimises(planning)
    mauvais_profil = ~p["profil"].map(len).between(1, JOURS_FIXES_MAX)
    hors_profil = np.array([d.day_of_week not in prof for d, prof in zip(p["date"], p["profil"])], dtype=bool)
    return p[mauvais_profil | hors_profil]


MOTIF_POIDS: str = "besoin d'un jour > 24,5 t"
"""Cause d'un cas impossible : le besoin d'un seul jour du couple dépasse la capacité d'un camion."""
MOTIF_RESERVE: str = "ligne sans poids (camion réservé)"
"""Cause d'un cas impossible : une ligne sans poids a son propre camion, le jour du besoin (règle absolue)."""


def c9_un_camion_par_jour(planning: pd.DataFrame, lignes: pd.DataFrame) -> pd.DataFrame:
    """C9 : au plus 1 camion par couple et par jour, camions réservés compris.

    Deux cas rendent la règle impossible à tenir ; ils sont justifiés, et notifiés dans ``alertes`` :

    - le besoin d'un seul jour du couple dépasse 24,5 t (2 camions optimisés inévitables) ;
    - une ligne sans poids a son camion réservé ce jour-là (règle absolue : elle ne peut être ni regroupée, ni
      déplacée).

    Returns:
        Les jours où un couple a 2 camions ou plus (colonnes ``plant``, ``supplier_id``, ``date``, ``camions``,
        ``reserves`` = camions réservés ce jour-là, ``motif`` = cause du cas impossible, vide sinon), avec la
        colonne ``justifie`` = True quand le cas est impossible à éviter.
    """
    par_jour = planning.groupby(["plant", "supplier_id", "date"]).agg(
        camions=("reserve", "size"), reserves=("reserve", "sum")).reset_index()
    trop = par_jour[par_jour["camions"] > 1].reset_index(drop=True)
    besoin_jour = lignes.dropna(subset=["weight"]).groupby(["plant", "supplier_id", "need_date"])["weight"].sum()
    impossibles = set(besoin_jour[besoin_jour > POIDS_MAX].index.droplevel("need_date"))  # type: ignore[arg-type]  # stubs pandas trop stricts
    motifs = []
    for p, s, n, r in zip(trop["plant"], trop["supplier_id"], trop["camions"], trop["reserves"]):
        causes = ([MOTIF_POIDS] if n - r > 1 and (p, s) in impossibles else []) + ([MOTIF_RESERVE] if r > 0 else [])
        motifs.append(" + ".join(causes))
    trop["motif"] = motifs
    trop["justifie"] = [n - r <= 1 or (p, s) in impossibles     # au plus 1 camion optimisé, ou besoin du jour > 24,5 t
                        for p, s, n, r in zip(trop["plant"], trop["supplier_id"], trop["camions"], trop["reserves"])]
    return trop


def c10_lissage(planning: pd.DataFrame, lignes: pd.DataFrame) -> pd.DataFrame:
    """C10 (souple) : aucun jour ne s'écarte de plus de 35 % de la moyenne de la semaine.

    Tous les camions reçus sont comptés (camions réservés compris).

    Returns:
        Les semaines hors tolérance, par usine (colonnes ``plant``, ``semaine``, ``ecart``, ``camions_par_jour``).
    """
    lignes_hors = []
    for plant, charge in charges_camions(planning).items():
        hors = hors_tolerance(charge)
        for w in donnees.CONTROLE:
            if hors[w]:
                lignes_hors.append({"plant": plant, "semaine": donnees.SEMAINES[w], "ecart": ecart(charge[w]),
                                    "camions_par_jour": charge[w].astype(int).tolist()})
    return pd.DataFrame(lignes_hors)


def c11_profil_utilise(planning: pd.DataFrame, lignes: pd.DataFrame) -> pd.DataFrame:
    """C11 : un couple à 2 ou 3 jours fixes livre au moins une semaine sur tous ses jours fixes.

    Returns:
        Les couples qui ne livrent jamais tous leurs jours fixes la même semaine
        (colonnes ``plant``, ``supplier_id``, ``profil``).
    """
    manques = [(plant, supplier, g["profil"].iloc[0])
               for (plant, supplier), g in optimises(planning).groupby(["plant", "supplier_id"])
               if not profil_utilise(g["date"], g["profil"].iloc[0])]
    return pd.DataFrame(manques, columns=["plant", "supplier_id", "profil"])


CONTRAINTES: list[tuple[str, str, str, Callable[..., pd.DataFrame]]] = [
    ("C1", "Poids ≤ 24,5 t", "dure", c1_poids),
    ("C2", "Volume ≤ 110,4 m³", "dure", c2_volume),
    ("C3", "Chaque ligne livrée une fois, entière", "dure", c3_exhaustivite),
    ("C4", "Un seul couple par camion", "dure", c4_un_couple),
    ("C5", "Jamais de retard", "dure", c5_retard),
    ("C6", "Au plus 7 jours d'avance", "dure", c6_avance),
    ("C7", "Jour ouvré, dans l'horizon", "dure", c7_jours_ouvres),
    ("C8", "Jours fixes (1 à 3 par couple, sans exception)", "dure", c8_jours_fixes),
    ("C9", "Au plus 1 camion par couple et par jour", "dure", c9_un_camion_par_jour),
    ("C10", "Lissage (écart ≤ 35 %)", "souple", c10_lissage),
    ("C11", "Profil utilisé : une semaine sur tous ses jours fixes", "dure", c11_profil_utilise),
]
"""Les contraintes : ``(code, description, type "dure" ou "souple", fonction de vérification)``."""


def alertes(planning: pd.DataFrame, lignes: pd.DataFrame) -> pd.DataFrame:
    """Liste les cas où une règle ne peut pas être respectée, pour les notifier.

    - C9 : un couple reçoit 2 camions ou plus le même jour (besoin d'un jour > 24,5 t, ou ligne sans poids) ;
    - C8 : un camion réservé (ligne sans poids) part le jour du besoin, hors des jours fixes du couple.

    Args:
        planning: planning complet, une ligne par camion (réservés compris).
        lignes: lignes livrées (réservées comprises).

    Returns:
        Une ligne par cas : ``regle``, ``usine``, ``fournisseur``, ``date``, ``camions``, ``cause`` et ``a_faire``.
    """
    a_faire = {MOTIF_POIDS: "aucune : le besoin du jour dépasse la capacité d'un camion, 2 camions sont nécessaires",
               MOTIF_RESERVE: "obtenir le poids de la ligne auprès du client pour pouvoir la consolider"}
    cas = []
    c9 = c9_un_camion_par_jour(planning, lignes)
    for r in c9[c9["justifie"]].itertuples():
        cas.append({"regle": "C9 : 2 camions ou plus le même jour", "usine": r.plant, "fournisseur": r.supplier_id,
                    "date": r.date, "camions": int(r.camions), "cause": r.motif,
                    "a_faire": " ; ".join(a_faire[m] for m in str(r.motif).split(" + "))})
    profils = optimises(planning).groupby(["plant", "supplier_id"])["profil"].first()
    for r in planning[planning["reserve"]].itertuples():
        profil = profils.get((r.plant, r.supplier_id))
        if profil is None or r.date.day_of_week not in profil:
            cas.append({"regle": "C8 : camion hors jours fixes", "usine": r.plant, "fournisseur": r.supplier_id,
                        "date": r.date, "camions": 1,
                        "cause": MOTIF_RESERVE + ("" if profil is not None else ", couple sans autre livraison (pas de jours fixes)"),
                        "a_faire": a_faire[MOTIF_RESERVE]})
    colonnes = ["regle", "usine", "fournisseur", "date", "camions", "cause", "a_faire"]
    return pd.DataFrame(cas, columns=colonnes).sort_values(["regle", "usine", "date", "fournisseur"]).reset_index(drop=True)


def verifier_contraintes(planning: pd.DataFrame, lignes: pd.DataFrame, ids_attendus: set[str]) -> pd.DataFrame:
    """Vérifie toutes les contraintes et fait la synthèse.

    Pour C9, les cas impossibles (besoin d'un jour > 24,5 t, ligne sans poids) ne comptent pas comme violations :
    ils sont notifiés dans ``alertes``. Pour C8, les camions réservés hors jours fixes sont aussi notifiés.

    Args:
        planning: une ligne par camion.
        lignes: une ligne par ligne livrée.
        ids_attendus: identifiants de toutes les lignes qui doivent être livrées.

    Returns:
        Une ligne par contrainte (index ``Contrainte``), avec ``Description``, ``Type``, ``Violations``,
        ``Statut`` et ``Remarque``.
    """
    resultats = []
    for code_c, nom, type_c, fonction in CONTRAINTES:
        args = (planning, lignes, ids_attendus) if fonction is c3_exhaustivite else (planning, lignes)
        violations = fonction(*args)
        remarque, notifies = "", 0
        if fonction is c8_jours_fixes:
            notifies = int((alertes(planning, lignes)["regle"].str.startswith("C8")).sum())
            remarque = f"{notifies} camions réservés hors jours fixes, notifiés (alertes)"
        if fonction is c9_un_camion_par_jour:
            justifies = violations[violations["justifie"]]
            notifies = len(justifies)
            remarque = (f"{len(justifies)} cas impossibles, notifiés (alertes) : "
                        f"{int(justifies['motif'].str.contains('24,5').sum())} besoin d'un jour > 24,5 t, "
                        f"{int(justifies['motif'].str.contains('sans poids').sum())} ligne sans poids")
            violations = violations[~violations["justifie"]]
        if fonction is c10_lissage:
            remarque = f"sur {len(donnees.USINES) * len(donnees.CONTROLE)} semaines contrôlées"
        nb = len(violations)
        statut = "respectée" if nb == 0 else ("violée" if type_c == "dure" else f"{nb} semaine(s) hors tolérance")
        if nb == 0 and notifies:
            statut = "respectée, sauf cas impossibles notifiés"
        resultats.append({"Contrainte": code_c, "Description": nom, "Type": type_c, "Violations": nb,
                          "Statut": statut, "Remarque": remarque})
    return pd.DataFrame(resultats).set_index("Contrainte")


def valider_resultats(planning: pd.DataFrame, lignes: pd.DataFrame) -> pd.DataFrame:
    """Contrôle la cohérence du planning final : contenu des camions, poids livré, coût.

    Args:
        planning: planning complet, une ligne par camion (réservés compris).
        lignes: lignes livrées, une ligne par ligne de besoin (réservées comprises).

    Returns:
        Une ligne par contrôle (index ``Contrôle``), colonne ``Résultat`` = ``"OK"`` ou ``"ÉCHEC"``.
    """
    opti, lignes_opti = optimises(planning), lignes[~lignes["reserve"]]
    contenu = lignes_opti.groupby("camion_id").agg(poids=("weight", "sum"), volume=("volume", "sum"), nb=("weight", "size"))
    p = opti.set_index("camion_id")
    controles = {
        "Chaque camion optimisé contient au moins une ligne": opti["camion_id"].isin(contenu.index).all(),
        "Poids de chaque camion = somme des poids de ses lignes": np.allclose(p["poids"], contenu.loc[p.index, "poids"]),
        "Volume de chaque camion = somme des volumes de ses lignes": np.allclose(p["volume"], contenu.loc[p.index, "volume"]),
        "Poids total livré = poids total des besoins": np.isclose(lignes_opti["weight"].sum(),
                                                                       donnees.besoins["weight"].sum()),
        "Un camion réservé par ligne sans poids ou sans volume": (lignes[lignes["reserve"]].groupby("camion_id").size() == 1).all()
                                                   and planning["reserve"].sum() == donnees.NB_RESERVE,
        "Coût de chaque camion = grille tarifaire": np.allclose(
            planning["cout"], [cout_camion(w, s) for w, s in zip(planning["poids"], planning["supplier_id"])]),
        "Coût total = somme des coûts des camions": np.isclose(planning["cout"].sum(), cout_total(planning)),
    }
    return pd.DataFrame({"Contrôle": list(controles),
                         "Résultat": ["OK" if v else "ÉCHEC" for v in controles.values()]}).set_index("Contrôle")


def valider(planning_complet: pd.DataFrame, lignes_complet: pd.DataFrame,
            ids_attendus: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Vérifie le planning final et arrête le moteur s'il est faux.

    Args:
        planning_complet: planning complet, une ligne par camion (réservés compris).
        lignes_complet: lignes livrées (réservées comprises).
        ids_attendus: identifiants de toutes les lignes qui doivent être livrées.

    Returns:
        ``(synthèse des contraintes, contrôles de cohérence)``, voir ``verifier_contraintes`` et ``valider_resultats``.

    Raises:
        AssertionError: si un contrôle de cohérence échoue ou si une contrainte dure est violée.
    """
    controle_contraintes = verifier_contraintes(planning_complet, lignes_complet, ids_attendus)
    validation = valider_resultats(planning_complet, lignes_complet)
    assert (validation["Résultat"] == "OK").all(), "le planning final est incohérent"
    assert (controle_contraintes.loc[controle_contraintes["Type"] == "dure", "Violations"] == 0).all(), \
        "une contrainte dure est violée"
    return controle_contraintes, validation
