"""Point d'entrée du dashboard : ``streamlit run frontend/app.py`` (depuis la racine du dépôt)."""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:          # pour importer main.py, backend/ et frontend/
    sys.path.insert(0, str(RACINE))

import streamlit as st  # noqa: E402

from frontend.style import appliquer_style  # noqa: E402

st.set_page_config(page_title="Consolidation des livraisons", page_icon=":material/local_shipping:", layout="wide")
appliquer_style()

# Streamlit efface l'état des widgets d'une page quand on en affiche une autre ; ré-écrire leur clé à chaque
# exécution les garde (choix de l'origine du schedule, séparateur) d'une page à l'autre.
for cle, defaut in (("origine", "Importer un CSV"), ("separateur", ",")):
    st.session_state[cle] = st.session_state.get(cle, defaut)

DOSSIER_VUES = Path(__file__).resolve().parent / "vues"
page = st.navigation(
    [
        st.Page(DOSSIER_VUES / "analyse.py", title="Analyse", icon=":material/bolt:", default=True),
        st.Page(DOSSIER_VUES / "historique.py", title="Historique", icon=":material/monitoring:"),
    ],
    position="top",
)
page.run()
