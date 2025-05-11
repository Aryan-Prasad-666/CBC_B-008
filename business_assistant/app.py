from flask import Flask, request, jsonify, render_template
import sqlite3
import google.generativeai as genai
from dotenv import load_dotenv
import os
import re
import json
from datetime import datetime

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DB_PATH = os.getenv("SQLITE_DB_PATH", "database.db")

# Configure Gemini API
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

app = Flask(__name__, template_folder="templates")

def get_table_schema():
    """Extract and return database schema."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    schema = {}
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        for table in tables:
            table_name = table[0]
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            schema[table_name] = [
                {"name": col[1], "type": col[2], "primary_key": bool(col[5]), "not_null": bool(col[3])}
                for col in columns
            ]
    except sqlite3.Error as e:
        print(f"Error getting schema: {e}")
    finally:
        conn.close()
    
    return schema

def check_customer_exists(name):
    """Check if a customer with the given name already exists (case-insensitive)."""
    if not name:
        return None
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id FROM customers WHERE LOWER(name) = LOWER(?)", (name,))
        result = cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error as e:
        print(f"Error checking customer existence: {e}")
        return None
    finally:
        conn.close()

def get_or_create_customer(name, phone=None):
    """Get customer ID or create a new customer if not exists, storing name in lowercase."""
    if not name:
        return None
    
    customer_id = check_customer_exists(name)
    
    if customer_id:
        return customer_id
    
    # Validate and clean phone number
    valid, result = validate_phone_number(phone)
    if not valid:
        print(f"Phone number validation error: {result}")
        return None, result
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        lowercase_name = name.lower()
        cursor.execute("INSERT INTO customers (name, phone) VALUES (?, ?)", (lowercase_name, phone or ""))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        print(f"Error creating customer: {e}")
        return None, [f"Database error creating customer: {str(e)}"]
    finally:
        conn.close()

def update_customer_phone(customer_name, phone):
    """Update the phone number for a customer."""
    # Validate and clean phone number
    valid, result = validate_phone_number(phone)
    if not valid:
        return None, result
    
    customer_id = check_customer_exists(customer_name)
    if not customer_id:
        return None, [f"Customer '{customer_name}' does not exist."]
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("UPDATE customers SET phone = ? WHERE id = ?", (result or "", customer_id))
        conn.commit()
        affected_rows = cursor.rowcount
        if affected_rows == 0:
            return None, ["No changes made to customer phone number."]
        return customer_id, None
    except sqlite3.Error as e:
        return None, [f"Database error updating phone number: {str(e)}"]
    finally:
        conn.close()

def check_stock_exists(product_name):
    """Check if a stock item with the given product name already exists (case-insensitive)."""
    if not product_name:
        return None
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id FROM stocks WHERE LOWER(product_name) = LOWER(?)", (product_name,))
        result = cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error as e:
        print(f"Error checking stock existence: {e}")
        return None
    finally:
        conn.close()

def get_stock_details(stock_id):
    """Get stock details by ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT product_name, quantity, price FROM stocks WHERE id = ?", (stock_id,))
        return cursor.fetchone()
    except sqlite3.Error as e:
        print(f"Error getting stock details: {e}")
        return None
    finally:
        conn.close()

def validate_phone_number(phone):
    """Validate phone number: only digits, up to 12 digits, ignore spaces/symbols."""
    if phone is None or phone == "":
        return True, None  # Allow empty phone numbers
    if not isinstance(phone, str):
        return False, ["Not a valid input: Phone number must be a string."]
    # Remove spaces and symbols
    cleaned_phone = ''.join(filter(str.isdigit, phone))
    if not cleaned_phone:
        return False, ["Not a valid input: Phone number must contain at least one digit."]
    if len(cleaned_phone) > 12:
        return False, ["Not a valid input: Phone number must be 12 digits or fewer."]
    return True, cleaned_phone

def validate_stock_params(product_name, price, quantity=None):
    """Validate stock parameters, ensuring name and price are provided, quantity defaults to 0."""
    errors = []
    if not product_name or not isinstance(product_name, str):
        errors.append("Product name is required and must be a string.")
    if price is None or not isinstance(price, (int, float)) or price < 0:
        errors.append("Price is required and must be a non-negative number.")
    
    if errors:
        return False, errors
    
    # Default quantity to 0 if not provided
    quantity = 0 if quantity is None else quantity
    if not isinstance(quantity, int) or quantity < 0:
        errors.append("Quantity must be a non-negative integer.")
        return False, errors
    
    return True, {"product_name": product_name, "price": float(price), "quantity": quantity}

