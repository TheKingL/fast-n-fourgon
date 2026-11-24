"""Export des livrables d'une analyse : classeur Excel mis en forme, ou archive ZIP de fichiers CSV.

Les trois sorties du projet :

- sortie 1 : le profil de livraison à appliquer pour chaque couple ;
- sortie 2 : les materials regroupés dans chaque camion ;
- sortie 3 : le saving potentiel par couple ;

plus une synthèse (bilan des économies et économies par usine).
"""
import io
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import pandas as pd

try:                                    # openpyxl est facultatif : sans lui, seul l'export CSV est proposé
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    EXCEL_DISPONIBLE: bool = True
except ImportError:
    EXCEL_DISPONIBLE = False
if TYPE_CHECKING:
    from openpyxl.worksheet.worksheet import Worksheet

from backend.resultats import Resultats
from backend.sorties import construire_sortie3

BLEU_ENTETE: Final[str] = "0B3D5C"
"""Fond des en-têtes de colonnes (bleu nuit, comme les tableaux de la présentation)."""
BLEU_TOTAL: Final[str] = "DCEBF7"
"""Fond de la ligne Total."""


@dataclass(frozen=True)
class Livrable:
    """Une table exportable.

    Attributes:
        cle: identifiant court (``sortie1``...).
        libelle: nom affiché dans le dashboard.
        onglet: nom de la feuille Excel (31 caractères au plus).
        fichier: nom du fichier CSV.
        colonnes: nom de colonne -> ``(en-tête lisible, format Excel)`` ; les colonnes absentes sont gardées telles quelles.
    """

    cle: str
    libelle: str
    onglet: str
    fichier: str
    colonnes: dict[str, tuple[str, str]]


EUR: Final[str] = '#,##0.00 "€"'
"""Format Excel d'un montant."""
PCT: Final[str] = "0.0%"
"""Format Excel d'une proportion."""
ENTIER: Final[str] = "#,##0"
"""Format Excel d'un entier."""
DECIMAL: Final[str] = "#,##0.00"
"""Format Excel d'un nombre à deux décimales."""
DATE: Final[str] = "dd/mm/yyyy"
"""Format Excel d'une date."""

LIVRABLES: Final[dict[str, Livrable]] = {l.cle: l for l in [
    Livrable("synthese", "Synthèse", "Synthèse", "bilan.csv", {
        "Coût": ("Coût", EUR), "Économie vs baseline": ("Économie vs baseline", EUR),
        "Économie (%)": ("Économie (%)", PCT), "Avance moyenne (j)": ("Avance moyenne (j)", DECIMAL),
        "Camions": ("Camions", ENTIER)}),
    Livrable("sortie1", "Sortie 1 · profils", "Sortie 1 - Profils", "sortie1_profils.csv", {
        "fournisseur": ("Fournisseur", ""), "usine": ("Usine", ""), "distance_km": ("Distance (km)", ENTIER),
        "livraisons_semaine_actuelles": ("Livraisons / sem. actuelles", DECIMAL),
        "frequence_cible": ("Fréquence cible (jours / sem.)", ENTIER), "jours": ("Jours", ""),
        "camions_semaine": ("Camions / sem.", DECIMAL), "remplissage_poids": ("Remplissage poids", PCT)}),
    Livrable("sortie2", "Sortie 2 · camions", "Sortie 2 - Camions", "sortie2_camions.csv", {
        "camion_id": ("Camion", ENTIER), "usine": ("Usine", ""), "fournisseur": ("Fournisseur", ""),
        "date_livraison": ("Date de livraison", DATE), "jour": ("Jour", ""), "material": ("Material", ""),
        "quai": ("Quai", ""), "besoins": ("Besoins regroupés", ""), "nb_lignes": ("Lignes de besoin", ENTIER),
        "quantite": ("Quantité", ENTIER), "poids_kg": ("Poids (kg)", DECIMAL)}),
    Livrable("sortie3", "Sortie 3 · savings", "Sortie 3 - Savings", "sortie3_savings.csv", {
        "fournisseur": ("Fournisseur", ""), "usine": ("Usine", ""), "distance_km": ("Distance (km)", ENTIER),
        "camions_actuels": ("Camions actuels", ENTIER), "cout_actuel": ("Coût actuel", EUR),
        "camions_apres": ("Camions après", ENTIER), "cout_apres": ("Coût après", EUR),
        "economie": ("Économie", EUR), "economie_pct": ("Économie (%)", PCT),
        "cout_actuel_semaine": ("Coût actuel / sem.", EUR), "cout_apres_semaine": ("Coût après / sem.", EUR)}),
]}
"""Les tables exportables, dans l'ordre des feuilles du classeur."""

PAR_USINE: Final[dict[str, tuple[str, str]]] = {
    "usine": ("Usine", ""), "camions_baseline": ("Camions baseline", ENTIER), "cout_baseline": ("Coût baseline", EUR),
    "camions_final": ("Camions final", ENTIER), "cout_final": ("Coût final", EUR), "economie": ("Économie", EUR),
    "economie_pct": ("Économie (%)", PCT)}
"""En-têtes et formats du tableau des économies par usine (sous le bilan, dans la feuille Synthèse)."""


def tables(r: Resultats) -> dict[str, pd.DataFrame]:
    """Rassemble les tables exportables d'une analyse.

    Args:
        r: résultats du moteur.

    Returns:
        Clé du livrable -> table (``synthese`` est le bilan des économies).
    """
    return {"synthese": r.bilan, "sortie1": r.sortie1, "sortie2": sortie2(r),
            "sortie3": construire_sortie3(r.camions_base, r.planning_complet)}


