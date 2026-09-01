"""
Ponto de entrada do backend v2.

Porta 5001 por padrao para poder rodar LADO A LADO com o v1 (5000) enquanto
voce compara os dois. `ADRI_V2_PORTA=5000` sobe no lugar do v1.
"""
from __future__ import annotations

import logging
import os
import sys

# A RAIZ do projeto entra no path -- nao esta pasta. O v2 se importa como o
# pacote `backend_v2`, e assim nenhum modulo de topo dele disputa nome com o
# backend v1, que tambem tem `app.py` e `servidor.py`.
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from backend_v2.app import criar_app  # noqa: E402

log = logging.getLogger("adri.v2.servidor")

HOST = os.environ.get("ADRI_V2_HOST", "127.0.0.1")
PORTA = int(os.environ.get("ADRI_V2_PORTA", "5001"))


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        aplicacao = criar_app()
    except Exception:
        log.exception("Nao foi possivel inicializar o backend v2")
        return 1

    log.info("ERP v2 em http://%s:%s/api/v2/saude", HOST, PORTA)
    log.info("Banco: %s", aplicacao.config["CAMINHO_BANCO"])
    aplicacao.run(host=HOST, port=PORTA, debug=False, use_reloader=False, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
