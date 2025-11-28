# objective_agent.py

import json
from openai import OpenAI

class ObjectiveAgent:
    """
    Uses gpt-4o-mini (Responses API) to re-rank recipes according to user's objective:
    e.g. 'cutting', 'bulking', 'healthier', etc.
    """

    def __init__(self, client=None, model="gpt-4o-mini"):
        self.client = client or OpenAI()
        self.model = model

    def _build_payload(self, recipes, user):
        recipe_summaries = []
        for r in recipes:
            recipe_summaries.append(
                {
                    "id": r.id,
                    "name": r.name,
                    "calories": r.calories,
                    "protein": r.protein,
                    "carbs": r.carbs,
                    "fat": r.fat,
                }
            )

        payload = {
            "objective": user.objective or "healthier",
            "recipes": recipe_summaries,
        }
        return payload

    def _call_llm_for_ranking(self, payload, temperature):
        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "You are a nutrition-aware assistant that ranks recipes according "
                                "to a user's high-level objective.\n"
                                "- If objective is 'cutting' or 'fat loss', prefer lower-calorie meals "
                                "with reasonable protein.\n"
                                "- If objective is 'bulking' or 'muscle gain', prefer higher-calorie "
                                "and high-protein meals.\n"
                                "- If objective is 'healthier' or unspecified, prefer moderate calories, "
                                "decent protein, and not excessive fat.\n\n"
                                "Return ONLY valid JSON with keys:\n"
                                "- 'ranked_ids': list of recipe IDs from best to worst\n"
                                "- 'notes': a short text explanation (optional).\n"
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(payload),
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
        return content

    def recommend(self, recipes, user, top_k=10, temperature=0.2):
        """
        Ask gpt-4o-mini to re-rank recipes based on user's objective.

        Expected JSON:

        {
          "ranked_ids": ["id2", "id1", ...],
          "notes": "Optional explanation text"
        }
        """

        payload = self._build_payload(recipes, user)

        try:
            content = self._call_llm_for_ranking(payload, temperature)
            data = json.loads(content)
            ranked_ids = data.get("ranked_ids", [])
            # notes = data.get("notes", "")  # use in UI/LLM response if needed
        except Exception:
            ranked_ids = [r.id for r in recipes]

        id_to_recipe = {r.id: r for r in recipes}
        ranked_recipes = []

        for rid in ranked_ids:
            recipe = id_to_recipe.get(rid)
            if recipe is not None and recipe not in ranked_recipes:
                ranked_recipes.append(recipe)

        for r in recipes:
            if r not in ranked_recipes:
                ranked_recipes.append(r)

        return ranked_recipes[:top_k]
