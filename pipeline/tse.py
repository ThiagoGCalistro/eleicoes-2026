"""Funções compartilhadas: endereços do TSE, download e leitura de logs e boletins de urna."""
import http.client
import io
import json
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
SITE = RAIZ / "site"

BASE = "https://resultados.tse.jus.br/oficial/ele2026"
CKAN = "https://dadosabertos.tse.jus.br/api/3/action/package_show?id="

TURNOS = {
    1: {"pleito": 3220, "eleicao": 6257, "data": "04/10/2026"},
    2: {"pleito": 3221, "eleicao": 6258, "data": "25/10/2026"},
}

UFS = ["ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms", "mt", "pa",
       "pb", "pe", "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc", "se", "sp", "to"]
REGIAO = {
    "Norte": ["ac", "am", "ap", "pa", "ro", "rr", "to"],
    "Nordeste": ["al", "ba", "ce", "ma", "pb", "pe", "pi", "rn", "se"],
    "Centro-Oeste": ["df", "go", "ms", "mt"],
    "Sudeste": ["es", "mg", "rj", "sp"],
    "Sul": ["pr", "rs", "sc"],
}
REGIAO_DA_UF = {uf: r for r, ufs in REGIAO.items() for uf in ufs}

# Diferença (em horas) entre o relógio da urna e o horário de Brasília quando não há tabela por
# município (fuso_da_secao). Regra do TSE: AC 6h-15h; AM 7h-16h, exceto 11 municípios no fuso do
# Acre; RR, RO, MT e MS 7h-16h; Fernando de Noronha 9h-18h; demais 8h-17h.
FUSO_PADRAO = {"ac": -2, "am": -1, "rr": -1, "ro": -1, "mt": -1, "ms": -1}
FUSO_MUNICIPIO = {  # exceções dentro da UF (código TSE do município)
    "am02020": -2, "am02054": -2, "am02135": -2, "am02291": -2, "am02313": -2, "am02399": -2,
    "am02496": -2, "am02755": -2, "am02917": -2, "am98370": -2, "am98477": -2,  # 11 do AM no fuso do AC
    "pe30015": 1,  # Fernando de Noronha
}

H17 = 17 * 3600
AVISO_TSE = 17 * 3600 + 49 * 60  # hora em que o TSE avisou os TREs da prorrogação
H19 = 19 * 3600


# ---------------------------------------------------------------- download

INTERVALO_MIN = 0.0  # segundos entre pedidos (somando todas as threads); 0 = sem limite
INTERVALO_ALVO = 0.0  # ritmo pedido pelo usuário; após um 429 o script volta a ele aos poucos
_trava_ritmo = threading.Lock()
_proximo_pedido = 0.0
_sucessos = 0


def definir_ritmo(por_segundo):
    global INTERVALO_MIN, INTERVALO_ALVO
    INTERVALO_MIN = INTERVALO_ALVO = 1 / por_segundo


def _esperar_vez():
    global _proximo_pedido
    if not INTERVALO_MIN:
        return
    with _trava_ritmo:
        agora = time.monotonic()
        espera = _proximo_pedido - agora
        _proximo_pedido = max(agora, _proximo_pedido) + INTERVALO_MIN
    if espera > 0:
        time.sleep(espera)


BLOQUEIO_TSE = 11 * 60  # o TSE bloqueia o IP por 10 min; tentar antes disso reinicia o bloqueio


def _desacelerar():
    """Após um HTTP 429: pausa todas as threads por 11 minutos e reduz o ritmo em 30% (até 2 pedidos/s)."""
    global INTERVALO_MIN, _proximo_pedido
    with _trava_ritmo:
        agora = time.monotonic()
        if _proximo_pedido < agora + 60:  # primeiro 429 deste bloqueio (vários chegam juntos)
            if INTERVALO_MIN:
                INTERVALO_MIN = min(0.5, INTERVALO_MIN / 0.7)
            print(f"HTTP 429: pausa de {BLOQUEIO_TSE // 60} min; ritmo reduzido para "
                  f"{1 / INTERVALO_MIN if INTERVALO_MIN else 0:.1f} pedidos/s", flush=True)
        _proximo_pedido = max(_proximo_pedido, agora + BLOQUEIO_TSE)


def _acelerar():
    """A cada 500 pedidos bem-sucedidos, volta 10% em direção ao ritmo pedido."""
    global INTERVALO_MIN, _sucessos
    with _trava_ritmo:
        _sucessos += 1
        if _sucessos % 500 == 0 and INTERVALO_ALVO and INTERVALO_MIN > INTERVALO_ALVO:
            INTERVALO_MIN = max(INTERVALO_ALVO, INTERVALO_MIN * 0.9)


