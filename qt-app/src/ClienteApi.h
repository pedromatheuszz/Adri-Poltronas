// Cliente HTTP da API do Flask.
//
// A janela Qt nao fala com o SQLite: ela consome os mesmos endpoints
// /api/clientes e /api/dashboard que o frontend web. Duas UIs sobre um unico
// backend -- validacao, migrations e regras de negocio continuam em um lugar
// so, o Python, que e onde estao os testes.
#pragma once

#include <QJsonObject>
#include <QList>
#include <QNetworkAccessManager>
#include <QObject>
#include <QString>
#include <QUrl>

namespace adri {

struct Cliente {
    int id = 0;
    QString nome;
    QString cep;
    QString rua;
    QString bairro;
    QString cidade;
    QString entregaRetirada;
    QString observacoes;

    static Cliente doJson(const QJsonObject &objeto);
    /// Corpo enviado ao backend. O id nao entra: ele viaja na URL.
    QJsonObject paraJson() const;
};

struct MetricasDashboard {
    int totalClientes = 0;
    int totalEntrega = 0;
    int totalRetirada = 0;
    int cadastros30d = 0;

    static MetricasDashboard doJson(const QJsonObject &objeto);
};

class ClienteApi : public QObject {
    Q_OBJECT

public:
    explicit ClienteApi(QUrl base, QObject *pai = nullptr);

    /// Exposto para teste: a busca precisa ser percent-encoded, senao um nome
    /// com espaco ou acento gera uma URL invalida e o filtro some.
    QUrl urlDeClientes(const QString &busca) const;
    QUrl urlDeCliente(int id) const;
    QUrl urlDoDashboard() const;

    void listarClientes(const QString &busca = QString());
    void carregarMetricas();
    void criarCliente(const Cliente &cliente);
    void atualizarCliente(int id, const Cliente &cliente);
    void excluirCliente(int id);

signals:
    void clientesRecebidos(const QList<adri::Cliente> &clientes);
    void metricasRecebidas(const adri::MetricasDashboard &metricas);
    /// Emitido apos criar/atualizar/excluir, para a janela recarregar a lista.
    void escritaConcluida(const QString &mensagem);
    void falhou(const QString &mensagem);

private:
    /// Traduz erro de rede em mensagem legivel, preferindo a chave `erro` que
    /// a API sempre devolve -- o frontend web depende dela e nos tambem.
    void tratarFalha(class QNetworkReply *resposta);
    void enviarEscrita(const QByteArray &verbo, const QUrl &url, const QJsonObject &corpo,
                       const QString &mensagemDeSucesso);

    QUrl base_;
    QNetworkAccessManager *rede_;
};

}  // namespace adri
