@echo off
rem Lance le dashboard Streamlit du moteur de consolidation (double-clic ou "lancer_dashboard.bat").
rem Utilise l'environnement .venv s'il existe, sinon le Python du système.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)
"%PY%" -m streamlit --version >nul 2>&1 || (
    echo Installation des dependances...
    "%PY%" -m pip install -r requirements.txt || exit /b 1
)
"%PY%" -m streamlit run frontend\app.py %*
