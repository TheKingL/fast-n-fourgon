"""Moteur de consolidation des livraisons (milestone 3).

Reprend l'algorithme de data_analysis/milestone3.ipynb, sans les graphiques ni les études annexes :
  1. jours fixes : chaque couple fournisseur × usine choisit ses 1 ou 2 jours de livraison les moins chers ;
  2. contrôle de l'équilibre des usines (C10) ;
  3. lissage : changements de profil au moindre surcoût jusqu'à ce que les semaines soient dans la tolérance ;
  4. report des lignes sur le jour fixe suivant, puis planning final.

Sorties (mêmes fichiers que le notebook, écrits dans data/gold/) :
  - sortie 1, sortie1_profils.csv : le profil à appliquer pour chaque couple (aperçu dans la console) ;
  - sortie 2, sortie2_camions.csv : les materials regroupés dans chaque camion (détail d'un camion dans la console) ;
  - bilan.csv : tableau des économies (baseline vs chaque étape du moteur), aussi affiché dans la console.

Lancement : python main.py            (détaille le camion qui regroupe le plus de lignes de besoin)
            python main.py <camion>   (détaille le camion choisi, par exemple python main.py 254)
"""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):          # console Windows ; absent dans un notebook
    sys.stdout.reconfigure(encoding="utf-8")

# ---------- Fichiers ----------
DATA = Path(__file__).resolve().parent / "data"
SILVER_CLEAN_PATH = DATA / "silver" / "released_schedule_cleaned.csv"
QUARANTAINE_PATH = DATA / "silver" / "released_schedule_quarantine.csv"
BASELINE_PATH = DATA / "baseline" / "baseline_camion.csv"   # baseline du milestone 2 : une ligne par camion
RATE_SHEET_PATH = DATA / "bronze" / "rate_sheet.csv"
DISTANCES_PATH = DATA / "bronze" / "distances.csv"
SORTIE = DATA / "gold"

# ---------- Paramètres du moteur ----------
POIDS_MAX = 24500                 # kg par camion
VOLUME_MAX = 110.4                # m³ par camion
FENETRE = pd.Timedelta(days=7)    # avance maximale d'une livraison sur le besoin
JOURS_FIXES_MAX = 2               # un couple livre 1 ou 2 jours fixes par semaine
SEUIL_LISSAGE = 0.35              # écart max toléré entre un jour et la moyenne de la semaine
MIN_CAMIONS_SEMAINE = 5           # semaines plus petites (moins d'un camion par jour) : pas contrôlées
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]

# ---------- Coût de transport ----------
FREIGHT_VALUE_MARGIN = 2.3923     # +239,23 %
DIESEL_SURCHARGE = 1.1943
couts = pd.read_csv(RATE_SHEET_PATH, index_col="km_max")
TRANCHES_KM = [int(km) for km in couts.index if not km.startswith(">")]    # 30, 50, ..., 650
TRANCHES_KG = [int(kg) for kg in couts.columns if not kg.startswith(">")]  # 50, 100, ..., 4000
distances = pd.read_csv(DISTANCES_PATH, encoding="utf-8-sig").set_index("supplier_id")["distance"]

# Données manquantes : estimations hautes (comme dans la baseline du milestone 2)
DISTANCE_PAR_DEFAUT = TRANCHES_KM[-1] + 1  # 651 km -> tranche "> 650 km"
POIDS_PAR_DEFAUT = TRANCHES_KG[-1] + 1     # 4 001 kg -> tranche "> 4 000 kg"
SANS_DISTANCE = sorted(distances.index[distances.isna()])
distances = distances.fillna(DISTANCE_PAR_DEFAUT)


def tranche(valeur, tranches):
    # Première tranche >= valeur (on majore), sinon la tranche '>max'
    for borne in tranches:
        if valeur <= borne:
            return str(borne)
    return f">{tranches[-1]}"


def cout_transport(poids, distance):
    # Prix d'un camion en € = coût de la grille × (1 + marge) × diesel
    cout_base = couts.loc[tranche(distance, TRANCHES_KM), tranche(poids, TRANCHES_KG)]
    return float(round(cout_base * (1 + FREIGHT_VALUE_MARGIN) * DIESEL_SURCHARGE, 2))


def cout_camion(poids, supplier_id):
    # Coût d'un camion ; poids inconnu (camion réservé) -> tranche > 4 000 kg
    return cout_transport(POIDS_PAR_DEFAUT if pd.isna(poids) else poids, distances[supplier_id])


def cout_total(planning):
    # Objectif à minimiser : somme des coûts des camions
    return sum(cout_camion(p, s) for p, s in zip(planning["poids"], planning["supplier_id"]))


# ---------- Mise en forme ----------
def nombre(x):
    return f"{x:,.1f}".replace(",", " ").replace(".", ",").removesuffix(",0")


def pourcent(x):
    return f"{x:.1%}".replace(".", ",").replace("%", " %")


def eur(x):
    return f"{x:,.0f} €".replace(",", " ")


# =====================================================================================================
# Données des milestones 1 et 2
# =====================================================================================================
silver = pd.read_csv(SILVER_CLEAN_PATH, parse_dates=["need_date"])
quarantaine = pd.read_csv(QUARANTAINE_PATH, parse_dates=["need_date"])
N_SILVER = len(silver)
sans_poids = quarantaine["weight"].isna()
a_consolider = ~sans_poids & (quarantaine["weight"] <= POIDS_MAX)   # la ligne de plus de 24,5 t est exclue

