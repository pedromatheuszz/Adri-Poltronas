# backend/blueprints/backup.py
"""
Blueprint de backup e restauracao.

Ate aqui havia backup e nao havia volta. As copias eram criadas -- antes de
cada migration e uma por dia --, mas recuperar uma delas exigia fechar o app,
achar a pasta em %APPDATA%, entender o nome dos arquivos e sobrescrever o banco
na mao. Um backup sem procedimento de restauracao e uma suposicao, nao uma
garantia; ninguem descobre que a copia nao presta no dia em que precisa dela.

As rotas antigas (`/api/clientes/backup/json` e `/api/clientes/backup/sqlite`)
continuam existindo em `clientes.py`: elas estao no atalho de teclado do app e
em instalacoes ja distribuidas. As daqui sao o endereco correto para o assunto.
"""
import io
import json
import logging
import os
import time

from flask import Blueprint, jsonify, request, send_file

import database
from erp.core import backup as servico_backup
from permissoes import exigir_permissao

log = logging.getLogger("adri.backup")

backup_bp = Blueprint('backup', __name__, url_prefix='/api/backup')


@backup_bp.route('/copias')
@exigir_permissao("config.backup.restaurar")
def listar_copias():
    """Copias disponiveis para restauracao, da mais recente para a mais antiga."""
    caminho = database.obter_caminho_banco_absoluto()
    return jsonify({
        "pasta": servico_backup.pasta_de_backups(caminho),
        "copias": servico_backup.listar_copias(caminho),
    })


@backup_bp.route('/criar', methods=['POST'])
@exigir_permissao("config.backup.restaurar")
def criar_copia():
    """Copia sob demanda, alem das automaticas."""
    caminho = database.obter_caminho_banco_absoluto()
    destino = servico_backup.criar_backup(caminho, servico_backup.MOTIVO_DIARIO)
    if not destino:
        return jsonify({
            "erro": "Nao foi possivel gravar a copia. Verifique espaco em disco "
                    "e permissao de escrita na pasta de dados.",
        }), 500
    return jsonify({
        "mensagem": "Copia criada.",
        "arquivo": os.path.basename(destino),
    }), 201


@backup_bp.route('/restaurar', methods=['POST'])
@exigir_permissao("config.backup.restaurar")
def restaurar_copia():
    """
    Sobrescreve o banco atual com o conteudo de uma copia.

    E destrutivo, e por isso o estado atual e salvo antes -- restaurar do
    arquivo errado precisa ter volta. O servico verifica a integridade da copia
    ANTES de qualquer escrita: trocar um banco ruim por um pior seria o unico
    desfecho de restaurar de um arquivo corrompido.
    """
    dados = request.get_json(silent=True) or {}
    nome = (dados.get('arquivo') or '').strip()
    if not nome:
        return jsonify({"erro": "Informe qual copia restaurar."}), 400

    caminho_banco = database.obter_caminho_banco_absoluto()
    # `caminho_da_copia` recusa qualquer coisa que nao seja um nome simples
    # dentro da pasta de backups. Sem isso, o nome vindo da API viraria um
    # caminho arbitrario e a restauracao, uma leitura de arquivo qualquer.
    caminho_copia = servico_backup.caminho_da_copia(caminho_banco, nome)
    if not caminho_copia:
        return jsonify({"erro": "Copia nao encontrada."}), 404

    ok, mensagem = servico_backup.restaurar(caminho_banco, caminho_copia)
    if not ok:
        return jsonify({"erro": mensagem}), 500

    log.warning("[BACKUP] Restauracao concluida a partir de %s", nome)
    return jsonify({
        "mensagem": mensagem,
        # O app precisa reabrir: telas ja carregadas seguem mostrando os dados
        # de antes, e uma edicao feita sobre elas gravaria por cima do que
        # acabou de ser restaurado.
        "requer_reinicio": True,
    }), 200


@backup_bp.route('/json')
@exigir_permissao("clientes.exportar")
def baixar_json():
    """Exportacao legivel dos clientes. Nao substitui a copia do banco."""
    clientes = database.listar_clientes()
    conteudo = {
        "versao": "1.0",
        "data_exportacao": time.strftime('%Y-%m-%dT%H:%M:%S'),
        "clientes": clientes,
    }
    buffer = io.BytesIO(json.dumps(conteudo, ensure_ascii=False, indent=2).encode('utf-8'))
    return send_file(
        buffer, mimetype='application/json', as_attachment=True,
        download_name=f"backup_adri_poltronas_{time.strftime('%Y%m%d_%H%M%S')}.json",
    )


@backup_bp.route('/sqlite')
@exigir_permissao("config.backup.restaurar")
def baixar_sqlite():
    """
    Copia integra do banco, para guardar fora da maquina.

    Nao envia o arquivo em uso: com o app aberto, isso captura um estado no
    meio de uma transacao e deixa de fora o que estiver no `-wal`. O operador
    baixava algo que parecia um backup e podia nao abrir.
    """
    caminho = database.obter_caminho_banco_absoluto()
    if not os.path.exists(caminho):
        return jsonify({"erro": "Banco de dados nao encontrado."}), 404

    copia = servico_backup.copia_para_download(caminho)
    if not copia:
        return jsonify({"erro": "Nao foi possivel preparar a copia do banco."}), 500

    try:
        with open(copia, 'rb') as arquivo:
            conteudo = arquivo.read()
    except OSError:
        return jsonify({"erro": "Nao foi possivel ler a copia do banco."}), 500
    finally:
        # O arquivo temporario nao pode sobreviver ao download: e uma copia
        # integral dos dados de clientes na pasta temporaria do sistema.
        try:
            os.remove(copia)
        except OSError:
            log.warning("[BACKUP] Copia temporaria nao removida: %s", copia)

    return send_file(
        io.BytesIO(conteudo), mimetype='application/x-sqlite3', as_attachment=True,
        download_name=f"backup_adri_poltronas_{time.strftime('%Y%m%d_%H%M%S')}.db",
    )
