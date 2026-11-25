"""Partie 3 : table de correspondance fournisseur -> distance, à compléter.

Un fournisseur sans distance est chiffré au tarif le plus cher (tranche ``> 650 km``). Les distances saisies ici
sont enregistrées à part (``data/mapping/distances_saisies.csv``), sans modifier le fichier source
``data/bronze/distances.csv`` ; le moteur les utilise dès la prochaine analyse. Le fichier complété peut aussi
être téléchargé, au format de ``distances.csv``.
"""
import pandas as pd
import streamlit as st

from backend.config import DATA, DISTANCES_SAISIES_PATH
from backend.couts import DISTANCE_PAR_DEFAUT
from backend.formatage import eur, nombre
from frontend import moteur
from frontend.composants import carte, hero, pastille, section

# ---------- Fournisseurs à afficher : ceux de l'analyse en cours, sinon ceux du schedule du projet ----------
analyse = st.session_state.get("analyse")
if analyse is not None:
    r = analyse["resultats"]
    table = moteur.table_mapping(r.lignes_complet, r.planning_complet)
    contexte = f"usines, lignes et coût de l'analyse en cours ({analyse['source']})"
else:
    projet = pd.read_csv(DATA / "bronze" / "released_schedule.csv")
    projet = projet[pd.to_numeric(projet["schedule_quantity"], errors="coerce") > 0]
    table = moteur.table_mapping(projet, None)
    contexte = "usines et lignes du schedule du projet (lance une analyse pour voir aussi le coût)"

# Lisibilité : pas de « None » dans les colonnes d'information (les distances inconnues restent vides)
table["usines"] = table["usines"].fillna("non livré")
table["lignes"] = table["lignes"].fillna(0).astype(int)
table["saisie_le"] = table["saisie_le"].fillna("")
if analyse is not None:
    table["cout"] = table["cout"].fillna(0.0)

a_completer = table["distance"].isna()
utilises = table["lignes"].fillna(0) > 0
hero("Mapping", "Distances des fournisseurs",
     "Table de correspondance fournisseur → distance. Complète les distances manquantes : le moteur les utilise "
     "dès la prochaine analyse, au lieu du tarif maximal.", stats=[
         ("Fournisseurs", nombre(len(table))), ("Sans distance", nombre(int(a_completer.sum()))),
         ("Dont livrés", nombre(int((a_completer & utilises).sum()))),
         ("Saisies", nombre(int((table["statut"] == "saisie").sum())))])

cout_en_jeu = table.loc[a_completer, "cout"].sum()
st.html(pastille(f"sans distance, un fournisseur est chiffré à {DISTANCE_PAR_DEFAUT} km (tarif « > 650 km »)",
                 "info")
        + (pastille(f"{eur(cout_en_jeu)} de transport chiffrés ainsi dans l'analyse en cours", "ko")
           if cout_en_jeu > 0 else "")
        + pastille(f"saisies enregistrées dans {DISTANCES_SAISIES_PATH.relative_to(DATA.parent).as_posix()}, "
                   "le fichier source n'est pas modifié", "ok"))

# ---------- Table à compléter ----------
section("Table de correspondance", contexte)
c_filtre, c_recherche = st.columns([1, 2], vertical_alignment="bottom")
filtre = c_filtre.segmented_control("Afficher", ["À compléter", "Saisies", "Tous"], default="À compléter",
                                    required=True, key="mapping_filtre", width="stretch")
recherche = c_recherche.text_input("Rechercher un fournisseur", placeholder="SUP_00130", key="mapping_recherche")
vue = table[a_completer] if filtre == "À compléter" else table[table["statut"] == "saisie"] if filtre == "Saisies" \
    else table
if recherche:
    vue = vue[vue["fournisseur"].str.contains(recherche.strip(), case=False, regex=False)]

