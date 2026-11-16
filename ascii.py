from PIL import Image, ImageDraw, ImageFont

def converter_para_ascii_jpeg(
    caminho_entrada, 
    caminho_saida, 
    escala=1.0, 
    caracteres_ascii="@%#*+=-:. ", 
    cor_fundo="black"
):
    try:
        # Carrega a imagem e converte para o formato RGB garantido
        imagem = Image.open(caminho_entrada).convert("RGB")
    except Exception as e:
        print(f"Erro ao carregar a imagem: {e}")
        return

    # 1. Definir as dimensões exatas que a imagem de saída terá
    largura_original, altura_original = imagem.size
    largura_final = int(largura_original * escala)
    altura_final = int(altura_original * escala)

    # 2. Carregar a fonte e descobrir o tamanho de cada caractere
    fonte = ImageFont.load_default()
    
    # Tenta calcular o tamanho exato da fonte padrão da biblioteca
    try:
        bbox = fonte.getbbox("A")
        largura_char = bbox[2] - bbox[0]
        altura_char = bbox[3] - bbox[1] + 2  # +2 para dar uma pequena folga vertical (line-height)
    except AttributeError:
        # Fallback para versões mais antigas do Pillow
        largura_char, altura_char = 6, 11 

    # Evita divisão por zero caso a fonte falhe
    largura_char = max(largura_char, 6)
    altura_char = max(altura_char, 10)

    # 3. Calcular a grade (quantas "letras" cabem na imagem final)
    # Isso define a resolução da amostragem (quantos blocos de pixels teremos)
    colunas = largura_final // largura_char
    linhas = altura_final // altura_char

    # 4. Redimensionar a imagem de entrada para o tamanho da grade
    # Cada pixel dessa miniatura representará um caractere na imagem final
    # (Usamos um método de interpolação moderno para melhor precisão nas cores)
    metodo_resampling = getattr(Image, 'Resampling', Image).LANCZOS
    img_amostra = imagem.resize((colunas, linhas), metodo_resampling)
    pixels = img_amostra.load()

    # 5. Criar a tela (canvas) em branco com o tamanho final e cor de fundo definida
    imagem_saida = Image.new("RGB", (largura_final, altura_final), color=cor_fundo)
    desenho = ImageDraw.Draw(imagem_saida)

    # Centralizar a arte caso a divisão não seja exata (evita bordas desiguais)
    offset_x = (largura_final - (colunas * largura_char)) // 2
    offset_y = (altura_final - (linhas * altura_char)) // 2

    # Pré-calcular o tamanho do conjunto ASCII para o mapeamento
    tamanho_densidade = len(caracteres_ascii) - 1

    # 6. Percorrer a grade e desenhar as letras
    for y in range(linhas):
        for x in range(colunas):
            r, g, b = pixels[x, y]
            
            # Calcular a luminosidade (0 a 255)
            luminosidade = int(0.299 * r + 0.587 * g + 0.114 * b)
            
            # Mapear luminosidade -> Índice do caractere
            indice = int((luminosidade / 255.0) * tamanho_densidade)
            caractere = caracteres_ascii[indice]
            
            # Coordenadas exatas para desenhar
            pos_x = offset_x + (x * largura_char)
            pos_y = offset_y + (y * altura_char)
            
            # Desenha a letra
            desenho.text((pos_x, pos_y), caractere, font=fonte, fill=(r, g, b))

    # 7. Salvar com qualidade máxima do JPEG
    imagem_saida.save(caminho_saida, "JPEG", quality=95)
    print(f"Sucesso! Imagem gerada com {largura_final}x{altura_final} pixels.")
    print(f"Salva em: {caminho_saida}")

# ==========================================
# Exemplo de como usar com diferentes parâmetros:
# ==========================================

if __name__ == "__main__":
    # # Mantém tamanho exato da imagem original
    # converter_para_ascii_jpeg(
    #     caminho_entrada="image.png",
    #     caminho_saida="exata_original.jpeg",
    #     escala=2.0, 
    #     caracteres_ascii="@%#*+=-:. " # Padrão (10 níveis de tons)
    # )

    # Dobra o tamanho da imagem gerada e usa caracteres customizados (mais densos)
    converter_para_ascii_jpeg(
        caminho_entrada="mysterious-artifact.jpg",
        caminho_saida="gigante.jpeg",
        escala=1.0, 
        caracteres_ascii="█▓▒░*@$=+ ", # Estilo mais texturizado / "hacker"
    )