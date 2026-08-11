# design/

Protótipo visual da página publicada. **A v3 já foi implementada** em `app/streamlit_app.py` e
`app/charts.py` (10/08/2026); esta pasta continua sendo onde o layout se decide antes de tocar no
app, e o SVG é a referência de como a página deve parecer.

| Arquivo | O que é |
|---|---|
| `app-redesign-v3.svg` | **versão corrente**, 1440 × 2022 |
| `make_mockup_v3.py` | gera a v3 — `python design/make_mockup_v3.py` |
| `app-redesign-v2.svg` | versão anterior, 1440 × 2150 — mantida para comparação |
| `make_mockup.py` | gera a v2 — `python design/make_mockup.py` |

### O que a v3 mudou

- **Manchete em uma linha só** (38px, mede 1258 dos 1312 disponíveis), com a descrição logo
  abaixo em vez de ao lado.
- **A safra 2025/26 virou um card estreito com scroll**, na mesma linha do gráfico de
  severidade. Mostra 8 das 11 previsões; o resto rola. O fade no corte e a trilha à direita são
  o que comunica que a lista continua — em Streamlit isso é um `st.container(height=...)`, que
  rola sozinho.
- **Exposição por estado em barras em pé**, em faixa de largura inteira, com o texto explicativo
  à esquerda do gráfico em vez de acima.
- **"Season by season" sem texto dentro do plot**: as duas anotações saíram e a legenda subiu
  para antes do gráfico, logo abaixo do subtítulo.
- **Saiu o aviso longo de PR e MS.** O que a página ainda diz é "11 of 13 states scored", no
  subtítulo do card.
- Largura de texto agora é **medida na fonte real** (Pillow lê a Segoe UI) em vez de estimada por
  contagem de caracteres — é o que garante que legenda, chip e rótulo não se sobreponham.
- **Folga de 12% sobre toda largura medida** (`SAFETY`), porque a página pode ser aberta onde não
  há Segoe UI e a fonte substituta é mais larga: o subtítulo da exposição cabia na medição e
  vazava do card no navegador. Por isso a manchete é 34px e não 38px — a 38 sobravam só 4%.
  Um guard no fim do script recalcula cada texto com a folga e **aborta a geração** se algum
  passar da borda útil, em vez de gravar um SVG com texto vazando.

O mockup **não tem número digitado à mão**: gain por severidade, correlação por estado,
previsão 2025/26 e a série do RS saem dos mesmos CSVs que o app lê. Se o pipeline rodar e os
dados mudarem, é só rodar o script de novo e o mockup acompanha.

O SVG sai com hex inline em cada elemento, sem `var()` e sem bloco `<style>` — o Figma não
resolve nenhum dos dois e importaria o arquivo invisível.

## O que muda em relação ao app atual

O conteúdo e a ordem da narrativa são os mesmos; o que muda é hierarquia e enquadramento.
A lista abaixo descreve a v2; a v3 mexe no arranjo, não nos princípios.

1. **Barra superior escura** com marca, cobertura do dado (`Weather through 3 Aug 2026`) e o
   stack visível (`dbt · BigQuery`). Hoje a página abre direto no `st.title`, sem moldura.
2. **Hero em duas colunas de texto**: a tese honesta em 42px à esquerda, o parágrafo de apoio
   à direita. Sem gráfico aqui — a página abre em texto e só depois mostra número.
3. **Quatro KPIs de peso igual**, logo abaixo do hero — cartão claro, rótulo em caps miúdo,
   número em 44px, uma linha de contexto. O que muda em relação ao `st.metric` de hoje é o
   enquadramento (moldura, respiro, o "por quê" embaixo do número), não a hierarquia.
4. **A safra aberta 2025/26 sobe para logo abaixo dos KPIs**, em card de largura inteira. Hoje
   ela está no rodapé da página, onde recrutador nenhum chega. Em largura inteira cabem as 11
   previsões em duas colunas, então some o "+5 more states" que um card estreito precisaria
   esconder. O aviso de janela truncada (PR e MS) vira nota do card, não um `st.info` solto.