with carte("mapping"):
    if vue.empty:
        st.caption("Aucun fournisseur à compléter." if filtre == "À compléter" else "Aucun fournisseur.")
        modifiee = vue
    else:
        modifiee = st.data_editor(
            vue, hide_index=True, width="stretch", height=min(38 * len(vue) + 40, 560),
            key=f"mapping_table_{filtre}_{recherche}",
            disabled=["fournisseur", "usines", "lignes", "cout", "distance_source", "statut", "saisie_le"],
            column_config={
                "fournisseur": st.column_config.TextColumn("Fournisseur"),
                "usines": st.column_config.TextColumn("Usines livrées"),
                "lignes": st.column_config.NumberColumn("Lignes", format="%d"),
                "cout": st.column_config.NumberColumn("Coût de transport", format="%.0f €",
                                                      help="Coût de ses camions dans l'analyse en cours."),
                "distance_source": st.column_config.NumberColumn("Distance source", format="%d km",
                                                                 help="Valeur du fichier data/bronze/distances.csv."),
                "distance": st.column_config.NumberColumn(
                    "Distance (km) ✎", min_value=1, max_value=5000, step=1, format="%d km", required=False,
                    help="À saisir ou corriger. Vide : la distance du fichier source (ou, à défaut, le tarif maximal)."),
                "statut": st.column_config.TextColumn("Statut"),
                "saisie_le": st.column_config.TextColumn("Saisie le"),
            })
    changements = int((modifiee["distance"].fillna(-1) != vue["distance"].fillna(-1)).sum()) if len(vue) else 0

    c_info, c_annuler, c_enregistrer = st.columns([3, 1, 1], vertical_alignment="center")
    c_info.caption(f"{changements} distance(s) modifiée(s), pas encore enregistrée(s)." if changements
                   else "Modifie la colonne « Distance (km) ✎ », puis enregistre.")
    if c_annuler.button("Annuler", icon=":material/undo:", disabled=not changements, width="stretch"):
        st.session_state.pop(f"mapping_table_{filtre}_{recherche}", None)
        st.rerun()
    if c_enregistrer.button("Enregistrer", type="primary", icon=":material/save:", disabled=not changements,
                            width="stretch"):
        complete = table.set_index("fournisseur")
        complete.loc[modifiee["fournisseur"], "distance"] = modifiee["distance"].to_numpy()
        try:
            nb = moteur.enregistrer_mapping(complete.reset_index())
        except ValueError as erreur:
            st.error(str(erreur), icon=":material/error:")
        else:
            st.session_state.pop(f"mapping_table_{filtre}_{recherche}", None)
            st.session_state["mapping_enregistre"] = nb
            st.rerun()

if "mapping_enregistre" in st.session_state:
    st.toast(f"Distances enregistrées ({st.session_state.pop('mapping_enregistre')} saisie(s) au total). "
             "Relance l'analyse pour en tenir compte.", icon=":material/check_circle:")

# ---------- Fichier complété ----------
with st.expander("Fichier des distances complété", icon=":material/download:"):
    completees = moteur.distances_completees()
    st.caption("Le fichier source complété par les saisies, au format de data/bronze/distances.csv : à transmettre "
               "à qui gère le référentiel, ou à mettre à la place du fichier source.")
    st.download_button("Télécharger distances.csv", completees.to_csv(index=False).encode("utf-8-sig"),
                       "distances.csv", "text/csv", icon=":material/download:")
    if (table["statut"] == "saisie").any():
        st.markdown("**Annuler des saisies**")
        a_effacer = st.multiselect("Saisies à effacer", table.loc[table["statut"] == "saisie", "fournisseur"],
                                   placeholder="Choisis des fournisseurs", label_visibility="collapsed")
        if st.button("Effacer ces saisies", icon=":material/delete:", disabled=not a_effacer):
            complete = table.assign(distance=table["distance"].where(~table["fournisseur"].isin(a_effacer)))
            moteur.enregistrer_mapping(complete)
            st.rerun()
