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
| Valores, vencimentos, status | `pagamentos` | Cobrança e conferência |
| Endereço e horário de entrega | `entregas_agendadas` | Agenda da equipe |
| Pedidos e itens | `pedidos`, `pedido_itens` | O que foi vendido |
| Ações realizadas | `historico`, `auditoria_eventos` | Rastreabilidade |
| Conta Microsoft conectada | `sessao` | Exportar para o OneDrive |
| Identificador do cliente no Asaas | `clientes_asaas` | Emitir cobrança |

**O que o sistema NÃO guarda:** CPF/CNPJ, telefone, e-mail, dados de cartão,
senha de cliente. O Asaas cria cobranças sem CPF, e nenhuma tela pede esses
campos.

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

Não há servidor central, nem sincronização em nuvem, nem telemetria. O banco
não sai da máquina exceto pelas ações abaixo.

## Quando dados saem da máquina — e para onde

Cada uma destas é iniciada por alguém clicando em algo. Nenhuma é automática.

| Destino | O que vai | Quando |
|---|---|---|
| **Asaas** | Nome do cliente, endereço, valor, vencimento | Ao gerar cobrança Pix ou boleto |
| **Microsoft OneDrive** | Planilha com os clientes exportados | Ao clicar em "Enviar para Excel" |
| **ViaCEP** | O CEP digitado | Ao preencher endereço a partir do CEP |
| **Nominatim (OpenStreetMap)** | Rua, bairro, cidade, CEP | Ao abrir o mapa, para posicionar os marcadores |
| **Google Gemini** | Cidade e CEP | Ao pedir sugestão de bairro (opcional) |
| **Arquivo local** | O que o operador escolher | Exportar CSV/XLSX, backup |

A tela do mapa avisa que consulta serviços externos. **A mesma clareza precisa
existir para o Asaas e o OneDrive** — está na lista de melhorias.

## Retenção

| Dado | Quanto tempo | Como é apagado |
|---|---|---|
| Clientes | Enquanto o usuário quiser | Exclusão lógica (`ativo = 0`); some das telas e das exportações |
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
| **Informação sobre compartilhamento** | ⚠️ Parcial — está nesta página; a interface só avisa no mapa |

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
- **Não há controle de acesso no aplicativo.** Quem abre, vê tudo. Use conta de
  usuário do Windows com senha.
- **Segredos ficam em `%APPDATA%\AdriPoltronas\.env`**, em texto. Quem lê o
  perfil do usuário lê as chaves do Asaas e do Gemini.
- **Chave do Asaas em produção move dinheiro de verdade.** Mantenha em sandbox
  até haver certeza.

## Incidentes

Vazamento de dados pessoais precisa ser comunicado à ANPD e aos titulares em
prazo razoável. Um incidente com este sistema significa, na prática, acesso ao
arquivo do banco ou a um backup. Se acontecer:

1. Identifique quais cópias foram expostas (a pasta de backups tem data e hora
   no nome de cada arquivo).
2. Rotacione as chaves do `.env` — elas estão na mesma pasta.
3. Registre o que aconteceu e o que foi feito.

Para falha de segurança **no software**, veja [SECURITY.md](SECURITY.md).
