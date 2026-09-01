# Code Signing para o instalador da Adri Poltronas

> **Status atual**: o executável **NÃO está assinado digitalmente**. Quando um usuário
> baixa e tenta abrir, o Windows SmartScreen exibe o aviso azul
> *"A proteção da Microsoft Defender SmartScreen impediu a inicialização de um app
> não reconhecido. A execução deste app pode colocar seu PC em risco."*

Esse aviso é o principal motivo de usuários desistirem da instalação de apps
pequenos e desconhecidos. Assinar digitalmente o `.exe` resolve isso.

---

## O que é code signing?

É o processo de assinar o executável com um certificado digital (X.509) emitido
por uma Autoridade Certificadora (CA) confiável. O Windows valida a assinatura
e, se válida, mostra o nome do publisher em vez do aviso genérico.

---

## Tipos de certificado

| Tipo | Custo (USD/ano) | SmartScreen | Validação |
|------|----------------|-------------|-----------|
| **EV** (Extended Validation) | ~300-500 | Reputação **imediata** | Rígida (empresa + pessoa física + hardware) |
| **OV** (Organization Validation) | ~60-200 | Reputação **após volume de downloads** | Média (empresa + domínio) |
| Auto-assinado | 0 | Não remove aviso | Nenhuma (inútil para distribuição) |

**Recomendação para Adri Poltronas**:
- Se for distribuição **interna** (poucos PCs conhecidos): OV + signing manual é suficiente.
- Se for distribuição **pública** (site, anúncios): **EV é praticamente obrigatório** —
  sem EV, o SmartScreen continua alertando por centenas/milhares de downloads.

---

## CAs conhecidas (Windows-compatible)

- **Certum** (polonesa, aceita CNPJ brasileiro) — a partir de ~$59/ano (OV)
- **SSL.com** — EV a partir de ~$329/ano
- **Sectigo (Comodo)** — EV ~$299/ano
- **GlobalSign** — EV ~$329/ano
- **DigiCert** — EV ~$499/ano (mais tradicional)

**Atenção**: algumas CAs exigem empresa aberta (CNPJ) — não emitem para pessoa
física. Verifique antes de comprar.

---

## O que precisa ser assinado

Desde a migração para o Electron, o build gera três artefatos:

| Artefato | Onde | Assinar? |
|----------|------|----------|
| `dist-instalador/AdriPoltronasSetup-<versão>.exe` | electron-builder (NSIS) | **Sim** — é o que o usuário baixa |
| `dist-instalador/win-unpacked/Adri Poltronas.exe` | electron-builder | Sim (o electron-builder assina junto) |
| `dist/AdriPoltronasBackend/AdriPoltronasBackend.exe` | PyInstaller | Opcional — não é executado diretamente pelo usuário |

O caminho mais simples é deixar o **electron-builder** assinar tudo: ele chama o
`signtool` sozinho quando encontra as variáveis `CSC_LINK` e `CSC_KEY_PASSWORD`.

```cmd
set CSC_LINK=C:\caminho\certificado.pfx
set CSC_KEY_PASSWORD=senha-do-certificado
python build.py installer
```

## Como assinar manualmente com `signtool`

### Pré-requisitos
- Windows 10/11 com **Windows SDK** instalado (vem com Visual Studio Build Tools)
- Arquivo `.pfx` ou `.p12` do certificado (você baixa da CA após compra)
- O `.pfx` deve estar no **Repositório de Certificados Pessoal** do Windows
  (duplo-clique → "Instalar" → "Usuário atual" → "Pessoal")

### Passo a passo

1. **Abra o Developer Command Prompt for VS** (tem o `signtool` no PATH).

2. **Verifique se o certificado está instalado**:
   ```cmd
   signtool sign /sm /a /fd SHA256 "C:\caminho\AdriPoltronasSetup-1.0.0.exe"
   ```
   - `/sm` = seleciona do repositório de usuário
   - `/a` = seleciona automaticamente o certificado disponível
   - `/fd SHA256` = força digest SHA-256 (recomendado)

