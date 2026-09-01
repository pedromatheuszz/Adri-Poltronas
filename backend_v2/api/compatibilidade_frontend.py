"""Adaptador da interface Electron atual para o dominio do backend ERP v2.

O frontend ainda usa o contrato historico ``/api/*``. Este blueprint traduz
somente a borda HTTP: todas as escritas relevantes continuam passando pelos
casos de uso, unidade de trabalho, validacoes e auditoria do v2. Nenhum modulo
do backend v1 e importado.
"""
from __future__ import annotations

import csv
from datetime import date
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

from flask import (
    Blueprint,
    Response,
    after_this_request,
    current_app,
    jsonify,
    request,
    send_file,
    send_from_directory,
)

from backend_v2.aplicacao import cadastro, financeiro, relatorios
from backend_v2.nucleo.erros import ErroDeDominio, RegraDeNegocioViolada
from .comum import corpo, transacional


bp_frontend = Blueprint("frontend_compat_v2", __name__)

RAIZ = Path(__file__).resolve().parents[2]
PASTA_FRONTEND = RAIZ / "frontend"
INDEX_HTML = RAIZ / "backend" / "templates" / "index.html"


def _resposta(dados, status=200):
    resposta = jsonify(dados)
    resposta.headers["X-Adri-Backend"] = "v2"
    return resposta, status


def _cliente_legado(parceiro: dict) -> dict:
    """Nomeia os campos como a tela atual espera, sem mudar o modelo do v2."""
    return {
        "id": parceiro["id"],
        "nome": parceiro["nome"],
        "cep": parceiro.get("cep", ""),
        "rua": parceiro.get("logradouro", ""),
        "bairro": parceiro.get("bairro", ""),
        "cidade": parceiro.get("cidade", ""),
        "entrega_retirada": parceiro.get("entrega_retirada", "Entrega"),
        "observacoes": parceiro.get("observacoes", ""),
        "criado_em": parceiro.get("criado_em", ""),
    }


def _campos_parceiro(dados: dict, existente: dict | None = None) -> dict:
    """Traduz o formulario antigo e preserva campos ERP que ele nao edita."""
    base = dict(existente or {})
    base.update({
        "nome": dados.get("nome", base.get("nome", "")),
        "cep": dados.get("cep", base.get("cep", "")),
        "logradouro": dados.get("rua", dados.get("logradouro", base.get("logradouro", ""))),
        "bairro": dados.get("bairro", base.get("bairro", "")),
        "cidade": dados.get("cidade", base.get("cidade", "")),
        "entrega_retirada": dados.get(
            "entrega_retirada", base.get("entrega_retirada", "Entrega")
        ),
        "observacoes": dados.get("observacoes", base.get("observacoes", "")),
        "e_cliente": True,
        "e_fornecedor": bool(base.get("e_fornecedor", False)),
    })
    campos_permitidos = {
        "nome", "nome_fantasia", "documento", "email", "telefone", "cep",
        "logradouro", "numero", "complemento", "bairro", "cidade", "uf",
        "entrega_retirada", "observacoes", "e_cliente", "e_fornecedor",
    }
    return {chave: base.get(chave, "") for chave in campos_permitidos}


def _linhas_clientes(u, *, busca="", tipo="", cidade="", de="", ate="") -> list[dict]:
    condicoes = ["ativo=1", "e_cliente=1"]
    parametros: list = []
    if busca:
        condicoes.append("(nome LIKE ? OR nome_fantasia LIKE ? OR documento LIKE ?)")
        termo = f"%{busca}%"
        parametros.extend((termo, termo, termo))
    if tipo in ("Entrega", "Retirada"):
        condicoes.append("entrega_retirada=?")
        parametros.append(tipo)
    if cidade:
        condicoes.append("cidade LIKE ?")
        parametros.append(f"%{cidade}%")
    if de:
        condicoes.append("date(criado_em)>=date(?)")
        parametros.append(de)
    if ate:
        condicoes.append("date(criado_em)<=date(?)")
        parametros.append(ate)
    linhas = u.conexao.execute(
        "SELECT * FROM parceiros WHERE " + " AND ".join(condicoes) + " ORDER BY nome",
        parametros,
    ).fetchall()
    return [dict(linha) for linha in linhas]