5. **Zona sombreada no gráfico de severidade**, separando "pior que a baseline" de "melhor", e
   o `n` de cada faixa ao lado do rótulo — o argumento "só ganha na cauda" fica visível sem ler
   a legenda. Valores que não cabem fora da barra entram nela, em branco.
6. **Faixa climática sob a série anual.** O terço inferior do gráfico de linha era espaço morto;
   agora carrega a anomalia de dias secos no mesmo eixo de tempo, então a variável de entrada e
   o resultado ficam na mesma leitura. **Não é eixo duplo** — são dois painéis, cada um com sua
   escala.
7. **Duas anotações no gráfico anual**: um acerto grande (2020) e um falso alarme (2007). O
   falso alarme é deliberado — a página inteira depende de admitir que metade das chamadas erra.
8. **Rodapé com o pipeline** (CONAB/IBGE/NASA POWER → Python → DuckDB/BigQuery → dbt → sklearn
   → Streamlit). É a parte que interessa a quem contrata e que hoje só aparece escondida dentro
   do expander "Method".

## Dados: o que é derivado e o que é fixo

A v3 aplica ao mockup a regra que o projeto já tem para o app — **nada que a página afirma
sobre o dado pode ser digitado à mão**. Passou a ser derivado dos CSVs:

| Antes escrito à mão | Agora vem de |
|---|---|
| "Weather through 3 Aug 2026" | `meta.json` → `weather_through` |
| "7 STATES · 1992–2026" | `season_risk` → nº de UFs, min/max de `harvest_year` |
| "48%" (quebras sinalizadas), aqui e no parágrafo | recall calculado do `backtest` |
| "40%" (erro removido), aqui e no parágrafo | RMSE modelo ÷ baseline na faixa de quebra |
| "23" e "2003–2025" | `backtest` → nº e intervalo de safras |
| "3.3M" | `meta.json` → `weather_rows` |
| "2025/26" | safra aberta do `season_risk` |
| "11 of 13 states scored" | linhas com e sem previsão no `forecast` |
| **"55% of the sample"** | fração da faixa Normal — **o valor real é 48%** |
| "four times as sensitive", "Rio Grande do Sul", "Mato Grosso" | razão entre o maior e o menor r, e os próprios estados |
| "Pearson r, 1992–2025" | intervalo da janela usada na correlação |
| "Roughly half the calls are false alarms" | 1 − precisão, calculada → 48% |
| "10% or more below trend" | `FLAG_PCT`, a mesma constante que filtra os anéis |
| Rótulos das faixas ("Failure < -20%" …) | gerados dos limites do `pd.cut` |
| Topo do eixo de exposição (0,6), de produtividade (3.600) e da faixa climática (2,3 z) | do próprio dado, com folga |

✅ **O "55%" já foi corrigido no app**: os dois lados calculam a fração da faixa Normal, e o
dado atual dá **48%**.

Os eixos merecem nota à parte: um teto digitado **corta a barra maior e renderiza assim
mesmo**, subestimando em silêncio justo o caso que o gráfico existe para mostrar. É a mesma
armadilha do eixo `[0, 0.6]` já corrigida no app.

### O que continua fixo (e por quê)

| Fixo | Onde | Por que |
|---|---|---|
| `GRID_CELLS = 255` | KPI de clima | não está em nenhum CSV publicado. `season_risk.grid_cells` é por UF, e somar dá dobro (as células se repetem entre UFs). Para sair daqui, teria de entrar no `meta.json` |
| `DBT_TESTS = 78` | rodapé do pipeline | vive no projeto dbt, não nos dados. Ou entra no `meta.json`, ou sai da página |
| `FLAG_PCT` / `FAIL_PCT` (−10 / −20) | limiares | são parâmetros do modelo, não observações. Ficam numa constante só, que alimenta texto, rótulo e filtro |
| "baseline flags 0%" | KPI 1 | verdade por construção: a baseline prevê "safra = tendência" e nunca sinaliza |
| `FOCUS_STATE = "RS"` | explorador | é a seleção que a página abre, estado de UI |

