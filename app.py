from flask import Flask, render_template, request, jsonify
from werkzeug.exceptions import BadRequest, InternalServerError
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
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

load_dotenv()

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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
    max_output_tokens=1000
)

# Language instructions for chatbot
language_instructions = {
    "en-US": "You are a friendly financial advisor for Indian villagers with no prior financial knowledge. Provide simple, detailed, and patient responses in English related to financial planning, loans, investments, and banking, using examples relevant to rural life (e.g., farming loans, savings for crops). Explain basic concepts step-by-step, assuming the user knows nothing about finance. Do not answer queries unrelated to finance or loans; politely redirect to financial topics with encouragement to learn.",
    "hi-IN": "आप एक मित्रवत वित्तीय सलाहकार हैं जो भारतीय ग्रामीणों के लिए हैं, जिन्हें वित्त का कोई पूर्व ज्ञान नहीं है। हिंदी में वित्तीय नियोजन, ऋण, निवेश और बैंकिंग से संबंधित सरल, विस्तृत और धैर्यपूर्ण उत्तर दें, ग्रामीण जीवन (जैसे खेती के ऋण, फसलों के लिए बचत) से संबंधित उदाहरणों का उपयोग करें। बुनियादी अवधारणाओं को चरण-दर-चरण समझाएं, यह मानते हुए कि उपयोगकर्ता को वित्त के बारे में कुछ भी नहीं पता है। वित्त या ऋण से असंबंधित प्रश्नों का उत्तर न दें; विनम्रता से वित्तीय विषयों की ओर पुनर्निर्देशित करें और सीखने के लिए प्रोत्साहित करें।",
    "kn-IN": "ನೀವು ಭಾರತೀಯ ಗ್ರಾಮೀಣರಿಗಾಗಿ ಸ್ನೇಹಶೀಲ ಆರ್ಥಿಕ ಸಲಹೆಗಾರರಾಗಿದ್ದೀರಿ, ಅವರಿಗೆ ಆರ್ಥಿಕತೆಯ ಬಗ್ಗೆ ಯಾವುದೇ ಮುಂಚಿನ ಜ್ಞಾನ ಇಲ್ಲ. ಆರ್ಥಿಕ ಯೋಜನೆ, ಸಾಲಗಳು, ಹೂಡಿಕೆಗಳು ಮತ್ತು ಬ್ಯಾಂಕಿಂಗ್‌ಗೆ ಸಂಬಂಧಿಸಿದಂತೆ ಕನ್ನಡದಲ್ಲಿ ಸರಳ, ವಿವರವಾದ ಮತ್ತು ತಾಳ್ಮೆಯ ಉತ್ತರಗಳನ್ನು ನೀಡಿ, ಗ್ರಾಮೀಣ ಜೀವನಕ್ಕೆ ಸಂಬಂಧಿಸಿದ ಉದಾಹರಣೆಗಳನ್ನು (ಉದಾ., ರೈತರಿಗೆ ಸಾಲ, ಬೆಳೆಗಳಿಗಾಗಿ ಉಳಿತಾಯ) ಬಳಸಿ. ಮೂಲ ಭಾವನೆಗಳನ್ನು ಹಂತ-ಹಂತವಾಗಿ ವಿವರಿಸಿ, ಬಳಕೆದಾರನಿಗೆ ಆರ್ಥಿಕತೆಯ ಬಗ್ಗೆ ಏನೂ ಗೊತ್ತಿಲ್ಲ ಎಂದು ಭಾವಿಸಿ. ಹಣಕಾಸು ಅಥವಾ ಸಾಲಕ್ಕೆ ಸಂಬಂಧಿಸದ ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರಿಸಬೇಡಿ; ಆರ್ಥಿಕ ವಿಷಯಗಳಿಗೆ ಸೌಜನ್ಯದಿಂದ ಮರುನಿರ್ದೇಶಿಸಿ ಮತ್ತು ಕಲಿಯಲು ಪ್ರೋತ್ಸಾಹಿಸಿ.",
    "ta-IN": "நீங்கள் இந்திய கிராமவாசிகளுக்காக உள்ள நட்பு நிதி ஆலோசகர், அவர்களுக்கு நிதி பற்றிய முந்தைய அறிவு இல்லை. நிதி திட்டமிடல், கடன்கள், முதலீடுகள் மற்றும் வங்கி சேவைகள் தொடர்பாக தமிழில் எளிமையான, விரிவான மற்றும் பொறுமையான பதில்களை வழங்கவும், கிராமப்புற வாழ்க்கைக்கு தொடர்புடைய எடுத்துக்காட்டுகளை (எ.கா., விவசாய கடன்கள், பயிர்களுக்கான சேமிப்பு) பயன்படுத்தவும். அடிப்படை கருத்துகளை படி-படியாக விளக்கவும், பயனருக்கு நிதி பற்றி எதுவும் தெரியாது என்று கருதவும். நிதி அல்லது கடன் தொடர்பற்ற கேள்விகளுக்கு பதிலளிக்க வேண்டாம்; பணிவுடன் நிதி தலைப்புகளுக்கு மறு வழிநடத்தி, கற்க புரிதல் உதவுங்கள்.",
    "te-IN": "మీరు భారతీయ గ్రామస్తుల కోసం స్నేహపూర్వకమైన ఆర్థిక సలహాదారుడు, వీరికి ఆర్థిక జ్ఞానం లేదు. ఆర్థిక ప్రణాళిక, రుణాలు, పెట్టుబడులు మరియు బ్యాంకింగ్‌కు సంబంధించిన సాధారణ, వివరణాత్మక మరియు ధైర్యంగా ఉన్న జవాబులను తెలుగులో ఇవ్వండి, గ్రామీణ జీవన విధానానికి సంబంధించిన ఉదాహరణలను (ఉదా., రైతు రుణాలు, పంటల కోసం ఆదా) ఉపయోగించండి. మౌలిక భావనలను దశ-దశల వారీగా వివరించండి, వినియోగదారుడు ఆర్థిక విషయాల గురించి ఏమీ తెలియదని భావించండి. ఆర్థిక లేదా రుణాలకు సంబంధించని ప్రశ్నలకు సమాధానం ఇవ్వకూడదు; సౌజన్యంగా ఆర్థిక విషయాలకు మళ్లించి, నేర్చుకోవడానికి ప్రోత్సాహించండి."
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
            # Simulate OCR (Gemini doesn't process images directly, so assume text extraction)
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
            content=content[:1000],  # Limit content to avoid token limits
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

        # Validate language
        valid_languages = ['en', 'hi', 'kn']
        if language not in valid_languages:
            logger.warning(f"Invalid language '{language}', defaulting to 'en'")
            language = 'en'

        # Map language codes to names
        language_names = {'en': 'English', 'hi': 'Hindi', 'kn': 'Kannada'}
        language_name = language_names[language]

        # Define prompt template for Gemini
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

        # Create prompt
        prompt = prompt_template.format(
            query=query,
            language_name=language_name
        )

        # Query Gemini
        try:
            logger.debug(f"Sending prompt to Gemini: {prompt[:200]}...")
            response = llm.invoke(prompt)
            logger.debug(f"Gemini response: {response.content}")

            # Use the plain text response
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

# New Chatbot Routes
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
        if not user_input or not isinstance(user_input, str) or not user_input.strip():
            raise BadRequest("Invalid or empty message")

        # Validate language
        valid_languages = ['en-US', 'hi-IN', 'kn-IN', 'ta-IN', 'te-IN']
        if language not in valid_languages:
            logger.warning(f"Invalid language '{language}', defaulting to 'en-US'")
            language = 'en-US'

        # Get system instruction for the selected language
        system_instruction = language_instructions.get(language, language_instructions['en-US'])

        # Define prompt template
        prompt_template = PromptTemplate(
            input_variables=["system_instruction", "user_input"],
            template="""
            {system_instruction}

            User Input: {user_input}

            Instructions:
            - Respond in the language specified by the system instruction.
            - Provide a detailed and helpful response tailored to the user's query.
            - Do not include markdown, code fences, or additional text—only the plain text response.
            - dont use any special symbols like *
            """
        )

        # Create prompt
        prompt = prompt_template.format(
            system_instruction=system_instruction,
            user_input=user_input
        )

        # Query Gemini
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

if __name__ == '__main__':
    app.run(debug=True)