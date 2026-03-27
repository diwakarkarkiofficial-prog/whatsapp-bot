from flask import Flask, request
import requests
from twilio.twiml.messaging_response import MessagingResponse
import os

app = Flask(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

BUSINESS_CONFIGS = {
    "default": {
        "name": "Aura Unisex Salon",
        "hours": "10am to 9pm, Monday to Sunday",
        "location": "Sector 110, Noida",
        "services": "Haircut, Hair Colour, Bridal Makeup, Nail Art, Facials",
        "pricing": "Haircut from Rs 300, Colour from Rs 800, Bridal packages from Rs 5000",
        "booking": "Call us or visit directly",
        "contact": "+91 92667 11535"
    }
}

def get_system_prompt(config):
    return f"""You are a helpful WhatsApp assistant for {config['name']}.

Business Information:
- Working Hours: {config['hours']}
- Location: {config['location']}
- Services: {config['services']}
- Pricing: {config['pricing']}
- Booking: {config['booking']}
- Contact: {config['contact']}

Rules:
- Keep all replies under 60 words
- Be friendly, warm and professional
- If asked something you don't know, say: Please contact us directly at {config['contact']}
- Never make up information
- Reply in the same language the customer uses
- Don't use bullet points, keep it conversational"""

def ask_groq(message, config):
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {"role": "system", "content": get_system_prompt(config)},
                    {"role": "user", "content": message}
                ],
                "max_tokens": 150,
                "temperature": 0.7
            },
            timeout=10
        )
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return "Sorry, I'm having trouble right now. Please contact us directly."

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "")
    
    if not incoming_msg:
        resp = MessagingResponse()
        return str(resp)
    
    config = BUSINESS_CONFIGS.get("default")
    ai_reply = ask_groq(incoming_msg, config)
    
    resp = MessagingResponse()
    resp.message(ai_reply)
    return str(resp)

@app.route("/health", methods=["GET"])
def health():
    return "Bot is running!", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)


