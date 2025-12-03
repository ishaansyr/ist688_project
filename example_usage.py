import os
import toml

secrets_path = ".streamlit/secrets.toml"
if os.path.exists(secrets_path):
    secrets = toml.load(secrets_path)
    os.environ["OPENAI_API_KEY"] = secrets["OPENAI_API_KEY"]
else:
    raise FileNotFoundError("No secrets.toml found.")

from conversational_agent import ConversationalAgent

agent = ConversationalAgent(excel_file_path="MemoryFiles/TestWorkBook.xlsx")
username = "DebugUser"
message = "Give me chicken recipes"

recipes, analysis, user, _ = agent.handle_message(username, message)
print("Returned recipes:", len(recipes))
for r in recipes:
    print("-", r.name)
