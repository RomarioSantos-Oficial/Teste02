# Fuel Time — relatório técnico

O widget prioriza os valores do LMU enriquecidos pela API REST local e usa a memória compartilhada como fallback.

- Mede o consumo pela diferença do tanque entre passagens de volta; pit, saltos e reabastecimentos são descartados.
- Corrida por voltas: usa o limite de voltas fornecido pelo jogo.
- Corrida por tempo: soma ao tempo restante a possível última volta iniciada pela classe mais rápida e converte o tempo pelo ritmo do jogador. Assim, carros mais rápidos e voltas tomadas entram na estimativa.
- Necessário = `(voltas restantes + margem) × média por volta`; “Adicionar” desconta o tanque atual.
- “Alvo/volta” informa o consumo máximo para chegar preservando a margem configurada.
- Fuel Ratio segue a definição do TinyPedal: `litros consumidos / energia virtual consumida`.

Antes de completar uma volta válida, valores calculados ficam `--`. Safety car, chuva, tráfego e lift-and-coast alteram a projeção; a margem padrão é uma volta.
