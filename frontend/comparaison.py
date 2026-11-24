"""Comparaison de deux runs (utilisée par les deux pages).

Lecture : on compare un run « B » à un run de référence « A ».

1. Les périodes planifiées : si elles diffèrent, les totaux ne sont pas comparables et les chiffres clés passent
   aux valeurs par semaine.
2. Les chiffres clés (valeur de B, écart avec A).
3. Ce qui a changé dans le planning : couples nouveaux, disparus, ou dont les jours fixes ont changé (sortie 1).
4. Le détail des métriques, par catégorie, avec l'effet de chaque écart : mieux, moins bien, identique, ou neutre
   (une métrique du schedule d'entrée décrit le fichier, elle n'est ni bonne ni mauvaise).
"""
from html import escape
from typing import Final

import pandas as pd
import streamlit as st

from backend.formatage import eur, nombre

from . import graphiques
from .composants import carte, ecart_texte, pastille, section

Periode = tuple[pd.Timestamp, pd.Timestamp, int]
"""Période planifiée d'un run : premier jour, dernier jour, nombre de semaines."""

SENS: Final[dict[str, int]] = {
    "coût total (€)": -1, "coût baseline (€)": 0, "économie vs baseline (€)": 1, "économie vs baseline (%)": 1,
    "coût par tonne livrée (€)": -1, "camions": -1, "camions baseline": 0, "camions réservés": -1,
    "remplissage poids moyen (%)": 1, "remplissage volume moyen (%)": 1, "lignes livrées": 0,
    "avance moyenne (j)": -1, "livrées le jour du besoin (%)": 1, "semaines hors tolérance": -1,
    "contraintes dures violées": -1, "coût / semaine (€)": -1, "économie / semaine (€)": 1,
    "camions / semaine": -1, "poids livré / semaine (t)": 0, "lignes livrées / semaine": 0,
}
"""Sens favorable de chaque métrique : 1 = plus haut est mieux, -1 = plus bas est mieux, 0 = neutre
(absente = neutre, comme les métriques du schedule d'entrée)."""

CHIFFRES_CLES: Final[list[tuple[str, str, str, str]]] = [
    ("coût total (€)", "Coût total", "€", ":material/euro:"),
    ("économie vs baseline (%)", "Économie", "pt", ":material/savings:"),
    ("camions", "Camions", "", ":material/local_shipping:"),
    ("remplissage poids moyen (%)", "Remplissage moyen", "pt", ":material/scale:"),
    ("lignes", "Lignes du schedule", "", ":material/table_rows:"),
]
"""Cartes du haut, quand les deux runs couvrent la même période : (métrique, libellé, unité de l'écart, icône)."""
CHIFFRES_CLES_SEMAINE: Final[list[tuple[str, str, str, str]]] = [
    ("coût / semaine (€)", "Coût / semaine", "€", ":material/euro:"),
    ("économie vs baseline (%)", "Économie", "pt", ":material/savings:"),
    ("camions / semaine", "Camions / semaine", "", ":material/local_shipping:"),
    ("remplissage poids moyen (%)", "Remplissage moyen", "pt", ":material/scale:"),
    ("poids livré / semaine (t)", "Poids livré / semaine (t)", "", ":material/weight:"),
]
"""Cartes du haut quand les périodes diffèrent : des valeurs par semaine, comparables."""
ORDRE_CATEGORIES: Final[list[str]] = ["Coût", "Par semaine", "Camions", "Service", "Schedule"]
STATUTS: Final[list[str]] = ["nouveau couple", "couple disparu", "jours fixes changés", "inchangé"]
"""Statut d'un couple fournisseur × usine entre deux plannings."""


def comparer(a: dict[str, float], b: dict[str, float], categories: dict[str, str]) -> pd.DataFrame:
    """Calcule l'écart de chaque métrique entre deux runs.

    Args:
        a: métriques du run de référence (nom -> valeur).
        b: métriques du run comparé.
        categories: catégorie de chaque métrique (nom -> catégorie).

    Returns:
        Une ligne par métrique présente dans les deux runs : ``catégorie``, ``métrique``, ``A``, ``B``,
        ``écart`` (B - A), ``écart %`` (vide quand A vaut 0) et ``effet`` (mieux, moins bien, identique, neutre).
    """
    noms = [m for m in b if m in a]
    table = pd.DataFrame({"catégorie": [categories.get(m, "Autre") for m in noms], "métrique": noms,
                          "A": [a[m] for m in noms], "B": [b[m] for m in noms]})
    table["écart"] = (table["B"] - table["A"]).round(2)
    table["écart %"] = (table["écart"] / table["A"].where(table["A"] != 0) * 100).round(2)

    def effet(nom: str, ecart: float) -> str:
        """Effet de l'écart d'une métrique, selon son sens favorable."""
        sens = SENS.get(nom, 0)
        if abs(ecart) < 0.005:
            return "= identique"
        if sens == 0:
            return "· neutre"
        return "▲ mieux" if ecart * sens > 0 else "▼ moins bien"

    table["effet"] = [effet(n, e) for n, e in zip(table["métrique"], table["écart"])]
    return table


