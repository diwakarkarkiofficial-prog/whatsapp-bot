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
greeted_numbers = set()
message_counts = {}

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
        "owner_number": "whatsapp:+91OWNERNUMBER"
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
        "owner_number": "whatsapp:+918167042585"
    }
}

def is_business_open(config):
    now = datetime.now(IST)
    if now.weekday() in config.get("closed_days", []):
        return False
    return config["open_hour"] <= now.hour < config["close_hour"]

def get_system_prompt(config):
    is_open = is_business_open(config)
    now = datetime.now(IST)
    time_str = now.strftime("%I:%M %p")
    
    if is_open:
        status = "The business is currently OPEN."
    else:
        status = f"The business is currently CLOSED. It is {time_str} IST. Working hours are {config['hours']}. Politely inform the customer and tell them when to reach out."

    return f"""You are a friendly WhatsApp assistant for {config['name']}.

Business Info:
- Hours: {config['hours']}
- Location: {config['location']}
- Services: {config['services']}
- Pricing: {config['pricing']}
- Booking: {config['booking']}
- Contact: {config['contact']}

Status: {status}

Rules:
- Keep replies under 60 words
- Be warm, friendly and conversational
- Never use bullet points in replies
- Reply in the same language the customer uses
- If you don't know something, say: Please contact us directly at {config['contact']}
- Never make up information
- Remember the full conversation when answering
- If customer seems angry or frustrated, apologize sincerely and offer to connect them with the team
- If customer asks to speak to a human, give them the contact number immediately"""

def ask_groq(from_number, message, config):
    if from_number not in conversation_history:
        conversation_history[from_number] = []

    conversation_history[from_number].append({
        "role": "user",
        "content": message
    })

    if len(conversation_history[from_number]) > 20:
        conversation_history[from_number] = conversation_history[from_number][-20:]

    messages = [{"role": "system", "content": get_system_prompt(config)}] + conversation_history[from_number]

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
        print(f"Groq error: {e}")
        return f"Sorry, I'm having a technical issue. Please contact us directly at {config['contact']}"

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

def is_escalation_needed(message):
    triggers = ["speak to human", "real person", "manager", "speak to someone",
                "not helpful", "useless", "terrible", "worst", "angry",
                "complaint", "refund", "legal", "sue", "baat karo", "insaan se baat"]
    return any(trigger in message.lower() for trigger in triggers)

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "")

    if not incoming_msg:
        return str(MessagingResponse())

    business_key = NUMBER_TO_BUSINESS.get(from_number, "default")
    config = BUSINESS_CONFIGS.get(business_key)

    message_counts[from_number] = message_counts.get(from_number, 0) + 1

    resp = MessagingResponse()

    if is_escalation_needed(incoming_msg):
        reply = f"I completely understand your concern. Please contact our team directly at {config['contact']} and they'll sort this out for you right away."
        resp.message(reply)
        notify_owner(config, from_number, f"URGENT - Customer needs human: {incoming_msg}", reply)
        return str(resp)

    if from_number not in greeted_numbers:
        greeted_numbers.add(from_number)
        conversation_history[from_number] = []

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
