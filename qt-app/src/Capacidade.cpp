#include "Capacidade.h"

#include <QDir>
#include <QFile>
#include <QRandomGenerator>
#include <QStandardPaths>
#include <QTextStream>

namespace adri {
namespace {

constexpr int kBytesDoToken = 32;
constexpr char kNomeDaPasta[] = "AdriPoltronas";
constexpr char kNomeDoArquivo[] = ".capacidade";

/// Pasta de dados do usuario, EXATAMENTE onde as outras duas pilhas a
/// procuram.
///
/// Nenhum `QStandardPaths` serve aqui, e a primeira tentativa provou isso na
/// pratica: `GenericConfigLocation` no Windows resolve para
/// `%LOCALAPPDATA%`, e nao para `%APPDATA%` (Roaming). O Qt criou um segundo
/// arquivo de capacidade, com outro token, e a sonda respondeu
/// "RecusouCapacidade" contra o backend do Electron -- que e justamente o
/// defeito que este modulo veio corrigir.
///
/// O Python usa `os.environ["APPDATA"]` e o .NET usa
/// `SpecialFolder.ApplicationData`; os dois chegam ao Roaming. Aqui vale a
/// mesma regra, pela variavel de ambiente, com `~/.config` fora do Windows.
QString pastaDeDados() {
#ifdef Q_OS_WIN
    const QString raiz = qEnvironmentVariable("APPDATA");
#else
    QString raiz = qEnvironmentVariable("XDG_CONFIG_HOME");
    if (raiz.isEmpty())
        raiz = QDir(QStandardPaths::writableLocation(QStandardPaths::HomeLocation))
                   .filePath(QStringLiteral(".config"));
#endif
    if (raiz.isEmpty()) return QString();
    return QDir(raiz).filePath(QString::fromLatin1(kNomeDaPasta));
}

QString sortearToken() {
    // Hexadecimal, como nas outras duas implementacoes: o arquivo e lido por
    // todas elas e o formato precisa ser o mesmo.
    QString token;
    token.reserve(kBytesDoToken * 2);
    for (int i = 0; i < kBytesDoToken; ++i) {
        const quint32 byte = QRandomGenerator::system()->bounded(256);
        token += QString::number(byte, 16).rightJustified(2, QLatin1Char('0'));
    }
    return token;
}

}  // namespace

QString caminhoDoArquivoDeCapacidade() {
    const QString pasta = pastaDeDados();
    if (pasta.isEmpty()) return QString();
    return QDir(pasta).filePath(QString::fromLatin1(kNomeDoArquivo));
}

QString tokenDeCapacidade() {
    const QString caminho = caminhoDoArquivoDeCapacidade();
    if (caminho.isEmpty()) return QString();

    QFile arquivo(caminho);
    if (arquivo.open(QIODevice::ReadOnly | QIODevice::Text)) {
        const QString existente = QString::fromUtf8(arquivo.readAll()).trimmed();
        arquivo.close();
        if (!existente.isEmpty()) return existente;
    }

    // Primeira execucao nesta maquina, ou arquivo removido pelo usuario.
    const QString token = sortearToken();
    QDir().mkpath(QFileInfo(caminho).absolutePath());
    if (!arquivo.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text)) {
        // Perfil somente leitura nao pode impedir a janela de abrir. O token
        // vale em memoria; so nao sobrevive ao fechamento.
        return token;
    }
    QTextStream saida(&arquivo);
    saida << token;
    arquivo.close();
    // Somente o dono le. No Windows isso mexe apenas no atributo de leitura;
    // a protecao real vem da ACL do perfil, como no Python e no Electron.
    arquivo.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner);
    return token;
}

}  // namespace adri
