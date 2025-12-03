# conversational_agent.py

import json
import re
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

        # Short-term per-user memory of last recommendations (in-process)
        # { username: [Recipe, Recipe, ...] }
        self.last_recommendations = {}

    # ---------- Helpers for index-based references ----------

    def _extract_index_from_message(self, message: str):
        """
        Try to detect references like 'number 1', '1', '1st', 'first one', etc.
        Returns an integer index (1-based) or None.
        """
        msg = message.lower()

        # Explicit "number X" pattern
        m = re.search(r"number\s+(\d+)", msg)
        if m:
            return int(m.group(1))

        # 1st / 2nd / 3rd / 4th patterns
        m = re.search(r"\b(\d+)(st|nd|rd|th)\b", msg)
        if m:
            return int(m.group(1))

        # "first / second / third" words
        word_to_idx = {
            "first": 1,
            "second": 2,
            "third": 3,
            "fourth": 4,
            "fifth": 5,
        }
        for w, idx in word_to_idx.items():
            if w in msg:
                return idx

        # Bare single digit (avoid treating years etc. as indexes)
        m = re.search(r"\b([1-9])\b", msg)
        if m:
            return int(m.group(1))

        return None

    def _is_detail_request(self, message: str) -> bool:
        """
        Heuristic: decide whether the user is asking for details of a specific recipe
        rather than new suggestions.
        """
        msg = message.lower()
        keywords = [
            "recipe",
            "ingredients",
            "how do i make",
            "how to make",
            "steps",
            "method",
            "instructions",
        ]
        return any(k in msg for k in keywords)

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
        "inventory": ["chicken", "broccoli", "milk", "potatoes", ...],
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
            "existing_inventory": sorted(list(user.inventory)),
            "objective": user.objective,
        }

        default_result = {
            "objective": user.objective,
            "dietary_restrictions": list(user.dietary_restrictions),
            "allergies": list(user.allergies),
            "likes": list(user.likes),
            "dislikes": list(user.dislikes),
            "inventory": list(user.inventory),
            "wants_meal_plan": False,
            "time_horizon": None,
            "query": message,
        }

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
                                    "they want a meal plan for a day or a week. "
                                    "Also extract an 'inventory' list of all items the user says they "
                                    "currently have in their fridge or pantry. "
                                    "Provide a concise 'query' string summarising what kind of recipes "
                                    "to search for (e.g. 'high protein vegan dinners with chickpeas')."
                                ),
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({
                                    "message": message,
                                    "current_user": current_user,
                                }),
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
    
    def _build_recipe_query(self, analysis: dict, message: str) -> str | None:
        """
        Build a concise query string suitable for external recipe APIs.

        Priority:
        1) Use inventory items, if available.
        2) Extract a few strong keywords from the message.
        Returns None if nothing meaningful can be formed.
        """

        # 1. Use inventory if present
        inv_list = [i.strip() for i in analysis.get("inventory", []) if i and i.strip()]
        if inv_list:
            return ", ".join(inv_list)

        # 2. Extract simplified keywords from message
        text = message.lower()

        # Remove common phrases that add no query value
        remove_phrases = [
            "i am", "i'm", "please", "can you", "could you", "suggest", "give me",
            "recommend", "recipes", "recipe", "in my inventory", "currently have",
            "trying to", "trying", "bulk", "cut", "lose weight", "healthy", "healthier",
            "allergic to", "allergy", "inventory", "dietary", "preference"
        ]
        for phrase in remove_phrases:
            text = text.replace(phrase, " ")

        tokens = re.findall(r"[a-z]+", text)
        stopwords = {
            "a", "an", "the", "for", "and", "with", "or", "of", "on", "in", "to", "my", "is", "am"
        }

        keywords = [t for t in tokens if t not in stopwords]

        # Only keep concise, content-heavy terms
        if len(keywords) >= 2:
            return " ".join(keywords[:6])

        # 3. If nothing left, signal that query formation failed
        return None

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

        # --- INVENTORY UPDATE ---
        # If new inventory is mentioned, replace old one completely (snapshot approach)
        if analysis.get("inventory"):
            user.inventory = set(analysis["inventory"])

        return user

    # ---------- Macro / nutrient focus inference ----------

    def _infer_focus_nutrient(self, message: str, analysis: dict):
        """
        Infer which nutrient should be emphasised for reranking.
        Returns 'protein', 'fiber', 'calories', or None.
        """
        text = (message + " " + str(analysis.get("objective") or "")).lower()

        if "fibre" in text or "fiber" in text:
            return "fiber"

        if "protein" in text or "high protein" in text:
            return "protein"

        if any(word in text for word in ["cutting", "calorie deficit", "low calorie", "weight loss"]):
            return "calories"

        obj = (analysis.get("objective") or "").lower()
        if obj in {"bulking", "muscle gain", "high protein"}:
            return "protein"
        if obj in {"weight loss", "cutting"}:
            return "calories"

        return None

    def _sort_by_focus_nutrient(self, recipes, focus_nutrient):
        """
        Enforce descending order by the focus nutrient on the final list.
        """
        if not focus_nutrient or not recipes:
            return recipes

        key_map = {
            "protein": "protein",
            "fiber": "fiber",
            "fibre": "fiber",
            "calories": "calories",
            "energy": "calories",
        }
        field = key_map.get(focus_nutrient.lower())
        if not field:
            return recipes

        return sorted(
            recipes,
            key=lambda r: getattr(r, field, 0) or 0.0,
            reverse=True,
        )

    # ---------- Orchestration + Memory ----------

    def handle_message(self, username, message, temperature=0.2, extra_inventory=None):
        """
        Main entry point for the app.

        There are now two modes:

        A) Detail mode:
           - If the user refers to 'number 1' / 'first one' etc., and
             we have last_recommendations[username],
             we directly return that specific recipe (no new retrieval).

        B) Normal mode:
           - Full analysis → retrieval → dietary filter → LLM ranking.

        Returns:
          final_recipes, analysis, updated_user, save_result
        """

         # 0. Clear-inventory command (before anything else)
        if any(phrase in message.lower() for phrase in ["clear my fridge", "clear my inventory", "reset inventory"]):
            user = self.memory_agent.load_user_profile(username)
            if user is None:
                user = UserProfile(user_id=username, name=username)

            user.inventory = []
            save_result = self.memory_agent.save_user_profile(
                user, conversation_context="INVENTORY_CLEARED"
            )

            print(f"[INFO] Cleared inventory for user {username}")
            return [], {"action": "inventory_cleared"}, user, save_result        
        # 1. Load or create user profile
        user = self.memory_agent.load_user_profile(username)
        if user is None:
            user = UserProfile(user_id=username, name=username)

        # 1a. Check if this is a detail request referring to previous list
        last_list = self.last_recommendations.get(username, [])
        idx = self._extract_index_from_message(message)
        if last_list and idx is not None and 1 <= idx <= len(last_list) and self._is_detail_request(message):
            selected = last_list[idx - 1]

            # Build a minimal analysis payload so the UI can see what happened
            analysis = {
                "mode": "detail",
                "detail_index": idx,
                "detail_recipe_name": selected.name,
            }

            # Save to Excel memory
            conv_context = "DETAIL_REQUEST: index {} -> {}".format(idx, selected.name)
            save_result = self.memory_agent.save_user_profile(
                user, conversation_context=conv_context
            )

            # Return only the selected recipe; do not fabricate anything
            final_recipes = [selected]

            # Keep last_recommendations as they are, so user can still refer to 2, 3, etc.
            self.last_recommendations[username] = last_list

            return final_recipes, analysis, user, save_result

        # 2. Normal mode: interpret message with LLM
        analysis = self._analyse_message_with_llm(user, message, temperature=temperature)

        # 2a. Merge extra_inventory (from fridge image) into analysis["inventory"]
        if extra_inventory:
            existing_inventory = analysis.get("inventory") or []
            merged_inventory = list({*existing_inventory, *extra_inventory})
            analysis["inventory"] = merged_inventory

        # 3. Update user profile from analysis (including merged inventory)
        user = self._update_user_profile_from_analysis(user, analysis)

        # 4. Build a query and infer nutrient focus
        query = self._build_recipe_query(analysis, message)
        if not query:
            print("[WARNING] No valid query could be formed from user input.")
            save_result = self.memory_agent.save_user_profile(
                user, conversation_context="NO_VALID_QUERY"
            )
            return [], analysis, user, save_result

        focus_nutrient = self._infer_focus_nutrient(message, analysis)
        analysis["focus_nutrient"] = focus_nutrient
        include_usda = self._wants_usda_snacks_or_macros(message, analysis)

        # 5. Fetch candidate recipes (deterministic + reranking in API agent)
        all_recipes = self.api_agent.fetch_recipes(
            query,
            focus_nutrient=focus_nutrient,
            top_k=30,
            include_usda=include_usda,
        )
        print(f"[DEBUG] all_recipes: {len(all_recipes)}")

        # 6. Apply dietary restrictions and allergies (deterministic)
        compliant_recipes = self.diet_agent.filter_recipes(all_recipes, user)
        print(f"[DEBUG] compliant_recipes: {len(compliant_recipes)}")
        if not compliant_recipes:
            conv_context = "ANALYSIS: " + json.dumps(analysis)
            save_result = self.memory_agent.save_user_profile(
                user, conversation_context=conv_context
            )
            self.last_recommendations[username] = []
            return [], analysis, user, save_result

        # 7. Rank by ingredients (LLM)
        ingredient_ranked = self.ingredient_agent.recommend(
            compliant_recipes,
            user,
            top_k=50,
            temperature=temperature,
        )
        print(f"[DEBUG] ingredient_ranked: {len(ingredient_ranked)}")

        # 8. Rank by objective (LLM)
        final_recipes = self.objective_agent.recommend(
            ingredient_ranked,
            user,
            top_k=10,
            temperature=temperature,
        )
        print(f"[DEBUG] final_recipes: {len(final_recipes)}")

        # 9. Enforce descending nutrient order on the final list
        final_recipes = self._sort_by_focus_nutrient(final_recipes, focus_nutrient)

        # 10. Save updated user profile + conversation summary
        conv_context = "ANALYSIS: " + json.dumps(analysis)
        save_result = self.memory_agent.save_user_profile(
            user, conversation_context=conv_context
        )

        # 11. Store final_recipes as last recommendations for this user
        self.last_recommendations[username] = list(final_recipes)

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

    def _wants_usda_snacks_or_macros(self, message: str, analysis: dict) -> bool:
        text = (message + " " + str(analysis.get("objective") or "")).lower()

        snack_words = [
            "snack", "snacks", "protein bar", "bars",
            "ready to eat", "grab and go", "on the go"
        ]
        macro_words = [
            "macros", "macro info", "nutritional info",
            "nutrition info", "calories", "grams of protein",
            "macro breakdown"
        ]

        return any(w in text for w in snack_words + macro_words)
