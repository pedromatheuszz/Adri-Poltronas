#include "DialogoCliente.h"

#include <QComboBox>
#include <QDialogButtonBox>
#include <QFormLayout>
#include <QLineEdit>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QVBoxLayout>

namespace adri {

DialogoCliente::DialogoCliente(const Cliente &inicial, QWidget *pai)
    : QDialog(pai),
      nome_(new QLineEdit(inicial.nome, this)),
      cep_(new QLineEdit(inicial.cep, this)),
      rua_(new QLineEdit(inicial.rua, this)),
      bairro_(new QLineEdit(inicial.bairro, this)),
      cidade_(new QLineEdit(inicial.cidade, this)),
      tipo_(new QComboBox(this)),
      observacoes_(new QPlainTextEdit(inicial.observacoes, this)),
      id_(inicial.id) {
    setWindowTitle(id_ == 0 ? QStringLiteral("Novo cliente") : QStringLiteral("Editar cliente"));
    setMinimumWidth(420);

    cep_->setPlaceholderText(QStringLiteral("00000-000"));
    // Os dois unicos valores aceitos por validators.validar_cliente.
    tipo_->addItems({QStringLiteral("Entrega"), QStringLiteral("Retirada")});
    if (!inicial.entregaRetirada.isEmpty()) tipo_->setCurrentText(inicial.entregaRetirada);
    observacoes_->setFixedHeight(70);

    auto *formulario = new QFormLayout;
    formulario->addRow(QStringLiteral("Nome"), nome_);
    formulario->addRow(QStringLiteral("CEP"), cep_);
    formulario->addRow(QStringLiteral("Rua"), rua_);
    formulario->addRow(QStringLiteral("Bairro"), bairro_);
    formulario->addRow(QStringLiteral("Cidade"), cidade_);
    formulario->addRow(QStringLiteral("Tipo"), tipo_);
    formulario->addRow(QStringLiteral("Observacoes"), observacoes_);

    auto *botoes = new QDialogButtonBox(QDialogButtonBox::Save | QDialogButtonBox::Cancel, this);
    botoes->button(QDialogButtonBox::Save)->setText(QStringLiteral("Salvar"));
    botoes->button(QDialogButtonBox::Cancel)->setText(QStringLiteral("Cancelar"));
    connect(botoes, &QDialogButtonBox::accepted, this, &QDialog::accept);
    connect(botoes, &QDialogButtonBox::rejected, this, &QDialog::reject);

    // Sem nome nao ha o que salvar; o resto o backend valida e devolve na
    // chave `erro`, que a janela exibe na barra de status.
    auto atualizarSalvar = [this, botoes] {
        botoes->button(QDialogButtonBox::Save)->setEnabled(!nome_->text().trimmed().isEmpty());
    };
    connect(nome_, &QLineEdit::textChanged, this, atualizarSalvar);
    atualizarSalvar();

    auto *coluna = new QVBoxLayout(this);
    coluna->addLayout(formulario);
    coluna->addWidget(botoes);
}

Cliente DialogoCliente::cliente() const {
    Cliente cliente;
    cliente.id = id_;
    cliente.nome = nome_->text().trimmed();
    cliente.cep = cep_->text().trimmed();
    cliente.rua = rua_->text().trimmed();
    cliente.bairro = bairro_->text().trimmed();
    cliente.cidade = cidade_->text().trimmed();
    cliente.entregaRetirada = tipo_->currentText();
    cliente.observacoes = observacoes_->toPlainText().trimmed();
    return cliente;
}

}  // namespace adri
