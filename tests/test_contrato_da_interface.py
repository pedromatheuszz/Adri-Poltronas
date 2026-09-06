"""
A interface nao pode mandar o operador para um lugar que nao existe.

Este arquivo nasceu de um defeito real. A 1.5.0 removeu as abas Pagamentos e
Relatorios -- decisao deliberada, registrada no CHANGELOG. O que ninguem
percebeu e que dois textos da tela de faturamento continuavam dizendo
"na aba Pagamentos" e "em Pagamentos". O operador faturava, lia que as parcelas
estavam na aba Pagamentos, e procurava por uma aba que nao existia mais.

Nenhum teste podia pegar isso: o backend estava certo, o frontend estava certo,
e o que estava errado era a FRASE. E o tipo de defeito que so aparece quando
alguem usa o sistema -- ou quando um teste le a interface como texto.

Sao testes estaticos de proposito. Nao sobem o Flask nem abrem navegador: leem
os arquivos e conferem que o que a interface promete existe. Custam
milissegundos e cobrem a classe inteira de defeito, que e o que os torna
valiosos num projeto que REMOVE escopo com alguma frequencia.
"""
import os
import re

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
INDEX = os.path.join(RAIZ, 'backend', 'templates', 'index.html')
PASTA_JS = os.path.join(RAIZ, 'frontend', 'js')


def _ler(caminho: str) -> str:
    with open(caminho, encoding='utf-8') as arquivo:
        return arquivo.read()


def _fontes_da_interface() -> dict:
    """index.html mais todo o JS do frontend, por caminho."""
    fontes = {'backend/templates/index.html': _ler(INDEX)}
    for nome in sorted(os.listdir(PASTA_JS)):
        if nome.endswith('.js'):
            fontes[f'frontend/js/{nome}'] = _ler(os.path.join(PASTA_JS, nome))
    return fontes


def _abas_existentes() -> set:
    """
    As abas de verdade, lidas dos paineis `id="aba-<nome>"`.

    Deriva do HTML e nao de uma lista escrita aqui: uma lista escrita aqui
    precisaria ser atualizada junto com o HTML, e e exatamente esse tipo de
    atualizacao esquecida que o teste existe para pegar.
    """
    return set(re.findall(r'id="aba-([a-z]+)"', _ler(INDEX)))


def test_index_declara_as_abas_esperadas():
    """Guarda de sanidade: se este falhar, os outros testes leem lixo."""
    assert _abas_existentes() == {
        'dashboard', 'pedidos', 'clientes', 'produtos', 'entregas', 'mapa'}


def test_nenhum_texto_manda_o_operador_para_aba_inexistente():
    """
    O defeito original, em forma de teste.

    Procura por "aba <Nome>" em qualquer texto da interface e exige que <Nome>
    seja uma aba que existe.
    """
    abas = _abas_existentes()
    orfas = []

    for caminho, fonte in _fontes_da_interface().items():
        for encontrado in re.finditer(r'\baba\s+([A-Z][a-zA-Z]+)', fonte):
            nome = encontrado.group(1).lower()
            if nome not in abas:
                linha = fonte[:encontrado.start()].count('\n') + 1
                orfas.append(f"{caminho}:{linha} cita a aba '{encontrado.group(1)}'")

    assert not orfas, (
        "A interface manda o operador para abas que nao existem:\n  "
        + "\n  ".join(orfas)
    )


def test_nenhuma_aba_da_navegacao_ficou_sem_painel():
    """
    O inverso: um botao de navegacao apontando para um painel removido levaria
    a uma tela em branco.
    """
    html = _ler(INDEX)
    destinos = set(re.findall(r'data-comando="trocarAba" data-arg="([a-z]+)"', html))
    faltando = destinos - _abas_existentes()

    assert not faltando, f"botoes de navegacao sem painel correspondente: {faltando}"


def test_toda_acao_declarativa_do_html_existe_no_javascript():
    """
    A CSP nao permite `onclick=`, entao a tela liga botao a funcao por
    `data-comando`. O preco disso e que um nome errado falha em SILENCIO: o
    clique nao faz nada e nenhum erro aparece.
    """
    fontes = _fontes_da_interface()
    js = "\n".join(v for k, v in fontes.items() if k.endswith('.js'))
    html = fontes['backend/templates/index.html']

    # `trocarAba` e coberto pelo teste acima; aqui interessam as demais.
    comandos = set(re.findall(r'data-comando="([A-Za-z_$][\w$]*)"', html))
    ausentes = {
        nome for nome in comandos
        if not re.search(rf'(?:function\s+{re.escape(nome)}\s*\(|'
                         rf'\b{re.escape(nome)}\s*[:=]\s*(?:async\s+)?function|'
                         rf'\b{re.escape(nome)}\s*[:=]\s*(?:async\s+)?\()', js)
    }

    assert not ausentes, (
        f"data-comando sem funcao correspondente no JS (o clique nao faz nada): {ausentes}"
    )


def test_as_parcelas_do_faturamento_tem_onde_ser_mostradas():
    """
    A regressao especifica do BUG-02.

    Faturar grava dinheiro a receber. Se o bloco que exibe as parcelas sumir do
    HTML, ou o render sumir do JS, o pedido volta a ser terminal com o valor
    invisivel -- e nenhum teste de backend notaria, porque o backend continuaria
    devolvendo as parcelas certinhas.
    """
    html = _ler(INDEX)
    js = _ler(os.path.join(PASTA_JS, 'comercial.js'))

    assert 'id="pedidoBlocoParcelas"' in html
    assert 'id="tabelaParcelasPedido"' in html
    assert '_renderizarParcelas' in js
    # E precisa haver como dar baixa: so exibir devolveria metade do ciclo.
    assert '/parcelas/' in js
