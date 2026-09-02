"""
Capacidade de acesso a API local.

O problema que isto resolve
---------------------------
O Flask escuta em 127.0.0.1:5000. Loopback nao e a mesma coisa que privado:
QUALQUER processo da maquina -- e qualquer pagina aberta no navegador do
usuario -- consegue falar com essa porta. Ate aqui, o que separava o aplicativo
de um curl qualquer era:

* a checagem de `Origin`/`Referer`, que so vale para POST/PUT/PATCH/DELETE e
  que um cliente que simplesmente NAO envia esses cabecalhos atravessa;
* a exigencia de sessao Microsoft para escrita, que e uma linha no banco e nao
  uma credencial de quem esta chamando.

Ou seja: `GET /api/clientes` respondia a lista inteira de clientes, com nome,
endereco e CEP, para qualquer coisa que perguntasse.

A solucao
---------
Um segredo que so o aplicativo conhece, apresentado em toda requisicao. O
Electron gera o token, guarda no perfil do usuario, passa para o Flask filho
por variavel de ambiente e injeta o cabecalho em todas as requisicoes da
janela. Quem nao tem o token nao fala com a API.

Por que persistido no perfil, e nao sorteado a cada execucao
------------------------------------------------------------
Um token por execucao seria mais forte no papel, mas quebraria a reutilizacao
do backend orfao: quando o Electron morre sem levar o Python junto, a proxima
abertura encontra a porta ocupada por um servidor que so aceita o token
ANTERIOR, e o app nao teria como se recuperar sozinho.

O arquivo fica em `%APPDATA%\\AdriPoltronas\\.capacidade`, no mesmo diretorio
onde ja vive o banco SQLite com os dados dos clientes. Isso delimita
honestamente o que a protecao alcanca: um processo rodando como o mesmo
usuario ja pode abrir o banco direto, entao contra ele o token nao acrescenta
nada. O que ele fecha e o vetor real de um servico em loopback -- pagina web,
script de terceiro, ferramenta curiosa -- que chuta a porta 5000 as cegas.

Quando a variavel de ambiente nao esta definida, a exigencia fica DESLIGADA e
um aviso vai para o log. E o que mantem `python backend/servidor.py` sozinho
no terminal e a suite de testes funcionando. A instalacao empacotada sempre
passa pelo Electron, que sempre define o token.
"""
from __future__ import annotations

import hmac
import logging
import os
import secrets

log = logging.getLogger("adri.capacidade")

VARIAVEL_DE_AMBIENTE = "ADRI_API_TOKEN"
NOME_DO_HEADER = "X-Adri-Capacidade"
NOME_DO_COOKIE = "adri_capacidade"
NOME_DO_ARQUIVO = ".capacidade"

# 32 bytes em hexadecimal. Curto demais e adivinhavel; mais que isso so
# engorda o cabecalho de toda requisicao.
BYTES_DO_TOKEN = 32

# Rotas que precisam responder sem o token, e por que cada uma:
#
#   /api/pagamentos/webhook -- chamado pelo Asaas, de fora. Tem autenticacao
#       propria (ASAAS_WEBHOOK_TOKEN), que e o controle correto para ele.
#   /callback -- o redirect do OAuth Microsoft chega pelo navegador do
#       sistema, que nao tem como carregar o cabecalho. Nao expoe dado: so
#       troca o `code` por token.
#   /api/health -- e a sonda de identidade. Precisa responder para que o
#       Electron consiga descobrir SE o servidor na porta e este aplicativo e
#       se aceita a capacidade apresentada. Nao devolve dado de negocio.
ROTAS_ISENTAS = frozenset({
    "/api/pagamentos/webhook",
    "/callback",
    "/api/health",
})


def token_esperado() -> str:
    """Token desta execucao, ou string vazia quando a exigencia esta desligada."""
    return (os.environ.get(VARIAVEL_DE_AMBIENTE) or "").strip()


def esta_ativa() -> bool:
    return bool(token_esperado())


def gerar_token() -> str:
    return secrets.token_hex(BYTES_DO_TOKEN)


def caminho_do_arquivo(pasta_de_dados: str) -> str:
    return os.path.join(pasta_de_dados, NOME_DO_ARQUIVO)


def confere(apresentado: str | None) -> bool:
    """
    Compara em tempo constante.

    `hmac.compare_digest` em vez de `==` porque a comparacao ingenua de
    strings vaza, pelo tempo de resposta, quantos caracteres iniciais batem --
    e um servico local responde rapido o bastante para isso ser medivel.
    """
    esperado = token_esperado()
    if not esperado or not apresentado:
        return False
    return hmac.compare_digest(apresentado, esperado)


def apresentado_em(headers, cookies) -> str | None:
    """
    Token que veio na requisicao, do cabecalho ou do cookie.

    O cabecalho e a via principal: o Electron o injeta na sessao da janela. O
    cookie e a rede de seguranca para requisicoes que nascem fora desse
    caminho -- em particular as do Service Worker, que reencaminha um
    `Request` ja montado pela pagina.
    """
    do_header = headers.get(NOME_DO_HEADER)
    if do_header:
        return do_header
    return cookies.get(NOME_DO_COOKIE)


def carregar_ou_criar(pasta_de_dados: str) -> str:
    """
    Le o token do perfil do usuario, criando-o na primeira vez.

    Usado pelo backend quando ele sobe sozinho e quer publicar um token para
    quem for se conectar. O Electron tem a propria copia desta logica em
    TypeScript, porque precisa do token ANTES de iniciar o processo Python.
    """
    caminho = caminho_do_arquivo(pasta_de_dados)
    try:
        with open(caminho, "r", encoding="utf-8") as arquivo:
            existente = arquivo.read().strip()
        if existente:
            return existente
    except OSError:
        pass

    token = gerar_token()
    try:
        os.makedirs(pasta_de_dados, exist_ok=True)
        # O_EXCL nao serve aqui: duas aberturas simultaneas do app produziriam
        # uma excecao em vez de convergirem. Escreve e, se outro chegou antes,
        # a proxima leitura devolve o dele.
        with open(caminho, "w", encoding="utf-8") as arquivo:
            arquivo.write(token)
        _restringir_permissoes(caminho)
    except OSError as erro:
        log.warning("[CAPACIDADE] Nao foi possivel gravar %s: %s", caminho, erro)
    return token


def _restringir_permissoes(caminho: str) -> None:
    """Deixa o arquivo legivel so pelo dono, onde o sistema permite."""
    try:
        os.chmod(caminho, 0o600)
    except OSError:
        # No Windows o chmod so mexe no atributo somente-leitura; a protecao
        # real vem da ACL do perfil do usuario. Falhar aqui nao e motivo para
        # derrubar nada.
        pass
