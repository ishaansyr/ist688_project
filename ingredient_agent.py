# ingredient_agent.py

import json
from openai import OpenAI


class IngredientAgent:
    """
    Uses gpt-4o-mini (Responses API) to rank recipes based on:
    - user likes / dislikes
    - pantry / inventory ingredients
    """

    def __init__(self, client=None, model="gpt-4o-mini"):
        self.client = client or OpenAI()
        self.model = model

    def _build_payload(self, recipes, user):
        # Convert Recipe objects into simple dicts for the LLM
        recipe_summaries = []
        for r in recipes:
            recipe_summaries.append(
                {
                    "id": r.id,
                    "name": r.name,
                    "ingredients": sorted(list(r.ingredients)),
                }
            )

        user_info = {
            "likes": sorted(list(user.likes)),
            "dislikes": sorted(list(user.dislikes)),
            "inventory": sorted(list(user.inventory)),
        }
        return {"user": user_info, "recipes": recipe_summaries}

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
                                "You are an assistant that ranks recipes based on a user's "
                                "ingredient preferences and pantry. "
                                "Prioritise recipes that:\n"
                                "- contain more liked ingredients\n"
                                "- avoid disliked ingredients\n"
                                "- use ingredients already in the user's inventory where possible.\n\n"
                                "Return ONLY valid JSON with a single key 'ranked_ids', "
                                "whose value is a list of recipe IDs ordered from best to worst."
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

        # Extract plain text from Responses API output
        output = response.output[0]
        text_chunks = []
        for c in output.content:
            if c.type == "output_text":
                text_chunks.append(c.text)
        content = "".join(text_chunks).strip()
        return content

    def recommend(self, recipes, user, top_k=10, temperature=0.2):
        """
        Ask gpt-4o-mini to rank recipes.

        Expected JSON from the model:

        {
          "ranked_ids": ["id3", "id1", "id2", ...]
        }
        """

        payload = self._build_payload(recipes, user)

        try:
            content = self._call_llm_for_ranking(payload, temperature)
            data = json.loads(content)
            ranked_ids = data.get("ranked_ids", [])
        except Exception:
            # Fallback: keep original order if parsing or API fails
            ranked_ids = [r.id for r in recipes]

        # Map ids back to Recipe objects
        id_to_recipe = {r.id: r for r in recipes}
        ranked_recipes = []

        for rid in ranked_ids:
            recipe = id_to_recipe.get(rid)
            if recipe is not None and recipe not in ranked_recipes:
                ranked_recipes.append(recipe)

        # Append any recipes the model omitted
        for r in recipes:
            if r not in ranked_recipes:
                ranked_recipes.append(r)

        return ranked_recipes[:top_k]
