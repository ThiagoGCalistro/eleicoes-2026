# Eleições 2026 nas urnas

Site estático que mostra o 1º e o 2º turnos da eleição presidencial de 2026 a partir dos **logs** e dos **Boletins de Urna** publicados pelo TSE. Usa **só dados oficiais e de todas as urnas**: sem amostra, sem projeção, sem estimativa.

- **Resultado do 2º turno**: placar, comparecimento, abstenção, brancos e nulos.
- **1º turno × 2º turno**: participação, votos por hora, tempo na cabine, biometria, horário de fechamento das seções e quanto cada finalista cresceu por região.
- **Brancos, nulos e abstenção**: totais do dia inteiro nos dois turnos, no Brasil, por UF e por município (com busca e CSV).
- **2º turno em detalhe**: resultado por UF e por região, votos por hora.
- **Votos depois das 17h**: o que aconteceu com a prorrogação até as 19h; quantos votos houve após as 17h, 17h49 e 19h; quais cidades (com destaque para o Nordeste); o resultado oficial dessas seções; e se isso poderia mudar o resultado.
- **Urnas tardias**: seções ainda abertas às 17h49 (aviso do TSE) — quantas, onde, até que horas houve eleitor votando, a que horas fecharam, o resultado oficial delas e se já fechavam tarde no 1º turno. Lista completa em `site/urnas_tardias_2turno.csv`.

## Como ver

Online: <https://thiagogcalistro.github.io/eleicoes-2026/>

Localmente: abra `site/index.html` no navegador. Não precisa de servidor: os dados ficam em `site/dados.js` e `site/municipios.js`.

A cada push na `main` que altere a pasta `site/`, o workflow `.github/workflows/pages.yml` publica o site no GitHub Pages.

## Como atualizar os dados

Requer Python 3.10 ou mais novo. Não usa bibliotecas externas.

```bash
python pipeline/atualizar.py
```

O script roda as etapas em sequência e pode ser rodado de novo quantas vezes quiser, porque cada etapa pula o que já foi baixado:

| Script | O que faz | Fonte oficial |
|---|---|---|
| `baixar_resultados.py` | Resultado de Presidente, Brasil e UFs, nos dois turnos | API de resultados do TSE |
| `baixar_boletins.py --turno N` | Boletim de Urna de cada seção (resultado, abertura, encerramento) | Portal de Dados Abertos, "Boletim de Urna" |
| `baixar_municipios.py` | Resultado por município (eleitorado, abstenção, brancos, nulos, votos). Soma os boletins quando já baixados; senão usa a API (~3 pedidos/s) | Boletins / API de resultados |
| `processar_arquivos_urna.py --turno N` | Log e boletim de **todas** as urnas do turno, uma UF por vez (baixa, processa, apaga) | Portal de Dados Abertos, "Arquivos transmitidos para totalização" |
| `baixar_logs_api.py --turno N` | O mesmo, seção por seção, enquanto o pacote acima não é publicado (~1 milhão de pedidos, ~1 dia) | API de resultados do TSE |
| `gerar_dados.py` | Junta tudo em `site/dados.js`, `site/municipios.js` e nos CSVs | — |

Enquanto um turno não foi todo processado, o site mostra a contagem parcial **com a cobertura** ("X de Y seções") e não extrapola nada.

## Pastas

```
pipeline/   scripts em Python (só biblioteca padrão)
site/       o site: index.html, estilo.css, app.js e os dados gerados
dados/      downloads e arquivos intermediários (não vão para o git)
```

## Metodologia e limites

- **O voto é secreto.** O log registra a hora em que cada voto foi computado, mas não em quem a pessoa votou. Por isso não há divisão dos votos após as 17h entre candidatos. O site mostra o resultado oficial (boletim de urna) das seções onde houve voto após as 17h e o máximo que esses votos poderiam representar para cada candidato.
- **Horário de Brasília.** A votação segue o horário de Brasília (8h às 17h), mas o relógio das urnas marca a hora local: AC 6h às 15h; AM (exceto 11 municípios no fuso do AC), RR, RO, MT e MS 7h às 16h; Fernando de Noronha 9h às 18h. Os horários são convertidos com esse fuso fixo por município (`FUSO_PADRAO` e `FUSO_MUNICIPIO` em `pipeline/tse.py`).
- **Urnas substituídas.** Quando uma urna é trocada no meio do dia, o arquivo de log traz os logs de todas as urnas da seção, e os votos de todas são somados.
- **Seções agregadas** não têm log próprio; os eleitores delas aparecem no log da seção principal.
- **Exterior** (UF "ZZ") fica fora da análise de horário, porque cada país vota no seu horário local.
- **Brancos e nulos** são do voto para Presidente, em % do comparecimento; **abstenção** é em % do eleitorado apto. Votos em números de candidatura anulada contam como nulos, como no resultado oficial.
- **Conferência.** O comparecimento contado no log e os votos lidos do boletim de cada seção são comparados com o arquivo oficial de Boletins de Urna; no 1º turno bateram em todas as seções conferidas.
- **Limite de pedidos.** O site de resultados do TSE responde HTTP 429 quando recebe pedidos demais. Os scripts esperam, reduzem o ritmo e voltam a acelerar aos poucos; se o bloqueio persistir, basta rodar `atualizar.py` mais tarde.

## Fontes

- Resultados e arquivos de urna (API JSON usada pelo próprio site de resultados): <https://resultados.tse.jus.br>
- Portal de Dados Abertos do TSE: <https://dadosabertos.tse.jus.br>
- Cronologia da prorrogação: [Poder360](https://www.poder360.com.br/poder-eleicoes-2026/leia-a-cronologia-da-ampliacao-do-horario-de-votacao-no-2o-turno/), [O Tempo](https://www.otempo.com.br/eleicoes/2026/presidentes/2026/10/25/pela-1-vez-no-brasil-votacao-e-prorrogada-em-todo-o-pais-mas-ordem-chega-com-urnas-ja-lacradas), [CartaCapital](https://www.cartacapital.com.br/politica/lula-e-flavio-bolsonaro-pedem-ao-tse-prorrogacao-da-votacao-ate-as-19h/), [Exame](https://exame.com/brasil/tse-aprova-a-extensao-do-horario-de-votacao-do-2o-turno-para-as-19h/)

Análise independente, sem vínculo com o TSE.
