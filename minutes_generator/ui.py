# -*- coding: utf-8 -*-
"""브라우저에서 쓰는 간단한 UI.

표준 라이브러리만으로 로컬 웹서버를 띄운다.  python3 -m minutes_generator --ui
"""

import io
import json
import os
import random
import threading
import urllib.parse
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional

from .agenda import GENERATORS, KIND_LABELS
from .generator import build_minutes
from .html_render import render_html
from .render import ground_truth, render_text

MAX_BATCH = 500


# ---------------------------------------------------------------- 요청 처리

def _params(query: str) -> Dict[str, List[str]]:
    return urllib.parse.parse_qs(query, keep_blank_values=True)


def _one(params, key, default=None):
    values = params.get(key) or []
    return values[0] if values and values[0] != "" else default


def _int(params, key, default=None):
    raw = _one(params, key)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _kinds(params) -> Optional[List[str]]:
    raw = _one(params, "agenda")
    if not raw:
        return None
    picked = [k for k in raw.split(",") if k in GENERATORS]
    return picked or None


def _make(params):
    seed = _int(params, "seed", random.randrange(1 << 30))
    return seed, build_minutes(seed=seed,
                               agenda_kinds=_kinds(params),
                               n_agenda=_int(params, "n_agenda"))


def pdf_status() -> Dict[str, object]:
    from . import fonts
    try:
        import reportlab
        version = reportlab.Version
    except ImportError:
        return {"ok": False, "reason": "reportlab 이 설치되어 있지 않습니다.",
                "fix": "pip install reportlab"}
    hit = fonts.find_font("gothic")
    if not hit:
        return {"ok": False, "reason": "한글 글꼴을 찾지 못했습니다.",
                "fix": "나눔고딕을 설치하거나 MINUTES_FONT_GOTHIC 환경변수를 지정하세요."}
    return {"ok": True, "reportlab": version, "font": os.path.basename(hit[0])}


