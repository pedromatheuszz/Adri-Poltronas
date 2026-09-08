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
