"""Palette et feuille de style du dashboard : pleine largeur, fond bleu très clair, cartes blanches à ombre douce."""
from typing import Final

import streamlit as st

# ---------- Palette ----------
BLEU: Final[str] = "#2A78D6"
"""Couleur principale : série principale, éléments actifs."""
BLEU_FONCE: Final[str] = "#0D366B"
"""Titres et seconde série foncée."""
BLEU_CLAIR: Final[str] = "#9EC5F4"
"""Série secondaire claire, fonds d'accent."""
GRIS: Final[str] = "#A3ADB8"
"""Référence (baseline) : ce à quoi on se compare."""
ORANGE: Final[str] = "#EB6834"
"""Seconde couleur catégorielle."""
AQUA: Final[str] = "#1BAF7A"
"""Troisième couleur catégorielle."""
JAUNE: Final[str] = "#EDA100"
"""Quatrième couleur catégorielle."""
VIOLET: Final[str] = "#6250D6"
"""Septième couleur catégorielle."""
VERT: Final[str] = "#0CA30C"
"""Statut « bon » (toujours accompagné d'un libellé)."""
ROUGE: Final[str] = "#D03B3B"
"""Statut « critique » et pôle négatif des écarts."""
TEXTE: Final[str] = "#0F1E2E"
"""Texte principal."""
TEXTE_SECONDAIRE: Final[str] = "#5B6B7C"
"""Texte secondaire (légendes, axes)."""
GRILLE: Final[str] = "#EDF2F8"
"""Lignes de grille des graphiques."""
RAMPE_BLEUE: Final[list[str]] = ["#F4F8FC", "#CDE2FB", "#9EC5F4", "#6DA7EC", "#3987E5", "#256ABF", "#184F95", "#0D366B"]
"""Rampe séquentielle (intensité) : du presque blanc au bleu foncé."""

