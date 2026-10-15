@echo off
setlocal

rem Sempre trabalhar a partir da pasta onde este .bat esta salvo
cd /d "%~dp0"

echo ============================================
echo  Sistema de Analise Historica do ENEM
echo ============================================
echo.

rem 1) Verifica se existe uma venv. Se nao existir, cria uma nova.
if not exist "venv\Scripts\python.exe" (
    echo [1/3] Nenhum ambiente virtual encontrado. Criando um novo...
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo ERRO: nao foi possivel criar o ambiente virtual.
        echo Verifique se o Python esta instalado e disponivel no PATH.
        pause
        exit /b 1
    )
) else (
    echo [1/3] Ambiente virtual encontrado.
)

echo.
echo [2/3] Instalando/atualizando dependencias (pode demorar um pouco na primeira vez)...
"venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
"venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERRO ao instalar as dependencias. Veja a mensagem acima.
    pause
    exit /b 1
)

rem 2) Verifica se o arquivo .env existe (precisa da senha do Supabase)
if not exist ".env" (
    echo.
    echo AVISO: arquivo .env nao encontrado. Copiando .env.example, se existir...
    if exist ".env.example" copy ".env.example" ".env" >nul
)

echo.
echo [3/3] Iniciando o servidor...
echo A pagina vai abrir automaticamente em alguns segundos.
echo Para PARAR o sistema, feche esta janela ou pressione Ctrl+C.
echo.

rem Abre o navegador em segundo plano, depois de dar tempo do servidor subir
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000/docs"

rem Sobe o servidor (essa janela fica mostrando os logs)
"venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo Servidor encerrado.
pause
