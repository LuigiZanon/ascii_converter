/**
 * Frontend do ASCII Studio (PyWebView + Endpoints HTTP Binários)
 *
 * Destaques de Eficiência:
 * - Single-Flight Request Coalescing: evita fila de requisições concorrentes
 *   durante o arraste dos sliders; no máximo 1 requisição de preview fica em voo,
 *   e apenas o estado mais recente pendente é disparado em seguida.
 * - Recebe JPEG binário direto via Blob + ObjectURL (sem Base64), liberando o
 *   ObjectURL anterior imediatamente via URL.revokeObjectURL().
 * - Zoom e Pan 100% acelerados por GPU via CSS Transform (zero chamadas ao Python
 *   ao redimensionar a janela ou dar zoom).
 */

(() => {
  const estado = {
    imagemCarregada: false,
    larguraOriginal: 0,
    alturaOriginal: 0,
    templates: {},
    modoVisualizacao: "ascii", // "ascii" | "split" | "text"
    zoom: 1.0,
    modoZoomAjustado: true,
    panX: 0,
    panY: 0,
    splitPercent: 50,
    urlPreviewAtual: null,
    urlOriginalAtual: null,
    emVoo: false,
    pendente: false,
  };

  // Referências DOM
  const el = {
    sidebar: document.getElementById("sidebar"),
    splitter: document.getElementById("splitter"),
    btnToggleSidebar: document.getElementById("btnToggleSidebar"),
    dropOverlay: document.getElementById("dropOverlay"),
    dropZoneCard: document.getElementById("dropZoneCard"),
    thumbPreview: document.getElementById("thumbPreview"),
    uploadPlaceholder: document.getElementById("uploadPlaceholder"),
    badgeDimensoesOrig: document.getElementById("badgeDimensoesOrig"),
    btnCarregarImagem: document.getElementById("btnCarregarImagem"),
    btnEmptyCarregar: document.getElementById("btnEmptyCarregar"),
    labelNomeImagem: document.getElementById("labelNomeImagem"),
    inputArquivoImagem: document.getElementById("inputArquivoImagem"),

    sliderBrilho: document.getElementById("sliderBrilho"),
    sliderContraste: document.getElementById("sliderContraste"),
    sliderSaturacao: document.getElementById("sliderSaturacao"),
    sliderGamma: document.getElementById("sliderGamma"),
    sliderEscala: document.getElementById("sliderEscala"),
    valBrilho: document.getElementById("valBrilho"),
    valContraste: document.getElementById("valContraste"),
    valSaturacao: document.getElementById("valSaturacao"),
    valGamma: document.getElementById("valGamma"),
    valEscala: document.getElementById("valEscala"),
    chkInverter: document.getElementById("chkInverter"),
    btnRestaurarPadroes: document.getElementById("btnRestaurarPadroes"),

    comboTemplate: document.getElementById("comboTemplate"),
    editCaracteres: document.getElementById("editCaracteres"),
    badgeNivelChars: document.getElementById("badgeNivelChars"),
    btnInverterRampa: document.getElementById("btnInverterRampa"),
    btnEscolherFonte: document.getElementById("btnEscolherFonte"),
    btnRemoverFonte: document.getElementById("btnRemoverFonte"),
    labelFonteAtual: document.getElementById("labelFonteAtual"),
    inputArquivoFonte: document.getElementById("inputArquivoFonte"),

    inputCorFundo: document.getElementById("inputCorFundo"),
    swatchCorAtual: document.getElementById("swatchCorAtual"),
    labelHexFundo: document.getElementById("labelHexFundo"),
    badgeGrade: document.getElementById("badgeGrade"),

    btnExportar: document.getElementById("btnExportar"),

    zoomControls: document.getElementById("zoomControls"),
    btnZoomIn: document.getElementById("btnZoomIn"),
    btnZoomOut: document.getElementById("btnZoomOut"),
    btnZoomFit: document.getElementById("btnZoomFit"),
    btnZoom100: document.getElementById("btnZoom100"),
    labelZoom: document.getElementById("labelZoom"),
    btnCopiarTexto: document.getElementById("btnCopiarTexto"),

    canvasStage: document.getElementById("canvasStage"),
    emptyState: document.getElementById("emptyState"),
    transformContainer: document.getElementById("transformContainer"),
    imageWrapper: document.getElementById("imageWrapper"),
    imgPreviewAscii: document.getElementById("imgPreviewAscii"),
    imgPreviewOriginal: document.getElementById("imgPreviewOriginal"),
    splitOverlay: document.getElementById("splitOverlay"),
    splitHandle: document.getElementById("splitHandle"),
    textStage: document.getElementById("textStage"),
    preTextoAscii: document.getElementById("preTextoAscii"),

    statusDot: document.getElementById("statusDot"),
    statusMensagem: document.getElementById("statusMensagem"),
    metricGrade: document.getElementById("metricGrade"),
    metricSaida: document.getElementById("metricSaida"),
    metricTempo: document.getElementById("metricTempo"),
    toast: document.getElementById("toast"),
  };

  let timerToast = null;

  function mostrarToast(msg) {
    el.toast.textContent = msg;
    el.toast.classList.remove("hidden");
    clearTimeout(timerToast);
    timerToast = setTimeout(() => el.toast.classList.add("hidden"), 2800);
  }

  function definirStatus(msg, ocupado = false) {
    el.statusMensagem.textContent = msg;
    el.statusDot.classList.toggle("busy", ocupado);
  }

  function temPywebviewApi() {
    return Boolean(window.pywebview && window.pywebview.api);
  }

  function coletarParametros() {
    return {
      brilho: Number(el.sliderBrilho.value),
      contraste: Number(el.sliderContraste.value),
      saturacao: Number(el.sliderSaturacao.value),
      gamma: Number(el.sliderGamma.value),
      inverter: Boolean(el.chkInverter.checked),
      escala: Number(el.sliderEscala.value),
      caracteres: el.editCaracteres.value,
      cor_fundo: el.inputCorFundo.value,
    };
  }

  function atualizarRotulosControles() {
    el.valBrilho.textContent = `${el.sliderBrilho.value}%`;
    el.valContraste.textContent = `${el.sliderContraste.value}%`;
    el.valSaturacao.textContent = `${el.sliderSaturacao.value}%`;
    el.valGamma.textContent = (Number(el.sliderGamma.value) / 100).toFixed(2);
    const esc = Number(el.sliderEscala.value);
    el.valEscala.textContent = `${(esc / 100).toFixed(2)}x (${esc}%)`;

    const chars = el.editCaracteres.value || "@%#*+=-:. ";
    el.badgeNivelChars.textContent = `${chars.length} níveis`;
  }

  // ------------------------------------------------------------------ //
  // Pipeline Single-Flight de Preview (Zero fila acumulada)
  // ------------------------------------------------------------------ //
  function agendarPreview() {
    atualizarRotulosControles();
    if (!estado.imagemCarregada) return;

    if (estado.emVoo) {
      estado.pendente = true;
      return;
    }
    executarPreview();
  }

  async function executarPreview() {
    if (!estado.imagemCarregada) return;
    estado.emVoo = true;
    estado.pendente = false;
    definirStatus("Renderizando preview…", true);

    const params = coletarParametros();

    try {
      if (estado.modoVisualizacao === "text") {
        const res = await fetch("/api/texto", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(params),
        });
        const dados = await res.json();
        if (dados.ok) {
          el.preTextoAscii.textContent = dados.texto;
          el.badgeGrade.textContent = `${dados.colunas}×${dados.linhas}`;
          el.metricGrade.textContent = `Grade: ${dados.colunas}×${dados.linhas} chars`;
          el.metricTempo.textContent = `Tempo: ${dados.duracao_ms} ms`;
          definirStatus(`Texto ASCII gerado (${dados.colunas}×${dados.linhas})`);
        }
      } else {
        const res = await fetch("/api/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(params),
        });
        if (!res.ok) {
          throw new Error(await res.text());
        }

        const blob = await res.blob();
        const novaUrl = URL.createObjectURL(blob);
        const urlAntiga = estado.urlPreviewAtual;
        estado.urlPreviewAtual = novaUrl;

        await new Promise((resolve) => {
          el.imgPreviewAscii.onload = resolve;
          el.imgPreviewAscii.onerror = resolve;
          el.imgPreviewAscii.src = novaUrl;
        });

        if (urlAntiga) {
          URL.revokeObjectURL(urlAntiga);
        }

        const outW = res.headers.get("X-Output-Width") || "—";
        const outH = res.headers.get("X-Output-Height") || "—";
        const cols = res.headers.get("X-Grid-Cols") || "—";
        const rows = res.headers.get("X-Grid-Rows") || "—";
        const ms = res.headers.get("X-Render-Ms") || "—";

        el.badgeGrade.textContent = `${cols}×${rows}`;
        el.metricGrade.textContent = `Grade: ${cols}×${rows} chars`;
        el.metricSaida.textContent = `Saída: ${outW}×${outH} px`;
        el.metricTempo.textContent = `Tempo: ${ms} ms`;
        definirStatus(`Preview atualizado em ${ms} ms (saída final: ${outW}×${outH} px)`);

        if (estado.modoZoomAjustado) {
          ajustarZoomATela();
        } else {
          aplicarTransformacao();
        }
        if (estado.modoVisualizacao === "split") {
          atualizarSplit(estado.splitPercent);
        }
      }
    } catch (err) {
      definirStatus(`Erro no preview: ${err.message || err}`);
    } finally {
      estado.emVoo = false;
      if (estado.pendente) {
        requestAnimationFrame(executarPreview);
      }
    }
  }

  // ------------------------------------------------------------------ //
  // Carregamento de Imagem e Fonte
  // ------------------------------------------------------------------ //
  async function aposImagemCarregada(info) {
    estado.imagemCarregada = true;
    estado.larguraOriginal = info.largura;
    estado.alturaOriginal = info.altura;

    el.labelNomeImagem.textContent = info.nome;
    el.badgeDimensoesOrig.textContent = `${info.largura}×${info.altura}`;
    el.badgeDimensoesOrig.classList.remove("hidden");

    // Busca o JPEG da imagem original para miniatura e split-view
    const resOrig = await fetch(`/api/original?t=${Date.now()}`);
    if (resOrig.ok) {
      const blob = await resOrig.blob();
      if (estado.urlOriginalAtual) URL.revokeObjectURL(estado.urlOriginalAtual);
      estado.urlOriginalAtual = URL.createObjectURL(blob);
      el.thumbPreview.src = estado.urlOriginalAtual;
      el.imgPreviewOriginal.src = estado.urlOriginalAtual;
      el.thumbPreview.classList.remove("hidden");
      el.uploadPlaceholder.classList.add("hidden");
    }

    el.emptyState.classList.add("hidden");
    atualizarModoVisualizacao(estado.modoVisualizacao);
    estado.modoZoomAjustado = true;
    agendarPreview();
  }

  async function escolherImagem() {
    if (temPywebviewApi()) {
      const res = await window.pywebview.api.selecionar_imagem();
      if (res && res.ok) {
        await aposImagemCarregada(res);
      } else if (res && res.erro) {
        mostrarToast(res.erro);
      }
    } else {
      el.inputArquivoImagem.click();
    }
  }

  async function enviarArquivoImagem(arquivo) {
    const form = new FormData();
    form.append("arquivo", arquivo, arquivo.name);
    definirStatus(`Carregando ${arquivo.name}…`, true);
    const res = await fetch("/api/upload-imagem", { method: "POST", body: form });
    const dados = await res.json();
    if (dados.ok) {
      await aposImagemCarregada(dados);
    } else {
      mostrarToast(dados.erro || "Erro ao carregar imagem.");
    }
  }

  async function escolherFonte() {
    if (temPywebviewApi()) {
      const res = await window.pywebview.api.selecionar_fonte();
      if (res && res.ok) {
        el.labelFonteAtual.textContent = res.nome;
        el.btnRemoverFonte.classList.remove("hidden");
        agendarPreview();
      } else if (res && res.erro) {
        mostrarToast(res.erro);
      }
    } else {
      el.inputArquivoFonte.click();
    }
  }

  async function enviarArquivoFonte(arquivo) {
    const form = new FormData();
    form.append("arquivo", arquivo, arquivo.name);
    const res = await fetch("/api/upload-fonte", { method: "POST", body: form });
    const dados = await res.json();
    if (dados.ok) {
      el.labelFonteAtual.textContent = dados.nome;
      el.btnRemoverFonte.classList.remove("hidden");
      mostrarToast(`Fonte ativada: ${dados.nome}`);
      agendarPreview();
    } else {
      mostrarToast(dados.erro || "Fonte inválida.");
    }
  }

  // ------------------------------------------------------------------ //
  // Zoom, Pan e Split Antes/Depois (GPU Composited)
  // ------------------------------------------------------------------ //
  function aplicarTransformacao() {
    el.imageWrapper.style.transform = `translate3d(${estado.panX}px, ${estado.panY}px, 0) scale(${estado.zoom})`;
    el.imgPreviewAscii.style.imageRendering = estado.zoom >= 1.0 ? "pixelated" : "auto";
    el.labelZoom.textContent = estado.modoZoomAjustado
      ? `Ajustar (${Math.round(estado.zoom * 100)}%)`
      : `${Math.round(estado.zoom * 100)}%`;
  }

  function ajustarZoomATela() {
    const imgW = el.imgPreviewAscii.naturalWidth || 1;
    const imgH = el.imgPreviewAscii.naturalHeight || 1;
    const palcoW = Math.max(el.canvasStage.clientWidth - 40, 100);
    const palcoH = Math.max(el.canvasStage.clientHeight - 40, 100);

    estado.zoom = Math.min(palcoW / imgW, palcoH / imgH, 1.0);
    estado.panX = 0;
    estado.panY = 0;
    estado.modoZoomAjustado = true;
    aplicarTransformacao();
  }

  function definirZoomManual(novoZoom) {
    estado.zoom = Math.min(Math.max(novoZoom, 0.1), 8.0);
    estado.modoZoomAjustado = false;
    aplicarTransformacao();
  }

  function atualizarSplit(percentual) {
    estado.splitPercent = Math.min(Math.max(percentual, 0), 100);
    el.splitOverlay.style.width = `${estado.splitPercent}%`;
    el.splitHandle.style.left = `${estado.splitPercent}%`;

    // Mantém a imagem original do mesmo tamanho exato da imagem ASCII
    const w = el.imgPreviewAscii.width || el.imgPreviewAscii.naturalWidth;
    const h = el.imgPreviewAscii.height || el.imgPreviewAscii.naturalHeight;
    el.imgPreviewOriginal.style.width = `${w}px`;
    el.imgPreviewOriginal.style.height = `${h}px`;
  }

  function atualizarModoVisualizacao(modo) {
    estado.modoVisualizacao = modo;
    document.querySelectorAll(".tab-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.mode === modo);
    });

    if (!estado.imagemCarregada) return;

    if (modo === "text") {
      el.transformContainer.classList.add("hidden");
      el.textStage.classList.remove("hidden");
      el.zoomControls.classList.add("hidden");
      el.btnCopiarTexto.classList.remove("hidden");
    } else {
      el.textStage.classList.add("hidden");
      el.transformContainer.classList.remove("hidden");
      el.zoomControls.classList.remove("hidden");
      el.btnCopiarTexto.classList.add("hidden");

      const ehSplit = modo === "split";
      el.splitOverlay.classList.toggle("hidden", !ehSplit);
      el.splitHandle.classList.toggle("hidden", !ehSplit);
      if (ehSplit) atualizarSplit(estado.splitPercent);
    }
    agendarPreview();
  }

  // ------------------------------------------------------------------ //
  // Eventos e Inicialização
  // ------------------------------------------------------------------ //
  async function inicializar() {
    let config = null;
    try {
      const res = await fetch("/api/config");
      config = await res.json();
    } catch (_) {}

    if (config && config.ordem_templates) {
      estado.templates = config.templates;
      el.comboTemplate.innerHTML = "";
      for (const nome of config.ordem_templates) {
        const opt = document.createElement("option");
        opt.value = nome;
        opt.textContent = `${nome}  (${config.templates[nome]})`;
        el.comboTemplate.appendChild(opt);
      }
      const optCustom = document.createElement("option");
      optCustom.value = "Personalizado…";
      optCustom.textContent = "Personalizado…";
      el.comboTemplate.appendChild(optCustom);

      el.editCaracteres.value = config.caracteres_iniciais;
    }

    atualizarRotulosControles();

    // Sliders: atualização fluida + duplo clique para resetar individualmente
    const sliders = [
      el.sliderBrilho,
      el.sliderContraste,
      el.sliderSaturacao,
      el.sliderGamma,
      el.sliderEscala,
    ];
    for (const s of sliders) {
      s.addEventListener("input", agendarPreview);
      s.addEventListener("dblclick", () => {
        s.value = s.parentElement.dataset.default || 100;
        agendarPreview();
      });
    }

    el.chkInverter.addEventListener("change", agendarPreview);

    el.btnRestaurarPadroes.addEventListener("click", () => {
      el.sliderBrilho.value = 100;
      el.sliderContraste.value = 100;
      el.sliderSaturacao.value = 100;
      el.sliderGamma.value = 100;
      el.chkInverter.checked = false;
      agendarPreview();
    });

    el.comboTemplate.addEventListener("change", () => {
      const nome = el.comboTemplate.value;
      if (nome !== "Personalizado…" && estado.templates[nome]) {
        el.editCaracteres.value = estado.templates[nome];
        agendarPreview();
      }
    });

    el.editCaracteres.addEventListener("input", () => {
      el.comboTemplate.value = "Personalizado…";
      agendarPreview();
    });

    el.btnInverterRampa.addEventListener("click", () => {
      el.editCaracteres.value = [...el.editCaracteres.value].reverse().join("");
      el.comboTemplate.value = "Personalizado…";
      agendarPreview();
    });

    // Cores de fundo
    function definirCorFundo(hex) {
      el.inputCorFundo.value = hex;
      el.swatchCorAtual.style.background = hex;
      el.labelHexFundo.textContent = hex.toUpperCase();
      document.querySelectorAll(".swatch-Preset").forEach((b) => {
        b.classList.toggle("active", b.dataset.color.toLowerCase() === hex.toLowerCase());
      });
      agendarPreview();
    }

    el.inputCorFundo.addEventListener("input", () => definirCorFundo(el.inputCorFundo.value));
    document.querySelectorAll(".swatch-Preset").forEach((b) => {
      b.addEventListener("click", () => definirCorFundo(b.dataset.color));
    });

    // Botões de arquivo
    el.btnCarregarImagem.addEventListener("click", escolherImagem);
    el.btnEmptyCarregar.addEventListener("click", escolherImagem);
    el.dropZoneCard.addEventListener("click", escolherImagem);
    el.inputArquivoImagem.addEventListener("change", (e) => {
      if (e.target.files[0]) enviarArquivoImagem(e.target.files[0]);
    });

    el.btnEscolherFonte.addEventListener("click", escolherFonte);
    el.inputArquivoFonte.addEventListener("change", (e) => {
      if (e.target.files[0]) enviarArquivoFonte(e.target.files[0]);
    });

    el.btnRemoverFonte.addEventListener("click", async () => {
      if (temPywebviewApi()) await window.pywebview.api.remover_fonte();
      el.labelFonteAtual.textContent = "Padrão (Monospace)";
      el.btnRemoverFonte.classList.add("hidden");
      agendarPreview();
    });

    // Exportar imagem final
    el.btnExportar.addEventListener("click", async () => {
      if (!estado.imagemCarregada) {
        mostrarToast("Carregue uma imagem antes de exportar.");
        return;
      }
      if (!temPywebviewApi()) return;

      definirStatus("Renderizando arte em resolução final…", true);
      const res = await window.pywebview.api.exportar_imagem(coletarParametros());
      definirStatus("Pronto.");
      if (res && res.ok) {
        definirStatus(`Salvo em ${res.caminho} (${res.largura}×${res.altura} px em ${res.duracao_ms} ms)`);
        mostrarToast(`Salvo com sucesso (${res.duracao_ms} ms)!`);
      } else if (res && res.erro) {
        mostrarToast(res.erro);
      }
    });

    // Abas de modo de visualização
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => atualizarModoVisualizacao(btn.dataset.mode));
    });

    // Copiar Texto ASCII
    el.btnCopiarTexto.addEventListener("click", async () => {
      const texto = el.preTextoAscii.textContent || "";
      if (!texto) return;
      await navigator.clipboard.writeText(texto);
      mostrarToast("Arte ASCII copiada para a área de transferência!");
    });

    // Zoom e Pan no Canvas
    el.btnZoomIn.addEventListener("click", () => definirZoomManual(estado.zoom * 1.25));
    el.btnZoomOut.addEventListener("click", () => definirZoomManual(estado.zoom / 1.25));
    el.btnZoomFit.addEventListener("click", ajustarZoomATela);
    el.labelZoom.addEventListener("click", ajustarZoomATela);
    el.btnZoom100.addEventListener("click", () => {
      estado.panX = 0;
      estado.panY = 0;
      definirZoomManual(1.0);
    });

    el.canvasStage.addEventListener("wheel", (e) => {
      if (!estado.imagemCarregada || estado.modoVisualizacao === "text") return;
      e.preventDefault();
      const fator = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      definirZoomManual(estado.zoom * fator);
    }, { passive: false });

    let arrastandoPan = false;
    let arrastandoSplit = false;
    let inicioX = 0;
    let inicioY = 0;

    el.splitHandle.addEventListener("mousedown", (e) => {
      e.stopPropagation();
      arrastandoSplit = true;
    });

    el.transformContainer.addEventListener("mousedown", (e) => {
      if (e.target.closest("#splitHandle")) return;
      arrastandoPan = true;
      inicioX = e.clientX - estado.panX;
      inicioY = e.clientY - estado.panY;
      el.transformContainer.classList.add("panning");
    });

    window.addEventListener("mousemove", (e) => {
      if (arrastandoSplit) {
        const rect = el.imageWrapper.getBoundingClientRect();
        if (rect.width > 0) {
          const pct = ((e.clientX - rect.left) / rect.width) * 100;
          atualizarSplit(pct);
        }
      } else if (arrastandoPan) {
        estado.panX = e.clientX - inicioX;
        estado.panY = e.clientY - inicioY;
        estado.modoZoomAjustado = false;
        aplicarTransformacao();
      }
    });

    window.addEventListener("mouseup", () => {
      arrastandoPan = false;
      arrastandoSplit = false;
      el.transformContainer.classList.remove("panning");
    });

    window.addEventListener("resize", () => {
      if (estado.imagemCarregada && estado.modoZoomAjustado) {
        ajustarZoomATela();
      }
    });

    // Splitter redimensionável da Sidebar
    let redimensionandoSidebar = false;
    el.splitter.addEventListener("mousedown", () => {
      redimensionandoSidebar = true;
      el.splitter.classList.add("dragging");
    });

    window.addEventListener("mousemove", (e) => {
      if (!redimensionandoSidebar) return;
      const novaLargura = Math.min(Math.max(e.clientX, 280), 500);
      document.documentElement.style.setProperty("--sidebar-width", `${novaLargura}px`);
      if (estado.imagemCarregada && estado.modoZoomAjustado) ajustarZoomATela();
    });

    window.addEventListener("mouseup", () => {
      if (redimensionandoSidebar) {
        redimensionandoSidebar = false;
        el.splitter.classList.remove("dragging");
      }
    });

    el.btnToggleSidebar.addEventListener("click", () => {
      el.sidebar.classList.toggle("collapsed");
      setTimeout(() => {
        if (estado.imagemCarregada && estado.modoZoomAjustado) ajustarZoomATela();
      }, 220);
    });

    // Drag & Drop Global (Imagens e Fontes)
    let contadorDrag = 0;
    window.addEventListener("dragenter", (e) => {
      e.preventDefault();
      contadorDrag++;
      el.dropOverlay.classList.remove("hidden");
    });
    window.addEventListener("dragover", (e) => e.preventDefault());
    window.addEventListener("dragleave", () => {
      contadorDrag = Math.max(0, contadorDrag - 1);
      if (contadorDrag === 0) el.dropOverlay.classList.add("hidden");
    });
    window.addEventListener("drop", (e) => {
      e.preventDefault();
      contadorDrag = 0;
      el.dropOverlay.classList.add("hidden");
      const arq = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (!arq) return;
      const nome = arq.name.toLowerCase();
      if (nome.endsWith(".ttf") || nome.endsWith(".otf") || nome.endsWith(".ttc")) {
        enviarArquivoFonte(arq);
      } else {
        enviarArquivoImagem(arq);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", inicializar);
})();
