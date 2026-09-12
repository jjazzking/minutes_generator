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
from typing import Any, Dict, List, Optional

from .agenda import GENERATORS, KIND_LABELS
from .generator import build_minutes, force_seals
from .html_render import render_html
from .render import ground_truth, render_text

MAX_BATCH = 500
PREVIEW_DPI_CAP = 140          # 미리보기는 응답 속도를 위해 해상도를 낮춘다


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
    minutes = build_minutes(seed=seed, agenda_kinds=_kinds(params),
                            n_agenda=_int(params, "n_agenda"))
    seals = _one(params, "seals", "auto")
    if seals in ("on", "off"):
        force_seals(minutes, seals == "on", seed)
    return seed, minutes


def _scan_pages(minutes, seed: int, profile: str, dpi=None):
    """(페이지 이미지, 적용값)을 돌려준다."""
    from .pdf import pdf_bytes
    from .scan import scan

    return scan(pdf_bytes(minutes, seed), profile,
                random.Random(seed ^ 0x5CA4), dpi)


def scan_status() -> Dict[str, object]:
    base = pdf_status()
    if not base.get("ok"):
        return {"ok": False, "reason": base["reason"], "fix": base["fix"]}
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        try:
            import fitz  # noqa: F401
        except ImportError:
            return {"ok": False, "reason": "PDF 래스터라이저가 없습니다.",
                    "fix": "pip install pypdfium2"}
    return {"ok": True}


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
                from .scan import PROFILE_LABELS, PROFILES
                self._json({
                    "pdf": pdf_status(),
                    "scan": scan_status(),
                    "kinds": [{"key": k, "label": KIND_LABELS[k]}
                              for k in sorted(GENERATORS, key=lambda x: KIND_LABELS[x])],
                    "profiles": [{"key": k, "label": PROFILE_LABELS.get(k, k)}
                                 for k in list(PROFILES) + ["random"]],
                    "max_batch": MAX_BATCH,
                })
            elif route == "/preview":
                seed, minutes = _make(params)
                profile = _one(params, "scan", "clean")
                if profile and profile != "clean":
                    dpi = min(_int(params, "dpi", PREVIEW_DPI_CAP), PREVIEW_DPI_CAP)
                    pages, applied = _scan_pages(minutes, seed, profile, dpi)
                    body = _scan_page_html(pages, applied)
                else:
                    body = render_html(minutes, seed)
                self._send(body.encode("utf-8"), "text/html; charset=utf-8")
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
        elif fmt in ("scan_pdf", "scan_png"):
            profile = _one(params, "scan", "office_scan")
            if profile == "clean":
                profile = "office_scan"
            pages, _applied = _scan_pages(minutes, seed, profile, _int(params, "dpi"))
            if fmt == "scan_pdf":
                from .scan import images_to_pdf
                buf = io.BytesIO()
                images_to_pdf(pages, buf)
                self._send(buf.getvalue(), "application/pdf", f"{stem}_scan.pdf")
            else:
                buf = io.BytesIO()
                pages[0].save(buf, format="PNG")
                self._send(buf.getvalue(), "image/png", f"{stem}_scan_p1.png")
        else:
            self._error("알 수 없는 형식입니다.")

    def _batch(self, params):
        count = max(1, min(MAX_BATCH, _int(params, "count", 10)))
        base = _int(params, "seed", random.randrange(1 << 30))
        formats = [f for f in (_one(params, "formats", "pdf,json") or "").split(",")
                   if f in ("pdf", "txt", "json", "html", "scan")]
        if not formats:
            return self._error("형식을 하나 이상 고르세요.")
        kinds = _kinds(params)
        n_agenda = _int(params, "n_agenda")
        seals = _one(params, "seals", "auto")
        profile = _one(params, "scan", "office_scan")
        if profile == "clean":
            profile = "office_scan"

        buf = io.BytesIO()
        width = max(4, len(str(count)))
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for i in range(count):
                seed = base + i
                minutes = build_minutes(seed=seed, agenda_kinds=kinds, n_agenda=n_agenda)
                if seals in ("on", "off"):
                    force_seals(minutes, seals == "on", seed)
                stem = f"minutes_{i + 1:0{width}d}"
                applied = None
                if "scan" in formats:
                    from .scan import images_to_pdf
                    pages, applied = _scan_pages(minutes, seed, profile, _int(params, "dpi"))
                    page_buf = io.BytesIO()
                    images_to_pdf(pages, page_buf)
                    zf.writestr(stem + "_scan.pdf", page_buf.getvalue())
                    applied["pages"] = len(pages)
                if "txt" in formats:
                    zf.writestr(stem + ".txt", render_text(minutes, seed))
                if "json" in formats:
                    payload = ground_truth(minutes)
                    payload["seed"] = seed
                    if applied:
                        payload["scan"] = applied
                    zf.writestr(stem + ".json",
                                json.dumps(payload, ensure_ascii=False, indent=2))
                if "html" in formats:
                    zf.writestr(stem + ".html", render_html(minutes, seed))
                if "pdf" in formats:
                    from .pdf import pdf_bytes
                    zf.writestr(stem + ".pdf", pdf_bytes(minutes, seed))
        self._send(buf.getvalue(), "application/zip", f"minutes_{base}_{count}건.zip")


