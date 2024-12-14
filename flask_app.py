from flask import Flask, request, jsonify
import openai
import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
import psycopg2
import jwt
import datetime
from functools import wraps
from bcrypt import hashpw, gensalt, checkpw
import json

app = Flask(__name__)

# Initialize OpenAI client
load_dotenv()

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")  # Replace with a strong secret key

client = openai.Client()

# Database connection
def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT")
    )

# Authentication decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")
        if not token:
            return jsonify({"message": "Token is missing"}), 401
        try:
            jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"message": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"message": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated

# Signup endpoint
@app.route("/signup", methods=["POST"])
def signup():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"message": "Username and password are required"}), 400

    # Hash the password
    hashed_password = hashpw(password.encode("utf-8"), gensalt())

    # Save the user to the database
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_password.decode("utf-8")))
        conn.commit()
        return jsonify({"message": "User created successfully"}), 201
    except psycopg2.errors.UniqueViolation:
        return jsonify({"message": "Username already exists"}), 400
    finally:
        cur.close()

# Login endpoint
@app.route("/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"message": "Username and password are required"}), 400

    # Authenticate user
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    
    if not user or not checkpw(password.encode("utf-8"), user[0].encode("utf-8")):
        return jsonify({"message": "Invalid credentials"}), 401

    # Generate JWT token
    token = jwt.encode(
        {"username": username, "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)},
        SECRET_KEY,
        algorithm="HS256"
    )
    return jsonify({"token": token})

# Fetch agents from the database
@app.route("/agents", methods=["GET"])
@token_required
def fetch_agents():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT agent_name, prompt, image_url FROM agents")
    agents = cur.fetchall()
    cur.close()
    return jsonify(agents)

# Save a new agent to the database
@app.route("/agents", methods=["POST"])
@token_required
def save_agent():
    data = request.json
    agent_name = data.get("agent_name")
    prompt = data.get("prompt")
    image_url = data.get("image_url", "image_placeholder.png")

    if not agent_name or not prompt:
        return jsonify({"error": "agent_name and prompt are required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO agents (agent_name, prompt, image_url) VALUES (%s, %s, %s)",
                (agent_name, prompt, image_url))
    conn.commit()
    cur.close()
    return jsonify({"message": "Agent saved successfully"})

# Save a new product to the database
@app.route("/products", methods=["POST"])
@token_required
def save_product():
    data = request.json
    name = data.get("name")
    price = data.get("price")
    description = data.get("description")

    if not name or not price or not description:
        return jsonify({"error": "name, price, and description are required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO products (name, price, description) VALUES (%s, %s, %s)",
                (name, price, description))
    conn.commit()
    cur.close()
    return jsonify({"message": "Product saved successfully"})

# Analyze endpoint
@app.route("/analyze", methods=["POST"])
@token_required
def analyze():
    data = request.json
    url = data.get("url")
    if not url:
        return jsonify({"error": "URL is required"}), 400

    # Prepend the URL with "https://r.jina.ai/"
    full_url = f"https://r.jina.ai/{url}"

    try:
        response = requests.get(full_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        html_content = str(soup)  # Convert to string

        # Call OpenAI API with the system prompt using the client
        openai_response = client.chat.completions.create(
            model="gpt-4o",  # Or your preferred model
            messages=[
                {
                    "role": "system",
                    "content": "You are a markdown text scraper, you need to scrape information to fill the schema {name: ... , price: ... , description: ... }. Make the output in the format so that json.loads on python can directly read from the output string generated."
                },
                {
                    "role": "user",
                    "content": f"Analyze the following HTML content:\n\n{html_content}"
                }
            ],
            temperature=1,
            max_tokens=2048,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0
        )

        response_text = openai_response.choices[0].message.content.strip()

        if 'json' in response_text:
            response_text = json.loads(response_text.split("```json")[1].split("```")[0])  # Convert to dictionary using
        else:
            response_text = json.loads(response_text)

        # Extract the contents of the JSON
        name = response_text.get("name")
        price = response_text.get("price")
        description = response_text.get("description")

        return jsonify({"name": name, "price": price, "description": description})

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Error fetching the URL: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"An error occurred: {e}"}), 500

if __name__ == "__main__":
    app.run(debug=True)