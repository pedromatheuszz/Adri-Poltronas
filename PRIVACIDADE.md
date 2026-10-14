# Dados pessoais, retenção e LGPD

Este documento existe porque o sistema guarda **dados pessoais de clientes
reais** — nome, endereço completo e CEP — e até aqui não havia nada escrito
sobre o que é feito com eles. Sem isso, cada decisão sobre exportar, enviar ou
apagar era tomada no improviso.

Ele descreve o comportamento real do software. Não é parecer jurídico.

## Que dados o sistema guarda

| Dado | Onde | Por que |
|---|---|---|
| Nome, CEP, rua, bairro, cidade | `clientes` | Identificar e entregar |
| Observações livres | `clientes` | Anotações da equipe |
| Valores, vencimentos, status das parcelas | `pagamentos` | Conferência do recebimento |
| Endereço e horário de entrega | `entregas_agendadas` | Agenda da equipe |
| Pedidos e itens | `pedidos`, `pedido_itens` | O que foi vendido |
| Ações realizadas | `historico`, `auditoria_eventos` | Rastreabilidade |
| Nome de usuário, e-mail opcional, perfil e hash da senha | `usuarios` | Login local e controle de acesso |
| Conta Microsoft conectada | `sessao` | Exportar para o OneDrive |
| Chaves de integração (Mercado Pago, Gemini) | `.segredos` | Cifradas com DPAPI |

**O que o sistema NÃO guarda:** CPF/CNPJ, telefone, dados de cartão ou senha
em texto claro. As senhas das contas locais são armazenadas somente como
hashes bcrypt.

A tabela `clientes_asaas`, que guardava o identificador do cliente no gateway
de cobrança, foi apagada do banco pela migração `e5c94a17b3d8` junto com a
integração, na versão 1.5.0. Ela não existe mais em instalação nenhuma.

**IP não é guardado em texto.** A auditoria registra um hash derivado do IP com
o segredo da instalação (`anonimizar_ip`), o que permite correlacionar sessões
sem preservar o endereço.

## Onde os dados ficam

Tudo em **um arquivo SQLite** na máquina do usuário:

```
%APPDATA%\AdriPoltronas\adri_poltronas.db
%APPDATA%\AdriPoltronas\backups\        cópias automáticas
%APPDATA%\AdriPoltronas\logs\           registro de execução
```

Os dados comerciais do ERP permanecem na máquina local. Para controlar a
licença entre computadores, a instalação pode sincronizar com a API central
descrita em `licensing-service/README.md`.

## Quando dados saem da máquina — e para onde

As transferências abaixo acontecem durante o uso das funções indicadas; a API
de licença também sincroniza automaticamente enquanto o aplicativo está aberto.

| Destino | O que vai | Quando |
|---|---|---|
| **Microsoft OneDrive** | Planilha com os clientes exportados | Ao clicar em "Enviar para Excel" |
| **ViaCEP** | O CEP digitado | Ao preencher endereço a partir do CEP |
| **Nominatim (OpenStreetMap)** | Rua, bairro, cidade, CEP | Depois que o usuário autoriza o mapa para sua conta |
| **Google Gemini** | Cidade e CEP | Ao pedir sugestão de bairro (opcional) |
| **Mercado Pago** | Valor e referência da instalação — **nenhum dado de cliente** | Ao pagar a licença de uso do aplicativo |
| **API central de licenças** | ID aleatório da conta, nome de usuário, e-mail e estado do teste/licença | Ao entrar no sistema e, enquanto aberto, a cada 30 segundos |
| **Arquivo local** | O que o operador escolher | Exportar CSV/XLSX, backup |

Nenhum dado de cliente vai ao Mercado Pago: a cobrança ali é da licença do
aplicativo, paga pela própria Adri, e leva apenas o valor e um identificador da
instalação.

A API central não recebe nome/endereço de clientes do ERP, pedidos, produtos,
valores de venda ou dados financeiros. O serviço guarda o nome/e-mail da conta
do software e o estado da licença em PostgreSQL hospedado pelo fornecedor. O
segredo aleatório de sincronização é guardado como hash no servidor; o token
administrativo fica somente no backend da máquina do desenvolvedor, cifrado
com DPAPI no cofre local. A conexão de produção usa HTTPS. As respostas
confirmadas permitem até 72 horas de uso offline.

A tela do mapa explica a consulta e aguarda autorização antes de enviar os
endereços. O consentimento é guardado por conta neste computador. A exportação
para o OneDrive é iniciada pelo operador ao selecionar a ação de exportar.

