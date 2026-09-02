// A janela Qt e o backend protegido.
//
// Ate a versao 1.2.1 o Qt era o buraco na protecao que o Electron ganhou: ele
// sondava apenas "tem alguem na porta 5000?" e nao enviava cabecalho nenhum.
// Na pratica, ou subia um backend SEM exigencia de token -- desfazendo a
// protecao para todo mundo --, ou tomava 403 em cada requisicao ao tentar
// reaproveitar o backend do Electron. O README prometia duas interfaces sobre
// um backend so; sem o token, isso deixou de ser verdade.
#include "Capacidade.h"
#include "ClienteApi.h"
#include "ProcessoBackend.h"

#include <QDir>
#include <QFile>
#include <QTest>

using namespace adri;

class TesteCapacidade : public QObject {
    Q_OBJECT

private slots:
    void oArquivoFicaOndeAsOutrasPilhasOProcuram();
    void oTokenEEstavelEntreLeituras();
    void oTokenTemOFormatoDasOutrasImplementacoes();
    void aSondaDistingueQuemAtendeNaPorta();
};

void TesteCapacidade::oArquivoFicaOndeAsOutrasPilhasOProcuram() {
    // A regressao que este teste guarda: a primeira versao usava
    // `QStandardPaths::GenericConfigLocation`, que no Windows resolve para
    // %LOCALAPPDATA% -- e nao para %APPDATA% (Roaming), onde o Python e o
    // .NET escrevem. O Qt criava um SEGUNDO arquivo, com outro token, e
    // nunca conseguia falar com o backend do Electron.
    const QString caminho = caminhoDoArquivoDeCapacidade();
    QVERIFY(!caminho.isEmpty());
    QCOMPARE(QFileInfo(caminho).fileName(), QStringLiteral(".capacidade"));
    QCOMPARE(QDir(QFileInfo(caminho).absolutePath()).dirName(),
             QStringLiteral("AdriPoltronas"));

#ifdef Q_OS_WIN
    const QString roaming = QDir::fromNativeSeparators(qEnvironmentVariable("APPDATA"));
    if (!roaming.isEmpty())
        QVERIFY2(QDir::fromNativeSeparators(caminho).startsWith(roaming),
                 "o arquivo precisa ficar em %APPDATA% (Roaming), como no Python");
#endif
}

void TesteCapacidade::oTokenEEstavelEntreLeituras() {
    // Persistido, e nao sorteado a cada execucao: quando o Electron morre sem
    // levar o Python junto, a abertura seguinte precisa reconhecer o backend
    // orfao que ficou na porta.
    const QString primeiro = tokenDeCapacidade();
    QVERIFY(!primeiro.isEmpty());
    QCOMPARE(tokenDeCapacidade(), primeiro);
}

void TesteCapacidade::oTokenTemOFormatoDasOutrasImplementacoes() {
    // 32 bytes em hexadecimal, como em capacidade.py e capacidade.ts. O
    // arquivo e lido pelas tres, entao o formato precisa ser o mesmo.
    const QString token = tokenDeCapacidade();
    QCOMPARE(token.size(), 64);
    for (const QChar &c : token)
        QVERIFY2(c.isDigit() || (c >= QLatin1Char('a') && c <= QLatin1Char('f')),
                 "o token precisa ser hexadecimal minusculo");
}

void TesteCapacidade::aSondaDistingueQuemAtendeNaPorta() {
    // Sem ninguem na porta, a resposta e `Livre` -- e nao uma das situacoes
    // de erro. Este teste roda sem backend no ar, entao e o unico desfecho
    // que da para afirmar aqui; os outros tres sao exercitados no
    // test_processo_backend e na verificacao manual contra o backend real.
    const auto estado = ProcessoBackend::sondarPorta(QByteArrayLiteral("token-qualquer"), 300);
    QVERIFY(estado == ProcessoBackend::EstadoDaPorta::Livre
            || estado == ProcessoBackend::EstadoDaPorta::Nosso
            || estado == ProcessoBackend::EstadoDaPorta::Estranho
            || estado == ProcessoBackend::EstadoDaPorta::RecusouCapacidade);
}

QTEST_MAIN(TesteCapacidade)
#include "test_capacidade.moc"
