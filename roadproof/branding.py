"""Original user-supplied RoadProof artwork, converted from App icon.pdf."""
import base64
from functools import lru_cache
from pathlib import Path


ASSETS = Path(__file__).resolve().parents[1] / "assets" / "brand"


@lru_cache(maxsize=1)
def brand_markup():
    encoded = base64.b64encode((ASSETS / "roadproof-logo.png").read_bytes()).decode()
    return (
        '<div class="brand">'
        f'<img class="brand-logo" src="data:image/png;base64,{encoded}" '
        'alt="RoadProof AI logo" width="44" height="44">'
        '<span class="brand-name">RoadProof <small>AI</small></span></div>'
    )