# Besoins à consolider : silver + lignes de la quarantaine dont le poids est connu
besoins = (pd.concat([silver, quarantaine.loc[a_consolider, silver.columns]], ignore_index=True)
           .sort_values(["plant", "supplier_id", "need_date", "weight"], ascending=[True, True, True, False])
           [["need_date", "supplier_id", "material", "plant", "unloading_point", "schedule_quantity", "weight", "volume"]])

# Lignes sans poids : un camion réservé par ligne, le jour du besoin
lignes_reserves = quarantaine[sans_poids].drop(columns="flags").reset_index(drop=True)
lignes_reserves["numero"] = range(1, len(lignes_reserves) + 1)
lignes_reserves["id_ligne"] = "Q" + lignes_reserves["numero"].astype(str)
lignes_reserves["date_livraison"], lignes_reserves["avance_jours"] = lignes_reserves["need_date"], 0
camions_reserves = pd.DataFrame({
    "numero": lignes_reserves["numero"], "plant": lignes_reserves["plant"], "supplier_id": lignes_reserves["supplier_id"],
    "date": lignes_reserves["need_date"], "demarrage": False, "nb_lignes": 1, "poids": np.nan,
    "volume": lignes_reserves["volume"], "cout": [cout_camion(np.nan, s) for s in lignes_reserves["supplier_id"]],
    "motif": "poids inconnu"})
COUT_RESERVE, NB_RESERVE = camions_reserves["cout"].sum(), len(camions_reserves)


def avec_reserves(camions):
    return pd.concat([camions, camions_reserves.drop(columns="numero")], ignore_index=True)


# Baseline du milestone 2 (sans ses camions réservés, comptés à part : les mêmes pour toutes les versions)
camions_base = pd.read_csv(BASELINE_PATH, parse_dates=["date"])
assert camions_base["reserve"].sum() == NB_RESERVE
camions_base = camions_base[~camions_base["reserve"]].copy()
camions_base["cout"] = [cout_camion(p, s) for p, s in zip(camions_base["poids"], camions_base["supplier_id"])]
COUT_BASELINE = camions_base["cout"].sum()

# Horizon du planning
DEBUT, FIN = besoins["need_date"].min(), besoins["need_date"].max()   # lundi 09/11 -> vendredi 18/12
SEMAINES = sorted(besoins["need_date"].dt.isocalendar().week.unique())
NB_SEMAINES = len(SEMAINES)
CONTROLE = list(range(NB_SEMAINES - 1))   # la dernière semaine est incomplète : pas contrôlée
USINES = sorted(besoins["plant"].unique())
IDS_ATTENDUS = {f"L{i}" for i in besoins.index} | set(lignes_reserves["id_ligne"])


# =====================================================================================================
# Charge des usines (utilisée par C10 et par le lissage)
# =====================================================================================================
def case(date):
    # (n° de semaine dans l'horizon, jour de la semaine) d'une date
    return SEMAINES.index(date.isocalendar().week), date.day_of_week


def charge_depuis_camions(camions, plant):
    # Camions reçus par une usine : une ligne par semaine, une colonne par jour (lundi -> vendredi)
    charge = np.zeros((NB_SEMAINES, 5))
    for d in camions.loc[camions["plant"] == plant, "date"]:
        if d.isocalendar().week in SEMAINES and d.day_of_week < 5:
            charge[case(d)] += 1
    return charge


def charges_camions(camions):
    return {plant: charge_depuis_camions(camions, plant) for plant in USINES}


def ecart(charge_jours):
    # Écart du jour le plus éloigné de la moyenne, en % de la moyenne (0.35 = 35 %)
    charge_jours = np.asarray(charge_jours, dtype=float)
    moyenne = charge_jours.mean()
    return 0.0 if moyenne == 0 else float(np.abs(charge_jours - moyenne).max() / moyenne)


def hors_tolerance(charge_semaines, seuil=None):
    # C10 pour chaque semaine : un jour s'écarte-t-il de la moyenne de plus du seuil (et d'au moins 1 camion) ?
    seuil = SEUIL_LISSAGE if seuil is None else seuil
    moyenne = charge_semaines.mean(axis=1, keepdims=True)
    tolerance = np.maximum(seuil * moyenne, 1.0)
    depasse = (np.abs(charge_semaines - moyenne) > tolerance + 1e-9).any(axis=1)
    return depasse & (charge_semaines.sum(axis=1) >= MIN_CAMIONS_SEMAINE)


def nb_hors_tolerance(camions):
    return sum(int(hors_tolerance(charge[CONTROLE]).sum()) for charge in charges_camions(camions).values())


# =====================================================================================================
# Vérification des contraintes
# Chaque fonction retourne les cas qui violent la contrainte (table vide = contrainte respectée).
# =====================================================================================================
def optimises(planning):
    # Camions construits par le moteur (sans les camions réservés de la quarantaine)
    return planning[~planning["reserve"]]


def c1_poids(planning, lignes):
    p = optimises(planning)
    return p[p["poids"] > POIDS_MAX + 1e-6]


def c2_volume(planning, lignes):
    return planning[planning["volume"] > VOLUME_MAX + 1e-6]


