# ✅ QUICK REFERENCE - Adri Poltronas

## 🚀 START HERE

### First Time Setup
```bash
# 1. Install dependencies (Python + Node)
python build.py install-deps

# 2. Run tests to verify
python build.py test

# 3. Start development (Electron abre a janela e sobe o Flask)
npm start
```

### Common Commands
```bash
# Testing
python build.py test          # Run all tests
make test                      # Alternative

# Building (dois estágios)
python build.py build         # 1. PyInstaller empacota o backend
python build.py installer     # 2. electron-builder gera o instalador
make installer                # Alternative

# Development
npm start                     # Run application (janela Electron)
python build.py qt            # Compila e testa a janela Qt (alternativa)
python build.py dotnet        # Compila e testa a solution .NET/Avalonia
make run-dotnet               # Executa o aplicativo Avalonia
npm run typecheck             # Checagem de tipos do processo principal
ADRI_API_SEM_TOKEN=1 python backend/servidor.py   # Só o backend, sem janela
make dev                      # Alternative

# Sem o Electron nao ha quem injete o token de capacidade, e a API responde
# 403. ADRI_API_SEM_TOKEN=1 desliga a exigencia -- so para desenvolvimento.

# Cleaning
python build.py clean         # Remove generated files
make clean                    # Alternative

# Linting
python build.py lint          # Check code style
```

---

## 📁 WHERE TO FIND THINGS