def add_stock_item(product_name, price, quantity=None):
    """Add a new stock item with strict validation, defaulting quantity to 0 if not provided."""
    # Check if stock item already exists (case-insensitive)
    stock_id = check_stock_exists(product_name)
    if stock_id:
        return None, [f"Stock item '{product_name}' already exists with ID {stock_id}."]
    
    valid, result = validate_stock_params(product_name, price, quantity)
    if not valid:
        return None, result
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO stocks (product_name, price, quantity) VALUES (?, ?, ?)",
            (result["product_name"], result["price"], result["quantity"])
        )
        conn.commit()
        return cursor.lastrowid, None
    except sqlite3.Error as e:
        return None, [f"Database error adding stock item: {str(e)}"]
    finally:
        conn.close()

def add_bill_item(bill_id, stock_id, quantity):
    """Add an item to a bill with validation and stock checking."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Verify bill exists
        cursor.execute("SELECT id FROM bills WHERE id = ?", (bill_id,))
        if not cursor.fetchone():
            return None, [f"Bill ID {bill_id} does not exist."]
        
        # Get stock details
        stock = get_stock_details(stock_id)
        if not stock:
            return None, [f"Stock ID {stock_id} does not exist."]
        
        product_name, available_quantity, price = stock


        
        
        # Validate quantity
        if not isinstance(quantity, int) or quantity <= 0:
            return None, ["Quantity must be a positive integer."]
        if available_quantity == 0:
            return None, [f"No stock available for {product_name} (current quantity: 0)."]
        if quantity > available_quantity:
            return None, [f"Requested quantity ({quantity}) exceeds available stock ({available_quantity}) for {product_name}."]
        
        # Calculate total price
        total_price = price * quantity
        
        # Insert bill item
        cursor.execute(
            "INSERT INTO bill_items (bill_id, stock_id, quantity, total_price) VALUES (?, ?, ?, ?)",
            (bill_id, stock_id, quantity, total_price)
        )
        
        # Update stock quantity
        cursor.execute(
            "UPDATE stocks SET quantity = quantity - ? WHERE id = ?",
            (quantity, stock_id)
        )
        
        # Update bill total_amount
        cursor.execute(
            "UPDATE bills SET total_amount = total_amount + ? WHERE id = ?",
            (total_price, bill_id)
        )
        
        conn.commit()
        return cursor.lastrowid, None
    except sqlite3.Error as e:
        return None, [f"Error adding bill item: {str(e)}"]
    finally:
        conn.close()

def query_db(query, params=()):
    """Execute a SQLite query and return results with column names."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    results = []
    column_names = []
    
    try:
        cursor.execute(query, params)
        
        if query.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()
            if rows:
                column_names = [description[0] for description in cursor.description]
                results = [dict(row) for row in rows]
        else:
            conn.commit()
            affected_rows = cursor.rowcount
            results = {"affected_rows": affected_rows}
            if query.strip().upper().startswith("INSERT"):
                results["last_id"] = cursor.lastrowid
    
    except sqlite3.IntegrityError as e:
        print(f"SQLite integrity error: {e}")
        if "UNIQUE constraint failed" in str(e):
            raise Exception("Customer already exists.")
        elif "FOREIGN KEY constraint failed" in str(e):
            raise Exception("Invalid reference: The referenced customer, bill, or stock does not exist.")
        elif "NOT NULL constraint failed" in str(e):
            raise Exception(f"Missing required field: {str(e)}")
        else:
            raise Exception(f"Database integrity error: {str(e)}")
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
        raise Exception(f"Database error: {str(e)}")
    finally:
        conn.close()
    
    return {"data": results, "columns": column_names}

