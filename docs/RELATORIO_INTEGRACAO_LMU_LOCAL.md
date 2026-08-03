# Relatorio da integracao LMU local no Sector Flow

Data da analise: 3 de agosto de 2026.

## Resultado

O Sector Flow passou a usar uma arquitetura hibrida:

1. A memoria compartilhada continua sendo a fonte de alta frequencia para
   fisica, comandos, motor, velocidade e movimento dos carros.
2. A API oficial local do LMU em `http://localhost:6397` complementa e, nos
   campos em que e mais confiavel, corrige estado do jogo, sessao, clima,
   standings, pneus, combustivel, energia virtual, danos e estrategia.
3. DR e SR sao obtidos pelo mesmo fluxo RaceOS usado pela interface do LMU.
   Eles nao existem diretamente como campos do Swagger local.

O schema Swagger observado nesta versao do LMU possui 179 rotas. Apenas
rotas de leitura foram usadas. Nenhum comando de pilotagem, setup, box,
replay ou navegacao e enviado ao jogo.

## Melhorias implementadas

### Coletor central leve

Foi criado um coletor REST em uma thread de segundo plano. Uma demora ou
falha do HTTP local nao bloqueia o ciclo principal dos widgets. O coletor:

- consulta apenas `GetGameState` e `navigation/state` fora de uma sessao;
- habilita dados de sessao apenas dentro de `NAV_EVENT`;
- habilita pneus e condicao do carro somente quando existe veiculo carregado;
- usa timeout curto, validade por campo e recuo automatico depois de erro;
- troca respostas completas de forma atomica, sem copiar standings grandes
  a cada quadro;
- mantem a memoria compartilhada como fallback se a API ficar indisponivel.

Intervalos atuais:

| Endpoint | Intervalo | Uso no Sector Flow |
|---|---:|---|
| `/rest/sessions/GetGameState` | 0,50 s | carro, monitor, replay, fim, box e no de clima |
| `/navigation/state` | 0,75 s | menu, evento e carregamento |
| `/rest/watch/sessionInfo` | 0,75 s | sessao, tempo, pista, chuva, vento e bandeiras por setor |
| `/rest/watch/standings` | 0,75 s | classificacao oficial e dados extras de cada carro |
| `/rest/garage/tireinfo` | 0,75 s | temperaturas L/C/R, pressao e carga dos pneus |
| `/rest/garage/getVehicleCondition` | 1,00 s | combustivel, pneus, freios, suspensao e dano do jogador |
| `/rest/strategy/pitstop-estimate` | 2,00 s | previsao de duracao do pit stop |
| `/rest/strategy/usage` | 3,00 s | stints, pit, combustivel, pneus e energia virtual |
| `/rest/watch/getIncidentsList/1` | 3,00 s | incidentes publicados pelo jogo |
| `/rest/sessions/weather` | 10,00 s | grade oficial de previsao por sessao |
| `/rest/sessions/GetSessionsInfoForEvent` | 15,00 s | sessoes seguintes, temperatura e chance de chuva |
| `/navigation/GetLoadingScreen` | 30,00 s | carro e pista selecionados, carregados sob demanda |

### Visibilidade correta dos widgets

A exibicao agora considera conjuntamente:

- `navigationState`;
- `inControlOfVehicle`;
- `inMonitor`;
- `playerVehicleLoaded`;
- `isReplayActive`;
- `raceFinished`;
- `inRealtime`.

Isso resolve memoria compartilhada congelada ao sair do carro. No teste real,
o LMU estava em `NAV_EVENT`, com `inControlOfVehicle=true`, mas tambem
`inMonitor=true` e `inRealtime=false`; o resultado correto foi manter os
widgets ocultos. No menu principal, onde `GetGameState` pode responder HTTP
503, `navigation/state` continua sendo usado para ocultar tudo corretamente.

### Clima e previsao

Os valores atuais passam a vir de `/rest/watch/sessionInfo`:

- temperatura ambiente e da pista;
- chuva atual;
- umidade minima, media e maxima do caminho;
- nuvens escuras;
- vento;
- tempo restante da fase;
- estado amarelo e bandeira de cada setor.

