using AdriPoltronas.Domain.Entities;
using AdriPoltronas.Domain.Enums;

namespace AdriPoltronas.Application.Dtos;

/// <summary>
/// Cliente como a interface o consome: plano, so leitura, sem comportamento.
/// </summary>
/// <remarks>
/// A View nao recebe a entidade. Se recebesse, um binding de duas vias do
/// XAML escreveria direto nas propriedades do dominio, contornando a validacao
/// de <see cref="Cliente.Atualizar"/> -- que e justamente o que garante que
/// nao existe cliente sem nome no banco.
/// </remarks>
public sealed record ClienteDto(
    int Id,
    string Nome,
    string Cep,
    string Rua,
    string Bairro,
    string Cidade,
    string Tipo,
    string Observacoes,
    DateTime CriadoEm,
    DateTime AtualizadoEm)
{
    public static ClienteDto De(Cliente cliente) => new(
        cliente.Id,
        cliente.Nome,
        cliente.Endereco.Cep.Valor,
        cliente.Endereco.Rua,
        cliente.Endereco.Bairro,
        cliente.Endereco.Cidade,
        cliente.Tipo.ParaTexto(),
        cliente.Observacoes,
        cliente.CriadoEm,
        cliente.AtualizadoEm);
}
