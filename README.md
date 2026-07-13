# carteira-socinvest

Painel estático (GitHub Pages) para acompanhar a rentabilidade da conta
Socinvest N3 (custódia UBS, USD) com preços do Yahoo Finance.

## Como funciona

```
positions.json  ──▶  fetch_prices.py  ──▶  data/prices.json  ──▶  index.html
(extrato UBS)        (Yahoo Finance)       (closes diários)       (dashboard)
```

- **positions.json** — posições, quantidades e custo médio extraídos do
  extrato UBS de 09.07.2026 (início da conta: 26.05.2026, USD 1.000.000).
  Inclui os checkpoints oficiais de patrimônio/TWR do extrato.
- **fetch_prices.py** — busca closes diários de todos os símbolos no Yahoo
  (ETFs por ticker, fundos por código `0P…`, posições EUR convertidas por
  `EURUSD=X`). Só stdlib.
- **update-prices.yml** — GitHub Actions roda o fetch em dias úteis após o
  fechamento dos EUA e commita `data/prices.json`.
- **index.html** — dashboard vanilla JS/SVG: valor da carteira vs. capital
  inicial e checkpoints UBS, alocação por classe, tabela de posições com P&L.

## Rodar local

```bash
python fetch_prices.py
python -m http.server 8123   # abrir http://localhost:8123
```

## Atualizar com um novo extrato

Editar `positions.json`: quantidades/custos das posições, `cash_usd`,
`statement_date`/`statement_value` e acrescentar o checkpoint novo.

## Ressalvas

- NAV de fundos atrasa 1-2 dias úteis (marcado com ● na tabela).
- Caixa fica constante entre extratos — dividendos e custos só entram
  quando o extrato novo é importado.
- Ferramenta pessoal de acompanhamento; não é aconselhamento de investimento.
