#include "JanelaPrincipal.h"

#include <QHBoxLayout>
#include <QHeaderView>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QPushButton>
#include <QStatusBar>
#include <QTableView>
#include <QTimer>
#include <QVBoxLayout>

#include "DialogoCliente.h"
#include "ModeloClientes.h"

namespace adri {
namespace {

constexpr int kAtrasoDaBuscaMs = 300;

/// Cartao de metrica: rotulo em cima, numero embaixo.
QWidget *cartao(const QString &titulo, QLabel **valorFora) {
    auto *caixa = new QWidget;
    caixa->setObjectName(QStringLiteral("cartao"));

    auto *valor = new QLabel(QStringLiteral("--"));
    valor->setObjectName(QStringLiteral("valorDoCartao"));
    auto *rotulo = new QLabel(titulo);
    rotulo->setObjectName(QStringLiteral("rotuloDoCartao"));

    auto *coluna = new QVBoxLayout(caixa);
    coluna->setContentsMargins(16, 12, 16, 12);
    coluna->addWidget(valor);
    coluna->addWidget(rotulo);

    *valorFora = valor;
    return caixa;
}

}  // namespace

JanelaPrincipal::JanelaPrincipal(ClienteApi *api, QWidget *pai)
    : QMainWindow(pai),
      api_(api),
      modelo_(new ModeloClientes(this)),
      tabela_(new QTableView(this)),
      busca_(new QLineEdit(this)),
      adiarBusca_(new QTimer(this)) {
    setWindowTitle(QStringLiteral("Adri Poltronas -- Qt"));
    resize(1000, 680);

    tabela_->setModel(modelo_);
    tabela_->setSelectionBehavior(QAbstractItemView::SelectRows);
    tabela_->setSelectionMode(QAbstractItemView::SingleSelection);
    tabela_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    tabela_->verticalHeader()->setVisible(false);
    tabela_->setAlternatingRowColors(true);

    // Nome e rua sao os campos longos e ficam com o espaco sobrando; os
    // demais encolhem ate o conteudo. Com largura igual para todas, o nome --
    // justamente o que se procura na lista -- aparecia truncado.
    QHeaderView *cabecalho = tabela_->horizontalHeader();
    cabecalho->setStretchLastSection(false);
    cabecalho->setSectionResizeMode(ModeloClientes::ColunaNome, QHeaderView::Stretch);
    cabecalho->setSectionResizeMode(ModeloClientes::ColunaTipo, QHeaderView::ResizeToContents);
    cabecalho->setSectionResizeMode(ModeloClientes::ColunaCidade, QHeaderView::ResizeToContents);
    cabecalho->setSectionResizeMode(ModeloClientes::ColunaBairro, QHeaderView::ResizeToContents);
    cabecalho->setSectionResizeMode(ModeloClientes::ColunaRua, QHeaderView::Stretch);
    connect(tabela_, &QTableView::doubleClicked, this, &JanelaPrincipal::editarSelecionado);

    adiarBusca_->setSingleShot(true);
    adiarBusca_->setInterval(kAtrasoDaBuscaMs);
    connect(adiarBusca_, &QTimer::timeout, this, &JanelaPrincipal::recarregar);
    connect(busca_, &QLineEdit::textChanged, adiarBusca_, qOverload<>(&QTimer::start));

    auto *central = new QWidget(this);
    auto *coluna = new QVBoxLayout(central);
    coluna->setContentsMargins(18, 18, 18, 18);
    coluna->setSpacing(14);
    coluna->addWidget(montarCartoes());
    coluna->addWidget(montarBarraDeBusca());
    coluna->addWidget(tabela_, 1);
    setCentralWidget(central);
    // Buscar e a primeira coisa que se faz numa lista de clientes; comecar com
    // o cursor ali poupa um clique a cada abertura.
    busca_->setFocus();

    connect(api_, &ClienteApi::clientesRecebidos, modelo_, &ModeloClientes::definirClientes);
    connect(api_, &ClienteApi::metricasRecebidas, this, &JanelaPrincipal::aoReceberMetricas);
    connect(api_, &ClienteApi::falhou, this, &JanelaPrincipal::aoFalhar);
    connect(api_, &ClienteApi::escritaConcluida, this, [this](const QString &mensagem) {
        statusBar()->showMessage(mensagem, 4000);
        recarregar();
    });

    recarregar();
}

QWidget *JanelaPrincipal::montarCartoes() {
    auto *faixa = new QWidget;
    auto *linha = new QHBoxLayout(faixa);
    linha->setContentsMargins(0, 0, 0, 0);
    linha->setSpacing(12);
    linha->addWidget(cartao(QStringLiteral("Total de clientes"), &valorTotal_));
    linha->addWidget(cartao(QStringLiteral("Entregas"), &valorEntregas_));
    linha->addWidget(cartao(QStringLiteral("Retiradas"), &valorRetiradas_));
    linha->addWidget(cartao(QStringLiteral("Novos (30 dias)"), &valorNovos_));
    return faixa;
}

QWidget *JanelaPrincipal::montarBarraDeBusca() {
    busca_->setPlaceholderText(QStringLiteral("Buscar por nome, cidade ou bairro..."));
    busca_->setClearButtonEnabled(true);

    auto *novo = new QPushButton(QStringLiteral("Novo"));
    auto *editar = new QPushButton(QStringLiteral("Editar"));
    auto *excluir = new QPushButton(QStringLiteral("Excluir"));
    connect(novo, &QPushButton::clicked, this, &JanelaPrincipal::novoCliente);
    connect(editar, &QPushButton::clicked, this, &JanelaPrincipal::editarSelecionado);
    connect(excluir, &QPushButton::clicked, this, &JanelaPrincipal::excluirSelecionado);

    auto *barra = new QWidget;
    auto *linha = new QHBoxLayout(barra);
    linha->setContentsMargins(0, 0, 0, 0);
    linha->addWidget(busca_, 1);
    linha->addWidget(novo);
    linha->addWidget(editar);
    linha->addWidget(excluir);
    return barra;
}

void JanelaPrincipal::recarregar() {
    api_->listarClientes(busca_->text().trimmed());
    api_->carregarMetricas();
}

void JanelaPrincipal::aoReceberMetricas(const MetricasDashboard &metricas) {
    valorTotal_->setText(QString::number(metricas.totalClientes));
    valorEntregas_->setText(QString::number(metricas.totalEntrega));
    valorRetiradas_->setText(QString::number(metricas.totalRetirada));
    valorNovos_->setText(QString::number(metricas.cadastros30d));
}

void JanelaPrincipal::aoFalhar(const QString &mensagem) {
    // Barra de status em vez de caixa modal: uma falha de rede durante a busca
    // dispararia um popup a cada tecla.
    statusBar()->showMessage(mensagem, 8000);
}

const Cliente *JanelaPrincipal::selecionado() const {
    const QModelIndexList linhas = tabela_->selectionModel()->selectedRows();
    if (linhas.isEmpty()) return nullptr;
    return modelo_->clienteNaLinha(linhas.first().row());
}

void JanelaPrincipal::novoCliente() {
    DialogoCliente dialogo{Cliente{}, this};
    if (dialogo.exec() == QDialog::Accepted) api_->criarCliente(dialogo.cliente());
}

void JanelaPrincipal::editarSelecionado() {
    const Cliente *cliente = selecionado();
    if (!cliente) {
        statusBar()->showMessage(QStringLiteral("Selecione um cliente."), 3000);
        return;
    }
    DialogoCliente dialogo{*cliente, this};
    if (dialogo.exec() == QDialog::Accepted)
        api_->atualizarCliente(cliente->id, dialogo.cliente());
}

void JanelaPrincipal::excluirSelecionado() {
    const Cliente *cliente = selecionado();
    if (!cliente) {
        statusBar()->showMessage(QStringLiteral("Selecione um cliente."), 3000);
        return;
    }
    const auto resposta = QMessageBox::question(
        this, QStringLiteral("Excluir cliente"),
        QStringLiteral("Excluir \"%1\"? A acao nao pode ser desfeita.").arg(cliente->nome));
    if (resposta == QMessageBox::Yes) api_->excluirCliente(cliente->id);
}

}  // namespace adri
