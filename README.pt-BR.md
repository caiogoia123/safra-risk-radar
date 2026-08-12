# Safra Risk Radar

[English](README.md) · **Português**

**[→ Painel publicado](https://safra-risk-radar.streamlit.app)** · reconstruído toda semana pelo
CI, a partir de CONAB, IBGE e NASA POWER, passando por dbt até o BigQuery.

<sub>Hospedado no plano gratuito do Streamlit, que coloca o app para dormir depois de um tempo sem
visitas. Se cair numa tela "Zzzz", o botão dela acorda o app em cerca de meio minuto.</sub>

**Quanto da variação de produtividade da soja e do milho segunda safra no Brasil é explicado pelo
clima na janela crítica de cada cultura — e dá para apontar uma quebra antes de o levantamento
oficial fechar?**

O Brasil responde por perto de metade das exportações mundiais de soja. Uma safrinha ruim em Mato
Grosso mexe no preço global de ração. Só que o número oficial de produtividade sai meses depois do
clima que o causou, e é nessa lacuna que trading, seguro agrícola e crédito rural precisam decidir.
Aqui o clima é a **entrada**, já medida — nada sobre o clima futuro está sendo previsto.

---

## O achado: isto não é um previsor de safra

Na média de todas as safras, o modelo praticamente empata com o baseline ingênuo de
"produtividade = tendência" — 3,4% melhor na soja, 1,2% no milho segunda safra. Publicado só por
esse número, a conclusão honesta seria "não bate a tendência".

**A média esconde o resultado.** Separando por quão ruim a safra realmente foi (soja, walk-forward
2003–2025, RMSE do resíduo de produtividade em pontos percentuais):

| Desvio real | n | Baseline | Modelo | Mudança |
|---|---|---|---|---|
| Quebra < -20% | 14 | 34,4 | 20,6 | **-40% de erro** |
| -20% a -10% | 15 | 15,7 | 10,8 | **-31% de erro** |
| Normal ±10% | 89 | 5,9 | 9,6 | +61% de erro |
| Boa > +20% | 12 | 33,5 | 34,8 | +4% de erro |

O modelo se paga só quando a safra quebra, e atrapalha de verdade em ano normal — e os anos normais
são 48% da amostra, que é exatamente o que dilui a métrica global. O milho segunda safra repete o
padrão, mais fraco: -27% de erro nas quebras, +68% em anos normais.

Lido como detector em vez de previsor, sobre as safras que fecharam 10% ou mais abaixo da
tendência:

| Cultura | Eventos reais | Sinalizados | Corretos | Recall | Precisão | Sinais do baseline |
|---|---|---|---|---|---|---|
| Soja | 29 | 28 | 13 | 45% | 46% | **0** |
| Milho segunda safra | 38 | 34 | 19 | 50% | 56% | **0** |

O baseline detecta zero quebras por construção — uma reta de tendência nunca prevê um ano ruim.
Então o enquadramento honesto é: **um detector de quebra que pega cerca de metade delas com cerca
de metade de alarme falso, contra um baseline que nunca avisa.** Para uma mesa de trading ou de
crédito, metade das quebras apontada cedo vale mais do que 3% de RMSE.

## Por que o alvo é um resíduo, e não a produtividade

A produtividade sobe ao longo das décadas porque semente, maquinário e manejo melhoram. Um modelo
treinado no nível redescobre principalmente essa tendência, reporta um erro lisonjeiro e não prevê
nada. O alvo aqui é o **resíduo contra a tendência de produtividade do próprio estado** — a parte
da safra que a tecnologia não explica.

Escolher essa tendência já foi um resultado. Doze métodos de detrend foram comparados por erro
fora da amostra:

- **Tendência não-linear não conserta a safrinha**, mesmo com a cultura tendo saído de 1.796 para
  5.198 kg/ha enquanto passava de marginal a dominante. `log_linear` é a *pior* das doze (RMSE 39,4
  contra 31,5 da reta): em escala logarítmica a expansão inicial extrapola para o absurdo.
  Quadrática e Theil-Sen também perdem para a reta.
- **O que vence é não extrapolar** — média móvel de 3 anos, RMSE 28,3.
- **E mesmo assim a reta ficou.** A média móvel é a melhor *previsão* e o pior *alvo*: ela já
  absorveu o clima recente, então o resíduo contra ela carrega reversão à média em vez de clima, e
  todo modelo treinado nesse alvo saiu ~50% pior que o próprio baseline. Escolher a tendência pelo
  melhor baseline não é o mesmo que escolher pelo melhor sistema ponta a ponta, e só o segundo
  importa.

## O que não funcionou

- **O *veranico* não é a variável forte que se esperava.** O período seco dentro da janela crítica
  — maior sequência de dias secos consecutivos, calculada por gaps-and-islands sobre a série
  diária — correlaciona *pior* com o resíduo de produtividade do que uma contagem simples de dias
  secos (-0,26 contra -0,39 na soja). Limiares de 1, 2 e 5 mm foram testados; a definição não é o
  problema. Foi rebaixado de variável do modelo a coluna descritiva.
- Medir o período seco *inteiro* que apenas encosta na janela foi tentado e rejeitado: na Bahia a
  janela fecha em abril, bem quando começam os cinco meses de estação seca, então a métrica
  capturava a estação seca e não um evento de seca.

## O que o dado mostra

O clima na janela crítica acompanha a produtividade na direção que a agronomia prevê. Contra o
normal de 1992–2020 de cada estado, ao longo de 1992–2025:

| Cultura | Anomalia de dias secos | Anomalia de chuva | Anomalia de temperatura |
|---|---|---|---|
| Soja | **-0,39** | +0,29 | -0,29 |
| Milho segunda safra | -0,26 | +0,21 | -0,18 |

**A exposição climática é muito desigual entre os estados** — correlação do resíduo de
produtividade da soja contra a anomalia climática:

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
nacional apaga isso por completo: a seca que mal arranha o Mato Grosso é a que quebra a safra no
Sul. Quem precifica risco agrícola por um número de país inteiro está errando o preço nos dois
estados.

Duas quebras que o pipeline encontrou sozinho são eventos reconhecíveis. A pior safra de soja da
série é o Rio Grande do Sul em 2005, com **-67% ante a tendência** e 17 dias secos a mais — a seca
de 2004/05. O milho segunda safra do Paraná em 2021 fechou em **-51%** com chuva a **-2,06 desvios
padrão**, a quebra da safrinha de 2021.

## Arquitetura

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

| Camada | Tecnologia | Por quê |
|---|---|---|
| Extração e carga | Python, `requests`, DuckDB | arquivos crus guardados na íntegra, para reprodutibilidade |
| Transformação | dbt Core | staging → intermediate → marts, 78 testes nos dois targets |
| Data warehouse | DuckDB (dev) / BigQuery (prod) | mesmo projeto dbt, dois targets |
| Orquestração | GitHub Actions | refresh semanal nos dois targets, mais CI a cada push |
| App | Streamlit | painel publicado, sem precisar de toolchain Node |

O mesmo projeto dbt aponta para os dois warehouses, então o SQL fica perto do ANSI. Essa
portabilidade é garantida rodando de verdade: `dbt compile` resolve o Jinja, mas só a execução
recusa um tipo, uma função ou uma cláusula que um motor tem e o outro não.

O app publicado lê CSVs exportados em vez de consultar o warehouse, então o painel não custa nada
para servir e não quebra se as tabelas do sandbox do BigQuery expirarem. Esses exports são
reprodutíveis byte a byte — reconstruir o warehouse do zero em outra máquina e reexportar produz
arquivos idênticos, que é o que faz o commit semanal tocar só nas linhas que realmente mudaram.

## Fontes de dados

| Fonte | Grão | Cobertura |
|---|---|---|
| Série de grãos da [CONAB](https://portaldeinformacoes.conab.gov.br) | estado × cultura × safra | 1976/77 → 2025/26 |
| [IBGE SIDRA 1612](https://sidra.ibge.gov.br/tabela/1612) (PAM) | município × cultura × ano | 1974 → 2024 |
| [NASA POWER](https://power.larc.nasa.gov) diário | ponto de grade de 0,5° | 1981 → hoje, ingerido a partir de 1991 |

**Por que dado municipal se a tabela fato é por estado:** o centroide de um estado não é onde está
a lavoura. O centroide do Mato Grosso cai na floresta; o da Bahia, em caatinga sem irrigação. A
produção municipal do PAM localiza o cinturão produtor de verdade — os municípios que somam 80% da
produção de grãos de cada estado, 510 deles — e é ali que o clima é amostrado e ponderado.

Esses 510 polos colapsam em 255 células distintas do NASA POWER, e a razão muitos-para-um varia
muito por estado: 3,3 polos por célula no Paraná contra 1,0 na Bahia. Somar chuva depois desse join
triplicaria o total do Paraná e deixaria o da Bahia intacto — um erro silencioso e enviesado por
região. Todo agregado climático deduplica por célula antes de somar.

## Método

1. **Detrend** da produtividade por estado e cultura, para que o alvo seja o resíduo, não o nível.
2. **Janelas fenológicas, não anos-calendário.** Os meses de plantio e colheita vêm do calendário
   oficial da CONAB, extraídos das barras coloridas do PDF em vez de digitados à mão. A janela
   crítica é derivada dele: do último mês de plantio até um mês antes do fim da colheita.
3. **Anomalias contra o normal do próprio estado.** 100 mm de chuva em maio é banal no Rio Grande
   do Sul e sinal de seca no Mato Grosso.
4. **Variáveis agronômicas nomeadas** — dias secos na janela, chuva, temperatura e graus-dia, cada
   uma medida contra o normal daquele estado. Não são 200 colunas anônimas.
5. **Validação walk-forward.** Tendência, normais climáticas e modelo são reajustados a cada safra
   usando só os anos anteriores; nada da safra *T* existe quando *T* é prevista. O baseline
   ("produtividade = tendência") é reportado ao lado, e teria sido publicado se tivesse vencido.

## Escopo e limitações

- **O Rio Grande do Sul fica fora do milho segunda safra** — a CONAB não publica calendário de
  safrinha para o estado porque ele não tem segunda safra relevante. É um corte deliberado, não uma
  lacuna.
- **A safra corrente é estimativa de levantamento, não colheita realizada**, e o arquivo da CONAB
  não traz a data do levantamento. Ela é tratada como alvo de previsão e mantida fora da verdade de
  treino.
- **O modelo só é útil nas quebras.** Em ano normal ele é pior do que supor a tendência. Deve ser
  lido como alarme, não como número de produtividade.
- **Produtividade estadual esconde variação dentro do estado.** A amostragem climática ponderada
  por produção reduz isso, mas não elimina.
- **Safra em andamento não é prevista.** Janelas parciais são recusadas em vez de extrapoladas:
  medir clima incompleto contra um normal de janela cheia produz anomalia falsa, o que já
  transformou uma previsão do Paraná em +99%.
- A produtividade na fonte vem arredondada a uma casa em t/ha, e é recalculada a partir de produção
  e área para preservar a precisão que a análise de resíduo exige.

## Reproduzindo

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
python -m ingestion              # baixa as fontes e carrega no DuckDB
cd dbt
dbt build                        # target DuckDB por padrão
```

`data/` está no gitignore — a etapa de ingestão reconstrói a pasta a partir das fontes públicas. O
calendário da CONAB, a tabela do PAM municipal e os centroides dos polos são versionados em vez de
baixados de novo: são derivados uma vez da fonte oficial e regerados de propósito, o que também
mantém as duas APIs do IBGE (que recusam IP de datacenter) fora do caminho crítico do CI.

Para rodar contra o BigQuery, defina `GCP_KEYFILE` e `GCP_PROJECT` (veja `.env.example`), depois
`python -m ingestion --target prod` e `dbt build --target prod`. Os comandos dbt rodam de dentro de
`dbt/`, já que o caminho do DuckDB é relativo ao diretório de trabalho.

## Diário de engenharia

`docs/PROJETO.md` é o diário mantido durante todo o projeto: as decisões, as medições que as
resolveram e os becos sem saída. Foi escrito para mim, não para um leitor — mas é onde qualquer
afirmação acima foi discutida por inteiro.

## Licença

MIT
