.PHONY: help test lint install-deps clean build installer qt dotnet run run-qt run-dotnet dev

PYTHON := python
NPM := npm
PIP := $(PYTHON) -m pip
PYTEST := $(PYTHON) -m pytest
RUFF := $(PYTHON) -m ruff

help:
	@echo "🚀 Adri Poltronas - Makefile"
	@echo ""
	@echo "Comandos disponíveis:"
	@echo "  make install-deps    Instala dependências (Python + Node)"
	@echo "  make test            Executa testes"
	@echo "  make lint            Verifica estilo do código (ruff + tsc)"
	@echo "  make clean           Remove arquivos gerados"
	@echo "  make build           Empacota o backend (testes → lint → PyInstaller)"
	@echo "  make installer       Build + electron-builder (instalador completo)"
	@echo "  make qt              Compila e testa a janela Qt (QT_PREFIX_PATH)"
	@echo "  make run-qt          Executa a janela Qt"
	@echo "  make dotnet          Compila e testa a solution .NET/Avalonia"
	@echo "  make run-dotnet      Executa o aplicativo Avalonia"
	@echo "  make run             Executa a aplicação (janela Electron)"
	@echo "  make dev             Executa só o backend (sem janela)"
	@echo ""

install-deps:
	@echo "📥 Instalando dependências..."
	$(PIP) install -r backend/requirements.txt
	$(NPM) install

test:
	@echo "🧪 Executando testes..."
	cd backend && $(PYTEST) ../tests -v --tb=short

lint:
	@echo "🔍 Verificando estilo do código..."
	$(RUFF) check backend/ tests/ build.py
	$(NPM) run typecheck

clean:
	@echo "🗑️  Limpando arquivos gerados..."
	rm -rf build/ dist/ dist-electron/ dist-instalador/ .pytest_cache/ __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "✓ Limpeza concluída"

# Estagio 1: o backend Flask, sem janela. O .spec gera um executavel console
# que o electron-builder consome como extraResources.
build: test lint
	@echo "Empacotando backend..."
	$(PYTHON) -m PyInstaller AdriPoltronasBackend.spec \
		--noconfirm \
		--distpath dist \
		--workpath build
	@echo "OK: dist/AdriPoltronasBackend/AdriPoltronasBackend.exe"

# Estagio 2: a janela Electron + o backend do estagio 1, num instalador NSIS.
installer: build
	@echo "Gerando instalador..."
	$(NPM) run dist
	@echo "OK: instalador em dist-instalador/"

# Janela alternativa em C++/Qt. QT_PREFIX_PATH aponta a instalacao do Qt;
# nao fica fixo no repositorio porque varia por maquina.
qt:
	$(PYTHON) build.py qt

run-qt: qt
	@echo "Executando janela Qt..."
	qt-app/build/AdriPoltronasQt.exe

# Aplicativo desktop em C#/Avalonia: e a arquitetura para onde o projeto
# esta migrando (Domain, Application, Infrastructure, Presentation).
dotnet:
	$(PYTHON) build.py dotnet

run-dotnet:
	@echo "Executando aplicacao Avalonia..."
	cd dotnet && dotnet run --project src/AdriPoltronas.Desktop

run:
	@echo "Executando aplicacao (janela Electron)..."
	$(NPM) start

dev:
	@echo "Somente o backend, sem janela (http://127.0.0.1:5000/)..."
	$(PYTHON) backend/servidor.py

.DEFAULT_GOAL := help
