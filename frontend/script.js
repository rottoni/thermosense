// script.js - Atualiza o painel "Informações Atuais Detectadas" com os dados do backend.

// Se a página vier do próprio Flask (porta 5000), usa caminho relativo.
// Se vier do Live Server (outra porta), aponta para o Flask.
const API_URL = (location.port === "5000" ? "" : "http://localhost:5000") + "/api/dados";
const INTERVALO_MS = 2000; // mesmo ritmo de leitura do Arduino

const campos = {
    temperaturaAtual: document.getElementById("temp-atual"),
    umidadeAtual: document.getElementById("umid-atual"),
    temperaturaMax: document.getElementById("temp-max"),
    temperaturaMin: document.getElementById("temp-min"),
    umidadeMax: document.getElementById("umid-max"),
    umidadeMin: document.getElementById("umid-min"),
    taxaAtualizacao: document.getElementById("taxa-atualizacao"),
};

function formatar(valor, unidade) {
    return typeof valor === "number" ? `${valor.toFixed(1)} ${unidade}` : "--";
}

function mostrarSemDados() {
    for (const campo of Object.values(campos)) {
        if (campo) campo.textContent = "--";
    }
}

async function atualizar() {
    try {
        const resposta = await fetch(API_URL, { cache: "no-store" });
        if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
        const dados = await resposta.json();

        const l = dados.limites || {};
        campos.temperaturaMax.textContent = formatar(l.temperatura_max, "°C");
        campos.temperaturaMin.textContent = formatar(l.temperatura_min, "°C");
        campos.umidadeMax.textContent = formatar(l.umidade_max, "%");
        campos.umidadeMin.textContent = formatar(l.umidade_min, "%");
        if (campos.taxaAtualizacao) {
            // "intervalo" do arduino.ino, em milissegundos
            campos.taxaAtualizacao.textContent =
                typeof l.intervalo_ms === "number" ? `${l.intervalo_ms} ms` : "--";
        }

        if (dados.conectado) {
            campos.temperaturaAtual.textContent = formatar(dados.temperatura, "°C");
            campos.umidadeAtual.textContent = formatar(dados.umidade, "%");
        } else {
            campos.temperaturaAtual.textContent = "sem dados";
            campos.umidadeAtual.textContent = "sem dados";
        }
    } catch (erro) {
        // Backend desligado ou inacessível
        mostrarSemDados();
        console.warn("Falha ao consultar o backend:", erro);
    }
}

atualizar();
setInterval(atualizar, INTERVALO_MS);