# ---------------------------------------------------------------------------
# Shell e assets do aplicativo
# ---------------------------------------------------------------------------
@bp_frontend.get("/")
def pagina_inicial():
    html = INDEX_HTML.read_text(encoding="utf-8")
    html = html.replace(
        "<title>Adri Poltronas</title>",
        "<title>Adri Poltronas - ERP v2</title>",
    )
    html = html.replace(
        '<h1 class="sidebar-titulo">Adri Poltronas</h1>',
        '<h1 class="sidebar-titulo">Adri Poltronas '
        '<small style="font-size:.58em;color:#60a5fa">ERP v2</small></h1>',
    )
    return Response(
        html,
        mimetype="text/html",
        headers={"X-Adri-Backend": "v2", "Cache-Control": "no-store"},
    )


@bp_frontend.get("/<path:caminho>")
def asset_frontend(caminho: str):
    return send_from_directory(PASTA_FRONTEND, caminho)


# ---------------------------------------------------------------------------
# Clientes: tela atual -> parceiros do ERP
# ---------------------------------------------------------------------------
@bp_frontend.get("/api/clientes")
@transacional
def listar_clientes(u):
    itens = _linhas_clientes(u, busca=(request.args.get("busca") or "").strip())
    return _resposta([_cliente_legado(item) for item in itens])


@bp_frontend.post("/api/clientes")
@transacional
def criar_cliente(u):
    criado = cadastro.criar(u, _campos_parceiro(corpo()))
    return _resposta({
        "mensagem": "Cliente cadastrado no ERP v2!",
        "id": criado["id"],
        "cliente": _cliente_legado(criado),
    }, 201)


@bp_frontend.put("/api/clientes/<int:identificador>")
@transacional
def atualizar_cliente(u, identificador: int):
    existente = cadastro.obter(u, identificador)
    atualizado = cadastro.atualizar(
        u, identificador, _campos_parceiro(corpo(), existente)
    )
    return _resposta({
        "mensagem": "Cliente atualizado no ERP v2!",
        "cliente": _cliente_legado(atualizado),
    })


@bp_frontend.delete("/api/clientes/<int:identificador>")
@transacional
def excluir_cliente(u, identificador: int):
    cadastro.inativar(u, identificador)
    return _resposta({"mensagem": "Cliente inativado no ERP v2!"})


