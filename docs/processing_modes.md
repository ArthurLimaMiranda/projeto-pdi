# Console PDI: realce da cena e remoção de ruído

O console mostra a imagem recebida e o resultado lado a lado. O operador
escolhe **um modo de cena (realce ou análise)** e **um modo de ruído** em linhas separadas. As
duas escolhas são independentes: por exemplo, `Baixa luz + Sal e pimenta` ou
`Contraste local + Listras`. A ordem do processamento é:

```text
frame recebido → filtro de ruído opcional → realce ou análise → espelhamento opcional
```

Filtrar antes de realçar evita que gama e CLAHE ampliem o ruído. Os controles
deslizantes ajustam a linha selecionada por último, indicada por `AJUSTANDO`.
Cada opção conserva os seus parâmetros quando se troca de opção. **Restaurar
padrão** redefine somente a opção em ajuste; **Espelhar** é global.

## Realce da cena

| Opção | Técnica | Parâmetros |
|---|---|---|
| Sem realce | Nenhum realce; útil para medir o efeito isolado do filtro de ruído. | Nenhum. |
| Baixa luz | Bilateral leve na luminância, transformação gama e CLAHE. | Gama 0,25–1,50: valores menores clareiam mais. `CLAHE clip` 1–6 limita a amplificação do contraste local. |
| Contraste local | CLAHE no canal L de Lab; os canais de cor são preservados. | `CLAHE clip` 1–6 e grade de 2×2 a 12×12 regiões. |
| Marcadores | CLAHE na luminância, filtro bilateral, Canny e componentes conexos produzem uma máscara de bordas brancas sobre fundo preto. | Sensibilidade do Canny 10–70 e tamanho mínimo do fragmento de borda 6–80 pixels. Arraste na imagem original para definir a região de interesse. |

Na estação dos marcadores, a ROI inicial é apenas um ponto de partida. A
posição da parede muda com a posição do robô. O operador pode pausar o vídeo,
arrastar uma ROI menor e ajustar os dois controles. Componentes de borda com
menos pixels que o mínimo são removidos. A imagem processada mostra somente a
máscara binária; não há caixas, rótulos ou contagem de extremidades.
O operador clica uma vez em cada marcador sobre a máscara; **Quantidade
marcada** registra essa seleção. Um segundo clique no mesmo ponto a desfaz.
Mudar a ROI ou restaurar o modo limpa a contagem. Em
vídeo ao vivo, convém parar o robô durante a conferência.

A imagem de exemplo do enunciado mostra objetos amarelos sobre um fundo escuro:
uma máscara por cor/luminância separa os corpos e componentes conexos pode
contá-los diretamente. Nos quadros da câmara real, os corpos brancos têm
intensidade muito próxima à parede branca, dois se sobrepõem e algumas bordas
tocam as dobras do cenário. O Canny revela os contornos, mas não fecha seis
regiões confiáveis para uma contagem automática. **Quantidade marcada** registra
a contagem feita pelo operador, sem apresentar um número automático enganoso.

## Ruídos

| Opção | O que representa | Tratamento | Parâmetros |
|---|---|---|---|
| Sem filtro | Não aplica um filtro de ruído; útil para comparação. | Nenhum. | Nenhum. |
| Sal e pimenta | **Ruído impulsivo:** pixels isolados saltam muito em relação aos vizinhos, frequentemente para preto ou branco. A compressão pode suavizar os extremos. | Mediana integral quando mais de 3% dos pixels diferem da mediana local além do limiar; substituição seletiva quando os pontos são raros. | Janela 3×3 a 7×7, padrão 5×5, e limiar 20–100. Janela maior remove mais pontos, mas pode apagar letras finas. |
| Listras (FFT) | **Interferência periódica:** faixas regulares criam pares de picos no espectro de Fourier. | Detecta picos isolados e aplica filtros *notch* gaussianos em pares simétricos. | Raio 2–10 e até 1–4 pares de picos. Raio e quantidade altos podem remover detalhes reais que tenham a mesma frequência. |
| Estático | **Granulação contínua:** pequenas variações de intensidade e cor em muitos pixels, semelhante a ruído de sensor em baixa luz. | *Non-Local Means* colorido compara regiões parecidas. Um diagnóstico pelo resíduo de mediana só aciona o filtro em quadros com granulação difusa e o desliga em cenas limpas ou dominadas por impulsos. | Força 4–25 e janela de busca 7×7 a 15×15. Valores altos suavizam detalhes e aumentam o tempo por frame. |

Os botões antigos **Ruído impulsivo** e **Ruído suave** tinham nomes pouco
claros. O primeiro já usava mediana para o problema de sal e pimenta, mas
filtrava a imagem inteira. Agora ele aparece explicitamente como **Sal e
pimenta** e adapta a mediana à densidade dos impulsos. **Ruído suave** era o nome dado ao filtro
bilateral para perturbações pequenas; não é uma classe específica de ruído.
Para a granulação estática do vídeo, o modo **Estático** usa Non-Local Means
com intensidade gradual por quadro. O percentil 75 do resíduo da mediana
define a mistura: até 2, mantém o quadro de entrada; de 2 a 8, aumenta
linearmente o peso da imagem filtrada; a partir de 8, usa todo o resultado
do NLM. O filtro é ignorado se mais de 2,5% dos resíduos ultrapassarem 60,
como pode ocorrer em quadros dominados por sal e pimenta.

O controle **Quadros** vai de 1 a 15. Em 1 (padrão), vale a detecção
automática acima. Ao escolher 2 ou mais, o operador solicita a média dos
quadros mais recentes seguida de NLM, inclusive quando o ruído forte
acionaria o bloqueio automático. Use esse ajuste com a câmera parada.
A média pode borrar contornos se houver movimento. Com o robô, segure
**Espaço** para enviar o comando de parada e acumular novos quadros.
Ao soltar a tecla, o console descarta o histórico e volta a processar
o quadro atual. Após um salto no vídeo local,
deixe a reprodução avançar até o contador de quadros atingir o valor
selecionado antes de pausar.

## Vídeo de demonstração

O arquivo `../video_com_ruidos_recortado_320x240.mp4` foi preparado a partir
de `../video_com_ruidos.mp4`. A gravação original é da tela inteira; a área
da câmera foi recortada e reduzida para 320×240, a resolução usada pela
ESP32-CAM. O recorte é reproduzível com:

```bash
ffmpeg -i ../video_com_ruidos.mp4 \
  -vf 'crop=960:720:300:40,scale=320:240:flags=area,fps=15' \
  -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -an \
  ../video_com_ruidos_recortado_320x240.mp4
```

Use a barra de tempo para visitar aproximadamente **60 s** (listras),
**44 ou 80 s** (sal e pimenta) e **190 ou 220 s** (estático). A estação dos
marcadores aparece por volta de **190–230 s** no vídeo recortado. Pause a imagem, selecione
`Sem realce` no realce e teste primeiro o filtro de ruído isolado. Depois
acione `Baixa luz` ou `Contraste local` para observar a combinação.

O vídeo gravado tem compressão e não é uma referência limpa alinhada frame a
frame; por isso, a avaliação visual deve verificar tanto o ruído removido
quanto os detalhes preservados. Nenhum filtro recupera informações que não
foram captadas pela câmera.
