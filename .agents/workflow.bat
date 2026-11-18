@echo off
setlocal EnableDelayedExpansion
chcp 65001 > nul

title Antigravity Workflow - Plataforma Tributaria (Python + SQLite)

echo ============================================================================
echo   WORKFLOW DE VALIDACAO - PLATAFORMA TRIBUTARIA (11 BLOCOS / SQLITE)
echo ============================================================================
echo.

:: 1. Verificacao das Skills e Agentes no workspace Antigravity
echo [1/6] Verificando Skills e Agentes...
set "MISSING=0"
for %%S in (sqlite_fiscal_schema fiscal_math_engine nfe_and_erp_auditor linx_microvix_sync official_law_scraper fiscal_qa_validator streamlit_fiscal_ui) do (
    if not exist ".agents\skills\%%S\SKILL.md" (
        echo   [ERRO] Skill ausente: .agents\skills\%%S\SKILL.md
        set "MISSING=1"
    ) else (
        echo   [OK] Skill ativa: %%S
    )
)

for %%A in (agent_tax_auditor.md agent_db_architect.md agent_law_guard.md agent_linx_integrator.md) do (
    if not exist ".agents\agents\%%A" (
        echo   [ERRO] Agente ausente: .agents\agents\%%A
        set "MISSING=1"
    ) else (
        echo   [OK] Agente ativo: %%A
    )
)

if "!MISSING!"=="1" (
    echo.
    echo [FALHA] Crie os arquivos ausentes acima antes de continuar.
    exit /b 1
)
echo.

:: 2. Verificacao do Ambiente Virtual Python
echo [2/6] Verificando ambiente Python...
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo   [OK] Virtualenv .venv ativado.
) else (
    echo   [AVISO] .venv nao encontrado, usando Python global.
)
python --version > nul 2>&1
if !errorlevel! neq 0 (
    echo   [ERRO] Python nao encontrado no PATH.
    exit /b 1
)
echo.

:: 3. Validacao do schema.sql no SQLite (Dry-run em memoria + checagem WAL)
echo [3/6] Validando schema.sql no SQLite...
if exist "schema.sql" (
    python -c "import sqlite3; conn = sqlite3.connect(':memory:'); conn.executescript(open('schema.sql', encoding='utf-8').read()); print('  [OK] schema.sql validado com sucesso no SQLite!')"
    if !errorlevel! neq 0 (
        echo   [ERRO] Falha de sintaxe ou integridade no schema.sql!
        exit /b 1
    )
) else (
    echo   [AVISO] schema.sql nao encontrado na raiz.
)
echo.

:: 4. Auditoria Estatica de Seguranca (Guardrails)
echo [4/6] Executando Guardrails estaticos no codigo Python...
if exist "src" (
    findstr /S /I /C:"TRUNCATE" src\*.py src\*.sql > nul 2>&1
    if !errorlevel!==0 (
        echo   [BLOQUEIO] Encontrado TRUNCATE no codigo! Use UPSERT - ON CONFLICT DO UPDATE.
        exit /b 1
    )
    echo   [OK] Guardrail Anti-TRUNCATE aprovado.
) else (
    echo   [INFO] Pasta src\ ainda nao criada.
)
echo.

:: 5. Execucao dos Testes Unitarios (Pytest)
echo [5/6] Executando suite Pytest (Calculos 11 Blocos, DIFAL, ST, FCI, URLs Oficiais)...
if exist "tests" (
    python -m pytest -v
    if !errorlevel! neq 0 (
        echo   [FALHA] Testes unitarios falharam! Revise o motor tributario.
        exit /b 1
    )
) else (
    echo   [INFO] Pasta tests\ ainda nao criada.
)
echo.

:: 6. Instrucoes de uso dos Agentes no Antigravity
echo [6/6] Ambiente validado! Utilize os agentes abaixo no chat do Antigravity:
echo   - @agent_db_architect     -> Auditar schema.sql, indices SQLite WAL e historico
echo   - @agent_tax_auditor      -> Auditar motor Python (11 blocos, DIFAL, ST, IBS/CBS)
echo   - @agent_law_guard        -> Auditar scrapers .gov.br, recortes e Vigia Noturno
echo   - @agent_linx_integrator  -> Auditar Web Service Linx, XML NF-e e matriz ERP

:: Atalho para popular o Seed SP (Etapa 3) caso o banco ainda nao exista
if not exist "revtributaria.db" (
    if exist "src\app\seed_sp.py" (
        echo [INFO] Banco revtributaria.db nao encontrado. Executando Seed inicial de SP...
        python -m src.app.seed_sp --offline
    )
)

if exist "src\ui\app.py" (
    echo.
    set /p "RUN_UI=Deseja iniciar a interface visual Streamlit agora [S/N]: "
    if /i "!RUN_UI!"=="S" (
        python -m streamlit run src\ui\app.py
    )
)
echo ============================================================================
pause