def c3_exhaustivite(planning, lignes, ids_attendus):
    # Lignes sans camion, livrées deux fois, ou absentes
    sans_camion = lignes[lignes["camion_id"].isna()].assign(probleme="sans camion")
    doublons = lignes[lignes["id_ligne"].duplicated(keep=False)].assign(probleme="livrée plusieurs fois")
    absentes = pd.DataFrame({"id_ligne": sorted(set(ids_attendus) - set(lignes["id_ligne"])), "probleme": "absente"})
    inconnues = lignes[~lignes["id_ligne"].isin(ids_attendus)].assign(probleme="ligne inconnue")
    return pd.concat([sans_camion, doublons, absentes, inconnues], ignore_index=True)


def c4_un_couple(planning, lignes):
    nb_couples = lignes.groupby("camion_id")[["plant", "supplier_id"]].nunique().max(axis=1)
    return nb_couples[nb_couples > 1].rename("couples").reset_index()


def c5_retard(planning, lignes):
    return lignes[lignes["date_livraison"] > lignes["need_date"]]


def c6_avance(planning, lignes):
    return lignes[lignes["need_date"] - lignes["date_livraison"] > FENETRE]


def c7_jours_ouvres(planning, lignes):
    d = planning["date"]
    return planning[(d.dt.day_of_week >= 5) | (d < DEBUT) | (d > FIN)]


def c8_jours_fixes(planning, lignes):
    p = optimises(planning)
    mauvais_profil = ~p["profil"].map(len).between(1, JOURS_FIXES_MAX)
    hors_profil = np.array([not dem and d.day_of_week not in prof
                            for d, prof, dem in zip(p["date"], p["profil"], p["demarrage"])], dtype=bool)
    return p[mauvais_profil | hors_profil]


def c9_un_camion_par_jour(planning, lignes):
    # Jours où un couple a 2 camions ou plus. 'justifie' = le besoin d'un seul jour du couple dépasse
    # 24,5 t : 2 camions sont alors inévitables
    par_jour = optimises(planning).groupby(["plant", "supplier_id", "date"]).size()
    trop = par_jour[par_jour > 1].rename("camions").reset_index()
    besoin_jour = lignes.dropna(subset=["weight"]).groupby(["plant", "supplier_id", "need_date"])["weight"].sum()
    impossibles = set(besoin_jour[besoin_jour > POIDS_MAX].index.droplevel("need_date"))
    trop["justifie"] = [(p, s) in impossibles for p, s in zip(trop["plant"], trop["supplier_id"])]
    return trop


def c10_lissage(planning, lignes):
    # Semaines hors tolérance, par usine (tous les camions reçus, démarrage et réservés compris)
    lignes_hors = []
    for plant, charge in charges_camions(planning).items():
        hors = hors_tolerance(charge)
        for w in CONTROLE:
            if hors[w]:
                lignes_hors.append({"plant": plant, "semaine": SEMAINES[w], "ecart": ecart(charge[w]),
                                    "camions_par_jour": charge[w].astype(int).tolist()})
    return pd.DataFrame(lignes_hors)


CONTRAINTES = [
    ("C1", "Poids ≤ 24,5 t", "dure", c1_poids),
    ("C2", "Volume ≤ 110,4 m³", "dure", c2_volume),
    ("C3", "Chaque ligne livrée une fois, entière", "dure", c3_exhaustivite),
    ("C4", "Un seul couple par camion", "dure", c4_un_couple),
    ("C5", "Jamais de retard", "dure", c5_retard),
    ("C6", "Au plus 7 jours d'avance", "dure", c6_avance),
    ("C7", "Jour ouvré, dans l'horizon", "dure", c7_jours_ouvres),
    ("C8", "Jours fixes (1 ou 2 par couple)", "dure", c8_jours_fixes),
    ("C9", "Au plus 1 camion par couple et par jour", "dure", c9_un_camion_par_jour),
    ("C10", "Lissage (écart ≤ 35 %)", "souple", c10_lissage),
]


def verifier_contraintes(planning, lignes, ids_attendus):
    # Tableau de synthèse : nombre de violations de chaque contrainte
    resultats = []
    for code_c, nom, type_c, fonction in CONTRAINTES:
        args = (planning, lignes, ids_attendus) if fonction is c3_exhaustivite else (planning, lignes)
        violations = fonction(*args)
        remarque = ""
        if fonction is c9_un_camion_par_jour:
            remarque = f"{int(violations['justifie'].sum())} cas inévitables (besoin d'un jour > 24,5 t)"
            violations = violations[~violations["justifie"]]
        if fonction is c10_lissage:
            remarque = f"sur {len(USINES) * len(CONTROLE)} semaines contrôlées"
        nb = len(violations)
        statut = "respectée" if nb == 0 else ("violée" if type_c == "dure" else f"{nb} semaine(s) hors tolérance")
        resultats.append({"Contrainte": code_c, "Description": nom, "Type": type_c, "Violations": nb,
                          "Statut": statut, "Remarque": remarque})
    return pd.DataFrame(resultats).set_index("Contrainte")


