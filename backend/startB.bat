@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creation de l'environnement virtuel .venv...
    python -m venv .venv
)

call ".venv\Scripts\activate.bat"

python -c "import uvicorn" 2>nul
if errorlevel 1 (
    echo Installation des dependances...
    pip install -r requirements.txt
    python -c "import uvicorn" 2>nul
    if errorlevel 1 (
        pip install "uvicorn[standard]"
    )
)

echo Lancement du serveur FastAPI...
python -m uvicorn app.main:app --reload
pause