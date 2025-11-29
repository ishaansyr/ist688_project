# api_agent.py

import os
import json
from typing import List

import requests
from models import Recipe

# Try to use Streamlit secrets when available
try:
    import streamlit as st
    _SECRETS = st.secrets
except Exception:
    _SECRETS = {}


class APIDataError(Exception):
    pass


class APIDataAgent:
    """
    Fetches and normalises recipe / nutrition data from:
    - TheMealDB  (recipes)
    - Spoonacular (recipes + macros, optional)
    - USDA FoodData Central (single foods + macros, optional)
    """

    def __init__(self):
        # Base URLs
        self.themealdb_base = "https://www.themealdb.com/api/json/v1/1"
        self.spoonacular_base = "https://api.spoonacular.com"
        self.usda_base = "https://api.nal.usda.gov/fdc"

        # API keys: prefer Streamlit secrets, fall back to env vars
        self.spoonacular_key = _SECRETS.get("SPOONACULAR_API_KEY") or os.getenv(
            "SPOONACULAR_API_KEY"
        )
        self.usda_key = _SECRETS.get("USDA_API_KEY") or os.getenv("USDA_API_KEY")

    # ------------------------------------------------------------------
    # TheMealDB
    # ------------------------------------------------------------------
    def _fetch_from_themealdb(self, query: str) -> List[dict]:
        """
        Search TheMealDB by name. No API key required.
        """
        url = f"{self.themealdb_base}/search.php"
        params = {"s": query}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        meals = data.get("meals") or []
        results: List[dict] = []

        for meal in meals:
            # Collect ingredients from strIngredient1..20
            ingredients = []
            for i in range(1, 21):
                key = f"strIngredient{i}"
                ing = meal.get(key)
                if ing and ing.strip():
                    ingredients.append(ing.strip())

            results.append(
                {
                    "id": f"mealdb_{meal.get('idMeal')}",
                    "name": meal.get("strMeal", "Unknown Meal"),
                    "ingredients": ingredients,
                    "diets": [],        # TheMealDB doesn't encode diets explicitly
                    "allergens": [],    # you could infer later
                    "calories": None,
                    "protein": None,
                    "carbs": None,
                    "fat": None,
                }
            )
        return results

    # ------------------------------------------------------------------
    # Spoonacular (optional)
    # ------------------------------------------------------------------
    def _fetch_from_spoonacular(self, query: str) -> List[dict]:
        """
        Uses Spoonacular's complexSearch endpoint to get recipes + macros.
        Only called if SPOONACULAR_API_KEY is configured.
        """
        if not self.spoonacular_key:
            return []

        url = f"{self.spoonacular_base}/recipes/complexSearch"
        params = {
            "apiKey": self.spoonacular_key,
            "query": query,
            "number": 5,
            "addRecipeNutrition": True,
            "addRecipeInformation": True,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results: List[dict] = []

        for r in data.get("results", []):
            nutrients = {
                n["name"].lower(): n["amount"]
                for n in r.get("nutrition", {}).get("nutrients", [])
                if "name" in n and "amount" in n
            }

            calories = nutrients.get("calories")
            protein = nutrients.get("protein")
            fat = nutrients.get("fat")
            carbs = nutrients.get("carbohydrates")

            ingredients = []
            for ing in r.get("nutrition", {}).get("ingredients", []):
                name = ing.get("name")
                if name:
                    ingredients.append(name)

            results.append(
                {
                    "id": f"spoon_{r.get('id')}",
                    "name": r.get("title", "Unknown Recipe"),
                    "ingredients": ingredients,
                    "diets": r.get("diets", []),
                    "allergens": [],        # could be enriched later
                    "calories": calories,
                    "protein": protein,
                    "carbs": carbs,
                    "fat": fat,
                }
            )
        return results

    # ------------------------------------------------------------------
    # USDA FoodData Central (optional)
    # ------------------------------------------------------------------
    def _fetch_from_usda(self, query: str, page_size: int = 5) -> List[dict]:
        """
        Uses USDA FoodData Central 'foods/search' endpoint to get single-food entries
        with macronutrients. Only called if USDA_API_KEY is configured.
        """
        if not self.usda_key:
            return []

        url = f"{self.usda_base}/v1/foods/search"
        params = {
            "api_key": self.usda_key,
            "query": query,
            "pageSize": page_size,
            # You can tweak this; Foundation + Branded covers a lot.
            "dataType": "Foundation,Branded",
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        foods = data.get("foods") or []
        results: List[dict] = []

        for food in foods:
            desc = food.get("description") or food.get("descriptionShort") or "USDA food"
            nutrients = food.get("foodNutrients", []) or []

            cal = prot = carb = fat = None
            for n in nutrients:
                name = (n.get("nutrientName") or "").lower()
                val = n.get("value")
                if not isinstance(val, (int, float)):
                    continue
                if "energy" in name or "kcal" in name:
                    cal = val if cal is None else cal
                elif "protein" in name:
                    prot = val if prot is None else prot
                elif "carbohydrate" in name:
                    carb = val if carb is None else carb
                elif "total lipid" in name or "fat" in name:
                    fat = val if fat is None else fat

            results.append(
                {
                    "id": f"usda_{food.get('fdcId')}",
                    "name": desc,
                    "ingredients": [desc],  # treat single food as a 1-ingredient "recipe"
                    "diets": [],            # you can later infer e.g. vegetarian/vegan
                    "allergens": [],        # could map from description later
                    "calories": cal,
                    "protein": prot,
                    "carbs": carb,
                    "fat": fat,
                }
            )
        return results

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------
    def _normalise_recipe(self, raw: dict) -> Recipe:
        return Recipe(
            recipe_id=str(raw.get("id")),
            name=raw.get("name", "Unknown Recipe"),
            ingredients=raw.get("ingredients", []),
            diets=raw.get("diets", []),
            allergens=raw.get("allergens", []),
            calories=raw.get("calories"),
            protein=raw.get("protein"),
            carbs=raw.get("carbs"),
            fat=raw.get("fat"),
        )

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------
    def fetch_recipes(self, query: str) -> List[Recipe]:
        """
        High-level entry point used by other agents.

        Strategy:
        - Always query TheMealDB.
        - If Spoonacular key is present, also query Spoonacular.
        - If USDA key is present, also query USDA.
        - If nothing found, fall back to one mock recipe so the system
          never returns an empty list purely because of API failure.
        """
        try:
            results_raw: List[dict] = []

            # TheMealDB (always)
            results_raw.extend(self._fetch_from_themealdb(query))

            # Spoonacular (optional)
            results_raw.extend(self._fetch_from_spoonacular(query))

            # USDA FoodData Central (optional)
            results_raw.extend(self._fetch_from_usda(query))

            if not results_raw:
                # Fallback: simple mock recipe
                results_raw = [
                    {
                        "id": "mock_1",
                        "name": "Mock Chickpea Curry",
                        "ingredients": ["chickpeas", "onion", "garlic", "tomato"],
                        "diets": ["vegan", "gluten-free"],
                        "allergens": [],
                        "calories": 450,
                        "protein": 18,
                        "carbs": 60,
                        "fat": 12,
                    }
                ]

        except Exception as e:
            raise APIDataError(f"Failed to fetch recipes: {e}")

        # Normalise to Recipe objects
        recipes: List[Recipe] = [self._normalise_recipe(r) for r in results_raw]
        return recipes
