# backend/blueprints/__init__.py
"""Pacote de blueprints Flask."""
from .auth import auth_bp
from .auth_local import auth_local_bp
from .clientes import clientes_bp
from .ia import ia_bp
from .entregas import entregas_bp
from .dashboard import dashboard_bp
from .notificacoes import notificacoes_bp
from .excel import excel_bp
from .comercial import produtos_bp, pedidos_bp
from .backup import backup_bp
from .licenca_bp import licenca_bp

__all__ = [
    'auth_bp',
    'auth_local_bp',
    'clientes_bp',
    'ia_bp',
    'entregas_bp',
    'dashboard_bp',
    'notificacoes_bp',
    'excel_bp',
    'produtos_bp',
    'pedidos_bp',
    'backup_bp',
    'licenca_bp',
]