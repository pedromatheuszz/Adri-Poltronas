"""
Cofre das credenciais de integracao.

O problema
----------
`MP_ACCESS_TOKEN`, `GEMINI_API_KEY` e o token administrativo da licença
viviam em texto puro em
`%APPDATA%\\AdriPoltronas\\.env`. Qualquer processo rodando como o mesmo
usuario -- e qualquer pessoa que abrisse a pasta -- lia as chaves. A do
Mercado Pago da acesso total a conta do vendedor: criar cobranca, ler
movimentacao, estornar.

Os tokens da Microsoft ja eram cifrados com DPAPI desde a 1.0. As chaves de
integracao ficaram de fora, e nao havia motivo tecnico: e a mesma
infraestrutura.

Como funciona
-------------
As chaves passam a viver em `%APPDATA%\\AdriPoltronas\\.segredos`, cifradas
pelo `security.cifrar()` -- Fernet com chave protegida por DPAPI, amarrada a
conta do Windows. Copiar o arquivo para outra maquina nao serve de nada: o
DPAPI de la nao decifra.

Precedencia de leitura, e o porque de cada degrau:

    1. variavel de ambiente   -- override explicito; e como o CI e a suite
                                 injetam valores, e como um operador testa uma
                                 chave sem gravar nada
    2. cofre cifrado          -- o lugar normal
    3. .env em texto          -- compatibilidade com instalacoes anteriores,
                                 e a fonte de onde a migracao le

Migracao
--------
`migrar_do_env()` roda no boot. Encontrando chave em texto no `.env`, ela e
cifrada para o cofre e a linha do `.env` vira um comentario apontando para
onde a chave foi. O arquivo original e preservado como `.env.bak` antes de
qualquer escrita -- mexer no arquivo de configuracao do usuario sem deixar
copia seria trocar um risco por outro.

O que este modulo NAO resolve
-----------------------------
DPAPI protege contra outra conta de usuario e contra o arquivo sair da
maquina. Nao protege contra codigo rodando como o proprio usuario: esse
codigo pode simplesmente pedir ao DPAPI que decifre. Contra ele, o que vale e
cifrar o disco -- ver PRIVACIDADE.md.
"""
from __future__ import annotations

import logging
import os
import shutil

import security

log = logging.getLogger("adri.segredos")

NOME_DO_COFRE = ".segredos"

# Chaves que o cofre guarda. Sao as credenciais de integracao; `ADRI_FLASK_SECRET`
# fica de fora de proposito -- ele e um segredo de sessao, regeneravel, e
# perde-lo custa apenas relogin.
CHAVES_PROTEGIDAS = (
    "MP_ACCESS_TOKEN",
    "GEMINI_API_KEY",
    "ADRI_LICENCA_ADMIN_TOKEN",
)

_cache: dict | None = None


def caminho_do_cofre() -> str:
    """`.segredos` ao lado do `.env`, do banco e dos logs."""
    return os.path.join(
        os.environ.get("APPDATA", os.getcwd()), "AdriPoltronas", NOME_DO_COFRE
    )


def _ler_cofre() -> dict:
    """
    Le e decifra o cofre. Nunca levanta: cofre ilegivel vira cofre vazio, e a
    leitura cai para o `.env`.
    """
    global _cache
    if _cache is not None:
        return _cache

    _cache = {}
    caminho = caminho_do_cofre()
    if not os.path.exists(caminho):
        return _cache

    try:
        with open(caminho, encoding="utf-8") as arquivo:
            linhas = arquivo.read().splitlines()
    except OSError as erro:
        log.warning("[SEGREDOS] Nao foi possivel ler o cofre: %s", erro)
        return _cache

    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        nome, _, cifrado = linha.partition("=")
        valor = security.decifrar(cifrado.strip())
        if valor is None:
            # Chave cifrada para outra conta do Windows, ou arquivo corrompido.
            # Perder uma credencial e ruim; fingir que ela esta certa e pior.
            log.warning("[SEGREDOS] Nao foi possivel decifrar %s.", nome.strip())
            continue
        _cache[nome.strip()] = valor
    return _cache


