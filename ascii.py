import math
from pathlib import Path
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageEnhance, ImageFont

from ajustes import aplicar_ajustes

# Permite exportar imagens em escalas altas (ex.: 4K em 4x = 15360x8640) sem aviso de DecompressionBomb
Image.MAX_IMAGE_PIXELS = None

_RESAMPLING_LANCZOS = getattr(Image, "Resampling", Image).LANCZOS
_RESAMPLING_NEAREST = getattr(Image, "Resampling", Image).NEAREST

# Caminhos de fontes monoespaçadas reais do sistema com suporte amplo a Unicode
_FONTES_MONO_SISTEMA = (
    "/usr/share/fonts/adwaita-mono-fonts/AdwaitaMono-Bold.ttf",
    "/usr/share/fonts/adwaita-mono-fonts/AdwaitaMono-Regular.ttf",
    "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/liberation-mono-fonts/LiberationMono-Bold.ttf",
    "/usr/share/fonts/liberation-mono-fonts/LiberationMono-Regular.ttf",
    "/usr/share/fonts/google-noto-vf/NotoSansMono[wght].ttf",
)

_FONTE_PADRAO_CACHE = None
_CACHE_SCANLINES = {}


def carregar_fonte_padrao(tamanho=14):
    """Carrega uma fonte monoespaçada nítida do sistema (evitando a fonte proporcional padrão do Pillow)."""
    global _FONTE_PADRAO_CACHE
    if _FONTE_PADRAO_CACHE is not None and getattr(_FONTE_PADRAO_CACHE, "size", None) == tamanho:
        return _FONTE_PADRAO_CACHE

    for caminho in _FONTES_MONO_SISTEMA:
        if Path(caminho).is_file():
            try:
                _FONTE_PADRAO_CACHE = ImageFont.truetype(caminho, tamanho)
                return _FONTE_PADRAO_CACHE
            except Exception:
                continue

    try:
        _FONTE_PADRAO_CACHE = ImageFont.load_default(size=tamanho)
    except TypeError:
        _FONTE_PADRAO_CACHE = ImageFont.load_default()
    return _FONTE_PADRAO_CACHE


def carregar_imagem(caminho):
    """Carrega a imagem e converte para o formato RGB garantido."""
    return Image.open(caminho).convert("RGB")


def medida_caractere(fonte):
    """Descobre o tamanho (largura, altura) da célula de cada caractere sem cortar glifos."""
    try:
        if hasattr(fonte, "getmetrics"):
            ascent, descent = fonte.getmetrics()
            altura_metrica = ascent + descent
        else:
            altura_metrica = 0

        if hasattr(fonte, "getlength"):
            largura_avanco = int(math.ceil(fonte.getlength("M")))
        else:
            largura_avanco = 0

        bbox = fonte.getbbox("@") or fonte.getbbox("M") or fonte.getbbox("A")
        largura_bbox = (bbox[2] - bbox[0]) if bbox else 6
        altura_bbox = bbox[3] if bbox else 11

        # +1 px horizontal evita colisão entre caracteres adjacentes
        largura_char = max(largura_avanco, largura_bbox) + 1
        altura_char = max(altura_metrica, altura_bbox + 2)
    except AttributeError:
        largura_char, altura_char = 8, 14

    largura_char = max(largura_char, 6)
    altura_char = max(altura_char, 10)
    return largura_char, altura_char


