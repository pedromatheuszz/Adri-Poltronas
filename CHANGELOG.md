# Registro de mudanças

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento [semântico](https://semver.org/lang/pt-BR/).

---

## [1.5.1-beta] — 2026-09-12

Correções da auditoria técnica da 1.5.0 (41 achados: 2 altos, 18 médios,
17 baixos, 4 informativos). Nenhuma funcionalidade nova além do destino das
parcelas, que fecha um ciclo que a 1.5.0 deixou pela metade.

### Corrigido — alta severidade

- **Uma queda de rede apagava a sessão e trancava o operador fora do banco.**
  `renovar_token()` já distinguia "a Microsoft recusou" de "não consegui falar
  com a Microsoft", mas devolvia `None` nos dois casos, e o chamador apagava a
  sessão em ambos. Roteador reiniciando, Wi-Fi ainda não conectado ou máquina
  saindo de suspensão bastavam: a partir daí toda rota `/api/` respondia 401 e
  a única saída era refazer o login OAuth no navegador. Um ERP que anuncia
  funcionar offline virava um aplicativo que não abre. Agora só uma recusa
  explícita apaga a sessão; timeout e resposta ilegível (o portal cativo de
  Wi-Fi público, que responde 200 com HTML) preservam.

- **Faturar gerava dinheiro a receber que nenhuma tela mostrava.** A 1.5.0
  removeu a aba Pagamentos e não removeu o faturamento: as parcelas eram
  criadas, `faturado` é estado terminal, e não havia onde ver, conferir ou dar
  baixa. Dois textos da interface ainda mandavam procurar "a aba Pagamentos".
  As parcelas passam a viver **dentro do próprio pedido**, com baixa manual via
  `PATCH /api/pedidos/<id>/parcelas/<n>`.

### Corrigido — integridade e concorrência

- **Toda escrita passou a travar o duplo clique, não só o faturamento.** O
  backend recusa a segunda de duas requisições concorrentes sobre o mesmo
  registro, o que fecha a duplicidade no banco — mas resolvia só metade: sem
  travar na tela, o operador que clicasse duas vezes em Abrir, Aprovar,
  Cancelar, dar baixa numa parcela ou mudar o status de uma entrega levava um
  409 vermelho. Trocar uma falha silenciosa por uma confusa não é progresso.
  As cinco ações agora compartilham um guarda por registro (`_umaDeCadaVez`),
  com a chave carregando o ID — travar "aprovar" inteiro impediria aprovar
  dois pedidos diferentes em sequência, que é uso legítimo.

- **Duplo clique no faturamento emitia dois conjuntos de parcelas.** O
  `sqlite3` do Python só abre transação na primeira escrita, então a leitura da
  situação acontecia fora de qualquer transação; com `threaded=True`, dois
  cliques viravam duas threads que liam `aprovado` e gravavam as duas. Um
  pedido de R$ 100,00 em 3x virava seis lançamentos somando R$ 200,00. A
  transição agora é condicional (`WHERE situacao = ?`), o que vale para todas
  as transições, e o botão trava durante o envio.

- **Corrida na numeração de pedido virava 500.** Dois cadastros simultâneos
  liam o mesmo último número; o índice único recusava o segundo e o handler
  genérico devolvia erro opaco. Agora reemite o número seguinte. A corrida
  equivalente no código de produto passa a devolver a mesma mensagem da
  checagem prévia, como 400.

- **Excluir cliente não checava vínculo nenhum**, deixando pedido em aberto e
  parcela pendente órfãos de um cliente invisível — e o pedido passava a
  recusar edição com um 404 que não tinha nada a ver com ele.

- **Entrega podia apontar para pedido de outro cliente**, ou para um pedido em
  rascunho ou cancelado.

- **Cancelar pedido não cancelava as entregas dele**, que seguiam gerando
  "ENTREGA ATRASADA" para um pedido morto.

### Corrigido — o schema que as instalações novas recebem

- **Os `DEFAULT` de `status` e `tipo_pagamento` gravavam o valor entre aspas.**
  A migration inicial declarou `server_default="'Pendente'"`; para o
  SQLAlchemy uma `str` ali é um *valor a ser aspeado*, não SQL cru — quem quer
  SQL cru usa `sa.text(...)`. O DDL saiu `DEFAULT '''Pendente'''` e o SQLite
  passou a gravar a string `'Pendente'`, com apóstrofos dentro.

  Nenhum erro era levantado: os filtros simplesmente não encontravam nada. Em
  toda instalação nova, `cancelar_pedido` não cancelava entrega alguma e a
  trava de exclusão de cliente não enxergava parcela pendente — ou seja, duas
  correções desta mesma versão nasciam inertes exatamente onde precisavam
  valer. A migration `b7f21c9e4a05` corrige o `DEFAULT` e desaspeia as linhas
  já gravadas. O banco de produção não tem o problema (veio do caminho legado),
  e por isso a correção é condicional.

  A causa de nada ter pego isso: a suíte montava o banco por `criar_tabela()`
  → `schema_fallback`, que estava correto. O caminho das *migrations* — o de
  toda instalação real — não era exercitado por teste funcional nenhum.
  `tests/test_migrations_schema.py` fecha a lacuna, inclusive com um teste que
  falha se os dois schemas voltarem a divergir num `DEFAULT`.

- **Parcela antiga sem pedido tornava o cliente inexcluível para sempre.** As
  parcelas são lidas e baixadas *dentro* do pedido que as emitiu, então uma
  linha sem `pedido_id` não aparece em tela nenhuma — e a mensagem mandava
  "conclua ou cancele" algo que o operador não tinha como achar. Nenhum
  caminho de escrita atual produz uma dessas (`inserir_parcela` exige o pedido
  e é o único `INSERT` em `pagamentos`), mas bancos anteriores à 1.5.0 têm. A
  trava agora conta essas linhas à parte e diz explicitamente que a interface
  não as resolve. `'Atrasado'` também passou a contar: o código nunca grava
  esse status — o atraso é derivado do vencimento —, mas versões anteriores
  gravavam, e uma parcela vencida é mais devida, não menos.

### Corrigido — segurança e privacidade

- **Allowlist de contas** (`ADRI_CONTAS_AUTORIZADAS`). Vazia, o comportamento é
  o histórico: qualquer conta Microsoft entra. Preenchida, fecha o cenário do
  colaborador que conecta a conta pessoal e passa a poder tudo.

- **A migração do cofre deixava a chave em texto claro ao lado.** O `.env.bak`
  ficava para sempre, com o `MP_ACCESS_TOKEN` legível, na mesma pasta do banco.
  Agora é descartado — mas só depois de reler o cofre e conferir cada chave.

- **Consentimento explícito para o mapa.** Abrir a aba enviava o endereço
  completo de todos os clientes ao Nominatim/OpenStreetMap. O aviso existia; o
  que faltava era poder recusar e poder apagar as coordenadas guardadas.

- **Leaflet e Chart.js deixaram de vir de CDN.** Num aplicativo desktop, isso
  significava mapa e gráficos em branco na primeira abertura sem internet — o
  Service Worker só ajudava a partir da segunda — e, pior, uma CSP que
  autorizava `unpkg.com` e `cdn.jsdelivr.net` a **executar código** dentro de
  um programa que trata nome, endereço e valores a receber dos clientes. As
  duas passaram para `frontend/vendor/`, conferidas byte a byte contra os
  hashes SRI que já estavam no HTML, e `script-src` voltou a ser só `'self'`.

- **A conferência que autorizava apagar o `.env.bak` não lia o cofre.** Ela
  usava `obter()`, cujo último degrau é `return do_ambiente_real or padrao` — e
  em produção o `load_dotenv()` já colocou as chaves em `os.environ` com o
  mesmo valor que está sendo migrado. Se o DPAPI cifrasse e **não** conseguisse
  decifrar de volta, o cofre devolvia vazio, a função caía nesse último degrau
  e a conferência "passava": o `.env` já reescrito sem as chaves, mais a cópia
  apagada, davam perda irrecuperável das credenciais. Agora a conferência
  consulta `_ler_cofre()` diretamente, que é a única fonte que responde a
  pergunta certa.

- **Revogar o mapa não desfazia o que já estava na tela.** Os marcadores
  continuavam no DOM, cada um com nome e endereço no popup, e uma
  geocodificação já em voo regravava em disco as coordenadas que o operador
  acabara de mandar apagar — o guarda de geração do laço só é consultado
  *depois* do `await`, e a gravação acontece antes. A revogação agora invalida
  a geração, remove os marcadores, e `guardarGeocache()` recusa gravar sem
  consentimento, fechando o caso para qualquer caminho futuro.

- **A allowlist não existia no `.env` da máquina instalada.** Ela estava só no
  `.env.example`, que fica no repositório e não entra no bundle. O controle
  nascia desligado e sem nenhum lugar onde a operadora descobrisse que existe.
  Foi para o `config._MODELO_ENV`, junto de `ADRI_BACKUP_EXTRA`, e um teste
  agora exige que toda variável do `.env.example` seja classificada como
  configurável na instalação ou como só-para-desenvolvimento.

- **`/api/auth/status` dizia "conectado" para conta que a allowlist recusaria.**
  A rota está em `ROTAS_SEM_AUTH` — precisa estar —, então o guarda de `/api/`
  não roda nela. A tela anunciava "Conectado (fulano)" no boot e a primeira
  requisição de dados recusava aquela mesma conta.

- **O 403 da allowlist chegava como erro genérico.** É o mesmo status que a
  capacidade usa para "Acesso negado.", então a tela não tinha como separá-los.
  O backend passou a enviar `codigo: "conta_nao_autorizada"` e a interface
  explica o motivo em vez de mandar reconectar a conta recusada.

- `.capacidade` entrou no `.gitignore`; `ci.yml` declara `permissions: contents: read`;
  a cópia do banco para download usa `tempfile.mkstemp()`.

### Removido

- **Quase metade de `security.py`** (165 dos 342 comandos): CSRF de uso único,
  gerenciador de sessão, sanitizadores, `validar_sql_safe`, assinatura HMAC,
  detecção de anomalia, detecção de força bruta e o par PBKDF2
  `hash_senha`/`verificar_senha`. Nada disso era chamado por rota nenhuma. O ritual do
  CSRF existia completo nas duas pontas para uma validação que nunca acontecia
  — quem protege é a checagem de `Origin`/`Referer` —, e
  `esta_bloqueado_bruteforce()` sempre devolvia `False` porque o contador nunca
  era incrementado.

- **Cinco variáveis de "segurança avançada" do `.env.example`** que nenhuma
  linha do backend lia. Quem preenchesse a allowlist de IP acreditava ter
  restringido o acesso, e não havia restringido nada.

- **Resíduos da saída do Asaas**: o módulo `erp/financeiro/` inteiro (que
  consultava uma coluna apagada do schema), o `hiddenimport` inexistente no
  `.spec`, a fixture órfã de teste e os comentários que descreviam a máquina
  de cobrança removida.

- **Dez funções de `database.py` sem chamador em produção**, mais os três
  auxiliares que só elas usavam. O arquivo caiu de 988 para 717 linhas, e a
  cobertura global subiu de 82% para 84% — o código morto era testado, e era
  ele que puxava o número para baixo. As últimas três (`listar_pagamentos`,
  `salvar_pagamento`, `obter_metricas_pagamentos`) tinham sido preservadas
  para uma eventual tela de contas a receber; com a decisão de manter o
  escopo atual, saíram também.

### Desempenho

- A importação de planilha materializava o arquivo três vezes e só conferia o
  teto de linhas depois do parse completo. Agora mede sem ler, usa
  `read_only=True` no openpyxl e corta durante a leitura.
- A exportação carregava a base inteira para filtrar N clientes.
- `notificacoes_lidas` nunca era expurgada.

### Documentação

- README, `SECURITY.md`, `API_STANDARD.md` e `PRIVACIDADE.md` descreviam o
  produto de duas versões atrás — abas, integrações e rotas removidas na 1.5.0.
  O `PRIVACIDADE.md` era o mais grave: declarava o gateway como destino de dado
  pessoal e listava uma tabela que a migration já havia apagado.

### Build e CI

- **A verificação de conteúdo do bundle não olhava para `frontend/`.** Conferia
  `alembic.ini`, `migrations` e `templates` — e nada mais. Com `script-src
  'self'` e o precache de CDN removido, não há mais fallback: se
  `frontend/vendor/` não chegasse ao instalador, o app abriria normal e o mapa
  e os gráficos ficariam em branco **em silêncio**. Os arquivos do frontend
  entraram na lista.

- `python build.py lint` lintava `backend/` e `tests/` mas não `build.py`, então
  passava verde num arquivo que o job de teste reprovaria — exatamente o que o
  comando local existe para evitar.

### Testes

- `test_concorrencia.py`, `test_contrato_da_interface.py`, `test_autorizacao.py`
  e `test_configuracao.py` são novos. O primeiro roda threads de verdade com
  barreira de largada; o segundo lê a interface e a documentação como texto e
  falha quando elas apontam para algo que não existe — a classe de defeito que
  nenhum teste de backend pegaria.
- `conftest.py` gera uma `FERNET_KEY` efêmera: a suíte deixa de exigir Windows
  e para de tocar na chave DPAPI real do desenvolvedor.
- `ruff.toml` liga as regras `S`, `B` e `UP`. Sem configuração, o ruff nunca
  aplicou a regra de SQL — uma consulta concatenando entrada do usuário passava
  pelo pipeline sem reclamação.

## [1.5.0-beta] — 2026-09-05

Remoção do Asaas e das áreas Financeiro e Análise. É uma **regressão
deliberada de escopo**: funcionalidade que existia sai do produto enquanto a
base de cobrança é repensada.

### Removido

- **A integração com o Asaas, por inteiro.** Cliente HTTP, emissão idempotente
  de Pix e boleto, conciliação automática e o webhook. Com ele saem as
  credenciais `ASAAS_API_KEY`, `ASAAS_SANDBOX` e `ASAAS_WEBHOOK_TOKEN`.

- **A aba Pagamentos e a aba Relatórios**, e com elas as rotas `/api/pagamentos`
  e `/api/relatorios`. O registro local de pagamento funcionava sem gateway,
  mas a **confirmação** não: conferir o recebimento contra o Asaas era o que
  impedia o ERP de declarar receita que ninguém recebeu — um dos bloqueios
  financeiros que a auditoria da 1.3.1 apontou. Sem gateway sobrava a versão
  sem lastro do mesmo problema.

- **Os indicadores financeiros e o gráfico de receita do Dashboard**, e as
  notificações de pagamento vencido e vencendo hoje.

- **As colunas do gateway e a tabela `clientes_asaas`** (migration
  `e5c94a17b3d8`). Isso descarta dados, e foi aplicado sabendo disso: o
  aplicativo ainda não foi entregue a nenhum cliente, então não existe cobrança
  emitida em lugar nenhum.

### O que ficou, e por quê

- **A tabela `pagamentos`.** O módulo Comercial gera as parcelas de um pedido
  como linhas nela, e `pagamentos` tem chave estrangeira para `pedidos`.
  Removê-la quebraria Pedidos, que não estava no escopo. `tipo_pagamento`
  também fica: "Pix", "Boleto" e "Dinheiro" descrevem como o dinheiro chegou, e
  isso continua verdade sem gateway.

### Segurança

Some o webhook, e com ele o único caminho pelo qual algo da internet falava com
este backend. As isenções que existiam só para ele caíram junto — as de
capacidade passaram de três rotas para duas, e `ROTAS_QUE_CHEGAM_DE_FORA` ficou
vazia.

### Notas de teste

A suíte foi de 751 para 580 testes. Os que sumiram cobriam o que deixou de
existir. Dois foram **adaptados** em vez de removidos, porque a cobertura era
de outra coisa e só usava o financeiro como cenário: as notificações passaram a
se apoiar em entregas atrasadas, e a censura de segredos na auditoria passou a
ser exercitada pelo mecanismo (`registrar_evento` com campo sensível) em vez de
por colunas específicas de cobrança.
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