def is_casual_query(user_input):
    """Check if the input appears to be casual conversation rather than a database query."""
    casual_patterns = [
        r'^(hi|hello|hey|howdy|greetings|good morning|good afternoon|good evening)(\s|$)',
        r'^how are (you|u)(\s|$)',
        r'^(thanks|thank you|thx|ty)(\s|$)',
        r'^(bye|goodbye|see you|later|cya)(\s|$)',
        r'^(what\'?s up|sup)(\s|$)'
    ]
    
    for pattern in casual_patterns:
        if re.search(pattern, user_input.lower()):
            return True
    
    db_keywords = ['list', 'show', 'get', 'find', 'display', 'view', 'add', 'create', 'insert', 
                  'update', 'change', 'modify', 'delete', 'remove', 'customer', 'bill', 'stock', 
                  'payment', 'item', 'price', 'quantity', 'status', 'phone', 'name', 'amount']
    
    has_db_keyword = any(keyword in user_input.lower() for keyword in db_keywords)
    
    words = user_input.split()
    return (len(words) < 3 and not has_db_keyword) or not has_db_keyword

def handle_casual_query(user_input):
    """Generate a friendly response to casual conversation."""
    prompt = f"""
    You are a friendly database assistant for a small business management system.
    Respond to this casual input in a friendly, helpful way. Keep it concise (1-2 sentences).
    Input: {user_input}
    """
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini error for casual input: {e}")
        return "Hi there! I'm your database assistant. How can I help with your business data today?"

