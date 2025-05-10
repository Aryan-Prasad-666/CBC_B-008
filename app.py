from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session
from werkzeug.exceptions import BadRequest, InternalServerError
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from datetime import datetime, timedelta  # Add this import if not already present
from dotenv import load_dotenv
import os
import json
import requests
import logging
import re
import base64
from io import BytesIO
from PIL import Image
import PyPDF2
import docx
import sqlite3
from datetime import datetime
import numpy as np
from dateutil.relativedelta import relativedelta

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key')

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            bill_type TEXT NOT NULL,
            amount REAL NOT NULL,
            bill_date TEXT NOT NULL,
            file_path TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Initialize API keys
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY environment variable not set")

# Use Gemini 2.0 Flash
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=GEMINI_API_KEY,
    temperature=0.5,
    max_output_tokens=1500
)

# Language instructions for chatbot
language_instructions = {
    "en-US": {
        "general": "You are a friendly financial advisor for Indian villagers with no prior financial knowledge. Provide simple, detailed, and patient responses in English related to financial planning, loans, investments, and banking, using examples relevant to rural life (e.g., farming loans, savings for crops). Explain basic concepts step-by-step, assuming the user knows nothing about finance. Do not answer queries unrelated to finance or loans; politely redirect to financial topics with encouragement to learn.",
        "ATM assistance": "You are a friendly ATM usage assistant for Indian villagers with no prior banking knowledge. Provide simple, step-by-step, and patient responses in English about using ATMs (e.g., withdrawing cash, checking balance, PIN safety). Use examples relevant to rural life (e.g., withdrawing money for farming needs). Explain each step clearly, assuming the user has never used an ATM. Do not answer queries unrelated to ATM usage; politely redirect to ATM-related topics with encouragement to learn.",
        "locker assistance": "You are a friendly locker facility assistant for Indian villagers with no prior banking knowledge. Provide simple, step-by-step, and patient responses in English about using bank locker facilities (e.g., renting a locker, accessing it, safety tips). Use examples relevant to rural life (e.g., storing crop earnings or family jewelry). Explain each step clearly, assuming the user has never used a locker. Do not answer queries unrelated to locker facilities; politely redirect to locker-related topics with encouragement to learn."
    },
    "hi-IN": {
        "general": "आप एक मित्रवत वित्तीय सलाहकार हैं जो भारतीय ग्रामीणों के लिए हैं, जिन्हें वित्त का कोई पूर्व ज्ञान नहीं है। हिंदी में वित्तीय नियोजन, ऋण, निवेश और बैंकिंग से संबंधित सरल, विस्तृत और धैर्यपूर्ण उत्तर दें, ग्रामीण जीवन (जैसे खेती के ऋण, फसलों के लिए बचत) से संबंधित उदाहरणों का उपयोग करें। बुनियादी अवधारणाओं को चरण-दर-चरण समझाएं, यह मानते हुए कि उपयोगकर्ता को वित्त के बारे में कुछ भी नहीं पता है। वित्त या ऋण से असंबंधित प्रश्नों का उत्तर न दें; विनम्रता से वित्तीय विषयों की ओर पुनर्निर्देशित करें और सीखने के लिए प्रोत्साहित करें।",
        "ATM assistance": "आप एक मित्रवत एटीएम उपयोग सहायक हैं जो भारतीय ग्रामीणों के लिए हैं, जिन्हें बैंकिंग का कोई पूर्व ज्ञान नहीं है। हिंदी में एटीएम उपयोग (जैसे नकदी निकासी, बैलेंस चेक, पिन सुरक्षा) के बारे में सरल, चरण-दर-चरण और धैर्यपूर्ण उत्तर दें। ग्रामीण जीवन से संबंधित उदाहरणों का उपयोग करें (जैसे खेती की जरूरतों के लिए पैसे निकालना)। प्रत्येक चरण को स्पष्ट रूप से समझाएं, यह मानते हुए कि उपयोगकर्ता ने कभी एटीएम का उपयोग नहीं किया है। एटीएम उपयोग से असंबंधित प्रश्नों का उत्तर न दें; विनम्रता से एटीएम से संबंधित विषयों की ओर पुनर्निर्देशित करें और सीखने के लिए प्रोत्साहित करें।",
        "locker assistance": "आप भारतीय ग्रामीणों के लिए एक मित्रवत लॉकर सुविधा सहायक हैं, जिन्हें बैंकिंग का कोई पूर्व ज्ञान नहीं है। बैंक लॉकर सुविधाओं (जैसे लॉकर किराए पर लेना, उसका उपयोग करना, सुरक्षा सुझाव) के बारे में हिंदी में सरल, चरण-दर-चरण और धैर्यपूर्ण उत्तर दें। ग्रामीण जीवन से संबंधित उदाहरणों का उपयोग करें (जैसे फसल की कमाई या पारिवारिक गहने संग्रह करना)। प्रत्येक चरण को स्पष्ट रूप से समझाएं, यह मानते हुए कि उपयोगकर्ता ने कभी लॉकर का उपयोग नहीं किया है। लॉकर सुविधाओं से असंबंधित प्रश्नों का उत्तर न दें; विनम्रता से लॉकर से संबंधित विषयों की ओर पुनर्निर्देशित करें और सीखने के लिए प्रोत्साहित करें।"
    },
    "kn-IN": {
        "general": "ನೀವು ಭಾರತೀಯ ಗ್ರಾಮೀಣರಿಗಾಗಿ ಸ್ನೇಹಶೀಲ ಆರ್ಥಿಕ ಸಲಹೆಗಾರರಾಗಿದ್ದೀರಿ, ಅವರಿಗೆ ಆರ್ಥಿಕತೆಯ ಬಗ್ಗೆ ಯಾವುದೇ ಮುಂಚಿನ ಜ್ಞಾನ ಇಲ್ಲ. ಆರ್ಥಿಕ ಯೋಜನೆ, ಸಾಲಗಳು, ಹೂಡಿಕೆಗಳು ಮತ್ತು ಬ್ಯಾಂಕಿಂಗ್‌ಗೆ ಸಂಬಂಧಿಸಿದಂತೆ ಕನ್ನಡದಲ್ಲಿ ಸರಳ, ವಿವರವಾದ ಮತ್ತು ತಾಳ್ಮೆಯ ಉತ್ತರಗಳನ್ನು ನೀಡಿ, ಗ್ರಾಮೀಣ ಜೀವನಕ್ಕೆ ಸಂಬಂಧಿಸಿದ ಉದಾಹರಣೆಗಳನ್ನು (ಉದಾ., ರೈತರಿಗೆ ಸಾಲ, ಬೆಳೆಗಳಿಗಾಗಿ ಉಳಿತಾಯ) ಬಳಸಿ. ಮೂಲ ಭಾವನೆಗಳನ್ನು ಹಂತ-ಹಂತವಾಗಿ ವಿವರಿಸಿ, ಬಳಕೆದಾರನಿಗೆ ಆರ್ಥಿಕತೆಯ ಬಗ್ಗೆ ಏನೂ ಗೊತ್ತಿಲ್ಲ ಎಂದು ಭಾವಿಸಿ. ಹಣಕಾಸು ಅಥವಾ ಸಾಲಕ್ಕೆ ಸಂಬಂಧಿಸದ ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರಿಸಬೇಡಿ; ಆರ್ಥಿಕ ವಿಷಯಗಳಿಗೆ ಸೌಜನ್ಯದಿಂದ ಮರುನಿರ್ದೇಶಿಸಿ ಮತ್ತು ಕಲಿಯಲು ಪ್ರೋತ್ಸಾಹಿಸಿ.",
        "ATM assistance": "ನೀವು ಭಾರತೀಯ ಗ್ರಾಮೀಣರಿಗಾಗಿ ಸ್ನೇಹಶೀಲ ಎಟಿಎಂ ಬಳಕೆ ಸಹಾಯಕರಾಗಿದ್ದೀರಿ, ಅವರಿಗೆ ಬ್ಯಾಂಕಿಂಗ್‌ನ ಯಾವುದೇ ಮುಂಚಿನ ಜ್ಞಾನ ಇಲ್ಲ. ಎಟಿಎಂ ಬಳಕೆಯ ಬಗ್ಗೆ (ಉದಾ., ನಗದು ಹಿಂಪಡೆಯುವಿಕೆ, ಬ್ಯಾಲೆನ್ಸ್ ಚೆಕ್, ಪಿನ್ ಸುರಕ್ಷತೆ) ಕನ್ನಡದಲ್ಲಿ ಸರಳ, ಹಂತ-ಹಂತವಾಗಿ ಮತ್ತು ತಾಳ್ಮೆಯ ಉತ್ತರಗಳನ್ನು ನೀಡಿ. ಗ್ರಾಮೀಣ ಜೀವನಕ್ಕೆ ಸಂಬಂಧಿಸಿದ ಉದಾಹರಣೆಗಳನ್ನು ಬಳಸಿ (ಉದಾ., ರೈತರಿಗೆ ಅಗತ್ಯವಿರುವ ಹಣವನ್ನು ಹಿಂಪಡೆಯುವಿಕೆ). ಪ್ರತಿ ಹಂತವನ್ನು ಸ್ಪಷ್ಟವಾಗಿ ವಿವರಿಸಿ, ಬಳಕೆದಾರನಿಗೆ ಎಟಿಎಂ ಬಳಸಿಲ್ಲ ಎಂದು ಭಾವಿಸಿ. ಎಟಿಎಂ ಬಳಕೆಗೆ ಸಂಬಂಧಿಸದ ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರಿಸಬೇಡಿ; ಎಟಿಎಂಗೆ ಸಂಬಂಧಿತ ವಿಷಯಗಳಿಗೆ ಸೌಜನ್ಯದಿಂದ ಮರುನಿರ್ದೇಶಿಸಿ ಮತ್ತು ಕಲಿಯಲು ಪ್ರೋತ್ಸಾಹಿಸಿ.",
        "locker assistance": "ನೀವು ಭಾರತೀಯ ಗ್ರಾಮೀಣರಿಗಾಗಿ ಸ್ನೇಹಶೀಲ ಲಾಕರ್ ಸೌಲಭ್ಯ ಸಹಾಯಕರಾಗಿದ್ದೀರಿ, ಅವರಿಗೆ ಬ್ಯಾಂಕಿಂಗ್‌ನ ಯಾವುದೇ ಮುಂಚಿನ ಜ್ಞಾನ ಇಲ್ಲ. ಬ್ಯಾಂಕ್ ಲಾಕರ್ ಸೌಲಭ್ಯಗಳ ಬಗ್ಗೆ (ಉದಾ., ಲಾಕರ್ ಬಾಡಿಗೆಗೆ ತೆಗೆದುಕೊಳ್ಳುವುದು, ಅದನ್ನು ಬಳಸುವುದು, ಸುರಕ್ಷತಾ ಸಲಹೆಗಳು) ಕನ್ನಡದಲ್ಲಿ ಸರಳ, ಹಂತ-ಹಂತವಾಗಿ ಮತ್ತು ತಾಳ್ಮೆಯ ಉತ್ತರಗಳನ್ನು ನೀಡಿ. ಗ್ರಾಮೀಣ ಜೀವನಕ್ಕೆ ಸಂಬಂಧಿಸಿದ ಉದಾಹರಣೆಗಳನ್ನು ಬಳಸಿ (ಉದಾ., ಬೆಳೆ ಆದಾಯ ಅಥವಾ ಕುಟುಂಬ ಆಭರಣಗಳನ್ನು ಶೇಖರಿಸುವುದು). ಪ್ರತಿ ಹಂತವನ್ನು ಸ್ಪಷ್ಟವಾಗಿ ವಿವರಿಸಿ, ಬಳಕೆದಾರನಿಗೆ ಲಾಕರ್ ಬಳಸಿಲ್ಲ ಎಂದು ಭಾವಿಸಿ. ಲಾಕರ್ ಸೌಲಭ್ಯಗಳಿಗೆ ಸಂಬಂಧಿಸದ ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರಿಸಬೇಡಿ; ಸೌಜನ್ಯದಿಂದ ಲಾಕರ್ ಸಂಬಂಧಿತ ವಿಷಯಗಳಿಗೆ ಮರುನಿರ್ದೇಶಿಸಿ ಮತ್ತು ಕಲಿಯಲು ಪ್ರೋತ್ಸಾಹಿಸಿ."
    },
    "ta-IN": {
        "general": "நீங்கள் இந்திய கிராமவாசிகளுக்காக உள்ள நட்பு நிதி ஆலோசகர், அவர்களுக்கு நிதி பற்றிய முந்தைய அறிவு இல்லை. நிதி திட்டமிடல், கடன்கள், முதலீடுகள் மற்றும் வங்கி சேவைகள் தொடர்பாக தமிழில் எளிமையான, விரிவான மற்றும் பொறுமையான பதில்களை வழங்கவும், கிராமப்புற வாழ்க்கைக்கு தொடர்புடைய எடுத்துக்காட்டுகளை (எ.கா., விவசாய கடன்கள், பயிர்களுக்கான சேமிப்பு) பயன்படுத்தவும். அடிப்படை கருத்துகளை படி-படியாக விளக்கவும், பயனருக்கு நிதி பற்றி எதுவும் தெரியாது என்று கருதவும். நிதி அல்லது கடன் தொடர்பற்ற கேள்விகளுக்கு பதிலளிக்க வேண்டாம்; பணிவுடன் நிதி தலைப்புகளுக்கு மறு வழிநடத்தி, கற்க புரிதல் உதவுங்கள்.",
        "ATM assistance": "நீங்கள் இந்திய கிராமவாசிகளுக்காக உள்ள நட்பு ஏடிஎம் பயன்பாட்டு உதவியாளர், அவர்களுக்கு வங்கி பற்றிய முந்தைய அறிவு இல்லை. ஏடிஎம் பயன்பாடு (எ.கா., பணம் எடுப்பது, இருப்பு சரிபார்ப்பது, பின் பாதுகாப்பு) பற்றி தமிழில் எளிமையான, படி-படியான மற்றும் பொறுமையான பதில்களை வழங்கவும். கிராமப்புற வாழ்க்கைக்கு தொடர்புடைய எடுத்துக்காட்டுகளைப் பயன்படுத்தவும் (எ.கா., விவசாயத் தேவைகளுக்கு பணம் எடுப்பது). ஒவ்வொரு படியையும் தெளிவாக விளக்கவும், பயனர் ஏடிஎம்மைப் பயன்படுத்தவில்லை என்று கருதவும். ஏடிஎம் பயன்பாட்டுக்கு தொடர்பில்லாத கேள்விகளுக்கு பதிலளிக்க வேண்டாம்; பணிவுடன் ஏடிஎம் தொடர்பான தலைப்புகளுக்கு மறு வழிநடத்தி, கற்க ஊக்குவிக்கவும்.",
        "locker assistance": "நீங்கள் இந்திய கிராமவாசிகளுக்காக உள்ள நட்பு லாக்கர் வசதி உதவியாளர், அவர்களுக்கு வங்கி பற்றிய முந்தைய அறிவு இல்லை. வங்கி லாக்கர் வசதிகள் (எ.கா., லாக்கர் வாடகைக்கு எடுப்பது, அதைப் பயன்படுத்துவது, பாதுகாப்பு குறிப்புகள்) பற்றி தமிழில் எளிமையான, படி-படியான மற்றும் பொறுமையான பதில்களை வழங்கவும். கிராமப்புற வாழ்க்கைக்கு தொடர்புடைய எடுத்துக்காட்டுகளைப் பயன்படுத்தவும் (எ.கா., பயிர் வருவாய் அல்லது குடும்ப நகைகளை சேமித்தல்). ஒவ்வொரு படியையும் தெளிவாக விளக்கவும், பயனர் லாக்கரைப் பயன்படுத்தவில्लை என்று கருதவும். லாக்கர் வசதிகளுக்கு தொடர்பில்லாத கேள்விகளுக்கு பதிலளிக்க வேண்டாம்; பணிவுடன் லாக்கர் தொடர்பான தலைப்புகளுக்கு மறு வழிநடத்தி, கற்க ஊக்குவிக்கவும்."
    },
    "te-IN": {
        "general": "మీరు భారతీయ గ్రామస్తుల కోసం స్నేహపూర్వకమైన ఆర్థిక సలహాదారుడు, వీరికి ఆర్థిక జ్ఞానం లేదు. ఆర్థిక ప్రణాళిక, రుణాలు, పెట్టుబడులు మరియు బ్యాంకింగ్‌కు సంబంధించిన సాధారణ, వివరణాత్మక మరియు ధైర్యంగా ఉన్న జవాబులను తెలుగులో ఇవ్వండి, గ్రామీణ జీవన విధానానికి సంబంధించిన ఉదాహరణలను (ఉదా., రైతు రుణాలు, పంటల కోసం ఆదా) ఉపయోగించండి. మౌలిక భావనలను దశ-దశల వారీగా వివరించండి, వినియోగదారుడు ఆర్థిక విషయాల గురించి ఏమీ తెలియదని భావించండి. ఆర్థిక లేదా రుణాలకు సంబంధించని ప్రశ్నలకు సమాధానం ఇవ్వకూడదు; సౌజన్యంగా ఆర్థిక విషయాలకు మళ్లించి, నేర్చుకోవడానికి ప్రోత్సాహించండి.",
        "ATM assistance": "మీరు భారతీయ గ్రామస్తుల కోసం స్నేహపూర్వకమైన ఏటీఎం వినియోగ సహాయకుడు, వీరికి బ్యాంకింగ్ గురించి ఎటువంటి ముందస్తు జ్ఞానం లేదు. ఏటీఎం వినియోగం (ఉదా., నగదు ఉపసంహరణ, బ్యాలెన్స్ చెక్, పిన్ భద్రత) గురించి తెలుగులో సాధారణ, దశ-దశలవారీగా మరియు ఓపికగా జవాబులు ఇవ్వండి. గ్రామీణ జీవనానికి సంబంధించిన ఉదాహరణలను ఉపయోగించండి (ఉదా., వ్యవసాయ అవసరాల కోసం డబ్బు ఉపసంహరణ). ప్రతి దశను స్పష్టంగా వివరించండి, వినియోగదారుడు ఏటీఎం ఉపయోగించలేదని భావించండి. ఏటీఎం వినియోగానికి సంబంధించని ప్రశ్నలకు సమాధానం ఇవ్వకండి; సౌజన్యంగా ఏటీఎం సంబంధిత అంశాలకు మళ్లించి, నేర్చుకోవడానికి ప్రోత్సాహించండి.",
        "locker assistance": "మీరు భారతీయ గ్రామస్తుల కోసం స్నేహపూర్వక లాకర్ సౌకర్య సహాయకుడు, వీరికి బ్యాంకింగ్ గురించి ఎటువంటి ముందస్తు జ్ఞానం లేదు. బ్యాంక్ లాకర్ సౌకర్యాల గురించి (ఉదా., లాకర్ అద్దెకు తీసుకోవడం, దానిని ఉపయోగించడం, భద్రతా చిట్కాలు) తెలుగులో సాధారణ, దశ-దశలవారీగా మరియు ఓపికగా జవాబులు ఇవ్వండి. గ్రామీణ జీవనానికి సంబంధించిన ఉదాహరణలను ఉపయోగించండి (ఉదా., పంట ఆదాయం లేదా కుటుంబ ఆభరణాలను నిల్వ చేయడం). ప్రతి దశను స్పష్టంగా వివరించండి, వినియోగదారుడు లాకర్ ఉపయోగించలేదని భావించండి. లాకర్ సౌకర్యాలకు సంబంధించని ప్రశ్నలకు సమాధానం ఇవ్వకండి; సౌజన్యంగా లాకర్ సంబంధిత అంశాలకు మళ్లించి, నేర్చుకోవడానికి ప్రోత్సాహించండి."
    }
}

