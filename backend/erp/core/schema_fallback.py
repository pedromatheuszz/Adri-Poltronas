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
        "CREATE INDEX IF NOT EXISTS ix_produtos_descricao ON produtos(descricao)",
        "CREATE INDEX IF NOT EXISTS ix_pedidos_cliente_id ON pedidos(cliente_id)",
        "CREATE INDEX IF NOT EXISTS ix_pedidos_situacao_emissao ON pedidos(situacao, data_emissao)",
        "CREATE INDEX IF NOT EXISTS ix_pedidos_entrega_prevista ON pedidos(data_entrega_prevista)",
        "CREATE INDEX IF NOT EXISTS ix_pedido_itens_pedido_id ON pedido_itens(pedido_id)",
        "CREATE INDEX IF NOT EXISTS ix_pedido_itens_produto_id ON pedido_itens(produto_id)",
        "CREATE INDEX IF NOT EXISTS ix_pagamentos_pedido_id ON pagamentos(pedido_id)",
        "CREATE INDEX IF NOT EXISTS ix_entregas_pedido_id ON entregas_agendadas(pedido_id)",
        "CREATE INDEX IF NOT EXISTS ix_auditoria_entidade_registro ON auditoria_eventos(entidade, entidade_id, id)",
        "CREATE INDEX IF NOT EXISTS ix_auditoria_criado_em ON auditoria_eventos(criado_em)",
        "CREATE INDEX IF NOT EXISTS ix_operacoes_idempotentes_criado_em "
        "ON operacoes_idempotentes(criado_em)",
        "CREATE INDEX IF NOT EXISTS ix_auditoria_usuario_criado_em ON auditoria_eventos(usuario_id, criado_em)",
    ]
    for comando in comandos:
        conexao.execute(comando)

    indices_unicos = [
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_produtos_codigo "
        "ON produtos(codigo) WHERE ativo = 1",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_pedidos_numero ON pedidos(numero)",
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
            valor_centavos INTEGER,
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
            pedido_id INTEGER,
            parcela INTEGER NOT NULL DEFAULT 1,
            total_parcelas INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT fk_pagamentos_cliente_id_clientes
                FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE RESTRICT,
            -- RESTRICT, e nao CASCADE: apagar um pedido nao pode levar junto as
            -- parcelas dele. O dominio resolve isso por cancelamento, que
            -- preserva o registro.
            --
            -- Declarada aqui, no CREATE, porque SQLite nao aceita acrescentar
            -- constraint por ALTER TABLE -- e era exatamente por isso que a
            -- coluna vivia sem FK. Num banco que ja existe, quem cria a
            -- constraint e a migration a3b6f019c72d, recriando a tabela.
            CONSTRAINT fk_pagamentos_pedido_id_pedidos
                FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE RESTRICT
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
            pedido_id INTEGER,
            CONSTRAINT fk_entregas_agendadas_cliente_id_clientes
                FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE RESTRICT,
            CONSTRAINT fk_entregas_agendadas_pedido_id_pedidos
                FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL,
            descricao TEXT NOT NULL,
            unidade TEXT NOT NULL DEFAULT 'un',
            preco_venda_centavos INTEGER NOT NULL DEFAULT 0,
            observacoes TEXT NOT NULL DEFAULT '',
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            atualizado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT NOT NULL,
            cliente_id INTEGER NOT NULL,
            cliente_nome TEXT NOT NULL DEFAULT '',
            situacao TEXT NOT NULL DEFAULT 'rascunho',
            data_emissao TEXT NOT NULL DEFAULT (date('now', 'localtime')),
            data_entrega_prevista TEXT NOT NULL DEFAULT '',
            total_bruto_centavos INTEGER NOT NULL DEFAULT 0,
            desconto_centavos INTEGER NOT NULL DEFAULT 0,
            frete_centavos INTEGER NOT NULL DEFAULT 0,
            total_liquido_centavos INTEGER NOT NULL DEFAULT 0,
            observacoes TEXT NOT NULL DEFAULT '',
            criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            atualizado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            faturado_em TEXT NOT NULL DEFAULT '',
            cancelado_em TEXT NOT NULL DEFAULT '',
            motivo_cancelamento TEXT NOT NULL DEFAULT '',
            CONSTRAINT fk_pedidos_cliente_id_clientes
                FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE RESTRICT,
            CHECK (situacao IN ('rascunho', 'aberto', 'aprovado', 'faturado', 'cancelado'))
        );

        CREATE TABLE IF NOT EXISTS pedido_itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER NOT NULL,
            produto_id INTEGER NOT NULL,
            descricao TEXT NOT NULL,
            quantidade INTEGER NOT NULL DEFAULT 1,
            preco_unitario_centavos INTEGER NOT NULL,
            desconto_centavos INTEGER NOT NULL DEFAULT 0,
            total_centavos INTEGER NOT NULL,
            sequencia INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT fk_pedido_itens_pedido_id_pedidos
                FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE,
            CONSTRAINT fk_pedido_itens_produto_id_produtos
                FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE RESTRICT,
            CHECK (quantidade > 0)
        );

        CREATE TABLE IF NOT EXISTS operacoes_idempotentes (
            chave TEXT PRIMARY KEY,
            rota TEXT NOT NULL,
            metodo TEXT NOT NULL,
            -- `reservada` ate a rota responder; `concluida` depois. Uma
            -- reserva orfa (processo morreu no meio) e recolhida pela poda
            -- por idade.
            estado TEXT NOT NULL DEFAULT 'concluida',
            -- Hash de metodo + rota + corpo. Distingue "a mesma operacao,
            -- reenviada" de "chave reutilizada por engano em outra".
            impressao TEXT,
            -- Anulaveis: uma chave reservada ainda nao tem resposta.
            status INTEGER,
            corpo TEXT,
            criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
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

        -- Estado da licenca de uso do aplicativo. Precisa existir tambem
        -- aqui: um banco montado pelo caminho de emergencia que nao tivesse
        -- esta tabela faria `licenca.py` perder o lado do banco e passar a
        -- depender so do arquivo do perfil -- que e justamente o lado que se
        -- apaga com um clique.
        CREATE TABLE IF NOT EXISTS licenca (
            instalado_em TEXT NOT NULL DEFAULT '',
            visto_em TEXT NOT NULL DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'teste',
            pagamento_id TEXT NOT NULL DEFAULT '',
            pago_em TEXT NOT NULL DEFAULT '',
            referencia TEXT NOT NULL DEFAULT ''
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
        # Dinheiro em centavos inteiros. `valor` (REAL) continua sendo gravado
        # durante a transicao; ver a migration a3b6f019c72d para o porque.
        "valor_centavos": "INTEGER",
    }
    for coluna, declaracao in colunas_pagamentos.items():
        _garantir_coluna(conexao, "pagamentos", coluna, declaracao)

    # Backfill: um banco que veio pelo caminho de emergencia tem `valor` e nao
    # tem `valor_centavos`. ROUND antes de CAST -- CAST sozinho trunca, e um
    # centavo por linha nao e arredondamento, e erro.
    conexao.execute(
        "UPDATE pagamentos SET valor_centavos = "
        "CAST(ROUND(COALESCE(valor, 0) * 100) AS INTEGER) "
        "WHERE valor_centavos IS NULL"
    )

    # A sessao Microsoft ganhou refresh_token e validade do access_token.
    # Anulaveis: a linha gravada por uma versao anterior segue valida ate o
    # proximo login, que ja preenche as duas.
    # Vinculo do pagamento com o pedido que o originou. Anulaveis: os
    # lancamentos avulsos que ja existem nasceram sem pedido.
    colunas_idempotencia = {
        "estado": "TEXT NOT NULL DEFAULT 'concluida'",
        "impressao": "TEXT",
    }
    for coluna, declaracao in colunas_idempotencia.items():
        _garantir_coluna(conexao, "operacoes_idempotentes", coluna, declaracao)

    colunas_pagamentos_pedido = {
        "pedido_id": "INTEGER",
        "parcela": "INTEGER NOT NULL DEFAULT 1",
        "total_parcelas": "INTEGER NOT NULL DEFAULT 1",
    }
    for coluna, declaracao in colunas_pagamentos_pedido.items():
        _garantir_coluna(conexao, "pagamentos", coluna, declaracao)

    # De qual pedido esta entrega e. Anulavel pelo mesmo motivo.
    _garantir_coluna(conexao, "entregas_agendadas", "pedido_id", "INTEGER")

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
