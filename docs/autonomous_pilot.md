# Piloto experimental para LMU

## Estado implementado

A primeira etapa usa o `LMUAdapter` já existente em `src/telemetry/lmu_adapter.py`. O adapter continua sendo o único leitor da Shared Memory; o novo código transforma `SessionData` em `UnifiedState`, produz uma decisão em modo `OBSERVE` e pode gravar amostras JSON Lines versionadas.

```text
LMU Shared Memory + enriquecimento REST local
                     ↓
                 LMUAdapter
                     ↓
                 SessionData
                     ↓
              UnifiedState v1
                     ↓
              ObserveDriver + RecordedRouteRepository
                     ↓
          data/autonomous/observe.jsonl
```

Executar a partir da pasta do projeto:

```powershell
.\.venv\Scripts\python.exe src\tools\run_pilot_observe.py
```

Opções: `--output <arquivo>`, `--hz 1..60` e `--no-record`. O programa não envia comandos ao jogo.

Se houver um mapa gravado compatível em `data/track_maps`, cada decisão OBSERVE inclui `route_preview` (ponto amostrado cerca de 30 m adiante) e `route_assessment`. O monitor calcula a distância da posição do veículo ao segmento mais próximo e o alinhamento da direção com esse segmento. Ele classifica `ON_ROUTE`, `OFF_ROUTE`, `WRONG_DIRECTION`, `HEADING_MISMATCH`, `NO_MATCHING_ROUTE` ou `INSUFFICIENT_TELEMETRY`. O limite inicial de desvio é 5 m. O nome da pista precisa coincidir e o comprimento deve ficar dentro de 2%. Há mapas para Fuji Speedway e Michelin Raceway Road Atlanta.

Esses mapas vêm de telemetria observada, não das linhas AIW do jogo. Alertas são apenas diagnósticos: não desviam de carros/obstáculos, não calculam um caminho de recuperação e não geram freio, acelerador ou direção. Não detectam necessariamente uma colisão; indicam apenas desvio geométrico ou orientação incompatível com a rota salva.

## Campos mapeados

- Veículo: modelo/classe, velocidade convertida para m/s e km/h, RPM, marcha, comandos medidos do jogador, combustível, energia, volta/setor e rodas.
- Pneus/rodas: pressão, desgaste, temperaturas publicadas, grip publicado, cargas, forças, velocidades de patch, camber/toe, composto, pneu furado e roda destacada.
- Pista: nome, comprimento e distância/posição lateral/limite publicados pelo scoring.
- Clima: chuva, molhamento mínimo/médio/máximo, temperaturas, vento e hora do dia.
- Tráfego: classe/modelo, velocidade, posição lateral, boxes e distância relativa calculada a partir das distâncias do scoring na volta.

Curvatura, linha central precisa, massa e potência não são fabricadas. A curvatura ainda não está disponível em `SessionData`; distância lateral e `mPathLateral` usam a linha central aproximada do scoring do jogo. Valores zero que os modelos legados do adapter usam como fallback podem significar “não fornecido”; o consumidor deve consultar `provenance` e `unavailable` antes de treinar.

## Fontes de captura reutilizadas

O piloto não tem uma segunda implementação de captura: `src/tools/run_pilot_observe.py` chama o mesmo `LMUAdapter` de `src/telemetry/lmu_adapter.py` usado pelos diagnósticos do projeto. O adaptador lê a Shared Memory pelo SDK em `vendor/pyLMUSharedMemory`, enriquece a sessão com a API REST local GET em `lmu_rest_client.py`/`lmu_rest_enrichment.py`, e já aplica os gates de segurança existentes. O estado unificado agora preserva também dados que antes eram descartados pelo piloto:

| Dados no registro do piloto | Captura existente | Observação |
| --- | --- | --- |
| Velocidade, RPM, marcha, comandos medidos, combustível e híbrido | Shared Memory; REST pode completar combustível/condição | Comandos são observações, não saída de controle. |
| Posição, orientação, distância na volta, posição lateral e limite da pista | Scoring/telemetria Shared Memory | `mPathLateral` é referência aproximada. |
| Impacto, dano, volta invalidada, rodas e pneus | Shared Memory; condição REST pode complementar dano/consumo | O valor de impacto é o que o jogo publica. |
| Chuva, pista molhada, temperaturas, vento e hora | Shared Memory com enriquecimento REST disponível | Unidades permanecem nomeadas no schema. |
| Tráfego e distâncias relativas | Scoring Shared Memory, com enriquecimento REST para alguns campos | Distância relativa é derivada das distâncias de volta. |
| Estado de controle, monitor/replay, fase e disponibilidade REST | Snapshot da API REST local e estado da Shared Memory | Serve para contexto e gates, não para controlar o carro. |

Os valores são preservados no JSONL por `UnifiedState.to_dict()`. “Validado” aqui significa que o projeto já possui adaptador e testes unitários/diagnósticos para esses caminhos; a leitura durante uma sessão real ainda depende de executar o LMU e observar os valores ao vivo.

## Controle do veículo

O código deste projeto confirma interfaces de leitura: Shared Memory via SDK incluído em `vendor/pyLMUSharedMemory` e chamadas GET à API REST local para estado/enriquecimento. O SDK lido mapeia telemetria e scoring; não contém mecanismo de escrita dos controles de direção. A REST client deste projeto também só faz GET. `LMUControl` descreve quem está no controle no dado de scoring, não uma API de envio de comandos.

Assim, `OBSERVE` é o único modo executável por enquanto. `ASSIST` e `AUTONOMOUS` são modos planejados, mas não podem ser ativados até existir uma interface de saída compatível e validada. Não se deve chamar uma gravação de telemetria ou endpoint REST de controle do carro. Este protótipo não usa injeção de memória nem contorna proteções do simulador.

## Próximas fases

1. Coletar sessões reais usando `run_pilot_observe.py` e validar campos/unidades contra a gravação nativa do LMU.
2. Criar dataset e filtros usando o schema versionado.
3. Validar os mapas gravados com voltas completas e, se houver exportação legítima e legível dos AIW, criar um importador com formato confirmado. O conteúdo AIW do LMU não foi lido neste ambiente; não há integração AIW implementada.
4. Construir mapa/curvatura da pista e estimar erro de posição/orientação.
5. Implementar e validar controlador clássico em simulação/replay antes de emitir entradas.
6. Pesquisar uma interface de controle documentada e permitida para o ambiente alvo; integrar atrás de uma configuração desligada por padrão, com intertravamentos e parada manual.
7. Só então experimentar `ASSIST` e, após validação offline e pista controlada, `AUTONOMOUS`.

## Testes

```powershell
.\.venv\Scripts\python.exe -m unittest src.tools.test_autonomous_state -v
```
