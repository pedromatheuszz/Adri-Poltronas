# backend/blueprints/auth_local.py
"""Blueprint de autenticação local (username/senha)."""
import logging
import hmac
import sqlite3
from flask import Blueprint, jsonify, request

import database
import licenca
import security
from limites import limiter

log = logging.getLogger("adri.auth_local")

auth_local_bp = Blueprint('auth_local', __name__, url_prefix='/api/auth/local')
DURACAO_SESSAO_LOCAL_SEGUNDOS = 60 * 60 * 24 * 30
TAMANHO_MAXIMO_EMAIL = 254


def _dados_json() -> dict | None:
    dados = request.get_json(silent=True)
    return dados if isinstance(dados, dict) else None


def _texto(dados: dict, campo: str, padrao: str = '') -> str | None:
    valor = dados.get(campo, padrao)
    return valor if isinstance(valor, str) else None


def _senha_forte(senha: str) -> bool:
    return (
        isinstance(senha, str)
        and len(senha) >= database.TAMANHO_MINIMO_SENHA
        and len(senha.encode('utf-8')) <= database.TAMANHO_MAXIMO_SENHA_BYTES
    )


def _email_valido(email: str) -> bool:
    return isinstance(email, str) and len(email) <= TAMANHO_MAXIMO_EMAIL


def _sessao_local_valida() -> dict | None:
    """Exige o token de sessão guardado em cookie HttpOnly e no banco."""
    sessao = database.obter_sessao_local()
    cookie = request.cookies.get(database.NOME_COOKIE_SESSAO_LOCAL, '')
    token = (sessao or {}).get('token', '')
    if cookie and token and hmac.compare_digest(cookie, token):
        usuario = database.obter_usuario_por_id(sessao['user_id'])
        if usuario and usuario['ativo']:
            return sessao
        database.excluir_sessao_local()
    return None


def _resposta_com_sessao(payload: dict, status: int, token: str):
    resposta = jsonify(payload)
    resposta.set_cookie(
        database.NOME_COOKIE_SESSAO_LOCAL,
        token,
        max_age=DURACAO_SESSAO_LOCAL_SEGUNDOS,
        httponly=True,
        samesite='Strict',
        secure=False,  # O servidor local usa HTTP em loopback.
        path='/',
    )
    return resposta, status


def _desenvolvedor_autenticado() -> bool:
    sessao = _sessao_local_valida()
    if not sessao:
        return False
    usuario = database.obter_usuario_por_id(sessao['user_id'])
    return bool(usuario and usuario['ativo'] and usuario['role'] == 'desenvolvedor')


@auth_local_bp.route('/login', methods=['POST'])
@limiter.limit('5 per minute')
def local_login():
    """Login com username e senha local."""
    dados = _dados_json()
    if dados is None:
        return jsonify({"erro": "Informe usuário e senha."}), 400
    username_recebido = _texto(dados, 'username')
    senha = _texto(dados, 'senha')
    if username_recebido is None or senha is None:
        return jsonify({"erro": "Usuário e senha devem ser texto."}), 400
    username = username_recebido.strip()

    if not username or not senha:
        return jsonify({"erro": "Usuário e senha são obrigatórios."}), 400
    if len(username) > 80:
        return jsonify({"erro": "O nome de usuário deve ter até 80 caracteres."}), 400

    usuario = database.autenticar_usuario_local(username, senha)
    if not usuario:
        log.warning("[AUTH_LOCAL] Falha de autenticação local.")
        return jsonify({"erro": "Usuário ou senha inválidos."}), 401

    # Cria sessão local (usa a mesma tabela sessao, mas com tipo 'local')
    token_local = security.gerar_token_seguro(32)
    database.salvar_sessao_local(token_local, usuario['id'], usuario['username'], usuario['role'])

    log.info("[AUTH_LOCAL] Login local realizado (role: %s).", usuario['role'])
    return _resposta_com_sessao({
        "mensagem": "Login realizado com sucesso.",
        "usuario": {
            "id": usuario['id'],
            "username": usuario['username'],
            "email": usuario['email'],
            "role": usuario['role']
        },
        "senha_precisa_ser_atualizada": len(senha) < database.TAMANHO_MINIMO_SENHA,
    }, 200, token_local)


