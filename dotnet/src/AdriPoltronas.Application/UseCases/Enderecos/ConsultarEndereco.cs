using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.ValueObjects;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Application.UseCases.Enderecos;

/// <summary>
/// Preenche o endereco a partir do CEP.
/// </summary>
/// <remarks>
/// Quando o CEP e valido mas o servico nao devolve bairro, tenta o palpite.
/// Isso e comum em cidade pequena, e era exatamente o caso em que o operador
/// precisava digitar tudo a mao.
/// </remarks>
public sealed class ConsultarEndereco(
    IConsultaDeCep consulta,
    ISugestaoDeBairro sugestao,
    ILogger<ConsultarEndereco> log)
{
    public async Task<EnderecoConsultado?> ExecutarAsync(
        string? cep, CancellationToken cancelamento = default)
    {
        if (!Cep.TentarCriar(cep, out var validado))
        {
            return null;
        }

        var encontrado = await consulta.ConsultarAsync(validado.Valor, cancelamento);
        if (encontrado is null)
        {
            log.LogInformation("CEP {Cep} nao encontrado.", validado.Valor);
            return null;
        }

        if (encontrado.TemBairro || !sugestao.Configurado)
        {
            return encontrado;
        }

        var palpite = await sugestao.SugerirAsync(
            encontrado.Cep, encontrado.Rua, encontrado.Cidade, cancelamento);

        return string.IsNullOrWhiteSpace(palpite)
            ? encontrado
            : encontrado with { Bairro = palpite.Trim() };
    }
}
