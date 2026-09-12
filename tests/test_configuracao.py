"""
O `.env.example` nao pode prometer protecao que nao existe.

Ate a 1.5.0 ele documentava, sob o cabecalho "SEGURANCA AVANCADA (opcional)",
cinco variaveis que nenhuma linha do backend lia: ADRI_HMAC_SECRET,
ADRI_ALLOWED_IPS, ADRI_SESSION_TIMEOUT, ADRI_LOGIN_ATTEMPTS e
ADRI_REQUEST_TIMEOUT.

O dano nao e teorico. Um operador que lesse

    # IP permitido para acesso (opcional - deixe vazio para permitir todos)
    # ADRI_ALLOWED_IPS=127.0.0.1,::1

e escrevesse `ADRI_ALLOWED_IPS=127.0.0.1` sairia acreditando ter restringido o
acesso por IP. Nao restringiu nada, e nada no sistema lhe diria isso. O mesmo
vale para `ADRI_LOGIN_ATTEMPTS=3`.

Configuracao que promete e nao entrega e pior do que configuracao ausente: ela
calibra a confianca errado. E faz isso no arquivo que mais circula -- o modelo
que se copia para montar uma instalacao nova.

Este teste e barato e cobre a classe inteira: qualquer variavel `ADRI_` ou
`MP_` documentada aqui precisa aparecer em `backend/`.
"""
import os
import re

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MODELO = os.path.join(RAIZ, '.env.example')
BACKEND = os.path.join(RAIZ, 'backend')

# Prefixos que o proprio projeto define e portanto tem de ler em algum lugar.
# Nomes de terceiros (PATH, APPDATA) ficam de fora: quem os le e o sistema.
PREFIXOS_DO_PROJETO = ('ADRI_', 'MP_', 'GEMINI_', 'FERNET_')


def _nomes_documentados() -> set:
    """
    Toda variavel citada no modelo, comentada ou nao.

    A linha comentada conta: e a forma mais comum de documentar uma opcao, e
    foi exatamente assim que quatro das cinco variaveis fantasma estavam la.
    """
    nomes = set()
    with open(MODELO, encoding='utf-8') as arquivo:
        for linha in arquivo:
            achado = re.match(r'\s*#?\s*([A-Z][A-Z0-9_]*)\s*=', linha)
            if achado:
                nomes.add(achado.group(1))
    return nomes


def _fonte_do_backend() -> str:
    partes = []
    for pasta, _subpastas, arquivos in os.walk(BACKEND):
        if '__pycache__' in pasta:
            continue
        for nome in arquivos:
            if nome.endswith('.py'):
                with open(os.path.join(pasta, nome), encoding='utf-8') as arquivo:
                    partes.append(arquivo.read())
    return '\n'.join(partes)


def test_o_modelo_documenta_variaveis_de_verdade():
    """Se esta aqui, alguem tem de ler."""
    fonte = _fonte_do_backend()
    orfas = {
        nome for nome in _nomes_documentados()
        if nome.startswith(PREFIXOS_DO_PROJETO) and nome not in fonte
    }

    assert not orfas, (
        "O .env.example documenta variaveis que nenhum codigo le -- o operador "
        f"vai crer numa protecao que nao existe: {sorted(orfas)}"
    )


def test_o_modelo_nao_carrega_valor_de_credencial():
    """
    Este arquivo ja vazou uma chave real do Gemini uma vez. O gitleaks pega o
    formato conhecido; este teste pega o caso generico -- qualquer credencial
    com valor preenchido.
    """
    credenciais = {'GEMINI_API_KEY', 'MP_ACCESS_TOKEN', 'ADRI_FLASK_SECRET', 'FERNET_KEY'}
    preenchidas = []

    with open(MODELO, encoding='utf-8') as arquivo:
        for numero, linha in enumerate(arquivo, start=1):
            if linha.lstrip().startswith('#'):
                continue
            achado = re.match(r'\s*([A-Z][A-Z0-9_]*)\s*=\s*(\S.*)', linha)
            if achado and achado.group(1) in credenciais:
                preenchidas.append(f"linha {numero}: {achado.group(1)}")

    assert not preenchidas, f"credencial com valor no arquivo versionado: {preenchidas}"