def calcular_grade(largura_final, altura_final, largura_char, altura_char):
    """Calcula a grade: quantas colunas/linhas de caracteres cabem na imagem final.

    Isso define a resolução da amostragem (quantos blocos de pixels teremos).
    O mínimo de 1 coluna/linha evita crash com escalas muito pequenas.
    """
    colunas = max(largura_final // largura_char, 1)
    linhas = max(altura_final // altura_char, 1)
    return colunas, linhas


def _lut_luminosidade_para_char(caracteres_ascii, limiar_fundo=0, curva_perceptual=False):
    """Gera tabela de 256 posições mapeando brilho (0..255) -> caractere."""
    rampa = caracteres_ascii if caracteres_ascii else " .:-=+*#%@"
    ultimo = len(rampa) - 1
    if ultimo <= 0:
        return [rampa[0]] * 256

    if not curva_perceptual or limiar_fundo <= 0:
        return [rampa[int((lum / 255.0) * ultimo)] for lum in range(256)]

    # Com gate de ruído de fundo escuro e curva perceptual:
    # - Pixels quase pretos (< limiar_fundo) usam rampa[0] (espaço limpo, zero ruído de fundo).
    # - Demais valores usam curva gamma 0.68 para distribuir bem todos os caracteres do template.
    lut = []
    faixa = max(255 - limiar_fundo, 1)
    for v in range(256):
        if v < limiar_fundo:
            lut.append(rampa[0])
        else:
            norm = ((v - limiar_fundo) / float(faixa)) ** 0.68
            idx = int(norm * ultimo)
            if rampa[0] == " " and ultimo >= 1:
                idx = max(1, min(idx, ultimo))
            lut.append(rampa[min(max(idx, 0), ultimo)])
    return lut


def mapear_caracteres(pixels, colunas, linhas, caracteres_ascii):
    """Mapeia a luminosidade de cada pixel para um caractere.

    Args:
        pixels: acesso via pixels[x, y] -> (r, g, b).
        colunas: número de colunas da grade.
        linhas: número de linhas da grade.
        caracteres_ascii: ordenado do mais escuro ao mais claro.

    Returns:
        Lista de linhas; cada linha é uma lista de caracteres.
    """
    lut = _lut_luminosidade_para_char(caracteres_ascii, limiar_fundo=0, curva_perceptual=False)
    grade = []
    for y in range(linhas):
        linha = []
        for x in range(colunas):
            r, g, b = pixels[x, y]
            luminosidade = int(0.299 * r + 0.587 * g + 0.114 * b)
            linha.append(lut[luminosidade])
        grade.append(linha)
    return grade


def _renderizar_glifo_nitido(caractere, fonte, largura_char, altura_char, bytes_notdef):
    """Renderiza um caractere em máscara binária nítida (0 ou 255, zero halo de ruído).

    Inclui síntese procedural exata para caracteres de bloco/sombra (`░▒▓█▄▀`) e
    Braille (`⠁..⣿`), garantindo que nenhuma fonte produza caixas `.notdef` (tofu)
    ou borrões cinzas indistintos.
    """
    g = Image.new("L", (largura_char, altura_char), 0)
    if caractere == " ":
        return g

    w_util = max(largura_char - 1, 1)
    h_util = max(altura_char - 1, 1)
    draw = ImageDraw.Draw(g)

    # 1. Blocos e sombreados Unicode (renderização pixel-perfect sem tofu)
    if caractere == "█":
        draw.rectangle([0, 0, w_util - 1, h_util - 1], fill=255)
        return g
    if caractere == "▄":
        draw.rectangle([0, altura_char // 2, w_util - 1, h_util - 1], fill=255)
        return g
    if caractere == "▀":
        draw.rectangle([0, 0, w_util - 1, max(altura_char // 2 - 1, 0)], fill=255)
        return g
    if caractere in ("▓", "▒", "░"):
        px = g.load()
        for y in range(h_util):
            for x in range(w_util):
                ativo = (
                    ((x + y) % 2 == 0 or (x % 2 == 0 and y % 2 == 1))
                    if caractere == "▓"
                    else ((x + y) % 2 == 0 if caractere == "▒" else (x % 2 == 0 and y % 2 == 0))
                )
                if ativo:
                    px[x, y] = 255
        return g

    # 2. Padrões Braille Unicode (U+2800 .. U+28FF)
    codigo = ord(caractere)
    if 0x2800 <= codigo <= 0x28FF:
        bits = codigo - 0x2800
        if bits == 0:
            return g
        # Mapa de bits padrão Braille (2 colunas x 4 linhas)
        posicoes_bits = (
            (0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (1, 0, 0x08),
            (1, 1, 0x10), (1, 2, 0x20), (0, 3, 0x40), (1, 3, 0x80),
        )
        r_ponto = max(min(largura_char, altura_char) // 7, 1)
        for col_b, lin_b, mascara_bit in posicoes_bits:
            if bits & mascara_bit:
                cx = int((col_b + 0.6) * (w_util / 2.2))
                cy = int((lin_b + 0.6) * (h_util / 4.2))
                draw.rectangle([cx, cy, min(cx + r_ponto, w_util - 1), min(cy + r_ponto, h_util - 1)], fill=255)
        return g

    # 3. Glifo tipográfico normal: centraliza na célula (largura_char, altura_char)
    bbox = fonte.getbbox(caractere)
    if bbox:
        gw = bbox[2] - bbox[0]
        gh = bbox[3] - bbox[1]
        ox = (largura_char - gw) // 2 - bbox[0]
        oy = (altura_char - gh) // 2 - bbox[1]
    else:
        ox, oy = 0, 0

    draw.text((ox, oy), caractere, font=fonte, fill=255)

    # Se a fonte não possui o caractere (gerou caixa .notdef igual a \ufffd), substitui por '#'
    if bytes_notdef is not None and g.tobytes() == bytes_notdef and caractere != "\ufffd":
        g = Image.new("L", (largura_char, altura_char), 0)
        bbox_fb = fonte.getbbox("#")
        ox_fb = (largura_char - (bbox_fb[2] - bbox_fb[0])) // 2 - bbox_fb[0] if bbox_fb else 0
        oy_fb = (altura_char - (bbox_fb[3] - bbox_fb[1])) // 2 - bbox_fb[1] if bbox_fb else 0
        ImageDraw.Draw(g).text((ox_fb, oy_fb), "#", font=fonte, fill=255)

    # Limiarização binária (0 ou 255): elimina 100% do halo borrado ao redor das letras
    # e garante que cada pixel da letra receba 100% da cor pura da imagem.
    return g.point([255 if i >= 82 else 0 for i in range(256)])


def _obter_lut_scanlines(fonte, largura_char, altura_char, caracteres_ascii, limiar_fundo=12, curva_perceptual=True):
    """Pré-rasteriza cada caractere único uma única vez e monta LUTs por scanline."""
    rampa = caracteres_ascii if caracteres_ascii else " .:-=+*#%@"
    chave = (
        getattr(fonte, "path", None) or id(fonte),
        getattr(fonte, "size", 0),
        largura_char,
        altura_char,
        rampa,
        limiar_fundo,
        curva_perceptual,
    )
    cached = _CACHE_SCANLINES.get(chave)
    if cached is not None:
        return cached

    # Rasteriza o glifo .notdef (\ufffd) da fonte para detectar caracteres ausentes
    g_notdef = Image.new("L", (largura_char, altura_char), 0)
    bbox_nd = fonte.getbbox("\ufffd")
    if bbox_nd:
        ox_nd = (largura_char - (bbox_nd[2] - bbox_nd[0])) // 2 - bbox_nd[0]
        oy_nd = (altura_char - (bbox_nd[3] - bbox_nd[1])) // 2 - bbox_nd[1]
        ImageDraw.Draw(g_notdef).text((ox_nd, oy_nd), "\ufffd", font=fonte, fill=255)
        bytes_notdef = g_notdef.tobytes()
    else:
        bytes_notdef = None

    glyph_rows = {}
    for c in set(rampa):
        g = _renderizar_glifo_nitido(c, fonte, largura_char, altura_char, bytes_notdef)
        raw = g.tobytes()
        glyph_rows[c] = [raw[sy * largura_char : (sy + 1) * largura_char] for sy in range(altura_char)]

    lut_chars = _lut_luminosidade_para_char(rampa, limiar_fundo=limiar_fundo, curva_perceptual=curva_perceptual)
    celula_vazia = b"\x00" * largura_char
    lut_scanlines = []
    for sy in range(altura_char):
        lut_sy = [glyph_rows[lut_chars[v]][sy] for v in range(256)]
        if all(cell == celula_vazia for cell in lut_sy):
            lut_scanlines.append(None)
        else:
            lut_scanlines.append(lut_sy.__getitem__)

    if len(_CACHE_SCANLINES) > 64:
        _CACHE_SCANLINES.clear()
    _CACHE_SCANLINES[chave] = lut_scanlines
    return lut_scanlines


def _fundo_eh_claro(cor_fundo):
    """Retorna True se a cor de fundo tiver luminosidade alta (> 128)."""
    try:
        rgb = ImageColor.getrgb(cor_fundo)
        lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
        return lum > 128
    except Exception:
        return False


def renderizar_ascii(
    imagem,
    escala=1.0,
    caracteres_ascii=" .:-=+*#%@",
    cor_fundo="black",
    fonte=None,
    img_amostra=None,
):
    """Renderiza a arte ASCII a partir de uma imagem RGB (sem salvar em disco).

    Devolve o canvas PIL.Image com as letras desenhadas de forma nítida,
    sem halos/ruídos ao redor dos caracteres e com suporte completo a Unicode.
    """
    if fonte is None:
        fonte = carregar_fonte_padrao(14)

    # 1. Definir as dimensões exatas que a imagem de saída terá
    largura_original, altura_original = imagem.size
    largura_final = max(int(largura_original * escala), 1)
    altura_final = max(int(altura_original * escala), 1)

    # 2. Descobrir o tamanho de cada caractere e calcular a grade
    largura_char, altura_char = medida_caractere(fonte)
    colunas, linhas = calcular_grade(largura_final, altura_final, largura_char, altura_char)

    # 3. Redimensionar a imagem de entrada para o tamanho da grade (se não fornecida)
    if img_amostra is None or img_amostra.size != (colunas, linhas):
        img_amostra = imagem.resize((colunas, linhas), _RESAMPLING_LANCZOS)

    # 4. Ajustar orientação da rampa conforme a cor de fundo (escuro vs claro)
    rampa = caracteres_ascii if caracteres_ascii else " .:-=+*#%@"
    fundo_claro = _fundo_eh_claro(cor_fundo)
    if not fundo_claro and len(rampa) >= 2 and rampa[-1] == " " and rampa[0] != " ":
        # Rampa foi passada no formato antigo (denso -> espaço); inverte para fundo escuro
        rampa = rampa[::-1]
    elif fundo_claro and len(rampa) >= 2 and rampa[0] == " " and rampa[-1] != " ":
        # Em fundo claro, pixels escuros recebem mais tinta e pixels claros ficam vazios
        rampa = rampa[::-1]

    # 5. Extrair brilho perceptivo (combina luminância e canal máximo RGB para não
    # apagar vermelhos/azuis intensos)
    r_ch, g_ch, b_ch = img_amostra.split()
    canal_max = ImageChops.lighter(r_ch, ImageChops.lighter(g_ch, b_ch))
    brilho_bytes = canal_max.tobytes()

    w_grade = colunas * largura_char
    h_grade = linhas * altura_char
    limiar = 0 if fundo_claro else 12
    lut_scanlines = _obter_lut_scanlines(
        fonte, largura_char, altura_char, rampa, limiar_fundo=limiar, curva_perceptual=not fundo_claro
    )

    linha_vazia = b"\x00" * w_grade
    scanlines = []
    join = b"".join
    _map = map
    for y in range(linhas):
        row = brilho_bytes[y * colunas : (y + 1) * colunas]
        for getter in lut_scanlines:
            if getter is None:
                scanlines.append(linha_vazia)
            else:
                scanlines.append(join(_map(getter, row)))

    mascara = Image.frombytes("L", (w_grade, h_grade), join(scanlines))

    # 6. Realçar levemente a vivacidade das cores dos caracteres em fundo escuro
    # (compensando o fato de cada letra ocupar apenas ~25% da área da célula)
    if not fundo_claro:
        amostra_cores = ImageEnhance.Brightness(
            ImageEnhance.Color(img_amostra).enhance(1.15)
        ).enhance(1.25)
    else:
        amostra_cores = img_amostra

    cores = amostra_cores.resize((w_grade, h_grade), _RESAMPLING_NEAREST)
    imagem_saida = Image.new("RGB", (largura_final, altura_final), color=cor_fundo)
    offset_x = (largura_final - w_grade) // 2
    offset_y = (altura_final - h_grade) // 2
    imagem_saida.paste(cores, (offset_x, offset_y), mascara)

    return imagem_saida


def converter_para_ascii_jpeg(
    caminho_entrada,
    caminho_saida,
    escala=1.0,
    caracteres_ascii=" .:-=+*#%@",
    cor_fundo="black",
    brilho=1.0,
    contraste=1.0,
    saturacao=1.0,
    gamma=1.0,
    inverter=False,
):
    """Converte uma imagem em arte ASCII e salva em disco com nitidez máxima (4:4:4)."""
    try:
        imagem = carregar_imagem(caminho_entrada)
    except Exception as e:
        print(f"Erro ao carregar a imagem: {e}")
        return

    fonte = carregar_fonte_padrao(14)
    largura_final = max(int(imagem.size[0] * escala), 1)
    altura_final = max(int(imagem.size[1] * escala), 1)
    largura_char, altura_char = medida_caractere(fonte)
    colunas, linhas = calcular_grade(largura_final, altura_final, largura_char, altura_char)

    amostra = imagem.resize((colunas, linhas), _RESAMPLING_LANCZOS)
    amostra_ajustada = aplicar_ajustes(
        amostra,
        brilho=brilho,
        contraste=contraste,
        saturacao=saturacao,
        gamma=gamma,
        inverter=inverter,
    )

    imagem_saida = renderizar_ascii(
        imagem,
        escala=escala,
        caracteres_ascii=caracteres_ascii,
        cor_fundo=cor_fundo,
        fonte=fonte,
        img_amostra=amostra_ajustada,
    )

    # subsampling=0 (4:4:4) impede o borramento de cor (chroma bleeding) e ruído ao redor das letras
    if str(caminho_saida).lower().endswith(".png"):
        imagem_saida.save(caminho_saida, "PNG")
    else:
        imagem_saida.save(caminho_saida, "JPEG", quality=98, subsampling=0)
    print(f"Sucesso! Imagem gerada com {imagem_saida.size[0]}x{imagem_saida.size[1]} pixels.")
    print(f"Salva em: {caminho_saida}")


if __name__ == "__main__":
    converter_para_ascii_jpeg(
        caminho_entrada="mysterious-artifact.jpg",
        caminho_saida="gigante.jpeg",
        escala=1.0,
        caracteres_ascii=" .:-=+*$#@",
    )