@bp_frontend.get("/api/clientes/mapa")
@transacional
def clientes_mapa(u):
    itens = _linhas_clientes(u)
    return _resposta([
        {
            **_cliente_legado(item),
            "tipo": item.get("entrega_retirada", "Entrega"),
        }
        for item in itens
        if item.get("cep")
    ])


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@bp_frontend.get("/api/dashboard/dados")
@transacional
def dashboard_dados(u):
    contagens = {
        linha["entrega_retirada"]: int(linha["total"])
        for linha in u.conexao.execute(
            "SELECT entrega_retirada, COUNT(*) total FROM parceiros "
            "WHERE ativo=1 AND e_cliente=1 GROUP BY entrega_retirada"
        ).fetchall()
    }
    por_tipo = {
        "Entrega": contagens.get("Entrega", 0),
        "Retirada": contagens.get("Retirada", 0),
    }
    cidades_linhas = u.conexao.execute(
        "SELECT cidade, COUNT(*) total FROM parceiros "
        "WHERE ativo=1 AND e_cliente=1 AND cidade<>'' "
        "GROUP BY cidade ORDER BY total DESC, cidade LIMIT 10"
    ).fetchall()
    timeline_linhas = u.conexao.execute(
        "SELECT date(criado_em) dia, COUNT(*) total FROM parceiros "
        "WHERE ativo=1 AND e_cliente=1 AND date(criado_em)>=date('now','-29 days') "
        "GROUP BY date(criado_em) ORDER BY dia"
    ).fetchall()
    ultimos = u.conexao.execute(
        "SELECT nome, cidade, entrega_retirada FROM parceiros "
        "WHERE ativo=1 AND e_cliente=1 ORDER BY id DESC LIMIT 5"
    ).fetchall()

    painel = relatorios.painel(u)
    fin = painel["financeiro"]
    comercial = painel["comercial"]
    qtd_vencidos = u.conexao.execute(
        "SELECT COUNT(*) FROM titulos_situacao WHERE natureza='receber' "
        "AND cancelado=0 AND situacao='vencido'"
    ).fetchone()[0]
    recebimentos_mes = u.conexao.execute(
        "SELECT COUNT(*) FROM titulo_baixas b JOIN titulos t ON t.id=b.titulo_id "
        "WHERE b.estornada=0 AND t.natureza='receber' "
        "AND strftime('%Y-%m',b.data_baixa)=strftime('%Y-%m',date('now','localtime'))"
    ).fetchone()[0]
    meses = [dict(linha) for linha in u.conexao.execute(
        "SELECT strftime('%Y-%m',faturado_em) mes, "
        "SUM(total_liquido_centavos) total_centavos FROM documentos_venda "
        "WHERE situacao='faturado' GROUP BY mes ORDER BY mes DESC LIMIT 6"
    ).fetchall()][::-1]
    serie = [
        {"mes": item["mes"], "total": int(item["total_centavos"] or 0) / 100}
        for item in meses
    ]
    faturamento_mes = int(comercial["faturado_mes_centavos"] or 0) / 100
    faturamento_anterior = serie[-2]["total"] if len(serie) >= 2 else 0
    variacao = None
    if faturamento_anterior:
        variacao = round((faturamento_mes - faturamento_anterior) * 100 / faturamento_anterior, 1)
    ticket = faturamento_mes / recebimentos_mes if recebimentos_mes else 0

    return _resposta({
        "por_tipo": por_tipo,
        "cidades": {
            "labels": [linha["cidade"] for linha in cidades_linhas],
            "valores": [int(linha["total"]) for linha in cidades_linhas],
        },
        "timeline": {
            "labels": [linha["dia"] for linha in timeline_linhas],
            "valores": [int(linha["total"]) for linha in timeline_linhas],
        },
        "ultimos_clientes": [
            {"nome": linha["nome"], "cidade": linha["cidade"],
             "tipo": linha["entrega_retirada"]}
            for linha in ultimos
        ],
        "financeiro": {
            "faturamento_mes": faturamento_mes,
            "faturamento_mes_anterior": faturamento_anterior,
            "variacao_percentual": variacao,
            "a_receber": int(fin["a_receber_centavos"] or 0) / 100,
            "em_atraso": int(fin["receber_vencido_centavos"] or 0) / 100,
            "ticket_medio_mes": ticket,
            "qtd_recebimentos_mes": int(recebimentos_mes),
            "qtd_em_atraso": int(qtd_vencidos),
            "serie_mensal": serie,
        },
    })


# ---------------------------------------------------------------------------
# Financeiro: pagamentos da tela -> titulos e baixas do ERP
# ---------------------------------------------------------------------------
_FORMAS_PARA_V2 = {
    "pix": "pix", "boleto": "boleto", "dinheiro": "dinheiro",
    "cartao": "cartao", "transferencia": "transferencia", "outro": "outro",
}
_FORMAS_PARA_TELA = {
    "pix": "Pix", "boleto": "Boleto", "dinheiro": "Dinheiro",
    "cartao": "Cartao", "transferencia": "Transferencia", "cheque": "Outro",
    "outro": "Outro",
}


def _status_tela(situacao: str) -> str:
    return {
        "quitado": "Recebido",
        "cancelado": "Cancelado",
        "vencido": "Atrasado",
        "parcial": "Parcial",
    }.get(situacao, "Pendente")


