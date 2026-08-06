# Build & Development Guide - Adri Poltronas

## Quick Start

### Instalação de Dependências
```bash
# Usando Python script
python build.py install-deps

# Ou usando Makefile (Linux/macOS)
make install-deps

# Ou pip direto
pip install -r backend/requirements.txt
```

### Executar Testes
```bash
python build.py test
# ou
make test
```

### Verificar Estilo do Código
```bash
python build.py lint
# ou
make lint
```

### Build da Aplicação (PyInstaller)
```bash
python build.py build
# ou
make build
```

### Desenvolvimento Local
```bash
# Executar a aplicação
python build.py test && python main.py

# Ou com Makefile
make run

# Modo debug Flask
make dev
```

### Limpeza
```bash
python build.py clean
# ou
make clean
```

## Estrutura de Build

### Scripts Disponíveis

#### build.py (Cross-platform)
Script Python que funciona em Windows, Linux e macOS. Ideal para CI/CD e desenvolvimento.

**Comandos:**
- `python build.py test` - Executa testes
- `python build.py lint` - Verifica estilo
- `python build.py install-deps` - Instala dependências
- `python build.py clean` - Limpa arquivos gerados
- `python build.py build` - Build completo
- `python build.py help` - Mostra ajuda

#### Makefile (Linux/macOS)
Tradicional Makefile para Unix-like systems.

**Targets:**
- `make test` - Testes
- `make lint` - Lint
- `make build` - Build completo
- `make run` - Executar aplicação
- `make dev` - Modo desenvolvimento
- `make clean` - Limpeza
- `make help` - Ajuda

## CI/CD Pipeline

O GitHub Actions está configurado para:

1. **Lint** - Verifica estilo com ruff
2. **Testes** - Executa pytest com Python 3.10, 3.11, 3.12
3. **Segurança** - Verifica vulnerabilidades com pip-audit e safety
4. **Coverage** - Enviia relatórios para Codecov (opcional)

Arquivo: `.github/workflows/ci.yml`

## Testes

### Executar Testes Específicos
```bash
cd backend
python -m pytest ../tests/test_api.py -v
python -m pytest ../tests/test_validators.py::test_cliente_valido -v
```

### Cobertura de Testes
```bash
cd backend
python -m pytest ../tests --cov=. --cov-report=html
```

## Desenvolvimento

### Estrutura do Projeto
```
Adri Poltronas/
├── main.py                 # Entry point
├── backend/
│   ├── app.py              # Flask app (core)
│   ├── blueprints/         # Modularização de rotas
│   ├── database.py         # SQLite ORM
│   ├── validators.py       # Validação de entrada
│   ├── security.py         # Criptografia
│   ├── asaas.py            # Integração Asaas
│   ├── config.py           # Configurações
│   ├── migrations_manager.py # Gerenciador de migrações
│   └── requirements.txt
├── frontend/
│   ├── css/style.css
│   ├── js/app.js
│   ├── js/offline.js
│   └── manifest.json
├── tests/
│   ├── test_api.py         # Testes de API
│   ├── test_database.py    # Testes de banco
│   └── test_validators.py  # Testes de validação
├── migrations/             # Alembic migrations
├── docs/
├── build.py                # Build script
└── Makefile
```

### Adicionando Nova Rota

1. **Criar novo blueprint** em `backend/blueprints/novo_modulo.py`:
```python
from flask import Blueprint, jsonify

novo_bp = Blueprint('novo', __name__, url_prefix='/api/novo')

@novo_bp.route('/exemplo', methods=['GET'])
def exemplo():
    return jsonify({"mensagem": "Hello"})
```

2. **Registrar no `__init__.py`** do blueprints
3. **Registrar no `app.py`**:
```python
from blueprints import novo_bp
app.register_blueprint(novo_bp)
```

4. **Adicionar testes** em `tests/test_api.py`

### Adicionando Migrações

```bash
cd backend
alembic revision --autogenerate -m "Descrição da alteração"
alembic upgrade head
```

## Variáveis de Ambiente

Criar `.env` na raiz do projeto (já existe `.env.example`):

```bash
ADRI_FLASK_SECRET=sua_chave_secreta
ADRI_MICROSOFT_CLIENT_ID=seu_client_id
GEMINI_API_KEY=sua_gemini_key
ASAAS_API_KEY=sua_asaas_key
ASAAS_SANDBOX=true
```

## Troubleshooting

### Testes falhando
```bash
# Limpar cache
make clean

# Reinstalar deps
pip install -r backend/requirements.txt --force-reinstall

# Rodar testes
make test
```

### Build falhando
- Verificar se PyInstaller está instalado
- Verificar se icone_sistema.ico existe
- Ver logs em `build/` directory

### Porta 5000 ocupada
```bash
# Windows
netstat -ano | findstr :5000
taskkill /PID <PID> /F

# Linux/macOS
lsof -ti:5000 | xargs kill -9
```

## Recursos Adicionais

- [Flask Documentation](https://flask.palletsprojects.com/)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/)
- [Alembic Migrations](https://alembic.sqlalchemy.org/)
- [pytest Documentation](https://docs.pytest.org/)
- [ruff Linter](https://github.com/astral-sh/ruff)
