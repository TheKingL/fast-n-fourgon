"""Moteur de consolidation des livraisons : flux d'exécution principal.

Le code du moteur est dans le package consolidation/ (un module par étape) ; ce fichier enchaîne les étapes :
  1. jours fixes : chaque couple fournisseur × usine choisit ses 1 ou 2 jours de livraison les moins chers ;
  2. contrôle de l'équilibre des usines (C10) ;
  3. lissage : changements de profil au moindre surcoût jusqu'à ce que les semaines soient dans la tolérance ;
  4. report des lignes sur le jour fixe suivant, puis planning final ;
  5. validation des contraintes, bilan des économies, sorties.

Sorties (écrites dans data/gold/) :
  - sortie 1, sortie1_profils.csv : le profil à appliquer pour chaque couple (aperçu dans la console) ;
  - sortie 2, sortie2_camions.csv : les materials regroupés dans chaque camion (détail d'un camion dans la console) ;
  - bilan.csv : tableau des économies (baseline vs chaque étape du moteur), aussi affiché dans la console.

Lancement : python main.py            (détaille le camion qui regroupe le plus de lignes de besoin)
            python main.py <camion>   (détaille le camion choisi, par exemple python main.py 254)

Depuis un notebook : import main ; r = main.executer()   (calcule tout sans rien écrire ni afficher)
"""
import sys
from types import SimpleNamespace

import pandas as pd

from consolidation import config, donnees, sorties
from consolidation.contraintes import valider
from consolidation.formatage import eur, nombre, pourcent
from consolidation.jours_fixes import VARIANTES, Scenarios, algorithme_de_base
from consolidation.lissage import lisser
from consolidation.report import ajouter_reserves, construire_planning, finaliser, reporter_lignes


def executer():
    """Fait tourner tout le moteur et retourne ses résultats (sans écrire de fichier ni afficher)."""
    # ---------- Bloc 1 : jours fixes, profil le moins cher de chaque couple ----------
    scenarios = Scenarios()
    choix_initiaux = {nom: scenarios.choix_moins_cher(profils) for nom, profils in VARIANTES.items()}

    # ---------- Blocs 2 et 3 : contrôle de l'équilibre des usines et lissage ----------
    choix_lisses, journaux = {}, {}
    for nom, profils in VARIANTES.items():
        choix_lisses[nom], journaux[nom] = lisser(scenarios, choix_initiaux[nom], profils)
    principale = min(VARIANTES, key=lambda nom: scenarios.cout_choix(choix_lisses[nom]))   # la moins chère après lissage

    # ---------- Bloc 4 : report et planning final (planning de chaque étape, pour le bilan) ----------
    plannings = {}
    for nom in VARIANTES:
        plannings[nom] = finaliser(construire_planning(scenarios, choix_initiaux[nom]))
        plannings[f"{nom} + lissage"] = finaliser(construire_planning(scenarios, choix_lisses[nom]))
    camions_report, journal_report = reporter_lignes(construire_planning(scenarios, choix_lisses[principale]))
    plannings[f"{principale} + lissage + report"] = finaliser(camions_report)
    planning, lignes_planning = plannings[f"{principale} + lissage + report"]
    planning_complet, lignes_complet = ajouter_reserves(planning, lignes_planning)

    # ---------- Validation : s'arrête si une contrainte dure est violée ----------
    controle_contraintes, validation = valider(planning_complet, lignes_complet, donnees.IDS_ATTENDUS)

    # ---------- Bilan et sorties ----------
    versions = {"Baseline": (donnees.camions_base, None), "Algorithme de base (sans jours fixes)": finaliser(algorithme_de_base())}
    versions.update(plannings)
    sortie2 = sorties.construire_sortie2(lignes_complet, planning_complet)

    return SimpleNamespace(
        scenarios=scenarios, choix_initiaux=choix_initiaux, choix_lisses=choix_lisses, journaux=journaux,
        principale=principale, journal_report=journal_report, plannings=plannings,
        planning=planning, planning_complet=planning_complet, lignes_complet=lignes_complet,
        controle_contraintes=controle_contraintes, validation=validation,
        bilan=sorties.calculer_bilan(versions), par_usine=sorties.economies_par_usine(planning_complet),
        sortie1=sorties.construire_sortie1(planning), sortie2=sortie2,
    )


