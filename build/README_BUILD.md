# Build Guide - SectorFlow ALFA

Este diretório contém tudo necessário para gerar um executável instalável do **SectorFlow ALFA** para Windows.

---

## Requisitos

| Ferramenta | Versão Mínima | Link |
|---|---|---|
| Python | 3.10+ | https://www.python.org/downloads/ |
| PySide6 | (via pip) | `pip install PySide6` |
| PyInstaller | 6.x+ (via pip) | `pip install pyinstaller` |
| Inno Setup | 6.x+ | https://jrsoftware.org/isinfo.php |

---

## Passo a Passo

### 1. Gerar o Executável (.exe)

Abra o terminal na raiz do projeto (onde está `run.py`) e execute:

```batch
build\build_sectorflow.bat
```

Ou via PowerShell (mais completo):

```powershell
powershell -ExecutionPolicy Bypass -File build\build_all.ps1
```

Isso gera:
- `app\SectorFlow\SectorFlow.exe` — o executável principal
- `app\SectorFlow\` — pasta completa com todas as dependências

### 2. Gerar o Instalador (.exe Setup)

Depois de gerar o executável, instale o [Inno Setup](https://jrsoftware.org/isinfo.php) e execute:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build\sectorflow_installer.iss
```

Isso gera:
- `app\SectorFlow_Setup_0.0.6.exe` — instalador profissional

### 3. Distribuir para Outro PC

**Opção A - Sem instalador (portável):**
Copie toda a pasta `app\SectorFlow\` para o PC destino e execute `SectorFlow.exe`.

**Opção B - Com instalador:**
Distribua o arquivo `app\SectorFlow_Setup_0.0.6.exe`. O usuário executa e o instalador cuida de tudo.

---

## Assinatura de Código (Opcional)

Para evitar avisos do Windows SmartScreen, assine o executável com um certificado Authenticode:

```powershell
.\sign.ps1 -pfxPath "C:\caminho\meu_cert.pfx" -pfxPassword "SENHA"
```

Ou com o script completo:

```powershell
.\build_all.ps1 -SignWithCert "C:\caminho\meu_cert.pfx" -CertPassword "SENHA"
```

---

## Estrutura Gerada

```
app/
├── SectorFlow/                    ← Executável portável
│   ├── SectorFlow.exe             ← Executável principal
│   ├── _internal/                 ← Dependências internas
│   ├── images/                    ← Imagens empacotadas
│   ├── data/                      ← Dados empacotados
│   └── vendor/                    ← Bibliotecas LMU
│
├── SectorFlow_Setup_0.0.6.exe     ← Instalador (se usar Inno Setup)
└── SectorFlow ALFA 0.0.6.zip      ← Pacote ZIP
```

---

## Notas Importantes

- O **vendor/pyLMUSharedMemory** deve conter os arquivos `lmu_data.py` e `lmu_mmap.py` para que a leitura de memória compartilhada do LMU funcione.
- O executável é específico para **Windows x64** (a aplicação usa memória compartilhada Windows).
- Para builds de outras arquiteturas, execute o build diretamente no PC alvo.