@auth_local_bp.route('/status', methods=['GET'])
def local_status():
    """Verifica se existem usuários cadastrados no sistema."""
    tem_usuarios = database.existe_algum_usuario()
    tem_desenvolvedor = database.existe_desenvolvedor()
    return jsonify({
        "tem_usuarios": tem_usuarios,
        "tem_desenvolvedor": tem_desenvolvedor,
        "setup_required": not tem_usuarios and not tem_desenvolvedor,
    }), 200


@auth_local_bp.route('/setup', methods=['POST'])
@limiter.limit('3 per hour')
def local_configurar_desenvolvedor_inicial():
    """Cria a conta proprietária somente no primeiro acesso à instalação."""
    dados = _dados_json()
    if dados is None:
        return jsonify({"erro": "Informe os dados da conta."}), 400
    username_recebido = _texto(dados, 'username')
    senha = _texto(dados, 'senha')
    email_recebido = _texto(dados, 'email')
    if username_recebido is None or senha is None or email_recebido is None:
        return jsonify({"erro": "Os campos devem ser texto."}), 400
    username = username_recebido.strip()
    email = email_recebido.strip()

    if not username or not senha:
        return jsonify({"erro": "Usuário e senha são obrigatórios."}), 400
    if len(username) > 80:
        return jsonify({"erro": "O nome de usuário deve ter até 80 caracteres."}), 400
    if not _senha_forte(senha):
        return jsonify({"erro": "Use uma senha com pelo menos 12 caracteres e até 72 bytes em UTF-8."}), 400
    if not _email_valido(email):
        return jsonify({"erro": "O e-mail deve ter até 254 caracteres."}), 400

    try:
        user_id = database.criar_desenvolvedor_inicial(username, senha, email)
    except sqlite3.IntegrityError:
        return jsonify({"erro": "Não foi possível criar a conta inicial."}), 409
    if not user_id:
        return jsonify({"erro": "A configuração inicial já foi concluída."}), 409

    usuario = database.obter_usuario_por_id(user_id)
    token_local = security.gerar_token_seguro(32)
    database.salvar_sessao_local(token_local, user_id, usuario['username'], usuario['role'])
    log.info("[AUTH_LOCAL] Conta de desenvolvedor inicial configurada.")
    return _resposta_com_sessao({
        "mensagem": "Conta de desenvolvedor criada com sucesso.",
        "usuario": {
            "id": usuario['id'],
            "username": usuario['username'],
            "email": usuario['email'],
            "role": usuario['role'],
        },
        "logado": True,
    }, 201, token_local)


