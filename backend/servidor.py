"""
Ponto de entrada do backend.

Antes o processo Python tambem hospedava a janela, via pywebview/WebView2.
Agora ele so serve o Flask em loopback: a janela e do Electron, que sobe este
processo como filho e aponta o BrowserWindow para a mesma porta.

Consequencia pratica: nada aqui depende mais de GUI, entao o backend roda
igual sob o Electron, sozinho no terminal ou dentro da suite de testes.
"""
import logging
import os
import sys

# O diretorio precisa estar em sys.path antes dos imports do proprio backend,
# porque os modulos se referenciam por nome de topo (`import database`).
DIRETORIO_BACKEND = os.path.dirname(os.path.abspath(__file__))
if DIRETORIO_BACKEND not in sys.path:
    sys.path.insert(0, DIRETORIO_BACKEND)

import database  # noqa: E402
from app import app  # noqa: E402

log = logging.getLogger("adri.servidor")

HOST = "127.0.0.1"  # loopback apenas -- nao exposto na rede
PORTA = 5000  # fixa: o redirect_uri do OAuth Microsoft aponta para ela


def preparar_banco() -> None:
    """
    Aplica as migracoes; se falhar, cria o schema pelo caminho antigo.

    O fallback existe porque uma instalacao sem alembic.ini legivel ainda
    consegue subir com o schema basico, em vez de nao abrir.
    """
    try:
        import migrations_manager
        migrations_manager.aplicar_migrações()
    except Exception:
        log.exception("Falha ao aplicar migracoes; usando criar_tabela()")
        database.criar_tabela()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        preparar_banco()
    except Exception:
        log.exception("Nao foi possivel inicializar o banco de dados local")
        return 1

    log.info("Servidor em http://%s:%s/", HOST, PORTA)
    # debug/reloader desligados: o reloader duplicaria o processo, e o Electron
    # perderia a referencia do filho que precisa encerrar junto com a janela.
    app.run(host=HOST, port=PORTA, debug=False, use_reloader=False, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