def obter(nome: str, padrao: str = "") -> str:
    """
    Valor da credencial, na ordem: ambiente, cofre, `.env`.

    O `.env` ja foi carregado por `load_dotenv()` para dentro de `os.environ`
    quando este modulo e consultado -- entao os degraus 1 e 3 chegam pelo
    mesmo lugar. A diferenca esta na PRECEDENCIA: o cofre vence o que veio do
    arquivo, e perde para o que foi injetado explicitamente.
    """
    do_ambiente_real = os.environ.get(nome, "")
    if do_ambiente_real and nome not in _valores_vindos_do_env():
        return do_ambiente_real

    do_cofre = _ler_cofre().get(nome, "")
    if do_cofre:
        return do_cofre

    return do_ambiente_real or padrao


_origem_env: set = set()


def _valores_vindos_do_env() -> set:
    """
    Nomes que o `.env` colocou em `os.environ`.

    Sem esta distincao nao daria para saber se `MP_ACCESS_TOKEN` veio do
    arquivo (e portanto perde para o cofre) ou foi injetada de fora (e portanto
    vence).
    """
    return _origem_env


def registrar_origem_env(nomes) -> None:
    """Chamado por `config` logo apos o `load_dotenv()`."""
    _origem_env.update(nomes)


def gravar(valores: dict) -> bool:
    """
    Cifra e grava as credenciais informadas, preservando as demais.

    Devolve True quando o cofre ficou gravado.
    """
    atuais = dict(_ler_cofre())
    atuais.update({n: v for n, v in valores.items() if v})

    caminho = caminho_do_cofre()
    linhas = [
        "# Credenciais de integracao do Adri Poltronas, cifradas.",
        "#",
        "# Cifradas com DPAPI, amarradas a esta conta do Windows: copiar este",
        "# arquivo para outra maquina nao serve de nada. Nao edite a mao -- os",
        "# valores nao sao legiveis. Para trocar uma chave, use a tela de",
        "# configuracao do aplicativo.",
        "",
    ]
    for nome, valor in sorted(atuais.items()):
        try:
            linhas.append(f"{nome}={security.cifrar(valor)}")
        except Exception as erro:
            log.error("[SEGREDOS] Nao foi possivel cifrar %s: %s", nome, erro)
            return False

    try:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, "w", encoding="utf-8") as arquivo:
            arquivo.write("\n".join(linhas) + "\n")
        _restringir(caminho)
    except OSError as erro:
        log.error("[SEGREDOS] Nao foi possivel gravar o cofre: %s", erro)
        return False

    global _cache
    _cache = atuais
    return True


def _restringir(caminho: str) -> None:
    """Deixa o arquivo legivel so pelo dono, onde o sistema permite."""
    try:
        os.chmod(caminho, 0o600)
    except OSError:
        # No Windows o chmod so mexe no atributo somente-leitura; a protecao
        # real vem do DPAPI e da ACL do perfil.
        pass


def migrar_do_env(caminho_env: str) -> list:
    """
    Move para o cofre as credenciais que ainda estao em texto no `.env`.

    Devolve a lista de nomes migrados. Nunca levanta: falhar aqui nao pode
    impedir o aplicativo de abrir -- as chaves continuam funcionando de onde
    estao, so que menos protegidas.
    """
    if not caminho_env or not os.path.exists(caminho_env):
        return []

    try:
        with open(caminho_env, encoding="utf-8") as arquivo:
            linhas = arquivo.read().splitlines()
    except OSError as erro:
        log.warning("[SEGREDOS] Nao foi possivel ler %s: %s", caminho_env, erro)
        return []

    em_texto = {}
    for linha in linhas:
        despida = linha.strip()
        if not despida or despida.startswith("#") or "=" not in despida:
            continue
        nome, _, valor = despida.partition("=")
        nome, valor = nome.strip(), valor.strip()
        if nome in CHAVES_PROTEGIDAS and valor:
            em_texto[nome] = valor

    if not em_texto:
        return []

    if not gravar(em_texto):
        log.warning("[SEGREDOS] Migracao abortada: o cofre nao pode ser gravado.")
        return []

    # Copia antes de reescrever. Mexer no arquivo de configuracao do usuario
    # sem deixar volta seria trocar um risco por outro.
    try:
        shutil.copy2(caminho_env, caminho_env + ".bak")
    except OSError as erro:
        log.warning("[SEGREDOS] Sem copia de seguranca do .env (%s); nao vou reescreve-lo.", erro)
        return list(em_texto)

    novas = []
    for linha in linhas:
        despida = linha.strip()
        nome = despida.partition("=")[0].strip() if "=" in despida else ""
        if nome in em_texto and not despida.startswith("#"):
            novas.append(f"# {nome} foi movida para {NOME_DO_COFRE}, cifrada.")
        else:
            novas.append(linha)

    try:
        with open(caminho_env, "w", encoding="utf-8") as arquivo:
            arquivo.write("\n".join(novas) + "\n")
    except OSError as erro:
        log.warning("[SEGREDOS] Cofre gravado, mas o .env nao pode ser limpo: %s", erro)
        # O `.env` continua com as chaves em claro, entao a copia ainda pode
        # servir de referencia. Nao apagar aqui e deliberado.
        return sorted(em_texto)

    _descartar_copia_em_claro(caminho_env + ".bak", em_texto)
    log.info("[SEGREDOS] Migradas para o cofre: %s", ", ".join(sorted(em_texto)))
    return sorted(em_texto)


