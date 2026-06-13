"""Build a self-contained, backend-free ``docs/index.html``.

The page runs the *actual* Python engine in the browser via Pyodide: the engine
sources are embedded as strings, written to Pyodide's filesystem on load, and
called through :mod:`kstycoon.bridge`. No server, no build of the engine — open
the file (or host ``docs/`` on GitHub Pages) and it just runs.

    python tools/build_standalone.py

Re-run after changing the engine so the embedded copy stays in sync.
"""

from __future__ import annotations

import json
import os

from kstycoon._ui import PAGE

PYODIDE = "0.26.4"

# Pure-Python modules to embed. Excludes web.py (needs sockets) and cli.py.
MODULES = [
    "kstycoon/__init__.py",
    "kstycoon/config.py",
    "kstycoon/model.py",
    "kstycoon/market.py",
    "kstycoon/resolve.py",
    "kstycoon/report.py",
    "kstycoon/serialize.py",
    "kstycoon/bridge.py",
    "kstycoon/scenarios/__init__.py",
    "kstycoon/scenarios/south_korea_y0.py",
]

HEAD = f'<script src="https://cdn.jsdelivr.net/pyodide/v{PYODIDE}/full/pyodide.js"></script>'

API_TMPL = """
let _bridge = null;
const _ready = (async () => {
  try {
    boot('Loading Python engine (first load pulls Pyodide, ~10s)…');
    const pyodide = await loadPyodide();
    const FILES = __FILES__;
    for (const [path, src] of Object.entries(FILES)) {
      const dir = '/' + path.split('/').slice(0, -1).join('/');
      pyodide.FS.mkdirTree(dir);
      pyodide.FS.writeFile('/' + path, src);
    }
    pyodide.runPython("import sys; sys.path.insert(0, '/')");
    _bridge = pyodide.pyimport("kstycoon.bridge");
  } catch (e) { boot('Engine failed to load: ' + e, true); throw e; }
})();

function _loadSaved(){
  try { const v = localStorage.getItem('kstycoon_state'); return v ? JSON.parse(v) : null; }
  catch(e){ return null; }
}

const api = {
  async newState(){
    await _ready;
    return _loadSaved() || JSON.parse(_bridge.new_state_json());
  },
  async tick(state, d){
    await _ready;
    try { return JSON.parse(_bridge.tick_json(JSON.stringify(state), JSON.stringify(d))); }
    catch(e){ return {error: String(e)}; }
  },
  async reset(){
    await _ready;
    try { localStorage.removeItem('kstycoon_state'); } catch(e){}
    return JSON.parse(_bridge.new_state_json());
  },
  persist(state){ try { localStorage.setItem('kstycoon_state', JSON.stringify(state)); } catch(e){} },
};
"""


def build() -> str:
    files = {path: open(path, encoding="utf-8").read() for path in MODULES}
    api = API_TMPL.replace("__FILES__", json.dumps(files))
    return PAGE.replace("__HEAD_EXTRA__", HEAD).replace("__API__", api)


def main() -> int:
    os.makedirs("docs", exist_ok=True)
    html = build()
    with open("docs/index.html", "w", encoding="utf-8") as fh:
        fh.write(html)
    # .nojekyll lets GitHub Pages serve the file as-is.
    open("docs/.nojekyll", "w").close()
    print(f"wrote docs/index.html ({len(html):,} bytes), Pyodide v{PYODIDE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
