"""Obtém os logs de um turno pelo caminho que terminar primeiro e regenera o site.

Uso:  python pipeline/acompanhar_turno.py --turno 2 [--por-segundo 25] [--intervalo 15]

Roda o download seção por seção pela API (baixar_logs_api.py) e, a cada `--intervalo` minutos,
verifica se o TSE já publicou o pacote consolidado do turno no Portal de Dados Abertos. Se
publicou, interrompe a API e processa o pacote (processar_arquivos_urna.py), que é bem mais
rápido. Em qualquer caso, termina rodando gerar_dados.py.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

import processar_arquivos_urna

AQUI = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turno", type=int, choices=(1, 2), required=True)
    ap.add_argument("--por-segundo", type=float, default=25.0)
    ap.add_argument("--intervalo", type=float, default=15.0, help="minutos entre as verificações do portal")
    a = ap.parse_args()
    turno = str(a.turno)

    api = subprocess.Popen([sys.executable, str(AQUI / "baixar_logs_api.py"), "--turno", turno,
                            "--por-segundo", str(a.por_segundo)])
    print(f"download pela API iniciado (pid {api.pid})", flush=True)
    while api.poll() is None:
        time.sleep(a.intervalo * 60)
        try:
            publicado = bool(processar_arquivos_urna.recursos(a.turno))
        except Exception as e:  # portal fora do ar: tenta na próxima rodada
            print(f"não foi possível consultar o portal: {e}", flush=True)
            continue
        if publicado:
            print("pacote consolidado publicado: interrompendo a API e processando o pacote", flush=True)
            api.terminate()
            api.wait()
            subprocess.run([sys.executable, str(AQUI / "processar_arquivos_urna.py"), "--turno", turno])
            break
    else:
        print(f"download pela API terminou (código {api.returncode})", flush=True)
    return subprocess.run([sys.executable, str(AQUI / "gerar_dados.py")]).returncode


if __name__ == "__main__":
    sys.exit(main())
