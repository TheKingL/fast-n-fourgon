"""Partie 2 : historique des runs, évolution des métriques, comparaison de deux runs, journal."""
import pandas as pd
import streamlit as st

from backend.formatage import eur, nombre
from frontend import comparaison, graphiques, historique
from frontend.composants import carte, ecart_texte, hero, section

runs = historique.charger_runs()
metriques = historique.charger_metriques()

if runs.empty:
    hero("Historique", "Aucun run pour l'instant",
         "Lance une analyse dans l'onglet Analyse, puis clique sur « Enregistrer dans l'historique ».")
    st.stop()

# =====================================================================================================
# Filtres
# =====================================================================================================
with st.sidebar:
    st.markdown("#### Filtres")
    debut, fin = runs["horodatage"].min().date(), runs["horodatage"].max().date()
    periode = st.date_input("Période", (debut, fin), min_value=debut, max_value=fin, format="DD/MM/YYYY")
    sources = st.multiselect("Sources", sorted(runs["source"].unique()), placeholder="Toutes")

if isinstance(periode, tuple) and len(periode) == 2:
    de, a = pd.Timestamp(periode[0]), pd.Timestamp(periode[1]) + pd.Timedelta(days=1)
    runs = runs[(runs["horodatage"] >= de) & (runs["horodatage"] < a)]
if sources:
    runs = runs[runs["source"].isin(sources)]
metriques = metriques[metriques["run_id"].isin(runs["run_id"])]
if runs.empty:
    hero("Historique", "Historique & tendances", "Aucun run sur ce filtre.")
    st.stop()

hero("Historique", "Historique & tendances", "Évolution des métriques, comparaison de deux runs, journal.", stats=[
    ("Runs", str(len(runs))), ("Sources", str(runs["source"].nunique())),
    ("Du", f"{runs['horodatage'].min():%d/%m/%Y}"), ("Au", f"{runs['horodatage'].max():%d/%m/%Y}")])

# =====================================================================================================
# Cartes KPI : dernier run, écart avec l'avant-dernier
# =====================================================================================================
dernier = runs.iloc[0]


def serie(nom: str) -> list[float]:
    """Valeurs d'une métrique, run après run (plus ancien -> plus récent)."""
    s = metriques[metriques["metrique"] == nom].sort_values("horodatage")
    return s["valeur"].astype(float).tolist()


def courbe(nom: str) -> list[float] | None:
    """Données de la mini-courbe d'une carte KPI (None tant qu'il y a moins de deux runs)."""
    v = serie(nom)
    return v if len(v) > 1 else None


def dernier_et_ecart(nom: str) -> tuple[float | None, float | None]:
    """Valeur au dernier run et écart avec l'avant-dernier."""
    v = serie(nom)
    if not v:
        return None, None
    return v[-1], (round(v[-1] - v[-2], 2) if len(v) > 1 else None)


cout, d_cout = dernier_et_ecart("coût total (€)")
eco, d_eco = dernier_et_ecart("économie vs baseline (%)")
cam, d_cam = dernier_et_ecart("camions")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Runs", len(runs), f"dernier le {dernier['horodatage']:%d/%m à %H:%M}", delta_color="off",
          delta_arrow="off", icon=":material/history:", border=True)
k2.metric("Coût total", eur(cout) if cout is not None else "–", ecart_texte(d_cout, "€"), delta_color="inverse",
          icon=":material/euro:", border=True, chart_data=courbe("coût total (€)"), chart_type="area")
k3.metric("Économie", f"{nombre(eco)} %" if eco is not None else "–", ecart_texte(d_eco, "pt"),
          icon=":material/savings:", border=True, chart_data=courbe("économie vs baseline (%)"), chart_type="area")
k4.metric("Camions", nombre(cam) if cam is not None else "–", ecart_texte(d_cam), delta_color="inverse",
          icon=":material/local_shipping:", border=True, chart_data=courbe("camions"), chart_type="area")

