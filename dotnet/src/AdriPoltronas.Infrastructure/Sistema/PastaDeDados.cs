namespace AdriPoltronas.Infrastructure.Sistema;

/// <summary>
/// Onde ficam banco, configuracao e logs do usuario.
/// </summary>
/// <remarks>
/// Encapsula a unica diferenca real entre os sistemas operacionais que o app
/// suporta. <see cref="Environment.SpecialFolder.ApplicationData"/> resolve
/// para <c>%APPDATA%</c> no Windows e para <c>~/.config</c> no Linux e no
/// macOS, entao nao ha <c>#if WINDOWS</c> em lugar nenhum do codigo.
///
/// <para><b>Banco separado, por decisao.</b> Ate a versao 1.1 esta classe
/// apontava para <c>adri_poltronas.db</c> -- o MESMO arquivo do backend
/// Python. Duas pilhas escrevendo no mesmo SQLite, com dominios e sistemas de
/// migracao diferentes, e o defeito estrutural que o diagnostico apontou:</para>
/// <list type="bullet">
///   <item>o Python inativa cliente (<c>ativo = 0</c>); o EF Core remove a
///         linha, e com ela o historico que aponta para o cliente;</item>
///   <item>o ledger <c>auditoria_eventos</c> so e alimentado pelo Python, entao
///         toda escrita vinda do .NET era invisivel na trilha de auditoria;</item>
///   <item>Alembic e EF Core versionam o schema de formas incompativeis. Se o
///         .NET criasse o arquivo primeiro, o banco nasceria sem
///         <c>alembic_version</c> e a migracao inicial do Python tentaria criar
///         tabelas ja existentes;</item>
///   <item>o .NET ainda nao tem catalogo nem pedidos, entao nao ha paridade
///         funcional que justifique o risco.</item>
/// </list>
/// <para>Enquanto essa paridade nao existir, o dono do dado de producao e o
/// Electron/Flask. O .NET trabalha na propria copia. Quem precisar apontar as
/// duas pilhas para o mesmo arquivo -- para um teste de compatibilidade, por
/// exemplo -- passa <c>Banco__ConexaoString</c> explicitamente: e uma decisao
/// consciente, nao mais o comportamento padrao.</para>
/// </remarks>
public static class PastaDeDados
{
    public const string NomeDaPasta = "AdriPoltronas";

    /// <summary>Banco do backend Python. Fonte de verdade da operacao.</summary>
    public const string NomeDoBancoDoBackend = "adri_poltronas.db";

    /// <summary>Banco desta aplicacao. Arquivo proprio, sem escritor concorrente.</summary>
    public const string NomeDoBanco = "adri_poltronas_dotnet.db";

    public static string Raiz()
    {
        var baseDoUsuario = Environment.GetFolderPath(
            Environment.SpecialFolder.ApplicationData,
            // DoNotVerify: em uma conta recem-criada a pasta pode ainda nao
            // existir, e sem isso o retorno seria string vazia.
            Environment.SpecialFolderOption.DoNotVerify);

        if (string.IsNullOrWhiteSpace(baseDoUsuario))
        {
            baseDoUsuario = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".config");
        }

        var raiz = Path.Combine(baseDoUsuario, NomeDaPasta);
        Directory.CreateDirectory(raiz);
        return raiz;
    }

    public static string CaminhoDoBanco() => Path.Combine(Raiz(), NomeDoBanco);

    /// <summary>
    /// Caminho do banco do backend Python. Existe para leitura pontual --
    /// diagnostico, importacao inicial --, nunca para escrita concorrente.
    /// </summary>
    public static string CaminhoDoBancoDoBackend() => Path.Combine(Raiz(), NomeDoBancoDoBackend);

    public static string PastaDeLogs()
    {
        var pasta = Path.Combine(Raiz(), "logs");
        Directory.CreateDirectory(pasta);
        return pasta;
    }
}
