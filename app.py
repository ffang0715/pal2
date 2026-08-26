# -*- coding: utf-8 -*-
"""
出貨單分類 - 網頁版  Order Sorter (web)
------------------------------------------------
上傳出貨單 PDF (可含多筆訂單)，網頁會把每筆訂單的品項分成
常溫 / 冷藏 / 冷凍，並在每組上方標分數，畫面排版比照原本出貨單。
按「列印 / 存成 PDF」，瀏覽器就會存成 PDF。

本機執行:  pip install flask pdfplumber
          python app.py   ->  打開 http://127.0.0.1:5000
"""
import io
import re
import html
import base64
import logging

import pdfplumber
from flask import Flask, request, Response, redirect

logging.getLogger("pdfminer").setLevel(logging.ERROR)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024   # 上限 25MB

BUCKET_ORDER = ["常溫", "冷藏", "冷凍"]
BUCKET_TINT = {"常溫": "#f4efe4", "冷藏": "#e7f0f7", "冷凍": "#e6f2f4"}
BUCKET_INK = {"常溫": "#8a6d3b", "冷藏": "#2e6da4", "冷凍": "#2f7d8c"}


# ============================================================
# 分類 + 讀 PDF (與桌面版相同邏輯，去掉 tkinter/playwright)
# ============================================================
def categorize(name: str) -> str:
    n = name.replace("\n", " ")
    if "冷凍" in n:
        return "冷凍"
    if "冷藏" in n:
        return "冷藏"
    return "常溫"


def group_items(items):
    b = {x: [] for x in BUCKET_ORDER}
    for it in items:
        b[categorize(it["name"])].append(it)
    present = [x for x in BUCKET_ORDER if b[x]]
    denom = len(present)
    return [(x, i, denom, b[x]) for i, x in enumerate(present, 1)]


def _logo_b64(page):
    if not page.images:
        return ""
    im = page.images[0]
    bbox = (im["x0"], page.height - im["y1"], im["x1"], page.height - im["y0"])
    try:
        img = page.crop(bbox).to_image(resolution=300)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def _parse_header(text):
    def field(label):
        m = re.search(label + r"[：:]\s*(.*)", text)
        return m.group(1).strip() if m else ""
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    header = {k: field(k) for k in
              ["訂單編號", "購買日期", "訂購姓名", "手機號碼", "收件姓名",
               "收件電話", "收件地址", "付款方式", "配送方式", "指定到貨日", "消費金額"]}
    header["訂購帳號"] = m.group(0) if m else ""
    return header


def _parse_note(text):
    lines = text.splitlines()
    if "備註" not in lines:
        return ""
    out = []
    for l in lines[lines.index("備註") + 1:]:
        s = l.strip()
        if not s:
            continue
        if (s.startswith("http") or "出貨明細單" in s
                or re.match(r"\d{1,2}/\d{1,2}/\d{2,4},", s)):
            break
        out.append(s)
    return "\n".join(out).strip()


def _classify_rows(tables, items, summary):
    for tbl in tables:
        for row in tbl:
            if not row:
                continue
            idx = (row[0] or "").strip()
            name = (row[1] or "").strip()
            last = (row[-1] or "").strip()
            if idx.isdigit():
                items.append({
                    "name":  name,
                    "spec":  (row[2] or "").strip() if len(row) > 2 else "",
                    "qty":   (row[3] or "").strip() if len(row) > 3 else "",
                    "price": (row[4] or "").strip() if len(row) > 4 else "",
                    "total": (row[5] or "").strip() if len(row) > 5 else "",
                })
            elif name == "商品":
                continue
            elif last.startswith("$") or last.startswith("＄"):
                summary.append((name.rstrip(" ：:").strip(), last))
            elif name and "：" not in name and ":" not in name and items:
                items[-1]["name"] += "\n" + name


def parse_pdf(file_stream):
    """單次掃描每一頁，處理完就釋放，避免大檔把記憶體吃爆。"""
    raw = []            # 每筆訂單: {"texts":[...], "items":[...], "summary":[...]}
    logo = ""
    cur = None
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            tables = page.extract_tables()
            if "訂單編號" in text or cur is None:
                cur = {"texts": [text], "items": [], "summary": []}
                raw.append(cur)
                if not logo:
                    logo = _logo_b64(page)
            else:
                cur["texts"].append(text)
            _classify_rows(tables, cur["items"], cur["summary"])
            # 這頁處理完，立刻把快取清掉
            try:
                page.flush_cache()
            except Exception:
                pass
    orders = []
    for c in raw:
        if not c["items"]:
            continue
        text = "\n".join(c["texts"])
        orders.append({"logo": logo, "header": _parse_header(text),
                       "items": c["items"], "summary": c["summary"],
                       "note": _parse_note(text)})
    return orders


