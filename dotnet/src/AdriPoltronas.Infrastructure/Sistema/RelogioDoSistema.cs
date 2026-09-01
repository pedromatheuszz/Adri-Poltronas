using AdriPoltronas.Application.Abstractions;

namespace AdriPoltronas.Infrastructure.Sistema;

/// <inheritdoc cref="IRelogio"/>
/// <remarks>
/// Hora local, e nao UTC: as colunas de data do banco foram gravadas com
/// <c>datetime('now','localtime')</c> desde o inicio. Passar a gravar UTC
/// misturaria dois fusos na mesma coluna e deslocaria em tres horas os
/// cadastros contados no painel.
/// </remarks>
public sealed class RelogioDoSistema : IRelogio
{
    public DateTime Agora => DateTime.Now;
}
