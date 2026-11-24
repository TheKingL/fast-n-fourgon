"""Moteur de consolidation des livraisons : flux d'exécution principal.

Le code du moteur est dans le package ``backend/`` (un module par étape) ; ce fichier enchaîne les étapes :

0. entrée : les données du projet (``data/silver``, ``data/baseline``) ou un schedule brut, nettoyé
   (milestone 1) puis comparé à sa baseline (milestone 2) ;
1. jours fixes : chaque couple fournisseur × usine choisit ses 1 à 3 jours de livraison les moins chers ; les
   premiers besoins peuvent partir dans la semaine ajoutée avant le planning, et un couple à 2 ou 3 jours doit
   livrer au moins une semaine sur tous ses jours ;
2. contrôle de l'équilibre des usines (C10) ;
3. lissage : changements de profil au moindre surcoût jusqu'à ce que les semaines soient dans la tolérance ;
4. report des lignes sur le jour fixe suivant, puis planning final ;
5. validation des contraintes, bilan des économies, sorties.

Sorties (écrites dans ``data/gold/``) :

- sortie 1, ``sortie1_profils.csv`` : le profil à appliquer pour chaque couple (aperçu dans la console) ;
- sortie 2, ``sortie2_camions.csv`` : les materials regroupés dans chaque camion (détail d'un camion dans la console) ;
- ``bilan.csv`` : tableau des économies (baseline vs chaque étape du moteur), aussi affiché dans la console ;
- ``alertes.csv`` : les cas où une règle ne peut pas être respectée (2 camions un même jour, camion réservé hors
  jours fixes), avec leur cause et l'action à mener.

Lancement (depuis la racine du dépôt)::

    python main.py                          # données du projet ; détaille le camion le plus chargé en lignes
    python main.py 254                      # détaille le camion n° 254
    python main.py --schedule planning.csv  # nettoie et consolide un autre schedule brut

Depuis un notebook ou un front end::

    import main
    r = main.executer()             # données du projet ; r est un backend.resultats.Resultats
    r = main.executer(schedule)     # un schedule brut (DataFrame au format de released_schedule.csv)
"""
import argparse
import sys

import pandas as pd

from backend import config, donnees, sorties
from backend.baseline import construire_baseline
from backend.contraintes import alertes, valider
from backend.nettoyage import nettoyer
from backend.formatage import eur, nombre, pourcent
from backend.jours_fixes import VARIANTES, Scenarios, algorithme_de_base
from backend.lissage import lisser
from backend.report import ajouter_reserves, construire_planning, finaliser, reporter_lignes
from backend.resultats import Resultats
from backend.typage import Choix


def charger_entree(schedule: pd.DataFrame | None = None) -> None:
    """Prépare l'entrée du moteur.

    Args:
        schedule: schedule brut (format de ``released_schedule.csv``) ; None pour les données du projet.

    Raises:
        ValueError: si le schedule n'a pas les colonnes attendues ou aucune ligne de besoin.
    """
    if schedule is None:
        donnees.charger_fichiers()
        return
    clean, quarantaine = nettoyer(schedule)                                  # milestone 1
    donnees.charger(clean, quarantaine, construire_baseline(clean, quarantaine))  # milestone 2


def executer(schedule: pd.DataFrame | None = None) -> Resultats:
    """Fait tourner tout le moteur, sans écrire de fichier ni afficher.

    Args:
        schedule: schedule brut à consolider ; None (par défaut) pour les données du projet.

    Returns:
        Tous les résultats : planning final, sorties 1 et 2, bilan, contrôles... (voir ``Resultats``).

    Raises:
        ValueError: si le schedule n'est pas exploitable (voir ``charger_entree``).
        AssertionError: si le planning final est incohérent ou viole une contrainte dure.
    """
    # ---------- Entrée : schedule nettoyé et sa baseline ----------
    charger_entree(schedule)

    # ---------- Bloc 1 : jours fixes, profil le moins cher de chaque couple ----------
    scenarios = Scenarios()
    choix_initiaux = {nom: scenarios.choix_moins_cher(profils) for nom, profils in VARIANTES.items()}

    # ---------- Blocs 2 et 3 : contrôle de l'équilibre des usines et lissage ----------
    choix_lisses: dict[str, Choix] = {}
    journaux: dict[str, pd.DataFrame] = {}
    for nom, profils in VARIANTES.items():
        choix_lisses[nom], journaux[nom] = lisser(scenarios, choix_initiaux[nom], profils)
    # Variante retenue : la moins chère après lissage, parmi celles qui respectent C9 (une variante à 1 jour fixe
    # peut obliger un gros couple à 2 camions le même jour, alors qu'un 2e jour fixe l'éviterait)
    admissibles = [nom for nom in VARIANTES if scenarios.camions_en_trop_evitables(choix_lisses[nom]) == 0]
    principale = min(admissibles, key=lambda nom: scenarios.cout_choix(choix_lisses[nom]))

    # ---------- Bloc 4 : report et planning final (planning de chaque étape, pour le bilan) ----------
    plannings: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
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
    versions: dict[str, tuple[pd.DataFrame, pd.DataFrame | None]] = {
        "Baseline": (donnees.camions_base, None),
        "Algorithme de base (sans jours fixes)": finaliser(algorithme_de_base()),
    }
    versions.update(plannings)

    return Resultats(
        scenarios=scenarios, choix_initiaux=choix_initiaux, choix_lisses=choix_lisses, journaux=journaux,
        principale=principale, journal_report=journal_report, plannings=plannings,
        planning=planning, planning_complet=planning_complet, lignes_complet=lignes_complet,
        controle_contraintes=controle_contraintes, validation=validation,
        bilan=sorties.calculer_bilan(versions), par_usine=sorties.economies_par_usine(planning_complet),
        sortie1=sorties.construire_sortie1(planning),
        sortie2=sorties.construire_sortie2(lignes_complet, planning_complet),
        alertes=alertes(planning_complet, lignes_complet),
        quarantaine=donnees.quarantaine, camions_base=donnees.camions_base,
    )


