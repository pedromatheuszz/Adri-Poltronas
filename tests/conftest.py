"""
Preparo comum da suite.

A suite precisava de Windows para passar limpa. Tres testes de Fernet
dependiam de uma chave que `security._obter_chave_fernet()` so consegue de duas
fontes: a variavel `FERNET_KEY` ou o DPAPI. Sem nenhuma das duas ela levanta
RuntimeError, e fora do Windows o resultado era `3 failed, 549 passed`.

Como a CI roda em `windows-latest`, isso passava despercebido -- e o custo caia
inteiro sobre quem tentasse auditar ou contribuir de outra maquina: a primeira
execucao da suite ja vem com tres falhas vermelhas que nao tem nada a ver com o
que a pessoa mudou.

A chave efemera resolve por execucao. Preferi isso a um `skipif`: pular deixa o
caminho Fernet SEM COBERTURA fora do Windows, que e justamente onde ele e o
unico mecanismo de cifragem disponivel. Com a chave, o teste roda de verdade em
qualquer sistema.

De quebra, fecha um incomodo que existia tambem no Windows: com DPAPI
disponivel, `_obter_chave_fernet()` le e ate CRIA
`%APPDATA%\\AdriPoltronas\\.fernet_key` -- o arquivo de chave real do
desenvolvedor. Rodar a suite nao deveria tocar em nada disso.
"""
import atexit
import logging
import os
import shutil
import socket
import sys
import tempfile

import dotenv.main
import pytest
from cryptography.fernet import Fernet

# -----------------------------------------------------------------------------
# A SUITE NAO TOCA O PERFIL DE QUEM A EXECUTA
#
# Tudo abaixo roda no import deste arquivo, ANTES de qualquer modulo do
# backend ser carregado -- e a ordem e o ponto. `database`, `app`, `config` e
# `segredos` resolvem caminhos a partir de `APPDATA` no momento do import ou da
# primeira chamada; depois disso, trocar a variavel ja nao muda para onde o log
# escreve nem onde o banco padrao mora.
#
# Sem este isolamento, rodar a suite na maquina de quem tambem usa o
# aplicativo:
#   * escrevia em `%APPDATA%\AdriPoltronas\logs\app.log` de verdade;
#   * lia o cofre real `.segredos` -- inclusive o token administrativo da API
#     central, entregue aos dubles de rede -- e podia regrava-lo;
#   * carregava o `.env` do checkout (DATABASE_URL de producao, chave do
#     Render) para dentro de `os.environ` do processo de teste.
# Na CI nada disso existe, entao a suite se comportava de um jeito la e de
# outro na maquina do desenvolvedor.
# -----------------------------------------------------------------------------
_PERFIL_DA_SUITE = tempfile.mkdtemp(prefix='adri-suite-')
os.environ['APPDATA'] = _PERFIL_DA_SUITE
# Um ADRI_DB_PATH herdado do terminal apontaria os testes que nao definem o
# proprio banco para um arquivo que ninguem escolheu.
os.environ.pop('ADRI_DB_PATH', None)

# `load_dotenv()` sem argumento procura um `.env` subindo a partir do arquivo
# que o chamou -- e acha o da raiz do checkout. Devolver vazio aqui desliga
# so essa descoberta: o carregamento por caminho explicito (o `.env` do
# usuario em %APPDATA%, que varios testes exercitam) continua funcionando.
dotenv.main.find_dotenv = lambda *_args, **_kwargs: ''


def _descartar_perfil_da_suite() -> None:
    # O `app.log` fica aberto pelo handler ate o logging encerrar; no Windows
    # um arquivo aberto nao e apagado, e a pasta ficaria para tras a cada
    # execucao.
    logging.shutdown()
    shutil.rmtree(_PERFIL_DA_SUITE, ignore_errors=True)


atexit.register(_descartar_perfil_da_suite)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

_HOSTS_LOCAIS = frozenset({'127.0.0.1', '::1', 'localhost', ''})


