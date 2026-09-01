// Testes do modelo da tabela.
//
// O ponto sensivel e `clienteNaLinha`: ele alimenta editar e excluir a partir
// da selecao, e um indice fora de faixa ali significaria excluir o cliente
// errado -- ou desreferenciar lixo.
#include <QColor>
#include <QTest>

#include "ModeloClientes.h"

using adri::Cliente;
using adri::ModeloClientes;

namespace {

Cliente fazerCliente(int id, const QString &nome, const QString &tipo) {
    Cliente cliente;
    cliente.id = id;
    cliente.nome = nome;
    cliente.entregaRetirada = tipo;
    cliente.cidade = QStringLiteral("Joinville");
    cliente.bairro = QStringLiteral("Gloria");
    cliente.rua = QStringLiteral("Rua Nazareno, 287");
    return cliente;
}

}  // namespace

class TesteModeloClientes : public QObject {
    Q_OBJECT

private slots:
    void tabelaVaziaNaoTemLinhas();
    void linhasEColunasRefletemOsDados();
    void colunasMostramOsCamposCertos();
    void tipoUsaAsCoresDosBadges();
    void linhaForaDeFaixaDevolveNulo();
    void recarregarSubstituiALista();
};

void TesteModeloClientes::tabelaVaziaNaoTemLinhas() {
    ModeloClientes modelo;

    QCOMPARE(modelo.rowCount(), 0);
    QCOMPARE(modelo.columnCount(), int(ModeloClientes::TotalColunas));
}

void TesteModeloClientes::linhasEColunasRefletemOsDados() {
    ModeloClientes modelo;

    modelo.definirClientes({fazerCliente(1, QStringLiteral("Ana"), QStringLiteral("Entrega")),
                            fazerCliente(2, QStringLiteral("Bruno"), QStringLiteral("Retirada"))});

    QCOMPARE(modelo.rowCount(), 2);
}

void TesteModeloClientes::colunasMostramOsCamposCertos() {
    ModeloClientes modelo;
    modelo.definirClientes({fazerCliente(1, QStringLiteral("Ana"), QStringLiteral("Entrega"))});

    QCOMPARE(modelo.index(0, ModeloClientes::ColunaNome).data().toString(),
             QStringLiteral("Ana"));
    QCOMPARE(modelo.index(0, ModeloClientes::ColunaTipo).data().toString(),
             QStringLiteral("Entrega"));
    QCOMPARE(modelo.index(0, ModeloClientes::ColunaCidade).data().toString(),
             QStringLiteral("Joinville"));
}

void TesteModeloClientes::tipoUsaAsCoresDosBadges() {
    ModeloClientes modelo;
    modelo.definirClientes({fazerCliente(1, QStringLiteral("Ana"), QStringLiteral("Entrega")),
                            fazerCliente(2, QStringLiteral("Bruno"), QStringLiteral("Retirada"))});

    const auto cor = [&modelo](int linha) {
        return modelo.index(linha, ModeloClientes::ColunaTipo)
            .data(Qt::ForegroundRole)
            .value<QColor>();
    };

    QCOMPARE(cor(0), QColor(0x10, 0xb9, 0x81));  // verde: entrega
    QCOMPARE(cor(1), QColor(0xf5, 0x9e, 0x0b));  // ambar: retirada
}

void TesteModeloClientes::linhaForaDeFaixaDevolveNulo() {
    ModeloClientes modelo;
    modelo.definirClientes({fazerCliente(1, QStringLiteral("Ana"), QStringLiteral("Entrega"))});

    QVERIFY(modelo.clienteNaLinha(0) != nullptr);
    QCOMPARE(modelo.clienteNaLinha(0)->id, 1);
    QVERIFY(modelo.clienteNaLinha(-1) == nullptr);
    QVERIFY(modelo.clienteNaLinha(1) == nullptr);
    QVERIFY(modelo.clienteNaLinha(999) == nullptr);
}

void TesteModeloClientes::recarregarSubstituiALista() {
    // A busca recarrega o modelo a cada termo digitado; se a lista fosse
    // acumulada, o resultado do filtro viria somado ao anterior.
    ModeloClientes modelo;
    modelo.definirClientes({fazerCliente(1, QStringLiteral("Ana"), QStringLiteral("Entrega")),
                            fazerCliente(2, QStringLiteral("Bruno"), QStringLiteral("Retirada"))});

    modelo.definirClientes({fazerCliente(2, QStringLiteral("Bruno"), QStringLiteral("Retirada"))});

    QCOMPARE(modelo.rowCount(), 1);
    QCOMPARE(modelo.clienteNaLinha(0)->nome, QStringLiteral("Bruno"));
}

QTEST_MAIN(TesteModeloClientes)
#include "test_modelo_clientes.moc"