@auth_local_bp.route('/register', methods=['POST'])
@limiter.limit('5 per hour')
def local_register():
    """Permite autocadastro de usuario e cadastro gerenciado pelo desenvolvedor."""
    dados = _dados_json()
    if dados is None:
        return jsonify({"erro": "Informe os dados da conta."}), 400
    username_recebido = _texto(dados, 'username')
    senha = _texto(dados, 'senha')
    email_recebido = _texto(dados, 'email')
    role_recebido = _texto(dados, 'role', 'usuario')
    if any(valor is None for valor in (username_recebido, senha, email_recebido, role_recebido)):
        return jsonify({"erro": "Os campos devem ser texto."}), 400
    username = username_recebido.strip()
    email = email_recebido.strip()
    role = role_recebido.strip()

    if not username or not senha:
        return jsonify({"erro": "Usuário e senha são obrigatórios."}), 400
    if len(username) > 80:
        return jsonify({"erro": "O nome de usuário deve ter até 80 caracteres."}), 400
    if not _senha_forte(senha):
        return jsonify({"erro": "Use uma senha com pelo menos 12 caracteres e até 72 bytes em UTF-8."}), 400
    if not _email_valido(email):
        return jsonify({"erro": "O e-mail deve ter até 254 caracteres."}), 400
    if not database.existe_desenvolvedor():
        return jsonify({"erro": "Configure a conta de desenvolvedor antes de criar usuários."}), 409
    if role not in ('desenvolvedor', 'administrador', 'usuario'):
        return jsonify({"erro": "Role inválida."}), 400

    # Verifica se username já existe
    existente = database.obter_usuario_por_username(username)
    if existente:
        return jsonify({"erro": "Nome de usuário já existe."}), 409

    # Rota publica da tela de login: jamais cria perfis administrativos, mesmo
    # que uma sessao de desenvolvedor esteja aberta na mesma instalacao.
    if role != 'usuario':
        return jsonify({"erro": "O cadastro público cria apenas contas de usuário."}), 403
    try:
        user_id = database.criar_usuario(username, senha, role, email)
        token_local = security.gerar_token_seguro(32)
        database.salvar_sessao_local(token_local, user_id, username, role)

        log.info("[AUTH_LOCAL] Usuário criado por autocadastro.")
        return _resposta_com_sessao({
            "mensagem": "Usuário criado com sucesso. Sessão iniciada.",
            "id": user_id,
            "usuario": {
                "id": user_id,
                "username": username,
                "email": email,
                "role": role
            },
            "logado": True
        }, 201, token_local)
    except sqlite3.IntegrityError:
        return jsonify({"erro": "Nome de usuário já existe."}), 409
    except Exception as e:
        log.exception("[AUTH_LOCAL] Erro ao criar usuário: %s", e)
        return jsonify({"erro": "Não foi possível criar o usuário."}), 500


@auth_local_bp.route('/logout', methods=['POST'])
def local_logout():
    """Logout da sessão local."""
    if not _sessao_local_valida():
        return jsonify({"erro": "Não autenticado."}), 401
    database.excluir_sessao_local()
    resposta = jsonify({"mensagem": "Sessão local encerrada."})
    resposta.set_cookie(
        database.NOME_COOKIE_SESSAO_LOCAL, '', max_age=0,
        httponly=True, samesite='Strict', secure=False, path='/',
    )
    return resposta, 200


@auth_local_bp.route('/me', methods=['GET'])
def local_me():
    """Retorna info do usuário logado localmente."""
    sessao = _sessao_local_valida()
    if not sessao:
        return jsonify({"logado": False}), 401

    usuario = database.obter_usuario_por_id(sessao['user_id'])
    if not usuario or not usuario['ativo']:
        database.excluir_sessao_local()
        return jsonify({"logado": False, "motivo": "usuario_inativo"}), 401

    return jsonify({
        "logado": True,
        "usuario": {
            "id": usuario['id'],
            "username": usuario['username'],
            "email": usuario['email'],
            "role": usuario['role']
        }
    }), 200


@auth_local_bp.route('/alterar-senha', methods=['POST'])
@limiter.limit('5 per minute')
def local_alterar_senha():
    """Altera senha do usuário logado."""
    sessao = _sessao_local_valida()
    if not sessao:
        return jsonify({"erro": "Não autenticado."}), 401

    dados = _dados_json()
    if dados is None:
        return jsonify({"erro": "Informe a senha atual e a nova senha."}), 400
    senha_atual = _texto(dados, 'senha_atual')
    nova_senha = _texto(dados, 'nova_senha')
    if senha_atual is None or nova_senha is None:
        return jsonify({"erro": "As senhas devem ser texto."}), 400

    if not senha_atual or not nova_senha:
        return jsonify({"erro": "Senha atual e nova senha são obrigatórias."}), 400
    if not _senha_forte(nova_senha):
        return jsonify({"erro": "Use uma nova senha com pelo menos 12 caracteres e até 72 bytes em UTF-8."}), 400

    ok = database.alterar_senha(sessao['user_id'], senha_atual, nova_senha)
    if not ok:
        return jsonify({"erro": "Senha atual incorreta."}), 400

    usuario = database.obter_usuario_por_id(sessao['user_id'])
    token_local = security.gerar_token_seguro(32)
    database.salvar_sessao_local(
        token_local, sessao['user_id'], usuario['username'], usuario['role']
    )
    return _resposta_com_sessao({"mensagem": "Senha alterada com sucesso."}, 200, token_local)