COLONNES_SORTIE1: dict[str, str] = {"Fournisseur": "fournisseur", "Usine": "usine", "Jours": "jours",
                                    "Camions / sem.": "camions_semaine"}
"""En-têtes de la sortie 1 -> noms utilisés ici (les runs enregistrés avant le renommage gardent les anciens noms)."""


def normaliser_sortie1(sortie1: pd.DataFrame) -> pd.DataFrame:
    """Ramène une sortie 1, ancienne ou nouvelle, aux noms de colonnes ``fournisseur``, ``usine``, ``jours``,
    ``camions_semaine``."""
    return sortie1.rename(columns=COLONNES_SORTIE1)


def changements(sortie1_a: pd.DataFrame, sortie1_b: pd.DataFrame) -> pd.DataFrame:
    """Compare les profils de livraison (sortie 1) de deux plannings, couple par couple.

    Args:
        sortie1_a: sortie 1 du run de référence.
        sortie1_b: sortie 1 du run comparé.

    Returns:
        Une ligne par couple présent dans l'un ou l'autre : ``usine``, ``fournisseur``, ``statut`` (voir
        ``STATUTS``), ``jours A``, ``jours B``, ``camions / sem. A``, ``camions / sem. B``.
    """
    cles = ["usine", "fournisseur"]
    sortie1_a, sortie1_b = normaliser_sortie1(sortie1_a), normaliser_sortie1(sortie1_b)
    a = sortie1_a[cles + ["jours", "camions_semaine"]]
    b = sortie1_b[cles + ["jours", "camions_semaine"]]
    t = a.merge(b, on=cles, how="outer", suffixes=(" A", " B"), indicator=True)
    present = t["_merge"].astype(str)
    statut = present.map({"right_only": "nouveau couple", "left_only": "couple disparu", "both": "inchangé"})
    statut = statut.where(~((present == "both") & (t["jours A"] != t["jours B"])), "jours fixes changés")
    t = t.assign(statut=pd.Categorical(statut, STATUTS, ordered=True)).drop(columns="_merge")
    t = t.rename(columns={"camions_semaine A": "camions / sem. A", "camions_semaine B": "camions / sem. B"})
    t[["jours A", "jours B"]] = t[["jours A", "jours B"]].fillna("—")          # couple absent d'un des plannings
    return t.sort_values(["statut", "usine", "fournisseur"]).reset_index(drop=True)[
        ["usine", "fournisseur", "statut", "jours A", "jours B", "camions / sem. A", "camions / sem. B"]]


def _texte_periode(p: Periode | None) -> str:
    """Période en clair, par exemple ``09/11 → 18/12/2026 (6 sem.)``."""
    return "période inconnue" if p is None else f"{p[0]:%d/%m} → {p[1]:%d/%m/%Y} ({p[2]} sem.)"


