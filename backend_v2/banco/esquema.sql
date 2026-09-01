-- ===========================================================================
-- Esquema do ERP Adri Poltronas (backend v2)
--
-- Tres decisoes estruturais, todas ausentes no v1:
--
-- 1. DINHEIRO E INTEIRO. Toda coluna monetaria termina em `_centavos` e e
--    INTEGER. O v1 usa REAL, que acumula erro binario ao somar milhares de
--    lancamentos -- num fechamento de caixa isso vira centavo faltando.
--
-- 2. ESTOQUE E RAZAO, NAO SALDO. `estoque_movimentos` e append-only; o saldo
--    e a soma dela. Guardar so um campo `quantidade` mutavel apaga a historia
--    e torna impossivel responder "por que o saldo mudou?".
--
-- 3. TITULO FINANCEIRO TEM BAIXAS. O status nao e um campo que alguem
--    sobrescreve: e derivado do quanto ja foi baixado. Assim recebimento
--    parcial existe, e o v1 nao tinha como representa-lo.
-- ===========================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- CADASTRO -- parceiro de negocio unico (cliente E/OU fornecedor)
--
-- Um cadastro so, com papeis. Duas tabelas separadas duplicariam endereco,
-- documento e contato de quem e os dois -- e transportadora que tambem compra
-- e caso comum.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS parceiros (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    nome              TEXT    NOT NULL,
    nome_fantasia     TEXT    NOT NULL DEFAULT '',
    documento         TEXT    NOT NULL DEFAULT '',
    tipo_documento    TEXT    NOT NULL DEFAULT '' CHECK (tipo_documento IN ('', 'CPF', 'CNPJ')),
    e_cliente         INTEGER NOT NULL DEFAULT 1 CHECK (e_cliente IN (0, 1)),
    e_fornecedor      INTEGER NOT NULL DEFAULT 0 CHECK (e_fornecedor IN (0, 1)),
    email             TEXT    NOT NULL DEFAULT '',
    telefone          TEXT    NOT NULL DEFAULT '',
    cep               TEXT    NOT NULL DEFAULT '',
    logradouro        TEXT    NOT NULL DEFAULT '',
    numero            TEXT    NOT NULL DEFAULT '',
    complemento       TEXT    NOT NULL DEFAULT '',
    bairro            TEXT    NOT NULL DEFAULT '',
    cidade            TEXT    NOT NULL DEFAULT '',
    uf                TEXT    NOT NULL DEFAULT '',
    entrega_retirada  TEXT    NOT NULL DEFAULT 'Entrega'
                              CHECK (entrega_retirada IN ('Entrega', 'Retirada')),
    observacoes       TEXT    NOT NULL DEFAULT '',
    ativo             INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    criado_em         TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    atualizado_em     TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    inativado_em      TEXT    NOT NULL DEFAULT '',
    CHECK (e_cliente = 1 OR e_fornecedor = 1)
);

-- Documento unico entre os ativos, quando informado. Indice PARCIAL porque
-- documento vazio e permitido e se repetiria.
CREATE UNIQUE INDEX IF NOT EXISTS ux_parceiros_documento
    ON parceiros(documento) WHERE documento != '' AND ativo = 1;
CREATE INDEX IF NOT EXISTS ix_parceiros_nome ON parceiros(nome);
CREATE INDEX IF NOT EXISTS ix_parceiros_papel ON parceiros(e_cliente, e_fornecedor, ativo);
CREATE INDEX IF NOT EXISTS ix_parceiros_cidade ON parceiros(cidade, ativo);

