# Diagnostico tecnico e roadmap ERP — Adri Poltronas

**Data da auditoria:** 29/08/2026  
**Escopo:** todo o repositorio, schema SQLite instalado, APIs, interfaces, testes, build e CI.  
**Decisao principal:** evoluir por um **monolito modular**, mantendo o aplicativo funcional e os contratos atuais. Nao ha justificativa para reescrever ou criar microsservicos neste momento.

## Resumo executivo

O produto em uso e um aplicativo desktop Electron que inicia um backend Flask em loopback. O Flask serve uma interface HTML/CSS/JavaScript e concentra APIs, integracoes e acesso SQLite. Existem ainda duas interfaces alternativas: uma C++/Qt, parcial, e uma C#/.NET 8 com Avalonia, mais estruturada e com boa cobertura, mas que escreve diretamente no mesmo SQLite. A coexistencia de tres pilhas e o maior risco estrutural do repositorio.

O sistema atual cobre bem cadastro e relacionamento basico com clientes, entregas, recebimentos, notificacoes, mapas, relatorios e integracoes. Ainda nao existem os nucleos que caracterizam um ERP: catalogo de produtos, orcamento/pedido/venda, estoque como ledger, compras, contas a pagar, caixa, usuarios/RBAC e processos transacionais entre modulos.

A menor fundacao segura foi implementada nesta entrega:

- recuperacao da migration `f4c8b2d6e1a0`, que estava aplicada no banco instalado, mas ausente do repositorio;
- nova migration de auditoria append-only;
- chaves estrangeiras efetivamente habilitadas em toda conexao da aplicacao;
- exclusao de cliente convertida em inativacao, sem quebrar o contrato HTTP atual;
- contexto de operacao com correlacao, origem, identidade disponivel e IP anonimizado;
- auditoria na mesma transacao das mutacoes atuais;
- evento de webhook Asaas idempotente e sem payload sensivel nos logs;
- primeira fronteira modular em `backend/erp/core` e `backend/erp/financeiro`.

Essa fundacao nao transforma sozinha o produto em ERP. Ela resolve os riscos que impediam uma evolucao segura dos proximos modulos.

## 1. Stack atual encontrada

| Area | Tecnologia atual | Observacao |
|---|---|---|
| Aplicativo principal | Electron 33 + TypeScript 5.7 | Processo principal isolado; inicia o backend empacotado e abre `127.0.0.1:5000` |
| Backend principal | Python + Flask 3.1 | Blueprints HTTP, validadores, integracoes e SQL manual |
| Persistencia principal | SQLite + `sqlite3` | Arquivo em `%APPDATA%/AdriPoltronas/adri_poltronas.db` |
| Migrations | Alembic 1.12 + SQLAlchemy transitivo | Alembic e o dono declarado do schema compartilhado |
| Frontend principal | HTML5, CSS3 e JavaScript sem framework | Um template grande, `app.js`, service worker e IndexedDB |
| Visualizacao | Chart.js 4.4 e Leaflet 1.9 | Carregados com SRI; OpenStreetMap/Nominatim |
| Interface alternativa | C++17 + Qt 6 Widgets/Network | Parcial; consome o Flask e cobre principalmente clientes |
| Migracao paralela | .NET 8 + Avalonia + MVVM + EF Core | Domain/Application/Infrastructure/Desktop e quatro projetos de testes |
| Arquivos | openpyxl | Importacao/exportacao XLSX; CSV e JSON tambem suportados |
| Seguranca local | `cryptography`, DPAPI/pywin32 | Token Microsoft cifrado no Windows; headers e verificacao de origem |
| Empacotamento | PyInstaller + electron-builder/NSIS | Backend vira executavel e e incluido no instalador Electron |
| Qualidade | pytest, Ruff, TypeScript, CTest, xUnit/.NET | CI Windows para Python/Electron/Qt; .NET tambem validado em Linux |
| CI/CD | GitHub Actions | Testes, builds, `pip-audit` e gitleaks; nao ha publicacao automatica |
| Containers | Nao ha Docker | Coerente com o produto desktop atual; nao e uma lacuna por si so |