| What | Where |
|------|-------|
| Janela / processo principal | `electron/main.ts` |
| Janela alternativa (C++/Qt) | `qt-app/` |
| Regras de negócio (C#) | `dotnet/src/AdriPoltronas.Domain/` |
| Casos de uso (C#) | `dotnet/src/AdriPoltronas.Application/UseCases/` |
| Acesso a dados (EF Core) | `dotnet/src/AdriPoltronas.Infrastructure/Persistence/` |
| Views e ViewModels (Avalonia) | `dotnet/src/AdriPoltronas.Desktop/` |
| Ciclo de vida do backend | `electron/backend.ts` |
| Entry point do backend | `backend/servidor.py` |
| API endpoints | `backend/blueprints/` |
| Database logic | `backend/database.py` |
| Validation rules | `backend/validators.py` |
| Configuration | `backend/config.py` |
| API response format | `API_STANDARD.md` |
| Formatação de planilhas | `backend/planilha.py` |
| Frontend | `frontend/` |
| Tests | `tests/` |
| Migrations | `backend/migrations/` |

---

## 📖 DOCUMENTATION

- **BUILD_GUIDE.md** - Build, dev, deploy guide
- **API_STANDARD.md** - API response standards
- **IMPLEMENTATION_REPORT.md** - Full audit report
- **COMPLETION_SUMMARY.md** - Executive summary

---

## 🔑 KEY FILES MODIFIED

### Backend Refactored
- `app.py` - Now 250 lines (was 837)
- `blueprints/` - 10 new modular files
- `config.py` - Shared configuration
- `migrations/` - Alembic schema versioning

### Frontend Enhanced
- `index.html` - Tab "Pagamentos" added
- `app.js` - Payment functions added

### Motor de exibição
- `electron/` - Processo principal em TypeScript (substituiu o pywebview/WebView2)
- `package.json` - Manifesto + config do electron-builder (substituiu `setup.iss`)
- `AdriPoltronasBackend.spec` - PyInstaller do backend (era `AdriPoltronasApp.spec`)
- `qt-app/` - Segunda interface em C++/Qt sobre o mesmo backend (ver `qt-app/README.md`)
- `dotnet/` - Aplicativo C#/Avalonia em camadas, sobre o mesmo banco (ver `dotnet/README.md`)

### New DevOps
- `build.py` - Cross-platform build script
- `Makefile` - Unix targets
- `.github/workflows/ci.yml` - CI/CD pipeline
- `.env.example` - Config template

---

## ⚙️ CONFIGURATION

### Environment Variables (.env)
```bash
ADRI_FLASK_SECRET=your_secret_here
ADRI_MICROSOFT_CLIENT_ID=your_client_id
GEMINI_API_KEY=your_gemini_key
ASAAS_API_KEY=your_asaas_key
ASAAS_SANDBOX=true
# Token do webhook Asaas - obrigatorio e DIFERENTE da ASAAS_API_KEY
ASAAS_WEBHOOK_TOKEN=your_webhook_token
```

### Microsoft / OneDrive (exportacao para Excel)

Escopos pedidos no login (`config.ESCOPOS_MICROSOFT`, usado tanto na
autorizacao quanto na troca do code):

```text
User.Read Files.ReadWrite offline_access
```

`offline_access` e o que rende o **refresh_token**. Sem ele a Microsoft entrega
so um access_token de ~1 hora e o operador precisa refazer o login no navegador
a cada vez que a hora vira. Com ele, `backend/microsoft.py` renova o token em
silencio antes de cada uso do Graph.

O que precisa estar certo no registro do Azure AD (portal → App registrations):

| Item | Valor esperado |
|---|---|
| Application (client) ID | igual a `ADRI_MICROSOFT_CLIENT_ID` |
| Redirect URI | `http://localhost:5000/callback` |
| Tipo do redirect | **Mobile and desktop applications** (cliente publico) |
| Allow public client flows | Habilitado — o app usa PKCE, sem client secret |
| Permissoes delegadas | `User.Read`, `Files.ReadWrite` |

A porta 5000 e fixa justamente porque o redirect URI esta registrado nela;
sortear porta quebra o login.

Ao adicionar `offline_access` a um app que ja tinha consentimento, a Microsoft
pede o consentimento de novo **uma vez** por usuario. E esperado.

Diagnostico rapido do registro, sem concluir login:

```bash
curl -s -o /dev/null -w "%{http_code}\n" "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=$ADRI_MICROSOFT_CLIENT_ID&response_type=code&redirect_uri=http%3A%2F%2Flocalhost%3A5000%2Fcallback&scope=User.Read"
```

`AADSTS700038` no corpo da resposta significa client_id invalido.

### Database Migrations
```bash
cd backend
alembic revision --autogenerate -m "Description"
alembic upgrade head
```

---

## 🧪 TESTING

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_api.py -v

# Specific test
pytest tests/test_api.py::test_index_page -v

# With coverage (rode de dentro de backend/)
cd backend && pytest ../tests --cov=. --cov-report=term-missing
```

**Current Status:** 292/292 tests passing ✅ (cobertura 79%)

---

## 🔒 SECURITY CHECKLIST

- ✅ Webhook autenticado por token estático (`asaas-access-token`), fail closed
- ✅ Proteção contra CSRF (checagem de `Origin`/`Referer`)
- ✅ Cabeçalhos de segurança (CSP, nosniff, DENY, no-referrer)
- ✅ Rate limiting configured
- ✅ SQL injection prevented (parameterized)
- ✅ Input validation centralized
- ✅ Credentials in .env (not in code)
- ✅ `pip-audit` bloqueante no CI + scan de segredos
- ⏳ SRI nos assets de CDN (pendente: exige vendorizar os arquivos)

---

## 📋 FORMATO DE RESPOSTA

A API não usa envelope. Veja `API_STANDARD.md` para o contrato completo.

```python
# Sucesso
return jsonify(dados), 200

# Erro (a chave `erro` e obrigatoria - o frontend depende dela)
return jsonify({"erro": "Cliente nao encontrado."}), 404
```

> O módulo `api_response.py` foi removido em 07/08/2026: existia mas nenhum
> endpoint o usava. Veja a errata em `COMPLETION_SUMMARY.md`.

---

## 🐛 TROUBLESHOOTING

### Tests failing
```bash
python build.py clean
pip install -r backend/requirements.txt --force-reinstall
python build.py test
```

### Build failing
- Check `icone_sistema.ico` exists
- Check PyInstaller installed: `pip install pyinstaller`
- Check logs in `build/` directory

### Janela em branco
O backend não subiu. Rode `python backend/servidor.py` sozinho para ver o erro.

### Port 5000 occupied
```bash
# Find process
netstat -ano | findstr :5000

# Kill it
taskkill /PID <PID> /F
```

---

## 📞 GETTING HELP

- Check **BUILD_GUIDE.md** for detailed instructions
- Check **API_STANDARD.md** for response format
- Run `python build.py help` for build commands
- Run `make help` for Makefile targets

---

## 🎯 NEXT PRIORITIES

1. **This week:** Gerar o instalador ponta a ponta (`python build.py installer`)
2. **Next 2 weeks:** Modularize frontend (Vite), migrate endpoints
3. **This month:** Add E2E tests, observability (Sentry)

---

**Last Updated:** 2026-08-05T05:37:08Z  
**Status:** ✅ Production Ready
