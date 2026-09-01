using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Exceptions;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Application.UseCases.Pagamentos;

/// <summary>Lanca uma cobranca ou um recebimento.</summary>
public sealed class RegistrarPagamento(
    IPagamentoRepository pagamentos,
    IClienteRepository clientes,
    IUnidadeDeTrabalho unidade,
    IRelogio relogio,
    ILogger<RegistrarPagamento> log)
{
    public async Task<Resultado<PagamentoDto>> ExecutarAsync(
        DadosDoPagamento dados, CancellationToken cancelamento = default)
    {
        // O cliente e conferido contra o banco, e nao so pelo id ser positivo:
        // o formulario antigo aceitava um id orfao e a cobranca aparecia na
        // lista sem dono, sem jeito de descobrir de quem era.
        var cliente = await clientes.ObterPorIdAsync(dados.ClienteId, cancelamento);
        if (cliente is null)
        {
            return Resultado<PagamentoDto>.NaoEncontrado("Cliente nao encontrado.");
        }

        Pagamento pagamento;
        try
        {
            pagamento = Pagamento.Criar(
                cliente.Id, cliente.Nome, dados.Valor, dados.Descricao,
                dados.DataVencimento, dados.Tipo, dados.Status,
                dados.DataPagamento, relogio.Agora);
        }
        catch (ValidacaoException erro)
        {
            return Resultado<PagamentoDto>.Invalido(erro.Erros);
        }

        pagamentos.Adicionar(pagamento);
        await unidade.ConfirmarAsync(cancelamento);

        log.LogInformation(
            "Pagamento {PagamentoId} registrado para o cliente {ClienteId}.",
            pagamento.Id, cliente.Id);
        return Resultado<PagamentoDto>.Ok(PagamentoDto.De(pagamento, relogio.Agora));
    }
}
