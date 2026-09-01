# Build & Development Guide - Adri Poltronas

## Arquitetura

O app tem dois processos:

| Processo | O que faz | Onde mora |
|----------|-----------|-----------|
| **Electron** (Node/TypeScript) | Abre a janela principal e aponta para o backend | `electron/` -> compilado em `dist-electron/` |
| **Flask** (Python) | API, banco SQLite, migrations, integracoes | `backend/` -> entrypoint `backend/servidor.py` |
| **Qt** (C++) | Janela alternativa, opcional, sobre o mesmo backend | `qt-app/` -> ver [qt-app/README.md](qt-app/README.md) |
| **.NET / Avalonia** (C#) | Aplicativo desktop em camadas; le o mesmo banco | `dotnet/` -> ver [dotnet/README.md](dotnet/README.md) |

O Electron sobe o Python como processo filho, espera a porta `127.0.0.1:5000`
responder e so entao mostra a janela. Ao fechar a janela, o filho e encerrado.

> A porta e fixa porque o `redirect_uri` do OAuth da Microsoft esta registrado
> no Azure como `http://localhost:5000/callback`.

O motor de exibicao anterior era o WebView2, embutido via pywebview. Ele foi
removido: alem de depender do runtime da Microsoft instalado na maquina, o
`fetch()` para hosts externos falhava nele, o que quebrava a geocodificacao do
mapa (ViaCEP/Nominatim). O Electron traz o proprio Chromium e nao tem o problema.

## Pre-requisitos

- Python 3.10+ (o CI cobre 3.10, 3.11 e 3.12)
- Node.js 20+ (o CI usa 22)
- Opcional, so para a janela Qt: Qt 6.8+ com MinGW e CMake 3.21+
- Para o aplicativo Avalonia: .NET SDK 8.0+

## Quick Start

### Instalação de Dependências
```bash
# Usando Python script (instala Python + Node)
python build.py install-deps

# Ou usando Makefile
make install-deps

# Ou direto
pip install -r backend/requirements.txt
npm install
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

### Build (dois estágios)
```bash
# Estágio 1: PyInstaller empacota o backend (sem janela)
python build.py build      # -> dist/AdriPoltronasBackend/

# Estágio 2: electron-builder gera o instalador NSIS
python build.py installer  # -> dist-instalador/
# ou
make installer
```

### Desenvolvimento Local
```bash
# App completo (compila o TypeScript e abre a janela)
npm start
# ou
make run

# Só o backend, sem janela, em http://127.0.0.1:5000/
python backend/servidor.py
# ou
make dev

# Checagem de tipos do processo principal do Electron
npm run typecheck

# Janela alternativa em Qt (compila + ctest)
python build.py qt
# ou
make qt

# Aplicativo .NET/Avalonia (restore + build + test)
python build.py dotnet
# ou
make dotnet

# Executar o aplicativo Avalonia
make run-dotnet
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
- `python build.py build` - Empacota o backend com PyInstaller
- `python build.py installer` - Build + electron-builder (instalador)
- `python build.py qt` - Compila e testa a janela Qt
- `python build.py dotnet` - Restaura, compila e testa a solution .NET
- `python build.py help` - Mostra ajuda

#### Makefile (Linux/macOS)
Tradicional Makefile para Unix-like systems.

**Targets:**
- `make test` - Testes
- `make lint` - Lint
- `make build` - Empacota o backend
- `make installer` - Instalador completo
- `make qt` - Compila e testa a janela Qt
- `make dotnet` - Compila e testa a solution .NET/Avalonia
- `make run` - Executar aplicação (janela Electron)
- `make run-qt` - Executar a janela Qt
- `make run-dotnet` - Executar o aplicativo Avalonia
- `make dev` - Modo desenvolvimento
- `make clean` - Limpeza
- `make help` - Ajuda

## CI/CD Pipeline

O GitHub Actions está configurado para:

1. **Lint** - Verifica estilo com ruff
2. **Testes** - Executa pytest com Python 3.10, 3.11, 3.12
3. **Electron** - `npm ci`, `tsc --noEmit` e build do processo principal
4. **Qt** - CMake + ctest da janela alternativa
5. **.NET** - `dotnet restore`, `build` e `test` (roda no Linux, para pegar dependência acidental de Windows)
6. **Segurança** - Verifica vulnerabilidades com pip-audit e scan de segredos
7. **Coverage** - Envia relatórios para Codecov (opcional)

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
├── package.json            # Manifesto do Electron + config do electron-builder
├── tsconfig.json           # TypeScript (strict) do processo principal
├── electron/
│   ├── main.ts             # Janela, single-instance, links externos
│   └── backend.ts          # Sobe/encerra o processo Flask
├── dotnet/                 # Aplicativo C#/Avalonia em camadas
│   ├── AdriPoltronas.sln
│   ├── src/                # Domain, Application, Infrastructure, Desktop
│   └── tests/              # xUnit, um projeto por camada
├── qt-app/                 # Janela alternativa em C++/Qt (opcional)
│   ├── CMakeLists.txt
│   ├── src/                # ProcessoBackend, ClienteApi, JanelaPrincipal...
│   └── tests/              # QtTest, rodados pelo ctest
├── backend/
│   ├── servidor.py         # Entry point do backend (headless)
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
├── AdriPoltronasBackend.spec  # PyInstaller (backend, console)
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

### A janela abre em branco
O backend não subiu. Rode `python backend/servidor.py` sozinho para ver o erro
— o Electron repassa a saída do filho prefixada com `[backend]` no console.

### electron-builder falha com `Cannot create symbolic link`
O pacote `winCodeSign` traz dois symlinks de dylibs do macOS, e criar symlink no
Windows exige privilégio de administrador ou o Modo Desenvolvedor ligado. Extraia
o cache manualmente, sem a pasta `darwin` (inútil num build Windows):

```bash
CACHE="$LOCALAPPDATA/electron-builder/Cache/winCodeSign"
node_modules/7zip-bin/win/x64/7za.exe x -y "-x!darwin"   "$CACHE/<hash>.7z" "-o$CACHE/winCodeSign-2.6.0"
```
Depois apague os diretórios numéricos órfãos em `$CACHE` e rode o build de novo.

### electron-builder falha com `image must be at least 256x256`
O `icone_sistema.ico` precisa de uma camada de 256×256. Há um teste que cobre
isso (`test_icone_tem_camada_de_256px`).

### `npm install` não baixou o binário do Electron
Versões recentes do npm bloqueiam scripts de instalação. Force o download:
```bash
cd node_modules/electron && node install.js
```

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
