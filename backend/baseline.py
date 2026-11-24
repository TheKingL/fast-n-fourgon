"""Baseline de transport (milestone 2) : la situation actuelle, avant consolidation entre les jours.

Une commande = un fournisseur, une usine, un jour. Les lignes d'une commande sont triées du plus lourd au plus
léger et chacune va dans le premier camion où elle rentre (24,5 t, 110,4 m³), sinon dans un nouveau camion
(First Fit Decreasing). Une ligne sans poids ou sans volume part seule dans un camion réservé ; une ligne de plus de 24,5 t
est exclue (en attente de la réponse du client).
"""
import numpy as np
import pandas as pd

from .config import POIDS_MAX, VOLUME_MAX

CLES_COMMANDE: list[str] = ["need_date", "supplier_id", "plant"]
"""Une commande = un fournisseur, une usine, un jour."""


def construire_baseline(clean: pd.DataFrame, quarantaine: pd.DataFrame) -> pd.DataFrame:
    """Construit les camions de la baseline.

    Args:
        clean: lignes saines (silver clean, voir ``nettoyage.nettoyer``).
        quarantaine: lignes en quarantaine (avec la colonne ``flags``).

    Returns:
        Une ligne par camion : ``camion_id``, ``commande_id``, ``supplier_id``, ``plant``, ``date``,
        ``camion`` (n° dans la commande), ``poids``, ``volume`` (NaN si inconnu), ``nb_lignes``, ``reserve``
        (camion réservé à une ligne sans poids) et ``source`` (``silver`` ou ``quarantaine``) ;
        flottants arrondis à 6 décimales, comme le fichier ``baseline_camion.csv``.
    """
    silver = clean.assign(source="silver", ligne_id=range(len(clean)))
    q = quarantaine.assign(source="quarantaine", ligne_id=range(len(quarantaine)))
    trop_lourd = q["weight"] > POIDS_MAX                       # exclue, en attente de la réponse du client
    schedule = pd.concat([silver, q[~trop_lourd].drop(columns="flags")], ignore_index=True)
    # poids ou volume inconnu : un camion réservé pour la ligne
    schedule["reserve"] = schedule["weight"].isna() | schedule["volume"].isna()

    # Tri : commande, puis poids du plus lourd au plus léger (les poids inconnus à la fin)
    df = schedule.sort_values(CLES_COMMANDE + ["weight"], ascending=[True, True, True, False],
                              na_position="last").copy()
    numeros_camion: list[int] = []
    for _, lignes in df.groupby(CLES_COMMANDE, sort=False):
        ouverts: list[list[float]] = []                        # [poids, volume] chargés dans chaque camion
        for poids, volume, reserve in zip(lignes["weight"], lignes["volume"], lignes["reserve"]):
            if reserve:                                        # camion réservé, fermé aux autres lignes
                ouverts.append([np.inf, np.inf])
                numeros_camion.append(len(ouverts))
                continue
            for i, (poids_camion, volume_camion) in enumerate(ouverts):
                if poids_camion + poids <= POIDS_MAX and volume_camion + volume <= VOLUME_MAX:
                    ouverts[i] = [poids_camion + poids, volume_camion + volume]
                    numeros_camion.append(i + 1)
                    break
            else:                                              # ne rentre dans aucun camion ouvert
                ouverts.append([poids, volume])
                numeros_camion.append(len(ouverts))

    df["camion"] = numeros_camion
    df["commande_id"] = df.groupby(CLES_COMMANDE).ngroup() + 1
    df["camion_id"] = df.groupby(CLES_COMMANDE + ["camion"]).ngroup() + 1
    df = df.rename(columns={"need_date": "date"})

    def somme(s: pd.Series) -> float:
        """Somme, NaN si aucune valeur n'est connue."""
        return s.sum(min_count=1)

    camions = (df.groupby(["camion_id", "commande_id", "supplier_id", "plant", "date", "camion"])
                 .agg(poids=("weight", somme), volume=("volume", somme), nb_lignes=("weight", "size"),
                      reserve=("reserve", "any"),
                      source=("source", lambda s: "quarantaine" if s.eq("quarantaine").any() else "silver"))
                 .reset_index())

    connus = ~camions["reserve"]
    assert abs(camions["poids"].sum() - schedule["weight"].sum()) < 1e-6          # aucun poids perdu
    assert (camions.loc[connus, "poids"] <= POIDS_MAX).all()
    assert (camions.loc[connus, "volume"] <= VOLUME_MAX).all()
    assert (camions.loc[~connus, "nb_lignes"] == 1).all()                         # un camion réservé = une ligne
    # arrondi à 6 décimales, comme le CSV : enlève le bruit des sommes en virgule flottante
    return camions.round(dict.fromkeys(camions.select_dtypes("float").columns, 6))