def _pagamento_legado(titulo: dict) -> dict:
    return {
        "id": titulo["titulo_id"],
        "cliente_id": titulo["parceiro_id"],
        "cliente_nome": titulo.get("parceiro_nome", ""),
        "valor": int(titulo["valor_centavos"]) / 100,
        "descricao": titulo.get("descricao", ""),
        "status": _status_tela(titulo["situacao"]),
        "tipo_pagamento": _FORMAS_PARA_TELA.get(titulo.get("forma_pagamento"), "Outro"),
        "data_vencimento": titulo["data_vencimento"],
        "data_pagamento": titulo.get("ultima_baixa_em", ""),
        "asaas_payment_id": "",
        "pix_payload": "",
        "pix_qr_code": "",
        "boleto_url": "",
        "nosso_numero": "",
    }


def _titulos_receber(u) -> list[dict]:
    linhas = u.conexao.execute(
        "SELECT s.*, t.descricao, t.forma_pagamento, p.nome parceiro_nome, "
        "(SELECT MAX(b.data_baixa) FROM titulo_baixas b "
        " WHERE b.titulo_id=t.id AND b.estornada=0) ultima_baixa_em "
        "FROM titulos_situacao s JOIN titulos t ON t.id=s.titulo_id "
        "JOIN parceiros p ON p.id=s.parceiro_id WHERE s.natureza='receber' "
        "ORDER BY s.data_vencimento DESC, s.titulo_id DESC"
    ).fetchall()
    return [dict(linha) for linha in linhas]


def _conta_interface(u) -> int:
    linhas = u.conexao.execute(
        "SELECT id FROM contas_financeiras WHERE ativo=1 ORDER BY id"
    ).fetchall()
    if len(linhas) == 1:
        return int(linhas[0]["id"])
    if len(linhas) > 1:
        raise RegraDeNegocioViolada(
            "Ha mais de uma conta financeira ativa. Use a API ERP v2 para "
            "informar em qual conta a baixa deve ser lancada."
        )
    return int(financeiro.criar_conta(
        u, {"nome": "Caixa principal", "tipo": "caixa", "saldo_inicial": "0,00"}
    )["id"])


@bp_frontend.get("/api/pagamentos")
@transacional
def listar_pagamentos(u):
    return _resposta([_pagamento_legado(item) for item in _titulos_receber(u)])


@bp_frontend.get("/api/pagamentos/metricas")
@transacional
def metricas_pagamentos(u):
    linhas = _titulos_receber(u)
    recebido = sum(
        int(item["baixado_centavos"]) for item in linhas if not item["cancelado"]
    )
    pendente = sum(
        int(item["saldo_centavos"])
        for item in linhas if item["situacao"] in ("aberto", "parcial")
    )
    atrasado = sum(
        int(item["saldo_centavos"])
        for item in linhas if item["situacao"] == "vencido"
    )
    return _resposta({
        "total_recebido": recebido / 100,
        "total_pendente": pendente / 100,
        "total_atrasado": atrasado / 100,
    })


@bp_frontend.post("/api/pagamentos")
@transacional
def criar_pagamento(u):
    dados = corpo()
    forma = _FORMAS_PARA_V2.get(str(dados.get("tipo_pagamento", "")).lower(), "outro")
    emitidos = financeiro.criar_titulo_avulso(u, {
        "natureza": "receber",
        "parceiro_id": dados.get("cliente_id"),
        "valor": dados.get("valor"),
        "descricao": dados.get("descricao", ""),
        "data_vencimento": dados.get("data_vencimento"),
        "forma_pagamento": forma,
    })
    titulo_id = int(emitidos[0]["id"])
    if dados.get("status") == "Recebido":
        financeiro.baixar(u, titulo_id, {
            "conta_id": _conta_interface(u),
            "valor": dados.get("valor"),
            "data_baixa": dados.get("data_pagamento") or date.today().isoformat(),
            "forma_pagamento": forma,
        })
    return _resposta({"mensagem": "Recebimento registrado no ERP v2!", "id": titulo_id}, 201)