def valider_resultats(planning, lignes):
    # Cohérence du planning final : contenu des camions, poids livré, coût
    opti, lignes_opti = optimises(planning), lignes[~lignes["reserve"]]
    contenu = lignes_opti.groupby("camion_id").agg(poids=("weight", "sum"), volume=("volume", "sum"), nb=("weight", "size"))
    p = opti.set_index("camion_id")
    controles = {
        "Chaque camion optimisé contient au moins une ligne": opti["camion_id"].isin(contenu.index).all(),
        "Poids de chaque camion = somme des poids de ses lignes": np.allclose(p["poids"], contenu.loc[p.index, "poids"]),
        "Volume de chaque camion = somme des volumes de ses lignes": np.allclose(p["volume"], contenu.loc[p.index, "volume"]),
        "Poids total livré = poids total des besoins": np.isclose(lignes_opti["weight"].sum(), besoins["weight"].sum()),
        "Un camion réservé par ligne sans poids": (lignes[lignes["reserve"]].groupby("camion_id").size() == 1).all()
                                                   and planning["reserve"].sum() == NB_RESERVE,
        "Coût de chaque camion = grille tarifaire": np.allclose(
            planning["cout"], [cout_camion(w, s) for w, s in zip(planning["poids"], planning["supplier_id"])]),
        "Coût total = somme des coûts des camions": np.isclose(planning["cout"].sum(), cout_total(planning)),
    }
    return pd.DataFrame({"Contrôle": list(controles),
                         "Résultat": ["OK" if v else "ÉCHEC" for v in controles.values()]}).set_index("Contrôle")


# =====================================================================================================
# Bloc 1 : jours fixes
# =====================================================================================================
PROFILS = [(j,) for j in range(5)] + list(itertools.combinations(range(5), JOURS_FIXES_MAX))
REFERENCE = (0, 1, 2, 3, 4)   # algorithme de base du milestone 2 (sans jours fixes) = livrer les 5 jours


def nom_profil(profil):
    return " + ".join(JOURS[j] for j in profil)


def date_camion(besoin, profil):
    # Dernier jour du profil avant ou égal au besoin ; s'il tombe avant l'horizon -> date du besoin (démarrage)
    date = max(besoin - pd.Timedelta(days=(besoin.day_of_week - j) % 7) for j in profil)
    return (besoin, True) if date < DEBUT else (date, False)


def consolider_couple(lignes, profil):
    # Consolidation d'un couple avec des jours fixes (lignes triées par date, puis poids décroissant)
    restantes = list(lignes.itertuples())
    camions = []
    while restantes:
        date, demarrage = date_camion(restantes[0].need_date, profil)
        poids, volume, contenu, i = 0.0, 0.0, [], 0
        while i < len(restantes):
            ligne = restantes[i]
            if ligne.need_date > date + FENETRE:
                break                                   # hors fenêtre de 7 jours : camion fermé
            if poids + ligne.weight > POIDS_MAX or volume + ligne.volume > VOLUME_MAX:
                i += 1                                  # ne rentre pas : ligne suivante
                continue
            poids, volume = poids + ligne.weight, volume + ligne.volume
            contenu.append(ligne.Index)
            restantes.pop(i)
            i = 0
        camions.append({"date": date, "demarrage": demarrage, "poids": poids, "volume": volume, "lignes": contenu})
    return pd.DataFrame(camions)


# Toutes les options : chaque couple × chaque profil
scenarios = {}
for (plant, supplier), lignes_couple in besoins.groupby(["plant", "supplier_id"]):
    for profil in PROFILS:
        camions = consolider_couple(lignes_couple, profil)
        camions["cout"] = [cout_camion(p, supplier) for p in camions["poids"]]
        scenarios[(plant, supplier, profil)] = camions

camions_algo = pd.concat([consolider_couple(lignes_couple, REFERENCE).assign(plant=plant, supplier_id=supplier)
                          for (plant, supplier), lignes_couple in besoins.groupby(["plant", "supplier_id"])],
                         ignore_index=True)
camions_algo["profil"] = [REFERENCE] * len(camions_algo)
camions_algo["cout"] = [cout_camion(p, s) for p, s in zip(camions_algo["poids"], camions_algo["supplier_id"])]

cout_option = {cle: c["cout"].sum() for cle, c in scenarios.items()}
nb_camions_option = {cle: len(c) for cle, c in scenarios.items()}
charge_option = {(p, s, prof): charge_depuis_camions(c[~c["demarrage"]].assign(plant=p), p)   # hors démarrage
                 for (p, s, prof), c in scenarios.items()}
max_jour = {cle: int(c.groupby("date").size().max()) for cle, c in scenarios.items()}   # camions max un même jour


def autorises(plant, supplier, profils_variante):
    # Profils de la variante qui ne mettent jamais 2 camions le même jour à ce couple (C9).
    # Si aucun ne le permet (besoin d'un seul jour > 24,5 t) : tous les profils de la variante
    ok = [p for p in profils_variante if max_jour[(plant, supplier, p)] <= 1]
    return ok if ok else list(profils_variante)


def choix_moins_cher(profils_variante):
    # Profil le moins cher de chaque couple (à égalité : moins de camions, puis moins de jours)
    choix = {}
    for cle in sorted((k for k in scenarios if k[2] in autorises(k[0], k[1], profils_variante)),
                      key=lambda k: (k[0], k[1], round(cout_option[k], 2), nb_camions_option[k], len(k[2]), k[2])):
        choix.setdefault(cle[:2], cle[2])
    return choix


