"""Smoke test du dashboard dans l'image Docker, lancé par le CI avant de publier l'image (pas un test pytest).

Avec AppTest (Streamlit), sans navigateur : page Analyse sur le schedule du projet, lancement du moteur, exports Excel
et CSV, enregistrement du run dans l'historique (data/historique).

    docker run --rm -v "${PWD}/tests/smoke_image.py:/smoke.py:ro" fast-n-fourgon python /smoke.py
"""
import io
import sys
import zipfile
from pathlib import Path

from streamlit.testing.v1 import AppTest

RACINE = Path("/app")
sys.path.insert(0, str(RACINE))

from frontend import export  # import après sys.path : le code de l'application est dans /app

app = AppTest.from_file(str(RACINE / "frontend" / "app.py"), default_timeout=180)
app.session_state["origine"] = "Projet"
app.run()
assert not app.exception, f"page Analyse : {app.exception}"

app.button(key="lancer_lateral").click().run()
assert not app.exception, f"lancement du moteur : {app.exception}"
r = app.session_state["analyse"]["resultats"]
print(f"moteur : {len(r.planning_complet)} camions, variante {r.principale}")

classeur = export.classeur_excel(r, list(export.LIVRABLES))
fichiers = zipfile.ZipFile(io.BytesIO(export.archive_csv(r, list(export.LIVRABLES), excel_fr=True))).namelist()
assert classeur[:2] == b"PK", "classeur Excel illisible"
assert {"sortie1_profils.csv", "sortie2_camions.csv", "sortie3_savings.csv"} <= set(fichiers), fichiers
print(f"exports : classeur Excel {len(classeur) // 1024} Ko, archive CSV {sorted(fichiers)}")

next(b for b in app.button if b.label == "Enregistrer dans l'historique").click().run()
assert not app.exception, f"enregistrement : {app.exception}"
run_id = app.session_state["analyse"]["run_id"]
assert run_id and (RACINE / "data" / "historique" / "runs" / run_id).is_dir(), "run absent de data/historique"
print(f"historique : run {run_id} enregistré")
print("smoke test OK")