# Existing Routes
@app.route('/')
def index():
    lang = request.args.get('lang', 'en')
    return render_template('homepage.html', lang=lang)

@app.route('/microloan')
def microloan():
    lang = request.args.get('lang', 'en')
    return render_template('loan.html', lang=lang)

@app.route('/banks')
def banks():
    lang = request.args.get('lang', 'en')
    return render_template('banks.html', lang=lang)

@app.route('/schemes')
def schemes():
    lang = request.args.get('lang', 'en')
    return render_template('schemes.html', lang=lang)

@app.route('/document_analyzer')
def document_analyzer():
    lang = request.args.get('lang', 'en')
    return render_template('document_analyzer.html', lang=lang)

@app.route('/check_eligibility', methods=['POST'])
def check_eligibility():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        required_fields = [
            'age', 'monthlyIncome', 'existingLoans', 'existingLoanAmount',
            'defaultHistory', 'loanAmount', 'loanPurpose', 'loanTenure'
        ]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing field: {field}"}), 400

        try:
            age = int(data['age'])
            monthly_income = int(data['monthlyIncome'])
            existing_loan_amount = int(data['existingLoanAmount'])
            loan_amount = int(data['loanAmount'])
            loan_tenure = int(data['loanTenure'])
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid numeric input"}), 400

        # Manual basic validation
        if not (18 <= age <= 65):
            return jsonify({"status": "rejected", "reason": "Age must be between 18 and 65."}), 200
        if monthly_income < 5000:
            return jsonify({"status": "rejected", "reason": "Monthly income must be at least ₹5,000."}), 200
        if not (1000 <= loan_amount <= 100000):
            return jsonify({"status": "rejected", "reason": "Loan amount must be between ₹1,000 and ₹100,000."}), 200
        if existing_loan_amount > 2 * monthly_income:
            return jsonify({"status": "pending", "reason": "Existing loan amount exceeds 2x monthly income. Additional review required."}), 200
        if data['defaultHistory'] == 'yes':
            return jsonify({"status": "rejected", "reason": "History of loan default detected."}), 200

        prompt_template = PromptTemplate(
            input_variables=["age", "monthlyIncome", "existingLoans", "existingLoanAmount", 
                            "defaultHistory", "loanAmount", "loanPurpose", "loanTenure"],
            template=""" 
            Evaluate the eligibility of an applicant for a microloan based on the following information:
            - Age: {age} years
            - Monthly Income: ₹{monthlyIncome}
            - Existing Loans: {existingLoans}
            - Existing Loan Amount: ₹{existingLoanAmount}
            - Default History: {defaultHistory}
            - Loan Amount Requested: ₹{loanAmount}
            - Loan Purpose: {loanPurpose}
            - Loan Tenure: {loanTenure} months

            Eligibility criteria:
            - Monthly income should be at least ₹5,000.
            - No recent loan defaults.
            - Loan amount should be between ₹1,000 and ₹100,000.
            - Age should be between 18 and 65.
            - Existing loan amount should not exceed 2x monthly income.
            - Loan purpose should be reasonable (e.g., agriculture, business, education).

            Return a JSON object with:
            - status: "approved", "pending", or "rejected"
            - reason: A brief explanation for the status

            Example output:
            {{
                "status": "approved",
                "reason": "Applicant meets all eligibility criteria."
            }}
            """
        )

        prompt = prompt_template.format(
            age=age,
            monthlyIncome=monthly_income,
            existingLoans=data['existingLoans'],
            existingLoanAmount=existing_loan_amount,
            defaultHistory=data['defaultHistory'],
            loanAmount=loan_amount,
            loanPurpose=data['loanPurpose'],
            loanTenure=loan_tenure
        )

        response = llm.invoke(prompt)

        try:
            result = json.loads(response.content)
        except:
            result = {
                "status": "pending",
                "reason": "Unable to process eligibility. Please contact support."
            }

        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/find_banks', methods=['POST'])
