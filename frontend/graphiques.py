"""Graphiques Plotly du dashboard, tous construits sur la même mise en page (fond transparent, grille discrète).

Chaque fonction retourne une figure ; l'affichage passe par ``afficher``.

Code couleur : gris = baseline, bleu = planning final, bleu / rouge = hausse / baisse ; chaque usine garde sa
couleur d'un graphique à l'autre (``couleur_usine``) ; les autres graphiques ont chacun leur teinte.
"""
from collections.abc import Sequence
from typing import Any, Final

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backend.config import JOURS, POIDS_MAX

from .style import (AQUA, BLEU, BLEU_CLAIR, GRILLE, GRIS, JAUNE, ORANGE, RAMPE_BLEUE, ROUGE, TEXTE,
                    TEXTE_SECONDAIRE, VERT, VIOLET)

SERIES: Final[list[str]] = [BLEU, ORANGE, AQUA, JAUNE, "#E87BA4", "#008300", VIOLET, "#E34948"]
"""Couleurs des séries, toujours dans cet ordre (une série garde sa couleur quand on filtre)."""
_CONFIG: Final[dict[str, Any]] = {"displayModeBar": False, "scrollZoom": False}


def couleur_usine(usine: str) -> str:
    """Couleur d'une usine, la même dans tous les graphiques (``PLT_001`` -> 1re couleur...).

    Args:
        usine: code de l'usine, par exemple ``"PLT_002"``.

    Returns:
        La couleur de l'usine (une usine au code non numérique prend la dernière couleur).
    """
    chiffres = "".join(c for c in usine if c.isdigit())
    return SERIES[(int(chiffres) - 1) % len(SERIES)] if chiffres else SERIES[-1]


