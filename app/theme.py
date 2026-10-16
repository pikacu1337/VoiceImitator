"""Тема «Night Glass» — перенесена из дизайн-системы (артефакт Night Glass,
снятой с Zapret Launcher). customtkinter не умеет настоящее размытие, поэтому
полупрозрачные токены сведены в сплошные цвета поверх фона окна: стекло — тёмные
пластины, чуть светлее неба, с тонкой светлой обводкой.
"""

# --- фон / небо ---
WINDOW = "#050505"
SKY_TOP = "#121212"       # центр радиального градиента неба
SKY_BOTTOM = "#030303"    # край

# --- стекло (панели) ---
GLASS = "#141414"         # заливка панели (темнее неба + вуаль)
GLASS_2 = "#191919"       # вложенная панель / поле чуть светлее
EDGE = "#333333"          # обводка стекла (#ffffff24 поверх тёмного)
EDGE_STRONG = "#555555"   # обводка пилюли под курсором

# --- текст ---
TEXT = "#f2f2f2"
MUTED = "#9a9a9a"
FAINT = "#6b6b6b"

# --- поля и дорожки ---
FIELD = "#242424"         # заливка поля ввода / дропдауна
FIELD_FOCUS = "#6f6f6f"   # обводка поля в фокусе
TRACK_OFF = "#2e2e2e"     # дорожка слайдера / выключенного свитча
WASH = "#262626"          # подсветка под курсором (строка, пилюля)
WASH_SELECTED = "#333333"

# --- сплошная «главная» кнопка (solid) ---
SOLID = "#dedede"
SOLID_HOVER = "#ffffff"
ON_SOLID = "#0a0a0a"      # текст на solid

SWITCH_KNOB = "#eaeaea"

# --- радиусы ---
R_BAR = 2
R_ROW = 8
R_PILL = 9
R_HINT = 14
R_CARD = 16

# --- шрифт ---
FONT_UI = "Segoe UI Variable Text"
FONT_UI_FALLBACK = "Segoe UI"

# размер, вес
F_STATUS = (28, "bold")
F_TITLE = (15, "bold")
F_PANEL = (14, "bold")
F_LABEL = (14, "normal")
F_LIST = (13, "normal")
F_BODY = (13, "normal")
F_BUTTON = (13, "normal")
F_CAPTION = (12, "normal")
F_SMALL = (11, "normal")

# --- акценты (означают «работает» / «выбрано») ---
ACCENTS = {
    "white": "#ffffff",
    "sky": "#7ab8ff",
    "mint": "#5eead4",
    "leaf": "#86efac",
    "sun": "#fde047",
    "peach": "#fdba74",
    "rose": "#fb7185",
    "lilac": "#c4b5fd",
}
ACCENT_ORDER = ["white", "sky", "mint", "leaf", "sun", "peach", "rose", "lilac"]
DEFAULT_ACCENT = "#7ab8ff"


def accent_soft(hex_color: str, factor: float = 0.64) -> str:
    """Акцент × factor — приглушённый акцент для дорожки включённого свитча."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (int(r * factor), int(g * factor), int(b * factor))
