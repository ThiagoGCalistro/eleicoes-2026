"""Junta o resultado oficial e a contagem completa dos logs em site/dados.js (lido pelo site).

Uso:  python pipeline/gerar_dados.py

Só dados oficiais do TSE, sem amostra e sem projeção:
  - resultado oficial (dados/oficial.json e dados/municipios/);
  - log e boletim de cada urna (dados/completo/<turno>t_<uf>.jsonl), vindos do pacote consolidado
    do Portal de Dados Abertos ou, enquanto ele não sai, da API de resultados.
Se um turno ainda não foi todo processado, os números valem para as seções já processadas e o
site mostra a cobertura; nada é extrapolado.
O voto é secreto: o log não diz em quem cada eleitor votou, então não há divisão por candidato
dos votos dados depois das 17h. O site mostra o resultado oficial das seções onde eles ocorreram
e o máximo que eles poderiam representar para cada candidato.
"""
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime

import tse

FAIXAS_ENC = [("antes das 17h", 0, tse.H17), ("17h00–17h05", tse.H17, tse.H17 + 300),
              ("17h05–17h30", tse.H17 + 300, tse.H17 + 1800),
              ("17h30–17h49", tse.H17 + 1800, tse.AVISO_TSE),
              ("17h49–19h", tse.AVISO_TSE, tse.H19), ("19h ou depois", tse.H19, 10 ** 9)]
HORAS = list(range(8, 21))  # 8h ... 20h (20 = 20h ou depois)


def faixa_enc(seg):
    for nome, ini, fim in FAIXAS_ENC:
        if ini <= seg < fim:
            return nome
    return FAIXAS_ENC[-1][0]


def arredondar(x):
    if isinstance(x, float):
        return round(x, 3)
    if isinstance(x, dict):
        return {k: arredondar(v) for k, v in x.items()}
    if isinstance(x, list):
        return [arredondar(v) for v in x]
    return x


def somar(dic, outro):
    for k, v in outro.items():
        dic[k] = dic.get(k, 0) + v


def ler_secoes(turno):
    """Registros de dados/completo/<turno>t_*.jsonl, ficando com o último válido de cada seção."""
    regs = {}
    for arq in sorted((tse.DADOS / "completo").glob(f"{turno}t_*.jsonl")):
        for linha in arq.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(linha)
            except json.JSONDecodeError:
                continue
            chave = (r["uf"], r["mun"], r["zona"], r["secao"])
            if "erro" not in r or chave not in regs:
                regs[chave] = r
    return regs


def cobertura(turno, regs):
    """Seções processadas por UF. O pacote consolidado traz todas as urnas totalizadas da UF."""
    arq = tse.DADOS / "completo" / f"{turno}t_status.json"
    status = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    feitas = defaultdict(int)
    for (uf, *_), r in regs.items():
        if r.get("erro") in (None, "sem log publicado"):
            feitas[uf] += 1
    ufs = {}
    for uf in tse.UFS:
        boletins = tse.DADOS / "boletins" / f"secoes_{turno}t_{uf}.csv"
        if uf in status:
            total = status[uf]["secoes"]
        elif boletins.exists():  # total de seções totalizadas segundo os boletins oficiais
            with open(boletins, encoding="utf-8") as f:
                total = sum(1 for _ in f) - 1
        else:
            total = feitas[uf]
        ufs[uf] = {"secoes": total, "processadas": min(feitas[uf], total) if total else 0,
                   "fonte": status.get(uf, {}).get("fonte", "pacote consolidado" if feitas[uf] else None)}
    completas = [uf for uf, c in ufs.items() if c["secoes"] and c["processadas"] >= c["secoes"]]
    return {"ufs": ufs, "completas": completas,
            "secoes": sum(c["secoes"] for c in ufs.values()),
            "processadas": sum(c["processadas"] for c in ufs.values())}


FAIXAS_ULTIMO = ["sem voto no dia", "antes das 17h", "17h00–17h49", "17h49–19h", "19h ou depois"]


def faixa_ultimo(seg):
    if seg is None:
        return FAIXAS_ULTIMO[0]
    if seg < tse.H17:
        return FAIXAS_ULTIMO[1]
    if seg < tse.AVISO_TSE:
        return FAIXAS_ULTIMO[2]
    return FAIXAS_ULTIMO[3] if seg < tse.H19 else FAIXAS_ULTIMO[4]


def chave(r):
    return (r["uf"], r["mun"], r["zona"], r["secao"])


