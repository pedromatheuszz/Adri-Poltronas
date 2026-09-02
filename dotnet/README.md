# Adri Poltronas — aplicativo .NET / Avalonia

Aplicativo desktop em C# com Avalonia UI, MVVM e Entity Framework Core.

É uma **exploração arquitetural**, não a versão que o cliente usa. Hoje ela
cobre cinco telas — Dashboard, Clientes, Mapa, Pagamentos e Relatórios — e não
tem catálogo de produtos nem pedidos, que são o centro do dia a dia da
operação. Enquanto essa paridade não existir, a versão oficial é a do
Electron/Flask.

> ### Banco separado, por decisão
>
> Até a versão 1.1 as duas pilhas liam e escreviam **o mesmo arquivo SQLite**.
> Isso foi revertido: cada uma trabalha na própria cópia.
>
> Dois sistemas escrevendo no mesmo banco, com domínios e sistemas de migração
> diferentes, produzem divergências que nenhum teste de compatibilidade pega:
>
> - o Python inativa cliente (`ativo = 0`); o EF Core **remove a linha**, e com
>   ela o histórico que aponta para o cliente;
> - o ledger `auditoria_eventos` só é alimentado pelo Python, então toda
>   escrita vinda do .NET era invisível na trilha de auditoria;
> - Alembic e EF Core versionam o schema de formas incompatíveis. Se o .NET
>   criasse o arquivo primeiro, o banco nasceria sem `alembic_version` e a
>   migração inicial do Python tentaria criar tabelas já existentes.
>
> Quem precisar apontar as duas pilhas para o mesmo arquivo — um teste de
> compatibilidade, uma importação pontual — passa `Banco__ConexaoString`
> explicitamente. É uma decisão consciente, não mais o padrão.

## Camadas

```
AdriPoltronas.sln
├── src/
│   ├── AdriPoltronas.Domain           entidades e regras de negócio
│   ├── AdriPoltronas.Application      casos de uso, DTOs, interfaces
│   ├── AdriPoltronas.Infrastructure   EF Core, repositórios, configuração
│   └── AdriPoltronas.Desktop          Avalonia: Views, ViewModels, navegação
└── tests/
    ├── AdriPoltronas.Domain.Tests
    ├── AdriPoltronas.Application.Tests
    ├── AdriPoltronas.Infrastructure.Tests
    └── AdriPoltronas.Desktop.Tests
```

Direção das dependências:

```
Desktop ──► Application ──► Domain
                 ▲              ▲
                 └── Infrastructure ──┘
```

O `Domain` não referencia **nenhum** pacote — nem Avalonia, nem EF Core. Há
teste que falha se isso mudar (`ArquiteturaTests`).

O `Desktop` referencia `Infrastructure` apenas para registrar as dependências
em `Program.cs`. Nenhum ViewModel recebe tipo de infraestrutura, e há teste
que verifica (`ArquiteturaDaApresentacaoTests`).

## Fluxo de um CRUD

```
ClientesView.axaml            binding, sem lógica
      ↓
ClientesViewModel             comandos e estado
      ↓
CriarCliente (use case)       orquestra, devolve Resultado
      ↓
Cliente.Criar (Domain)        valida e normaliza
      ↓
IClienteRepository            interface, em Application
      ↓
ClienteRepository             EF Core, em Infrastructure
      ↓
AdriPoltronasDbContext
      ↓
SQLite (%APPDATA%/AdriPoltronas/adri_poltronas.db)
```

## Comandos

```bash
cd dotnet
dotnet restore
dotnet build
dotnet test
dotnet run --project src/AdriPoltronas.Desktop
```

Ou pela raiz do projeto: `python build.py dotnet`, `make dotnet`,
`make run-dotnet`.

## Banco de dados

| | |
|---|---|
| Provedor atual | SQLite |
| Arquivo | `%APPDATA%/AdriPoltronas/adri_poltronas_dotnet.db` (Windows), `~/.config/AdriPoltronas/` (Linux e macOS) |
| Banco do backend Python | `adri_poltronas.db`, na mesma pasta — **não é tocado por esta aplicação** |
| Dono do schema | EF Core, neste arquivo |

O `InicializadorDoBanco` ainda detecta a tabela `alembic_version` e, se a
encontrar, **não aplica** as migrações do EF Core. A checagem continua fazendo
sentido para quem apontar deliberadamente as duas pilhas para o mesmo arquivo
via `Banco__ConexaoString`: duas ferramentas versionando o mesmo schema é
receita para banco inconsistente.

### Trocar para PostgreSQL

A arquitetura não está presa ao SQLite, mas o pacote do Npgsql ainda não é
referenciado (seria dependência sem uso). Para habilitar:

1. `dotnet add src/AdriPoltronas.Infrastructure package Npgsql.EntityFrameworkCore.PostgreSQL`
2. Em `DependencyInjection.AddInfrastructure`, trocar o `throw` do caso
   `PostgreSql` por `construtor.UseNpgsql(opcoes.ConexaoString)`.
