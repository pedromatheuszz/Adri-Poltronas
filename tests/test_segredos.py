"""
Cofre das credenciais de integracao.

`MP_ACCESS_TOKEN` e `GEMINI_API_KEY` viviam em texto puro em
`%APPDATA%\\AdriPoltronas\\.env`. Qualquer processo rodando como o mesmo
usuario -- e qualquer pessoa que abrisse a pasta -- lia as chaves. A do Mercado Pago,
em producao, movimenta dinheiro de verdade.

Os tokens da Microsoft ja eram cifrados com DPAPI desde a 1.0; as chaves de
integracao ficaram de fora, e nao havia motivo tecnico: e a mesma
infraestrutura.

O que estes testes protegem:

* que a chave sai mesmo do texto claro, e nao apenas ganha uma copia cifrada;
* que o `.env` original e preservado antes de ser reescrito -- mexer na
  configuracao do usuario sem deixar volta seria trocar um risco por outro;
* que a precedencia nao se inverte: ambiente vence cofre, cofre vence arquivo.
"""
import os
import sys

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(RAIZ, 'backend'))

import segredos  # noqa: E402


@pytest.fixture(autouse=True)
def cofre_isolado(tmp_path, monkeypatch):
    """
    %APPDATA% proprio por teste.

    Sem isso os testes escreveriam no cofre real do desenvolvedor -- e um
    teste que mexe em credencial de verdade e um teste que ninguem quer
    rodar.
    """
    monkeypatch.setenv('APPDATA', str(tmp_path))
    (tmp_path / "AdriPoltronas").mkdir()
    monkeypatch.setattr(segredos, '_cache', None)
    monkeypatch.setattr(segredos, '_origem_env', set())
    yield tmp_path
    monkeypatch.setattr(segredos, '_cache', None)


def _escrever_env(pasta, conteudo: str) -> str:
    caminho = os.path.join(str(pasta), "AdriPoltronas", ".env")
    with open(caminho, "w", encoding="utf-8") as arquivo:
        arquivo.write(conteudo)
    return caminho


ENV_COM_SEGREDOS = """# Configuracao do Adri Poltronas.
ADRI_FLASK_SECRET=segredo-de-sessao
GEMINI_API_KEY=AIzaSyFALSA
MP_ACCESS_TOKEN=APP_USR-FALSA
"""


# =============================================================================
# Ida e volta
# =============================================================================
def test_grava_cifrado_e_le_de_volta(cofre_isolado):
    assert segredos.gravar({'MP_ACCESS_TOKEN': '$aact_prod_XYZ'}) is True

    with open(segredos.caminho_do_cofre(), encoding="utf-8") as arquivo:
        bruto = arquivo.read()

    # A propriedade que importa: o valor NAO aparece no arquivo.
    assert '$aact_prod_XYZ' not in bruto
    assert 'MP_ACCESS_TOKEN=' in bruto

    segredos._cache = None
    assert segredos.obter('MP_ACCESS_TOKEN') == '$aact_prod_XYZ'


def test_gravar_preserva_as_chaves_que_ja_estavam(cofre_isolado):
    """Gravar uma credencial nao pode apagar as outras -- seria trocar a
    protecao de uma pela perda das demais."""
    segredos.gravar({'MP_ACCESS_TOKEN': 'primeira'})
    segredos.gravar({'GEMINI_API_KEY': 'segunda'})

    segredos._cache = None
    assert segredos.obter('MP_ACCESS_TOKEN') == 'primeira'
    assert segredos.obter('GEMINI_API_KEY') == 'segunda'


def test_cofre_inexistente_nao_quebra_a_leitura(cofre_isolado):
    assert segredos.obter('MP_ACCESS_TOKEN') == ''
    assert segredos.obter('MP_ACCESS_TOKEN', 'padrao') == 'padrao'


def test_cofre_corrompido_nao_derruba_o_aplicativo(cofre_isolado):
    """Perder uma credencial e ruim; nao abrir e pior."""
    with open(segredos.caminho_do_cofre(), "w", encoding="utf-8") as arquivo:
        arquivo.write("MP_ACCESS_TOKEN=DPAPI1:bytes-que-nao-decifram\n")

    segredos._cache = None
    assert segredos.obter('MP_ACCESS_TOKEN') == ''


