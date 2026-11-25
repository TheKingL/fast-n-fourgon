"""Chargement du moteur (main.py) et aides communes aux tests.

Fichier généré à partir de data_analysis/milestone4.ipynb : les tests sont les mêmes que dans le notebook.
"""
import contextlib
import io
import types

import pandas as pd

with contextlib.redirect_stdout(io.StringIO()):   # le moteur tourne une fois, sans rien afficher ni écrire
    import main
    from backend import charge, config, contraintes, couts, donnees, formatage, jours_fixes, lissage, report
    R = main.executer()

# m regroupe les fonctions et données du backend (un seul nom pour les tests) et les résultats du moteur
m = types.SimpleNamespace()
for module in (config, couts, donnees, charge, contraintes, jours_fixes, lissage, report, formatage):
    vars(m).update({nom: valeur for nom, valeur in vars(module).items() if not nom.startswith("_")})
for nom in ("planning_complet", "lignes_complet", "sortie1", "sortie2"):
    setattr(m, nom, getattr(R, nom))

J = pd.Timestamp
P, L = m.planning_complet, m.lignes_complet       # planning final (une ligne par camion) et lignes de besoin livrées


def lignes_test(*lignes):
    # Lignes de besoin d'un couple fictif : (date du besoin, poids en kg, volume en m³)
    return pd.DataFrame([{"need_date": J(d), "weight": w, "volume": v} for d, w, v in lignes])
