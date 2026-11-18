"""Interface visual moderna em HTML/CSS/JS via PyWebView para o conversor ASCII.

Arquitetura voltada à máxima eficiência e fidelidade 1:1 entre preview e imagem salva:
1. O preview e a exportação final utilizam exatamente o mesmo pipeline
   (`renderizar_final`), com a mesma `escala` e a mesma grade `(colunas, linhas)`
   de caracteres. O último resultado renderizado no preview fica em cache na
   sessão para que o salvamento seja instantâneo e 100% idêntico ao preview.
2. Quando o usuário move sliders de cor (brilho, contraste, saturação, gamma,
   inversão, caracteres ou fundo), o redimensionamento LANCZOS da imagem original
   para `(colunas, linhas)` é reaproveitado do cache, rodando `aplicar_ajustes`
   apenas sobre os pixels da grade.
3. O preview é transmitido em PNG binário sem perdas (`compress_level=1`),
   eliminando artefatos de compressão JPEG ao redor dos caracteres.
"""

import io
from pathlib import Path
import threading
import time

import bottle
from PIL import Image, ImageFont
import webview

from ajustes import aplicar_ajustes
from ascii import (
    _RESAMPLING_LANCZOS,
    calcular_grade,
    carregar_fonte_padrao,
    carregar_imagem,
    mapear_caracteres,
    medida_caractere,
    renderizar_ascii,
)
import templates

DIRETORIO_WEB = Path(__file__).resolve().parent / "web"
LIMITE_ORIGINAL_PREVIEW_PX = 1440
LIMITE_TEXTURA_WEBVIEW_PX = 4096