@auth_local_bp.route('/usuarios', methods=['POST'])
@limiter.limit('10 per hour')
def local_criar_usuario_desenvolvedor():
    """Cria uma conta pelo painel sem encerrar a sessão de desenvolvedor."""
    if not _desenvolvedor_autenticado():
        return jsonify({"erro": "Apenas o desenvolvedor pode cadastrar contas."}), 403

    dados = _dados_json()
    if dados is None:
        return jsonify({"erro": "Informe os dados da conta."}), 400
    username_recebido = _texto(dados, 'username')
    senha = _texto(dados, 'senha')
    email_recebido = _texto(dados, 'email')
    role_recebido = _texto(dados, 'role', 'usuario')
    if any(valor is None for valor in (username_recebido, senha, email_recebido, role_recebido)):
        return jsonify({"erro": "Os campos devem ser texto."}), 400
    username = username_recebido.strip()
    email = email_recebido.strip()
    role = role_recebido.strip()
    if not username or not senha:
        return jsonify({"erro": "Usuário e senha são obrigatórios."}), 400
    if len(username) > 80:
        return jsonify({"erro": "O nome de usuário deve ter até 80 caracteres."}), 400
    if not _senha_forte(senha):
        return jsonify({"erro": "Use uma senha com pelo menos 12 caracteres e até 72 bytes em UTF-8."}), 400
    if not _email_valido(email):
        return jsonify({"erro": "O e-mail deve ter até 254 caracteres."}), 400
    if role not in ('usuario', 'administrador'):
        return jsonify({"erro": "Perfil inválido."}), 400
    if database.obter_usuario_por_username(username):
        return jsonify({"erro": "Nome de usuário já existe."}), 409
    try:
        user_id = database.criar_usuario(username, senha, role, email)
    except sqlite3.IntegrityError:
        return jsonify({"erro": "Nome de usuário já existe."}), 409
    log.info("[AUTH_LOCAL] Conta criada pelo desenvolvedor (role: %s).", role)
    return jsonify({
        "mensagem": "Usuário criado com sucesso.",
        "id": user_id,
        "usuario": {"id": user_id, "username": username, "email": email, "role": role},
        "logado": False,
    }), 201


@auth_local_bp.route('/usuarios', methods=['GET'])
def local_listar_usuarios():
    """Lista usuários (apenas desenvolvedor)."""
    if not _desenvolvedor_autenticado():
        return jsonify({"erro": "Acesso negado.", "codigo": "role_insuficiente"}), 403

    usuarios = database.listar_usuarios(apenas_ativos=False)
    for usuario in usuarios:
        usuario['teste'] = licenca.situacao_usuario(usuario['id'])
    return jsonify(usuarios), 200


@auth_local_bp.route('/usuarios/<int:user_id>/teste', methods=['POST'])
@limiter.limit('30 per minute')
def local_controlar_teste_usuario(user_id):
    """Altera o período de teste de uma conta, somente para o desenvolvedor."""
    if not _desenvolvedor_autenticado():
        return jsonify({"erro": "Acesso negado."}), 403
    usuario = database.obter_usuario_por_id(user_id)
    if not usuario:
        return jsonify({"erro": "Usuário não encontrado."}), 404
    if usuario['role'] == 'desenvolvedor':
        return jsonify({"erro": "A conta de desenvolvedor não usa período de teste."}), 400
    dados = _dados_json()
    if dados is None:
        return jsonify({"erro": "Informe a ação."}), 400
    acao = _texto(dados, 'acao')
    if acao is None:
        return jsonify({"erro": "Ação inválida."}), 400
    try:
        situacao = licenca.controlar_teste_usuario(user_id, acao.strip())
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400
    if situacao is None:
        return jsonify({"erro": "Não foi possível atualizar o período de teste."}), 404
    return jsonify({"mensagem": "Período de teste atualizado.", "teste": situacao}), 200