def _clair(couleur: str, opacite: float = 0.22) -> str:
    """Version transparente d'une couleur hexadécimale (fond d'aire, contour)."""
    r, v, b = (int(couleur[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{v},{b},{opacite})"


def _mise_en_page(fig: go.Figure, titre: str, hauteur: int = 340) -> go.Figure:
    """Applique la mise en page commune.

    Args:
        fig: la figure.
        titre: titre affiché en haut à gauche.
        hauteur: hauteur en pixels.

    Returns:
        La même figure.
    """
    fig.update_layout(
        title={"text": titre, "x": 0, "xanchor": "left", "font": {"size": 15, "color": TEXTE}},
        height=hauteur, margin={"l": 8, "r": 8, "t": 48, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, Segoe UI, sans-serif", "color": TEXTE_SECONDAIRE, "size": 12},
        hoverlabel={"bgcolor": "white", "bordercolor": GRILLE, "font": {"color": TEXTE}},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "xanchor": "right", "x": 1, "title": None},
        barcornerradius=4, bargap=0.3,
        separators=", ",                          # format français : virgule décimale, espace des milliers
    )
    fig.update_xaxes(gridcolor=GRILLE, zeroline=False, linecolor=GRILLE, ticks="", automargin=True)
    fig.update_yaxes(gridcolor=GRILLE, zeroline=False, linecolor=GRILLE, ticks="", automargin=True)
    return fig


def afficher(fig: go.Figure, cle: str | None = None) -> None:
    """Affiche une figure dans la page, sans barre d'outils.

    Args:
        fig: la figure.
        cle: clé Streamlit (nécessaire si la même figure apparaît deux fois).
    """
    st.plotly_chart(fig, config=_CONFIG, theme=None, key=cle)


def euros(x: float) -> str:
    """Montant en euros, format court (``123 k€``) pour les étiquettes."""
    return f"{x / 1000:,.0f} k€".replace(",", " ")


def pourcent_signe(x: float) -> str:
    """Pourcentage signé au format français, par exemple ``-38,2 %`` (``x`` est déjà en %)."""
    return f"{x:+.1f} %".replace(".", ",").replace("-", "−")


def cout_par_etape(bilan: pd.DataFrame) -> go.Figure:
    """Coût de chaque version du planning, de la baseline au planning final.

    Args:
        bilan: tableau des économies (une ligne par version).

    Returns:
        Barres horizontales : baseline en gris, planning final en bleu, étapes intermédiaires en bleu clair.
    """
    b = bilan.iloc[::-1]
    couleurs = [GRIS if v == "Baseline" else BLEU if i == 0 else BLEU_CLAIR for i, v in enumerate(b["Version"])]
    fig = go.Figure(go.Bar(
        x=b["Coût"], y=b["Version"], orientation="h", marker_color=couleurs,
        text=[f"{euros(c)}  ({pourcent_signe(-e * 100)})" if v != "Baseline" else euros(c)
              for c, e, v in zip(b["Coût"], b["Économie (%)"], b["Version"])],
        textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br>%{x:,.0f} €<extra></extra>"))
    fig.update_xaxes(showticklabels=False, showgrid=False, range=[0, b["Coût"].max() * 1.3])
    return _mise_en_page(fig, "Coût de chaque étape du moteur", 330)


def economies_par_usine(par_usine: pd.DataFrame) -> go.Figure:
    """Coût baseline et coût final de chaque usine.

    Args:
        par_usine: économies par usine (avec une ligne ``Total``, ignorée ici).

    Returns:
        Barres groupées : baseline en gris, planning final en bleu.
    """
    u = par_usine.drop(index="Total")
    fig = go.Figure([
        go.Bar(name="Baseline", x=u.index, y=u["cout_baseline"], marker_color=GRIS,
               hovertemplate="%{x}<br>baseline : %{y:,.0f} €<extra></extra>"),
        go.Bar(name="Planning final", x=u.index, y=u["cout_final"], marker_color=BLEU,
               text=[pourcent_signe(-p * 100) for p in u["economie_pct"]], textposition="outside", cliponaxis=False,
               hovertemplate="%{x}<br>final : %{y:,.0f} €<extra></extra>"),
    ])
    fig.update_layout(barmode="group", bargroupgap=0.08)
    fig.update_yaxes(ticksuffix=" €", separatethousands=True)
    return _mise_en_page(fig, "Coût par usine")


def camions_par_jour(planning: pd.DataFrame) -> go.Figure:
    """Nombre de camions reçus par chaque usine, jour par jour.

    Args:
        planning: planning complet, une ligne par camion.

    Returns:
        Carte de chaleur usine × jour, en rampe de bleus (plus foncé = plus de camions).
    """
    t = planning.groupby(["plant", "date"]).size().unstack(fill_value=0).sort_index()
    t = t.reindex(columns=pd.bdate_range(t.columns.min(), t.columns.max()), fill_value=0)
    fig = go.Figure(go.Heatmap(
        z=t.values, x=[f"{JOURS[d.day_of_week][:3].lower()} {d:%d/%m}" for d in t.columns], y=t.index,
        colorscale=[[i / (len(RAMPE_BLEUE) - 1), c] for i, c in enumerate(RAMPE_BLEUE)],
        xgap=2, ygap=2, colorbar={"title": {"text": "camions"}, "thickness": 10, "outlinewidth": 0},
        hovertemplate="%{y} · %{x}<br>%{z} camions<extra></extra>"))
    fig.update_xaxes(showgrid=False, tickangle=-45, nticks=15)
    fig.update_yaxes(showgrid=False)
    return _mise_en_page(fig, "Camions reçus par usine et par jour", 320)


def avance_livraisons(lignes: pd.DataFrame) -> go.Figure:
    """Répartition des lignes selon leur avance de livraison sur le besoin (0 à 7 jours).

    Args:
        lignes: lignes livrées, avec ``avance_jours``.

    Returns:
        Barres : part des lignes livrées le jour même, 1 jour avant... 7 jours avant.
    """
    n = lignes["avance_jours"].value_counts().sort_index().reindex(range(8), fill_value=0)
    part = n / n.sum()
    fig = go.Figure(go.Bar(
        x=["jour même"] + [f"J-{j}" for j in range(1, 8)], y=part, marker_color=AQUA,
        text=[f"{p:.0%}" for p in part], textposition="outside", cliponaxis=False, customdata=n,
        hovertemplate="%{x}<br>%{y:.1%} des lignes (%{customdata})<extra></extra>"))
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    return _mise_en_page(fig, "Avance des livraisons sur le besoin")


def remplissage_camions(planning: pd.DataFrame) -> go.Figure:
    """Distribution du remplissage en poids des camions optimisés.

    Args:
        planning: planning complet (les camions réservés, au poids inconnu, sont ignorés).

    Returns:
        Histogramme par tranche de 10 %, avec la moyenne en trait pointillé.
    """
    taux = planning.loc[~planning["reserve"], "poids"] / POIDS_MAX
    fig = go.Figure(go.Histogram(
        x=taux, xbins={"start": 0, "end": 1.0001, "size": 0.1}, marker_color=VIOLET,
        hovertemplate="remplissage %{x}<br>%{y} camions<extra></extra>"))
    fig.add_vline(x=taux.mean(), line_dash="dot", line_color=TEXTE,
                  annotation_text=f"moyenne {taux.mean():.0%}", annotation_position="top right",
                  annotation_font_color=TEXTE)
    fig.update_xaxes(tickformat=".0%", range=[0, 1])
    fig.update_yaxes(title_text="camions")
    return _mise_en_page(fig, "Remplissage des camions (poids)")


def couples_par_jour(sortie1: pd.DataFrame) -> go.Figure:
    """Nombre de couples livrés chaque jour de la semaine (un couple à 2 jours compte pour chacun).

    Args:
        sortie1: la sortie 1 (colonne ``jours``, par exemple ``"Lundi + Jeudi"``).

    Returns:
        Barres du lundi au vendredi.
    """
    jours = sortie1["jours"].str.split(" + ", regex=False).explode().value_counts().reindex(JOURS, fill_value=0)
    fig = go.Figure(go.Bar(x=jours.index, y=jours.values, marker_color=ORANGE, text=jours.values,
                           textposition="outside", cliponaxis=False,
                           hovertemplate="%{x}<br>%{y} couples<extra></extra>"))
    return _mise_en_page(fig, "Couples livrés par jour fixe", 300)


def _besoins_utiles(schedule: pd.DataFrame) -> pd.DataFrame:
    """Lignes d'un schedule brut qui portent un vrai besoin (quantité > 0, date lisible)."""
    s = schedule.assign(date=pd.to_datetime(schedule["date"], errors="coerce"),
                        weight=pd.to_numeric(schedule["weight"], errors="coerce"),
                        schedule_quantity=pd.to_numeric(schedule["schedule_quantity"], errors="coerce"))
    return s[(s["schedule_quantity"] > 0) & s["date"].notna()]


def besoins_par_jour(schedule: pd.DataFrame) -> go.Figure:
    """Nombre de lignes de besoin par jour, empilé par usine (schedule brut, avant nettoyage).

    Args:
        schedule: schedule brut.

    Returns:
        Barres empilées, une couleur par usine (ordre fixe ``SERIES``).
    """
    s = _besoins_utiles(schedule)
    t = s.groupby(["date", "plant"]).size().unstack(fill_value=0).sort_index()
    fig = go.Figure()
    for usine in sorted(t.columns):
        fig.add_trace(go.Bar(x=t.index, y=t[usine], name=usine, marker_color=couleur_usine(usine),
                             marker_line_color="white", marker_line_width=1,
                             hovertemplate=f"{usine}<br>%{{x|%d/%m/%Y}} : %{{y}} lignes<extra></extra>"))
    fig.update_layout(barmode="stack", bargap=0.18, barcornerradius=2)
    fig.update_xaxes(tickformat="%d/%m", showgrid=False)
    fig.update_yaxes(title_text="lignes")
    return _mise_en_page(fig, "Lignes de besoin par jour et par usine", 360)


def poids_par_usine(schedule: pd.DataFrame) -> go.Figure:
    """Poids total à livrer à chaque usine (schedule brut, lignes à quantité > 0).

    Args:
        schedule: schedule brut.

    Returns:
        Barres horizontales, en tonnes, chaque usine dans sa couleur (la même que dans les autres graphiques).
    """
    p = (_besoins_utiles(schedule).groupby("plant")["weight"].sum() / 1000).sort_values()
    fig = go.Figure(go.Bar(x=p.values, y=p.index, orientation="h", marker_color=[couleur_usine(u) for u in p.index],
                           text=[f"{v:,.0f} t".replace(",", " ") for v in p.values], textposition="outside",
                           cliponaxis=False, hovertemplate="%{y}<br>%{x:,.1f} t<extra></extra>"))
    fig.update_xaxes(showticklabels=False, showgrid=False, range=[0, p.max() * 1.25 if len(p) else 1])
    fig.update_yaxes(showgrid=False)
    return _mise_en_page(fig, "Poids à livrer par usine", 360)


def top_fournisseurs(schedule: pd.DataFrame, n: int = 10) -> go.Figure:
    """Les fournisseurs qui envoient le plus de poids (schedule brut, lignes à quantité > 0).

    Args:
        schedule: schedule brut.
        n: nombre de fournisseurs affichés.

    Returns:
        Barres horizontales, du plus lourd au plus léger.
    """
    p = (_besoins_utiles(schedule).groupby("supplier_id")["weight"].sum() / 1000).nlargest(n)
    fig = go.Figure(go.Bar(x=p.values, y=p.index, orientation="h", marker_color=_clair(AQUA, 0.55),
                           marker_line_color=AQUA, marker_line_width=1,
                           text=[f"{v:,.0f} t".replace(",", " ") for v in p.values], textposition="outside",
                           cliponaxis=False, hovertemplate="%{y}<br>%{x:,.1f} t<extra></extra>"))
    fig.update_xaxes(showticklabels=False, showgrid=False, range=[0, p.max() * 1.25 if len(p) else 1])
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return _mise_en_page(fig, f"Top {n} fournisseurs (poids)", 360)


def camions_par_jour_semaine(camions_base: pd.DataFrame, planning: pd.DataFrame) -> go.Figure:
    """Camions moyens par jour de la semaine : baseline contre planning final (camions réservés compris).

    Args:
        camions_base: camions de la baseline (hors réservés).
        planning: planning complet (réservés compris).

    Returns:
        Barres groupées du lundi au vendredi : baseline en gris, planning final en bleu.
    """
    def moyenne(camions: pd.DataFrame) -> pd.Series:
        par_date = camions.groupby("date").size()
        par_date = par_date[par_date.index.day_of_week < 5]
        return par_date.groupby(par_date.index.day_of_week).mean().reindex(range(5), fill_value=0)

    reserves = planning[planning["reserve"]]
    base = moyenne(pd.concat([camions_base[["date"]], reserves[["date"]]]))
    final = moyenne(planning)
    fig = go.Figure([
        go.Bar(name="Baseline", x=JOURS, y=base.values, marker_color=GRIS,
               hovertemplate="%{x}<br>baseline : %{y:.0f} camions / jour<extra></extra>"),
        go.Bar(name="Planning final", x=JOURS, y=final.values, marker_color=BLEU,
               text=[f"{v:.0f}" for v in final.values], textposition="outside", cliponaxis=False,
               hovertemplate="%{x}<br>final : %{y:.0f} camions / jour<extra></extra>"),
    ])
    fig.update_layout(barmode="group", bargroupgap=0.08)
    fig.update_yaxes(title_text="camions / jour")
    return _mise_en_page(fig, "Camions moyens par jour de la semaine")


def changements_par_usine(changements: pd.DataFrame) -> go.Figure:
    """Nombre de couples qui changent entre deux plannings, par usine et par type de changement.

    Args:
        changements: couples qui changent (colonnes ``usine`` et ``statut``, voir ``comparaison.changements``).

    Returns:
        Barres horizontales empilées : nouveaux couples en bleu, couples disparus en gris, jours fixes changés
        en orange (la légende nomme chaque type).
    """
    couleurs = {"nouveau couple": BLEU, "couple disparu": GRIS, "jours fixes changés": ORANGE}
    t = changements.groupby(["usine", "statut"], observed=True).size().unstack(fill_value=0)
    fig = go.Figure()
    for statut, couleur in couleurs.items():
        if statut in t.columns:
            fig.add_trace(go.Bar(y=t.index, x=t[statut], name=statut, orientation="h", marker_color=couleur,
                                 marker_line_color="white", marker_line_width=1,
                                 hovertemplate=f"%{{y}}<br>{statut} : %{{x}}<extra></extra>"))
    fig.update_layout(barmode="stack", barcornerradius=2)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(title_text="couples", dtick=max(1, int(t.values.sum(axis=1).max() // 6) or 1))
    return _mise_en_page(fig, "Changements par usine", max(240, 60 * len(t) + 110))


def lignes_par_flag(par_flag: pd.Series) -> go.Figure:
    """Nombre de lignes en quarantaine par problème détecté (une ligne peut en avoir plusieurs).

    Args:
        par_flag: nom du flag -> nombre de lignes.

    Returns:
        Barres horizontales, du flag le plus fréquent au moins fréquent.
    """
    libelles = {"MISSING_WEIGHT": "poids manquant", "MISSING_VOLUME": "volume manquant",
                "NO_DISTANCE": "fournisseur sans distance", "OVER_TRUCK_WEIGHT": "plus lourd qu'un camion",
                "OVER_TRUCK_VOLUME": "plus volumineux qu'un camion"}
    fig = go.Figure(go.Bar(
        x=par_flag.values, y=[libelles.get(f, f) for f in par_flag.index], orientation="h", marker_color=JAUNE,
        text=par_flag.values, textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br>%{x} lignes<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(range=[0, par_flag.max() * 1.2])
    return _mise_en_page(fig, "Lignes en quarantaine par problème", max(220, 46 * len(par_flag) + 90))


def barres_runs(x: Sequence[str], series: dict[str, list[float]], titre: str, suffixe: str = "") -> go.Figure:
    """Valeur d'une ou plusieurs métriques à chaque run : une barre par run (et par métrique).

    Args:
        x: libellé de chaque run (date et fichier), du plus ancien au plus récent.
        series: nom de la métrique -> valeurs, dans l'ordre des runs.
        titre: titre du graphique.
        suffixe: unité affichée après les valeurs (par exemple ``" %"``).

    Returns:
        Barres groupées, une couleur par métrique (ordre fixe ``SERIES``), valeur au-dessus de chaque barre
        tant qu'il y a peu de barres.
    """
    fig = go.Figure()
    etiquettes = len(x) * len(series) <= 24
    for i, (nom, valeurs) in enumerate(series.items()):
        fig.add_trace(go.Bar(
            x=list(x), y=valeurs, name=nom, marker_color=SERIES[i % len(SERIES)],
            text=[f"{v:,.1f}".replace(",", " ").replace(".", ",").removesuffix(",0") + suffixe for v in valeurs]
            if etiquettes else None,
            textposition="outside", cliponaxis=False,
            hovertemplate=f"{nom}<br>%{{x}}<br>%{{y:,.2f}}{suffixe}<extra></extra>"))
    fig.update_layout(barmode="group", bargroupgap=0.06, showlegend=len(series) > 1,
                      bargap=0.45 if len(x) <= 3 else 0.25)
    fig.update_xaxes(showgrid=False, type="category")
    fig.update_yaxes(rangemode="tozero")
    return _mise_en_page(fig, titre, 400)


def barres_ecarts(noms: Sequence[str], ecarts_pct: Sequence[float], effets: Sequence[str], titre: str) -> go.Figure:
    """Écart en % de chaque métrique entre deux runs, coloré selon l'effet.

    Args:
        noms: noms des métriques.
        ecarts_pct: écart de chaque métrique, en %.
        effets: effet de chaque écart (``▲ mieux``, ``▼ moins bien``, ``= identique``, ``· neutre``),
            repris dans l'étiquette pour ne pas reposer sur la couleur seule.
        titre: titre du graphique.

    Returns:
        Barres horizontales autour de 0 : mieux en vert, moins bien en rouge, neutre en gris.
    """
    couleurs = [VERT if e.startswith("▲") else ROUGE if e.startswith("▼") else GRIS for e in effets]
    fig = go.Figure(go.Bar(
        x=list(ecarts_pct), y=list(noms), orientation="h", marker_color=couleurs,
        text=[f"{pourcent_signe(v)}  {e.split(' ')[0]}" for v, e in zip(ecarts_pct, effets)],
        textposition="outside", cliponaxis=False, customdata=list(effets),
        hovertemplate="%{y}<br>%{x:+.2f} % (%{customdata})<extra></extra>"))
    fig.add_vline(x=0, line_color=TEXTE_SECONDAIRE, line_width=1)
    bas, haut = min(0.0, min(ecarts_pct)), max(0.0, max(ecarts_pct))
    marge = (haut - bas) * 0.35 or 1.0            # place pour les étiquettes, des deux côtés
    fig.update_xaxes(ticksuffix=" %", zeroline=False, range=[bas - (marge if bas < 0 else 0),
                                                            haut + (marge if haut > 0 else 0)])
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return _mise_en_page(fig, titre, max(240, 34 * len(noms) + 90))


def savings_par_couple(sortie3: pd.DataFrame, nb: int = 15, par_semaine: bool = True,
                       titre: str | None = None) -> go.Figure:
    """Coût de transport avant et après consolidation des couples qui économisent le plus (sortie 3).

    Args:
        sortie3: la sortie 3, triée par économie décroissante.
        nb: nombre de couples affichés.
        par_semaine: coût moyen par semaine (sinon coût sur toute la période).
        titre: titre du graphique (par défaut, il décrit la sélection).

    Returns:
        Barres horizontales groupées : coût actuel en gris, coût après consolidation en bleu, le plus gros saving
        en haut, l'économie en % au bout de la barre bleue.
    """
    s = sortie3.head(nb).iloc[::-1]
    avant, apres = ("cout_actuel_semaine", "cout_apres_semaine") if par_semaine else ("cout_actuel", "cout_apres")
    couples = [f"{f} × {u}" for f, u in zip(s["fournisseur"], s["usine"])]
    # en barres horizontales groupées, la première trace est dessinée en bas : « après » d'abord, « actuel » au-dessus
    fig = go.Figure([
        go.Bar(name="Coût après consolidation", y=couples, x=s[apres], orientation="h", marker_color=BLEU,
               text=[pourcent_signe(-p * 100) for p in s["economie_pct"].fillna(0)], textposition="outside",
               cliponaxis=False, hovertemplate="%{y}<br>après : %{x:,.0f} €<extra></extra>"),
        go.Bar(name="Coût actuel", y=couples, x=s[avant], orientation="h", marker_color=GRIS,
               hovertemplate="%{y}<br>actuel : %{x:,.0f} €<extra></extra>"),
    ])
    fig.update_layout(barmode="group", bargroupgap=0.06, bargap=0.28, legend_traceorder="reversed")
    fig.update_xaxes(ticksuffix=" €", separatethousands=True)
    fig.update_yaxes(showgrid=False)
    titre = titre or f"Coût de transport{' par semaine' if par_semaine else ''}, {len(s)} couples qui économisent le plus"
    return _mise_en_page(fig, titre, max(380, 62 * len(s) + 110))
