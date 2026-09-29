"""Nome, colore e ordine delle linee (uguali per dati reali e simulati)."""

DEFAULT_COLOR = "#0d6efd"

# codice: (nome, colore)
STYLE = {
    "S1": ("Saronno - Milano - Lodi", "#e2001a"),
    "S2": ("Mariano Comense - Milano - Rogoredo", "#00a651"),
    "S3": ("Saronno - Milano Cadorna", "#f39200"),
    "S4": ("Camnago-Lentate - Milano Cadorna", "#7b3f98"),
    "S5": ("Varese - Milano - Treviglio", "#8e44ad"),
    "S6": ("Novara - Milano - Treviglio", "#e67e22"),
    "S7": ("Lecco - Molteno - Milano Porta Garibaldi", "#0072bc"),
    "S8": ("Lecco - Carnate - Milano Porta Garibaldi", "#00a7b5"),
    "S9": ("Saronno - Milano - Albairate", "#27ae60"),
    "S11": ("Chiasso - Milano - Rho", "#c0392b"),
    "S12": ("Bovisa - Milano - Melegnano", "#a0522d"),
    "S13": ("Garbagnate - Milano - Pavia", "#6d6e71"),
    "MXP1": ("Malpensa Express: Milano Cadorna - Malpensa", "#d4145a"),
    "MXP2": ("Malpensa Express: Milano Centrale - Malpensa", "#ee7203"),
    "RE": ("Regionale Express", "#34495e"),
}
ORDER = list(STYLE)


def style_for(code):
    name, color = STYLE.get(code, ("", DEFAULT_COLOR))
    order = ORDER.index(code) if code in ORDER else 100
    return name, color, order


def apply_styles():
    """Applica nome/colore/ordine a tutte le linee nel database (correggendo quelle create in blu di default)."""
    from trains.models import Line
    n = 0
    for line in Line.objects.all():
        name, color, order = style_for(line.code)
        if line.code not in STYLE:
            continue
        if (line.color, line.position) != (color, order) or (not line.name and name):
            line.color, line.position = color, order
            line.name = line.name or name
            line.save(update_fields=["color", "position", "name"])
            n += 1
    return n