3. **Com timestamp** (importante — sem ele a assinatura expira com o certificado):
   ```cmd
   signtool sign /sm /a /fd SHA256 /tr http://timestamp.sectigo.com /td SHA256 "C:\caminho\AdriPoltronasSetup-1.0.0.exe"
   ```
   - `/tr` = URL do servidor de timestamp
   - `/td SHA256` = algoritmo do timestamp

4. **Verifique a assinatura**:
   ```cmd
   signtool verify /pa "C:\caminho\AdriPoltronasSetup-1.0.0.exe"
   ```
   Deve retornar: `Successfully verified`.

5. **Assinatura automática pelo electron-builder** (recomendado em vez do passo manual):
   - Defina `CSC_LINK` (caminho do `.pfx`) e `CSC_KEY_PASSWORD` antes de rodar
     `python build.py installer`.
   - Para usar um certificado já instalado no repositório do Windows (token USB,
     comum em certificados EV), use `WIN_CSC_LINK` vazio e configure
     `"win": { "certificateSubjectName": "Nome no certificado" }` no `package.json`.

   > O antigo instalador Inno Setup (`setup.iss`) foi removido junto com o
   > WebView2; a diretiva `SignTool=` dele não existe mais.

### Variáveis de ambiente úteis (CI/CD)
```cmd
set CSC_LINK=C:\caminho\certificado.pfx
set CSC_KEY_PASSWORD=senha-do-certificado
```

---

## Integração com o build

### Opção A: deixar o electron-builder assinar
```cmd
set CSC_LINK=C:\caminho\certificado.pfx
set CSC_KEY_PASSWORD=senha
python build.py installer
```
O `signtool` é chamado pelo electron-builder para o `.exe` da aplicação e para
o instalador NSIS, com timestamp.

### Opção B: assinar também o backend do PyInstaller
```bat
@echo off
python build.py build
signtool sign /sm /a /fd SHA256 /tr http://timestamp.sectigo.com /td SHA256 dist\AdriPoltronasBackend\AdriPoltronasBackend.exe
npm run dist
echo Build + sign OK.
```

### Opção C: GitHub Actions (exemplo)
```yaml
- name: Sign Windows binary
  uses: sigstore/cosign-installer@main
  with:
    cosign-release: 'v2.0.0'
- name: Sign executable
  run: |
    signtool sign /fd SHA256 /tr http://timestamp.sectigo.com /td SHA256 /f ${{ secrets.CERT_FILE }} /p ${{ secrets.CERT_PASSWORD }} "dist-instalador/AdriPoltronasSetup-1.0.0.exe"
  env:
    CERT_FILE: ${{ github.workspace }}/certs/cert.pfx
```

---

## Custos totais (estimativa)

| Item | Custo |
|------|-------|
| Certificado EV (1 ano) | $300-500 |
| Conta de desenvolvedor Microsoft Partner (opcional, para o app ser "verified") | $19 (uma vez) |
| Hardware token USB (algumas CAs exigem) | $30-50 |
| Renovação anual | $300-500 |

**Total inicial**: ~$350-600 USD.

---

## Alternativas gratuitas (limitadas)

- **SignPath.io** — oferece code signing gratuito para projetos open source (precisa ser aprovado).
- **Azure Trusted Signing** (Microsoft) — novo serviço da Microsoft, integração nativa com Windows. Preços ainda em definição (final 2024+).

---

## Checklist antes de distribuir

- [ ] Certificado válido e dentro da validade
- [ ] Timestamp incluído na assinatura
- [ ] `signtool verify` retorna sucesso
- [ ] Teste em uma VM Windows limpa (sem DevMode habilitado)
- [ ] SmartScreen mostra nome do publisher (não mais o aviso azul genérico)
- [ ] URL do publisher nas propriedades do `.exe` está correta

---

## Referências

- [Microsoft: Authenticode Signing](https://learn.microsoft.com/en-us/windows/win32/seccrypto/authenticode-signing)
- [signtool documentation](https://learn.microsoft.com/en-us/windows/win32/secccode/signtool)
- [electron-builder: Code Signing](https://www.electron.build/code-signing)