def test_no_app_empacotado_o_cofre_recusa_valor_em_texto_claro(cofre_isolado, monkeypatch):
    """
    Contrato do `security.decifrar`: em producao, valor sem prefixo de
    cifragem e RECUSADO -- melhor a integracao parar de funcionar, com o
    motivo no log, do que o sistema tratar como normal um segredo em claro
    onde deveria haver um cifrado.

    Em desenvolvimento o mesmo valor e aceito, e e deliberado: facilita
    depurar sem exigir DPAPI.
    """
    import security

    with open(segredos.caminho_do_cofre(), "w", encoding="utf-8") as arquivo:
        arquivo.write("MP_ACCESS_TOKEN=chave-em-texto-puro\n")

    monkeypatch.setattr(security, 'PRODUCAO', True)
    segredos._cache = None
    assert segredos.obter('MP_ACCESS_TOKEN') == ''

    monkeypatch.setattr(security, 'PRODUCAO', False)
    segredos._cache = None
    assert segredos.obter('MP_ACCESS_TOKEN') == 'chave-em-texto-puro'


# =============================================================================
# Migracao: a chave precisa SAIR do texto claro
# =============================================================================
def test_migracao_tira_a_chave_do_env(cofre_isolado):
    caminho = _escrever_env(cofre_isolado, ENV_COM_SEGREDOS)

    migradas = segredos.migrar_do_env(caminho)

    assert sorted(migradas) == ['GEMINI_API_KEY', 'MP_ACCESS_TOKEN']

    with open(caminho, encoding="utf-8") as arquivo:
        depois = arquivo.read()

    # A regressao central: uma copia cifrada nao adianta se o texto claro
    # continua la.
    assert 'AIzaSyFALSA' not in depois
    assert '$aact_hmlg_FALSA' not in depois
    # E o operador precisa entender para onde a chave foi.
    assert '.segredos' in depois


def test_migracao_preserva_o_que_nao_e_credencial(cofre_isolado):
    """`ADRI_FLASK_SECRET` e segredo de sessao, regeneravel, e perde-lo custa
    apenas relogin -- entao ele fica no `.env`, e nao vai para o cofre."""
    caminho = _escrever_env(cofre_isolado, ENV_COM_SEGREDOS)
    segredos.migrar_do_env(caminho)

    with open(caminho, encoding="utf-8") as arquivo:
        depois = arquivo.read()

    assert 'ADRI_FLASK_SECRET=segredo-de-sessao' in depois


def test_migracao_nao_deixa_copia_em_texto_claro_para_tras(cofre_isolado):
    """
    A copia de seguranca existe para proteger a REESCRITA do `.env`, e so.

    Cumprida essa funcao, ela vira o oposto do que o cofre faz: um arquivo
    permanente, em texto puro, na mesma pasta do banco, com o `MP_ACCESS_TOKEN`
    -- que da acesso total a conta do vendedor no Mercado Pago -- ao lado da
    versao cifrada. O trabalho de cifrar ficava metade desfeito, e para sempre.
    """
    caminho = _escrever_env(cofre_isolado, ENV_COM_SEGREDOS)
    segredos.migrar_do_env(caminho)

    assert not os.path.exists(caminho + ".bak")
    # E a chave continua recuperavel -- apagar a copia so vale se o cofre
    # cumprir o papel dela.
    segredos._cache = None
    assert segredos.obter('MP_ACCESS_TOKEN') == 'APP_USR-FALSA'
    assert segredos.obter('GEMINI_API_KEY') == 'AIzaSyFALSA'