A previsao usa `/rest/sessions/weather`, separada da medicao atual. Foi
corrigido o icone futuro que anteriormente recebia chuva zero e podia repetir
o clima atual. A grade do LMU continua sendo uma estimativa; ela nao garante
que a chuva prevista realmente acontecera.

### Standings

`/rest/watch/standings` agora complementa cada piloto pelo `slotID` e, como
fallback, pelo nome normalizado. Sao usados:

- posicao, voltas, setor e distancia na volta;
- melhor e ultima volta quando o tempo e valido;
- intervalos para o lider e carro da frente;
- `countLapFlag` para saber se a volta atual conta tempo;
- numero, equipe, modelo, arquivo do veiculo e grupo de box;
- DRS, farois, pit, garagem, paradas, penalidades e bandeira;
- status de chegada, desclassificacao ou abandono;
- combustivel e energia virtual de cada carro quando o servidor publica;
- Attack Mode, incluindo usos e tempo restante.

O valor de energia dos outros carros deixa de depender primeiro de uma
extrapolacao de estrategia: `veFraction` oficial tem prioridade. Quando um
servidor nao publica o campo, o comportamento anterior permanece como
fallback.

### Pneus, combustivel e danos

O widget de pneus passa a preferir a temperatura de superficie media, porque
o LMU publica diretamente esquerda, centro e direita em Kelvin. A conversao
para Celsius foi validada. Valores crus iguais a zero nao viram mais
`-273,15 C`.

Tambem sao lidos:

- pressao oficial em kPa;
- carga convertida de kg para N;
- vida restante dos quatro pneus;
- vida dos quatro freios;
- dano de suspensao por roda;
- dano geral do veiculo;
- litros atuais e capacidade total.

Dados REST lentos nunca substituem sinais de fisica de alta frequencia que a
memoria compartilhada ja entrega melhor.

### DR, SR, pais e badge

O Swagger local oferece `getAuthSessionTicket`, mas nao devolve DR/SR em uma
rota REST local. O fluxo correto identificado na interface oficial e:

1. `GET /rest/profile/getAuthSessionTicket` no LMU local;
2. `POST https://raceos.gg/authenticate` com jogo `lmu` e plataforma `steam`;
3. `POST https://raceos.gg/api/v1/players` com os nomes publicados em
   `/rest/multiplayer/teams` ou nos standings;
4. associacao do perfil ao piloto por Steam ID, username, nome exato e nome
   sem o sufixo `#1234`.

O Sector Flow nao precisa de chave Nakama externa. O ticket e o access token
sao temporarios, ficam somente na memoria e nao entram em arquivo de log nem
em diagnostico exportado. A atualizacao e feita na troca do roster e, em
regime normal, no maximo a cada 900 segundos.

Validacao real: 16 pilotos da sessao foram encontrados no RaceOS com DR, SR
e pais. Uma entrada administrativa do roster foi corretamente ignorada por
nao representar um perfil de piloto.

## Ordem de confianca dos dados

| Informacao | Fonte preferida | Fallback |
|---|---|---|
| Fisica e comandos do jogador | memoria compartilhada | nenhum |
| Posicao e estado dos adversarios | REST standings | memoria compartilhada |
| Presenca no carro/menu/monitor | REST estado+navegacao | memoria compartilhada |
| Clima atual e pista | REST sessionInfo | memoria compartilhada |
| Previsao | REST weather | memoria compartilhada, quando publicada |
| Pneu/combustivel/dano do jogador | REST garage | memoria compartilhada |
| Energia dos adversarios | REST `veFraction` | historico de estrategia |
| Pais e badge | REST multiplayer/teams | perfil RaceOS |
| DR e SR | RaceOS oficial | ocultar campo se indisponivel |

Um valor ausente nunca deve ser inventado. O widget deve mostrar `--` ou
ocultar a coluna quando nem a fonte oficial nem o fallback possuem o dado.

## Rotas uteis para uma proxima etapa

### Alta prioridade

