"""Templates de conjuntos de caracteres para a montagem da arte ASCII.

Convenção (otimizada para fundo escuro padrão): os caracteres são ordenados do
menos denso / mais escuro (índice 0, espaço vazio no fundo escuro) ao mais
denso / mais iluminado (último índice). Quando o usuário escolhe um fundo claro,
o motor de renderização inverte automaticamente a rampa.
"""

TEMPLATES = {
    "Clássico": " .:-=+*#%@",
    "Hacker / Texturizado": " .:-=+*$#@",
    "Minimalista": " .+*#@",
    "Alto detalhe": " .,:-+*?!%S#@",
    "Binário": " 01",
    "Pontilhado": " .:-+*#%@",
    "Sombreado": " ░▒▓█",
    "Braille": " ⠁⠃⠇⡇⣿",
    "Retro 8-bit": " .-=+*#%@",
    "Tipográfico": " .,:;irsxX#@%",
    "Bloco denso": " ▄▀█",
}


def listar_templates():
    """Nomes dos templates disponíveis (para o combobox da GUI)."""
    return list(TEMPLATES.keys())


def obter_template(nome):
    """Retorna a string de caracteres do template pelo nome."""
    return TEMPLATES[nome]
