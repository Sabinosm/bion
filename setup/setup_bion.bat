@echo off
setlocal enabledelayedexpansion

REM =========================================================
REM setup_bion.bat
REM
REM 1. Clona os dois repositorios do GitHub.
REM 2. Cria um .env com valores padrao/gerados.
REM 3. Cria um .venv dentro de bion/ e instala requirements.txt.
REM 4. Copia o create_database.sql para a raiz do projeto,
REM    pronto para voce importar manualmente no seu MySQL/MariaDB.
REM
REM Uso:
REM     setup_bion.bat
REM     setup_bion.bat "C:\meus_projetos"
REM =========================================================

set "DEST=%~1"
if "%DEST%"=="" set "DEST=%CD%"

echo == Pasta de destino: %DEST% ==
if not exist "%DEST%" mkdir "%DEST%"
cd /d "%DEST%"

REM --- checa se git existe ---
where git >nul 2>nul
if errorlevel 1 (
    echo ERRO: git nao encontrado no PATH. Instale o git e rode de novo.
    exit /b 1
)

REM --- 1. Clonar repositorios ---
echo.
echo == Clonando repositorios ==

if exist "%DEST%\bion" (
    echo [skip] bion ja existe, nao vou clonar de novo.
) else (
    git clone https://github.com/Sabinosm/bion.git "%DEST%\bion"
    if errorlevel 1 echo [ERRO] Falha ao clonar bion. Repositorio pode ser privado.
)

if exist "%DEST%\sabinosm.github.io" (
    echo [skip] sabinosm.github.io ja existe, nao vou clonar de novo.
) else (
    git clone https://github.com/Sabinosm/sabinosm.github.io.git "%DEST%\sabinosm.github.io"
    if errorlevel 1 echo [ERRO] Falha ao clonar sabinosm.github.io. Repositorio pode ser privado.
)

REM --- 2. Criar .env ---
echo.
echo == Criando .env ==

set "ENV_FILE=%DEST%\.env"

if exist "%ENV_FILE%" (
    copy /y "%ENV_FILE%" "%DEST%\.env.bak" >nul
    echo [aviso] .env ja existia, backup salvo em .env.bak
)

REM gera chaves aleatorias via PowerShell (32 bytes em hex)
for /f %%A in ('powershell -NoProfile -Command "-join ((1..32) | ForEach-Object { \"{0:x2}\" -f (Get-Random -Maximum 256) })"') do set "SECRET_KEY=%%A"
for /f %%A in ('powershell -NoProfile -Command "-join ((1..32) | ForEach-Object { \"{0:x2}\" -f (Get-Random -Maximum 256) })"') do set "AES_KEY=%%A"
for /f %%A in ('powershell -NoProfile -Command "-join ((1..32) | ForEach-Object { \"{0:x2}\" -f (Get-Random -Maximum 256) })"') do set "HMAC_KEY=%%A"

(
    echo FLASK_ENV=development
    echo SECRET_KEY=%SECRET_KEY%
    echo DB_USER=root
    echo DB_PASSWORD=
    echo DB_HOST=localhost
    echo DB_PORT=3306
    echo DB_NAME=testes
    echo AES_KEY=%AES_KEY%
    echo HMAC_KEY=%HMAC_KEY%
) > "%ENV_FILE%"

echo [ok] .env criado em %ENV_FILE%
echo      -^> DB_USER/DB_PASSWORD/DB_HOST/DB_PORT/DB_NAME sao placeholders.
echo      Ajuste manualmente se for apontar para um MySQL real.

REM --- 3. Criar .venv e instalar dependencias ---
echo.
echo == Criando .venv e instalando dependencias ==

set "BION_DIR=%DEST%\bion"
set "REQ_FILE=%BION_DIR%\requirements.txt"
set "VENV_DIR=%BION_DIR%\.venv"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERRO] python nao encontrado no PATH. Pulando criacao do .venv.
    goto :sql_step
)

if not exist "%BION_DIR%" (
    echo [aviso] pasta bion nao encontrada. Pulando .venv.
    goto :sql_step
)

if not exist "%REQ_FILE%" (
    echo [aviso] requirements.txt nao encontrado em %BION_DIR%. Pulando .venv.
    goto :sql_step
)

if exist "%VENV_DIR%" (
    echo [skip] .venv ja existe em %VENV_DIR%, nao vou recriar.
) else (
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERRO] Falha ao criar o .venv.
        goto :sql_step
    )
)

"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip
"%VENV_DIR%\Scripts\pip.exe" install -r "%REQ_FILE%"
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias. O .venv foi criado, mas
    echo        voce vai precisar rodar o pip install manualmente.
) else (
    echo [ok] .venv criado e dependencias instaladas em %VENV_DIR%
    echo      -^> para ativar: %VENV_DIR%\Scripts\activate
)

:sql_step
REM --- 4. Copiar o .sql pronto ---
echo.
echo == Preparando o schema SQL ==

set "SQL_SRC=%DEST%\bion\database\create_database.sql"
set "SQL_DEST=%DEST%\create_database.sql"

if exist "%SQL_SRC%" (
    copy /y "%SQL_SRC%" "%SQL_DEST%" >nul
    echo [ok] Schema copiado para %SQL_DEST%
    echo      -^> Importe manualmente no seu MySQL/MariaDB, por exemplo:
    echo         mysql -u root -p ^< "%SQL_DEST%"
) else (
    echo [aviso] Nao encontrei %SQL_SRC%
    echo         Confira se o repositorio bion foi clonado corretamente
    echo         ou informe o caminho certo do .sql manualmente.
)

echo.
echo Concluido.
endlocal