"""
Brand Assistant — server backend
=================================
Turns the original CLI Gemini chatbot into a small local Flask API that a
floating chat-bubble widget (static/widget.js) can talk to from a WordPress
site (or any website).

Run it with:  python app.py
Then embed static/widget.js + static/widget.css on your site (see README.md).
"""

import os
import threading
import uuid

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from google import genai
from google.genai import types

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")

WC_STORE_URL = (os.environ.get("WC_STORE_URL") or "").rstrip("/")
WC_CONSUMER_KEY = os.environ.get("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET = os.environ.get("WC_CONSUMER_SECRET")

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not set. Copy .env.example to .env and fill it in."
    )

client = genai.Client(api_key=GEMINI_API_KEY)


# ---------------------------------------------------------------------------
# Website knowledge — plain context stuffing, no RAG/embeddings.
# Everything in site_context.txt is simply always included in the system
# prompt. Fine for FAQs / policies / about-us copy on a small-to-medium
# site. If that file ever grows past a few thousand words, that's the
# point where real RAG (chunking + retrieval) starts to make sense instead.
# ---------------------------------------------------------------------------
def load_site_context() -> str:
    path = os.path.join(os.path.dirname(__file__), "site_context.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


SITE_CONTEXT = load_site_context()

BASE_PERSONA = """
Your name is Arif's Brand Assistant — a friendly, hyper-casual Gen-Z bestie who
helps visitors right here on this website.
Use Gen-Z slang naturally (e.g. 'no cap', 'bet', 'slay', 'fr', 'real', 'vibes'),
but never let slang get in the way of a correct answer about products or orders.
Keep your tone warm, enthusiastic, and supportive.
You're chatting inside a website text-chat bubble, so keep replies short and
scannable — 1 to 4 sentences, no markdown symbols like asterisks or headings,
plain text only. Use emojis naturally, but don't overdo it.

You have three tools: get_product_info, place_order, and track_order.
Call the right one whenever the user asks about a product, wants to buy
something, or wants to check an order. Never invent product names, prices,
links, stock levels, or order statuses — always call a tool and answer from
what it returns.
Before calling place_order, confirm the product, quantity, and the
customer's name, email, phone, and shipping address back to the user first.
If a tool returns an error, explain plainly what's missing or wrong and how
to fix it.
""".strip()

SYSTEM_PROMPT = BASE_PERSONA
if SITE_CONTEXT:
    SYSTEM_PROMPT += (
        "\n\n--- WEBSITE INFO ---\n"
        "Use this to answer general questions about the business (hours, "
        "policies, FAQs, what the brand is about). Answer naturally in your "
        "own words, don't paste it verbatim.\n\n" + SITE_CONTEXT
    )


# ---------------------------------------------------------------------------
# WooCommerce tools
# These are plain Python functions with type hints + docstrings so the
# Gemini SDK can turn them into callable tools automatically. get_or_create_chat()
# below wires them in, and run_chat_turn() executes any function calls the
# model makes and feeds the results back in.
# ---------------------------------------------------------------------------
def _wc_auth():
    if not (WC_CONSUMER_KEY and WC_CONSUMER_SECRET):
        raise RuntimeError("WooCommerce API keys aren't configured on the server (.env).")
    return (WC_CONSUMER_KEY, WC_CONSUMER_SECRET)


def get_product_info(query: str) -> dict:
    """Search the WooCommerce store for products matching a name or keyword,
    and return their price, stock status, and product page link.

    Args:
        query: The product name or keyword the customer is asking about.
    """
    if not WC_STORE_URL:
        return {"error": "This store isn't connected yet — ask the site owner to set WC_STORE_URL."}
    try:
        resp = requests.get(
            f"{WC_STORE_URL}/wp-json/wc/v3/products",
            params={"search": query, "per_page": 5, "status": "publish"},
            auth=_wc_auth(),
            timeout=15,
        )
        resp.raise_for_status()
        products = resp.json()
    except Exception as e:
        return {"error": f"Could not reach the store catalog: {e}"}

    if not products:
        return {"results": [], "message": "No matching products found."}

    results = []
    for p in products:
        short_desc = (p.get("short_description") or "").replace("<p>", "").replace("</p>", "").strip()
        results.append(
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "price": p.get("price"),
                "stock_status": p.get("stock_status"),
                "link": p.get("permalink"),
                "short_description": short_desc,
            }
        )
    return {"results": results}


