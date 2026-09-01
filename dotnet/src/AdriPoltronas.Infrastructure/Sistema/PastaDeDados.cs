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
/// O nome da pasta e o mesmo que o backend Python ja usa
/// (<c>AdriPoltronas</c>), porque as duas pilhas leem o mesmo banco enquanto a
/// migracao nao termina.
/// </remarks>
public static class PastaDeDados
{
    public const string NomeDaPasta = "AdriPoltronas";
    public const string NomeDoBanco = "adri_poltronas.db";

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

    public static string PastaDeLogs()
    {
        var pasta = Path.Combine(Raiz(), "logs");
        Directory.CreateDirectory(pasta);
        return pasta;
    }
}