def cout_choix(choix):
    return sum(cout_option[(p, s, prof)] for (p, s), prof in choix.items())


VARIANTES = {"1 jour fixe": [p for p in PROFILS if len(p) == 1], "1 ou 2 jours fixes": PROFILS}
choix_initiaux = {nom: choix_moins_cher(profils) for nom, profils in VARIANTES.items()}


# =====================================================================================================
# Blocs 2 et 3 : contrôle de l'équilibre et lissage
# =====================================================================================================
CHARGE_RESERVEE = charges_camions(camions_reserves)   # charge fixe, que le lissage ne déplace pas


def charges_choix(choix, fond=None):
    # Charge de chaque usine pour un choix de profils (hors démarrage), avec les camions réservés
    fond = CHARGE_RESERVEE if fond is None else fond
    return {plant: fond[plant] + sum(charge_option[(p, s, prof)] for (p, s), prof in choix.items() if p == plant)
            for plant in USINES}


def dispersion(charge):
    # Somme, sur les semaines contrôlées, des carrés des écarts à la moyenne de la semaine
    charge = charge[CONTROLE]
    return float(((charge - charge.mean(axis=1, keepdims=True)) ** 2).sum())


def lisser_par_couple(choix, plant, profils_variante, seuil=None, fond=None):
    # Change le profil de couples de `plant` jusqu'à ce qu'aucune semaine contrôlée ne soit hors tolérance
    choix = dict(choix)
    charge = charges_choix(choix, fond)[plant]
    journal = []
    while hors_tolerance(charge[CONTROLE], seuil).any():
        dispersion_actuelle, meilleur = dispersion(charge), None
        for (p, s), prof in choix.items():
            if p != plant:
                continue
            for prof2 in autorises(p, s, profils_variante):     # jamais 2 camions le même jour
                if prof2 == prof:
                    continue
                nouvelle = charge - charge_option[(p, s, prof)] + charge_option[(p, s, prof2)]
                gain = dispersion_actuelle - dispersion(nouvelle)
                if gain <= 1e-9:
                    continue
                surcout = cout_option[(p, s, prof2)] - cout_option[(p, s, prof)]
                cle = (max(surcout, 0) / gain, -gain)
                if meilleur is None or cle < meilleur["cle"]:
                    meilleur = {"cle": cle, "supplier_id": s, "de": prof, "vers": prof2, "surcout": surcout,
                                "charge": nouvelle}
        if meilleur is None:
            break                                               # plus aucun changement n'améliore les semaines
        choix[(plant, meilleur["supplier_id"])] = meilleur["vers"]
        charge = meilleur["charge"]
        journal.append({"plant": plant, "supplier_id": meilleur["supplier_id"], "de": nom_profil(meilleur["de"]),
                        "vers": nom_profil(meilleur["vers"]), "surcout": round(meilleur["surcout"], 2),
                        "semaines_hors_tolerance_apres": int(hors_tolerance(charge[CONTROLE], seuil).sum())})
    return choix, journal


def lisser(choix, profils_variante, seuil=None, fond=None):
    # Lisse toutes les usines qui ont au moins une semaine hors tolérance
    choix, journal = dict(choix), []
    for plant in USINES:
        if hors_tolerance(charges_choix(choix, fond)[plant][CONTROLE], seuil).any():
            choix, journal_u = lisser_par_couple(choix, plant, profils_variante, seuil, fond)
            journal += journal_u
    return choix, pd.DataFrame(journal)


choix_lisses, journaux = {}, {}
for nom, profils in VARIANTES.items():
    choix_lisses[nom], journaux[nom] = lisser(choix_initiaux[nom], profils)
PRINCIPALE = min(VARIANTES, key=lambda nom: cout_choix(choix_lisses[nom]))   # la moins chère après lissage


# =====================================================================================================
# Bloc 4 : report et planning final
# =====================================================================================================
def prochain_jour_fixe(date, profil):
    # Premier jour du profil strictement après `date`
    return min(date + pd.Timedelta(days=(j - date.day_of_week - 1) % 7 + 1) for j in profil)


def construire_planning(choix):
    # Camions d'un choix de profils (une ligne par camion, avec la liste de ses lignes)
    return pd.concat([scenarios[(p, s, prof)].assign(plant=p, supplier_id=s, profil=[prof] * len(scenarios[(p, s, prof)]))
                      for (p, s), prof in choix.items()], ignore_index=True)