class SessaoConversor:
    """Gerencia o estado da sessão e os caches de amostragem e renderização."""

    def __init__(self):
        self._lock = threading.RLock()
        self.imagem_original = None  # PIL.Image (RGB)
        self.nome_imagem = None
        self.caminho_imagem = None

        self.fonte = None            # PIL.ImageFont customizada ou None
        self.nome_fonte = None
        self.caminho_fonte = None

        # Cache da imagem redimensionada para (id_imagem, colunas, linhas)
        self._chave_amostra = None
        self._img_amostra_base = None

        # Cache da última imagem ASCII completa renderizada (garante paridade 1:1 preview == salvo)
        self._chave_render = None
        self._ultima_imagem_renderizada = None

        # Cache do JPEG da imagem original para o comparador Antes/Depois
        self._jpeg_original_preview = None

    def _invalidar_caches_render(self):
        self._chave_Render = None
        self._ultima_imagem_renderizada = None

    def definir_imagem(self, imagem, nome="imagem", caminho=None):
        """Define uma nova imagem RGB base e invalida os caches dependentes."""
        img_rgb = imagem.convert("RGB")
        with self._lock:
            self.imagem_original = img_rgb
            self.nome_imagem = nome
            self.caminho_imagem = caminho
            self._chave_amostra = None
            self._img_amostra_base = None
            self._chave_render = None
            self._ultima_imagem_renderizada = None
            self._jpeg_original_preview = None
        return {
            "ok": True,
            "nome": nome,
            "caminho": caminho or nome,
            "largura": img_rgb.size[0],
            "altura": img_rgb.size[1],
        }

    def carregar_imagem_caminho(self, caminho):
        """Carrega imagem a partir de um caminho em disco."""
        img = carregar_imagem(caminho)
        return self.definir_imagem(img, nome=Path(caminho).name, caminho=str(caminho))

    def carregar_imagem_bytes(self, dados, nome="upload.png"):
        """Carrega imagem a partir de bytes enviados via Drag & Drop."""
        img = Image.open(io.BytesIO(dados)).convert("RGB")
        return self.definir_imagem(img, nome=nome, caminho=nome)

    def carregar_fonte_caminho(self, caminho):
        """Valida e carrega uma fonte TrueType/OpenType do disco."""
        fonte = ImageFont.truetype(str(caminho), 14)
        with self._lock:
            self.fonte = fonte
            self.nome_fonte = Path(caminho).name
            self.caminho_fonte = str(caminho)
            self._chave_render = None
            self._ultima_imagem_renderizada = None
        return {"ok": True, "nome": self.nome_fonte, "caminho": self.caminho_fonte}

    def carregar_fonte_bytes(self, dados, nome="fonte.ttf"):
        """Valida e carrega uma fonte TrueType/OpenType a partir de bytes em memória."""
        fonte = ImageFont.truetype(io.BytesIO(dados), 14)
        with self._lock:
            self.fonte = fonte
            self.nome_fonte = nome
            self.caminho_fonte = nome
            self._chave_render = None
            self._ultima_imagem_renderizada = None
        return {"ok": True, "nome": self.nome_fonte}

    def remover_fonte(self):
        """Restaura a fonte monoespaçada padrão."""
        with self._lock:
            self.fonte = None
            self.nome_fonte = None
            self.caminho_fonte = None
            self._chave_render = None
            self._ultima_imagem_renderizada = None
        return {"ok": True, "nome": None}

    def obter_jpeg_original_preview(self):
        """Retorna bytes JPEG da imagem original para miniatura e split-view."""
        with self._lock:
            if self.imagem_original is None:
                return None
            if self._jpeg_original_preview is not None:
                return self._jpeg_original_preview

            img = self.imagem_original
            maior_lado = max(img.size)
            if maior_lado > LIMITE_ORIGINAL_PREVIEW_PX:
                fator = LIMITE_ORIGINAL_PREVIEW_PX / float(maior_lado)
                novo_tam = (max(int(img.size[0] * fator), 1), max(int(img.size[1] * fator), 1))
                img = img.resize(novo_tam, _RESAMPLING_LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=92, subsampling=0)
            self._jpeg_original_preview = buf.getvalue()
            return self._jpeg_original_preview

    def _obter_amostra_ajustada(self, colunas, linhas, params):
        """Obtém a grade (colunas, linhas) do cache e aplica os ajustes de cor."""
        chave = (id(self.imagem_original), colunas, linhas)
        if self._chave_amostra != chave or self._img_amostra_base is None:
            self._img_amostra_base = self.imagem_original.resize(
                (colunas, linhas), _RESAMPLING_LANCZOS
            )
            self._chave_amostra = chave

        return aplicar_ajustes(
            self._img_amostra_base,
            brilho=float(params.get("brilho", 100)) / 100.0,
            contraste=float(params.get("contraste", 100)) / 100.0,
            saturacao=float(params.get("saturacao", 100)) / 100.0,
            gamma=max(float(params.get("gamma", 100)) / 100.0, 0.1),
            inverter=bool(params.get("inverter", False)),
        )

    @staticmethod
    def _extrair_caracteres(params):
        """Extrai a rampa de caracteres preservando o espaço (' ') para o fundo."""
        texto = str(params.get("caracteres", ""))
        return texto if (texto and len(texto) >= 2) else " .:-=+*#%@"

    def _normalizar_chave_params(self, params):
        return (
            id(self.imagem_original),
            id(self.fonte),
            round(float(params.get("brilho", 100)), 2),
            round(float(params.get("contraste", 100)), 2),
            round(float(params.get("saturacao", 100)), 2),
            round(float(params.get("gamma", 100)), 2),
            bool(params.get("inverter", False)),
            round(max(float(params.get("escala", 100)) / 100.0, 0.05), 4),
            self._extrair_caracteres(params),
            str(params.get("cor_fundo", "#000000") or "#000000"),
        )

    def _renderizar_com_meta(self, params):
        """Renderiza a arte ASCII na escala exata solicitada e guarda em cache."""
        with self._lock:
            if self.imagem_original is None:
                raise ValueError("Nenhuma imagem carregada.")

            escala = max(float(params.get("escala", 100)) / 100.0, 0.05)
            cor_fundo = str(params.get("cor_fundo", "#000000") or "#000000")
            caracteres = self._extrair_caracteres(params)
            fonte = self.fonte or carregar_fonte_padrao(14)

            larg_orig, alt_orig = self.imagem_original.size
            larg_final = max(int(larg_orig * escala), 1)
            alt_final = max(int(alt_orig * escala), 1)
            larg_char, alt_char = medida_caractere(fonte)
            colunas, linhas = calcular_grade(larg_final, alt_final, larg_char, alt_char)

            chave_render = self._normalizar_chave_params(params)
            if self._chave_render == chave_render and self._ultima_imagem_renderizada is not None:
                imagem_renderizada = self._ultima_imagem_renderizada
            else:
                amostra_ajustada = self._obter_amostra_ajustada(colunas, linhas, params)
                imagem_renderizada = renderizar_ascii(
                    self.imagem_original,
                    escala=escala,
                    caracteres_ascii=caracteres,
                    cor_fundo=cor_fundo,
                    fonte=fonte,
                    img_amostra=amostra_ajustada,
                )
                self._chave_render = chave_render
                self._ultima_imagem_renderizada = imagem_renderizada

            return imagem_renderizada, {
                "largura_final": imagem_renderizada.size[0],
                "altura_final": imagem_renderizada.size[1],
                "colunas": colunas,
                "linhas": linhas,
            }

    def renderizar_preview_jpeg(self, params):
        """Renderiza o preview usando exatamente a mesma imagem final (paridade 1:1)."""
        inicio = time.perf_counter()
        imagem_renderizada, info = self._renderizar_com_meta(params or {})

        # Se a imagem renderizada ultrapassar o limite de textura da WebView (ex.: 15360px em 400%),
        # reduzimos apenas a cópia de exibição APÓS a renderização ASCII completa, preservando
        # exatamente a mesma grade de caracteres da imagem salva.
        img_exibicao = imagem_renderizada
        maior_lado = max(img_exibicao.size)
        if maior_lado > LIMITE_TEXTURA_WEBVIEW_PX:
            fator = LIMITE_TEXTURA_WEBVIEW_PX / float(maior_lado)
            novo_tam = (
                max(int(img_exibicao.size[0] * fator), 1),
                max(int(img_exibicao.size[1] * fator), 1),
            )
            img_exibicao = img_exibicao.resize(novo_tam, _RESAMPLING_LANCZOS)

        buf = io.BytesIO()
        img_exibicao.save(buf, format="PNG", compress_level=1)
        duracao_ms = (time.perf_counter() - inicio) * 1000.0

        meta = {
            "largura_final": info["largura_final"],
            "altura_final": info["altura_final"],
            "largura_preview": img_exibicao.size[0],
            "altura_preview": img_exibicao.size[1],
            "colunas": info["colunas"],
            "linhas": info["linhas"],
            "duracao_ms": round(duracao_ms, 1),
        }
        return buf.getvalue(), meta

    def gerar_texto_ascii(self, params):
        """Gera a matriz de caracteres em texto puro na grade da escala escolhida."""
        inicio = time.perf_counter()
        with self._lock:
            if self.imagem_original is None:
                raise ValueError("Nenhuma imagem carregada.")

            escala_usuario = max(float(params.get("escala", 100)) / 100.0, 0.05)
            caracteres = self._extrair_caracteres(params)
            fonte = self.fonte or carregar_fonte_padrao(14)

            larg_orig, alt_orig = self.imagem_original.size
            larg_final = max(int(larg_orig * escala_usuario), 1)
            alt_final = max(int(alt_orig * escala_usuario), 1)
            larg_char, alt_char = medida_caractere(fonte)
            colunas, linhas = calcular_grade(larg_final, alt_final, larg_char, alt_char)

            amostra_ajustada = self._obter_amostra_ajustada(colunas, linhas, params)
            grade = mapear_caracteres(amostra_ajustada.load(), colunas, linhas, caracteres)

        texto = "\n".join("".join(linha) for linha in grade)
        duracao_ms = (time.perf_counter() - inicio) * 1000.0
        return {
            "ok": True,
            "texto": texto,
            "colunas": colunas,
            "linhas": linhas,
            "duracao_ms": round(duracao_ms, 1),
        }

    def renderizar_final(self, params):
        """Devolve a arte ASCII na resolução final completa (reutilizando o cache do preview)."""
        imagem, _ = self._renderizar_com_meta(params or {})
        return imagem


