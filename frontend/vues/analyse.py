"""Partie 1 : un schedule en entrée, le moteur tourne, on voit les résultats et l'écart avec le dernier run."""
import hashlib
import time

import pandas as pd
import streamlit as st

from backend.config import DATA, POIDS_MAX
from backend.formatage import eur, nombre, pourcent
from backend.sorties import camion_le_plus_charge, construire_sortie3, detail_camion
from frontend import comparaison, export, graphiques, historique, moteur
from frontend.composants import carte, ecart_texte, hero, pastille, section, tuile

SCHEDULE_PROJET = DATA / "bronze" / "released_schedule.csv"
SEPARATEURS = {",": ",", ";": ";", "tab": "\t", "|": "|"}

# =====================================================================================================
# Entrée : le schedule
# =====================================================================================================
# Les widgets d'une page sont effacés quand on change de page : le choix de l'origine et le séparateur ont une clé
# conservée par app.py, et le fichier importé est gardé dans la session (« memoire_fichier »), pour retrouver
# l'analyse au retour sur la page.
memoire = st.session_state
with st.sidebar:
    st.markdown("#### Schedule")
    origine = st.segmented_control("Origine", ["Importer un CSV", "Projet"], required=True, key="origine", label_visibility="collapsed", width="stretch",
                                   help="« Projet » : le schedule du projet (data/bronze), utile comme jeu de test.")
    if origine == "Importer un CSV":
        fichier = st.file_uploader("CSV schedule", type=["csv"], label_visibility="collapsed")
        separateur = st.segmented_control("Séparateur", list(SEPARATEURS), required=True, key="separateur")
        if fichier is not None:
            memoire["memoire_fichier"] = (fichier.name, fichier.getvalue())
        elif "memoire_fichier" in memoire:
            st.caption(f"Fichier en mémoire : **{memoire['memoire_fichier'][0]}**")
            if st.button("Oublier ce fichier", icon=":material/close:", type="tertiary"):
                del memoire["memoire_fichier"]
                st.rerun()
        source, contenu = memoire.get("memoire_fichier", (None, None))
    else:
        separateur = ","
        source, contenu = SCHEDULE_PROJET.name, SCHEDULE_PROJET.read_bytes()
        st.caption(f"Jeu de test : `data/bronze/{SCHEDULE_PROJET.name}`")
    st.markdown("#### Moteur")
    lancer = st.button("Lancer l'analyse", type="primary", icon=":material/play_arrow:", width="stretch",
                       disabled=contenu is None, key="lancer_lateral")
    st.caption("Nettoyage, baseline, jours fixes, lissage, report, contrôles des contraintes.")
lancer = lancer or bool(st.session_state.get("lancer_principal"))      # bouton de la page (aperçu)

if contenu is None:
    hero("Analyse", "Consolidation des livraisons", "Importe un schedule CSV dans le panneau de gauche pour commencer.")
    st.html('<div class="appel">⬅ <span><b>Glisse un fichier CSV</b> au format de '
            "<code>released_schedule.csv</code> dans le panneau de gauche, ou choisis « Projet » pour essayer "
            "avec le schedule du projet.</span></div>")
    st.stop()

empreinte = hashlib.sha1(contenu + str(separateur).encode()).hexdigest()
try:
    schedule = moteur.lire_schedule(contenu, SEPARATEURS[str(separateur)])
except Exception as erreur:  # noqa: BLE001 (fichier quelconque illisible : on l'explique au lieu de planter)
    hero("Analyse", "Fichier illisible", f"{source} : {erreur}")
    st.stop()
manquantes = moteur.colonnes_manquantes(schedule)
if manquantes:
    hero("Analyse", "Schedule incomplet", f"{source} : il manque les colonnes {', '.join(manquantes)}.")
    st.caption(f"Colonnes attendues : {', '.join(moteur.COLONNES_SCHEDULE)}. Vérifie aussi le séparateur.")
    st.dataframe(schedule.head(20), hide_index=True)
    st.stop()

profil = moteur.profil_schedule(schedule)
debut_h, fin_h = schedule["date"].min(), schedule["date"].max()
hero("Analyse", "Consolidation des livraisons", f"Schedule : {source}", stats=[
    ("Lignes", nombre(profil["lignes"])), ("Couples", nombre(profil["couples fournisseur × usine"])),
    ("Usines", nombre(profil["usines"])), ("Période", f"{debut_h:%d/%m} → {fin_h:%d/%m/%Y}")])