def find_banks():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        required_fields = ['location', 'district', 'state']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"Missing or empty field: {field}"}), 400

        address = f"{data['location']}, {data['district']}, {data['state']}, India"

        geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={GOOGLE_API_KEY}"
        geocode_response = requests.get(geocode_url)
        geocode_data = geocode_response.json()

        if geocode_data['status'] != 'OK' or not geocode_data['results']:
            return jsonify({
                "error": "Unable to geocode address",
                "banks": [],
                "center": {"lat": 12.9716, "lng": 77.5946}
            }), 400

        location = geocode_data['results'][0]['geometry']['location']
        lat, lng = location['lat'], location['lng']

        places_url = (
            f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?"
            f"location={lat},{lng}&radius=10000&type=bank&key={GOOGLE_API_KEY}"
        )
        places_response = requests.get(places_url)
        places_data = places_response.json()

        if places_data['status'] != 'OK':
            mock_banks = [
                {
                    "name": "State Bank of India (Mock)",
                    "address": "123 Main Road, Shivajinagar, Bengaluru, Karnataka",
                    "lat": 12.9716,
                    "lng": 77.5946
                },
                {
                    "name": "Canara Bank (Mock)",
                    "address": "456 MG Road, Bengaluru, Karnataka",
                    "lat": 12.9750,
                    "lng": 77.6000
                }
            ]
            return jsonify({
                "banks": mock_banks,
                "center": {"lat": lat, "lng": lng}
            }), 200

        banks = []
        for place in places_data['results'][:5]:
            banks.append({
                "name": place['name'],
                "address": place.get('vicinity', 'Address not available'),
                "lat": place['geometry']['location']['lat'],
                "lng": place['geometry']['location']['lng']
            })

        return jsonify({
            "banks": banks,
            "center": {"lat": lat, "lng": lng}
        }), 200

    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/find_lockers', methods=['POST'])
