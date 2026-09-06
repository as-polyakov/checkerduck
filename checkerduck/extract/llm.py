import json
from typing import List

import requests

PROMPT_CLASSIFICATION_TEMPLATE = """
You are an SEO analyst.

Your task:
Given a sample content and a list of possible categories with subcategories, determine the single most appropriate category and subcategory for that website.

Step 1: Determine the main theme of the text and possible category/subcategory.
For analysis, consider:
- given content,
 - organic keywords (if provided),
 - backlink anchors (if provided),
 - titles and meta descriptions,
 - outgoing links (if provided).

Step 2: Match the detected theme to the closest option from the predefined list of categories and return only the category. Respond in strict JSON format only — no extra text or explanations outside JSON.
Fields in the JSON response:
  - "category": string — the chosen category/subcategory from the list
  - "confidence": float — number between 0 and 1. How confident you are in the assignment
  - "summary": string — 1-2 sentences explaining why you chose this category

### Example input:
The new 2025 Yamaha MT-09 delivers an aggressive riding experience with its 890cc triple engine and lightweight aluminum frame. Riders will appreciate the improved suspension setup, quick-shifter, and updated TFT display for navigation and performance tracking. Explore accessories like saddlebags, helmets, and performance exhausts designed specifically for the MT series.

### Example output:
{{
  "category": "Vehicles/Motorcycles",
  "confidence": 0.95,
  "summary": "Motorcycles review"
}}

Now categorize the following text:

Text: {content}
Categories: {categories}
"""