# ---------- Lancement du moteur ----------
if lancer:
    with st.status("Le moteur tourne…", expanded=False) as statut:
        debut = time.perf_counter()
        statut.update(label="Nettoyage, baseline, jours fixes, lissage, report, validation…")
        try:
            resultats = moteur.executer_moteur(contenu, SEPARATEURS[str(separateur)])
        except (ValueError, AssertionError) as erreur:
            statut.update(label="Le moteur n'a pas pu traiter ce schedule", state="error")
            st.error(f"{erreur}", icon=":material/error:")
            st.stop()
        duree = time.perf_counter() - debut
        statut.update(label=f"Analyse terminée en {duree:.1f} s", state="complete")
    st.session_state["analyse"] = {
        "empreinte": empreinte, "source": source, "resultats": resultats, "duree": duree, "run_id": None,
        "metriques": moteur.toutes_metriques(schedule, resultats),
    }

analyse = st.session_state.get("analyse")
if analyse is not None and analyse["empreinte"] != empreinte:
    st.info("Le schedule a changé depuis la dernière analyse : relance l'analyse pour mettre les résultats à jour.",
            icon=":material/refresh:")
    analyse = None

# =====================================================================================================
# Avant le lancement : aperçu du schedule
# =====================================================================================================
def apercu_schedule(cle: str) -> None:
    """Indicateurs et graphiques du schedule d'entrée (affichés avant l'analyse, puis dans un onglet).

    Args:
        cle: suffixe des cartes (les mêmes graphiques peuvent apparaître à deux endroits de la page).
    """
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Lignes", nombre(profil["lignes"]), icon=":material/table_rows:", border=True)
    c2.metric("Couples", nombre(profil["couples fournisseur × usine"]), icon=":material/hub:", border=True,
              help="Couples fournisseur × usine")
    c3.metric("Fournisseurs", nombre(profil["fournisseurs"]), icon=":material/storefront:", border=True)
    c4.metric("Materials", nombre(profil["materials"]), icon=":material/inventory_2:", border=True)
    c5.metric("Poids total", f"{nombre(profil['poids total (t)'])} t", icon=":material/scale:", border=True)
    st.html(" ".join([
        pastille(f"{pourcent(profil['lignes à quantité nulle (%)'] / 100)} de lignes à quantité nulle",
                 "ko" if profil["lignes à quantité nulle (%)"] else "ok"),
        pastille(f"{nombre(profil['lignes sans poids'])} lignes sans poids", "ko" if profil["lignes sans poids"] else "ok"),
        pastille(f"{nombre(profil['lignes de plus de 24,5 t'])} lignes de plus de 24,5 t",
                 "ko" if profil["lignes de plus de 24,5 t"] else "ok"),
    ]))

    g1, g2 = st.columns([2, 1], gap="medium")
    with carte(f"besoins-jour-{cle}", g1):
        graphiques.afficher(graphiques.besoins_par_jour(schedule), cle=f"besoins-jour-{cle}")
    with carte(f"poids-usine-{cle}", g2):
        graphiques.afficher(graphiques.poids_par_usine(schedule), cle=f"poids-usine-{cle}")
    g3, g4 = st.columns([1, 2], gap="medium")
    with carte(f"top-fournisseurs-{cle}", g3):
        graphiques.afficher(graphiques.top_fournisseurs(schedule), cle=f"top-fournisseurs-{cle}")
    with g4:
        st.markdown("**Aperçu du fichier** (300 premières lignes)")
        st.dataframe(schedule.head(300), hide_index=True, height=330, key=f"apercu-{cle}",
                     column_config={"date": st.column_config.DateColumn("date", format="DD/MM/YYYY")})


if analyse is None:
    with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
        st.html('<div class="appel">✦ <span><b>Schedule prêt.</b> Le moteur va le nettoyer, construire sa baseline '
                "puis consolider les livraisons (5 à 15 s).</span></div>")
        st.button("Lancer l'analyse", type="primary", icon=":material/play_arrow:", key="lancer_principal")
    section("Schedule d'entrée", "avant analyse · lignes à quantité > 0")
    apercu_schedule("avant")
    st.stop()

# =====================================================================================================
# Résultats
# =====================================================================================================
r = analyse["resultats"]
m = moteur.aplatir(analyse["metriques"])

runs = historique.charger_runs()
precedents = runs[runs["run_id"] != analyse["run_id"]]
dernier = historique.metriques_run(precedents["run_id"].iloc[0]) if len(precedents) else {}
toutes = historique.charger_metriques()


