# Backend ERP v2

Segundo backend da Adri Poltronas, construído separadamente do backend atual
para permitir uma comparação segura antes de qualquer migração. Ele não altera
o banco do v1 e usa a API `/api/v2` na porta 5001.

## Estado atual

- O Electron usa o v1 por padrão e pode iniciar o v2 com `npm run start:v2`.
- O v2 roda lado a lado na porta 5001.
- O banco padrão do v2 é `%APPDATA%\AdriPoltronas\adri_poltronas_v2.db`.
- `ADRI_V2_DB_PATH` aponta o v2 para outro banco, útil em testes e demonstrações.
- O snapshot restaurável do v1 está em `backup/backend_v1_2026-08-30`.

## Por que ele é um ERP

O domínio foi organizado em processos de negócio, e não apenas em telas CRUD:

- cadastro único de parceiros com papéis de cliente e fornecedor;
- catálogo de produtos e serviços;
- estoque como razão imutável de movimentos e estornos;
- compras com abertura, recebimento, entrada em estoque e contas a pagar;
- vendas com abertura, aprovação, faturamento, baixa de estoque e contas a receber;
- títulos a pagar/receber com parcelas, baixas parciais e estornos;
- contas financeiras, extrato e fluxo de caixa;
- entregas com máquina de estados;
- painel gerencial, curva ABC e auditoria transacional;
- valores monetários armazenados em centavos inteiros.

## Executar

```powershell
python -m pip install -r backend_v2\requirements.txt
python backend_v2\servidor.py
```

Depois, confira `http://127.0.0.1:5001/api/v2/saude`.

Para abrir a interface Electron usando o backend v2 na porta 5000:

```powershell
npm.cmd run start:v2
```

O v2 serve a interface atual por uma camada de compatibilidade própria. Clientes,
dashboard, mapa, recebimentos, relatórios e backups são traduzidos para o modelo
ERP; o contrato canônico `/api/v2` permanece inalterado. As integrações Asaas,
Microsoft/OneDrive e IA retornam uma mensagem explícita de indisponibilidade no
v2, pois ainda não foram migradas.

Para rodar com um banco descartável ou de demonstração:

```powershell
$env:ADRI_V2_DB_PATH = "$PWD\backend_v2_demo.db"
python backend_v2\servidor.py
```

## Qualidade

```powershell
python -m pip install -r backend_v2\requirements-dev.txt
python -m pytest tests_v2 -q
python -m ruff check backend_v2 tests_v2
```

A regressão conjunta dos dois backends pode ser executada com
`python -m pytest -q`.

## Comparação com o v1

| Tema | Backend v1 | Backend ERP v2 |
|---|---|---|
| Uso atual | Padrão do Electron | Selecionável com `npm run start:v2` |
| Porta | 5000 | 5001 |
| Banco | `adri_poltronas.db` | `adri_poltronas_v2.db` |
| Dinheiro | Valores legados em ponto flutuante | Centavos inteiros |
| Estoque | Estrutura incremental/legada | Razão de movimentos e estornos |
| Financeiro | Pagamentos/cobranças do app atual | Títulos, parcelas, baixas e contas |
| Operações | Foco nas telas atuais | Ciclos completos de compra e venda |
| Compatibilidade | Contrato histórico nativo | Adaptador para a interface e API ERP canônica |

Escolher o v2 como padrão no futuro deve continuar sendo uma decisão explícita.
Os dados do v1 não são migrados automaticamente: cada backend mantém seu banco.

## Rotas principais

- `/api/v2/parceiros`, `/api/v2/produtos` e `/api/v2/estoque`;
- `/api/v2/compras` e `/api/v2/vendas`;
- `/api/v2/financeiro/titulos`, `/api/v2/financeiro/contas` e
  `/api/v2/financeiro/extrato`;
- `/api/v2/entregas`, `/api/v2/painel`, `/api/v2/fluxo-caixa` e
  `/api/v2/curva-abc`.

Listagens são paginadas e os erros distinguem validação (400), recurso ausente
(404), conflito de estado (409) e regra de negócio (422). Todas as respostas
recebem um identificador de correlação e cabeçalhos básicos de segurança.
