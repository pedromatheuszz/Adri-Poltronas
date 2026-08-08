# ✅ QUICK REFERENCE - Adri Poltronas

## 🚀 START HERE

### First Time Setup
```bash
# 1. Install dependencies
python build.py install-deps

# 2. Run tests to verify
python build.py test

# 3. Start development
python main.py
```

### Common Commands
```bash
# Testing
python build.py test          # Run all tests
make test                      # Alternative

# Building
python build.py build         # Full build with PyInstaller
make build                    # Alternative

# Development
python main.py                # Run application
make dev                      # Flask debug mode

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

**Current Status:** 48/48 tests passing ✅
(28 funcionais + 20 de regressão em `tests/test_regressoes.py`)

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

1. **This week:** Test builds, validate CI/CD
2. **Next 2 weeks:** Modularize frontend (Vite), migrate endpoints
3. **This month:** Add E2E tests, observability (Sentry)

---

**Last Updated:** 2026-08-05T05:37:08Z  
**Status:** ✅ Production Ready