def analisar_tardias(validos, tardias_outro_turno=None):
    """Urnas tardias: seções ainda abertas às 17h49 (hora do aviso do TSE sobre a prorrogação),
    ou seja, com encerramento oficial (boletim de urna) às 17h49 ou depois."""
    tard = [r for r in validos if (r["encerramento"] or 0) >= tse.AVISO_TSE]
    if not tard:
        return None, set()
    chaves = {chave(r) for r in tard}
    total_mun = defaultdict(int)
    total_uf = defaultdict(int)
    total_reg = defaultdict(int)
    for r in validos:
        total_mun[(r["uf"], r["mun"])] += 1
        total_uf[r["uf"]] += 1
        total_reg[tse.REGIAO_DA_UF[r["uf"]]] += 1
    ultimo = defaultdict(int)
    enc = defaultdict(int)
    municipios, por_uf, por_reg = {}, defaultdict(lambda: defaultdict(int)), defaultdict(int)
    resultado, aptos, comparecimento, com_resultado = {}, 0, 0, 0
    for r in tard:
        ultimo[faixa_ultimo(r["ultimo_voto"])] += 1
        enc[min(r["encerramento"] // 600 * 600, 20 * 3600)] += 1  # faixas de 10 min; 20h+ juntas
        m = municipios.setdefault((r["uf"], r["mun"]), {
            "uf": r["uf"], "nome": r["nome_mun"].title(), "regiao": tse.REGIAO_DA_UF[r["uf"]],
            "secoes": 0, "total_secoes": total_mun[(r["uf"], r["mun"])], "com_voto_pos_aviso": 0,
            "sem_eleitor_apos_17h": 0, "pos17": 0, "pos_aviso": 0, "pos19": 0})
        u = por_uf[r["uf"]]
        for g in (m, u):
            g["secoes"] += 1
            g["com_voto_pos_aviso"] += r["pos_aviso"] > 0
            g["sem_eleitor_apos_17h"] += r["pos17"] == 0
            g["pos17"] += r["pos17"]
            g["pos_aviso"] += r["pos_aviso"]
            g["pos19"] += r["pos19"]
        por_reg[tse.REGIAO_DA_UF[r["uf"]]] += 1
        if r.get("votos_cand"):
            somar(resultado, r["votos_cand"])
            comparecimento += sum(r["votos_cand"].values())
            aptos += r.get("aptos") or 0
            com_resultado += 1
    return {
        "secoes": len(tard), "secoes_total": len(validos),
        "com_voto_pos_aviso": sum(1 for r in tard if r["pos_aviso"]),
        "sem_eleitor_apos_17h": sum(1 for r in tard if not r["pos17"]),
        "pos17": sum(r["pos17"] for r in tard), "pos_aviso": sum(r["pos_aviso"] for r in tard),
        "pos19": sum(r["pos19"] for r in tard),
        "ultimo_voto": [{"faixa": f, "secoes": ultimo[f]} for f in FAIXAS_ULTIMO],
        "encerramento": [{"inicio": k, "secoes": n} for k, n in sorted(enc.items())],
        "regioes": [{"regiao": k, "secoes": n, "total": total_reg[k]} for k, n in por_reg.items()],
        "ufs": [{"uf": k, "total": total_uf[k], **v} for k, v in por_uf.items()],
        "municipios": sorted(municipios.values(), key=lambda m: -m["secoes"]),
        "resultado": resultado, "aptos": aptos, "comparecimento": comparecimento,
        "secoes_com_resultado": com_resultado,
        "tardias_tambem_no_outro_turno": (len(chaves & tardias_outro_turno)
                                          if tardias_outro_turno is not None else None),
    }, chaves


def resumo(turno, oficial, tardias_outro_turno=None):
    regs = ler_secoes(turno)
    if not regs:
        return None
    validos = [r for r in regs.values() if "erro" not in r]
    cob = cobertura(turno, regs)
    hora = defaultdict(int)
    enc = defaultdict(int)
    cabines = []
    tot = defaultdict(int)
    por_reg = defaultdict(lambda: defaultdict(int))
    por_uf = defaultdict(lambda: defaultdict(int))
    municipios = {}
    resultado_pos17 = {}
    secoes_pos17_com_bu = 0
    for r in validos:
        for k, n in r["faixas"].items():
            hora[min(max(int(k) // 6, 8), 20)] += n
        if r["encerramento"] is not None:
            enc[faixa_enc(r["encerramento"])] += 1
        if r["cabine_mediana"] is not None:
            cabines.append(r["cabine_mediana"])
        for chave in ("comparecimento", "pos17", "pos_aviso", "pos19", "biometricos"):
            tot[chave] += r[chave]
        tot["secoes"] += 1
        tot["secoes_pos17"] += r["pos17"] > 0
        for grupo in (por_reg[tse.REGIAO_DA_UF[r["uf"]]], por_uf[r["uf"]]):
            for chave in ("comparecimento", "pos17", "pos_aviso", "pos19"):
                grupo[chave] += r[chave]
            grupo["secoes"] += 1
            grupo["secoes_pos17"] += r["pos17"] > 0
        if r["pos17"]:
            m = municipios.setdefault((r["uf"], r["mun"]), {
                "uf": r["uf"], "nome": r["nome_mun"].title(), "regiao": tse.REGIAO_DA_UF[r["uf"]],
                "pos17": 0, "pos_aviso": 0, "pos19": 0, "secoes_pos17": 0, "resultado": {}})
            m["pos17"] += r["pos17"]
            m["pos_aviso"] += r["pos_aviso"]
            m["pos19"] += r["pos19"]
            m["secoes_pos17"] += 1
            if r.get("votos_cand"):
                somar(m["resultado"], r["votos_cand"])
                somar(resultado_pos17, r["votos_cand"])
                secoes_pos17_com_bu += 1
    cabines.sort()
    tot_h = sum(hora.values()) or 1
    tot_enc = sum(enc.values()) or 1

    # Qualidade: votos do resultado oficial que não aparecem nos logs (seção sem log publicado ou
    # log incompleto). Entram no resultado, mas não na contagem por horário.
    oficial_ufs = sum(oficial[uf]["comparecimento"] for uf in tse.UFS if uf in oficial)
    qualidade = {"comparecimento_oficial": oficial_ufs, "comparecimento_logs": tot["comparecimento"],
                 "votos_sem_horario": oficial_ufs - tot["comparecimento"]}
    tardias, chaves_tardias = analisar_tardias(validos, tardias_outro_turno)
    return {
        "cobertura": cob,
        "qualidade": qualidade,
        "tardias": tardias,
        "_chaves_tardias": chaves_tardias,
        "_validos": validos,
        **tot,
        "curva_horaria": [{"hora": h, "votos": hora[h], "pct": 100 * hora[h] / tot_h} for h in HORAS],
        "encerramento": [{"faixa": f[0], "secoes": enc[f[0]], "pct": 100 * enc[f[0]] / tot_enc} for f in FAIXAS_ENC],
        "cabine_mediana_seg": cabines[len(cabines) // 2] if cabines else None,
        "pct_biometria": 100 * tot["biometricos"] / tot["comparecimento"] if tot["comparecimento"] else None,
        "regioes": [{"regiao": k, **v} for k, v in por_reg.items()],
        "ufs": [{"uf": k, **v} for k, v in por_uf.items()],
        "municipios": sorted(municipios.values(), key=lambda m: -m["pos17"]),
        "resultado_secoes_pos17": resultado_pos17,
        "secoes_pos17_com_resultado": secoes_pos17_com_bu,
    }


def main():
    oficial = json.loads((tse.DADOS / "oficial.json").read_text(encoding="utf-8"))
    saida = {"gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
             "oficial": {int(t): v for t, v in oficial.items()},
             "regiao_da_uf": tse.REGIAO_DA_UF, "turnos": {}}
    chaves_tardias, validos = {}, {}
    for turno in (1, 2):
        # o 2º turno compara as suas urnas tardias com as mesmas seções no 1º
        r = resumo(turno, saida["oficial"][turno], chaves_tardias.get(1) if turno == 2 else None)
        saida["turnos"][turno] = r
        if r:
            chaves_tardias[turno] = r.pop("_chaves_tardias")
            validos[turno] = r.pop("_validos")
            c = r["cobertura"]
            print(f"{turno}º turno: {c['processadas']} de {c['secoes']} seções processadas "
                  f"({len(c['completas'])} UFs completas); {r['pos17']} votos após 17h; "
                  f"{r['tardias']['secoes'] if r['tardias'] else 0} urnas tardias")
        else:
            print(f"{turno}º turno: nenhum log processado ainda")

    if saida["turnos"][1]:
        saida["turnos"][1]["municipios"] = []  # o site lista cidades só do 2º turno
        if saida["turnos"][1]["tardias"]:
            saida["turnos"][1]["tardias"]["municipios"] = []

    tse.SITE.mkdir(exist_ok=True)
    js = "window.DADOS = " + json.dumps(arredondar(saida), ensure_ascii=False, separators=(",", ":")) + ";\n"
    (tse.SITE / "dados.js").write_text(js, encoding="utf-8")
    print(f"site/dados.js gerado ({len(js) // 1024} KB)")

    # planilha dos municípios com votos após 17h no 2º turno, para download no site
    if saida["turnos"][2]:
        with open(tse.SITE / "municipios_pos17h_2turno.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["UF", "Município", "Região", "Seções com voto após 17h", "Votos após 17h",
                        "Votos após 17h49", "Votos às 19h ou depois",
                        "Lula (13) nessas seções", "Flávio Bolsonaro (22) nessas seções"])
            for m in saida["turnos"][2]["municipios"]:
                w.writerow([m["uf"].upper(), m["nome"], m["regiao"], m["secoes_pos17"], m["pos17"], m["pos_aviso"],
                            m["pos19"], m["resultado"].get("13", ""), m["resultado"].get("22", "")])
    if 2 in validos:
        gerar_csv_tardias(validos[2], chaves_tardias.get(1, set()))
    gerar_municipios()
    return 0


def gerar_csv_tardias(validos, tardias_1t):
    """Uma linha por urna tardia do 2º turno, com horários e resultado oficial da seção."""
    def hora(s):
        return "" if s is None else f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"
    tard = sorted((r for r in validos if (r["encerramento"] or 0) >= tse.AVISO_TSE), key=chave)
    with open(tse.SITE / "urnas_tardias_2turno.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["UF", "Município", "Zona", "Seção", "Abertura (Brasília)", "Encerramento (Brasília)",
                    "Último voto (Brasília)", "Votos após 17h", "Votos após 17h49", "Votos às 19h ou depois",
                    "Eleitores aptos", "Comparecimento", "Lula (13)", "Flávio Bolsonaro (22)", "Brancos", "Nulos",
                    "Também fechou após 17h49 no 1º turno"])
        for r in tard:
            v = r.get("votos_cand") or {}
            w.writerow([r["uf"].upper(), r["nome_mun"], r["zona"], r["secao"], hora(r["abertura"]),
                        hora(r["encerramento"]), hora(r["ultimo_voto"]), r["pos17"], r["pos_aviso"], r["pos19"],
                        r.get("aptos") or "", sum(v.values()) if v else r["comparecimento"], v.get("13", ""),
                        v.get("22", ""), v.get("branco", ""), v.get("nulo", ""),
                        "sim" if chave(r) in tardias_1t else "não"])
    print(f"site/urnas_tardias_2turno.csv gerado ({len(tard)} seções)")


def gerar_municipios():
    """Brancos, nulos e abstenção por município nos dois turnos -> site/municipios.js e CSV."""
    turnos = {}
    for t in (1, 2):
        turnos[t] = {}
        for arq in (tse.DADOS / "municipios").glob(f"{t}t_*.json"):
            uf = arq.stem.split("_")[1]
            for mun, m in json.loads(arq.read_text(encoding="utf-8")).items():
                turnos[t][(uf, mun)] = m
    comuns = sorted(set(turnos[1]) & set(turnos[2]))
    if not comuns:
        print("municípios: nada baixado ainda (rode baixar_municipios.py)")
        return

    def pc(parte, todo):
        return round(100 * parte / todo, 2) if todo else 0.0

    linhas = []
    for uf, mun in comuns:
        a, b = turnos[1][(uf, mun)], turnos[2][(uf, mun)]
        linhas.append([uf, b["nome"].title(), b["aptos"],
                       pc(a["abstencoes"], a["aptos"]), pc(b["abstencoes"], b["aptos"]),
                       pc(a["brancos"], a["comparecimento"]), pc(b["brancos"], b["comparecimento"]),
                       pc(a["nulos"], a["comparecimento"]), pc(b["nulos"], b["comparecimento"]),
                       a["abstencoes"], b["abstencoes"], a["brancos"], b["brancos"], a["nulos"], b["nulos"]])
    cab = ["uf", "nome", "aptos", "abst1", "abst2", "br1", "br2", "nu1", "nu2",
           "n_abst1", "n_abst2", "n_br1", "n_br2", "n_nu1", "n_nu2"]
    js = ("window.MUNICIPIOS = " + json.dumps({"colunas": cab, "linhas": linhas}, ensure_ascii=False,
                                               separators=(",", ":")) + ";\n")
    (tse.SITE / "municipios.js").write_text(js, encoding="utf-8")
    with open(tse.SITE / "municipios_brancos_nulos_abstencao.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["UF", "Município", "Eleitores aptos", "Abstenção 1º turno (%)", "Abstenção 2º turno (%)",
                    "Brancos 1º turno (%)", "Brancos 2º turno (%)", "Nulos 1º turno (%)", "Nulos 2º turno (%)",
                    "Abstenção 1º turno", "Abstenção 2º turno", "Brancos 1º turno", "Brancos 2º turno",
                    "Nulos 1º turno", "Nulos 2º turno"])
        for l in linhas:
            w.writerow([l[0].upper(), *l[1:3], *(str(x).replace(".", ",") for x in l[3:9]), *l[9:]])
    print(f"site/municipios.js gerado ({len(linhas)} municípios, {len(js) // 1024} KB)")


if __name__ == "__main__":
    sys.exit(main())