def _scan_page_html(pages, applied: Dict[str, Any]) -> str:
    """열화된 페이지 이미지를 한 장씩 보여 주는 미리보기 문서."""
    import base64

    shots = []
    for page in pages:
        buf = io.BytesIO()
        page.save(buf, format="JPEG", quality=82)
        uri = base64.b64encode(buf.getvalue()).decode("ascii")
        shots.append(f'<img src="data:image/jpeg;base64,{uri}" alt="스캔본">')
    rows = "".join(
        f"<dt>{k}</dt><dd>{v if not isinstance(v, float) else round(v, 3)}</dd>"
        for k, v in sorted(applied.items()))
    return (
        "<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\">"
        "<style>body{margin:0;background:#5b5f66;padding:14px;"
        "font-family:system-ui,'Malgun Gothic',sans-serif}"
        "img{display:block;width:min(100%,900px);margin:0 auto 14px;"
        "box-shadow:0 4px 18px rgba(0,0,0,.45)}"
        "dl{max-width:900px;margin:0 auto;color:#e8eaed;font-size:12px;"
        "display:grid;grid-template-columns:max-content 1fr;gap:2px 12px;"
        "background:#3c4046;padding:12px 16px;border-radius:8px}"
        "dt{color:#a8b0bb}dd{margin:0}</style></head><body>"
        f"{''.join(shots)}<dl>{rows}</dl></body></html>")


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
  <span class="chip" id="scanchip">확인 중…</span>
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

    <h2>겉모습</h2>
    <label for="seals">인영(도장)</label>
    <select id="seals">
      <option value="auto">자동 (문서마다 다르게)</option>
      <option value="on">항상 찍기</option>
      <option value="off">찍지 않기</option>
    </select>

    <label for="scanprofile" style="margin-top:12px">스캔 노이즈</label>
    <select id="scanprofile"></select>
    <p class="hint">노이즈를 고르면 미리보기가 열화된 이미지로 바뀐다.
      만드는 데 몇 초 걸린다.</p>

    <div style="margin-top:16px">
      <button class="primary" id="make">새 문서 만들기</button>
    </div>

    <h2>이 문서 내려받기</h2>
    <div class="stack">
      <button class="wide" data-dl="pdf" id="dlpdf">PDF</button>
      <button class="wide" data-dl="txt">텍스트 (.txt)</button>
      <button class="wide" data-dl="json">정답셋 (.json)</button>
      <button class="wide" data-dl="html">HTML</button>
      <button class="wide" data-dl="scan_pdf" id="dlscanpdf">스캔본 (PDF)</button>
      <button class="wide" data-dl="scan_png" id="dlscanpng">스캔본 1쪽 (PNG)</button>
    </div>
    <p class="hint">스캔본은 위에서 고른 노이즈를 쓴다.
      노이즈가 "깨끗한 원본" 이면 사무실 스캔으로 만든다.</p>

    <h2>여러 건 한꺼번에</h2>
    <label for="count">개수</label>
    <input type="number" id="count" value="20" min="1" max="500">
    <div class="checks" style="margin:10px 0">
      <label><input type="checkbox" class="bf" value="pdf" checked>PDF</label>
      <label><input type="checkbox" class="bf" value="json" checked>JSON</label>
      <label><input type="checkbox" class="bf" value="txt">TXT</label>
      <label><input type="checkbox" class="bf" value="html">HTML</label>
      <label><input type="checkbox" class="bf" value="scan">스캔본</label>
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
  p.set('seals', $('seals').value);
  p.set('scan', $('scanprofile').value || 'clean');
  for (const [key, val] of Object.entries(extra || {})) p.set(key, val);
  return p.toString();
}

function refresh() {
  const profile = $('scanprofile').value || 'clean';
  const busy = profile !== 'clean';
  $('seedlabel').textContent = busy
    ? '시드 ' + ($('seed').value || '0') + ' · 스캔본 만드는 중…'
    : '시드 ' + ($('seed').value || '0');
  $('frame').src = '/preview?' + query();
}

$('frame') && ($('frame').onload = () => {
  $('seedlabel').textContent = '시드 ' + ($('seed').value || '0');
});

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

  const sc = $('scanchip');
  $('scanprofile').innerHTML = status.profiles.map(
    p => `<option value="${p.key}">${p.label}</option>`).join('');
  if (status.scan.ok) {
    sc.textContent = '스캔 노이즈 사용 가능';
  } else {
    sc.className = 'chip bad';
    sc.textContent = '스캔 불가 · ' + status.scan.reason + ' → ' + status.scan.fix;
    $('scanprofile').disabled = true;
    $('dlscanpdf').disabled = true;
    $('dlscanpng').disabled = true;
    const sb = document.querySelector('.bf[value=scan]');
    sb.checked = false; sb.disabled = true;
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
$('seals').onchange = refresh;
$('scanprofile').onchange = refresh;
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