def find_lockers():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        required_fields = ['location', 'district', 'state']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"Missing or empty field: {field}"}), 400

        location = data['location'].strip().title()
        district = data['district'].strip().title()
        state = data['state'].strip().title()

        prompt_template = PromptTemplate(
            input_variables=["location", "district", "state"],
            template=""" 
            You are a banking assistant for India. Based on the provided location details, generate a list of banks that offer locker facilities in the specified area. Focus on banks that are likely to have locker services (e.g., major public and private banks like State Bank of India, HDFC Bank, or Canara Bank) and are relevant to the given location.

            Location Details:
            - Village/Town: {location}
            - District: {district}
            - State: {state}

            Instructions:
            - Generate a list of 3-5 banks that likely offer locker facilities in or near the specified location.
            - Each bank must include:
              - name: The bank's name (e.g., State Bank of India).
              - address: A plausible address for the bank branch in the specified area (e.g., Main Road, {location}, {district}, {state}).
              - lat: A plausible latitude coordinate for the branch (e.g., based on typical coordinates for the district or state).
              - lng: A plausible longitude coordinate for the branch.
            - Return a JSON object with:
              - banks: An array of bank objects.
              - center: An object with 'lat' and 'lng' representing the approximate center of the search area.
            - If specific bank branches are not known, provide plausible examples of major banks likely to have branches in the area (e.g., SBI, ICICI, Canara Bank) with realistic addresses and coordinates.
            - Do not include any additional text, markdown, or explanations—only the JSON object.
            - Ensure the JSON is valid and properly formatted.

            Example Output:
            {{
                "banks": [
                    {{
                        "name": "State Bank of India",
                        "address": "Main Road, Shivajinagar, Bengaluru Urban, Karnataka",
                        "lat": 12.9716,
                        "lng": 77.5946
                    }},
                    {{
                        "name": "HDFC Bank",
                        "address": "MG Road, Bengaluru Urban, Karnataka",
                        "lat": 12.9750,
                        "lng": 77.6000
                    }}
                ],
                "center": {{
                    "lat": 12.9716,
                    "lng": 77.5946
                }}
            }}
            """
        )

        prompt = prompt_template.format(
            location=location,
            district=district,
            state=state
        )

        try:
            logger.debug(f"Sending prompt to Gemini for lockers: {prompt[:200]}...")
            response = llm.invoke(prompt)
            logger.debug(f"Raw Gemini response: {response.content}")

            response_content = response.content.strip()
            response_content = re.sub(r'^```json\s*|\s*```$', '', response_content).strip()
            logger.debug(f"Cleaned Gemini response: {response_content}")

            result = json.loads(response_content)
            if not isinstance(result, dict) or 'banks' not in result or 'center' not in result:
                logger.error("Invalid response format from Gemini")
                return jsonify({
                    "banks": [],
                    "center": {"lat": 12.9716, "lng": 77.5946}
                }), 200

            required_fields = ['name', 'address', 'lat', 'lng']
            valid_banks = []
            for bank in result['banks']:
                if isinstance(bank, dict) and all(field in bank for field in required_fields):
                    valid_banks.append(bank)
                else:
                    logger.warning(f"Invalid bank object: {bank}")
            result['banks'] = valid_banks

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Error parsing Gemini response: {str(e)}")
            return jsonify({
                "banks": [],
                "center": {"lat": 12.9716, "lng": 77.5946}
            }), 200
        except Exception as e:
            logger.error(f"Gemini query error: {str(e)}")
            return jsonify({"error": f"Server error: {str(e)}"}), 500

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/find_schemes', methods=['POST'])
def find_schemes():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        required_fields = ['location', 'district', 'state']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"Missing or empty field: {field}"}), 400

        location = data['location'].strip().title()
        district = data['district'].strip().title()
        state = data['state'].strip().title()

        prompt_template = PromptTemplate(
            input_variables=["location", "district", "state"],
            template=""" 
            You are a government schemes assistant for India. Based on the provided location details, generate a list of government schemes available in the specified area. Include both national schemes (applicable to all states) and state- or district-specific schemes relevant to the given location.

            Location Details:
            - Village/Town: {location}
            - District: {district}
            - State: {state}

            Instructions:
            - Generate at least 3-5 schemes, including:
              - National schemes (e.g., MGNREGA, PMGSY) if applicable.
              - State-specific schemes for {state} (e.g., schemes by the {state} government).
              - District-specific schemes for {district} if available.
            - Each scheme must include:
              - name: The scheme's name.
              - description: A brief description (2-3 sentences).
              - eligibility: Who can apply (e.g., rural households, farmers).
              - link: A realistic URL for more information (e.g., official government website).
              - states: List of applicable states (include 'All' for national schemes, or specific states like '{state}').
              - districts: List of applicable districts (include 'All' for state/national schemes, or specific districts like '{district}').
              - launch_date: The scheme's launch date in YYYY-MM-DD format (use recent dates for new schemes, e.g., 2023 or 2024).
            - Return a JSON array of scheme objects, sorted by launch_date (newest first).
            - If no specific schemes are known for the district, include national and state schemes and note any limitations.
            - Do not include any additional text, markdown, or explanations—only the JSON array.
            - Ensure the JSON is valid and properly formatted.

            Example Output:
            [
                {{
                    "name": "Chief Minister’s Gram Vikas Yojana",
                    "description": "Supports village development through infrastructure and grants in Karnataka.",
                    "eligibility": "Selected villages under the scheme in Karnataka.",
                    "link": "https://bengaluruurban.nic.in",
                    "states": ["Karnataka"],
                    "districts": ["Bengaluru Urban", "Shivamogga"],
                    "launch_date": "2024-01-01"
                }},
                {{
                    "name": "MGNREGA",
                    "description": "Guarantees 100 days of wage employment per year to rural households for unskilled manual work.",
                    "eligibility": "Rural households willing to do unskilled manual work.",
                    "link": "https://nrega.nic.in",
                    "states": ["All"],
                    "districts": ["All"],
                    "launch_date": "2006-02-02"
                }}
            ]
            """
        )

        prompt = prompt_template.format(
            location=location,
            district=district,
            state=state
        )

        try:
            logger.debug(f"Sending prompt to Gemini: {prompt[:200]}...")
            response = llm.invoke(prompt)
            logger.debug(f"Raw Gemini response: {response.content}")

            response_content = response.content.strip()
            response_content = re.sub(r'^```json\s*|\s*```$', '', response_content).strip()
            logger.debug(f"Cleaned Gemini response: {response_content}")

            schemes = json.loads(response_content)
            if not isinstance(schemes, list):
                logger.error("Gemini response is not a list")
                schemes = []

            required_fields = ['name', 'description', 'eligibility', 'link', 'states', 'districts', 'launch_date']
            valid_schemes = []
            for scheme in schemes:
                if isinstance(scheme, dict) and all(field in scheme for field in required_fields):
                    valid_schemes.append(scheme)
                else:
                    logger.warning(f"Invalid scheme object: {scheme}")
            schemes = valid_schemes

            schemes.sort(key=lambda x: x['launch_date'], reverse=True)

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Error parsing Gemini response: {str(e)}")
            schemes = []
        except Exception as e:
            logger.error(f"Gemini query error: {str(e)}")
            schemes = []

        return jsonify({"schemes": schemes}), 200

    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/analyze_document', methods=['POST'])