def reporter_lignes(camions):
    # Report des lignes sur le jour fixe suivant + regroupement des camions d'un même jour, couple par couple,
    # gardé seulement s'il ne coûte rien
    besoin, poids, volume = besoins["need_date"], besoins["weight"], besoins["volume"]

    def charge_ok(ls):
        return poids[ls].sum() <= POIDS_MAX + 1e-9 and volume[ls].sum() <= VOLUME_MAX + 1e-9

    resultat, journal = [], []
    for (plant, supplier), groupe in camions.groupby(["plant", "supplier_id"], sort=False):
        profil = groupe["profil"].iloc[0]

        def cout(ls):
            return cout_camion(poids[ls].sum(), supplier)

        cam = [{"date": r.date, "demarrage": r.demarrage, "lignes": list(r.lignes)}
               for r in groupe.sort_values("date").itertuples()]
        cout_avant, nb_avant, reportees = sum(cout(c["lignes"]) for c in cam), len(cam), 0
        for c in cam:                                               # 1) report vers le jour fixe suivant
            suivant = prochain_jour_fixe(c["date"], profil)
            cibles = [u for u in cam if u["date"] == suivant and not u["demarrage"]]
            for l in sorted((l for l in c["lignes"] if besoin[l] >= suivant), key=lambda l: -poids[l]):
                for u in cibles:
                    if charge_ok(u["lignes"] + [l]):
                        c["lignes"].remove(l)
                        u["lignes"].append(l)
                        reportees += 1
                        break
        for date in sorted({c["date"] for c in cam}):                # 2) regroupement des camions d'un même jour
            du_jour = [c for c in cam if c["date"] == date and c["lignes"]]
            for a, b in itertools.combinations(du_jour, 2):
                if a["lignes"] and b["lignes"] and charge_ok(a["lignes"] + b["lignes"]):
                    a["lignes"] += b["lignes"]
                    b["lignes"] = []
        apres = [c for c in cam if c["lignes"]]
        cout_apres = sum(cout(c["lignes"]) for c in apres)
        garde = cout_apres <= cout_avant + 0.005
        if not garde:
            apres = [{"date": r.date, "demarrage": r.demarrage, "lignes": list(r.lignes)} for r in groupe.itertuples()]
        journal.append({"plant": plant, "supplier_id": supplier, "lignes_reportees": reportees if garde else 0,
                        "camions_en_moins": nb_avant - len(apres),
                        "gain": round(cout_avant - cout_apres, 2) if garde else 0.0,
                        "report_refuse_car_plus_cher": not garde and reportees > 0})
        resultat += [{**c, "plant": plant, "supplier_id": supplier, "profil": profil} for c in apres]
    return pd.DataFrame(resultat), pd.DataFrame(journal)


def finaliser(camions):
    # Planning (une ligne par camion) et contenu (une ligne par ligne de besoin) à partir des camions
    camions = camions.sort_values(["plant", "date", "supplier_id"]).reset_index(drop=True)
    camions["camion_id"] = range(1, len(camions) + 1)
    affectation = camions[["camion_id", "date", "lignes"]].explode("lignes").set_index("lignes")
    lignes = besoins.join(affectation.rename(columns={"date": "date_livraison"}))
    lignes["avance_jours"] = (lignes["need_date"] - lignes["date_livraison"]).dt.days
    lignes.insert(0, "id_ligne", "L" + lignes.index.astype(str))
    contenu = lignes.groupby("camion_id").agg(poids=("weight", "sum"), volume=("volume", "sum"),
                                              nb_lignes=("weight", "size"))
    planning = camions.drop(columns=[c for c in ["lignes", "poids", "volume", "cout"] if c in camions]).join(contenu, on="camion_id")
    planning["cout"] = [cout_camion(p, s) for p, s in zip(planning["poids"], planning["supplier_id"])]
    planning["jours_fixes"] = planning["profil"].map(nom_profil)
    planning["reserve"] = False
    return planning, lignes


# Planning de chaque étape (pour le bilan)
plannings = {}
for nom in VARIANTES:
    plannings[nom] = finaliser(construire_planning(choix_initiaux[nom]))
    plannings[f"{nom} + lissage"] = finaliser(construire_planning(choix_lisses[nom]))
camions_report, journal_report = reporter_lignes(construire_planning(choix_lisses[PRINCIPALE]))
plannings[f"{PRINCIPALE} + lissage + report"] = finaliser(camions_report)
planning, lignes_planning = plannings[f"{PRINCIPALE} + lissage + report"]

# Planning complet : camions optimisés + camions réservés (numérotés à la suite)
decalage = int(planning["camion_id"].max())
reserves = camions_reserves.assign(camion_id=camions_reserves["numero"] + decalage, reserve=True, profil=None,
                                   jours_fixes="réservé : " + camions_reserves["motif"])
planning_complet = (pd.concat([planning, reserves.drop(columns=["numero", "motif"])], ignore_index=True)
                    .sort_values(["plant", "date", "supplier_id"]).reset_index(drop=True))
planning_complet["jour"] = planning_complet["date"].dt.day_of_week.map(dict(enumerate(JOURS)))
planning_complet["semaine"] = planning_complet["date"].dt.isocalendar().week
lignes_complet = pd.concat([lignes_planning.assign(reserve=False),
                            lignes_reserves.assign(camion_id=lignes_reserves["numero"] + decalage, reserve=True)
                            .drop(columns="numero")], ignore_index=True)


# =====================================================================================================
# Validation
# =====================================================================================================
controle_contraintes = verifier_contraintes(planning_complet, lignes_complet, IDS_ATTENDUS)
validation = valider_resultats(planning_complet, lignes_complet)
assert (validation["Résultat"] == "OK").all(), "le planning final est incohérent"
assert (controle_contraintes.loc[controle_contraintes["Type"] == "dure", "Violations"] == 0).all(), \
    "une contrainte dure est violée"