def extract_parameters(user_input, sql_query):
    """Extract parameters from user input based on SQL query structure."""
    params = []
    
    quoted_strings = re.findall(r'["\']([^"\']+)["\']', user_input)
    numbers = re.findall(r'\b(\d+(?:\.\d+)?)\b', user_input)
    dates = re.findall(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b', user_input)
    status_values = re.findall(r'\b(paid|unpaid|pending|delivered|canceled|completed)\b', user_input.lower())
    
    potential_params = []
    potential_params.extend([s.lower() for s in quoted_strings])
    potential_params.extend(status_values)
    
    for num in numbers:
        if '.' in num:
            potential_params.append(float(num))
        else:
            potential_params.append(int(num))
    
    for date_str in dates:
        try:
            for fmt in ['%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d', '%d-%m-%Y', '%m-%d-%Y', '%Y-%m-%d']:
                try:
                    date_obj = datetime.strptime(date_str, fmt)
                    iso_date = date_obj.strftime('%Y-%m-%d %H:%M:%S')
                    potential_params.append(iso_date)
                    break
                except ValueError:
                    continue
        except Exception as e:
            print(f"Error processing date: {e}")
            potential_params.append(date_str)
    
    param_count = sql_query.count('?')
    return potential_params[:param_count]

def preprocess_user_query(user_input):
    """Process user query to handle special cases before generating SQL."""
    bill_patterns = [
        r'create (?:a )?(?:new )?bill for customer [\'""]?([a-zA-Z0-9\s]+)[\'""]?',
        r'add (?:a )?(?:new )?bill for (?:customer )?[\'""]?([a-zA-Z0-9\s]+)[\'""]?',
        r'generate (?:a )?(?:new )?bill for [\'""]?([a-zA-Z0-9\s]+)[\'""]?',
        r'create (?:a )?(?:new )?bill for [\'""]?([a-zA-Z0-9\s]+)[\'""]?'
    ]
    
    for pattern in bill_patterns:
        match = re.search(pattern, user_input.lower())
        if match:
            customer_name = match.group(1).strip()
            return {"special_action": "create_customer_and_bill", "customer_name": customer_name}
    
    bill_item_pattern = r'add (\d+)\s*(?:units of)?\s*([a-zA-Z\s]+)\s*to bill\s*(?:id\s*)?(\d+)'
    match = re.search(bill_item_pattern, user_input.lower())
    if match:
        quantity = int(match.group(1))
        product_name = match.group(2).strip()
        bill_id = int(match.group(3))
        return {
            "special_action": "add_bill_item",
            "quantity": quantity,
            "product_name": product_name,
            "bill_id": bill_id
        }
    
    return {"special_action": None}

def generate_sql_query(user_input):
    """Use Gemini to convert natural language to SQLite query."""
    preprocess_result = preprocess_user_query(user_input)
    
    if preprocess_result["special_action"] == "create_customer_and_bill":
        customer_name = preprocess_result["customer_name"]
        customer_id = check_customer_exists(customer_name)
        
        if not customer_id:
            customer_id = get_or_create_customer(customer_name)
            if isinstance(customer_id, tuple) or not customer_id:
                return None, None, [f"Failed to create customer {customer_name}"]
        
        current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        default_status = "pending"
        default_amount = 0.0
        
        sql_query = "INSERT INTO bills (customer_id, bill_date, total_amount, payment_status) VALUES (?, ?, ?, ?)"
        params = [customer_id, current_date, default_amount, default_status]
        
        return sql_query, params, None
    
    if preprocess_result["special_action"] == "add_bill_item":
        quantity = preprocess_result["quantity"]
        product_name = preprocess_result["product_name"]
        bill_id = preprocess_result["bill_id"]
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id FROM stocks WHERE LOWER(product_name) = LOWER(?)", (product_name,))
            result = cursor.fetchone()
            if not result:
                return None, None, [f"Product '{product_name}' not found in stock."]
            stock_id = result[0]
        except sqlite3.Error as e:
            return None, None, [f"Error finding stock item: {str(e)}"]
        finally:
            conn.close()
        
        bill_item_id, error = add_bill_item(bill_id, stock_id, quantity)
        if error:
            return None, None, error
        
        return (
            "INSERT INTO bill_items (bill_id, stock_id, quantity, total_price) VALUES (?, ?, ?, ?)",
            [bill_id, stock_id, quantity, 0.0],  # total_price updated by add_bill_item
            None
        )
    
    # Handle phone number update
    phone_update_pattern = r'update (?:customer )?[\'""]?([a-zA-Z0-9\s]+)[\'""]?\s*phone\s*(?:number)?\s*to\s*([\d\s\-()+]+)'
    match = re.search(phone_update_pattern, user_input.lower())
    if match:
        customer_name = match.group(1).strip()
        phone = match.group(2).strip()
        customer_id, error = update_customer_phone(customer_name, phone)
        if error:
            return None, None, error
        valid, cleaned_phone = validate_phone_number(phone)
        return (
            "UPDATE customers SET phone = ? WHERE id = ?",
            [cleaned_phone, customer_id],
            None
        )
    
    # Handle bill deletion
    bill_delete_pattern = r'delete (?:bill|invoice)\s*(?:id\s*)?(\d+)'
    match = re.search(bill_delete_pattern, user_input.lower())
    if match:
        bill_id = int(match.group(1))
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id FROM bills WHERE id = ?", (bill_id,))
            if not cursor.fetchone():
                return None, None, [f"Bill ID {bill_id} does not exist."]
            sql_query = "DELETE FROM bills WHERE id = ?"
            params = [bill_id]
            return sql_query, params, None
        except sqlite3.Error as e:
            return None, None, [f"Error deleting bill: {str(e)}"]
        finally:
            conn.close()
    
    # Handle customer deletion
    delete_customer_pattern = r'delete (?:customer )?[\'""]?([a-zA-Z0-9\s]+)[\'""]?'
    match = re.search(delete_customer_pattern, user_input.lower())
    if match:
        customer_name = match.group(1).strip()
        customer_id = check_customer_exists(customer_name)
        if not customer_id:
            return None, None, [f"Customer '{customer_name}' does not exist."]
        sql_query = "DELETE FROM customers WHERE id = ?"  # Fixed to use id
        params = [customer_id]
        return sql_query, params, None
    
    # Handle stock creation
    stock_pattern = r'(?:add|create)\s*(?:new)?\s*stock\s*(?:item)?\s*([a-zA-Z\s]+)(?:\s*with\s*price\s*\$?(\d+(?:\.\d+)?))?(?:\s*(?:and\s*quantity\s*(\d+)))?'
    match = re.search(stock_pattern, user_input.lower())
    if match:
        product_name = match.group(1).strip()
        price = float(match.group(2)) if match.group(2) else None
        quantity = int(match.group(3)) if match.group(3) else 0
        
        # Check if stock item already exists
        stock_id = check_stock_exists(product_name)
        if stock_id:
            return None, None, [f"Stock item '{product_name}' already exists with ID {stock_id}.Use 'Add [quantity] {product_name} to stock' to update quantity."]
        
        valid, result = validate_stock_params(product_name, price, quantity)
        if not valid:
            prompt = "Please provide all required fields for the stock item. You provided:"
            prompt += f"\n- Product name: {product_name}" if product_name else ""
            prompt += f"\n- Price: ${price}" if price is not None else ""
            prompt += f"\n- Quantity: {quantity}"
            prompt += "\nMissing or invalid fields: " + ", ".join(result)
            prompt += "\nExample: 'Add new stock item Ceramic Mug with price $12.99 and quantity 50'"
            return None, None, [prompt]
        
        stock_id, error = add_stock_item(product_name, price, quantity)
        if error:
            return None, None, error
        
        return (
            "INSERT INTO stocks (product_name, price, quantity) VALUES (?, ?, ?)",
            [product_name, price, result["quantity"]],
            None
        )
    # Handle stock quantity update
    add_stock_quantity_pattern = r'add\s*(\d+)\s*(?:units of)?\s*([a-zA-Z\s]+)\s*to\s*stock'
    match = re.search(add_stock_quantity_pattern, user_input.lower())
    if match:
        quantity = int(match.group(1))
        product_name = match.group(2).strip()
        
        stock_id = check_stock_exists(product_name)
        if not stock_id:
            return None, None, [f"Stock item '{product_name}' does not exist. Create it first with 'Add stock item {product_name} with price $X'."]
        
        if quantity <= 0:
            return None, None, ["Quantity must be a positive integer."]
        
        sql_query = "UPDATE stocks SET quantity = quantity + ? WHERE id = ?"
        params = [quantity, stock_id]
        return sql_query, params, None
    
    # Handle view bill items
    view_bill_items_pattern = r'(?:view|show|list)\s*(?:bill\s*)?items\s*(?:of\s*)?(?:bill\s*)?(?:id\s*)?(\d+)'
    match = re.search(view_bill_items_pattern, user_input.lower())
    if match:
        bill_id = int(match.group(1))
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id FROM bills WHERE id = ?", (bill_id,))
            if not cursor.fetchone():
                return None, None, [f"Bill ID {bill_id} does not exist."]
            sql_query = """
                SELECT bi.id AS item_id, s.product_name, bi.quantity, s.price, bi.total_price,
                       b.total_amount AS bill_total
                FROM bill_items bi
                JOIN stocks s ON bi.stock_id = s.id
                JOIN bills b ON bi.bill_id = b.id
                WHERE bi.bill_id = ?
                ORDER BY bi.id
            """
            params = [bill_id]
            return sql_query, params, None
        except sqlite3.Error as e:
            return None, None, [f"Error retrieving bill items: {str(e)}"]
        finally:
            conn.close()
    
    # Handle show all bills
    show_bills_pattern = r'(?:show|list|display)\s*(?:all\s*)?bills'
    match = re.search(show_bills_pattern, user_input.lower())
    if match:
        sql_query = """
            SELECT b.id AS bill_id, b.customer_id, c.name AS customer_name, 
                   b.bill_date, b.total_amount, b.payment_status
            FROM bills b
            JOIN customers c ON b.customer_id = c.id
            ORDER BY b.bill_date DESC
            LIMIT 100
        """
        params = []
        return sql_query, params, None

    schema = get_table_schema()
    schema_str = json.dumps(schema, indent=2)
    
    prompt = f"""
    Convert this natural language query into a valid SQLite SQL query.
    
    DATABASE SCHEMA:
    {schema_str}
    
    IMPORTANT RULES:
    1. Return ONLY the raw SQL query with no explanation or markdown.
    2. For INSERT, UPDATE, or DELETE operations, use parameterized queries with ? placeholders.
    3. For searching text fields, use LIKE with % wildcards (e.g., WHERE name LIKE '%value%').
    4. All customer names are stored in lowercase in the customers table.
    5. Join tables when necessary to fulfill the request.
    6. For listing all records, include a LIMIT 100 to avoid excessive results.
    7. When ordering results, use ORDER BY with an appropriate field.
    8. For bill creation, ALWAYS include the bill_date field with a ? placeholder.
    9. When inserting into bills table, always include customer_id, bill_date, total_amount, and payment_status.
    10. Use ISO format (YYYY-MM-DD HH:MM:SS) for dates.
    11. For stock insertions, product_name and price are REQUIRED. Quantity defaults to 0 if not provided.
    12. For stock queries (e.g., 'show all stock items'), include items with quantity=0 in the results.
    13. Stock item names are case-insensitive; check for existing items using LOWER(product_name).
    14. For customer phone number updates or insertions, ensure the phone number contains only numerical digits, up to 12 digits, ignoring spaces or symbols.
    15. For bill deletion, ensure the bill_id exists in the bills table.
    16. For viewing bill items, join bill_items, stocks, and bills to show item details and total amount.
    USER QUERY:
    {user_input.lower()}
    """
    
    try:
        response = model.generate_content(prompt)
        sql_query = response.text.strip()
        
        sql_query = re.sub(r'```(?:sqlite|sql)?\n?', '', sql_query, flags=re.MULTILINE).strip()
        
        if not re.search(r'\b(SELECT|INSERT|UPDATE|DELETE)\b', sql_query, re.IGNORECASE):
            print(f"Invalid SQL generated: {sql_query}")
            return None, None, ["Generated query doesn't appear to be valid SQL."]
        
        dangerous_patterns = [
            r'--',           # SQL comment
            r'/\*.*?\*/',    # Multi-line comment
            r';.*?;',        # Multiple statements
            r'DROP\s+TABLE', # Drop table
            r'DELETE\s+FROM\s+\w+\s*(?:WHERE\s+\d+\s*=\s*\d+|$)' # Delete all records
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, sql_query, re.IGNORECASE):
                return None, None, ["Generated query contains potentially unsafe patterns."]
        
        # Validate phone number for UPDATE customers SET phone or INSERT INTO customers
        params = extract_parameters(user_input, sql_query)
        if (sql_query.strip().upper().startswith("UPDATE CUSTOMERS") and "phone" in sql_query.lower()) or \
           sql_query.strip().upper().startswith("INSERT INTO CUSTOMERS"):
            phone_param_index = None
            if sql_query.upper().startswith("UPDATE CUSTOMERS"):
                match = re.search(r'SET\s+phone\s*=\s*\?', sql_query, re.IGNORECASE)
                if match:
                    fields = re.findall(r'\b\w+\s*=\s*\?', sql_query, re.IGNORECASE)
                    for i, field in enumerate(fields):
                        if "phone =" in field.lower():
                            phone_param_index = i
                            break
            elif sql_query.upper().startswith("INSERT INTO CUSTOMERS"):
                match = re.search(r'$$ ([^)]+) $$', sql_query, re.IGNORECASE)
                if match:
                    fields = [f.strip() for f in match.group(1).split(',')]
                    if 'phone' in fields:
                        phone_param_index = fields.index('phone')
            
            if phone_param_index is not None and phone_param_index < len(params):
                phone = params[phone_param_index]
                valid, result = validate_phone_number(phone)
                if not valid:
                    return None, None, result
                params[phone_param_index] = result
        
        # Validate bill_id for deletion
        if sql_query.strip().upper().startswith("DELETE FROM BILLS"):
            bill_id_index = None
            match = re.search(r'WHERE\s+id\s*=\s*\?', sql_query, re.IGNORECASE)
            if match:
                bill_id_index = 0  # First parameter is bill_id
            if bill_id_index is not None and bill_id_index < len(params):
                bill_id = params[bill_id_index]
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT id FROM bills WHERE id = ?", (bill_id,))
                    if not cursor.fetchone():
                        return None, None, [f"Bill ID {bill_id} does not exist."]
                except sqlite3.Error as e:
                    return None, None, [f"Error validating bill: {str(e)}"]
                finally:
                    conn.close()
        
        params = extract_parameters(user_input, sql_query)
        return sql_query, params, None
        
    except Exception as e:
        print(f"Gemini error for SQL parsing: {e}")
        return None, None, [f"Error generating SQL: {str(e)}"]

def handle_bill_creation(customer_name):
    """Create a new bill for a customer by name."""
    customer_id = check_customer_exists(customer_name)
    
    if not customer_id:
        customer_id = get_or_create_customer(customer_name)
        if not customer_id:
            return None, [f"Failed to create customer {customer_name}"]
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            "INSERT INTO bills (customer_id, bill_date, total_amount, payment_status) VALUES (?, ?, ?, ?)",
            (customer_id, current_date, 0.0, "pending")
        )
        conn.commit()
        new_bill_id = cursor.lastrowid
        
        return {
            "bill_id": new_bill_id,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "date": current_date
        }, None
    except sqlite3.Error as e:
        return None, [f"Database error while creating bill: {str(e)}"]
    finally:
        conn.close()

