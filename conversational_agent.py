# conversational_agent.py

import json
from openai import OpenAI

from models import UserProfile
from api_agent import APIDataAgent
from dietary_agent import DietaryRestrictionAgent
from ingredient_agent import IngredientAgent
from objective_agent import ObjectiveAgent
from memory_agent import MemoryAgent


class ConversationalAgent:
    """
    LLM-driven conversational and orchestration layer with Excel-backed memory,
    using the Responses API (gpt-4o-mini).
    """

    def __init__(self, model="gpt-4o-mini", excel_file_path="MemoryFiles/TestWorkBook.xlsx"):
        self.client = OpenAI()
        self.model = model

        # Memory / storage
        self.memory_agent = MemoryAgent(excel_file_path=excel_file_path)

        # Deterministic agents
        self.api_agent = APIDataAgent()
        self.diet_agent = DietaryRestrictionAgent()

        # LLM-based agents share the same client and model
        self.ingredient_agent = IngredientAgent(client=self.client, model=self.model)
        self.objective_agent = ObjectiveAgent(client=self.client, model=self.model)

    # ---------- LLM: interpret user message ----------

    def _analyse_message_with_llm(self, user, message, temperature=0.2):
        """
        Ask gpt-4o-mini (Responses API) to extract structured info from the message.

        Expected JSON output:

        {
          "objective": "cutting" | "bulking" | "healthier" | null,
          "dietary_restrictions": ["vegan", "gluten-free", ...],
          "allergies": ["peanut", "dairy", ...],
          "likes": ["chickpeas", "tofu", ...],
          "dislikes": ["broccoli", ...],
          "wants_meal_plan": true/false,
          "time_horizon": "day" | "week" | null,
          "query": "short text to use when searching for recipes"
        }
        """

        current_user = {
            "existing_dietary_restrictions": sorted(list(user.dietary_restrictions)),
            "existing_allergies": sorted(list(user.allergies)),
            "existing_likes": sorted(list(user.likes)),
            "existing_dislikes": sorted(list(user.dislikes)),
            "objective": user.objective,
        }

        default_result = {
            "objective": user.objective,
            "dietary_restrictions": list(user.dietary_restrictions),
            "allergies": list(user.allergies),
            "likes": list(user.likes),
            "dislikes": list(user.dislikes),
            "wants_meal_plan": False,
            "time_horizon": None,
            "query": message,
        }

        response = None
        try:
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "You are an assistant that interprets a user's free-text request "
                                    "about food and meal planning. You must output ONLY valid JSON. "
                                    "Infer their objective (cutting, bulking, healthier if possible), "
                                    "dietary restrictions, allergies, likes, dislikes, and whether "
                                    "they want a meal plan for a day or a week.\n\n"
                                    "Also provide a concise 'query' string that captures what kind "
                                    "of recipes to search for "
                                    "(e.g. 'high protein vegan dinners with chickpeas')."
                                ),
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {
                                        "message": message,
                                        "current_user": current_user,
                                    }
                                ),
                            }
                        ],
                    },
                ],
                temperature=temperature,
            )

            output = response.output[0]
            text_chunks = []
            for c in output.content:
                if c.type == "output_text":
                    text_chunks.append(c.text)
            content = "".join(text_chunks).strip()
            data = json.loads(content)
        except Exception:
            data = default_result

        # Fill any missing keys with defaults
        for key, value in default_result.items():
            if key not in data or data[key] is None:
                data[key] = value

        return data

    def _update_user_profile_from_analysis(self, user, analysis):
        if analysis.get("objective"):
            user.objective = analysis["objective"]

        for r in analysis.get("dietary_restrictions", []):
            user.dietary_restrictions.add(r)

        for a in analysis.get("allergies", []):
            user.allergies.add(a)

        for item in analysis.get("likes", []):
            user.likes.add(item)
        for item in analysis.get("dislikes", []):
            user.dislikes.add(item)

        return user

    # ---------- Orchestration + Memory ----------

    def handle_message(self, username, message, temperature=0.2):
        """
        Main entry point for the app.

        Steps:
        1. Load/create UserProfile via MemoryAgent.
        2. Use gpt-4o-mini (Responses API) to analyse the message.
        3. Update the UserProfile.
        4. Use analysis['query'] to fetch recipes (deterministic).
        5. Filter with DietaryRestrictionAgent (deterministic).
        6. Rank with IngredientAgent (LLM).
        7. Rank with ObjectiveAgent (LLM).
        8. Save updated UserProfile + analysis to Excel.

        Returns:
          final_recipes, analysis, updated_user, save_result
        """

        # 1. Load or create user profile
        user = self.memory_agent.load_user_profile(username)
        if user is None:
            user = UserProfile(user_id=username, name=username)

        # 2. Interpret message with LLM
        analysis = self._analyse_message_with_llm(user, message, temperature=temperature)

        # 3. Update user profile
        user = self._update_user_profile_from_analysis(user, analysis)

        # 4. Build a query for the external recipe APIs
        query = analysis.get("query") or message

        # 5. Fetch candidate recipes (deterministic)
        all_recipes = self.api_agent.fetch_recipes(query)

        # 6. Apply dietary restrictions and allergies (deterministic)
        compliant_recipes = self.diet_agent.filter_recipes(all_recipes, user)
        if not compliant_recipes:
            conv_context = "ANALYSIS: " + json.dumps(analysis)
            save_result = self.memory_agent.save_user_profile(
                user, conversation_context=conv_context
            )
            # IMPORTANT: return 4 values even in this branch
            return [], analysis, user, save_result

        # 7. Rank by ingredients (LLM)
        ingredient_ranked = self.ingredient_agent.recommend(
            compliant_recipes,
            user,
            top_k=50,
            temperature=temperature,
        )

        # 8. Rank by objective (LLM)
        final_recipes = self.objective_agent.recommend(
            ingredient_ranked,
            user,
            top_k=10,
            temperature=temperature,
        )

        # 9. Save updated user profile + conversation summary
        conv_context = "ANALYSIS: " + json.dumps(analysis)
        save_result = self.memory_agent.save_user_profile(
            user, conversation_context=conv_context
        )

        # IMPORTANT: always return 4 values
        return final_recipes, analysis, user, save_result

    # -------------------------------------------------------------
    # Memory wrappers (so example_usage.py can call them)
    # -------------------------------------------------------------
    def get_user_history(self, username: str):
        if not self.memory_agent:
            return {"status": "error", "message": "Memory agent not initialized."}
        return self.memory_agent.get_user_history(username)

    def list_all_users(self):
        if not self.memory_agent:
            return []
        return self.memory_agent.list_all_users()

        return final_recipes, analysis, user, save_result