3. Definir a conexão por variável de ambiente:
   `Banco__Provedor=PostgreSql` e `Banco__ConexaoString=...`

Nenhum caso de uso, entidade ou ViewModel precisa mudar.

## Configuração

`appsettings.json` no diretório do executável, sobreposto por variáveis de
ambiente (`Banco__ConexaoString`, `Logging__LogLevel__Default`). Senha de banco
nunca vai para o arquivo versionado.

## Logging

`Microsoft.Extensions.Logging` com dois destinos: console (desenvolvimento) e
arquivo diário em `%APPDATA%/AdriPoltronas/logs/desktop-AAAA-MM-DD.log` — um
aplicativo empacotado não tem console, e sem arquivo o log do único ambiente
que importa se perderia.

## Módulos

| Aba | Casos de uso | Observações |
|-----|--------------|-------------|
| Dashboard | `ObterPainel` | uma chamada monta os 8 cartões, os 4 gráficos e os últimos clientes — a tela nunca aparece pela metade |
| Clientes | `BuscarClientes`, `CriarCliente`, `AtualizarCliente`, `ExcluirCliente`, `ImportarClientes`, `ExportarClientes`, `FazerBackup` | importação por CSV/XLSX/JSON reconhece a coluna pelo cabeçalho, não pela posição |
| Mapa | `ObterPontosDoMapa` | carga sob demanda; o serviço de geocodificação limita uma consulta por segundo |
| Pagamentos | `BuscarPagamentos`, `RegistrarPagamento`, `ConfirmarPagamento`, `CancelarPagamento`, `ExcluirPagamento`, `GerarCobranca` | a coerência entre status e data de recebimento é invariante da entidade |
| Relatórios | `GerarRelatorio`, `ExportarRelatorio`, `ObterDesempenhoPorRegiao` | exporta em CSV (com BOM) ou XLSX |
| Notificações | `ObterNotificacoes`, `MarcarNotificacoesLidas` | derivadas na hora; só o estado de "lida" vai para o banco |

### Gráficos e mapa sem dependência externa

`Controles/GraficoDeBarras`, `GraficoDeLinha`, `GraficoDeRosca` e
`ControleDeMapa` são desenhados à mão sobre o `DrawingContext` do Avalonia.

São três formas simples e uma projeção de Mercator; uma biblioteca de gráficos
traria tema próprio, licenciamento e uma superfície de API inteira para manter,
e o mapa exigiria embutir um navegador só para desenhar círculos. O desenho
direto acompanha a paleta do aplicativo sem adaptador e funciona offline.

### Integrações externas

Todas atrás de interface na `Application`, todas opcionais: chave ausente
desliga o recurso e esconde o botão, sem derrubar o aplicativo.

| Interface | Implementação | Chave |
|-----------|---------------|-------|
| `IConsultaDeCep` | ViaCEP | nenhuma |
| `ISugestaoDeBairro` | Gemini | `Integracoes__ChaveDoGemini` |
| `IServicoDeCobranca` | Asaas | `Integracoes__ChaveDoAsaas` |
| `IGeocodificador` | Nominatim + cache em arquivo | nenhuma |
| `IFonteDeLadrilhos` | OpenStreetMap + cache em disco | nenhuma |

## Idioma e formatação

A cultura é fixada em `pt-BR` no arranque (`Program.Idioma`), e não herdada do
sistema operacional: a mesma base é lida pelo backend Python e por planilhas
que vão para o contador. Uma máquina configurada em inglês gravaria
`1,234.56` no relatório exportado e quebraria a leitura do outro lado.

Por isso `InvariantGlobalization` está **desligado**. Em Linux isso exige o
pacote `libicu`; no Windows o suporte já vem no sistema.

## Multiplataforma

Nada de específico do Windows no código. A única diferença entre sistemas está
encapsulada em `PastaDeDados`, que usa `Environment.SpecialFolder.ApplicationData`.

```bash
dotnet publish src/AdriPoltronas.Desktop -c Release -r win-x64   --self-contained
dotnet publish src/AdriPoltronas.Desktop -c Release -r linux-x64 --self-contained
dotnet publish src/AdriPoltronas.Desktop -c Release -r osx-arm64 --self-contained
```

## Testes

| Projeto | Cobre |
|---------|-------|
| `Domain.Tests` | regras do cadastro, normalização de CEP, detecção de alterações, direção das dependências |
| `Application.Tests` | casos de uso contra dublês em memória, transação única, distinção entre inválido e inexistente |
| `Infrastructure.Tests` | EF Core contra um **SQLite com o schema legado real**: formato de data, tipo como texto, FK, colunas não mapeadas |
| `Desktop.Tests` | fluxo das telas sem abrir janela, incluindo a regressão da lista que não recarregava e a do contador de notificações |

```bash
dotnet test          # 127 testes
```
