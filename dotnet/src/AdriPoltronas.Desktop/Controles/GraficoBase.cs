using AdriPoltronas.Application.Dtos;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Media;
using Avalonia.Styling;
using Avalonia.VisualTree;

namespace AdriPoltronas.Desktop.Controles;

/// <summary>
/// Base dos graficos desenhados a mao.
/// </summary>
/// <remarks>
/// Sem biblioteca de graficos. Sao tres formas simples -- barras, linha e
/// rosca -- e uma dependencia externa para isso traria tema proprio,
/// licenciamento e uma superficie de API inteira para manter. O desenho direto
/// cabe em poucas dezenas de linhas e acompanha a paleta do aplicativo sem
/// adaptador.
/// </remarks>
public abstract class GraficoBase : Control
{
    public static readonly StyledProperty<IReadOnlyList<PontoDoGrafico>?> PontosProperty =
        AvaloniaProperty.Register<GraficoBase, IReadOnlyList<PontoDoGrafico>?>(nameof(Pontos));

    protected GraficoBase()
    {
        // Sem isto o grafico ficaria com os dados da primeira carga: mudar a
        // colecao nao redesenha por conta propria.
        PontosProperty.Changed.AddClassHandler<GraficoBase>((grafico, _) =>
            grafico.InvalidateVisual());
    }

    /// <summary>
    /// Redesenha quando o tema muda.
    /// </summary>
    /// <remarks>
    /// As cores sao lidas dentro do <c>Render</c>, entao trocar de claro para
    /// escuro nao chega ao grafico por si so -- ele fica com os tons do tema
    /// anterior ate algum outro motivo forcar o redesenho.
    /// </remarks>
    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs evento)
    {
        base.OnAttachedToVisualTree(evento);
        if (Avalonia.Application.Current is { } aplicacao)
        {
            aplicacao.ActualThemeVariantChanged += AoMudarOTema;
        }
    }

    protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs evento)
    {
        if (Avalonia.Application.Current is { } aplicacao)
        {
            aplicacao.ActualThemeVariantChanged -= AoMudarOTema;
        }

        base.OnDetachedFromVisualTree(evento);
    }

    private void AoMudarOTema(object? remetente, EventArgs evento) => InvalidateVisual();

    public IReadOnlyList<PontoDoGrafico>? Pontos
    {
        get => GetValue(PontosProperty);
        set => SetValue(PontosProperty, value);
    }

    /// <summary>Pontos validos para desenhar, ou vazio.</summary>
    protected IReadOnlyList<PontoDoGrafico> Dados => Pontos ?? [];

    /// <summary>Cor do tema, buscada por chave para acompanhar claro e escuro.</summary>
    protected IBrush Pincel(string chave, string alternativa)
    {
        var variante = (this.GetVisualRoot() as ThemeVariantScope)?.ActualThemeVariant
                       ?? Avalonia.Application.Current?.ActualThemeVariant;

        if (Avalonia.Application.Current?.TryGetResource(chave, variante, out var valor) == true &&
            valor is IBrush pincel)
        {
            return pincel;
        }

        return new SolidColorBrush(Color.Parse(alternativa));
    }

    protected void DesenharAviso(DrawingContext contexto, string texto)
    {
        var formatado = Texto(texto, 12, Pincel("TextoFraco", "#94A3B8"));
        contexto.DrawText(formatado, new Point(
            (Bounds.Width - formatado.Width) / 2,
            (Bounds.Height - formatado.Height) / 2));
    }

    protected FormattedText Texto(string valor, double tamanho, IBrush cor) =>
        new(valor,
            System.Globalization.CultureInfo.CurrentCulture,
            FlowDirection.LeftToRight,
            new Typeface(FontFamily.Default),
            tamanho,
            cor);
}
