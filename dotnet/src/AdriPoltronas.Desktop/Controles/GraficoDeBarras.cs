using Avalonia;
using Avalonia.Media;

namespace AdriPoltronas.Desktop.Controles;

/// <summary>Barras verticais com rotulo embaixo e valor no topo.</summary>
public sealed class GraficoDeBarras : GraficoBase
{
    private const double AlturaDoRotulo = 22;
    private const double AlturaDoValor = 16;
    private const double EspacoEntreBarras = 10;

    /// <summary>
    /// Teto da largura de uma barra.
    /// </summary>
    /// <remarks>
    /// Sem ele, uma serie de um item so vira um bloco ocupando o painel
    /// inteiro -- que nao comunica quantidade nenhuma, so preenche espaco.
    /// </remarks>
    private const double LarguraMaxima = 72;

    public override void Render(DrawingContext contexto)
    {
        var dados = Dados;
        if (dados.Count == 0)
        {
            DesenharAviso(contexto, "Sem dados no periodo.");
            return;
        }

        var destaque = Pincel("Destaque", "#3B82F6");
        var fraco = Pincel("TextoFraco", "#94A3B8");
        var grade = Pincel("Grade", "#243349");

        var alturaUtil = Bounds.Height - AlturaDoRotulo - AlturaDoValor;
        if (alturaUtil <= 0)
        {
            return;
        }

        // Linha de base: sem ela as barras pequenas parecem flutuar.
        contexto.DrawLine(
            new Pen(grade),
            new Point(0, AlturaDoValor + alturaUtil),
            new Point(Bounds.Width, AlturaDoValor + alturaUtil));

        var maior = dados.Max(p => p.Valor);
        var disponivel = (Bounds.Width - (EspacoEntreBarras * (dados.Count - 1))) / dados.Count;
        var largura = Math.Min(disponivel, LarguraMaxima);

        // Poucas barras ficam centradas em vez de encostadas a esquerda.
        var recuo = (Bounds.Width -
            ((largura * dados.Count) + (EspacoEntreBarras * (dados.Count - 1)))) / 2;

        for (var indice = 0; indice < dados.Count; indice++)
        {
            var ponto = dados[indice];
            var esquerda = recuo + (indice * (largura + EspacoEntreBarras));

            // Maior igual a zero significa serie toda zerada; desenhar altura
            // cheia daria a impressao de movimento que nao houve.
            var altura = maior <= 0 ? 0 : ponto.Valor / maior * alturaUtil;
            var topo = AlturaDoValor + alturaUtil - altura;

            if (altura > 0)
            {
                contexto.DrawRectangle(
                    destaque, null,
                    new RoundedRect(new Rect(esquerda, topo, largura, altura), 5, 5, 0, 0));
            }

            var valor = Texto(Formatar(ponto.Valor), 10, fraco);
            contexto.DrawText(valor, new Point(
                esquerda + ((largura - valor.Width) / 2), Math.Max(topo - 14, 0)));

            var rotulo = Texto(ponto.Rotulo, 10, fraco);
            contexto.DrawText(rotulo, new Point(
                esquerda + ((largura - rotulo.Width) / 2),
                AlturaDoValor + alturaUtil + 5));
        }
    }

    /// <summary>Milhar abreviado: numero longo estoura a largura da barra.</summary>
    private static string Formatar(double valor) => valor switch
    {
        >= 1_000_000 => $"{valor / 1_000_000:0.#}M",
        >= 1_000 => $"{valor / 1_000:0.#}k",
        _ => valor.ToString("0.##"),
    };
}
