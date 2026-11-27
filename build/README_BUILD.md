# Build Guide - SectorFlow Overley 1.2

Este diretório contém o pipeline para gerar o pacote portátil e o instalador do **SectorFlow Overley 1.2** para Windows.

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

### 1. Gerar as distribuições

Abra o terminal na raiz do projeto (onde está `run.py`) e execute:

```powershell
powershell -ExecutionPolicy Bypass -File build\build_all.ps1
```

O build completo usa PyInstaller e Inno Setup 6 e gera:
- `app\SectorFlow\` — pasta portátil pronta para executar;
- `app\SectorFlow_Portable_1.2.zip` — pacote para copiar para outro PC;
- `app\SectorFlow_Setup_1.2.exe` — instalador profissional.

### 3. Distribuir para Outro PC

**Opção A - Sem instalador (portátil):**
Extraia `app\SectorFlow_Portable_1.2.zip` em uma pasta nova no PC destino e execute `SectorFlow.exe`.
Para atualizar, feche o programa, remova a pasta anterior e extraia o ZIP novo.

**Opção B - Com instalador:**
Distribua `app\SectorFlow_Setup_1.2.exe`. Em atualizações, o instalador substitui os arquivos do programa e limpa os caches da instalação.

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
│   └── vendor/                    ← Aviso de licença da biblioteca LMU
│
├── SectorFlow_Portable_1.2.zip    ← Pacote portátil
└── SectorFlow_Setup_1.2.exe       ← Instalador
```

---

## Notas Importantes

- Os módulos LMU são incorporados ao executável; o pacote inclui o aviso de licença da biblioteca.
- O executável é específico para **Windows x64** (a aplicação usa memória compartilhada Windows).
- Para builds de outras arquiteturas, execute o build diretamente no PC alvo.
