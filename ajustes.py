"""Ajustes de imagem (brilho, contraste, saturação, gamma e inversão).

Todas as funções são puras: recebem uma PIL.Image e devolvem uma nova imagem,
nunca mutando a entrada. Fatores de 1.0 (ou gamma 1.0) não alteram a imagem.
"""

from PIL import ImageEnhance, ImageOps


def aplicar_ajustes(
    imagem,
    brilho=1.0,
    contraste=1.0,
    saturacao=1.0,
    gamma=1.0,
    inverter=False,
):
    """Aplica os ajustes na ordem: brilho -> contraste -> saturação -> gamma -> inversão.

    Args:
        imagem: PIL.Image em RGB.
        brilho: fator 0.0 (preto) a 2.0; 1.0 = neutro.
        contraste: fator 0.0 (cinza plano) a 2.0; 1.0 = neutro.
        saturacao: fator 0.0 (escala de cinza) a 2.0; 1.0 = neutro.
        gamma: 0.1 a 3.0; > 1 escurece, < 1 clareia; 1.0 = neutro.
        inverter: inverte as cores da imagem.

    Returns:
        PIL.Image nova com os ajustes aplicados.
    """
    resultado = imagem
    if brilho != 1.0:
        resultado = ImageEnhance.Brightness(resultado).enhance(brilho)
    if contraste != 1.0:
        resultado = ImageEnhance.Contrast(resultado).enhance(contraste)
    if saturacao != 1.0:
        resultado = ImageEnhance.Color(resultado).enhance(saturacao)
    if gamma != 1.0:
        # Transformação via tabela de busca (LUT) em C: gamma > 1 escurece, < 1 clareia
        inv_gamma = 1.0 / gamma
        lut = [int(255.0 * ((i / 255.0) ** inv_gamma)) for i in range(256)]
        resultado = resultado.point(lut * len(resultado.getbands()))
    if inverter:
        resultado = ImageOps.invert(resultado)
    return resultado
