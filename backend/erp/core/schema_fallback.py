"""Schema de emergencia quando o Alembic nao pode ser executado.

Alembic continua sendo a fonte de verdade. Este modulo apenas preserva a
capacidade historica do aplicativo desktop de iniciar em uma instalacao com
os artefatos de migration indisponiveis.
"""

from __future__ import annotations

import logging
import sqlite3


log = logging.getLogger("adri.schema_fallback")


def _garantir_coluna(
    conexao: sqlite3.Connection,
    tabela: str,
    coluna: str,
    declaracao: str,
) -> None:
    existentes = {linha[1] for linha in conexao.execute(f"PRAGMA table_info({tabela})")}
    if coluna not in existentes:
        conexao.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {declaracao}")


def _criar_indices(conexao: sqlite3.Connection) -> None:
    comandos = [
        "CREATE INDEX IF NOT EXISTS ix_clientes_id ON clientes(id DESC)",
        "CREATE INDEX IF NOT EXISTS ix_clientes_nome_cep ON clientes(nome, cep)",
        "CREATE INDEX IF NOT EXISTS ix_clientes_criado_em ON clientes(criado_em)",
        "CREATE INDEX IF NOT EXISTS ix_clientes_ativo_atualizado_em ON clientes(ativo, atualizado_em)",
        "CREATE INDEX IF NOT EXISTS ix_historico_cliente_id ON historico(cliente_id)",
        "CREATE INDEX IF NOT EXISTS ix_historico_data_hora ON historico(data_hora)",
        "CREATE INDEX IF NOT EXISTS ix_pagamentos_cliente_id ON pagamentos(cliente_id)",
        "CREATE INDEX IF NOT EXISTS ix_pagamentos_status_pagamento ON pagamentos(status, data_pagamento)",
        "CREATE INDEX IF NOT EXISTS ix_pagamentos_status_vencimento ON pagamentos(status, data_vencimento)",
        "CREATE INDEX IF NOT EXISTS ix_entregas_cliente_id ON entregas_agendadas(cliente_id)",
        "CREATE INDEX IF NOT EXISTS ix_entregas_data_status ON entregas_agendadas(data_entrega, status)",
        "CREATE INDEX IF NOT EXISTS ix_auditoria_entidade_registro ON auditoria_eventos(entidade, entidade_id, id)",
        "CREATE INDEX IF NOT EXISTS ix_auditoria_criado_em ON auditoria_eventos(criado_em)",
        "CREATE INDEX IF NOT EXISTS ix_auditoria_usuario_criado_em ON auditoria_eventos(usuario_id, criado_em)",
    ]
    for comando in comandos:
        conexao.execute(comando)

    indices_unicos = [
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_pagamentos_asaas_payment_id "
        "ON pagamentos(asaas_payment_id) WHERE asaas_payment_id IS NOT NULL AND asaas_payment_id != ''",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_pagamentos_asaas_external_reference "
        "ON pagamentos(asaas_external_reference) WHERE asaas_external_reference IS NOT NULL AND asaas_external_reference != ''",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_clientes_asaas_customer_id "
        "ON clientes_asaas(asaas_customer_id) WHERE asaas_customer_id IS NOT NULL AND asaas_customer_id != ''",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_clientes_asaas_external_reference "
        "ON clientes_asaas(asaas_external_reference) WHERE asaas_external_reference IS NOT NULL AND asaas_external_reference != ''",
    ]
    for comando in indices_unicos:
        try:
            conexao.execute(comando)
        except sqlite3.IntegrityError:
            log.exception("Indice unico nao criado porque ha dados duplicados no banco legado")


