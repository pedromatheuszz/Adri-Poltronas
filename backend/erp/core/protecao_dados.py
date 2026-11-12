"""
Onde o banco vive, e o que isso significa para os dados do cliente.

O SECURITY.md sempre disse a verdade sobre o arquivo `adri_poltronas.db`:
ele contem nome, endereco, CEP e valores a receber de pessoas reais, e nao e
cifrado em repouso. Quem protege esse arquivo contra a maquina fisica sair
de casa e o disco: BitLocker ou equivalente. O que faltava era o sistema
SABER dizer ao operador quando essa protecao nao esta la.

Duas perguntas, uma resposta honesta para cada:

1. O banco esta numa pasta de rede? (UNC ou unidade mapeada)
   Resposta definitiva, porque ha como determinar. E recusa: o SQLite em
   compartilhamento SMB corrompe -- o proprio SECURITY.md diz que varios
   computadores na mesma base nao sao suportados. Corrupcao silenciosa e
   pior que recusar a abrir.

2. O disco do banco tem BitLocker?
   Melhor esforco. A consulta exige privilegio que o aplicativo nao tem na
   maquina do cliente, e em muitos cenarios nao ha como saber. `None` e a
   resposta "nao sei", e quem nao sabe nao acusa: um aviso falso ensinaria
   o operador a ignorar avisos, que e o unico alerta que este sistema nao
   pode se dar ao luxo de perder.

Foi deliberado nao fingir SQLCipher aqui. Cifrar o banco inteiro exige uma
chave que alguem precisa digitar a cada abertura -- decisao de produto que
o SECURITY.md registra como pendente. O que ESTE modulo entrega e real: a
copia de seguranca sai cifrada (ver `erp/core/backup.py`) e o operador que
roda sem BitLocker passa a ser avisado disso no log de seguranca.
"""
from __future__ import annotations

import logging
import os
import subprocess

log = logging.getLogger("adri.protecao_dados")

# Unica saida para quem decide rodar em rede assim mesmo. E deliberadamente
# explicita: quem a define esta assumindo a corrupcao que o SQLite em SMB
# produz, e o nome da variavel precisa dizer isso.
VARIAVEL_PERMITIR_REDE = "ADRI_PERMITIR_BANCO_EM_REDE"
VARIAVEL_PERMITIR_DISCO_SEM_BITLOCKER = "ADRI_PERMITIR_BANCO_SEM_BITLOCKER"

# DRIVE_REMOTE do Win32. Consultado pelo GetDriveTypeW, que nao exige
# elevacao: distinguir unidade local de mapeada e informacao publica.
_DRIVE_REMOTE = 4


def rede_permitida_explicitamente() -> bool:
    """Verdadeiro so quando alguem pediu, por escrito, para rodar em rede."""
    return (os.environ.get(VARIAVEL_PERMITIR_REDE) or "").strip() == "1"


def _tipo_da_unidade_win32(unidade: str) -> int:
    """Tipo da unidade pelo Win32. Sem elevacao, sem rede, sem custo."""
    import ctypes

    return ctypes.windll.kernel32.GetDriveTypeW(unidade)  # noqa: S606 - funcao Win32 publica, entrada e a propria unidade do banco


def em_pasta_de_rede(caminho: str, tipo_da_unidade=_tipo_da_unidade_win32) -> bool:
    """
    O arquivo mora num compartilhamento de rede?

    Dois formatos chegam aqui:

    * UNC (`\\\\servidor\\compartilhamento\\...`): reconhecivel em qualquer
      plataforma pelo prefixo de barras invertidas.
    * Unidade mapeada (`Z:\\dados\\...`): uma letra comum apontando para um
      compartilhamento. `GetDriveTypeW` resolve sem exigir elevacao; sem ele,
      um caminho local e uma unidade mapeada sao indistingueis no texto.

    `tipo_da_unidade` e injetavel de proposito: e a unica borda com o
    sistema operacional desta funcao, e injeta-la e o unico jeito honesto de
    testar o caso "mapeada" numa suite que roda em disco local.

    Caminho relativo nao e rede: quem chega aqui sempre traz caminho
    absoluto (o banco resolve o dele no boot), mas a resposta `False` para
    relativo e a segura -- nao ha como um caminho relativo resolver para UNC
    sem que a raiz ja fosse rede, e nesse caso o absoluto foi conferido.
    """
    if not caminho:
        return False

    normalizado = os.path.normpath(caminho)
    if normalizado.startswith("\\\\") or normalizado.startswith("//"):
        return True

    unidade, _ = os.path.splitdrive(normalizado)
    # `splitdrive` devolve 'Z:' (sem barra). Uma letra seguida de dois-pontos
    # e tudo o que ha de informacao ali; qualquer outra coisa nao e unidade
    # mapeavel, e responder `False` e o seguro.
    if len(unidade) != 2 or not unidade.endswith(":"):
        return False

    try:
        # Com a barra: e o formato de raiz que a documentacao do Win32 pede.
        return tipo_da_unidade(unidade + "\\") == _DRIVE_REMOTE
    except (AttributeError, OSError, ImportError, ValueError):
        # Nao-Windows, ou resolvedor ausente: sem API para consultar, e a
        # resposta honesta e que NAO e rede, ja que o prefixo UNC ja foi
        # descartado acima.
        return False