# =====================================================================================================
# Tableau des économies
# =====================================================================================================
versions = {"Baseline": (camions_base, None), "Algorithme de base (sans jours fixes)": finaliser(camions_algo)}
versions.update(plannings)
COUT_BASELINE_TOTAL = COUT_BASELINE + COUT_RESERVE
COL_HORS = f"Semaines hors tolérance (sur {len(USINES) * len(CONTROLE)})"
bilan = pd.DataFrame([{
    "Version": nom,
    "Camions": len(c) + NB_RESERVE,
    "Coût": c["cout"].sum() + COUT_RESERVE,
    "Économie vs baseline": COUT_BASELINE - c["cout"].sum(),
    "Économie (%)": (COUT_BASELINE - c["cout"].sum()) / COUT_BASELINE_TOTAL,
    "Avance moyenne (j)": np.nan if l is None else l["avance_jours"].mean(),
    COL_HORS: nb_hors_tolerance(avec_reserves(c)),
} for nom, (c, l) in versions.items()])

# Économies par usine (camions réservés compris)
base_u = avec_reserves(camions_base).groupby("plant").agg(camions_baseline=("cout", "size"), cout_baseline=("cout", "sum"))
final_u = planning_complet.groupby("plant").agg(camions_final=("cout", "size"), cout_final=("cout", "sum"))
par_usine = base_u.join(final_u)
par_usine.loc["Total"] = par_usine.sum()
par_usine["economie"] = par_usine["cout_baseline"] - par_usine["cout_final"]
par_usine["economie_pct"] = par_usine["economie"] / par_usine["cout_baseline"]


# =====================================================================================================
# Sortie 1 : le profil à appliquer pour chaque couple
# =====================================================================================================
distance_brute = distances.where(~distances.index.isin(SANS_DISTANCE))   # NaN = distance inconnue


def moyennes_par_semaine(camions):
    # Par couple, sur les semaines où il est livré : jours de livraison et camions par semaine (moyennes)
    par_sem = camions.assign(semaine=camions["date"].dt.isocalendar().week).groupby(["plant", "supplier_id", "semaine"])
    jours = par_sem["date"].nunique().groupby(["plant", "supplier_id"]).mean()
    nb_camions = par_sem.size().groupby(["plant", "supplier_id"]).mean()
    return jours, nb_camions


livraisons_actuelles, _ = moyennes_par_semaine(camions_base)
_, camions_semaine = moyennes_par_semaine(planning)
par_couple = planning.groupby(["plant", "supplier_id"])
sortie1 = pd.DataFrame({
    "frequence_cible": par_couple["profil"].first().map(len),
    "jours": par_couple["jours_fixes"].first(),
    "camions_semaine": camions_semaine.round(2),
    "remplissage_poids": (par_couple["poids"].mean() / POIDS_MAX).round(4),
}).reset_index()
sortie1.insert(2, "distance_km", sortie1["supplier_id"].map(distance_brute))
sortie1.insert(3, "livraisons_semaine_actuelles",
               [round(livraisons_actuelles.get((p, s), 0), 2) for p, s in zip(sortie1["plant"], sortie1["supplier_id"])])
sortie1 = sortie1.rename(columns={"supplier_id": "fournisseur", "plant": "usine"})[
    ["fournisseur", "usine", "distance_km", "livraisons_semaine_actuelles", "frequence_cible", "jours",
     "camions_semaine", "remplissage_poids"]].sort_values(["usine", "fournisseur"]).reset_index(drop=True)
assert sortie1[["fournisseur", "usine"]].duplicated().sum() == 0      # un profil par couple
assert len(sortie1) == besoins.groupby(["plant", "supplier_id"]).ngroups


# =====================================================================================================
# Sortie 2 : les materials regroupés dans chaque camion
# =====================================================================================================
sortie2 = (lignes_complet
           .groupby(["camion_id", "plant", "supplier_id", "date_livraison", "material", "unloading_point"])
           .agg(besoins=("need_date", lambda d: ", ".join(sorted(d.dt.strftime("%Y-%m-%d").unique()))),
                nb_lignes=("need_date", "size"), quantite=("schedule_quantity", "sum"),
                poids_kg=("weight", lambda w: w.sum(min_count=1)), reserve=("reserve", "first"))
           .reset_index()
           .rename(columns={"plant": "usine", "supplier_id": "fournisseur", "unloading_point": "quai"}))
sortie2.insert(4, "jour", sortie2["date_livraison"].dt.day_of_week.map(dict(enumerate(JOURS))))
sortie2["poids_kg"] = sortie2["poids_kg"].round(1)
sortie2 = sortie2.sort_values(["camion_id", "poids_kg", "material"], ascending=[True, False, True]).reset_index(drop=True)
assert sortie2["nb_lignes"].sum() == len(IDS_ATTENDUS)                  # toutes les lignes de besoin
assert sortie2["camion_id"].nunique() == len(planning_complet)          # tous les camions

NB_AFFICHES = 10
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
        "décembre"]


def poids_camion(contenu):
    # Poids total d'un camion et remplissage ; camion réservé : poids inconnu
    poids = contenu["poids_kg"].sum(min_count=1)
    if pd.isna(poids):
        return "poids inconnu (camion réservé)"
    return f"{nombre(round(poids))} kg (remplissage poids {pourcent(poids / POIDS_MAX)})"


