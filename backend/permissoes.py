"""Sistema de permissoes baseado em roles.

Administrador e usuario/cliente acessam todas as areas comuns. Somente o
desenvolvedor administra contas e configura o periodo de teste.
"""

from functools import wraps
from flask import jsonify, g, current_app
from erp.core.contexto import obter_contexto


# Definicao de permissoes por role
# True = permitido, False = negado, None = nao aplicavel
PERMISSOES = {
    # Configuracoes e sistema
    "config.licenca.gerenciar": {
        "desenvolvedor": True,
        "administrador": False,
        "usuario": False,
    },
    "config.sistema.gerenciar": {
        "desenvolvedor": True,
        "administrador": False,
        "usuario": False,
    },
    "config.backup.restaurar": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": False,
    },
    "config.integracao.microsoft": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": False,
    },
    # Clientes
    "clientes.criar": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": True,
    },
    "clientes.editar": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": True,
    },
    "clientes.excluir": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": False,
    },
    "clientes.importar": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": False,
    },
    "clientes.exportar": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": False,
    },
    "clientes.ver_todos": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": True,
    },
    # Produtos (catalogo)
    "produtos.criar": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": False,
    },
    "produtos.editar": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": False,
    },
    "produtos.excluir": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": False,
    },
    "produtos.ver": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": True,
    },
    # Pedidos
    "pedidos.criar": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": True,
    },
    "pedidos.editar": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": True,
    },
    "pedidos.excluir": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": False,
    },
    "pedidos.faturar": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": True,
    },
    "pedidos.cancelar": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": False,
    },
    "pedidos.ver_todos": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": True,
    },
    # Entregas
    "entregas.criar": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": True,
    },
    "entregas.editar": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": True,
    },
    "entregas.excluir": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": False,
    },
    "entregas.ver_todas": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": True,
    },
    # Financeiro / Parcelas
    "financeiro.parcelas.baixar": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": True,
    },
    "financeiro.parcelas.cancelar": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": False,
    },
    "financeiro.relatorios": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": False,
    },
    # Dashboard e metricas
    "dashboard.ver": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": True,
    },
    # Mapa
    "mapa.ver": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": True,
    },
    # Notificacoes
    "notificacoes.ver": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": True,
    },
    "notificacoes.gerenciar": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": True,
    },
    # Auditoria
    "auditoria.ver": {
        "desenvolvedor": True,
        "administrador": True,
        "usuario": False,
    },
}

# As funções do ERP são liberadas para usuário/cliente e administrador. O
# controle de licenças e do acesso das contas continua exclusivo do desenvolvedor.
for _regras in PERMISSOES.values():
    _regras["administrador"] = True
    _regras["usuario"] = True
PERMISSOES["config.licenca.gerenciar"]["administrador"] = False
PERMISSOES["config.licenca.gerenciar"]["usuario"] = False
PERMISSOES["config.sistema.gerenciar"]["administrador"] = False
PERMISSOES["config.sistema.gerenciar"]["usuario"] = False


def obter_role_atual() -> str:
    """Retorna o role do usuario autenticado na requisicao atual."""
    contexto = obter_contexto()
    return contexto.usuario_role or "usuario"


def tem_permissao(permissao: str, role: str | None = None) -> bool:
    """Verifica se o role tem a permissao."""
    if role is None:
        role = obter_role_atual()
    regras = PERMISSOES.get(permissao)
    if regras is None:
        # Permissao nao definida: nega por seguranca (deny by default)
        return False
    return bool(regras.get(role, False))


def exigir_permissao(permissao: str):
    """Decorator para exigir uma permissao especifica na rota."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if current_app.config.get('TESTING'):
                return f(*args, **kwargs)
            role = getattr(g, 'erp_usuario_role', None) or obter_role_atual()
            if not tem_permissao(permissao, role):
                return jsonify({
                    "erro": "Acesso negado. Permissao insuficiente.",
                    "codigo": "permissao_insuficiente",
                    "permissao_requerida": permissao,
                }), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


def role_necessario(*roles_permitidos: str):
    """Decorator para exigir um dos roles especificados."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if current_app.config.get('TESTING'):
                return f(*args, **kwargs)
            role = getattr(g, 'erp_usuario_role', None) or obter_role_atual()
            if role not in roles_permitidos:
                return jsonify({
                    "erro": "Acesso negado. Role insuficiente.",
                    "codigo": "role_insuficiente",
                    "roles_permitidos": list(roles_permitidos),
                }), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


def desenvolvedor_necessario(f):
    """Decorator: so desenvolvedor pode acessar."""
    return role_necessario("desenvolvedor")(f)


def administrador_ou_desenvolvedor(f):
    """Decorator: administrador ou desenvolvedor podem acessar."""
    return role_necessario("administrador", "desenvolvedor")(f)


def usuario_autenticado(f):
    """Decorator: qualquer usuario autenticado (ja verificado pelo auth middleware)."""
    return f
