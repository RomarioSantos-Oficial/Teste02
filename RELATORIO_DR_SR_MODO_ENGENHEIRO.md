# Relatório de diagnóstico — ST, DR/SR e modo Engenheiro

Data da análise: 27/08/2026

## Resumo atualizado após reprodução por imagem

Foram investigados dois sintomas:

1. DR e SR no Standings (ST) aparecem arredondados.
2. No perfil/modo Engenheiro os overlays aparentam aparecer duas vezes.

O arredondamento visual foi confirmado. A nova evidência também permitiu localizar a causa da duplicação no modo Engenheiro: o publicador URL cria cópias locais de widgets que já existem em processos isolados. Quando o modo de edição é ativado, essas cópias ocultas também são mostradas. Há ainda dois caminhos confirmados pelos quais uma configuração antiga de tamanho/posição pode sobrescrever a geometria escolhida pelo usuário.

## 1. DR e SR arredondados no ST

### Causas confirmadas

Em `src/widget/standings/standings_widget.py`, no método `_draw_rank`, o progresso é formatado com zero casas decimais:

```python
progress_text = f"{max(0.0, min(100.0, value)):.0f}%"
```

O ganho estimado de DR também é formatado com zero casas:

```python
gain_text = f"{float(estimated_gain):+.0f}%"
```

O especificador `.0f` manda o Python arredondar o valor para o inteiro mais próximo. Exemplos:

- `43.4` → `43%`
- `43.6` → `44%`
- `+2.7` → `+3%`

Isso explica a perda de casas decimais, mas não explica sozinho os valores da imagem sempre em dezenas (`40%`, `70%`, `80%`, `90%`, `100%`). Essa segunda característica indica que o dado recebido/cacheado já chega quantizado em passos de 0,1 (ou em dezenas percentuais). O código aceita diretamente tanto fração quanto porcentagem, sem registrar a unidade ou a precisão da fonte. Assim, o ST apenas reproduz a granularidade fornecida pela API/cache e depois aplica `.0f`.

Conclusão: existem duas camadas diferentes no problema de DR/SR:

1. a interface remove decimais por causa de `.0f`;
2. a fonte usada na captura mostrada parece fornecer somente passos de 10%, portanto trocar apenas para `.1f` pode produzir `70,0%`, mas não recuperar uma precisão que não veio da fonte.

### Correção recomendada

Exibir ao menos uma casa decimal (`.1f`) no progresso de DR/SR e, se desejado, também no ganho estimado. Deve-se validar a largura mínima das colunas, pois o texto ficará um pouco maior.

## 2. Overlays duplicados no modo Engenheiro

### Causa confirmada

Na configuração real, o perfil Engenheiro tem `delta`, `driver_panel` e `url` habilitados. O publicador URL possui onze widgets em `published_widgets`, inclusive `delta` e `driver_panel`.

O método `_configure_url_sources()` de `src/ui/overlay_manager.py` percorre essa lista e executa:

```python
source = self.widgets.get(widget_id) or self.create_widget(widget_id)
```

Esse caminho não respeita `external_widget_ids`. Portanto ele cria, dentro do processo principal, uma segunda instância de `delta` e `driver_panel`, embora esses dois widgets já estejam rodando nos processos isolados. Em operação normal as cópias podem ficar ocultas. Ao ativar o modo de edição, `OverlayManager.set_edit_mode()` mostra todo widget habilitado existente em `self.widgets`; as fontes do URL passam a aparecer junto com os widgets isolados.

Isso corresponde exatamente à imagem: dois Deltas e dois painéis de Telemetry, com dados/estados diferentes.

### Verificações complementares

- Existe somente um perfil interno `engineer` na configuração atual.
- O gerenciador principal guarda cada widget em um dicionário por identificador e os métodos de criação reutilizam a instância existente.
- Ao trocar de perfil, `switch_profile()` chama `close_all()` antes de criar os widgets do novo perfil.
- Os widgets isolados (`driver_panel`, `delta`, `map`, `lap_timer`, `tires`, `radar` e `flags`) vivem, por projeto, em processos separados. Na inspeção havia exatamente os sete processos-filho previstos, e não duas famílias completas de processos.
- O bloqueio de instância única por mutex também está ativo.
- No arquivo real do usuário, o perfil Engenheiro possui apenas `delta`, `url` e `driver_panel` habilitados. O perfil Padrão possui nove widgets habilitados.

### Correção recomendada

Fontes destinadas ao servidor URL não devem ser janelas nativas visíveis. Para widgets isolados, o publicador precisa usar uma fonte de renderização sem janela ou impedir explicitamente que a instância de publicação seja mostrada pelo modo de edição. `_configure_url_sources()` também deve tratar `external_widget_ids`.

