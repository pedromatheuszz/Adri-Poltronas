# Registro de mudanças

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento [semântico](https://semver.org/lang/pt-BR/).

---

## [1.4.2-beta] — 2026-09-05

### Alterado

- **A conexão com a Microsoft mudou para a barra superior**, ao lado do
  indicador de rede. As duas dizem a mesma coisa — "como este app está ligado
  ao mundo" — e ficavam em lugares distantes: o estado da rede no topo, a conta
  no rodapé da aba Clientes, onde só era encontrada por quem já sabia que
  existia. Quem precisa exportar planilha agora vê de onde ela depende sem
  procurar.

  O botão espelha as medidas do indicador de rede de propósito: alturas ou
  raios diferentes fariam dois controles vizinhos parecerem sem relação.
  Conectado, mostra o nome da conta e leva o endereço completo no `title`, que
  é o que permite caber num espaço curto sem esconder informação.

  O envio ao Excel, o backup e a restauração **continuam no rodapé da lista**:
  operam sobre a seleção de clientes e sobre a tela, não sobre o estado da
  conexão.

---

## [1.4.1-beta] — 2026-09-05

O aplicativo não se identificava como beta em lugar nenhum. O README, a
descrição do repositório e a página de releases já avisavam — e quem usa o app
instalado nunca vê nenhum dos três.

### Adicionado

- **Selo `BETA` na barra lateral**, sob o nome do aplicativo. Discreto de
  propósito: quem abre o sistema todo dia não precisa de um alerta permanente,
  e um selo chamativo vira ruído que se aprende a ignorar — o mesmo raciocínio
  da contagem do período de teste, que só ganha destaque na última semana. O
  que ele precisa fazer é responder "que versão é essa?" quando alguém
  perguntar; a versão exata está no `title`, lida de `/api/health`, que por sua
  vez a lê do `package.json`. Um lugar só onde a versão é escrita.

### Alterado

- **A versão passou a carregar o sufixo de pré-lançamento.** É o que faz o
  instalador sair como `AdriPoltronasSetup-1.4.1-beta.exe` e a sonda
  `/api/health` reportar beta. Sem isso, o aviso viveria só na documentação e o
  artefato entregue diria que é uma versão final.

  `1.4.1-beta`, e não `1.4.0-beta`: em versionamento semântico o sufixo de
  pré-lançamento vale **menos** que a versão sem ele, então `1.4.0-beta`
  apareceria como anterior à `1.4.0` já registrada aqui — um retrocesso.

- Nome e selo ficam **empilhados** no cabeçalho da barra lateral. Lado a lado
  disputavam os 223px disponíveis e truncavam "Adri Poltronas" em
  "Adri Poltr...", que parece defeito.

---

## [1.4.0] — 2026-09-05

Licenca de uso: 30 dias de teste a partir da primeira abertura, depois compra
de R$ 1.500,00 via Pix do Mercado Pago, com confirmacao automatica.

### Adicionado

- **Periodo de teste de 30 dias.** Comeca na primeira abertura do aplicativo.
  A topbar mostra a contagem de forma discreta, e ganha destaque na ultima
  semana — avisar com o mesmo peso durante 30 dias ensina o operador a nao ver
  o aviso.

- **Bloqueio ao fim do teste.** O backend responde `402 Payment Required` em
  todo `/api/`, exceto nas rotas da propria licenca, no login e na sonda de
  identidade — sem essas isencoes o operador ficaria trancado do lado de fora
  com a chave dentro. A tela substitui o conteudo por uma explicacao com o
  valor a vista e o botao de pagar; nenhum numero fica visivel para ser lido
  errado.

- **Pagamento via Pix do Mercado Pago, verificado automaticamente.** O app
  gera a cobranca, mostra o QR Code e o copia-e-cola, e pergunta ao Mercado
  Pago a cada 5 segundos se o pagamento entrou. Confirmado, a tela libera
  sozinha. A consulta substitui o webhook pelo mesmo motivo ja documentado
  para o Asaas: o backend escuta em loopback e um servidor da internet nao
  alcanca esse endereco.

  Apenas `approved` libera a licenca. `authorized` — cartao autorizado e nao
  capturado — e dinheiro reservado, nao recebido.

### O limite honesto deste controle

O aplicativo roda inteiro na maquina do cliente, entao quem tem administrador
ali contorna qualquer bloqueio local. O que o desenho alcanca e tornar o
contorno **deliberado**:

- o estado vive em dois lugares — arquivo cifrado com DPAPI no perfil e tabela
  no banco — e a reconciliacao pega sempre o lado mais restritivo. Apagar o
  arquivo nao reinicia a contagem; restaurar um backup antigo do banco tambem
  nao. Apagar os dois reinicia, e isso nao acontece por acidente;
- atrasar o relogio do sistema congela a contagem em vez de reverte-la, por
  uma marca d'agua que guarda a data mais adiantada ja vista.

O `access_token` do Mercado Pago fica na maquina do cliente, cifrado com DPAPI.
Isso o prende aquela conta do Windows, mas nao impede quem tem administrador de
extrai-lo. A forma correta de fechar isso e um endpoint do vendedor que
responda apenas "esta licenca esta paga?" — enquanto ele nao existe, use um
token de aplicacao dedicada, e nao o principal da conta.

### Corrigido

- **A ordem dos portoes fazia o app abrir vazio depois de pagar.** A checagem
  de sessao disparava o carregamento dos dados antes de a licenca ser
  consultada: com o teste vencido as requisicoes voltavam 402, a tela ficava
  com os zeros do HTML e o app se dava por carregado. Ao pagar, a tela
  liberava sem trazer dado nenhum. Agora um unico ponto decide, e ele exige os
  dois portoes abertos.

---

## [1.3.2] — 2026-09-05

A 1.3.1 fechou a leitura da API sem sessão. Correto do lado do servidor — e do
lado da tela criou um estado que nunca tinha existido, porque até a 1.3.0 abrir
o app sem conta conectada funcionava como qualquer outra abertura.

### Corrigido

- **O app aberto sem conta conectada mostrava zeros como se fossem o cadastro.**
  Não era um erro na tela: era o Dashboard exibindo "0 Total Clientes" e
  "R$ 0,00 em atraso" — os zeros escritos no próprio HTML — enquanto quatro
  requisições voltavam 401 no console, onde ninguém olha. Quem abrisse o
  sistema sem ter conectado leria "nada a receber" e acreditaria. Número errado
  com ar de número certo é pior que aviso de erro.

  Agora a abertura pergunta primeiro se há sessão e só então decide: com
  sessão, carrega; sem sessão, substitui o conteúdo por uma explicação e o
  botão de conectar. Enquanto o painel está visível não há número na tela para
  ser lido errado.

- **A sessão que expira com o app aberto virava um "Erro ao carregar
  pagamentos." vermelho.** Um gancho central em toda resposta 401 de `/api/`
  troca a tela pelo mesmo painel, e o erro deixa de aparecer: a explicação
  calma no meio da tela e um toque de alarme por cima são o pior dos dois
  mundos. Desconectar a conta também limpa a tela na hora, em vez de deixar o
  cadastro do operador anterior visível até a próxima requisição.

- **A primeira instalação anunciava "App atualizado! Recarregue".** O evento
  `updatefound` do Service Worker dispara igual na instalação inicial e numa
  atualização de verdade; sem distinguir os dois casos, a primeira abertura do
  app pedia ao operador uma ação que não servia para nada.

---

## [1.3.1] — 2026-09-05

Correção dos achados da auditoria de segurança e funcionamento do commit
`261ee44`. Dois bloqueios altos, quatro médios e um baixo — mais um bug de
observabilidade encontrado enquanto se testava outra coisa.

### Corrigido — os dois bloqueios altos

- **A leitura da API respondia sem sessão, incluindo o download do banco.** O
  guarda só barrava métodos que alteram estado, e todas as rotas que entregam
  dados pessoais em bloco são GET: `/api/clientes`, `/api/clientes/mapa`,
  `/api/pagamentos`, `/api/relatorios/exportar` e, no pior caso,
  `/api/backup/sqlite`, que devolve uma cópia integral do arquivo SQLite.
  Fechar a leitura não tira nada do operador — sem sessão ele já não cadastrava
  nem editava. `/api/health` entrou nas isenções porque a sonda de identidade
  roda antes de existir login.

- **A capacidade falhava em aberto.** `esta_ativa()` era
  `bool(token_esperado())`, então a ausência de `ADRI_API_TOKEN` no ambiente
  virava "pode entrar sem token": bastava o Electron falhar em repassar a
  variável ao processo filho para o servidor subir com a API inteira aberta,
  sem nada na interface indicando isso. Agora a exigência é sempre ligada e,
  quando a variável não vem pronta, o backend cai no mesmo `.capacidade` do
  perfil que o Electron já lê. Desligar virou opt-in por `ADRI_API_SEM_TOKEN=1`.

- **O guarda de autenticação não tinha teste.** `_verificar_autenticacao`
  começa com `if TESTING: return None` e a suíte inteira roda com o modo
  ligado — 599 testes verdes não provavam a regra mais básica do backend, e foi
  por isso que a folga acima sobreviveu. `test_autenticacao.py` desliga o modo
  e exercita os guardas na ordem real.

### Corrigido — privacidade e observabilidade

- **O log gravava o cadastro do cliente.** Os três tratadores de `HTTPError`
  em `asaas.py` registravam o corpo bruto da resposta, que numa recusa repete
  nome, CPF/CNPJ, e-mail e telefone — em `%APPDATA%`, sem cifragem. Agora vai
  só o código de erro do Asaas.

- **A migração levava embora o log do aplicativo.** Todo comando do Alembic
  carrega `migrations/env.py`, que chama `fileConfig` sobre o `alembic.ini` —
  e esse arquivo declara `[logger_root]` com `level = WARN` e
  `handlers = console`. `fileConfig` não acrescenta: substitui. O estrago era
  triplo e permanente pelo resto do processo: os loggers `adri.*` já criados
  eram desligados (`disable_existing_loggers` é `True` por padrão), o nível da
  raiz caía para WARNING (derrubando todo `log.info` do app) e o
  `RotatingFileHandler` sumia — com ele, o `app.log` em `%APPDATA%` parava de
  receber **qualquer coisa**, inclusive WARNING e ERROR.

  Como `servidor.py` importa `app` antes de preparar o banco, e a preparação
  roda `upgrade` em todo boot, isso valia para toda execução do aplicativo, não
  só para a que tinha migração pendente. Sumiam os avisos de `[AUTH]`,
  `[CAPACIDADE]` e `[SEGURANCA]` — a trilha em que a auditoria se apoia — e o
  log que o `QUICK_REFERENCE.md` manda o operador enviar. Falha silenciosa: o
  arquivo continuava lá, apenas vazio.

  A correção restaura a configuração do aplicativo em volta de cada chamada ao
  Alembic, em vez de mexer no `alembic.ini`: o `.ini` é o que faz o `alembic`
  na linha de comando ser legível, e quem invade configuração alheia é a
  chamada embutida.

### Adicionado

- **Conciliação automática com o Asaas.** O módulo estava correto, era
  idempotente e tinha rota pronta — e nada o acionava: a única chamada partia
  de um clique. O cliente pagava o Pix, o dinheiro entrava na conta do Asaas e
  a cobrança seguia "Pendente" até alguém lembrar. Agora roda na abertura e a
  cada 20 minutos, em silêncio, e a tela mostra quando foi a última conferência
  bem-sucedida.

### Alterado

- **A allowlist de nome, rua, bairro e cidade aceita `&`, `#`, `+` e `%`.**
  Barrava razão social comum ("Movéis & Cia", "Loja #2", "50% Decor") numa loja
  cuja clientela é em boa parte pessoa jurídica, sem ganho de segurança — os
  mesmos caracteres sempre passaram em `observacoes`. A mensagem de erro passou
  a dizer qual caractere foi recusado.

- **O teto de requisições subiu de 200/min para 2000/min.** O limite não
  defendia de ninguém: o guarda de host já recusa o que não vem de loopback,
  então quem apanhava era o próprio app — numa rajada de 250 GET, 124 voltavam
  429. O aperto foi para onde cada chamada gasta cota de terceiro: Gemini,
  emissão de cobrança, conciliação e upload ao OneDrive.

- **`servidor.py` avisa no boot quando a capacidade está exigida**, dizendo que
  abrir o endereço num navegador comum resulta em 403 e nomeando a variável que
  desliga a exigência. Sem isso o sintoma era uma tela que carrega e fica
  vazia, sem nada explicando por quê. `make dev` passou a definir a variável
  sozinho, porque é justamente o alvo que serve o backend a um navegador.

- **O webhook do Asaas deixou de ser recusado pelo guarda de host.** Ele já era
  isento da checagem de origem e da capacidade, mas levava 400 antes de o
  próprio token ser lido. Inofensivo hoje, porque nada chega de fora; armadilha
  no dia do relay público.

---

## [1.2.1] — 2026-09-02

Correção do job de instalador introduzido na 1.2.0, que reprovou na primeira
execução real.

### Corrigido

- **O CI construía o instalador e reprovava ao tentar publicá-lo.** O
  electron-builder detecta que está num CI e liga publicação implícita: o
  `.exe` ficava pronto e o passo falhava logo depois, sem token do GitHub.
  `--publish never` entrou no script `dist` do `package.json` — assim vale
  igual no CI e na máquina de quem empacota, e ninguém publica release por
  acidente.

### Alterado

- O job do instalador roda também na `develop`. A ideia original de poupar
  minutos rodando só na promoção invertia a ordem: quem descobria a quebra era
  a `main`, cuja regra é "se está aqui, funciona".
- Falha do empacotamento agora aparece na anotação do job, com as últimas
  linhas do log, e o log completo sobe como artefato. O log do passo só é
  acessível com direitos de admin no repositório — a informação existia e não
  alcançava quem precisava dela.

---

## [1.3.0] — 2026-09-02

Correção dos pontos levantados na reavaliação técnica do commit `fa78284`. O
foco são os três bloqueios que impediam operação financeira real.

### Corrigido — bloqueios financeiros

- **Emissão de cobrança podia travar para sempre.** `iniciada` era um estado
  absorvente: um processo encerrado entre reivindicar a emissão e chamar o
  Asaas deixava o pagamento respondendo 409 indefinidamente — a tentativa
  seguinte consultava o gateway, não achava cobrança nenhuma, e ainda assim
  não conseguia reivindicar. A única saída era mexer no banco à mão. A
  reivindicação passou a ser uma **concessão com prazo** (5 minutos): expirada,
  outra tentativa a retoma; viva, a exclusão mútua continua valendo.

- **O `PUT` era porta dos fundos da máquina de estados.** Aceitava `status` no
  corpo e gravava direto — dava para marcar "Recebido" sem passar pela
  conferência com o gateway. E aceitava alterar valor, vencimento e tipo de uma
  cobrança **já emitida**, deixando o boleto que o cliente tem na mão diferente
  do que o ERP mostra. A regra que impedia o estrago vivia no comportamento da
  tela; agora vive no backend.

- **Cancelamento podia divergir do Asaas.** Com cobrança no gateway e sem chave
  configurada, o sistema cancelava apenas localmente: o ERP dizia "cancelado",
  o cliente recebia a cobrança e pagava. E cobranças `Atrasado` não podiam ser
  canceladas, embora vencer não quite nem cancele nada — eram justamente as
  mais antigas que não podiam ser encerradas.

### Corrigido — integridade e segurança

- **A chave de idempotência passou a ser reservada antes da escrita.** Ela era
  gravada depois, em outra transação: um processo encerrado nessa janela
  deixava a escrita feita e a chave sem registro, e o reenvio da fila
  duplicava. Agora a intenção é registrada primeiro, e a repetição recua em vez
  de repetir. A reserva guarda também um **hash de método + rota + corpo**:
  reaproveitar a mesma chave para outra operação devolvia, em silêncio, a
  resposta da primeira.

- **O Qt deixou de ser o buraco na proteção da API local.** Ele sondava apenas
  se havia alguém na porta 5000 e não enviava cabeçalho nenhum — na prática, ou
  subia um backend **sem** exigência de token, desfazendo a proteção para todo
  mundo, ou tomava 403 ao tentar conversar com o backend do Electron. Agora lê
  o mesmo arquivo de capacidade das outras duas pilhas e a sonda pergunta
  *quem* está atendendo.

- **Os relatórios financeiros passaram a somar centavos.** Escrever em centavos
  e ler em ponto flutuante desfaz metade do trabalho: somar 300 parcelas de
  33,33 em IEEE 754 não devolve 9.999,00, e o total do dashboard não batia com
  a soma das linhas na tela.

### Adicionado

- **Releases automáticas.** Empurrar uma tag `v*` constrói o instalador, gera
  o **SHA-256** e publica um GitHub Release com o arquivo e o trecho
  correspondente do CHANGELOG. Existiam tags e a página de Releases estava
  vazia — quem quisesse o instalador precisava construí-lo. O checksum não
  substitui assinatura digital, mas é o mínimo verificável enquanto não há
  certificado.
- **Chaves de integração cifradas em repouso.** `ASAAS_API_KEY`,
  `GEMINI_API_KEY` e `ASAAS_WEBHOOK_TOKEN` saem do `.env` em texto puro e
  passam a viver cifradas com DPAPI, reusando a mesma infraestrutura que já
  protegia os tokens da Microsoft. A migração acontece na abertura do
  aplicativo, preservando o `.env` original como `.env.bak`.
- **O CI instala o instalador e o exercita**, em vez de apenas construí-lo. Ele
  verifica que o app instalado abre, exige a capacidade, recusa quem não a
  apresenta — e que o banco criado por ele chega à cabeça da cadeia de
  migrations. Um bundle sem `alembic.ini` responde `/api/health` normalmente;
  olhar só a resposta HTTP deixaria passar o defeito da 1.2.

---

## [1.2.0] — 2026-09-01

Correção dos pontos levantados no diagnóstico técnico do commit `c50c2ec`. As
mudanças de segurança e de integridade financeira são o centro desta versão.

### Corrigido — bloqueadores

- **Migração deixou de avançar sobre banco irrecuperável.** O backup de
  pré-migração podia falhar e a migração rodava assim mesmo; se a migração
  quebrasse no meio, o schema de emergência era aplicado por cima do banco
  parcialmente migrado e o app subia como se nada tivesse acontecido. Havia
  ainda um caso pior: banco legado (sem `alembic_version`) era classificado
  como "nada pendente" e migrava **sem backup** — justamente o banco com mais
  a perder. Agora o estado do arquivo é classificado antes de qualquer decisão,
  e banco com dados que falha na preparação impede o sistema de subir, com
  instruções de recuperação na tela.

- **Cobrança no Asaas passou a ser idempotente.** Se o processo morresse entre
  criar a cobrança e gravar o id, a cobrança existia no gateway e o sistema não
  sabia — o operador clicava de novo e o cliente recebia duas cobranças do
  mesmo valor. Nada impedia clique duplo, requisições simultâneas, ou emissão
  sobre pagamento já cobrado ou já recebido. A intenção agora é registrada
  antes da chamada de rede, com referência externa que permite perguntar ao
  Asaas se a tentativa anterior chegou a criar algo.

- **Conciliação ativa com o Asaas.** O webhook nunca chega numa instalação
  normal: o backend escuta em loopback e um servidor na internet não alcança
  esse endereço. O cliente pagava, o dinheiro entrava na conta do Asaas e a
  cobrança seguia "Pendente". O sistema agora pergunta ao gateway o estado das
  cobranças em aberto — consulta de saída atravessa firewall e não expõe nada.

- **Fila offline deixou de perder e de recriar alterações.** Editar um cliente
  criado offline apagava a edição (PUT contra id negativo → 404 → descarte
  silencioso); excluir um cliente temporário o fazia reaparecer; reenviar podia
  criar o mesmo cliente duas vezes; e qualquer recusa definitiva apagava o
  trabalho sem aviso.

- **API local fechada para quem não é o aplicativo.** `curl
  http://127.0.0.1:5000/api/clientes` devolvia a lista inteira de clientes, com
  nome, endereço e CEP, para qualquer processo da máquina.

- **.NET passou a usar banco próprio.** Duas pilhas escreviam no mesmo SQLite
  com domínios e sistemas de migração diferentes.

### Corrigido — financeiro e dados

- Confirmação manual de pagamento agora confere com o Asaas antes de marcar
  como recebido. Forçar exige motivo, e o motivo vai para a auditoria.
- Cancelar cobrança marca `Cancelado` em vez de apagar a linha.
- **Dinheiro em centavos inteiros** (`pagamentos.valor_centavos`). O rateio de
  parcelas já era exato, mas o faturamento entregava o resultado a
  `pagamentos` passando por `round(centavos / 100, 2)` — e três parcelas de um
  pedido de R$ 100,00 deixavam de somar R$ 100,00 em ponto flutuante binário.
  `valor` continua sendo gravado durante a transição.
- **Chaves estrangeiras reais** em `pagamentos.pedido_id` e
  `entregas_agendadas.pedido_id`. Elas foram acrescentadas por `ALTER TABLE`, e
  SQLite não aceita adicionar constraint por ALTER: nada impedia uma parcela
  apontando para um pedido inexistente.
- Exportações CSV e XLSX neutralizam texto que o Excel interpretaria como
  fórmula.
- `.xls` deixou de ser aceito na importação com uma mensagem que explica o que
  fazer — a extensão era aceita e o leitor não suporta o formato.

### Adicionado

- **Restauração de backup pela interface**, com verificação de integridade
  antes da troca e salvaguarda do estado atual. Backup sem restauração testada
  é suposição, não garantia.
- **Cópia de backup para um segundo destino** (`ADRI_BACKUP_EXTRA`).
- **Fila de erros visível** para alterações offline recusadas, com reenvio e
  descarte.
- **19 testes ponta a ponta** rodando o JavaScript da interface num navegador
  de verdade (Playwright). O resto da suíte verificava o front-end lendo os
  arquivos e procurando trechos de texto — isso pega "o seletor sumiu do
  HTML" e não pega nada do que acontece quando o código roda.
- **Paginação na lista de clientes** (200 por página, com contagem do total).
  A tela baixava e desenhava todos os registros de uma vez.
- `SECURITY.md`, `PRIVACIDADE.md`, `LICENSE`, `CODEOWNERS`, este arquivo e o
  primeiro ADR (`docs/adr/`), registrando por que o .NET deixou de escrever
  no banco de produção.
- CI: `npm audit`, auditoria de pacotes NuGet, cobertura mínima de 80%,
  auditoria do `requirements.lock`, checksum do binário do gitleaks, actions
  fixadas por SHA e **construção do instalador**, que nunca era exercitada.

- **O aplicativo instalado nunca aplicou uma migration.** `alembic/env.py`
  chama `logging.config.fileConfig`, e o PyInstaller não enxergava esse import
  — ele está dentro do `env.py`, carregado como script em tempo de execução.
  Toda migração falhava no executável empacotado com
  `No module named 'logging.config'`, e o backend caía no schema de emergência
  em silêncio. O defeito só aparecia na máquina de quem instalasse, e foi
  encontrado ao construir o instalador pela primeira vez.
- O `package.json` passou a entrar no bundle: sem ele, o app instalado se
  identificava com versão "desconhecida" na sonda que o Electron usa para
  reconhecer o próprio backend.

### Segurança

- Validação do host contra a lista de apelidos de loopback (DNS rebinding).
- Rotação dos arquivos de log — antes um único `app.log` crescia sem limite.
- Dependências Node atualizadas: 14 vulnerabilidades (13 altas, 1 crítica) na
  cadeia do `electron-builder` e no próprio Electron, agora em zero.
- Duas vulnerabilidades altas em pacotes NuGet transitivos, que ninguém via
  porque o CI nunca auditou o lado .NET: `SQLitePCLRaw.lib.e_sqlite3`
  (GHSA-2m69-gcr7-jv3q, via EF Core) e `Tmds.DBus.Protocol`
  (GHSA-xrw6-gwf8-vvr9, via Avalonia). As versões corrigidas passaram a ser
  declaradas explicitamente.

---

## [1.1.0] — 2026-09-01

### Adicionado

- **Módulo Pedido**: catálogo de produtos, pedidos com itens, máquina de
  estados explícita (`rascunho → aberto → aprovado → faturado`) e faturamento
  transacional que gera as parcelas a receber.
- **Agenda de entregas** ligada ao pedido, com visão de agenda e de tabela.
- **Backup automático do banco**: antes de cada migração e uma vez por dia,
  usando a API online do SQLite com verificação de integridade.
- Dinheiro em centavos nas tabelas novas, com rateio de parcelas sem perder
  centavo.

### Corrigido

- Backup que dizia ter funcionado e não funcionava — a função apontava para uma
  rota inexistente e `window.open` não enxerga o 404.
- Importação em lote inalcançável: o modal não tinha botão que a executasse.
- Leitura offline quebrada: o Service Worker respondia 200 com `{offline:true}`
  e a tela tentava filtrar um objeto.
- Indicador de filtro que nunca era atualizado.
- `server_default="''"` na migração inicial gerava `DEFAULT ''''''`, e o segundo
  recebimento cadastrado numa instalação nova falhava com HTTP 500.

---

## [1.0.0] — 2026-08

Primeira versão em produção: cadastro de clientes, pagamentos com Asaas,
dashboard, mapa, relatórios, notificações, exportação para o OneDrive e
interface renovada em Electron.

[1.2.1]: https://github.com/pedromatheuszz/Adri-Poltronas/releases/tag/v1.2.1
[1.3.0]: https://github.com/pedromatheuszz/Adri-Poltronas/releases/tag/v1.3.0
[1.2.0]: https://github.com/pedromatheuszz/Adri-Poltronas/releases/tag/v1.2.0
[1.1.0]: https://github.com/pedromatheuszz/Adri-Poltronas/releases/tag/v1.1.0
