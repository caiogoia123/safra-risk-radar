# Safra Risk Radar — plano de trabalho

> Documento interno (português). O `README.md` é a peça de portfólio, em inglês.
> **Retomando o projeto depois de uns dias? Leia o "Estado atual" e o "Log de sessões" no fim.**

---

## 1. Pergunta de negócio

**Quanto do desvio de produtividade de soja e milho 2ª safra, por estado, é explicado por
anomalia climática na janela crítica da cultura — e dá pra antecipar uma quebra de safra
antes do fechamento do levantamento oficial?**

Quem se importa: trading de grãos, cooperativas, seguradora agrícola, crédito rural.
A decisão que a resposta destrava: antecipar posição de compra/venda e exposição a risco
de safra semanas antes do consenso de mercado.

## 2. Por que este projeto (contexto de portfólio)

Fecha, de uma vez, quatro lacunas do portfólio atual:

| Lacuna | Como este projeto fecha |
|---|---|
| Nenhum warehouse cloud | dbt com target `prod` em BigQuery |
| dbt não aparece de verdade | staging / intermediate / marts + testes + docs |
| Sem orquestração nem qualidade de dado | GitHub Actions agendado + `dbt test` no CI |
| Nada clicável pra recrutador | app Streamlit publicado (URL pública) |

Mantém o nicho agro, que é o diferencial real (INTECSO + Coamo + AgriExport).

## 3. Escopo fechado da v1

- **Culturas:** soja e milho 2ª safra (safrinha).
  A safrinha é plantada tarde, depende de chuva residual e sofre com veranico —
  é onde o sinal climático é mais forte. Soja entra como cultura-âncora, de maior volume.
- **Recorte geográfico:** UFs que concentram a produção — MT, GO, PR, RS, MS, MG, BA
  (~85% da soja). Definir o corte exato por participação, não por chute.
- **Grão da fato:** `UF × cultura × safra`. É o grão da CONAB; não inventar precisão municipal
  que o dado de produtividade não tem.
- **Janela temporal:** safras de 2000/01 em diante (NASA POWER começa em 1981, mas
  produtividade pré-2000 tem outro regime tecnológico).
