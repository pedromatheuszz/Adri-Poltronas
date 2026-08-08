.PHONY: help test lint install-deps clean build run dev

PYTHON := python
PIP := $(PYTHON) -m pip
PYTEST := $(PYTHON) -m pytest
RUFF := $(PYTHON) -m ruff

help:
	@echo "🚀 Adri Poltronas - Makefile"
	@echo ""
	@echo "Comandos disponíveis:"
	@echo "  make install-deps    Instala dependências"
	@echo "  make test            Executa testes"
	@echo "  make lint            Verifica estilo do código"
	@echo "  make clean           Remove arquivos gerados"
	@echo "  make build           Build completo (testes → lint → PyInstaller)"
	@echo "  make run             Executa a aplicação"
	@echo "  make dev             Executa em modo desenvolvimento (Flask debug)"
	@echo ""

install-deps:
	@echo "📥 Instalando dependências..."
	$(PIP) install -r backend/requirements.txt

test:
	@echo "🧪 Executando testes..."
	cd backend && $(PYTEST) ../tests -v --tb=short

lint:
	@echo "🔍 Verificando estilo do código..."
	$(RUFF) check backend/ tests/

clean:
	@echo "🗑️  Limpando arquivos gerados..."
	rm -rf build/ dist/ .pytest_cache/ __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "✓ Limpeza concluída"

build: test lint
	@echo "🔨 Building aplicação..."
	$(PYTHON) -m PyInstaller AdriPoltronasApp.spec \
		--noconfirm \
		--distpath dist \
		--workpath build
	@echo "✅ Build concluído!"
	@echo "📍 Executável em: dist/AdriPoltronasApp/AdriPoltronasApp.exe"

run:
	@echo "▶️  Executando aplicação..."
	$(PYTHON) main.py

dev:
	@echo "🔧 Modo desenvolvimento (Flask debug)..."
	cd backend && FLASK_ENV=development $(PYTHON) -m flask run --debug

.DEFAULT_GOAL := help
