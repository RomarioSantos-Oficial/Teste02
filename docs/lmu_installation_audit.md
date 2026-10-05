# Auditoria da instalação local do Le Mans Ultimate

**Instalação examinada:** `D:\SteamLibrary\steamapps\common\Le Mans Ultimate`  
**Data:** 2026-10-02  
**Escopo:** inventário local, arquivos de usuário/telemetria, SDK Shared Memory, índices dos arquivos MAS de pistas e carros. Nenhum arquivo da instalação foi alterado.

## Resumo

Sim: a instalação contém dados de navegação para a IA interna do jogo. Os arquivos de layout incluem `.AIW` e `.GDB`, empacotados em arquivos `.mas`. O layout de Le Mans inclui `LeMansWEC.AIW` e `LeMansWEC_Mulsanne.AIW`. Os pacotes dos demais circuitos examinados também listam arquivos AIW de layout.

Esses arquivos são dados usados pela IA interna do simulador. Não são um bot externo pronto nem, pelo que foi confirmado, uma tabela simples “frear a N metros e acelerar a N metros”. A referência técnica de criação AIW do Studio 397 descreve caminhos principais, linhas de corrida, corredores, pit path e posições especiais como entradas para o comportamento dos pilotos AI. O controle de aceleração e frenagem é resolvido pela lógica do simulador junto da física do veículo.

## Inventário local

- 140 arquivos `.mas` em `Installed\Locations`.
- 74 arquivos `.mas` em `Installed\Vehicles`.
- 18 diretórios de circuitos de corrida em `Installed\Locations`, com múltiplas variantes de layout.
- Foram confirmados índices AIW/GDB para os circuitos e variantes abaixo. As variantes podem compartilhar ou separar pacotes de layout.

| Circuito | AIW encontrados nos índices dos pacotes |
| --- | --- |
| Bahrain | BahrainWEC, Endurance, Outer, Paddock |
| Barcelona | BarcelonaELMS |
| Circuit of The Americas | COTA e National |
| Daytona | DaytonaRC |
| Fuji | FujiWEC e FujiWEC_CL |
| Imola | ImolaWEC e ImolaELMS |
| Interlagos | InterlagosWEC |
| Laguna Seca | LagunaSeca |
| Le Mans | LeMansWEC e LeMansWEC_Mulsanne |
| Long Beach | LongBeach |
| Monza | MonzaWEC e MonzaWEC_Grande |
| Paul Ricard | 1A, 1A-V2, 1A-V2-Short, 3A e ELMS |
| Portimão | PortimaoWEC e PortimaoELMS |
| Qatar | QatarWEC e QatarWEC_Short |
| Road Atlanta | RoadAtlanta |
| Sebring | SebringWEC e SebringWEC_School |
| Silverstone | ELMS, International, National e WEC |
| Spa-Francorchamps | SpaWEC, SpaELMS e SpaWEC_Endce |

Também há AIW/GDB de showroom, que não é um circuito de corrida.

## Onde ficam as informações de pista

Exemplo confirmado no disco:

```text
Installed\Locations\LeMans_2023\1.35\layoutLeMans.mas
    LeMansWEC.AIW
    LeMansWEC.gdb
    LeMansWEC.scn
    LeMansWEC.cam

Installed\Locations\LeMans_2023\1.35\layoutMulsanne.mas
    LeMansWEC_Mulsanne.AIW
    LeMansWEC_Mulsanne.gdb
```

O formato MAS é um contêiner binário. O inventário dos índices confirmou nomes e tamanhos, mas não foi possível concluir a leitura do conteúdo interno do AIW: o Controle de Aplicativos do Windows bloqueou a execução do leitor temporário ao tentar mostrar esse conteúdo. Esse bloqueio não foi contornado. Portanto, ainda não confirmei os campos e a representação binária/textual das linhas de cada AIW.

## Telemetria e controles salvos pelo jogo

`UserData\Telemetry\config.json` configura canais e frequências de gravação. A configuração local inclui, entre outros:

- `Steering Pos`, `Throttle Pos`, `Brake Pos` e versões unfiltered;
- `Lap Dist`, `Total Dist`, `Path Lateral`, `Track Edge`;
- `Ground Speed`, RPM, combustível, chuva, temperatura da pista;
- temperatura, pressão e desgaste dos pneus;
- forças e dados de roda.

As frequências configuradas para sinais de controle incluem 50 Hz para acelerador/freio e 100 Hz para direção; outros canais usam frequências menores. O diretório `UserData\Telemetry` continha somente `config.json` na inspeção: não havia uma gravação `.duckdb` dessa instalação nesse local. O LMU documenta gravação nativa em DuckDB; ela precisa estar ativa e produzir uma sessão para gerar os dados.

`UserData\player\gamepad.json` e `current controls.json` mostram um dispositivo de controle do tipo gamepad e mapeamentos de entradas do jogador. Eles documentam a configuração do controle local; não são uma API para que um processo escreva steering/throttle/brake.

## Física dos carros

Cada carro tem arquivos `car.mas` e `car-upgrade.mas`. O inventário conseguiu ler `.veh` dos pacotes de upgrade, que identificam veículos/liveries e referências/configuração de veículo. Os arquivos base `car.mas` não foram interpretados pelo leitor de MAS temporário usado nesta auditoria. Não extraí nem reproduzi arquivos proprietários de física, como parâmetros internos de pneus, suspensão ou motor.

O jogo também expõe medições da física em tempo real pelo adapter já presente no projeto, incluindo estado e forças das rodas, temperaturas, grip, velocidade e controles observados. Isso é a fonte de dados adequada para calibrar modelos externos sem assumir parâmetros que ainda não confirmamos.

## Possibilidade de integração com o piloto externo

1. **Mapa da pista:** os AIW parecem uma fonte melhor que coordenadas de mapa desenhadas para obter caminhos e linhas por layout. Se uma ferramenta de leitura permitida puder exportar os arquivos, podemos transformar os waypoints em trajetórias e compará-los com `lap_distance_m`, `path_lateral_m` e posição/orientação publicados pelo `LMUAdapter`.
2. **Freada e aceleração:** os nomes AIW, por si só, não provam que cada ponto contenha uma ação de freio/acelerador. A hipótese mais provável é linha/corredor/waypoint; pontos de frenagem devem ser aprendidos dos canais de telemetria registrados ou inferidos de uma volta humana/AI.
3. **Física por carro:** combinar dados AIW da pista com telemetria medida por carro é mais seguro que copiar parâmetros internos ainda não validados.
4. **Envio de comandos:** `SharedMemoryInterface.hpp` documenta memória compartilhada de saída do jogo para leitura de estado; não encontrei ali uma estrutura pública de escrita de controles. A API REST já implementada no projeto usa requisições GET. Uma saída de controle precisa ser avaliada separadamente; não se deve confundir AIW ou telemetria com uma API de controle.

## Recomendação para o projeto

- Preservar o `LMUAdapter` existente como única leitura de telemetria.
- Adicionar um importador opcional de AIW somente após definir uma forma permitida de extrair/listar conteúdo e verificar o formato em amostras.
- Tratar os AIW como geometria/trajetória de referência, não como política completa de condução.
- Gravar sessões LMU nativas e alinhar steering/brake/throttle ao longo da distância da volta para estimar pontos e perfis de controle.
- Continuar com o piloto em `OBSERVE` até validar separadamente uma interface de entrada.

## Fontes

- LMU, gravação de telemetria em DuckDB: https://guide.lemansultimate.com/hc/en-gb/articles/14524956311695-Telemetry-Recording
- Studio 397, tutorial AIW rFactor 2: https://www.studio-397.com/wp-content/uploads/2016/12/rF2_AIW_Creation_Tutorial.pdf
- Studio 397, tutorial de empacotamento de pistas: https://www.studio-397.com/wp-content/uploads/2016/12/rF2_Packaging_Tutorial.pdf
- O cabeçalho `Support\SharedMemoryInterface\SharedMemoryInterface.hpp` foi lido diretamente da instalação local.
