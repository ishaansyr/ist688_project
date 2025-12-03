# app.py
import base64
import io
import os
import json
import streamlit as st
from openai import OpenAI
from conversational_agent import ConversationalAgent

# ---------------------------
# Setup
# ---------------------------

st.set_page_config(
    page_title="Recipe Assistant",
    page_icon="🍽",
    layout="centered",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600;700&family=Dancing+Script:wght@500;600&display=swap');

/* ===== Global background: remove white bars top/bottom ===== */
html, body {
    background: linear-gradient(180deg, #faf4e8 0%, #f6efdf 45%, #f1ebdd 100%) !important;
}
.stApp,
main,
section.main,
div[data-testid="stAppViewContainer"],
div[data-testid="stHeader"],
footer,
div[data-testid="stDecoration"] {
    background: transparent !important;
}

/* Main app text baseline */
.stApp {
    color: #354436;
    font-family: 'Playfair Display', Georgia, 'Times New Roman', serif;
}

/* Layout container shadow */
div[data-testid="stAppViewContainer"] {
    padding-top: 1rem;
    box-shadow: inset 0 0 60px rgba(190, 170, 120, 0.08);
}

/* Headings */
h1, h2, h3, h4 {
    font-family: 'Dancing Script', 'Playfair Display', serif;
    color: #2f4a34;
    letter-spacing: 0.8px;
    font-weight: 600;
    text-shadow: 0 1px 2px rgba(60, 80, 60, 0.18);
}
h1 { font-size: 2.8rem !important; margin-bottom: 0.1rem; }
h2 { font-size: 1.8rem !important; }

/* Sidebar */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #f3ecdb 0%, #e8dfc7 100%);
    border-right: 1px solid #d2c5a7;
}
section[data-testid="stSidebar"] * {
    font-family: 'Playfair Display', Georgia, serif;
}
div[data-testid="collapsedControl"] {
    font-size: 0 !important; /* hide off-centre label */
}

/* Chat messages */
.stChatMessage {
    background-color: #fffcf5;
    border-radius: 14px;
    border: 1px solid rgba(197,176,139,0.8);
    box-shadow: 0 4px 10px rgba(160,130,90,0.14);
    padding: 0.9rem 1rem;
    margin-bottom: 0.8rem;
}
.stChatMessage[data-testid="stChatMessage-user"] {
    background: linear-gradient(135deg, #faf1e2 0%, #f6e6cf 100%);
    border-left: 4px solid #b6915f;
}
.stChatMessage[data-testid="stChatMessage-assistant"] {
    background: linear-gradient(135deg, #f3f7f0 0%, #e6f0e4 100%);
    border-left: 4px solid #7e9d78;
}

/* ===== Chat input: single clean pill, no inner line ===== */
div[data-testid="stChatInput"] {
    background: #fdf8ef !important;  /* slightly warmer cream */
    border: 1px solid #d5cbb7 !important;
    border-radius: 999px !important;
}

div[data-testid="stChatInput"] * {
    box-shadow: none !important;
}
div[data-testid="stChatInput"] > div {
    background: transparent !important;
    border: none !important;
}
div[data-baseweb="textarea"] {
    background: transparent !important;
    border: none !important;
}
/* Fix inner blue/grey rectangle inside chat input */
div[data-baseweb="base-input"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}
div[data-testid="stChatInput"] textarea {
    background: transparent !important;
    border: none !important;
    outline: none !important;
    color: #3c4035 !important;
    font-family: 'Playfair Display', Georgia, serif !important;
    font-size: 1.05rem;
}
div[data-testid="stChatInput"] svg {
    color: #7c7e78 !important;
}

/* Buttons */
.stButton>button {
    background: linear-gradient(135deg, #7c946a 0%, #6c835d 100%);
    color: #fffaf0;
    border-radius: 999px;
    border: none;
    padding: 0.4rem 1.1rem;
    font-family: 'Playfair Display', serif;
    font-style: italic;
    transition: 0.15s ease-out;
}
.stButton>button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 10px rgba(100,120,90,0.25);
    filter: brightness(1.05);
}

/* Inputs */
input, textarea, select {
    background-color: #fffaf0 !important;
    border: 1px solid #d5cdb7 !important;
    border-radius: 8px !important;
    color: #374635 !important;
}

/* Recipe cards */
.recipe-card {
    background: #fffcf7;
    border-radius: 12px;
    padding: 0.75rem 0.9rem;
    margin-bottom: 0.6rem;
    border: 1px solid rgba(210,190,150,0.9);
    box-shadow: 0 3px 7px rgba(156,132,98,0.18);
}
.recipe-card-title {
    font-family: 'Dancing Script', serif;
    font-size: 1.25rem;
    color: #2f4a34;
}
.recipe-card-macros { color: #3b5d3d; }

/* Center chat messages on large screens */
@media (min-width: 992px) {
    .stChatMessage {
        max-width: 780px;
        margin-left: auto;
        margin-right: auto;
    }
}
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Initialise Agent
# ---------------------------

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

if "agent" not in st.session_state:
    excel_path = "MemoryFiles/TestWorkBook.xlsx"
    st.session_state.agent = ConversationalAgent(
        model="gpt-4o-mini",
        excel_file_path=excel_path,
    )

if "messages" not in st.session_state:
    st.session_state.messages = []

if "username" not in st.session_state:
    st.session_state.username = "Ishaan"

# ---------------------------
# Helper: extract ingredients from image
# ---------------------------

import re  # add this near the top of the file

def extract_ingredients_from_image(image_file) -> list[str]:
    img_bytes = image_file.read()
    b64 = base64.b64encode(img_bytes).decode("utf-8")

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
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
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

        # Strip ```json ... ``` fences if present
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = re.sub(r"^json", "", raw, flags=re.IGNORECASE).strip()

        # Extract JSON object substring
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1:
            raw_json = raw[start : end + 1]
        else:
            raw_json = raw

        data = json.loads(raw_json)
        ingredients = data.get("ingredients", [])
        return [
            i.strip()
            for i in ingredients
            if isinstance(i, str) and i.strip()
        ]
    except Exception as e:
        # Optional: temporary debug
        # st.sidebar.write(f"Vision parse error: {e}")
        return []

# ---------------------------
# Sidebar
# ---------------------------

with st.sidebar:
    st.header("👩‍🍳 User profile")
    st.session_state.username = st.text_input("Name", value=st.session_state.username)
    st.markdown("---")
    st.header("📷 Fridge snapshot")
    uploaded_image = st.file_uploader(
        "Upload your fridge or pantry photo (optional)",
        type=["png", "jpg", "jpeg"],
    )
    use_fridge_photo = st.checkbox("Use fridge photo for this request", value=False)
    st.markdown("---")

# ---------------------------
# Chat Interface
# ---------------------------

st.title("🍽 The Recipe Companion")
st.markdown(
    "<p style='font-family: \"Playfair Display\", serif; font-style: italic; "
    "color:#5a6b58; margin-top:-0.5rem; margin-bottom:1.3rem;'>"
    "A calm, curated kitchen notebook for your day-to-day cooking."
    "</p>",
    unsafe_allow_html=True,
)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("recipes"):
            st.markdown("**Top recipe suggestions:**")
            for i, r in enumerate(msg["recipes"], 1):
                details = []
                if r.get("calories"):
                    details.append(f"{r['calories']} kcal")
                if r.get("protein"):
                    details.append(f"{r['protein']} protein")
                if r.get("carbs"):
                    details.append(f"{r['carbs']} carbs")
                if r.get("fat"):
                    details.append(f"{r['fat']} fat")
                if r.get("fiber"):
                    details.append(f"{r['fiber']} fiber")

                st.markdown(
                    f"""
                    <div class="recipe-card">
                        <div class="recipe-card-title">{i}. {r['name']}</div>
                        <div class="recipe-card-macros">
                            {', '.join(details)}
                        </div>
                        {f"<a href='{r['url']}' target='_blank'>View recipe</a>" if r.get('url') else ''}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

# ---------------------------
# User Input
# ---------------------------

# ---------------------------
# User Input
# ---------------------------

user_input = st.chat_input("Ask for recipes, meal ideas, or nutrition tips...")

if user_input:
    username = st.session_state.username
    agent = st.session_state.agent

    # 1. Extract ingredients from image (if used)
    fridge_ingredients: list[str] = []
    if use_fridge_photo and uploaded_image is not None:
        fridge_ingredients = extract_ingredients_from_image(uploaded_image)

    # Optional: show the detected ingredients in the UI so you can see what the model saw
    if fridge_ingredients:
        st.sidebar.caption("Detected from photo: " + ", ".join(fridge_ingredients))

    # 2. Call the agent with:
    #    - raw user text as `message`
    #    - fridge ingredients as structured `extra_inventory`
    recipes, parsed_request, user_profile, save_result = agent.handle_message(
        username,
        user_input,                 # <<< do NOT append fridge ingredients here
        extra_inventory=fridge_ingredients or None,
    )

    # 3. Build reply
    if parsed_request.get("action") == "inventory_cleared":
        reply_text = "Your fridge inventory has been cleared."
    elif recipes:
        reply_text = "Here are some recipes that match your preferences and goals:"
    else:
        reply_text = "I couldn’t find recipes that meet your dietary preferences right now."

    # 4. Record chat messages
    st.session_state.messages.append({"role": "user", "content": user_input})

    recipe_summaries = [
        {
            "name": r.name,
            "calories": round(r.calories, 2) if r.calories else None,
            "protein": f"{round(r.protein, 2)} g" if r.protein else None,
            "carbs": f"{round(r.carbs, 2)} g" if r.carbs else None,
            "fat": f"{round(r.fat, 2)} g" if r.fat else None,
            "fiber": f"{round(r.fiber, 2)} g" if r.fiber else None,
            "url": r.source_url or getattr(r, "url", None) or None,
        }
        for r in recipes[:5]
    ]

    st.session_state.messages.append(
        {"role": "assistant", "content": reply_text, "recipes": recipe_summaries}
    )

    st.rerun()