def baixar(url, tentativas=6, timeout=60, esperas_429=10):
    """Retorna os bytes da URL, ou None se o arquivo não existir (404/403).

    Em HTTP 429 (limite de pedidos do TSE: 100/s por IP, com bloqueio de 10 min) pausa todos os
    downloads por 11 minutos e tenta de novo, até `esperas_429` vezes."""
    n = bloqueios = 0
    while n < tentativas:
        _esperar_vez()
        try:
            status, cabecalhos, dados = _get(url, timeout)
            if status == 200:
                _acelerar()
                return dados
            if status in (403, 404):
                return None
            erro = f"HTTP {status}"
            if status == 429 and bloqueios < esperas_429:
                bloqueios += 1
                _desacelerar()  # a pausa acontece em _esperar_vez, para todas as threads
                continue
        except Exception as e:  # rede instável: tenta de novo com espera crescente
            erro = e
        time.sleep(2 ** n)
        n += 1
    raise RuntimeError(f"falha ao baixar {url}: {erro}")


_conexoes = threading.local()


def _get(url, timeout):
    """GET reaproveitando uma conexão HTTPS por thread e servidor (evita refazer o TLS a cada
    pedido, que custava ~1 s por arquivo)."""
    u = urllib.parse.urlsplit(url)
    abertas = getattr(_conexoes, "abertas", None)
    if abertas is None:
        abertas = _conexoes.abertas = {}
    c = abertas.get(u.netloc)
    if c is None:
        c = abertas[u.netloc] = http.client.HTTPSConnection(u.netloc, timeout=timeout)
    try:
        c.request("GET", u.path + (f"?{u.query}" if u.query else ""),
                  headers={"User-Agent": "eleicoes-2026-analise/1.0"})
        r = c.getresponse()
        return r.status, r.headers, r.read()
    except Exception:
        c.close()
        abertas.pop(u.netloc, None)
        raise


def baixar_json(url):
    b = baixar(url)
    return None if b is None else json.loads(b.decode("utf-8"))


