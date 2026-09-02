#include "ClienteApi.h"

#include "Capacidade.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QUrlQuery>

namespace adri {
namespace {

QString texto(const QJsonObject &objeto, const char *chave) {
    return objeto.value(QLatin1String(chave)).toString();
}

}  // namespace

Cliente Cliente::doJson(const QJsonObject &objeto) {
    Cliente cliente;
    cliente.id = objeto.value(QLatin1String("id")).toInt();
    cliente.nome = texto(objeto, "nome");
    cliente.cep = texto(objeto, "cep");
    cliente.rua = texto(objeto, "rua");
    cliente.bairro = texto(objeto, "bairro");
    cliente.cidade = texto(objeto, "cidade");
    cliente.entregaRetirada = texto(objeto, "entrega_retirada");
    cliente.observacoes = texto(objeto, "observacoes");
    return cliente;
}

QJsonObject Cliente::paraJson() const {
    return QJsonObject{
        {QLatin1String("nome"), nome},
        {QLatin1String("cep"), cep},
        {QLatin1String("rua"), rua},
        {QLatin1String("bairro"), bairro},
        {QLatin1String("cidade"), cidade},
        {QLatin1String("entrega_retirada"), entregaRetirada},
        {QLatin1String("observacoes"), observacoes},
    };
}

MetricasDashboard MetricasDashboard::doJson(const QJsonObject &objeto) {
    MetricasDashboard metricas;
    metricas.totalClientes = objeto.value(QLatin1String("total_clientes")).toInt();
    metricas.totalEntrega = objeto.value(QLatin1String("total_entrega")).toInt();
    metricas.totalRetirada = objeto.value(QLatin1String("total_retirada")).toInt();
    metricas.cadastros30d = objeto.value(QLatin1String("cadastros_30d")).toInt();
    return metricas;
}

ClienteApi::ClienteApi(QUrl base, QObject *pai)
    : QObject(pai), base_(std::move(base)), rede_(new QNetworkAccessManager(this)),
      capacidade_(tokenDeCapacidade().toUtf8()) {}

QUrl ClienteApi::urlDeClientes(const QString &busca) const {
    QUrl url = base_.resolved(QUrl(QStringLiteral("/api/clientes")));
    if (!busca.isEmpty()) {
        QUrlQuery consulta;
        consulta.addQueryItem(QStringLiteral("busca"), busca);
        url.setQuery(consulta);
    }
    return url;
}

QUrl ClienteApi::urlDeCliente(int id) const {
    return base_.resolved(QUrl(QStringLiteral("/api/clientes/%1").arg(id)));
}

QUrl ClienteApi::urlDoDashboard() const {
    return base_.resolved(QUrl(QStringLiteral("/api/dashboard")));
}

QNetworkRequest ClienteApi::requisicao(const QUrl &url) const {
    QNetworkRequest pedido(url);
    if (!capacidade_.isEmpty())
        pedido.setRawHeader(kHeaderDaCapacidade, capacidade_);
    return pedido;
}

void ClienteApi::tratarFalha(QNetworkReply *resposta) {
    const QByteArray corpo = resposta->readAll();
    const QJsonObject json = QJsonDocument::fromJson(corpo).object();
    const QString detalhe = json.value(QLatin1String("erro")).toString();
    emit falhou(detalhe.isEmpty() ? resposta->errorString() : detalhe);
}

void ClienteApi::listarClientes(const QString &busca) {
    QNetworkReply *resposta = rede_->get(requisicao(urlDeClientes(busca)));
    connect(resposta, &QNetworkReply::finished, this, [this, resposta] {
        resposta->deleteLater();
        if (resposta->error() != QNetworkReply::NoError) {
            tratarFalha(resposta);
            return;
        }
        QList<Cliente> clientes;
        const QJsonArray registros = QJsonDocument::fromJson(resposta->readAll()).array();
        clientes.reserve(registros.size());
        for (const QJsonValue &registro : registros)
            clientes.append(Cliente::doJson(registro.toObject()));
        emit clientesRecebidos(clientes);
    });
}

void ClienteApi::carregarMetricas() {
    QNetworkReply *resposta = rede_->get(requisicao(urlDoDashboard()));
    connect(resposta, &QNetworkReply::finished, this, [this, resposta] {
        resposta->deleteLater();
        if (resposta->error() != QNetworkReply::NoError) {
            tratarFalha(resposta);
            return;
        }
        emit metricasRecebidas(
            MetricasDashboard::doJson(QJsonDocument::fromJson(resposta->readAll()).object()));
    });
}

void ClienteApi::enviarEscrita(const QByteArray &verbo, const QUrl &url, const QJsonObject &corpo,
                               const QString &mensagemDeSucesso) {
    QNetworkRequest pedido = requisicao(url);
    pedido.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("application/json"));

    const QByteArray dados =
        corpo.isEmpty() ? QByteArray() : QJsonDocument(corpo).toJson(QJsonDocument::Compact);
    QNetworkReply *resposta = rede_->sendCustomRequest(pedido, verbo, dados);

    connect(resposta, &QNetworkReply::finished, this, [this, resposta, mensagemDeSucesso] {
        resposta->deleteLater();
        if (resposta->error() != QNetworkReply::NoError) {
            tratarFalha(resposta);
            return;
        }
        emit escritaConcluida(mensagemDeSucesso);
    });
}

void ClienteApi::criarCliente(const Cliente &cliente) {
    enviarEscrita("POST", urlDeClientes(QString()), cliente.paraJson(),
                  QStringLiteral("Cliente cadastrado."));
}

void ClienteApi::atualizarCliente(int id, const Cliente &cliente) {
    enviarEscrita("PUT", urlDeCliente(id), cliente.paraJson(),
                  QStringLiteral("Cliente atualizado."));
}

void ClienteApi::excluirCliente(int id) {
    enviarEscrita("DELETE", urlDeCliente(id), {}, QStringLiteral("Cliente excluido."));
}

}  // namespace adri
