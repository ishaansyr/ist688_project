# api_agent.py

from models import Recipe


class APIDataError(Exception):
    pass


class APIDataAgent:
    """
    Responsible for fetching recipe and nutrition data from:
    - TheMealDB
    - Spoonacular
    - USDA FoodData Central

    Currently uses a mock implementation; real HTTP calls can be added later.
    """

    def __init__(self):
        self.themealdb_base = "https://www.themealdb.com/api/json/v1/1"
        self.spoonacular_base = "https://api.spoonacular.com"
        self.usda_base = "https://api.nal.usda.gov/fdc"

    def _mock_fetch_from_themealdb(self, query):
        # Replace this stub with real HTTP requests later
        return [
            {
                "id": "meal1",
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

    def _normalise_recipe(self, raw):
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

    def fetch_recipes(self, query):
        """
        High-level entry point for other agents.
        Currently uses mocked TheMealDB data.
        """
        try:
            raw_results = self._mock_fetch_from_themealdb(query)
        except Exception as e:
            raise APIDataError("Failed to fetch recipes: {}".format(e))

        recipes = []
        for raw in raw_results:
            recipes.append(self._normalise_recipe(raw))
        return recipes
