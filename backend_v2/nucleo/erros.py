"""
Erros de dominio.

Cada um carrega o status HTTP que lhe corresponde. A alternativa -- servico
devolvendo tuplas (ok, mensagem) e cada rota decidindo o status -- foi o que
produziu, no v1, o mesmo caso (cliente inexistente) respondendo 404 em
/api/entregas e 500 em /api/pagamentos.
"""
from __future__ import annotations


class ErroDeDominio(Exception):
    """Raiz de tudo que e falha esperada de negocio."""
    status_http = 400
    codigo = "erro_de_dominio"

    def __init__(self, mensagem: str, detalhes=None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.detalhes = detalhes or []

    def como_dict(self) -> dict:
        corpo = {"erro": self.mensagem, "codigo": self.codigo}
        if self.detalhes:
            corpo["detalhes"] = self.detalhes
        return corpo


class DadosInvalidos(ErroDeDominio):
    status_http = 400
    codigo = "dados_invalidos"


class NaoEncontrado(ErroDeDominio):
    status_http = 404
    codigo = "nao_encontrado"

    def __init__(self, entidade: str, identificador=None):
        alvo = "%s %s" % (entidade, identificador) if identificador is not None else entidade
        super().__init__("%s nao encontrado(a)." % alvo)
        self.entidade = entidade


class ConflitoDeEstado(ErroDeDominio):
    """
    A operacao e valida em abstrato, mas nao no estado atual do registro.

    Ex.: faturar um pedido ja cancelado, dar baixa num titulo ja quitado.
    409 e o status certo: o pedido nao esta malformado, o mundo e que mudou.
    """
    status_http = 409
    codigo = "conflito_de_estado"


class RegraDeNegocioViolada(ErroDeDominio):
    """
    Ex.: retirar 10 unidades de um item com saldo 3.

    422 separa isto de 400: a sintaxe estava certa, a regra e que barrou.
    """
    status_http = 422
    codigo = "regra_violada"


class ServicoExternoIndisponivel(ErroDeDominio):
    status_http = 502
    codigo = "servico_externo"
