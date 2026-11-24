"""Backend du moteur de consolidation des livraisons.

Le package contient tout le calcul ; ``main.py`` (à la racine du dépôt) enchaîne les étapes et un front end
peut appeler directement ``main.executer()``, qui retourne un objet ``backend.resultats.Resultats``.

Modules, dans l'ordre du flux :

- ``config`` : chemins des fichiers et paramètres du moteur ;
- ``typage`` : alias de types partagés (``Profil``, ``Couple``, ``Choix``, ``Charge``...) ;
- ``formatage`` : mise en forme des nombres pour l'affichage ;
- ``couts`` : grille tarifaire, distances et coût d'un camion ;
- ``donnees`` : besoins à consolider, camions réservés, baseline, horizon du planning ;
- ``charge`` : charge des usines (camions par jour) et tolérance de lissage ;
- ``contraintes`` : vérification des contraintes C1 à C10 et cohérence du planning ;
- ``jours_fixes`` : bloc 1, scénarios de chaque couple pour chaque profil de jours fixes ;
- ``lissage`` : blocs 2 et 3, contrôle de l'équilibre des usines et lissage ;
- ``report`` : bloc 4, report des lignes sur le jour fixe suivant et planning final ;
- ``sorties`` : bilan des économies, sortie 1, sortie 2 et export CSV ;
- ``resultats`` : la dataclass ``Resultats`` retournée par le moteur.
"""
