/* Dashboard de la defensa, fase 1: el camino del proyecto por la ingesta.
   Renderizador genérico: dibuja la línea y los cuatro tipos de prueba que trae
   window.DATOS (lo escribe project.analysis.dashboard_ingesta) y no sabe nada de
   paradas concretas. Una sola línea de tiempo de GSAP con una etiqueta por
   parada: avanzar es tweenTo y retroceder es la misma animación al revés. */
(function () {
  "use strict";
  // Castellano en los ejes y en las cifras: 3.000 y 99,3, no 3,000 y 99.3.
  d3.formatDefaultLocale({ decimal: ",", thousands: ".", grouping: [3], currency: ["", " €"] });
  const D = window.DATOS;
  const lienzo = document.getElementById("lienzo");

  function escalar() {
    const s = Math.min(innerWidth / 1920, innerHeight / 1080);
    lienzo.style.transform =
      `translate(${(innerWidth - 1920 * s) / 2}px, ${(innerHeight - 1080 * s) / 2}px) scale(${s})`;
  }
  addEventListener("resize", escalar);
  escalar();

  if (!D) {
    lienzo.innerHTML = '<p class="aviso">Falta <code>datos/ingesta.js</code>.<br>' +
      "Genéralo con <code>uv run python -m project.analysis.dashboard_ingesta</code></p>";
    return;
  }

  const fmtFecha = d3.utcFormat("%d/%m/%Y");
  const fmtValor = d3.format(",.3~f");
  const PASO = 280, X0 = 160, Y = 120, ANCHO = 1920;

  // --- La línea: estaciones (capítulos) y paradas, en orden -----------------
  const nodos = [];
  D.capitulos.forEach((c) => {
    nodos.push({ tipo: "estacion", c });
    D.paradas.filter((p) => p.capitulo === c.n).forEach((p) => nodos.push({ tipo: "parada", p }));
  });
  nodos.forEach((n, i) => (n.x = X0 + i * PASO));
  const xFin = nodos[nodos.length - 1].x;
  const xDe = (p) => nodos.find((n) => n.p === p).x;
  // La cámara deja el marcador a un tercio de la izquierda sin pasarse de los extremos.
  const camara = (x) => Math.max(Math.min(0, ANCHO / 3 - x), ANCHO - (xFin + X0));

  const mundo = d3.select("#linea").append("g");
  mundo.append("line").attr("class", "via")
    .attr("x1", X0).attr("x2", xFin).attr("y1", Y).attr("y2", Y);
  const hecha = mundo.append("line").attr("class", "via-hecha")
    .attr("x1", X0).attr("x2", X0).attr("y1", Y).attr("y2", Y);
  const est = mundo.selectAll("g.estacion").data(nodos.filter((n) => n.tipo === "estacion"))
    .join("g").attr("class", "estacion").attr("transform", (n) => `translate(${n.x},${Y})`);
  est.append("circle").attr("r", 24);
  est.append("text").attr("class", "num").attr("dy", "0.35em").text((n) => n.c.n);
  est.append("text").attr("class", "nombre").attr("y", 56).text((n) => n.c.nombre);
  const circuloDe = new Map();
  const par = mundo.selectAll("g.parada").data(nodos.filter((n) => n.tipo === "parada"))
    .join("g").attr("class", "parada").attr("transform", (n) => `translate(${n.x},${Y})`);
  par.append("circle").attr("r", 10).each(function (n) { circuloDe.set(n.p, this); });
  par.append("text").attr("y", 40).text((n) => n.p.id);
  const marcador = mundo.append("g").attr("class", "marcador");
  marcador.append("circle").attr("r", 15);
  const fecha = marcador.append("text").attr("class", "fecha").attr("y", -32);

  const estado = { x: X0, cam: 0, t: Date.parse(D.paradas[0].fecha) };
  function pinta() {
    mundo.attr("transform", `translate(${estado.cam},0)`);
    marcador.attr("transform", `translate(${estado.x},${Y})`);
    hecha.attr("x2", estado.x);
    fecha.text(fmtFecha(new Date(estado.t)));
  }
  pinta();

  // --- Las pruebas: cada una devuelve la línea de tiempo de su entrada -------
  function lista(el, pr) {
    const li = d3.select(el).append("ul").attr("class", "lista")
      .selectAll("li").data(pr.elementos).join("li").attr("class", (e) => `v-${e.veredicto}`);
    li.append("span").attr("class", "marca")
      .text((e) => ({ si: "✓", parcial: "!", no: "✕" })[e.veredicto]);
    li.append("span").attr("class", "nombre").text((e) => e.nombre);
    li.append("span").attr("class", "detalle").text((e) => e.detalle);
    return gsap.timeline().from(li.nodes(), { autoAlpha: 0, x: -40, stagger: 0.12, duration: 0.4 });
  }

  function pares(el, pr) {
    const tarjetas = d3.select(el).append("div").attr("class", "pares")
      .selectAll("div").data(pr.registros).join("div").attr("class", "registro");
    tarjetas.append("h3").text((r) => r.titulo);
    const filas = tarjetas.selectAll("div.fila").data((r) => Object.entries(r.campos)).join("div")
      .attr("class", ([k]) => (k === pr.resalta ? "fila resaltada" : "fila"));
    filas.append("span").attr("class", "k").text(([k]) => k);
    filas.append("span").attr("class", "v").text(([, v]) => v);
    return gsap.timeline()
      .from(tarjetas.nodes(), { autoAlpha: 0, y: 30, stagger: 0.25, duration: 0.45 })
      .from(d3.select(el).selectAll(".resaltada").nodes(),
        { backgroundColor: "rgba(217,130,43,0.75)", duration: 0.9 }, ">");
  }

  // Tooltip único, en coordenadas del lienzo (que va escalado por CSS).
  const tip = d3.select(lienzo).append("div").attr("id", "tip");
  function muestra(e, texto) {
    const r = lienzo.getBoundingClientRect(), s = r.width / 1920;
    tip.text(texto).style("display", "block");
    const w = tip.node().offsetWidth, h = tip.node().offsetHeight;
    let x = (e.clientX - r.left) / s + 16, y = (e.clientY - r.top) / s + 16;
    if (x + w > 1920) x = (e.clientX - r.left) / s - 16 - w;
    if (y + h > 1080) y = (e.clientY - r.top) / s - 16 - h;
    tip.style("left", `${Math.max(0, x)}px`).style("top", `${Math.max(0, y)}px`);
  }
  const oculta = () => tip.style("display", "none");
  const conTip = (sel, texto) => sel
    .on("mouseenter mousemove", (e, d) => muestra(e, texto(d))).on("mouseleave", oculta);

  function serie(el, pr) {
    const W = 1680, n = pr.series.length, H = Math.min(160, 400 / n);
    const M = { l: 400, r: 30, t: 56, b: 34 };
    const fechas = pr.x.map((d) => new Date(d));
    const x = d3.scaleUtc().domain(d3.extent(fechas)).range([M.l, W - M.r]);
    const alto = M.t + H * n;
    const DIA = 864e5;
    const svg = d3.select(el).append("svg").attr("class", "serie")
      .attr("width", W).attr("height", alto + M.b);
    const sombras = svg.selectAll("rect.sombra").data(pr.sombras).join("rect").attr("class", "sombra")
      .attr("x", (s) => x(new Date(s.desde)))
      .attr("width", (s) => Math.max(3,
        Math.min(x(new Date(Date.parse(s.hasta) + DIA)), W - M.r) - x(new Date(s.desde))))
      .attr("y", M.t).attr("height", H * n);
    conTip(sombras, (s) => s.etiqueta);
    const tl = gsap.timeline();
    pr.series.forEach((s, i) => {
      const y0 = M.t + H * i;
      const y = d3.scaleLinear().domain([0, d3.max(s.valores) || 1]).nice()
        .range([y0 + H - 14, y0 + 8]);
      const g = svg.append("g");
      // «fuente · medida» en dos líneas: el nombre entero no cabe a la izquierda del eje.
      const rotulo = g.append("text").attr("class", "rotulo").attr("y", y0 + H / 2)
        .attr("text-anchor", "end");
      s.nombre.split(" · ").forEach((linea, k) => rotulo.append("tspan")
        .attr("x", M.l - 70).attr("dy", k ? "1.2em" : "-0.25em").text(linea));
      g.append("g").attr("class", "eje").attr("transform", `translate(${M.l - 8},0)`)
        .call(d3.axisLeft(y).ticks(3).tickSizeOuter(0));
      const puntos = pr.x.map((d, j) => [fechas[j], s.valores[j], d]);
      const linea = d3.line().defined((v) => v[1] != null).x((v) => x(v[0])).y((v) => y(v[1]));
      const trazo = g.append("path").attr("class", "trazo").attr("d", linea(puntos));
      conTip(g.selectAll("circle").data(puntos.filter((v) => v[1] != null)).join("circle")
        .attr("class", "punto").attr("r", 9).attr("cx", (v) => x(v[0])).attr("cy", (v) => y(v[1])),
      (v) => `${s.nombre} · ${fmtFecha(v[0])} · ${fmtValor(v[1])}`);
      const L = trazo.node().getTotalLength();
      trazo.attr("stroke-dasharray", L).attr("stroke-dashoffset", L);
      tl.to(trazo.node(), { attr: { "stroke-dashoffset": 0 }, duration: 1.3, ease: "power1.inOut" }, i * 0.2);
    });
    svg.append("g").attr("class", "eje").attr("transform", `translate(0,${alto})`)
      .call(d3.axisBottom(x).ticks(d3.utcWeek.every(1)).tickFormat(d3.utcFormat("%d/%m")));
    const anot = svg.selectAll("g.anot").data(pr.anotaciones).join("g").attr("class", "anot")
      .attr("transform", (a) => `translate(${x(new Date(a.x))},0)`);
    anot.append("line").attr("y1", M.t - 4).attr("y2", alto);
    anot.append("text").attr("y", (a, i) => M.t - 12 - (i % 2) * 22)
      .attr("text-anchor", "middle").text((a) => a.texto);
    return tl.from(sombras.nodes(), { opacity: 0, duration: 0.5 }, 0)
      .from(anot.nodes(), { opacity: 0, stagger: 0.15, duration: 0.4 }, ">-0.4");
  }

  function cifra(el, pr) {
    const c = d3.select(el).append("div").attr("class", "cifra");
    const valor = c.append("div").attr("class", "valor");
    c.append("div").attr("class", "etiqueta").text(pr.etiqueta);
    const li = c.append("ul").attr("class", "detalle").selectAll("li").data(pr.detalle).join("li");
    li.append("span").attr("class", "k").text((d) => d.nombre);
    li.append("span").attr("class", "v").text((d) => d.valor);
    const fmt = d3.format(`,.${pr.decimales}f`);
    const o = { v: pr.valor };
    valor.text(fmt(pr.valor));
    return gsap.timeline()
      .from(o, { v: 0, duration: 1.2, ease: "power2.out", onUpdate: () => valor.text(fmt(o.v)) })
      .from(li.nodes(), { autoAlpha: 0, y: 12, stagger: 0.08, duration: 0.3 }, "-=0.6");
  }

  const R = { lista, pares, serie, cifra };

  // --- Paneles: todos se construyen al cargar, ocultos ------------------------
  const contenedor = document.getElementById("paneles");
  const paneles = D.paradas.map((p) => {
    const el = d3.select(contenedor).append("section").attr("class", "panel");
    el.append("p").attr("class", "apartado")
      .text(`${p.capitulo} · ${D.capitulos[p.capitulo - 1].nombre} · ${p.apartado}`);
    const h = el.append("h2").text(p.titulo);
    const t = el.append("p").attr("class", "texto").text(p.texto);
    const pr = el.append("div").attr("class", "prueba");
    el.append("p").attr("class", "remite")
      .text(p.remite.map((f) => f.ficha).join("   ·   "));
    const entrada = gsap.timeline()
      .from([h.node(), t.node()], { autoAlpha: 0, y: 24, stagger: 0.15, duration: 0.45 })
      .add(R[p.prueba.tipo](pr.node(), p.prueba), ">-0.1");
    return { el: el.node(), entrada };
  });

  const carteles = new Map(D.capitulos.map((c) => [c.n,
    d3.select("#carteles").append("div").attr("class", "cartel").text(`${c.n} · ${c.nombre}`).node()]));

  // --- La línea de tiempo maestra ---------------------------------------------
  const tl = gsap.timeline({ paused: true });
  D.paradas.forEach((p, i) => {
    const previa = D.paradas[i - 1];
    if (previa) tl.to(paneles[i - 1].el, { autoAlpha: 0, y: -20, duration: 0.4 });
    tl.to(estado, {
      x: xDe(p), cam: camara(xDe(p)), t: Date.parse(p.fecha),
      duration: previa ? 1.2 : 0.8, ease: "power2.inOut", onUpdate: pinta,
    });
    if (!previa || previa.capitulo !== p.capitulo) {
      const c = carteles.get(p.capitulo);
      tl.to(c, { autoAlpha: 1, duration: 0.3 }, "<0.3").to(c, { autoAlpha: 0, duration: 0.3 }, "+=0.7");
    }
    tl.to(circuloDe.get(p), { attr: { r: 18 }, duration: 0.2, yoyo: true, repeat: 1 });
    tl.set(paneles[i].el, { autoAlpha: 1, y: 0 });
    tl.add(paneles[i].entrada);
    tl.addLabel(`p${i}`);
  });

  // --- Navegación ---------------------------------------------------------------
  const total = D.paradas.length;
  let actual = -1, auto = false, espera = null;
  function programar() {
    clearTimeout(espera);
    if (auto && actual < total - 1)
      espera = setTimeout(() => ir(actual + 1), D.paradas[actual].duracion_s * 1000);
  }
  function ir(j) {
    actual = Math.max(0, Math.min(total - 1, j));
    clearTimeout(espera);
    tl.tweenTo(`p${actual}`, { overwrite: true, onComplete: programar });
  }
  addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === " ") ir(actual + 1);
    else if (e.key === "ArrowLeft") ir(actual - 1);
    else if (e.key === "Home") ir(0);
    else if (e.key === "a" || e.key === "A") { auto = !auto; programar(); }
    else if (e.key === "f" || e.key === "F") {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen();
    }
  });
  addEventListener("click", () => ir(actual + 1));

  d3.select("#pie").text(
    `foto ${D.origen.commit}${D.origen.sucio ? " (con cambios sin commitear)" : ""} · ` +
    `generada ${D.origen.generado} · crudo ${D.origen.crudo_desde} → ${D.origen.crudo_hasta}`);

  const q = new URLSearchParams(location.search);
  if (q.has("p")) {
    actual = Math.max(0, Math.min(total - 1, Number(q.get("p")) - 1));
    tl.seek(`p${actual}`, false);
  } else {
    ir(0);
  }
  if (q.get("auto") === "1") { auto = true; programar(); }
  console.log(`[dashboard] ${total} paradas, foto ${D.origen.commit}`);
})();