## Cores

**Identidade: violeta `#4a3aa7` + laranja `#eb6834`** — o azul `#2a78d6` que o app usa hoje saiu.
Os dois hexes continuam sendo slots da paleta de referência (7 e 2), sem re-stepping.

A troca não foi por gosto. Medido com o validador da paleta (distância OKLab ×100, simulação
Machado-Oliveira-Fernandes severidade 1.0), pareado com o laranja:

| Candidato | ΔE sob CVD | ΔE visão normal | Contraste | Veredito |
|---|---|---|---|---|
| **violeta `#4a3aa7`** | **29,5** | 37,6 | passa | **escolhido** |
| aqua `#1baf7a` | 9,2 | 27,6 | 2,74:1 (relief) | passa raspando |
| azul `#2a78d6` (atual) | 9,1 | 19,6 | passa | passa raspando |
| verde `#008300` | 3,2 | 31,0 | passa | reprovado |
| magenta `#e87ba4` | 12,5 | 12,9 | 2,62:1 | reprovado |
| amarelo `#eda100` | 9,7 | 13,7 | 2,11:1 | reprovado |

Pisos: CVD ≥ 8, visão normal ≥ 15, contraste ≥ 3:1. Violeta+laranja não só passa — sobra mais de
três vezes o piso de CVD, e é o único candidato que também limpa o contraste sem ressalva.

**Azul e vermelho continuam na página, mas só como par divergente** — seco/úmido na faixa
climática. Ali a cor marca polaridade, não identidade de série, e o par azul↔vermelho é o único
divergente documentado (dois polos que leem como opostos, com cinza no meio). Violeta não serve
de polo: já significa "soja" três centímetros acima. Se você quiser zero azul na página, a troca
possível é a faixa climática virar laranja↔violeta — mas aí a mesma cor faz dois trabalhos.

Na exposição por estado é **uma série só**, então é uma cor só: violeta em todas as barras, com
as não destacadas em opacidade 0,42. O comprimento já carrega a magnitude; o RS ganha ênfase
sem precisar de um segundo hex.

O validador não roda nesta máquina (precisa de Node), então foi portado para Python e conferido
contra os números que a paleta documenta — reproduziu 9,1/19,6 em light e 8,4/19,3 em dark antes
de ser usado para decidir.

## Como foi implementado

Tudo em Streamlit + Plotly, sem dependência nova:

- barra superior, hero e rodapé de pipeline: `st.markdown` com HTML, um bloco de CSS injetado;
- stat tiles: um `st.markdown` por tile em vez de `st.metric`, para controlar moldura e a
  linha de contexto;
- zona sombreada e faixa climática: `add_vrect` e um segundo eixo em `make_subplots`
  (`shared_xaxes=True`, `row_heights=[0.75, 0.25]`);
- lista da safra aberta (v3): `st.container(height=300)` — rolava nativamente, sem CSS, e a
  altura da figura cresce com o nº de linhas em vez de espremê-las;
- legenda antes do gráfico (v3): `legend=dict(orientation="h", yanchor="bottom", y=1.02)`.

⚠️ **O CSS do Streamlit vence classe solta.** Ele estiliza `.stMarkdown p` (especificidade 0,1,1),
que ganha de `.srr-head` (0,1,0) — a manchete saiu com corpo de texto comum até os seletores
virarem `p.srr-head`. Vale para todo texto injetado por `st.markdown`.

### O passe de acabamento (10/08, depois da v3)

O app implementava a v3 no arranjo, mas ainda destoava do SVG no acabamento. O que foi
igualado — e o motivo, quando não é só gosto:

- **Barra escura e rodapé sangram até a borda.** Eram cartões arredondados com margem; no SVG
  são faixas de ponta a ponta. Feito com margem negativa do tamanho exato do padding da página
  (`--srr-pad`), não com `100vw` — `vw` conta a barra de rolagem e sobra scroll horizontal.
  ⚠️ Quem escrever `padding:` de atalho na `.srr-top`/`.srr-pipe` zera o horizontal que a
  `.srr-bleed` usa para realinhar, e o texto cola na borda da tela.
- **Toolbar do Streamlit escondido** (Deploy + menu): flutuava por cima da barra escura.
- **Fundo da página meio tom mais escuro que os cartões** (`#f9f9f7` contra `#fcfcfb`). Com os
  dois iguais, sobrava a borda de 1px fazendo todo o trabalho de separar.
- **`primaryColor` virou o violeta da paleta** — o azul tinha saído dos gráficos e continuava
  nos widgets.
- **Previsão 2025/26: os valores viraram coluna à direita**, como no SVG. Escritos fora da
  ponta da barra, os onze caíam onde cada barra terminasse; em coluna, viram lista. Só a régua
  do zero fica (com o rótulo "trend"), sem grade e sem eixo de %.
- **A lista não rola mais** (aqui o app se afasta do SVG de propósito): a altura fixa de 380px
  rolava por menos de uma linha e ainda sobrava faixa branca embaixo, porque o cartão é
  esticado pelo vizinho mais alto. Agora `st.container(height="stretch")` +
  `st.plotly_chart(height="stretch")` — o gráfico cresce até o pé do cartão e as 11 linhas
  aparecem inteiras. Some junto o "scroll for N more". Esticar só é seguro porque o número de
  linhas é limitado às 13 combinações cultura × estado que o pipeline pontua; numa lista aberta,
  esticar espreme as linhas até virarem lascas e a altura fixa com rolagem volta a ser o certo.
- **Severidade: o `n` de cada faixa entrou no rótulo**, com as legendas "worse/better than
  baseline" sob o eixo e o valor em branco dentro da barra quando ela é longa demais para
  caber fora. ⚠️ O `_value_axis` tinha de ser chamado **depois** do `_style`, que reseta os
  eixos — chamado antes, a grade e a régua do zero voltavam a sumir.
- **Exposição mais baixa (250px) e sem o tick do teto**, que era uma linha que barra nenhuma
  alcança. RS ganhou rótulo e valor em negrito.
- **Faixa climática legendada dentro do gráfico** (o que era nota embaixo) e as cores
  seco/úmido entraram na legenda por dois traces vazios — cor por ponto não vira legenda.
- **Os quatro KPIs saíram de `st.columns` para um `display:grid`.** Em janela estreita o rótulo
  de um deles quebrava em duas linhas e aquele cartão ficava mais alto que os outros três.
  ⚠️ A tentativa óbvia — esticar a corrente coluna → stElementContainer → stMarkdown com
  `height:100%` — **piora**: em altura percentual o cartão mais alto deixa de contar para a
  altura da linha, a linha encolhe até a do mais baixo e o mais alto vaza para fora da própria
  coluna. Item de grid estica de graça, e como não há widget nenhum dentro dos cartões, não se
  perde nada indo para HTML puro. O número ganhou `white-space:nowrap` + `clamp()` (em 780px
  "3.3M" virava "3.3" com o "M" embaixo) e a nota desceu para o pé do cartão.
- **"Table view" virou link discreto** dentro dos cartões, em vez de caixa da largura da página.
- **O aviso de PR e MS saiu para dentro do "Method"**, como a v3 decidiu. O texto continua
  inteiro; o que muda é que não é mais a caixa mais chamativa da página.

Ainda **não feito** no app: versão dark e ajuste fino para telas estreitas (conferido só até
1280px, onde ainda fecha).

Ainda **não feito** aqui: versão dark, versão mobile (1440 é desktop), e os estados de hover —
o mockup é estático, e o app já tem tooltip em todo gráfico.
