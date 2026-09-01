// Modelo de tabela dos clientes.
//
// A filtragem por texto e feita pelo backend (?busca=), nao aqui: e a mesma
// consulta SQL que o frontend web usa, entao as duas interfaces mostram
// exatamente o mesmo resultado para o mesmo termo.
#pragma once

#include <QAbstractTableModel>
#include <QList>

#include "ClienteApi.h"

namespace adri {

class ModeloClientes : public QAbstractTableModel {
    Q_OBJECT

public:
    enum Coluna { ColunaNome = 0, ColunaTipo, ColunaCidade, ColunaBairro, ColunaRua, TotalColunas };

    explicit ModeloClientes(QObject *pai = nullptr);

    int rowCount(const QModelIndex &pai = QModelIndex()) const override;
    int columnCount(const QModelIndex &pai = QModelIndex()) const override;
    QVariant data(const QModelIndex &indice, int papel = Qt::DisplayRole) const override;
    QVariant headerData(int secao, Qt::Orientation orientacao,
                        int papel = Qt::DisplayRole) const override;

    void definirClientes(const QList<Cliente> &clientes);
    /// Nulo quando a linha nao existe -- o chamador tipico e uma selecao de
    /// tabela, que pode estar vazia.
    const Cliente *clienteNaLinha(int linha) const;

private:
    QList<Cliente> clientes_;
};

}  // namespace adri
