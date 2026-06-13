@echo off
REM Makefile equivalente para Windows para ejecutar tests

setlocal enabledelayedexpansion

if "%1%"=="" goto help
if "%1%"=="help" goto help
if "%1%"=="all" goto all
if "%1%"=="quick" goto quick
if "%1%"=="coverage" goto coverage
if "%1%"=="health" goto health
if "%1%"=="p1" goto p1
if "%1%"=="seq" goto seq
if "%1%"=="install-test" goto install_test

:help
echo Uso: test.bat [comando]
echo.
echo Comandos:
echo   all            - Ejecutar todos los tests
echo   quick          - Tests rapidos
echo   coverage       - Tests con cobertura
echo   health         - Verificar health check
echo   p1             - Tests de Pipeline 1
echo   seq            - Tests de Secuencia
echo   install-test   - Instalar dependencias de testing
echo   help           - Ver esta ayuda
echo.
echo Ejemplos:
echo   test.bat all
echo   test.bat coverage
echo   test.bat health
goto end

:all
echo Ejecutando todos los tests...
pytest tests/ -v
goto end

:quick
echo Ejecutando tests rapidos...
pytest tests/ -v -m "not slow"
goto end

:coverage
echo Ejecutando tests con cobertura...
pytest tests/ --cov=app --cov-report=html --cov-report=term-missing
goto end

:health
echo Verificando health check...
pytest tests/test_pipelines.py::TestHealthCheck -v
goto end

:p1
echo Tests de Pipeline 1...
pytest tests/test_pipelines.py::TestPipeline1 -v
goto end

:seq
echo Tests de Secuencia...
pytest tests/test_pipelines.py::TestSequence -v
goto end

:install_test
echo Instalando dependencias de testing...
pip install pytest pytest-asyncio pytest-cov httpx
goto end

:end
endlocal