Nao foi encontrado `AGENTS.md` aplicavel. Tambem nao existe diretorio `.git` neste workspace; portanto, nao ha historico, branch, diff ou rollback Git disponivel para esta auditoria.

## 2. Arquitetura atual

Fluxo principal em producao:

```text
Electron BrowserWindow
        |
        | HTTP em loopback
        v
Flask / blueprints
        |
        +-- database.py / sqlite3 -------- SQLite em %APPDATA%
        +-- Asaas
        +-- Microsoft Graph / OneDrive
        +-- ViaCEP / Gemini / Nominatim
```

O Electron esta corretamente configurado com `contextIsolation`, `sandbox`, sem Node no renderer e bloqueio de navegacao externa. O backend e iniciado como processo filho e encerrado com a janela.

O Flask esta separado em blueprints por recurso, mas as regras e consultas permaneciam concentradas em `database.py`. A camada HTTP ainda orquestra parte de processos empresariais e integracoes. O frontend principal concentra navegacao, estado e chamadas em um `app.js` grande; nao ha store ou biblioteca de formularios.

A aplicacao .NET possui arquitetura em camadas, entidades, value objects, casos de uso e repositorios. Apesar disso, ela acessa o mesmo SQLite diretamente. Isso cria dois modelos de dominio e dois caminhos de escrita. O Qt, por outro lado, atua como cliente HTTP do Flask.

Direcao recomendada: enquanto o produto principal for Electron/Flask, o backend HTTP deve ser a unica fronteira de escrita e Alembic deve continuar sendo o unico dono do schema. A eventual escolha entre Electron e Avalonia exige um ADR e paridade funcional comprovada; nao deve ser feita implicitamente durante a evolucao do ERP.

## 3. Estrutura atual do banco

### Banco instalado antes desta entrega

O schema instalado foi inspecionado apenas por metadados. Ele estava marcado como `f4c8b2d6e1a0`, embora o repositorio contivesse somente as revisions `21d8d4eb2b6f` e `7c2f19a4b8e3`. Em cada inicializacao, o Alembic nao reconhecia a revision e o servidor caia silenciosamente no criador de tabelas legado. Essa era a maior ameaca imediata a qualquer migration futura.

Tabelas encontradas:

| Tabela | Papel atual | Relacoes principais |
|---|---|---|
| `clientes` | Cadastro/CRM basico | Pai de pagamentos, entregas, historico e vinculo Asaas |
| `pagamentos` | Recebimentos e cobrancas | `cliente_id -> clientes`, RESTRICT |
| `clientes_asaas` | Identidade remota no Asaas | `cliente_id -> clientes`, RESTRICT |
| `entregas_agendadas` | Agenda operacional | `cliente_id -> clientes`, RESTRICT |
| `historico` | Historico legivel do cliente | `cliente_id -> clientes`, SET NULL |
| `notificacoes_lidas` | Estado de leitura | Notificacoes em si sao derivadas por consulta |
| `sessao` | Token e conta Microsoft | Integracao Microsoft, nao identidade ERP |
| `alembic_version` | Versao do schema | Alembic |

O schema instalado ja possuia `clientes.ativo`, `clientes.excluido_em`, campos de idempotencia Asaas, foreign keys e indices que nao estavam representados nas migrations versionadas. A revision recuperada agora documenta e reproduz essa estrutura em bancos novos.

### Problemas de modelagem atuais

- dinheiro e armazenado como SQLite `REAL`, consumido como `float`/`double`;
- datas sao `TEXT` e misturam data simples com data/hora;
- status sao texto livre em parte da pilha Python;
- nao existem empresa, filial, deposito, usuario, papel ou permissao;
- nao existem produto, SKU, orcamento, pedido, venda, compra ou movimentos de estoque;
- pagamentos representam principalmente contas a receber, mas o nome generico esconde essa semantica;
- nao ha paginacao server-side;
- o modo WAL nao esta habilitado; adequado para uso desktop simples, insuficiente para varios escritores concorrentes.