# ============================================================
# 產生出貨單 HTML
# ============================================================
def _order_section(data, title, page_break):
    h = data["header"]
    esc = html.escape

    def cell(v):
        return esc(v or "").replace("\n", "<br>")

    left = [("訂單編號", h["訂單編號"]), ("購買日期", h["購買日期"]),
            ("訂購姓名", h["訂購姓名"]), ("訂購帳號", h["訂購帳號"]),
            ("手機號碼", h["手機號碼"])]
    right = [("收件姓名", h["收件姓名"]), ("收件電話", h["收件電話"]),
             ("收件地址", h["收件地址"]), ("付款方式", h["付款方式"]),
             ("配送方式", h["配送方式"]), ("指定到貨日", h["指定到貨日"]),
             ("消費金額", h["消費金額"])]

    def col(rows):
        return "".join(
            f'<div class="frow"><span class="flabel">{esc(k)}：</span>'
            f'<span class="fval">{cell(v)}</span></div>' for k, v in rows)

    logo_html = (f'<img class="logo" src="data:image/png;base64,{data["logo"]}">'
                 if data["logo"] else '<div class="logo"></div>')

    rows_html, seq = [], 0
    for name, num, denom, items in group_items(data["items"]):
        tint, ink = BUCKET_TINT.get(name, "#eee"), BUCKET_INK.get(name, "#333")
        rows_html.append(
            f'<tr class="grouphead" style="background:{tint};color:{ink}">'
            f'<td colspan="6"><span class="gname">{esc(name)}</span>'
            f'<span class="gfrac">{num} / {denom}</span></td></tr>')
        for it in items:
            seq += 1
            rows_html.append(
                "<tr>"
                f'<td class="c-idx">{seq}</td>'
                f'<td class="c-name">{cell(it["name"])}</td>'
                f'<td class="c-spec">{cell(it["spec"])}</td>'
                f'<td class="c-num">{cell(it["qty"])}</td>'
                f'<td class="c-num">{cell(it["price"])}</td>'
                f'<td class="c-num">{cell(it["total"])}</td></tr>')

    summary = "".join(
        f'<tr class="sumrow"><td colspan="5" class="sumlabel">{esc(lb)}：</td>'
        f'<td class="c-num">{esc(amt)}</td></tr>' for lb, amt in data["summary"])

    note_html = (f'<div class="note"><div class="note-h">備註</div>'
                 f'<div class="note-b">{cell(data["note"])}</div></div>'
                 if data["note"] else "")

    brk = " brk" if page_break else ""
    return f"""<div class="order{brk}">
  <div class="top">{logo_html}<div class="title">{esc(title)}</div></div>
  <hr>
  <div class="head"><div class="lcol">{col(left)}</div><div class="rcol">{col(right)}</div></div>
  <table>
    <thead><tr>
      <th class="c-idx"></th><th class="c-name">商品</th><th class="c-spec">型號</th>
      <th class="c-num">數量</th><th class="c-num">單價</th><th class="c-num">總計</th>
    </tr></thead>
    <tbody>{''.join(rows_html)}{summary}</tbody>
  </table>
  {note_html}
</div>"""


def results_page(orders) -> str:
    multi = len(orders) > 1
    body = "".join(
        _order_section(data, f"出貨單-{i+1}" if multi else "出貨單",
                       page_break=(i < len(orders) - 1))
        for i, data in enumerate(orders))
    count_txt = f"共 {len(orders)} 筆訂單" if multi else "1 筆訂單"
    return f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>出貨單</title>
