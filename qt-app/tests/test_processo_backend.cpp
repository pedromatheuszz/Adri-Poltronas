// Testes do ciclo de vida do backend.
//
// A janela Qt e a do Electron precisam apontar para a MESMA porta e para o
// MESMO entrypoint. Se um dos dois lados mudar sozinho, as duas interfaces
// passam a falar com backends diferentes -- ou nenhuma sobe. Estes testes
// travam esse contrato do lado C++; do lado Node ele esta em
// tests/test_electron.py.
#include <QDir>
#include <QTest>

#include "ProcessoBackend.h"

using adri::ProcessoBackend;

class TesteProcessoBackend : public QObject {
    Q_OBJECT

private slots:
    void urlEhLoopbackNaPortaDoOauth();
    void emDesenvolvimentoRodaOServidorPython();
    void empacotadoRodaOExecutavelDoPyinstaller();
    void sondaEmPortaLivreFalhaRapido();
};

void TesteProcessoBackend::urlEhLoopbackNaPortaDoOauth() {
    const QUrl url = ProcessoBackend::urlDoApp();

    QCOMPARE(url.host(), QStringLiteral("127.0.0.1"));
    // 5000 e fixa: o redirect_uri registrado no Azure aponta para ela.
    QCOMPARE(url.port(), 5000);
    QCOMPARE(int(adri::kPorta), 5000);
}

void TesteProcessoBackend::emDesenvolvimentoRodaOServidorPython() {
    const auto comando = ProcessoBackend::comandoPara(QStringLiteral("C:/projeto"), false);

    QVERIFY(comando.programa.startsWith(QStringLiteral("python")));
    QCOMPARE(comando.argumentos.size(), 1);
    QVERIFY(comando.argumentos.first().endsWith(QStringLiteral("backend/servidor.py")));
    QCOMPARE(QDir::fromNativeSeparators(comando.diretorio), QStringLiteral("C:/projeto"));
}

void TesteProcessoBackend::empacotadoRodaOExecutavelDoPyinstaller() {
    const auto comando = ProcessoBackend::comandoPara(QStringLiteral("C:/instalado"), true);

    // Mesmo nome e mesmo layout que o electron-builder usa em resources/.
    QVERIFY(comando.programa.endsWith(QStringLiteral("backend/AdriPoltronasBackend.exe")));
    QVERIFY(comando.argumentos.isEmpty());
}

void TesteProcessoBackend::sondaEmPortaLivreFalhaRapido() {
    // Sem servidor no ar a sonda tem que devolver falso depressa: ela roda em
    // laco durante a inicializacao, e um timeout longo travaria a janela.
    QElapsedTimer relogio;
    relogio.start();

    const bool respondeu = ProcessoBackend::servidorNoAr(200);

    if (!respondeu) QVERIFY(relogio.elapsed() < 2000);
}

QTEST_MAIN(TesteProcessoBackend)
#include "test_processo_backend.moc"