### Alteracao desta entrega

A head atual passa a ser `a7e3c9d1f5b2`, com `auditoria_eventos`, indices e triggers que recusam `UPDATE` e `DELETE`. O evento de auditoria e inserido na mesma transacao do dado empresarial: se a auditoria falhar, a operacao e revertida.

## 4. Funcionalidades existentes e destino no ERP

| Funcionalidade atual | Entidades/dados | Regra observada | Modulo ERP futuro |
|---|---|---|---|
| Cadastro, busca, edicao e inativacao de cliente | `clientes`, `historico` | Validacao no backend; exclusao agora preserva registro | CRM / Clientes |
| Importacao CSV/JSON/XLSX | `clientes`, `historico` | Ate 5.000 linhas; duplicidade por nome + CEP | CRM / Importacoes |
| Backup JSON e SQLite | banco/arquivos | Download local do conjunto ativo ou arquivo completo | Core / Continuidade |
| Mapa de clientes | clientes com CEP | Geocodificacao via Nominatim; Leaflet/OSM | CRM / Geografia comercial |
| Consulta de CEP | endereco | ViaCEP | Core / Enderecos |
| Sugestao de bairro | endereco | Gemini opcional | CRM / Assistencia de cadastro |
| Agenda de entrega | `entregas_agendadas` | Cliente e nome validados; estados explicitos na API | Operacional / Entregas |
| Notificacoes de entrega | consultas derivadas | Hoje, proximas e atrasadas; limite por tipo | Core / Notificacoes |
| Registro de recebimento/cobranca | `pagamentos` | Pendente/Recebido/Atrasado/Cancelado | Financeiro / Contas a receber |
| Pix e boleto | pagamentos + Asaas | Cliente remoto, cobranca, QR code/boleto e webhook | Financeiro / Cobrancas |
| Estado de notificacao lida | `notificacoes_lidas` | Chave estavel e operacao idempotente | Core / Notificacoes |
| Dashboard atual | clientes e pagamentos | Metricas de cadastro, receita e inadimplencia | Analytics / Executivo |
| Graficos | agregacoes SQL | Tipo, cidade, cadastros e receita mensal | Analytics / CRM e financeiro |
| Relatorios | clientes | Filtros de tipo, cidade e periodo; CSV/XLSX | Analytics / Relatorios |
| Excel no OneDrive | sessao Microsoft | OAuth e upload ao Graph | Core / Integracoes |
| Operacao offline parcial | IndexedDB | Enfileira mutacoes de clientes no renderer | Core / Sincronizacao local |
| Historico de cliente | `historico` | Criacao, alteracao, exclusao e pagamentos | CRM / Timeline |
| Auditoria tecnica nova | `auditoria_eventos` | Antes/depois, origem, ator disponivel e correlacao | Core / Auditoria |

Nenhuma dessas capacidades deve ser removida durante a modularizacao. O `historico` continua como timeline voltada ao usuario; `auditoria_eventos` tem finalidade de controle e nao o substitui.

## 5. Principais entidades atuais

- **Cliente:** nome, endereco, modalidade Entrega/Retirada, observacoes, timestamps e estado ativo.
- **Pagamento:** cliente, valor, vencimento, recebimento, tipo, status e identificadores/artefatos Asaas.
- **Entrega agendada:** cliente, data, hora, descricao e status.
- **Registro historico:** cliente, nome desnormalizado, acao, detalhe e instante.
- **Cliente Asaas:** mapeamento local-remoto e controle de idempotencia.
- **Notificacao lida:** chave derivada e instante de leitura.
- **Sessao Microsoft:** token cifrado e conta usada na integracao.
- **Evento de auditoria:** ator, acao, entidade, antes/depois, origem, contexto, correlacao e instante.