- **Alvo do modelo:** desvio da produtividade **em relação à tendência**, não a produtividade
  absoluta. Sem esse detrend o modelo só redescobre o ganho tecnológico ("ano mais recente =
  safra melhor") e a métrica fica inflada sem valor preditivo.

### Fora do escopo da v1 (registrar para não virar escopo por acidente)
Previsão de preço, dado de satélite (NDVI), grão municipal de produtividade, cultura de
inverno, Dagster/Airflow (GitHub Actions basta para o volume aqui).

## 4. Arquitetura

```
CONAB (TXT)  ─┐
IBGE PAM     ─┼─→ ingestion/ (Python) ─→ data/raw + data/staging (Parquet)
NASA POWER   ─┘                                    │
                                                   ▼
                                       dbt: staging → intermediate → marts
                                        (DuckDB em dev / BigQuery em prod)
                                                   │
                                    ┌──────────────┴──────────────┐
                                    ▼                             ▼
                            analysis/ (modelo)            app/ (Streamlit)
```

**Decisão: DuckDB em dev, BigQuery em prod.** O mesmo projeto dbt aponta para os dois via
target. Dev roda offline, de graça e rápido; prod prova o warehouse cloud. SQL precisa ficar
o mais ANSI possível para os dois adapters aceitarem.

**Decisão: Streamlit, não Evidence.** Evidence exige Node, que não existe nesta máquina.
O Streamlit Community Cloud publica direto do repo do GitHub, de graça.

## 5. Fontes

| Fonte | O que dá | Formato | Status |
|---|---|---|---|
| CONAB Série Histórica de Grãos | área, produção, produtividade por UF × cultura × safra, 1976/77→2025/26 | TXT `;` latin-1 | **validada e ingerida** |
| IBGE SIDRA 1612 (PAM) | produção **municipal** anual, 1974→2024 | API JSON | **ingerida** — 26.320 linhas, 2.632 municípios |
| IBGE malhas v3 | contorno do município (para o centroide) | GeoJSON | **ingerida** — 510 centroides em cache |
| NASA POWER daily | T2M, T2M_MAX, T2M_MIN, precipitação, radiação por ponto | API JSON | validada (amostra); 2s por ponto |

**Por que o PAM entra se a fato é estadual:** o clima do centroide da UF não representa a área
agrícola (o centroide do MT cai em floresta; o da BA, na caatinga não irrigada). O PAM municipal
serve para achar onde a produção realmente está e ponderar o clima por produção.

### Seleção dos polos produtores (`ingestion/geo.py`)
Por UF, municípios ordenados por produção média de grãos (soja + milho somados, porque a
safrinha ocupa o mesmo talhão), acumulando até **80% da produção estadual**. Dá 510 polos.

**O teto por UF não pode ser baixo.** Com teto de 25 a cobertura saía absurdamente desigual:
82% na BA (6 municípios bastam, tudo concentrado no oeste baiano) contra **26% no PR** e 29% no
RS, que são pulverizados — 165 municípios para os mesmos 80%. Isso sub-amostraria justamente o
Sul, onde a variabilidade climática é maior (geada, estiagem). O teto virou salvaguarda em 250.

**Centroide = centro da caixa delimitadora, de propósito.** A grade do NASA POWER tem ~55 km e
o município típico ~40 km: a grade é maior que o município, então centroide de área não mudaria
a célula consultada. Pelo mesmo motivo dá para **deduplicar por célula** — 510 polos viram 255
consultas de clima (economia de 50%).

### ⚠️ Armadilha: fan-out no join polo → célula
A relação é **muitos-para-um** e o fator varia MUITO por UF:

| UF | polos | células | fan-out |
|---|---|---|---|
| PR | 165 | 50 | **3,30** |
| RS | 163 | 63 | **2,59** |
| MG | 76 | 49 | 1,55 |
| MT | 39 | 38 | 1,03 |
| BA | 6 | 6 | 1,00 |

Somar chuva depois desse join **triplica o total do PR e não muda o da BA** — o erro é silencioso
e enviesado por região, exatamente o pior tipo. Já caí nele: a primeira validação deu 5.350 mm/ano
no PR (o real é ~1.620). Qualquer agregação de clima precisa **deduplicar por célula antes de
somar**, ou ponderar por produção dividindo pelo peso total. Nunca `sum()` cru pós-join.

### Armadilhas já encontradas na CONAB
1. **`crop_year` tem dois formatos**: `1976/77` (verão) e `1976` (inverno: trigo, aveia, cevada,
   centeio, canola, triticale). Normalizar no staging.
2. **`produtividade_mil_ha_mil_t` vem arredondada a 1 decimal** (`6.9` para `6902 kg/ha`).
   Sempre recalcular `producao_mil_t / area_plantada_mil_ha * 1000`. Como o alvo é o *desvio*
   de produtividade, esse arredondamento comeria boa parte do sinal.
3. **17.447 das 28.447 linhas têm área plantada zero** (UF que não planta a cultura).
   Filtrar no staging, não na ingestão.
4. **A safra mais recente é estimativa, não realizado.** 2025/26 já aparece com números.
   O arquivo não traz a data do levantamento — tratar a última safra como previsão e
   **nunca usar como verdade de treino**.

## 6. Método (o que dá credibilidade ao projeto)

1. **Detrend:** produtividade esperada por UF × cultura via tendência (regressão robusta sobre
   a safra). O alvo vira o resíduo, em kg/ha e em %.
2. **Janela fenológica por cultura**, não ano civil: soja ~out→fev; milho 2ª safra ~fev→jun.
   Recorte por UF, porque o calendário do MT não é o do RS.
3. **Anomalia climática, não valor absoluto:** desvio contra a normal de 1991–2020 daquele
   ponto e daquele dia do ano. Chuva de 100 mm em maio é normal no RS e catástrofe de seca no MT.
4. **Features com sentido agronômico:** dias secos na janela crítica, graus-dia, noites quentes,
   déficit hídrico acumulado. Não jogar 200 features num XGBoost. *(Dias secos **consecutivos**
   estavam nesta lista e saíram — medido em 04/08, é redundante; ver a seção do veranico.)*
5. **Validação temporal honesta:** treina até a safra `t`, testa em `t+1`. Nada de embaralhar.
   Baseline explícito (previsão = tendência) — se o modelo não bater a tendência, o projeto
   **relata isso**, não esconde. Esse é o padrão do `alpha-validation-lab`.

## 7. Cronograma (~10h/semana, 4–6 semanas)

| Semana | Entrega | Feito? |
|---|---|---|
| 1 | Repo, ingestão CONAB + PAM + POWER, camada raw | parcial — CONAB pronta, PAM e POWER faltando |
| 2 | dbt staging + intermediate (normais climatológicas, janelas) | parcial — projeto dbt de pé, `stg_conab_grain` rodando |
| 3 | Marts + testes dbt + análise exploratória (achar o insight) | ✅ |
| 4 | Modelo, backtest temporal, comparação com baseline | ✅ |
| 5 | Streamlit publicado + GitHub Actions agendado + target BigQuery | ✅ CI verde (3m34s); **app no ar em 07/08** |
| 6 | README em inglês liderado pelo achado, diagrama, post no LinkedIn | |

## 8. Como rodar

Os comandos dbt rodam **de dentro de `dbt/`** — o caminho do DuckDB no `profiles.yml` é
relativo ao diretório de trabalho (`--project-dir` não muda o cwd; já tropeçamos nisso).

```powershell
# uma vez por sessão, só se for usar o BigQuery
$env:GCP_KEYFILE = "C:\Users\caio.prado\.gcp\safra-risk-radar.json"
$env:GCP_PROJECT = "safra-risk-radar"

python -m ingestion --target dev      # baixa as fontes e carrega no DuckDB
python -m ingestion --target prod     # carrega no BigQuery

cd dbt
..\.venv\Scripts\dbt build --target dev
..\.venv\Scripts\dbt build --target prod
```

## 9. Estado atual (07/08/2026)

**Funcionando de ponta a ponta:**
- `.venv` com dbt-core 1.12.0 + dbt-duckdb 1.10.1 + dbt-bigquery 1.12.0 no Python 3.14.5
- `python -m ingestion` roda CONAB → PAM → polos/centroides → NASA POWER → warehouse
- 4 tabelas raw: `conab_grain_series` (28.447), `ibge_pam_municipal` (26.320),
  `producer_hubs` (510), `nasa_power_daily` (**3.313.215**, 1991-01-01 → 2026-07-28)
- 3 modelos staging: `stg_conab_grain`, `stg_producer_hubs`, `stg_weather_daily`
- `dbt build --target dev`: **17/17 verde**
- Chave do BigQuery rotacionada em 04/08 e `dbt debug --target prod` passando

**Validação geográfica do clima (passou):** o gradiente de geada ordena RS (-6,1 °C, 79.501
dias com mínima ≤ 3 °C) → PR → MS → MG → GO → MT (2,0 °C, 2 dias) → BA (10,2 °C, zero).
Chuva anual por UF entre 1.112 mm (oeste baiano) e 1.655 mm (MT), tudo plausível.

**Camada analítica pronta:** `int_crop_windows`, `int_season_weather`, `fct_season_risk`.
`dbt build --target dev`: **29/29 verde**.

### 🎯 O SINAL EXISTE (medido em 04/08)
Correlação entre anomalia climática na janela crítica e resíduo de produtividade (1992–2025):

| Cultura | dias secos | chuva | temperatura |
|---|---|---|---|
| Soja | **-0,39** | +0,29 | -0,29 |
| Milho 2ª safra | -0,26 | +0,21 | -0,18 |

**A exposição climática é muito desigual entre UFs** — o achado mais forte até agora.
Soja, correlação do resíduo com anomalia de chuva: **RS +0,50**, MS +0,39, MG +0,35, PR +0,24,
BA +0,22, GO +0,15, **MT +0,13**. O RS é ~4× mais sensível a chuva que o MT. Média nacional
esconde isso por completo.

**Validação histórica sem ajuda:** as duas piores safras da série são eventos reais —
RS soja 2005 (**-67%** vs tendência, 17 dias secos a mais: a seca de 2004/05) e
PR safrinha 2021 (**-51%**, chuva a **-2,06 desvios-padrão**: a quebra da safrinha de 2021).

### ⚠️ Limitação metodológica encontrada: detrend linear não serve para a safrinha
Produtividade média da safrinha por período: 1.796 → 2.971 → 4.607 → **5.198 kg/ha**. A cultura
saiu de marginal para dominante; a reta não acompanha, e o resíduo dos anos iniciais carrega
**erro de tendência, não sinal climático**. Evidência: cortando a série em 2010+, a correlação
com dias secos sobe de -0,26 para **-0,48**, enquanto a soja fica estável em ~-0,38 nos dois
recortes (a soja cresce perto de uma reta — 2.212 → 3.501).
Encaminhamento para a semana 4: tendência não-linear, início mais tarde, ou os dois.

### ❌ Resultado negativo: o veranico não é a variável forte que se esperava (04/08)
Implementado o veranico — maior sequência de dias secos dentro da janela crítica, por
gaps-and-islands sobre a série diária (`int_season_weather.sql`). **A hipótese era que ele
fosse a variável mais forte do conjunto. É mais fraca que a contagem simples de dias secos:**

| Métrica (correlação com o resíduo, 1992–2025) | Soja | Safrinha |
|---|---|---|
| Dias secos soltos (já existia) | **-0,39** | **-0,26** |
| Veranico na janela | -0,25 | -0,20 |
| Dias em veranicos ≥ 10 dias | -0,29 | -0,22 |
| Veranico da pior célula | -0,22 | -0,16 |

Não é fragilidade da definição: testados limiares de dia seco de 1, 2 e 5 mm (a suspeita era
que uma garoa de 1,2 mm partisse um veranico em dois) e quatro formas da métrica — **nenhuma
das 12 combinações bate o baseline.** A melhor delas, dias em veranicos ≥ 10 dias com limiar de
2 mm, chega a -0,31 na soja.

**O teste que fechou a questão foi a correlação parcial.** Veranico e dias secos correlacionam
**0,73** entre si na soja; controlando por dias secos, o que sobra do veranico é **+0,05** — some
e ainda troca de sinal. Na safrinha sobra -0,10. Por UF, só GO (-0,26) e MG (-0,18) mostram algo
residual; no PR e no RS o sinal inverte, que é o que ruído faz.

**Leitura:** numa janela de ~120 dias, a contagem total de dias secos já é um proxy de déficit
hídrico acumulado e é mais estável. O veranico descreve **um** evento e joga fora o resto da
janela, então carrega mais variância amostral pela mesma informação.

**Decisão:** a coluna **fica no mart como descritiva, fora do modelo.** "31 dias sem chuva no
enchimento de grão, contra 12 normais" é a versão legível do mesmo fato, e o dashboard precisa
falar assim. De propósito **não tem z-score** — publicar um convidaria a tratá-la como feature
ao lado das outras. Isso vai para o README: testar uma hipótese agronômica plausível e publicar
que ela não se sustentou é o padrão do `alpha-validation-lab`.

### ⚠️ Armadilha: medir o veranico inteiro captura a estação seca, não o veranico
Primeira implementação contava o **spell completo** que tocasse a janela (argumento: se choveu
zero por 40 dias, o solo está seco quando a cultura entra no enchimento, tendo a seca começado
antes ou não). Some com a realidade da BA: a janela da soja fecha em abril, exatamente quando
começa a estação seca de cinco meses. O veranico médio da BA foi a **29 dias** (contra 12 no PR)
e a pior célula a **180 dias** — a métrica virou um detector de estação seca, e enviesado por
região, a mesma classe de erro do fan-out. A versão que ficou conta **só os dias dentro da
janela**: a BA cai para 11,8, alinhada com PR (10,9) e RS (11,4).

### ✅ Modelo preditivo entregue — e o resultado tem uma manchete diferente da esperada
Código em `analysis/` (`dataset.py`, `trend.py`, `compare_detrend.py`, `backtest.py`).
Backtest walk-forward de 2003 a 2025: **tendência, normais climatológicas e modelo são todos
refeitos a cada safra usando só o passado.** Nada da safra `T` está disponível quando `T` é
prevista — inclusive as normais, que no mart são fixas em 1992–2020 e ali seriam vazamento.

**Na média, o modelo empata com o baseline.** Skill sobre "safra = tendência": soja **+3,4%**,
safrinha **+1,2%** no RMSE do resíduo. Acerto direcional 53% e 58% — perto de moeda.
Se o projeto parasse aqui, a conclusão publicada seria "não bate a tendência".

**Mas a média esconde o resultado.** Separando por severidade da safra:

| Faixa do desvio real | n (soja) | RMSE baseline | RMSE modelo | Ganho |
|---|---|---|---|---|
| Quebra < -20% | 14 | 34,4 | 20,6 | **+40%** |
| -20% a -10% | 15 | 15,7 | 10,8 | **+31%** |
| Normal ±10% | 89 | 5,9 | 9,6 | -61% |
| Boa > +20% | 12 | 33,5 | 34,8 | -4% |

**O modelo é útil só nas quebras, e atrapalha em ano normal** — e ano normal é 55% da amostra,
o que dilui tudo no RMSE global. Na safrinha o padrão se repete mais fraco (+27% nas quebras).
Detecção de safra 10% ou mais abaixo da tendência: **recall de 45% na soja e 50% na safrinha**,
com precisão de ~50%. O baseline detecta **zero** por construção — ele nunca prevê quebra.

Essa é a leitura honesta e é a que vai para o README: *não* é um previsor de safra; é um
detector de quebra com metade de acerto e metade de falso alarme, contra um baseline que
nunca avisa. Para trading e crédito rural, avisar metade das quebras com antecedência vale
mais que 3% de RMSE.

**Erro de previsão da produtividade** (comparável à tabela de tendências, mesma métrica):
soja **22,3% → 16,7%**, safrinha **31,8% → 26,5%**.

### A escolha do detrend: as duas hipóteses da sessão anterior caíram
`compare_detrend.py` testa 12 formas de tendência por erro out-of-sample. Resultado para a
safrinha, onde a reta era o problema conhecido:

- **Tendência não-linear não resolve.** `log_linear` é a **pior** de todas (RMSE 39,4 contra
  31,5 da reta, viés de +15%): em espaço log a expansão inicial extrapola para o absurdo.
  Quadrática e Theil-Sen também perdem para a reta.
- **O que ganha é não extrapolar:** média móvel de 3 anos, RMSE 28,3 e viés -3%.
- **E mesmo assim a reta ficou.** A média móvel é melhor *previsão* e pior *alvo*: ela já
  absorve o clima recente, então o resíduo contra ela carrega reversão à média em vez de
  clima, e todo modelo treinado nesse alvo ficou ~50% **pior** que o próprio baseline. Na reta,
  os mesmos modelos batem o baseline. Ponta a ponta — que é o que importa — reta + modelo
  (26,5% de erro) bate média móvel sozinha (28,6%).

⚠️ **Viés de seleção declarado:** o par tendência × modelo foi escolhido olhando o backtest.
Os números acima são otimistas por uma margem desconhecida; o teste honesto é a próxima safra
não vista. Registrado no código também, não só aqui.

### ⚠️ Armadilha: janela climática incompleta lê como seca
A previsão da safrinha 2026 saiu com **+99% no PR e +96% no MS** — quase o dobro de qualquer
produtividade já registrada. Causa: o NASA POWER vai até 28/07/2026 e a janela crítica do PR é
abr–ago, então só **119 dos 153 dias** estavam na base. Menos dias = menos chuva acumulada e
menos dias secos, o modelo lê "anomalia extrema" e extrapola. Guard implementado: só prevê com
**≥95% da janela coberta**; PR e MS ficam suprimidos até agosto entrar na base.
Isso é o mesmo problema da janela parcial (decisão abaixo), e mostra como ela precisa ser feita:
as anomalias têm de ser medidas contra a normal **da mesma janela parcial**, nunca da completa.

### Previsão para 2026 (a CONAB ainda não fechou)
Soja, desvio previsto contra a tendência: **RS -22,9%**, **PR -12,5%**, MS -6,7%, o resto perto
de zero. O modelo está **mais pessimista que a CONAB** no RS (2.226 contra 2.769 kg/ha
estimados, -20%) e no PR (-17%). É a aposta verificável do projeto — quando a CONAB fechar,
dá para conferir sem ajuste posterior.
Na safrinha as diferenças contra a CONAB são grandes (GO +26%, BA -23%), mas ali o erro é
principalmente da **tendência**, não do clima: a série é curta e a reta ainda é frouxa.

### ✅✅ App Streamlit PUBLICADO — https://safra-risk-radar.streamlit.app
No ar desde 07/08/2026. Verificado em produção no mesmo dia: os 4 gráficos, as 4 métricas e os
2 filtros renderizam, sem overflow horizontal e sem erro de console, e o aviso de janela truncada
já saiu com a data vinda do dado ("the weather series ends 31 July 2026").

⚠️ **Para inspecionar a página por ferramenta, use `/~/+/`.** A URL raiz devolve só a casca do
Community Cloud (avatar do criador, status) e o app vive num iframe — ler o DOM da raiz dá página
vazia e parece app quebrado. `https://safra-risk-radar.streamlit.app/~/+/_stcore/health` responde
`ok` e é a checagem rápida de que o servidor está de pé.


`app/streamlit_app.py` (layout e texto) + `app/charts.py` (figuras e transformações, sem
Streamlit — dá para renderizar e **olhar** os gráficos fora do app, que foi como os problemas
de leitura apareceram). Roda local com:

```powershell
.venv\Scripts\python -m streamlit run app\streamlit_app.py
```

**Decisão: o app não fala com o warehouse.** `analysis/export_app_data.py` congela três CSVs em
`app/data` (244 KB no total) e o app lê deles. Motivo: o Community Cloud serve do repo do
GitHub e `data/` é gitignorado (171 MB). Assim o app publicado não tem credencial, não gasta
cota do sandbox e não quebra quando as tabelas do BigQuery expiram. `app/requirements.txt` é
propositalmente magro (streamlit + pandas + plotly) — sem duckdb, dbt ou scikit-learn.
**Rodar o export de novo sempre que o `dbt build` mudar os marts.**

O app lidera pelo resultado honesto ("weather predicts the bad harvests"), tem tabela para cada
gráfico e uma seção final de limitações que inclui o viés de seleção. Cores da paleta validada,
tema claro fixo em `.streamlit/config.toml` — tema escuro exigiria revalidar os passos.

**Nada que o texto afirma sobre o dado pode ser digitado à mão.** A frase do aviso de janela
truncada trazia "the weather series ends 28 July 2026" escrito no código, e o primeiro refresh
automático já a deixou errada: a série andou para 31/07 e a frase não. O export passou a gravar
`app/data/meta.json` (`weather_through`, lido do `stg_weather_daily`) e o app formata a data de
lá; o `selftest` falha se o arquivo sumir ou vier sem data parseável, porque essa data é impressa
em prosa e um `KeyError` derrubaria a página inteira, não só a frase.

**Como foi publicado:** share.streamlit.io → New app → repo `caiogoia123/safra-risk-radar`, branch
`main`, main file `app/streamlit_app.py`, Python 3.13 no Advanced settings. Sem secrets — o app não
toca o warehouse. O Community Cloud acha o `app/requirements.txt` sozinho (procura primeiro no
diretório do entrypoint, depois na raiz), então o `requirements.txt` pesado da raiz fica de fora.
**Todo push no `main` dispara redeploy automático.**

### ✅ CI no GitHub Actions
Dois workflows, separados por custo:

- **`.github/workflows/ci.yml`** — todo push e PR, ~1 min, sem warehouse e sem credencial.
  Job `dbt-parse` resolve o grafo inteiro (pega um `ref` para modelo renomeado sem precisar de
  dado); job `app` instala o `app/requirements.txt` e roda `app/selftest.py`, que constrói **todas**
  as figuras do dashboard a partir dos CSVs commitados. Esse selftest existe por um motivo
  específico: se o export e o código dos gráficos divergirem (uma coluna renomeada), o dashboard
  publicado quebra para todo mundo e nada mais no repo perceberia.
- **`.github/workflows/refresh.yml`** — segundas 06:00 UTC + manual. Ingestão completa →
  `dbt build --target dev` → BigQuery (load + `dbt build --target prod`) → `export_app_data` →
  commita `app/data` se mudou. Mata dois coelhos: mantém o app atual e **zera o relógio dos 60
  dias** das tabelas do sandbox.

**Secrets a configurar** (Settings → Secrets and variables → Actions): `GCP_SA_KEY` com o
**conteúdo** do JSON da service account e `GCP_PROJECT` com `safra-risk-radar`. Sem eles o
refresh ainda roda — só pula a metade do BigQuery. O `refresh.yml` **não** dispara em
`pull_request` de propósito: num repo público, isso impede que um PR de terceiro rode código
com acesso ao secret.

### ⚠️ O NASA POWER estrangula IP de datacenter (primeiro run do CI morreu por isso)
O primeiro `refresh.yml` foi **cancelado pelo timeout de 60 min** dentro da ingestão. Não era
loop nem bug: as mesmas 255 células que levam ~13 min na máquina do Caio (2,6 s por célula,
1 MB de resposta) não terminaram em 59 min no runner — mais de 14 s cada, ~5× mais lento.

Três consertos, todos aplicados:
1. **Download concorrente do POWER** (`MAX_WORKERS = 5` em `ingestion/nasa_power.py`). O tempo é
   espera de rede, não processamento, então sobrepor recupera quase tudo: medido localmente,
   **75 células/min contra ~23 sequencial** (3,3×). Validado com 10 células tiradas do cache e
   rebaixadas — coordenadas, parâmetros e número de dias idênticos ao original. Timeout por
   request caiu de 300 s para 120 s, e entrou retry com backoff (2 tentativas) para não perder o
   run inteiro por um 5xx isolado.
2. **`python -u` no workflow.** O log ficou uma hora em branco porque o Python bufferiza stdout
   fora de terminal — os prints de progresso ficaram presos no buffer. Um passo silencioso é
   indistinguível de um travado, e foi o que fez parecer loop infinito.
3. **`ingestion/geo.py` tinha o mesmo defeito, e passou despercebido no primeiro conserto.** São
   **510 requisições sequenciais** ao IBGE, com um único print no fim. A API é rápida (0,40 s
   medidos), mas 510 × (0,40 + 0,3 de sleep) já dá 7,6 min local e muito mais no runner.
   Paralelizado igual, com progresso a cada 50: **204/min contra ~86 sequencial**, e os 20
   centroides testados voltaram idênticos ao cache original. Lição: ao achar um gargalo desse
   tipo, procurar os irmãos dele no mesmo módulo antes de dar por encerrado.

### Auditoria da ingestão (04/08, antes do 3º run) — 3 achados a mais
Varredura pedida pelo Caio atrás de outros pontos frágeis, com tudo medido em vez de estimado:

4. **`ibge_pam.py`: 14 requisições sequenciais** (7 UFs × 2 culturas), ~20 s cada no runner, ~5 min
   de espera pura. Paralelizado: **27 s local**, com as 26.320 linhas byte a byte idênticas.
5. **🔴 O mais importante: o SIDRA caiu no meio de uma resposta durante a própria medição** —
   `ChunkedEncodingError: IncompleteRead(621971 bytes read, 711168 more expected)`. Nem
   `ibge_pam` nem `geo` tinham retry: uma falha dessas aos 25 min de execução jogava fora tudo o
   que já havia sido baixado. Criado o **`ingestion/http.py`**, um único helper com retry e
   backoff, agora usado pelas quatro fontes. Retry só no que é transitório (timeout, conexão
   caída, resposta truncada, 5xx, 429); **4xx propaga na hora**, de propósito — foi um 400 do
   IBGE que revelou o bug do `qualidade=1` na sessão 1, e repetir teria escondido a causa.
   Os quatro caminhos foram testados (200 real, retry com sucesso na 3ª, falha persistente
   propagada, 400 sem retry).
6. **O export não era reprodutível.** Soma de float não é associativa: com as fontes buscadas em
   paralelo, os mesmos dados somados em ordem diferente mudavam a 12ª casa decimal, e isso sozinho
   reescrevia **758 linhas de CSV** num run em que nada mudou — o job semanal ficaria commitando
   ruído puro e enterrando os diffs de verdade. `analysis/export_app_data.py` passou a arredondar
   os floats em 6 casas; dois exports seguidos agora são byte-idênticos.

**Medido e OK, não precisa de ajuste:** `to_parquet` do POWER (20 s, pico de 212 MB — folgado no
runner), `export_app_data` (69 s), `dbt build` completo (11 s, 29/29 verde), `conab.py` (uma única
requisição, agora com retry). `scripts/extract_conab_calendar.py` não entra no CI (só roda quando
a CONAB publica edição nova do calendário).

**Pipeline inteiro revalidado depois da refatoração:** ingestão completa → `dbt build` 29/29 verde
→ export → selftest verde, com as mesmas 455 linhas do fato, 3.313.215 de clima e as mesmas
previsões (soja RS -22,885%).

### ✅✅ CI VERDE — 3m34s, ponta a ponta (04/08)
Primeiro run completo do `refresh.yml`, do download ao commit:

```
[pam]   26,320 rows | 2,632 municipalities from pam_municipal.parquet, no request needed
[geo]   510 centroids from centroids.json, no request needed
[power] 255/255 downloaded | 142.6/min | 3,313,980 rows
dbt     PASS=29 WARN=0 ERROR=0
commit  [main e3b1649] Refresh dashboard data [skip ci] -> 2 files, 12 insertions, 12 deletions
```

**De >59 min falhando para 3m34s verde.** O POWER, único download que sobrou, roda a **142
células/min no runner** — mais rápido que na máquina local (75/min), o que reforça que o gargalo
nunca foi banda, e sim o IBGE recusando IP de datacenter.

**As 12 linhas do commit automático são a prova de que a reprodutibilidade funcionou.** O POWER
trouxe 765 linhas novas (série até 31/07 em vez de 28/07), e isso mexeu só nas safras em curso:
`forecast.csv` e `season_risk.csv` com 12 linhas cada, `backtest.csv` **intocado** — o histórico
não muda. Sem o arredondamento e a ordenação, esse mesmo commit teria reescrito 758 linhas de
ruído e o histórico do repo seria inútil.

⚠️ **Os passos do BigQuery foram pulados** — `HAS_GCP` falso, secrets ainda não configurados.
Então o segundo objetivo do workflow, manter as tabelas do sandbox dentro dos 60 dias, ainda
**não** está sendo cumprido. Falta criar `GCP_SA_KEY` e `GCP_PROJECT` em Settings → Secrets and
variables → Actions.

### O caminho até aqui: o IBGE saiu inteiro do caminho crítico do CI
Depois dos centroides, o run seguinte morreu no **PAM**: as 14 requisições ao
`apisidra.ibge.gov.br` falharam, todas as 4 tentativas, com `ConnectTimeout` imediato. Os dois
domínios do IBGE (`servicodados` e `apisidra`) recusam conexão de IP de runner — intermitente no
começo, consistente depois.

Mesma solução, porque é o mesmo tipo de dado: **`YEARS` está fixo em 2020-2024**, o PAM é anual e
esses anos estão fechados. Cada run baixava 3,9 MB de JSON para reconstruir uma tabela idêntica.
Versionado como **`ingestion/reference/pam_municipal.parquet`** — 146 KB, um vigésimo do JSON, e é
o parquet que o warehouse carrega de fato. Atualizar é deliberado:
`py -c "from ingestion import ibge_pam; ibge_pam.run(force=True)"`.

**O CI agora depende só de CONAB e NASA POWER**, as duas fontes que respondem ao runner. Validado
apagando todo o `data/` do IBGE: ingestão completa → `dbt build` 29/29 → export → selftest, tudo
verde, e os CSVs **sem uma linha de diferença**.

Os três insumos versionados seguem a mesma regra e a mesma justificativa (`crop_calendar.csv`,
`centroids.json`, `pam_municipal.parquet`): derivado uma vez da fonte oficial, commitado,
regenerado sob comando. **Antes de otimizar um download, perguntar se o dado muda.**

### O gargalo anterior: os centroides viraram insumo versionado
O 5º run mostrou que paralelizar o IBGE **piora**: a taxa decaiu **124 → 75 → 53 → menos de
5 por minuto** ao longo do run, até a API parar de aceitar conexões e derrubar o job mesmo com
4 tentativas por município. O `servicodados.ibge.gov.br` estrangula IP de datacenter de forma
progressiva — quanto mais se insiste, menos ele responde.

A saída não foi ajustar concorrência, foi **parar de baixar**: contorno municipal é dado
estático, redesenhado a cada vários anos. Estávamos fazendo 510 requisições semanais para
recalcular **16 KB de números que não mudam**. O arquivo saiu de `data/raw/ibge/` (gitignorado)
para **`ingestion/reference/centroids.json`**, versionado — mesmo tratamento já dado ao calendário
da CONAB extraído do PDF: derivado uma vez da fonte oficial, commitado, regenerado de propósito.

- O passo `geo` caiu de **15+ min (e falhando) para 0,12 s, sem nenhuma requisição**.
- Some do CI a fonte mais instável das três; sobra só o POWER, que tem dado novo de verdade.
- Se o ranking de polos mudar e faltar município, o log diz exatamente o que fazer:
  `py -c "from ingestion import geo; geo.run(force=True)"` e commitar. Testado removendo 2
  entradas — busca só as que faltam, os valores voltam idênticos e o arquivo é reescrito ordenado.
- O arquivo só é reescrito quando algo é buscado, e com chaves ordenadas: sendo versionado, uma
  reescrita à toa seria diff falso.

### ⚠️ `select *` sem `order by` não é determinístico
Descoberto ao revalidar: recarregar o warehouse mudou a ordem das linhas do `fct_season_risk` e
reescreveu **63 linhas** de `season_risk.csv` sem nenhum valor ter mudado. Agora o export ordena
explicitamente (no SQL e no pandas, `SORT_KEYS` por dataset). Junto com o arredondamento, os CSVs
passaram a depender só do dado: **dois exports com o warehouse inteiro recarregado no meio saem
byte a byte idênticos** — que é a condição para o commit automático semanal só mexer no que mudou.

**E vale entre máquinas, não só entre dois runs aqui:** em 07/08, com o `data/` local
ressincronizado até 31/07, o export reproduziu os três CSVs **byte-idênticos aos que o runner
tinha commitado** — mesmo tendo passado por download concorrente, outra máquina e outro sistema
operacional. Sem o arredondamento e a ordenação explícita isso não aconteceria.

### 3º run: o paralelismo funcionou, e a falha foi de versão
Ingestão caiu de **>59 min para 11m38s** — problema de tempo resolvido. O run mesmo assim falhou,
com `ConnectTimeout` no SIDRA, e o traceback mostrava `requests.get` direto em `_fetch`: **o CI
estava rodando o commit anterior**, sem o `http.py`. As correções da auditoria existiam só na
máquina local. Lição operacional trivial e cara: *push antes de disparar*, e conferir a versão
pelo traceback antes de investigar a lógica.

**A falha valeu por um achado, ainda assim.** O timeout de 180 s de cada fonte é dimensionado para
uma *resposta* lenta, mas o `requests` aplica o mesmo número à conexão TCP — o run gastou 139 s
num handshake que nunca ia completar. `http.fetch` passou a separar os dois orçamentos
(`CONNECT_TIMEOUT = 10`): host inalcançável agora falha em 20 s com duas tentativas, contra 360 s
antes, e é isso que dá espaço para o retry acontecer de fato. Retries subiram para 3 (espera
acumulada de 30 s), porque desistir custa dez minutos de run e esperar custa segundos.
O SIDRA respondeu normalmente no run anterior — é instabilidade da API, não bloqueio de IP.

**O desperdício estrutural continua de pé:** cada run rebaixa 35 anos (70 MB) para obter 7 dias
novos. A correção definitiva é cache incremental por época — histórico até dez/2025 imutável no
`actions/cache` e só o ano corrente por request — que levaria o refresh a ~2-3 min. Decidido em
04/08 **não** fazer agora: o paralelismo já traz para dentro do orçamento de tempo.

### ⚠️ O cache do POWER era validado só por existência (warehouse local 3 dias atrás)
Em 07/08 um `python -m ingestion --target dev` local imprimiu `19910101 -> 20260731` e carregou
`1991-01-01 -> 2026-07-28`. O cache tinha sido baixado três dias antes e `fetch_cell` devolvia o
arquivo **só por ele existir**, sem olhar até quando ia. O CI nunca viu isso — runner limpo começa
sem cache. Um `export_app_data` local depois disso teria regredido os CSVs de `app/data` que o
refresh semanal já havia commitado com dado mais novo.

Agora todo run lê a última data de dentro de cada arquivo e rebaixa as células que param antes da
janela pedida. **O POWER responde exatamente a janela pedida**, preenchendo com -999 os dias que
ainda não publicou (verificado na API ao vivo em 07/08: `end` um dia atrás volta completo, com -999
na cauda). Por isso a data dentro do arquivo *é* a data com que ele foi pedido, e a comparação
nunca entra em loop rebaixando tudo à espera de dado que não existe — confirmado rodando duas vezes
seguidas: o segundo run não baixa nada.

- Ler os 255 arquivos custa 8-14 s (quente/frio), contra minutos de download. mtime ou tamanho
  seriam chute: a data está dentro do payload.
- Arquivo ilegível (escrita interrompida) conta como ausente e é rebaixado, em vez de estourar no
  `to_parquet` minutos depois.
- `to_parquet` também avisa quando as células discordam entre si: uma faixa única para a tabela
  inteira escondia justamente o subconjunto que parava antes.
- `--force` continua tudo-ou-nada e refaz as 510 requisições de centroide ao IBGE, que foram
  deliberadamente tiradas do caminho. Para pular o rebaixamento sem isso existe `--allow-stale`,
  que só avisa alto — útil offline ou mexendo em parsing.

**Efeito colateral aceito: o cache local passou a valer um dia.** O `end_date` é `hoje - 7`, então
anda sozinho — medido em 07/08 com o cache baixado na mesma manhã: hoje dá `255 reach 20260731,
0 stale`; com a data um dia à frente, `0 reach 20260801, 255 stale`. Ou seja, **todo `python -m
ingestion` num dia novo rebaixa os 70 MB inteiros (~3 min) para ganhar 1 dia de clima**. Antes era
permanente, mas só porque era o bug. Fica assim de propósito: carregar em silêncio a janela da
semana passada é pior que gastar 3 min, e quem quiser evitar o download tem o `--allow-stale`.

**Isto não substitui o cache incremental por época**, que continua sendo a correção definitiva —
e que agora resolveria as duas coisas de uma vez. O que mudou aqui é a falha ter deixado de ser
silenciosa.

### ⚠️ Armadilha: `data/` no .gitignore também casava com `app/data/`
Uma linha `data/` sem barra inicial casa com **qualquer** diretório `data` em qualquer nível.
Os CSVs do dashboard estavam sendo silenciosamente ignorados — o commit `8878ea9` foi feito com
a mensagem "with exported mart data" e **sem os dados**; publicado assim, o app cairia com
`FileNotFoundError`. Corrigido para `/data/`, ancorado na raiz. Sintoma a lembrar: `git add`
não reclama de arquivo ignorado, ele simplesmente não adiciona.

**Ainda não existe:** README final.

### Próximos passos, em ordem
1. **Configurar `GCP_SA_KEY` e `GCP_PROJECT`** nos secrets. Confirmado em 07/08 pela API do GitHub
   que o refresh **continua pulando os três passos do BigQuery** (`skipped`): o último `dbt build
   --target prod` foi em 04/08, então **as tabelas do sandbox expiram por volta de 03/10/2026**.
   É a única pendência com prazo.
2. README final liderado pelo achado + post no LinkedIn. **Incluir a URL do app** — hoje o README
   cita "Streamlit app" no diagrama mas não tem link nenhum para o dashboard no ar.
3. *(Opcional, alto valor)* **Janela parcial** — prever com o clima até janeiro em vez da janela
   fechada, medindo quanto de precisão se perde por mês de antecedência ganho. Vira o gráfico
   mais forte do dashboard. Exige um modelo dbt de clima acumulado por mês da janela e normais
   parciais correspondentes (ver a armadilha acima).

Dívida pequena, quando for mexer no dbt de novo: os modelos não têm `_models.yml` — os 22 testes
atuais são todos de source e de seed. As colunas do mart não têm teste nenhum.

### Git
Tudo commitado e no GitHub até `129f849` (07/08/2026), CI verde. **O Caio faz todos os commits** —
entregar os comandos prontos, nunca executar ([[preferencias]] na memória nativa).

### Infra resolvida (não repetir a pesquisa)
- **BigQuery sandbox**: sem cartão, sem conta de faturamento. 1 TB de consulta e 10 GB de
  armazenamento por mês; ao estourar, bloqueia em vez de cobrar. Upgrade é manual.
- **Conta de serviço funciona no sandbox** — a documentação não dizia, foi testado e funciona.
  Chave em `C:\Users\caio.prado\.gcp\safra-risk-radar.json`, fora do repo.
- **Tabelas expiram em 60 dias** no sandbox, mas cada `dbt build` recria e zera o relógio.
  O CI agendado da semana 5 mantém tudo vivo sozinho.
- **Sem DML no sandbox** — por isso tudo é `materialized: table`; `incremental` e `snapshot`
  não funcionariam lá.
- Dataset `safra_raw` (carga) e `safra_staging`/`safra_marts` (dbt), todos em
  `southamerica-east1`. Região não pode ser trocada sem recriar o dataset.

## 10. Calendário agrícola (resolvido — fonte oficial)

Os meses de plantio e colheita por cultura × UF vêm do **Calendário de Plantio e Colheita de
Grãos no Brasil (CONAB, 2022)**, o PDF oficial. Viraram o seed `dbt/seeds/crop_calendar.csv`.

**Não foram digitados à mão.** O PDF codifica os meses como **barras coloridas**, não texto —
o texto da página só tem as siglas das UFs e os cabeçalhos dos meses. O
`scripts/extract_conab_calendar.py` lê a geometria: a cor da barra dá a fase (laranja = plantio,
azul = colheita, verde = ambos) e o intervalo horizontal dela diz quais colunas de mês cobre.
Rodar de novo só quando a CONAB publicar edição nova.

### ⚠️ Armadilha: o calendário é circular
As colunas vão de **Out a Set**, então Out/Nov/Dez são do ano anterior ao da colheita
(safra 2023/24 → `harvest_year` 2024, e o outubro dela é outubro de 2023). O problema está no
**setembro**: quando o plantio da soja começa em setembro, a barra aparece na **última** coluna,
mas se refere ao setembro *anterior* a outubro. Tratado como offset 0, a janela de plantio do MT
ficaria **onze meses fora do lugar**.

Regra aplicada: setembro volta para o ano anterior **só quando emenda contiguamente em outubro
dentro da mesma fase**. Isso corrige a soja do MT e do PR (plantio set–dez) sem estragar a
colheita da safrinha em MS e PR (jun–set), onde setembro é mesmo do ano da colheita.

### O que a CONAB diz (extraído)
| Cultura | UF | Plantio | Colheita |
|---|---|---|---|
| Soja | MT | set–dez | jan–abr |
| Soja | GO, MG, MS | out–dez | jan–abr |
| Soja | PR | set–jan | jan–mai |
| Soja | RS | out–jan | fev–mai |
| Soja | BA | out–jan | jan–mai |
| Milho 2ª safra | MT | jan–mar | mai–ago |
| Milho 2ª safra | GO | jan–fev | jun–ago |
| Milho 2ª safra | MG, MS | jan–mar | jun–set |
| Milho 2ª safra | PR | jan–abr | mai–set |
| Milho 2ª safra | BA | mar | jul–ago |

**O RS não tem calendário de milho 2ª safra na CONAB** — o estado não faz safrinha relevante.
Ele fica fora dessa metade da análise, e isso precisa aparecer no README como recorte, não
como dado faltando.

Ciclo da soja, da mesma publicação: **105 a 135 dias**.

### Janela crítica (aprovada pelo Caio em 04/08, implementada)
O calendário dá plantio e colheita, não a fase de enchimento de grão — que é a sensível à seca.
A janela crítica é **derivada**, e por ser decisão de modelagem e não dado oficial, o seed guarda
só o que a CONAB publica; a derivação vive numa regra explícita em `int_crop_windows.sql`.

**Regra:** do último mês de plantio até um mês antes do fim da colheita. O enchimento antecede
imediatamente o corte, e o fim da janela de colheita é secagem em campo, quando o clima já não
define produtividade.

| Cultura | UF | Janela crítica |
|---|---|---|
| Soja | MT, GO, MG, MS | dez–mar |
| Soja | PR, RS, BA | jan–abr |
| Milho 2ª safra | MT, MG, BA | mar–jul |
| Milho 2ª safra | PR | abr–ago |

### Índice de mês da safra (truque que simplificou tudo)
Meses viram um índice sequencial da safra: `Set(-1) = -3 … Dez(-1) = 0, Jan = 1 … Set = 9`.
A propriedade útil: para a safra de colheita `Y`, o índice `s` é o mês absoluto `Y * 12 + s`
nos dois ramos. Assim toda a aritmética de data vira soma de inteiros — sem construir datas,
o que também mantém o SQL portátil (DuckDB tem `make_date()`, BigQuery tem `DATE()`).

## 11. Modelo preditivo — o que exatamente se prevê

Ponto que gerou confusão na conversa de 04/08 e precisa ficar explícito:
**clima é ENTRADA, não saída. Não se prevê tempo.**

```
ENTRA:  clima que JÁ aconteceu (medido pelo NASA POWER, já na base)
   ↓
SAI:    produtividade que ainda NÃO foi divulgada pela CONAB
```

- **Alvo:** `yield_residual_pct` — o desvio percentual da produtividade contra a tendência
  do próprio estado. Não a produtividade absoluta: um modelo treinado no nível só redescobre
  o ganho tecnológico, exibe métrica boa e não serve para nada.
- **Grão:** UF × cultura × safra.
- **Features:** as anomalias já prontas no `fct_season_risk` (dias secos, chuva, temperatura,
  graus-dia), cada uma medida contra a normal do próprio estado.
- **Baseline obrigatório:** "a safra vai ser igual à tendência" (resíduo = 0). Se o modelo com
  clima não bater esse chute, **publica-se esse resultado** — é o padrão do `alpha-validation-lab`.
- **Validação:** treina até a safra `t`, testa em `t+1`. Nunca embaralhado.

**Por que isso tem valor:** o número oficial sai meses depois de o clima ter acontecido, e é
nesse vão que trading, crédito rural e seguro agrícola decidem. Exemplo real da própria base:
o clima de abr–ago/2021 no PR (chuva a -2 desvios, 19 dias secos a mais) era fato medido muito
antes de a CONAB fechar a produtividade que veio 51% abaixo da tendência.

### Estado da decisão janela completa × parcial
**Implementada a completa** (v1, em `analysis/backtest.py`). A parcial continua valendo a pena e
virou o item 4 dos próximos passos, com um requisito que a armadilha da safra 2026 deixou claro:
as anomalias precisam ser medidas contra a normal **da mesma janela parcial**. Comparar clima
parcial contra normal de janela cheia produz anomalia falsa — foi assim que o PR 2026 virou +99%.

A **safra corrente (2025/26) já é estimada** — ver "Previsão para 2026" no estado atual.

## 12. Log de sessões

**04/08/2026 — sessão 1 (trabalho)**
Escolhido o projeto entre 4 alternativas. Ambiente validado (Python 3.14, git, rede liberada
para IBGE/CONAB/NASA/PyPI/GitHub). Maior risco técnico afastado: dbt instala no Python 3.14.
Três fontes sondadas com dado real. Escopo fechado e ingestão da CONAB entregue.
Repo publicado em github.com/caiogoia123/safra-risk-radar.
Conta GCP criada (sandbox) e **fatia vertical fechada**: CONAB → Parquet → DuckDB + BigQuery →
`dbt build` verde nos dois targets, com 5 testes passando.
Sondagem do PAM municipal deu certo (1.996 linhas para o PR em 5,5s) e o NASA POWER é barato
(2s por ponto).
Pendência dos centroides **resolvida na mesma sessão**: a API de malhas do IBGE funcionava o
tempo todo — eu é que passava `qualidade=1`, parâmetro inválido para município, e a API devolve
400 com um JSON de erro. Meu código procurava `features` nesse corpo de erro e quebrava com
`KeyError` em vez de checar o status. Lição: sempre `raise_for_status()` antes de ler o payload.
PAM e polos ingeridos, `dbt build` 12/12 verde.
Chave do BigQuery **rotacionada e validada** no fim da sessão.
NASA POWER ingerido: 255 células, 3,3 milhões de linhas, 1991 → jul/2026, 21 fill values (-999)
convertidos para nulo. `dbt build` 17/17 verde com os 3 modelos de staging.
Armadilha do fan-out polo → célula descoberta durante a validação e documentada na seção 5.

**04/08/2026 — sessão 2 (trabalho)**
Veranico implementado, medido e **rebaixado de feature a coluna descritiva** — a hipótese não se
sustentou (seção "Resultado negativo", acima). Saldo da sessão: uma variável a menos para o
modelo e um achado a mais para o README.
Duas coisas técnicas ficaram de pé no caminho: `day_index` no `stg_weather_daily`, um contador de
dias sem buracos (`weather_year * 366 + day_of_year` parece equivalente e não é — deixa um furo
em cada virada de ano, que partiria justamente o veranico de dez→jan da soja), gerado com a macro
`dbt.datediff` para não amarrar o SQL a um adapter; e o gaps-and-islands em si, que no
`compile --target prod` sai como `datetime_diff` do BigQuery — portabilidade confirmada sem gastar
cota. Validado também que a série diária não tem nenhum dia faltando nas 255 células e que 1.854
spells cruzam a virada do ano (se o índice estivesse errado, seriam zero).
`dbt build --target dev`: **29/29 verde**.
Uma linha (BA safrinha 2011) viola por 1,4e-14 o invariante `worst_cell >= média ponderada` —
é acúmulo de ponto flutuante quando todas as células têm o mesmo valor, não erro de lógica.

**04/08/2026 — sessão 3 (trabalho)**
Semana 4 fechada: `analysis/` com detrend, backtest walk-forward e previsão da safra corrente.
scikit-learn 1.9 instalado (wheel para Python 3.14 existe) e fixado no `requirements.txt`.
Duas hipóteses da sessão anterior caíram no teste — detrend não-linear para a safrinha (a pior
de todas) e a média móvel como alvo (melhor previsão, alvo pior). A manchete do modelo mudou de
"bate a tendência" para "só serve nas quebras": +40% nas safras 20% abaixo da tendência e -61%
em ano normal. Guard de janela incompleta implementado depois de a safrinha 2026 do PR prever
o dobro do plausível.
Três coisas que valem lembrar no próximo modelo: (1) RMSE médio esconde utilidade concentrada
na cauda — sempre cortar por severidade; (2) escolher a tendência pelo melhor baseline não é o
mesmo que escolher pelo melhor sistema, e foi o segundo critério que valeu; (3) o alvo do
modelo e a previsão do nível são objetivos distintos e podem apontar para formas diferentes.

**04/08/2026 — sessão 4 (trabalho)**
App Streamlit construído e rodando local (`app/`), com export dos marts para CSV — o app
publicado não toca o warehouse. Gráficos extraídos para `app/charts.py` justamente para poder
renderizá-los como PNG e **olhar**: foi assim que apareceu um erro de leitura que nenhum teste
pegaria — as barras estavam coloridas por ganho/perda (azul/vermelho) *e* a legenda dizia
"Soybean = azul", então o hue carregava identidade e polaridade ao mesmo tempo. Trocado para
cor por cultura; o sinal já está no lado do zero em que a barra fica.
Verificação no navegador ficou parcial: o painel do preview não estava visível, então não houve
screenshot nem clique nos filtros — conferido por inspeção de DOM (geometria dos 4 gráficos,
zero overflow, rótulos não cortados, sem erro de console) e a lógica dos filtros testada em
Python direto (inclusive safrinha sem RS).

**04/08/2026 — sessão 5 (trabalho)**
CI no GitHub Actions: `ci.yml` (rápido, todo push) e `refresh.yml` (semanal, pipeline inteiro +
BigQuery + commit dos dados do app). Criado o `app/selftest.py`, que o CI usa para construir
todas as figuras a partir dos CSVs — a regressão que ele pega é o export e os gráficos
divergirem, que quebraria o dashboard publicado sem nada mais notar.
**Achado incidental que valia a sessão inteira:** os CSVs do app nunca tinham sido commitados —
`data/` no .gitignore casa com `app/data/` também. O commit anterior levava o app sem os dados.
Testado localmente o que dá para testar sem push (YAML válido nos dois workflows, `dbt parse`
com as env vars falsas do CI, selftest verde); o que só o primeiro run vai provar é o Python
3.14 no runner, os wheels no Linux, o tempo do NASA POWER e a permissão de push do bot.

**Primeiro run do `refresh.yml`, no mesmo dia:** Python 3.14.6 e os wheels no Linux passaram
(install em 1m02s), mas a ingestão estourou os 60 min e foi cancelada — ver a seção do throttling
do POWER acima. Corrigido com download concorrente e `-u`; falta rodar de novo para confirmar.
Duas lições que valem além deste projeto: **estimativa de tempo medida na máquina local não vale
para runner de CI** (IP de datacenter é tratado diferente por APIs públicas), e **todo passo longo
precisa imprimir progresso sem buffer**, senão não há como distinguir lento de travado.

**07/08/2026 — sessão 6 (trabalho)**
Pre-flight da publicação: working tree limpo e sincronizado, repo público, os três CSVs e o
`config.toml` versionados, `app/requirements.txt` com wheel binária para os Pythons que o
Community Cloud oferece (pandas 3.0.5 exige ≥3.11 e tem cp312/cp313 — nada compila lá).
Achados dois problemas que só apareceram por olhar o dado em vez do código: a data da série
climática escrita à mão no app (já errada pelo primeiro refresh automático, corrigida aqui) e o
cache do POWER aceito sem conferir cobertura, que virou tarefa própria e foi consertada no mesmo
dia — as duas seções acima.
Screenshot falhou de novo pelo painel do preview não estar visível; a conferência foi por DOM,
com a frase corrigida lida na página renderizada.

**App publicado no fim da sessão** — semana 5 fechada de verdade. Verificado no ar: gráficos,
métricas, filtros e a data derivada do dado, sem erro de console. CI verde nos três pushes do dia.

Revisão do conserto do cache, feito em sessão paralela: aprovado com dois ajustes. O aviso do
`--allow-stale` dizia que o warehouse terminaria na data da célula mais atrasada, quando a tabela
termina na **mais nova** — a mesma confusão global-vs-célula que tornara o bug original invisível,
e visível só no caso misto (uma célula atrás, as outras em dia). A mensagem parou de citar data.
E o `end_date` sendo `hoje - 7` faz o cache local **expirar todo dia**; ficou declarado no
docstring do módulo em vez de virar surpresa. Lacuna de verificação fechada na revisão: o
`to_parquet` novo só tinha sido testado com 3 células, rodou contra as 255 reais em 17 s
(3.313.980 linhas), contra os 20 s de antes.
