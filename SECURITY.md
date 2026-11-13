# Segurança

## Como relatar uma vulnerabilidade

**Não abra uma issue pública.** Uma issue neste repositório é visível para
qualquer pessoa, e uma falha descrita ali fica disponível antes de existir
correção.

Use um destes canais:

1. **Preferido** — [Security Advisories](https://github.com/pedromatheuszz/Adri-Poltronas/security/advisories/new),
   na aba *Security* do repositório. O relato fica privado até a publicação.
2. E-mail para o mantenedor, listado no perfil do GitHub.

Inclua, na medida do possível: a versão afetada, o passo a passo para
reproduzir, o impacto que você enxerga e qualquer prova de conceito.

**Resposta em até 7 dias.** Este é um projeto de um mantenedor só — o prazo é
o que dá para sustentar honestamente, não o de uma equipe dedicada.

## O que está no escopo

| | |
|---|---|
| ✅ | O backend Flask (`backend/`) e as APIs que ele expõe |
| ✅ | O processo principal do Electron (`electron/`) e a configuração da janela |
| ✅ | O tratamento de credenciais: Microsoft, Gemini, Mercado Pago |
| ✅ | O banco local e os backups |
| ✅ | A cadeia de build e o instalador |
| ❌ | O aplicativo `.NET/Avalonia` (`dotnet/`) — exploração arquitetural, não distribuída |
| ❌ | A janela Qt (`qt-app/`) — interface alternativa, não distribuída |
| ❌ | Serviços de terceiros (Microsoft Graph, ViaCEP, Nominatim, Mercado Pago) — relate a eles |

## Versões suportadas

| Versão | Situação |
|---|---|
| 1.5.x | Suportada |
| < 1.5 | Sem suporte |

## O modelo de ameaça, e seus limites

Ser franco sobre o que o produto **não** protege vale mais do que uma lista de
boas intenções. O Adri Poltronas é um aplicativo desktop de um único
computador, e isso define o que é defensável:

### O que é tratado

- **A API local não responde a estranhos.** O backend escuta em
  `127.0.0.1:5000`, e loopback não é privado: qualquer processo da máquina e
  qualquer página aberta no navegador do usuário alcançam essa porta. Toda
  requisição precisa apresentar um segredo que só o aplicativo conhece
  (`backend/capacidade.py`).
- **DNS rebinding.** O nome do host é validado contra a lista de apelidos de
  loopback, em vez de ser inferido do próprio cabeçalho `Host`.
- **Login e autorização locais.** A API de negócio exige cookie de sessão
  `HttpOnly` e conta ativa. Senhas locais são armazenadas como hashes bcrypt;
  novas contas exigem ao menos 12 caracteres. O perfil é conferido no servidor:
  só o desenvolvedor pode administrar contas e períodos de teste.
- **Tokens da Microsoft cifrados em repouso**, com DPAPI no Windows.
- **As cópias de segurança saem cifradas da máquina.** Os backups automáticos
  (diário e de pré-migração, incluindo a cópia extra de `ADRI_BACKUP_EXTRA`)
  são gravados com Fernet, e a chave vive protegida pelo DPAPI da conta do
  Windows. Um pendrive com uma cópia dentro não abre em outro computador nem
  em outra conta. A cópia para download sai em claro por ser uma exportação
  deliberada do operador — a mesma natureza do backup JSON de clientes.
- **A cópia externa só recupera um computador perdido se houver senha.** Com
  `ADRI_BACKUP_SENHA` definida (12 caracteres ou mais), o que vai para
  `ADRI_BACKUP_EXTRA` é cifrado com uma chave derivada dela (scrypt) e abre em
  qualquer máquina que tenha o arquivo e a senha. Sem a senha, a cópia externa
  é um duplicado da local — presa a esta conta do Windows, inútil depois de um
  roubo ou de um disco morto — e o log avisa a cada cópia. A senha precisa ser
  anotada fora do computador: no aplicativo ela fica no cofre DPAPI.
- **A chave das cópias nunca é sobrescrita.** Se `.fernet_key` deixar de abrir
  (senha do Windows redefinida, perfil migrado), o arquivo é renomeado para
  `.fernet_key.ilegivel-<data>` em vez de substituído: as cópias antigas
  voltam a abrir se a conta voltar a decifrá-lo.
- **Banco em pasta de rede é recusado no boot.** O SQLite sobre SMB corrompe.
  O aplicativo não abre com o banco em compartilhamento (UNC ou unidade
  mapeada) sem a variável explícita `ADRI_PERMITIR_BANCO_EM_REDE=1` — e quem
  a define assume, por escrito, a corrupção documentada.
- **Disco sem BitLocker bloqueia a abertura, quando dá para saber.** O sistema
  consulta o estado do volume antes de abrir o banco e recusa iniciar quando
  o Windows confirma que a proteção está desligada. `ADRI_PERMITIR_BANCO_SEM_BITLOCKER=1`
  é uma exceção explícita. Se o Windows não permitir verificar, o aplicativo
  registra a limitação e segue; por isso a criptografia do disco continua sendo
  responsabilidade operacional.
- **Trilha de auditoria append-only**, protegida por gatilhos no banco, com
  valores sensíveis removidos.
- **Janela isolada**: `contextIsolation`, sandbox, sem integração com Node,
  navegação externa bloqueada.
- **Rotas externas limitadas.** Desde a 1.5.0 não há webhook: a verificação
  do pagamento da licença é feita perguntando ao Mercado Pago, de dentro para
  fora. `/callback` recebe o retorno OAuth e `/api/health` identifica o
  backend; nenhuma delas devolve dados de negócio. Ambas continuam restritas
  ao host de loopback.
- **Segredos fora do repositório e cifrados em repouso**: o `MP_ACCESS_TOKEN`
  e a `GEMINI_API_KEY` vivem em `%APPDATA%\AdriPoltronas\.segredos`,
  protegidos por DPAPI. Uma chave em texto no `.env` é migrada automaticamente
  na próxima abertura, e a cópia em texto claro é descartada depois que o cofre
  é relido e conferido.
- **Allowlist Microsoft, quando configurada.** `ADRI_CONTAS_AUTORIZADAS`
  restringe quais contas Microsoft podem vincular o OneDrive. Isso não cria
  login local nem concede perfil no ERP.

### O que **não** é tratado — e por quê

- **Outro processo rodando como o mesmo usuário.** Ele já pode abrir o banco
  SQLite diretamente, ler o `.env` e o arquivo de capacidade. Nenhum controle
  dentro do aplicativo muda isso; quem defende essa fronteira é o sistema
  operacional.
- **As chaves cifradas não resistem a código rodando como você.** O DPAPI
  protege contra outra conta do Windows e contra o arquivo sair da máquina;
  um processo executando com a sua identidade pode simplesmente pedir que ele
  decifre. É a mesma fronteira do arquivo de capacidade.
- **O arquivo SQLite não usa SQLCipher.** O banco contém nome, endereço e CEP
  de clientes reais. A proteção em repouso depende da criptografia do volume;
  o app bloqueia quando consegue confirmar que ela está desligada. Consultas
  inconclusivas ainda permitem iniciar. As cópias automáticas saem cifradas;
  exportações deliberadas podem conter dados em claro.
- **O limite de confiança é o usuário do Windows.** As permissões locais
  impedem que uma conta comum use a área de desenvolvedor pela API do
  aplicativo, mas não protegem os arquivos contra outro processo executado
  pela mesma conta do Windows. Uma pessoa com essa identidade pode ler ou
  alterar o banco diretamente.

- **A licença central é uma barreira comercial, não inviolável.** O servidor
  central guarda os estados de teste/pagamento e o ERP consulta a API por HTTPS.
  O estado local dá até 72 horas de operação offline após validação. O dono do
  computador ainda controla o executável local e pode adulterá-lo; não se deve
  prometer proteção contra engenharia reversa.
- **O token administrativo da licença não vai aos clientes.** Só o backend da
  máquina do vendedor deve receber `ADRI_LICENCA_ADMIN_TOKEN`. Os clientes
  autenticam sua própria consulta com um segredo aleatório por conta, cujo hash
  fica no serviço central.
- **O instalador segue não assinado até existir certificado.** O Windows
  exibe o aviso do SmartScreen na instalação. Desde a 1.5.2 existe o caminho
  pronto para mudar isso: `python build.py assinar` (ver BUILD_GUIDE.md),
  que assina instalador e backend com o certificado do vendedor e confere a
  assinatura no fim. Enquanto nenhum certificado é configurado, o comando
  explica o que falta em vez de falhar em silêncio.
- **Vários computadores compartilhando a mesma base** não são suportados. O
  SQLite em pasta de rede corrompe — e desde a 1.5.2 o aplicativo se recusa
  a abrir nessa configuração, em vez de abrir e corromper depois.

### Contas e perfis

- Na primeira execução de uma instalação comum, o usuário cria uma conta
  regular. O perfil de desenvolvedor exige a chave privada do fornecedor e
  fica vinculado ao hash da identidade Windows deste computador, cifrado no
  cofre DPAPI, e ao histórico recente de IPs públicos. Um IP compartilhado não
  basta para entrar; um IP novo precisa também de validação da chave privada
  na API central. Não existe senha padrão nem credencial desenvolvedora
  embutida no código.
- Usuários podem criar a própria conta; o cadastro público só aceita o perfil
  comum. Administrador e desenvolvedor são criados ou gerenciados pelo
  desenvolvedor.
- Usuário e administrador acessam as áreas comuns. A área de desenvolvedor e
  o controle de contas/períodos de teste são exclusivos do perfil
  desenvolvedor, com checagem repetida no backend.
- A central vincula cada licença ao identificador do Windows. Só a primeira
  conta por instalação recebe teste automático; contas seguintes aguardam
  liberação manual. A API limita a três novas instalações em teste por IP a
  cada 30 dias e guarda somente um hash pseudônimo desse IP.
- A conexão Microsoft é opcional e serve à integração com o OneDrive. Ela não
  substitui o login local nem altera o perfil local.

## Se você encontrou um segredo neste repositório

O `gitleaks` roda em cada push, mas nenhuma varredura é perfeita. Se você achar
uma chave em algum commit, relate pelo canal privado acima **e considere-a
comprometida**: um segredo que entrou no histórico do Git continua acessível
mesmo depois de removido do último commit. A correção é rotacionar a chave, não
apagar o arquivo.
