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
    # Os mesmos alvos que a CI e o CONTRIBUTING.md mandam rodar, `build.py`
    # incluido. Ele ficava de fora, entao `python build.py lint` passava verde
    # num arquivo que o job de teste reprovaria -- e o comando local existe
    # justamente para evitar descobrir isso depois de abrir o PR.
    alvos = ["backend/", "tests/", "build.py"]
    cmd = (
        [ruff_executavel, "check", *alvos]
        if ruff_executavel
        else [sys.executable, "-m", "ruff", "check", *alvos]
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


# =============================================================================
# Assinatura de codigo
# =============================================================================
# O Windows exibe o aviso do SmartScreen para executaveis nao assinados: para
# um instalador que sai por download ou pendrive, e a diferenca entre a
# cliente instalar e ligar achando que baixou virus. O SECURITY.md sempre
# disse que o app nao e assinado; este comando e o caminho para mudar isso
# sem virar receita solta em documento.
#
# As credenciais vem do AMBIENTE e nunca de arquivo versionado:
#   ADRI_CERT_THUMBPRINT  SHA-1 do certificado no repositorio do usuario
#   ADRI_CERT_ARQUIVO     arquivo .pfx, junto com ADRI_CERT_SENHA
#   ADRI_CARIMBO          servidor de carimbo RFC 3161 (opcional)
CARIMBO_RFC3161_PADRAO = "http://timestamp.digicert.com"


def validar_thumbprint(valor):
    """
    Normaliza o SHA-1 do certificado, ou None se nao for um SHA-1.

    Aceita espacos (o Windows copia o thumbprint com espacos entre os pares)
    e maiuscula/minuscula. Recusa qualquer outra coisa: um thumbprint errado
    so faria o signtool procurar um certificado que nao existe, com uma
    mensagem generica -- o erro tem de nascer aqui, onde da para explicar.
    """
    limpo = (valor or "").replace(" ", "").strip().upper()
    if len(limpo) != 40:
        return None
    if any(caractere not in "0123456789ABCDEF" for caractere in limpo):
        return None
    return limpo


def executaveis_para_assinar():
    """
    O instalador e o backend que o instalador carrega.

    O backend viaja em extraResources: assinar so o instalador deixa o
    servidor que escuta em 127.0.0.1 sem assinatura, e ele e justamente o
    processo que o SmartScreen e os antivirus mais desconfiam.
    """
    alvos = []
    if INSTALADOR_DIR.is_dir():
        alvos += sorted(INSTALADOR_DIR.glob("*.exe"))
    backend_exe = DIST_DIR / "AdriPoltronasBackend" / "AdriPoltronasBackend.exe"
    if backend_exe.is_file():
        alvos.append(backend_exe)
    return alvos


def argumentos_de_assinatura(exe, thumbprint, arquivo_pfx, carimbo):
    """
    A linha de comando do signtool, montada em lista e nunca em shell.

    `/tr` com `/td`: carimbo RFC 3161 pela rede, que faz a assinatura
    continuar valida depois do certificado expirar. Sem carimbo, o
    instalador volta a ser "desconhecido" no dia em que o certificado vence.
    """
    args = ["sign", "/fd", "SHA256", "/td", "SHA256", "/tr", carimbo]
    if thumbprint:
        args += ["/sha1", thumbprint]
    else:
        args += ["/f", str(arquivo_pfx)]
    args.append(str(exe))
    return args


def localizar_signtool():
    """
    Onde mora o signtool.exe, ou None quando nao ha Windows SDK.

    `which` primeiro: quem tem o SDK no PATH ganha o caminho curto. O resto
    percorre as pastas do Windows Kits, pegando a versao mais recente -- o
    numero entre `bin` e `x64` muda a cada release do SDK.
    """
    encontrado = shutil.which("signtool")
    if encontrado:
        return encontrado

    kits = Path("C:/Program Files (x86)/Windows Kits/10")
    padroes = [
        "bin/*/x64/signtool.exe",
        "bin/*/x86/signtool.exe",
        "App Certification Kit/signtool.exe",
    ]
    for padrao in padroes:
        achados = sorted(kits.glob(padrao))
        if achados:
            # O curinga em bin/*/ e a versao do SDK: a ordenacao lexica
            # deixa a mais recente por ultimo.
            return str(achados[-1])
    return None


def assinar():
    """Assina os executaveis gerados e confere cada assinatura no fim."""
    print("🖋  Assinatura de codigo...")

    alvos = executaveis_para_assinar()
    if not alvos:
        print("❌ Nada para assinar. Rode `python build.py installer` antes.")
        print("   (Procurando em dist-instalador/ e dist/AdriPoltronasBackend/)")
        return False

    thumbprint = validar_thumbprint(os.environ.get("ADRI_CERT_THUMBPRINT", ""))
    arquivo_pfx = os.environ.get("ADRI_CERT_ARQUIVO", "").strip()
    senha = os.environ.get("ADRI_CERT_SENHA", "")
    carimbo = os.environ.get("ADRI_CARIMBO", "").strip() or CARIMBO_RFC3161_PADRAO

    if not thumbprint and not (arquivo_pfx and senha):
        print("❌ Sem credencial de assinatura. Use uma das duas formas:")
        print("   set ADRI_CERT_THUMBPRINT=<SHA-1 do certificado no repositorio do usuario>")
        print("   ou")
        print("   set ADRI_CERT_ARQUIVO=<caminho do .pfx>")
        print("   set ADRI_CERT_SENHA=<senha do .pfx>")
        print()
        print("   Certificado de teste (so silencia o aviso na sua maquina):")
        print("     New-SelfSignedCertificate -Type Custom -Subject 'CN=Adri Poltronas'")
        print("     -KeyUsage DigitalSignature -FriendlyName 'Adri Poltronas (teste)'")
        print("     -CertStoreLocation Cert:\\CurrentUser\\My -TextExtension @('2.5.29.37")
        print("     ={text}1.3.6.1.5.5.7.3.3')")
        print("   Certificado de verdade: Autoridade Certificadora (OV/EV).")
        return False
    if "ADRI_CERT_THUMBPRINT" in os.environ and not thumbprint:
        print("❌ ADRI_CERT_THUMBPRINT nao parece um SHA-1 (40 caracteres hex).")
        print("   O valor vem do campo 'Impressao digital' do certificado.")
        return False
    if arquivo_pfx and not Path(arquivo_pfx).is_file():
        print(f"❌ ADRI_CERT_ARQUIVO nao existe: {arquivo_pfx}")
        return False

    signtool = localizar_signtool()
    if not signtool:
        print("❌ signtool.exe nao encontrado. Instale o Windows SDK")
        print("   (Apps > Windows > 'Windows Software Development Kit').")
        return False

    for alvo in alvos:
        print(f"  ✍  {alvo.name}")
        # Lista, e nao string para o shell: a senha do .pfx nunca aparece em
        # linha de comando visivel a outros processos... exceto quando o
        # formato exige, que e o caso do /p. Por isso o .pfx e a segunda
        # opcao: o thumbprint no repositorio do usuario nao expoe nada.
        comando = [signtool] + argumentos_de_assinatura(
            alvo, thumbprint, arquivo_pfx, carimbo)
        if senha:
            comando += ["/p", senha]
        resultado = subprocess.run(comando, capture_output=True, text=True)  # noqa: S603 - signtool vem do SDK e os argumentos sao montados por argumentos_de_assinatura, testados
        if resultado.returncode != 0:
            print(f"❌ Falhou: {resultado.stdout}{resultado.stderr}")
            return False

        # Assinar sem conferir e prometer sem olhar: o verify /pa exige a
        # cadeia ate uma raiz confiavel, nao apenas a presenca de bytes.
        verificacao = subprocess.run(
            # signtool vem do SDK local e o alvo e o executavel do proprio
            # build: nada aqui vem de fora da maquina de quem assina.
            [signtool, "verify", "/pa", "/all", str(alvo)],  # noqa: S603
            capture_output=True, text=True)
        if verificacao.returncode != 0:
            print(f"❌ Assinatura gravada mas nao verificou: {verificacao.stdout}")
            return False
        print("  ✓ Assinado e verificado.")

    print("✅ Executaveis assinados.")
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
  assinar       Assina instalador e backend com signtool (ver BUILD_GUIDE.md)
  qt            Compila e testa a janela Qt (precisa de QT_PREFIX_PATH)
  dotnet        Restaura, compila e testa a solution .NET/Avalonia
  help          Mostra esta mensagem

Exemplos:
  python build.py test
  python build.py build
  python build.py assinar
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
        "assinar": assinar,
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
