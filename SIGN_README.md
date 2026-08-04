Passos para cumprir políticas Microsoft (SmartScreen / AppLocker / WDAC)

1) Assinatura (requer certificado de assinatura de código - Authenticode)
- Compre um certificado de Code Signing (EV recomendado) de uma CA confiável (DigiCert, Sectigo, GlobalSign).
- Ou use um certificado interno (AD CS) se sua organização controlar políticas (AppLocker/WDAC).

2) Assinar o executável
- Use o `signtool.exe` (parte do Windows SDK). Exemplo:

```powershell
# Assinatura com timestamp
.\sign.ps1 -pfxPath "C:\caminho\meu_cert.pfx" -pfxPassword "SENHA"
```

- O script `sign.ps1` procura `signtool.exe` e executa a assinatura com `sha256` + timestamp.

3) Testar SmartScreen e reputação
- SmartScreen usa reputação; builds novos podem ser sinalizados até adquirirem reputação.
- EV (Extended Validation) accelerates SmartScreen reputation and reduces blocks.

4) AppLocker / WDAC
- Para ambientes corporativos com AppLocker/WDAC, registre o Publisher (CN do certificado) ou a hash do executável na política.
- Peça ao administrador AD para adicionar regra de exceção.

5) Embalagem e instalador
- Recomendo criar um instalador (`.msi` ou InnoSetup) e assinar o instalador também.
- Ferramentas: WiX Toolset (MSI) ou Inno Setup (EXE). Assine o instalador com `signtool`.

6) Verificações locais antes de distribuir
- Execute o exe localmente com seu Python para validar:
```powershell
.venv\Scripts\python.exe run.py
```
- Verifique logs em `data/online_debug` e `data/flags` carregadas.

Se você enviar o `.pfx` e a senha, eu posso rodar `sign.ps1` aqui (se `signtool` estiver instalado). Caso contrário, eu gerei `app/` assinado localmente — você precisa executar `sign.ps1` no seu ambiente com o certificado.