class Handler(BaseHTTPRequestHandler):
    server_version = "MinutesGeneratorUI"

    def log_message(self, fmt, *args):        # 조용히
        pass

    # ----- 응답 도우미 -----

    def _send(self, body: bytes, ctype: str, filename: str = None, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            quoted = urllib.parse.quote(filename)
            self.send_header("Content-Disposition",
                             f"attachment; filename*=UTF-8''{quoted}")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, code=200):
        self._send(json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", code=code)

    def _error(self, message: str, code: int = 400):
        self._json({"error": message}, code=code)

    # ----- 라우팅 -----

    def do_GET(self):                          # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        route, params = parsed.path, _params(parsed.query)
        try:
            if route == "/":
                self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif route == "/api/status":
                self._json({
                    "pdf": pdf_status(),
                    "kinds": [{"key": k, "label": KIND_LABELS[k]}
                              for k in sorted(GENERATORS, key=lambda x: KIND_LABELS[x])],
                    "max_batch": MAX_BATCH,
                })
            elif route == "/preview":
                seed, minutes = _make(params)
                html = render_html(minutes, seed)
                self._send(html.encode("utf-8"), "text/html; charset=utf-8")
            elif route == "/download":
                self._download(params)
            elif route == "/batch":
                self._batch(params)
            else:
                self._error("없는 경로입니다.", 404)
        except BrokenPipeError:
            pass
        except Exception as exc:               # noqa: BLE001
            self._error(f"{type(exc).__name__}: {exc}", 500)

    # ----- 내려받기 -----

    def _download(self, params):
        fmt = _one(params, "fmt", "pdf")
        seed, minutes = _make(params)
        stem = f"minutes_{seed}"
        if fmt == "txt":
            self._send(render_text(minutes, seed).encode("utf-8"),
                       "text/plain; charset=utf-8", stem + ".txt")
        elif fmt == "json":
            payload = ground_truth(minutes)
            payload["seed"] = seed
            self._send(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
                       "application/json; charset=utf-8", stem + ".json")
        elif fmt == "html":
            self._send(render_html(minutes, seed).encode("utf-8"),
                       "text/html; charset=utf-8", stem + ".html")
        elif fmt == "pdf":
            from .pdf import pdf_bytes
            self._send(pdf_bytes(minutes, seed), "application/pdf", stem + ".pdf")
        else:
            self._error("알 수 없는 형식입니다.")

    def _batch(self, params):
        count = max(1, min(MAX_BATCH, _int(params, "count", 10)))
        base = _int(params, "seed", random.randrange(1 << 30))
        formats = [f for f in (_one(params, "formats", "pdf,json") or "").split(",")
                   if f in ("pdf", "txt", "json", "html")]
        if not formats:
            return self._error("형식을 하나 이상 고르세요.")
        kinds = _kinds(params)
        n_agenda = _int(params, "n_agenda")

        buf = io.BytesIO()
        width = max(4, len(str(count)))
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for i in range(count):
                seed = base + i
                minutes = build_minutes(seed=seed, agenda_kinds=kinds, n_agenda=n_agenda)
                stem = f"minutes_{i + 1:0{width}d}"
                if "txt" in formats:
                    zf.writestr(stem + ".txt", render_text(minutes, seed))
                if "json" in formats:
                    payload = ground_truth(minutes)
                    payload["seed"] = seed
                    zf.writestr(stem + ".json",
                                json.dumps(payload, ensure_ascii=False, indent=2))
                if "html" in formats:
                    zf.writestr(stem + ".html", render_html(minutes, seed))
                if "pdf" in formats:
                    from .pdf import pdf_bytes
                    zf.writestr(stem + ".pdf", pdf_bytes(minutes, seed))
        self._send(buf.getvalue(), "application/zip", f"minutes_{base}_{count}건.zip")


# ---------------------------------------------------------------- 화면

PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>이사회 의사록 생성기</title>
<style>
  :root {
    --bg: #f4f5f7; --panel: #ffffff; --ink: #14161a; --muted: #6b7280;
    --line: #dcdfe4; --accent: #2f5fd0; --accent-ink: #ffffff; --warn: #b45309;
    --ok-bg: #e8f2e8; --ok-ink: #256029; --bad-bg: #fdeceb; --bad-ink: #9b2c2c;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #15171b; --panel: #1d2026; --ink: #e8eaed; --muted: #9aa2ad;
      --line: #2f343d; --accent: #5b8cf0; --accent-ink: #0d1117;
      --ok-bg: #1e2f22; --ok-ink: #8ed69a; --bad-bg: #3a1f1f; --bad-ink: #f0a3a3;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--ink);
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Malgun Gothic',
      'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
    font-size: 14px; line-height: 1.55;
  }
  header {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    padding: 14px 20px; border-bottom: 1px solid var(--line); background: var(--panel);
  }
  header h1 { font-size: 16px; margin: 0; font-weight: 650; }
  .chip {
    font-size: 12px; padding: 3px 9px; border-radius: 999px;
    background: var(--ok-bg); color: var(--ok-ink);
  }
  .chip.bad { background: var(--bad-bg); color: var(--bad-ink); }
  .layout { display: flex; gap: 0; align-items: stretch; min-height: calc(100vh - 57px); }
  aside {
    flex: 0 0 320px; padding: 18px 20px 40px; border-right: 1px solid var(--line);
    background: var(--panel); overflow-y: auto; max-height: calc(100vh - 57px);
  }
  main { flex: 1 1 auto; padding: 18px; overflow: hidden; }
  h2 { font-size: 12px; letter-spacing: .06em; color: var(--muted);
       text-transform: uppercase; margin: 22px 0 8px; font-weight: 650; }
  h2:first-child { margin-top: 0; }
  label { display: block; font-size: 13px; margin-bottom: 5px; color: var(--muted); }
  input[type=number], select {
    width: 100%; padding: 7px 9px; border: 1px solid var(--line); border-radius: 7px;
    background: var(--bg); color: var(--ink); font: inherit; font-size: 13px;
  }
  .row { display: flex; gap: 8px; }
  .row > * { flex: 1 1 auto; }
  button {
    font: inherit; font-size: 13px; padding: 8px 12px; border-radius: 7px;
    border: 1px solid var(--line); background: var(--bg); color: var(--ink);
    cursor: pointer;
  }
  button:hover { border-color: var(--accent); }
  button.primary {
    background: var(--accent); color: var(--accent-ink); border-color: var(--accent);
    font-weight: 600; width: 100%; padding: 10px;
  }
  button.wide { width: 100%; }
  button:disabled { opacity: .45; cursor: not-allowed; }
  .stack { display: flex; flex-direction: column; gap: 7px; }
  .kinds {
    max-height: 190px; overflow-y: auto; border: 1px solid var(--line);
    border-radius: 7px; padding: 8px 10px; background: var(--bg);
  }
  .kinds label {
    display: flex; gap: 7px; align-items: flex-start; color: var(--ink);
    font-size: 13px; margin: 0 0 4px; cursor: pointer;
  }
  .kinds input { margin-top: 3px; }
  .hint { font-size: 12px; color: var(--muted); margin: 6px 0 0; }
  .checks { display: flex; gap: 12px; flex-wrap: wrap; font-size: 13px; }
  .checks label { display: flex; gap: 5px; align-items: center; color: var(--ink); margin: 0; }
  .frame {
    width: 100%; height: calc(100vh - 93px); border: 1px solid var(--line);
    border-radius: 10px; background: #fff;
  }
  .bar { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
  .bar .seedlabel { font-size: 13px; color: var(--muted); margin-right: auto; }
  code { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px; }
  @media (max-width: 880px) {
    .layout { flex-direction: column; }
    aside { flex: 1 1 auto; max-height: none; border-right: none;
            border-bottom: 1px solid var(--line); }
    .frame { height: 70vh; }
  }
</style>
</head><body>
<header>
  <h1>이사회 의사록 생성기</h1>
  <span class="chip" id="pdfchip">확인 중…</span>
</header>

<div class="layout">
  <aside>
    <h2>문서</h2>
    <label for="seed">시드 (같은 값이면 같은 문서)</label>
    <div class="row">
      <input type="number" id="seed" min="0" step="1">
      <button id="dice" title="무작위 시드" style="flex:0 0 auto">무작위</button>
    </div>

    <label for="nagenda" style="margin-top:12px">의안 개수</label>
    <select id="nagenda">
      <option value="">자동 (1~6건)</option>
      <option>1</option><option>2</option><option>3</option>
      <option>4</option><option>5</option><option>6</option>
    </select>

    <label style="margin-top:12px">의안 종류</label>
    <div class="kinds" id="kinds"></div>
    <p class="hint">아무것도 고르지 않으면 22종에서 무작위로 뽑는다.
      고른 종류가 있으면 그 순서대로 들어간다.</p>
    <div class="row" style="margin-top:6px">
      <button id="clearkinds">전체 해제</button>
    </div>

    <div style="margin-top:16px">
      <button class="primary" id="make">새 문서 만들기</button>
    </div>

    <h2>이 문서 내려받기</h2>
    <div class="stack">
      <button class="wide" data-dl="pdf" id="dlpdf">PDF</button>
      <button class="wide" data-dl="txt">텍스트 (.txt)</button>
      <button class="wide" data-dl="json">정답셋 (.json)</button>
      <button class="wide" data-dl="html">HTML</button>
    </div>

    <h2>여러 건 한꺼번에</h2>
    <label for="count">개수</label>
    <input type="number" id="count" value="20" min="1" max="500">
    <div class="checks" style="margin:10px 0">
      <label><input type="checkbox" class="bf" value="pdf" checked>PDF</label>
      <label><input type="checkbox" class="bf" value="json" checked>JSON</label>
      <label><input type="checkbox" class="bf" value="txt">TXT</label>
      <label><input type="checkbox" class="bf" value="html">HTML</label>
    </div>
    <button class="wide" id="zip">ZIP 으로 내려받기</button>
    <p class="hint">시드 값부터 1씩 올려가며 만든다. 500건까지.
      PDF 를 포함하면 시간이 걸린다.</p>
  </aside>

  <main>
    <div class="bar">
      <span class="seedlabel" id="seedlabel"></span>
      <button id="print">인쇄 / PDF 로 저장</button>
      <button id="open">새 탭에서 열기</button>
    </div>
    <iframe class="frame" id="frame" title="의사록 미리보기"></iframe>
  </main>
</div>

<script>
const $ = (id) => document.getElementById(id);
let status = null;

function randomSeed() { return Math.floor(Math.random() * 1000000); }

function selectedKinds() {
  return [...document.querySelectorAll('#kinds input:checked')].map(i => i.value);
}

function query(extra) {
  const p = new URLSearchParams();
  p.set('seed', $('seed').value || '0');
  const n = $('nagenda').value;
  if (n) p.set('n_agenda', n);
  const k = selectedKinds();
  if (k.length) p.set('agenda', k.join(','));
  for (const [key, val] of Object.entries(extra || {})) p.set(key, val);
  return p.toString();
}

function refresh() {
  const q = query();
  $('frame').src = '/preview?' + q;
  $('seedlabel').textContent = '시드 ' + ($('seed').value || '0');
}

async function boot() {
  status = await (await fetch('/api/status')).json();
  const chip = $('pdfchip');
  if (status.pdf.ok) {
    chip.textContent = 'PDF 사용 가능 · ' + status.pdf.font;
  } else {
    chip.className = 'chip bad';
    chip.textContent = 'PDF 불가 · ' + status.pdf.reason + ' → ' + status.pdf.fix;
    $('dlpdf').disabled = true;
    document.querySelector('.bf[value=pdf]').checked = false;
    document.querySelector('.bf[value=pdf]').disabled = true;
  }
  const box = $('kinds');
  box.innerHTML = status.kinds.map(k =>
    `<label><input type="checkbox" value="${k.key}"><span>${k.label}</span></label>`
  ).join('');
  $('count').max = status.max_batch;
  $('seed').value = randomSeed();
  refresh();
}

$('dice').onclick = () => { $('seed').value = randomSeed(); refresh(); };
$('make').onclick = () => { $('seed').value = randomSeed(); refresh(); };
$('seed').onchange = refresh;
$('nagenda').onchange = refresh;
$('kinds').onchange = refresh;
$('clearkinds').onclick = () => {
  document.querySelectorAll('#kinds input').forEach(i => i.checked = false);
  refresh();
};
document.querySelectorAll('[data-dl]').forEach(btn => {
  btn.onclick = () => {
    window.location = '/download?' + query({ fmt: btn.dataset.dl });
  };
});
$('zip').onclick = () => {
  const formats = [...document.querySelectorAll('.bf:checked')].map(i => i.value);
  if (!formats.length) { alert('형식을 하나 이상 고르세요.'); return; }
  window.location = '/batch?' + query({ count: $('count').value, formats: formats.join(',') });
};
$('print').onclick = () => {
  const f = $('frame');
  f.contentWindow.focus();
  f.contentWindow.print();
};
$('open').onclick = () => window.open('/preview?' + query(), '_blank');

boot();
</script>
</body></html>
"""


# ---------------------------------------------------------------- 실행

def serve(port: int = 8765, host: str = "127.0.0.1", open_browser: bool = True) -> int:
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{httpd.server_address[1]}/"
    print(f"이사회 의사록 생성기 UI: {url}")
    print("종료하려면 Ctrl+C")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
