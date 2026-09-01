namespace AdriPoltronas.Domain.Enums;

/// <summary>Categorias de alerta exibidas no sino.</summary>
public enum TipoNotificacao
{
    EntregaHoje = 0,
    EntregaProxima = 1,
    EntregaAtrasada = 2,
    ClienteInativo = 3,
    PagamentoAtrasado = 4,
    PagamentoHoje = 5,
}

/// <summary>
/// Urgencia do alerta.
/// </summary>
/// <remarks>
/// Define a ordem da lista e a cor da borda. Uma entrega atrasada precisa
/// aparecer antes de um cliente sem atualizacao ha tres meses.
/// </remarks>
public enum PrioridadeNotificacao
{
    Baixa = 0,
    Media = 1,
    Alta = 2,
    Critica = 3,
}
