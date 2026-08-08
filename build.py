# Build script para Adri Poltronas
# Uso: python build.py [comando]
# Comandos: test, lint, build, clean, install-deps, help

import os
import sys
import subprocess
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
SPEC_FILE = PROJECT_ROOT / "AdriPoltronasApp.spec"

def run_command(cmd, cwd=None, description=""):
    """Executa um comando e retorna o status."""
    if description:
        print(f"\n📦 {description}...")
    print(f"  $ {' '.join(cmd)}")
    try:
        subprocess.run(cmd, cwd=cwd or PROJECT_ROOT, check=True)
        return True
    except subprocess.CalledProcessError:
        print(f"❌ Erro: {description or 'Comando falhou'}")
        return False

def test():
    """Executa testes."""
    print("🧪 Executando testes...")
    os.chdir(BACKEND_DIR)
    cmd = [sys.executable, "-m", "pytest", "../tests", "-v", "--tb=short"]
    return run_command(cmd, BACKEND_DIR, "Testes")

def lint():
    """Verifica estilo do código."""
    print("🔍 Verificando estilo do código...")
    cmd = [sys.executable, "-m", "ruff", "check", "backend/", "tests/"]
    return run_command(cmd, None, "Lint com ruff")

def install_deps():
    """Instala dependências."""
    print("📥 Instalando dependências...")
    cmd = [sys.executable, "-m", "pip", "install", "-r", "backend/requirements.txt"]
    return run_command(cmd, None, "Instalação de dependências")

def clean():
    """Remove arquivos gerados."""
    print("🗑️  Limpando arquivos gerados...")
    for d in [DIST_DIR, BUILD_DIR, PROJECT_ROOT / "__pycache__"]:
        if d.exists():
            shutil.rmtree(d)
            print(f"  ✓ Removido: {d}")
    
    for pattern in ["**/__pycache__", "**/*.pyc", "**/.pytest_cache"]:
        for f in PROJECT_ROOT.glob(pattern):
            if f.is_dir():
                shutil.rmtree(f)
            else:
                f.unlink()
    print("  ✓ Limpeza concluída")

def build():
    """Build da aplicação com PyInstaller."""
    print("🔨 Building aplicação...")

    if not test():
        print("❌ Testes falharam. Build abortado.")
        return False

    if not lint():
        print("❌ Lint encontrou problemas. Build abortado.")
        return False

    # O build usa o .spec, que declara templates/, alembic.ini e migrations/
    # como datas. Recriar as flags aqui produziria um bundle sem esses
    # recursos e o app empacotado quebraria no primeiro render_template.
    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(SPEC_FILE),
        "--noconfirm",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
    ]

    if run_command(cmd, PROJECT_ROOT, "PyInstaller"):
        print("✅ Build concluído com sucesso!")
        print(f"  📍 Executável em: {DIST_DIR / 'AdriPoltronasApp' / 'AdriPoltronasApp.exe'}")
        return True
    return False

def help_cmd():
    """Mostra ajuda."""
    print("""
🚀 Adri Poltronas - Build Script

Uso: python build.py [comando]

Comandos:
  test          Executa testes com pytest
  lint          Verifica estilo do código com ruff
  install-deps  Instala dependências do requirements.txt
  clean         Remove arquivos e diretórios gerados
  build         Build completo (testes → lint → PyInstaller)
  help          Mostra esta mensagem

Exemplos:
  python build.py test
  python build.py build
  python build.py clean
    """)

def main():
    if len(sys.argv) < 2:
        help_cmd()
        sys.exit(0)
    
    comando = sys.argv[1]
    
    commands = {
        "test": test,
        "lint": lint,
        "install-deps": install_deps,
        "clean": clean,
        "build": build,
        "help": help_cmd,
    }
    
    if comando not in commands:
        print(f"❌ Comando desconhecido: {comando}")
        help_cmd()
        sys.exit(1)
    
    success = commands[comando]()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