OLLAMA_URL = "http://localhost:11434/api/generate"
CATEGORIES = [
    "Arts_and_Entertainment/Animation_and_Comics",
    "Arts_and_Entertainment/Arts_and_Entertainment",
    "Arts_and_Entertainment/Books_and_Literature",
    "Arts_and_Entertainment/Humor",
    "Arts_and_Entertainment/Music",
    "Arts_and_Entertainment/Performing_Arts",
    "Arts_and_Entertainment/TV_Movies_and_Streaming",
    "Arts_and_Entertainment/Visual_Arts_and_Design",
    "Business_and_Consumer_Services/Business_and_Consumer_Services",
    "Business_and_Consumer_Services/Business_Services",
    "Business_and_Consumer_Services/Marketing_and_Advertising",
    "Business_and_Consumer_Services/Online_Marketing",
    "Business_and_Consumer_Services/Publishing_and_Printing",
    "Business_and_Consumer_Services/Real_Estate",
    "Business_and_Consumer_Services/Relocation_and_Household_Moving",
    "Business_and_Consumer_Services/Shipping_and_Logistics",
    "Business_and_Consumer_Services/Textiles",
    "Community_and_Society/Community_and_Society",
    "Community_and_Society/Decease",
    "Community_and_Society/Faith_and_Beliefs",
    "Community_and_Society/Holidays_and_Seasonal_Events",
    "Community_and_Society/LGBTQ",
    "Community_and_Society/Philanthropy",
    "Community_and_Society/Romance_and_Relationships",
    "Computers_Electronics_and_Technology/Advertising_Networks",
    "Computers_Electronics_and_Technology/Computer_Hardware",
    "Computers_Electronics_and_Technology/Computer_Security",
    "Computers_Electronics_and_Technology/Computers_Electronics_and_Technology",
    "Computers_Electronics_and_Technology/Consumer_Electronics",
    "Computers_Electronics_and_Technology/Email",
    "Computers_Electronics_and_Technology/File_Sharing_and_Hosting",
    "Computers_Electronics_and_Technology/Graphics_Multimedia_and_Web_Design",
    "Computers_Electronics_and_Technology/Programming_and_Developer_Software",
    "Computers_Electronics_and_Technology/Search_Engines",
    "Computers_Electronics_and_Technology/Social_Networks_and_Online_Communities",
    "Computers_Electronics_and_Technology/Telecommunications",
    "Computers_Electronics_and_Technology/Web_Hosting_and_Domain_Names",
    "E-commerce_and_Shopping/Auctions",
    "E-commerce_and_Shopping/Classifieds",
    "E-commerce_and_Shopping/Coupons_and_Rebates",
    "E-commerce_and_Shopping/E-commerce_and_Shopping",
    "E-commerce_and_Shopping/Marketplace",
    "E-commerce_and_Shopping/Price_Comparison",
    "E-commerce_and_Shopping/Tickets",
    "Finance/Accounting_and_Auditing",
    "Finance/Banking_Credit_and_Lending",
    "Finance/Finance",
    "Finance/Financial_Planning_and_Management",
    "Finance/Insurance",
    "Finance/Investing",
    "Food_and_Drink/Beverages",
    "Food_and_Drink/Cooking_and_Recipes",
    "Food_and_Drink/Food_and_Drink",
    "Food_and_Drink/Groceries",
    "Food_and_Drink/Restaurants_and_Delivery",
    "Food_and_Drink/Vegetarian_and_Vegan",
    "Gambling/Bingo",
    "Gambling/Casinos",
    "Gambling/Gambling",
    "Gambling/Lottery",
    "Gambling/Poker",
    "Gambling/Sports_Betting",
    "Games/Board_and_Card_Games",
    "Games/Games",
    "Games/Puzzles_and_Brainteasers",
    "Games/Roleplaying_Games",
    "Games/Video_Games_Consoles_and_Accessories",
    "Health/Addictions",
    "Health/Alternative_and_Natural_Medicine",
    "Health/Biotechnology_and_Pharmaceuticals",
    "Health/Childrens_Health",
    "Health/Dentist_and_Dental_Services",
    "Health/Developmental_and_Physical_Disabilities",
    "Health/Geriatric_and_Aging_Care",
    "Health/Health",
    "Health/Health_Conditions_and_Concerns",
    "Health/Medicine",
    "Health/Mens_Health",
    "Health/Mental_Health",
    "Health/Nutrition_and_Fitness",
    "Health/Nutrition_Diets_and_Fitness",
    "Health/Pharmacy",
    "Health/Public_Health_and_Safety",
    "Health/Womens_Health",
    "Heavy_Industry_and_Engineering/Aerospace_and_Defense",
    "Heavy_Industry_and_Engineering/Agriculture",
    "Heavy_Industry_and_Engineering/Architecture",
    "Heavy_Industry_and_Engineering/Chemical_Industry",
    "Heavy_Industry_and_Engineering/Construction_and_Maintenance",
    "Heavy_Industry_and_Engineering/Energy_Industry",
    "Heavy_Industry_and_Engineering/Heavy_Industry_and_Engineering",
    "Heavy_Industry_and_Engineering/Metals_and_Mining",
    "Heavy_Industry_and_Engineering/Waste_Water_and_Environmental",
    "Hobbies_and_Leisure/Ancestry_and_Genealogy",
    "Hobbies_and_Leisure/Antiques_and_Collectibles",
    "Hobbies_and_Leisure/Camping_Scouting_and_Outdoors",
    "Hobbies_and_Leisure/Crafts",
    "Hobbies_and_Leisure/Hobbies_and_Leisure",
    "Hobbies_and_Leisure/Models",
    "Hobbies_and_Leisure/Photography",
    "Home_and_Garden/Furniture",
    "Home_and_Garden/Gardening",
    "Home_and_Garden/Home_and_Garden",
    "Home_and_Garden/Home_Improvement_and_Maintenance",
    "Home_and_Garden/Interior_Design",
    "Jobs_and_Career/Human_Resources",
    "Jobs_and_Career/Jobs_and_Career",
    "Jobs_and_Career/Jobs_and_Employment",
    "Law_and_Government/Government",
    "Law_and_Government/Immigration_and_Visas",
    "Law_and_Government/Law_and_Government",
    "Law_and_Government/Law_Enforcement_and_Protective_Services",
    "Law_and_Government/Legal",
    "Law_and_Government/National_Security",
    "Lifestyle/Beauty_and_Cosmetics",
    "Lifestyle/Childcare",
    "Lifestyle/Fashion_and_Apparel",
    "Lifestyle/Gifts_and_Flowers",
    "Lifestyle/Jewelry_and_Luxury_Products",
    "Lifestyle/Lifestyle",
    "Lifestyle/Tobacco",
    "Lifestyle/Weddings",
    "News_and_Media",
    "Pets_and_Animals/Animals",
    "Pets_and_Animals/Birds",
    "Pets_and_Animals/Fish_and_Aquaria",
    "Pets_and_Animals/Horses",
    "Pets_and_Animals/Pet_Food_and_Supplies",
    "Pets_and_Animals/Pets",
    "Pets_and_Animals/Pets_and_Animals",
    "Reference_Materials/Dictionaries_and_Encyclopedias",
    "Reference_Materials/Maps",
    "Reference_Materials/Public_Records_and_Directories",
    "Reference_Materials/Reference_Materials",
    "Science_and_Education/Astronomy",
    "Science_and_Education/Biology",
    "Science_and_Education/Business_Training",
    "Science_and_Education/Chemistry",
    "Science_and_Education/Colleges_and_Universities",
    "Science_and_Education/Earth_Sciences",
    "Science_and_Education/Education",
    "Science_and_Education/Environmental_Science",
    "Science_and_Education/Grants_Scholarships_and_Financial_Aid",
    "Science_and_Education/History",
    "Science_and_Education/Libraries_and_Museums",
    "Science_and_Education/Literature",
    "Science_and_Education/Math",
    "Science_and_Education/Philosophy",
    "Science_and_Education/Physics",
    "Science_and_Education/Public_Records_and_Directories",
    "Science_and_Education/Science_and_Education",
    "Science_and_Education/Social_Sciences",
    "Science_and_Education/Universities_and_Colleges",
    "Science_and_Education/Weather",
    "Sports/American_Football",
    "Sports/Baseball",
    "Sports/Basketball",
    "Sports/Boxing",
    "Sports/Climbing",
    "Sports/Cycling_and_Biking",
    "Sports/Extreme_Sports",
    "Sports/Fantasy_Sports",
    "Sports/Fishing",
    "Sports/Golf",
    "Sports/Hunting_and_Shooting",
    "Sports/Martial_Arts",
    "Sports/Rugby",
    "Sports/Running",
    "Sports/Soccer",
    "Sports/Sports",
    "Sports/Tennis",
    "Sports/Volleyball",
    "Sports/Water_Sports",
    "Sports/Winter_Sports",
    "Travel_and_Tourism/Accommodation_and_Hotels",
    "Travel_and_Tourism/Air_Travel",
    "Travel_and_Tourism/Car_Rentals",
    "Travel_and_Tourism/Ground_Transportation",
    "Travel_and_Tourism/Tourist_Attractions",
    "Travel_and_Tourism/Transportation_and_Excursions",
    "Travel_and_Tourism/Travel_and_Tourism",
    "Vehicles/Automotive_Industry",
    "Vehicles/Aviation",
    "Vehicles/Boats",
    "Vehicles/Makes_and_Models",
    "Vehicles/Motorcycles",
    "Vehicles/Motorsports",
    "Vehicles/Vehicles",
    "Adult",
]


class OllamaClient:
    def __init__(self, api_key: str, api_secret: str, classifiers: List[str]):
        self.api_key = api_key
        self.api_secret = api_secret
        self.classifiers = classifiers

    def classify_content(self, content: str, model: str = "llama3.1:8b"):
        prompt = PROMPT_CLASSIFICATION_TEMPLATE.format(content=content, categories=self.classifiers)

        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,  # return the full response at once
            },
        )

        response.raise_for_status()

        # Ollama returns a JSON object with a "response" field containing the model output
        data = response.json()
        raw_output = data.get("response", "").strip()

        # Try to extract valid JSON
        try:
            result = json.loads(raw_output)
        except json.JSONDecodeError:
            # Sometimes models output text around JSON; try to extract JSON substring
            import re
            match = re.search(r"\{.*\}", raw_output, re.DOTALL)
            result = json.loads(match.group(0)) if match else {"error": "invalid JSON", "raw": raw_output}

        return result


if __name__ == "__main__":
    client = OllamaClient(None, None, CATEGORIES)
    res = client.classify_content("The latest technology news and reviews, covering computing, home entertainment systems, gadgets and more")
    print(json.dumps(res, indent=2, ensure_ascii=False))