def serie(nom: str) -> list[float] | None:
    """Valeurs historisées d'une métrique (plus ancien -> plus récent) suivies de celle de ce run ;
    None s'il n'y a pas encore d'historique (une courbe d'un seul point n'apprend rien)."""
    h = toutes[(toutes["metrique"] == nom) & (toutes["run_id"] != analyse["run_id"])].sort_values("horodatage")
    valeurs = [*h["valeur"].astype(float).tolist(), m[nom]]
    return valeurs if len(valeurs) > 1 else None


def kpi(colonne: st.delta_generator.DeltaGenerator, libelle: str, valeur: str, nom: str, icone: str,
        unite: str, hausse_favorable: bool = True) -> None:
    """Carte KPI : valeur de ce run, écart avec le dernier run enregistré (``unite`` : ``€``, ``pt`` ou vide)
    et courbe de l'historique."""
    delta = ecart_texte(m[nom] - dernier[nom] if nom in dernier else None, unite)
    colonne.metric(libelle, valeur, delta, delta_color="normal" if hausse_favorable else "inverse",
                   icon=icone, border=True, chart_data=serie(nom), chart_type="area",
                   delta_description="vs dernier run" if delta is not None else None)


calcul = "résultat en cache" if analyse["duree"] < 0.5 else f"calcul en {analyse['duree']:.1f} s"
with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
    if analyse["run_id"] is None:
        if st.button("Enregistrer dans l'historique", icon=":material/save:", type="primary"):
            analyse["run_id"] = historique.enregistrer_run(analyse["source"], schedule, r, analyse["metriques"],
                                                           analyse["duree"])
            st.toast(f"Run {analyse['run_id']} enregistré", icon=":material/check_circle:")
            st.rerun()
        etat = pastille("run pas encore historisé", "info")
    else:
        etat = pastille(f"run {analyse['run_id']} enregistré", "ok")
    st.html(etat + pastille(f"variante retenue : {r.principale}", "info") + pastille(calcul, "info"))

section("Résultats du moteur", f"économie mesurée par rapport à la baseline ({eur(m['coût baseline (€)'])}, "
                               f"{nombre(m['camions baseline'])} camions)")
k1, k2, k3, k4, k5 = st.columns(5)
kpi(k1, "Coût total", eur(m["coût total (€)"]), "coût total (€)", ":material/euro:", "€", hausse_favorable=False)
kpi(k2, "Économie", f"{nombre(m['économie vs baseline (%)'])} %", "économie vs baseline (%)", ":material/savings:", "pt")
kpi(k3, "Camions", nombre(m["camions"]), "camions", ":material/local_shipping:", "", hausse_favorable=False)
kpi(k4, "Remplissage moyen", f"{nombre(m['remplissage poids moyen (%)'])} %", "remplissage poids moyen (%)",
    ":material/scale:", "pt")
kpi(k5, "Avance moyenne", f"{nombre(m['avance moyenne (j)'])} j", "avance moyenne (j)", ":material/schedule:", "",
    hausse_favorable=False)

# ---------- Export des livrables ----------
nom_base = f"consolidation_{source.rsplit('.', 1)[0]}" if source else "consolidation"
with carte("export"):
    c_titre, c_choix, c_format, c_bouton = st.columns([1.1, 2.2, 1.6, 1], vertical_alignment="bottom", gap="medium")
    c_titre.markdown("**Exporter l'analyse**  \n:gray[les 3 sorties du projet, en Excel ou en CSV]")
    choix = c_choix.pills("Livrables", list(export.LIVRABLES), selection_mode="multi", key="export_livrables",
                          default=list(export.LIVRABLES), format_func=lambda c: export.LIVRABLES[c].libelle,
                          help="Synthèse : bilan des économies et économies par usine.")
    formats = ["Excel (.xlsx)", "CSV (.zip)"] if export.EXCEL_DISPONIBLE else ["CSV (.zip)"]
    format_export = c_format.segmented_control(
        "Format", formats, required=True, default=formats[0], key="export_format", width="stretch",
        help=None if export.EXCEL_DISPONIBLE else "Export Excel indisponible : le module openpyxl n'est pas installé.")
    if format_export == "CSV (.zip)":
        excel_fr = c_format.toggle("CSV pour Excel français", value=True, key="export_excel_fr",
                                   help="Séparateur « ; » et virgule décimale, lisibles directement par un Excel "
                                        "français. Désactivé : séparateur « , » et point décimal (format de data/gold).")
        donnees_export = lambda: export.archive_csv(r, choix, excel_fr)  # généré au clic
        fichier_export, type_export = f"{nom_base}.zip", "application/zip"
    else:
        donnees_export = lambda: export.classeur_excel(r, choix, source or "")
        fichier_export = f"{nom_base}.xlsx"
        type_export = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    c_bouton.download_button("Télécharger", donnees_export, fichier_export, type_export, type="primary",
                             icon=":material/download:", disabled=not choix, width="stretch", on_click="ignore")

