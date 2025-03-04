from google import genai
from google.genai import types
import base64


def generate():
    client = genai.Client(
        vertexai=True,
        project="nodal-wall-426818-t6",
        location="us-central1",
    )

    model = "gemini-2.0-flash-001"
    contents = [types.Content(role="user", parts=[])]
    generate_content_config = types.GenerateContentConfig(
        temperature=1,
        top_p=0.95,
        max_output_tokens=8192,
        response_modalities=["TEXT"],
    )

    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=generate_content_config,
    ):
        print(chunk.text, end="")


generate()
