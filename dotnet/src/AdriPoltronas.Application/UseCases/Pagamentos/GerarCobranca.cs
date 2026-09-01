using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Enums;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Application.UseCases.Pagamentos;

/// <summary>
/// Emite a cobranca online de um lancamento existente.
/// </summary>
/// <remarks>
/// O que o provedor devolve e gravado no proprio lancamento. Sem isso, cada
/// reabertura da tela geraria uma cobranca nova para a mesma divida e o
/// cliente receberia dois codigos Pix diferentes.
/// </remarks>
public sealed class GerarCobranca(
    IPagamentoRepository pagamentos,
    IServicoDeCobranca cobrancas,
    IUnidadeDeTrabalho unidade,
    IRelogio relogio,
    ILogger<GerarCobranca> log)
{
    public async Task<Resultado<PagamentoDto>> ExecutarAsync(
        int id, CancellationToken cancelamento = default)
    {
        if (!cobrancas.Configurado)
        {
            return Resultado<PagamentoDto>.Invalido(
                ["Cobranca online nao configurada. Informe a chave de API."]);
        }

        var pagamento = await pagamentos.ObterPorIdAsync(id, cancelamento);
        if (pagamento is null)
        {
            return Resultado<PagamentoDto>.NaoEncontrado("Cobranca nao encontrada.");
        }

        if (!pagamento.Tipo.EmitidoPeloAsaas())
        {
            return Resultado<PagamentoDto>.Invalido(
                ["Somente Pix e Boleto geram cobranca online."]);
        }

        if (pagamento.Cobranca.Emitida)
        {
            // Ja existe: devolve a que existe em vez de criar outra.
            return Resultado<PagamentoDto>.Ok(PagamentoDto.De(pagamento, relogio.Agora));
        }

        var emissao = await cobrancas.EmitirAsync(pagamento, cancelamento);
        if (!emissao.Sucesso || emissao.Valor is null)
        {
            log.LogWarning(
                "Emissao da cobranca {PagamentoId} falhou: {Motivo}", id, emissao.Mensagem);
            return Resultado<PagamentoDto>.Invalido(emissao.Erros);
        }

        pagamento.RegistrarCobrancaEmitida(emissao.Valor);
        await unidade.ConfirmarAsync(cancelamento);

        log.LogInformation("Cobranca emitida para o pagamento {PagamentoId}.", id);
        return Resultado<PagamentoDto>.Ok(PagamentoDto.De(pagamento, relogio.Agora));
    }
}
