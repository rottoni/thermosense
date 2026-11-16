// graficos.js - Gráficos de histórico de temperatura e umidade (canvas, sem bibliotecas).
//
// O histórico fica guardado no servidor (servidor.py). Esta página só pede os pontos
// novos a cada segundo e desenha. Se o Arduino reiniciar, o gráfico continua; ele só
// é zerado quando o servidor é reiniciado.
(function () {
    "use strict";

    // Se a página vier do próprio Flask (porta 5000), usa caminho relativo.
    // Se vier do Live Server (outra porta), aponta para o Flask.
    const BASE_URL = location.port === "5000" ? "" : "http://localhost:5000";
    const API_HISTORICO = BASE_URL + "/api/historico";
    const POLL_MS = 1000; // o menor intervalo permitido para o Arduino é 1000 ms

    // Posições dentro de cada ponto: [id, tempo(ms), temperatura, umidade, intervalo(ms)]
    const I_T = 1, I_TEMP = 2, I_UMID = 3, I_INT = 4;

    let sessao = "";
    let ultimoId = 0;
    let pontos = [];
    let limites = {};

    const COR_TEXTO = "#253a57";
    const COR_GRADE = "#d5d9e3";
    const COR_LIMITE = "#c62828";

    // ------------------------------------------------------------------
    // Utilidades
    // ------------------------------------------------------------------
    // Escolhe um passo "redondo" (1, 2, 5, 10...) para as marcas do eixo Y
    function passoBonito(faixa, alvo) {
        const bruto = faixa / alvo;
        const magnitude = Math.pow(10, Math.floor(Math.log10(bruto)));
        const norm = bruto / magnitude;
        const passo = norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10;
        return passo * magnitude;
    }

    function formatarEixo(ms, faixaMs) {
        const d = new Date(ms);
        const hora = d.toLocaleTimeString("pt-BR", { hour12: false });
        if (faixaMs < 10 * 60 * 1000) return hora; // HH:MM:SS
        if (faixaMs < 24 * 3600 * 1000) return hora.slice(0, 5); // HH:MM
        return (
            d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) +
            " " + hora.slice(0, 5)
        );
    }

    function formatarCompleto(ms) {
        const d = new Date(ms);
        return (
            d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) +
            " " + d.toLocaleTimeString("pt-BR", { hour12: false })
        );
    }

    // ------------------------------------------------------------------
    // Gráfico
    // ------------------------------------------------------------------
    function criarGrafico(canvas, cfg) {
        const ctx = canvas.getContext("2d");
        canvas.style.width = "100%";
        canvas.style.height = (canvas.dataset.altura || 260) + "px";
        canvas.style.display = "block";
        canvas.style.touchAction = "pan-y";

        let cursorX = null; // posição do mouse sobre o gráfico

        function desenhar() {
            const w = canvas.clientWidth;
            const h = canvas.clientHeight;
            if (!w || !h) return;

            const dpr = window.devicePixelRatio || 1;
            if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
                canvas.width = Math.round(w * dpr);
                canvas.height = Math.round(h * dpr);
            }
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.clearRect(0, 0, w, h);
            ctx.font = "12px 'Segoe UI', sans-serif";

            if (!pontos.length) {
                ctx.fillStyle = COR_TEXTO;
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillText("Aguardando as primeiras leituras...", w / 2, h / 2);
                return;
            }

            const m = { esq: 46, dir: 16, topo: 26, base: 26 };
            const area = { x: m.esq, y: m.topo, w: w - m.esq - m.dir, h: h - m.topo - m.base };
            if (area.w < 50 || area.h < 50) return;

            // ---- Faixa do eixo Y
            const idx = cfg.indice;
            let dmin = Infinity;
            let dmax = -Infinity;
            for (const p of pontos) {
                if (p[idx] < dmin) dmin = p[idx];
                if (p[idx] > dmax) dmax = p[idx];
            }
            if (dmax - dmin < cfg.faixaMin) {
                const meio = (dmin + dmax) / 2;
                dmin = meio - cfg.faixaMin / 2;
                dmax = meio + cfg.faixaMin / 2;
            }
            const faixa = dmax - dmin;
            let ymin = dmin - faixa * 0.1;
            let ymax = dmax + faixa * 0.1;

            // Inclui as linhas de limite quando elas estão perto dos dados
            const lmax = cfg.limMax();
            const lmin = cfg.limMin();
            for (const l of [lmax, lmin]) {
                if (typeof l === "number" && l >= dmin - faixa && l <= dmax + faixa) {
                    ymin = Math.min(ymin, l - faixa * 0.05);
                    ymax = Math.max(ymax, l + faixa * 0.05);
                }
            }
            ymin = Math.max(ymin, cfg.abs[0]);
            ymax = Math.min(ymax, cfg.abs[1]);
            if (ymax <= ymin) return;

            const tmin = pontos[0][I_T];
            const tmax = pontos.length > 1 ? pontos[pontos.length - 1][I_T] : tmin + 1000;
            const faixaT = Math.max(tmax - tmin, 1);

            const X = (t) => area.x + ((t - tmin) / faixaT) * area.w;
            const Y = (v) => area.y + (1 - (v - ymin) / (ymax - ymin)) * area.h;

            // ---- Título e valor atual
            ctx.fillStyle = COR_TEXTO;
            ctx.textBaseline = "alphabetic";
            ctx.textAlign = "left";
            ctx.font = "bold 12px 'Segoe UI', sans-serif";
            ctx.fillText(cfg.rotulo, area.x, 14);
            const ultimo = pontos[pontos.length - 1];
            ctx.textAlign = "right";
            ctx.fillStyle = cfg.cor;
            ctx.fillText(`atual: ${ultimo[idx].toFixed(1)} ${cfg.unidade}`, area.x + area.w, 14);
            ctx.font = "12px 'Segoe UI', sans-serif";

            // ---- Grade e rótulos do eixo Y
            const passo = passoBonito(ymax - ymin, 5);
            const casas = Math.max(0, -Math.floor(Math.log10(passo)));
            ctx.lineWidth = 1;
            ctx.textBaseline = "middle";
            ctx.textAlign = "right";
            for (let k = Math.ceil(ymin / passo); k * passo <= ymax + 1e-9; k++) {
                const v = k * passo;
                const y = Math.round(Y(v)) + 0.5;
                ctx.strokeStyle = COR_GRADE;
                ctx.beginPath();
                ctx.moveTo(area.x, y);
                ctx.lineTo(area.x + area.w, y);
                ctx.stroke();
                ctx.fillStyle = COR_TEXTO;
                ctx.fillText(v.toFixed(casas), area.x - 6, y);
            }

            // ---- Rótulos do eixo X (horário)
            ctx.textBaseline = "top";
            for (let i = 0; i <= 4; i++) {
                const t = tmin + (faixaT * i) / 4;
                const x = area.x + (area.w * i) / 4;
                ctx.textAlign = i === 0 ? "left" : i === 4 ? "right" : "center";
                ctx.fillStyle = COR_TEXTO;
                ctx.fillText(formatarEixo(t, faixaT), x, area.y + area.h + 8);
            }

            // ---- Linhas de limite (tracejadas)
            ctx.save();
            ctx.setLineDash([6, 4]);
            ctx.strokeStyle = COR_LIMITE;
            ctx.fillStyle = COR_LIMITE;
            ctx.textAlign = "left";
            ctx.textBaseline = "bottom";
            const limitesDesenho = [
                [lmax, "máx"],
                [lmin, "mín"],
            ];
            for (const [valor, nome] of limitesDesenho) {
                if (typeof valor !== "number" || valor < ymin || valor > ymax) continue;
                const y = Math.round(Y(valor)) + 0.5;
                ctx.beginPath();
                ctx.moveTo(area.x, y);
                ctx.lineTo(area.x + area.w, y);
                ctx.stroke();
                const texto = `${nome} ${valor.toFixed(1)}`;
                const larguraTexto = ctx.measureText(texto).width;
                ctx.save();
                ctx.setLineDash([]);
                ctx.fillStyle = "rgba(241, 241, 247, 0.85)"; // fundo do container, para ler por cima da curva
                ctx.fillRect(area.x + 2, y - 16, larguraTexto + 6, 14);
                ctx.restore();
                ctx.fillStyle = COR_LIMITE;
                ctx.fillText(texto, area.x + 5, y - 3);
            }
            ctx.restore();

            // ---- Linha dos dados (quebra quando há um buraco grande, ex.: Arduino desligado)
            ctx.strokeStyle = cfg.cor;
            ctx.lineWidth = 2;
            ctx.lineJoin = "round";
            ctx.beginPath();
            let anterior = null;
            for (const p of pontos) {
                const x = X(p[I_T]);
                const y = Y(p[idx]);
                const buraco =
                    anterior &&
                    p[I_T] - anterior[I_T] > 3 * Math.max(p[I_INT], anterior[I_INT]) + 5000;
                if (!anterior || buraco) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
                anterior = p;
            }
            ctx.stroke();

            // Poucos pontos: marca cada um (também aparecem os pontos isolados)
            ctx.fillStyle = cfg.cor;
            if (pontos.length <= 120) {
                for (const p of pontos) {
                    ctx.beginPath();
                    ctx.arc(X(p[I_T]), Y(p[idx]), 2.5, 0, Math.PI * 2);
                    ctx.fill();
                }
            }
            // Último ponto, em destaque
            ctx.beginPath();
            ctx.arc(X(ultimo[I_T]), Y(ultimo[idx]), 4, 0, Math.PI * 2);
            ctx.fill();

            // ---- Ponto sob o mouse (tooltip)
            if (cursorX !== null && cursorX >= area.x && cursorX <= area.x + area.w) {
                const alvo = tmin + ((cursorX - area.x) / area.w) * faixaT;
                let lo = 0;
                let hi = pontos.length - 1;
                while (lo < hi) {
                    const meio = (lo + hi) >> 1;
                    if (pontos[meio][I_T] < alvo) lo = meio + 1;
                    else hi = meio;
                }
                if (lo > 0 && alvo - pontos[lo - 1][I_T] < pontos[lo][I_T] - alvo) lo--;
                const p = pontos[lo];
                const px = X(p[I_T]);
                const py = Y(p[idx]);

                ctx.strokeStyle = COR_TEXTO;
                ctx.lineWidth = 1;
                ctx.setLineDash([3, 3]);
                ctx.beginPath();
                ctx.moveTo(Math.round(px) + 0.5, area.y);
                ctx.lineTo(Math.round(px) + 0.5, area.y + area.h);
                ctx.stroke();
                ctx.setLineDash([]);

                ctx.fillStyle = "#ffffff";
                ctx.strokeStyle = cfg.cor;
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.arc(px, py, 4.5, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();

                const linha1 = formatarCompleto(p[I_T]);
                const linha2 = `${p[idx].toFixed(1)} ${cfg.unidade}`;
                ctx.font = "12px 'Segoe UI', sans-serif";
                const bw = Math.max(ctx.measureText(linha1).width, ctx.measureText(linha2).width) + 16;
                const bh = 40;
                let bx = px + 12;
                if (bx + bw > w - 4) bx = px - 12 - bw;
                const by = area.y + 6;
                ctx.fillStyle = "rgba(37, 58, 87, 0.92)";
                ctx.beginPath();
                ctx.roundRect(bx, by, bw, bh, 6);
                ctx.fill();
                ctx.fillStyle = "#ffffff";
                ctx.textAlign = "left";
                ctx.textBaseline = "top";
                ctx.fillText(linha1, bx + 8, by + 6);
                ctx.font = "bold 12px 'Segoe UI', sans-serif";
                ctx.fillText(linha2, bx + 8, by + 22);
            }
        }

        canvas.addEventListener("pointermove", (e) => {
            cursorX = e.clientX - canvas.getBoundingClientRect().left;
            desenhar();
        });
        canvas.addEventListener("pointerleave", () => {
            cursorX = null;
            desenhar();
        });
        if (typeof ResizeObserver !== "undefined") {
            new ResizeObserver(desenhar).observe(canvas);
        }

        return { desenhar };
    }

    // ------------------------------------------------------------------
    // Criação dos dois gráficos (os <canvas> precisam existir no HTML)
    // ------------------------------------------------------------------
    const graficos = [];

    const canvasTemp = document.getElementById("grafico-temperatura");
    if (canvasTemp) {
        graficos.push(criarGrafico(canvasTemp, {
            indice: I_TEMP,
            rotulo: "Temperatura (°C)",
            unidade: "°C",
            cor: "#e8590c",
            faixaMin: 2,
            abs: [-40, 80],
            limMax: () => limites.temperatura_max,
            limMin: () => limites.temperatura_min,
        }));
    }

    const canvasUmid = document.getElementById("grafico-umidade");
    if (canvasUmid) {
        graficos.push(criarGrafico(canvasUmid, {
            indice: I_UMID,
            rotulo: "Umidade (%)",
            unidade: "%",
            cor: "#1c7ed6",
            faixaMin: 5,
            abs: [0, 100],
            limMax: () => limites.umidade_max,
            limMin: () => limites.umidade_min,
        }));
    }

    function redesenhar() {
        for (const g of graficos) g.desenhar();
    }

    // ------------------------------------------------------------------
    // Busca dos pontos no servidor
    // ------------------------------------------------------------------
    async function buscar() {
        try {
            const url = `${API_HISTORICO}?sessao=${encodeURIComponent(sessao)}&desde=${ultimoId}`;
            const resposta = await fetch(url, { cache: "no-store" });
            if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
            const dados = await resposta.json();

            if (dados.sessao !== sessao) {
                // Primeira carga, ou o servidor foi reiniciado: começa do zero
                sessao = dados.sessao;
                pontos = dados.pontos;
            } else {
                for (const p of dados.pontos) pontos.push(p);
            }
            if (pontos.length > dados.max) pontos.splice(0, pontos.length - dados.max);
            ultimoId = dados.ultimo_id;
            limites = dados.limites || {};
            redesenhar();
        } catch (erro) {
            // Servidor fora do ar: os gráficos continuam como estavam
            console.warn("Falha ao buscar o histórico:", erro);
        } finally {
            setTimeout(buscar, POLL_MS);
        }
    }

    redesenhar();
    buscar();
})();