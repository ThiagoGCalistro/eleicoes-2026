"""Baixa o resultado oficial de Presidente (Brasil e cada UF) nos dois turnos.

Uso:  python pipeline/baixar_resultados.py
Saída: dados/oficial.json
"""
import json
import sys

import tse


def _n(x):
    return int(x) if x not in (None, "") else 0


def _pct(x):
    return float(x.replace(",", ".")) if x else 0.0


def resumo(d):
    cargo = d["carg"][0]
    cands = []
    for grupo in cargo.get("agr", []):
        for partido in grupo.get("par", []):
            for c in partido.get("cand", []):
                cands.append({"numero": c["n"], "nome": c["nmu"], "partido": partido["sg"],
                              "votos": _n(c["vap"]), "pct": _pct(c["pvap"]), "situacao": c["st"]})
    cands.sort(key=lambda c: -c["votos"])
    e, v = d["e"], d["v"]
    return {
        "aptos": _n(e["te"]), "comparecimento": _n(e["c"]), "abstencoes": _n(e["a"]),
        "pct_comparecimento": _pct(e["pc"]), "pct_abstencao": _pct(e["pa"]),
        "validos": _n(v["vv"]), "brancos": _n(v["vb"]), "nulos": _n(v["tvn"]),
        "pct_brancos": _pct(v["pvb"]), "pct_nulos": _pct(v["ptvn"]),
        "candidatos": cands, "gerado_em": f"{d['dg']} {d['hg']}",
    }


def main():
    saida = {}
    for turno, t in tse.TURNOS.items():
        e = t["eleicao"]
        saida[turno] = {}
        for abr in ["br"] + tse.UFS:
            d = tse.baixar_json(f"{tse.BASE}/{e}/dados/{abr}/{abr}-c0001-e{e:06d}-u.json")
            if d:
                saida[turno][abr] = resumo(d)
        print(f"{turno}º turno: {len(saida[turno])} abrangências", flush=True)
    tse.DADOS.mkdir(exist_ok=True)
    (tse.DADOS / "oficial.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