# ---------- Onglets ----------
vue, entree, profils, camions, savings, contraintes, qualite, comparer = st.tabs(
    [":material/dashboard: Vue d'ensemble", ":material/input: Schedule d'entrée",
     ":material/event_repeat: Profils (sortie 1)", ":material/local_shipping: Camions (sortie 2)",
     ":material/savings: Savings (sortie 3)",
     ":material/rule: Contraintes", ":material/fact_check: Qualité des données",
     ":material/compare_arrows: Comparaison"],
    key="onglet_analyse", on_change="rerun")     # onglet suivi : un filtre modifié ne ramène pas au premier onglet

with entree:
    apercu_schedule("apres")

with vue:
    g1, g2, g3 = st.columns(3, gap="medium")
    with carte("cout-etapes", g1):
        graphiques.afficher(graphiques.cout_par_etape(r.bilan))
    with carte("cout-usine", g2):
        graphiques.afficher(graphiques.economies_par_usine(r.par_usine))
    with carte("jours-semaine", g3):
        graphiques.afficher(graphiques.camions_par_jour_semaine(r.camions_base, r.planning_complet))
    with carte("charge"):
        graphiques.afficher(graphiques.camions_par_jour(r.planning_complet))
    g4, g5, g6 = st.columns(3, gap="medium")
    with carte("avance", g4):
        graphiques.afficher(graphiques.avance_livraisons(r.lignes_complet))
    with carte("remplissage", g5):
        graphiques.afficher(graphiques.remplissage_camions(r.planning_complet))
    with carte("couples-jour", g6):
        graphiques.afficher(graphiques.couples_par_jour(r.sortie1))
    with st.expander("Tableau des économies", icon=":material/table_chart:"):
        st.dataframe(r.bilan, hide_index=True, column_config={
            "Coût": st.column_config.NumberColumn(format="%.0f €"),
            "Économie vs baseline": st.column_config.NumberColumn(format="%.0f €"),
            "Économie (%)": st.column_config.NumberColumn(format="percent"),
            "Avance moyenne (j)": st.column_config.NumberColumn(format="%.2f")})

with profils:
    usines = st.multiselect("Usines", sorted(r.sortie1["Usine"].unique()), placeholder="Toutes les usines")
    s1 = r.sortie1[r.sortie1["Usine"].isin(usines)] if usines else r.sortie1
    st.dataframe(s1, hide_index=True, height=520, column_config={
        "Distance": st.column_config.NumberColumn(format="%d km"),
        "Livraisons / sem. actuelles": st.column_config.NumberColumn(format="%.2f"),
        "Fréquence cible": st.column_config.NumberColumn("Jours fixes", format="%d / sem."),
        "Camions / sem.": st.column_config.NumberColumn(format="%.2f"),
        "Remplissage poids": st.column_config.ProgressColumn(format="percent",
                                                             min_value=0, max_value=1)})
    st.download_button("Télécharger la sortie 1", r.sortie1.to_csv(index=False), "sortie1_profils.csv",
                       "text/csv", icon=":material/download:")

