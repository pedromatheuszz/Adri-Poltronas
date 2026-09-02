"""
Ponto de entrada do backend.

Antes o processo Python tambem hospedava a janela, via pywebview/WebView2.
Agora ele so serve o Flask em loopback: a janela e do Electron, que sobe este
processo como filho e aponta o BrowserWindow para a mesma porta.

Consequencia pratica: nada aqui depende mais de GUI, entao o backend roda
igual sob o Electron, sozinho no terminal ou dentro da suite de testes.
"""
import logging
import os
import sys

# O diretorio precisa estar em sys.path antes dos imports do proprio backend,
# porque os modulos se referenciam por nome de topo (`import database`).
DIRETORIO_BACKEND = os.path.dirname(os.path.abspath(__file__))
if DIRETORIO_BACKEND not in sys.path:
    sys.path.insert(0, DIRETORIO_BACKEND)

import database  # noqa: E402
from erp.core import backup  # noqa: E402
from app import app  # noqa: E402

log = logging.getLogger("adri.servidor")

HOST = "127.0.0.1"  # loopback apenas -- nao exposto na rede
PORTA = 5000  # fixa: o redirect_uri do OAuth Microsoft aponta para ela

# Prefixo que o Electron procura no stderr para distinguir "o banco esta
# quebrado, com instrucoes" de um traceback qualquer.
MARCADOR_FALHA_BANCO = "[ADRI-BANCO-FALHOU]"


# Texto de recuperacao mostrado quando o banco nao pode ser preparado. Fica
# aqui, num molde unico, porque e a unica coisa que o operador vai ler quando
# o sistema se recusar a abrir -- e precisa dizer o que fazer, nao so o que
# houve.
_MOLDE_RECUPERACAO = """{resumo}

Banco:   {banco}
Backups: {backups}

O sistema NAO foi iniciado, de proposito: subir agora poderia gravar por
cima de um banco em estado inconsistente.

Como recuperar:
  1. Feche o aplicativo.
  2. Guarde uma copia do arquivo do banco em outro lugar.
  3. Restaure a copia mais recente da pasta de backups por cima do arquivo
     do banco (o nome de cada copia traz data e hora).
  4. Abra o aplicativo de novo.

Persistindo, envie o arquivo de log da pasta "logs", ao lado do banco."""


class ErroDePreparacaoDoBanco(RuntimeError):
    """
    Falha que impede subir com seguranca sobre um banco que tem dados.

    Existe para separar "nao consegui preparar o banco" de qualquer outra
    excecao: e a unica que `main()` transforma em mensagem de recuperacao
    para o operador, em vez de um traceback.
    """

    def __init__(self, resumo: str, caminho_banco: str) -> None:
        self.resumo = resumo
        self.caminho_banco = caminho_banco
        super().__init__(resumo)

    def instrucoes(self) -> str:
        """Texto que o operador ve. Diz o que houve, onde estao as copias e o
        que fazer -- um erro de banco sem caminho de volta e so um susto."""
        pasta = backup.pasta_de_backups(self.caminho_banco)
        return _MOLDE_RECUPERACAO.format(
            resumo=self.resumo,
            banco=self.caminho_banco,
            backups=pasta,
        )


def preparar_banco() -> None:
    """
    Faz backup quando necessario, aplica as migracoes e decide o que fazer
    quando algo falha -- e a decisao depende de haver dado a perder.

    Banco novo ou vazio: o fallback `criar_tabela()` e legitimo. Nao ha o que
    corromper, e uma instalacao sem alembic.ini legivel ainda sobe com o
    schema basico em vez de nao abrir.

    Banco com dados: falha e falha. A versao anterior desta funcao seguia em
    frente nos dois casos -- migrava sem backup quando a copia falhava e, se a
    migracao morresse no meio, rodava o schema fallback POR CIMA de um banco
    parcialmente migrado e subia como se nada tivesse acontecido. Um erro de
    schema virava perda silenciosa; agora vira recusa explicita, com a pasta
    de backups apontada na mensagem.
    """
    caminho = database.obter_caminho_banco_absoluto()

    try:
        import migrations_manager
    except Exception as erro:
        # Sem o gerenciador nao da para nem classificar o banco. Em instalacao
        # nova isso ainda e recuperavel pelo schema basico.
        log.exception("migrations_manager indisponivel")
        if os.path.exists(caminho) and os.path.getsize(caminho) > 0:
            raise ErroDePreparacaoDoBanco(
                "O componente de migracoes nao pode ser carregado e o banco "
                "existente nao pode ser verificado.", caminho,
            ) from erro
        database.criar_tabela()
        return

    estado = migrations_manager.estado_do_banco()
    tem_dados = estado not in migrations_manager.ESTADOS_SEM_DADOS
    log.info("Estado do banco antes de migrar: %s", estado)

    if estado == migrations_manager.ESTADO_ILEGIVEL:
        raise ErroDePreparacaoDoBanco(
            "O arquivo do banco existe mas nao pode ser lido. Ele pode estar "
            "corrompido, em uso por outro programa ou sem permissao de acesso.",
            caminho,
        )

    # Copia antes de mexer no schema: migration e a unica operacao que
    # reescreve estrutura, e e onde uma falha custa o banco inteiro.
    # So dispara quando ha migration pendente de verdade.
    if migrations_manager.ha_migracoes_pendentes():
        destino = backup.backup_antes_de_migrar(caminho)
        if destino:
            log.info("Backup de pre-migracao: %s", destino)
        elif tem_dados:
            # Migrar sem rede sobre dado real e o que transforma um erro
            # recuperavel em perda definitiva. Recusar aqui e o unico
            # comportamento defensavel.
            raise ErroDePreparacaoDoBanco(
                "Nao foi possivel gravar o backup obrigatorio de pre-migracao. "
                "Verifique espaco em disco e permissao de escrita na pasta de "
                "dados.", caminho,
            )
        else:
            log.warning("Migracao pendente sem backup previo (banco vazio).")

    try:
        migrations_manager.aplicar_migrações()
    except Exception as erro:
        if tem_dados:
            raise ErroDePreparacaoDoBanco(
                "A atualizacao da estrutura do banco falhou. O banco pode ter "
                "ficado parcialmente migrado.", caminho,
            ) from erro
        # Banco novo: o schema basico e melhor do que nao abrir.
        log.exception("Falha ao migrar banco novo; usando criar_tabela()")
        database.criar_tabela()

    # Copia do dia, depois do schema estar no lugar. Silenciosa quando a de
    # hoje ja existe, entao reabrir o app varias vezes nao acumula arquivos.
    diario = backup.backup_diario(caminho)
    if diario:
        log.info("Backup diario: %s", diario)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        preparar_banco()
    except ErroDePreparacaoDoBanco as erro:
        log.error("Banco nao pode ser preparado: %s", erro.resumo)
        # stderr, e nao so o log: o Electron le esta saida e a mostra na
        # caixa de dialogo de falha. Sem isso o operador ve "o servidor nao
        # respondeu" e nao tem o que fazer com a informacao.
        print(MARCADOR_FALHA_BANCO, file=sys.stderr, flush=True)
        print(erro.instrucoes(), file=sys.stderr, flush=True)
        return 2
    except Exception:
        log.exception("Nao foi possivel inicializar o banco de dados local")
        return 1

    log.info("Servidor em http://%s:%s/", HOST, PORTA)
    # debug/reloader desligados: o reloader duplicaria o processo, e o Electron
    # perderia a referencia do filho que precisa encerrar junto com a janela.
    app.run(host=HOST, port=PORTA, debug=False, use_reloader=False, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
