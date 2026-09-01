"""A interface Electron historica operando sobre o dominio ERP v2."""
from __future__ import annotations

import json
import re


def _post(cliente, rota, dados):
    return cliente.post(
        rota,
        data=json.dumps(dados),
        content_type="application/json",
    )


def _put(cliente, rota, dados):
    return cliente.put(
        rota,
        data=json.dumps(dados),
        content_type="application/json",
    )


def _json(resposta):
    return json.loads(resposta.data)


def test_v2_serve_o_shell_e_os_assets_do_electron(cliente_http):
    pagina = cliente_http.get("/")
    assert pagina.status_code == 200
    assert pagina.headers["X-Adri-Backend"] == "v2"
    assert b"ERP v2" in pagina.data
    css = cliente_http.get("/css/style.css")
    assert css.status_code == 200
    regra_form_grid = re.search(rb"\.form-grid\s*\{([^}]+)\}", css.data)
    assert regra_form_grid
    assert b"border: 0" in regra_form_grid.group(1)
    assert b"padding: 0" in regra_form_grid.group(1)
    assert cliente_http.get("/js/app.js").status_code == 200


def test_endpoints_de_boot_da_interface_respondem_no_v2(cliente_http):
    clientes = cliente_http.get("/api/clientes?busca=")
    dashboard = cliente_http.get("/api/dashboard/dados")
    auth = cliente_http.get("/api/auth/status")
    notificacoes = cliente_http.get("/api/notificacoes")

    assert clientes.status_code == 200
    assert _json(clientes) == []
    assert dashboard.status_code == 200
    assert set(_json(dashboard)) == {
        "por_tipo", "cidades", "timeline", "ultimos_clientes", "financeiro",
    }
    assert _json(auth)["logado"] is False
    assert _json(notificacoes) == {"nao_lidas": 0, "notificacoes": []}


def test_crud_de_cliente_da_tela_grava_parceiro_erp(cliente_http):
    criado = _post(cliente_http, "/api/clientes", {
        "nome": "Cliente da interface",
        "cep": "89200-000",
        "rua": "Rua do ERP",
        "bairro": "Centro",
        "cidade": "Joinville",
        "entrega_retirada": "Entrega",
        "observacoes": "Criado pelo contrato legado",
    })
    assert criado.status_code == 201
    identificador = _json(criado)["id"]

    listados = _json(cliente_http.get("/api/clientes?busca=interface"))
    assert len(listados) == 1
    assert listados[0]["rua"] == "Rua do ERP"
    assert listados[0]["entrega_retirada"] == "Entrega"

    atualizado = _put(cliente_http, f"/api/clientes/{identificador}", {
        "nome": "Cliente atualizado",
        "cep": "89200-000",
        "rua": "Avenida ERP",
        "bairro": "America",
        "cidade": "Joinville",
        "entrega_retirada": "Retirada",
        "observacoes": "",
    })
    assert atualizado.status_code == 200
    assert _json(atualizado)["cliente"]["rua"] == "Avenida ERP"

    excluido = cliente_http.delete(f"/api/clientes/{identificador}")
    assert excluido.status_code == 200
    assert _json(cliente_http.get("/api/clientes")) == []


def test_recebimento_da_tela_vira_titulo_e_baixa_no_erp(cliente_http):
    cliente = _json(_post(cliente_http, "/api/clientes", {
        "nome": "Cliente financeiro",
        "cidade": "Curitiba",
        "entrega_retirada": "Entrega",
    }))
    titulo = _post(cliente_http, "/api/pagamentos", {
        "cliente_id": cliente["id"],
        "cliente_nome": "texto nao autoritativo",
        "valor": 125.50,
        "descricao": "Sinal do pedido",
        "data_vencimento": "2030-10-10",
        "tipo_pagamento": "Pix",
        "status": "Pendente",
        "data_pagamento": "",
    })
    assert titulo.status_code == 201
    titulo_id = _json(titulo)["id"]

    pagamentos = _json(cliente_http.get("/api/pagamentos"))
    assert len(pagamentos) == 1
    assert pagamentos[0]["id"] == titulo_id
    assert pagamentos[0]["cliente_nome"] == "Cliente financeiro"
    assert pagamentos[0]["valor"] == 125.5
    assert pagamentos[0]["status"] == "Pendente"

    confirmado = _post(
        cliente_http, f"/api/pagamentos/{titulo_id}/confirmar", {}
    )
    assert confirmado.status_code == 200
    assert _json(cliente_http.get("/api/pagamentos"))[0]["status"] == "Recebido"
    metricas = _json(cliente_http.get("/api/pagamentos/metricas"))
    assert metricas["total_recebido"] == 125.5
    assert metricas["total_pendente"] == 0

    extrato = _json(cliente_http.get("/api/v2/financeiro/extrato"))
    assert extrato["itens"][0]["valor_centavos"] == 12550


def test_relatorio_e_mapa_leem_clientes_do_v2(cliente_http):
    _post(cliente_http, "/api/clientes", {
        "nome": "Cliente de Blumenau",
        "cep": "89010-000",
        "rua": "Rua XV",
        "bairro": "Centro",
        "cidade": "Blumenau",
        "entrega_retirada": "Retirada",
    })
    relatorio = _json(cliente_http.get(
        "/api/relatorios?tipo=Retirada&cidade=Blumenau"
    ))
    mapa = _json(cliente_http.get("/api/clientes/mapa"))

    assert relatorio["total"] == 1
    assert relatorio["regioes"][0] == {
        "cidade": "Blumenau", "total": 1, "entregas": 0, "retiradas": 1,
    }
    assert mapa[0]["tipo"] == "Retirada"
    assert mapa[0]["rua"] == "Rua XV"


def test_integracoes_ainda_ausentes_sao_explicitas(cliente_http):
    resposta = _post(cliente_http, "/api/pagamentos/gerar-cobranca", {
        "pagamento_id": 1,
    })
    assert resposta.status_code == 501
    assert "Asaas" in _json(resposta)["erro"]
