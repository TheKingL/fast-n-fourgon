"""Lien entre le dashboard et le backend : lecture du schedule, exécution du moteur, métriques d'un run.

Le moteur tourne sur le schedule choisi (celui du projet ou un CSV importé) : nettoyage (milestone 1),
baseline (milestone 2), puis consolidation (``main.executer``).

Les métriques sont rangées par catégorie (``Schedule``, ``Coût``, ``Camions``, ``Service``) : ce sont elles
qui sont historisées run après run et comparées d'un run à l'autre.
"""
import hashlib
import threading
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st

import main
from backend import couts
from backend.config import COLONNES_SCHEDULE, DATES_EXCLUES, DISTANCES_SAISIES_PATH, POIDS_MAX, VOLUME_MAX
from backend.nettoyage import nettoyer, verifier_colonnes
from backend.resultats import Resultats

Metriques = dict[str, dict[str, float]]
"""Métriques d'un run : catégorie -> nom de la métrique -> valeur."""

_VERROU = threading.Lock()
"""Le backend garde ses données d'entrée en mémoire (module ``donnees``) : un seul calcul à la fois."""

__all__ = [
    "COLONNES_SCHEDULE",
    "Metriques",
    "aplatir",
    "colonnes_manquantes",
    "distances_completees",
    "enregistrer_mapping",
    "etapes_nettoyage",
    "executer_moteur",
    "lire_schedule",
    "profil_schedule",
    "qualite_par_fournisseur",
    "table_mapping",
    "toutes_metriques",
    "version_distances",
]


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


def version_distances() -> str:
    """Empreinte des distances saisies dans l'onglet Mapping (chaîne vide s'il n'y en a pas).

    Elle fait partie de la clé du cache du moteur : après une saisie, la même analyse est recalculée.
    """
    if not DISTANCES_SAISIES_PATH.exists():
        return ""
    return hashlib.sha1(DISTANCES_SAISIES_PATH.read_bytes()).hexdigest()


@st.cache_resource(show_spinner=False, max_entries=6)
def executer_moteur(contenu: bytes, separateur: str, distances: str = "") -> Resultats:
    """Nettoie le schedule, construit sa baseline et fait tourner le moteur.

    Le résultat est gardé en cache pour ce contenu exact et ces distances : relancer le même fichier est
    instantané.

    Args:
        contenu: contenu brut du fichier CSV.
        separateur: séparateur de colonnes.
        distances: empreinte des distances saisies (``version_distances``), pour la clé du cache.

    Returns:
        Les résultats du moteur.

    Raises:
        ValueError: si le schedule n'est pas exploitable.
        AssertionError: si le planning obtenu viole une contrainte dure.
    """
    with _VERROU:
        couts.charger_distances()          # relit les distances saisies (éventuellement par un autre utilisateur)
        return main.executer(lire_schedule(contenu, separateur))


def qualite_par_fournisseur(schedule: pd.DataFrame) -> pd.DataFrame:
    """Poids et volumes manquants, fournisseur par fournisseur (lignes gardées après nettoyage).

    Un indicateur pour l'entreprise : une ligne sans poids ou sans volume ne peut pas être consolidée (elle part
    seule, dans un camion réservé) ; les fournisseurs qui renseignent mal leurs envois coûtent donc plus cher.

    Args:
        schedule: schedule brut.

    Returns:
        Une ligne par fournisseur : ``fournisseur``, ``usines``, ``lignes``, ``poids_manquants``,
        ``volumes_manquants``, ``lignes_incompletes`` (poids ou volume manquant) et ``taux_incomplet``
        (proportion) ; triée par nombre de lignes incomplètes décroissant.
    """
    saines, signalees = nettoyer(schedule)
    colonnes = ["supplier_id", "plant", "weight", "volume"]
    lignes = pd.concat([saines[colonnes], signalees[colonnes]], ignore_index=True)
    sans_poids, sans_volume = lignes["weight"].isna(), lignes["volume"].isna()
    par_fournisseur = lignes.groupby("supplier_id")
    t = pd.DataFrame({
        "usines": par_fournisseur["plant"].agg(lambda p: ", ".join(sorted(p.unique()))),
        "lignes": par_fournisseur.size(),
        "poids_manquants": sans_poids.groupby(lignes["supplier_id"]).sum(),
        "volumes_manquants": sans_volume.groupby(lignes["supplier_id"]).sum(),
        "lignes_incompletes": (sans_poids | sans_volume).groupby(lignes["supplier_id"]).sum(),
    })
    t["taux_incomplet"] = (t["lignes_incompletes"] / t["lignes"]).round(4)
    t = t.rename_axis("fournisseur").reset_index()
    return t.sort_values(["lignes_incompletes", "taux_incomplet", "fournisseur"],
                         ascending=[False, False, True]).reset_index(drop=True)


