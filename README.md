# SectorFlow ALFA

Overlay de telemetria para **Le Mans Ultimate (LMU)** no Windows. O SectorFlow lê dados locais do jogo, apresenta informações da corrida em janelas transparentes e permite configurar cada elemento pelo menu principal.

> Versão atual: **0.0.6**<br>
> Plataforma: **Windows 10/11 x64**<br>
> O programa permite somente uma instância por usuário.

## Aviso de uso comercial e licenças

**É proibido vender, cobrar pelo acesso ou redistribuir como produto próprio a compilação oficial, o instalador, a marca, o nome e os logotipos do SectorFlow sem autorização prévia e escrita do titular desses materiais.**

Partes do código contêm avisos da **GNU General Public License versão 3** e código derivado do TinyPedal. A regra acima não elimina os direitos concedidos pela GPL aos componentes cobertos por ela. A GPL permite distribuição, modificação e atividade comercial quando suas condições são cumpridas. Marcas, nomes e materiais gráficos podem ter regras distintas. Preserve sempre os avisos de autoria e identifique a licença de cada componente.

Este projeto não é afiliado, patrocinado ou aprovado pelos responsáveis pelo Le Mans Ultimate.

## Requisitos

- Windows 10 ou 11 x64;
- Le Mans Ultimate instalado;
- aproximadamente 700 MB livres após a instalação;
- LMU e SectorFlow executados no mesmo usuário do Windows.

Python, PySide6 e Inno Setup **não são necessários** no computador do usuário. As dependências acompanham o instalador.

## Instalação normal

1. Copie `SectorFlow_Setup_0.0.6.exe` para o computador.
2. Feche versões antigas pela bandeja: botão direito no ícone e **Sair**.
3. Execute o instalador.
4. Escolha **Português Brasileiro** ou **English**.
5. Avance pelas telas, escolha os atalhos e conclua.
6. Abra o SectorFlow pelo Menu Iniciar.

Pasta padrão do programa:

```text
%LOCALAPPDATA%\Programs\SectorFlow ALFA
```

Configurações pessoais:

```text
%LOCALAPPDATA%\SectorFlow\widgets.json
```

As configurações ficam separadas para que uma atualização não apague o layout do usuário.

## Instalação pelo CMD

Abra o **Prompt de Comando** na pasta do instalador.

Assistente visual:

```bat
SectorFlow_Setup_0.0.6.exe
```

Instalação silenciosa:

```bat
SectorFlow_Setup_0.0.6.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS
```

Instalação silenciosa com log:

```bat
SectorFlow_Setup_0.0.6.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /LOG="%TEMP%\SectorFlow-install.log"
```

Verifique o resultado:

```bat
echo %ERRORLEVEL%
```

O código `0` indica sucesso.

## Execução pelo CMD

```bat
"%LOCALAPPDATA%\Programs\SectorFlow ALFA\SectorFlow.exe"
```

Se já estiver aberto, o comando não cria outro processo: a janela existente é trazida para frente.

Verificar o processo:

```bat
tasklist /FI "IMAGENAME eq SectorFlow.exe"
```

Encerramento emergencial, apenas se **Sair** não responder:

```bat
taskkill /IM SectorFlow.exe /F
```

## Atualização

Não desinstale a versão anterior. Execute o instalador novo por cima dela.

- O mesmo `AppId` identifica a instalação existente.
- A pasta e as tarefas escolhidas anteriormente são reutilizadas.
- O Inno Setup compara as regras de versão/conteúdo e substitui arquivos aplicáveis.
- O instalador detecta o mutex do SectorFlow e pede que ele seja fechado.
- As preferências em `%LOCALAPPDATA%\SectorFlow` são preservadas.

Exemplo para uma versão futura:

```bat
SectorFlow_Setup_NOVA_VERSAO.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS
```

## Verificação do arquivo

```bat
powershell -NoProfile -Command "Get-FileHash '.\SectorFlow_Setup_0.0.6.exe' -Algorithm SHA256"
```

SHA-256 do instalador 0.0.6:

```text
13CDA1EFE9BF3F4C56098FE1E1AC40E28D500F163FCBF4D6D349253445A4AD88
```

Se o valor for diferente, confirme a origem antes de executar.

## Primeira utilização

1. Abra o SectorFlow.
2. Abra o LMU e entre em uma sessão na pista.
3. Aguarde o estado de conexão no menu.
4. Ative os widgets desejados.
5. Ligue o **Modo edição** para mover, redimensionar e configurar.
6. Desligue o modo edição antes de dirigir.
7. Feche a janela principal para mantê-lo na bandeja.

Menu da bandeja, perto do relógio:

- **Abrir SectorFlow**;
- **Ativar overlays** ou **Desativar overlays**;
- **Sair**.

## Desinstalação

Use **Configurações > Aplicativos > Aplicativos instalados > SectorFlow ALFA > Desinstalar** ou execute:

