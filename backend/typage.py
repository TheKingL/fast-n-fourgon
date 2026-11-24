"""Alias de types partagés par tous les modules du backend.

Ils donnent un nom métier aux structures qui circulent entre les étapes du moteur :

- ``Profil`` : jours fixes de livraison d'un couple, en numéros de jour (0 = lundi ... 4 = vendredi),
  par exemple ``(0,)`` = le lundi, ``(1, 3)`` = le mardi et le jeudi ;
- ``Couple`` : couple ``(usine, fournisseur)``, par exemple ``("PLT_002", "SUP_00038")`` ;
- ``CleScenario`` : un couple et un profil, ``(usine, fournisseur, profil)`` ;
- ``Choix`` : le profil retenu pour chaque couple ;
- ``Charge`` : camions reçus par une usine, matrice ``semaines × 5 jours`` (lundi -> vendredi) ;
- ``Charges`` : la charge de chaque usine, indexée par le code usine.
"""
from typing import TypeAlias

import numpy as np
import numpy.typing as npt

Profil: TypeAlias = tuple[int, ...]
Couple: TypeAlias = tuple[str, str]
CleScenario: TypeAlias = tuple[str, str, Profil]
Choix: TypeAlias = dict[Couple, Profil]
Charge: TypeAlias = npt.NDArray[np.float64]
Charges: TypeAlias = dict[str, Charge]