- `/rest/watch/standings/history`: historico de posicao, setores e voltas.
  Pode melhorar a linha do tempo e a recuperacao de voltas, mas a resposta
  observada nao traz um marcador explicito de invalidacao. Nao se deve tratar
  automaticamente todo `lapTime=-1` como uma volta completa invalidada.
- `/rest/watch/trackmap`: 1.340 pontos no circuito observado. Deve ser lido
  uma vez por pista e colocado em cache; a resposta tinha cerca de 107 KB e
  nao deve ser consultada continuamente.
- `/navigation/GetLoadingScreen`: ja e coletado lentamente e pode substituir
  heuristicas de nome, fabricante, numero e pais da pista.
- `/rest/garage/summary`: pode fornecer carro, fabricante e setup ativo. A
  resposta observada tinha cerca de 25 KB; consultar apenas ao trocar carro,
  pista ou setup.

### Prioridade media

- `/rest/garage/getPlayerGarageData`: TC, ABS, brake bias, mapa de motor,
  regeneracao, asas, dutos e outros valores do setup. Tinha cerca de 42 KB;
  usar apenas na garagem e por evento de mudanca.
- `/rest/watch/getBookmarkedTimestamps` e incidentes: util para replay e
  revisao de contatos, sem atribuir culpa automaticamente.
- `/rest/race/car`, `/rest/sessions/getAllVehicles` e imagens: melhorar o
  catalogo e logos, com cache permanente. Sao endpoints pesados e alguns
  builds demoram mais de um segundo para responder.
- `/rest/profile/profileInfo/getProfileInfo`: dados do proprio jogador, como
  pais e Steam ID. Ja e usado lentamente no standings.

### Opcional: WebSocket oficial

O servidor de broadcast do LMU tambem publica dados em
`ws://localhost:6398/websocket/controlpanel`, incluindo `standings`,
`sessionInfo` e `standingsHistory`. Uma fase futura pode substituir parte do
polling de `watch` por mensagens push. Antes disso, e necessario medir
reconexao, perda de mensagens e compatibilidade entre builds; o REST atual e
mais simples como fallback.

## Rotas que nao devem ser automatizadas pelo overlay

As rotas `POST`, `PUT` ou `DELETE` para dirigir, sair do veiculo, assumir
controle, mudar setup, acionar pit menu, reiniciar sessao, controlar replay ou
navegar na interface podem alterar o jogo. Elas ficaram deliberadamente fora
do coletor. Um overlay de leitura nao deve executar essas acoes sem um comando
explicito do usuario.

## Limites reais da API

- DR e SR nao estao no JSON local do Swagger; dependem do RaceOS e de uma
  sessao valida do jogador.
- Temperatura, desgaste e dano detalhado dos carros adversarios geralmente
  nao sao publicados. O programa nao deve estimar esses valores como se
  fossem exatos.
- A previsao meteorologica e uma grade de probabilidade do evento, nao uma
  leitura do futuro realizado.
- O jogo pode devolver 503 ou corpo vazio durante trocas de menu, carregamento
  e encerramento. Isso e tratado como estado transitório.
- Nem todo servidor publica combustivel ou energia dos adversarios.
- A API de incidentes informa eventos, mas nao determina culpa com seguranca.

## Validacoes executadas

- testes unitarios de merge REST, expiracao de dados e visibilidade;
- testes do fluxo RaceOS em lote, sem chave externa;
- compilacao de todo o diretorio `src`;
- leitura real da API com 15 carros no adapter central;
- estado real de monitor corretamente oculto;
- clima real recebido: chuva, umidade da pista, ar e pista;
- pneus reais convertidos de Kelvin para Celsius;
- RaceOS real associado ao roster sem imprimir ou persistir credenciais.

## Recomendacao final

Manter a combinacao atual: memoria compartilhada para sinais rapidos, REST
para estado oficial e dados de interface, RaceOS apenas para perfis. A proxima
melhoria com melhor relacao entre precisao e custo e carregar
`/rest/watch/trackmap` uma vez por pista. Depois, testar o WebSocket 6398 como
otimizacao opcional, sempre mantendo o REST como fallback.

