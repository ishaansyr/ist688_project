from models import Recipe, UserProfile


class DietaryRestrictionAgent:
    """
    Final filter: ensures recipes comply with dietary restrictions and allergies.
    """

    def __init__(self, debug: bool = False):
        self.debug = debug

        # Canonical mapping for common restriction labels
        self.canonical_map = {
            # gluten-related
            "gluten-free": "gluten free",
            "gluten free": "gluten free",
            "celiac": "gluten free",
            "celiac disease": "gluten free",

            # vegan / vegetarian
            "vegan": "vegan",
            "strict vegan": "vegan",
            "vegetarian": "vegetarian",
            "lacto ovo vegetarian": "lacto ovo vegetarian",

            # pescetarian
            "pescetarian": "pescetarian",
            "pescatarian": "pescetarian",
        }

    def _normalise_restrictions(self, restrictions):
        """
        Map user-facing labels to canonical diet tags that we expect in recipe.diets.
        """
        required_tags = set()
        for r in restrictions:
            r_lower = r.strip().lower()
            if not r_lower:
                continue
            if r_lower in self.canonical_map:
                required_tags.add(self.canonical_map[r_lower])
            else:
                required_tags.add(r_lower)
        return required_tags

    def _matches_lifestyle(self, recipe: Recipe, restrictions):
        """
        Check that the recipe satisfies all required diet tags.
        """
        recipe_diets_lower = {d.lower() for d in (recipe.diets or [])}
        required_tags = self._normalise_restrictions(restrictions)

        if self.debug:
            print(f"[DietaryAgent] Recipe: {recipe.name}")
            print(f"  recipe.diets (norm): {recipe_diets_lower}")
            print(f"  required_tags:       {required_tags}")

        for tag in required_tags:
            # Only enforce tags that are actually diet constraints
            if tag in {"gluten free", "vegan", "vegetarian", "lacto ovo vegetarian", "pescetarian"}:
                if tag not in recipe_diets_lower:
                    if self.debug:
                        print(f"  -> FAIL: missing required tag '{tag}'\n")
                    return False

        if self.debug:
            print("  -> PASS lifestyle\n")
        return True

    def _violates_allergies(self, recipe: Recipe, allergies):
        """
        True if any of the user's allergies are present in recipe.allergens.
        """
        recipe_allergens_lower = {a.lower() for a in (recipe.allergens or [])}
        for allergy in allergies:
            a = allergy.strip().lower()
            if not a:
                continue
            if a in recipe_allergens_lower:
                if self.debug:
                    print(f"[DietaryAgent] Recipe {recipe.name} violates allergy '{a}'")
                return True
        return False

    def filter_recipes(self, recipes, user: UserProfile):
        """
        Keep only recipes that:
        - match all lifestyle restrictions
        - do not violate allergies
        """
        filtered = []
        for recipe in recipes:
            if not self._matches_lifestyle(recipe, user.dietary_restrictions):
                continue
            if self._violates_allergies(recipe, user.allergies):
                continue
            filtered.append(recipe)
        return filtered