```bat
"%LOCALAPPDATA%\Programs\SectorFlow ALFA\uninstall\unins000.exe"
```

A configuração pessoal pode permanecer em `%LOCALAPPDATA%\SectorFlow` para permitir uma reinstalação sem perder o layout.

## Usar uma versão pelo Git

Esta seção é para quem deseja executar o programa diretamente pelo código-fonte. Quem usa `SectorFlow_Setup_0.0.6.exe` não precisa instalar Git, Python nem criar `.venv`.

### 1. Instalar as ferramentas

Instale:

- [Git para Windows](https://git-scm.com/download/win);
- Python 3.10 ou superior, com a opção **Add Python to PATH** marcada.

Confirme pelo CMD:

```bat
git --version
python --version
```

### 2. Clonar o repositório

No CMD, escolha uma pasta e execute:

```bat
git clone https://github.com/RomarioSantos-Oficial/Teste02.git
cd Teste02
```

### 3. Escolher a versão

Usar a versão mais recente da branch principal:

```bat
git switch main
git pull --ff-only origin main
```

Listar tags disponíveis:

```bat
git tag --list
```

Usar uma tag específica, quando o projeto possuir tags:

```bat
git switch --detach NOME_DA_TAG
```

Usar um commit específico:

```bat
git switch --detach CODIGO_DO_COMMIT
```

Exemplo com o commit da versão documentada:

```bat
git switch --detach 5ff1cd5
```

O modo `detached HEAD` é normal quando se escolhe uma tag ou commit somente para uso. Para editar o código a partir dele, crie uma branch:

```bat
git switch -c minha-versao
```

### 4. Criar o ambiente virtual

Dentro da raiz do repositório:

```bat
python -m venv .venv
```

Ativar no **CMD**:

```bat
.venv\Scripts\activate.bat
```

Ativar no **PowerShell**:

```powershell
.\.venv\Scripts\Activate.ps1
```

Quando estiver ativo, normalmente aparece `(.venv)` no começo da linha do terminal.

Se o PowerShell bloquear a ativação, use o CMD ou libere apenas a sessão atual:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 5. Instalar os requisitos

Com o `.venv` ativado:

```bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

As bibliotecas são instaladas somente dentro de `.venv`, sem alterar o Python global do computador.

### 6. Executar pelo código-fonte

```bat
python run.py
```

Também é possível executar sem ativar o ambiente:

```bat
.venv\Scripts\python.exe run.py
```

Para encerrar o ambiente virtual depois de fechar o programa:

```bat
deactivate
```

### 7. Atualizar o código clonado

Se estiver usando a `main`:

```bat
git switch main
git pull --ff-only origin main
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Execute novamente porque uma atualização pode modificar `requirements.txt`.

Para trocar para outra tag ou commit:

```bat
git fetch --all --tags --prune
git switch --detach NOME_DA_TAG_OU_COMMIT
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 8. Voltar para a versão mais recente

```bat
git switch main
git pull --ff-only origin main
```

## Gerar o executável e o instalador

Além do ambiente descrito acima, o build do instalador exige o Inno Setup 6.

Build completo:

```bat
powershell -ExecutionPolicy Bypass -File build\build_all.ps1
```

Somente o aplicativo:

```bat
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm --workpath build\work build\SectorFlow.spec
```

Somente o instalador, depois de gerar `dist\SectorFlow`:

```bat
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build\sectorflow_installer.iss
```

O resultado é criado em `app`.

## Problemas comuns

### O Windows bloqueia o instalador

O instalador ainda não possui assinatura digital reconhecida. Em computadores pessoais, o SmartScreen pode oferecer **Mais informações > Executar assim mesmo**. Em computadores administrados, somente o administrador pode autorizar. Não contorne políticas corporativas.

### Não aparece telemetria

- Confirme que o LMU está aberto e o carro está na pista.
- Execute LMU e SectorFlow no mesmo usuário.
- Overlays podem ficar ocultos no menu, replay, garagem, pausa ou fim da sessão.
- Reinicie os dois programas.

### Fechei a janela e continua aberto

É intencional: ele continua na bandeja. Use botão direito no ícone e **Sair**.

### Tentei abrir novamente e nada aconteceu

Somente uma instância é permitida. Procure o ícone na bandeja, inclusive dentro da seta `^`. A segunda abertura deve mostrar a janela existente.

### Restaurar toda a configuração

Saia do SectorFlow, faça backup e renomeie a configuração:

```bat
copy "%LOCALAPPDATA%\SectorFlow\widgets.json" "%USERPROFILE%\Desktop\widgets-backup.json"
ren "%LOCALAPPDATA%\SectorFlow\widgets.json" widgets-antigo.json
```

Na próxima abertura, os padrões serão recriados.

## Documentação adicional

Consulte [app/README.md](app/README.md) para conhecer cada widget, uso diário, limitações e diagnósticos detalhados.