def format_results(query_results, sql_query):
    """Format query results for display in the chat interface."""
    if not query_results.get("data"):
        return "No results found."
    
    if sql_query.strip().upper().startswith("SELECT"):
        results = query_results["data"]
        columns = query_results["columns"]
        
        if not results:
            return "Query executed, but no matching records found."
        
        # Format numeric fields for clarity
        formatted_results = []
        for row in results:
            formatted_row = {}
            for col in columns:
                if col in ["total_amount", "price", "total_price", "bill_total"] and isinstance(row[col], (int, float)):
                    formatted_row[col] = f"{row[col]:.2f}"
                elif col == "quantity" and isinstance(row[col], int):
                    formatted_row[col] = str(row[col])
                elif row[col] is None:
                    formatted_row[col] = ""
                else:
                    formatted_row[col] = row[col]
            formatted_results.append(formatted_row)
        return {
            "type": "table",
            "columns": columns,
            "data": formatted_results
        }
    
    elif sql_query.strip().upper().startswith("INSERT"):
        affected = query_results["data"].get("affected_rows", 0)
        last_id = query_results["data"].get("last_id")
        
        if "bills" in sql_query.lower():
            return f"Bill created successfully with ID: {last_id}"
        elif "stocks" in sql_query.lower():
            return f"Stock item created successfully with ID: {last_id}"
        
        return f"Added successfully. Affected rows: {affected}, New ID: {last_id}"
    
    elif sql_query.strip().upper().startswith("UPDATE"):
        affected = query_results["data"].get("affected_rows", 0)
        return f"Updated successfully. Affected rows: {affected}"
    
    elif sql_query.strip().upper().startswith("DELETE"):
        affected = query_results["data"].get("affected_rows", 0)
        return f"Deleted successfully. Affected rows: {affected}"
    
    return f"Query executed successfully."

