"""Moteur de consolidation des livraisons, découpé en modules.

Ordre des modules = ordre du flux (orchestré par main.py à la racine du dépôt) :
  config      : chemins des fichiers et paramètres du moteur
  formatage   : mise en forme des nombres pour l'affichage
  couts       : grille tarifaire, distances et coût d'un camion
  donnees     : besoins à consolider, camions réservés, baseline, horizon du planning
  charge      : charge des usines (camions par jour) et tolérance de lissage
  contraintes : vérification des contraintes C1 à C10 et cohérence du planning
  jours_fixes : bloc 1, scénarios de chaque couple pour chaque profil de jours fixes
  lissage     : blocs 2 et 3, contrôle de l'équilibre des usines et lissage
  report      : bloc 4, report des lignes sur le jour fixe suivant et planning final
  sorties     : bilan des économies, sortie 1, sortie 2 et export CSV
"""
