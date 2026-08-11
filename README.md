# carteira-socinvest

Painel estático (GitHub Pages) para acompanhar a rentabilidade da conta
Socinvest N3 (custódia UBS, USD) com preços do Yahoo Finance.

## Como funciona

```
positions.json ─┐
(extrato UBS)   │
                ├─▶ fetch_prices.py ─▶ data/prices.json ─┐
ledger.json ────┘   (Yahoo Finance)    (closes diários)   ├─▶ index.html
(movimentações)                                           │   (dashboard)
                                        ledger.json ──────┘
```

- **positions.json** — posições, quantidades e custo médio extraídos do
  extrato UBS de 10.08.2026 (início da conta: 26.05.2026, USD 1.000.000).
  Inclui os checkpoints oficiais de patrimônio/TWR do extrato.
- **ledger.json** — o extrato de **movimentações** da conta: saldo de caixa por
  data-valor (79 lançamentos desde o início) e as pernas de compra/venda com
  quantidade. É o que permite reconstruir o NAV **dia a dia**.
- **fetch_prices.py** — busca closes diários de todos os símbolos no Yahoo
  (ETFs por ticker, fundos por código `0P…`, posições EUR convertidas por
  `EURUSD=X`), incluindo as posições já encerradas do ledger e o benchmark.
  Só stdlib.
- **update-prices.yml** — GitHub Actions roda o fetch em dias úteis após o
  fechamento dos EUA e commita `data/prices.json`.
- **index.html** — dashboard vanilla JS/SVG: NAV diário vs. capital inicial,
  benchmark e checkpoints UBS, alocação por classe, tabela de posições com P&L.

### A linha do gráfico é NAV de verdade

`NAV(t) = caixa(t) + Σ quantidade_i(t) × preço_i(t)`, com o caixa e as
quantidades vindos do `ledger.json` — a carteira que existia **naquele dia**,
não a de hoje remarcada para trás. Compra e venda não mexem no NAV (só trocam
caixa por papel), então a variação diária é limpa mesmo com trade no meio do
caminho; e como o saldo de caixa é o do extrato, dividendos, juros e taxas
entram na data em que caíram.

Validado contra os quatro checkpoints oficiais do UBS: erro de +0,16% no
primeiro dia (compras liquidando com NAV de fundo defasado) e ≤0,06% nos
outros três.

**Benchmark:** `meta.benchmark` (`{symbol, name}`) no positions.json — hoje AOK
(iShares Core Conservative Allocation, 30/70). O `fetch_prices.py` busca a série
mesmo sem ser posição, em **adjclose** (retorno total, com dividendos), porque o
NAV da conta também inclui proventos. O dashboard parte o ETF do mesmo capital
inicial na mesma data, desenha a linha cinza e mostra o tile "Vs AOK". Trocar o
benchmark = trocar o símbolo e rodar o fetch.

## Rodar local

```bash
python fetch_prices.py
python -m http.server 8123   # abrir http://localhost:8123
```

## Comprar / vender posição

```bash
# compra (resolve o ticker Yahoo pelo ISIN, debita o caixa, atualiza preços):
python adicionar_ativo.py IE000ABC1234 100 25.50 --classe Bonds --push

# reforço de posição existente (agrega e recalcula custo médio): mesmo comando
# venda parcial ou total (credita o caixa):
python adicionar_ativo.py --vender GLD --preco 377.00 --qtd 20 --push
```

`--dry-run` mostra sem gravar; `--moeda EUR` se o preço pago não for USD;
`--simbolo` força o ticker quando a busca por ISIN não achar a linha certa.

Isso mantém a tabela de posições em dia, mas **não** escreve no `ledger.json` —
a série diária só incorpora o trade no próximo import de extrato.

## Atualizar com um novo extrato

Baixar os dois PDFs do UBS Connect (**positions** e **transactions**) e:

1. `positions.json` — quantidades/custos, `cash_usd`, `statement_date`,
   `statement_value` e o checkpoint novo.
2. `ledger.json` — acrescentar os saldos de caixa por data-valor e as pernas de
   trade novas; mover para `closed` a posição que zerou (o fetch precisa da
   série dela para o histórico não ficar furado).

Invariantes que devem valer depois: soma dos lançamentos = saldo impresso, e
quantidades acumuladas do ledger = quantidades do extrato de posições.

## Ressalvas

- NAV de fundos atrasa 1-2 dias úteis (coluna "Priced" mostra a data de cada
  preço; âmbar quando passa de 4 dias).
- `PJAG.SG` (Pictet EM Local Currency) não tem histórico utilizável no Yahoo —
  só cotação corrente. É carregada achatada no último preço conhecido, e o
  rodapé do painel diz isso. É a maior fonte de erro da série diária.
- O caixa fica congelado depois da última data do ledger, até o próximo import.
- Filers em EUR (`BNK.PA`) têm custo em USD histórico, como o UBS reporta —
  não reconvertido pelo câmbio do dia.
- Ferramenta pessoal de acompanhamento; não é aconselhamento de investimento.
