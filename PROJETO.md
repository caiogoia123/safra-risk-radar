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
| IBGE SIDRA 1612 (PAM) | produção **municipal** anual, 1974→2024 | API JSON | validada (metadados + amostra) |
| NASA POWER daily | T2M, T2M_MAX, T2M_MIN, precipitação, radiação por ponto | API JSON | validada (amostra) |

**Por que o PAM entra se a fato é estadual:** o clima do centroide da UF não representa a área
agrícola (o centroide do MT cai em floresta; o da BA, na caatinga não irrigada). O PAM municipal
serve para achar onde a produção realmente está e ponderar o clima por produção.

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
4. **Features com sentido agronômico:** dias secos consecutivos na janela crítica, graus-dia,
   noites quentes, déficit hídrico acumulado. Não jogar 200 features num XGBoost.
5. **Validação temporal honesta:** treina até a safra `t`, testa em `t+1`. Nada de embaralhar.
   Baseline explícito (previsão = tendência) — se o modelo não bater a tendência, o projeto
   **relata isso**, não esconde. Esse é o padrão do `alpha-validation-lab`.

## 7. Cronograma (~10h/semana, 4–6 semanas)

| Semana | Entrega | Feito? |
|---|---|---|
| 1 | Repo, ingestão CONAB + PAM + POWER, camada raw | parcial — CONAB pronta, PAM e POWER faltando |
| 2 | dbt staging + intermediate (normais climatológicas, janelas) | parcial — projeto dbt de pé, `stg_conab_grain` rodando |
| 3 | Marts + testes dbt + análise exploratória (achar o insight) | |
| 4 | Modelo, backtest temporal, comparação com baseline | |
| 5 | Streamlit publicado + GitHub Actions agendado + target BigQuery | |
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

## 9. Estado atual (04/08/2026)

**Funcionando de ponta a ponta, nos dois targets:**
- `.venv` com dbt-core 1.12.0 + dbt-duckdb 1.10.1 + dbt-bigquery 1.12.0 no Python 3.14.5
- `ingestion/conab.py` → Parquet → `ingestion/warehouse.py` → DuckDB **e** BigQuery
- `dbt build` verde nos dois: 1 modelo (`stg_conab_grain`, 11.000 linhas) e 5 testes
- BigQuery consumiu 1,7 MiB da cota mensal de 1 TB

**Ainda não existe:** ingestão PAM e POWER, camadas intermediate e marts, modelo, app, CI.

**Próximo passo concreto:** `ingestion/ibge_pam.py` — produção municipal de soja e milho para
achar os polos produtores de cada UF, que definem os pontos de consulta do NASA POWER.

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

## 10. Log de sessões

**04/08/2026 — sessão 1 (trabalho)**
Escolhido o projeto entre 4 alternativas. Ambiente validado (Python 3.14, git, rede liberada
para IBGE/CONAB/NASA/PyPI/GitHub). Maior risco técnico afastado: dbt instala no Python 3.14.
Três fontes sondadas com dado real. Escopo fechado e ingestão da CONAB entregue.
Repo publicado em github.com/caiogoia123/safra-risk-radar.
Conta GCP criada (sandbox) e **fatia vertical fechada**: CONAB → Parquet → DuckDB + BigQuery →
`dbt build` verde nos dois targets, com 5 testes passando.
Sondagem do PAM municipal deu certo (1.996 linhas para o PR em 5,5s) e o NASA POWER é barato
(2s por ponto, ~4 min para 100 pontos). **Pendência aberta: a API de malhas do IBGE não devolveu
o GeoJSON no formato esperado** — falta achar outra fonte para os centroides dos municípios.
