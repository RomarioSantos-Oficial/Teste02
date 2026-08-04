# Guia Completo de Build - SectorFlow ALFA

## Visao Geral

Este guia explica como transformar o projeto **SectorFlow ALFA** em uma aplicacao executavel instalavel para Windows que pode ser distribuida e instalada em qualquer outro PC.

## Sim, e possivel!

O projeto ja foi projetado para ser empacotado com **PyInstaller**, incluindo logica de resilencia no `lmu_adapter.py` que detecta `sys._MEIPASS` (o caminho onde o PyInstaller coloca os arquivos). Portanto, o processo de build e totalmente suportado.

---

## O Que Voce Precisa

| Ferramenta | O Que Faz | Onde Baixar |
|---|---|---|
| **Python 3.10+** | Runtime do Python | https://www.python.org/downloads/ |
| **PySide6** | Framework Qt (interface grafica) | Instalado via pip |
| **PyInstaller** | Empacota Python em .exe | Instalado via pip |
| **Inno Setup 6+** | Cria instalador .exe profissional | https://jrsoftware.org/isinfo.php |

---

## Metodo 1: Build Rapido (Portavel)

O metodo mais simples. Gera uma pasta que voce pode copiar para qualquer PC.

### Passo 1: Instalar Python

Baixe e instale o **Python 3.10+** do site oficial. Durante a instalacao, marque a opcao **"Add Python to PATH"**.

### Passo 2: Abrir Terminal

Abra o **Command Prompt** ou **PowerShell** na raiz do projeto (onde esta o arquivo `run.py`).

### Passo 3: Executar o Build

```batch
build\build_portable.bat
```

Ou manualmente:

```batch
pip install PySide6 pyinstaller
pyinstaller --clean --noconfirm build\SectorFlow.spec
xcopy /E /I /Y dist\SectorFlow app\SectorFlow
```

### Resultado

Apos o build, voce tera:

```
app/SectorFlow/
  SectorFlow.exe          <-- Executavel principal
  _internal/              <-- Todas as dependencias
  images/                 <-- Logos, badges, bandeiras, etc.
  data/                   <-- Mapas, perfis, flags
  vendor/                 <-- Bibliotecas LMU
```

**Para instalar em outro PC:** Basta copiar toda a pasta `app\SectorFlow` para o computador destino e executar `SectorFlow.exe`.

---

## Metodo 2: Build com Instalador Profissional

Este metodo cria um instalador `.exe` que o usuario executa para instalar o programa.

### Passo 1: Fazer o Build do Executavel

Execute o **Metodo 1** acima primeiro para gerar o executavel.

### Passo 2: Instalar o Inno Setup

Baixe e instale o **Inno Setup 6** em: https://jrsoftware.org/isinfo.php

### Passo 3: Gerar Assets do Instalador (BMP e ICO)

```batch
python build\create_installer_assets.py
```

### Passo 4: Compilar o Instalador

Abra o **Inno Setup Compiler** e carregue o arquivo:

```
build\sectorflow_installer.iss
```

Depois clique em **Build > Compile**.

Ou via linha de comando:

```batch
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build\sectorflow_installer.iss
```

### Resultado

O instalador sera gerado em:

```
app/SectorFlow_Setup_0.0.1.exe
```

Este arquivo pode ser distribuido e o usuario executa para instalar automaticamente, com icone na area de trabalho, entrada no menu Iniciar, etc.

---

## Metodo 3: Build Completo (com Assinatura Digital)

Para distribuir profissionalmente sem avisos do Windows SmartScreen.

### Passo 1: Obter Certificado de Code Signing

Compre um certificado Authenticode de uma CA confiavel (DigiCert, Sectigo, GlobalSign).

### Passo 2: Executar o Build Completo

```powershell
powershell -ExecutionPolicy Bypass -File build\build_all.ps1 -SignWithCert "C:\cert\meu_cert.pfx" -CertPassword "SENHA"
```

---

## Estrutura do Projeto de Build

```
build/
  SectorFlow.spec          <- Configuracao do PyInstaller
  build_portable.bat       <- Build rapido (portavel)
  build_sectorflow.bat     <- Build basico
  build_all.ps1            <- Build completo (PowerShell)
  sectorflow_installer.iss <- Script Inno Setup
  create_installer_assets.py <- Gera BMP e ICO do instalador
  README_BUILD.md          <- Este guia
```

---

## Arquivos Empacotados

O PyInstaller inclui automaticamente:

| Tipo | Conteudo |
|---|---|
| Python modules | Todo o codigo `src/` |
| Imagens | `images/` (logos, badges, flags, tempo, logo) |
| Dados | `data/flags/`, `data/track_maps/`, `data/vehicle_catalog/`, `data/online_profiles/` |
| Config | `src/config/widgets.json` |
| Bibliotecas | `vendor/pyLMUSharedMemory/` (se existir) |
| Dependencias | PySide6, Qt6, e todas as DLLs necessarias |

---

## Notas Importantes

1. **Windows x64**: O executavel e especifico para Windows 64-bit. Para outros sistemas, execute o build diretamente no PC alvo.

2. **vendor/pyLMUSharedMemory**: A pasta `vendor/pyLMUSharedMemory` esta vazia no repositorio. Para que a leitura de memoria compartilhada do LMU funcione, e necessario adicionar os arquivos `lmu_data.py` e `lmu_mmap.py` nessa pasta antes do build.

3. **SmartScreen**: Executaveis novos sem assinatura digital podem receber avisos do Windows SmartScreen. Isso desaparece apos adquirir reputacao ou com assinatura digital.

4. **Atualizacoes**: Ao atualizar o codigo no GitHub, basta refazer o build para gerar o novo executavel.

---

## Solucao de Problemas

| Problema | Solucao |
|---|---|
| Python nao encontrado | Reinstale Python e marque "Add to PATH" |
| PySide6 nao encontrado | Execute `pip install PySide6` |
| PyInstaller nao encontrado | Execute `pip install pyinstaller` |
| Build falha com import errors | Verifique se todos os modulos estao no `hiddenimports` do `.spec` |
| SmartScreen bloqueia | Assine com certificado Authenticode |
| LMU nao conecta | Verifique se o LMU esta rodando com telemetry ativa |