def afficher(r: Resultats, camion_detail: int, fichiers: dict[str, pd.DataFrame]) -> None:
    """Affiche le résumé du moteur dans la console.

    Args:
        r: résultats du moteur.
        camion_detail: numéro du camion dont on affiche le contenu.
        fichiers: fichiers écrits, nom -> table (voir ``sorties.exporter``).
    """
    besoins = donnees.besoins
    print(f"Besoins à consolider : {len(besoins)} lignes, {besoins.groupby(['plant', 'supplier_id']).ngroups} couples, "
          f"{len(donnees.USINES)} usines, du {donnees.DEBUT:%d/%m} au {donnees.FIN:%d/%m} "
          f"(livraisons possibles dès le {donnees.DEBUT_LIVRAISONS:%d/%m})")
    print(f"Camions réservés (lignes sans poids) : {donnees.NB_RESERVE}, {eur(donnees.COUT_RESERVE)}")
    print(f"Variante retenue : {r.principale} ({len(r.journaux[r.principale])} changements de profil au lissage)")
    print(f"Report : {r.journal_report['lignes_reportees'].sum()} lignes reportées sur le jour fixe suivant, "
          f"gain {eur(r.journal_report['gain'].sum())}")

    print("\n=== Contraintes ===")
    print(r.controle_contraintes.drop(columns="Description").to_string())

    print(f"\n=== Alertes : {len(r.alertes)} cas où une règle ne peut pas être respectée (détail dans alertes.csv) ===")
    print(r.alertes.groupby(["regle", "cause"]).size().rename("cas").to_string())

    print("\n=== Économies (camions réservés compris) ===")
    print(r.bilan.to_string(index=False, na_rep="–", formatters={
        "Coût": eur, "Économie vs baseline": eur, "Économie (%)": pourcent, "Avance moyenne (j)": nombre}))

    print("\n=== Économies par usine ===")
    print(r.par_usine.to_string(formatters={
        "camions_baseline": "{:.0f}".format, "camions_final": "{:.0f}".format, "cout_baseline": eur,
        "cout_final": eur, "economie": eur, "economie_pct": pourcent}))

    print(f"\n=== Sortie 1 : le profil à appliquer pour chaque couple ({len(r.sortie1)} couples, aperçu des 10 premiers) ===")
    print(r.sortie1.head(10).to_string(index=False, formatters={
        "Distance": lambda d: "inconnue" if pd.isna(d) else f"{d:.0f} km", "Livraisons / sem. actuelles": nombre,
        "Fréquence cible": "{} / semaine".format, "Camions / sem.": nombre, "Remplissage poids": pourcent}))

    resume, table_camion = sorties.detail_camion(r.sortie2, camion_detail)
    print(f"\n=== Sortie 2 : les materials regroupés dans chaque camion ({r.sortie2['camion_id'].nunique()} camions) ===")
    print(resume)
    print(table_camion)

    print(f"\nFichiers écrits dans {config.SORTIE} :")
    for nom_fichier, table in fichiers.items():
        print(f"  {nom_fichier:<22}: {len(table)} lignes")


def main() -> None:
    """Point d'entrée en ligne de commande : calcule, écrit les CSV de sortie et affiche le résumé.

    Arguments optionnels : numéro du camion à détailler (par défaut, celui qui regroupe le plus de lignes) et
    ``--schedule`` (un schedule brut à la place des données du projet).
    """
    if hasattr(sys.stdout, "reconfigure"):          # console Windows (accents)
        sys.stdout.reconfigure(encoding="utf-8")
    parseur = argparse.ArgumentParser(description="Moteur de consolidation des livraisons")
    parseur.add_argument("camion", nargs="?", type=int, help="numéro du camion à détailler")
    parseur.add_argument("--schedule", help="schedule brut (CSV au format de data/bronze/released_schedule.csv)")
    arguments = parseur.parse_args()

    schedule = pd.read_csv(arguments.schedule, encoding="utf-8-sig") if arguments.schedule else None
    r = executer(schedule)
    fichiers = sorties.exporter(r.sortie1, r.sortie2, r.bilan, r.alertes)

    camion_detail = arguments.camion if arguments.camion is not None else sorties.camion_le_plus_charge(r.planning_complet)
    assert camion_detail in set(r.sortie2["camion_id"]), f"camion {camion_detail} inconnu (1 à {r.sortie2['camion_id'].max()})"
    afficher(r, camion_detail, fichiers)


if __name__ == "__main__":
    main()