# =====================================================================================================
# Évolution des métriques
# =====================================================================================================
section("Évolution des métriques", "une barre par run, du plus ancien au plus récent")
source_run = dict(zip(runs["run_id"], runs["source"]))
with carte("evolution"):
    c_cat, c_met, c_base = st.columns([1, 1.8, 0.6], vertical_alignment="bottom")
    categories = list(dict.fromkeys(metriques["categorie"]))
    categorie = c_cat.selectbox("Catégorie", categories, index=categories.index("Coût") if "Coût" in categories else 0)
    sous = metriques[metriques["categorie"] == categorie]
    noms = list(dict.fromkeys(sous["metrique"]))
    defaut = ["coût total (€)"] if "coût total (€)" in noms else noms[:1]
    choisies = c_met.multiselect("Métriques", noms, default=defaut,
                                 help="Plusieurs métriques : active « Base 100 » pour comparer leurs évolutions.")
    base100 = c_base.toggle("Base 100", value=False,
                            help="Chaque métrique vaut 100 au premier run : on compare des évolutions d'échelles "
                                 "différentes (par exemple un coût et un nombre de camions).")
    if choisies:
        large = (sous[sous["metrique"].isin(choisies)]
                 .pivot_table(index=["horodatage", "run_id"], columns="metrique", values="valeur", aggfunc="last")
                 .sort_index()[choisies])
        if base100:
            large = large / large.iloc[0].replace(0, float("nan")) * 100
        # une étiquette unique par run : fichier, puis date et fin de l'identifiant
        etiquettes = [f"{source_run.get(rid, '?')}<br>{h:%d/%m %H:%M} · {rid[-4:]}" for h, rid in large.index]
        suffixe = " %" if not base100 and all("(%)" in c for c in choisies) else ""
        graphiques.afficher(graphiques.barres_runs(
            etiquettes, {c: large[c].round(2).tolist() for c in large.columns},
            f"{', '.join(choisies)}{' · base 100' if base100 else ''}", suffixe))
    else:
        st.caption("Choisis au moins une métrique.")

# =====================================================================================================
# Comparer deux runs
# =====================================================================================================
section("Comparer deux runs", "écart de B par rapport à A")
if len(runs) < 2:
    st.caption("Il faut au moins deux runs pour comparer.")
else:
    ids = runs["run_id"].tolist()
    libelles = {rid: f"{src} · {h:%d/%m %H:%M} · {rid[-4:]}"
                for rid, h, src in zip(runs["run_id"], runs["horodatage"], runs["source"])}
    c_a, c_b = st.columns(2)
    run_a = c_a.selectbox("Run A (référence)", ids, index=1, format_func=libelles.get,
                          help="Par défaut : l'avant-dernier run.")
    run_b = c_b.selectbox("Run B (comparé)", ids, index=0, format_func=libelles.get,
                          help="Par défaut : le dernier run.")
    categories = dict(zip(metriques["metrique"], metriques["categorie"]))
    comparaison.afficher_comparaison(
        comparaison.comparer(historique.metriques_run(run_a), historique.metriques_run(run_b), categories),
        f"A : {libelles[run_a]}", f"B : {libelles[run_b]}", cle="historique",
        periode_a=historique.periode_run(run_a), periode_b=historique.periode_run(run_b),
        sortie1_a=historique.charger_fichier_run(run_a, "sortie1_profils.csv"),
        sortie1_b=historique.charger_fichier_run(run_b, "sortie1_profils.csv"))

# =====================================================================================================
# Journal des runs
# =====================================================================================================
section("Journal des runs", "du plus récent au plus ancien")
st.dataframe(
    runs, hide_index=True, width="stretch",
    column_config={
        "run_id": st.column_config.TextColumn("Run"),
        "horodatage": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY HH:mm"),
        "source": "Source",
        "debut": st.column_config.DateColumn("Du", format="DD/MM/YYYY"),
        "fin": st.column_config.DateColumn("Au", format="DD/MM/YYYY"),
        "semaines": st.column_config.NumberColumn("Semaines", format="%d"),
        "lignes": st.column_config.ProgressColumn("Lignes", min_value=0, max_value=int(runs["lignes"].max()), format="%d"),
        "camions": st.column_config.NumberColumn("Camions", format="%d"),
        "cout_total": st.column_config.NumberColumn("Coût total", format="%.0f €"),
        "economie_pct": st.column_config.NumberColumn("Économie", format="%.1f %%"),
        "duree_s": st.column_config.NumberColumn("Durée", format="%.1f s"),
        "statut": "Statut",
    })

with st.expander("Rouvrir les fichiers d'un run", icon=":material/folder_open:"):
    c_run, c_fic = st.columns(2)
    rid = c_run.selectbox("Run", runs["run_id"], format_func=lambda x: f"{x} · {runs.set_index('run_id').loc[x, 'source']}")
    nom = c_fic.selectbox("Fichier", list(historique.FICHIERS_RUN), format_func=historique.FICHIERS_RUN.get)
    table = historique.charger_fichier_run(rid, nom)
    if table is None:
        st.caption("Fichier introuvable pour ce run.")
    else:
        st.dataframe(table.head(500), hide_index=True)
        st.download_button(f"Télécharger {nom}", table.to_csv(index=False), f"{rid}_{nom}", "text/csv",
                           icon=":material/download:")

with st.expander("Supprimer un run", icon=":material/delete:"):
    a_supprimer = st.selectbox("Run à supprimer", runs["run_id"], key="suppression")
    confirme = st.checkbox(f"Je confirme la suppression du run {a_supprimer} (fichiers compris)")
    if st.button("Supprimer", icon=":material/delete:", disabled=not confirme):
        historique.supprimer_run(a_supprimer)
        st.toast(f"Run {a_supprimer} supprimé", icon=":material/delete:")
        st.rerun()