def garantir_schema_fallback(conexao: sqlite3.Connection) -> None:
    conexao.executescript(
        """
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cep TEXT,
            rua TEXT,
            bairro TEXT,
            cidade TEXT,
            entrega_retirada TEXT NOT NULL DEFAULT 'Entrega',
            observacoes TEXT DEFAULT '',
            criado_em TEXT DEFAULT (datetime('now', 'localtime')),
            atualizado_em TEXT DEFAULT (datetime('now', 'localtime')),
            ativo INTEGER NOT NULL DEFAULT 1,
            excluido_em TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS sessao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT NOT NULL,
            conta TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            cliente_nome TEXT,
            acao TEXT NOT NULL,
            detalhes TEXT DEFAULT '',
            data_hora TEXT DEFAULT (datetime('now', 'localtime')),
            CONSTRAINT fk_historico_cliente_id_clientes
                FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            cliente_nome TEXT DEFAULT '',
            valor REAL NOT NULL DEFAULT 0,
            descricao TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Pendente',
            data_pagamento TEXT DEFAULT '',
            data_vencimento TEXT DEFAULT '',
            criado_em TEXT DEFAULT (datetime('now', 'localtime')),
            tipo_pagamento TEXT NOT NULL DEFAULT 'Pix',
            asaas_payment_id TEXT DEFAULT '',
            pix_payload TEXT DEFAULT '',
            pix_qr_code TEXT DEFAULT '',
            boleto_url TEXT DEFAULT '',
            nosso_numero TEXT DEFAULT '',
            asaas_external_reference TEXT DEFAULT '',
            asaas_emissao_estado TEXT DEFAULT '',
            asaas_emissao_inicio TEXT DEFAULT '',
            CONSTRAINT fk_pagamentos_cliente_id_clientes
                FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS clientes_asaas (
            cliente_id INTEGER PRIMARY KEY,
            asaas_customer_id TEXT NOT NULL DEFAULT '',
            asaas_external_reference TEXT DEFAULT '',
            asaas_criacao_estado TEXT DEFAULT '',
            asaas_criacao_inicio TEXT DEFAULT '',
            CONSTRAINT fk_clientes_asaas_cliente_id_clientes
                FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS notificacoes_lidas (
            chave TEXT PRIMARY KEY,
            lida_em TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS entregas_agendadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            cliente_nome TEXT DEFAULT '',
            data_entrega TEXT NOT NULL,
            hora_entrega TEXT DEFAULT '',
            descricao TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Pendente',
            criado_em TEXT DEFAULT (datetime('now', 'localtime')),
            CONSTRAINT fk_entregas_agendadas_cliente_id_clientes
                FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS auditoria_eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id TEXT,
            usuario_identificador TEXT,
            acao TEXT NOT NULL,
            entidade TEXT NOT NULL,
            entidade_id TEXT,
            valores_anteriores TEXT,
            valores_novos TEXT,
            origem TEXT NOT NULL DEFAULT 'backend',
            contexto TEXT NOT NULL DEFAULT '{}',
            correlation_id TEXT,
            criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
        """
    )

    colunas_clientes = {
        "entrega_retirada": "TEXT NOT NULL DEFAULT 'Entrega'",
        "observacoes": "TEXT DEFAULT ''",
        "criado_em": "TEXT",
        "atualizado_em": "TEXT",
        "ativo": "INTEGER NOT NULL DEFAULT 1",
        "excluido_em": "TEXT DEFAULT ''",
    }
    for coluna, declaracao in colunas_clientes.items():
        _garantir_coluna(conexao, "clientes", coluna, declaracao)

    colunas_pagamentos = {
        "data_vencimento": "TEXT DEFAULT ''",
        "tipo_pagamento": "TEXT NOT NULL DEFAULT 'Pix'",
        "asaas_payment_id": "TEXT DEFAULT ''",
        "pix_payload": "TEXT DEFAULT ''",
        "pix_qr_code": "TEXT DEFAULT ''",
        "boleto_url": "TEXT DEFAULT ''",
        "nosso_numero": "TEXT DEFAULT ''",
        "asaas_external_reference": "TEXT DEFAULT ''",
        "asaas_emissao_estado": "TEXT DEFAULT ''",
        "asaas_emissao_inicio": "TEXT DEFAULT ''",
    }
    for coluna, declaracao in colunas_pagamentos.items():
        _garantir_coluna(conexao, "pagamentos", coluna, declaracao)

    # A sessao Microsoft ganhou refresh_token e validade do access_token.
    # Anulaveis: a linha gravada por uma versao anterior segue valida ate o
    # proximo login, que ja preenche as duas.
    colunas_sessao = {
        "refresh_token": "TEXT",
        "expira_em": "INTEGER",
    }
    for coluna, declaracao in colunas_sessao.items():
        _garantir_coluna(conexao, "sessao", coluna, declaracao)

    colunas_clientes_asaas = {
        "asaas_external_reference": "TEXT DEFAULT ''",
        "asaas_criacao_estado": "TEXT DEFAULT ''",
        "asaas_criacao_inicio": "TEXT DEFAULT ''",
    }
    for coluna, declaracao in colunas_clientes_asaas.items():
        _garantir_coluna(conexao, "clientes_asaas", coluna, declaracao)

    conexao.execute(
        "UPDATE clientes SET criado_em=datetime('now', 'localtime') WHERE criado_em IS NULL"
    )
    conexao.execute(
        "UPDATE clientes SET atualizado_em=datetime('now', 'localtime') WHERE atualizado_em IS NULL"
    )

    _criar_indices(conexao)
    conexao.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS trg_auditoria_eventos_immutable_update
        BEFORE UPDATE ON auditoria_eventos
        BEGIN
            SELECT RAISE(ABORT, 'auditoria_eventos e append-only');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_auditoria_eventos_immutable_delete
        BEFORE DELETE ON auditoria_eventos
        BEGIN
            SELECT RAISE(ABORT, 'auditoria_eventos e append-only');
        END;
        """
    )
