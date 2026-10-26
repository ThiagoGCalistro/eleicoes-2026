"""Baixa da API de resultados do TSE o log de todas as seções de um turno (e o boletim das que
tiveram voto depois das 17h). Usado enquanto o pacote consolidado do turno não sai no Portal de
Dados Abertos; quando sair, prefira processar_arquivos_urna.py.

Uso:  python pipeline/baixar_logs_api.py --turno 2 [--por-segundo 10]

São ~514 mil seções (o exterior fica de fora) e ~1 milhão de pedidos. O TSE aceita até 100 pedidos
por segundo por IP; acima disso (ou com muitos 404) bloqueia o IP por 10 minutos, e tentar antes
reinicia o bloqueio. Por isso: seções agregadas (sem arquivos próprios) não são pedidas, e a cada
HTTP 429 todos os downloads param por 11 minutos e o ritmo cai 30%, voltando aos poucos depois.
Retomável: seções já baixadas são puladas. Ordem: Nordeste primeiro, depois as demais UFs.
Saída: dados/completo/<turno>t_<uf>.jsonl (mesmo formato do processar_arquivos_urna.py) e
       dados/completo/<turno>t_status.json (quantas seções de cada UF já foram processadas).
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import tse

PASTA = tse.DADOS / "completo"


def secao(turno, uf, mun, nome, zona, sec):
    try:
        arqs = tse.arquivos_da_secao(turno, uf, mun, zona, sec)
        if "log" not in arqs:
            return {"turno": turno, "uf": uf, "mun": mun, "nome_mun": nome, "zona": zona, "secao": sec,
                    "erro": "sem log publicado"}
        log = tse.baixar(arqs["log"])
        r = tse.metricas_dos_arquivos(turno, uf, mun, nome, zona, sec, log)
        if precisa_bu(r) and "bu" in arqs:
            r = tse.metricas_dos_arquivos(turno, uf, mun, nome, zona, sec, log, tse.baixar(arqs["bu"]))
        return r
    except Exception as e:
        return {"turno": turno, "uf": uf, "mun": mun, "nome_mun": nome, "zona": zona, "secao": sec,
                "erro": str(e)}


def precisa_bu(r):
    """O boletim (resultado oficial e horário oficial de encerramento) é baixado só onde é usado:
    seções com voto depois das 17h e seções que ainda estavam abertas no aviso do TSE (17h49)."""
    return bool(r["pos17"]) or (r["encerramento"] or 0) >= tse.AVISO_TSE


def ja_feitas(caminho):
    """Seções já resolvidas. Uma seção que precisa do boletim e ainda não o tem conta como pendente."""
    feitas = set()
    if caminho.exists():
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(linha)
            except json.JSONDecodeError:
                continue
            chave = (r["mun"], r["zona"], r["secao"])
            if r.get("erro") == "sem log publicado":
                feitas.add(chave)
            elif "erro" not in r:
                if precisa_bu(r) and not r.get("votos_cand"):
                    feitas.discard(chave)  # o registro mais recente é que vale
                else:
                    feitas.add(chave)
    return feitas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turno", type=int, choices=(1, 2), required=True)
    ap.add_argument("--por-segundo", type=float, default=10.0, help="o TSE aceita até 100 por IP")
    ap.add_argument("--trabalhadores", type=int, default=48)
    a = ap.parse_args()
    tse.definir_ritmo(a.por_segundo)
    PASTA.mkdir(parents=True, exist_ok=True)
    arq_status = PASTA / f"{a.turno}t_status.json"
    status = json.loads(arq_status.read_text(encoding="utf-8")) if arq_status.exists() else {}

    def salvar_status(uf, total, saida):
        status[uf] = {"secoes": total, "processadas": len(ja_feitas(saida)), "fonte": "API de resultados"}
        arq_status.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")

    # registra antes o total de seções de todas as UFs, para a cobertura parcial ficar correta
    ordem = tse.REGIAO["Nordeste"] + [uf for uf in tse.UFS if uf not in tse.REGIAO["Nordeste"]]
    secoes_uf = {}
    for uf in ordem:
        if status.get(uf, {}).get("fonte") == "pacote consolidado":
            continue  # já processada a partir do pacote oficial
        secoes_uf[uf] = tse.secoes_do_turno(a.turno, uf)
        salvar_status(uf, len(secoes_uf[uf]), PASTA / f"{a.turno}t_{uf}.jsonl")

    with ThreadPoolExecutor(a.trabalhadores) as ex:
        for uf, secoes in secoes_uf.items():
            saida = PASTA / f"{a.turno}t_{uf}.jsonl"
            feitas = ja_feitas(saida)
            pendentes = [s for s in secoes if (s[1], s[3], s[4]) not in feitas]
            print(f"{uf}: {len(secoes)} seções, {len(pendentes)} pendentes", flush=True)
            if saida.exists() and saida.stat().st_size and not saida.read_bytes().endswith(b"\n"):
                with open(saida, "a", encoding="utf-8") as out:
                    out.write("\n")  # linha cortada por uma interrupção anterior
            with open(saida, "a", encoding="utf-8") as out:
                # seções agregadas não têm arquivos próprios: registra sem pedir nada ao TSE
                # (pedidos que dão 404 em excesso também levam a bloqueio)
                for uf_, mun, nome, zona, sec, principal in pendentes:
                    if principal:
                        out.write(json.dumps({"turno": a.turno, "uf": uf_, "mun": mun, "nome_mun": nome,
                                              "zona": zona, "secao": sec, "erro": "sem log publicado",
                                              "agregada_a": principal}, ensure_ascii=False) + "\n")
                pendentes = [s for s in pendentes if not s[5]]
                futuros = [ex.submit(secao, a.turno, *s[:5]) for s in pendentes]
                for i, f in enumerate(as_completed(futuros), 1):
                    out.write(json.dumps(f.result(), ensure_ascii=False) + "\n")
                    if i % 1000 == 0:
                        out.flush()
                        salvar_status(uf, len(secoes), saida)
                        print(f"  {uf}: {i}/{len(pendentes)} (ritmo {1 / tse.INTERVALO_MIN:.1f} pedidos/s)", flush=True)
            salvar_status(uf, len(secoes), saida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
