using System.Collections.Concurrent;
using System.Collections.Specialized;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Desktop.Servicos;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using Avalonia.Threading;

namespace AdriPoltronas.Desktop.Controles;

/// <summary>
/// Mapa com ladrilhos do OpenStreetMap e um marcador por cliente.
/// </summary>
/// <remarks>
/// Escrito a mao em vez de embutir um navegador. A versao web usava Leaflet
/// dentro da pagina; aqui isso exigiria um WebView so para desenhar quadrados
/// e circulos -- uma dependencia grande, com processo proprio, para um recurso
/// que cabe em projecao de Mercator e composicao de imagens.
///
/// A projecao e a padrao dos ladrilhos (Web Mercator), a mesma do Leaflet, e
/// por isso os marcadores caem exatamente onde caiam antes.
/// </remarks>
public sealed class ControleDeMapa : Control
{
    private const int LadoDoLadrilho = 256;
    private const int ZoomMinimo = 3;
    private const int ZoomMaximo = 17;

    public static readonly StyledProperty<IReadOnlyList<PontoNoMapa>?> PontosProperty =
        AvaloniaProperty.Register<ControleDeMapa, IReadOnlyList<PontoNoMapa>?>(nameof(Pontos));

    public static readonly StyledProperty<IFonteDeLadrilhos?> FonteProperty =
        AvaloniaProperty.Register<ControleDeMapa, IFonteDeLadrilhos?>(nameof(Fonte));

    private readonly ConcurrentDictionary<string, Bitmap?> _ladrilhos = new();
    private readonly HashSet<string> _pedidos = [];

    // Centro do Brasil: e o enquadramento inicial ate os pontos chegarem.
    private double _centroLatitude = -15.79;
    private double _centroLongitude = -47.88;
    private int _zoom = 4;
    private Point? _arrasteAnterior;

    public ControleDeMapa()
    {
        ClipToBounds = true;
        Focusable = true;

        PontosProperty.Changed.AddClassHandler<ControleDeMapa>((mapa, evento) =>
            mapa.TrocarColecao(
                evento.OldValue as IReadOnlyList<PontoNoMapa>,
                evento.NewValue as IReadOnlyList<PontoNoMapa>));
    }

    public IReadOnlyList<PontoNoMapa>? Pontos
    {
        get => GetValue(PontosProperty);
        set => SetValue(PontosProperty, value);
    }

    /// <summary>De onde vem as imagens. Sem ela o mapa desenha so os marcadores.</summary>
    public IFonteDeLadrilhos? Fonte
    {
        get => GetValue(FonteProperty);
        set => SetValue(FonteProperty, value);
    }

    public override void Render(DrawingContext contexto)
    {
        var fundo = new SolidColorBrush(Color.Parse("#0B1220"));
        contexto.FillRectangle(fundo, new Rect(Bounds.Size));

        DesenharLadrilhos(contexto);
        DesenharMarcadores(contexto);
        DesenharCredito(contexto);
    }

    protected override void OnPointerPressed(PointerPressedEventArgs evento)
    {
        _arrasteAnterior = evento.GetPosition(this);
        evento.Pointer.Capture(this);
    }

    protected override void OnPointerMoved(PointerEventArgs evento)
    {
        if (_arrasteAnterior is not { } anterior)
        {
            return;
        }

        var atual = evento.GetPosition(this);
        var pixelsPorVolta = LadoDoLadrilho * Math.Pow(2, _zoom);

        // Arrastar move o centro no sentido contrario ao do ponteiro: o mapa
        // acompanha o dedo, e nao foge dele.
        _centroLongitude -= (atual.X - anterior.X) * 360 / pixelsPorVolta;
        _centroLatitude = LatitudeDeY(YDeLatitude(_centroLatitude) - (atual.Y - anterior.Y));

        _centroLatitude = Math.Clamp(_centroLatitude, -85, 85);
        _centroLongitude = Math.Clamp(_centroLongitude, -180, 180);

        _arrasteAnterior = atual;
        InvalidateVisual();
    }

    protected override void OnPointerReleased(PointerReleasedEventArgs evento)
    {
        _arrasteAnterior = null;
        evento.Pointer.Capture(null);
    }