def test_a_copia_e_mantida_se_o_cofre_nao_confere(cofre_isolado, monkeypatch):
    """
    O risco oposto, e o motivo de a conferencia por releitura existir.

    Cofre legivel, mas devolvendo outra coisa: arquivo corrompido, gravacao
    parcial, colisao de nome. Diante de qualquer divergencia, a copia fica.

    O monkeypatch e em `_ler_cofre` porque e ele que a conferencia consulta.
    Antes este teste substituia `obter`, e passou a valer nada no dia em que a
    conferencia deixou de usa-la -- um stub inerte nao acusa nada.
    """
    caminho = _escrever_env(cofre_isolado, ENV_COM_SEGREDOS)
    monkeypatch.setattr(segredos, '_ler_cofre', lambda: {'MP_ACCESS_TOKEN': 'outra-coisa'})

    segredos.migrar_do_env(caminho)

    with open(caminho + ".bak", encoding="utf-8") as arquivo:
        assert arquivo.read() == ENV_COM_SEGREDOS


def test_a_copia_e_mantida_quando_o_dpapi_nao_decifra_de_volta(cofre_isolado, monkeypatch):
    """
    A falha REAL, que o teste acima nao alcancava.

    Aquele faz monkeypatch da propria `obter`, entao exercita o ramo do `if
    divergentes` -- nao o mecanismo de leitura. E era justamente o mecanismo
    que estava errado: a conferencia usava `obter()`, cujo ultimo degrau e
    `return do_ambiente_real or padrao`. Em producao o `load_dotenv()` ja pos
    as chaves em `os.environ` com o mesmo valor que esta sendo migrado, entao
    um cofre ilegivel ainda "conferia" -- e o backup ia embora junto com a
    unica copia recuperavel.

    Aqui a falha e simulada onde ela acontece de verdade: a gravacao funciona,
    a releitura nao decifra. E as chaves estao no ambiente, como estariam.
    """
    import security

    caminho = _escrever_env(cofre_isolado, ENV_COM_SEGREDOS)
    monkeypatch.setenv('GEMINI_API_KEY', 'AIzaSyFALSA')
    monkeypatch.setenv('MP_ACCESS_TOKEN', 'APP_USR-FALSA')
    segredos.registrar_origem_env({'GEMINI_API_KEY', 'MP_ACCESS_TOKEN'})

    original = security.decifrar
    estado = {'gravou': False}

    def decifrar_que_falha_depois_de_gravar(valor):
        # Deixa a gravacao acontecer; quebra so na releitura da conferencia.
        if estado['gravou']:
            return None
        return original(valor)

    def gravar_e_marcar(valores):
        resultado = segredos_gravar_original(valores)
        estado['gravou'] = True
        return resultado

    segredos_gravar_original = segredos.gravar
    monkeypatch.setattr(segredos, 'gravar', gravar_e_marcar)
    monkeypatch.setattr(security, 'decifrar', decifrar_que_falha_depois_de_gravar)

    segredos.migrar_do_env(caminho)

    assert os.path.exists(caminho + ".bak"), (
        "o cofre nao devolveu as chaves e a copia em texto claro foi apagada assim mesmo"
    )
    with open(caminho + ".bak", encoding="utf-8") as arquivo:
        assert arquivo.read() == ENV_COM_SEGREDOS


def test_migracao_e_idempotente(cofre_isolado):
    """Roda a cada abertura do app. A segunda passada nao tem o que fazer."""
    caminho = _escrever_env(cofre_isolado, ENV_COM_SEGREDOS)
    primeira = segredos.migrar_do_env(caminho)
    segunda = segredos.migrar_do_env(caminho)

    assert primeira
    assert segunda == []


def test_chave_nova_colada_depois_tambem_e_migrada(cofre_isolado):
    """
    O modelo gravado em %APPDATA% convida o operador a colar chave no `.env`.
    Sem uma passada por boot, a chave nova ficaria em claro para sempre.
    """
    # O `.env` inicial NAO traz a chave que sera colada -- senao a primeira
    # passada ja a migraria, e a segunda (que e o objeto do teste) nao teria o
    # que fazer.
    caminho = _escrever_env(
        cofre_isolado, "ADRI_FLASK_SECRET=segredo\nGEMINI_API_KEY=AIzaSyFALSA\n"
    )
    assert segredos.migrar_do_env(caminho) == ['GEMINI_API_KEY']

    with open(caminho, "a", encoding="utf-8") as arquivo:
        arquivo.write("\nMP_ACCESS_TOKEN=colado-depois\n")

    assert segredos.migrar_do_env(caminho) == ['MP_ACCESS_TOKEN']

    segredos._cache = None
    assert segredos.obter('MP_ACCESS_TOKEN') == 'colado-depois'
    with open(caminho, encoding="utf-8") as arquivo:
        assert 'colado-depois' not in arquivo.read()


