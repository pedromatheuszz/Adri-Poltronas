# Padrão de resposta da API — Adri Poltronas

> **Este documento descreve o formato que a API realmente usa hoje.**
>
> Uma versão anterior documentava um envelope `{status, code, message, data}`
> implementado em `backend/api_response.py`. Esse módulo nunca chegou a ser
> usado por nenhum endpoint e foi removido na auditoria de agosto/2026, junto
> com esta seção da documentação. Se o envelope for adotado no futuro, a
> migração precisa ser feita em conjunto com o frontend, que hoje depende do
> formato descrito abaixo.

## Formato em uso

A API não usa envelope. O corpo da resposta é o próprio recurso, e o status
HTTP carrega o resultado da operação.

### Sucesso

Listagens devolvem um array direto:

```json
[
  { "id": 1, "nome": "Ana", "cidade": "Santos" }
]
```

Objetos e métricas devolvem o objeto direto:

```json
{ "total_clientes": 42, "total_entrega": 30, "total_retirada": 12 }
```

Operações de escrita devolvem uma confirmação curta:

```json
{ "mensagem": "Salvo" }
```

### Erro

Todo erro traz a chave `erro` com uma mensagem apresentável ao usuário:

```json
{ "erro": "Cliente nao encontrado." }
```

Erros de validação acrescentam `detalhes` com a lista de problemas:

```json
{
  "erro": "Dados invalidos.",
  "detalhes": [
    "Nome obrigatorio (entre 2 e 120 caracteres).",
    "CEP invalido. Use o formato 00000-000."
  ]
}
```

Erros não tratados (500) trazem um `id` de correlação que aparece também no
log da aplicação, para rastrear o caso sem expor o stack trace:

```json
{ "erro": "Erro interno do servidor.", "id": "a1b2c3d4e5f6" }
```

## Códigos de status em uso

| Status | Uso | Onde aparece |
|--------|-----|--------------|
| 200 | Sucesso geral | GET, PUT, confirmações |
| 201 | Recurso criado | POST de cliente, pagamento, entrega |
| 400 | Requisição inválida | Falha de validação, arquivo ilegível |
| 401 | Não autenticado | Sessão OneDrive ausente/expirada; webhook sem token válido |
| 403 | Origem não permitida | Bloqueio de CSRF (`Origin`/`Referer` externo) |
| 404 | Não encontrado | Cliente, pagamento ou entrega inexistente |
| 502 | Falha em serviço externo | Erro retornado pelo Asaas ou Microsoft Graph |
| 503 | Integração indisponível | `ASAAS_API_KEY` ou `ASAAS_WEBHOOK_TOKEN` ausente |

## Tratamento centralizado

`backend/app.py` registra dois handlers globais que garantem que rotas sob
`/api/` nunca devolvam HTML:

- `HTTPException` → `{"erro": <descrição>}` com o status original.
- `Exception` → `{"erro": "Erro interno do servidor.", "id": <correlação>}` com
  status 500 e o stack trace registrado no log.

## Cabeçalhos de segurança

Toda resposta recebe, via `after_request`:

| Cabeçalho | Valor |
|-----------|-------|
| `Content-Security-Policy` | restringe script/style/img/connect às origens efetivamente usadas |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |

## Proteção contra CSRF

Requisições `POST`/`PUT`/`PATCH`/`DELETE` para `/api/` são recusadas com 403
quando trazem um `Origin` (ou, na ausência dele, um `Referer`) que não
corresponde ao host da própria requisição.

A lista de origens aceitas é derivada de `request.host` — e não fixada numa
constante — para que a checagem continue correta se a porta mudar. Os aliases
de loopback (`127.0.0.1`, `localhost`, `[::1]`) na mesma porta são tratados
como a mesma origem, já que o navegador os considera distintos.

Requisições sem `Origin` nem `Referer` são permitidas: não vêm de navegador
(curl, scripts locais) e portanto não são vetor de CSRF.

O webhook do Asaas (`/api/pagamentos/webhook`) é isento dessa checagem por ser
uma chamada servidor-para-servidor — ele tem autenticação própria por token.