    protected override void OnPointerWheelChanged(PointerWheelEventArgs evento)
    {
        var novo = Math.Clamp(_zoom + (evento.Delta.Y > 0 ? 1 : -1), ZoomMinimo, ZoomMaximo);
        if (novo == _zoom)
        {
            return;
        }

        _zoom = novo;
        InvalidateVisual();
    }

    /// <summary>
    /// Assina a colecao nova e larga a anterior.
    /// </summary>
    /// <remarks>
    /// A tela nao troca a colecao: ela limpa e repovoa a mesma
    /// <c>ObservableCollection</c>. Reagir so a mudanca da propriedade deixava
    /// o mapa parado no enquadramento do Brasil inteiro, sem marcador nenhum,
    /// mesmo com a barra de status ja dizendo quantos clientes foram
    /// localizados.
    /// </remarks>
    private void TrocarColecao(
        IReadOnlyList<PontoNoMapa>? anterior, IReadOnlyList<PontoNoMapa>? nova)
    {
        if (anterior is INotifyCollectionChanged velha)
        {
            velha.CollectionChanged -= AoMudarAColecao;
        }

        if (nova is INotifyCollectionChanged atual)
        {
            atual.CollectionChanged += AoMudarAColecao;
        }

        Enquadrar();
        InvalidateVisual();
    }

    private void AoMudarAColecao(object? remetente, NotifyCollectionChangedEventArgs evento)
    {
        Enquadrar();
        InvalidateVisual();
    }

    /// <summary>Ajusta centro e zoom para caber todos os pontos.</summary>
    private void Enquadrar()
    {
        var pontos = Pontos;
        if (pontos is null || pontos.Count == 0)
        {
            return;
        }

        var menorLat = pontos.Min(p => p.Latitude);
        var maiorLat = pontos.Max(p => p.Latitude);
        var menorLon = pontos.Min(p => p.Longitude);
        var maiorLon = pontos.Max(p => p.Longitude);

        _centroLatitude = (menorLat + maiorLat) / 2;
        _centroLongitude = (menorLon + maiorLon) / 2;

        // Um unico cliente nao define extensao; o zoom de bairro e o util.
        var extensao = Math.Max(maiorLat - menorLat, maiorLon - menorLon);
        _zoom = extensao switch
        {
            <= 0.001 => 14,
            < 0.05 => 12,
            < 0.3 => 10,
            < 1.5 => 8,
            < 6 => 6,
            _ => 4,
        };
    }

    private void DesenharLadrilhos(DrawingContext contexto)
    {
        var fonte = Fonte;
        if (fonte is null)
        {
            return;
        }

        var total = 1 << _zoom;
        var centroX = (_centroLongitude + 180) / 360 * total;
        var centroY = YDeLatitude(_centroLatitude) / LadoDoLadrilho;

        var primeiroX = (int)Math.Floor(centroX - (Bounds.Width / 2 / LadoDoLadrilho));
        var ultimoX = (int)Math.Floor(centroX + (Bounds.Width / 2 / LadoDoLadrilho));
        var primeiroY = (int)Math.Floor(centroY - (Bounds.Height / 2 / LadoDoLadrilho));
        var ultimoY = (int)Math.Floor(centroY + (Bounds.Height / 2 / LadoDoLadrilho));

        for (var x = primeiroX; x <= ultimoX; x++)
        {
            for (var y = primeiroY; y <= ultimoY; y++)
            {
                if (y < 0 || y >= total)
                {
                    continue;
                }

                // O eixo horizontal do mundo e circular: arrastar para o lado
                // continua mostrando mapa em vez de faixa vazia.
                var xNoMundo = ((x % total) + total) % total;
                var imagem = Ladrilho(fonte, _zoom, xNoMundo, y);
                if (imagem is null)
                {
                    continue;
                }

                var destino = new Rect(
                    (x - centroX) * LadoDoLadrilho + (Bounds.Width / 2),
                    (y - centroY) * LadoDoLadrilho + (Bounds.Height / 2),
                    LadoDoLadrilho,
                    LadoDoLadrilho);

                contexto.DrawImage(imagem, destino);
            }
        }
    }

