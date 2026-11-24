"""Lien entre le dashboard et le backend : lecture du schedule, exécution du moteur, métriques d'un run.

Le moteur tourne sur le schedule choisi (celui du projet ou un CSV importé) : nettoyage (milestone 1),
baseline (milestone 2), puis consolidation (``main.executer``).

Les métriques sont rangées par catégorie (``Schedule``, ``Coût``, ``Camions``, ``Service``) : ce sont elles
qui sont historisées run après run et comparées d'un run à l'autre.
"""
import threading
from io import BytesIO

import pandas as pd
import streamlit as st

import main
from backend.config import COLONNES_SCHEDULE, DATES_EXCLUES, POIDS_MAX, VOLUME_MAX
from backend.nettoyage import verifier_colonnes
from backend.resultats import Resultats

Metriques = dict[str, dict[str, float]]
"""Métriques d'un run : catégorie -> nom de la métrique -> valeur."""

_VERROU = threading.Lock()
"""Le backend garde ses données d'entrée en mémoire (module ``donnees``) : un seul calcul à la fois."""

__all__ = ["COLONNES_SCHEDULE", "Metriques", "lire_schedule", "colonnes_manquantes", "profil_schedule",
           "executer_moteur", "etapes_nettoyage", "toutes_metriques", "aplatir"]


def lire_schedule(contenu: bytes, separateur: str = ",") -> pd.DataFrame:
    """Lit un schedule CSV.

    Args:
        contenu: contenu brut du fichier.
        separateur: séparateur de colonnes.

    Returns:
        Le schedule, avec la colonne ``date`` en dates (si elle existe ; date illisible -> NaT).
    """
    schedule = pd.read_csv(BytesIO(contenu), sep=separateur, encoding="utf-8-sig")
    if "date" in schedule:
        schedule["date"] = pd.to_datetime(schedule["date"], errors="coerce")
    return schedule


def colonnes_manquantes(schedule: pd.DataFrame) -> list[str]:
    """Liste les colonnes obligatoires absentes d'un schedule (liste vide = schedule exploitable)."""
    return verifier_colonnes(schedule)


def profil_schedule(schedule: pd.DataFrame) -> dict[str, float]:
    """Calcule les indicateurs d'entrée d'un schedule brut (volume et qualité des données).

    Args:
        schedule: schedule avec les colonnes de ``COLONNES_SCHEDULE``.

    Returns:
        Indicateurs : lignes, couples, fournisseurs, usines, materials, poids total, lignes à quantité nulle,
        lignes sans poids, lignes de plus de 24,5 t.
    """
    poids = pd.to_numeric(schedule["weight"], errors="coerce")
    quantite = pd.to_numeric(schedule["schedule_quantity"], errors="coerce")
    utiles = quantite > 0
    return {
        "lignes": float(len(schedule)),
        "couples fournisseur × usine": float(schedule.groupby(["supplier_id", "plant"]).ngroups),
        "fournisseurs": float(schedule["supplier_id"].nunique()),
        "usines": float(schedule["plant"].nunique()),
        "materials": float(schedule["material"].nunique()),
        "poids total (t)": round(float(poids.sum()) / 1000, 2),
        "lignes à quantité nulle (%)": round(float((~utiles).mean()) * 100, 2),
        "lignes sans poids": float((poids.isna() & utiles).sum()),
        "lignes de plus de 24,5 t": float((poids > POIDS_MAX).sum()),
    }


@st.cache_resource(show_spinner=False, max_entries=6)
def executer_moteur(contenu: bytes, separateur: str) -> Resultats:
    """Nettoie le schedule, construit sa baseline et fait tourner le moteur.

    Le résultat est gardé en cache pour ce contenu exact : relancer le même fichier est instantané.

    Args:
        contenu: contenu brut du fichier CSV.
        separateur: séparateur de colonnes.

    Returns:
        Les résultats du moteur.

    Raises:
        ValueError: si le schedule n'est pas exploitable.
        AssertionError: si le planning obtenu viole une contrainte dure.
    """
    with _VERROU:
        return main.executer(lire_schedule(contenu, separateur))


def etapes_nettoyage(schedule: pd.DataFrame, r: Resultats) -> pd.DataFrame:
    """Décompte des lignes à chaque étape, du schedule brut aux lignes consolidées.

    Args:
        schedule: schedule brut.
        r: résultats du moteur sur ce schedule.

    Returns:
        Une ligne par étape : ``étape``, ``lignes`` et ``détail``.
    """
    date = pd.to_datetime(schedule["date"], errors="coerce")
    quantite = pd.to_numeric(schedule["schedule_quantity"], errors="coerce")
    retirees_qte = int((date.notna() & ~(quantite > 0)).sum())
    retirees_date = int((date.isna() | (date.isin(pd.to_datetime(DATES_EXCLUES)) & (quantite > 0))).sum())
    q = r.quarantaine
    sans_poids = int(q["weight"].isna().sum())
    sans_volume = int((q["weight"].notna() & q["volume"].isna() & (q["weight"] <= POIDS_MAX)).sum())
    exclues = int((q["weight"] > POIDS_MAX).sum())
    consolidees = int((~r.lignes_complet["reserve"]).sum())
    return pd.DataFrame([
        {"étape": "Schedule brut", "lignes": len(schedule), "détail": "fichier d'entrée"},
        {"étape": "Quantité nulle", "lignes": -retirees_qte, "détail": "aucun besoin ce jour-là : retirées"},
        {"étape": "Date exclue ou illisible", "lignes": -retirees_date,
         "détail": f"dates exclues : {', '.join(DATES_EXCLUES)}"},
        {"étape": "Quarantaine", "lignes": len(q), "détail": "lignes avec au moins un flag"},
        {"étape": "  dont sans poids", "lignes": sans_poids, "détail": "un camion réservé par ligne"},
        {"étape": "  dont sans volume", "lignes": sans_volume, "détail": "poids connu : un camion réservé par ligne"},
        {"étape": "  dont plus de 24,5 t", "lignes": exclues, "détail": "exclues, en attente du client"},
        {"étape": "Lignes consolidées", "lignes": consolidees, "détail": "silver + quarantaine au poids connu"},
    ])


