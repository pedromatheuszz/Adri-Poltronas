"""Gera o par de chaves Ed25519 que assina as respostas de licenca.

Uso (uma unica vez, no computador do fornecedor):

    python licensing-service/gerar_chave_de_assinatura.py

Imprime duas linhas:

* `LICENSE_SIGNING_KEY` -- a chave PRIVADA. Vai somente para as variaveis de
  ambiente do servico de licencas (Render, ou o `.env` do Docker Compose).
  Quem a tiver emite licencas validas: nao a guarde no repositorio, nao a
  envie por mensagem e nao a coloque em nenhuma instalacao de cliente.
* `CHAVE_PUBLICA_DA_CENTRAL` -- a chave PUBLICA. Vai para a constante de
  mesmo nome em `backend/licenca_remota.py`. Nao e segredo.

Gerar um par novo invalida as provas ja emitidas: os aplicativos com a chave
publica antiga deixam de reconhecer o servico ate serem atualizados. Ver a
ordem de ativacao em `licensing-service/README.md`.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def gerar_par() -> tuple[str, str]:
    """(privada, publica), ambas em base64 dos 32 bytes crus."""
    privada = Ed25519PrivateKey.generate()
    semente = privada.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    publica = privada.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(semente).decode("ascii"), base64.b64encode(publica).decode("ascii")


if __name__ == "__main__":
    chave_privada, chave_publica = gerar_par()
    print("LICENSE_SIGNING_KEY=" + chave_privada)
    print('CHAVE_PUBLICA_DA_CENTRAL = "' + chave_publica + '"')
