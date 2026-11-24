"""Sorties du moteur : bilan des économies, sortie 1 (profil par couple), sortie 2 (contenu des camions), export CSV."""
from pathlib import Path

import numpy as np
import pandas as pd

from .charge import nb_hors_tolerance
from .config import JOURS, POIDS_MAX, SORTIE
from .couts import distance_brute
from . import donnees
from .formatage import nombre, pourcent

NB_AFFICHES: int = 10
"""Nombre de materials détaillés pour un camion (les suivants sont regroupés en « N autres materials »)."""
MOIS: list[str] = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
                   "novembre", "décembre"]
"""Noms des mois, indexés à partir de 0."""


# =====================================================================================================
# Tableau des économies
# =====================================================================================================
def calculer_bilan(versions: dict[str, tuple[pd.DataFrame, pd.DataFrame | None]]) -> pd.DataFrame:
    """Compare les versions du planning à la baseline (camions réservés compris).

    Args:
        versions: nom de la version -> ``(camions, lignes livrées)`` ; ``lignes`` vaut None pour la baseline.

    Returns:
        Une ligne par version : ``Version``, ``Camions``, ``Coût``, ``Économie vs baseline``, ``Économie (%)``,
        ``Avance moyenne (j)`` et le nombre de semaines hors tolérance.
    """
    d = donnees
    cout_baseline_total = d.COUT_BASELINE + d.COUT_RESERVE
    col_hors = f"Semaines hors tolérance (sur {len(d.USINES) * len(d.CONTROLE)})"
    return pd.DataFrame([{
        "Version": nom,
        "Camions": len(c) + d.NB_RESERVE,
        "Coût": c["cout"].sum() + d.COUT_RESERVE,
        "Économie vs baseline": d.COUT_BASELINE - c["cout"].sum(),
        "Économie (%)": (d.COUT_BASELINE - c["cout"].sum()) / cout_baseline_total,
        "Avance moyenne (j)": np.nan if l is None else l["avance_jours"].mean(),
        col_hors: nb_hors_tolerance(d.avec_reserves(c)),
    } for nom, (c, l) in versions.items()])


def economies_par_usine(planning_complet: pd.DataFrame) -> pd.DataFrame:
    """Compare, usine par usine, le planning final à la baseline (camions réservés compris).

    Args:
        planning_complet: planning final, une ligne par camion.

    Returns:
        Une ligne par usine plus une ligne ``Total`` : ``camions_baseline``, ``cout_baseline``, ``camions_final``,
        ``cout_final``, ``economie`` (€) et ``economie_pct`` (proportion).
    """
    base_u = donnees.avec_reserves(donnees.camions_base).groupby("plant").agg(camions_baseline=("cout", "size"), cout_baseline=("cout", "sum"))
    final_u = planning_complet.groupby("plant").agg(camions_final=("cout", "size"), cout_final=("cout", "sum"))
    par_usine = base_u.join(final_u)
    par_usine.loc["Total"] = par_usine.sum()
    par_usine["economie"] = par_usine["cout_baseline"] - par_usine["cout_final"]
    par_usine["economie_pct"] = par_usine["economie"] / par_usine["cout_baseline"]
    return par_usine


