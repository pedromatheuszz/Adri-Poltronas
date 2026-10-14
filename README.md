Adri Poltronas
Sistema desktop para organizar clientes, locações, pedidos, entregas, pagamentos e a rotina diária da Adri Poltronas.

Sobre o software
O Adri Poltronas é um aplicativo desktop profissional para Windows, inspirado em sistemas de gestão empresarial e desenvolvido especialmente para a rotina da Adri Poltronas, empresa que realiza a locação de poltronas elétricas com elevação, muito utilizadas durante períodos de recuperação e pós-operatório.
O aplicativo centraliza as principais informações do negócio em um só lugar. Ele ajuda a reduzir a dependência de planilhas separadas, anotações, mensagens antigas e controles manuais, oferecendo mais organização, agilidade e segurança para acompanhar cada atendimento.
Seu objetivo principal é facilitar o gerenciamento e o controle da operação, permitindo acompanhar:
clientes e endereços;
pedidos e locações;
modelos de poltronas e demais itens do catálogo;
entregas e retiradas;
parcelas a receber geradas pelo faturamento;
indicadores operacionais;
localização dos clientes;
alertas importantes.
Importante: na versão atual, a aba Produtos funciona como catálogo de itens usados nos pedidos. O controle físico de estoque — quantidade total, disponível, locada, movimentações e reservas automáticas — ainda não está completo.
Sumário
Primeiros passos
Como navegar pelo aplicativo
Fluxo recomendado de trabalho
Dashboard
Pedidos
Clientes
Produtos
Entregas
Mapa
Notificações
Importação, exportação e backup
Atalhos de teclado
Rotina diária recomendada
Boas práticas
Limitações atuais
Dúvidas comuns
Primeiros passos
Instalação
Acesse a página de versões do Adri Poltronas.
Baixe o instalador oficial para Windows.
Execute o instalador e siga as instruções apresentadas.
Abra o Adri Poltronas pelo atalho criado no Windows.
Aguarde alguns segundos até que o Dashboard seja exibido.
Use somente instaladores obtidos pelo repositório oficial ou fornecidos diretamente pelo responsável pelo sistema.
Preparação inicial
Antes de registrar a primeira locação, recomenda-se:
na primeira abertura, criar a conta de desenvolvedor com uma senha forte;
cadastrar os modelos de poltronas na aba Produtos;
cadastrar ou importar os clientes existentes;
conferir endereços, cidades e tipos de atendimento;
criar um backup inicial;
configurar, com o responsável pelo sistema, a integração opcional de Microsoft/Excel.

O acesso ao sistema exige login local. Usuários podem criar a própria conta na
tela de login; o desenvolvedor cria contas administrativas e gerencia o acesso
e os períodos de teste. A conexão Microsoft é opcional e serve apenas à
integração com o OneDrive.