## 3. Tamanho e posição voltam ao padrão

### Causas confirmadas no fluxo

1. Os editores recebem uma cópia completa da configuração no momento em que são abertos. Quando emitem `config_changed`, enviam novamente essa cópia, incluindo `position`, `size`, `scale` e `monitor`. Se o usuário moveu/redimensionou o overlay depois que o editor abriu, a cópia antiga substitui a geometria nova. A proteção `_preserve_editor_geometry()` existe somente para `standings`; Delta, Telemetry e os demais continuam vulneráveis.

2. Os processos isolados enviam alterações de geometria por uma fila contendo apenas `(widget_id, x, y, width, height)`. A mensagem não carrega o identificador do perfil. Se o usuário troca de perfil antes de a fila ser processada, uma geometria atrasada do perfil anterior pode ser salva no perfil que acabou de ser selecionado.

3. Sempre que os processos isolados detectam qualquer mudança no arquivo de configuração, chamam `_apply_config(force_geometry=True)`. Isso reaplica posição e tamanho mesmo quando a alteração feita não era geométrica.

### Correção recomendada

- Preservar geometria para todos os widgets quando a alteração vem de um editor de aparência/conteúdo.
- Incluir `profile_id` e uma geração da configuração nas mensagens de geometria dos processos isolados.
- Reaplicar geometria somente quando `position`, `size`, `scale` ou `monitor` realmente mudarem.

## 4. Avisos do Qt no encerramento

### `QFont::setPointSize: Point size <= 0 (-1)`

Não existe chamada direta a `setPointSize()` no código funcional pesquisado. Os widgets usam predominantemente `setPixelSize()`. O `-1` é o valor que o Qt usa quando uma fonte não possui tamanho em pontos definido; algum caminho interno/editor está copiando esse valor para `setPointSize`. O aviso é real, mas sua origem exata exige rastreamento Qt/fatal warnings para obter a pilha da chamada.

### `Timers cannot be stopped from another thread`

O aviso significa que um `QObject` com timer está sendo destruído ou parado fora da thread Qt que o criou. O projeto mistura `QTimer`, threads Python de telemetria/enriquecimento e processos isolados. O encerramento chama `stop()`/`close()` em vários objetos, e pelo menos um deles chega à destruição pela thread errada. Isso pode contribuir para processos/janelas remanescentes após encerramento anormal, embora não seja a causa principal da duplicação mostrada.

A correção deve garantir que cada `QTimer` seja parado via sinal/slot ou `invokeMethod` na thread proprietária, antes de encerrar workers e destruir os objetos.

## Prioridade sugerida

1. Impedir que fontes URL de `delta` e `driver_panel` se tornem janelas visíveis no modo de edição.
2. Proteger a geometria de todos os widgets contra configurações antigas enviadas pelos editores e pelas filas entre processos.
3. Registrar o valor bruto e a origem de DR/SR para confirmar por que a fonte está quantizada em passos de 10%.
4. Depois de confirmar a precisão disponível, alterar a apresentação `.0f` conforme necessário.
5. Corrigir a ordem de encerramento dos timers Qt.

## Correções implementadas

- Fontes URL de widgets isolados são marcadas como fontes internas e permanecem ocultas durante edição e sessão.
- A ativação do modo de edição deixou de ser enviada duas vezes ao `OverlayManager`.
- Atualizações dos editores preservam posição, tamanho, escala e monitor de todos os overlays.
- Mensagens de geometria dos processos isolados agora carregam o perfil de origem.
- Mudanças não geométricas deixam de reaplicar forçadamente tamanho e posição.
- DR/SR preservam uma casa decimal quando ela existe, removendo apenas zero decimal desnecessário.
- O seletor de fonte do Lap Timer passa uma fonte com tamanho válido ao Qt.
- Timers do Delta, Flags e Lap Timer são parados explicitamente no fechamento.

## Validação executada

- Compilação de todo o diretório `src`: aprovada.
- 105 testes unitários: aprovados.
- Smoke test individual de criação, modo de edição e fechamento de 14 overlays: aprovado para Telemetry, Delta, Flags, Weather, Tires, Battery, Damage, Fuel Time, Lap Timer, Relative, Radar, Map, Standings e URL.
- Regressão de fonte URL duplicada para Delta e Telemetry: aprovada.
- Persistência de geometria no perfil de origem: aprovada.
- Formatação DR/SR com decimal disponível: aprovada.
- Nenhum aviso `QFont::setPointSize` ou `Timers cannot be stopped from another thread` apareceu nos smoke tests.

A leitura ao vivo de DR/SR ainda depende da precisão entregue pelo serviço do LMU. O código agora deixa de arredondar decimais recebidos, mas não inventa precisão quando a origem entrega apenas dezenas inteiras.