with camions:
    ids = sorted(r.sortie2["camion_id"].unique())
    c_choix, c_resume = st.columns([1, 3], vertical_alignment="bottom")
    choisi = c_choix.selectbox("Camion", ids, index=ids.index(camion_le_plus_charge(r.planning_complet)),
                               help="Par défaut : le camion qui regroupe le plus de lignes de besoin.")
    resume, _ = detail_camion(r.sortie2, int(choisi))
    c_resume.html(pastille(resume, "info"))
    contenu_camion = r.sortie2[r.sortie2["camion_id"] == choisi]
    st.dataframe(contenu_camion.drop(columns=["camion_id", "usine", "fournisseur", "date_livraison", "jour", "reserve"]),
                 hide_index=True, height=min(38 * len(contenu_camion) + 40, 420), column_config={
                     "Quantité": st.column_config.NumberColumn(format="localized"),
                     "Poids (kg)": st.column_config.ProgressColumn(format="%.1f", min_value=0,
                                                                   max_value=float(contenu_camion["Poids (kg)"].max() or 1))})
    camions_planning = r.planning_complet.assign(remplissage=r.planning_complet["poids"] / POIDS_MAX)
    with st.expander(f"Tous les camions ({len(camions_planning)})", icon=":material/list:"):
        st.dataframe(camions_planning[["camion_id", "plant", "supplier_id", "date", "jour", "jours_fixes", "nb_lignes",
                                       "poids", "volume", "remplissage", "cout", "reserve"]],
                     hide_index=True, column_config={
                         "date": st.column_config.DateColumn(format="DD/MM/YYYY"),
                         "remplissage": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
                         "cout": st.column_config.NumberColumn("coût", format="%.2f €")})
    st.download_button("Télécharger la sortie 2", export.sortie2(r).to_csv(index=False, date_format="%Y-%m-%d"),
                       "sortie2_camions.csv", "text/csv", icon=":material/download:")

with savings:
    semaines = sorted(pd.concat([r.camions_base["date"], r.planning_complet["date"]]).dt.to_period("W-SUN")
                      .dt.start_time.unique())
    sortie3 = construire_sortie3(r.camions_base, r.planning_complet)
    c_sem, c_nb, c_usines = st.columns([1, 1, 2], vertical_alignment="bottom")
    semaine = c_sem.selectbox("Semaine", [None, *semaines], key="semaine_sortie3",
                              format_func=lambda d: "Moyenne par semaine" if d is None else f"Semaine du {d:%d/%m/%Y}",
                              help="Une semaine du planning (camions livrés cette semaine-là), ou la moyenne de "
                                   "toutes les semaines.")
    usines_s3 = c_usines.multiselect("Usines", sorted(sortie3["usine"].unique()), placeholder="Toutes les usines",
                                     key="usines_sortie3")
    s3 = sortie3 if semaine is None else construire_sortie3(r.camions_base, r.planning_complet, pd.Timestamp(semaine))
    if semaine is not None:                       # une seule semaine : le coût de la semaine est le coût total
        s3 = s3.assign(cout_actuel_semaine=s3["cout_actuel"], cout_apres_semaine=s3["cout_apres"])
    s3 = s3[s3["usine"].isin(usines_s3)] if usines_s3 else s3
    nb_couples = c_nb.slider("Couples affichés", 1, max(min(40, len(s3)), 2), min(5, len(s3)), key="nb_sortie3")
    if s3.empty:
        st.caption("Aucun camion sur cette sélection.")
    else:
        quand = "par semaine en moyenne" if semaine is None else f"sur la semaine du {semaine:%d/%m}"
        top = s3.head(nb_couples)
        avant, apres = top["cout_actuel_semaine"].sum(), top["cout_apres_semaine"].sum()
        meilleur = top.iloc[0]
        diviseur = len(semaines) if semaine is None else 1     # en moyenne : camions ramenés à une semaine
        n_avant, n_apres = meilleur["camions_actuels"] / diviseur, meilleur["camions_apres"] / diviseur
        c_graphe, c_tuiles = st.columns([2.3, 1], gap="medium")
        with carte("savings", c_graphe):
            titre = "Coût de transport par semaine (moyenne)" if semaine is None else                 f"Coût de transport, semaine du {semaine:%d/%m}"
            graphiques.afficher(graphiques.savings_par_couple(s3, nb_couples, True, titre))
        with c_tuiles:
            st.html(tuile(f"{pourcent(-(avant - apres) / avant) if avant else '–'}",
                          f"coût des {len(top)} couples : {eur(avant)} → {eur(apres)} {quand}", accent=True)
                    + tuile(eur(avant - apres), f"économisés {quand} pour {len(top)} couples")
                    + tuile(eur(meilleur["cout_actuel_semaine"] - meilleur["cout_apres_semaine"]),
                            f"{meilleur['fournisseur']} × {meilleur['usine']} : {nombre(round(n_avant, 1))} envoi(s) "
                            f"({eur(meilleur['cout_actuel_semaine'])}) → {nombre(round(n_apres, 1))} envoi(s) "
                            f"({eur(meilleur['cout_apres_semaine'])})"))
            total_avant, total_apres = s3["cout_actuel_semaine"].sum(), s3["cout_apres_semaine"].sum()
            st.html(pastille(f"tous les couples : {eur(total_avant)} → {eur(total_apres)}", "info")
                    + pastille(f"{int((s3['economie'] > 0).sum())} / {len(s3)} couples économisent", "ok"))
        with st.expander(f"Tableau de la sortie 3 ({len(s3)} couples)", icon=":material/table_chart:"):
            st.dataframe(s3, hide_index=True, height=420, column_config={
                col: (st.column_config.NumberColumn(titre_col, format="percent") if fmt == export.PCT
                      else st.column_config.NumberColumn(titre_col, format="%.2f €") if fmt == export.EUR
                      else st.column_config.NumberColumn(titre_col, format="%d") if fmt == export.ENTIER else titre_col)
                for col, (titre_col, fmt) in export.LIVRABLES["sortie3"].colonnes.items()})

