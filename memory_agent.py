# memory_agent.py
import pandas as pd
from typing import Optional, Dict, Any
from models import UserProfile
import json
import os


class MemoryAgent:
    """
    Agent responsible for long-term memory stored in an Excel sheet.
    This version is fully consistent and error-free. 
    """

    # ---------------------------------------------------------
    # INITIALISATION
    # ---------------------------------------------------------
    def __init__(self, excel_file_path: str):
        self.excel_file_path = excel_file_path

        # Ensure directory exists
        directory = os.path.dirname(excel_file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        # Create file if missing
        if not os.path.exists(excel_file_path):
            df = pd.DataFrame({
                "UserName": [],
                "DietRules": [],
                "ConvSummary": []
            })
            df.to_excel(excel_file_path, index=False)

        # Load workbook
        self.df = pd.read_excel(excel_file_path)

        # Ensure required columns exist
        for col in ["UserName", "DietRules", "ConvSummary"]:
            if col not in self.df.columns:
                self.df[col] = ""

    # ---------------------------------------------------------
    # LOAD USER PROFILE
    # ---------------------------------------------------------
    def load_user_profile(self, username: str) -> Optional[UserProfile]:
        """
        Converts row in Excel → UserProfile object
        """
        try:
            if username not in self.df["UserName"].values:
                return None

            row = self.df[self.df["UserName"] == username].iloc[0]

            profile = UserProfile(
                user_id=username,
                name=username
            )

            # Load restrictions
            if pd.notna(row["DietRules"]) and row["DietRules"] != "":
                profile.dietary_restrictions = self._parse_dietary_restrictions(row["DietRules"])

            # Load conversation summary → profile fields
            if pd.notna(row["ConvSummary"]) and row["ConvSummary"] != "":
                data = self._parse_conversation_summary(row["ConvSummary"])
                self._update_profile_from_summary(profile, data)

            return profile

        except Exception as e:
            print(f"Error loading user profile: {e}")
            return None

    # ---------------------------------------------------------
    # SAVE USER PROFILE
    # ---------------------------------------------------------
    def save_user_profile(self, user: UserProfile, conversation_context: str = None) -> Dict[str, Any]:
        """
        Writes UserProfile back into Excel
        """
        try:
            username = user.user_id

            diet_rules_str = self._format_dietary_restrictions(user)
            summary_str = self._create_conversation_summary(user, conversation_context)

            if username in self.df["UserName"].values:
                self.df.loc[self.df["UserName"] == username, "DietRules"] = diet_rules_str
                self.df.loc[self.df["UserName"] == username, "ConvSummary"] = summary_str
            else:
                new_row = pd.DataFrame({
                    "UserName": [username],
                    "DietRules": [diet_rules_str],
                    "ConvSummary": [summary_str]
                })
                self.df = pd.concat([self.df, new_row], ignore_index=True)

            self.df.to_excel(self.excel_file_path, index=False)
            return {"status": "success"}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ---------------------------------------------------------
    # UPDATE CONVERSATION MEMORY
    # ---------------------------------------------------------
    def update_conversation_memory(self, username: str, new_context: str, append: bool = True):
        if username not in self.df["UserName"].values:
            return {"status": "error", "message": "User not found"}

        old = self.df[self.df["UserName"] == username]["ConvSummary"].iloc[0]

        if append and pd.notna(old) and old != "":
            updated = f"{old}\n{new_context}"
        else:
            updated = new_context

        self.df.loc[self.df["UserName"] == username, "ConvSummary"] = updated
        self.df.to_excel(self.excel_file_path, index=False)
        return {"status": "success"}

    # ---------------------------------------------------------
    # API FOR YOUR example_usage.py
    # ---------------------------------------------------------
    def get_user_history(self, username: str):
        if username not in self.df["UserName"].values:
            return {"status": "error", "message": "User not found"}

        row = self.df[self.df["UserName"] == username].iloc[0]
        return {
            "status": "success",
            "UserName": row["UserName"],
            "DietRules": row["DietRules"],
            "ConvSummary": row["ConvSummary"]
        }

    def list_all_users(self):
        return list(self.df["UserName"].dropna().unique())

    # ---------------------------------------------------------
    # HELPER METHODS
    # ---------------------------------------------------------
    def _parse_dietary_restrictions(self, s: str) -> set:
        if not s:
            return set()
        return {x.strip().lower() for x in s.split(",") if x.strip()}

    def _format_dietary_restrictions(self, user: UserProfile) -> str:
        rules = list(user.dietary_restrictions)
        allergies = [f"{a} allergy" for a in user.allergies]
        combined = rules + allergies
        return ", ".join(combined)

    def _create_conversation_summary(self, user: UserProfile, ctx: str = None) -> str:
        payload = {
            "objective": user.objective,
            "likes": list(user.likes),
            "dislikes": list(user.dislikes),
            "inventory": list(user.inventory),
            "allergies": list(user.allergies),
        }
        base = f"PROFILE_DATA: {json.dumps(payload)}"
        return base if not ctx else base + "\n" + f"CONTEXT: {ctx}"

    def _parse_conversation_summary(self, s: str) -> Dict[str, Any]:
        out = {}
        try:
            if "PROFILE_DATA:" in s:
                json_part = s.split("PROFILE_DATA:", 1)[1].split("\n")[0].strip()
                out = json.loads(json_part)
        except:
            pass
        return out

    def _update_profile_from_summary(self, user: UserProfile, d: Dict[str, Any]):
        if d.get("objective"):
            user.objective = d["objective"]
        if "likes" in d:
            user.likes = set(d["likes"])
        if "dislikes" in d:
            user.dislikes = set(d["dislikes"])
        if "inventory" in d:
            user.inventory = set(d["inventory"])
        if "allergies" in d:
            user.allergies = set(d["allergies"])
