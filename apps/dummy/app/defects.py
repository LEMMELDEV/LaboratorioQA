"""Seeded defects ("bug injection") with runtime toggles.

Each defect is OFF by default and can be enabled by:
  1. BUG_PROFILE=default (env) -> all bugs enabled at startup
  2. The /lab panel (in-memory toggles, per process)
  3. Tests calling set_profile() directly

The ground truth for every defect lives in apps/dummy/lab/ground_truth.yaml.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock

from app.config import settings


@dataclass(frozen=True)
class Defect:
    id: str
    screen: str
    severity: str  # critical | high | medium | low
    detectable_by: str  # ui | api | ui+api
    title: str
    description: str  # observed (buggy) behaviour
    expected: str  # correct behaviour


DEFECTS: dict[str, Defect] = {
    "BUG-01": Defect(
        id="BUG-01",
        screen="productos",
        severity="high",
        detectable_by="ui",
        title="La busqueda solo filtra la pagina visible",
        description="Al buscar, se filtran unicamente los productos de la pagina actual "
        "en lugar de buscar en todo el catalogo.",
        expected="La busqueda debe aplicarse sobre el catalogo completo.",
    ),
    "BUG-02": Defect(
        id="BUG-02",
        screen="carrito",
        severity="critical",
        detectable_by="ui+api",
        title="Descuento fantasma de 5% en el carrito",
        description="Con 3 o mas unidades de un producto se aplica un descuento de 5% "
        "que no esta especificado en ningun criterio.",
        expected="El total debe ser subtotal + IVA (19%), sin descuentos no especificados.",
    ),
    "BUG-03": Defect(
        id="BUG-03",
        screen="carrito",
        severity="critical",
        detectable_by="ui+api",
        title="Se aceptan cantidades 0 o negativas",
        description="El carrito acepta cantidad 0 o -1, generando subtotales nulos o negativos.",
        expected="La cantidad minima por linea es 1.",
    ),
    "BUG-04": Defect(
        id="BUG-04",
        screen="servicios",
        severity="medium",
        detectable_by="ui+api",
        title="Email con '+' es rechazado",
        description="La validacion de email rechaza direcciones validas con '+', "
        "por ejemplo usuario+tag@dominio.com.",
        expected="Debe aceptarse cualquier email RFC valido.",
    ),
    "BUG-05": Defect(
        id="BUG-05",
        screen="inicio",
        severity="high",
        detectable_by="api",
        title="Newsletter muestra exito sin persistir",
        description="El formulario de newsletter responde 'suscrito' pero el email "
        "nunca se guarda.",
        expected="El email suscrito debe persistir y listarse via API.",
    ),
    "BUG-06": Defect(
        id="BUG-06",
        screen="productos",
        severity="low",
        detectable_by="ui",
        title="Paginacion muestra una pagina vacia",
        description="La paginacion enlaza una pagina adicional que no tiene productos.",
        expected="El numero de paginas debe coincidir con el contenido real.",
    ),
    "BUG-07": Defect(
        id="BUG-07",
        screen="global (footer)",
        severity="low",
        detectable_by="ui",
        title="Link roto a Terminos y condiciones",
        description="El link del footer a /terminos responde 404.",
        expected="El link debe llevar a una pagina existente.",
    ),
    "BUG-08": Defect(
        id="BUG-08",
        screen="productos",
        severity="medium",
        detectable_by="ui+api",
        title="Orden por precio como texto",
        description="Al ordenar por precio (menor a mayor), los precios se comparan "
        "como cadenas y quedan desordenados.",
        expected="El orden por precio debe ser numerico.",
    ),
    "BUG-09": Defect(
        id="BUG-09",
        screen="checkout",
        severity="critical",
        detectable_by="ui+api",
        title="Checkout acepta direccion vacia",
        description="La orden se crea aunque la direccion de envio este vacia.",
        expected="La direccion de envio es obligatoria.",
    ),
    "BUG-10": Defect(
        id="BUG-10",
        screen="cuenta",
        severity="high",
        detectable_by="ui+api",
        title="Logout no invalida la sesion",
        description="Tras cerrar sesion, /cuenta sigue mostrando la cuenta del usuario.",
        expected="Tras el logout, /cuenta debe redirigir a /login.",
    ),
}


@dataclass
class LabState:
    """Runtime, in-process state of the defect toggles."""

    profile: str = "none"
    disabled: set[str] = field(default_factory=set)
    _lock: RLock = field(default_factory=RLock, repr=False)

    def apply_startup_config(self) -> None:
        self.set_profile(settings.bug_profile)
        forced = [b.strip() for b in settings.lab_disabled_bugs.split(",") if b.strip()]
        for bug_id in forced:
            self.disabled.add(bug_id)

    def set_profile(self, profile: str) -> None:
        with self._lock:
            profile = profile.strip().lower() or "none"
            if profile not in {"none", "default"}:
                raise ValueError(f"Unknown bug profile: {profile}")
            self.profile = profile

    def toggle(self, bug_id: str) -> bool:
        """Toggle a single bug. Returns True if it is now enabled."""
        with self._lock:
            if bug_id in self.disabled:
                self.disabled.remove(bug_id)
                return True
            self.disabled.add(bug_id)
            return False

    def active(self, bug_id: str) -> bool:
        with self._lock:
            if bug_id not in DEFECTS:
                return False
            if bug_id in self.disabled:
                return False
            return self.profile == "default"

    def active_ids(self) -> set[str]:
        with self._lock:
            return {bid for bid in DEFECTS if self.active(bid)}


lab_state = LabState()
lab_state.apply_startup_config()


def is_active(bug_id: str) -> bool:
    return lab_state.active(bug_id)
