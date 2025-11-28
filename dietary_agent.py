# dietary_agent.py

from models import Recipe, UserProfile


class DietaryRestrictionAgent:
    """
    Final filter: ensures recipes comply with dietary restrictions and allergies.
    """

    def _matches_lifestyle(self, recipe, restrictions):
        # restrictions: e.g. {"vegan", "vegetarian", "pescetarian", "gluten-free"}
        recipe_diets_lower = set(d.lower() for d in recipe.diets)

        for restriction in restrictions:
            r_lower = restriction.lower()
            if r_lower in {"vegan", "vegetarian", "pescetarian", "gluten-free"}:
                if r_lower not in recipe_diets_lower:
                    return False
        return True

    def _violates_allergies(self, recipe, allergies):
        recipe_allergens_lower = set(a.lower() for a in recipe.allergens)

        for allergy in allergies:
            if allergy.lower() in recipe_allergens_lower:
                return True
        return False

    def filter_recipes(self, recipes, user):
        filtered = []

        for recipe in recipes:
            if not self._matches_lifestyle(recipe, user.dietary_restrictions):
                continue
            if self._violates_allergies(recipe, user.allergies):
                continue
            filtered.append(recipe)

        return filtered
