namespace AdriPoltronas.Application.Abstractions;

/// <summary>
/// Hora atual, injetavel.
/// </summary>
/// <remarks>
/// Sem isso, testar "cadastros dos ultimos 30 dias" exigiria mexer no relogio
/// da maquina ou aceitar um teste que muda de resultado conforme o dia.
/// </remarks>
public interface IRelogio
{
    DateTime Agora { get; }
}
