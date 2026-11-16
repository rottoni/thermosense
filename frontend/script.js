// script.js - Atualiza o painel, os status, o ícone/som de alerta e envia os limites.

// Se a página vier do próprio Flask (porta 5000), usa caminho relativo.
// Se vier do Live Server (outra porta), aponta para o Flask.
const BASE_URL = location.port === "5000" ? "" : "http://localhost:5000";
const API_URL = BASE_URL + "/api/dados";
const API_LIMITES = BASE_URL + "/api/limites";
const INTERVALO_MS = 2000; // frequência com que a página consulta o servidor

// Mesmo caminho usado pelo <img> do ícone no HTML
const SOM_URL = "../assets/alerta.wav";

// Campos de texto simples (valor à direita do <p>)
const campos = {
    temperaturaAtual: document.getElementById("temp-atual"),
    umidadeAtual: document.getElementById("umid-atual"),
    temperaturaMax: document.getElementById("temp-max"),
    temperaturaMin: document.getElementById("temp-min"),
    umidadeMax: document.getElementById("umid-max"),
    umidadeMin: document.getElementById("umid-min"),
    taxaAtualizacao: document.getElementById("taxa-atualizacao"),
};

// Campos de status (mostram "etiquetas" lado a lado)
const statusAmbiente = document.getElementById("status-ambiente");
const statusSistema = document.getElementById("status-sistema");

// Ícone de alerta
const imagemAlerta = document.querySelector(".alerta-logo");
if (imagemAlerta) {
    imagemAlerta.style.transition = "opacity 0.3s";
    imagemAlerta.style.opacity = "0"; // escondido até a primeira resposta do backend
}

// Últimos limites recebidos do servidor (usados na validação do formulário)
let ultimosLimites = {};

// ---------------------------------------------------------------------------
// Som de alerta (em loop)
// ---------------------------------------------------------------------------
const somAlerta = new Audio(SOM_URL);
somAlerta.loop = true;
somAlerta.preload = "auto";

let deveTocar = false;      // o estado atual pede som?
let somBloqueado = false;   // o navegador bloqueou o autoplay?
let somErro = false;        // o arquivo de som não carregou (caminho errado ou formato inválido)?

somAlerta.addEventListener("error", () => {
    somErro = true;
    console.warn("Não consegui carregar o som de alerta:", somAlerta.src);
    atualizarBotaoSom();
});

function lerPreferenciaSom() {
    try {
        return localStorage.getItem("thermosense-som") !== "desligado"; // padrão: ligado
    } catch {
        return true;
    }
}

function salvarPreferenciaSom(ligado) {
    try {
        localStorage.setItem("thermosense-som", ligado ? "ligado" : "desligado");
    } catch {
        /* sem armazenamento: a preferência vale só nesta página */
    }
}

let somAtivado = lerPreferenciaSom();

// Botão fixo no canto da tela (criado pelo script, não precisa mexer no HTML)
const botaoSom = document.createElement("button");
botaoSom.type = "button";
botaoSom.id = "botao-som";
Object.assign(botaoSom.style, {
    position: "fixed",
    right: "1rem",
    bottom: "1rem",
    padding: "0.5rem 1rem",
    border: "none",
    borderRadius: "999px",
    background: "#253a57",
    color: "white",
    fontWeight: "bold",
    cursor: "pointer",
    zIndex: "1000",
});
document.body.appendChild(botaoSom);

function atualizarBotaoSom() {
    if (somErro) {
        botaoSom.textContent = "⚠️ Som indisponível (arquivo não encontrado) - clique para tentar de novo";
    } else if (!somAtivado) {
        botaoSom.textContent = "🔇 Som de alerta: desligado";
    } else if (somBloqueado) {
        botaoSom.textContent = "🔈 Clique para ativar o som de alerta";
    } else {
        botaoSom.textContent = "🔊 Som de alerta: ligado";
    }
}

function sincronizarSom() {
    if (deveTocar && somAtivado && !somErro) {
        if (somAlerta.paused) {
            somAlerta
                .play()
                .then(() => {
                    somBloqueado = false;
                    atualizarBotaoSom();
                })
                .catch((erro) => {
                    // NotAllowedError = o navegador exige um clique antes de tocar áudio
                    if (erro.name === "NotAllowedError") {
                        somBloqueado = true;
                        atualizarBotaoSom();
                    } else {
                        // NotSupportedError etc.: arquivo ausente ou em formato inválido
                        somErro = true;
                        console.warn("Não foi possível tocar o som de alerta:", erro);
                        atualizarBotaoSom();
                    }
                });
        }
    } else if (!somAlerta.paused) {
        somAlerta.pause();
        somAlerta.currentTime = 0;
    }
}

