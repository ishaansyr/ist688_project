# example_usage.py
"""
Generated example usage demonstrating the recipe recommendation system with long-term memory. There is an interatice mode where you can genrate your own data, otherswise it generates sysntehic data
"""

from conversational_agent import ConversationalAgent


def main():
    # Initialize the conversational agent with memory
    # Using relative path for Excel file
    excel_path = 'MemoryFiles/TestWorkBook.xlsx'
    agent = ConversationalAgent(excel_file_path=excel_path)
    
    print("=" * 60)
    print("Recipe Recommendation System with Memory")
    print("=" * 60)
    
    # Example 1: New user interaction
    print("\n--- Example 1: New User ---")
    username = "Alice"
    message = "I'm vegan and I'd like some healthy recipes. I love chickpeas but hate broccoli."
    
    recipes, parsed_request, user, _ = agent.handle_message(username, message)
    
    print(f"User: {username}")
    print(f"Message: {message}")
    print(f"Parsed Request: {parsed_request}")
    print(f"User Profile Updated:")
    print(f"  - Dietary Restrictions: {user.dietary_restrictions}")
    print(f"  - Likes: {user.likes}")
    print(f"  - Dislikes: {user.dislikes}")
    print(f"  - Objective: {user.objective}")
    print(f"Recommended Recipes: {[r.name for r in recipes]}")
    
    # Example 2: Returning user
    print("\n--- Example 2: Returning User ---")
    message2 = "I want to start cutting. Can you suggest a meal plan for the week?"
    
    recipes2, parsed_request2, user2, _ = agent.handle_message(username, message2)
    
    print(f"User: {username}")
    print(f"Message: {message2}")
    print(f"Parsed Request: {parsed_request2}")
    print(f"Updated Objective: {user2.objective}")
    print(f"Meal Plan Requested: {parsed_request2['wants_meal_plan']}")
    print(f"Time Horizon: {parsed_request2['time_horizon']}")
    
    # Example 3: Check user history
    print("\n--- Example 3: User History ---")
    history = agent.get_user_history(username)
    if history["status"] == "success":
        print(f"User: {history['UserName']}")
        print(f"Dietary Rules: {history['DietRules']}")
        print(f"Conversation Summary: {history['ConvSummary'][:200]}...")  # First 200 chars
    
    # Example 4: Multiple users
    print("\n--- Example 4: Another User ---")
    username2 = "Bob"
    message3 = "I'm allergic to peanuts and dairy. I want to bulk up. I have chicken and rice."
    
    recipes3, parsed_request3, user3, _ = agent.handle_message(username2, message3)
    
    print(f"User: {username2}")
    print(f"Message: {message3}")
    print(f"User Profile:")
    print(f"  - Allergies: {user3.allergies}")
    print(f"  - Objective: {user3.objective}")
    print(f"  - Inventory: {user3.inventory}")
    
    # Example 5: List all users
    print("\n--- Example 5: All Users in System ---")
    all_users = agent.list_all_users()
    print(f"Total users: {len(all_users)}")
    print(f"Users: {all_users}")
    
    # Example 6: Direct memory agent usage
    print("\n--- Example 6: Direct Memory Operations ---")
    from memory_agent import MemoryAgent
    
    memory = MemoryAgent(excel_path)
    
    # Load a specific user profile
    alice_profile = memory.load_user_profile("Alice")
    if alice_profile:
        print(f"Loaded Alice's profile:")
        print(f"  - ID: {alice_profile.user_id}")
        print(f"  - Dietary Restrictions: {alice_profile.dietary_restrictions}")
        print(f"  - Likes: {alice_profile.likes}")
        print(f"  - Dislikes: {alice_profile.dislikes}")
        print(f"  - Objective: {alice_profile.objective}")
    
    # Update conversation memory
    update_result = memory.update_conversation_memory(
        "Alice", 
        "Alice asked for low-calorie vegan breakfast ideas.",
        append=True
    )
    print(f"\nMemory update result: {update_result}")


def interactive_mode():
    """
    Interactive mode for testing the system.
    """
    excel_path = 'MemoryFiles/TestWorkBook.xlsx'
    agent = ConversationalAgent(excel_file_path=excel_path)
    
    print("\n" + "=" * 60)
    print("Interactive Recipe Recommendation System")
    print("Type 'quit' to exit, 'switch <username>' to change user")
    print("=" * 60)
    
    current_user = input("\nEnter your username: ").strip()
    
    while True:
        message = input(f"\n[{current_user}] Enter your request: ").strip()
        
        if message.lower() == 'quit':
            break
        
        if message.lower().startswith('switch '):
            current_user = message[7:].strip()
            print(f"Switched to user: {current_user}")
            continue
        
        if message.lower() == 'history':
            history = agent.get_user_history(current_user)
            if history["status"] == "success":
                print(f"\n--- History for {current_user} ---")
                print(f"Dietary Rules: {history['DietRules']}")
                print(f"Summary: {history['ConvSummary']}")
            else:
                print(f"Error: {history['message']}")
            continue
        
        # Process the message
        recipes, parsed_request, user, _ = agent.handle_message(current_user, message)
        
        print(f"\n--- Results ---")
        print(f"Understood: {parsed_request}")
        
        if recipes:
            print(f"\nTop Recommendations:")
            for i, recipe in enumerate(recipes[:5], 1):
                print(f"{i}. {recipe.name}")
                if recipe.calories:
                    print(f"   Calories: {recipe.calories}, Protein: {recipe.protein}g")
        else:
            print("No recipes found matching your criteria.")
        
        print(f"\nProfile Update:")
        print(f"  Objective: {user.objective}")
        print(f"  Restrictions: {user.dietary_restrictions}")
        print(f"  Allergies: {user.allergies}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "interactive":
        interactive_mode()
    else:
        main()
