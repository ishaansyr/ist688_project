# models.py
from typing import Optional, Set


class Recipe:
    def __init__(
        self,
        recipe_id: str,
        name: str,
        ingredients: Optional[Set[str]] = None,
        diets: Optional[Set[str]] = None,       # e.g. {"vegan", "gluten-free"}
        allergens: Optional[Set[str]] = None,   # e.g. {"peanut", "dairy"}
        calories: Optional[float] = None,
        protein: Optional[float] = None,
        carbs: Optional[float] = None,
        fat: Optional[float] = None,
    ):
        self.id = recipe_id
        self.name = name
        self.ingredients = ingredients or set()
        self.diets = diets or set()
        self.allergens = allergens or set()
        self.calories = calories
        self.protein = protein
        self.carbs = carbs
        self.fat = fat

    def __repr__(self) -> str:
        return f"Recipe(id={self.id!r}, name={self.name!r})"


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