def analyze_document():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files['file']
        document_type = request.form.get('document_type', 'other')
        language = request.form.get('language', 'en')

        if not file.filename:
            return jsonify({"error": "No file selected"}), 400

        # Validate file type
        allowed_extensions = {'pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx'}
        if file.filename.rsplit('.', 1)[-1].lower() not in allowed_extensions:
            return jsonify({"error": "Unsupported file type. Use PDF, JPG, PNG, DOC, or DOCX."}), 400

        # Basic content extraction (simulated OCR for images/PDFs, direct for DOCX)
        content = ""
        if file.filename.endswith('.pdf'):
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                content += page.extract_text() or ""
        elif file.filename.endswith(('.jpg', '.jpeg', '.png')):
            image = Image.open(file)
            content = f"Sample {document_type} document content extracted from image."
        elif file.filename.endswith(('.doc', '.docx')):
            doc = docx.Document(file)
            content = "\n".join([para.text for para in doc.paragraphs])

        if not content.strip():
            content = f"Placeholder content for {document_type} document."

        # Define prompt template
        prompt_template = PromptTemplate(
            input_variables=["content", "document_type", "language"],
            template=""" 
            You are a financial document analysis assistant for India. Analyze the provided document content and provide guidance for filling it out correctly. The document type is '{document_type}' and the output must be in '{language}'.

            Document Content:
            {content}

            Instructions:
            - Analyze the document content and identify its purpose and requirements.
            - Provide the following in '{language}':
              - Summary: A brief description of the document's purpose (1-2 sentences).
              - Required Information: A list of 3-5 key fields or details needed to complete the document.
              - Filing Instructions: A list of 3-5 steps to correctly fill out or submit the document.
              - Important Notes: Any additional guidance or requirements (e.g., supporting documents, mandatory fields).
            - Return a JSON object with translations for English, Hindi, and Kannada, even if the requested language is only one of them.
            - Ensure the JSON is valid and properly formatted.
            - Do not include markdown or extra text, only the JSON object.

            Example Output:
            {{
                "en": {{
                    "summary": "This is a loan application form requiring personal and financial details.",
                    "required_info": ["Name and address", "Monthly income", "Loan amount", "Purpose of loan", "Repayment period"],
                    "instructions": ["Fill in personal details in BLOCK LETTERS", "Provide accurate income", "State loan purpose clearly", "Include bank details", "Sign the form"],
                    "notes": "Attach Aadhaar/PAN, address proof, and income proof. All fields marked with * are mandatory."
                }},
                "hi": {{
                    "summary": "यह एक ऋण आवेदन पत्र है जिसमें व्यक्तिगत और वित्तीय विवरण की आवश्यकता है।",
                    "required_info": ["नाम और पता", "मासिक आय", "ऋण राशि", "ऋण का उद्देश्य", "पुनर्भुगतान अवधि"],
                    "instructions": ["व्यक्तिगत विवरण बड़े अक्षरों में भरें", "सटीक आय प्रदान करें", "ऋण का उद्देश्य स्पष्ट करें", "बैंक विवरण शामिल करें", "फॉर्म पर हस्ताक्षर करें"],
                    "notes": "आधार/पैन, पते का प्रमाण और आय प्रमाण संलग्न करें। * के साथ चिह्नित सभी फ़ील्ड अनिवार्य हैं।"
                }},
                "kn": {{
                    "summary": "ಇದು ವೈಯಕ್ತಿಕ ಮತ್ತು ಆರ್ಥಿಕ ವಿವರಗಳನ್ನು ಕೋರುವ ಸಾಲದ ಅರ್ಜಿ ನಮೂನೆಯಾಗಿದೆ.",
                    "required_info": ["ಹೆಸರು ಮತ್ತು ವಿಳಾಸ", "ಮಾಸಿಕ ಆದಾಯ", "ಸಾಲದ ಮೊತ್ತ", "ಸಾಲದ ಉದ್ದೇಶ", "ಮರುಪಾವತಿ ಅವಧಿ"],
                    "instructions": ["ವೈಯಕ್ತಿಕ ವಿವರಗಳನ್ನು ದೊಡ್ಡ ಅಕ್ಷರಗಳಲ್ಲಿ ಭರ್ತಿ ಮಾಡಿ", "ನಿಖರವಾದ ಆದಾಯವನ್ನು ಒದಗಿಸಿ", "ಸಾಲದ ಉದ್ದೇಶವನ್ನು ಸ್ಪಷ್ಟವಾಗಿ ತಿಳಿಸಿ", "ಬ್ಯಾಂಕ್ ವಿವರಗಳನ್ನು ಸೇರಿಸಿ", "ಫಾರ್ಮ್‌ಗೆ ಸಹಿ ಮಾಡಿ"],
                    "notes": "ಆಧಾರ್/ಪ್ಯಾನ್, ವಿಳಾಸದ ಪ್ರಮಾಣಪತ್ರ ಮತ್ತು ಆದಾಯದ ಪ್ರಮಾಣಪತ್ರವನ್ನು ಲಗತ್ತಿಸಿ. * ಗುರುತಿನ ಎಲ್ಲಾ ಕ್ಷೇತ್ರಗಳು ಕಡ್ಡಾಯವಾಗಿವೆ."
                }}
            }}
            """
        )

        prompt = prompt_template.format(
            content=content[:1000],
            document_type=document_type,
            language={'en': 'English', 'hi': 'Hindi', 'kn': 'Kannada'}[language]
        )

        try:
            logger.debug(f"Sending prompt to Gemini: {prompt[:200]}...")
            response = llm.invoke(prompt)
            logger.debug(f"Raw Gemini response: {response.content}")

            response_content = response.content.strip()
            response_content = re.sub(r'^```json\s*|\s*```$', '', response_content).strip()
            logger.debug(f"Cleaned Gemini response: {response_content}")

            analysis = json.loads(response_content)
            if not isinstance(analysis, dict) or not all(lang in analysis for lang in ['en', 'hi', 'kn']):
                logger.error("Invalid analysis response format")
                return jsonify({"error": "Invalid analysis response"}), 500

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Error parsing Gemini response: {str(e)}")
            return jsonify({"error": "Failed to parse analysis response"}), 500
        except Exception as e:
            logger.error(f"Gemini query error: {str(e)}")
            return jsonify({"error": f"Analysis error: {str(e)}"}), 500

        return jsonify({"analysis": analysis}), 200

    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/financial_assistant')
def financial_assistant():
    lang = request.args.get('lang', 'en')
    return render_template('financial_assistant.html', lang=lang)

