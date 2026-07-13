"""Adiciona, reforça ou vende uma posição no positions.json e atualiza os preços.

Comprar (ou reforçar posição existente — agrega e recalcula custo médio):
  python adicionar_ativo.py IE000ABC1234 100 25.50 --classe Bonds [--nome "Fundo X"]
  # QTD e PRECO em USD por cota. Se pagou em outra moeda, use --moeda EUR
  # (converte pelo câmbio corrente do Yahoo — confira o custo no final).

Vender (total ou parcial):
  python adicionar_ativo.py --vender IE000ABC1234 --preco 26.10 [--qtd 50]

Opções: --dry-run (só mostra, não grava) · --sem-precos (não roda fetch_prices.py)
        --push (git add/commit/push ao final)

O caixa (cash_usd) é ajustado automaticamente: compra debita, venda credita.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSITIONS = os.path.join(BASE_DIR, "positions.json")
SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search?q={q}&quotesCount=6"
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=1d"
HEADERS = {"User-Agent": "Mozilla/5.0 (carteira-socinvest)"}
CLASSES = ("Bonds", "Equities", "Gold")


def _get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def quote_meta(symbol):
    try:
        return _get(CHART_URL.format(sym=urllib.parse.quote(symbol)))["chart"]["result"][0]["meta"]
    except Exception:
        return None


def resolver_simbolo(isin):
    """ISIN -> (symbol, currency, nome) preferindo a linha que cota em USD."""
    d = _get(SEARCH_URL.format(q=urllib.parse.quote(isin)))
    quotes = d.get("quotes") or []
    if not quotes:
        sys.exit(f"Yahoo não encontrou nada para {isin!r}. Confira o ISIN "
                 "ou informe o símbolo direto com --simbolo.")
    melhores = []
    for q in quotes[:6]:
        sym = q.get("symbol", "")
        meta = quote_meta(sym)
        ccy = (meta or {}).get("currency")
        score = 0
        if ccy == "USD":
            score += 4
        elif ccy in ("EUR", "GBP"):
            score += 1
        if not sym.upper().startswith(isin.upper()):
            score += 2        # evita listagens genéricas tipo "ISIN.SG"
        if meta and meta.get("regularMarketPrice") is not None:
            score += 1
        melhores.append((score, sym, ccy, q.get("shortname") or q.get("longname") or ""))
    melhores.sort(reverse=True)
    _, sym, ccy, nome = melhores[0]
    if ccy is None:
        sys.exit(f"Símbolo {sym} não tem cotação utilizável no Yahoo.")
    return sym, ccy, nome


def fx_para_usd(moeda):
    if moeda == "USD":
        return 1.0
    meta = quote_meta(f"{moeda}USD=X")
    if not meta or meta.get("regularMarketPrice") is None:
        sys.exit(f"Sem câmbio {moeda}USD=X no Yahoo — informe o custo já em USD.")
    return float(meta["regularMarketPrice"])


def achar(book, chave):
    chave = chave.upper()
    for p in book["positions"]:
        if p["isin"].upper() == chave or p["symbol"].upper() == chave:
            return p
    return None


def salvar(book):
    with open(POSITIONS, "w", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False, indent=2)
        f.write("\n")


def comprar(book, args):
    fx = fx_para_usd(args.moeda)
    custo_usd = round(args.preco * fx, 6)
    existente = achar(book, args.isin)
    if existente:
        q0, c0 = existente["qty"], existente["cost_usd"]
        q1 = q0 + args.qtd
        existente["cost_usd"] = round((q0 * c0 + args.qtd * custo_usd) / q1, 6)
        existente["qty"] = q1
        alvo = existente
        acao = f"reforço: {q0} -> {q1} @ custo médio {alvo['cost_usd']}"
    else:
        if args.simbolo:
            sym = args.simbolo
            meta = quote_meta(sym) or sys.exit(f"Símbolo {sym} sem cotação no Yahoo.")
            ccy, nome_y = meta["currency"], ""
        else:
            sym, ccy, nome_y = resolver_simbolo(args.isin)
        alvo = {
            "name": args.nome or nome_y or args.isin,
            "isin": args.isin.upper(),
            "symbol": sym,
            "class": args.classe,
            "qty": args.qtd,
            "cost_usd": custo_usd,
            "price_ccy": "GBP" if ccy == "GBp" else ccy,
            "stmt_price": custo_usd,
            "stmt_value": round(args.qtd * custo_usd),
        }
        book["positions"].append(alvo)
        acao = f"nova posição via {sym} ({ccy})"
    book["meta"]["cash_usd"] = round(book["meta"]["cash_usd"] - args.qtd * custo_usd, 2)
    return alvo, acao, -args.qtd * custo_usd


def vender(book, args):
    alvo = achar(book, args.vender)
    if not alvo:
        sys.exit(f"Posição {args.vender!r} não encontrada no positions.json.")
    if args.preco is None:
        sys.exit("Venda exige --preco (preço de venda em USD por cota).")
    qtd = args.qtd if args.qtd else alvo["qty"]
    if qtd > alvo["qty"]:
        sys.exit(f"Só há {alvo['qty']} cotas de {alvo['symbol']}.")
    alvo["qty"] = round(alvo["qty"] - qtd, 6)
    acao = f"venda de {qtd} @ {args.preco}"
    if alvo["qty"] == 0:
        book["positions"].remove(alvo)
        acao += " (posição encerrada)"
    book["meta"]["cash_usd"] = round(book["meta"]["cash_usd"] + qtd * args.preco, 2)
    return alvo, acao, qtd * args.preco


def main():
    ap = argparse.ArgumentParser(description="Compra/venda de posição no positions.json")
    ap.add_argument("isin", nargs="?", help="ISIN do ativo (compra)")
    ap.add_argument("qtd_pos", nargs="?", type=float, help="quantidade (compra)")
    ap.add_argument("preco_pos", nargs="?", type=float, help="preço pago por cota (compra)")
    ap.add_argument("--vender", metavar="ISIN_OU_SIMBOLO")
    ap.add_argument("--qtd", type=float, help="quantidade (venda parcial ou compra)")
    ap.add_argument("--preco", type=float, help="preço por cota (venda, USD)")
    ap.add_argument("--classe", choices=CLASSES, default="Equities")
    ap.add_argument("--nome", help="nome de exibição (senão usa o do Yahoo)")
    ap.add_argument("--simbolo", help="força o símbolo Yahoo (pula a busca por ISIN)")
    ap.add_argument("--moeda", default="USD", help="moeda do preço pago (default USD)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sem-precos", action="store_true", help="não roda fetch_prices.py")
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args()

    with open(POSITIONS, encoding="utf-8") as f:
        book = json.load(f)

    if args.vender:
        alvo, acao, fluxo = vender(book, args)
    else:
        if not (args.isin and args.qtd_pos and args.preco_pos):
            ap.error("compra exige: ISIN QTD PRECO (ou use --vender)")
        args.qtd, args.preco = args.qtd_pos, args.preco_pos
        alvo, acao, fluxo = comprar(book, args)

    print(f"{alvo['name']} [{alvo.get('symbol', '?')}] — {acao}")
    print(f"caixa: {fluxo:+,.2f} USD -> cash_usd = {book['meta']['cash_usd']:,.2f}")
    if args.dry_run:
        print("(dry-run: nada gravado)")
        return
    salvar(book)
    print(f"gravado {POSITIONS}")

    if not args.sem_precos:
        subprocess.run([sys.executable, os.path.join(BASE_DIR, "fetch_prices.py")], check=True)
    if args.push:
        subprocess.run(["git", "-C", BASE_DIR, "add", "positions.json", "data/prices.json"], check=True)
        subprocess.run(["git", "-C", BASE_DIR, "commit", "-m",
                        f"posicoes: {alvo.get('symbol', args.vender)} — {acao}"], check=True)
        subprocess.run(["git", "-C", BASE_DIR, "push"], check=True)
        print("push feito — o Pages republica em ~1 min")


if __name__ == "__main__":
    main()