## Retenção

| Dado | Quanto tempo | Como é apagado |
|---|---|---|
| Clientes | Enquanto o usuário quiser | Exclusão lógica (`ativo = 0`); some das telas e das exportações |
| Contas locais | Até exclusão pelo desenvolvedor | Remoção pela área de desenvolvedor |
| Pagamentos | Indefinido | Cancelamento marca `Cancelado`; a linha permanece |
| Auditoria | Indefinido | **Não é apagável** — a tabela é append-only, por design |
| Backups | 7 cópias diárias, 10 de pré-migração | Rotação automática, a mais antiga sai |
| Chaves de idempotência | 7 dias | Podadas na abertura do aplicativo |
| Logs | Até 5 arquivos de 2 MB | Rotação automática |

**A exclusão é lógica, não física.** Isso é deliberado: apagar a linha levaria
junto o histórico, os pagamentos e a trilha de auditoria que apontam para ela.
A consequência precisa ser dita com todas as letras: **um pedido de exclusão
sob a LGPD não é atendido pela tela de exclusão do sistema.** Para apagar de
verdade é preciso agir no banco, e não há ferramenta para isso hoje.

## Direitos do titular (LGPD, Lei 13.709/2018)

O sistema é ferramenta interna da empresa, que é a **controladora** dos dados.
O que o software oferece hoje:

| Direito | Situação |
|---|---|
| **Acesso** | ✅ A tela de clientes mostra tudo que há sobre a pessoa |
| **Portabilidade** | ✅ Exportação em CSV, XLSX ou JSON |
| **Correção** | ✅ Edição do cadastro |
| **Eliminação** | ⚠️ Parcial — exclusão lógica; o dado permanece no banco e nos backups |
| **Informação sobre compartilhamento** | ✅ A interface explica e pede autorização para o envio de endereços ao mapa |

Enquanto a eliminação definitiva não existir na interface, um pedido de
exclusão precisa ser tratado manualmente, incluindo as cópias de backup.

## Responsabilidades de quem opera

O software cuida de parte; o resto depende de como a máquina é usada.

- **Cifre o disco.** O banco e os backups não são cifrados. Sem BitLocker (ou
  equivalente), qualquer pessoa com acesso físico ao computador lê a base
  inteira.
- **Backups saem da máquina em claro.** O arquivo baixado por "Backup do banco"
  e a cópia em `ADRI_BACKUP_EXTRA` contêm todos os dados. Guarde em local
  controlado.
- **O acesso ao aplicativo exige conta local.** A senha é armazenada como hash
  bcrypt e a sessão usa cookie `HttpOnly`. Usuários comuns e administradores
  acessam as áreas comuns; somente o desenvolvedor administra contas e testes.
  O login Microsoft é opcional e é usado apenas para exportar ao OneDrive.
- **As chaves de integração ficam cifradas** em
  `%APPDATA%\AdriPoltronas\.segredos`, protegidas por DPAPI e amarradas à sua
  conta do Windows — copiar o arquivo para outra máquina não serve de nada. A
  migração é automática: uma chave colada no `.env` é movida para o cofre na
  próxima abertura. Uma cópia do arquivo original é feita em `.env.bak` antes
  da reescrita e **apagada logo depois**, assim que o cofre é relido e cada
  chave conferida — até a 1.5.0 essa cópia ficava para sempre, em texto puro,
  ao lado da versão cifrada.
  **O que isso não protege:** código rodando como o seu próprio usuário pode
  pedir ao DPAPI que decifre. Contra ele, o que vale é cifrar o disco.
- **O `MP_ACCESS_TOKEN` dá acesso total à conta do vendedor no Mercado Pago**
  — criar cobrança, ler movimentação, estornar. Use um token de aplicação
  dedicada à licença, nunca o token principal da conta. Ver
  `LICENCA_E_PAGAMENTO.md`.

## Incidentes

Vazamento de dados pessoais precisa ser comunicado à ANPD e aos titulares em
prazo razoável. Um incidente com este sistema significa, na prática, acesso ao
arquivo do banco ou a um backup. Se acontecer:

1. Identifique quais cópias foram expostas (a pasta de backups tem data e hora
   no nome de cada arquivo).
2. Rotacione as chaves do `.env` — elas estão na mesma pasta.
3. Registre o que aconteceu e o que foi feito.

Para falha de segurança **no software**, veja [SECURITY.md](SECURITY.md).
