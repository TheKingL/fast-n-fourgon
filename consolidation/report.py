"""Bloc 4 : report des lignes sur le jour fixe suivant, puis planning final (camions optimisés + camions réservés)."""
import itertools

import pandas as pd

from .config import JOURS, POIDS_MAX, VOLUME_MAX
from .couts import cout_camion
from .donnees import besoins, camions_reserves, lignes_reserves
from .jours_fixes import nom_profil


def prochain_jour_fixe(date, profil):
    # Premier jour du profil strictement après `date`
    return min(date + pd.Timedelta(days=(j - date.day_of_week - 1) % 7 + 1) for j in profil)


def construire_planning(scenarios, choix):
    # Camions d'un choix de profils (une ligne par camion, avec la liste de ses lignes)
    return pd.concat([scenarios.camions[(p, s, prof)].assign(plant=p, supplier_id=s,
                                                             profil=[prof] * len(scenarios.camions[(p, s, prof)]))
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


def ajouter_reserves(planning, lignes_planning):
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
    return planning_complet, lignes_complet