@app.route('/financial_assistant', methods=['POST'])
def financial_assistant_post():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        required_fields = ['query', 'language']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"Missing or empty field: {field}"}), 400

        query = data['query'].strip()
        language = data['language'].strip().lower()

        valid_languages = ['en', 'hi', 'kn']
        if language not in valid_languages:
            logger.warning(f"Invalid language '{language}', defaulting to 'en'")
            language = 'en'

        language_names = {'en': 'English', 'hi': 'Hindi', 'kn': 'Kannada'}
        language_name = language_names[language]

        prompt_template = PromptTemplate(
            input_variables=["query", "language_name"],
            template=""" 
            You are a financial assistant for users in India. Provide a clear and concise answer to the following finance or loan-related question. The answer must be in {language_name} and tailored to the Indian context (e.g., referencing Indian banks, government schemes, or financial regulations). Limit the response to 3-5 sentences for brevity.

            Question: {query}

            Instructions:
            - Answer in {language_name}, using simple and clear language.
            - Focus on practical advice or information relevant to finance or loans in India.
            - If the question is too vague or unrelated to finance/loans, return a polite message indicating the need for a more specific finance-related question.
            - Do not include markdown, code fences, or additional text—only the plain text response.
            - dont use any special symbols like *

            Example (for English):
            To apply for a microloan, visit a local bank like State Bank of India or a microfinance institution like Bandhan Bank. Ensure you meet eligibility criteria, such as a minimum monthly income of ₹5,000 and no recent loan defaults. Submit documents like Aadhaar, income proof, and address proof. Check government schemes like PMMY for subsidized loans.
            """
        )

        prompt = prompt_template.format(
            query=query,
            language_name=language_name
        )

        try:
            logger.debug(f"Sending prompt to Gemini: {prompt[:200]}...")
            response = llm.invoke(prompt)
            logger.debug(f"Gemini response: {response.content}")

            answer = response.content.strip()
            if not answer:
                logger.warning("Empty response from Gemini")
                answer = "No answer found."

        except Exception as e:
            logger.error(f"Gemini query error: {str(e)}")
            answer = "Error processing query. Please try again later."

        return jsonify({"response": answer}), 200

    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

# Chatbot Routes
@app.route('/chatbot')
def chatbot():
    try:
        lang = request.args.get('lang', 'en')
        return render_template('chatbot.html', lang=lang)
    except Exception as e:
        logger.error(f"Error rendering chatbot page: {e}")
        return jsonify({"error": "Failed to load the chatbot page"}), 500

@app.route('/chat', methods=['POST'])
def chat():
    try:
        if not request.is_json:
            raise BadRequest("Request must be JSON")
        data = request.json
        user_input = data.get('message')
        language = data.get('language', 'en-US')
        context = data.get('context', 'general')
        if not user_input or not isinstance(user_input, str) or not user_input.strip():
            raise BadRequest("Invalid or empty message")

        valid_languages = ['en-US', 'hi-IN', 'kn-IN', 'ta-IN', 'te-IN']
        if language not in valid_languages:
            logger.warning(f"Invalid language '{language}', defaulting to 'en-US'")
            language = 'en-US'

        valid_contexts = ['general', 'ATM assistance', 'locker assistance']
        if context not in valid_contexts:
            logger.warning(f"Invalid context '{context}', defaulting to 'general'")
            context = 'general'

        system_instruction = language_instructions.get(language, language_instructions['en-US']).get(context, language_instructions['en-US']['general'])

        prompt_template = PromptTemplate(
            input_variables=["system_instruction", "user_input"],
            template=""" 
            {system_instruction}

            User Input: {user_input}

            Instructions:
            - Respond in the language specified by the system instruction.
            - Provide a detailed and helpful response tailored to the user's query.
            - Keep responses concise, limited to 3-5 sentences for general queries, or step-by-step instructions for ATM or locker assistance.
            - Do not include markdown, code fences, or additional text—only the plain text response.
            - Avoid using special symbols like * or - for lists; use numbered steps (e.g., 1. Step one) for ATM or locker instructions.
            """
        )

        prompt = prompt_template.format(
            system_instruction=system_instruction,
            user_input=user_input
        )

        try:
            logger.debug(f"Sending prompt to Gemini: {prompt[:200]}...")
            response = llm.invoke(prompt)
            logger.debug(f"Gemini response: {response.content}")

            bot_response = response.content.strip()
            if not bot_response:
                logger.warning("Empty response from Gemini")
                bot_response = "No answer found."

        except Exception as e:
            logger.error(f"Gemini query error: {str(e)}")
            bot_response = "Error processing query. Please try again later."

        return jsonify({'response': bot_response}), 200

    except BadRequest as e:
        logger.warning(f"Bad request: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Server error in chat route: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/insurance')
def insurance():
    lang = request.args.get('lang', 'en')
    return render_template('insurance.html', lang=lang)

@app.route('/find_insurance', methods=['POST'])
def find_insurance():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        required_fields = ['location', 'district', 'state']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"Missing or empty field: {field}"}), 400

        location = data['location'].strip().title()
        district = data['district'].strip().title()
        state = data['state'].strip().title()

        prompt_template = PromptTemplate(
            input_variables=["location", "district", "state"],
            template=""" 
            You are an insurance schemes assistant for India. Based on the provided location details, generate a list of insurance schemes available in the specified area. Include both national insurance schemes (applicable to all states) and state- or district-specific insurance schemes relevant to the given location, focusing on options suitable for rural communities (e.g., crop insurance, health insurance, livestock insurance).

            Location Details:
            - Village/Town: {location}
            - District: {district}
            - State: {state}

            Instructions:
            - Generate at least 3-5 insurance schemes, including:
              - National schemes (e.g., PMFBY, Ayushman Bharat) if applicable.
              - State-specific insurance schemes for {state} (e.g., schemes by the {state} government or local insurers).
              - District-specific insurance schemes for {district} if available.
            - Each scheme must include:
              - name: The scheme's name.
              - description: A brief description (2-3 sentences).
              - eligibility: Who can apply (e.g., farmers, rural households, small business owners).
              - link: A realistic URL for more information (e.g., official government or insurance provider website).
              - states: List of applicable states (include 'All' for national schemes, or specific states like '{state}').
              - districts: List of applicable districts (include 'All' for state/national schemes, or specific districts like '{district}').
              - launch_date: The scheme's launch date in YYYY-MM-DD format (use recent dates for new schemes, e.g., 2023 or 2024).
            - Return a JSON array of insurance scheme objects, sorted by launch_date (newest first).
            - If no specific schemes are known for the district, include national and state schemes and note any limitations.
            - Do not include any additional text, markdown, or explanations—only the JSON array.
            - Ensure the JSON is valid and properly formatted.

            Example Output:
            [
                {{
                    "name": "Pradhan Mantri Fasal Bima Yojana",
                    "description": "Provides crop insurance to farmers against natural calamities and crop losses.",
                    "eligibility": "Farmers growing notified crops in the scheme area.",
                    "link": "https://pmfby.gov.in",
                    "states": ["All"],
                    "districts": ["All"],
                    "launch_date": "2016-01-13"
                }},
                {{
                    "name": "Karnataka Farmer Health Insurance",
                    "description": "Offers health insurance coverage for farmers in Karnataka, including hospitalization and medical expenses.",
                    "eligibility": "Registered farmers in Karnataka.",
                    "link": "https://karnataka.gov.in",
                    "states": ["Karnataka"],
                    "districts": ["All"],
                    "launch_date": "2023-06-01"
                }}
            ]
            """
        )

        prompt = prompt_template.format(
            location=location,
            district=district,
            state=state
        )

        try:
            logger.debug(f"Sending prompt to Gemini for insurance: {prompt[:200]}...")
            response = llm.invoke(prompt)
            logger.debug(f"Raw Gemini response: {response.content}")

            response_content = response.content.strip()
            response_content = re.sub(r'^```json\s*|\s*```$', '', response_content).strip()
            logger.debug(f"Cleaned Gemini response: {response_content}")

            insurance = json.loads(response_content)
            if not isinstance(insurance, list):
                logger.error("Gemini response is not a list")
                insurance = []

            required_fields = ['name', 'description', 'eligibility', 'link', 'states', 'districts', 'launch_date']
            valid_insurance = []
            for scheme in insurance:
                if isinstance(scheme, dict) and all(field in scheme for field in required_fields):
                    valid_insurance.append(scheme)
                else:
                    logger.warning(f"Invalid insurance scheme object: {scheme}")
            insurance = valid_insurance

            insurance.sort(key=lambda x: x['launch_date'], reverse=True)

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Error parsing Gemini response: {str(e)}")
            insurance = []
        except Exception as e:
            logger.error(f"Gemini query error: {str(e)}")
            insurance = []

        return jsonify({"insurance": insurance}), 200

    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/about')
