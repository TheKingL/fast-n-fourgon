"""Sorties du moteur : bilan des économies, sortie 1 (profil par couple), sortie 2 (contenu des camions), export CSV."""
import numpy as np
import pandas as pd

from .charge import nb_hors_tolerance
from .config import JOURS, POIDS_MAX, SORTIE
from .couts import distance_brute
from .donnees import (CONTROLE, COUT_BASELINE, COUT_RESERVE, IDS_ATTENDUS, NB_RESERVE, USINES, avec_reserves, besoins,
                      camions_base)
from .formatage import nombre, pourcent

NB_AFFICHES = 10
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
        "décembre"]


# =====================================================================================================
# Tableau des économies
# =====================================================================================================
def calculer_bilan(versions):
    # Une ligne par version (baseline, algorithme de base, chaque étape du moteur), camions réservés compris
    cout_baseline_total = COUT_BASELINE + COUT_RESERVE
    col_hors = f"Semaines hors tolérance (sur {len(USINES) * len(CONTROLE)})"
    return pd.DataFrame([{
        "Version": nom,
        "Camions": len(c) + NB_RESERVE,
        "Coût": c["cout"].sum() + COUT_RESERVE,
        "Économie vs baseline": COUT_BASELINE - c["cout"].sum(),
        "Économie (%)": (COUT_BASELINE - c["cout"].sum()) / cout_baseline_total,
        "Avance moyenne (j)": np.nan if l is None else l["avance_jours"].mean(),
        col_hors: nb_hors_tolerance(avec_reserves(c)),
    } for nom, (c, l) in versions.items()])


def economies_par_usine(planning_complet):
    # Économies par usine (camions réservés compris)
    base_u = avec_reserves(camions_base).groupby("plant").agg(camions_baseline=("cout", "size"), cout_baseline=("cout", "sum"))
    final_u = planning_complet.groupby("plant").agg(camions_final=("cout", "size"), cout_final=("cout", "sum"))
    par_usine = base_u.join(final_u)
    par_usine.loc["Total"] = par_usine.sum()
    par_usine["economie"] = par_usine["cout_baseline"] - par_usine["cout_final"]
    par_usine["economie_pct"] = par_usine["economie"] / par_usine["cout_baseline"]
    return par_usine


# =====================================================================================================
# Sortie 1 : le profil à appliquer pour chaque couple
# =====================================================================================================
def moyennes_par_semaine(camions):
    # Par couple, sur les semaines où il est livré : jours de livraison et camions par semaine (moyennes)
    par_sem = camions.assign(semaine=camions["date"].dt.isocalendar().week).groupby(["plant", "supplier_id", "semaine"])
    jours = par_sem["date"].nunique().groupby(["plant", "supplier_id"]).mean()
    nb_camions = par_sem.size().groupby(["plant", "supplier_id"]).mean()
    return jours, nb_camions


def construire_sortie1(planning):
    livraisons_actuelles, _ = moyennes_par_semaine(camions_base)
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
    assert len(sortie1) == besoins.groupby(["plant", "supplier_id"]).ngroups
    return sortie1


# =====================================================================================================
# Sortie 2 : les materials regroupés dans chaque camion
# =====================================================================================================
def construire_sortie2(lignes_complet, planning_complet):
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
    assert sortie2["nb_lignes"].sum() == len(IDS_ATTENDUS)                  # toutes les lignes de besoin
    assert sortie2["camion_id"].nunique() == len(planning_complet)          # tous les camions
    return sortie2


def poids_camion(contenu):
    # Poids total d'un camion et remplissage ; camion réservé : poids inconnu
    poids = contenu["poids_kg"].sum(min_count=1)
    if pd.isna(poids):
        return "poids inconnu (camion réservé)"
    return f"{nombre(round(poids))} kg (remplissage poids {pourcent(poids / POIDS_MAX)})"


def detail_camion(sortie2, camion_id, nb_affiches=NB_AFFICHES):
    # Materials d'un camion : les plus lourds, puis "N autres materials" ; retourne (résumé, tableau en texte)
    contenu = sortie2[sortie2["camion_id"] == camion_id]
    dates = pd.to_datetime([d for b in contenu["besoins"] for d in b.split(", ")])
    un_mois = dates.month.nunique() == 1

    def jours_besoin(b):
        return ", ".join(str(pd.Timestamp(d).day) if un_mois else pd.Timestamp(d).strftime("%d/%m")
                         for d in b.split(", "))

    table = (contenu.head(nb_affiches)[["material", "quai", "besoins", "quantite", "poids_kg"]]
             .assign(besoins=lambda t: t["besoins"].map(jours_besoin)).reset_index(drop=True))
    reste = contenu.iloc[nb_affiches:]
    if len(reste):
        table.loc[len(table)] = [f"{len(reste)} autres materials", "", "", reste["quantite"].sum(), reste["poids_kg"].sum()]
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
def exporter(sortie1, sortie2, bilan, dossier=SORTIE):
    # Écrit les fichiers CSV de sortie ; retourne {nom du fichier: table écrite}
    dossier.mkdir(parents=True, exist_ok=True)
    fichiers = {"sortie1_profils.csv": sortie1, "sortie2_camions.csv": sortie2,
                "bilan.csv": bilan.round({"Coût": 2, "Économie vs baseline": 2, "Économie (%)": 4, "Avance moyenne (j)": 2})}
    for nom_fichier, table in fichiers.items():
        table.to_csv(dossier / nom_fichier, index=False, date_format="%Y-%m-%d")
    return fichiers
