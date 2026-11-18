"""Testes da camada de interface PyWebView (SessaoConversor, ApiDesktop e HTTP)."""

import io
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image
import pytest

from gui import DIRETORIO_WEB, ApiDesktop, SessaoConversor, criar_servidor_http


def _criar_imagem_teste(tamanho=(160, 120), cor=(120, 180, 90)):
    return Image.new("RGB", tamanho, cor)


def test_arquivos_web_existem():
    assert (DIRETORIO_WEB / "index.html").is_file()
    assert (DIRETORIO_WEB / "styles.css").is_file()
    assert (DIRETORIO_WEB / "app.js").is_file()


def test_api_desktop_configuracao_inicial():
    sessao = SessaoConversor()
    api = ApiDesktop(sessao)
    cfg = api.obter_configuracao()
    assert "templates" in cfg
    assert len(cfg["ordem_templates"]) >= 10
    assert cfg["template_inicial"] in cfg["templates"]


def test_sessao_cache_amostra_e_preview_binario():
    sessao = SessaoConversor()
    img = _criar_imagem_teste((320, 240))
    info = sessao.definir_imagem(img, nome="teste.png")
    assert info["ok"] is True
    assert info["largura"] == 320
    assert info["altura"] == 240

    # Primeira chamada popula o cache da grade (colunas, linhas)
    jpeg_bytes, meta = sessao.renderizar_preview_jpeg({"brilho": 110, "escala": 100})
    assert len(jpeg_bytes) > 100
    assert meta["largura_final"] == 320
    assert meta["altura_final"] == 240
    amostra_ref = sessao._img_amostra_base
    assert amostra_ref is not None

    # Segunda chamada com mesma escala reutiliza exatamente o mesmo objeto de amostra base
    jpeg_bytes_2, _ = sessao.renderizar_preview_jpeg({"brilho": 140, "contraste": 120, "escala": 100})
    assert sessao._img_amostra_base is amostra_ref
    assert len(jpeg_bytes_2) > 100


def test_sessao_gerar_texto_ascii():
    sessao = SessaoConversor()
    sessao.definir_imagem(_criar_imagem_teste((80, 40), (0, 0, 0)))
    res = sessao.gerar_texto_ascii({"caracteres": "@. ", "escala": 100})
    assert res["ok"] is True
    assert res["colunas"] >= 1
    assert res["linhas"] >= 1
    assert "@" in res["texto"]


def test_rotas_servidor_http_registradas():
    sessao = SessaoConversor()
    app = criar_servidor_http(sessao)
    rotas = {r.rule for r in app.routes}
    assert "/" in rotas
    assert "/api/config" in rotas
    assert "/api/preview" in rotas
    assert "/api/texto" in rotas
    assert "/api/original" in rotas
    assert "/api/upload-imagem" in rotas


def test_preview_muda_com_escala_e_iguala_imagem_final():
    """Garante que modificar a escala altera o preview e mantém paridade 1:1 com a imagem salva."""
    sessao = SessaoConversor()
    sessao.definir_imagem(_criar_imagem_teste((600, 400), (180, 90, 40)))

    png_50, meta_50 = sessao.renderizar_preview_jpeg({"escala": 50})
    img_final_50 = sessao.renderizar_final({"escala": 50})

    png_150, meta_150 = sessao.renderizar_preview_jpeg({"escala": 150})
    img_final_150 = sessao.renderizar_final({"escala": 150})

    # A grade de caracteres e as dimensões do preview devem mudar quando a escala muda
    assert (meta_50["colunas"], meta_50["linhas"]) != (meta_150["colunas"], meta_150["linhas"])
    assert (meta_50["largura_preview"], meta_50["altura_preview"]) == (300, 200)
    assert (meta_150["largura_preview"], meta_150["altura_preview"]) == (900, 600)

    # A imagem decodificada do preview deve ter exatamente as mesmas dimensões e pixels da imagem final
    img_prev_150 = Image.open(io.BytesIO(png_150))
    assert img_prev_150.size == img_final_150.size
    assert list(img_prev_150.get_flattened_data()) == list(img_final_150.get_flattened_data())