@pytest.fixture(autouse=True)
def sem_rede_externa(monkeypatch):
    """
    Nenhum teste fala com a internet.

    O que se quer medir e o codigo, nao a disponibilidade do ViaCEP, do ipify
    ou da API central. Um teste que alcanca a rede passa ou falha conforme o
    wifi de quem o roda -- e, pior, pode enviar a um servico de verdade algo
    que saiu do ambiente local. Loopback continua liberado: e por ele que o
    Playwright e o proprio asyncio conversam.

    A recusa e um `OSError`, o mesmo que a rede fora do ar produz. O codigo
    que trata queda de conexao segue pelo caminho que ja tem; o que nao trata
    falha com uma mensagem que diz exatamente o que foi tentado.
    """
    resolver_original = socket.getaddrinfo
    conectar_original = socket.socket.connect

    def resolver(host, *args, **kwargs):
        nome = host.decode() if isinstance(host, bytes) else (host or '')
        if nome not in _HOSTS_LOCAIS:
            raise socket.gaierror(
                f"A suite nao acessa a rede: tentativa de resolver {nome!r}.")
        return resolver_original(host, *args, **kwargs)

    def conectar(self, endereco):
        if isinstance(endereco, tuple) and endereco and endereco[0] not in _HOSTS_LOCAIS:
            raise OSError(
                f"A suite nao acessa a rede: tentativa de conexao a {endereco[0]!r}.")
        return conectar_original(self, endereco)

    monkeypatch.setattr(socket, 'getaddrinfo', resolver)
    monkeypatch.setattr(socket.socket, 'connect', conectar)


@pytest.fixture(scope='session', autouse=True)
def chave_fernet_da_suite():
    """
    Garante uma `FERNET_KEY` valida durante toda a execucao.

    Uma `FERNET_KEY` ja definida no ambiente e respeitada: quem a define quer
    exercitar aquela chave especifica, e sobrescreve-la mudaria o que o teste
    mede.
    """
    import security

    definida_de_fora = bool(os.environ.get('FERNET_KEY'))
    if not definida_de_fora:
        os.environ['FERNET_KEY'] = Fernet.generate_key().decode()

    # O cache e populado na primeira cifragem e nao releria o ambiente depois.
    anterior = security._fernet_key_cache
    security._fernet_key_cache = None

    yield

    security._fernet_key_cache = anterior
    if not definida_de_fora:
        os.environ.pop('FERNET_KEY', None)


@pytest.fixture
def semear_parcela():
    """
    Insere uma parcela a receber direto no banco, para preparar cenario.

    Em producao quem cria linha em `pagamentos` e o faturamento de pedido
    (`erp.comercial.repositorio.inserir_parcela`), e so ele. Antes existia um
    `database.salvar_pagamento()` de uso geral que os testes chamavam para
    montar cenario -- mas ele nao tinha chamador nenhum em producao desde a
    remocao do financeiro na 1.5.0, e foi apagado junto com o resto do modulo
    morto.

    O preparo, porem, continua sendo necessario: varios testes precisam de uma
    parcela pendente sem querer exercitar um pedido inteiro so para chegar la.
    Um INSERT explicito diz o que e -- montagem de estado, nao uso de API --
    em vez de manter viva uma funcao de producao que ninguem chama.
    """
    import database

    def _semear(cliente_id, cliente_nome="Cliente", valor_centavos=12050,
                descricao="Sinal", data_vencimento="2030-01-01",
                status="Pendente", pedido_id=None):
        with database.conectar() as conexao:
            cursor = conexao.execute(
                """INSERT INTO pagamentos
                       (cliente_id, cliente_nome, valor, valor_centavos, descricao,
                        data_vencimento, tipo_pagamento, status, pedido_id)
                   VALUES (?, ?, ?, ?, ?, ?, 'Pix', ?, ?)""",
                (cliente_id, cliente_nome, valor_centavos / 100, valor_centavos,
                 descricao, data_vencimento, status, pedido_id),
            )
            return cursor.lastrowid

    return _semear