# =====================================================================================================
# Sortie 1 : le profil à appliquer pour chaque couple
# =====================================================================================================
def moyennes_par_semaine(camions: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Calcule, par couple, les moyennes hebdomadaires sur les semaines où il est livré.

    Args:
        camions: une ligne par camion, avec ``plant``, ``supplier_id`` et ``date``.

    Returns:
        ``(jours de livraison par semaine, camions par semaine)``, indexés par ``(plant, supplier_id)``.
    """
    par_sem = camions.assign(semaine=camions["date"].dt.isocalendar().week).groupby(["plant", "supplier_id", "semaine"])
    jours = par_sem["date"].nunique().groupby(["plant", "supplier_id"]).mean()
    nb_camions = par_sem.size().groupby(["plant", "supplier_id"]).mean()
    return jours, nb_camions


def construire_sortie1(planning: pd.DataFrame) -> pd.DataFrame:
    """Construit la sortie 1 : le profil de livraison à appliquer pour chaque couple.

    Args:
        planning: planning des camions optimisés (sans les réservés).

    Returns:
        Une ligne par couple : ``fournisseur``, ``usine``, ``distance_km`` (NaN = inconnue),
        ``livraisons_semaine_actuelles`` (baseline), ``frequence_cible`` (nombre de jours fixes), ``jours``,
        ``camions_semaine`` et ``remplissage_poids`` (proportion de 24,5 t).
    """
    livraisons_actuelles, _ = moyennes_par_semaine(donnees.camions_base)
    _, camions_semaine = moyennes_par_semaine(planning)
    par_couple = planning.groupby(["plant", "supplier_id"])
    sortie1 = pd.DataFrame({
        "frequence_cible": par_couple["profil"].first().map(len),
        "jours": par_couple["jours_fixes"].first(),
        "camions_semaine": camions_semaine.round(2),
        "remplissage_poids": (par_couple["poids"].mean() / POIDS_MAX).round(4),
    }).reset_index()
    sortie1.insert(2, "distance_km", sortie1["supplier_id"].map(distance_brute))
    sortie1.insert(3, "livraisons_semaine_actuelles",
                   [round(livraisons_actuelles.get((p, s), 0), 2) for p, s in zip(sortie1["plant"], sortie1["supplier_id"])])
    sortie1 = sortie1.rename(columns={"supplier_id": "fournisseur", "plant": "usine"})[
        ["fournisseur", "usine", "distance_km", "livraisons_semaine_actuelles", "frequence_cible", "jours",
         "camions_semaine", "remplissage_poids"]].sort_values(["usine", "fournisseur"]).reset_index(drop=True)
    assert sortie1[["fournisseur", "usine"]].duplicated().sum() == 0      # un profil par couple
    assert len(sortie1) == donnees.besoins.groupby(["plant", "supplier_id"]).ngroups
    return sortie1


# =====================================================================================================
# Sortie 2 : les materials regroupés dans chaque camion
# =====================================================================================================
def construire_sortie2(lignes_complet: pd.DataFrame, planning_complet: pd.DataFrame) -> pd.DataFrame:
    """Construit la sortie 2 : les materials chargés dans chaque camion.

    Args:
        lignes_complet: lignes livrées (réservées comprises).
        planning_complet: planning final, une ligne par camion.

    Returns:
        Une ligne par camion × material × quai : ``camion_id``, ``usine``, ``fournisseur``, ``date_livraison``,
        ``jour``, ``material``, ``quai``, ``besoins`` (dates regroupées), ``nb_lignes``, ``quantite``,
        ``poids_kg`` (NaN si inconnu) et ``reserve`` ; triée par camion puis poids décroissant.
    """
    sortie2 = (lignes_complet
               .groupby(["camion_id", "plant", "supplier_id", "date_livraison", "material", "unloading_point"])
               .agg(besoins=("need_date", lambda d: ", ".join(sorted(d.dt.strftime("%Y-%m-%d").unique()))),
                    nb_lignes=("need_date", "size"), quantite=("schedule_quantity", "sum"),
                    poids_kg=("weight", lambda w: w.sum(min_count=1)), reserve=("reserve", "first"))
               .reset_index()
               .rename(columns={"plant": "usine", "supplier_id": "fournisseur", "unloading_point": "quai"}))
    sortie2.insert(4, "jour", sortie2["date_livraison"].dt.day_of_week.map(dict(enumerate(JOURS))))
    sortie2["poids_kg"] = sortie2["poids_kg"].round(1)
    sortie2 = sortie2.sort_values(["camion_id", "poids_kg", "material"], ascending=[True, False, True]).reset_index(drop=True)
    assert sortie2["nb_lignes"].sum() == len(donnees.IDS_ATTENDUS)          # toutes les lignes de besoin
    assert sortie2["camion_id"].nunique() == len(planning_complet)          # tous les camions
    return sortie2


# =====================================================================================================
# Sortie 3 : le saving potentiel par couple
# =====================================================================================================
def construire_sortie3(camions_base: pd.DataFrame, planning_complet: pd.DataFrame) -> pd.DataFrame:
    """Construit la sortie 3 : le coût de transport avant et après consolidation, couple par couple.

    Les camions réservés (poids ou volume inconnu) sont comptés des deux côtés, comme dans le bilan.

    Args:
        camions_base: camions de la baseline, hors réservés (une ligne par camion).
        planning_complet: planning final, camions réservés compris (colonne ``reserve``).

    Returns:
        Une ligne par couple : ``fournisseur``, ``usine``, ``distance_km`` (NaN = inconnue), ``camions_actuels``,
        ``cout_actuel``, ``camions_apres``, ``cout_apres``, ``economie`` (€), ``economie_pct`` (proportion),
        ``cout_actuel_semaine`` et ``cout_apres_semaine`` (moyennes sur les semaines du planning) ;
        triée par économie décroissante.
    """
    reserves = planning_complet[planning_complet["reserve"]]
    base = pd.concat([camions_base[["plant", "supplier_id", "date", "cout"]],
                      reserves[["plant", "supplier_id", "date", "cout"]]], ignore_index=True)
    cles = ["plant", "supplier_id"]
    avant = base.groupby(cles).agg(camions_actuels=("cout", "size"), cout_actuel=("cout", "sum"))
    apres = planning_complet.groupby(cles).agg(camions_apres=("cout", "size"), cout_apres=("cout", "sum"))
    sortie3 = avant.join(apres, how="outer").fillna(0).reset_index()
    dates = pd.concat([base["date"], planning_complet["date"]])
    nb_semaines = max(len(dates.dt.isocalendar()[["year", "week"]].drop_duplicates()), 1)

    sortie3["economie"] = sortie3["cout_actuel"] - sortie3["cout_apres"]
    sortie3["economie_pct"] = (sortie3["economie"] / sortie3["cout_actuel"].where(sortie3["cout_actuel"] > 0)).round(4)
    sortie3["cout_actuel_semaine"] = sortie3["cout_actuel"] / nb_semaines
    sortie3["cout_apres_semaine"] = sortie3["cout_apres"] / nb_semaines
    for colonne in ("cout_actuel", "cout_apres", "economie", "cout_actuel_semaine", "cout_apres_semaine"):
        sortie3[colonne] = sortie3[colonne].round(2)
    for colonne in ("camions_actuels", "camions_apres"):
        sortie3[colonne] = sortie3[colonne].astype(int)
    sortie3.insert(2, "distance_km", sortie3["supplier_id"].map(distance_brute))
    sortie3 = sortie3.rename(columns={"supplier_id": "fournisseur", "plant": "usine"})[
        ["fournisseur", "usine", "distance_km", "camions_actuels", "cout_actuel", "camions_apres", "cout_apres",
         "economie", "economie_pct", "cout_actuel_semaine", "cout_apres_semaine"]]
    sortie3 = sortie3.sort_values(["economie", "usine", "fournisseur"], ascending=[False, True, True])
    assert sortie3[["fournisseur", "usine"]].duplicated().sum() == 0      # un bilan par couple
    return sortie3.reset_index(drop=True)


def camion_le_plus_charge(planning_complet: pd.DataFrame) -> int:
    """Donne le camion qui regroupe le plus de lignes de besoin (le premier en cas d'égalité).

    Args:
        planning_complet: planning final, une ligne par camion, avec ``camion_id`` et ``nb_lignes``.

    Returns:
        Le numéro du camion.
    """
    return int(planning_complet["camion_id"].to_numpy()[planning_complet["nb_lignes"].to_numpy().argmax()])


def poids_camion(contenu: pd.DataFrame) -> str:
    """Décrit le poids total d'un camion et son remplissage.

    Args:
        contenu: lignes de la sortie 2 d'un camion.

    Returns:
        Par exemple ``"5 812 kg (remplissage poids 23,7 %)"``, ou ``"poids inconnu (camion réservé)"``.
    """
    poids = contenu["poids_kg"].sum(min_count=1)
    if pd.isna(poids):
        return "poids inconnu (camion réservé)"
    return f"{nombre(round(poids))} kg (remplissage poids {pourcent(poids / POIDS_MAX)})"


def detail_camion(sortie2: pd.DataFrame, camion_id: int, nb_affiches: int = NB_AFFICHES) -> tuple[str, str]:
    """Prépare le détail d'un camion pour l'affichage : les materials les plus lourds, puis « N autres materials ».

    Args:
        sortie2: la sortie 2 (voir ``construire_sortie2``).
        camion_id: numéro du camion.
        nb_affiches: nombre de materials détaillés.

    Returns:
        ``(résumé du camion sur une ligne, tableau des materials en texte)``.
    """
    contenu = sortie2[sortie2["camion_id"] == camion_id]
    dates = pd.to_datetime([d for b in contenu["besoins"] for d in b.split(", ")])
    un_mois = dates.month.nunique() == 1

    def jours_besoin(b: str) -> str:
        """Dates de besoin abrégées : le jour seul si tout est dans le même mois, sinon jj/mm."""
        return ", ".join(str(pd.Timestamp(d).day) if un_mois else pd.Timestamp(d).strftime("%d/%m")
                         for d in b.split(", "))

    table = (contenu.head(nb_affiches)[["material", "quai", "besoins", "quantite", "poids_kg"]]
             .assign(besoins=lambda t: t["besoins"].map(jours_besoin)).reset_index(drop=True))
    reste = contenu.iloc[nb_affiches:]
    if len(reste):
        table.loc[len(table)] = [  # type: ignore[assignment]  # ajout d'une ligne : accepté par pandas, pas par ses stubs
            f"{len(reste)} autres materials", "", "", reste["quantite"].sum(), reste["poids_kg"].sum()]
    camion = contenu.iloc[0]
    resume = (f"Camion n° {camion_id} : {camion['fournisseur']} -> {camion['usine']}, {camion['jour'].lower()} "
              f"{camion['date_livraison']:%d/%m}, {len(contenu)} materials, "
              f"{contenu['nb_lignes'].sum()} lignes de besoin, {poids_camion(contenu)}")
    titre_besoins = f"Besoins regroupés (jours de {MOIS[dates[0].month - 1]})" if un_mois else "Besoins regroupés"
    table = table.rename(columns={"material": "Material", "quai": "Quai", "besoins": titre_besoins,
                                  "quantite": "Quantité", "poids_kg": "Poids (kg)"})
    return resume, table.to_string(index=False, formatters={"Quantité": nombre,
                                                            "Poids (kg)": lambda p: nombre(round(p))}, na_rep="–")


# =====================================================================================================
# Export
# =====================================================================================================
def exporter(sortie1: pd.DataFrame, sortie2: pd.DataFrame, bilan: pd.DataFrame,
             dossier: Path = SORTIE) -> dict[str, pd.DataFrame]:
    """Écrit les fichiers CSV de sortie.

    Args:
        sortie1: la sortie 1.
        sortie2: la sortie 2.
        bilan: le tableau des économies.
        dossier: dossier de destination, créé s'il n'existe pas ; ``data/gold`` par défaut.

    Returns:
        Nom du fichier -> table écrite (``sortie1_profils.csv``, ``sortie2_camions.csv``, ``bilan.csv``).
    """
    dossier.mkdir(parents=True, exist_ok=True)
    fichiers = {"sortie1_profils.csv": sortie1, "sortie2_camions.csv": sortie2,
                "bilan.csv": bilan.round({"Coût": 2, "Économie vs baseline": 2, "Économie (%)": 4, "Avance moyenne (j)": 2})}
    for nom_fichier, table in fichiers.items():
        table.to_csv(dossier / nom_fichier, index=False, date_format="%Y-%m-%d")
    return fichiers
