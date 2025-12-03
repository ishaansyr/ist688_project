# models.py
from typing import Optional, Set


# models.py

class Recipe:
    def __init__(
        self,
        recipe_id: str,
        name: str,
        ingredients=None,
        diets=None,
        allergens=None,
        calories=None,
        protein=None,
        carbs=None,
        fat=None,
        fiber=None,
        instructions=None,
        source_url=None,
    ):
        self.recipe_id = recipe_id
        self.id = recipe_id 
        self.name = name
        self.ingredients = ingredients or []
        self.diets = diets or []
        self.allergens = allergens or []
        self.calories = calories
        self.protein = protein
        self.carbs = carbs
        self.fat = fat
        self.fiber = fiber
        self.instructions = instructions  # <-- new
        self.source_url = source_url      # <-- new

    def __repr__(self):
        return f"<Recipe {self.name} ({self.calories} kcal)>"


class UserProfile:
    def __init__(
        self,
        user_id: str,
        name: str,
        age: Optional[int] = None,
        likes: Optional[Set[str]] = None,
        dislikes: Optional[Set[str]] = None,
        dietary_restrictions: Optional[Set[str]] = None,  # e.g. {"vegan", "nut-free"}
        allergies: Optional[Set[str]] = None,             # e.g. {"peanut", "dairy"}
        objective: Optional[str] = None,                  # e.g. "cutting", "bulking"
        inventory: Optional[Set[str]] = None,
    ):
        self.user_id = user_id
        self.name = name
        self.age = age
        self.likes = likes or set()
        self.dislikes = dislikes or set()
        self.dietary_restrictions = dietary_restrictions or set()
        self.allergies = allergies or set()
        self.objective = objective
        self.inventory = inventory or set()

    def __repr__(self) -> str:
        return f"UserProfile(user_id={self.user_id!r}, name={self.name!r})"
