# Build script para Adri Poltronas
# Uso: python build.py [comando]
# Comandos: test, lint, build, installer, qt, dotnet, clean, install-deps, help
#
# O build tem dois estagios desde a migracao para o Electron:
#   1. `build`     -> PyInstaller empacota o backend Flask (sem janela).
#   2. `installer` -> electron-builder empacota a janela + o backend do passo 1.

import os
import sys
import subprocess
import shutil
from pathlib import Path

# No Windows a saida redirecionada (pipe, CI, `> arquivo`) abre em cp1252 e os
# emojis das mensagens estouram UnicodeEncodeError -- o script morria antes de
# rodar qualquer coisa. Forcar UTF-8 mantem o comportamento igual no console.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
SPEC_FILE = PROJECT_ROOT / "AdriPoltronasBackend.spec"
INSTALADOR_DIR = PROJECT_ROOT / "dist-instalador"
# `npm` e um .cmd no Windows; sem shell=True o subprocess nao o encontra.
NPM = "npm.cmd" if os.name == "nt" else "npm"

# Janela alternativa em C++/Qt (qt-app/). O caminho do Qt e do compilador vem
# do ambiente para nao fixar a instalacao de uma maquina no repositorio.
QT_DIR = PROJECT_ROOT / "qt-app"
QT_BUILD_DIR = QT_DIR / "build"
QT_PREFIX = os.environ.get("QT_PREFIX_PATH", "")
QT_COMPILADOR = os.environ.get("QT_CXX_COMPILER", "")
QT_MAKE = os.environ.get("QT_MAKE_PROGRAM", "")

# Aplicativo desktop em C#/Avalonia (dotnet/). E a arquitetura para onde o
# projeto esta migrando: Domain, Application, Infrastructure e Presentation.
DOTNET_DIR = PROJECT_ROOT / "dotnet"

def run_command(cmd, cwd=None, description=""):
    """Executa um comando e retorna o status."""
    if description:
        print(f"\n📦 {description}...")
    print(f"  $ {' '.join(cmd)}")
    try:
        subprocess.run(cmd, cwd=cwd or PROJECT_ROOT, check=True)  # noqa: S603 - argumentos fixos, montados no codigo e nao pela entrada
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
    # Em ambientes sobrepostos (como `uv run --with-requirements`), o pacote
    # e o executavel podem viver em prefixes diferentes. O binario presente
    # no PATH e o mesmo entrypoint usado pela CI.
    ruff_executavel = shutil.which("ruff")
    cmd = (
        [ruff_executavel, "check", "backend/", "tests/"]
        if ruff_executavel
        else [sys.executable, "-m", "ruff", "check", "backend/", "tests/"]
    )
    return run_command(cmd, None, "Lint com ruff")

def install_deps():
    """Instala dependências."""
    print("📥 Instalando dependências...")
    cmd = [sys.executable, "-m", "pip", "install", "-r", "backend/requirements.txt"]
    return run_command(cmd, None, "Instalação de dependências")

def clean():
    """Remove arquivos gerados."""
    print("🗑️  Limpando arquivos gerados...")
    for d in [DIST_DIR, BUILD_DIR, INSTALADOR_DIR, QT_BUILD_DIR,
              PROJECT_ROOT / "dist-electron", PROJECT_ROOT / "__pycache__"]:
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
    return True

def build():
    """Empacota o backend Flask com PyInstaller (estagio 1)."""
    print("🔨 Building backend...")

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
        print("✅ Backend empacotado!")
        print(f"  📍 Executável em: {DIST_DIR / 'AdriPoltronasBackend' / 'AdriPoltronasBackend.exe'}")
        print("  ➡️  Próximo passo: python build.py installer")
        return True
    return False


def installer():
    """Gera o instalador com electron-builder (estagio 2)."""
    if not build():
        print("❌ Backend não foi empacotado. Instalador abortado.")
        return False

    # `npm run dist` compila o TypeScript e chama o electron-builder, que copia
    # dist/AdriPoltronasBackend para resources/backend (extraResources).
    if run_command([NPM, "run", "dist"], PROJECT_ROOT, "electron-builder"):
        print("✅ Instalador gerado!")
        print(f"  📍 Saída em: {INSTALADOR_DIR}")
        return True
    return False

def qt():
    """Compila e testa a janela Qt (qt-app/)."""
    print("Building janela Qt...")
    if not QT_PREFIX:
        print("QT_PREFIX_PATH nao definido. Exemplo:")
        print(r"  set QT_PREFIX_PATH=C:\Qt\6.8.3\mingw_64")
        return False

    configurar = [
        "cmake", "-S", str(QT_DIR), "-B", str(QT_BUILD_DIR),
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_PREFIX_PATH={QT_PREFIX}",
    ]
    # Com MinGW o gerador padrao (Visual Studio) nao serve; quem aponta o
    # compilador escolhe tambem o gerador.
    if QT_COMPILADOR:
        configurar += ["-G", "MinGW Makefiles", f"-DCMAKE_CXX_COMPILER={QT_COMPILADOR}"]
    if QT_MAKE:
        configurar.append(f"-DCMAKE_MAKE_PROGRAM={QT_MAKE}")

    if not run_command(configurar, PROJECT_ROOT, "CMake configure"):
        return False
    if not run_command(["cmake", "--build", str(QT_BUILD_DIR), "-j", "4"],
                       PROJECT_ROOT, "CMake build"):
        return False
    return run_command(["ctest", "--test-dir", str(QT_BUILD_DIR), "--output-on-failure"],
                       PROJECT_ROOT, "ctest")


def dotnet():
    """Restaura, compila e testa a solution .NET."""
    print("Building solution .NET...")
    etapas = [
        (["dotnet", "restore"], "dotnet restore"),
        (["dotnet", "build", "--no-restore"], "dotnet build"),
        (["dotnet", "test", "--no-build"], "dotnet test"),
    ]
    for comando, descricao in etapas:
        if not run_command(comando, DOTNET_DIR, descricao):
            return False
    return True


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
  build         Empacota o backend (testes → lint → PyInstaller)
  installer     Build + electron-builder (instalador completo)
  qt            Compila e testa a janela Qt (precisa de QT_PREFIX_PATH)
  dotnet        Restaura, compila e testa a solution .NET/Avalonia
  help          Mostra esta mensagem

Exemplos:
  python build.py test
  python build.py build
  python build.py clean
    """)
    return True

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
        "installer": installer,
        "qt": qt,
        "dotnet": dotnet,
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
