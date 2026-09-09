import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import webview

# Configuração de logging mínima (o backend também configura o seu)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("adri.main")

# Garante a inclusão correta da pasta 'backend' no escopo de importação do Python
caminho_raiz = os.path.dirname(os.path.abspath(__file__))
pasta_backend = os.path.join(caminho_raiz, 'backend')
if pasta_backend not in sys.path:
    sys.path.append(pasta_backend)
if caminho_raiz not in sys.path:
    sys.path.append(caminho_raiz)

# Importação após ajustar sys.path
from backend import database  # noqa: E402
from backend.app import app  # noqa: E402

PORTA = 5000
HOST = "127.0.0.1"  # loopback only — não exposto na rede
URL_LOCAL = f"http://{HOST}:{PORTA}/"


def _esperar_servidor(timeout: float = 10.0) -> bool:
    """
    Faz health check no Flask antes de abrir a janela.
    Substitui o antigo `time.sleep(1.5)` mágico.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(URL_LOCAL, timeout=0.5) as r:
                if 200 <= r.status < 500:
                    return True
        except (urllib.error.URLError, ConnectionResetError, OSError):
            time.sleep(0.1)
    return False


def rodar_flask():
    try:
        # debug=False e use_reloader=False para não spawnar processos filhos
        # dentro do app empacotado (PyInstaller não suporta bem).
        app.run(host=HOST, port=PORTA, debug=False, use_reloader=False)
    except OSError as e:
        # Provavelmente porta ocupada. Log e propaga para a thread principal.
        log.error("Falha ao iniciar Flask: %s", e)
        raise


def _mostrar_erro_e_sair(titulo: str, mensagem: str) -> None:
    """Exibe uma caixa de diálogo de erro via webview e encerra."""
    try:
        webview.create_window(titulo, html=f"<h2 style='font-family:sans-serif'>{mensagem}</h2>")
        webview.start()
    except Exception:
        log.exception("Falha ao mostrar diálogo de erro")
    sys.exit(1)


if __name__ == '__main__':
    # Garante que o schema do banco existe antes de servir
    try:
        database.criar_tabela()
    except Exception:
        log.exception("Falha ao inicializar o banco de dados")
        _mostrar_erro_e_sair(
            "Adri Poltronas — Erro",
            "Nao foi possivel inicializar o banco de dados local.",
        )

    # Sobe o Flask em thread daemon
    thread = threading.Thread(target=rodar_flask, daemon=True)
    thread.start()

    # Espera o servidor estar pronto (com timeout)
    if not _esperar_servidor(timeout=10.0):
        _mostrar_erro_e_sair(
            "Adri Poltronas — Erro",
            f"O servidor interno nao respondeu em http://{HOST}:{PORTA}/ . "
            "Verifique se outra instancia esta em uso.",
        )

    # Abre a janela desktop apontando para o servidor local
    try:
        webview.create_window(
            title='Adri Poltronas',
            url=URL_LOCAL,
            width=1000,
            height=700,
            resizable=True,
        )
        webview.start()
    except Exception:
        log.exception("Falha ao iniciar a janela desktop")
        sys.exit(1)