@bp_frontend.post("/api/pagamentos/<int:identificador>/confirmar")
@transacional
def confirmar_pagamento(u, identificador: int):
    titulo = financeiro.obter_titulo(u, identificador)
    if titulo["situacao"] != "quitado":
        financeiro.baixar(u, identificador, {
            "conta_id": _conta_interface(u),
            "valor": int(titulo["saldo_centavos"]) / 100,
            "data_baixa": date.today().isoformat(),
            "forma_pagamento": titulo.get("forma_pagamento", "dinheiro"),
        })
    return _resposta({"mensagem": "Pagamento confirmado no ERP v2!"})


@bp_frontend.delete("/api/pagamentos/<int:identificador>")
@transacional
def cancelar_pagamento(u, identificador: int):
    financeiro.cancelar_titulo(u, identificador, "Cancelado pela interface")
    return _resposta({"mensagem": "Pagamento cancelado no ERP v2!"})


@bp_frontend.post("/api/pagamentos/gerar-cobranca")
def cobranca_nao_disponivel():
    return _resposta({
        "erro": "A integracao Asaas ainda nao foi habilitada no backend ERP v2."
    }, 501)


@bp_frontend.get("/api/pagamentos/<int:identificador>/cobranca-dados")
@transacional
def dados_cobranca(u, identificador: int):
    titulo = financeiro.obter_titulo(u, identificador)
    return _resposta({
        "id": identificador,
        "tipo_pagamento": _FORMAS_PARA_TELA.get(
            titulo.get("forma_pagamento"), "Outro"
        ),
        "valor": int(titulo["valor_centavos"]) / 100,
        "status": _status_tela(titulo["situacao"]),
        "asaas_payment_id": "",
    })


# ---------------------------------------------------------------------------
# Relatorios, mapa e backups usados pela interface
# ---------------------------------------------------------------------------
def _regioes(clientes: list[dict]) -> list[dict]:
    mapa: dict[str, dict] = {}
    for cliente in clientes:
        cidade = cliente.get("cidade") or "Nao informada"
        item = mapa.setdefault(cidade, {
            "cidade": cidade, "total": 0, "entregas": 0, "retiradas": 0,
        })
        item["total"] += 1
        chave = "retiradas" if cliente.get("entrega_retirada") == "Retirada" else "entregas"
        item[chave] += 1
    return sorted(mapa.values(), key=lambda item: (-item["total"], item["cidade"]))


@bp_frontend.get("/api/relatorios")
@transacional
def relatorio_clientes(u):
    itens = _linhas_clientes(
        u,
        tipo=(request.args.get("tipo") or "").strip(),
        cidade=(request.args.get("cidade") or "").strip(),
        de=(request.args.get("data_inicio") or "").strip(),
        ate=(request.args.get("data_fim") or "").strip(),
    )
    clientes = [_cliente_legado(item) for item in itens]
    return _resposta({
        "clientes": clientes,
        "total": len(clientes),
        "regioes": _regioes(clientes),
    })


@bp_frontend.get("/api/relatorios/exportar")
@transacional
def exportar_relatorio(u):
    itens = _linhas_clientes(
        u,
        tipo=(request.args.get("tipo") or "").strip(),
        cidade=(request.args.get("cidade") or "").strip(),
        de=(request.args.get("data_inicio") or "").strip(),
        ate=(request.args.get("data_fim") or "").strip(),
    )
    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow([
        "Nome", "CEP", "Rua", "Bairro", "Cidade", "Entrega/Retirada",
        "Observacoes", "Criado em",
    ])
    for item in itens:
        cliente = _cliente_legado(item)
        escritor.writerow([
            cliente["nome"], cliente["cep"], cliente["rua"], cliente["bairro"],
            cliente["cidade"], cliente["entrega_retirada"],
            cliente["observacoes"], cliente["criado_em"],
        ])
    dados = io.BytesIO(buffer.getvalue().encode("utf-8-sig"))
    return send_file(
        dados,
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=f"relatorio_erp_v2_{time.strftime('%Y%m%d_%H%M%S')}.csv",
    )


