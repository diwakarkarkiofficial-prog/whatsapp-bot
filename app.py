from flask import Flask, request
import requests
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
from datetime import datetime
import pytz

app = Flask(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_FROM = "whatsapp:+14155238886"

IST = pytz.timezone("Asia/Kolkata")

conversation_history = {}

NUMBER_TO_BUSINESS = {
    "whatsapp:+919266711535": "aura_salon",
    "whatsapp:+918510831097": "metamind",
    "whatsapp:+918796021321": "sibling"
}

BUSINESS_CONFIGS = {
    "aura_salon": {
        "name": "Aura Unisex Salon",
        "hours": "10am to 9pm, Monday to Sunday",
        "open_hour": 10,
        "close_hour": 21,
        "closed_days": [],
        "location": "Sector 110, Noida",
        "services": "Haircut, Hair Colour, Bridal Makeup, Nail Art, Facials",
        "pricing": "Haircut from Rs 300, Colour from Rs 800, Bridal packages from Rs 5000",
        "booking": "Call us or visit directly",
        "contact": "+919266711535",
        "owner_number": "whatsapp:+918167042585"
    },
    "metamind": {
        "name": "Metamind",
        "hours": "10am to 5pm, Monday to Saturday",
        "open_hour": 10,
        "close_hour": 17,
        "closed_days": [6],
        "location": "Noida",
        "services": "Mental health clinic with clinical Psychologists",
        "pricing": "Minimum Rs 1700 depending on therapist and requirements",
        "booking": "Call or WhatsApp us",
        "contact": "+918510831097",
        "owner_number": "whatsapp:+918510831097"
    },
    "sibling": {
        "name": "Personal Sibling",
        "hours": "24/7 available",
        "open_hour": 0,
        "close_hour": 24,
        "closed_days": [],
        "location": "In house",
        "services": "Everything that a sister does",
        "pricing": "1 hug and 30 minutes time spent together",
        "booking": "Call or WhatsApp us",
        "contact": "+918796021321",
        "owner_number": "whatsapp:+918796021321"
    },
    "default": {
        "name": "Demo Business",
        "hours": "9am to 8pm, Monday to Saturday",
        "open_hour": 9,
        "close_hour": 20,
        "closed_days": [6],
        "location": "Noida",
        "services": "Various services available",
        "pricing": "Contact us for pricing",
        "booking": "Call or WhatsApp us",
        "contact": "+9199999 99999",
        "owner_number": "+918167042585"
    }
}

def is_business_open(config):
    now = datetime.now(IST)
    current_hour = now.hour
    current_day = now.weekday()
    if current_day in config.get("closed_days", []):
        return False
    if current_hour >= config["open_hour"] and current_hour < config["close_hour"]:
        return True
    return False

def get_system_prompt(config, is_open):
    status = "You are currently available to assist customers." if is_open else f"The business is currently closed. Working hours are {config['hours']}. Let the customer know politely and tell them when you will be open. Still answer basic questions about services and pricing."
    return f"""You are a helpful WhatsApp assistant for {config['name']}.

Business Information:
- Working Hours: {config['hours']}
- Location: {config['location']}
- Services: {config['services']}
- Pricing: {config['pricing']}
- Booking: {config['booking']}
- Contact: {config['contact']}

Current Status: {status}

Rules:
- Keep all replies under 60 words
- Be friendly, warm and professional
- If asked something you don't know, say: Please contact us directly at {config['contact']}
- Never make up information
- Reply in the same language the customer uses
- Don't use bullet points, keep it conversational
- Remember the full conversation context when answering"""

def ask_groq(from_number, message, config):
    is_open = is_business_open(config)
    system_prompt = get_system_prompt(config, is_open)

    if from_number not in conversation_history:
        conversation_history[from_number] = []

    conversation_history[from_number].append({
        "role": "user",
        "content": message
    })

    if len(conversation_history[from_number]) > 20:
        conversation_history[from_number] = conversation_history[from_number][-20:]

    messages = [{"role": "system", "content": system_prompt}] + conversation_history[from_number]

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": messages,
                "max_tokens": 150,
                "temperature": 0.7
            },
            timeout=10
        )
        reply = response.json()["choices"][0]["message"]["content"]
        conversation_history[from_number].append({
            "role": "assistant",
            "content": reply
        })
        return reply
    except Exception as e:
        return f"Sorry, I'm having trouble right now. Please contact us directly at {config['contact']}"

def notify_owner(config, from_number, customer_message, bot_reply):
    if not config.get("owner_number") or not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        return
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            from_=TWILIO_FROM,
            to=config["owner_number"],
            body=f"New message for {config['name']}:\nFrom: {from_number}\nCustomer: {customer_message}\nBot replied: {bot_reply}"
        )
    except Exception as e:
        print(f"Owner notification failed: {e}")

def get_greeting(config):
    is_open = is_business_open(config)
    if is_open:
        return f"Hi! Welcome to {config['name']}. How can I help you today?"
    else:
        return f"Hi! Welcome to {config['name']}. We're currently closed but our hours are {config['hours']}. How can I help you?"

greeted_numbers = set()

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "")

    if not incoming_msg or len(incoming_msg.strip()) == 0:
        resp = MessagingResponse()
        return str(resp)

    business_key = NUMBER_TO_BUSINESS.get(from_number, "default")
    config = BUSINESS_CONFIGS.get(business_key)

    resp = MessagingResponse()

    if from_number not in greeted_numbers:
        greeted_numbers.add(from_number)
        greeting = get_greeting(config)
        resp.message(greeting)
        conversation_history[from_number] = [{
            "role": "assistant",
            "content": greeting
        }]
        conversation_history[from_number].append({
            "role": "user",
            "content": incoming_msg
        })
        ai_reply = ask_groq(from_number, incoming_msg, config)
        resp.message(ai_reply)
        notify_owner(config, from_number, incoming_msg, ai_reply)
        return str(resp)

    ai_reply = ask_groq(from_number, incoming_msg, config)
    resp.message(ai_reply)
    notify_owner(config, from_number, incoming_msg, ai_reply)
    return str(resp)

@app.route("/health", methods=["GET"])
def health():
    return "Bot is running!", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