-- ---------------------------------------------------------------------------
-- CATALOGO
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS produtos (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo                 TEXT    NOT NULL,
    descricao              TEXT    NOT NULL,
    unidade                TEXT    NOT NULL DEFAULT 'UN',
    preco_venda_centavos   INTEGER NOT NULL DEFAULT 0 CHECK (preco_venda_centavos >= 0),
    custo_medio_centavos   INTEGER NOT NULL DEFAULT 0 CHECK (custo_medio_centavos >= 0),
    -- Servico (frete, montagem) entra em pedido mas nao movimenta saldo. Sem
    -- esta flag, todo servico vendido geraria saldo negativo eterno.
    controla_estoque       INTEGER NOT NULL DEFAULT 1 CHECK (controla_estoque IN (0, 1)),
    estoque_minimo         INTEGER NOT NULL DEFAULT 0 CHECK (estoque_minimo >= 0),
    ativo                  INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    criado_em              TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    atualizado_em          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_produtos_codigo ON produtos(codigo) WHERE ativo = 1;
CREATE INDEX IF NOT EXISTS ix_produtos_descricao ON produtos(descricao);

-- ---------------------------------------------------------------------------
-- ESTOQUE -- razao append-only
--
-- `quantidade` e assinada: entrada positiva, saida negativa. Somar a coluna da
-- o saldo, e nenhuma linha e jamais alterada ou apagada. Estorno e um
-- movimento novo, de sinal oposto, apontando para o original.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS estoque_movimentos (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id              INTEGER NOT NULL REFERENCES produtos(id) ON DELETE RESTRICT,
    tipo                    TEXT    NOT NULL CHECK (tipo IN
                                ('entrada_compra', 'saida_venda', 'ajuste_positivo',
                                 'ajuste_negativo', 'estorno', 'inventario')),
    quantidade              INTEGER NOT NULL CHECK (quantidade != 0),
    custo_unitario_centavos INTEGER NOT NULL DEFAULT 0 CHECK (custo_unitario_centavos >= 0),
    origem_tipo             TEXT    NOT NULL DEFAULT '',
    origem_id               INTEGER,
    movimento_estornado_id  INTEGER REFERENCES estoque_movimentos(id),
    observacao              TEXT    NOT NULL DEFAULT '',
    criado_em               TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS ix_estoque_produto ON estoque_movimentos(produto_id, id);
CREATE INDEX IF NOT EXISTS ix_estoque_origem ON estoque_movimentos(origem_tipo, origem_id);

-- ---------------------------------------------------------------------------
-- NUMERACAO de documentos por especie e exercicio
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS numeracao (
    especie   TEXT    NOT NULL,
    exercicio INTEGER NOT NULL,
    ultimo    INTEGER NOT NULL DEFAULT 0 CHECK (ultimo >= 0),
    PRIMARY KEY (especie, exercicio)
);

-- ---------------------------------------------------------------------------
-- VENDAS -- orcamento e pedido sao o MESMO documento em estados diferentes
--
-- Duas tabelas obrigariam a copiar itens do orcamento para o pedido na
-- aprovacao, e a partir dai as duas versoes divergem. Aqui aprovar e uma
-- transicao de estado; o historico do documento fica inteiro.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documentos_venda (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    numero                 TEXT    NOT NULL,
    especie                TEXT    NOT NULL DEFAULT 'pedido'
                                   CHECK (especie IN ('orcamento', 'pedido')),
    situacao               TEXT    NOT NULL DEFAULT 'rascunho' CHECK (situacao IN
                               ('rascunho', 'aberto', 'aprovado', 'faturado', 'cancelado')),
    parceiro_id            INTEGER NOT NULL REFERENCES parceiros(id) ON DELETE RESTRICT,
    data_emissao           TEXT    NOT NULL DEFAULT (date('now', 'localtime')),
    data_validade          TEXT    NOT NULL DEFAULT '',
    data_entrega_prevista  TEXT    NOT NULL DEFAULT '',
    -- Totais gravados: o valor de um documento fechado nao pode mudar so
    -- porque alguem editou o preco do produto no catalogo depois.
    total_bruto_centavos   INTEGER NOT NULL DEFAULT 0,
    desconto_centavos      INTEGER NOT NULL DEFAULT 0 CHECK (desconto_centavos >= 0),
    frete_centavos         INTEGER NOT NULL DEFAULT 0 CHECK (frete_centavos >= 0),
    total_liquido_centavos INTEGER NOT NULL DEFAULT 0,
    condicao_pagamento     TEXT    NOT NULL DEFAULT 'a_vista',
    observacoes            TEXT    NOT NULL DEFAULT '',
    criado_em              TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    atualizado_em          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    faturado_em            TEXT    NOT NULL DEFAULT '',
    cancelado_em           TEXT    NOT NULL DEFAULT ''
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_venda_numero ON documentos_venda(numero);
CREATE INDEX IF NOT EXISTS ix_venda_parceiro ON documentos_venda(parceiro_id, id);
CREATE INDEX IF NOT EXISTS ix_venda_situacao ON documentos_venda(situacao, data_emissao);

CREATE TABLE IF NOT EXISTS documentos_venda_itens (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_id            INTEGER NOT NULL REFERENCES documentos_venda(id) ON DELETE CASCADE,
    produto_id              INTEGER NOT NULL REFERENCES produtos(id) ON DELETE RESTRICT,
    -- Descricao copiada no lancamento: renomear o produto no catalogo nao pode
    -- reescrever um pedido ja emitido.
    descricao               TEXT    NOT NULL,
    quantidade              INTEGER NOT NULL CHECK (quantidade > 0),
    preco_unitario_centavos INTEGER NOT NULL CHECK (preco_unitario_centavos >= 0),
    desconto_centavos       INTEGER NOT NULL DEFAULT 0 CHECK (desconto_centavos >= 0),
    total_centavos          INTEGER NOT NULL CHECK (total_centavos >= 0),
    sequencia               INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS ix_venda_item_doc ON documentos_venda_itens(documento_id, sequencia);
CREATE INDEX IF NOT EXISTS ix_venda_item_produto ON documentos_venda_itens(produto_id);

-- ---------------------------------------------------------------------------
-- COMPRAS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documentos_compra (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    numero                 TEXT    NOT NULL,
    situacao               TEXT    NOT NULL DEFAULT 'rascunho' CHECK (situacao IN
                               ('rascunho', 'aberto', 'recebido', 'cancelado')),
    parceiro_id            INTEGER NOT NULL REFERENCES parceiros(id) ON DELETE RESTRICT,
    data_emissao           TEXT    NOT NULL DEFAULT (date('now', 'localtime')),
    data_prevista          TEXT    NOT NULL DEFAULT '',
    total_bruto_centavos   INTEGER NOT NULL DEFAULT 0,
    desconto_centavos      INTEGER NOT NULL DEFAULT 0 CHECK (desconto_centavos >= 0),
    frete_centavos         INTEGER NOT NULL DEFAULT 0 CHECK (frete_centavos >= 0),
    total_liquido_centavos INTEGER NOT NULL DEFAULT 0,
    condicao_pagamento     TEXT    NOT NULL DEFAULT 'a_vista',
    observacoes            TEXT    NOT NULL DEFAULT '',
    criado_em              TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    atualizado_em          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    recebido_em            TEXT    NOT NULL DEFAULT '',
    cancelado_em           TEXT    NOT NULL DEFAULT ''
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_compra_numero ON documentos_compra(numero);
CREATE INDEX IF NOT EXISTS ix_compra_parceiro ON documentos_compra(parceiro_id, id);
CREATE INDEX IF NOT EXISTS ix_compra_situacao ON documentos_compra(situacao, data_emissao);

CREATE TABLE IF NOT EXISTS documentos_compra_itens (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_id            INTEGER NOT NULL REFERENCES documentos_compra(id) ON DELETE CASCADE,
    produto_id              INTEGER NOT NULL REFERENCES produtos(id) ON DELETE RESTRICT,
    descricao               TEXT    NOT NULL,
    quantidade              INTEGER NOT NULL CHECK (quantidade > 0),
    preco_unitario_centavos INTEGER NOT NULL CHECK (preco_unitario_centavos >= 0),
    total_centavos          INTEGER NOT NULL CHECK (total_centavos >= 0),
    sequencia               INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS ix_compra_item_doc ON documentos_compra_itens(documento_id, sequencia);

-- ---------------------------------------------------------------------------
-- FINANCEIRO -- titulos a receber e a pagar, com baixas
--
-- `natureza` distingue receber de pagar: a mecanica (vencimento, baixa
-- parcial, juros, cancelamento) e identica nas duas pontas, e duplicar a
-- tabela duplicaria toda a regra junto.
--
-- NAO existe coluna `status`. A situacao vem de valor_baixado vs valor: ver a
-- view `titulos_situacao` abaixo. Um campo mutavel e o que permitiu, no v1,
-- um PUT sem `status` reverter uma cobranca ja recebida.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS titulos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    numero              TEXT    NOT NULL,
    natureza            TEXT    NOT NULL CHECK (natureza IN ('receber', 'pagar')),
    parceiro_id         INTEGER NOT NULL REFERENCES parceiros(id) ON DELETE RESTRICT,
    origem_tipo         TEXT    NOT NULL DEFAULT '',
    origem_id           INTEGER,
    parcela             INTEGER NOT NULL DEFAULT 1 CHECK (parcela > 0),
    total_parcelas      INTEGER NOT NULL DEFAULT 1 CHECK (total_parcelas > 0),
    descricao           TEXT    NOT NULL DEFAULT '',
    valor_centavos      INTEGER NOT NULL CHECK (valor_centavos > 0),
    data_emissao        TEXT    NOT NULL DEFAULT (date('now', 'localtime')),
    data_vencimento     TEXT    NOT NULL,
    forma_pagamento     TEXT    NOT NULL DEFAULT 'dinheiro',
    cancelado           INTEGER NOT NULL DEFAULT 0 CHECK (cancelado IN (0, 1)),
    cancelado_em        TEXT    NOT NULL DEFAULT '',
    motivo_cancelamento TEXT    NOT NULL DEFAULT '',
    observacoes         TEXT    NOT NULL DEFAULT '',
    criado_em           TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    -- Vencimento nunca vazio: no v1 a coluna aceitava '' e, como no SQLite
    -- '' < qualquer data, TODO titulo sem vencimento entrava como atrasado.
    CHECK (data_vencimento != ''),
    CHECK (parcela <= total_parcelas)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_titulo_numero ON titulos(numero);
CREATE INDEX IF NOT EXISTS ix_titulo_parceiro ON titulos(parceiro_id, id);
CREATE INDEX IF NOT EXISTS ix_titulo_vencimento ON titulos(natureza, data_vencimento, cancelado);
CREATE INDEX IF NOT EXISTS ix_titulo_origem ON titulos(origem_tipo, origem_id);

-- Baixa: cada pagamento/recebimento, total ou parcial. Append-only.
CREATE TABLE IF NOT EXISTS titulo_baixas (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo_id          INTEGER NOT NULL REFERENCES titulos(id) ON DELETE RESTRICT,
    conta_id           INTEGER NOT NULL REFERENCES contas_financeiras(id) ON DELETE RESTRICT,
    valor_centavos     INTEGER NOT NULL CHECK (valor_centavos > 0),
    juros_centavos     INTEGER NOT NULL DEFAULT 0 CHECK (juros_centavos >= 0),
    desconto_centavos  INTEGER NOT NULL DEFAULT 0 CHECK (desconto_centavos >= 0),
    data_baixa         TEXT    NOT NULL DEFAULT (date('now', 'localtime')),
    forma_pagamento    TEXT    NOT NULL DEFAULT 'dinheiro',
    observacao         TEXT    NOT NULL DEFAULT '',
    estornada          INTEGER NOT NULL DEFAULT 0 CHECK (estornada IN (0, 1)),
    estornada_em       TEXT    NOT NULL DEFAULT '',
    criado_em          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS ix_baixa_titulo ON titulo_baixas(titulo_id, estornada);
CREATE INDEX IF NOT EXISTS ix_baixa_data ON titulo_baixas(data_baixa, estornada);

-- ---------------------------------------------------------------------------
-- CAIXA E BANCOS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contas_financeiras (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    nome                   TEXT    NOT NULL,
    tipo                   TEXT    NOT NULL DEFAULT 'caixa'
                                   CHECK (tipo IN ('caixa', 'banco', 'aplicacao')),
    banco                  TEXT    NOT NULL DEFAULT '',
    agencia                TEXT    NOT NULL DEFAULT '',
    conta                  TEXT    NOT NULL DEFAULT '',
    saldo_inicial_centavos INTEGER NOT NULL DEFAULT 0,
    ativo                  INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    criado_em              TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_conta_nome ON contas_financeiras(nome) WHERE ativo = 1;

-- Razao do caixa. Como o estoque: append-only, saldo derivado da soma.
CREATE TABLE IF NOT EXISTS movimentos_caixa (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    conta_id       INTEGER NOT NULL REFERENCES contas_financeiras(id) ON DELETE RESTRICT,
    tipo           TEXT    NOT NULL CHECK (tipo IN
                       ('recebimento', 'pagamento', 'transferencia_entrada',
                        'transferencia_saida', 'ajuste', 'estorno')),
    valor_centavos INTEGER NOT NULL CHECK (valor_centavos != 0),
    data_movimento TEXT    NOT NULL DEFAULT (date('now', 'localtime')),
    baixa_id       INTEGER REFERENCES titulo_baixas(id),
    descricao      TEXT    NOT NULL DEFAULT '',
    criado_em      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS ix_caixa_conta ON movimentos_caixa(conta_id, data_movimento);
CREATE INDEX IF NOT EXISTS ix_caixa_data ON movimentos_caixa(data_movimento);
CREATE INDEX IF NOT EXISTS ix_caixa_baixa ON movimentos_caixa(baixa_id);

-- ---------------------------------------------------------------------------
-- OPERACIONAL -- entregas (o que o v1 ja tinha, agora ligado ao documento)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entregas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    parceiro_id    INTEGER NOT NULL REFERENCES parceiros(id) ON DELETE RESTRICT,
    documento_id   INTEGER REFERENCES documentos_venda(id) ON DELETE SET NULL,
    data_prevista  TEXT    NOT NULL,
    hora_prevista  TEXT    NOT NULL DEFAULT '',
    situacao       TEXT    NOT NULL DEFAULT 'pendente' CHECK (situacao IN
                       ('pendente', 'em_rota', 'concluida', 'cancelada')),
    endereco       TEXT    NOT NULL DEFAULT '',
    descricao      TEXT    NOT NULL DEFAULT '',
    criado_em      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    concluida_em   TEXT    NOT NULL DEFAULT '',
    CHECK (data_prevista != '')
);

CREATE INDEX IF NOT EXISTS ix_entrega_data ON entregas(data_prevista, situacao);
CREATE INDEX IF NOT EXISTS ix_entrega_parceiro ON entregas(parceiro_id);

-- ---------------------------------------------------------------------------
-- AUDITORIA -- trilha append-only, gravada na MESMA transacao do negocio
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS auditoria_eventos (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    acao               TEXT    NOT NULL,
    entidade           TEXT    NOT NULL,
    entidade_id        TEXT,
    valores_anteriores TEXT,
    valores_novos      TEXT,
    usuario_id         TEXT,
    usuario_nome       TEXT,
    origem             TEXT    NOT NULL DEFAULT 'backend_v2',
    correlation_id     TEXT,
    contexto           TEXT    NOT NULL DEFAULT '{}',
    criado_em          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS ix_auditoria_entidade ON auditoria_eventos(entidade, entidade_id, id);
CREATE INDEX IF NOT EXISTS ix_auditoria_criado ON auditoria_eventos(criado_em);
CREATE INDEX IF NOT EXISTS ix_auditoria_correlacao ON auditoria_eventos(correlation_id);

-- ---------------------------------------------------------------------------
-- VIEWS -- situacao derivada, para nenhuma tela ter que recalcular
-- ---------------------------------------------------------------------------

-- Saldo de estoque por produto: a soma da razao, nunca um campo guardado.
CREATE VIEW IF NOT EXISTS estoque_saldos AS
SELECT p.id                                   AS produto_id,
       p.codigo                               AS codigo,
       p.descricao                            AS descricao,
       p.estoque_minimo                       AS estoque_minimo,
       COALESCE(SUM(m.quantidade), 0)         AS saldo,
       CASE WHEN COALESCE(SUM(m.quantidade), 0) <= p.estoque_minimo THEN 1 ELSE 0 END
                                              AS abaixo_do_minimo
  FROM produtos p
  LEFT JOIN estoque_movimentos m ON m.produto_id = p.id
 WHERE p.ativo = 1 AND p.controla_estoque = 1
 GROUP BY p.id, p.codigo, p.descricao, p.estoque_minimo;

-- Situacao do titulo, derivada das baixas nao estornadas.
CREATE VIEW IF NOT EXISTS titulos_situacao AS
SELECT t.id                                            AS titulo_id,
       t.numero                                        AS numero,
       t.natureza                                      AS natureza,
       t.parceiro_id                                   AS parceiro_id,
       t.valor_centavos                                AS valor_centavos,
       t.data_vencimento                               AS data_vencimento,
       t.cancelado                                     AS cancelado,
       COALESCE(SUM(CASE WHEN b.estornada = 0 THEN b.valor_centavos END), 0)
                                                       AS baixado_centavos,
       t.valor_centavos
         - COALESCE(SUM(CASE WHEN b.estornada = 0 THEN b.valor_centavos END), 0)
                                                       AS saldo_centavos,
       CASE
           WHEN t.cancelado = 1 THEN 'cancelado'
           WHEN COALESCE(SUM(CASE WHEN b.estornada = 0 THEN b.valor_centavos END), 0)
                >= t.valor_centavos THEN 'quitado'
           WHEN COALESCE(SUM(CASE WHEN b.estornada = 0 THEN b.valor_centavos END), 0) > 0
                THEN 'parcial'
           WHEN date(t.data_vencimento) < date('now', 'localtime') THEN 'vencido'
           ELSE 'aberto'
       END                                             AS situacao
  FROM titulos t
  LEFT JOIN titulo_baixas b ON b.titulo_id = t.id
 GROUP BY t.id;

-- Saldo por conta financeira.
CREATE VIEW IF NOT EXISTS contas_saldos AS
SELECT c.id                                                AS conta_id,
       c.nome                                              AS nome,
       c.tipo                                              AS tipo,
       c.saldo_inicial_centavos                            AS saldo_inicial_centavos,
       c.saldo_inicial_centavos + COALESCE(SUM(m.valor_centavos), 0)
                                                           AS saldo_centavos
  FROM contas_financeiras c
  LEFT JOIN movimentos_caixa m ON m.conta_id = c.id
 WHERE c.ativo = 1
 GROUP BY c.id;
