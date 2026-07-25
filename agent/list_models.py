import os
from dotenv import load_dotenv
from google import genai

load_dotenv(dotenv_path="../.env")
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

for model in client.models.list():
    print(model.name)