def about():
    lang = request.args.get('lang', 'en')
    return render_template('about.html', lang=lang)

@app.route('/atm_assistance')
def atm_assistance():
    lang = request.args.get('lang', 'en')
    return render_template('atm_assistance.html', lang=lang)

@app.route('/locker')
def locker():
    lang = request.args.get('lang', 'en')
    return render_template('locker.html', lang=lang)

# Expense Tracker Routes
@app.route('/expense_tracker')
def expense_tracker():
    lang = request.args.get('lang', 'en')
    return render_template('expense_tracker.html', lang=lang)

@app.route('/upload_bill', methods=['POST'])
def upload_bill():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files['file']
        bill_type = request.form.get('bill_type', 'other').lower()
        user_id = request.form.get('user_id', 1)  # Default to 1 for demo

        if not file.filename:
            return jsonify({"error": "No file selected"}), 400

        # Validate file type
        allowed_extensions = {'pdf', 'jpg', 'jpeg', 'png'}
        if file.filename.rsplit('.', 1)[-1].lower() not in allowed_extensions:
            return jsonify({"error": "Unsupported file type. Use PDF, JPG, or PNG."}), 400

        # Save file
        upload_folder = 'uploads/bills'
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
        file.save(file_path)

        # Extract content
        content = ""
        if file.filename.endswith('.pdf'):
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text = page.extract_text()
                content += text or ""
        elif file.filename.endswith(('.jpg', '.jpeg', '.png')):
            content = f"Sample {bill_type} bill content extracted from image."

        if not content.strip():
            content = f"Placeholder content for {bill_type} bill in rural India."

        # Use Gemini to extract only the amount
        prompt_template = PromptTemplate(
            input_variables=["content", "bill_type"],
            template=""" 
            You are a bill analysis assistant for rural Indian households. Extract only the total bill amount from the provided {bill_type} bill content, focusing on typical bill formats in India.

            Content:
            {content}

            Instructions:
            - Extract the following field:
              - amount: Total bill amount in INR (numeric, e.g., 1500.50).
            - Return a JSON object with only the 'amount' field.
            - If the amount is not found, return {"amount": 0.0}.
            - Do not include markdown, explanations, or extra text—only the JSON object.

            Example Output:
            {{
                "amount": 1500.50
            }}
            """
        )

        prompt = prompt_template.format(content=content[:1000], bill_type=bill_type)
        try:
            response = llm.invoke(prompt)
            response_content = re.sub(r'^```json\s*|\s*```$', '', response.content).strip()
            extracted_data = json.loads(response_content)
            amount = extracted_data.get('amount', 0.0)
        except Exception as e:
            logger.error(f"Gemini extraction error: {str(e)}")
            amount = 0.0

        # Store in SQLite
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('''
            INSERT INTO bills (user_id, bill_type, amount, bill_date, file_path)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            user_id,
            bill_type,
            amount,
            datetime.now().strftime('%Y-%m-%d'),
            file_path
        ))
        conn.commit()
        bill_id = c.lastrowid
        conn.close()

        return jsonify({"message": "Bill uploaded successfully", "bill_id": bill_id}), 200

    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/add_manual_bill', methods=['POST'])
def add_manual_bill():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        bill_type = data.get('bill_type', 'other').lower()
        amount = data.get('amount')
        bill_date = data.get('bill_date')
        user_id = data.get('user_id', 1)  # Default to 1 for demo

        # Validate inputs
        try:
            amount = float(amount)
            if amount <= 0:
                return jsonify({"error": "Amount must be a positive number"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid amount"}), 400

        if not bill_date:
            bill_date = datetime.now().strftime('%Y-%m-%d')
        else:
            try:
                datetime.strptime(bill_date, '%Y-%m-%d')
            except ValueError:
                return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

        # Store in SQLite
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('''
            INSERT INTO bills (user_id, bill_type, amount, bill_date, file_path)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, bill_type, amount, bill_date, None))
        conn.commit()
        bill_id = c.lastrowid
        conn.close()

        return jsonify({"message": "Manual bill added successfully", "bill_id": bill_id}), 200

    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/analyze_bills', methods=['POST'])
def analyze_bills():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        bill_type = data.get('bill_type', 'all').lower()
        user_id = data.get('user_id', 1)  # Default to 1 for demo

        # Fetch bills from SQLite
        conn = sqlite3.connect('users.db')
        c = conn.cursor()

        if bill_type == 'all':
            # Fetch all bills for the user
            c.execute('''
                SELECT bill_type, amount, bill_date
                FROM bills
                WHERE user_id = ?
                ORDER BY bill_date ASC
            ''', (user_id,))
        else:
            # Fetch bills for the specified type
            c.execute('''
                SELECT bill_type, amount, bill_date
                FROM bills
                WHERE user_id = ? AND LOWER(bill_type) = ?
                ORDER BY bill_date ASC
            ''', (user_id, bill_type))
        bills = c.fetchall()

        # Fetch all bills for category-wise analysis
        c.execute('''
            SELECT bill_type, amount
            FROM bills
            WHERE user_id = ?
            GROUP BY bill_type
        ''', (user_id,))
        all_bills = c.fetchall()
        conn.close()

        if not bills:
            return jsonify({"error": "No bills found"}), 404

        # Group bills by bill_type for analysis
        bills_by_type = {}
        for bill in bills:
            bt, amount, bill_date = bill
            if bt not in bills_by_type:
                bills_by_type[bt] = []
            bills_by_type[bt].append((amount, bill_date))

        # Analyze each bill type
        analysis_by_type = {}
        for bt, bill_data in bills_by_type.items():
            amounts = [data[0] for data in bill_data]
            dates = [datetime.strptime(data[1], '%Y-%m-%d') for data in bill_data]

            # Statistical analysis
            monthly_avg = np.mean(amounts) if amounts else 0
            peak_months = []
            monthly_sums = {}
            if dates and amounts:
                for date, amount in zip(dates, amounts):
                    month_key = date.strftime('%Y-%m')
                    monthly_sums[month_key] = monthly_sums.get(month_key, 0) + amount
                sorted_months = sorted(monthly_sums.items(), key=lambda x: x[1], reverse=True)[:3]
                peak_months = [f"{month} (₹{amount:.2f})" for month, amount in sorted_months]

            # Future bill prediction (weighted moving average)
            future_prediction = monthly_avg
            if len(amounts) > 3:
                weights = np.array([0.2, 0.3, 0.5])
                recent_amounts = amounts[-3:]
                future_prediction = np.average(recent_amounts, weights=weights) * 1.05

            # Savings tips
            savings_tips = []
            if bt == 'electricity' and monthly_avg > 1000:
                savings_tips.append("Your electricity bills are high. Use LED bulbs or solar lanterns to reduce costs.")
            elif bt == 'water' and max(amounts) > np.mean(amounts) * 2:
                savings_tips.append("Unusually high water bill detected. Check for leaks or use rainwater harvesting.")
            else:
                savings_tips.append(f"Track your {bt} bills regularly to identify saving opportunities.")

            analysis_by_type[bt] = {
                "monthly_average": round(monthly_avg, 2),
                "peak_months": peak_months,
                "future_prediction": round(future_prediction, 2),
                "savings_tips": savings_tips,
                "total_bills": len(amounts),
                "trend": {
                    "labels": [date.strftime('%Y-%m') for date in dates],
                    "amounts": amounts
                }
            }

        # Category-wise spending for pie chart
        category_sums = {bill_type: sum(amount for bt, amount in all_bills if bt == bill_type) for bill_type, _ in all_bills}
        category_labels = list(category_sums.keys())
        category_values = list(category_sums.values())

        # Prepare graph data
        graph_data = {
            "category": {
                "labels": category_labels,
                "amounts": category_values
            }
        }

        analysis = {
            "by_type": analysis_by_type,
            "graph_data": graph_data,
            "total_bills": len(bills)
        }

        return jsonify({"analysis": analysis}), 200

    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