<style>
  * {{ box-sizing:border-box; }}
  body {{ font-family:"PingFang TC","Microsoft JhengHei","Noto Sans CJK TC","Heiti TC",sans-serif;
          color:#2b2b2b; margin:0; background:#efeae0;
          -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
  .toolbar {{ position:sticky; top:0; z-index:10; background:#5b4a2f; color:#fff;
              display:flex; align-items:center; gap:14px; padding:12px 18px; }}
  .toolbar .grow {{ flex:1; font-size:14px; }}
  .toolbar button, .toolbar a {{ font:inherit; font-size:14px; border:none; border-radius:8px;
              padding:9px 16px; cursor:pointer; text-decoration:none; }}
  .btn-pdf {{ background:#e5b769; color:#3a2f1a; font-weight:700; }}
  .btn-back {{ background:#7a6647; color:#fff; }}
  .page {{ background:#efeae0; padding:20px 0; }}
  .order {{ max-width:820px; margin:0 auto; background:#fff; padding:26px 34px;
            box-shadow:0 1px 6px rgba(0,0,0,.12); }}
  .order + .order {{ margin-top:22px; }}
  .top {{ display:flex; align-items:center; gap:16px; }}
  .logo {{ width:58px; height:58px; border-radius:50%; object-fit:cover; }}
  .title {{ font-size:28px; font-weight:800; letter-spacing:4px; }}
  hr {{ border:none; border-top:1px solid #d8d2c4; margin:12px 0 14px; }}
  .head {{ display:flex; margin-bottom:16px; }}
  .head .lcol {{ flex:1; padding-right:24px; }}
  .head .rcol {{ flex:1.15; padding-left:24px; border-left:1px solid #ddd; }}
  .frow {{ display:flex; margin:4px 0; font-size:13px; line-height:1.45; }}
  .flabel {{ color:#555; white-space:nowrap; }}
  .fval {{ color:#1e1e1e; word-break:break-all; }}
  table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
  tr {{ break-inside:avoid; }}
  thead th {{ background:#f3f1ec; border:1px solid #d9d5cb; padding:6px 10px;
              font-weight:600; text-align:left; color:#444; }}
  tbody td {{ border:1px solid #e2ded4; padding:5px 10px; vertical-align:top; }}
  .c-idx {{ width:34px; text-align:center; color:#888; }}
  .c-spec {{ width:130px; color:#555; }}
  .c-num {{ width:64px; text-align:right; white-space:nowrap; }}
  thead th.c-num, thead th.c-spec {{ text-align:left; }}
  .grouphead td {{ padding:8px 12px; font-weight:700; }}
  .gname {{ font-size:15px; letter-spacing:2px; }}
  .gfrac {{ float:right; font-size:15px; font-weight:800;
            border:1.5px solid currentColor; border-radius:14px; padding:1px 12px; }}
  .sumlabel {{ text-align:right; color:#444; }}
  .note {{ margin-top:18px; font-size:13px; }}
  .note-h {{ font-weight:700; margin-bottom:8px; }}
  .note-b {{ color:#333; padding-left:8px; }}
  @media print {{
    .toolbar {{ display:none; }}
    body, .page {{ background:#fff; padding:0; }}
    .order {{ box-shadow:none; max-width:none; padding-left:0; padding-right:0; }}
    .order.brk {{ page-break-after:always; }}
    .order + .order {{ margin-top:0; }}
    @page {{ margin:12mm; }}
  }}
</style></head>
<body>
  <div class="toolbar">
    <span class="grow">{count_txt}　已分好 常溫 / 冷藏 / 冷凍</span>
    <button class="btn-pdf" onclick="window.print()">列印 / 存成 PDF</button>
    <a class="btn-back" href="/">重新上傳</a>
  </div>
  <div class="page">{body}</div>
</body></html>"""


UPLOAD_PAGE = """<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>出貨單分類</title>
<style>
  body { font-family:"PingFang TC","Microsoft JhengHei","Noto Sans CJK TC",sans-serif;
         background:#efeae0; color:#3a2f1a; margin:0;
         min-height:100vh; display:flex; align-items:center; justify-content:center; }
  .card { background:#fff; width:min(560px,92vw); padding:34px 30px;
          border-radius:16px; box-shadow:0 4px 20px rgba(0,0,0,.10); text-align:center; }
  h1 { font-size:22px; margin:0 0 6px; }
  p.sub { color:#7a6647; margin:0 0 22px; font-size:14px; }
  #drop { display:block; border:2px dashed #c7b48d; border-radius:12px; padding:44px 20px;
          background:#faf7ef; cursor:pointer; transition:.15s; }
  #drop.hover { background:#f3ead2; border-color:#a98f5c; }
  #drop .big { font-size:16px; font-weight:700; margin-bottom:6px; }
  #drop .small { font-size:13px; color:#8a7a5c; }
  input[type=file] { display:none; }
  .err { color:#c0392b; font-size:14px; margin-top:14px; min-height:20px; }
  .foot { margin-top:18px; font-size:12px; color:#a2926f; }
</style></head>
<body>
  <div class="card">
    <h1>出貨單分類</h1>
    <p class="sub">上傳出貨單 PDF（可含多筆訂單），自動分成 常溫 / 冷藏 / 冷凍</p>
    <form id="f" method="post" action="/process" enctype="multipart/form-data">
      <label id="drop" for="file">
        <div class="big">把 PDF 拖到這裡</div>
        <div class="small">或點一下選擇檔案</div>
      </label>
      <input id="file" name="file" type="file" accept="application/pdf">
    </form>
    <div class="err" id="err"></div>
    <div class="foot">處理完成後按「列印 / 存成 PDF」即可存成 PDF</div>
  </div>
<script>
  const drop=document.getElementById('drop'), inp=document.getElementById('file'),
        form=document.getElementById('f'), err=document.getElementById('err');
  function submit(){ if(inp.files.length){ err.textContent='處理中…'; form.submit(); } }
  inp.addEventListener('change', submit);
  ['dragenter','dragover'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('hover');}));
  ['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove('hover');}));
  drop.addEventListener('drop',ev=>{ if(ev.dataTransfer.files.length){ inp.files=ev.dataTransfer.files; submit(); }});
</script>
</body></html>"""


@app.route("/")
def index():
    return UPLOAD_PAGE


@app.route("/process", methods=["POST"])
def process():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".pdf"):
        return redirect("/")
    try:
        orders = parse_pdf(f.stream)
    except Exception as e:
        return Response(f"讀取失敗：{html.escape(str(e))}", mimetype="text/plain")
    if not orders:
        return Response("這份 PDF 裡沒有抓到訂單。", mimetype="text/plain")
    return Response(results_page(orders), mimetype="text/html")


if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