def table_mapping(lignes: pd.DataFrame | None = None, planning: pd.DataFrame | None = None) -> pd.DataFrame:
    """Table de correspondance fournisseur -> distance, à compléter dans l'onglet Mapping.

    Args:
        lignes: lignes de besoin d'un schedule (``supplier_id``, ``plant``), pour les usines livrées et le nombre
            de lignes de chaque fournisseur ; None : ces colonnes restent vides.
        planning: planning d'une analyse (``supplier_id``, ``cout``), pour le coût de transport de chaque
            fournisseur ; None : colonne vide.

    Returns:
        Une ligne par fournisseur (ceux du fichier des distances, des saisies et du schedule) : ``fournisseur``,
        ``usines``, ``lignes``, ``cout``, ``distance_source`` (fichier source), ``distance`` (retenue : saisie si
        elle existe, sinon source), ``statut`` et ``saisie_le`` ; les fournisseurs sans distance d'abord.
    """
    couts.charger_distances()
    saisies = couts.lire_distances_saisies().set_index("supplier_id")
    fournisseurs = set(couts.distances_source.index) | set(saisies.index)
    if lignes is not None:
        fournisseurs |= set(lignes["supplier_id"])
    t = pd.DataFrame(index=pd.Index(sorted(fournisseurs), name="fournisseur"))
    if lignes is not None:
        par_fournisseur = lignes.groupby("supplier_id")
        t["usines"] = par_fournisseur["plant"].agg(lambda p: ", ".join(sorted(p.unique())))
        t["lignes"] = par_fournisseur.size()
    else:
        t["usines"], t["lignes"] = None, float("nan")
    t["cout"] = (planning.groupby("supplier_id")["cout"].sum().round(2) if planning is not None
                 else float("nan"))
    t["distance_source"] = couts.distances_source
    t["distance"] = couts.distance_brute
    t["saisie_le"] = saisies["saisie_le"] if len(saisies) else None
    t["statut"] = "manquante"
    t.loc[t["distance_source"].notna(), "statut"] = "fichier source"
    t.loc[t.index.isin(saisies.index), "statut"] = "saisie"
    t.loc[~t.index.isin(couts.distances_source.index) & t["distance"].isna(), "statut"] = "absent du fichier"
    t["a_completer"] = t["distance"].isna()
    t = t.reset_index().sort_values(["a_completer", "lignes", "fournisseur"], ascending=[False, False, True])
    return t.reset_index(drop=True)[
        ["fournisseur", "usines", "lignes", "cout", "distance_source", "distance", "statut", "saisie_le"]]


def enregistrer_mapping(table: pd.DataFrame) -> int:
    """Enregistre les distances de la table de mapping qui diffèrent du fichier source.

    Une distance vide ou égale à celle du fichier source n'est pas une saisie ; une saisie déjà enregistrée
    garde sa date si sa distance n'a pas changé.

    Args:
        table: table de ``table_mapping``, colonne ``distance`` éventuellement modifiée.

    Returns:
        Le nombre de distances saisies enregistrées.

    Raises:
        ValueError: si une distance n'est pas un nombre strictement positif.
    """
    anciennes = couts.lire_distances_saisies().set_index("supplier_id")["distance"]
    dates = couts.lire_distances_saisies().set_index("supplier_id")["saisie_le"]
    distance = pd.to_numeric(table["distance"], errors="coerce")
    saisie = distance.notna() & (distance != table["distance_source"])
    maintenant = datetime.now().isoformat(timespec="minutes")
    saisies = pd.DataFrame({"supplier_id": table.loc[saisie, "fournisseur"], "distance": distance[saisie]})
    saisies["saisie_le"] = [dates[f] if f in anciennes.index and anciennes[f] == d else maintenant
                            for f, d in zip(saisies["supplier_id"], saisies["distance"])]
    couts.enregistrer_distances_saisies(saisies)
    return len(saisies)


def distances_completees() -> pd.DataFrame:
    """Le fichier des distances complété par les saisies, au format de ``data/bronze/distances.csv``.

    Returns:
        Une ligne par fournisseur : ``supplier_id`` et ``distance`` (vide si toujours inconnue).
    """
    couts.charger_distances()
    return couts.distance_brute.rename_axis("supplier_id").reset_index()


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
        {"étape": "Lignes signalées", "lignes": len(q),
         "détail": "au moins un problème détecté ; gardées, sauf les lignes de plus de 24,5 t"},
        {"étape": "  dont sans poids", "lignes": sans_poids, "détail": "un camion réservé par ligne"},
        {"étape": "  dont sans volume", "lignes": sans_volume, "détail": "poids connu : un camion réservé par ligne"},
        {"étape": "  dont plus de 24,5 t", "lignes": exclues, "détail": "exclues, en attente du client"},
        {"étape": "Lignes consolidées", "lignes": consolidees, "détail": "lignes saines + lignes signalées au poids connu"},
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
    entree["lignes signalées"] = float(len(r.quarantaine))
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
