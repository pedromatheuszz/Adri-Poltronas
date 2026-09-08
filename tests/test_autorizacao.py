"""
Quem pode destravar a base.

Ate a 1.5.0 a resposta era: qualquer conta Microsoft. O guarda de autenticacao
aceitava qualquer linha na tabela `sessao` com token nao vazio, sem olhar de
QUEM era a conta, e o fluxo OAuth usa o endpoint `/common`, que aceita conta
pessoal ou de qualquer tenant.

A explorabilidade sempre foi baixa, e o motivo vale registrar: quem chega a
`/api/auth/login` ja precisa do token de capacidade, que vive em %APPDATA%, e
quem le esse arquivo ja poderia abrir o SQLite direto. Quem protege de fato e a
capacidade -- a autenticacao era decorativa.

O risco e operacional: um colaborador conecta a conta pessoal e passa a ser,
para todos os efeitos do sistema, o mesmo que o dono. Faturar, restaurar backup
e baixar o banco completo tem exatamente a mesma permissao que listar clientes.

Este e o degrau 1 dos tres que a auditoria propoe -- o mais barato, que fecha o
cenario concreto. Os degraus 2 (identidade propria, desacoplada do OneDrive) e
3 (papeis: operacao x administracao) continuam abertos e sao decisao de produto.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import config  # noqa: E402


@pytest.fixture
def allowlist(monkeypatch):
    """Define a allowlist como se viesse do ambiente."""
    def _definir(*contas):
        conjunto = frozenset(c.strip().casefold() for c in contas if c.strip())
        monkeypatch.setattr(config, 'CONTAS_AUTORIZADAS', conjunto)
    return _definir


# =============================================================================
# A regra
# =============================================================================
def test_sem_allowlist_qualquer_conta_passa(allowlist):
    """
    Vazio significa "qualquer conta", e a escolha e deliberada.

    Ligar a restricao por padrao trancaria o dono fora do proprio aplicativo na
    primeira atualizacao, com a unica saida sendo editar um arquivo de
    configuracao que ele nao sabe que existe. Quem quer a restricao a declara.
    """
    allowlist()
    assert config.conta_autorizada('qualquer@exemplo.com')
    assert config.conta_autorizada('')


def test_conta_na_allowlist_passa(allowlist):
    allowlist('adri@exemplo.com')
    assert config.conta_autorizada('adri@exemplo.com')


def test_conta_fora_da_allowlist_e_recusada(allowlist):
    """O cenario do colaborador que conecta a conta pessoal."""
    allowlist('adri@exemplo.com')
    assert not config.conta_autorizada('colaborador@gmail.com')


def test_a_comparacao_ignora_caixa_e_espaco(allowlist):
    """
    E-mail nao diferencia maiuscula de minuscula. Recusar o dono porque ele
    digitou o proprio e-mail com inicial maiuscula seria um defeito pior do que
    o que a allowlist resolve.
    """
    allowlist('  Adri@Exemplo.COM  ')
    assert config.conta_autorizada('adri@exemplo.com')
    assert config.conta_autorizada('ADRI@EXEMPLO.COM')
    assert config.conta_autorizada(' adri@exemplo.com ')


def test_conta_vazia_e_recusada_quando_ha_allowlist(allowlist):
    """Sessao sem conta gravada nao pode virar coringa."""
    allowlist('adri@exemplo.com')
    assert not config.conta_autorizada('')
    assert not config.conta_autorizada(None)


# =============================================================================
# Como a variavel e lida
# =============================================================================
@pytest.mark.parametrize('bruto, esperado', [
    ('a@x.com', {'a@x.com'}),
    ('a@x.com,b@x.com', {'a@x.com', 'b@x.com'}),
    ('a@x.com; b@x.com', {'a@x.com', 'b@x.com'}),      # ponto e virgula tambem
    ('  A@X.com , , b@x.com  ', {'a@x.com', 'b@x.com'}),  # vazios descartados
    ('', set()),
    ('   ', set()),
])
def test_leitura_da_variavel_de_ambiente(bruto, esperado, monkeypatch):
    """
    O operador vai digitar isso a mao num arquivo de texto. Aceitar virgula e
    ponto e virgula, e tolerar espaco sobrando, custa nada e evita o suporte
    mais chato que existe: "eu configurei e nao funcionou".
    """
    monkeypatch.setenv('ADRI_CONTAS_AUTORIZADAS', bruto)
    import importlib
    recarregado = importlib.reload(config)
    try:
        assert set(recarregado.CONTAS_AUTORIZADAS) == esperado
    finally:
        monkeypatch.delenv('ADRI_CONTAS_AUTORIZADAS', raising=False)
        importlib.reload(config)