def afficher(r, camion_detail, fichiers):
    """Résumé du moteur dans la console."""
    besoins = donnees.besoins
    print(f"Besoins à consolider : {len(besoins)} lignes, {besoins.groupby(['plant', 'supplier_id']).ngroups} couples, "
          f"{len(donnees.USINES)} usines, du {donnees.DEBUT:%d/%m} au {donnees.FIN:%d/%m}")
    print(f"Camions réservés (lignes sans poids) : {donnees.NB_RESERVE}, {eur(donnees.COUT_RESERVE)}")
    print(f"Variante retenue : {r.principale} ({len(r.journaux[r.principale])} changements de profil au lissage)")
    print(f"Report : {r.journal_report['lignes_reportees'].sum()} lignes reportées sur le jour fixe suivant, "
          f"gain {eur(r.journal_report['gain'].sum())}")

    print("\n=== Contraintes ===")
    print(r.controle_contraintes.drop(columns="Description").to_string())

    print("\n=== Économies (camions réservés compris) ===")
    print(r.bilan.to_string(index=False, na_rep="–", formatters={
        "Coût": eur, "Économie vs baseline": eur, "Économie (%)": pourcent, "Avance moyenne (j)": nombre}))

    print("\n=== Économies par usine ===")
    print(r.par_usine.to_string(formatters={
        "camions_baseline": "{:.0f}".format, "camions_final": "{:.0f}".format, "cout_baseline": eur,
        "cout_final": eur, "economie": eur, "economie_pct": pourcent}))

    print(f"\n=== Sortie 1 : le profil à appliquer pour chaque couple ({len(r.sortie1)} couples, aperçu des 10 premiers) ===")
    print(r.sortie1.head(10).rename(columns={
        "fournisseur": "Fournisseur", "usine": "Usine", "distance_km": "Distance",
        "livraisons_semaine_actuelles": "Livraisons / sem. actuelles", "frequence_cible": "Fréquence cible", "jours": "Jour",
        "camions_semaine": "Camions / sem.", "remplissage_poids": "Remplissage poids"})
        .to_string(index=False, formatters={
            "Distance": lambda d: "inconnue" if pd.isna(d) else f"{d:.0f} km", "Livraisons / sem. actuelles": nombre,
            "Fréquence cible": "{} / semaine".format, "Camions / sem.": nombre, "Remplissage poids": pourcent}))

    resume, table_camion = sorties.detail_camion(r.sortie2, camion_detail)
    print(f"\n=== Sortie 2 : les materials regroupés dans chaque camion ({r.sortie2['camion_id'].nunique()} camions) ===")
    print(resume)
    print(table_camion)

    print(f"\nFichiers écrits dans {config.SORTIE} :")
    for nom_fichier, table in fichiers.items():
        print(f"  {nom_fichier:<22}: {len(table)} lignes")


def main():
    if hasattr(sys.stdout, "reconfigure"):          # console Windows (accents)
        sys.stdout.reconfigure(encoding="utf-8")

    r = executer()
    fichiers = sorties.exporter(r.sortie1, r.sortie2, r.bilan)

    camion_detail = (int(sys.argv[1]) if len(sys.argv) > 1
                     else int(r.planning_complet.loc[r.planning_complet["nb_lignes"].idxmax(), "camion_id"]))
    assert camion_detail in set(r.sortie2["camion_id"]), f"camion {camion_detail} inconnu (1 à {r.sortie2['camion_id'].max()})"
    afficher(r, camion_detail, fichiers)


if __name__ == "__main__":
    main()
