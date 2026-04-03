from google import genai
client = genai.Client(api_key="AIzaSyApw71xyMw6QKIvRJomMk0rET8f5wJqCCs")
prompt = ("Generate 5 MCQs for 'Python'. "
          "Format: Question|A|B|C|D|CorrectLetter. "
          "Strictly NO intro text, NO markdown, NO backticks.")
try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    print(response.text)
except Exception as e:
    print("ERROR:", e)
