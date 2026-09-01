using Avalonia;
using Avalonia.Media;

namespace AdriPoltronas.Desktop.Controles;

/// <summary>
/// Rosca com legenda ao lado.
/// </summary>
/// <remarks>
/// Usada para entrega contra retirada, que e comparacao de duas partes de um
/// todo -- o unico caso em que a forma circular diz mais que uma barra.
/// </remarks>
public sealed class GraficoDeRosca : GraficoBase
{
    private const double EspessuraDoAnel = 22;
    private const double LarguraDaLegenda = 130;

    private static readonly string[] Paleta =
        ["#10B981", "#F59E0B", "#3B82F6", "#A855F7", "#EF4444", "#14B8A6"];

    public override void Render(DrawingContext contexto)
    {
        var dados = Dados.Where(p => p.Valor > 0).ToList();
        if (dados.Count == 0)
        {
            DesenharAviso(contexto, "Sem dados no periodo.");
            return;
        }

        var texto = Pincel("Texto", "#E2E8F0");
        var fraco = Pincel("TextoFraco", "#94A3B8");

        var total = dados.Sum(p => p.Valor);
        var lado = Math.Min(Bounds.Height, Math.Max(Bounds.Width - LarguraDaLegenda, 0));
        if (lado <= EspessuraDoAnel * 2)
        {
            return;
        }

        var centro = new Point(lado / 2, Bounds.Height / 2);
        var raio = (lado / 2) - 4;
        var anguloInicial = -Math.PI / 2;

        for (var indice = 0; indice < dados.Count; indice++)
        {
            var fatia = dados[indice].Valor / total * Math.PI * 2;
            var cor = new SolidColorBrush(Color.Parse(Paleta[indice % Paleta.Length]));

            contexto.DrawGeometry(null, new Pen(cor, EspessuraDoAnel),
                Arco(centro, raio - (EspessuraDoAnel / 2), anguloInicial, anguloInicial + fatia));

            anguloInicial += fatia;
        }

        var totalFormatado = Texto(total.ToString("0.##"), 18, texto);
        contexto.DrawText(totalFormatado, new Point(
            centro.X - (totalFormatado.Width / 2), centro.Y - (totalFormatado.Height / 2)));

        var alturaDaLegenda = dados.Count * 20;
        var topo = (Bounds.Height - alturaDaLegenda) / 2;

        for (var indice = 0; indice < dados.Count; indice++)
        {
            var cor = new SolidColorBrush(Color.Parse(Paleta[indice % Paleta.Length]));
            var linha = topo + (indice * 20);

            contexto.DrawRectangle(cor, null,
                new RoundedRect(new Rect(lado + 12, linha + 4, 10, 10), 3));

            var percentual = dados[indice].Valor / total * 100;
            var rotulo = Texto(
                $"{dados[indice].Rotulo}  {percentual:0}%", 11, fraco);
            contexto.DrawText(rotulo, new Point(lado + 28, linha + 1));
        }
    }

    /// <summary>Arco como geometria: o DrawingContext nao tem primitiva para isso.</summary>
    private static StreamGeometry Arco(Point centro, double raio, double inicio, double fim)
    {
        var geometria = new StreamGeometry();
        using var traco = geometria.Open();

        traco.BeginFigure(EmVolta(centro, raio, inicio), false);
        traco.ArcTo(
            EmVolta(centro, raio, fim),
            new Size(raio, raio),
            0,
            fim - inicio > Math.PI,
            SweepDirection.Clockwise);
        traco.EndFigure(false);

        return geometria;
    }

    private static Point EmVolta(Point centro, double raio, double angulo) =>
        new(centro.X + (raio * Math.Cos(angulo)), centro.Y + (raio * Math.Sin(angulo)));
}