def test_as_variaveis_essenciais_continuam_documentadas():
    """
    O inverso do primeiro teste: apagar do modelo o que o codigo LE deixaria
    quem monta uma instalacao nova sem saber o que preencher.
    """
    documentadas = _nomes_documentados()
    essenciais = {'ADRI_FLASK_SECRET', 'ADRI_MICROSOFT_CLIENT_ID',
                  'GEMINI_API_KEY', 'MP_ACCESS_TOKEN', 'ADRI_DB_PATH'}

    assert essenciais <= documentadas, (
        f"sumiram do .env.example: {sorted(essenciais - documentadas)}")


# =============================================================================
# O modelo do repositorio e o modelo da instalacao precisam concordar
# =============================================================================
# `.env.example` fica no repositorio e NAO entra no bundle -- o `.spec` empacota
# `frontend`, `templates`, `alembic.ini`, `migrations` e `package.json`, mais
# nada. O unico arquivo de configuracao que existe numa maquina instalada e o
# que `config.garantir_modelo_env()` escreve em %APPDATA% na primeira execucao.
#
# A allowlist de contas nasceu documentada so no `.env.example`. O resultado e
# pior que nao ter o recurso: o codigo da a impressao de que a autorizacao esta
# resolvida, e na maquina onde ela importa nao ha nada que revele que existe.
CONFIGURAVEIS_NA_INSTALACAO = {
    'ADRI_FLASK_SECRET',
    'ADRI_CONTAS_AUTORIZADAS',
    'ADRI_BACKUP_EXTRA',
    'GEMINI_API_KEY',
    'MP_ACCESS_TOKEN',
}

# Variaveis que existem so para desenvolvimento ou teste e nao fazem sentido no
# modelo da cliente. Ficam listadas para que a ausencia seja deliberada, e nao
# esquecimento.
SO_PARA_DESENVOLVIMENTO = {
    'ADRI_DB_PATH',            # aponta o banco para outro lugar
    'MP_API_URL',              # duble local do Mercado Pago
    'ADRI_MICROSOFT_CLIENT_ID',  # troca a aplicacao Azure
    'ADRI_API_SEM_TOKEN',      # desliga a capacidade, para o `make dev`
    'FERNET_KEY',              # chave injetada pela suite
}


def _modelo_da_instalacao() -> set:
    import sys
    sys.path.insert(0, BACKEND)
    import config

    nomes = set()
    for linha in config._MODELO_ENV.splitlines():
        achado = re.match(r'\s*#?\s*([A-Z][A-Z0-9_]*)\s*=', linha)
        if achado:
            nomes.add(achado.group(1))
    return nomes


def test_o_modelo_da_instalacao_oferece_o_que_a_cliente_precisa_configurar():
    faltando = CONFIGURAVEIS_NA_INSTALACAO - _modelo_da_instalacao()
    assert not faltando, (
        f"{sorted(faltando)} so existe no .env.example, que nao vai para a maquina "
        "instalada. Acrescente ao config._MODELO_ENV."
    )


def test_o_modelo_da_instalacao_nao_inventa_variavel():
    """O caminho inverso: nada no modelo que o backend nao leia."""
    fonte = _fonte_do_backend()
    orfas = {
        nome for nome in _modelo_da_instalacao()
        if nome.startswith(PREFIXOS_DO_PROJETO) and nome not in fonte
    }
    assert not orfas, f"o modelo da instalacao documenta o que ninguem le: {sorted(orfas)}"


def test_toda_variavel_do_env_example_esta_classificada():
    """
    Impede o esquecimento silencioso: uma variavel nova no `.env.example` tem de
    ser declarada como configuravel na instalacao OU como so-para-desenvolvimento.
    Sem isso, a proxima allowlist repete a mesma historia.
    """
    documentadas = {n for n in _nomes_documentados() if n.startswith(PREFIXOS_DO_PROJETO)}
    classificadas = CONFIGURAVEIS_NA_INSTALACAO | SO_PARA_DESENVOLVIMENTO
    assert not (documentadas - classificadas), (
        f"{sorted(documentadas - classificadas)} nao foi classificada. Decida se vai "
        "para o modelo da instalacao e acrescente ao conjunto correspondente."
    )