@auth_local_bp.route('/usuarios/<int:user_id>', methods=['PUT'])
@limiter.limit('30 per minute')
def local_atualizar_usuario(user_id):
    """Atualiza usuário (apenas desenvolvedor)."""
    if not _desenvolvedor_autenticado():
        return jsonify({"erro": "Acesso negado."}), 403

    dados = _dados_json()
    if dados is None:
        return jsonify({"erro": "Informe os campos para atualizar."}), 400
    sessao = database.obter_sessao_local()
    if sessao and sessao['user_id'] == user_id and ('username' in dados or dados.get('senha')):
        return jsonify({"erro": "As credenciais da conta de desenvolvedor são protegidas."}), 400
    if sessao and sessao['user_id'] == user_id and (dados.get('role') not in (None, 'desenvolvedor') or dados.get('ativo') is False):
        return jsonify({"erro": "Não é possível remover seu próprio acesso de desenvolvedor."}), 400
    campos = {}
    if 'username' in dados:
        username_recebido = _texto(dados, 'username')
        if username_recebido is None:
            return jsonify({"erro": "O nome de usuário deve ser texto."}), 400
        username = username_recebido.strip()
        if not username:
            return jsonify({"erro": "O nome de usuário é obrigatório."}), 400
        if len(username) > 80:
            return jsonify({"erro": "O nome de usuário deve ter até 80 caracteres."}), 400
        campos['username'] = username
    if 'email' in dados:
        email = _texto(dados, 'email')
        if email is None or not _email_valido(email):
            return jsonify({"erro": "O e-mail deve ter até 254 caracteres."}), 400
        campos['email'] = email.strip()
    if 'role' in dados:
        role = _texto(dados, 'role')
        if role not in ('desenvolvedor', 'administrador', 'usuario'):
            return jsonify({"erro": "Role inválida."}), 400
        atual = database.obter_usuario_por_id(user_id)
        if role == 'desenvolvedor' and atual and atual['role'] != 'desenvolvedor':
            return jsonify({"erro": "Já existe uma conta de desenvolvedor protegida."}), 409
        campos['role'] = role
    if 'ativo' in dados:
        if not isinstance(dados['ativo'], bool):
            return jsonify({"erro": "O campo de acesso deve ser verdadeiro ou falso."}), 400
        campos['ativo'] = 1 if dados['ativo'] else 0
    if dados.get('senha'):
        senha = _texto(dados, 'senha')
        if senha is None or not _senha_forte(senha):
            return jsonify({"erro": "Use uma senha com pelo menos 12 caracteres e até 72 bytes em UTF-8."}), 400
        campos['senha'] = senha

    if not campos:
        return jsonify({"erro": "Nenhum campo para atualizar."}), 400

    try:
        ok = database.atualizar_usuario_local(user_id, **campos)
    except sqlite3.IntegrityError:
        return jsonify({"erro": "Já existe uma conta com esse nome de usuário."}), 409
    if not ok:
        return jsonify({"erro": "Usuário não encontrado."}), 404

    return jsonify({"mensagem": "Usuário atualizado."}), 200


@auth_local_bp.route('/usuarios/<int:user_id>', methods=['DELETE'])
@limiter.limit('30 per hour')
def local_excluir_usuario(user_id):
    """Inativa usuário (apenas desenvolvedor)."""
    if not _desenvolvedor_autenticado():
        return jsonify({"erro": "Acesso negado."}), 403

    # Impede auto-exclusão
    sessao = database.obter_sessao_local()
    if sessao and sessao['user_id'] == user_id:
        return jsonify({"erro": "Não pode excluir a si mesmo."}), 400

    usuario = database.obter_usuario_por_id(user_id)
    if usuario and usuario['role'] == 'desenvolvedor':
        return jsonify({"erro": "A conta de desenvolvedor não pode ser excluída."}), 400

    ok = database.excluir_usuario_local(user_id)
    if not ok:
        return jsonify({"erro": "Usuário não encontrado."}), 404

    return jsonify({"mensagem": "Usuário inativado."}), 200