Entidades futuras prioritarias: Empresa, Usuario, Papel, Permissao, Produto, Variacao, ListaDePreco, Orcamento, Pedido, Venda, ItemComercial, Deposito, MovimentoEstoque, ReservaEstoque, Fornecedor, OrdemCompra, RecebimentoCompra, TituloReceber, TituloPagar, BaixaFinanceira, ContaFinanceira e CentroCusto.

## 6. Relacionamentos

Relacionamentos atuais relevantes:

```text
Cliente 1 ---- N Pagamento
Cliente 1 ---- N EntregaAgendada
Cliente 1 ---- N RegistroHistorico
Cliente 1 ---- 0..1 ClienteAsaas
Entidade logica 1 ---- N EventoAuditoria
```

Relacionamento-alvo do primeiro fluxo ERP completo:

```text
Cliente -> Orcamento -> Pedido -> Venda -> MovimentoEstoque
                                      |
                                      +-> TituloReceber -> Baixa -> Caixa
                                      +-> Auditoria / Historico / Analytics
```

O segundo fluxo integrado sera:

```text
Fornecedor -> OrdemCompra -> Recebimento -> MovimentoEstoque
                                      |
                                      +-> TituloPagar -> Baixa -> Caixa
```

## 7. Problemas arquiteturais encontrados

1. **Tres interfaces e dois caminhos de escrita.** Electron/Flask, Qt/Flask e Avalonia/EF podem divergir.
2. **Cadeia de migrations quebrada.** A revision instalada estava ausente; corrigido nesta entrega.
3. **Modulo de banco concentrador.** SQL, CRUD, analytics, historico e integracoes coexistem em `database.py`.
4. **Frontend monolitico.** Estado, UI e chamadas HTTP estao concentrados em poucos arquivos grandes.
5. **Autenticacao conceitualmente incorreta.** OAuth Microsoft protege mutacoes, mas e uma credencial de integracao, nao um usuario do ERP.
6. **Sem RBAC.** Nao existem usuarios, papeis ou verificacao de permissao no backend.
7. **CSRF incompleto.** Ha token emitido, mas a validacao real depende de `Origin`/`Referer`.
8. **Status sem maquina de estados central.** Blueprints e entidades .NET aplicam conjuntos diferentes de regras.
9. **Dinheiro em ponto flutuante.** Inadequado para contabilizacao e margem profissional.
10. **Analytics disperso.** Consultas agregadas ainda vivem junto ao CRUD.
11. **Operacoes externas dentro de transacao SQLite.** A criacao de cliente Asaas mantem a conexao aberta durante rede.
12. **Emissao Asaas ainda sem processo completo de idempotencia.** O schema possui campos preparatorios, mas o endpoint de emissao ainda pode repetir a chamada externa.
13. **Listagens sem paginacao.** A interface carrega conjuntos inteiros no browser.
14. **Rate limit em memoria.** Reinicia com o processo e nao serve a multiplas instancias.
15. **CSP depende de `unsafe-inline`.** O template ainda contem handlers inline.
16. **Sem repositorio Git no workspace.** Nao ha baseline confiavel de mudancas ou estrategia de reversao por commit.

## 8. Riscos de regressao

| Risco | Causa | Mitigacao obrigatoria |
|---|---|---|
| Perda ou invisibilidade de dados | migrations destrutivas/soft delete incompleto | migrations aditivas, backup, testes em copia e filtros consistentes |
| Divergencia entre interfaces | Flask e EF escrevendo o mesmo arquivo | uma unica API de escrita e testes de contrato durante transicao |
| Venda sem estoque/financeiro | atualizacoes independentes | um caso de uso transacional com ledger e titulos |
| Duplicidade Asaas | repeticao apos timeout | chave idempotente local + referencia externa unica |
| Metricas inconsistentes | consultas duplicadas | servico central de Analytics com definicoes documentadas |
| Quebra do modo offline | mudanca de contrato de clientes | versionar contrato e manter adaptador temporario |
| Corrupcao financeira | `REAL`/arredondamentos | valor monetario decimal ou centavos inteiros e testes de borda |
| Escalada de privilegio | autorizacao apenas na UI | policy/RBAC obrigatorio no backend |
| Bloqueio SQLite | rede dentro de transacao/escritores concorrentes | transacoes curtas, outbox/idempotencia e evolucao de banco quando necessaria |

