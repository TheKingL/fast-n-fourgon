"""Front end Streamlit du moteur de consolidation des livraisons.

Lancement (depuis la racine du dépôt) : ``streamlit run frontend/app.py`` ou ``lancer_dashboard.bat``.

- ``app`` : point d'entrée, navigation entre les deux pages ;
- ``vues/analyse`` : partie 1, un schedule en entrée, le moteur tourne, résultats et comparaison au dernier run ;
- ``vues/historique`` : partie 2, évolution des métriques run après run, comparaison de deux runs, journal ;
- ``moteur`` : appel du backend et calcul des métriques d'un run ;
- ``historique`` : historisation des runs (fichiers CSV dans ``data/historique/``) ;
- ``graphiques`` : graphiques Plotly ;
- ``composants`` / ``style`` : éléments d'interface et feuille de style.
"""