O período de teste e a confirmação manual do pagamento entre computadores
usam uma API central opcional. Para publicar o serviço e configurar as
instalações, consulte [`licensing-service/README.md`](licensing-service/README.md).
Como navegar pelo aplicativo
As áreas principais ficam no menu lateral esquerdo, organizadas por assunto:
Grupo
Abas
Visão geral
Dashboard
Comercial
Pedidos, Clientes e Produtos
Operacional
Entregas e Mapa
O menu pode ser recolhido para aumentar a área de trabalho. Na parte superior ficam o indicador de conexão, o botão de notificações e a opção de alternar entre tema claro e escuro.
Fluxo recomendado de trabalho
Para manter todas as informações relacionadas, utilize esta sequência:
Localize ou cadastre o cliente.
Confira o produto que será incluído na locação.
Crie o pedido e informe data prevista, desconto, frete e observações.
Salve o pedido antes de adicionar os itens.
Adicione a poltrona, quantidade, descrição personalizada e preço.
Abra e aprove o pedido quando a negociação estiver confirmada.
Agende a entrega ou retirada e confira data, horário e endereço.
Fature o pedido para gerar as parcelas, que ficam listadas dentro dele.
Acompanhe e dê baixa nas parcelas recebidas, pelo próprio pedido.
Atualize o andamento da entrega até sua conclusão.
Consulte o Dashboard e o Mapa para acompanhar os resultados.
Registrar cada mudança no momento em que ela acontece mantém os indicadores, alertas e valores pendentes confiáveis.
Abas do aplicativo
1. Dashboard
O Dashboard apresenta uma visão resumida da operação. É a melhor tela para consultar no início e no final do dia.
O que é exibido
total de clientes cadastrados;
cadastros classificados como entrega ou retirada;
novos clientes dos últimos 30 dias;
distribuição entre entregas e retiradas;
cidades com mais clientes;
evolução dos novos cadastros;
clientes cadastrados recentemente.
Como usar de forma eficiente
Comece pelas tarefas que vencem no dia.
Use as cidades com maior concentração de clientes para apoiar ações comerciais e logísticas.
Se um número parecer incorreto, confira se pedidos e entregas foram atualizados corretamente.
2. Pedidos
A aba Pedidos concentra as negociações e locações realizadas com os clientes. Cada pedido recebe um número e reúne cliente, itens, valores, previsão de entrega e observações.
Criar um pedido
Clique em Novo Pedido.
Selecione o cliente.
Informe a data prevista de entrega, quando houver.
Preencha desconto, frete e observações.
Clique em Salvar pedido.
Depois de salvar, selecione o produto e informe quantidade, preço unitário e detalhes como tecido, acabamento ou medida.
Clique em Adicionar para incluir o item.
Confira total dos itens, desconto, frete e valor final.
Um pedido precisa ser salvo antes que seus itens possam ser adicionados.
Situações do pedido
Situação
Significado
Rascunho
Pedido ainda em preparação e com informações editáveis.
Aberto
Pedido registrado e aguardando confirmação.
Aprovado
Negociação confirmada; a entrega pode ser agendada.
Faturado
Parcelas geradas e listadas no próprio pedido; ele deixa de aceitar alterações de itens.
Cancelado
Pedido encerrado e mantido apenas no histórico.
Ao faturar, informe a quantidade de parcelas, o primeiro vencimento e a forma de pagamento. As parcelas aparecem em uma tabela dentro do próprio pedido, com vencimento, valor e situação.
Cada parcela tem um botão Receber, que registra a baixa na data de hoje, e um botão Desfazer, para o caso de a baixa ter sido feita por engano. Uma parcela pendente cujo vencimento já passou aparece marcada como em atraso — isso é calculado pela data, não registrado manualmente.
Confira itens, preço, desconto, frete e vencimentos antes de faturar. Depois dessa etapa, o pedido não pode mais ser alterado pela tela.
Use a pesquisa por número ou cliente e o filtro por situação para localizar pedidos rapidamente.
3. Clientes
A aba Clientes reúne os dados das pessoas atendidas. O cadastro correto é a base para pedidos, agenda, mapa, pagamentos e relatórios.
Informações do cadastro
nome completo;
CEP;
rua e número;
bairro;
cidade;
tipo de atendimento: entrega ou retirada;
observações importantes para a operação.
Recursos disponíveis
cadastrar e editar clientes;
pesquisar por nome e outras informações;
aplicar e limpar filtros;
selecionar vários registros;
carregar mais resultados quando a lista for extensa;
importar clientes em lote;
exportar dados para Excel pela integração Microsoft;
criar backup completo do banco;
restaurar uma cópia anterior;
consultar o histórico de alterações.
Antes de cadastrar uma pessoa, pesquise pelo nome para evitar duplicidade. Mantenha CEP, rua, bairro e cidade completos, pois esses dados também são usados pelo Mapa e pelo planejamento das entregas.
4. Produtos
A aba Produtos é o catálogo dos modelos de poltronas e demais itens que podem ser adicionados aos pedidos.
Cada produto pode conter:
código único;
descrição;
unidade, como unidade, peça ou conjunto;
preço de venda padrão;
observações.
O preço cadastrado serve como referência ao adicionar o produto a um pedido. Se a negociação exigir um valor ou uma configuração diferente, os detalhes podem ser informados no próprio item do pedido.
Adote códigos e nomes padronizados. Por exemplo, evite cadastrar o mesmo modelo com grafias diferentes, pois isso dificulta pesquisas e análises.
Sobre o estoque
Esta área ainda não controla automaticamente quantidade disponível, equipamentos locados, entradas, saídas ou reservas por período. Para não confundir catálogo com disponibilidade real, confirme a disponibilidade física da poltrona antes de aprovar a locação.
5. Entregas
A aba Entregas funciona como agenda operacional. Ela organiza compromissos por data e destaca itens atrasados, de hoje, de amanhã e dos próximos dias.
Agendar uma entrega
Abra um pedido aprovado e use Agendar entrega, ou clique em Agendar Entrega na própria aba.
Selecione o cliente.
Vincule o pedido, quando existir.
Informe data, horário e descrição.
Confira os dados e clique em Agendar.
O vínculo com o pedido facilita a consulta das informações da negociação diretamente pela agenda.
Situações da entrega
Situação
Uso recomendado
Pendente
Compromisso agendado, ainda não iniciado.
Em andamento
Equipe realizando o atendimento.
Concluída
Entrega ou retirada finalizada.
Cancelada
Compromisso que não será realizado.
O filtro padrão mostra os compromissos em aberto. Atualize o status assim que a atividade começar ou terminar para evitar que tarefas concluídas continuem aparecendo como pendentes.
6. Mapa
A aba Mapa mostra a distribuição geográfica dos clientes. Os marcadores diferenciam cadastros de entrega e retirada e podem apresentar nome, CEP, rua, bairro e cidade.
Use o mapa para:
localizar clientes próximos;
agrupar atendimentos da mesma região;
planejar uma sequência de deslocamentos;
identificar cidades com maior concentração de clientes;
reduzir trajetos desnecessários.
O mapa e a localização dos endereços dependem de acesso à internet. Se um cliente não aparecer, revise CEP, rua, bairro e cidade no cadastro. O carregamento inicial de muitos endereços pode levar alguns instantes.
Parcelas a receber
As parcelas nascem do faturamento de um pedido e ficam dentro dele — não há aba financeira separada. Abra o pedido faturado e a tabela Parcelas a receber aparece abaixo dos itens, com o total já recebido e o total em aberto.
Situações da parcela
Situação
Significado
Pendente
Valor lançado, ainda aguardando pagamento.
Recebida
Pagamento confirmado, com a data em que foi registrado.
Cancelada
Parcela encerrada sem recebimento.
Uma parcela pendente com vencimento já passado aparece sinalizada como em atraso. Isso é calculado a partir da data, e não registrado: assim que ela é recebida, a marcação some sozinha.
Confira o valor antes de dar baixa. A ação fica registrada no histórico de auditoria, e desfazer uma baixa também.
O que esta versão não faz
A versão 1.5.0 removeu o módulo financeiro e a integração com gateway de cobrança. Não há, hoje, geração de Pix ou boleto pelo aplicativo, conciliação bancária, recebimento avulso desvinculado de pedido, nem relatórios financeiros. O acompanhamento de recebimento existe no escopo acima: parcela do pedido, baixa manual.
Notificações
O sino no canto superior da tela abre o painel de notificações. O número exibido representa os alertas ainda não lidos.
O sistema pode avisar sobre:
Alerta
Prioridade
Entrega atrasada
Crítica
Entrega prevista para hoje
Alta
Entrega nos próximos três dias
Média
Cliente sem movimentação há 90 dias
Baixa
Trate primeiro alertas críticos e altos. Depois de verificar um aviso, marque-o como lido para que o contador represente apenas as pendências novas. O botão Atualizar refaz a consulta.
Importação, exportação e backup
Importar clientes
A importação aceita arquivos CSV, JSON e XLSX. A primeira linha deve conter os nomes das colunas.
Antes de importar:
faça um backup;
confira se a planilha possui cabeçalhos;
padronize nomes, CEPs e cidades;
remova linhas duplicadas quando possível;
execute a importação e confira o resumo de sucessos, duplicados e erros.
Exportar para Excel
A exportação pela Microsoft permite enviar clientes selecionados ou os resultados da pesquisa atual para um arquivo do Excel. Essa função depende da conexão da conta Microsoft configurada pelo responsável pelo sistema.
Backup e restauração
O backup do banco inclui clientes, pedidos, parcelas, entregas e histórico. Faça uma cópia antes de importações, restaurações ou alterações em grande quantidade.
Guarde o arquivo em local seguro, pois ele contém informações pessoais e financeiras. Ao restaurar uma cópia, o banco atual é substituído; o sistema cria antes uma cópia de segurança do estado atual para permitir recuperação.
Funcionamento offline
O indicador no topo informa o estado da conexão. Parte dos dados de clientes já carregados pode continuar disponível no computador, e algumas alterações podem ficar pendentes para envio quando o serviço voltar a responder.
Operações que dependem da internet ou de serviços externos — como o mapa e a exportação para Microsoft/Excel — podem ficar indisponíveis. Verifique o indicador de pendências depois que a conexão retornar e não feche o aplicativo durante uma sincronização.
Atalhos de teclado
Atalho
Ação
Ctrl + N
Iniciar um novo cadastro de cliente
Ctrl + F
Ir para a pesquisa de clientes
Ctrl + E
Exportar clientes para Excel
Ctrl + B
Criar backup dos clientes em JSON
Ctrl + I
Abrir a importação de clientes
Esc
Cancelar ou fechar a janela atual, quando disponível
Os atalhos Ctrl + N, Ctrl + F e Ctrl + E atuam principalmente na área de Clientes.
Rotina diária recomendada
No início do dia
Abra o Dashboard.
Consulte as notificações críticas e altas.
Verifique entregas atrasadas e previstas para hoje.
Organize os deslocamentos usando a Agenda e o Mapa.
Ao atender um cliente
Pesquise se o cadastro já existe.
Atualize telefone, endereço e observações, se necessário.
Crie o pedido e registre tudo o que foi combinado.
Adicione os itens e confira os valores.
Aprove o pedido somente quando a negociação estiver confirmada.
Durante a locação
Agende e acompanhe a entrega.
Fature o pedido e revise as parcelas geradas.
Monitore os vencimentos pelo próprio pedido.
Dê baixa nas parcelas recebidas e atualize o status da entrega conforme as atividades acontecem.
No final do dia
Confira compromissos que continuam em aberto.
Dê baixa nas parcelas já recebidas.
Revise notificações ainda não tratadas.
Consulte novamente os indicadores do Dashboard.
Faça backup quando houver alterações importantes.
Boas práticas
Pesquise antes de cadastrar para evitar clientes duplicados.
Use nomes e códigos padronizados para os produtos.
Registre no pedido tudo o que foi combinado com o cliente.
Confira os valores antes de faturar ou dar baixa numa parcela.
Mantenha endereços completos para melhorar o Mapa e a logística.
Atualize os status no momento em que cada atividade acontecer.
Faça backups frequentes e mantenha pelo menos uma cópia fora do computador principal.
Não compartilhe arquivos de backup com pessoas não autorizadas.
Não use o campo de observações para informações pessoais que não sejam necessárias à operação.
O funcionamento correto depende da qualidade dos dados. Se uma entrega concluída continuar como pendente ou uma parcela recebida não receber baixa, os alertas e indicadores também ficarão incorretos.
Limitações atuais
A versão atual ainda não possui controle completo de:
quantidade física total, disponível e locada;
reservas automáticas por período;
entradas e saídas de estoque;
manutenção e avarias de cada poltrona;
compras, fornecedores e contas a pagar;
geração de Pix ou boleto, conciliação bancária e relatórios financeiros;
contratos e assinaturas digitais;
emissão de nota fiscal;
vários usuários com permissões diferentes;
vários computadores trabalhando simultaneamente em uma base centralizada.
Essas limitações não impedem o uso do sistema para cadastro, pedidos, agenda e acompanhamento das parcelas, mas devem ser consideradas na organização da operação.
Dúvidas comuns
O cliente não aparece no pedido
Confirme se o cadastro foi salvo e pesquise o nome na aba Clientes. Depois feche e abra novamente o formulário do pedido para atualizar a lista.
O produto não aparece na lista de itens
Confira se ele foi salvo na aba Produtos. Reabra o pedido para atualizar o catálogo disponível.
Um cliente não aparece no mapa
Revise CEP, rua, bairro e cidade. Confirme também se o computador possui acesso à internet e aguarde o processamento dos endereços.
Não encontro a aba Pagamentos
Ela foi removida na versão 1.5.0. As parcelas geradas pelo faturamento ficam dentro do próprio pedido: abra o pedido faturado e role até Parcelas a receber.
Não consigo exportar para Excel
Use Conectar Microsoft antes da exportação. Se a sessão tiver expirado, faça a conexão novamente.
O aplicativo pediu uma licença
O período de teste é de 30 dias a partir da primeira abertura. Depois disso o aplicativo pede a licença de uso e mostra um Pix para pagamento; a liberação é automática assim que o pagamento é confirmado. Fale com o responsável pelo sistema.
Os indicadores parecem desatualizados
Confira se as alterações foram salvas e se não existem operações offline pendentes. Navegue novamente até o Dashboard ou reinicie o aplicativo, se necessário.
O aplicativo informa que está sem conexão
Aguarde alguns segundos e verifique a internet. Se o aviso permanecer mesmo com internet ativa, feche e abra o aplicativo. Alterações pendentes devem ser conferidas depois que a conexão retornar.
Privacidade e uso responsável
O Adri Poltronas armazena informações de clientes e dados financeiros necessários à operação. Utilize esses dados somente para finalidades relacionadas ao atendimento e ao gerenciamento do negócio.
Para mais informações, consulte a Política de Privacidade.
Adri Poltronas — mais organização, controle e clareza para acompanhar o que já aconteceu, o que está acontecendo e o que ainda precisa ser feito.
Versão documentada: 1.5.1-beta.
