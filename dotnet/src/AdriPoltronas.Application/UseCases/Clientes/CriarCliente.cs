using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Exceptions;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Application.UseCases.Clientes;

/// <summary>Cadastra um cliente e registra a criacao no historico.</summary>
public sealed class CriarCliente(
    IClienteRepository clientes,
    IHistoricoRepository historico,
    IUnidadeDeTrabalho unidade,
    IRelogio relogio,
    ILogger<CriarCliente> log)
{
    public async Task<Resultado<ClienteDto>> ExecutarAsync(
        DadosDoCliente dados, CancellationToken cancelamento = default)
    {
        Cliente cliente;
        try
        {
            cliente = Cliente.Criar(
                dados.Nome, dados.Cep, dados.Rua, dados.Bairro,
                dados.Cidade, dados.Tipo, dados.Observacoes, relogio.Agora);
        }
        catch (ValidacaoException erro)
        {
            // Dado invalido e resposta esperada de um formulario: vira
            // Resultado, nao excecao propagada ate a UI.
            return Resultado<ClienteDto>.Invalido(erro.Erros);
        }

        clientes.Adicionar(cliente);
        // O historico entra na MESMA transacao. Como aponta para a entidade, e
        // nao para um id, o EF resolve a chave estrangeira depois do insert.
        historico.Adicionar(RegistroHistorico.Criacao(cliente, relogio.Agora));
        await unidade.ConfirmarAsync(cancelamento);

        log.LogInformation("Cliente {ClienteId} cadastrado.", cliente.Id);
        return Resultado<ClienteDto>.Ok(ClienteDto.De(cliente));
    }
}