# Sign Up and Login Routes
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Username and password are required.', 'error')
            return redirect(url_for('signup'))

        try:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
            conn.commit()
            conn.close()
            flash('Sign up successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists.', 'error')
            return redirect(url_for('signup'))
        except Exception as e:
            logger.error(f"Error during signup: {str(e)}")
            flash('An error occurred. Please try again.', 'error')
            return redirect(url_for('signup'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Username and password are required.', 'error')
            return redirect(url_for('login'))

        try:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT id FROM users WHERE username = ? AND password = ?', (username, password))
            user = c.fetchone()
            conn.close()

            if user:
                session['user_id'] = user[0]
                flash('Login successful!', 'success')
                return redirect(url_for('index'))
            else:
                flash('Invalid username or password.', 'error')
                return redirect(url_for('login'))
        except Exception as e:
            logger.error(f"Error during login: {str(e)}")
            flash('An error occurred. Please try again.', 'error')
            return redirect(url_for('login'))

    return render_template('login.html')


# Weather Advisory Route
@app.route('/weather_advisory')
def weather_advisory():
    lang = request.args.get('lang', 'en')
    return render_template('weather_advisory.html', lang=lang)

@app.route('/weather_advisory_data', methods=['POST'])
def weather_advisory_data():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        required_fields = ['location', 'district', 'state']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"Missing or empty field: {field}"}), 400

        location = data['location'].strip().title()
        district = data['district'].strip().title()
        state = data['state'].strip().title()

        # Generate dates for the forecast
        today = datetime.now()
        daily_dates = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1, 3)]  # Next 2 days
        weekly_dates = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1, 8)]  # Next 7 days

        prompt_template = PromptTemplate(
            input_variables=["location", "district", "state", "daily_dates", "weekly_dates"],
            template=""" 
            You are a weather and agricultural advisory assistant for rural India. Based on the provided location details, generate weather forecasts and agricultural tips for farmers. The current date is {today}.

            Location Details:
            - Village/Town: {location}
            - District: {district}
            - State: {state}

            Instructions:
            - Provide a weather forecast for the specified location, including:
              - Daily forecast for the next 2 days ({daily_dates}).
              - Weekly forecast for the next 7 days ({weekly_dates}).
              - Agricultural tips based on the weather conditions.
              - Weather alerts for any extreme conditions (e.g., heavy rain, drought).
            - Each daily forecast entry must include:
              - date: The date in YYYY-MM-DD format.
              - condition: Weather condition (e.g., Sunny, Rainy, Cloudy).
              - temperature: Temperature in Celsius (e.g., 28).
              - humidity: Humidity percentage (e.g., 70).
              - icon: A Font Awesome icon name (e.g., sun, cloud-rain, cloud) for the condition.
            - Each weekly forecast entry must include:
              - date: The date in YYYY-MM-DD format.
              - condition: Weather condition.
              - min_temp: Minimum temperature in Celsius.
              - max_temp: Maximum temperature in Celsius.
              - icon: A Font Awesome icon name for the condition.
            - Agricultural tips:
              - Provide 3-5 practical tips for farmers based on the weather forecast (e.g., irrigation advice, crop protection).
              - Return as a list of strings.
            - Weather alerts:
              - If there are extreme weather conditions (e.g., heavy rain, heatwave), provide a brief alert message.
              - If no alerts, return a message indicating no extreme weather.
            - Return a JSON object with:
              - daily_forecast: Array of daily forecast objects.
              - weekly_forecast: Array of weekly forecast objects.
              - agricultural_tips: Array of tip strings.
              - weather_alerts: A string with the alert message or a message indicating no alerts.
            - Ensure the JSON is valid and properly formatted.
            - Do not include any additional text, markdown, or explanations—only the JSON object.

            Example Output:
            {{
                "daily_forecast": [
                    {{
                        "date": "2025-05-12",
                        "condition": "Sunny",
                        "temperature": 30,
                        "humidity": 65,
                        "icon": "sun"
                    }},
                    {{
                        "date": "2025-05-13",
                        "condition": "Rainy",
                        "temperature": 26,
                        "humidity": 80,
                        "icon": "cloud-rain"
                    }}
                ],
                "weekly_forecast": [
                    {{
                        "date": "2025-05-12",
                        "condition": "Sunny",
                        "min_temp": 22,
                        "max_temp": 30,
                        "icon": "sun"
                    }},
                    {{
                        "date": "2025-05-13",
                        "condition": "Rainy",
                        "min_temp": 20,
                        "max_temp": 26,
                        "icon": "cloud-rain"
                    }}
                ],
                "agricultural_tips": [
                    "Ensure proper irrigation as the weather will be sunny.",
                    "Prepare for rain by protecting crops with covers."
                ],
                "weather_alerts": "No extreme weather alerts at this time."
            }}
            """
        )

        prompt = prompt_template.format(
            location=location,
            district=district,
            state=state,
            daily_dates=", ".join(daily_dates),
            weekly_dates=", ".join(weekly_dates),
            today=today.strftime('%Y-%m-%d')
        )

        try:
            logger.debug(f"Sending prompt to Gemini for weather: {prompt[:200]}...")
            response = llm.invoke(prompt)
            logger.debug(f"Raw Gemini response: {response.content}")

            response_content = response.content.strip()
            response_content = re.sub(r'^```json\s*|\s*```$', '', response_content).strip()
            logger.debug(f"Cleaned Gemini response: {response_content}")

            weather_data = json.loads(response_content)
            if not isinstance(weather_data, dict) or 'daily_forecast' not in weather_data or 'weekly_forecast' not in weather_data:
                logger.error("Invalid response format from Gemini")
                return jsonify({"error": "Invalid weather data format"}), 500

            # Validate daily forecast
            required_daily_fields = ['date', 'condition', 'temperature', 'humidity', 'icon']
            valid_daily = []
            for day in weather_data['daily_forecast']:
                if isinstance(day, dict) and all(field in day for field in required_daily_fields):
                    valid_daily.append(day)
                else:
                    logger.warning(f"Invalid daily forecast object: {day}")
            weather_data['daily_forecast'] = valid_daily

            # Validate weekly forecast
            required_weekly_fields = ['date', 'condition', 'min_temp', 'max_temp', 'icon']
            valid_weekly = []
            for day in weather_data['weekly_forecast']:
                if isinstance(day, dict) and all(field in day for field in required_weekly_fields):
                    valid_weekly.append(day)
                else:
                    logger.warning(f"Invalid weekly forecast object: {day}")
            weather_data['weekly_forecast'] = valid_weekly

            # Ensure agricultural tips and alerts are present
            if 'agricultural_tips' not in weather_data or not isinstance(weather_data['agricultural_tips'], list):
                weather_data['agricultural_tips'] = ["No agricultural tips available."]
            if 'weather_alerts' not in weather_data or not isinstance(weather_data['weather_alerts'], str):
                weather_data['weather_alerts'] = "No weather alerts available."

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Error parsing Gemini response: {str(e)}")
            return jsonify({"error": "Failed to parse weather data"}), 500
        except Exception as e:
            logger.error(f"Gemini query error: {str(e)}")
            return jsonify({"error": f"Server error: {str(e)}"}), 500

        return jsonify(weather_data), 200

    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)