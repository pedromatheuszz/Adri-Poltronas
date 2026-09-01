// Formulario de cadastro/edicao de cliente.
//
// A validacao real e do backend (backend/validators.py): CEP, tipo e tamanho
// dos campos sao verificados la, e o dialogo so exige o minimo para nao enviar
// uma requisicao obviamente vazia. Duplicar as regras aqui criaria duas fontes
// de verdade que divergem na primeira mudanca.
#pragma once

#include <QDialog>

#include "ClienteApi.h"

class QComboBox;
class QLineEdit;
class QPlainTextEdit;

namespace adri {

class DialogoCliente : public QDialog {
    Q_OBJECT

public:
    /// `inicial` vazio cadastra; preenchido edita.
    explicit DialogoCliente(const Cliente &inicial, QWidget *pai = nullptr);

    Cliente cliente() const;

private:
    QLineEdit *nome_;
    QLineEdit *cep_;
    QLineEdit *rua_;
    QLineEdit *bairro_;
    QLineEdit *cidade_;
    QComboBox *tipo_;
    QPlainTextEdit *observacoes_;
    int id_;
};

}  // namespace adri
