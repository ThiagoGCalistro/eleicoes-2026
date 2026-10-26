"""Roda todas as etapas e regenera o site. Pode ser rodado de novo quantas vezes quiser:
cada etapa pula o que já foi baixado.

Uso:  python pipeline/atualizar.py

Para os logs de cada turno, usa o pacote consolidado do Portal de Dados Abertos quando o TSE já
o publicou; se ainda não, baixa seção por seção pela API de resultados (bem mais lento).
"""
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def rodar(script, *args):
    print(f"\n>> {script} {' '.join(args)}", flush=True)
    return subprocess.run([sys.executable, str(AQUI / script), *args]).returncode


def main():
    if rodar("baixar_resultados.py"):
        return 1
    for turno in ("1", "2"):
        rodar("baixar_boletins.py", "--turno", turno)
    rodar("baixar_municipios.py")
    for turno in ("1", "2"):
        if rodar("processar_arquivos_urna.py", "--turno", turno) == 2:
            rodar("baixar_logs_api.py", "--turno", turno)
    return rodar("gerar_dados.py")


if __name__ == "__main__":
    sys.exit(main())
