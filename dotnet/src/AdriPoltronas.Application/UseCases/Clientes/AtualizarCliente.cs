using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Exceptions;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Application.UseCases.Clientes;

/// <summary>Altera um cliente existente e descreve a mudanca no historico.</summary>
public sealed class AtualizarCliente(
    IClienteRepository clientes,
    IHistoricoRepository historico,
    IUnidadeDeTrabalho unidade,
    IRelogio relogio,
    ILogger<AtualizarCliente> log)
{
    public async Task<Resultado<ClienteDto>> ExecutarAsync(
        int id, DadosDoCliente dados, CancellationToken cancelamento = default)
    {
        var cliente = await clientes.ObterPorIdAsync(id, cancelamento);
        if (cliente is null)
        {
            // Distinguir "nao existe" de "dado invalido" importa: o primeiro
            // significa que a lista da tela esta velha e precisa recarregar.
            return Resultado<ClienteDto>.NaoEncontrado($"Cliente {id} nao encontrado.");
        }

        IReadOnlyList<string> mudancas;
        try
        {
            mudancas = cliente.Atualizar(
                dados.Nome, dados.Cep, dados.Rua, dados.Bairro,
                dados.Cidade, dados.Tipo, dados.Observacoes, relogio.Agora);
        }
        catch (ValidacaoException erro)
        {
            return Resultado<ClienteDto>.Invalido(erro.Erros);
        }

        historico.Adicionar(RegistroHistorico.Atualizacao(cliente, mudancas, relogio.Agora));
        await unidade.ConfirmarAsync(cancelamento);

        log.LogInformation(
            "Cliente {ClienteId} atualizado ({Quantidade} campo(s)).", cliente.Id, mudancas.Count);
        return Resultado<ClienteDto>.Ok(ClienteDto.De(cliente));
    }
}
