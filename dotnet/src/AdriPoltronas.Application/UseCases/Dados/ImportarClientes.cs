using AdriPoltronas.Application.Abstractions;
using AdriPoltronas.Application.Common;
using AdriPoltronas.Application.Dtos;
using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Exceptions;
using Microsoft.Extensions.Logging;

namespace AdriPoltronas.Application.UseCases.Dados;

/// <summary>
/// Cadastra clientes vindos de arquivo.
/// </summary>
/// <remarks>
/// Uma linha invalida nao derruba a importacao inteira: as boas entram e as
/// recusadas voltam com o motivo e o numero da linha, para o operador corrigir
/// na planilha. Tudo numa transacao so, entao ou o lote inteiro entra ou nada
/// entra -- importar metade e o pior desfecho possivel aqui.
/// </remarks>
public sealed class ImportarClientes(
    IImportadorDePlanilha importador,
    IClienteRepository clientes,
    IHistoricoRepository historico,
    IUnidadeDeTrabalho unidade,
    IRelogio relogio,
    ILogger<ImportarClientes> log)
{
    public async Task<Resultado<ResultadoDaImportacao>> ExecutarAsync(
        string caminho, CancellationToken cancelamento = default)
    {
        var leitura = await importador.LerAsync(caminho, cancelamento);
        if (!leitura.Sucesso || leitura.Valor is null)
        {
            return Resultado<ResultadoDaImportacao>.Invalido(leitura.Erros);
        }

        var agora = relogio.Agora;
        var rejeitadas = new List<LinhaRejeitada>();
        var aceitos = 0;

        foreach (var linha in leitura.Valor)
        {
            try
            {
                var cliente = Cliente.Criar(
                    linha.Dados.Nome, linha.Dados.Cep, linha.Dados.Rua,
                    linha.Dados.Bairro, linha.Dados.Cidade, linha.Dados.Tipo,
                    linha.Dados.Observacoes, agora);

                clientes.Adicionar(cliente);
                historico.Adicionar(RegistroHistorico.Importacao(cliente, agora));
                aceitos++;
            }
            catch (ValidacaoException erro)
            {
                rejeitadas.Add(new LinhaRejeitada(
                    linha.Numero, linha.Dados.Nome ?? string.Empty, string.Join(" ", erro.Erros)));
            }
        }

        if (aceitos > 0)
        {
            await unidade.ConfirmarAsync(cancelamento);
        }

        log.LogInformation(
            "Importacao de {Caminho}: {Aceitos} cadastrados, {Rejeitados} recusados.",
            caminho, aceitos, rejeitadas.Count);

        return Resultado<ResultadoDaImportacao>.Ok(
            new ResultadoDaImportacao(aceitos, rejeitadas));
    }
}
