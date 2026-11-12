# Laboratorio QA

Laboratorio para un agente QA autónomo: el agente recibe **criterios de aceptación** (Gherkin),
la URL base de una app dummie y **nada más** — debe descubrir las pantallas, ejecutar acciones y
validar el comportamiento con Playwright, reportando evidencia y bugs.

## Estado del proyecto

| Hito | Contenido | Estado |
|---|---|---|
| M0 | Scaffolding, venv, scripts, .env | ✅ |
| M1 | App dummie (TiendaDemo) + API REST + bugs sembrados + tests | ✅ |
| M2 | Toolkit Playwright + crawler determinista (sin LLM) | ✅ |
| M3 | Temporal (workflow, activities, worker, CLI) | ⬜ |
| M4 | LangGraph (parse, discover, plan, execute) + LLM adapter | ⬜ |
| M5 | Human-in-the-loop (interrupt + signal) | ⬜ |
| M6 | Evaluación, reportes y scoring vs ground truth | ⬜ |
| M7 | API tool del agente + docs finales | ⬜ |

## Arquitectura (resumen)

```
requirements/*.feature ──► Temporal QARunWorkflow
                             ├─ activity: parse_requirement
                             ├─ activity: discover   (BFS sobre DOM/aria, sin rutas previas)
                             ├─ activity: plan       (criterios + site_map -> test cases)
                             ├─ ⏸ HITL: interrupt <-> signal approve_plan
                             ├─ activity: execute_suite (Playwright, heartbeats, traces)
                             ├─ activity: evaluate   (PASS/FAIL/BLOCKED + evidencia)
                             └─ activity: report     (report.json/md/html + metrics)
```

Regla de oro de Temporal: **todo LLM/IO vive en activities**; el workflow es determinista.
La fase de ejecución es una activity larga con `heartbeat` que mantiene la sesión de Playwright.

Anti-alucinación del agente:
- Solo puede actuar sobre `ref`s del último aria snapshot (los refs se invalidan al navegar).
- Aserciones duras en Python/Playwright; el LLM solo juzga lo semántico y **cita evidencia**.
- Modo `LLM_PROVIDER=heuristic` permite correr el pipeline completo sin gastar tokens.

## La app dummie: TiendaDemo

E-commerce ficticio (FastAPI + Jinja2 + HTMX) con 11 pantallas: Inicio, Productos, Detalle,
Servicios, Carrito, Checkout, Login, Registro, Mi cuenta, Contacto y **/lab** (panel de defectos).

- URL: http://127.0.0.1:8000 · API docs: http://127.0.0.1:8000/docs
- API REST: `/api/v1/*` (products, cart, orders, quotes, auth, newsletter, lab)

### Defectos sembrados

10 bugs activables (BUG-01..BUG-10) desde `/lab` o por perfil:

```
BUG_PROFILE=none|default      # none = app correcta, default = todos los bugs
LAB_DISABLED_BUGS=BUG-02,BUG-07
```

El *ground truth* de cada bug está en `apps/dummy/lab/ground_truth.yaml` y se usa para medir
al agente (precision/recall). El agente **no** debe leer ese archivo.

## Uso rápido

```powershell
# 1. Setup (venv + deps + tests)
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

# 2. Levantar la app
powershell -ExecutionPolicy Bypass -File scripts\run_app.ps1

# 3. Abrir en el navegador
#    http://127.0.0.1:8000          -> tienda
#    http://127.0.0.1:8000/lab      -> activar/desactivar bugs
#    http://127.0.0.1:8000/docs     -> API REST

# 4. Tests de la app
cd apps\dummy
..\..\.venv\Scripts\python.exe -m pytest
```

Usuario demo: `sofia@demo.com` / `demo1234` (se crea al arrancar).

## Estructura

```
LaboratorioQA/
├─ apps/dummy/            # TiendaDemo (app dummie + API + lab + tests)
├─ qa_agent/
│  ├─ browser/            # session.py (refs anti-alucinación), crawler.py, models.py
│  ├─ tests/              # tests del agente (server uvicorn en hilo + Playwright)
│  ├─ cli.py              # python -m qa_agent.cli crawl ...
│  └─ config.py           # AGENT_* settings
├─ requirements/          # criterios de aceptacion en Gherkin (entrada del agente)
├─ artifacts/             # site_map.json, screenshots, reportes (por run)
├─ scripts/               # setup.ps1, run_app.ps1
└─ .env.example           # configuracion (BUG_PROFILE, SESSION_SECRET, AGENT_*, ...)
```

## Crawler determinista (M2)

Descubre el sitio sin recibir rutas y **sin LLM**:

