"""Éléments d'interface réutilisables : bandeau de page, titres de section, cartes, pastilles, écarts KPI."""
from collections.abc import Sequence
from html import escape

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from backend.formatage import eur, nombre


def hero(badge: str, titre: str, sous_titre: str, stats: Sequence[tuple[str, str]] = ()) -> None:
    """Affiche le bandeau en haut d'une page.

    Args:
        badge: petit libellé au-dessus du titre (par exemple ``"ANALYSE"``).
        titre: titre de la page.
        sous_titre: une phrase de contexte sous le titre.
        stats: chiffres clés affichés à droite, ``(libellé, valeur)``.
    """
    blocs = "".join(f'<div class="stat"><span>{escape(l)}</span><b>{escape(v)}</b></div>' for l, v in stats)
    st.html(f'<div class="hero"><div class="texte"><span class="badge">{escape(badge.upper())}</span>'
            f"<h1>{escape(titre)}</h1><p>{escape(sous_titre)}</p></div>"
            f'<div class="stats">{blocs}</div></div>')


def section(titre: str, note: str = "") -> None:
    """Affiche un titre de section, avec une note discrète alignée à droite.

    Args:
        titre: titre de la section.
        note: précision affichée à droite (facultative).
    """
    st.html(f'<div class="section"><h3>{escape(titre)}</h3><span>{escape(note)}</span></div>')


def carte(nom: str, parent: DeltaGenerator | None = None) -> DeltaGenerator:
    """Crée une carte blanche (conteneur à ombre douce) pour un graphique ou un tableau.

    Args:
        nom: nom unique dans la page (sert de clé Streamlit et de classe CSS ``st-key-carte-<nom>``).
        parent: conteneur dans lequel placer la carte (une colonne...) ; la page par défaut.

    Returns:
        Le conteneur, à utiliser avec ``with``.
    """
    return (parent or st).container(key=f"carte-{nom}")


def pastille(texte: str, genre: str = "info") -> str:
    """Construit une pastille de statut en HTML (à insérer dans ``st.html``).

    Args:
        texte: libellé de la pastille (le statut ne repose jamais sur la couleur seule).
        genre: ``"ok"`` (vert), ``"ko"`` (rouge) ou ``"info"`` (bleu).

    Returns:
        Le HTML de la pastille.
    """
    icone = {"ok": "✓", "ko": "✕", "info": "•"}.get(genre, "•")
    return f'<span class="pastille {genre}">{icone} {escape(texte)}</span>'


def tuile(valeur: str, texte: str, accent: bool = False) -> str:
    """Tuile de chiffre clé (grande valeur et une ligne d'explication), en HTML pour ``st.html``.

    Args:
        valeur: le chiffre, déjà formaté.
        texte: l'explication sous le chiffre.
        accent: ``True`` pour la tuile mise en avant (fond orange).

    Returns:
        Le fragment HTML.
    """
    return (f'<div class="tuile{" accent" if accent else ""}"><div class="valeur">{escape(valeur)}</div>'
            f'<div class="texte">{escape(texte)}</div></div>')


def ecart_texte(ecart: float | None, unite: str = "") -> str | None:
    """Met en forme l'écart d'une carte KPI (``st.metric``), signe en tête pour le sens de la flèche.

    Args:
        ecart: écart à afficher (None : pas d'écart, la carte n'en montre pas).
        unite: ``"€"`` (montant), ``"pt"`` (points de pourcentage) ou ``""`` (nombre).

    Returns:
        Par exemple ``"-84 265 €"``, ``"+1,6 pt"``, ``"-532"`` ; None si ``ecart`` est None ou s'arrondit à 0
        (pas de flèche pour un écart invisible).
    """
    if ecart is None or round(abs(ecart), 0 if unite == "€" else 1) == 0:
        return None
    texte = eur(abs(ecart)) if unite == "€" else f"{nombre(abs(ecart))}{' pt' if unite == 'pt' else ''}"
    return f"{'-' if ecart < 0 else '+'}{texte}"