def metriques_moteur(r: Resultats) -> Metriques:
    """Calcule les métriques de résultat d'un run du moteur.

    Args:
        r: résultats du moteur.

    Returns:
        Métriques par catégorie : ``Coût``, ``Camions`` et ``Service``.
    """
    planning = r.planning_complet
    opti = planning[~planning["reserve"]]
    final = r.bilan.iloc[-1]
    baseline = r.bilan.iloc[0]
    contraintes = r.controle_contraintes
    poids_total_t = r.lignes_complet["weight"].sum() / 1000
    return {
        "Coût": {
            "coût total (€)": round(float(planning["cout"].sum()), 2),
            "coût baseline (€)": round(float(baseline["Coût"]), 2),
            "économie vs baseline (€)": round(float(final["Économie vs baseline"]), 2),
            "économie vs baseline (%)": round(float(final["Économie (%)"]) * 100, 2),
            "coût par tonne livrée (€)": round(float(planning["cout"].sum() / poids_total_t), 2),
        },
        "Camions": {
            "camions": float(len(planning)),
            "camions baseline": float(baseline["Camions"]),
            "camions réservés": float(planning["reserve"].sum()),
            "remplissage poids moyen (%)": round(float((opti["poids"] / POIDS_MAX).mean()) * 100, 2),
            "remplissage volume moyen (%)": round(float((opti["volume"] / VOLUME_MAX).mean()) * 100, 2),
        },
        "Service": {
            "lignes livrées": float(len(r.lignes_complet)),
            "avance moyenne (j)": round(float(r.lignes_complet["avance_jours"].mean()), 2),
            "livrées le jour du besoin (%)": round(float((r.lignes_complet["avance_jours"] == 0).mean()) * 100, 2),
            "semaines hors tolérance": float(contraintes.loc["C10", "Violations"]),
            "contraintes dures violées": float(contraintes.loc[contraintes["Type"] == "dure", "Violations"].sum()),
        },
    }


def periode(r: Resultats) -> tuple[pd.Timestamp, pd.Timestamp, int]:
    """Horizon du planning d'un run : dates des besoins livrés (après nettoyage) et nombre de semaines.

    Args:
        r: résultats du moteur.

    Returns:
        ``(premier jour, dernier jour, nombre de semaines ISO couvertes)``.
    """
    dates = r.lignes_complet["need_date"]
    semaines = dates.dt.isocalendar()[["year", "week"]].drop_duplicates()
    return dates.min(), dates.max(), len(semaines)


def toutes_metriques(schedule: pd.DataFrame, r: Resultats) -> Metriques:
    """Rassemble les métriques d'un run : schedule d'entrée, résultats du moteur, et valeurs par semaine.

    Les valeurs par semaine permettent de comparer deux plannings qui ne couvrent pas la même période.

    Args:
        schedule: schedule d'entrée.
        r: résultats du moteur sur ce schedule.

    Returns:
        Toutes les métriques du run, par catégorie.
    """
    entree = profil_schedule(schedule)
    entree["lignes en quarantaine"] = float(len(r.quarantaine))
    resultats = metriques_moteur(r)
    _, _, semaines = periode(r)
    entree["semaines planifiées"] = float(semaines)
    par_semaine = {
        "coût / semaine (€)": round(resultats["Coût"]["coût total (€)"] / semaines, 2),
        "économie / semaine (€)": round(resultats["Coût"]["économie vs baseline (€)"] / semaines, 2),
        "camions / semaine": round(resultats["Camions"]["camions"] / semaines, 2),
        "poids livré / semaine (t)": round(float(r.lignes_complet["weight"].sum()) / 1000 / semaines, 2),
        "lignes livrées / semaine": round(resultats["Service"]["lignes livrées"] / semaines, 2),
    }
    return {"Schedule": entree, **resultats, "Par semaine": par_semaine}


def aplatir(metriques: Metriques) -> dict[str, float]:
    """Met les métriques à plat, sans les catégories.

    Args:
        metriques: métriques par catégorie.

    Returns:
        Nom de la métrique -> valeur.
    """
    return {nom: valeur for groupe in metriques.values() for nom, valeur in groupe.items()}
