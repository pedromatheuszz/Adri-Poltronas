using System.Globalization;
using AdriPoltronas.Domain.Enums;
using Avalonia.Data.Converters;
using Avalonia.Media;

namespace AdriPoltronas.Desktop.Converters;

/// <summary>
/// Pinta a coluna Tipo: verde para entrega, ambar para retirada.
/// </summary>
/// <remarks>
/// E logica de apresentacao pura, e por isso mora aqui e nao no ViewModel. As
/// cores sao as mesmas dos badges da interface web e dos marcadores do mapa --
/// quem usa as duas telas reconhece o tipo pela cor antes de ler o texto.
/// </remarks>
public sealed class TipoParaCorConverter : IValueConverter
{
    private static readonly SolidColorBrush Entrega = new(Color.Parse("#10B981"));
    private static readonly SolidColorBrush Retirada = new(Color.Parse("#F59E0B"));
    private static readonly SolidColorBrush Neutro = new(Color.Parse("#94A3B8"));

    public object Convert(object? valor, Type tipoDestino, object? parametro, CultureInfo cultura) =>
        (valor as string) switch
        {
            TipoAtendimentoExtensions.TextoEntrega => Entrega,
            TipoAtendimentoExtensions.TextoRetirada => Retirada,
            // Cadastro antigo pode ter o campo em branco; cinza evita a linha
            // sem cor nenhuma, que pareceria um defeito de renderizacao.
            _ => Neutro,
        };

    public object ConvertBack(object? valor, Type tipoDestino, object? parametro, CultureInfo cultura) =>
        throw new NotSupportedException("A coluna Tipo e somente leitura.");
}
