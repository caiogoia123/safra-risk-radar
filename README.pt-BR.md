# Safra Risk Radar

[English](README.md) · **Português**

**[→ Painel publicado](https://safra-risk-radar.streamlit.app)** · reconstruído toda semana pelo
CI, a partir de CONAB, IBGE e NASA POWER, passando por dbt até o BigQuery.

<sub>Hospedado no plano gratuito do Streamlit, que coloca o app para dormir depois de um tempo sem
visitas. Se cair numa tela "Zzzz", o botão dela acorda o app em cerca de meio minuto.</sub>

## O que é

Um pipeline de dados que mede **quanto da variação de produtividade da soja e do milho segunda
safra no Brasil é explicado pelo clima na janela crítica de cada cultura**, e testa se dá para
apontar uma quebra antes de o levantamento oficial fechar.

O Brasil responde por perto de metade das exportações mundiais de soja, e o número oficial de
produtividade sai meses depois do clima que o causou. É nessa lacuna que trading, seguro agrícola e
crédito rural precisam decidir. Aqui o clima é **entrada já medida** — nada sobre o clima futuro
está sendo previsto.

Escala: 3,3 milhões de linhas de clima diário, 510 municípios-polo colapsados em 255 células de
grade, 13 pares cultura × estado, 293 safras avaliadas em backtest walk-forward (2003–2025).

## Principais resultados

Duas convenções para ler as tabelas: o **baseline** é o palpite mais simples possível ("a safra vai
dar o que a tendência do estado diz"), e o **erro** é a distância entre previsão e safra real em
pontos percentuais de produtividade — quanto menor, melhor.

**1. O clima da janela crítica carrega sinal real, porém moderado.** Correlação entre a previsão do
modelo e o resíduo observado: **+0,47** na soja e **+0,29** no milho segunda safra.

**2. Na média, o modelo empata com a tendência.** Ganho de RMSE sobre o baseline: 3,4% na soja e
1,2% no milho segunda safra. Esse 3,4% é o **melhor resultado entre as quatro famílias de modelo
testadas** — outras configurações ficam abaixo do baseline, e a escolha foi feita olhando o mesmo
backtest. Não é uma melhoria geral e definitiva; é ruído do tamanho de um empate.

**3. O ganho está concentrado nas quebras.** As 161 safras de soja avaliadas (7 estados ×
2003–2025), separadas por quão boa ou ruim a safra realmente foi:

| Como a safra fechou (contra a tendência) | Safras | Erro do baseline | Erro do modelo | Mudança |
|---|---|---|---|---|
| Quebra forte: abaixo de -20% | 14 | 34,4 | 20,6 | **-40% de erro** |
| Quebra moderada: -20% a -10% | 15 | 15,7 | 10,8 | **-31% de erro** |
| Safra normal: ±10% | 89 | 5,9 | 9,6 | +61% de erro |
| Safra boa: +10% a +20% | 31 | 14,8 | 18,3 | +24% de erro |
| Safra muito boa: acima de +20% | 12 | 33,5 | 34,8 | +4% de erro |

Nas safras normais — 89 das 161, e a maior parte da amostra — a tendência sozinha já é a resposta
certa, e o modelo só atrapalha. É isso que dilui o ganho médio do item 2.

Ressalva honesta: esse formato **não é exclusivo deste modelo**. Qualquer preditor com correlação
positiva e amplitude menor que a do dado real ganha do baseline nas caudas e perde no meio, por
construção. A tabela mostra onde o sinal é aproveitável, não uma propriedade especial do modelo.

**4. Como detector de quebra, ele bate o acaso.** Contando como quebra toda safra que fechou 10% ou
mais abaixo da tendência:

| Cultura | Quebras reais | Alarmes disparados | Alarmes certos | Recall | Precisão |
|---|---|---|---|---|---|
| Soja | 29 | 28 | 13 | 45% | 46% |
| Milho segunda safra | 38 | 34 | 19 | 50% | 56% |

Precisão só significa alguma coisa contra a taxa base: quebras são 18% das safras de soja e 29% das
de safrinha, então 46% e 56% representam ganho de 2,6× e 1,9× sobre o acaso. O baseline dispara
**zero** alarmes por construção — uma reta de tendência nunca prevê ano ruim. Com 29 e 38 eventos,
porém, as taxas são imprecisas: o intervalo de 95% do recall da soja vai de aproximadamente 25% a
70% (bootstrap em blocos por ano).

**5. Mas o modelo quase não ganha de uma regra de uma variável só.** Ordenando as safras pelo
z-score de uma única variável climática, com o mesmo número de alarmes que o modelo dispara:

| Cultura | Alarmes | Modelo | Regra: dias secos | Regra: chuva |
|---|---|---|---|---|
| Soja | 28 | 13 acertos | 13 acertos | 11 acertos |
| Milho segunda safra | 34 | 19 acertos | 19 acertos | **21 acertos** |

A única vantagem clara do modelo aparece nas **quebras severas de soja** (≤ -20%), onde ele pega 10
de 14 contra 8 da regra de dias secos e 6 da de chuva. Na safrinha ele não tem vantagem nenhuma: a
chuva sozinha detecta mais quebras que o modelo inteiro.

**Leitura final.** Este não é um modelo de previsão de safra preciso, e não deve ser apresentado
como tal. É um **detector de risco** com sinal climático real, útil na cauda de quebras severas da
soja, e cuja vantagem sobre uma regra simples é pequena ou inexistente no resto.

## O que foi analisado

**O alvo é o resíduo contra a tendência, não a produtividade.** A produtividade sobe ao longo das
décadas porque semente, maquinário e manejo melhoram; um modelo treinado no nível redescobre essa
tendência, reporta um erro lisonjeiro e não prevê nada. Doze métodos de detrend foram comparados
por erro fora da amostra, e dois resultados sobreviveram:

- **Tendência não-linear não conserta a safrinha**, mesmo com a cultura tendo saído de 1.796 para
  5.198 kg/ha. `log_linear` é a *pior* das doze (RMSE 39,4 contra 31,5 da reta): em escala
  logarítmica a expansão inicial extrapola para o absurdo.
- **A média móvel de 3 anos é a melhor previsão (RMSE 28,3) e o pior alvo.** Ela já absorveu o
  clima recente, então o resíduo contra ela carrega reversão à média em vez de clima, e todo modelo
  treinado nesse alvo saiu ~50% pior que o próprio baseline. Escolher a tendência pelo melhor
  baseline não é o mesmo que escolher pelo melhor sistema ponta a ponta.

**O veranico não é a variável forte que se esperava.** O período seco dentro da janela crítica —
maior sequência de dias secos consecutivos, calculada por gaps-and-islands sobre a série diária —
correlaciona *pior* com o resíduo de produtividade do que uma contagem simples de dias secos
(-0,26 contra -0,39 na soja). Limiares de 1, 2 e 5 mm foram testados; a definição não é o problema.
Foi rebaixado de variável do modelo a coluna descritiva. Medir o período seco *inteiro* que apenas
encosta na janela também foi tentado e rejeitado: na Bahia a janela fecha em abril, quando começa a
estação seca, então a métrica capturava a estação seca e não um evento de seca.

**O clima acompanha a produtividade na direção que a agronomia prevê.** Contra o normal de
1992–2020 de cada estado, ao longo de 1992–2025:

| Cultura | Anomalia de dias secos | Anomalia de chuva | Anomalia de temperatura |
|---|---|---|---|
| Soja | **-0,39** | +0,29 | -0,29 |
| Milho segunda safra | -0,26 | +0,21 | -0,18 |

**A exposição climática é muito desigual entre os estados**, e essa é a descoberta mais útil do
projeto — correlação do resíduo de produtividade da soja contra a anomalia climática:

| Estado | Chuva | Dias secos |
|---|---|---|
| Rio Grande do Sul | **+0,50** | **-0,56** |
| Mato Grosso do Sul | +0,39 | -0,51 |
| Minas Gerais | +0,35 | -0,25 |
| Paraná | +0,24 | -0,31 |
| Bahia | +0,22 | -0,51 |
| Goiás | +0,15 | -0,24 |
| Mato Grosso | +0,13 | -0,40 |

O Rio Grande do Sul é cerca de quatro vezes mais sensível à chuva que o Mato Grosso. Uma média
nacional apaga isso: a seca que mal arranha o Mato Grosso é a que quebra a safra no Sul.

Como validação de sanidade, duas quebras que o pipeline encontrou sozinho são eventos
reconhecíveis: a pior safra de soja da série é o Rio Grande do Sul em 2005, com **-67% ante a
tendência** e 17 dias secos a mais (a seca de 2004/05); e o milho segunda safra do Paraná em 2021
fechou em **-51%** com chuva a **-2,06 desvios padrão**.

## Arquitetura e ferramentas

```
Série de grãos CONAB ─┐
PAM municipal IBGE   ─┼─→ ingestão (Python) ─→ Parquet ─→ dbt ─→ marts
NASA POWER diário    ─┘                                     │
                                                            │
                                          ┌─────────────────┴────────────────┐
                                          ▼                                  ▼
                                   modelo de produtividade            app Streamlit
                                   (backtest walk-forward)            (painel público)
```

| Etapa | Onde roda | Ferramenta e papel |
|---|---|---|
| Extração e carga | local **ou** GitHub Actions | Python + `requests`; arquivos crus guardados na íntegra |
| Transformação | local **ou** GitHub Actions | dbt Core: staging → intermediate → marts, 78 testes |
| Warehouse de dev | **local** (arquivo) | DuckDB — roda sem servidor e sem credencial |
| Warehouse de prod | **cloud** | BigQuery (sandbox) |
| Backtest e export | local **ou** GitHub Actions | pandas + scikit-learn |
| Painel | **cloud** | Streamlit Community Cloud |
| Automação | **cloud** | GitHub Actions |

O mesmo projeto dbt aponta para os dois warehouses, então o SQL fica perto do ANSI. Essa
portabilidade é garantida rodando de verdade nos dois: `dbt compile` resolve o Jinja, mas só a
execução recusa um tipo ou uma função que um motor tem e o outro não.

**Por que dado municipal se a tabela fato é por estado:** o centroide de um estado não é onde está
a lavoura — o do Mato Grosso cai na floresta, o da Bahia em caatinga sem irrigação. A produção
municipal do PAM localiza o cinturão produtor real (os municípios que somam 80% da produção de cada
estado, 510 deles), e é ali que o clima é amostrado e ponderado. Esses 510 polos colapsam em 255
células distintas do NASA POWER, e a razão varia muito por estado: 3,3 polos por célula no Paraná
contra 1,0 na Bahia. Somar chuva depois desse join triplicaria o total do Paraná e deixaria o da
Bahia intacto — um erro silencioso e enviesado por região. Todo agregado climático deduplica por
célula antes de somar.

**Atualização automática.** Toda segunda, 06:00 UTC, o GitHub Actions refaz a ingestão, roda
`dbt build` nos dois targets, reexporta os CSVs do painel e commita se o dado mudou. São dois
objetivos no mesmo job: manter o painel atual (a CONAB revisa o levantamento todo mês) e manter as
tabelas do sandbox do BigQuery vivas, já que elas expiram em 60 dias e todo build reseta o relógio.
Um CI separado roda a cada push, mais leve: `dbt parse`, renderização de todas as figuras do painel
e conferência dos números deste README contra os CSVs exportados.

## Modelo e validação

Regressão **Ridge** sobre quatro variáveis agronômicas nomeadas — dias secos na janela, chuva,
temperatura média e graus-dia — cada uma medida como distância do normal daquele estado. Não são
200 colunas anônimas. Na soja o modelo usa interações por estado (uma inclinação por UF, α=10),
justificado pela exposição desigual da tabela acima; na safrinha, com menos safras por estado, a
versão agrupada (α=1) é a mais estável.

Detalhes que sustentam o resultado:

1. **Janelas fenológicas, não anos-calendário.** Os meses de plantio e colheita vêm do calendário
   oficial da CONAB, extraídos das barras coloridas do PDF em vez de digitados à mão. A janela
   crítica vai do último mês de plantio até um mês antes do fim da colheita.
2. **Anomalias contra o normal do próprio estado.** 100 mm de chuva em maio é banal no Rio Grande
   do Sul e sinal de seca no Mato Grosso.
3. **Validação walk-forward.** Tendência, normais climáticas e modelo são reajustados a cada safra
   usando só os anos anteriores; nada da safra *T* existe quando *T* é prevista. As anomalias já
   publicadas no mart são deliberadamente ignoradas aqui: elas usam um normal fixo de 1992–2020,
   que num backtest de 2005 injetaria quinze anos de futuro.
4. **O baseline é reportado ao lado** e teria sido publicado se tivesse vencido.

## Dashboard

O app publicado tem três páginas: a série de produtividade por cultura e estado com os alarmes do
modelo marcados, o painel de anomalias climáticas da janela crítica, e a previsão da safra aberta.
Ele lê os CSVs exportados em vez de consultar o warehouse, então não custa nada para servir e não
quebra se as tabelas do sandbox do BigQuery expirarem. Esses exports são reprodutíveis byte a byte:
reconstruir o warehouse do zero em outra máquina e reexportar produz arquivos idênticos, o que faz
o commit semanal tocar só nas linhas que realmente mudaram.

## Reprodução

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
python -m ingestion              # baixa as fontes e carrega no DuckDB
cd dbt
dbt build                        # target DuckDB por padrão
```

Não precisa de credencial nenhuma: o alvo padrão é o DuckDB local, um arquivo de cerca de 170 MB em
`data/`, que está no gitignore e é reconstruído pela ingestão. O calendário da CONAB, a tabela do
PAM municipal e os centroides dos polos são versionados em vez de baixados de novo — são derivados
uma vez da fonte oficial e regerados de propósito, o que também mantém as duas APIs do IBGE (que
recusam IP de datacenter) fora do caminho crítico do CI.

Para rodar contra o BigQuery, defina `GCP_KEYFILE` e `GCP_PROJECT` (veja `.env.example`), depois
`python -m ingestion --target prod` e `dbt build --target prod`. Os comandos dbt rodam de dentro de
`dbt/`, já que o caminho do DuckDB é relativo ao diretório de trabalho.

Para refazer a análise: `python -m analysis.backtest` roda o walk-forward completo e
`python -m analysis.export_app_data` regenera os CSVs do painel.

## Limitações

- **A escolha de modelo e de tendência foi feita no mesmo backtest que reporta o resultado**, sem
  hold-out final. Os números acima são otimistas por uma margem desconhecida.
- **A amostra é pequena para as taxas publicadas** — 29 e 38 eventos de quebra. Os intervalos de
  confiança são largos e as porcentagens não devem ser lidas como precisas.
- **O modelo só é útil nas quebras.** Em ano normal ele é pior do que supor a tendência. Deve ser
  lido como alarme, não como número de produtividade.
- **As previsões são encolhidas** — a amplitude prevista é cerca de metade da real na soja e um
  terço na safrinha, então o modelo raramente crava a magnitude de uma quebra grande.
- **O Rio Grande do Sul fica fora do milho segunda safra**: a CONAB não publica calendário de
  safrinha para o estado porque ele não tem segunda safra relevante. É um corte deliberado.
- **A safra corrente é estimativa de levantamento, não colheita realizada**, e é mantida fora da
  verdade de treino. Safra em andamento não é prevista: janelas parciais são recusadas em vez de
  extrapoladas, porque medir clima incompleto contra um normal de janela cheia produz anomalia
  falsa — o que já transformou uma previsão do Paraná em +99%.
- **Produtividade estadual esconde variação dentro do estado.** A amostragem climática ponderada
  por produção reduz isso, mas não elimina.

## Licença

MIT