def baixar_para_arquivo(url, destino, bloco=1 << 20):
    destino = Path(destino)
    tmp = destino.with_suffix(destino.suffix + ".parcial")
    req = urllib.request.Request(url, headers={"User-Agent": "eleicoes-2026-analise/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        while True:
            b = r.read(bloco)
            if not b:
                break
            f.write(b)
    tmp.replace(destino)
    return destino


def secoes_do_turno(turno, uf):
    """Lista (uf, cod_mun, nome_mun, zona, secao, secao_principal) a partir da configuração do site
    de resultados. secao_principal vem preenchida nas seções agregadas (votam junto com outra e
    não têm arquivos próprios); nas demais é None."""
    p = TURNOS[turno]["pleito"]
    cfg = baixar_json(f"{BASE}/arquivo-urna/{p}/config/{uf}/{uf}-p{p:06d}-cs.json")
    out = []
    for abr in cfg["abr"]:
        for mu in abr["mu"]:
            for z in mu["zon"]:
                for s in z["sec"]:
                    out.append((uf, mu["cd"], mu["nm"], z["cd"], s["ns"], s.get("nsp")))
    return out


def arquivos_da_secao(turno, uf, mun, zona, secao):
    """Retorna {tipo: url} dos arquivos totalizados da seção (log, bu, rdv, vota)."""
    p = TURNOS[turno]["pleito"]
    pasta = f"{BASE}/arquivo-urna/{p}/dados/{uf}/{mun}/{zona}/{secao}"
    aux = baixar_json(f"{pasta}/p{p:06d}-{uf}-m{mun}-z{zona}-s{secao}-aux.json")
    if not aux or not aux.get("hashes"):
        return {}
    validos = [h for h in aux["hashes"] if h.get("st") in ("Totalizado", "Recebido")] or aux["hashes"]
    h = validos[-1]
    return {a["tp"]: f"{pasta}/{h['hash']}/{a['nm']}" for a in h.get("arq", [])}


# ---------------------------------------------------------------- log da urna

def _seg(hhmmss):
    h, m, s = hhmmss.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def _textos_do_jez(conteudo_jez):
    # Quando a urna é substituída, o .jez traz também os logs das urnas anteriores (*.jez internos)
    with zipfile.ZipFile(io.BytesIO(conteudo_jez)) as z:
        for nome in z.namelist():
            dados = z.read(nome)
            if nome.lower().endswith(".jez"):
                yield from _textos_do_jez(dados)
            else:
                yield dados.decode("latin-1")


def linhas_do_log(conteudo_jez):
    """Descompacta o .jez e devolve as linhas de todas as urnas da seção, separadas por tab."""
    vistas = set()
    for texto in _textos_do_jez(conteudo_jez):
        for linha in texto.splitlines():
            partes = linha.split("\t")
            if len(partes) >= 5 and linha not in vistas:
                vistas.add(linha)
                yield partes


def ler_log(conteudo_jez, data, secao=None):
    """Extrai do log os eventos do dia da eleição. Horários em segundos do relógio local da urna."""
    r = {"abertura": None, "votos": [], "biometricos": 0, "justificativas": 0,
         "cabine": [], "fim_fila": None, "encerramento": None}
    habilitado = None
    linhas = [p for p in linhas_do_log(conteudo_jez) if p[0].startswith(data)]
    if secao is not None:
        # O arquivo pode trazer logs de outras urnas (substituídas, reserva ou, às vezes, de outra
        # seção). Descarta as urnas que se declaram configuradas para outra seção nesse dia.
        declarada = {}
        for p in linhas:
            if p[4].startswith("Seção Eleitoral: "):
                declarada[p[2]] = p[4].split(":")[1].strip()
        outras = {u for u, s in declarada.items() if s.isdigit() and int(s) != int(secao)}
        linhas = [p for p in linhas if p[2] not in outras]
    do_dia = sorted(((_seg(p[0][11:19]), p[4]) for p in linhas), key=lambda x: x[0])
    for t, msg in do_dia:
        if msg.startswith("Urna pronta para receber votos"):
            if r["abertura"] is None:
                r["abertura"] = t
        elif msg.startswith("Eleitor foi habilitado"):
            habilitado = t
        elif msg.startswith("Tipo de habilitação do eleitor [biométrica]"):
            r["biometricos"] += 1
        elif msg.startswith("O voto do eleitor foi computado"):
            r["votos"].append(t)
            if habilitado is not None:
                r["cabine"].append(t - habilitado)
            habilitado = None
        elif msg.startswith("Justificativa recebida"):
            r["justificativas"] += 1
        elif msg.startswith("Todas as pessoas presentes já votaram"):
            r["fim_fila"] = t
        elif msg.startswith("Votação encerrada") or msg.startswith("Inicio do Encerramento"):
            r["encerramento"] = t
    return r


def fuso_da_secao(uf, mun):
    """Horas a somar ao horário de Brasília para chegar no relógio da urna (regra fixa do TSE).

    Não se deduz o fuso pela hora de abertura: uma seção (ou um município inteiro) que abre
    atrasada pareceria estar em outro fuso."""
    return FUSO_MUNICIPIO.get(f"{uf}{mun}", FUSO_PADRAO.get(uf, 0))


def encerramento_brt(s):
    """Encerramento de uma linha de secoes_<t>t_<uf>.csv em segundos, horário de Brasília."""
    if not s["encerramento"]:
        return None
    return _seg(s["encerramento"]) - fuso_da_secao(s["uf"], s["mun"]) * 3600


# ---------------------------------------------------------------- boletim de urna (ASN.1 DER)

def _der(b, i, fim):
    nos = []
    while i < fim:
        tag = b[i]
        i += 1
        if tag & 0x1F == 0x1F:
            while b[i] & 0x80:
                i += 1
            i += 1
        ln = b[i]
        i += 1
        if ln & 0x80:
            n = ln & 0x7F
            ln = int.from_bytes(b[i:i + n], "big")
            i += n
        if i + ln > fim:
            raise ValueError("DER inválido")
        v = b[i:i + ln]
        if tag & 0x20:
            nos.append((tag, _der(b, i, i + ln)))
        elif tag == 0x04 and ln > 4 and v[0] == 0x30:
            # o conteúdo assinado do BU vem em DER dentro de um OCTET STRING; hashes que por
            # acaso começam com 0x30 não são DER válido e ficam como bytes
            try:
                nos.append((tag, _der(b, i, i + ln)))
            except (ValueError, IndexError):
                nos.append((tag, v))
        else:
            nos.append((tag, v))
        i += ln
    return nos


def _int(v):
    return int.from_bytes(v, "big", signed=True)


def _filhos(no):
    return no[1] if isinstance(no[1], list) else []


def ler_bu(conteudo, eleicao, cargo=1):
    """Lê o Boletim de Urna: horários de abertura/encerramento e votos do cargo (1 = Presidente)."""
    raiz = _der(conteudo, 0, len(conteudo))[0]
    bu = next(n for n in _filhos(raiz) if n[0] == 0x04 and isinstance(n[1], list))[1][0]
    r = {"abertura": None, "encerramento": None, "aptos": None, "biometricos": None, "votos": {}}
    for no in _filhos(bu):
        f = _filhos(no)
        if no[0] == 0xA0 and len(f) == 2 and all(x[0] == 0x1B for x in f):
            r["abertura"], r["encerramento"] = (x[1].decode() for x in f)
        elif no[0] == 0xA1 and len(f) >= 2:
            r["biometricos"] = _int(f[1][1])
        elif no[0] == 0x30 and f and f[0][0] == 0x30:
            for el in f:
                ef = _filhos(el)
                if ef and ef[0][0] == 0x02 and _int(ef[0][1]) == eleicao:
                    r["aptos"] = _int(ef[1][1])
                    _votos_do_cargo(el, cargo, r["votos"])
    return r


def _votos_do_cargo(no, cargo, saida):
    f = _filhos(no)
    # TotalVotosCargo: [1] código do cargo (1 = Presidente), ordem de impressão, lista de votáveis
    if (len(f) >= 3 and f[0][0] == 0x81 and _int(f[0][1]) == cargo and f[1][0] == 0x02
            and f[2][0] == 0x30):
        for voto in _filhos(f[2]):
            vf = {x[0]: x for x in _filhos(voto)}
            tipo = _int(vf[0x81][1])
            qtd = int.from_bytes(vf[0x82][1], "big")
            if tipo == 1 and 0xA3 in vf:
                chave = str(_int(_filhos(vf[0xA3])[-1][1]))
            else:
                chave = {2: "branco", 3: "nulo"}.get(tipo, f"tipo{tipo}")
            saida[chave] = saida.get(chave, 0) + qtd
        return
    for filho in f:
        if isinstance(filho[1], list):
            _votos_do_cargo(filho, cargo, saida)


def hora_iso_para_seg(iso):
    """'20261025T170123' -> segundos do dia."""
    return int(iso[9:11]) * 3600 + int(iso[11:13]) * 60 + int(iso[13:15])


# ---------------------------------------------------------------- métricas de uma seção

def metricas_da_secao(turno, uf, mun, nome_mun, zona, secao, com_bu=True):
    """Baixa log (e BU) de uma seção e devolve as métricas já em horário de Brasília."""
    base = {"turno": turno, "uf": uf, "mun": mun, "nome_mun": nome_mun, "zona": zona, "secao": secao}
    arqs = arquivos_da_secao(turno, uf, mun, zona, secao)
    if "log" not in arqs:
        return {**base, "erro": "sem log publicado"}
    bu = baixar(arqs["bu"]) if com_bu and "bu" in arqs else None
    return metricas_dos_arquivos(turno, uf, mun, nome_mun, zona, secao, baixar(arqs["log"]), bu)


def metricas_dos_arquivos(turno, uf, mun, nome_mun, zona, secao, conteudo_log, conteudo_bu=None):
    """Métricas de uma seção a partir dos bytes do log (.jez) e do boletim (bu.dat), em horário de Brasília."""
    base = {"turno": turno, "uf": uf, "mun": mun, "nome_mun": nome_mun, "zona": zona, "secao": secao}
    t = TURNOS[turno]
    log = ler_log(conteudo_log, t["data"], secao)
    bu = None
    if conteudo_bu is not None:
        try:
            bu = ler_bu(conteudo_bu, t["eleicao"])
        except Exception as e:  # BU com estrutura inesperada: segue só com o log
            bu = {"erro": str(e)}

    abertura = log["abertura"]
    if abertura is None and bu and bu.get("abertura"):
        abertura = hora_iso_para_seg(bu["abertura"])
    off = fuso_da_secao(uf, mun)
    brt = sorted(v - off * 3600 for v in log["votos"])

    # votos por faixa de 10 minutos (índice 0 = 00:00), em horário de Brasília
    faixas = {}
    for v in brt:
        k = v // 600
        faixas[k] = faixas.get(k, 0) + 1

    enc = None
    if bu and bu.get("encerramento"):
        enc = hora_iso_para_seg(bu["encerramento"]) - off * 3600
    elif log["encerramento"] is not None:
        enc = log["encerramento"] - off * 3600

    cab = sorted(log["cabine"])
    return {
        **base,
        "fuso": off,
        "abertura": None if abertura is None else abertura - off * 3600,
        "encerramento": enc,
        "comparecimento": len(brt),
        "aptos": bu.get("aptos") if bu else None,
        "votos_cand": bu.get("votos") if bu else None,
        "biometricos": log["biometricos"],
        "justificativas": log["justificativas"],
        "cabine_mediana": cab[len(cab) // 2] if cab else None,
        "ultimo_voto": brt[-1] if brt else None,
        "pos17": sum(1 for v in brt if v >= H17),
        "pos_aviso": sum(1 for v in brt if v >= AVISO_TSE),
        "pos19": sum(1 for v in brt if v >= H19),
        "faixas": faixas,
    }
