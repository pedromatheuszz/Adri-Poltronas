using AdriPoltronas.Domain.Entities;

namespace AdriPoltronas.Application.Abstractions;

/// <summary>Registro de auditoria das alteracoes de cadastro.</summary>
public interface IHistoricoRepository
{
    /// <summary>Marca o registro para inclusao; grava no <see cref="IUnidadeDeTrabalho"/>.</summary>
    void Adicionar(RegistroHistorico registro);

    Task<IReadOnlyList<RegistroHistorico>> UltimosAsync(
        int quantidade, CancellationToken cancelamento = default);
}