with contraintes:
    dures = r.controle_contraintes[r.controle_contraintes["Type"] == "dure"]
    ok_dures = int((dures["Violations"] == 0).sum())
    st.html(" ".join([pastille(f"{ok_dures} / {len(dures)} contraintes dures respectées",
                               "ok" if ok_dures == len(dures) else "ko"),
                      pastille(f"lissage : {nombre(m['semaines hors tolérance'])} semaine(s) hors tolérance", "info")]))
    c_contraintes, c_validation = st.columns([1.6, 1], gap="medium")
    c_contraintes.dataframe(r.controle_contraintes.reset_index(), hide_index=True, column_config={
        "Remarque": st.column_config.TextColumn(width="large")})
    c_validation.dataframe(r.validation.reset_index(), hide_index=True)
    section(f"Alertes à notifier ({len(r.alertes)})", "cas où une règle ne peut pas être respectée")
    if r.alertes.empty:
        st.caption("Aucune alerte.")
    else:
        st.html("".join(pastille(f"{regle} : {n} cas", "info")
                        for regle, n in r.alertes["regle"].value_counts().sort_index().items()))
        st.dataframe(r.alertes, hide_index=True, column_config={
            "regle": "Règle", "usine": "Usine", "fournisseur": "Fournisseur",
            "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
            "camions": st.column_config.NumberColumn("Camions", format="%d"),
            "cause": st.column_config.TextColumn("Cause", width="large"),
            "a_faire": st.column_config.TextColumn("À faire", width="large")})

with qualite:
    q1, q2 = st.columns([1, 1], gap="medium")
    with q1:
        st.markdown("**Du schedule brut aux lignes consolidées**")
        st.dataframe(moteur.etapes_nettoyage(schedule, r), hide_index=True, column_config={
            "étape": st.column_config.TextColumn("Étape"),
            "lignes": st.column_config.NumberColumn("Lignes", format="%d"),
            "détail": st.column_config.TextColumn("Détail", width="large")})
    with carte("flags", q2):
        par_flag = (r.quarantaine["flags"].str.split("|").explode().value_counts()
                    if len(r.quarantaine) else pd.Series(dtype=int))
        if par_flag.empty:
            st.caption("Aucune ligne en quarantaine.")
        else:
            graphiques.afficher(graphiques.lignes_par_flag(par_flag))
    with st.expander(f"Lignes en quarantaine ({len(r.quarantaine)})", icon=":material/warning:"):
        st.dataframe(r.quarantaine, hide_index=True,
                     column_config={"need_date": st.column_config.DateColumn("besoin", format="DD/MM/YYYY")})

with comparer:
    if precedents.empty:
        st.caption("Aucun autre run dans l'historique : enregistre ce run, puis relance une analyse pour comparer.")
    else:
        libelles = {rid: f"{src} · {h:%d/%m %H:%M} · {rid[-4:]}" for rid, h, src in
                    zip(precedents["run_id"], precedents["horodatage"], precedents["source"])}
        reference = st.selectbox("Comparer ce run à", list(libelles), format_func=libelles.get,
                                 help="Par défaut : le dernier run enregistré dans l'historique.")
        categories = {nom: cat for cat, groupe in analyse["metriques"].items() for nom in groupe}
        table = comparaison.comparer(historique.metriques_run(reference), m, categories)
        comparaison.afficher_comparaison(
            table, f"A : {libelles[reference]}", f"B : ce run ({analyse['source']})", cle="analyse",
            periode_a=historique.periode_run(reference), periode_b=moteur.periode(r),
            sortie1_a=historique.charger_fichier_run(reference, "sortie1_profils.csv"), sortie1_b=r.sortie1)
