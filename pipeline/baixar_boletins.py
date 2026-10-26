"""Baixa os Boletins de Urna em massa (dados abertos do TSE) e guarda uma linha por seção.

Uso:  python pipeline/baixar_boletins.py --turno 1
      python pipeline/baixar_boletins.py --turno 2   (quando o TSE publicar o 2º turno)

Cada UF é baixada, lida direto do zip (só as linhas de Presidente) e o zip é apagado em
seguida, para não ocupar disco. UFs já processadas são puladas.
Saída: dados/boletins/secoes_<turno>t_<uf>.csv
"""
import argparse
import csv
import io
import json
import sys
import zipfile

import tse

PASTA = tse.DADOS / "boletins"
COLUNAS = ["uf", "mun", "nome_mun", "zona", "secao", "local", "aptos", "comparecimento",
           "abstencoes", "abertura", "encerramento", "fuso", "encerramento_brt", "votos"]


def recursos_bweb(turno):
    pacote = tse.baixar_json(tse.CKAN + "resultados-2026-boletim-de-urna")["result"]
    nome_turno = "Primeiro turno" if turno == 1 else "Segundo turno"
    por_uf = {}
    for r in pacote["resources"]:
        nome, url = r.get("name") or "", r.get("url") or ""
        if nome_turno in nome and url.endswith(".zip"):
            uf = nome.split(" ")[0].lower()
            data = r.get("last_modified") or r.get("created") or ""
            if uf not in por_uf or data > por_uf[uf][0]:
                por_uf[uf] = (data, url)
    return {uf: url for uf, (_, url) in por_uf.items()}


def processar_uf(uf, url, turno):
    zip_local = PASTA / f"bweb_{turno}t_{uf}.zip"
    tse.baixar_para_arquivo(url, zip_local)
    secoes = {}
    with zipfile.ZipFile(zip_local) as z:
        nome_csv = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(nome_csv) as bruto:
            leitor = csv.reader(io.TextIOWrapper(bruto, encoding="latin-1"), delimiter=";")
            cab = {c: i for i, c in enumerate(next(leitor))}
            for lin in leitor:
                if lin[cab["DS_CARGO_PERGUNTA"]] != "Presidente":
                    continue
                chave = (lin[cab["CD_MUNICIPIO"]].zfill(5), lin[cab["NR_ZONA"]].zfill(4),
                         lin[cab["NR_SECAO"]].zfill(4))
                s = secoes.get(chave)
                if s is None:
                    abertura = lin[cab["DT_ABERTURA"]][11:19]
                    encerramento = lin[cab["DT_ENCERRAMENTO"]][11:19]
                    fuso = tse.fuso_da_secao(uf, chave[0])
                    s = secoes[chave] = {
                        "uf": uf, "mun": chave[0], "nome_mun": lin[cab["NM_MUNICIPIO"]],
                        "zona": chave[1], "secao": chave[2], "local": lin[cab["NR_LOCAL_VOTACAO"]],
                        "aptos": lin[cab["QT_APTOS"]], "comparecimento": lin[cab["QT_COMPARECIMENTO"]],
                        "abstencoes": lin[cab["QT_ABSTENCOES"]], "abertura": abertura,
                        "encerramento": encerramento, "fuso": fuso,
                        "encerramento_brt": tse._seg(encerramento) - fuso * 3600 if encerramento else "",
                        "votos": {},
                    }
                nr = lin[cab["NR_VOTAVEL"]]
                nr = {"95": "branco", "96": "nulo"}.get(nr, nr)
                s["votos"][nr] = s["votos"].get(nr, 0) + int(lin[cab["QT_VOTOS"]])
    zip_local.unlink()

    destino = PASTA / f"secoes_{turno}t_{uf}.csv"
    tmp = destino.with_suffix(".parcial")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUNAS)
        w.writeheader()
        for s in secoes.values():
            w.writerow({**s, "votos": json.dumps(s["votos"])})
    tmp.replace(destino)
    return len(secoes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turno", type=int, choices=(1, 2), required=True)
    a = ap.parse_args()
    PASTA.mkdir(parents=True, exist_ok=True)
    recursos = recursos_bweb(a.turno)
    if not recursos:
        print(f"O TSE ainda não publicou os Boletins de Urna do {a.turno}º turno.")
        return 2
    for uf in tse.UFS:
        if (PASTA / f"secoes_{a.turno}t_{uf}.csv").exists():
            continue
        if uf not in recursos:
            print(f"{uf}: arquivo não encontrado no portal", flush=True)
            continue
        print(f"{uf}: {processar_uf(uf, recursos[uf], a.turno)} seções", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