_CSS: Final[str] = """
<style>
/* La police (Inter) est déclarée dans .streamlit/config.toml : on ne la force pas ici,
   pour ne pas écraser la police des icônes Material. */

/* ---------- Fond et pleine largeur ---------- */
.stApp {
    background:
        radial-gradient(900px 420px at 92% -8%, rgba(57,135,229,0.13), transparent 62%),
        radial-gradient(700px 380px at 8% 108%, rgba(109,167,236,0.10), transparent 60%),
        #F4F8FC;
}
[data-testid="stMainBlockContainer"] {
    max-width: 100% !important;
    padding: 4.4rem clamp(1.2rem, 3vw, 3.6rem) 3rem !important;
}
[data-testid="stHeader"] { background: rgba(244,248,252,0.78); backdrop-filter: blur(10px); }
h1, h2, h3 { letter-spacing: -0.015em; color: #0F1E2E; }

/* ---------- Navigation du haut ---------- */
[data-testid="stTopNavLink"] { border-radius: 10px; padding: 0.3rem 0.8rem; }

/* ---------- Barre latérale ---------- */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #FFFFFF 0%, #F5F9FF 100%);
    border-right: 1px solid #E3EBF3;
}
[data-testid="stSidebar"] h4 {
    font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.09em; color: #5B6B7C; font-weight: 600;
    margin-top: 0.6rem;
}
.marque { display: flex; align-items: center; gap: 0.7rem; margin: -0.6rem 0 1.1rem; }
.marque .logo {
    width: 38px; height: 38px; border-radius: 11px; display: grid; place-items: center; color: white;
    font-weight: 700; font-size: 1.05rem; background: linear-gradient(135deg, #3987E5, #184F95);
    box-shadow: 0 6px 16px -6px rgba(42,120,214,0.55);
}
.marque b { display: block; font-size: 0.98rem; color: #0F1E2E; }
.marque span { font-size: 0.78rem; color: #5B6B7C; }

/* ---------- Hero ---------- */
.hero {
    position: relative; overflow: hidden; display: flex; flex-wrap: wrap; align-items: flex-end;
    justify-content: space-between; gap: 1.4rem;
    background: linear-gradient(118deg, #FFFFFF 0%, #F3F8FE 52%, #E2EEFC 100%);
    border: 1px solid #E3EBF3; border-radius: 22px; padding: 1.8rem 2.1rem 1.7rem; margin-bottom: 1.3rem;
    box-shadow: 0 1px 2px rgba(15,30,46,0.04), 0 18px 40px -28px rgba(42,120,214,0.45);
}
.hero::before {
    content: ""; position: absolute; right: -90px; top: -120px; width: 380px; height: 380px; border-radius: 50%;
    background: radial-gradient(circle, rgba(57,135,229,0.24) 0%, rgba(57,135,229,0) 68%);
}
.hero::after {
    content: ""; position: absolute; right: 18%; bottom: -150px; width: 260px; height: 260px; border-radius: 50%;
    background: radial-gradient(circle, rgba(109,167,236,0.18) 0%, rgba(109,167,236,0) 70%);
}
.hero .texte { position: relative; z-index: 1; min-width: 280px; }
.hero .badge {
    display: inline-block; font-size: 0.7rem; font-weight: 600; letter-spacing: 0.09em;
    color: #184F95; background: rgba(42,120,214,0.10); border-radius: 999px; padding: 0.24rem 0.75rem;
}
.hero h1 { font-size: clamp(1.7rem, 2.3vw, 2.35rem); font-weight: 700; margin: 0.55rem 0 0.3rem; padding: 0; }
.hero p { color: #5B6B7C; margin: 0; font-size: 1rem; }
.hero .stats { position: relative; z-index: 1; display: flex; flex-wrap: wrap; gap: 0.6rem; }
.hero .stat {
    background: rgba(255,255,255,0.78); border: 1px solid #E3EBF3; border-radius: 14px; padding: 0.55rem 0.95rem;
    backdrop-filter: blur(6px); min-width: 110px;
}
.hero .stat span { display: block; font-size: 0.72rem; color: #5B6B7C; text-transform: uppercase; letter-spacing: 0.06em; }
.hero .stat b { font-size: 1.05rem; color: #0F1E2E; font-weight: 650; }

/* ---------- Titres de section ---------- */
.section { display: flex; justify-content: space-between; align-items: baseline; margin: 1.7rem 0 0.7rem; }
.section h3 { font-size: 1.2rem; font-weight: 650; margin: 0; padding: 0; }
.section span { color: #5B6B7C; font-size: 0.85rem; }

/* ---------- Cartes : KPI, graphiques, tableaux ---------- */
[data-testid="stMetric"], [class*="st-key-carte"] {
    background: #FFFFFF; border: 1px solid #E3EBF3 !important; border-radius: 18px !important;
    box-shadow: 0 1px 2px rgba(15,30,46,0.04), 0 10px 28px -18px rgba(42,120,214,0.35);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
[data-testid="stMetric"] { padding: 1.05rem 1.2rem 0.85rem; }
[class*="st-key-carte"] { padding: 0.9rem 1.1rem 0.6rem; }
[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 1px 2px rgba(15,30,46,0.05), 0 16px 32px -18px rgba(42,120,214,0.5);
}
[data-testid="stMetricLabel"] p { color: #5B6B7C; font-size: 0.86rem; font-weight: 500; }
[data-testid="stMetricIcon"] {
    color: #2A78D6 !important; background: #E8F1FD; border-radius: 8px; padding: 3px;
}
[data-testid="stMetricValue"] { font-weight: 700; color: #0F1E2E; font-size: clamp(1.6rem, 2vw, 2.15rem); }
[data-testid="stDataFrame"] {
    background: #FFFFFF; border-radius: 14px; overflow: hidden; border: 1px solid #E3EBF3;
    box-shadow: 0 1px 2px rgba(15,30,46,0.04);
}
[data-testid="stExpander"] details {
    background: #FFFFFF; border-radius: 14px !important; border: 1px solid #E3EBF3 !important;
}

/* ---------- Onglets en pilules ---------- */
[data-testid="stTabs"] [role="tablist"] {
    gap: 0.25rem; background: #FFFFFF; border: 1px solid #E3EBF3; border-radius: 14px; padding: 0.3rem;
    width: fit-content; max-width: 100%; overflow-x: auto; margin-bottom: 0.6rem;
    box-shadow: 0 1px 2px rgba(15,30,46,0.04);
}
[data-testid="stTabs"] [role="tab"] { padding: 0.45rem 1rem; border-radius: 10px; height: auto; border: none; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] { background: #E8F1FD; color: #184F95; }
[data-testid="stTabs"] [role="tablist"] > div:not([role="tab"]) { display: none; }   /* soulignement par défaut */

/* ---------- Boutons ---------- */
[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, #3987E5 0%, #1C5CAB 100%); border: none;
    box-shadow: 0 8px 18px -10px rgba(42,120,214,0.8);
}
[data-testid="stBaseButton-primary"]:hover { filter: brightness(1.06); }

/* ---------- Bandeau d'appel à l'action ---------- */
.appel {
    display: flex; align-items: center; gap: 1rem; padding: 1rem 1.2rem; border-radius: 16px;
    background: linear-gradient(120deg, #E8F1FD, #F7FBFF); border: 1px dashed #9EC5F4; color: #184F95;
}
.appel b { color: #0D366B; }

/* ---------- Pastilles de statut ---------- */
.pastille { display: inline-flex; align-items: center; gap: 0.35rem; border-radius: 999px; margin: 0 0.3rem 0.3rem 0;
            padding: 0.2rem 0.7rem; font-size: 0.8rem; font-weight: 600; }
.pastille.ok { background: #E3F5E3; color: #0A6B0A; }
.pastille.ko { background: #FBE7E7; color: #A12C2C; }
.pastille.info { background: #E8F1FD; color: #184F95; }
.note { color: #5B6B7C; font-size: 0.85rem; }
</style>
"""

_MARQUE: Final[str] = (
    '<div class="marque"><div class="logo">C</div>'
    "<div><b>Consolidation</b><span>livraisons fournisseurs</span></div></div>"
)


def appliquer_style() -> None:
    """Injecte la feuille de style et le bloc de marque de la barre latérale (une fois, dans ``app.py``)."""
    st.html(_CSS)
    with st.sidebar:
        st.html(_MARQUE)
