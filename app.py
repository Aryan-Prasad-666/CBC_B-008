from flask import Flask, render_template, request, jsonify
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from dotenv import load_dotenv
import os
import json
import requests

load_dotenv()

app = Flask(__name__)

# Initialize API keys
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY environment variable not set")

# Use Gemini 2.0 Flash
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=GEMINI_API_KEY)

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

        # Use .invoke() instead of calling directly
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

        # Form full address
        address = f"{data['location']}, {data['district']}, {data['state']}, India"

        # Geocode address to get coordinates
        geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={GOOGLE_API_KEY}"
        geocode_response = requests.get(geocode_url)
        geocode_data = geocode_response.json()

        if geocode_data['status'] != 'OK' or not geocode_data['results']:
            return jsonify({
                "error": "Unable to geocode address",
                "banks": [],
                "center": {"lat": 12.9716, "lng": 77.5946}  # Default to Bengaluru
            }), 400

        location = geocode_data['results'][0]['geometry']['location']
        lat, lng = location['lat'], location['lng']

        # Find nearby banks using Google Places API
        places_url = (
            f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?"
            f"location={lat},{lng}&radius=10000&type=bank&key={GOOGLE_API_KEY}"
        )
        places_response = requests.get(places_url)
        places_data = places_response.json()

        if places_data['status'] != 'OK':
            # Fallback to mock data if API fails
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
        for place in places_data['results'][:5]:  # Limit to 5 banks
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

if __name__ == '__main__':
    app.run(debug=True)