def detail_camion(camion_id, nb_affiches=NB_AFFICHES):
    # Materials d'un camion : les plus lourds, puis "N autres materials" ; retourne (résumé, tableau en texte)
    contenu = sortie2[sortie2["camion_id"] == camion_id]
    dates = pd.to_datetime([d for b in contenu["besoins"] for d in b.split(", ")])
    un_mois = dates.month.nunique() == 1

    def jours_besoin(b):
        return ", ".join(str(pd.Timestamp(d).day) if un_mois else pd.Timestamp(d).strftime("%d/%m")
                         for d in b.split(", "))

    table = (contenu.head(nb_affiches)[["material", "quai", "besoins", "quantite", "poids_kg"]]
             .assign(besoins=lambda t: t["besoins"].map(jours_besoin)).reset_index(drop=True))
    reste = contenu.iloc[nb_affiches:]
    if len(reste):
        table.loc[len(table)] = [f"{len(reste)} autres materials", "", "", reste["quantite"].sum(), reste["poids_kg"].sum()]
    camion = contenu.iloc[0]
    resume = (f"Camion n° {camion_id} : {camion['fournisseur']} -> {camion['usine']}, {camion['jour'].lower()} "
              f"{camion['date_livraison']:%d/%m}, {len(contenu)} materials, "
              f"{contenu['nb_lignes'].sum()} lignes de besoin, {poids_camion(contenu)}")
    titre_besoins = f"Besoins regroupés (jours de {MOIS[dates[0].month - 1]})" if un_mois else "Besoins regroupés"
    table = table.rename(columns={"material": "Material", "quai": "Quai", "besoins": titre_besoins,
                                  "quantite": "Quantité", "poids_kg": "Poids (kg)"})
    return resume, table.to_string(index=False, formatters={"Quantité": nombre,
                                                            "Poids (kg)": lambda p: nombre(round(p))}, na_rep="–")


def main():
    # Export des sorties et affichage : seulement quand le script est lancé (python main.py),
    # pas quand il est importé (par exemple par les tests du milestone 4)
    # =====================================================================================================
    # Export
    # =====================================================================================================
    SORTIE.mkdir(parents=True, exist_ok=True)
    fichiers = {"sortie1_profils.csv": sortie1, "sortie2_camions.csv": sortie2,
                "bilan.csv": bilan.round({"Coût": 2, "Économie vs baseline": 2, "Économie (%)": 4, "Avance moyenne (j)": 2})}
    for nom_fichier, table in fichiers.items():
        table.to_csv(SORTIE / nom_fichier, index=False, date_format="%Y-%m-%d")


    # =====================================================================================================
    # Affichage
    # =====================================================================================================
    print(f"Besoins à consolider : {len(besoins)} lignes, {besoins.groupby(['plant', 'supplier_id']).ngroups} couples, "
          f"{len(USINES)} usines, du {DEBUT:%d/%m} au {FIN:%d/%m}")
    print(f"Camions réservés (lignes sans poids) : {NB_RESERVE}, {eur(COUT_RESERVE)}")
    print(f"Variante retenue : {PRINCIPALE} ({len(journaux[PRINCIPALE])} changements de profil au lissage)")
    print(f"Report : {journal_report['lignes_reportees'].sum()} lignes reportées sur le jour fixe suivant, "
          f"gain {eur(journal_report['gain'].sum())}")

    print("\n=== Contraintes ===")
    print(controle_contraintes.drop(columns="Description").to_string())

    print("\n=== Économies (camions réservés compris) ===")
    print(bilan.to_string(index=False, na_rep="–", formatters={
        "Coût": eur, "Économie vs baseline": eur, "Économie (%)": pourcent, "Avance moyenne (j)": nombre}))

    print("\n=== Économies par usine ===")
    print(par_usine.to_string(formatters={
        "camions_baseline": "{:.0f}".format, "camions_final": "{:.0f}".format, "cout_baseline": eur,
        "cout_final": eur, "economie": eur, "economie_pct": pourcent}))

    print(f"\n=== Sortie 1 : le profil à appliquer pour chaque couple ({len(sortie1)} couples, aperçu des 10 premiers) ===")
    print(sortie1.head(10).rename(columns={
        "fournisseur": "Fournisseur", "usine": "Usine", "distance_km": "Distance",
        "livraisons_semaine_actuelles": "Livraisons / sem. actuelles", "frequence_cible": "Fréquence cible", "jours": "Jour",
        "camions_semaine": "Camions / sem.", "remplissage_poids": "Remplissage poids"})
        .to_string(index=False, formatters={
            "Distance": lambda d: "inconnue" if pd.isna(d) else f"{d:.0f} km", "Livraisons / sem. actuelles": nombre,
            "Fréquence cible": "{} / semaine".format, "Camions / sem.": nombre, "Remplissage poids": pourcent}))

    camion_detail = (int(sys.argv[1]) if len(sys.argv) > 1
                     else int(planning_complet.loc[planning_complet["nb_lignes"].idxmax(), "camion_id"]))
    assert camion_detail in set(sortie2["camion_id"]), f"camion {camion_detail} inconnu (1 à {sortie2['camion_id'].max()})"
    resume, table_camion = detail_camion(camion_detail)
    print(f"\n=== Sortie 2 : les materials regroupés dans chaque camion ({sortie2['camion_id'].nunique()} camions) ===")
    print(resume)
    print(table_camion)

    print(f"\nFichiers écrits dans {SORTIE} :")
    for nom_fichier, table in fichiers.items():
        print(f"  {nom_fichier:<22}: {len(table)} lignes")


if __name__ == "__main__":
    main()