def _consultar_bitlocker(mount_point: str) -> object:
    """
    Pergunta ao Windows, por PowerShell, se o volume tem BitLocker.

    Funcao separada para ser substituivel em teste: a consulta real exige o
    cmdlet do BitLocker, que pede elevacao -- exatamente o cenario em que a
    chamada falha e o chamador precisa responder "nao sei".
    """
    comando = (
        "$v = Get-BitLockerVolume -MountPoint $args[0] | Select-Object -First 1; "
        "if ($v) { $v | Select-Object ProtectionStatus | ConvertTo-Json }"
    )
    try:
        # CREATE_NO_WINDOW: o Python empacotado nao tem console, e um flash
        # de janela do PowerShell na maquina do cliente seria o unico sinal
        # visivel de uma consulta que deveria ser invisivel.
        resultado = subprocess.run(
            # "powershell" vem do PATH de proposito (S603/S607): os argumentos
            # sao montados nesta funcao, e o unico valor externo e a propria
            # unidade do banco.
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", comando,  # noqa: S603, S607
             mount_point],
            capture_output=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if resultado.returncode != 0:
        return None
    return resultado.stdout.decode("utf-8", errors="replace")


def volume_com_bitlocker(caminho: str, consultar=_consultar_bitlocker) -> bool | None:
    """
    True/False quando consegue provar; None quando nao ha como saber.

    `ProtectionStatus`: 0 = desprotegido, 1 = protegido. Qualquer outra
    coisa -- cmdlet ausente, acesso negado, saida ilegivel -- vira None, e
    None nao gera aviso: acusar quem nao se pode examinar e o caminho mais
    curto para que o proximo aviso verdadeiro seja ignorado.
    """
    if not os.name == "nt" or not caminho:
        return None

    unidade, _ = os.path.splitdrive(os.path.abspath(caminho))
    if not unidade:
        return None

    saida = consultar(unidade + "\\")
    if not saida:
        return None

    import json

    try:
        dados = json.loads(saida)
    except ValueError:
        return None
    if not isinstance(dados, dict):
        return None

    status = dados.get("ProtectionStatus")
    if status == 0:
        return False
    if status == 1:
        return True
    return None


def avaliar_local_do_banco(caminho: str, consultar=_consultar_bitlocker) -> dict:
    """Reune as duas respostas num dicionario, para quem precisa das duas."""
    return {
        "caminho": os.path.abspath(caminho),
        "em_rede": em_pasta_de_rede(caminho),
        "bitlocker": volume_com_bitlocker(caminho, consultar=consultar),
    }


def avisar_protecao_do_banco(
    caminho: str, consultar=_consultar_bitlocker, situacao: dict | None = None,
) -> dict:
    """
    Registra no log de seguranca o que falta, quando ha como saber.

    Chamado uma vez por boot, depois do banco estar aberto: e um aviso, nao
    um bloqueio, e nao pode custar a abertura do aplicativo. O BitLocker
    indisponivel nao gera nada -- quem nao sabe, cala.
    """
    import security

    situacao = situacao or avaliar_local_do_banco(caminho, consultar=consultar)

    if situacao["bitlocker"] is False:
        mensagem = (
            f"O disco do banco ({caminho}) NAO tem BitLocker. Um disco "
            "roubado entrega nome, endereco e valores a receber dos clientes. "
            "Ligue a cifra de disco do Windows."
        )
        log.warning("[PROTECAO] %s", mensagem)
        security.log_evento_seguro("DISCO_SEM_BITLOCKER", mensagem, "warning")

    return situacao
