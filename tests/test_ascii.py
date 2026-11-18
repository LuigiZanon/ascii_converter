"""Testes do core (ascii), dos ajustes e dos templates."""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from ajustes import aplicar_ajustes
from ascii import (
    converter_para_ascii_jpeg,
    mapear_caracteres,
    renderizar_ascii,
)
import templates


def _imagem_solido(cor, tamanho=(40, 30)):
    return Image.new("RGB", tamanho, cor)


def _luminosidade_media(imagem):
    pixels = list(imagem.get_flattened_data())
    return sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in pixels) / len(pixels)


def _desvio_padrao(imagem):
    valores = [sum(p) / 3 for p in imagem.get_flattened_data()]
    media = sum(valores) / len(valores)
    return (sum((v - media) ** 2 for v in valores) / len(valores)) ** 0.5


# ------------------------- ajustes.py ------------------------- #

def test_aplicar_ajustes_preserva_tamanho():
    imagem = _imagem_solido((120, 60, 200))
    resultado = aplicar_ajustes(imagem, brilho=1.5, contraste=0.8, saturacao=1.3, gamma=1.2)
    assert resultado.size == imagem.size


def test_brilho_aumenta_luminosidade_media():
    imagem = _imagem_solido((100, 100, 100))
    mais_claro = aplicar_ajustes(imagem, brilho=1.5)
    assert _luminosidade_media(mais_claro) > _luminosidade_media(imagem)


def test_contraste_aumenta_desvio_padrao():
    random.seed(42)
    imagem = Image.new("RGB", (30, 30))
    imagem.putdata([(random.randrange(256),) * 3 for _ in range(30 * 30)])
    ajustado = aplicar_ajustes(imagem, contraste=1.8)
    assert _desvio_padrao(ajustado) > _desvio_padrao(imagem)


def test_inverter():
    preto = _imagem_solido((0, 0, 0), (10, 10))
    invertido = aplicar_ajustes(preto, inverter=True)
    assert invertido.getpixel((0, 0)) == (255, 255, 255)


def test_gamma_neutro_nao_altera():
    imagem = _imagem_solido((100, 150, 200))
    resultado = aplicar_ajustes(imagem, gamma=1.0)
    assert list(resultado.get_flattened_data()) == list(imagem.get_flattened_data())


# ------------------------- ascii.py ------------------------- #

def test_mapear_caracteres_extremos():
    rampa = "@%#*+=-:. "
    preta = _imagem_solido((0, 0, 0), (8, 4))
    branca = _imagem_solido((255, 255, 255), (8, 4))
    grade_preto = mapear_caracteres(preta.load(), 8, 4, rampa)
    grade_branco = mapear_caracteres(branca.load(), 8, 4, rampa)
    assert all(c == rampa[0] for linha in grade_preto for c in linha)
    assert all(c == rampa[-1] for linha in grade_branco for c in linha)


def test_renderizar_ascii_dimensoes():
    imagem = _imagem_solido((128, 64, 0), (200, 100))
    resultado = renderizar_ascii(imagem, escala=2.0)
    assert resultado.size == (400, 200)


def test_renderizar_ascii_escala_minima_nao_crasha():
    imagem = _imagem_solido((200, 100, 50), (60, 40))
    resultado = renderizar_ascii(imagem, escala=0.25)
    assert resultado.size[0] >= 1 and resultado.size[1] >= 1


def test_converter_para_ascii_jpeg_gera_arquivo(tmp_path):
    entrada = tmp_path / "entrada.png"
    _imagem_solido((10, 200, 30), (80, 60)).save(entrada)
    saida = tmp_path / "saida.jpeg"
    converter_para_ascii_jpeg(str(entrada), str(saida), escala=1.0)
    assert saida.exists()
    with Image.open(saida) as img:
        assert img.size[0] > 0 and img.size[1] > 0


# ------------------------- templates.py ------------------------- #

def test_templates_disponiveis():
    nomes = templates.listar_templates()
    assert len(nomes) >= 10
    assert len(set(nomes)) == len(nomes), "nomes de template duplicados"
    for nome in nomes:
        chars = templates.obter_template(nome)
        assert len(chars) >= 2
        assert len(set(chars)) >= 2, f"template '{nome}' sem contraste (caracteres repetidos)"


def test_renderizar_ascii_sem_ruido_ao_redor_dos_caracteres():
    """Garante que apenas os caracteres tenham a cor da imagem e o fundo seja 100% puro."""
    cor_img = (220, 40, 20)
    imagem = _imagem_solido(cor_img, (120, 80))
    saida = renderizar_ascii(imagem, escala=1.0, caracteres_ascii=" .:-=+*#%@", cor_fundo="#000000")
    cores_unicas = set(saida.get_flattened_data())
    # Não pode existir nenhum pixel com cor intermediária/ruído entre o fundo (0,0,0) e a cor do glifo
    assert (0, 0, 0) in cores_unicas
    assert len(cores_unicas) == 2, f"Encontradas cores de ruído/halo indesejadas: {cores_unicas}"


def test_todos_templates_renderizam_glifos_distintos_sem_tofu():
    """Garante que templates Unicode (Braille, Sombreado, Blocos) não virem caixas .notdef."""
    from ascii import _renderizar_glifo_nitido, carregar_fonte_padrao, medida_caractere

    fonte = carregar_fonte_padrao(14)
    w, h = medida_caractere(fonte)
    for nome in templates.listar_templates():
        rampa = templates.obter_template(nome)
        bitmaps = set()
        for ch in set(rampa):
            if ch == " ":
                continue
            g = _renderizar_glifo_nitido(ch, fonte, w, h, None)
            raw = g.tobytes()
            assert any(b > 0 for b in raw), f"Caractere {ch!r} do template '{nome}' ficou invisível"
            bitmaps.add(raw)
        # Cada caractere visível do template deve produzir um desenho próprio (não uma mesma caixa tofu)
        chars_visiveis = set(rampa) - {" "}
        assert len(bitmaps) == len(chars_visiveis), (
            f"Template '{nome}' colapsou múltiplos caracteres no mesmo desenho (tofu)"
        )