## 9. Debitos tecnicos

- schema e tipos duplicados entre Python, JavaScript e C#;
- ausencia de OpenAPI/contratos versionados;
- nomes de status em portugues e ingles sem padrao de persistencia;
- `database.py` ainda e uma fachada grande, embora agora abaixo do limite historico de 800 linhas;
- `app.js` e CSS extensos e com responsabilidades misturadas;
- tratamento de erro nao e totalmente uniforme entre blueprints;
- GETs da API nao exigem autenticacao;
- segredos de integracao ainda compartilham o conceito de sessao do produto;
- SQL analitico sem camada dedicada;
- ausencia de testes end-to-end reais do Electron;
- dados financeiros existentes sem escala decimal garantida;
- ausencia de estrategia explicita para multiempresa e filial;
- documentacao raiz fragmentada e sem README principal.

## 10. Partes reutilizaveis

- validadores Flask e respostas 400 estruturadas;
- blueprints e contratos HTTP usados pelo Electron e pelo Qt;
- isolamento seguro do Electron e controle de instancia unica;
- importacao/exportacao e backup;
- integracoes Asaas, ViaCEP, Gemini, Microsoft Graph e Nominatim;
- notificacoes derivadas com limite e estado de leitura;
- dashboard financeiro ja baseado em agregacoes do backend;
- pipeline de build e testes multiplataforma;
- dominio, value objects, casos de uso e testes da solucao .NET;
- entidades de pagamento e entrega com estados explicitos na camada .NET;
- migration manager com caminho absoluto;
- novo contexto operacional, ledger de auditoria e servico financeiro modular.

## 11. Partes que precisam de refatoracao

Prioridade imediata:

1. separar autenticacao ERP da integracao Microsoft;
2. criar empresa padrao, usuarios e RBAC no backend;
3. extrair consultas de dashboard para `erp/analytics`;
4. extrair CRM da fachada `database.py` para casos de uso/repositories simples;
5. concluir idempotencia da emissao Asaas sem rede dentro da transacao;
6. formalizar estados e transicoes de pagamentos e entregas;
7. introduzir paginacao e filtros server-side preservando respostas antigas por periodo de compatibilidade;
8. modularizar `app.js` e remover handlers inline;
9. decidir, por ADR, a interface desktop canonica e impedir escrita direta concorrente no SQLite.

## 12. Proposta de arquitetura ERP

Adotar um **monolito modular orientado a casos de uso**, com estas regras:

- blueprints sao adaptadores HTTP e nao contem regra empresarial complexa;
- cada modulo expoe casos de uso e contratos explicitos;
- repositories escondem SQL quando a consulta faz parte de um processo de dominio;
- analytics pode usar SQL otimizado de leitura sem forcar um repository por tabela;
- uma transacao envolve todo o processo local critico;
- integracoes externas usam idempotencia e transacoes locais curtas;
- eventos internos simples desacoplam efeitos posteriores; outbox so quando houver efeito externo confiavel;
- Alembic permanece como unico dono do schema durante a coexistencia das pilhas;
- Flask permanece como fachada de compatibilidade; nenhum endpoint e removido sem versao/adaptador;
- a UI consome dados calculados no backend e nao recompõe metricas criticas.

Fronteiras logicas:

```text
HTTP/UI -> Application (casos de uso) -> Domain
                         |                 |
                         v                 v
                   Infrastructure <- contratos
                         |
                         +-- SQLite/Alembic
                         +-- integracoes externas
```

