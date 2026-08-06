# API Response Standard - Adri Poltronas

## Envelope Padrão

Todas as respostas da API seguem um envelope JSON consistente:

### Sucesso (2xx)
```json
{
  "status": "success",
  "code": 200,
  "message": "Mensagem descritiva",
  "data": { /* dados da resposta */ }
}
```

### Erro (4xx, 5xx)
```json
{
  "status": "error",
  "code": 400,
  "error_code": "ERROR_CODE",
  "message": "Mensagem descritiva",
  "details": { /* informações adicionais */ }
}
```

## Códigos de Status HTTP

| Status | Uso | Exemplo |
|--------|-----|---------|
| 200 | OK - Sucesso geral | GET, PUT bem-sucedido |
| 201 | Created - Recurso criado | POST bem-sucedido |
| 204 | No Content - Sem conteúdo | DELETE bem-sucedido |
| 400 | Bad Request - Requisição inválida | Dados inválidos |
| 401 | Unauthorized - Não autenticado | Token ausente/expirado |
| 403 | Forbidden - Sem permissão | Acesso negado |
| 404 | Not Found - Não encontrado | Recurso inexistente |
| 422 | Unprocessable Entity - Erro validação | Validação falhou |
| 500 | Internal Server Error | Erro no servidor |

## Exemplos de Uso

### Sucesso Simples
```python
from api_response import ApiResponse

@app.route('/api/clientes/<int:id>')
def obter_cliente(id):
    cliente = database.obter_cliente_por_id(id)
    if not cliente:
        return ApiResponse.not_found("Cliente não encontrado")
    return ApiResponse.success(cliente, "Cliente obtido com sucesso")
```

**Resposta:**
```json
{
  "status": "success",
  "code": 200,
  "message": "Cliente obtido com sucesso",
  "data": {
    "id": 1,
    "nome": "João Silva",
    "cep": "12345-678"
  }
}
```

### Criação de Recurso
```python
@app.route('/api/clientes', methods=['POST'])
def criar_cliente():
    cliente, erros = validators.validar_cliente(request.get_json())
    if erros:
        return ApiResponse.validation_error({"cliente": erros})
    
    id_cliente = database.salvar_cliente(**cliente)
    return ApiResponse.created(
        {"id": id_cliente},
        "Cliente criado com sucesso"
    )
```

**Resposta:**
```json
{
  "status": "success",
  "code": 201,
  "message": "Cliente criado com sucesso",
  "data": {
    "id": 42
  }
}
```

### Erro de Validação
```python
@app.route('/api/pagamentos', methods=['POST'])
def criar_pagamento():
    pagamento, erros = validators.validar_pagamento(request.get_json())
    if erros:
        return ApiResponse.validation_error({
            "pagamento": erros
        })
    # ...
```

**Resposta:**
```json
{
  "status": "error",
  "code": 422,
  "error_code": "VALIDATION_ERROR",
  "message": "Erro de validação",
  "details": {
    "pagamento": [
      "Valor invalido. Use entre R$ 0.01 e R$ 500000.00.",
      "Data de vencimento obrigatoria."
    ]
  }
}
```

### Erro de Autorização
```python
@app.route('/api/excel/enviar', methods=['POST'])
def enviar_excel():
    sessao = database.obter_sessao()
    if not sessao:
        return ApiResponse.unauthorized("Usuário não autenticado")
    # ...
```

**Resposta:**
```json
{
  "status": "error",
  "code": 401,
  "error_code": "UNAUTHORIZED",
  "message": "Usuário não autenticado"
}
```

### Erro Não Encontrado
```python
@app.route('/api/clientes/<int:id>', methods=['DELETE'])
def excluir_cliente(id):
    linhas = database.excluir_cliente(id)
    if linhas == 0:
        return ApiResponse.not_found("Cliente não encontrado")
    return ApiResponse.success(None, "Cliente excluído com sucesso")
```

**Resposta (sucesso):**
```json
{
  "status": "success",
  "code": 200,
  "message": "Cliente excluído com sucesso",
  "data": null
}
```

### Lista Paginada
```python
@app.route('/api/clientes')
def listar_clientes():
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 10, type=int)
    
    todos = database.listar_clientes()
    total = len(todos)
    start = (page - 1) * page_size
    items = todos[start:start + page_size]
    
    return ApiResponse.paginated(
        items, 
        total, 
        page, 
        page_size,
        "Clientes listados com sucesso"
    )
```

**Resposta:**
```json
{
  "status": "success",
  "code": 200,
  "message": "Clientes listados com sucesso",
  "data": [
    {"id": 1, "nome": "João"},
    {"id": 2, "nome": "Maria"}
  ],
  "pagination": {
    "total": 42,
    "page": 1,
    "page_size": 10,
    "pages": 5
  }
}
```

### Erro Interno
```python
@app.errorhandler(Exception)
def handle_error(e):
    correlation_id = uuid.uuid4().hex[:12]
    log.exception("Erro não tratado [%s]: %s", correlation_id, e)
    return ApiResponse.server_error(
        "Erro interno do servidor",
        correlation_id
    )
```

**Resposta:**
```json
{
  "status": "error",
  "code": 500,
  "error_code": "INTERNAL_SERVER_ERROR",
  "message": "Erro interno do servidor",
  "details": {
    "correlation_id": "a1b2c3d4e5f6"
  }
}
```

## Guia de Migração

Para migrar endpoints existentes para o novo padrão:

1. **Importar ApiResponse:**
```python
from api_response import ApiResponse
```

2. **Substituir retornos simples:**
```python
# Antes
return jsonify({"mensagem": "Salvo"}), 201

# Depois
return ApiResponse.created(None, "Salvo com sucesso")
```

3. **Substituir retornos com dados:**
```python
# Antes
return jsonify({"mensagem": "OK", "data": cliente}), 200

# Depois
return ApiResponse.success(cliente, "Cliente obtido com sucesso")
```

4. **Substituir erros:**
```python
# Antes
return jsonify({"erro": "Not found"}), 404

# Depois
return ApiResponse.not_found("Cliente não encontrado")
```

## Status Atual

- ✅ Implementado: `api_response.py`
- ⏳ Pendente: Migração de endpoints existentes
- 📋 Checklist de migração: [Ver abaixo]

### Endpoints a Migrar
- [ ] `/api/clientes` - CRUD
- [ ] `/api/pagamentos` - CRUD
- [ ] `/api/relatorios` - Filtros e export
- [ ] `/api/dashboard` - Métricas
- [ ] `/api/auth` - Autenticação
- [ ] `/api/entregas` - Agendamentos
- [ ] `/api/notificacoes` - Notificações
- [ ] `/api/excel` - OneDrive
- [ ] `/api/ia` - IA sugestões
