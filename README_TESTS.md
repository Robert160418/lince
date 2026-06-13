# Tests - Guía Rápida

## Instalación

```bash
pip install pytest pytest-asyncio pytest-cov httpx
```

O usa el script:
```bash
python test.bat install-test
```

## Ejecutar Tests

### Windows (PowerShell)
```powershell
# Todos los tests
python run_tests.py all

# O con el batch file
test.bat all

# Tests rápidos
test.bat quick

# Con cobertura
test.bat coverage
```

### Linux/macOS
```bash
# Todos los tests
pytest tests/ -v

# Tests rápidos
pytest tests/ -v -m "not slow"

# Con cobertura
pytest tests/ --cov=app --cov-report=html
```

## Opciones Comunes

| Comando | Descripción |
|---------|------------|
| `pytest tests/ -v` | Todos los tests (verbose) |
| `pytest tests/test_pipelines.py::TestHealthCheck -v` | Tests específicos |
| `pytest tests/ -k "p1"` | Tests que contengan "p1" en el nombre |
| `pytest tests/ --tb=short` | Traceback corto |
| `pytest tests/ -x` | Parar en el primer fallo |
| `pytest tests/ --lf` | Correr último fallo |

## Tests Disponibles

### Health Check
```bash
pytest tests/test_pipelines.py::TestHealthCheck -v
```

### Pipeline 1 (Google Maps)
```bash
pytest tests/test_pipelines.py::TestPipeline1 -v
```

### Pipeline 2 (Reviews)
```bash
pytest tests/test_pipelines.py::TestPipeline2 -v
```

### Secuencia Completa
```bash
pytest tests/test_pipelines.py::TestSequence -v
```

### Manejo de Errores
```bash
pytest tests/test_pipelines.py::TestErrorHandling -v
```

## Cobertura

Genera reporte de cobertura:
```bash
pytest tests/ --cov=app --cov-report=html
```

Abre `htmlcov/index.html` en el navegador para ver el reporte.

## Debugging

### Ver logs detallados
```bash
pytest tests/ -v -s
```

### Parar en primer error
```bash
pytest tests/ -x
```

### Ejecutar un test específico
```bash
pytest tests/test_pipelines.py::TestPipeline1::test_p1_basic -v
```

### Ver variables de ambiente
```bash
pytest tests/ -v --fixtures | grep "app\|place\|email"
```

## Troubleshooting

### Error: "Connection refused"
Verifica que el servidor está corriendo:
```bash
python -m uvicorn app.main:app --reload
```

### Error: ModuleNotFoundError: No module named 'pytest'
Instala pytest:
```bash
pip install pytest pytest-asyncio pytest-cov
```

### Tests lentos o timeouts
Aumenta el timeout en `test_pipelines.py`:
```python
TIMEOUT = 300.0  # 5 minutos en lugar de 3
```

## Tips

1. **Ejecutar en paralelo** (si instalas pytest-xdist):
   ```bash
   pip install pytest-xdist
   pytest tests/ -n 4  # 4 workers
   ```

2. **Generar reporte HTML**:
   ```bash
   pytest tests/ --html=report.html
   ```

3. **Marcar tests lentos**:
   ```bash
   pytest tests/ -m "not slow"  # Excluye tests lentos
   ```

4. **Saltar tests específicos**:
   ```bash
   pytest tests/ -k "not test_p1_with_different_place_id"
   ```

## Checklist de Pruebas Manuales

- [ ] Health check funciona: `curl http://localhost:8000/health`
- [ ] Debug info accesible: `curl http://localhost:8000/debug`
- [ ] DB conectada: `curl http://localhost:8000/test-db`
- [ ] P1 devuelve leads: `pytest tests/test_pipelines.py::TestPipeline1::test_p1_basic -v`
- [ ] P5 devuelve 5 emails: `pytest tests/test_pipelines.py::TestPipeline5::test_p5_generates_5_emails -v`
- [ ] Sequence completa funciona: `pytest tests/test_pipelines.py::TestSequence::test_sequence_executes -v`
- [ ] Error handling robusto: `pytest tests/test_pipelines.py::TestErrorHandling -v`

## Referencias

- Documentación de pytest: https://docs.pytest.org/
- Guía de pruebas: [TEST_DOCUMENTATION.md](TEST_DOCUMENTATION.md)
