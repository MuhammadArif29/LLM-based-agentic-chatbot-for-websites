# Brand Assistant — floating chat widget

Turns your original CLI Gemini bot into a floating chat bubble you can drop
on any website (built with WordPress in mind), backed by a small local
Flask server. It answers general questions using your own site info (plain
text, no RAG — see below), and can look up products, place orders, and
track orders on a WooCommerce store.

```
echnify-chatbot/
├── app.py                      # Flask server + Gemini chat + WooCommerce tools
├── requirements.txt
├── .env.example                # copy to .env and fill in
├── site_context.txt            # your business FAQs/policies (edit this)
├── static/
│   ├── widget.js                # the chat bubble widget
│   └── widget.css
└── wordpress_embed_snippet.html # paste into WordPress
```

## 1. Install & configure

```bash
cd echnify-chatbot
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:
- `GEMINI_API_KEY` — from [Google AI Studio](https://aistudio.google.com/apikey).
- `GEMINI_MODEL` — defaults to `gemini-3.1-flash-lite` (fast/cheap, matches
  your original script). Swap in `gemini-3.5-flash` if you want stronger
  reasoning for the ordering/tracking flows.
- `WC_STORE_URL`, `WC_CONSUMER_KEY`, `WC_CONSUMER_SECRET` — only needed if
  you want product lookup / ordering / tracking. Get keys from WooCommerce:
  **WooCommerce → Settings → Advanced → REST API → Add key**, permissions
  set to **Read/Write**. Your store needs HTTPS for this to work.

Edit `site_context.txt` with your real brand info (what you sell, shipping,
returns, contact info, FAQs). This is **not RAG** — there's no vector
search or chunking. The whole file is simply pasted into the system prompt
every time, so the model always "knows" it. That's the right call for a
page or two of FAQs; if you ever need to hand it a huge knowledge base
(hundreds of pages), that's the point where real RAG (embeddings + vector
search) becomes worth the extra complexity — this setup intentionally
skips that.

## 2. Run it

```bash
python app.py
```

This starts a local server at `http://localhost:5000`. Visit that URL in a
browser — you should see `{"status": "ok", ...}`.

## 3. Embed the widget

Open `wordpress_embed_snippet.html`, set `apiUrl` to wherever the server
above will actually be reachable from your visitors' browsers, then paste
the snippet into WordPress:
- **Custom HTML block** on a page/post, or
- **Appearance → Theme File Editor → footer.php**, just before `</body>`, or
- a header/footer plugin like WPCode or "Insert Headers and Footers".

### Where should `apiUrl` point?

You said you don't have Apache — that's fine, Flask's built-in server is
enough for local use, but "local" only reaches browsers that can actually
route to your machine:

| Your setup | `apiUrl` |
|---|---|
| WordPress running on the **same computer** (e.g. LocalWP, XAMPP, Studio) | `http://localhost:5000` works as-is |
| WordPress is a **live site elsewhere** and you're just testing | Run `ngrok http 5000` (or Cloudflare Tunnel), copy the `https://xxxx.ngrok-free.app` URL it gives you, use that as `apiUrl`. Free ngrok URLs change every restart — fine for testing, not for permanent use. |
| You want this **permanently live** for real customers | Deploy `app.py` to a small VPS or host (Render, Railway, a $5 droplet, etc.) behind a real domain + HTTPS, then point `apiUrl` there. |

## 4. What it can do

- Answers general questions from `site_context.txt` (no RAG, just always-on
  context).
- `get_product_info` — searches WooCommerce products by name/keyword,
  returns price, stock, and a link.
- `place_order` — creates a **pending** WooCommerce order (status `pending`,
  not paid) after confirming product/quantity/contact details with the
  customer, and gives them a payment link to finish checkout.
- `track_order` — looks up an order by ID, but only shares details if the
  email given matches the order's billing email.

The bot is instructed to always call these tools rather than guessing at
prices, stock, or order status.

## 5. Notes before going live

- **CORS is wide open** (`CORS(app)`) for easy local testing. Before real
  traffic hits this, lock it to your actual site's origin, e.g.
  `CORS(app, origins=["https://yoursite.com"])`.
- **No rate limiting or auth** on `/api/chat` — anyone who can reach the
  server can call your Gemini key through it. Fine for local dev; add
  rate limiting (e.g. Flask-Limiter) before exposing this publicly.
- **Sessions live in memory** and reset when you restart `app.py`. Fine for
  a single local server; swap in Redis or a DB if you need persistence.
- Flask's dev server (`debug=True`) is not meant for production — for a
  permanent deployment, run it behind `waitress` or `gunicorn` instead.

## 6. Customizing the look

All widget colors/fonts are CSS variables on `.ba-root` in `widget.css` —
override them from your theme's CSS if you want to match your brand instead
of the default coral/lime/plum palette.