def sortie2(r: Resultats) -> pd.DataFrame:
    """Sortie 2 telle qu'exportée et affichée : sans la colonne technique ``reserve``."""
    return r.sortie2.drop(columns="reserve", errors="ignore")


def par_usine(r: Resultats) -> pd.DataFrame:
    """Économies par usine, avec l'usine en colonne (ligne ``Total`` comprise)."""
    return r.par_usine.rename_axis("usine").reset_index()


# =====================================================================================================
# Excel
# =====================================================================================================
def _ecrire(feuille: "Worksheet", table: pd.DataFrame, colonnes: dict[str, tuple[str, str]], ligne: int = 1) -> int:
    """Écrit une table mise en forme dans une feuille, à partir d'une ligne donnée.

    Args:
        feuille: feuille de destination.
        table: table à écrire.
        colonnes: nom de colonne -> ``(en-tête, format Excel)``.
        ligne: première ligne (celle des en-têtes).

    Returns:
        La première ligne libre sous la table.
    """
    entete_police = Font(bold=True, color="FFFFFF")
    entete_fond = PatternFill("solid", fgColor=BLEU_ENTETE)
    for j, nom in enumerate(table.columns, start=1):
        cellule = feuille.cell(row=ligne, column=j, value=colonnes.get(nom, (nom, ""))[0])
        cellule.font, cellule.fill = entete_police, entete_fond
        cellule.alignment = Alignment(vertical="center", wrap_text=True)
    for i, valeurs in enumerate(table.itertuples(index=False), start=ligne + 1):
        for j, (nom, valeur) in enumerate(zip(table.columns, valeurs), start=1):
            if pd.isna(valeur):
                continue
            if isinstance(valeur, pd.Timestamp):
                valeur = valeur.to_pydatetime()
            elif hasattr(valeur, "item"):                     # nombre numpy -> nombre Python
                valeur = valeur.item()
            cellule = feuille.cell(row=i, column=j, value=valeur)
            if colonnes.get(nom, ("", ""))[1]:
                cellule.number_format = colonnes[nom][1]
        if str(valeurs[0]) == "Total":
            for j in range(1, len(table.columns) + 1):
                feuille.cell(row=i, column=j).font = Font(bold=True)
                feuille.cell(row=i, column=j).fill = PatternFill("solid", fgColor=BLEU_TOTAL)
    for j, nom in enumerate(table.columns, start=1):
        largeur = max(len(colonnes.get(nom, (nom, ""))[0]),
                      *(len(str(v)) for v in table[nom].head(200)), 6) if len(table) else 12
        lettre = get_column_letter(j)
        feuille.column_dimensions[lettre].width = max(feuille.column_dimensions[lettre].width or 0, min(largeur + 3, 45))
    return ligne + len(table) + 1


def classeur_excel(r: Resultats, cles: Iterable[str], source: str = "") -> bytes:
    """Construit un classeur Excel avec une feuille par livrable choisi.

    Args:
        r: résultats du moteur.
        cles: livrables à inclure (clés de ``LIVRABLES``), écrits dans l'ordre de ``LIVRABLES``.
        source: nom du schedule analysé, rappelé dans la feuille Synthèse.

    Returns:
        Le contenu du fichier ``.xlsx``.
    """
    choisies = [c for c in LIVRABLES if c in set(cles)]
    toutes = tables(r)
    tampon = io.BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as classeur:
        for cle in choisies:
            livrable = LIVRABLES[cle]
            feuille = classeur.book.create_sheet(livrable.onglet)
            if cle == "synthese":
                feuille["A1"] = f"Bilan des économies{f' · {source}' if source else ''}"
                feuille["A1"].font = Font(bold=True, size=14, color=BLEU_ENTETE)
                suite = _ecrire(feuille, toutes[cle], livrable.colonnes, ligne=3)
                feuille.cell(row=suite + 1, column=1, value="Économies par usine").font = Font(bold=True, size=12,
                                                                                               color=BLEU_ENTETE)
                _ecrire(feuille, par_usine(r), PAR_USINE, ligne=suite + 2)
            else:
                _ecrire(feuille, toutes[cle], livrable.colonnes)
                feuille.freeze_panes = "A2"
                feuille.auto_filter.ref = feuille.dimensions
            feuille.sheet_view.showGridLines = cle == "sortie2"
    return tampon.getvalue()


# =====================================================================================================
# CSV
# =====================================================================================================
def csv(table: pd.DataFrame, excel_fr: bool) -> bytes:
    """Écrit une table en CSV.

    Args:
        table: table à écrire.
        excel_fr: ``True`` pour un Excel français (séparateur ``;``, virgule décimale, encodage avec BOM) ;
            ``False`` pour un CSV standard (``,`` et point décimal, comme les fichiers de ``data/gold``).

    Returns:
        Le contenu du fichier.
    """
    if excel_fr:
        return table.to_csv(index=False, sep=";", decimal=",", date_format="%d/%m/%Y").encode("utf-8-sig")
    return table.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8")


def archive_csv(r: Resultats, cles: Iterable[str], excel_fr: bool) -> bytes:
    """Construit une archive ZIP avec un fichier CSV par livrable choisi.

    Args:
        r: résultats du moteur.
        cles: livrables à inclure (clés de ``LIVRABLES``).
        excel_fr: format des CSV (voir ``csv``).

    Returns:
        Le contenu du fichier ``.zip``.
    """
    toutes = tables(r)
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        for cle in (c for c in LIVRABLES if c in set(cles)):
            archive.writestr(LIVRABLES[cle].fichier, csv(toutes[cle], excel_fr))
            if cle == "synthese":
                archive.writestr("economies_par_usine.csv", csv(par_usine(r), excel_fr))
    return tampon.getvalue()

