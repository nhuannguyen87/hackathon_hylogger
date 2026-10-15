"""
The rock companies logged down each hole (holes.models.Geology), grouped
into a few families so a strip of it reads beside the mineral log.

GSWA's harmonised rock name is used first, then the company's own name. An
interval with only the company's code (most of them) stays "code" - shown
as the code itself, since codes differ between companies and guessing
would invent geology.
"""

# family -> words that put a rock in it, checked in this order ("felsic
# granulite" is metamorphic; "ultramafic" must not be caught by "mafic")
FAMILIES = [
    ("regolith", ["regolith", "laterit", "saprolit", "saprock", "soil", "crete", "colluvi", "alluvi",
                  "duricrust", "cover", "transported", "pisolit", "mottled"]),
    ("vein", ["vein"]),
    ("ultramafic", ["ultramafic", "peridotit", "komatiit", "serpentinit", "dunit", "pyroxenit", "talc"]),
    ("metamorphic", ["schist", "gneiss", "granulite", "quartzite", "hornfels", "phyllite", "slate", "migmatit",
                     "mylonit", "metamorph", "amphibolite"]),
    ("felsic", ["granit", "granodiorit", "tonalit", "pegmatit", "felsic", "rhyolit", "dacit", "aplit",
                "syenit", "porphyr", "monzonit"]),
    ("mafic", ["basalt", "dolerit", "gabbr", "mafic", "norit", "andesit", "diorit"]),
    ("sedimentary", ["sandstone", "siltstone", "shale", "mudstone", "wacke", "conglomerat", "claystone",
                     "limestone", "chert", "sediment", "arenit", "ironstone", "banded iron", "bif",
                     "carbonate rock", "dolostone", "evaporit"]),
]

SOURCE = ("Company logging reported to WAMEX, compiled in GSWA's DASC interim package. Most intervals carry "
          "only the company's own code; GSWA has given a harmonised rock name to a few.")


def rock_family(rock, name):
    """'basalt' -> 'mafic'; a named rock no rule knows -> 'other'; nothing but a code -> 'code'.
    GSWA's harmonised name decides when there is one; the company's name only stands in for it."""
    text = (rock or name or "").strip().lower()
    if not text:
        return "code"
    return next((family for family, words in FAMILIES if any(w in text for w in words)), "other")


def hole_geology(hole):
    rows = list(hole.geology.order_by("depth_from_m"))
    return {
        "intervals": [{"from_m": r.depth_from_m, "to_m": r.depth_to_m, "rock": r.rock, "name": r.name,
                       "code": r.code, "family": rock_family(r.rock, r.name)} for r in rows],
        "source": SOURCE,
    }
