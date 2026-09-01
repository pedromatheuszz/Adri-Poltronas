namespace AdriPoltronas.Application.Abstractions;

/// <summary>
/// Confirma, numa unica transacao, tudo que os repositorios marcaram.
/// </summary>
/// <remarks>
/// Existe por um motivo concreto, e nao por padrao: cliente e historico
/// precisam ser gravados juntos. Com cada repositorio salvando por conta
/// propria, uma falha entre as duas gravacoes deixaria um cadastro sem a linha
/// de auditoria correspondente -- e o historico e o unico registro de quem
/// mudou o que.
///
/// E uma interface de um metodo so. Nao ha <c>Commit</c>/<c>Rollback</c>
/// expostos: quem nao chama <see cref="ConfirmarAsync"/> simplesmente nao
/// grava.
/// </remarks>
public interface IUnidadeDeTrabalho
{
    Task<int> ConfirmarAsync(CancellationToken cancelamento = default);
}
