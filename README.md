# ASCII Studio — Conversor de Imagem para Arte ASCII

Aplicação desktop que converte qualquer imagem em arte ASCII com preview em tempo real. A interface é uma janela PyWebView (backend Qt) servida por um servidor HTTP local (Bottle), com renderização nítida via Pillow e suporte completo a Unicode.

## Requisitos

- Python 3.x
- Linux (usa PySide6/Qt para a janela)

```bash
pip install -r requirements.txt
```

Dependências: `Pillow`, `pywebview`, `qtpy`, `PySide6` (e `pytest` para desenvolvimento).

## Como executar

```bash
python main.py
```

A janela abre com 1240×780 px (mínimo 760×500) e o servidor local é criado automaticamente — não é preciso configurar nada.

## Guia de uso da interface

### 1. Carregar uma imagem

- Arraste e solte a imagem na área de upload, ou clique em **Carregar imagem…**.
- Formatos aceitos: PNG, JPEG, WEBP, BMP.
- A miniatura e as dimensões originais aparecem no painel lateral.

### 2. Ajustes de imagem

Sliders com valor ao vivo (0–200%, neutro em 100%):

| Controle | Efeito |
|---|---|
| Brilho | Fator 0.0 (preto) a 2.0 |
| Contraste | Fator 0.0 (cinza plano) a 2.0 |
| Saturação | Fator 0.0 (escala de cinza) a 2.0 |
| Gamma | 0.1 a 3.0 — acima de 1 escurece, abaixo clareia |
| Inverter cores | Checkbox |

- **Duplo-clique em um slider** restaura apenas aquele ajuste.
- **Restaurar padrões** zera todos os ajustes de uma vez.

### 3. Densidade e caracteres

- **Template de densidade**: 11 presets — Clássico, Hacker/Texturizado, Minimalista, Alto detalhe, Binário, Pontilhado, Sombreado (░▒▓█), Braille (⠁⠃⠇⡇⣿), Retro 8-bit, Tipográfico, Bloco denso.
- **Rampa personalizada**: edite a string de caracteres do mais escuro ao mais claro; o badge mostra quantos níveis a rampa tem.
- **⇄ Inverter rampa** inverte a ordem dos caracteres.
- A rampa é ajustada automaticamente à cor do fundo: em fundo claro, pixels escuros recebem mais tinta.

### 4. Fonte de renderização

- Padrão: fonte monoespaçada nítida do sistema (14 px).
- **Escolher fonte** carrega um `.ttf`, `.otf` ou `.ttc` próprio; **✕** volta à fonte padrão.

### 5. Saída

- **Escala de saída**: 25% a 400% da dimensão original (passo de 5%).
- **Cor de fundo do canvas**: 6 presets (Preto Puro, Terminal Escuro, Fósforo Verde, Monitor Âmbar, Noite, Papel Claro) ou cor personalizada via picker.

### 6. Visualização

Três abas no painel principal:

- **Arte ASCII** — a renderização final em canvas.
- **Comparar (Antes / Depois)** — imagem original ao lado da arte, com splitter arrastável.
- **Texto Puro** — a grade de caracteres em texto selecionável, com badge `colunas×linhas`.

Controles de navegação: zoom (+/−, roda do mouse), **Ajustar** (zoom à tela), **100%**, pan por arraste, e botão para ocultar/exibir o painel lateral.

### 7. Exportar e copiar

- **Exportar** renderiza a arte em resolução final e salva via diálogo de arquivo (padrão `arte_ascii.png`). O status mostra caminho, dimensões e tempo de renderização.
- Na aba Texto Puro, **Copiar texto ASCII** coloca a grade de caracteres na área de transferência.

## Uso como biblioteca

O motor de conversão pode ser usado direto em Python:

```python
from ascii import converter_para_ascii_jpeg, renderizar_ascii, carregar_imagem

# Converte e salva em disco (JPEG 4:4:4)
converter_para_ascii_jpeg(
    "entrada.png",
    "saida.jpeg",
    escala=1.0,
    caracteres_ascii=" .:-=+*#%@",
    cor_fundo="black",
    brilho=1.0,
    contraste=1.0,
    saturacao=1.0,
    gamma=1.0,
    inverter=False,
)

# Ou renderiza em memória e devolve um PIL.Image
from ascii import carregar_imagem
imagem = carregar_imagem("entrada.png")
arte = renderizar_ascii(imagem, escala=1.5, cor_fundo="#0d1117")
arte.save("arte.png")
```

Ajustes de imagem puros (sem I/O) ficam em `ajustes.aplicar_ajustes()`, e os templates de rampa em `templates.listar_templates()` / `templates.obter_template(nome)`.

## Testes

```bash
pytest tests/
```

- `tests/test_ascii.py` — motor de renderização, ajustes e templates.
- `tests/test_gui.py` — sessão, cache, preview, API HTTP e rotas do servidor.

## Estrutura do projeto

| Arquivo | Responsabilidade |
|---|---|
| `main.py` | Ponto de entrada — chama `gui.main()` |
| `gui.py` | Janela PyWebView, `SessaoConversor` (cache/preview), API desktop e servidor Bottle |
| `ascii.py` | Motor: grade, rampa de caracteres, LUT de scanlines, renderização nítida |
| `ajustes.py` | Ajustes puros de brilho, contraste, saturação, gamma e inversão |
| `templates.py` | Presets de rampas de densidade |
| `web/` | Frontend da UI (`index.html`, `app.js`, `styles.css`) |
| `tests/` | Testes do motor e da camada GUI/API |
