# 出貨單分類 網頁版

上傳出貨單 PDF（可含多筆訂單），網頁會把每筆訂單的品項分成
常溫 / 冷藏 / 冷凍，並在每組上方標分數，排版比照原本的出貨單。
按「列印 / 存成 PDF」，瀏覽器就會存成 PDF。

檔案：
- `app.py` — 整個程式
- `requirements.txt` — 需要的套件
- `Procfile` — 給雲端平台啟動用
- `runtime.txt` — 指定 Python 版本

---

## 先在自己電腦上試跑（可跳過）

    pip install -r requirements.txt
    python app.py

打開瀏覽器到 http://127.0.0.1:5000 就能用。

---

## 放到網路上，給朋友一個網址

下面兩種擇一。第一種要用到 GitHub，第二種完全在瀏覽器操作、不用 Git。

### 方法 A：Render（推薦，免費）

1. 把這個資料夾的檔案放上一個 GitHub repo
   （在 github.com 建一個新的 repository，把 `app.py`、`requirements.txt`、
   `Procfile`、`runtime.txt` 上傳進去）。
2. 到 https://render.com 註冊 / 登入，按 **New +** → **Web Service**。
3. 選你剛剛那個 GitHub repo。
4. 設定：
   - Runtime：Python
   - Build Command：`pip install -r requirements.txt`
   - Start Command：`gunicorn app:app --bind 0.0.0.0:$PORT`
   - Instance Type：Free
5. 按 **Create Web Service**，等它跑完（第一次約 2–3 分鐘）。
6. 完成後會給你一個網址，像 `https://你的名字.onrender.com`，
   把它傳給朋友就能用。

註：免費方案閒置一段時間會休眠，朋友第一次打開可能要等約 30–60 秒喚醒，
之後就正常。

### 方法 B：PythonAnywhere（不用 Git，全在瀏覽器）

1. 到 https://www.pythonanywhere.com 註冊免費帳號。
2. 進 **Files**，把 `app.py` 上傳到你的帳號目錄。
3. 進 **Consoles** 開一個 Bash console，輸入：

       pip install --user flask pdfplumber

4. 進 **Web** → **Add a new web app** → 選 **Flask** → Python 3.10 以上。
5. 建好後，把它的 WSGI 設定檔改成指向你的 `app.py` 裡的 `app`
   （PythonAnywhere 會有說明，重點是 `from app import app as application`）。
6. 按 **Reload**，它會給你一個 `你的名字.pythonanywhere.com` 網址。

---

## 常見問題

- **PDF 沒有存成，只是列印預覽？**
  在列印視窗的「目的地 / 印表機」選「另存為 PDF」再存檔即可。
- **朋友手機也能用嗎？** 可以，網頁在手機也能上傳與列印。
- **會不會存到我的檔案？** 程式讀完 PDF 就丟掉，不會存在伺服器上。
- **分類規則想改？** 打開 `app.py`，找 `categorize` 函式：
  名稱含「冷凍」→ 冷凍，含「冷藏」→ 冷藏，其餘 → 常溫。

---

## 檔案很大（幾十、上百筆訂單）時

程式已經改成「一頁一頁讀、讀完就丟」，一百筆訂單約用 200MB 記憶體、
十幾秒可跑完，Render 免費方案（512MB）大致能負荷。

但如果你常常要處理「幾百筆」的超大檔，免費 512MB 還是可能不夠。
這時建議換到記憶體更大的地方，下面兩個都能用同一份程式：

### 選項一：Hugging Face Spaces（免費、記憶體大，推薦）

免費方案就有 16GB 記憶體，處理超大檔綽綽有餘。用到的是這個資料夾裡的
`Dockerfile`。

1. 到 https://huggingface.co 註冊，按 **New** → **Space**。
2. Space SDK 選 **Docker** → **Blank**。
3. 把 `app.py`、`requirements.txt`、`Dockerfile` 上傳到這個 Space
   （網頁上就能上傳，不必用 Git）。
4. 它會自動建置，完成後給你一個
   `https://你的名字-space名.hf.space` 的網址。

（Space 閒置約兩天會休眠，有人打開會自動喚醒。）

### 選項二：Render 付費方案

同一個 Render 專案，把 Instance Type 從 Free 改成 **Standard（2GB）**，
不用改任何程式，記憶體就夠了。適合想留在 Render、不想搬家的情況。

