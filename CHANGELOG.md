# Registro de mudanças

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento [semântico](https://semver.org/lang/pt-BR/).

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
- `SECURITY.md`, `PRIVACIDADE.md`, `LICENSE`, `CODEOWNERS` e este arquivo.
- CI: `npm audit`, auditoria de pacotes NuGet, cobertura mínima de 80%,
  auditoria do `requirements.lock`, checksum do binário do gitleaks, actions
  fixadas por SHA e **construção do instalador**, que nunca era exercitada.

### Segurança

- Validação do host contra a lista de apelidos de loopback (DNS rebinding).
- Rotação dos arquivos de log — antes um único `app.log` crescia sem limite.
- Dependências Node atualizadas: 14 vulnerabilidades (13 altas, 1 crítica) na
  cadeia do `electron-builder` e no próprio Electron, agora em zero.

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

[1.2.0]: https://github.com/pedromatheuszz/Adri-Poltronas/releases/tag/v1.2.0
[1.1.0]: https://github.com/pedromatheuszz/Adri-Poltronas/releases/tag/v1.1.0
