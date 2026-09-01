#include "ModeloClientes.h"

#include <QColor>

namespace adri {

ModeloClientes::ModeloClientes(QObject *pai) : QAbstractTableModel(pai) {}

int ModeloClientes::rowCount(const QModelIndex &pai) const {
    return pai.isValid() ? 0 : static_cast<int>(clientes_.size());
}

int ModeloClientes::columnCount(const QModelIndex &pai) const {
    return pai.isValid() ? 0 : TotalColunas;
}

QVariant ModeloClientes::data(const QModelIndex &indice, int papel) const {
    if (!indice.isValid() || indice.row() >= clientes_.size()) return {};
    const Cliente &cliente = clientes_.at(indice.row());

    if (papel == Qt::DisplayRole) {
        switch (indice.column()) {
            case ColunaNome: return cliente.nome;
            case ColunaTipo: return cliente.entregaRetirada;
            case ColunaCidade: return cliente.cidade;
            case ColunaBairro: return cliente.bairro;
            case ColunaRua: return cliente.rua;
            default: return {};
        }
    }

    // As mesmas cores dos badges da interface web: verde para entrega, ambar
    // para retirada. Quem usa as duas telas reconhece o tipo pela cor.
    if (papel == Qt::ForegroundRole && indice.column() == ColunaTipo) {
        return cliente.entregaRetirada == QLatin1String("Entrega") ? QColor(0x10, 0xb9, 0x81)
                                                                   : QColor(0xf5, 0x9e, 0x0b);
    }

    if (papel == Qt::ToolTipRole && !cliente.observacoes.isEmpty()) return cliente.observacoes;

    return {};
}

QVariant ModeloClientes::headerData(int secao, Qt::Orientation orientacao, int papel) const {
    if (papel != Qt::DisplayRole || orientacao != Qt::Horizontal) return {};
    switch (secao) {
        case ColunaNome: return QStringLiteral("Nome");
        case ColunaTipo: return QStringLiteral("Tipo");
        case ColunaCidade: return QStringLiteral("Cidade");
        case ColunaBairro: return QStringLiteral("Bairro");
        case ColunaRua: return QStringLiteral("Rua");
        default: return {};
    }
}

void ModeloClientes::definirClientes(const QList<Cliente> &clientes) {
    beginResetModel();
    clientes_ = clientes;
    endResetModel();
}

const Cliente *ModeloClientes::clienteNaLinha(int linha) const {
    if (linha < 0 || linha >= clientes_.size()) return nullptr;
    return &clientes_.at(linha);
}

}  // namespace adri
