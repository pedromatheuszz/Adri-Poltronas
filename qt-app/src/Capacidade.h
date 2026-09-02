// Segredo que separa o aplicativo de qualquer outro cliente da porta 5000.
//
// E o equivalente em C++ de backend/capacidade.py e electron/capacidade.ts. As
// tres implementacoes leem O MESMO arquivo, em %APPDATA%\AdriPoltronas, e por
// isso a janela Qt consegue tanto subir o proprio backend quanto conversar com
// um backend que o Electron ja deixou no ar.
//
// Sem isto, o Qt era o buraco na protecao: ele sondava apenas "tem alguem na
// porta?" e nao mandava cabecalho nenhum. Na pratica, ou subia um backend sem
// exigencia de token -- desfazendo a protecao para todo mundo --, ou tomava
// 403 em cada requisicao ao tentar reaproveitar o backend do Electron. O
// README do Qt prometia duas interfaces sobre o mesmo backend; sem o token,
// isso deixou de ser verdade na versao 1.2.
#pragma once

#include <QByteArray>
#include <QString>

namespace adri {

/// Cabecalho em que o token viaja. Precisa casar com `capacidade.py`.
inline constexpr char kHeaderDaCapacidade[] = "X-Adri-Capacidade";

/// Variavel de ambiente pela qual o backend filho recebe o token.
inline constexpr char kVariavelDaCapacidade[] = "ADRI_API_TOKEN";

/// Le o token do perfil do usuario, criando-o na primeira execucao.
///
/// Devolve string vazia quando nao consegue ler nem criar -- perfil somente
/// leitura, por exemplo. Nesse caso a janela ainda abre: quem decide o que
/// fazer com a ausencia e quem chama.
QString tokenDeCapacidade();

/// Caminho do arquivo, exposto para teste.
QString caminhoDoArquivoDeCapacidade();

}  // namespace adri
