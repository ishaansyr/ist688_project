# app.py
import base64
import io

import streamlit as st
from openai import OpenAI

from conversational_agent import ConversationalAgent


# ---------------------------
# Setup
# ---------------------------

st.set_page_config(page_title="Recipe Assistant", page_icon="🍽", layout="centered")

# Initialise OpenAI client using Streamlit secrets
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# One global conversational agent in session
if "agent" not in st.session_state:
    excel_path = "MemoryFiles/TestWorkBook.xlsx"
    st.session_state.agent = ConversationalAgent(
        model="gpt-4o-mini",
        excel_file_path=excel_path,
    )

# Chat history in session_state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Current username (simple text input for now)
if "username" not in st.session_state:
    st.session_state.username = "Alice"


# ---------------------------
# Helper: image → ingredients via LLM
# ---------------------------

def extract_ingredients_from_image(image_file) -> list[str]:
    """
    Use gpt-4o-mini vision via chat.completions to list visible ingredients.
    Keeps this separate from the Responses API you use elsewhere.
    """
    # Read bytes and base64-encode
    img_bytes = image_file.read()
    b64 = base64.b64encode(img_bytes).decode("utf-8")

    # Prompt: ask for JSON list of ingredients
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant that looks at a photo of a fridge or pantry "
                "and lists visible food items. "
                "Return ONLY valid JSON with one key 'ingredients' whose value is a list of strings."
            ),
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Look at this image and list all ingredients or food items you can clearly identify.",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}"
                    },
                },
            ],
        },
    ]

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.1,
        )
        raw = completion.choices[0].message.content.strip()
        import json
        data = json.loads(raw)
        ingredients = data.get("ingredients", [])
        return [i.strip() for i in ingredients if isinstance(i, str) and i.strip()]
    except Exception:
        return []


# ---------------------------
# UI: sidebar controls
# ---------------------------

with st.sidebar:
    st.header("User")
    st.session_state.username = st.text_input(
        "Username", value=st.session_state.username
    )

    st.markdown("---")
    st.header("Fridge photo")
    uploaded_image = st.file_uploader(
        "Upload a photo of your fridge/pantry (optional)",
        type=["png", "jpg", "jpeg"],
    )
    use_fridge_photo = st.checkbox(
        "Use fridge photo for this request (if uploaded)", value=False
    )

    st.markdown("---")
    st.caption("This is a barebones prototype. Aesthetics come later.")


# ---------------------------
# UI: chat history
# ---------------------------

st.title("Recipe Recommendation Chatbot")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("recipes"):
            st.write("**Top recipe suggestions:**")
            for i, r in enumerate(msg["recipes"], 1):
                line = f"{i}. {r['name']}"
                if r.get("calories") is not None:
                    line += f" — {r['calories']} kcal, {r['protein']} g protein"
                st.write(line)


# ---------------------------
# Handle new user input
# ---------------------------

user_input = st.chat_input("Ask for recipes, meal plans, or ideas...")

if user_input:
    username = st.session_state.username
    agent = st.session_state.agent

    # 1. (Optional) interpret fridge photo
    fridge_ingredients = []
    if use_fridge_photo and uploaded_image is not None:
        fridge_ingredients = extract_ingredients_from_image(uploaded_image)

    # Build a message that includes fridge inventory if we have it
    if fridge_ingredients:
        augmented_message = (
            user_input
            + "\n\nAlso, these items are currently in my fridge: "
            + ", ".join(fridge_ingredients)
        )
    else:
        augmented_message = user_input

    # 2. Call backend pipeline
    recipes, parsed_request, user_profile, save_result = agent.handle_message(
        username, augmented_message
    )

    # Prepare a simple text response for the assistant
    if recipes:
        reply_text = "Here are some recipes that match your preferences and goals."
    else:
        reply_text = (
            "I could not find recipes that satisfy your current restrictions and inventory."
        )

    # 3. Log user message
    st.session_state.messages.append(
        {
            "role": "user",
            "content": user_input,
        }
    )

    # 4. Log assistant message with recipe metadata
    recipe_summaries = [
        {
            "name": r.name,
            "calories": r.calories,
            "protein": r.protein,
        }
        for r in recipes[:5]
    ]

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": reply_text,
            "recipes": recipe_summaries,
        }
    )

    # 5. Rerun to update chat display
    st.rerun()
