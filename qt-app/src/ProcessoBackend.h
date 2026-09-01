// Ciclo de vida do backend Flask, visto pelo cliente Qt.
//
// E o equivalente em C++ de electron/backend.ts: sobe o mesmo processo Python,
// espera a porta responder e encerra o filho junto com a janela. As duas
// interfaces falam com o mesmo backend, entao a logica precisa casar --
// inclusive o reaproveitamento de um servidor ja no ar, que evita o segundo
// processo morrer com "endereco em uso".
#pragma once

#include <QObject>
#include <QProcess>
#include <QString>
#include <QStringList>
#include <QUrl>

namespace adri {

/// Porta fixa: o redirect_uri do OAuth da Microsoft esta registrado no Azure
/// como http://localhost:5000/callback. Sortear porta quebraria o OneDrive.
inline constexpr quint16 kPorta = 5000;
inline constexpr char kHost[] = "127.0.0.1";

class ProcessoBackend : public QObject {
    Q_OBJECT

public:
    /// Como iniciar o backend, conforme empacotado ou nao.
    struct Comando {
        QString programa;
        QStringList argumentos;
        QString diretorio;
    };

    explicit ProcessoBackend(QObject *pai = nullptr);
    ~ProcessoBackend() override;

    static QUrl urlDoApp();
    static Comando comandoPara(const QString &raizProjeto, bool empacotado);

    /// True quando alguem ja escuta na porta. Basta a conexao TCP: o corpo da
    /// resposta nao importa, so ter um servidor do outro lado.
    static bool servidorNoAr(int timeoutMs = 1000);

    /// Sobe o backend e so retorna quando ele responde. Em caso de falha
    /// preenche `erro` com algo exibivel ao operador.
    bool iniciar(const QString &raizProjeto, bool empacotado, QString *erro);

    void encerrar();

signals:
    /// Cada linha de stdout/stderr do backend, para log.
    void saidaDoBackend(const QString &linha);

private:
    QProcess *processo_ = nullptr;
    /// Falso quando reaproveitamos um servidor de outra instancia: nesse caso
    /// nao podemos mata-lo ao sair, ele nao e nosso.
    bool processoProprio_ = false;
};

}  // namespace adri