Nao e necessario replicar cerimonial de Clean Architecture em cada funcao simples. Services e repositories devem existir quando protegem uma regra, transacao ou fronteira real.

## 13. Modulos sugeridos

| Modulo | Responsabilidade | Primeiros casos de uso |
|---|---|---|
| Core | empresa, usuarios, RBAC, auditoria, arquivos, notificacoes | autenticar, autorizar, auditar, configurar empresa |
| CRM | clientes, contatos, leads, interacoes | cadastrar/inativar cliente, timeline, converter lead |
| Catalogo | produtos e personalizacoes de poltronas | cadastrar modelo/SKU, cor, tecido, dimensao, preco/custo |
| Comercial | orcamentos, pedidos, vendas | aprovar orcamento, gerar pedido, confirmar/cancelar venda |
| Estoque | saldo, reserva e ledger | reservar, movimentar, ajustar, inventariar, estornar |
| Compras | fornecedores e ordens | aprovar compra, receber itens, atualizar custo |
| Financeiro | receber, pagar, baixas e caixa | gerar titulo, baixar, estornar, projetar fluxo |
| Operacional | entrega e producao | programar, iniciar, concluir e cancelar entrega/producao |
| Analytics | indicadores e relatorios | visao executiva, comercial, estoque e financeiro |

## 14. Estrutura futura de diretorios

A estrutura sera criada apenas conforme houver codigo real:

```text
backend/
  app.py                         # composicao Flask e compatibilidade
  blueprints/                    # adaptadores HTTP atuais
  erp/
    core/
      contexto.py
      auditoria.py
      autenticacao.py            # proxima fase
      autorizacao.py             # proxima fase
    crm/
      casos_de_uso.py
      repositorio.py
      modelos.py
    catalogo/
    comercial/
    estoque/
    compras/
    financeiro/
      servico_pagamentos.py
    operacional/
    analytics/
    shared/
      erros.py
      dinheiro.py
      eventos.py
  infrastructure/
    persistence/
    integrations/
  migrations/
frontend/
  js/
    core/
    modules/
    components/
  css/
    tokens/
    components/
tests/
  unit/
  integration/
  contract/
```

Nao serao criadas pastas vazias nem camadas sem comportamento.

## 15. Alteracoes necessarias no banco

Ordem segura proposta:

1. **Concluido:** recuperar `f4c8b2d6e1a0` e adicionar auditoria.
2. Criar `empresas`, empresa padrao e `empresa_id` aditivo nos novos registros; migrar legado em etapas.
3. Criar `usuarios`, `papeis`, `permissoes`, tabelas de vinculo e sessao ERP separada.
4. Criar catalogo: produtos, categorias, variacoes, atributos especificos de poltronas e precos.
5. Criar comercial: orcamentos/pedidos/vendas, itens, historico de estados e snapshots de preco/custo.
6. Criar estoque: depositos, movimentos imutaveis, reservas e saldo derivado/materializado reconciliavel.
7. Evoluir financeiro: titulos a receber/pagar, parcelas, baixas, contas, categorias e centros de custo.
8. Criar compras/recebimentos e integrar entrada de estoque + contas a pagar.
9. Migrar dinheiro legado de `REAL` por estrategia dual-read para centavos inteiros ou `NUMERIC(18,2)` no banco futuro.
10. Padronizar timestamps e UTC sem quebrar as datas locais existentes.

Cada migration deve ser aditiva, testada em banco vazio e em copia do banco legado. Remocoes so ocorrerao depois de pelo menos uma versao de compatibilidade e reconciliacao.

## 16. Roadmap de implementacao

### Fase 0 — Recuperacao e guardrails (esta entrega)

- cadeia Alembic recuperada;
- integridade referencial habilitada;
- soft delete de cliente;
- auditoria transacional e imutavel;
- contexto/correlacao;
- webhook idempotente;
- diagnostico e testes de fundacao.