def afficher_comparaison(table: pd.DataFrame, libelle_a: str, libelle_b: str, cle: str,
                         periode_a: Periode | None = None, periode_b: Periode | None = None,
                         sortie1_a: pd.DataFrame | None = None, sortie1_b: pd.DataFrame | None = None) -> None:
    """Affiche une comparaison : périodes, chiffres clés, changements du planning, détail des métriques.

    Args:
        table: résultat de ``comparer``.
        libelle_a: nom du run de référence (par exemple le fichier et la date).
        libelle_b: nom du run comparé.
        cle: préfixe des clés Streamlit (une comparaison par page).
        periode_a: période planifiée du run de référence (None : inconnue).
        periode_b: période planifiée du run comparé.
        sortie1_a: sortie 1 du run de référence (None : la section des changements n'est pas affichée).
        sortie1_b: sortie 1 du run comparé.
    """
    st.html(f'<div class="appel">⇄ <span><b>{escape(libelle_b)}</b> · {escape(_texte_periode(periode_b))}'
            f"<br>comparé à <b>{escape(libelle_a)}</b> · {escape(_texte_periode(periode_a))} (référence). "
            "Les écarts sont ceux de B par rapport à A.</span></div>")
    meme_periode = periode_a is not None and periode_b is not None and periode_a == periode_b
    if not meme_periode:
        raison = ("une des périodes est inconnue (run enregistré avant cette version)"
                  if periode_a is None or periode_b is None else
                  f"{periode_a[2]} semaine(s) contre {periode_b[2]}" if periode_a[2] != periode_b[2] else
                  "les dates diffèrent")
        st.html(pastille(f"Périodes différentes : {raison}. Les totaux ne sont pas comparables, "
                         "les chiffres clés sont donnés par semaine.", "ko"))

    # ---------- Chiffres clés ----------
    valeurs = table.set_index("métrique")
    cartes = CHIFFRES_CLES if meme_periode else CHIFFRES_CLES_SEMAINE
    for colonne, (nom, libelle, unite, icone) in zip(st.columns(len(cartes)), cartes):
        if nom not in valeurs.index:
            colonne.metric(libelle, "–", border=True, icon=icone, help="Métrique absente d'un des deux runs.")
            continue
        ligne = valeurs.loc[nom]

        def texte(v: float, u: str = unite) -> str:
            """Valeur affichée dans la carte."""
            return eur(v) if u == "€" else f"{nombre(v)}{' %' if u == 'pt' else ''}"

        sens = SENS.get(nom, 0)
        colonne.metric(libelle, texte(ligne["B"]), ecart_texte(ligne["écart"], unite), border=True, icon=icone,
                       delta_color="off" if sens == 0 else ("normal" if sens > 0 else "inverse"),
                       delta_description=f"référence : {texte(ligne['A'])}")

    # ---------- Ce qui a changé dans le planning ----------
    if sortie1_a is not None and sortie1_b is not None:
        section("Ce qui a changé dans le planning", "couples fournisseur × usine (sortie 1)")
        diff = changements(sortie1_a, sortie1_b)
        compte = diff["statut"].value_counts()
        fournisseurs_a = set(normaliser_sortie1(sortie1_a)["fournisseur"])
        fournisseurs_b = set(normaliser_sortie1(sortie1_b)["fournisseur"])
        st.html(pastille(f"{compte.get('nouveau couple', 0)} nouveau(x) couple(s)", "info")
                + pastille(f"{compte.get('couple disparu', 0)} couple(s) disparu(s)", "info")
                + pastille(f"{compte.get('jours fixes changés', 0)} couple(s) aux jours fixes changés", "info")
                + pastille(f"{compte.get('inchangé', 0)} inchangé(s)", "ok")
                + pastille(f"fournisseurs : +{len(fournisseurs_b - fournisseurs_a)} / "
                           f"−{len(fournisseurs_a - fournisseurs_b)}", "info"))
        bouge = diff[diff["statut"] != "inchangé"]
        gauche, droite = st.columns([1, 1.6], gap="medium")
        with carte(f"{cle}-changements", gauche):
            if bouge.empty:
                st.markdown("**Changements par usine**")
                st.caption("Aucun couple n'a changé entre ces deux plannings.")
            else:
                graphiques.afficher(graphiques.changements_par_usine(bouge), cle=f"{cle}-changements-graphique")
        with droite:
            filtre = st.pills("Afficher", STATUTS, selection_mode="multi", default=STATUTS[:3], key=f"{cle}-statuts")
            vue = diff[diff["statut"].isin(filtre or STATUTS)]
            st.dataframe(vue, hide_index=True, width="stretch", height=min(38 * len(vue) + 40, 380),
                         column_config={"camions / sem. A": st.column_config.NumberColumn(format="%.2f"),
                                        "camions / sem. B": st.column_config.NumberColumn(format="%.2f")})

    # ---------- Détail des métriques ----------
    section("Détail des métriques", "une catégorie à la fois")
    jugees = table[table["effet"].isin(["▲ mieux", "▼ moins bien"])]
    mieux, moins = int((jugees["effet"] == "▲ mieux").sum()), int((jugees["effet"] == "▼ moins bien").sum())
    st.html(pastille(f"{mieux} métrique(s) en mieux", "ok") + pastille(f"{moins} métrique(s) en moins bien",
                                                                        "ko" if moins else "ok")
            + pastille(f"{int((table['effet'] == '= identique').sum())} identique(s)", "info"))
    presentes = [c for c in ORDRE_CATEGORIES if c in set(table["catégorie"])]
    presentes += [c for c in dict.fromkeys(table["catégorie"]) if c not in presentes]
    defaut = "Par semaine" if not meme_periode and "Par semaine" in presentes else presentes[0]
    categorie = st.segmented_control("Catégorie", presentes, default=defaut, required=True, key=f"{cle}-categorie")
    detail = table[table["catégorie"] == categorie].drop(columns="catégorie")
    gauche, droite = st.columns([1, 1.25], gap="medium")
    with carte(f"{cle}-ecarts", gauche):
        trace = detail.dropna(subset=["écart %"])
        if trace.empty or (trace["écart %"].abs() < 0.005).all():
            st.markdown(f"**{categorie} : écart en %**")
            st.caption("Aucune métrique de cette catégorie ne change entre ces deux runs.")
        else:
            graphiques.afficher(graphiques.barres_ecarts(trace["métrique"], trace["écart %"], trace["effet"],
                                                         f"{categorie} : écart en %"), cle=f"{cle}-barres")
    with droite:
        st.dataframe(
            detail, hide_index=True, width="stretch", height=38 * len(detail) + 40,
            column_config={
                "métrique": st.column_config.TextColumn("Métrique", width="medium"),
                "A": st.column_config.NumberColumn("A (référence)", format="localized"),
                "B": st.column_config.NumberColumn("B", format="localized"),
                "écart": st.column_config.NumberColumn("Écart", format="localized"),
                "écart %": st.column_config.NumberColumn("Écart %", format="%+.1f %%"),
                "effet": st.column_config.TextColumn("Effet"),
            })
