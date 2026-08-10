# Guia de funcionalidades do SectorFlow ALFA

Este documento explica o aplicativo instalado. Para instalação, CMD, atualização e compilação, consulte o [README principal](../README.md).

## Funcionamento geral

O SectorFlow consulta dados locais do Le Mans Ultimate e converte essas informações em overlays independentes. Cada widget pode ser ativado, desativado, movido, redimensionado e configurado.

O programa permanece na bandeja quando a janela é fechada. Somente uma instância é permitida: clicar novamente no atalho mostra a janela já aberta.

## Fluxo recomendado

1. Abra o SectorFlow.
2. Ative somente os widgets necessários.
3. Ligue o **Modo edição**.
4. Organize, redimensione e edite os overlays.
5. Desligue o modo edição.
6. Abra o LMU e entre na pista.
7. Confirme a conexão no menu.
8. Feche a janela para deixá-lo na bandeja.

## Menu, perfis e configuração

Os widgets são organizados por corrida, carro, estratégia e sistema. Perfis permitem layouts diferentes, por exemplo piloto, engenheiro ou monitores distintos.

As alterações ficam em:

```text
%LOCALAPPDATA%\SectorFlow\widgets.json
```

Backup recomendado:

```bat
copy "%LOCALAPPDATA%\SectorFlow\widgets.json" "%USERPROFILE%\Desktop\SectorFlow-widgets-backup.json"
```

## Widgets implementados

### Standings

Classificação e dados dos participantes. Pode combinar telemetria local e enriquecimento online quando disponível. Dados online dependem da sessão, servidor e serviços locais do LMU.

### Relative

Carros próximos e diferenças relativas. Útil para tráfego e retomada à pista. Valores podem oscilar em transições de volta e boxes.

### Delta

Ganho/perda de tempo, setores, melhor volta e histórico conforme a configuração. Precisa de voltas válidas; na primeira volta pode não existir referência.

### Mapa

Desenha a pista e posiciona carros. Uma pista ou variante ainda não catalogada pode precisar de um mapa novo.

### Telemetry / Driver Panel

Painel configurável de dados do veículo e do piloto. Elementos visíveis, tamanho e aparência são definidos pelo editor.

### Battery

Energia, uso e estimativas para veículos que oferecem canais híbridos/elétricos. Em outros carros, campos podem permanecer zerados.

### Fuel Time

Consumo, autonomia e estimativas por tempo/voltas. A precisão melhora após voltas consistentes e muda com pit stop, chuva ou ritmo.

### Tyres

Temperaturas, pressão, desgaste ou estado quando publicados pelo LMU. Nem todo carro disponibiliza todos os canais.

### Damage

Danos detectados no veículo. A granularidade depende dos dados fornecidos pelo jogo.

### Weather

Condições atuais e tendências calculadas. A previsão é uma estimativa, não uma garantia das mudanças definidas pelo servidor.

### Flags

Bandeiras e estados de pista detectados na telemetria.

### Radar

Veículos ao redor do jogador. É apenas um auxílio e não substitui espelhos, spotter ou atenção do piloto.

### URL

Servidor/visualização por URL. Depende de endereço, porta, firewall e rede. Não exponha diretamente à internet sem autenticação e análise de segurança.

## Ainda não implementado

- Replay;
- Race Control.

Esses itens não devem ser considerados funcionais até uma versão futura habilitá-los.

## Bandeja do Windows

O ícone fica perto do relógio ou dentro da seta `^`.

- **Abrir SectorFlow:** mostra a janela.
- **Desativar overlays:** suspende os overlays sem encerrar.
- **Ativar overlays:** volta a exibi-los quando a sessão permitir.
- **Sair:** encerra processo, telemetria e overlays.

A seleção individual dos widgets é preservada ao desativar pela bandeja.

## Modo edição

- Ative antes de mover ou redimensionar.
- Abra o editor para mudar aparência e comportamento.
- Desative ao terminar para evitar cliques acidentais.
- Alguns overlays aparecem no modo edição mesmo sem sessão ativa.

## Quando os overlays podem desaparecer

Isso pode ser intencional quando o LMU está:

- no menu principal;
- em replay;
- na garagem/monitor;
- aguardando veículo;
- com sessão encerrada;
- pausado;
- sem memória compartilhada disponível.

## Solução de problemas

### Não encontro o ícone

Clique na seta `^` perto do relógio e confira:

```bat
tasklist /FI "IMAGENAME eq SectorFlow.exe"
```

### Há mais de um ícone, mas um processo

O Windows pode deixar temporariamente um ícone órfão após encerramento forçado. Passe o mouse sobre ele ou reinicie o Explorer.

### Widget invisível

- confirme que está ativo no perfil atual;
- ligue o modo edição e procure fora da área visível;
- considere mudança de resolução/monitores;
- restaure o widget pelo editor;
- confirme que a sessão permite overlays.

### Overlay impede cliques

Desative o modo edição e confira a opção de passagem de clique (`click-through`).

### Valores zerados ou incompletos

- aguarde sessão e carro carregarem;
- complete voltas para cálculos com histórico;
- confirme que o veículo oferece o canal;
- teste uma sessão local para separar limitações do servidor.

### Segunda abertura não cria outra janela

É o comportamento correto. Apenas uma instância pode existir. Procure a janela ou o ícone na bandeja.

### Configuração corrompida

Saia do aplicativo e execute:

```bat
copy "%LOCALAPPDATA%\SectorFlow\widgets.json" "%USERPROFILE%\Desktop\widgets-com-problema.json"
ren "%LOCALAPPDATA%\SectorFlow\widgets.json" widgets-antigo.json
```

Na próxima abertura, o programa recria os padrões. Não restaure imediatamente o arquivo possivelmente corrompido.

### URL/rede não funciona

- confirme endereço e porta;
- teste primeiro no próprio computador;
- permita apenas em redes privadas no Firewall;
- confira se os dispositivos estão na mesma rede;
- verifique se outra aplicação usa a porta.

### Atualização informa que o programa está aberto

Use **Sair** na bandeja e tente novamente. O instalador verifica o mutex para evitar substituir arquivos em uso.

## Segurança e limitações

- Overlays não substituem atenção e regras da competição.
- Serviços online podem mudar ou ficar indisponíveis.
- Não compartilhe tokens, tickets ou chaves de sessão.
- Revise diagnósticos antes de publicá-los.
- Use somente em campeonatos que permitam overlays externos.

## Ao relatar um problema

Informe versão do SectorFlow e Windows, widget, carro, pista, tipo de sessão, mensagem exibida e passos para reproduzir. Nunca publique credenciais ou tokens.
