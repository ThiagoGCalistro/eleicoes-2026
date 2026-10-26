"""Resultado de Presidente por município nos dois turnos: eleitorado, comparecimento, abstenção,
brancos, nulos e votos por candidato.

Uso:  python pipeline/baixar_municipios.py [--por-segundo 3]

Para cada turno:
  - se os Boletins de Urna em massa já foram baixados (baixar_boletins.py), soma as seções de
    cada município, sem nenhum download;
  - senão, baixa um arquivo por município da API de resultados do TSE (~5.600 arquivos).
    O site limita a taxa de pedidos (HTTP 429), por isso o ritmo padrão é de ~3 pedidos/s.
UFs já processadas são puladas.
Saída: dados/municipios/<turno>t_<uf>.json
"""
import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import tse
from baixar_resultados import resumo

PASTA = tse.DADOS / "municipios"


def municipios_da_eleicao(eleicao):
    cfg = tse.baixar_json(f"{tse.BASE}/{eleicao}/config/mun-e{eleicao:06d}-cm.json")
    return {abr["cd"]: [(m["cd"], m["nm"]) for m in abr["mu"]] for abr in cfg["abr"]}


def da_api(eleicao, uf, mun, nome):
    d = tse.baixar_json(f"{tse.BASE}/{eleicao}/dados/{uf}/{uf}{mun}-c0001-e{eleicao:06d}-u.json")
    if not d:
        return mun, None
    r = resumo(d)
    return mun, {
        "nome": nome, "aptos": r["aptos"], "comparecimento": r["comparecimento"],
        "abstencoes": r["abstencoes"], "brancos": r["brancos"], "nulos": r["nulos"], "validos": r["validos"],
        "cand": {c["numero"]: c["votos"] for c in r["candidatos"]},
    }


def dos_boletins(arq, validos):
    """Soma as seções do arquivo de boletins de uma UF por município.

    Votos em números fora da lista oficial de candidatos (candidatura anulada) contam como
    nulos, como no resultado oficial."""
    out = {}
    with open(arq, encoding="utf-8") as f:
        for s in csv.DictReader(f):
            m = out.setdefault(s["mun"], {"nome": s["nome_mun"], "aptos": 0, "comparecimento": 0, "abstencoes": 0,
                                          "brancos": 0, "nulos": 0, "validos": 0, "cand": {}})
            m["aptos"] += int(s["aptos"])
            m["comparecimento"] += int(s["comparecimento"])
            m["abstencoes"] += int(s["abstencoes"])
            for k, v in json.loads(s["votos"]).items():
                if k == "branco":
                    m["brancos"] += v
                elif k == "nulo" or k not in validos:
                    m["nulos"] += v
                else:
                    m["validos"] += v
                    m["cand"][k] = m["cand"].get(k, 0) + v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trabalhadores", type=int, default=4)
    ap.add_argument("--por-segundo", type=float, default=3.0)
    a = ap.parse_args()
    tse.definir_ritmo(a.por_segundo)
    PASTA.mkdir(parents=True, exist_ok=True)
    oficial = json.loads((tse.DADOS / "oficial.json").read_text(encoding="utf-8"))
    with ThreadPoolExecutor(a.trabalhadores) as ex:
        for turno, t in tse.TURNOS.items():
            validos = {c["numero"] for c in oficial[str(turno)]["br"]["candidatos"]}
            por_uf = None
            for uf in tse.UFS:
                destino = PASTA / f"{turno}t_{uf}.json"
                if destino.exists():
                    continue
                boletins = tse.DADOS / "boletins" / f"secoes_{turno}t_{uf}.csv"
                if boletins.exists():
                    dados, origem = dos_boletins(boletins, validos), "boletins"
                else:
                    por_uf = por_uf or municipios_da_eleicao(t["eleicao"])
                    res = ex.map(lambda m: da_api(t["eleicao"], uf, *m), por_uf.get(uf, []))
                    dados, origem = {mun: r for mun, r in res if r}, "API"
                destino.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
                print(f"{turno}º turno {uf}: {len(dados)} municípios ({origem})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