@app.route('/')
def home():
    return render_template("home.html")

@app.route('/chat')
def chat():
    return render_template("chat.html")

@app.route('/query', methods=['POST'])
def process_query():
    user_input = request.json.get('query')
    if not user_input:
        return jsonify({"status": "error", "message": "Query is empty"}), 400

    try:
        if is_casual_query(user_input):
            casual_response = handle_casual_query(user_input)
            return jsonify({"status": "casual", "data": casual_response})
        
        bill_creation_patterns = [
            r'create (?:a )?(?:new )?bill for customer [\'""]?([a-zA-Z0-9\s]+)[\'""]?',
            r'add (?:a )?(?:new )?bill for (?:customer )?[\'""]?([a-zA-Z0-9\s]+)[\'""]?',
            r'generate (?:a )?(?:new )?bill for [\'""]?([a-zA-Z0-9\s]+)[\'""]?',
            r'create (?:a )?(?:new )?bill for [\'""]?([a-zA-Z0-9\s]+)[\'""]?'
        ]
        
        for pattern in bill_creation_patterns:
            match = re.search(pattern, user_input.lower())
            if match:
                customer_name = match.group(1).strip()
                bill_data, error = handle_bill_creation(customer_name)
                
                if error:
                    return jsonify({"status": "error", "message": error[0]}), 400
                
                return jsonify({
                    "status": "success",
                    "message": f"Created bill for {customer_name}",
                    "data": f"Bill #{bill_data['bill_id']} created for customer '{customer_name}' (ID: {bill_data['customer_id']}) on {bill_data['date']}.",
                    "sql": "INSERT INTO bills (customer_id, bill_date, total_amount, payment_status) VALUES (?, ?, ?, ?)"
                })
        
        customer_creation_patterns = [
            r'create (?:a )?(?:new )?customer (?:named )?[\'""]?([a-zA-Z0-9\s]+)[\'""]?',
            r'add (?:a )?(?:new )?customer (?:named )?[\'""]?([a-zA-Z0-9\s]+)[\'""]?',
            r'insert (?:a )?(?:new )?customer (?:named )?[\'""]?([a-zA-Z0-9\s]+)[\'""]?'
        ]
        
        for pattern in customer_creation_patterns:
            match = re.search(pattern, user_input.lower())
            if match:
                customer_name = match.group(1).strip()
                phone = match.group(2) if len(match.groups()) > 1 else None
                valid, result = validate_phone_number(phone)
                if not valid:
                    return jsonify({"status": "error", "message": result[0]}), 400
                customer_id = check_customer_exists(customer_name)
                if customer_id:
                    return jsonify({
                        "status": "success",
                        "message": f"Customer '{customer_name}' already exists with ID {customer_id}.",
                        "data": f"Customer '{customer_name}' already exists with ID {customer_id}."
                    }), 200
                customer_id = get_or_create_customer(customer_name, phone)
                if not customer_id:
                    return jsonify({"status": "error", "message": "Failed to create customer."}), 400
                return jsonify({
                    "status": "success",
                    "message": f"Customer '{customer_name}' created with ID {customer_id}.",
                    "data": f"Customer '{customer_name}' created with ID {customer_id}.",
                    "sql": "INSERT INTO customers (name, phone) VALUES (?, ?)"
                }), 200
            # Handle phone number update
        phone_update_pattern = r'update (?:customer )?[\'""]?([a-zA-Z0-9\s]+)[\'""]?\s*phone\s*(?:number)?\s*to\s*([\d\s\-()+]+)'
        match = re.search(phone_update_pattern, user_input.lower())
        if match:
            customer_name = match.group(1).strip()
            phone = match.group(2).strip()
            customer_id, error = update_customer_phone(customer_name, phone)
            if error:
                return jsonify({"status": "error", "message": error[0]}), 400
            valid, cleaned_phone = validate_phone_number(phone)
            return jsonify({
                "status": "success",
                "message": f"Updated phone number for customer '{customer_name}'.",
                "data": f"Phone number for customer '{customer_name}' (ID: {customer_id}) updated to {cleaned_phone}.",
                "sql": "UPDATE customers SET phone = ? WHERE id = ?"
            })
        
        sql_query, params, error = generate_sql_query(user_input)
        
        if error or not sql_query:
            return jsonify({
                "status": "error", 
                "message": error[0] if error else "Could not generate a valid SQL query. Try rephrasing your request."
            }), 400
        
        if sql_query.strip().upper().startswith("INSERT INTO CUSTOMERS"):
            customer_name = params[0] if params else None
            customer_id = check_customer_exists(customer_name) if customer_name else None
            
            if customer_id:
                return jsonify({
                    "status": "success",
                    "message": f"Customer '{customer_name}' already exists with ID {customer_id}.",
                    "data": f"Customer '{customer_name}' already exists with ID {customer_id}."
                }), 200
        
        if sql_query.strip().upper().startswith("INSERT INTO BILLS"):
            customer_id_param = None
            customer_id_index = None
            
            match = re.search(r'INSERT\s+INTO\s+bills\s*\(([^)]+)\)', sql_query, re.IGNORECASE)
            if match:
                fields = [f.strip() for f in match.group(1).split(',')]
                if 'customer_id' in fields:
                    customer_id_index = fields.index('customer_id')
                    if customer_id_index < len(params):
                        customer_id_param = params[customer_id_index]
            
            if customer_id_param:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT id FROM customers WHERE id = ?", (customer_id_param,))
                    result = cursor.fetchone()
                    if not result:
                        return jsonify({
                            "status": "error",
                            "message": f"Customer with ID {customer_id_param} does not exist."
                        }), 400
                except sqlite3.Error as e:
                    print(f"Error verifying customer: {e}")
                finally:
                    conn.close()
        
        results = query_db(sql_query, params)
        
        formatted_results = format_results(results, sql_query)
        
        print(f"Query executed: {sql_query} with params {params}")
        
        return jsonify({
            "status": "success", 
            "data": formatted_results,
            "sql": sql_query
        })
        
    except Exception as e:
        print(f"Error processing query: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/tables', methods=['GET'])
def get_tables():
    """API endpoint to get database schema information."""
    schema = get_table_schema()
    return jsonify({"status": "success", "data": schema})

@app.errorhandler(404)
def page_not_found(e):
    return jsonify({"status": "error", "message": "Requested resource not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"status": "error", "message": "Internal server error"}), 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=3000, debug=True)