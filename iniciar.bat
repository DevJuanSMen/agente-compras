@echo off
REM Agente de Compras UPARSISTEM v1.0 - arranque en Windows
cd /d "%~dp0"
if not exist frontend\dist\index.html (
  echo Compilando la interfaz...
  pushd frontend
  call npm install
  call npm run build
  popd
)
echo Abriendo http://localhost:8000
start "" http://localhost:8000
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
