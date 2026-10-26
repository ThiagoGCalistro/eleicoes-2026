"""Processa os arquivos oficiais de todas as urnas: log e boletim de cada seção, sem amostra.

Uso:  python pipeline/processar_arquivos_urna.py --turno 1 [--processos 5]

Fonte: conjunto "Resultados 2026 - Arquivos transmitidos para totalização" do Portal de Dados
Abertos do TSE, com um zip por UF contendo bu.dat, log.jez, rdv.dat e vota.vsc de cada urna
totalizada. Cada UF é baixada em partes paralelas, processada com vários processos e apagada
em seguida (o maior arquivo, SP, tem ~20 GB). UFs já processadas são puladas.
Saída: dados/completo/<turno>t_<uf>.jsonl, uma linha por seção.
"""
import argparse
import json
import sys
import threading
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Pool

import tse

PASTA = tse.DADOS / "completo"
PACOTE = "resultados-2026-arquivos-transmitidos-para-totalizacao"


def recursos(turno):
    nome_turno = "Primeiro turno" if turno == 1 else "Segundo turno"
    pacote = tse.baixar_json(tse.CKAN + PACOTE)["result"]
    return {r["name"].split(" ")[0].lower(): r["url"] for r in pacote["resources"]
            if nome_turno in (r.get("name") or "") and (r.get("url") or "").endswith(".zip")}


def baixar_em_partes(url, destino, partes=8, bloco=64 << 20):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "eleicoes-2026-analise/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        tamanho = int(r.headers["Content-Length"])
    with open(destino, "wb") as f:
        f.truncate(tamanho)
    trava = threading.Lock()

    def pedaco(ini):
        fim = min(tamanho, ini + bloco) - 1
        for n in range(6):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "eleicoes-2026-analise/1.0",
                                                           "Range": f"bytes={ini}-{fim}"})
                with urllib.request.urlopen(req, timeout=300) as r:
                    dados = r.read()
                if len(dados) != fim - ini + 1:
                    raise IOError("parte incompleta")
                with trava, open(destino, "r+b") as f:
                    f.seek(ini)
                    f.write(dados)
                return
            except Exception:
                if n == 5:
                    raise
    with ThreadPoolExecutor(partes) as ex:
        list(ex.map(pedaco, range(0, tamanho, bloco)))


# ---------------------------------------------------------------- processamento paralelo

_zip = None


def _abrir(caminho):
    global _zip
    _zip = zipfile.ZipFile(caminho)


def _processar(tarefa):
    turno, uf, mun, nome, zona, secao, nome_log, nome_bu = tarefa
    try:
        bu = _zip.read(nome_bu) if nome_bu else None
        return tse.metricas_dos_arquivos(turno, uf, mun, nome, zona, secao, _zip.read(nome_log), bu)
    except Exception as e:
        return {"turno": turno, "uf": uf, "mun": mun, "nome_mun": nome, "zona": zona, "secao": secao,
                "erro": str(e)}


def processar_uf(turno, uf, url, nomes, processos):
    zip_local = PASTA / f"arquivos_{turno}t_{uf}.zip"
    baixar_em_partes(url, zip_local)
    secoes = {}
    with zipfile.ZipFile(zip_local) as z:
        for nome in z.namelist():
            # o03220ac0101500020088-log.jez -> uf ac, município 01015, zona 0002, seção 0088
            if not nome.startswith("o") or "-" not in nome:
                continue
            chave, tipo = nome.split("-", 1)
            s = secoes.setdefault(chave[6:21], {})
            if tipo == "log.jez":
                s["log"] = nome
            elif tipo == "bu.dat":
                s["bu"] = nome
    tarefas = [(turno, uf, k[2:7], nomes.get(k[2:7], ""), k[7:11], k[11:15], s["log"], s.get("bu"))
               for k, s in secoes.items() if "log" in s]
    destino = PASTA / f"{turno}t_{uf}.jsonl"
    tmp = destino.with_suffix(".parcial")
    with Pool(processos, initializer=_abrir, initargs=(str(zip_local),)) as pool, \
            open(tmp, "w", encoding="utf-8") as out:
        for r in pool.imap_unordered(_processar, tarefas, chunksize=64):
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(destino)
    zip_local.unlink()
    sem_log = sum(1 for s in secoes.values() if "log" not in s)
    return len(tarefas), sem_log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turno", type=int, choices=(1, 2), required=True)
    ap.add_argument("--processos", type=int, default=5)
    ap.add_argument("--ufs", nargs="*", help="só estas UFs (ex.: ac rr)")
    a = ap.parse_args()
    PASTA.mkdir(parents=True, exist_ok=True)
    urls = recursos(a.turno)
    if not urls:
        print(f"O TSE ainda não publicou os arquivos de urna do {a.turno}º turno no Portal de Dados Abertos.")
        return 2
    e = tse.TURNOS[a.turno]["eleicao"]
    cfg = tse.baixar_json(f"{tse.BASE}/{e}/config/mun-e{e:06d}-cm.json")
    nomes = {m["cd"]: m["nm"] for abr in cfg["abr"] for m in abr["mu"]}
    arq_status = PASTA / f"{a.turno}t_status.json"
    status = json.loads(arq_status.read_text(encoding="utf-8")) if arq_status.exists() else {}
    for uf in a.ufs or tse.UFS:
        saida = PASTA / f"{a.turno}t_{uf}.jsonl"
        # pula UFs já processadas a partir do pacote; o que veio da API é substituído pelo pacote
        if saida.exists() and status.get(uf, {}).get("fonte") != "API de resultados":
            if uf not in status:
                with open(saida, encoding="utf-8") as f:
                    n = sum(1 for _ in f)
                status[uf] = {"secoes": n, "processadas": n, "fonte": "pacote consolidado"}
            continue
        if uf not in urls:
            print(f"{uf}: arquivo não encontrado no portal", flush=True)
            continue
        n, sem_log = processar_uf(a.turno, uf, urls[uf], nomes, a.processos)
        status[uf] = {"secoes": n, "processadas": n, "fonte": "pacote consolidado"}
        arq_status.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{a.turno}º turno {uf}: {n} seções" + (f" ({sem_log} sem log)" if sem_log else ""), flush=True)
    arq_status.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