class ApiDesktop:
    """Ponte JavaScript <-> Python (`window.pywebview.api`) para diálogos nativos."""

    def __init__(self, sessao: SessaoConversor):
        self._sessao = sessao
        self._janela = None

    def vincular_janela(self, janela):
        self._janela = janela

    def obter_configuracao(self):
        """Retorna templates disponíveis e estado inicial para o frontend."""
        lista_nomes = templates.listar_templates()
        mapa_templates = {nome: templates.obter_template(nome) for nome in lista_nomes}
        return {
            "templates": mapa_templates,
            "ordem_templates": lista_nomes,
            "template_inicial": lista_nomes[0],
            "caracteres_iniciais": mapa_templates[lista_nomes[0]],
        }

    def selecionar_imagem(self):
        """Abre diálogo de seleção de imagem e carrega na sessão."""
        if self._janela is None:
            return {"ok": False, "cancelado": True}
        arquivos = self._janela.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            file_types=("Imagens (*.png;*.jpg;*.jpeg;*.bmp;*.webp)",),
        )
        if not arquivos:
            return {"ok": False, "cancelado": True}
        caminho = arquivos[0] if isinstance(arquivos, (list, tuple)) else arquivos
        if not caminho:
            return {"ok": False, "cancelado": True}
        try:
            return self._sessao.carregar_imagem_caminho(caminho)
        except Exception as e:
            return {"ok": False, "erro": f"Não foi possível carregar a imagem: {e}"}

    def selecionar_fonte(self):
        """Abre diálogo para escolha de arquivo de fonte (.ttf, .otf, .ttc)."""
        if self._janela is None:
            return {"ok": False, "cancelado": True}
        arquivos = self._janela.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            file_types=("Fontes (*.ttf;*.otf;*.ttc)",),
        )
        if not arquivos:
            return {"ok": False, "cancelado": True}
        caminho = arquivos[0] if isinstance(arquivos, (list, tuple)) else arquivos
        if not caminho:
            return {"ok": False, "cancelado": True}
        try:
            return self._sessao.carregar_fonte_caminho(caminho)
        except Exception as e:
            return {"ok": False, "erro": f"Fonte inválida: {e}"}

    def remover_fonte(self):
        """Volta para a fonte monoespaçada padrão."""
        return self._sessao.remover_fonte()

    def exportar_imagem(self, params):
        """Abre diálogo de salvamento e salva a imagem idêntica ao preview."""
        if self._sessao.imagem_original is None:
            return {"ok": False, "erro": "Carregue uma imagem antes de exportar."}
        if self._janela is None:
            return {"ok": False, "cancelado": True}

        arquivos = self._janela.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename="arte_ascii.png",
            file_types=("PNG Sem Perdas (*.png)", "JPEG Alta Nitidez (*.jpeg;*.jpg)"),
        )
        if not arquivos:
            return {"ok": False, "cancelado": True}
        caminho = arquivos[0] if isinstance(arquivos, (list, tuple)) else arquivos
        if not caminho:
            return {"ok": False, "cancelado": True}

        inicio = time.perf_counter()
        try:
            imagem = self._sessao.renderizar_final(params or {})
            if str(caminho).lower().endswith(".png"):
                imagem.save(caminho, "PNG")
            else:
                imagem.save(caminho, "JPEG", quality=98, subsampling=0)
        except Exception as e:
            return {"ok": False, "erro": f"Falha ao salvar a imagem: {e}"}

        duracao_ms = (time.perf_counter() - inicio) * 1000.0
        return {
            "ok": True,
            "caminho": str(caminho),
            "largura": imagem.size[0],
            "altura": imagem.size[1],
            "duracao_ms": round(duracao_ms, 1),
        }