### Fase 1 — Core empresarial

- empresa/configuracoes;
- autenticacao local ERP;
- usuarios, papeis e permissoes no backend;
- erros de dominio padronizados;
- backup automatico antes de migrations;
- endpoint de consulta de auditoria autorizado.

### Fase 2 — CRM consolidado

- casos de uso/repository do cliente;
- contatos, observacoes e interacoes;
- timeline unificada;
- busca/paginacao server-side;
- contratos de API e testes de compatibilidade das tres interfaces.

### Fase 3 — Catalogo e precificacao

- produtos, modelos, SKU, cores, tecidos, dimensoes e imagens;
- custos, precos, margens e status;
- componentes visuais reutilizaveis para tabelas/filtros/formularios.

### Fase 4 — Comercial

- orcamento -> aprovacao -> pedido -> venda;
- snapshots de valores, descontos e condicoes;
- estados e transicoes validas;
- cancelamento/estorno auditados.

### Fase 5 — Estoque

- ledger de movimentos;
- saldo fisico, disponivel e reservado;
- reserva na aprovacao do pedido;
- baixa/estorno na venda;
- inventario e estoque minimo.

### Fase 6 — Compras e financeiro

- fornecedor -> ordem -> recebimento -> entrada;
- contas a pagar/receber, parcelas, baixas e estornos;
- caixa, bancos, categorias e centros de custo;
- integracao transacional com comercial/compras.

### Fase 7 — Analytics

- servico central de consultas;
- dashboards executivo, comercial, estoque e financeiro;
- receita, margem, ticket, conversao, giro e inadimplencia;
- reconciliacao entre indicadores e ledgers.

### Fase 8 — UX e convergencia de clientes

- menu ERP por modulos;
- design system/tokens;
- filtros, paginacao, estados vazios/erro/loading e acessibilidade;
- ADR sobre Electron, Qt e Avalonia;
- retirada de uma interface somente apos paridade, migracao e aceite explicitos.

## 17. Ordem recomendada de refatoracao

1. Core/RBAC e backup de migration.
2. CRM por casos de uso, mantendo os endpoints atuais.
3. Catalogo de produtos especifico para poltronas.
4. Orcamento e pedido sem impacto de estoque inicialmente.
5. Ledger e reserva de estoque.
6. Confirmacao de venda transacional com estoque + conta a receber.
7. Compras + entrada + conta a pagar.
8. Baixas/estornos e fluxo de caixa.
9. Analytics sobre os processos estabilizados.
10. Reorganizacao visual e convergencia das interfaces.

O primeiro fluxo vertical de aceite deve ser pequeno, mas completo:

> cadastrar produto -> criar orcamento -> aprovar pedido -> reservar estoque -> confirmar venda -> baixar estoque -> gerar conta a receber -> registrar pagamento -> refletir no dashboard -> auditar tudo.

## Gates de qualidade para cada incremento

- migration testada a partir de banco vazio e banco legado;
- contrato antigo preservado ou adaptador versionado;
- regra critica coberta por teste unitario e de integracao;
- lint e typecheck sem supressoes artificiais;
- suites Python, Electron e .NET verdes;
- build do artefato afetado concluido;
- verificacao manual do fluxo principal;
- documentacao de regra e decisao atualizada;
- reconciliacao de estoque/financeiro quando aplicavel.

## Regras arquiteturais registradas

- integridade e rastreabilidade prevalecem sobre conveniencia de CRUD;
- registros empresariais sao inativados, cancelados ou estornados, nao apagados sem criterio;
- quantidade de estoque nunca muda sem movimento;
- dinheiro nao usa ponto flutuante nos novos modulos;
- permissao e validada no backend;
- integracao externa nao define identidade do usuario do ERP;
- nenhum framework principal sera trocado antes de ADR, paridade e plano de migracao;
- nenhum microsservico sera criado enquanto um monolito modular atender aos requisitos.