@bp_frontend.get("/api/backup/json")
@transacional
def backup_json(u):
    clientes = [_cliente_legado(item) for item in _linhas_clientes(u)]
    dados = io.BytesIO(json.dumps({
        "versao": "2.0",
        "data_exportacao": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "clientes": clientes,
    }, ensure_ascii=False, indent=2).encode("utf-8"))
    return send_file(
        dados, mimetype="application/json", as_attachment=True,
        download_name=f"backup_erp_v2_{time.strftime('%Y%m%d_%H%M%S')}.json",
    )


@bp_frontend.get("/api/backup/sqlite")
def backup_sqlite():
    origem = current_app.config["CAMINHO_BANCO"]
    temporario = tempfile.NamedTemporaryFile(
        prefix="adri_erp_v2_", suffix=".db", delete=False
    )
    temporario.close()
    fonte = sqlite3.connect(origem)
    destino = sqlite3.connect(temporario.name)
    try:
        fonte.backup(destino)
    finally:
        destino.close()
        fonte.close()

    @after_this_request
    def _limpar(resposta):
        try:
            os.unlink(temporario.name)
        except OSError:
            pass
        return resposta

    return send_file(
        temporario.name, mimetype="application/x-sqlite3", as_attachment=True,
        download_name=f"adri_poltronas_v2_{time.strftime('%Y%m%d_%H%M%S')}.db",
    )


@bp_frontend.post("/api/clientes/importar")
@transacional
def importar_clientes(u):
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        return _resposta({"erro": "Nenhum arquivo enviado."}, 400)
    nome = arquivo.filename.lower()
    try:
        if nome.endswith(".json"):
            bruto = json.loads(arquivo.read().decode("utf-8-sig"))
            registros = bruto if isinstance(bruto, list) else bruto.get("clientes", [])
        elif nome.endswith(".csv"):
            texto = arquivo.read().decode("utf-8-sig")
            registros = list(csv.DictReader(io.StringIO(texto)))
        else:
            return _resposta({
                "erro": "No ERP v2, importe CSV ou JSON. XLSX ainda nao e suportado."
            }, 415)
    except (UnicodeError, ValueError, csv.Error):
        return _resposta({"erro": "Nao foi possivel ler o arquivo enviado."}, 400)

    sucessos = duplicados = erros = 0
    for registro in registros[:5000]:
        try:
            cadastro.criar(u, _campos_parceiro(registro))
            sucessos += 1
        except ErroDeDominio as erro:
            if erro.status_http == 409:
                duplicados += 1
            else:
                erros += 1
    return _resposta({
        "mensagem": "Importacao concluida no ERP v2!",
        "sucessos": sucessos, "duplicados": duplicados, "erros": erros,
        "total": len(registros),
    })


# Recursos do shell antigo que ainda nao pertencem ao dominio v2.
@bp_frontend.get("/api/notificacoes")
def notificacoes_vazias():
    return _resposta({"notificacoes": [], "nao_lidas": 0})


@bp_frontend.route("/api/notificacoes/lidas", methods=["POST", "DELETE"])
def notificacoes_lidas():
    return _resposta({"mensagem": "Nenhuma notificacao pendente."})


@bp_frontend.get("/api/auth/status")
def auth_status():
    return _resposta({"logado": False, "conta": ""})


@bp_frontend.route("/api/auth/login", methods=["GET", "POST"])
@bp_frontend.post("/api/auth/logout")
@bp_frontend.post("/api/excel/enviar")
@bp_frontend.post("/api/ia/sugestao-bairro")
def integracao_nao_disponivel():
    return _resposta({
        "erro": "Esta integracao ainda nao foi habilitada no backend ERP v2."
    }, 501)
