"""Résultats du moteur : ce que retourne ``main.executer()``, et ce qu'un front end peut afficher."""
from dataclasses import dataclass

import pandas as pd

from .jours_fixes import Scenarios
from .typage import Choix


@dataclass
class Resultats:
    """Tous les résultats d'une exécution du moteur.

    Attributes:
        scenarios: camions, coût et charge de chaque couple pour chaque profil (bloc 1).
        choix_initiaux: par variante, le profil le moins cher de chaque couple, avant lissage.
        choix_lisses: par variante, le profil de chaque couple après lissage.
        journaux: par variante, les changements de profil faits par le lissage.
        principale: nom de la variante retenue (la moins chère après lissage).
        journal_report: par couple, les lignes reportées et le gain du bloc 4.
        plannings: planning de chaque étape, ``nom -> (camions, lignes livrées)``, sans les camions réservés.
        planning: planning final, camions optimisés seulement (une ligne par camion).
        planning_complet: planning final, camions réservés compris (une ligne par camion).
        lignes_complet: lignes de besoin livrées, avec leur ``camion_id`` et leur ``date_livraison``.
        controle_contraintes: synthèse des contraintes C1 à C10 (une ligne par contrainte).
        validation: contrôles de cohérence du planning final (``OK`` / ``ÉCHEC``).
        bilan: tableau des économies, une ligne par version.
        par_usine: économies par usine, avec une ligne ``Total``.
        sortie1: profil à appliquer pour chaque couple.
        sortie2: materials chargés dans chaque camion.
        quarantaine: lignes mises en quarantaine au nettoyage, avec leurs ``flags``.
        camions_base: camions de la baseline (hors camions réservés), avec leur coût.
    """

    scenarios: Scenarios
    choix_initiaux: dict[str, Choix]
    choix_lisses: dict[str, Choix]
    journaux: dict[str, pd.DataFrame]
    principale: str
    journal_report: pd.DataFrame
    plannings: dict[str, tuple[pd.DataFrame, pd.DataFrame]]
    planning: pd.DataFrame
    planning_complet: pd.DataFrame
    lignes_complet: pd.DataFrame
    controle_contraintes: pd.DataFrame
    validation: pd.DataFrame
    bilan: pd.DataFrame
    par_usine: pd.DataFrame
    sortie1: pd.DataFrame
    sortie2: pd.DataFrame
    quarantaine: pd.DataFrame
    camions_base: pd.DataFrame
