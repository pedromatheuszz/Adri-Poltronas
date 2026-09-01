// Testes do cliente HTTP.
//
// Cobrem o que quebra em silencio: a montagem das URLs (uma busca mal
// codificada devolve a lista inteira em vez de filtrar) e a traducao entre o
// JSON do backend e a struct. As chaves aqui precisam casar com o que
// backend/blueprints/clientes.py devolve -- um rename la sem rename aqui deixa
// a tabela em branco sem erro nenhum.
#include <QJsonDocument>
#include <QJsonObject>
#include <QTest>
#include <QUrlQuery>

#include "ClienteApi.h"

using adri::Cliente;
using adri::ClienteApi;
using adri::MetricasDashboard;

namespace {

QJsonObject jsonDeCliente() {
    return QJsonDocument::fromJson(R"({
        "id": 4,
        "nome": "Doraci Pereira da Silva",
        "cep": "89230-210",
        "rua": "Rua Padre Roma, 126",
        "bairro": "Joao Costa",
        "cidade": "Joinville",
        "entrega_retirada": "Retirada",
        "observacoes": "portao azul"
    })")
        .object();
}

}  // namespace

class TesteClienteApi : public QObject {
    Q_OBJECT

private slots:
    void clienteVemDoJsonDoBackend();
    void campoAusenteNaoQuebraOParse();
    void corpoEnviadoNaoLevaOId();
    void metricasVemDoJsonDoDashboard();
    void buscaVaziaNaoAdicionaQueryString();
    void buscaComEspacoEAcentoEhCodificada();
    void urlDeClienteUsaOId();
};

void TesteClienteApi::clienteVemDoJsonDoBackend() {
    const Cliente cliente = Cliente::doJson(jsonDeCliente());

    QCOMPARE(cliente.id, 4);
    QCOMPARE(cliente.nome, QStringLiteral("Doraci Pereira da Silva"));
    QCOMPARE(cliente.cep, QStringLiteral("89230-210"));
    QCOMPARE(cliente.entregaRetirada, QStringLiteral("Retirada"));
    QCOMPARE(cliente.observacoes, QStringLiteral("portao azul"));
}

void TesteClienteApi::campoAusenteNaoQuebraOParse() {
    // Registros antigos vem com campos vazios ou ausentes; a tabela deve
    // mostrar a linha em branco, nao sumir com o cliente.
    const Cliente cliente = Cliente::doJson(QJsonObject{{"id", 3}, {"nome", "Teste"}});

    QCOMPARE(cliente.id, 3);
    QCOMPARE(cliente.nome, QStringLiteral("Teste"));
    QVERIFY(cliente.cidade.isEmpty());
    QVERIFY(cliente.entregaRetirada.isEmpty());
}

void TesteClienteApi::corpoEnviadoNaoLevaOId() {
    // O id viaja na URL (/api/clientes/<id>). Manda-lo tambem no corpo faria o
    // validador do backend recusar um campo que ele nao espera.
    const QJsonObject corpo = Cliente::doJson(jsonDeCliente()).paraJson();

    QVERIFY(!corpo.contains(QLatin1String("id")));
    QCOMPARE(corpo.value(QLatin1String("entrega_retirada")).toString(),
             QStringLiteral("Retirada"));
    QCOMPARE(corpo.size(), 7);
}

void TesteClienteApi::metricasVemDoJsonDoDashboard() {
    const QJsonObject json =
        QJsonDocument::fromJson(
            R"({"cadastros_30d":4,"total_clientes":4,"total_entrega":3,"total_retirada":1})")
            .object();

    const MetricasDashboard metricas = MetricasDashboard::doJson(json);

    QCOMPARE(metricas.totalClientes, 4);
    QCOMPARE(metricas.totalEntrega, 3);
    QCOMPARE(metricas.totalRetirada, 1);
    QCOMPARE(metricas.cadastros30d, 4);
}

void TesteClienteApi::buscaVaziaNaoAdicionaQueryString() {
    ClienteApi api{QUrl(QStringLiteral("http://127.0.0.1:5000/"))};

    QCOMPARE(api.urlDeClientes(QString()).toString(),
             QStringLiteral("http://127.0.0.1:5000/api/clientes"));
}

void TesteClienteApi::buscaComEspacoEAcentoEhCodificada() {
    ClienteApi api{QUrl(QStringLiteral("http://127.0.0.1:5000/"))};

    const QUrl url = api.urlDeClientes(QStringLiteral("Joao Costa"));

    // O termo precisa voltar intacto do outro lado da codificacao.
    QCOMPARE(QUrlQuery(url).queryItemValue(QStringLiteral("busca"), QUrl::FullyDecoded),
             QStringLiteral("Joao Costa"));
    QVERIFY(!url.toEncoded().contains(' '));
}

void TesteClienteApi::urlDeClienteUsaOId() {
    ClienteApi api{QUrl(QStringLiteral("http://127.0.0.1:5000/"))};

    QCOMPARE(api.urlDeCliente(42).toString(),
             QStringLiteral("http://127.0.0.1:5000/api/clientes/42"));
}

QTEST_MAIN(TesteClienteApi)
#include "test_cliente_api.moc"