def criar_servidor_http(sessao: SessaoConversor) -> bottle.Bottle:
    """Cria a aplicação WSGI Bottle que serve a UI e os endpoints binários."""
    app = bottle.Bottle()

    @app.get("/")
    def index():
        return bottle.static_file("index.html", root=str(DIRETORIO_WEB))

    @app.get("/static/<filepath:path>")
    def arquivos_estaticos(filepath):
        return bottle.static_file(filepath, root=str(DIRETORIO_WEB))

    @app.get("/api/config")
    def api_config():
        api_temp = ApiDesktop(sessao)
        return api_temp.obter_configuracao()

    @app.get("/api/original")
    def api_original():
        dados = sessao.obter_jpeg_original_preview()
        if dados is None:
            bottle.response.status = 404
            return "Nenhuma imagem carregada."
        bottle.response.content_type = "image/jpeg"
        bottle.response.set_header("Cache-Control", "no-store")
        return dados

    @app.post("/api/preview")
    def api_preview():
        params = bottle.request.json or {}
        try:
            png_bytes, meta = sessao.renderizar_preview_jpeg(params)
        except ValueError as e:
            bottle.response.status = 400
            return str(e)
        except Exception as e:
            bottle.response.status = 500
            return f"Erro ao renderizar preview: {e}"

        bottle.response.content_type = "image/png"
        bottle.response.set_header("Cache-Control", "no-store")
        bottle.response.set_header("X-Output-Width", str(meta["largura_final"]))
        bottle.response.set_header("X-Output-Height", str(meta["altura_final"]))
        bottle.response.set_header("X-Preview-Width", str(meta["largura_preview"]))
        bottle.response.set_header("X-Preview-Height", str(meta["altura_preview"]))
        bottle.response.set_header("X-Grid-Cols", str(meta["colunas"]))
        bottle.response.set_header("X-Grid-Rows", str(meta["linhas"]))
        bottle.response.set_header("X-Render-Ms", str(meta["duracao_ms"]))
        return png_bytes

    @app.post("/api/texto")
    def api_texto():
        params = bottle.request.json or {}
        try:
            return sessao.gerar_texto_ascii(params)
        except ValueError as e:
            bottle.response.status = 400
            return {"ok": False, "erro": str(e)}
        except Exception as e:
            bottle.response.status = 500
            return {"ok": False, "erro": f"Erro ao gerar texto: {e}"}

    @app.post("/api/upload-imagem")
    def api_upload_imagem():
        arquivo = bottle.request.files.get("arquivo")
        if arquivo is not None:
            nome = arquivo.raw_filename or arquivo.filename or "upload.png"
            dados = arquivo.file.read()
        else:
            nome = bottle.request.headers.get("X-File-Name", "upload.png")
            dados = bottle.request.body.read()

        if not dados:
            bottle.response.status = 400
            return {"ok": False, "erro": "Arquivo vazio."}
        try:
            return sessao.carregar_imagem_bytes(dados, nome=nome)
        except Exception as e:
            bottle.response.status = 400
            return {"ok": False, "erro": f"Imagem inválida: {e}"}

    @app.post("/api/upload-fonte")
    def api_upload_fonte():
        arquivo = bottle.request.files.get("arquivo")
        if arquivo is not None:
            nome = arquivo.raw_filename or arquivo.filename or "fonte.ttf"
            dados = arquivo.file.read()
        else:
            nome = bottle.request.headers.get("X-File-Name", "fonte.ttf")
            dados = bottle.request.body.read()

        if not dados:
            bottle.response.status = 400
            return {"ok": False, "erro": "Arquivo de fonte vazio."}
        try:
            return sessao.carregar_fonte_bytes(dados, nome=nome)
        except Exception as e:
            bottle.response.status = 400
            return {"ok": False, "erro": f"Fonte inválida: {e}"}

    return app


def main():
    """Inicializa a janela desktop PyWebView com backend Qt e servidor local."""
    try:
        from PySide6.QtCore import QCoreApplication, Qt

        # Evita o diálogo nativo GTK3 (bug de segfault em gtk_file_system_model no Fedora)
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
    except Exception:
        pass

    sessao = SessaoConversor()
    api = ApiDesktop(sessao)
    app_http = criar_servidor_http(sessao)

    janela = webview.create_window(
        title="ASCII Studio — Conversor de Imagem para Arte ASCII",
        url=app_http,
        js_api=api,
        width=1240,
        height=780,
        min_size=(760, 500),
        background_color="#0f1117",
        text_select=True,
    )
    api.vincular_janela(janela)
    webview.start(gui="qt", debug=False)


if __name__ == "__main__":
    main()
