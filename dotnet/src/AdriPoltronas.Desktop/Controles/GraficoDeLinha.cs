using Avalonia;
using Avalonia.Media;

namespace AdriPoltronas.Desktop.Controles;

/// <summary>Serie temporal com area preenchida sob a linha.</summary>
public sealed class GraficoDeLinha : GraficoBase
{
    private const double AlturaDoRotulo = 20;
    private const double MargemSuperior = 12;

    public override void Render(DrawingContext contexto)
    {
        var dados = Dados;
        if (dados.Count < 2)
        {
            DesenharAviso(contexto, "Sem historico suficiente.");
            return;
        }

        var destaque = Pincel("Destaque", "#3B82F6");
        var fraco = Pincel("TextoFraco", "#94A3B8");
        var grade = Pincel("Grade", "#243349");

        var alturaUtil = Bounds.Height - AlturaDoRotulo - MargemSuperior;
        if (alturaUtil <= 0)
        {
            return;
        }

        var maior = dados.Max(p => p.Valor);
        var passo = Bounds.Width / (dados.Count - 1);

        // Tres linhas de referencia: sem elas a curva nao diz magnitude.
        for (var fracao = 0; fracao <= 2; fracao++)
        {
            var altura = MargemSuperior + (alturaUtil * fracao / 2);
            contexto.DrawLine(
                new Pen(grade, 1, new DashStyle([2, 4], 0)),
                new Point(0, altura), new Point(Bounds.Width, altura));
        }

        var pontos = dados
            .Select((ponto, indice) => new Point(
                indice * passo,
                MargemSuperior + alturaUtil -
                    (maior <= 0 ? 0 : ponto.Valor / maior * alturaUtil)))
            .ToList();

        var area = new StreamGeometry();
        using (var traco = area.Open())
        {
            traco.BeginFigure(new Point(pontos[0].X, MargemSuperior + alturaUtil), true);
            foreach (var ponto in pontos)
            {
                traco.LineTo(ponto);
            }

            traco.LineTo(new Point(pontos[^1].X, MargemSuperior + alturaUtil));
            traco.EndFigure(true);
        }

        contexto.DrawGeometry(
            new SolidColorBrush(Color.Parse("#3B82F6"), 0.16), null, area);

        var caneta = new Pen(destaque, 2);
        for (var indice = 1; indice < pontos.Count; indice++)
        {
            contexto.DrawLine(caneta, pontos[indice - 1], pontos[indice]);
        }

        for (var indice = 0; indice < pontos.Count; indice++)
        {
            contexto.DrawEllipse(destaque, null, pontos[indice], 3, 3);

            var rotulo = Texto(dados[indice].Rotulo, 10, fraco);
            contexto.DrawText(rotulo, new Point(
                Math.Clamp(pontos[indice].X - (rotulo.Width / 2), 0,
                    Math.Max(Bounds.Width - rotulo.Width, 0)),
                MargemSuperior + alturaUtil + 4));
        }
    }
}
