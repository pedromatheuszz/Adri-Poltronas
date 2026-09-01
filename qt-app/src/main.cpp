// Ponto de entrada da janela Qt.
//
// E uma interface *alternativa* a do Electron, nao um substituto: as duas
// falam com o mesmo backend Flask e podem inclusive rodar ao mesmo tempo --
// quem subir primeiro liga o Python, a segunda reaproveita a porta.
#include <QApplication>
#include <QDebug>
#include <QDir>
#include <QFile>
#include <QIcon>
#include <QMessageBox>
#include <QTextStream>
#include <QtGlobal>

#include "ClienteApi.h"
#include "JanelaPrincipal.h"
#include "ProcessoBackend.h"

namespace {

/// Raiz do projeto a partir do executavel.
///
/// Em desenvolvimento o binario fica em qt-app/build/, dois niveis abaixo da
/// raiz. Empacotado, o backend vem ao lado do executavel (mesmo layout que o
/// electron-builder produz em resources/).
QString raizDoProjeto(bool empacotado) {
    QDir pasta(QCoreApplication::applicationDirPath());
    if (empacotado) return pasta.absolutePath();
    pasta.cdUp();
    pasta.cdUp();
    return pasta.absolutePath();
}

QString folhaDeEstilo() {
    QFile arquivo(QStringLiteral(":/tema.qss"));
    if (!arquivo.open(QIODevice::ReadOnly | QIODevice::Text)) return {};
    return QTextStream(&arquivo).readAll();
}

}  // namespace

int main(int argc, char *argv[]) {
    QApplication aplicacao(argc, argv);
    aplicacao.setApplicationName(QStringLiteral("Adri Poltronas"));
    aplicacao.setOrganizationName(QStringLiteral("Adri Poltronas"));
    aplicacao.setStyleSheet(folhaDeEstilo());

    // `--empacotado` troca o modo de localizar o backend. Fora isso os dois
    // modos sao identicos, o que mantem o caminho de producao exercitado em
    // desenvolvimento.
    const bool empacotado = aplicacao.arguments().contains(QStringLiteral("--empacotado"));
    const QString raiz = raizDoProjeto(empacotado);

    adri::ProcessoBackend backend;
    QObject::connect(&backend, &adri::ProcessoBackend::saidaDoBackend,
                     [](const QString &linha) { qInfo().noquote() << linha; });

    QString erro;
    if (!backend.iniciar(raiz, empacotado, &erro)) {
        QMessageBox::critical(nullptr, QStringLiteral("Adri Poltronas"), erro);
        return 1;
    }

    adri::ClienteApi api(adri::ProcessoBackend::urlDoApp());
    adri::JanelaPrincipal janela(&api);
    janela.show();

    const int codigo = aplicacao.exec();
    // Explicito, e nao so pelo destrutor: o backend precisa morrer antes de
    // devolvermos o controle, senao a porta continua ocupada para a proxima
    // abertura (da janela Qt ou da do Electron).
    backend.encerrar();
    return codigo;
}