def _descartar_copia_em_claro(caminho_bak: str, migradas: dict) -> None:
    """
    Apaga o `.env.bak` -- mas so depois de reler o cofre e conferir cada chave.

    A copia existe para proteger contra uma falha DURANTE a reescrita do
    `.env`. Cumprida essa funcao, ela vira o oposto do que o cofre faz: um
    arquivo permanente, em texto puro, na mesma pasta do banco, contendo o
    `MP_ACCESS_TOKEN` (que da acesso total a conta do vendedor no Mercado Pago
    -- criar cobranca, ler movimentacao, estornar), `GEMINI_API_KEY` e o token
    administrativo da API central de licencas. O
    trabalho de cifrar ficava metade desfeito, e para sempre.

    A conferencia por releitura e o que torna seguro apagar. O risco oposto e
    real: se o DPAPI gravar e nao conseguir decifrar de volta -- perfil de
    usuario recriado, chave da maquina trocada --, apagar a copia perderia a
    credencial. Entao releitura primeiro; qualquer divergencia mantem o
    arquivo e registra o motivo.
    """
    global _cache
    if not os.path.exists(caminho_bak):
        return

    # Forca a releitura do disco: o cache foi populado pelo `gravar()` e
    # confirmaria o valor que temos em memoria, nao o que ficou no arquivo.
    _cache = None
    try:
        # `_ler_cofre()` e nao `obter()`, e a diferenca e a razao de este
        # arquivo poder ser apagado com seguranca.
        #
        # `obter()` percorre a precedencia inteira e termina em
        # `return do_ambiente_real or padrao`. Em producao o `load_dotenv()` ja
        # colocou MP_ACCESS_TOKEN, GEMINI_API_KEY e o token administrativo em
        # `os.environ` -- com
        # exatamente o valor que esta sendo migrado. Entao, se o DPAPI cifrasse
        # e NAO conseguisse decifrar de volta, o cofre devolvia vazio, a funcao
        # caia nesse ultimo degrau, entregava o valor do ambiente e a
        # conferencia "passava". O `.env` ja reescrito sem as chaves mais a
        # copia apagada = credencial perdida sem volta.
        #
        # A pergunta que esta conferencia precisa responder e estreita: o COFRE
        # devolve o que foi gravado? Qualquer outra fonte responde outra
        # pergunta.
        do_cofre = _ler_cofre()
        divergentes = [nome for nome, valor in migradas.items()
                       if do_cofre.get(nome) != valor]
    except Exception as erro:  # noqa: BLE001 - qualquer falha aqui e motivo de nao apagar
        log.warning("[SEGREDOS] Cofre nao pode ser conferido (%s); "
                    "mantendo %s por seguranca.", erro, os.path.basename(caminho_bak))
        return

    if divergentes:
        log.warning("[SEGREDOS] Cofre nao devolveu %s como gravado; "
                    "mantendo %s por seguranca.",
                    ", ".join(sorted(divergentes)), os.path.basename(caminho_bak))
        return

    try:
        os.remove(caminho_bak)
        log.info("[SEGREDOS] Copia em texto claro descartada apos conferencia do cofre.")
    except OSError as erro:
        log.warning("[SEGREDOS] Nao foi possivel apagar %s: %s", caminho_bak, erro)