botaoSom.addEventListener("click", () => {
    if (somErro) {
        // Tenta carregar o arquivo de novo (útil depois de corrigir o caminho)
        somErro = false;
        somAlerta.load();
        atualizarBotaoSom();
        sincronizarSom();
        return;
    }
    if (somAtivado && somBloqueado) {
        // Primeiro clique só libera o áudio bloqueado
        sincronizarSom();
        return;
    }
    somAtivado = !somAtivado;
    salvarPreferenciaSom(somAtivado);
    atualizarBotaoSom();
    sincronizarSom();
});

// Qualquer clique ou tecla na página também libera o áudio bloqueado
for (const evento of ["click", "keydown"]) {
    document.addEventListener(evento, () => {
        if (somBloqueado) sincronizarSom();
    });
}

atualizarBotaoSom();

// ---------------------------------------------------------------------------
// Estado geral: "ok" | "alerta" | "sem-servidor" | "aguardando"
//   ok           -> ícone transparente, sem som
//   alerta       -> ícone visível, som em loop
//   sem-servidor -> ícone visível, sem som
//   aguardando   -> ícone visível, sem som (reiniciando / esperando 1ª leitura)
// ---------------------------------------------------------------------------
function definirEstado(estado) {
    if (imagemAlerta) {
        imagemAlerta.style.opacity = estado === "ok" ? "0" : "1";
    }
    deveTocar = estado === "alerta";
    sincronizarSom();
}

// ---------------------------------------------------------------------------
// Exibição dos dados
// ---------------------------------------------------------------------------
function formatar(valor, unidade) {
    return typeof valor === "number" ? `${valor.toFixed(1)} ${unidade}` : "--";
}

// itens: [{ texto, tipo }]  com tipo = "ok" | "perigo" | "erro" | "neutro"
function mostrarEtiquetas(container, itens) {
    if (!container) return;
    const elementos = itens.map(({ texto, tipo }) => {
        const etiqueta = document.createElement("span");
        etiqueta.className = `etiqueta etiqueta-${tipo}`;
        etiqueta.textContent = texto; // textContent: nada é interpretado como HTML
        return etiqueta;
    });
    container.replaceChildren(...elementos);
}

function mostrarSemDados() {
    for (const campo of Object.values(campos)) {
        if (campo) campo.textContent = "--";
    }
    mostrarEtiquetas(statusAmbiente, [{ texto: "--", tipo: "neutro" }]);
    mostrarEtiquetas(statusSistema, [{ texto: "Sem comunicação com o servidor", tipo: "erro" }]);
    definirEstado("sem-servidor");
}

function atualizarStatus(dados) {
    // --- Reiniciando (após enviar limites) ou esperando a primeira leitura
    if (dados.reiniciando || (dados.conectado && dados.status === null)) {
        const texto = dados.reiniciando
            ? "Reiniciando o sistema..."
            : "Aguardando a primeira leitura...";
        mostrarEtiquetas(statusSistema, [{ texto, tipo: "neutro" }]);
        mostrarEtiquetas(statusAmbiente, [{ texto: "--", tipo: "neutro" }]);
        definirEstado("aguardando");
        return;
    }

    // --- Sem leituras chegando do Arduino
    if (!dados.conectado) {
        mostrarEtiquetas(statusSistema, [{ texto: "Sem comunicação com o Arduino", tipo: "erro" }]);
        mostrarEtiquetas(statusAmbiente, [{ texto: "Sem dados", tipo: "neutro" }]);
        definirEstado("alerta");
        return;
    }

    // --- Status do Sistema: mesma mensagem que o arduino.ino imprime
    //     (OK, Checksum error, Time out error, Connect error, Ack Low error...)
    const sistemaOk = dados.status === "OK";
    mostrarEtiquetas(statusSistema, [
        { texto: dados.status || "--", tipo: sistemaOk ? "ok" : "erro" },
    ]);

    if (!sistemaOk) {
        // Com erro no sensor os valores lidos (-999) não são confiáveis
        mostrarEtiquetas(statusAmbiente, [
            { texto: "Indeterminado (erro de leitura)", tipo: "neutro" },
        ]);
        definirEstado("alerta");
        return;
    }

    // --- Status do Ambiente: até 2 alertas ao mesmo tempo (temperatura e umidade)
    const alertas = (dados.alertas || []).map((texto) => ({
        texto,
        tipo: texto.startsWith("PERIGO") ? "perigo" : "ok",
    }));
    mostrarEtiquetas(statusAmbiente, alertas.length ? alertas : [{ texto: "--", tipo: "neutro" }]);

    const tudoOk = alertas.length > 0 && alertas.every((a) => a.tipo === "ok");
    definirEstado(tudoOk ? "ok" : "alerta");
}

