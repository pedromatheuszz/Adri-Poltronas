using AdriPoltronas.Infrastructure.Persistence;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;

namespace AdriPoltronas.Infrastructure.Tests;

/// <summary>
/// Um banco temporario com o schema que o backend Python usa hoje.
/// </summary>
/// <remarks>
/// O DDL abaixo e copia fiel do que existe na base em producao -- incluindo as
/// colunas <c>ativo</c> e <c>excluido_em</c>, que o codigo Python nunca
/// preencheu, e a tabela <c>alembic_version</c>.
///
/// Testar contra o schema real, e nao contra um criado pelo proprio EF, e o
/// unico jeito de provar o que interessa aqui: que o mapeamento le e escreve a
/// base que ja existe, sem exigir migracao e sem quebrar o backend que continua
/// lendo as mesmas linhas.
/// </remarks>
public sealed class BancoLegado : IDisposable
{
    private readonly string _arquivo;

    public BancoLegado(bool comAlembic = true)
    {
        _arquivo = Path.Combine(Path.GetTempPath(), $"adri-teste-{Guid.NewGuid():N}.db");
        Conexao = $"Data Source={_arquivo}";

        using var conexao = new SqliteConnection(Conexao);
        conexao.Open();
        Executar(conexao, DdlClientes);
        Executar(conexao, DdlHistorico);
        Executar(conexao, DdlPagamentos);
        Executar(conexao, DdlEntregas);
        Executar(conexao, DdlNotificacoesLidas);
        if (comAlembic)
        {
            Executar(conexao, DdlAlembic);
            Executar(conexao, "INSERT INTO alembic_version (version_num) VALUES ('a1b2c3d4e5f6')");
        }
    }

    public string Conexao { get; }

    public AdriPoltronasDbContext AbrirContexto()
    {
        var opcoes = new DbContextOptionsBuilder<AdriPoltronasDbContext>()
            .UseSqlite(Conexao)
            .Options;
        return new AdriPoltronasDbContext(opcoes);
    }

    /// <summary>Insere uma linha pelo caminho do Python: SQL cru, sem o EF.</summary>
    public void InserirComoOPythonInsere(
        string nome, string cep, string rua, string bairro, string cidade,
        string tipo, string criadoEm)
    {
        using var conexao = new SqliteConnection(Conexao);
        conexao.Open();
        using var comando = conexao.CreateCommand();
        comando.CommandText = """
            INSERT INTO clientes
                (nome, cep, rua, bairro, cidade, entrega_retirada, observacoes,
                 criado_em, atualizado_em)
            VALUES ($nome, $cep, $rua, $bairro, $cidade, $tipo, '', $criado, $criado)
            """;
        comando.Parameters.AddWithValue("$nome", nome);
        comando.Parameters.AddWithValue("$cep", cep);
        comando.Parameters.AddWithValue("$rua", rua);
        comando.Parameters.AddWithValue("$bairro", bairro);
        comando.Parameters.AddWithValue("$cidade", cidade);
        comando.Parameters.AddWithValue("$tipo", tipo);
        comando.Parameters.AddWithValue("$criado", criadoEm);
        comando.ExecuteNonQuery();
    }

    /// <summary>Le uma coluna direto do arquivo, para conferir o que foi gravado.</summary>
    public string LerTexto(string sql)
    {
        using var conexao = new SqliteConnection(Conexao);
        conexao.Open();
        using var comando = conexao.CreateCommand();
        comando.CommandText = sql;
        return comando.ExecuteScalar()?.ToString() ?? string.Empty;
    }

    public long Contar(string tabela)
    {
        using var conexao = new SqliteConnection(Conexao);
        conexao.Open();
        using var comando = conexao.CreateCommand();
        // Nome de tabela vem de constante do proprio teste, nunca de entrada.
        comando.CommandText = $"SELECT COUNT(*) FROM {tabela}";
        return Convert.ToInt64(comando.ExecuteScalar());
    }

    public void Dispose()
    {
        SqliteConnection.ClearAllPools();
        if (File.Exists(_arquivo))
        {
            File.Delete(_arquivo);
        }
    }

    private static void Executar(SqliteConnection conexao, string sql)
    {
        using var comando = conexao.CreateCommand();
        comando.CommandText = sql;
        comando.ExecuteNonQuery();
    }

    private const string DdlClientes = """
        CREATE TABLE clientes (
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
            excluido_em TEXT DEFAULT '')
        """;

    private const string DdlHistorico = """
        CREATE TABLE historico (
            id INTEGER,
            cliente_id INTEGER,
            cliente_nome TEXT,
            acao TEXT NOT NULL,
            detalhes TEXT DEFAULT (''),
            data_hora TEXT DEFAULT (datetime('now', 'localtime')),
            PRIMARY KEY (id),
            CONSTRAINT fk_historico_cliente FOREIGN KEY(cliente_id)
                REFERENCES clientes (id) ON DELETE SET NULL)
        """;

    private const string DdlPagamentos = """
        CREATE TABLE pagamentos (
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
            nosso_numero TEXT DEFAULT '')
        """;

    private const string DdlEntregas = """
        CREATE TABLE entregas_agendadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            cliente_nome TEXT DEFAULT '',
            data_entrega TEXT NOT NULL,
            hora_entrega TEXT DEFAULT '',
            descricao TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Pendente',
            criado_em TEXT DEFAULT (datetime('now', 'localtime')))
        """;

    private const string DdlNotificacoesLidas = """
        CREATE TABLE notificacoes_lidas (
            chave TEXT PRIMARY KEY,
            lida_em TEXT DEFAULT (datetime('now', 'localtime')))
        """;

    private const string DdlAlembic = """
        CREATE TABLE alembic_version (
            version_num VARCHAR(32) NOT NULL,
            CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))
        """;
}
