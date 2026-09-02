# ADR 0001 — O dono do banco é o backend Python

- **Status:** aceito
- **Data:** 2026-09-01
- **Contexto:** versão 1.2.0

## O problema

O projeto tem três interfaces sobre o mesmo domínio:

| Pilha | O que é | Como falava com o banco |
|---|---|---|
| **Electron + Flask** | A versão instalada no cliente | Python, Alembic, SQLite |
| **.NET / Avalonia** | Exploração arquitetural | EF Core, **o mesmo arquivo SQLite** |
| **Qt** | Janela alternativa | Consome a API Flask |

O Qt não é problema: ele fala com a API, então herda todas as regras.

O .NET era. Até a versão 1.1 ele apontava para `adri_poltronas.db` — o mesmo
arquivo do backend Python — e escrevia nele com EF Core. O README do .NET
descrevia isso como uma transição em andamento: "é a arquitetura para onde o
projeto está migrando".

Duas pilhas escrevendo no mesmo SQLite, com domínios e sistemas de migração
diferentes, produzem divergências que nenhum teste de compatibilidade pega:

1. **Semânticas de exclusão em conflito.** O Python inativa cliente
   (`ativo = 0`); o EF Core **remove a linha**, e com ela o histórico e os
   pagamentos que apontam para o cliente. O .NET também apaga pagamento
   fisicamente, contra a política de preservar registro financeiro.

2. **Auditoria cega.** O ledger `auditoria_eventos` é append-only, protegido
   por gatilhos, e só é alimentado pelo Python. Toda escrita vinda do .NET era
   invisível na trilha — que é justamente o que existe para responder "quem
   mudou isso, e quando".

3. **Dois sistemas de migração sobre o mesmo schema.** Alembic e EF Core
   versionam de formas incompatíveis. Se o .NET criasse o arquivo primeiro, o
   banco nasceria sem `alembic_version` e a migração inicial do Python
   tentaria criar tabelas já existentes. O `InicializadorDoBanco` detectava
   essa tabela e recuava, mas isso é uma trégua, não uma solução: só funciona
   na ordem certa.

4. **Regras de negócio duplicadas e já divergentes.** A máquina de estados do
   pedido, o rateio de parcelas em centavos, a emissão idempotente de cobrança
   — tudo isso vive no Python. Reimplementar no .NET significaria manter duas
   versões da mesma regra, com um banco compartilhado como único árbitro.

E não havia paridade funcional que justificasse o risco: o .NET não tem
catálogo de produtos nem pedidos, que são o centro do dia a dia da operação.

## A decisão

**O backend Electron/Flask é o único sistema autorizado a escrever no banco de
produção.** O .NET passa a usar `adri_poltronas_dotnet.db`, na mesma pasta,
como base própria.

Quem precisar apontar as duas pilhas para o mesmo arquivo — um teste de
compatibilidade, uma importação pontual — passa `Banco__ConexaoString`
explicitamente. É uma decisão consciente, não mais o comportamento padrão.

## Alternativas consideradas

**Fazer o .NET consumir a API Flask.** Tecnicamente correto e o caminho certo
se o .NET vier a ser distribuído: todas as regras ficam num lugar só. Foi
descartado *agora* porque exigiria reescrever a camada `Infrastructure`
inteira para um projeto que não é o que o cliente usa. Continua sendo a opção
preferida se e quando o .NET voltar a ser prioridade.

**Manter o banco compartilhado e alinhar as semânticas.** Exigiria replicar,
em C#, a exclusão lógica, o ledger de auditoria, a máquina de estados e a
aritmética em centavos — e manter as duas implementações em sincronia para
sempre. É o custo mais alto das três opções, para o benefício de uma
arquitetura que ainda não decidimos adotar.

**Apagar o .NET.** Resolveria o problema hoje. Não foi feito porque o código
tem valor como exploração — a separação em camadas, os testes de arquitetura,
os gráficos desenhados sem dependência externa — e apagá-lo não é reversível
sem custo. Fica no repositório, sem pretensão de ser produto.

## Consequências

**Boas**

- Uma única fonte de verdade operacional, com uma única trilha de auditoria.
- O Alembic volta a ser dono exclusivo do schema de produção.
- O .NET pode evoluir seu modelo sem risco para o dado real.

**Ruins, e assumidas**

- As duas bases divergem com o tempo. Quem quiser comparar precisa importar.
- Os testes de `Infrastructure.Tests` que exercitam "o schema legado real"
  passam a exercitar uma cópia daquele schema, não o banco vivo.
- A divergência de semântica (exclusão física no EF Core) **não foi corrigida**
  — apenas deixou de ter consequência sobre o dado de produção. Se o .NET vier
  a ser distribuído, ela precisa ser resolvida antes.

## Como reverter

Apontar `PastaDeDados.NomeDoBanco` de volta para `adri_poltronas.db`, ou
definir `Banco__ConexaoString`. Reverter só é seguro depois de resolver os
quatro pontos do Contexto — em especial a exclusão física e a ausência de
registro na auditoria.

## Referências

- `dotnet/src/AdriPoltronas.Infrastructure/Sistema/PastaDeDados.cs`
- `dotnet/README.md` — seção "Banco separado, por decisão"
- `backend/migrations/` — Alembic, dono do schema de produção
