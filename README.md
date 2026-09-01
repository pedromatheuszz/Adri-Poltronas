# Adri Poltronas

Aplicativo desktop de gestao da Adri Poltronas em evolucao incremental para um ERP modular. A aplicacao principal usa Electron/TypeScript como janela e Flask/Python como API local, com SQLite e migrations Alembic.

## Documentacao

- [Diagnostico e roadmap ERP](docs/ERP_DIAGNOSTICO_E_ROADMAP.md)
- [Backend ERP v2 e comparacao com o v1](backend_v2/README.md)
- [Build e desenvolvimento](BUILD_GUIDE.md)
- [Padrao da API](API_STANDARD.md)
- [Aplicativo .NET/Avalonia](dotnet/README.md)
- [Code signing](docs/code-signing.md)

## Inicio rapido

Pre-requisitos principais: Windows, Python 3.10–3.12 e Node.js 22.

```powershell
python -m pip install -r backend/requirements.txt
npm ci
npm start
```

O Electron inicia o Flask em `http://127.0.0.1:5000`. O banco fica em `%APPDATA%\AdriPoltronas\adri_poltronas.db`; para testes isolados, defina `ADRI_DB_PATH`.

O backend ERP v2 é independente e pode rodar ao mesmo tempo em
`http://127.0.0.1:5001`. Use `npm.cmd run start:v2` para abrir o Electron com o
v2 na porta 5000; `npm start` continua selecionando o v1 por padrão. Veja
[backend_v2/README.md](backend_v2/README.md).

## Qualidade

```powershell
python -m ruff check backend tests build.py
python -m pytest tests -q
npm run typecheck
npm run build
dotnet test dotnet/AdriPoltronas.sln --configuration Release
```

As migrations rodam automaticamente no inicio do backend. Alembic e o unico dono do schema compartilhado enquanto as interfaces atuais coexistirem.

## Arquitetura em evolucao

Codigo novo de dominio e processos deve entrar em `backend/erp`, por modulo de negocio. Os blueprints atuais permanecem como adaptadores compativeis; funcionalidades e contratos existentes nao devem ser removidos sem migracao e testes.
