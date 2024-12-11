from flask import Flask, render_template_string, request, jsonify
import openai
import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv

app = Flask(__name__)

# Initialize OpenAI client
load_dotenv()

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

client = openai.Client()

@app.route("/analyze", methods=["POST"])
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
                    "content": "You are a markdown text scraper, you need to create an Embed JS output with the scraped information with the schema {name: ... , price: ... , description: ... }. Scrape all the information you can to provide an Embed JS script as output that can be displayed on FrontEnd. Only output the JS script after inference, nothing more nothing less."
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

        return jsonify({"response": response_text})

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Error fetching the URL: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"An error occurred: {e}"}), 500

if __name__ == "__main__":
    app.run(debug=True)

# After deploying this Flask application, you can use the /analyze endpoint as follows:
# 1. Make a POST request to the /analyze endpoint with a JSON payload containing the "url" key.
# 2. Example request using curl:
#    curl -X POST http://127.0.0.1:5000/analyze -H "Content-Type: application/json" -d '{"url": "example.com"}'
# 3. The endpoint will return a JSON response containing the analyzed data in the form of an Embed JS script.
# 4. Handle the response in your frontend application to display the scraped information.
