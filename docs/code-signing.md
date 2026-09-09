# Code Signing para AdriPoltronasApp.exe

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

## Como assinar o `AdriPoltronasApp.exe`

### Pré-requisitos
- Windows 10/11 com **Windows SDK** instalado (vem com Visual Studio Build Tools)
- Arquivo `.pfx` ou `.p12` do certificado (você baixa da CA após compra)
- O `.pfx` deve estar no **Repositório de Certificados Pessoal** do Windows
  (duplo-clique → "Instalar" → "Usuário atual" → "Pessoal")

### Passo a passo

1. **Abra o Developer Command Prompt for VS** (tem o `signtool` no PATH).

2. **Verifique se o certificado está instalado**:
   ```cmd
   signtool sign /sm /a /fd SHA256 "C:\caminho\AdriPoltronasApp.exe"
   ```
   - `/sm` = seleciona do repositório de usuário
   - `/a` = seleciona automaticamente o certificado disponível
   - `/fd SHA256` = força digest SHA-256 (recomendado)

3. **Com timestamp** (importante — sem ele a assinatura expira com o certificado):
   ```cmd
   signtool sign /sm /a /fd SHA256 /tr http://timestamp.sectigo.com /td SHA256 "C:\caminho\AdriPoltronasApp.exe"
   ```
   - `/tr` = URL do servidor de timestamp
   - `/td SHA256` = algoritmo do timestamp

4. **Verifique a assinatura**:
   ```cmd
   signtool verify /pa "C:\caminho\AdriPoltronasApp.exe"
   ```
   Deve retornar: `Successfully verified`.

5. **Para assinar o instalador Inno Setup também** (recomendado):
   - Em `setup.iss`, adicione após `[Setup]`:
     ```ini
     SignTool=signtool sign /sm /a /fd SHA256 /tr http://timestamp.sectigo.com /td SHA256 $f
     SignedUninstaller=yes
     ```
   - O Inno Setup chama `signtool` automaticamente durante a build.

### Variáveis de ambiente úteis (CI/CD)
```cmd
set CSC_LINK=C:\caminho\certificado.pfx
set CSC_KEY_PASSWORD=senha-do-certificado
```

---

## Integração com o build (PyInstaller)

O PyInstaller não assina diretamente, mas você pode:

### Opção A: script `build.bat`
```bat
@echo off
pyinstaller AdriPoltronasApp.spec --clean
signtool sign /sm /a /fd SHA256 /tr http://timestamp.sectigo.com /td SHA256 dist\AdriPoltronasApp\AdriPoltronasApp.exe
echo Build + sign OK.
```

### Opção B: GitHub Actions (exemplo)
```yaml
- name: Sign Windows binary
  uses: sigstore/cosign-installer@main
  with:
    cosign-release: 'v2.0.0'
- name: Sign executable
  run: |
    signtool sign /fd SHA256 /tr http://timestamp.sectigo.com /td SHA256 /f ${{ secrets.CERT_FILE }} /p ${{ secrets.CERT_PASSWORD }} dist/AdriPoltronasApp/AdriPoltronasApp.exe
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
- [Inno Setup: SignTool](https://jrsoftware.org/ishelp/topic_setup_signtool.htm)