    private void DesenharMarcadores(DrawingContext contexto)
    {
        var pontos = Pontos;
        if (pontos is null || pontos.Count == 0)
        {
            return;
        }

        var total = 1 << _zoom;
        var centroX = (_centroLongitude + 180) / 360 * total * LadoDoLadrilho;
        var centroY = YDeLatitude(_centroLatitude);

        var entrega = new SolidColorBrush(Color.Parse("#10B981"));
        var retirada = new SolidColorBrush(Color.Parse("#F59E0B"));
        var contorno = new Pen(new SolidColorBrush(Colors.White), 1.5);

        foreach (var ponto in pontos)
        {
            var x = (ponto.Longitude + 180) / 360 * total * LadoDoLadrilho;
            var y = YDeLatitudeNoZoom(ponto.Latitude, _zoom);

            var tela = new Point(
                x - centroX + (Bounds.Width / 2),
                y - centroY + (Bounds.Height / 2));

            if (tela.X < -20 || tela.Y < -20 ||
                tela.X > Bounds.Width + 20 || tela.Y > Bounds.Height + 20)
            {
                continue;
            }

            contexto.DrawEllipse(
                ponto.Tipo == "Entrega" ? entrega : retirada, contorno, tela, 6, 6);
        }
    }

    /// <summary>Credito obrigatorio pela licenca dos dados do OpenStreetMap.</summary>
    private void DesenharCredito(DrawingContext contexto)
    {
        var texto = new FormattedText(
            "(c) OpenStreetMap",
            System.Globalization.CultureInfo.CurrentCulture,
            FlowDirection.LeftToRight,
            new Typeface(FontFamily.Default),
            10,
            new SolidColorBrush(Color.Parse("#94A3B8")));

        contexto.FillRectangle(
            new SolidColorBrush(Colors.Black, 0.45),
            new Rect(
                Bounds.Width - texto.Width - 12, Bounds.Height - texto.Height - 6,
                texto.Width + 8, texto.Height + 2));

        contexto.DrawText(texto, new Point(
            Bounds.Width - texto.Width - 8, Bounds.Height - texto.Height - 5));
    }

    /// <summary>
    /// Ladrilho ja carregado, ou nulo enquanto ele nao chega.
    /// </summary>
    /// <remarks>
    /// A busca e disparada uma vez por coordenada e redesenha quando termina.
    /// Sem o registro de pedidos, cada quadro do arraste dispararia a mesma
    /// requisicao de novo.
    /// </remarks>
    private Bitmap? Ladrilho(IFonteDeLadrilhos fonte, int zoom, int x, int y)
    {
        var chave = $"{zoom}/{x}/{y}";
        if (_ladrilhos.TryGetValue(chave, out var pronto))
        {
            return pronto;
        }

        if (!_pedidos.Add(chave))
        {
            return null;
        }

        _ = Task.Run(async () =>
        {
            var bytes = await fonte.ObterAsync(zoom, x, y);
            Bitmap? imagem = null;

            if (bytes is not null)
            {
                try
                {
                    using var fluxo = new MemoryStream(bytes);
                    imagem = new Bitmap(fluxo);
                }
                catch (Exception erro) when (erro is ArgumentException or NotSupportedException)
                {
                    // Resposta que nao e imagem (pagina de erro do servico):
                    // guarda nulo para nao insistir.
                }
            }

            _ladrilhos[chave] = imagem;
            await Dispatcher.UIThread.InvokeAsync(InvalidateVisual);
        });

        return null;
    }

    /// <summary>Latitude para pixel vertical, projecao de Mercator.</summary>
    private double YDeLatitude(double latitude) => YDeLatitudeNoZoom(latitude, _zoom);

    private static double YDeLatitudeNoZoom(double latitude, int zoom)
    {
        var radianos = latitude * Math.PI / 180;
        var normalizado = (1 - (Math.Log(Math.Tan(radianos) + (1 / Math.Cos(radianos)))
            / Math.PI)) / 2;
        return normalizado * (1 << zoom) * LadoDoLadrilho;
    }

    private double LatitudeDeY(double y)
    {
        var normalizado = y / ((1 << _zoom) * LadoDoLadrilho);
        var radianos = Math.Atan(Math.Sinh(Math.PI * (1 - (2 * normalizado))));
        return radianos * 180 / Math.PI;
    }
}