```powershell
# Levanta la app, rastrea y escribe artifacts\crawl\site_map.json
..\..\.venv\Scripts\python.exe -m qa_agent.cli crawl --start-app --bug-profile default
```

Qué produce:
- `site_map.json`: páginas visitadas (con observaciones completas: refs, formularios, links),
  grafo de navegación, links rotos detectados y estadísticas.
- Políticas: BFS con `AGENT_MAX_PAGES` / `AGENT_MAX_DEPTH`, misma origén únicamente,
  y **excluye `/lab` y `/api`** (el panel de bugs revelaría el ground truth al agente).

Anti-alucinación del toolkit de navegador:
- Cada observación re-numera refs `s{seq}e{n}` y limpia los anteriores → un ref viejo
  falla inmediatamente (`StaleRefError`) en lugar de apuntar a otro elemento.
- El agente solo actúa con `session.click(ref)`, `fill(ref, ...)`, `select(ref, ...)` —
  nunca con selectores CSS.

## Run QA end-to-end (M3, Temporal)

El run completo pasa por Temporal: parse de criterios → discovery → plan →
**aprobación humana (HITL)** → ejecución con Playwright → reporte.
```powershell
# Terminal 1: servidor de desarrollo de Temporal (Web UI en http://localhost:8233)
powershell -ExecutionPolicy Bypass -File scripts\temporal_dev.ps1

# Terminal 2: worker del agente (cola 'qa-lab')
.\.venv\Scripts\python.exe -m qa_agent.temporal.worker

# Terminal 3: lanzar un run (levanta la app con bugs, ejecuta y reporta)
.\.venv\Scripts\python.exe -m qa_agent.cli run --feature requirements\carrito.feature --start-app --bug-profile default --auto-approve
```

Opciones útiles de `run`:
- `--headed` → **verás el navegador abriendo páginas y validando** (visible).
- la consola muestra **cada criterio en vivo** (`▶ criterio-... (2/6)`) y al final un
  bloque por escenario con **PASS/FAIL/BLOCKED + descripción de la ejecución + evidencia**.
- `--start-app` **reutiliza** una TiendaDemo ya levantada en el puerto (alinea su perfil
  de bugs); nunca falla con "puerto en uso" ni mata tu app manual.
- sin `--auto-approve` → HITL: cuando el plan esté listo se te pregunta
  `¿Aprobar ejecución? [S/n]` en la misma terminal y se envía la señal
  `approve_plan` al workflow (o puedes enviarla desde la Web UI de Temporal).
- `--feature requirements\...` acepta cualquier `.feature` de `requirements\`.

Qué produce (todo en `artifacts\runs\<run_id>\`):
- `plan.md` → **cómo entendió el agente cada criterio** (antes de ejecutar; es lo que
  se muestra en la aprobación HITL): entendido, pasos, qué verifica + origen del valor
  esperado, supuestos, no resuelto y confianza.
- `evidence\` → **una sola carpeta plana**: `criterio-XX__<check>.png` (pantallazo por
  verificación). Si un check nunca abrió pantalla (BLOCKED), la evidencia es una
  tarjeta legible "SIN EVIDENCIA VISUAL", nunca una imagen en blanco.
- `summary.md` → resumen legible (interpretación por criterio, PASS/FAIL/BLOCKED,
  hallazgos con evidencia).
- `report.json` → resultado completo machine-readable.
- `progress.json` → estado en vivo (el CLI lo usa para pintar cada criterio conforme
  se ejecuta: `▶ criterio-...`, `✅ / ❌ resultado`).

### Ritmo natural (M3.5)

El agente actúa con pausas humanas para que la validación se observe en vivo
(`AGENT_PACING=on` por defecto en `run`; los tests la desactivan para rapidez):

```powershell
# más lento / más rápido, a gusto (env o .env)
$env:AGENT_STEP_DELAY_MS     = "1000"  # pausa base tras cada accion
$env:AGENT_JITTER_MS         = "500"   # variacion aleatoria 0..N
$env:AGENT_REVIEW_DELAY_MS   = "3000"  # pausa de verificacion al cerrar cada criterio
```

Al cerrar cada criterio el agente se detiene ~2 s mirando el estado final y
captura `evidence\<criterio>\cierre.png` (pantallazo de cierre).

## Roadmap técnico
- **M3.5**: ✅ ritmo humano (`browser/pacing.py`) + capa de interpretación
  (`interpretation.py` + `narratives.py`, visible en plan.md / HITL / summary.md).
- **M4**: LangGraph con `LLM_PROVIDER=heuristic|gemini|groq|ollama` + caché de LLM en disco;
  el LLM llenará el MISMO contrato de `Interpretation` que hoy llena el intérprete heurístico.
- **M6**: `artifacts/<run_id>/` con reportes y `metrics.json` (precision/recall).