def test_env_sem_credencial_nao_e_tocado(cofre_isolado):
    caminho = _escrever_env(cofre_isolado, "ADRI_FLASK_SECRET=so-isso\n")

    assert segredos.migrar_do_env(caminho) == []
    assert not os.path.exists(caminho + ".bak"), "reescreveu um arquivo que nao precisava"


def test_env_inexistente_nao_quebra(cofre_isolado):
    assert segredos.migrar_do_env(os.path.join(str(cofre_isolado), "nao-existe.env")) == []
    assert segredos.migrar_do_env("") == []


def test_valor_comentado_nao_e_migrado(cofre_isolado):
    """Uma linha comentada e uma chave que o operador desativou de proposito."""
    caminho = _escrever_env(cofre_isolado, "# MP_ACCESS_TOKEN=antiga\nADRI_BACKUP_EXTRA=D:/copias\n")

    assert segredos.migrar_do_env(caminho) == []


# =============================================================================
# Precedencia
# =============================================================================
def test_ambiente_injetado_vence_o_cofre(cofre_isolado, monkeypatch):
    """
    E como o CI, a suite e um operador testando uma chave nova injetam
    valores sem gravar nada.
    """
    segredos.gravar({'MP_ACCESS_TOKEN': 'do-cofre'})
    monkeypatch.setenv('MP_ACCESS_TOKEN', 'injetada')

    segredos._cache = None
    assert segredos.obter('MP_ACCESS_TOKEN') == 'injetada'


def test_cofre_vence_o_que_veio_do_arquivo(cofre_isolado, monkeypatch):
    """
    Durante a migracao as duas fontes coexistem. Se o `.env` vencesse, a
    versao cifrada nunca seria usada -- e o cofre viraria enfeite.
    """
    segredos.gravar({'MP_ACCESS_TOKEN': 'do-cofre'})
    # Simula o que `load_dotenv` faz: coloca em os.environ e anota a origem.
    monkeypatch.setenv('MP_ACCESS_TOKEN', 'do-arquivo')
    segredos.registrar_origem_env({'MP_ACCESS_TOKEN'})

    segredos._cache = None
    assert segredos.obter('MP_ACCESS_TOKEN') == 'do-cofre'


def test_arquivo_vale_quando_o_cofre_esta_vazio(cofre_isolado, monkeypatch):
    """Compatibilidade com instalacao que ainda nao migrou."""
    monkeypatch.setenv('GEMINI_API_KEY', 'do-arquivo')
    segredos.registrar_origem_env({'GEMINI_API_KEY'})

    assert segredos.obter('GEMINI_API_KEY') == 'do-arquivo'


# =============================================================================
# O que o cofre guarda
# =============================================================================
def test_apenas_credenciais_de_integracao_sao_protegidas():
    """
    `ADRI_FLASK_SECRET` fica de fora de proposito: e um segredo de sessao,
    regeneravel, e perde-lo custa apenas relogin. Proteger tudo indistinta-
    mente tornaria a recuperacao de uma instalacao mais dificil sem ganho.
    """
    assert set(segredos.CHAVES_PROTEGIDAS) == {
        'MP_ACCESS_TOKEN', 'GEMINI_API_KEY', }
    assert 'ADRI_FLASK_SECRET' not in segredos.CHAVES_PROTEGIDAS


def test_o_cofre_fica_junto_do_banco_e_dos_logs(cofre_isolado):
    caminho = segredos.caminho_do_cofre()
    assert caminho.endswith(os.path.join("AdriPoltronas", ".segredos"))
    assert str(cofre_isolado) in caminho
