#include "ProcessoBackend.h"

#include <QCoreApplication>
#include <QDeadlineTimer>
#include <QDir>
#include <QFileInfo>
#include <QTcpSocket>
#include <QThread>

namespace adri {
namespace {

constexpr int kTimeoutBootMs = 30000;
constexpr int kIntervaloSondaMs = 250;
/// Margem para o Flask fechar conexoes antes de recorrer ao kill.
constexpr int kTimeoutEncerramentoMs = 5000;

}  // namespace

ProcessoBackend::ProcessoBackend(QObject *pai) : QObject(pai) {}

ProcessoBackend::~ProcessoBackend() {
    encerrar();
}

QUrl ProcessoBackend::urlDoApp() {
    return QUrl(QStringLiteral("http://%1:%2/").arg(QString::fromLatin1(kHost)).arg(kPorta));
}

ProcessoBackend::Comando ProcessoBackend::comandoPara(const QString &raizProjeto, bool empacotado) {
    if (empacotado) {
        // Mesmo layout que o electron-builder produz: o executavel do
        // PyInstaller fica em resources/backend ao lado da aplicacao.
        const QString pasta = QDir(raizProjeto).filePath(QStringLiteral("backend"));
        return {QDir(pasta).filePath(QStringLiteral("AdriPoltronasBackend.exe")), {}, pasta};
    }
#ifdef Q_OS_WIN
    const QString python = QStringLiteral("python");
#else
    const QString python = QStringLiteral("python3");
#endif
    const QString script =
        QDir(raizProjeto).filePath(QStringLiteral("backend/servidor.py"));
    return {python, {script}, raizProjeto};
}

bool ProcessoBackend::servidorNoAr(int timeoutMs) {
    QTcpSocket sonda;
    sonda.connectToHost(QString::fromLatin1(kHost), kPorta);
    return sonda.waitForConnected(timeoutMs);
}

bool ProcessoBackend::iniciar(const QString &raizProjeto, bool empacotado, QString *erro) {
    // Uma instancia anterior (ou a janela do Electron) pode ja estar servindo.
    // Reaproveitar evita o segundo processo morrer com a porta ocupada.
    if (servidorNoAr()) {
        emit saidaDoBackend(QStringLiteral("[backend] reaproveitando servidor em %1")
                                .arg(urlDoApp().toString()));
        processoProprio_ = false;
        return true;
    }

    const Comando comando = comandoPara(raizProjeto, empacotado);
    if (empacotado && !QFileInfo::exists(comando.programa)) {
        if (erro) *erro = QStringLiteral("Backend nao encontrado em %1").arg(comando.programa);
        return false;
    }

    processo_ = new QProcess(this);
    processo_->setWorkingDirectory(comando.diretorio);
    processo_->setProcessChannelMode(QProcess::MergedChannels);

    // PYTHONUNBUFFERED garante que a saida chegue linha a linha; sem isso o
    // log do backend so aparece quando o processo morre.
    QProcessEnvironment ambiente = QProcessEnvironment::systemEnvironment();
    ambiente.insert(QStringLiteral("PYTHONUNBUFFERED"), QStringLiteral("1"));
    processo_->setProcessEnvironment(ambiente);

    connect(processo_, &QProcess::readyReadStandardOutput, this, [this] {
        const QString saida = QString::fromLocal8Bit(processo_->readAllStandardOutput());
        for (const QString &linha : saida.split(QLatin1Char('\n'), Qt::SkipEmptyParts))
            emit saidaDoBackend(QStringLiteral("[backend] ") + linha.trimmed());
    });

    processo_->start(comando.programa, comando.argumentos);
    if (!processo_->waitForStarted(5000)) {
        if (erro) {
            *erro = QStringLiteral("Nao foi possivel iniciar o backend (%1): %2")
                        .arg(comando.programa, processo_->errorString());
        }
        return false;
    }
    processoProprio_ = true;

    QDeadlineTimer limite(kTimeoutBootMs);
    while (!limite.hasExpired()) {
        if (processo_->state() == QProcess::NotRunning) {
            if (erro) {
                *erro = QStringLiteral("O backend encerrou com codigo %1 antes de responder.")
                            .arg(processo_->exitCode());
            }
            return false;
        }
        if (servidorNoAr(kIntervaloSondaMs)) return true;
        QThread::msleep(kIntervaloSondaMs);
        QCoreApplication::processEvents();
    }

    if (erro) {
        *erro = QStringLiteral("O servidor interno nao respondeu em %1 dentro de %2s.")
                    .arg(urlDoApp().toString())
                    .arg(kTimeoutBootMs / 1000);
    }
    return false;
}

void ProcessoBackend::encerrar() {
    if (!processo_ || !processoProprio_) return;
    if (processo_->state() == QProcess::NotRunning) return;

    // Sem isso o Python sobrevive a janela e a proxima abertura encontra a
    // porta ocupada -- e o operador ve uma janela vazia sem explicacao.
    processo_->terminate();
    if (!processo_->waitForFinished(kTimeoutEncerramentoMs)) {
        processo_->kill();
        processo_->waitForFinished(1000);
    }
}

}  // namespace adri
