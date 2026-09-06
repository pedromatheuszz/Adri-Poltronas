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
import os
import sys

import pytest
from cryptography.fernet import Fernet

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


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
