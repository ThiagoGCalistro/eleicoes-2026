/* Eleições 2026 nas urnas — monta textos, números e gráficos a partir de window.DADOS (dados.js). */
(function () {
  "use strict";
  const D = window.DADOS;
  if (!D) {
    document.getElementById("selo-dados").textContent = "dados.js não encontrado: rode python pipeline/gerar_dados.py";
    return;
  }

  // ------------------------------------------------------------------ formatação
  const nf = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
  const fmt = (n) => nf.format(Math.round(n));
  const pct = (x, d = 1) => (x == null ? "–" : x.toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d }) + "%");
  function compacto(n) {
    const a = Math.abs(n);
    if (a >= 1e6) return (n / 1e6).toLocaleString("pt-BR", { maximumFractionDigits: a >= 1e7 ? 1 : 2 }) + " mi";
    if (a >= 1e3) return (n / 1e3).toLocaleString("pt-BR", { maximumFractionDigits: a >= 1e4 ? 0 : 1 }) + " mil";
    return fmt(n);
  }
  // percentual com casas suficientes para não arredondar valores pequenos para zero
  const pctFino = (x) => (x == null ? "–" : x === 0 ? "0%" : x >= 1 ? pct(x, 1) : x >= 0.1 ? pct(x, 2) : x >= 0.001 ? pct(x, 3) : "<0,001%");
  const sinal = (n, f = fmt) => (n > 0 ? "+" : n < 0 ? "−" : "") + f(Math.abs(n));
  const seg = (s) => (s == null ? "–" : s < 90 ? Math.round(s) + " s" : (s / 60).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " min");
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const $ = (id) => document.getElementById(id);

  // ------------------------------------------------------------------ dados derivados
  const T = { 1: D.turnos["1"], 2: D.turnos["2"] }; // contagem dos logs (null se nada processado)
  const OF = { 1: D.oficial["1"], 2: D.oficial["2"] };
  const temLog = (t) => T[t] && T[t].secoes > 0;
  const completo = (t) => temLog(t) && T[t].cobertura.processadas >= T[t].cobertura.secoes;
  const cobTxt = (t) => !T[t] ? "nenhuma seção processada ainda"
    : completo(t) ? `todas as ${fmt(T[t].cobertura.secoes)} seções`
      : `${fmt(T[t].cobertura.processadas)} de ${fmt(T[t].cobertura.secoes)} seções (${pct((100 * T[t].cobertura.processadas) / T[t].cobertura.secoes, 0)}), processamento em andamento`;
  const AGUARDANDO = `<p class="nota">Aguardando o processamento dos logs oficiais deste turno.</p>`;
  const REGIOES = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"];
  const UFS = Object.keys(D.regiao_da_uf);
  const NOMES = { "13": "Lula", "22": "Flávio Bolsonaro" };
  const COR = { "13": "var(--lula)", "22": "var(--flavio)", branco: "var(--outros)", nulo: "var(--outros)" };
  const COR_TURNO = { 1: "var(--turno1)", 2: "var(--turno2)" };
  const nomeCand = (c) => NOMES[c.numero] || c.nome.toLowerCase().replace(/\b\p{L}/gu, (l) => l.toUpperCase());
  const final2 = OF[2].br.candidatos.slice(0, 2);
  const [venc, seg2] = final2;
  const margem = venc.votos - seg2.votos;
  const votosCand = (t, uf, numero) => ((OF[t][uf] || {}).candidatos || []).find((c) => c.numero === numero)?.votos || 0;

  // ------------------------------------------------------------------ dica (tooltip)
  const dica = $("dica");
  function mostrarDica(ev, html) {
    dica.innerHTML = html;
    dica.classList.add("ativa");
    const r = dica.getBoundingClientRect();
    let x = ev.clientX + 14, y = ev.clientY + 14;
    if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - 14;
    if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - 14;
    dica.style.left = Math.max(8, x) + "px";
    dica.style.top = Math.max(8, y) + "px";
  }
  const esconderDica = () => dica.classList.remove("ativa");
  const linhaDica = (cor, rot, val) =>
    `<div class="lin"><span class="chave" style="background:${cor}"></span>${esc(rot)}<em>${val}</em></div>`;

  function ligarDicas(box, dicas) {
    box.onmousemove = (ev) => {
      const m = ev.target.closest("[data-i]");
      if (m && box.contains(m)) mostrarDica(ev, dicas[+m.dataset.i]);
      else esconderDica();
    };
    box.onmouseleave = esconderDica;
    box.onfocusin = (ev) => {
      const m = ev.target.closest("[data-i]");
      if (!m) return;
      const r = m.getBoundingClientRect();
      mostrarDica({ clientX: r.right, clientY: r.top }, dicas[+m.dataset.i]);
    };
    box.onfocusout = esconderDica;
  }

  // ------------------------------------------------------------------ utilidades de gráfico
  function escalaBonita(max, n = 4) {
    if (max <= 0) return { max: 1, passo: 1 };
    const bruto = max / n, mag = Math.pow(10, Math.floor(Math.log10(bruto)));
    const passo = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((p) => p >= bruto);
    return { max: Math.ceil(max / passo) * passo, passo };
  }
  const largura = (box) => Math.max(280, box.clientWidth || 600);
  function legenda(id, itens) {
    $(id).innerHTML = itens.map(([cor, rot]) => `<span><span class="chave" style="background:${cor}"></span>${esc(rot)}</span>`).join("");
  }
  function tabela(id, cab, linhas) {
    $(id).innerHTML = `<table><thead><tr>${cab.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${linhas
      .map((l) => `<tr>${l.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  }
  // barra com ponta arredondada (4px) e base reta, horizontal a partir de x0
  function barraH(x0, y, w, h, cor, extra = "") {
    if (w <= 0) return "";
    const r = Math.min(4, w, h / 2);
    return `<path ${extra} fill="${cor}" d="M${x0},${y}h${w - r}a${r},${r} 0 0 1 ${r},${r}v${h - 2 * r}a${r},${r} 0 0 1 ${-r},${r}h${-(w - r)}z"/>`;
  }
  function barraV(x, yBase, w, h, cor, extra = "") {
    if (h <= 0) return "";
    const r = Math.min(4, h, w / 2);
    return `<path ${extra} fill="${cor}" d="M${x},${yBase}v${-(h - r)}a${r},${r} 0 0 1 ${r},${-r}h${w - 2 * r}a${r},${r} 0 0 1 ${r},${r}v${h - r}z"/>`;
  }

  // Linhas com marcadores; dica mostra todas as séries na mesma hora
  function graficoLinhas(id, rotulos, series, fmtY) {
    const box = $(id), W = largura(box), H = 260, m = { t: 12, r: 16, b: 28, l: 44 };
    const max = Math.max(...series.flatMap((s) => s.valores));
    const esc_ = escalaBonita(max), iw = W - m.l - m.r, ih = H - m.t - m.b;
    const x = (i) => m.l + (iw * i) / (rotulos.length - 1), y = (v) => m.t + ih - (ih * v) / esc_.max;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Gráfico de linhas">`;
    for (let v = 0; v <= esc_.max + 1e-9; v += esc_.passo)
      s += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}" stroke="${v ? "var(--grade)" : "var(--eixo)"}"/><text class="eixo-txt" x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${fmtY(v)}</text>`;
    rotulos.forEach((r, i) => { if (rotulos.length < 14 || i % 2 === 0) s += `<text class="eixo-txt" x="${x(i)}" y="${H - 8}" text-anchor="middle">${r}</text>`; });
    for (const se of series) {
      s += `<polyline fill="none" stroke="${se.cor}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" points="${se.valores.map((v, i) => `${x(i)},${y(v)}`).join(" ")}"/>`;
      se.valores.forEach((v, i) => (s += `<circle cx="${x(i)}" cy="${y(v)}" r="4" fill="${se.cor}" stroke="var(--superficie)" stroke-width="2"/>`));
    }
    const dicas = [], bw = iw / (rotulos.length - 1);
    rotulos.forEach((r, i) => {
      dicas.push(`<b>${r}</b>` + series.map((se) => linhaDica(se.cor, se.nome,
        fmtY(se.valores[i], true) + (se.absolutos ? ` · ${fmt(se.absolutos[i])} votos` : ""))).join(""));
      s += `<rect data-i="${i}" tabindex="0" x="${x(i) - bw / 2}" y="${m.t}" width="${bw}" height="${ih}" fill="transparent"><title>${r}</title></rect>`;
    });
    box.innerHTML = s + "</svg>";
    ligarDicas(box, dicas);
  }

  // Barras horizontais agrupadas: categorias × séries
  function graficoBarrasH(id, categorias, series, fmtV, opc = {}) {
    const box = $(id), W = largura(box);
    const esp = 14, gap = 2, grupo = series.length * esp + (series.length - 1) * gap, passo = grupo + 18;
    const rotW = opc.rotW || Math.min(150, Math.max(...categorias.map((c) => c.length)) * 7 + 8);
    const maiorRot = Math.max(...series.flatMap((s) => (s.rotulos || s.valores.map(fmtV)).map((x) => String(x).length)));
    const m = { t: 4, r: Math.max(70, maiorRot * 6.6 + 12), l: rotW }, H = m.t + categorias.length * passo;
    const max = opc.max || Math.max(...series.flatMap((s) => s.valores), 1), iw = W - m.l - m.r;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Gráfico de barras">`, dicas = [];
    s += `<line x1="${m.l}" x2="${m.l}" y1="${m.t}" y2="${H - 10}" stroke="var(--eixo)"/>`;
    categorias.forEach((c, ci) => {
      const y0 = m.t + ci * passo + 4;
      s += `<text class="rot-txt" x="${m.l - 8}" y="${y0 + grupo / 2 + 4}" text-anchor="end">${esc(c)}</text>`;
      series.forEach((se, si) => {
        const v = se.valores[ci], w = Math.max(v > 0 ? 1 : 0, (iw * v) / max), y = y0 + si * (esp + gap);
        const i = dicas.length, rot = se.rotulos ? se.rotulos[ci] : fmtV(v);
        dicas.push(`<b>${esc(c)}</b>` + (se.dicas ? se.dicas[ci] : linhaDica(se.cores ? se.cores[ci] : se.cor, se.nome, rot)));
        s += barraH(m.l, y, w, esp, se.cores ? se.cores[ci] : se.cor, `class="marca" data-i="${i}" tabindex="0"`);
        s += `<text class="val-txt" x="${m.l + w + 6}" y="${y + esp / 2 + 4}">${rot}</text>`;
      });
    });
    box.innerHTML = s + "</svg>";
    ligarDicas(box, dicas);
  }

  // Colunas (uma série, cor por item); rótulos girados quando são muitos
  function graficoColunas(id, itens, fmtV, opc = {}) {
    const box = $(id), muitos = itens.length > 14;
    const W = Math.max(largura(box), muitos ? itens.length * 30 + 60 : 0);
    const rotH = muitos ? Math.min(130, Math.max(...itens.map((i) => i.rot.length)) * 6.2 + 10) : 24;
    const m = { t: 18, r: 12, b: rotH, l: 48 }, H = (opc.altura || 240) + m.b;
    const max = Math.max(...itens.map((i) => i.valor), 1), e = escalaBonita(max);
    const iw = W - m.l - m.r, ih = H - m.t - m.b, banda = iw / itens.length, bw = Math.min(24, banda * 0.7);
    const y = (v) => m.t + ih - (ih * v) / e.max;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Gráfico de colunas">`, dicas = [];
    for (let v = 0; v <= e.max + 1e-9; v += e.passo)
      s += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}" stroke="${v ? "var(--grade)" : "var(--eixo)"}"/><text class="eixo-txt" x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${compacto(v)}</text>`;
    itens.forEach((it, i) => {
      const cx = m.l + banda * i + banda / 2, h = Math.max(it.valor > 0 ? 1 : 0, y(0) - y(it.valor));
      dicas.push(it.dica);
      s += barraV(cx - bw / 2, y(0), bw, h, it.cor, `class="marca" data-i="${i}" tabindex="0"`);
      const rotular = opc.rotularSoMaior ? it.valor === max : !muitos || i < 3;
      if (rotular) s += `<text class="val-txt" x="${cx}" y="${y(it.valor) - 5}" text-anchor="middle">${fmtV(it.valor)}</text>`;
      s += muitos
        ? `<text class="rot-txt" transform="translate(${cx + 4},${y(0) + 10}) rotate(-50)" text-anchor="end">${esc(it.rot)}</text>`
        : `<text class="eixo-txt" x="${cx}" y="${y(0) + 16}" text-anchor="middle">${esc(it.rot)}</text>`;
    });
    box.innerHTML = s + "</svg>";
    ligarDicas(box, dicas);
  }

  // Halteres: dois pontos por linha (1º e 2º turno) ligados por um traço
  function graficoHalter(id, linhas, fmtV) {
    // m.l deixa espaço para o nome da linha e para o rótulo à esquerda do ponto do 2º turno
    const box = $(id), W = largura(box), passo = 22, rotX = 32, m = { t: 22, r: 60, b: 4, l: 90 };
    const H = m.t + linhas.length * passo + m.b, iw = W - m.l - m.r;
    const vals = linhas.flatMap((l) => [l.a, l.b]), lo0 = Math.min(...vals), hi0 = Math.max(...vals);
    const { passo: tick } = escalaBonita(hi0 - lo0 || 1, 5);
    const lo = Math.floor(lo0 / tick) * tick, hi = Math.ceil(hi0 / tick) * tick || tick;
    const x = (v) => m.l + (iw * (v - lo)) / (hi - lo || 1);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Comparação entre turnos por linha">`, dicas = [];
    for (let v = lo; v <= hi + 1e-9; v += tick)
      s += `<line x1="${x(v)}" x2="${x(v)}" y1="${m.t - 6}" y2="${H - m.b}" stroke="var(--grade)"/><text class="eixo-txt" x="${x(v)}" y="${m.t - 10}" text-anchor="middle">${fmtV(v, true)}</text>`;
    linhas.forEach((l, i) => {
      const y = m.t + i * passo + passo / 2;
      dicas.push(`<b>${esc(l.nome || l.rot)}</b>${linhaDica(COR_TURNO[1], "1º turno", fmtV(l.a))}${linhaDica(COR_TURNO[2], "2º turno", fmtV(l.b))}` +
        `<div class="lin">Variação<em>${sinal(l.b - l.a, (n) => n.toLocaleString("pt-BR", { maximumFractionDigits: 2 }))} p.p.</em></div>`);
      s += `<g class="marca" data-i="${i}" tabindex="0"><rect x="0" y="${y - passo / 2}" width="${W}" height="${passo}" fill="transparent"/>`;
      s += `<text class="rot-txt" x="${rotX}" y="${y + 4}" text-anchor="end">${esc(l.rot)}</text>`;
      s += `<line x1="${x(l.a)}" x2="${x(l.b)}" y1="${y}" y2="${y}" stroke="var(--eixo)" stroke-width="2"/>`;
      s += `<circle cx="${x(l.a)}" cy="${y}" r="5" fill="${COR_TURNO[1]}" stroke="var(--superficie)" stroke-width="2"/>`;
      s += `<circle cx="${x(l.b)}" cy="${y}" r="5" fill="${COR_TURNO[2]}" stroke="var(--superficie)" stroke-width="2"/>`;
      // rótulo ao lado do ponto do 2º turno, do lado de fora do traço
      s += l.b >= l.a
        ? `<text class="val-txt" x="${x(l.b) + 10}" y="${y + 4}">${fmtV(l.b)}</text></g>`
        : `<text class="val-txt" x="${x(l.b) - 10}" y="${y + 4}" text-anchor="end">${fmtV(l.b)}</text></g>`;
    });
    box.innerHTML = s + "</svg>";
    ligarDicas(box, dicas);
  }

  // Barras 100% empilhadas, uma por linha
  function grafico100(id, linhas, partesNomes, opc = {}) {
    const box = $(id), W = largura(box), alt = 16, passo = 24, m = { t: 4, r: 8, l: 40 };
    const H = m.t + linhas.length * passo, iw = W - m.l - m.r;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Barras 100% empilhadas">`, dicas = [];
    s += `<line x1="${m.l + iw / 2}" x2="${m.l + iw / 2}" y1="0" y2="${H}" stroke="var(--tinta-3)" stroke-width="1"/>`;
    linhas.forEach((l, li) => {
      const y = m.t + li * passo, total = l.partes.reduce((a, p) => a + p.valor, 0) || 1;
      s += `<text class="rot-txt" x="${m.l - 8}" y="${y + alt / 2 + 4}" text-anchor="end">${esc(l.rot)}</text>`;
      let x = m.l;
      const i = dicas.length;
      dicas.push(`<b>${esc(l.nome || l.rot)}</b>` + l.partes.map((p, pi) => linhaDica(p.cor, partesNomes[pi],
        opc.soPercentual ? pct((100 * p.valor) / total) : `${pct((100 * p.valor) / total)} · ${fmt(p.valor)}`)).join(""));
      l.partes.forEach((p, pi) => {
        const w = (iw * p.valor) / total - (pi < l.partes.length - 1 ? 2 : 0);
        const r = 4, ult = pi === l.partes.length - 1, pri = pi === 0;
        s += `<path class="marca" data-i="${i}" tabindex="${pi ? -1 : 0}" fill="${p.cor}" d="M${x + (pri ? r : 0)},${y}h${w - (pri ? r : 0) - (ult ? r : 0)}${ult ? `a${r},${r} 0 0 1 ${r},${r}v${alt - 2 * r}a${r},${r} 0 0 1 ${-r},${r}` : `v${alt}`}h${-(w - (pri ? r : 0) - (ult ? r : 0))}${pri ? `a${r},${r} 0 0 1 ${-r},${-r}v${-(alt - 2 * r)}a${r},${r} 0 0 1 ${r},${-r}` : `v${-alt}`}z"/>`;
        const txt = pct((100 * p.valor) / total, 0);
        if (w > txt.length * 7 + 12) s += `<text x="${pri ? x + 6 : x + w - 6}" y="${y + alt / 2 + 4}" text-anchor="${pri ? "start" : "end"}" fill="#fff" font-size="11" font-weight="600" pointer-events="none">${txt}</text>`;
        x += w + 2;
      });
    });
    box.innerHTML = s + "</svg>";
    ligarDicas(box, dicas);
  }

  // ------------------------------------------------------------------ seções
  function topo() {
    const st = (t) => (completo(t) ? "completo" : temLog(t) ? `${pct((100 * T[t].cobertura.processadas) / T[t].cobertura.secoes, 0)} das urnas` : "aguardando");
    $("selo-dados").textContent = `Atualizado em ${D.gerado_em} · logs das urnas: 1º turno ${st(1)}, 2º turno ${st(2)}`;
    $("rodape").textContent = `Dados processados em ${D.gerado_em}. Resultado oficial gerado pelo TSE em ${OF[2].br.gerado_em} (2º turno) e ${OF[1].br.gerado_em} (1º turno).`;
  }

  function resultado() {
    const b = OF[2].br;
    $("resultado-sub").textContent =
      `${nomeCand(venc)} foi eleito com ${pct(venc.pct, 2)} dos votos válidos, ${fmt(margem)} votos à frente de ${nomeCand(seg2)}.`;
    $("placar").innerHTML = final2.map((c) => `
      <div class="cand">
        <span class="nome"><span class="chave" style="background:${COR[c.numero]}"></span>${esc(nomeCand(c))} · ${esc(c.partido)} ${c.numero}</span>
        <span class="pct">${pct(c.pct, 2)}</span>
        <span class="votos">${fmt(c.votos)} votos · ${esc(c.situacao)}</span>
      </div>`).join("") +
      `<div style="grid-column:1/-1"><div class="barra-placar">${final2.map((c) => `<span style="width:calc(${c.pct}% - 1px);background:${COR[c.numero]}"></span>`).join("")}</div><div class="marco50"><span>50%</span></div></div>`;
    $("tiles-resultado").innerHTML = [
      ["Comparecimento", fmt(b.comparecimento), `${pct(b.pct_comparecimento)} dos ${compacto(b.aptos)} aptos`],
      ["Abstenção", fmt(b.abstencoes), pct(b.pct_abstencao) + " do eleitorado"],
      ["Votos brancos", fmt(b.brancos), pct(b.pct_brancos) + " dos votos"],
      ["Votos nulos", fmt(b.nulos), pct(b.pct_nulos) + " dos votos"],
    ].map(tile).join("");
  }

  function tile([rot, val, det]) {
    return `<div class="tile"><div class="rot">${rot}</div><div class="val">${val}</div>${det ? `<div class="det">${det}</div>` : ""}</div>`;
  }

  function comparativo() {
    const b1 = OF[1].br, b2 = OF[2].br;
    const bn = (b) => b.brancos + b.nulos;
    const doLog = (t, f) => (temLog(t) ? f(T[t]) : "–");
    $("tiles-comparativo").innerHTML = [
      ["Comparecimento no 2º turno", pct(b2.pct_comparecimento), `1º turno: ${pct(b1.pct_comparecimento)} (${sinal(b2.comparecimento - b1.comparecimento, compacto)} eleitores)`],
      ["Abstenção no 2º turno", pct(b2.pct_abstencao), `1º turno: ${pct(b1.pct_abstencao)}`],
      ["Brancos e nulos no 2º turno", compacto(bn(b2)), `1º turno: ${compacto(bn(b1))}`],
      ["Tempo mediano na cabine", doLog(2, (x) => seg(x.cabine_mediana_seg)), `1º turno: ${doLog(1, (x) => seg(x.cabine_mediana_seg))} (6 votos por eleitor)`],
      ["Eleitores liberados por biometria", doLog(2, (x) => pct(x.pct_biometria)), `1º turno: ${doLog(1, (x) => pct(x.pct_biometria))}`],
    ].map(tile).join("");

    const turnosLog = [1, 2].filter(temLog);
    legenda("leg-curva", turnosLog.map((t) => [COR_TURNO[t], `${t}º turno`]));
    const horas = Array.from({ length: 13 }, (_, i) => (i === 12 ? "20h+" : 8 + i + "h"));
    if (turnosLog.length) {
      graficoLinhas("g-curva", horas, turnosLog.map((t) => ({
        nome: `${t}º turno`, cor: COR_TURNO[t],
        valores: T[t].curva_horaria.map((h) => h.pct), absolutos: T[t].curva_horaria.map((h) => h.votos),
      })), (v, dica) => (dica ? pctFino(v) : pct(v, 0)));
      tabela("t-curva", ["Hora (Brasília)", ...turnosLog.map((t) => `${t}º turno`)],
        horas.map((h, i) => [h, ...turnosLog.map((t) => `${pctFino(T[t].curva_horaria[i].pct)} (${fmt(T[t].curva_horaria[i].votos)} votos)`)]));
    } else $("g-curva").innerHTML = AGUARDANDO;

    legenda("leg-enc", turnosLog.map((t) => [COR_TURNO[t], `${t}º turno`]));
    if (turnosLog.length) {
      const faixas = T[turnosLog[0]].encerramento.map((f) => f.faixa);
      graficoBarrasH("g-enc", faixas, turnosLog.map((t) => ({ nome: `${t}º turno`, cor: COR_TURNO[t], valores: T[t].encerramento.map((f) => f.pct) })),
        (v) => pct(v), { rotW: 110 });
      tabela("t-enc", ["Encerramento", ...turnosLog.map((t) => `${t}º turno (seções)`)],
        faixas.map((f, i) => [f, ...turnosLog.map((t) => `${fmt(T[t].encerramento[i].secoes)} (${pct(T[t].encerramento[i].pct)})`)]));
    } else $("g-enc").innerHTML = AGUARDANDO;
    $("nota-enc").textContent = `1º turno: ${cobTxt(1)}. 2º turno: ${cobTxt(2)}. O encerramento acontece depois do último eleitor, por isso quase toda seção fecha após as 17h.`;
    $("nota-curva").textContent = `1º turno: ${cobTxt(1)}. 2º turno: ${cobTxt(2)}.`;

    // ganho de votos entre os turnos: por região (mais o exterior, para fechar 100% do ganho)
    const ufsReg = (r) => UFS.filter((u) => D.regiao_da_uf[u] === r);
    const LOCAIS = [...REGIOES.map((r) => ({ nome: r, ufs: ufsReg(r) })), { nome: "Exterior", ufs: null }];
    const votosLocal = (t, num, l) => (l.ufs ? l.ufs.reduce((a, uf) => a + votosCand(t, uf, num), 0)
      : votosCand(t, "br", num) - UFS.reduce((a, uf) => a + votosCand(t, uf, num), 0));
    const pct1 = (x) => pct(Math.abs(x) < 0.05 ? 0 : x, 1), varPct = (g, base) => (base ? sinal((100 * g) / base, pct1) : "–");
    legenda("leg-ganho", final2.map((c) => [COR[c.numero], nomeCand(c)]));
    graficoBarrasH("g-ganho", LOCAIS.map((l) => l.nome), final2.map((c) => {
      const total = votosCand(2, "br", c.numero) - votosCand(1, "br", c.numero);
      const g = LOCAIS.map((l) => votosLocal(2, c.numero, l) - votosLocal(1, c.numero, l));
      const base = LOCAIS.map((l) => votosLocal(1, c.numero, l));
      return {
        nome: nomeCand(c), cor: COR[c.numero], valores: g,
        rotulos: g.map((v) => `${sinal(v, compacto)} · ${pct1((100 * v) / total)}`),
        dicas: g.map((v, i) => linhaDica(COR[c.numero], nomeCand(c), `${sinal(v)} votos`) +
          `<div class="lin">Parte do crescimento total dele<em>${pct1((100 * v) / total)}</em></div>` +
          `<div class="lin">Em relação ao 1º turno nesse local<em>${varPct(v, base[i])}</em></div>`),
      };
    }), (v) => sinal(v, compacto), { rotW: 104 });
    $("nota-ganho").textContent = final2.map((c) => {
      const total = votosCand(2, "br", c.numero) - votosCand(1, "br", c.numero);
      return `${nomeCand(c)}: ${sinal(total)} votos no total (${varPct(total, votosCand(1, "br", c.numero))} sobre o 1º turno)`;
    }).join(" · ") + ". O percentual ao lado de cada barra é a parte desse crescimento que veio de cada local.";

    const linha = (rot, num1, num2, cands) => [rot, ...cands.flatMap((c) => {
      const g = num2(c.numero) - num1(c.numero), total = votosCand(2, "br", c.numero) - votosCand(1, "br", c.numero);
      return [sinal(g), pct1((100 * g) / total), varPct(g, num1(c.numero))];
    })];
    tabela("t-ganho", ["Local", ...final2.flatMap((c) => [`${nomeCand(c)}: ganho`, "% do ganho total", "vs. 1º turno"])], [
      ...LOCAIS.map((l) => linha(`<strong>${l.nome}</strong>`, (n) => votosLocal(1, n, l), (n) => votosLocal(2, n, l), final2)),
      linha("<strong>Brasil</strong>", (n) => votosCand(1, "br", n), (n) => votosCand(2, "br", n), final2),
      ...UFS.slice().sort().map((uf) => linha(`${uf.toUpperCase()} · ${D.regiao_da_uf[uf]}`, (n) => votosCand(1, uf, n), (n) => votosCand(2, uf, n), final2)),
    ]);
  }

  let medidaBna = "abst";
  function brancosNulos() {
    const b1 = OF[1].br, b2 = OF[2].br;
    const MED = {
      br: { nome: "Brancos", n: (o) => o.brancos, p: (o) => o.pct_brancos, base: "dos votos" },
      nu: { nome: "Nulos", n: (o) => o.nulos, p: (o) => o.pct_nulos, base: "dos votos" },
      abst: { nome: "Abstenção", n: (o) => o.abstencoes, p: (o) => o.pct_abstencao, base: "do eleitorado" },
    };
    const soma = (o) => o.brancos + o.nulos + o.abstencoes;
    $("tiles-bna").innerHTML = ["br", "nu", "abst"].map((k) => {
      const M = MED[k];
      return tile([`${M.nome} no 2º turno`, fmt(M.n(b2)),
        `${pct(M.p(b2))} ${M.base} · 1º turno: ${fmt(M.n(b1))} (${pct(M.p(b1))}) · ${sinal(M.n(b2) - M.n(b1), compacto)}`]);
    }).join("") + tile(["Somando os três no 2º turno", fmt(soma(b2)),
      `${pct((100 * soma(b2)) / b2.aptos)} do eleitorado · 1º turno: ${fmt(soma(b1))} (${pct((100 * soma(b1)) / b1.aptos)})`]);

    // um gráfico por indicador, cada um na sua escala
    $("g-bna-multiplos").innerHTML = ["br", "nu", "abst"].map((k) =>
      `<div class="cartao"><h3>${MED[k].nome}</h3><p class="desc">Total do dia, ${MED[k].base === "dos votos" ? "% dos votos" : "% do eleitorado"}.</p><div class="grafico" id="g-bna-${k}"></div></div>`).join("");
    for (const k of ["br", "nu", "abst"]) {
      const M = MED[k];
      graficoBarrasH(`g-bna-${k}`, ["1º turno", "2º turno"], [{
        nome: M.nome, cores: [COR_TURNO[1], COR_TURNO[2]], valores: [M.n(b1), M.n(b2)],
        rotulos: [`${compacto(M.n(b1))} · ${pct(M.p(b1))}`, `${compacto(M.n(b2))} · ${pct(M.p(b2))}`],
      }], compacto, { rotW: 70 });
    }

    // por UF
    legenda("leg-halter", [[COR_TURNO[1], "1º turno"], [COR_TURNO[2], "2º turno"]]);
    const fmtP = (v, eixo) => pct(v, eixo && Number.isInteger(+v.toFixed(6)) ? 0 : 1);
    const desenhar = () => {
      const M = MED[medidaBna];
      $("desc-halter").textContent = `${M.nome} em cada UF, em % ${M.base}. Cada linha liga o 1º turno ao 2º; ordenado pelo 2º turno.`;
      graficoHalter("g-halter", UFS.filter((uf) => OF[1][uf] && OF[2][uf])
        .map((uf) => ({ rot: uf.toUpperCase(), nome: `${uf.toUpperCase()} · ${D.regiao_da_uf[uf]}`, a: M.p(OF[1][uf]), b: M.p(OF[2][uf]) }))
        .sort((p, q) => q.b - p.b), fmtP);
      desenharMunicipios();
    };
    tabela("t-bna-uf", ["UF", "Região", "Abstenção 1º", "Abstenção 2º", "Brancos 1º", "Brancos 2º", "Nulos 1º", "Nulos 2º"],
      UFS.slice().sort().map((uf) => [uf.toUpperCase(), D.regiao_da_uf[uf],
        ...["abst", "br", "nu"].flatMap((k) => [`${fmt(MED[k].n(OF[1][uf]))} (${pct(MED[k].p(OF[1][uf]))})`, `${fmt(MED[k].n(OF[2][uf]))} (${pct(MED[k].p(OF[2][uf]))})`])]));

    // por município
    const MU = window.MUNICIPIOS;
    const COL = { abst: [3, 4], br: [5, 6], nu: [7, 8] };
    let busca = "";
    function desenharMunicipios() {
      if (!MU) { $("t-bna-mun").innerHTML = `<p class="nota">municipios.js não encontrado: rode python pipeline/baixar_municipios.py e gerar_dados.py.</p>`; return; }
      const [c1, c2] = COL[medidaBna], M = MED[medidaBna];
      const norm = (s) => s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
      let lista = MU.linhas;
      if (busca) lista = lista.filter((l) => norm(`${l[1]} ${l[0]}`).includes(busca));
      else lista = lista.filter((l) => l[2] >= 1000);
      lista = lista.slice().sort((p, q) => (q[c2] - q[c1]) - (p[c2] - p[c1])).slice(0, 100);
      $("desc-bna-mun").textContent = busca
        ? `Resultados da busca (até 100).`
        : `Os 100 municípios em que ${M.nome.toLowerCase()} mais subiu entre os turnos, entre os ${fmt(MU.linhas.filter((l) => l[2] >= 1000).length)} com pelo menos 1.000 eleitores. Use a busca para ver qualquer município.`;
      const pp = (n) => sinal(n, (x) => x.toLocaleString("pt-BR", { maximumFractionDigits: 1 })) + " p.p.";
      tabela("t-bna-mun", ["Município", "UF", "Eleitores", `${M.nome} 1º`, `${M.nome} 2º`, "Variação", "Abstenção 2º", "Brancos 2º", "Nulos 2º"],
        lista.map((l) => [esc(l[1]), l[0].toUpperCase(), fmt(l[2]), pct(l[c1]), pct(l[c2]), pp(l[c2] - l[c1]), pct(l[4]), pct(l[6]), pct(l[8])]));
    }
    $("busca-bna").oninput = (ev) => { busca = ev.target.value.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().trim(); desenharMunicipios(); };
    document.querySelectorAll("[data-bna]").forEach((b) => (b.onclick = () => {
      medidaBna = b.dataset.bna;
      document.querySelectorAll("[data-bna]").forEach((x) => x.setAttribute("aria-pressed", x === b));
      desenhar();
    }));
    desenhar();
  }

  function segundoTurno() {
    const b = OF[2].br, a = T[2];
    const tiles = [["Eleitores aptos", fmt(b.aptos), "resultado oficial"]];
    if (temLog(2)) {
      const curva = a.curva_horaria, pico = curva.reduce((p, h) => (h.pct > p.pct ? h : p));
      const ateMeioDia = curva.filter((h) => h.hora < 12).reduce((s, h) => s + h.pct, 0);
      const base = completo(2) ? "" : ` · ${fmt(a.cobertura.processadas)} seções processadas`;
      tiles.push(
        ["Hora de maior movimento", `${pico.hora}h às ${pico.hora + 1}h`, `${pct(pico.pct)} dos votos do dia${base}`],
        ["Votaram até o meio-dia", pct(ateMeioDia, 0), `dos eleitores que compareceram${base}`],
        ["Tempo mediano na cabine", seg(a.cabine_mediana_seg), "mediana das seções, só Presidente"],
        ["Liberados por biometria", pct(a.pct_biometria), "o resto pelo documento e dados pessoais"]);
    }
    $("tiles-2t").innerHTML = tiles.map(tile).join("");

    // resultado por UF
    const [c1, c2] = final2;
    const linhas = UFS.map((uf) => ({ uf, v1: votosCand(2, uf, c1.numero), v2: votosCand(2, uf, c2.numero) }))
      .sort((p, q) => q.v1 / (q.v1 + q.v2) - p.v1 / (p.v1 + p.v2));
    legenda("leg-uf", final2.map((c) => [COR[c.numero], nomeCand(c)]));
    grafico100("g-uf", linhas.map((l) => ({
      rot: l.uf.toUpperCase(), nome: `${l.uf.toUpperCase()} · ${D.regiao_da_uf[l.uf]}`,
      partes: [{ valor: l.v1, cor: COR[c1.numero] }, { valor: l.v2, cor: COR[c2.numero] }],
    })), final2.map(nomeCand));
    tabela("t-uf", ["UF", "Região", nomeCand(c1), "%", nomeCand(c2), "%", "Abstenção"], linhas.map((l) => [
      l.uf.toUpperCase(), D.regiao_da_uf[l.uf], fmt(l.v1), pct((100 * l.v1) / (l.v1 + l.v2), 2), fmt(l.v2), pct((100 * l.v2) / (l.v1 + l.v2), 2), pct(OF[2][l.uf]?.pct_abstencao)]));

    // votos por hora, contados nos logs
    $("nota-hora2").textContent = `Contagem nos logs: ${cobTxt(2)}.`;
    if (temLog(2)) {
      const curva = a.curva_horaria;
      const itens = curva.map((h) => {
        const v = h.votos, rot = h.hora === 20 ? "20h+" : h.hora + "h";
        return { rot, valor: v, cor: "var(--turno2)", dica: `<b>${rot}</b>${linhaDica("var(--turno2)", "Votos", fmt(v))}${linhaDica("var(--turno2)", "Parte do dia", pctFino(h.pct))}` };
      });
      graficoColunas("g-hora2", itens, compacto, { altura: 200, rotularSoMaior: true });
      tabela("t-hora2", ["Hora", "Votos", "Parte do dia"], itens.map((i, k) => [i.rot, fmt(i.valor), pctFino(curva[k].pct)]));
    } else $("g-hora2").innerHTML = AGUARDANDO;

    // por região
    const ufsReg = (r) => UFS.filter((u) => D.regiao_da_uf[u] === r);
    const porReg = (num) => REGIOES.map((r) => ufsReg(r).reduce((s, uf) => s + votosCand(2, uf, num), 0));
    legenda("leg-reg2", final2.map((c) => [COR[c.numero], nomeCand(c)]));
    graficoBarrasH("g-reg2", REGIOES, final2.map((c) => ({ nome: nomeCand(c), cor: COR[c.numero], valores: porReg(c.numero) })), compacto, { rotW: 104 });
    const r1 = porReg(c1.numero), r2 = porReg(c2.numero);
    tabela("t-reg2", ["Região", nomeCand(c1), "%", nomeCand(c2), "%"], REGIOES.map((r, i) => [r, fmt(r1[i]), pct((100 * r1[i]) / (r1[i] + r2[i]), 2), fmt(r2[i]), pct((100 * r2[i]) / (r1[i] + r2[i]), 2)]));
  }

  let filtroCidades = "todas";
  function apos17h() {
    const p1 = T[1], p2 = T[2];
    const status = (t) => (completo(t) ? `<strong>${t}º turno: contagem completa</strong> (${cobTxt(t)})`
      : `<strong>${t}º turno: ${temLog(t) ? "contagem parcial" : "aguardando"}</strong> (${cobTxt(t)}; os números abaixo valem só para as seções já processadas, nada é projetado)`);
    $("aviso-pos17").innerHTML = `<span>ⓘ</span><span>Fonte: log oficial de cada urna, publicado pelo TSE. ${status(2)}. ${status(1)}.</span>`;
    if (!temLog(2)) {
      ["tiles-pos17", "g-cidades", "g-reg17", "g-faixas17", "g-cand17", "impacto", "g-escala", "conclusao"].forEach((id) => ($(id).innerHTML = ""));
      $("g-cidades").innerHTML = AGUARDANDO;
      return;
    }
    const pctSec = (p) => pct((100 * p.secoes_pos17) / p.secoes, 1);
    $("tiles-pos17").innerHTML = [
      ["Votos depois das 17h no 2º turno", fmt(p2.pos17), `${pct((100 * p2.pos17) / p2.comparecimento, 3)} dos votos dessas seções`],
      ["Seções com algum voto após 17h", fmt(p2.secoes_pos17), `${pctSec(p2)} das seções`],
      ["Depois do aviso do TSE (17h49)", fmt(p2.pos_aviso), "votos no 2º turno"],
      ["Às 19h ou depois", fmt(p2.pos19), "votos no 2º turno"],
      ["Para comparar: 1º turno", temLog(1) ? fmt(p1.pos17) : "–",
        temLog(1) ? `votos após 17h, sem prorrogação (${pct((100 * p1.pos17) / p1.comparecimento, 1)}; ${fmt(p1.secoes_pos17)} seções)` : "aguardando"],
    ].map(tile).join("");

    // cidades
    const todas = p2.municipios || [];
    $("desc-cidades").textContent = `Votos computados a partir das 17h00 (horário de Brasília), somando todas as seções processadas de cada cidade. ${fmt(todas.length)} cidades tiveram voto após as 17h; o gráfico mostra as 30 com mais votos.`;
    legenda("leg-cidades", [["var(--nordeste)", "Nordeste"], ["var(--outros)", "Outras regiões"]]);
    const desenharCidades = () => {
      const lista = todas.filter((m) => filtroCidades === "todas" || (filtroCidades === "nordeste") === (m.regiao === "Nordeste"));
      const top = lista.slice(0, 30);
      if (!top.length) { $("g-cidades").innerHTML = `<p class="nota">Nenhuma cidade neste filtro.</p>`; return; }
      graficoColunas("g-cidades", top.map((m) => ({
        rot: `${m.nome} (${m.uf.toUpperCase()})`, valor: m.pos17,
        cor: m.regiao === "Nordeste" ? "var(--nordeste)" : "var(--outros)",
        dica: `<b>${esc(m.nome)} · ${m.uf.toUpperCase()}</b>` +
          linhaDica("var(--tinta-3)", "Votos após 17h", fmt(m.pos17)) +
          linhaDica("var(--tinta-3)", "Após 17h49", fmt(m.pos_aviso)) +
          linhaDica("var(--tinta-3)", "Às 19h ou depois", fmt(m.pos19)) +
          linhaDica("var(--tinta-3)", "Seções com voto após 17h", fmt(m.secoes_pos17)),
      })), fmt, { altura: 220 });
    };
    document.querySelectorAll("[data-filtro]").forEach((b) => (b.onclick = () => {
      filtroCidades = b.dataset.filtro;
      document.querySelectorAll("[data-filtro]").forEach((x) => x.setAttribute("aria-pressed", x === b));
      desenharCidades();
    }));
    desenharCidades();
    const linhasCid = todas.map((m) => [esc(m.nome), m.uf.toUpperCase(), m.regiao, fmt(m.secoes_pos17), fmt(m.pos17), fmt(m.pos_aviso), fmt(m.pos19),
      ...final2.map((c) => (m.resultado[c.numero] != null ? fmt(m.resultado[c.numero]) : "–"))]);
    const cabCid = ["Cidade", "UF", "Região", "Seções c/ voto após 17h", "Após 17h", "Após 17h49", "19h ou depois",
      ...final2.map((c) => `${nomeCand(c)} nessas seções`)];
    tabela("t-cidades", cabCid, linhasCid);
    $("busca-cidade").oninput = (ev) => {
      const q = ev.target.value.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
      tabela("t-cidades", cabCid, linhasCid.filter((l) => (l[0] + " " + l[1]).normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().includes(q)));
    };

    // por região e faixas de horário, nos turnos já processados
    const turnosLog = [1, 2].filter(temLog);
    const reg = (t) => REGIOES.map((r) => (T[t].regioes.find((x) => x.regiao === r) || { pos17: 0 }).pos17);
    legenda("leg-reg17", turnosLog.map((t) => [COR_TURNO[t], `${t}º turno`]));
    graficoBarrasH("g-reg17", REGIOES, turnosLog.map((t) => ({ nome: `${t}º turno`, cor: COR_TURNO[t], valores: reg(t) })), fmt, { rotW: 104 });
    tabela("t-reg17", ["Região", ...turnosLog.map((t) => `${t}º turno`)], REGIOES.map((r, i) => [r, ...turnosLog.map((t) => fmt(reg(t)[i]))]));

    const faixas = (p) => [p.pos17 - p.pos_aviso, p.pos_aviso - p.pos19, p.pos19];
    const nomesF = ["17h00–17h49", "17h49–19h", "19h ou depois"];
    legenda("leg-faixas17", turnosLog.map((t) => [COR_TURNO[t], `${t}º turno`]));
    graficoBarrasH("g-faixas17", nomesF, turnosLog.map((t) => ({ nome: `${t}º turno`, cor: COR_TURNO[t], valores: faixas(T[t]) })), fmt, { rotW: 110 });
    tabela("t-faixas17", ["Horário do voto", ...turnosLog.map((t) => `${t}º turno`)], nomesF.map((n, i) => [n, ...turnosLog.map((t) => fmt(faixas(T[t])[i]))]));

    // candidatos: o voto é secreto, então só o que dá para afirmar com os dados oficiais
    const res = p2.resultado_secoes_pos17, totRes = Object.values(res).reduce((s, v) => s + v, 0) || 1;
    const outros = (res.branco || 0) + (res.nulo || 0);
    legenda("leg-cand17", [...final2.map((c) => [COR[c.numero], nomeCand(c)]), ["var(--outros)", "Brancos e nulos"]]);
    grafico100("g-cand17", [{
      rot: "", nome: `Resultado oficial nas ${fmt(p2.secoes_pos17_com_resultado)} seções com voto após 17h`,
      partes: [...final2.map((c) => ({ valor: res[c.numero] || 0, cor: COR[c.numero] })), { valor: outros, cor: "var(--outros)" }],
    }], [...final2.map(nomeCand), "Brancos e nulos"]);
    $("impacto").innerHTML = final2.map((c) => tile([
      `${esc(nomeCand(c))}: máximo possível`,
      pct((100 * p2.pos17) / c.votos, 3),
      `do total dele (${fmt(c.votos)}) se todos os ${fmt(p2.pos17)} votos após 17h tivessem sido para ele`,
    ])).join("") + tile(["Resultado nessas seções", final2.map((c) => `${nomeCand(c).split(" ")[0]} ${pct((100 * (res[c.numero] || 0)) / totRes, 1)}`).join(" · "),
      `todos os votos do dia nessas seções, não só os de depois das 17h`]);
    tabela("t-cand17", ["", ...final2.map(nomeCand), "Brancos e nulos"], [
      ["Votos nas seções com voto após 17h (dia todo)", ...final2.map((c) => fmt(res[c.numero] || 0)), fmt(outros)],
      ["% nessas seções", ...final2.map((c) => pct((100 * (res[c.numero] || 0)) / totRes, 2)), pct((100 * outros) / totRes, 2)],
      ["Máximo possível dos votos após 17h, em % do total do candidato", ...final2.map((c) => pct((100 * p2.pos17) / c.votos, 3)), "–"],
    ]);

    // escala: margem × votos após 17h
    graficoBarrasH("g-escala", ["Diferença final", "Votos após 17h"], [{
      nome: "Votos", cores: ["var(--outros)", "var(--turno2)"], valores: [margem, p2.pos17],
    }], fmt, { rotW: 120 });
    const sobra = margem - p2.pos17;
    const parcial = completo(2) ? "" : ` (contagem parcial: ${cobTxt(2)})`;
    $("conclusao").innerHTML = sobra > 0
      ? `A diferença entre os candidatos foi de <strong>${fmt(margem)}</strong> votos. Todos os votos dados depois das 17h somam <strong>${fmt(p2.pos17)}</strong>${parcial}, ${pct((100 * p2.pos17) / margem, 2)} da diferença. Mesmo que todos tivessem ido para ${esc(nomeCand(venc))} e fossem retirados, ${esc(nomeCand(venc))} continuaria à frente por ${fmt(sobra)} votos.`
      : `Os votos dados depois das 17h (${fmt(p2.pos17)}) são maiores que a diferença final (${fmt(margem)}).`;
  }

  function urnasTardias() {
    const x2 = temLog(2) && T[2].tardias, x1 = temLog(1) && T[1].tardias;
    if (!x2) { $("tiles-tardias").innerHTML = AGUARDANDO; return; }
    const um = (v) => v.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
    $("tiles-tardias").innerHTML = [
      ["Urnas tardias no 2º turno", fmt(x2.secoes), `${pct((100 * x2.secoes) / x2.secoes_total, 2)} das seções do país`],
      ["Receberam voto depois das 17h49", fmt(x2.com_voto_pos_aviso), `${pct((100 * x2.com_voto_pos_aviso) / x2.secoes, 0)} das urnas tardias`],
      ["Votos depois das 17h49", fmt(x2.pos_aviso), `média de ${um(x2.pos_aviso / x2.secoes)} por urna tardia · ${fmt(x2.pos19)} às 19h ou depois`],
      ["Sem nenhum eleitor depois das 17h", fmt(x2.sem_eleitor_apos_17h), `${pct((100 * x2.sem_eleitor_apos_17h) / x2.secoes, 0)} ficaram abertas sem receber voto após as 17h`],
      ...(x1 ? [["1º turno, sem prorrogação", fmt(x1.secoes), `seções fecharam às 17h49 ou depois; ${pct((100 * x1.com_voto_pos_aviso) / x1.secoes, 0)} delas com eleitor votando após 17h49 (${fmt(x1.pos_aviso)} votos)`]] : []),
    ].map(tile).join("");

    // último voto, nos dois turnos
    const turnosT = [1, 2].filter((t) => temLog(t) && T[t].tardias);
    const faixas = x2.ultimo_voto.map((f) => f.faixa).filter((f, i) => turnosT.some((t) => T[t].tardias.ultimo_voto[i].secoes));
    const val = (t, f) => T[t].tardias.ultimo_voto.find((x) => x.faixa === f).secoes;
    legenda("leg-tard-ultimo", turnosT.map((t) => [COR_TURNO[t], `${t}º turno`]));
    graficoBarrasH("g-tard-ultimo", faixas, turnosT.map((t) => ({
      nome: `${t}º turno`, cor: COR_TURNO[t], valores: faixas.map((f) => (100 * val(t, f)) / T[t].tardias.secoes),
      rotulos: faixas.map((f) => `${pct((100 * val(t, f)) / T[t].tardias.secoes, 0)} (${fmt(val(t, f))})`),
    })), (v) => pct(v, 0), { rotW: 104 });
    tabela("t-tard-ultimo", ["Último voto", ...turnosT.map((t) => `${t}º turno (seções)`)],
      faixas.map((f) => [f, ...turnosT.map((t) => `${fmt(val(t, f))} (${pct((100 * val(t, f)) / T[t].tardias.secoes, 1)})`)]));

    // horário de encerramento
    const hhmm = (s) => `${Math.floor(s / 3600)}h${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}`;
    const rotEnc = (s) => (s >= 20 * 3600 ? "20h+" : s < 17 * 3600 + 50 * 60 ? "17h49" : hhmm(s));
    const itensEnc = x2.encerramento.map((e) => ({
      rot: rotEnc(e.inicio), valor: e.secoes, cor: "var(--turno2)",
      dica: `<b>${rotEnc(e.inicio)}${e.inicio < 20 * 3600 ? " a " + hhmm(e.inicio + 600) : ""}</b>${linhaDica("var(--turno2)", "Urnas tardias", fmt(e.secoes))}`,
    }));
    graficoColunas("g-tard-enc", itensEnc, fmt, { altura: 200, rotularSoMaior: true });
    tabela("t-tard-enc", ["Encerramento (a partir de)", "Urnas"], itensEnc.map((i) => [i.rot, fmt(i.valor)]));

    // por UF e municípios
    legenda("leg-tard-uf", [["var(--nordeste)", "Nordeste"], ["var(--outros)", "Outras regiões"]]);
    graficoColunas("g-tard-uf", x2.ufs.slice().sort((a, b) => b.secoes - a.secoes).map((u) => ({
      rot: u.uf.toUpperCase(), valor: u.secoes,
      cor: D.regiao_da_uf[u.uf] === "Nordeste" ? "var(--nordeste)" : "var(--outros)",
      dica: `<b>${u.uf.toUpperCase()} · ${D.regiao_da_uf[u.uf]}</b>` +
        linhaDica("var(--tinta-3)", "Urnas tardias", fmt(u.secoes)) +
        linhaDica("var(--tinta-3)", "Das seções do estado", pct((100 * u.secoes) / u.total, 1)) +
        linhaDica("var(--tinta-3)", "Com voto após 17h49", fmt(u.com_voto_pos_aviso)) +
        linhaDica("var(--tinta-3)", "Votos após 17h49", fmt(u.pos_aviso)),
    })), fmt, { altura: 200 });
    const linhasMun = x2.municipios.map((m) => [esc(m.nome), m.uf.toUpperCase(), m.regiao, fmt(m.secoes), pct((100 * m.secoes) / m.total_secoes, 0),
      fmt(m.com_voto_pos_aviso), fmt(m.pos_aviso), fmt(m.sem_eleitor_apos_17h)]);
    const cabMun = ["Município", "UF", "Região", "Urnas tardias", "% das seções", "Com voto após 17h49", "Votos após 17h49", "Sem eleitor após 17h"];
    tabela("t-tard-mun", cabMun, linhasMun);
    $("busca-tardias").oninput = (ev) => {
      const norm = (s) => s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
      const q = norm(ev.target.value);
      tabela("t-tard-mun", cabMun, linhasMun.filter((l) => norm(`${l[0]} ${l[1]}`).includes(q)));
    };

    // resultado oficial nas urnas tardias × Brasil
    const res = x2.resultado, b = OF[2].br;
    legenda("leg-tard-res", [...final2.map((c) => [COR[c.numero], nomeCand(c)]), ["var(--outros)", "Brancos e nulos"]]);
    grafico100("g-tard-res", [
      { rot: "Tardias", nome: `Urnas tardias (${fmt(x2.secoes)} seções)`, partes: [...final2.map((c) => ({ valor: res[c.numero] || 0, cor: COR[c.numero] })), { valor: (res.branco || 0) + (res.nulo || 0), cor: "var(--outros)" }] },
      { rot: "Brasil", nome: "Brasil (resultado oficial)", partes: [...final2.map((c) => ({ valor: c.votos, cor: COR[c.numero] })), { valor: b.brancos + b.nulos, cor: "var(--outros)" }] },
    ], [...final2.map(nomeCand), "Brancos e nulos"], { soPercentual: true });
    const validosT = final2.reduce((s, c) => s + (res[c.numero] || 0), 0);
    $("nota-tard-res").textContent = `Votos válidos nas urnas tardias: ${final2.map((c) => `${nomeCand(c)} ${pct((100 * (res[c.numero] || 0)) / validosT, 1)}`).join(", ")} ` +
      `(no Brasil: ${final2.map((c) => `${nomeCand(c)} ${pct(c.pct, 1)}`).join(", ")}). Comparecimento nessas seções: ${pct((100 * x2.comparecimento) / x2.aptos, 1)} (Brasil: ${pct(b.pct_comparecimento, 1)}).`;
    $("g-tard-res").style.maxWidth = "100%";

    // as mesmas seções no 1º turno
    const tambem = x2.tardias_tambem_no_outro_turno;
    $("tiles-tard-1t").innerHTML = tambem == null ? AGUARDANDO : [
      ["Também fecharam às 17h49 ou depois", fmt(tambem), `${pct((100 * tambem) / x2.secoes, 0)} das urnas tardias do 2º turno`],
      ["Fecharam antes das 17h49 no 1º turno", fmt(x2.secoes - tambem), `${pct((100 * (x2.secoes - tambem)) / x2.secoes, 0)} das urnas tardias do 2º turno`],
    ].map(tile).join("");
  }

  function metodologia() {
    const q = (t) => {
      if (!completo(t) || !T[t].qualidade) return "";
      const x = T[t].qualidade;
      return ` No ${t}º turno, os logs registram ${fmt(x.comparecimento_logs)} votos e o resultado oficial tem ${fmt(x.comparecimento_oficial)} (sem o exterior):` +
        ` ${fmt(x.votos_sem_horario)} votos (${pct((100 * x.votos_sem_horario) / x.comparecimento_oficial, 4)}) vêm de seções sem log publicado ou com log incompleto. Eles estão no resultado oficial, mas não entram na contagem por horário.`;
    };
    $("metodo-cobertura").textContent = `Cobertura atual dos logs: 1º turno, ${cobTxt(1)}; 2º turno, ${cobTxt(2)}.${q(1)}${q(2)}`;
  }

  // ------------------------------------------------------------------ tema e montagem
  const raiz = document.documentElement;
  try { const t = localStorage.getItem("tema"); if (t) raiz.dataset.theme = t; } catch (e) { /* sem armazenamento */ }
  $("tema").onclick = () => {
    const escuro = raiz.dataset.theme ? raiz.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    raiz.dataset.theme = escuro ? "light" : "dark";
    try { localStorage.setItem("tema", raiz.dataset.theme); } catch (e) { /* sem armazenamento */ }
  };

  function montar() {
    topo(); resultado(); comparativo(); brancosNulos(); segundoTurno(); apos17h(); urnasTardias(); metodologia();
  }
  montar();
  let espera;
  addEventListener("resize", () => { clearTimeout(espera); espera = setTimeout(montar, 150); });
})();