async function atualizar() {
    try {
        const resposta = await fetch(API_URL, { cache: "no-store" });
        if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
        const dados = await resposta.json();

        const l = dados.limites || {};
        ultimosLimites = l;
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

        atualizarStatus(dados);
    } catch (erro) {
        // Backend desligado ou inacessível
        mostrarSemDados();
        console.warn("Falha ao consultar o backend:", erro);
    }
}

// ---------------------------------------------------------------------------
// Formulário "Definir Limites de Tolerância"
// ---------------------------------------------------------------------------
const REGRAS = [
    { id: "maxTemp", chave: "temperatura_max", nome: "Temperatura máxima", min: -40, max: 80 },
    { id: "minTemp", chave: "temperatura_min", nome: "Temperatura mínima", min: -40, max: 80 },
    { id: "maxUmid", chave: "umidade_max", nome: "Umidade máxima", min: 0, max: 100 },
    { id: "minUmid", chave: "umidade_min", nome: "Umidade mínima", min: 0, max: 100 },
    { id: "intervalo", chave: "intervalo_ms", nome: "Taxa de atualização", min: 1000, max: 900000, inteiro: true },
];

const formulario = document.getElementById("input-form");

if (formulario) {
    const botaoEnviar = formulario.querySelector("button[type='submit']");
    const textoBotao = botaoEnviar ? botaoEnviar.textContent : "";

    // Mensagem de resultado, criada pelo script logo abaixo do botão
    const mensagemForm = document.createElement("p");
    mensagemForm.id = "form-mensagem";
    mensagemForm.className = "text2";
    mensagemForm.setAttribute("role", "status");
    mensagemForm.style.marginTop = "1rem";
    mensagemForm.style.whiteSpace = "pre-line";
    formulario.appendChild(mensagemForm);

    function mostrarMensagemForm(texto, tipo) {
        mensagemForm.textContent = texto;
        mensagemForm.style.color =
            tipo === "erro" ? "#c62828" : tipo === "ok" ? "#1b8a2f" : "#253a57";
    }

    // Validação no navegador (o servidor valida de novo)
    function lerFormulario() {
        const valores = {};
        const numeros = {};
        const erros = [];

        for (const regra of REGRAS) {
            const campo = document.getElementById(regra.id);
            const bruto = campo ? campo.value.trim().replace(",", ".") : "";
            if (!bruto) continue; // vazio = mantém o valor atual

            if (!/^-?\d+(\.\d+)?$/.test(bruto)) {
                erros.push(`${regra.nome}: digite apenas um número.`);
                continue;
            }
            const numero = Number(bruto);
            if (numero < regra.min || numero > regra.max) {
                erros.push(`${regra.nome}: deve estar entre ${regra.min} e ${regra.max}.`);
                continue;
            }
            if (regra.inteiro && !Number.isInteger(numero)) {
                erros.push(`${regra.nome}: deve ser um número inteiro (em ms).`);
                continue;
            }
            valores[regra.id] = bruto;
            numeros[regra.chave] = numero;
        }

        if (!erros.length && Object.keys(valores).length === 0) {
            erros.push("Preencha pelo menos um campo.");
        }
        if (!erros.length) {
            const final = { ...ultimosLimites, ...numeros };
            if (final.temperatura_max < final.temperatura_min) {
                erros.push("A temperatura máxima deve ser maior ou igual à mínima.");
            }
            if (final.umidade_max < final.umidade_min) {
                erros.push("A umidade máxima deve ser maior ou igual à mínima.");
            }
        }
        return { valores, erros };
    }

    formulario.addEventListener("submit", async (evento) => {
        evento.preventDefault();

        const { valores, erros } = lerFormulario();
        if (erros.length) {
            mostrarMensagemForm(erros.join("\n"), "erro");
            return;
        }

        if (botaoEnviar) {
            botaoEnviar.disabled = true;
            botaoEnviar.textContent = "Aplicando...";
        }
        mostrarMensagemForm(
            "Reiniciando o Arduino e aplicando as alterações... (pode levar alguns segundos)",
            "info"
        );

        try {
            const resposta = await fetch(API_LIMITES, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(valores),
            });
            const corpo = await resposta.json().catch(() => ({}));

            if (resposta.ok && corpo.ok) {
                mostrarMensagemForm("Limites atualizados com sucesso!", "ok");
                formulario.reset();
            } else {
                const mensagens = corpo.erros || [`Erro ${resposta.status} no servidor.`];
                mostrarMensagemForm(mensagens.join("\n"), "erro");
            }
        } catch {
            mostrarMensagemForm("Não foi possível falar com o servidor.", "erro");
        } finally {
            if (botaoEnviar) {
                botaoEnviar.disabled = false;
                botaoEnviar.textContent = textoBotao;
            }
            atualizar();
        }
    });
}

atualizar();
setInterval(atualizar, INTERVALO_MS);