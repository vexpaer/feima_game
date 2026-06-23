import argparse
import base64
import json
import re
import tempfile
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright
from reportlab.lib.pagesizes import landscape
from reportlab.pdfgen import canvas as pdf_canvas

from fermat_app import service, store


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "db.json"
DEFAULT_OUT = ROOT / "poster"
POSTER_JS = ROOT / "static" / "poster.js"
BACKGROUND = ROOT / "static" / "feima.png"
POSTER_SIZE = (1200, 675)


def load_ranked_poster_data(db_path=DEFAULT_DB):
    data = store.read_db() if Path(db_path) == DEFAULT_DB else json.loads(Path(db_path).read_text(encoding="utf-8"))
    players = []
    for username, user in data.get("users", {}).items():
        if user.get("is_negative"):
            continue
        net_asset = service.compute_net_asset(username, data)
        players.append((username, net_asset))

    players.sort(key=lambda item: (item[1], item[0]), reverse=True)
    posters = []
    for index, (username, net_asset) in enumerate(players, start=1):
        item = service.build_poster_data(username, data, net_asset)
        item["safeFilename"] = f"{index:03d}_{safe_filename(username)}.png"
        posters.append(item)
    return posters


def safe_filename(value):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._")
    return cleaned or "player"


def site_poster_script(script_text=None):
    script = POSTER_JS.read_text(encoding="utf-8") if script_text is None else script_text
    background_data = base64.b64encode(BACKGROUND.read_bytes()).decode("ascii")
    background_src = f"data:image/png;base64,{background_data}"
    script = script.replace("bg.src = '/static/feima.png';", f"bg.src = '{background_src}';")
    marker = "ctx.fillRect(40, H - 4, W - 80, 3);"
    if marker in script and "window.__posterReady" not in script:
        script = script.replace(marker, marker + "\n    window.__posterReady = true;")
    return script


def build_poster_html(poster_data, script_text=None):
    poster_json = json.dumps(poster_data, ensure_ascii=False).replace("</", "<\\/")
    script = site_poster_script(script_text)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <style>
    html, body {{
      margin: 0;
      width: {POSTER_SIZE[0]}px;
      height: {POSTER_SIZE[1]}px;
      overflow: hidden;
      background: #000;
    }}
    canvas {{
      display: block;
      width: {POSTER_SIZE[0]}px;
      height: {POSTER_SIZE[1]}px;
    }}
  </style>
</head>
<body>
  <canvas id="poster-canvas" width="{POSTER_SIZE[0]}" height="{POSTER_SIZE[1]}"></canvas>
  <script id="poster-data" type="application/json">{poster_json}</script>
  <script>{script}</script>
</body>
</html>"""


def render_pngs(posters, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    image_paths = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": POSTER_SIZE[0], "height": POSTER_SIZE[1]},
                device_scale_factor=1,
            )
            for poster_data in posters:
                page.set_content(build_poster_html(poster_data), wait_until="load")
                page.wait_for_function("window.__posterReady === true", timeout=10000)
                canvas = page.locator("#poster-canvas")
                path = out_dir / poster_data["safeFilename"]
                canvas.screenshot(path=str(path))
                image_paths.append(path)
        finally:
            browser.close()
    return image_paths


def write_pdf(image_paths, pdf_path):
    page_size = landscape(POSTER_SIZE)
    doc = pdf_canvas.Canvas(str(pdf_path), pagesize=page_size)
    for image_path in image_paths:
        doc.drawImage(str(image_path), 0, 0, width=page_size[0], height=page_size[1])
        doc.showPage()
    doc.save()


def write_small_pdf(image_paths, pdf_path, jpeg_quality=80, scale=1):
    page_size = landscape(POSTER_SIZE)
    draw_size = (max(1, int(POSTER_SIZE[0] * scale)), max(1, int(POSTER_SIZE[1] * scale)))
    doc = pdf_canvas.Canvas(str(pdf_path), pagesize=page_size)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for index, image_path in enumerate(image_paths, start=1):
            jpg_path = tmp_path / f"{index:04d}.jpg"
            with Image.open(image_path) as image:
                image = image.convert("RGB").resize(draw_size, Image.Resampling.LANCZOS)
                image.save(jpg_path, "JPEG", quality=jpeg_quality, optimize=True, progressive=True)
            doc.drawImage(str(jpg_path), 0, 0, width=page_size[0], height=page_size[1])
            doc.showPage()
    doc.save()


def write_pdfs(image_paths, pdf_path, small_pdf_path):
    write_pdf(image_paths, pdf_path)
    write_small_pdf(image_paths, small_pdf_path)


def generate_posters(db_path=DEFAULT_DB, out_dir=DEFAULT_OUT):
    out_dir = Path(out_dir)
    posters = load_ranked_poster_data(db_path)
    image_paths = render_pngs(posters, out_dir)
    pdf_path = out_dir / "ranking_posters.pdf"
    small_pdf_path = out_dir / "ranking_posters_small.pdf"
    write_pdfs(image_paths, pdf_path, small_pdf_path)
    return image_paths, pdf_path, small_pdf_path


def main():
    parser = argparse.ArgumentParser(description="Generate ranked Fermat posters from the app database.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Optional legacy db.json path.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output directory. Defaults to ./poster.")
    args = parser.parse_args()

    images, pdf_path, small_pdf_path = generate_posters(args.db, args.out)
    print(f"Generated {len(images)} poster images in {Path(args.out).resolve()}")
    print(f"Generated PDF: {pdf_path.resolve()}")
    print(f"Generated small PDF: {small_pdf_path.resolve()}")


if __name__ == "__main__":
    main()
