# api_agent.py

import os
import math
from typing import List, Optional, Dict, Any

import requests
from models import Recipe

# Try to use Streamlit secrets when available
try:
    import streamlit as st
    _SECRETS: Dict[str, Any] = st.secrets
except Exception:
    _SECRETS = {}

# OpenAI embeddings
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore


class APIDataError(Exception):
    pass


class APIDataAgent:
    """
    Fetches and normalises recipe / nutrition data from:
    - Spoonacular (primary recipe source + macros)
    - USDA FoodData Central (foods + macros, optional)

    Also supports post-retrieval reranking based on:
    - semantic similarity (query vs recipe text)
    - ingredient coverage (query tokens present in name/ingredients)
    - a focus nutrient (e.g. 'protein', 'fiber', 'calories')
    """

    def __init__(self):
        # Base URLs
        self.spoonacular_base = "https://api.spoonacular.com"
        self.usda_base = "https://api.nal.usda.gov/fdc"

        # API keys: prefer Streamlit secrets, fall back to env vars
        self.spoonacular_key = _SECRETS.get("SPOONACULAR_API_KEY") or os.getenv(
            "SPOONACULAR_API_KEY"
        )
        self.usda_key = _SECRETS.get("USDA_API_KEY") or os.getenv("USDA_API_KEY")
        self.openai_key = _SECRETS.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")

        # OpenAI client for embeddings
        self._client = None
        if OpenAI is not None and self.openai_key:
            self._client = OpenAI(api_key=self.openai_key)

    def _extract_nutrient(self, raw, nutrient_name):
        """Extract a nutrient value by name from USDA's nutrient list."""
        for nutrient in raw.get("foodNutrients", []):
            if nutrient_name.lower() in nutrient.get("nutrientName", "").lower():
                return nutrient.get("value")
        return None

    # ------------------------------------------------------------------
    # Spoonacular (primary source)
    # ------------------------------------------------------------------
    def _fetch_from_spoonacular(self, query: str, page_size: int = 10) -> List[dict]:
        """
        Use Spoonacular's complexSearch endpoint to get recipes with
        ingredients + nutrition in a single call.

        Returns a list of dicts compatible with _normalise_recipe.
        """
        if not self.spoonacular_key:
            return []

        url = f"{self.spoonacular_base}/recipes/complexSearch"
        params = {
            "query": query,
            "number": page_size,
            "addRecipeInformation": True,   # include instructions, etc.
            "addRecipeNutrition": True,     # include nutrition.nutrients
            "fillIngredients": True,        # populate extendedIngredients
            "apiKey": self.spoonacular_key,
        }

        print(f"[SPOONACULAR] Calling {url} with params={params}")
        resp = requests.get(url, params=params, timeout=10)
        print(f"[SPOONACULAR] Status: {resp.status_code}")

        # Handle quota / error cases explicitly
        try:
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print("[SPOONACULAR] Error parsing response:", e)
            print(resp.text[:500])
            return []

        # Quota exceeded message often comes back as JSON with 'message' field
        msg = (data.get("message") or "").lower() if isinstance(data, dict) else ""
        if "daily points limit" in msg:
            print("[SPOONACULAR] Daily points limit reached.")
            return []

        results = data.get("results") or []
        recipes: List[dict] = []

        for r in results:
            # Ingredients
            ext_ings = r.get("extendedIngredients") or []
            ingredients: List[str] = []
            for ing in ext_ings:
                name_clean = (
                    ing.get("nameClean")
                    or ing.get("original")
                    or ing.get("name")
                )
                if name_clean:
                    ingredients.append(name_clean)

            # Diet tags
            diets = r.get("diets") or []

            # Nutrition
            cal = prot = carb = fat = fiber = None
            nutrients = (r.get("nutrition") or {}).get("nutrients") or []
            for n in nutrients:
                nname = (n.get("name") or "").lower()
                val = n.get("amount")
                if not isinstance(val, (int, float)):
                    continue
                if "calories" in nname:
                    cal = val if cal is None else cal
                elif "protein" in nname:
                    prot = val if prot is None else prot
                elif "carbohydrate" in nname:
                    carb = val if carb is None else carb
                elif "fat" in nname:
                    fat = val if fat is None else fat
                elif "fiber" in nname or "fibre" in nname:
                    fiber = val if fiber is None else fiber

            recipes.append(
                {
                    "id": f"spoon_{r.get('id')}",
                    "name": r.get("title") or "Unknown Recipe",
                    "ingredients": ingredients,
                    "diets": diets,
                    "allergens": [],
                    "calories": cal,
                    "protein": prot,
                    "carbs": carb,
                    "fat": fat,
                    "fiber": fiber,
                    # you prefer to use source_url rather than inline instructions
                    "instructions": None,
                    "source_url": r.get("sourceUrl"),
                    "source": "spoonacular",
                }
            )

        return recipes

    # ------------------------------------------------------------------
    # USDA FoodData Central (optional)
    # ------------------------------------------------------------------
    def _fetch_from_usda(self, query: str, page_size: int = 10) -> List[dict]:
        """
        Uses USDA FoodData Central 'foods/search' endpoint to get foods + macros.
        Only called if USDA_API_KEY is configured.
        """
        if not self.usda_key:
            return []

        url = f"{self.usda_base}/v1/foods/search"
        params = {
            "api_key": self.usda_key,
            "query": query,
            "pageSize": page_size,
            "dataType": "Foundation,Branded",
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        foods = data.get("foods") or []
        results: List[dict] = []

        for food in foods:
            desc = food.get("description") or "USDA food"
            nutrients = food.get("foodNutrients", []) or []

            cal = prot = carb = fat = fiber = None
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
                elif "fiber" in name:
                    fiber = val if fiber is None else fiber

            results.append(
                {
                    "id": f"usda_{food.get('fdcId')}",
                    "name": desc,
                    "ingredients": [desc],  # single-food "recipe"
                    "diets": [],
                    "allergens": [],
                    "calories": cal,
                    "protein": prot,
                    "carbs": carb,
                    "fat": fat,
                    "fiber": fiber,
                    "source": "usda",
                    "instructions": None,
                    "source_url": f"https://fdc.nal.usda.gov/fdc-app.html#/food/{food.get('fdcId')}",
                }
            )

        return results

    # ------------------------------------------------------------------
    # Embeddings + similarity
    # ------------------------------------------------------------------
    def _embed(self, texts: List[str]) -> List[List[float]]:
        """
        Returns embedding vectors for a list of texts.
        If no OpenAI client is available, returns empty list.
        """
        if not self._client:
            return []

        resp = self._client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
        )
        return [d.embedding for d in resp.data]

    @staticmethod
    def _cosine(u: List[float], v: List[float]) -> float:
        if not u or not v or len(u) != len(v):
            return 0.0
        dot = sum(a * b for a, b in zip(u, v))
        nu = math.sqrt(sum(a * a for a in u))
        nv = math.sqrt(sum(b * b for b in v))
        if nu == 0 or nv == 0:
            return 0.0
        return dot / (nu * nv)

    # ------------------------------------------------------------------
    # Reranking helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_recipe_text(raw: dict) -> str:
        name = raw.get("name", "")
        ingredients = ", ".join(raw.get("ingredients", []))
        diets = ", ".join(raw.get("diets", []))
        source = raw.get("source", "")
        return f"{name}. Ingredients: {ingredients}. Diets: {diets}. Source: {source}."

    @staticmethod
    def _extract_query_tokens(query: str) -> List[str]:
        """
        Very simple heuristic tokeniser for potential ingredient words.
        Filters out some common non-ingredient words.
        """
        query = query.lower()
        tokens = [t.strip(".,!?") for t in query.split()]
        stop = {
            "high",
            "low",
            "protein",
            "fibre",
            "fiber",
            "fat",
            "carb",
            "carbs",
            "calorie",
            "calories",
            "healthy",
            "recipe",
            "recipes",
            "meal",
            "meals",
            "for",
            "with",
            "and",
            "please",
        }
        return [t for t in tokens if t and t not in stop]

    @staticmethod
    def _ingredient_coverage(raw: dict, tokens: List[str]) -> float:
        if not tokens:
            return 1.0  # no explicit ingredient hints → neutral
        name = (raw.get("name") or "").lower()
        ingredients = [i.lower() for i in raw.get("ingredients", [])]
        hits = 0
        for t in tokens:
            if t in name or any(t in ing for ing in ingredients):
                hits += 1
        return hits / len(tokens)

    @staticmethod
    def _nutrient_value(raw: dict, focus_nutrient: Optional[str]) -> float:
        """
        Returns the nutrient value we care about for reranking.
        focus_nutrient can be 'protein', 'fiber', 'fat', 'carbs', 'calories', etc.
        """
        if not focus_nutrient:
            return 0.0
        key = focus_nutrient.lower()
        mapping = {
            "protein": "protein",
            "fiber": "fiber",
            "fibre": "fiber",
            "fat": "fat",
            "carb": "carbs",
            "carbs": "carbs",
            "calorie": "calories",
            "calories": "calories",
            "energy": "calories",
        }
        field = mapping.get(key)
        if not field:
            return 0.0
        val = raw.get(field)
        if isinstance(val, (int, float)):
            return float(val)
        return 0.0

    def _rerank(
        self,
        query: str,
        raw_results: List[dict],
        focus_nutrient: Optional[str],
        top_k: int,
    ) -> List[dict]:
        """
        Reranks raw results using:
        - semantic similarity (if embeddings available)
        - ingredient coverage (query tokens vs ingredients)
        - focus nutrient value (sorted descending)
        """
        if not raw_results:
            return []

        # Build texts for embeddings
        recipe_texts = [self._build_recipe_text(r) for r in raw_results]
        tokens = self._extract_query_tokens(query)

        # Embeddings
        if self._client:
            embeds = self._embed([query] + recipe_texts)
            if embeds:
                query_vec = embeds[0]
                recipe_vecs = embeds[1:]
            else:
                query_vec, recipe_vecs = None, []
        else:
            query_vec, recipe_vecs = None, []

        scored = []
        for idx, raw in enumerate(raw_results):
            cov = self._ingredient_coverage(raw, tokens)
            nutr = self._nutrient_value(raw, focus_nutrient)

            # Log-scale nutrient so very high values don’t dominate
            nutr_score = math.log(1 + max(nutr, 0)) if nutr else 0.0

            if query_vec is not None and idx < len(recipe_vecs):
                sim = self._cosine(query_vec, recipe_vecs[idx])
            else:
                sim = 0.0

            # Weighted combination
            score = (
                0.4 * cov +      # ingredient coverage
                0.4 * sim +      # semantic similarity
                0.2 * nutr_score # macro emphasis
            )

            scored.append({
                "score": score,
                "nutr_value": nutr or 0.0,
                "recipe": raw,
            })

        # Sort primarily by focus nutrient (descending), then by weighted score
        scored.sort(key=lambda x: (x["nutr_value"], x["score"]), reverse=True)

        top = [s["recipe"] for s in scored[:top_k]]
        return top

    # ------------------------------------------------------------------
    # Normalisation to Recipe objects
    # ------------------------------------------------------------------
    def _normalise_recipe(self, raw: dict) -> Recipe:
        """
        Convert a raw recipe dictionary into a Recipe object.
        If raw is already a Recipe instance, just return it.
        """
        if isinstance(raw, Recipe):
            return raw

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
            fiber=raw.get("fiber"),
            instructions=raw.get("instructions"),
            source_url=raw.get("source_url"),
        )

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------
    def fetch_recipes(
        self,
        query: str,
        focus_nutrient: Optional[str] = None,
        top_k: int = 30,
        include_usda: bool = False,
    ) -> List[Recipe]:
        """
        High-level entry used by other agents.

        - query: natural language query
        - focus_nutrient: which nutrient to emphasise in reranking
          (e.g. 'protein', 'fiber', 'calories')
        - top_k: how many recipes to keep after reranking
        - include_usda: whether to include USDA 'foods' in the candidate pool

        Returns a list of Recipe objects.
        """
        try:
            raw: List[dict] = []

            # 1. Collect raw dicts from external APIs
            raw.extend(self._fetch_from_spoonacular(query))

            if include_usda:
                raw.extend(self._fetch_from_usda(query))

            # Guard: keep only dicts (avoid accidentally mixing in Recipe objects)
            raw = [r for r in raw if isinstance(r, dict)]

            if not raw:
                return []

            # 2. Rerank raw dicts
            reranked_dicts = self._rerank(query, raw, focus_nutrient, top_k)
            #print(f"[DEBUG] Query: {query}")
            #print(f"[DEBUG] Focus Nutrient: {focus_nutrient}")
            #print(f"[DEBUG] Recipes fetched: {len(reranked_dicts)}")
            #if reranked_dicts:
            #    print(f"[DEBUG] Example recipe: {reranked_dicts[0].get('name', 'N/A')}")

            # 3. Normalise into Recipe objects
            recipes: List[Recipe] = [self._normalise_recipe(r) for r in reranked_dicts]

            return recipes

        except Exception as e:
            raise APIDataError(f"Failed to fetch recipes: {e}")
