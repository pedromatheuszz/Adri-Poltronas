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

Por que a ausencia da variavel nao desliga mais nada
---------------------------------------------------
Ate a 1.3.0 `esta_ativa()` devolvia False quando `ADRI_API_TOKEN` nao estava
no ambiente, e o guarda entao liberava a API inteira com um aviso no log. Isso
e um fail-open: bastava o Electron falhar em repassar a variavel ao processo
filho -- erro de spawn, antivirus no meio do caminho, backend orfao
reaproveitado de outra execucao -- para o servidor subir com tudo aberto, e
nada na interface indicava isso.

Agora a exigencia e sempre ligada. Quando a variavel nao vem pronta, o proprio
backend le (ou cria) o token no perfil do usuario -- o mesmo arquivo que o
Electron ja usa, entao os dois convergem para o mesmo segredo sem precisarem
conversar. Desligar virou opt-in explicito por `ADRI_API_SEM_TOKEN=1`, com
aviso no log e visivel em `/api/health`, e serve apenas para rodar
`python backend/servidor.py` sozinho no terminal.
"""
from __future__ import annotations

import hmac
import logging
import os
import secrets

log = logging.getLogger("adri.capacidade")

VARIAVEL_DE_AMBIENTE = "ADRI_API_TOKEN"

# Unica forma de desligar a exigencia. Existe para o desenvolvimento local, e
# e deliberadamente feia de escrever: quem a define esta abrindo a API para
# qualquer processo da maquina e precisa saber disso.
VARIAVEL_DE_DESLIGAMENTO = "ADRI_API_SEM_TOKEN"

NOME_DO_HEADER = "X-Adri-Capacidade"
NOME_DO_COOKIE = "adri_capacidade"
NOME_DO_ARQUIVO = ".capacidade"

# 32 bytes em hexadecimal. Curto demais e adivinhavel; mais que isso so
# engorda o cabecalho de toda requisicao.
BYTES_DO_TOKEN = 32

# Rotas que precisam responder sem o token, e por que cada uma:
#
#   /callback -- o redirect do OAuth Microsoft chega pelo navegador do
#       sistema, que nao tem como carregar o cabecalho. Nao expoe dado: so
#       troca o `code` por token.
#   /api/health -- e a sonda de identidade. Precisa responder para que o
#       Electron consiga descobrir SE o servidor na porta e este aplicativo e
#       se aceita a capacidade apresentada. Nao devolve dado de negocio.
ROTAS_ISENTAS = frozenset({
    "/callback",
    "/api/health",
})


# Token de reserva ja lido do disco, por pasta de dados. Sem isto,
# `token_esperado()` -- que roda em toda requisicao, dentro de `confere()` --
# abriria o arquivo do perfil a cada chamada.
_reserva_por_pasta: dict = {}


def desligada_explicitamente() -> bool:
    """Verdadeiro so quando alguem pediu, por escrito, para abrir a API."""
    return (os.environ.get(VARIAVEL_DE_DESLIGAMENTO) or "").strip() == "1"


def pasta_do_perfil() -> str:
    """
    Pasta onde vive o token de reserva: a mesma do banco.

    O import e tardio de proposito. `capacidade` e um modulo de funcoes puras
    que `app.py` carrega cedo; amarra-lo no topo a `database`, que abre o
    SQLite e puxa meia dezena de modulos de dominio, inverteria essa ordem sem
    necessidade.
    """
    import database
    return os.path.dirname(os.path.abspath(database.obter_caminho_banco()))


def _token_de_reserva() -> str:
    pasta = pasta_do_perfil()
    token = _reserva_por_pasta.get(pasta)
    if token is None:
        token = carregar_ou_criar(pasta)
        _reserva_por_pasta[pasta] = token
    return token


def token_esperado() -> str:
    """
    Token desta execucao, ou string vazia quando a exigencia esta desligada.

    A variavel de ambiente e o caminho normal: o Electron gera o token e o
    passa ao processo filho. Quando ela nao chega, cair no arquivo do perfil e
    o que impede a falha de virar liberacao geral -- o Electron le esse mesmo
    arquivo, entao na pratica os dois continuam falando o mesmo segredo.
    """
    if desligada_explicitamente():
        return ""
    do_ambiente = (os.environ.get(VARIAVEL_DE_AMBIENTE) or "").strip()
    if do_ambiente:
        return do_ambiente
    return _token_de_reserva()


# `esta_ativa()` roda em todo request. O aviso de desligamento sai uma vez por
# processo: repetido por requisicao ele afogaria o log justamente na execucao
# em que ha algo errado para ler nele.
_desligamento_ja_avisado = False


def esta_ativa() -> bool:
    """
    A exigencia so cai por pedido explicito.

    Antes isto era `bool(token_esperado())`, o que transformava "a variavel nao
    chegou" em "pode entrar sem token". Ver o cabecalho do modulo.
    """
    global _desligamento_ja_avisado
    if desligada_explicitamente():
        if not _desligamento_ja_avisado:
            log.warning(
                "[CAPACIDADE] Exigencia DESLIGADA por %s=1. A API responde a "
                "qualquer processo da maquina.", VARIAVEL_DE_DESLIGAMENTO
            )
            _desligamento_ja_avisado = True
        return False
    return True


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
