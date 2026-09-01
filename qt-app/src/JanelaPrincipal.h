// Janela principal do cliente Qt.
//
// Cobre o nucleo do app: metricas do dashboard e o CRUD de clientes. Entregas,
// pagamentos, mapa e relatorios seguem so na interface web -- dependem de
// Leaflet, graficos e do fluxo OAuth do OneDrive, que nao tem equivalente
// direto em Widgets. As duas janelas conversam com o mesmo backend, entao o
// que e feito aqui aparece la e vice-versa.
#pragma once

#include <QMainWindow>

#include "ClienteApi.h"

class QLabel;
class QLineEdit;
class QTableView;
class QTimer;

namespace adri {

class ModeloClientes;

class JanelaPrincipal : public QMainWindow {
    Q_OBJECT

public:
    explicit JanelaPrincipal(ClienteApi *api, QWidget *pai = nullptr);

private slots:
    void aoReceberMetricas(const adri::MetricasDashboard &metricas);
    void aoFalhar(const QString &mensagem);
    void novoCliente();
    void editarSelecionado();
    void excluirSelecionado();

private:
    QWidget *montarCartoes();
    QWidget *montarBarraDeBusca();
    void recarregar();
    /// Nulo quando nada esta selecionado.
    const Cliente *selecionado() const;

    ClienteApi *api_;
    ModeloClientes *modelo_;
    QTableView *tabela_;
    QLineEdit *busca_;
    /// Evita uma requisicao por tecla digitada na busca.
    QTimer *adiarBusca_;
    QLabel *valorTotal_;
    QLabel *valorEntregas_;
    QLabel *valorRetiradas_;
    QLabel *valorNovos_;
};

}  // namespace adri
