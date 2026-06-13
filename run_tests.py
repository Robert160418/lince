#!/usr/bin/env python3
"""Script para ejecutar tests con diferentes opciones"""

import subprocess
import sys
from pathlib import Path

def run_command(cmd, description=None):
    """Ejecuta un comando y muestra el resultado"""
    if description:
        print(f"\n{'='*70}")
        print(f"  {description}")
        print(f"{'='*70}\n")
    
    result = subprocess.run(cmd, shell=True)
    return result.returncode == 0

def main():
    if len(sys.argv) > 1:
        option = sys.argv[1].lower()
    else:
        option = "all"
    
    if option == "all" or option == "full":
        return run_command(
            "pytest tests/ -v",
            "EJECUTANDO TODOS LOS TESTS"
        )
    elif option == "quick":
        return run_command(
            "pytest tests/ -v -m 'not slow'",
            "EJECUTANDO TESTS RAPIDOS"
        )
    elif option == "unit":
        return run_command(
            "pytest tests/ -v -m 'unit'",
            "EJECUTANDO TESTS UNITARIOS"
        )
    elif option == "integration":
        return run_command(
            "pytest tests/ -v -m 'integration'",
            "EJECUTANDO TESTS DE INTEGRACION"
        )
    elif option == "coverage":
        return run_command(
            "pytest tests/ --cov=app --cov-report=html --cov-report=term-missing",
            "EJECUTANDO TESTS CON COVERAGE"
        )
    elif option == "health":
        return run_command(
            "pytest tests/test_pipelines.py::TestHealthCheck -v",
            "VERIFICANDO HEALTH CHECK"
        )
    elif option == "p1":
        return run_command(
            "pytest tests/test_pipelines.py::TestPipeline1 -v",
            "EJECUTANDO TESTS DE PIPELINE 1"
        )
    elif option == "seq":
        return run_command(
            "pytest tests/test_pipelines.py::TestSequence -v",
            "EJECUTANDO TESTS DE SECUENCIA"
        )
    else:
        print(f"Opcion desconocida: {option}")
        print("\nOpciones disponibles:")
        print("  all       - Todos los tests")
        print("  quick     - Tests rapidos (excluye slow)")
        print("  coverage  - Tests con reporte de cobertura")
        print("  health    - Health check")
        print("  p1        - Pipeline 1")
        print("  seq       - Tests de secuencia")
        print("\nEjemplos:")
        print("  python run_tests.py all")
        print("  python run_tests.py coverage")
        print("  python run_tests.py health")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