def place_order(
    product_id: int,
    quantity: int,
    customer_name: str,
    customer_email: str,
    customer_phone: str,
    shipping_address: str,
) -> dict:
    """Create a new pending order on the WooCommerce store for one product.
    Only call this after the customer has confirmed the product, quantity,
    and their contact + shipping details.

    Args:
        product_id: The numeric WooCommerce product ID (get this from get_product_info first).
        quantity: How many units the customer wants.
        customer_name: The customer's full name.
        customer_email: The customer's email address.
        customer_phone: The customer's phone number.
        shipping_address: The full shipping address as one string.
    """
    if not WC_STORE_URL:
        return {"error": "This store isn't connected yet — ask the site owner to set WC_STORE_URL."}

    name_parts = customer_name.strip().split(" ", 1)
    first_name = name_parts[0] if name_parts else customer_name
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    payload = {
        "payment_method": "cod",
        "payment_method_title": "Pending confirmation",
        "set_paid": False,
        "status": "pending",
        "billing": {
            "first_name": first_name,
            "last_name": last_name,
            "email": customer_email,
            "phone": customer_phone,
            "address_1": shipping_address,
        },
        "shipping": {
            "first_name": first_name,
            "last_name": last_name,
            "address_1": shipping_address,
        },
        "line_items": [{"product_id": product_id, "quantity": quantity}],
    }

    try:
        resp = requests.post(
            f"{WC_STORE_URL}/wp-json/wc/v3/orders",
            json=payload,
            auth=_wc_auth(),
            timeout=20,
        )
        resp.raise_for_status()
        order = resp.json()
    except Exception as e:
        return {"error": f"Could not place the order: {e}"}

    pay_url = (
        f"{WC_STORE_URL}/checkout/order-pay/{order.get('id')}/"
        f"?pay_for_order=true&key={order.get('order_key')}"
    )

    return {
        "order_id": order.get("id"),
        "status": order.get("status"),
        "total": order.get("total"),
        "payment_link": pay_url,
    }


def track_order(order_id: int, customer_email: str) -> dict:
    """Look up an existing WooCommerce order by its ID and return its status,
    items, and total — after verifying the given email matches the order on file.

    Args:
        order_id: The numeric WooCommerce order ID the customer gave you.
        customer_email: The email the customer used when placing the order.
    """
    if not WC_STORE_URL:
        return {"error": "This store isn't connected yet — ask the site owner to set WC_STORE_URL."}
    try:
        resp = requests.get(
            f"{WC_STORE_URL}/wp-json/wc/v3/orders/{order_id}",
            auth=_wc_auth(),
            timeout=15,
        )
        if resp.status_code == 404:
            return {"error": "No order found with that ID."}
        resp.raise_for_status()
        order = resp.json()
    except Exception as e:
        return {"error": f"Could not look up that order: {e}"}

    billing_email = (order.get("billing") or {}).get("email", "").lower()
    if billing_email != customer_email.strip().lower():
        return {"error": "That email doesn't match the email on this order, so I can't share its details."}

    items = [{"name": li.get("name"), "quantity": li.get("quantity")} for li in order.get("line_items", [])]

    return {
        "order_id": order.get("id"),
        "status": order.get("status"),
        "date_created": order.get("date_created"),
        "total": order.get("total"),
        "items": items,
    }


TOOLS = [get_product_info, place_order, track_order]
FUNCTION_MAP = {f.__name__: f for f in TOOLS}


# ---------------------------------------------------------------------------
# Chat session management (in-memory — fine for a single local server;
# sessions are lost on restart)
# ---------------------------------------------------------------------------
_sessions = {}
_sessions_lock = threading.Lock()


def get_or_create_chat(session_id: str):
    with _sessions_lock:
        chat = _sessions.get(session_id)
        if chat is None:
            chat = client.chats.create(
                model=MODEL_NAME,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.7,
                    tools=TOOLS,
                ),
            )
            _sessions[session_id] = chat
        return chat


def run_chat_turn(chat, message: str) -> str:
    """Send a message and, defensively, execute any function calls ourselves
    and feed the results back in — this works whether or not the SDK's
    automatic function calling already handled it."""
    response = chat.send_message(message)

    for _ in range(5):  # hard cap so a buggy tool loop can't hang the request
        function_calls = getattr(response, "function_calls", None)
        if not function_calls:
            break

        parts = []
        for fc in function_calls:
            func = FUNCTION_MAP.get(fc.name)
            if func is None:
                result = {"error": f"Unknown tool '{fc.name}'"}
            else:
                try:
                    result = func(**fc.args)
                except Exception as e:
                    result = {"error": str(e)}
            parts.append(types.Part.from_function_response(name=fc.name, response={"result": result}))

        response = chat.send_message(parts)

    return response.text or "Hmm, I've got nothing there — mind rephrasing that? 🙏"


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)  # dev-friendly wide-open CORS — lock this down before going live, see README


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    session_id = data.get("session_id") or str(uuid.uuid4())

    if not message:
        return jsonify({"error": "Empty message"}), 400

    try:
        chat = get_or_create_chat(session_id)
        reply = run_chat_turn(chat, message)
    except Exception as e:
        print(f"[chat error] {e}")
        reply = "Ugh, my brain glitched for a sec 😵‍💫 mind trying that again?"

    return jsonify({"reply": reply, "session_id": session_id})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    with _sessions_lock:
        _sessions.pop(session_id, None)
    return jsonify({"ok": True})


@app.route("/demo")
def demo():
    return send_from_directory("static", "demo.html")


@app.route("/widget.js")
def widget_js():
    return send_from_directory("static", "widget.js", mimetype="application/javascript")


@app.route("/widget.css")
def widget_css():
    return send_from_directory("static", "widget.css", mimetype="text/css")


@app.route("/")
def health():
    return jsonify({"status": "ok", "message": "Brand Assistant server is running."})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)