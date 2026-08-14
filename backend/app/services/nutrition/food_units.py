"""Food measurement unit classification.

Determines whether a food should be measured in units (NOS/pieces) or by weight (grams).
Uses deterministic rules and keyword matching - no AI calls needed.
"""

from __future__ import annotations

from typing import Literal

UnitType = Literal["nos", "grams", "ml"]


# Foods that are always counted in pieces/units with their standard weight per unit in grams
UNIT_FOODS: dict[str, float] = {
    # Eggs
    "egg": 50,
    "boiled egg": 50,
    "whole egg": 50,
    "fried egg": 55,
    "scrambled egg": 60,
    "omelette": 90,
    "egg white": 33,
    # Breads / rotis
    "roti": 40,
    "chapati": 40,
    "chapatti": 40,
    "phulka": 30,
    "paratha": 80,
    "aloo paratha": 100,
    "gobi paratha": 95,
    "paneer paratha": 100,
    "naan": 90,
    "kulcha": 90,
    "puri": 30,
    "bhatura": 60,
    "bread slice": 30,
    "bread": 30,
    "toast": 30,
    "bun": 50,
    "pav": 35,
    "tortilla": 40,
    "wrap": 50,
    # Fast food / assembled items
    "burger": 200,
    "sandwich": 150,
    "hot dog": 150,
    "pizza slice": 120,
    "samosa": 60,
    "kachori": 50,
    "vada pav": 120,
    "dosa": 80,
    "idli": 40,
    "medu vada": 50,
    "spring roll": 60,
    "momos": 25,
    "momo": 25,
    "dumpling": 25,
    "pakora": 30,
    "bhajiya": 30,
    "cutlet": 60,
    "patty": 80,
    # Fruits (whole)
    "banana": 120,
    "apple": 180,
    "orange": 150,
    "guava": 100,
    "pear": 170,
    "peach": 150,
    "plum": 70,
    "kiwi": 80,
    "mango": 200,
    "pomegranate": 200,
    "chikoo": 80,
    "sapota": 80,
    "fig": 50,
    "anjeer": 8,
    "date": 8,
    "khajoor": 8,
    # Snacks
    "protein bar": 60,
    "energy bar": 50,
    "biscuit": 8,
    "cookie": 15,
    "ladoo": 30,
    "laddu": 30,
    "barfi": 25,
    "jalebi": 30,
    "gulab jamun": 40,
    "rasgulla": 40,
    "dhokla": 40,
    # Supplements
    "whey scoop": 32,
    "whey protein scoop": 32,
    "protein scoop": 32,
    "scoop whey": 32,
}

# Aliases to canonical name (all lowercase)
FOOD_ALIASES: dict[str, str] = {
    "chapatti": "chapati",
    "roti": "chapati",
    "phulka": "chapati",
    "whole egg": "egg",
    "boiled egg": "egg",
    "fried egg": "egg",
    "dahi": "curd",
    "yogurt": "curd",
    "yoghurt": "curd",
    "chana": "chickpeas",
    "chole": "chickpeas",
    "chickpea": "chickpeas",
    "rajma": "kidney beans",
    "kidney bean": "kidney beans",
    "chawal": "rice",
    "bhaat": "rice",
    "atta": "wheat flour",
    "maida": "refined flour",
    "paneer": "paneer",
    "cottage cheese": "paneer",
    "tofu": "tofu",
    "soya chunk": "soya chunks",
    "soy chunks": "soya chunks",
    "nutrela": "soya chunks",
    "poha": "poha",
    "flattened rice": "poha",
    "beaten rice": "poha",
    "upma": "upma",
    "suji": "semolina",
    "rava": "semolina",
    "daliya": "daliya",
    "broken wheat": "daliya",
}

# Keywords that indicate a food is weight-based (grams)
WEIGHT_KEYWORDS = {
    "dal", "daal", "lentil", "rice", "chawal", "curd", "dahi", "yogurt", "yoghurt",
    "paneer", "cottage cheese", "chana", "chickpea", "rajma", "kidney bean",
    "sabzi", "vegetable", "salad", "soup", "gravy", "curry", "subzi",
    "poha", "upma", "khichdi", "pulao", "biryani", "fried rice",
    "pasta", "noodle", "maggi", "oats", "oatmeal", "porridge", "muesli",
    "halwa", "kheer", "raita", "chutney",
    "chicken", "mutton", "fish", "meat", "prawn", "shrimp",
    "milk", "buttermilk", "lassi", "juice", "shake", "smoothie",
    "ice cream", "cream",
    "flour", "atta", "maida", "suji", "rava", "besan",
    "sugar", "jaggery", "gur", "honey",
    "butter", "ghee", "oil", "mayonnaise",
    "cheese", "mozzarella", "cheddar",
    "peanut butter", "almond butter",
    "nuts", "almond", "cashew", "peanut", "walnut",
    "seeds", "flax", "chia", "sunflower",
    "powder", "whey protein", "protein powder",
}

# Keywords that strongly suggest unit/piece counting
UNIT_KEYWORDS = {
    "egg", "roti", "chapati", "paratha", "naan", "puri", "bread",
    "burger", "sandwich", "pizza", "samosa", "dosa", "idli", "vada",
    "momos", "momo", "dumpling", "spring roll",
    "banana", "apple", "orange", "mango", "guava",
    "biscuit", "cookie", "bar",
    "scoop",
}


def classify_food_unit(food_name: str, serving_description: str | None = None, tags: list[str] | None = None) -> tuple[UnitType, float | None]:
    """
    Classify whether a food is measured in units (NOS) or grams.

    Returns:
        (unit_type, weight_per_unit_g)
        - ("nos", 50.0) for eggs (50g each)
        - ("grams", None) for dal, rice, etc.
        - ("ml", None) for liquids
    """
    name_lower = food_name.strip().lower()
    tag_set = {t.lower() for t in (tags or [])}

    # Check direct match in unit foods dictionary
    if name_lower in UNIT_FOODS:
        return "nos", UNIT_FOODS[name_lower]

    # Check without common suffixes/prefixes
    # e.g. "boiled eggs" -> "boiled egg", "2 rotis" -> "roti"
    singular = name_lower.rstrip("s")
    if singular in UNIT_FOODS:
        return "nos", UNIT_FOODS[singular]

    # Check aliases
    canonical = FOOD_ALIASES.get(name_lower)
    if canonical and canonical in UNIT_FOODS:
        return "nos", UNIT_FOODS[canonical]

    # Check by keywords in the name
    name_words = set(name_lower.split())
    name_words.add(name_lower)

    # Unit keywords take priority over weight keywords when in food name
    for kw in UNIT_KEYWORDS:
        if kw in name_lower:
            # Try to find weight per unit from related entries
            for key, weight in UNIT_FOODS.items():
                if kw in key:
                    return "nos", weight
            return "nos", None

    # Weight keywords
    for kw in WEIGHT_KEYWORDS:
        if kw in name_lower:
            return "grams", None

    # Liquid indicators
    if any(liq in name_lower for liq in ("milk", "juice", "lassi", "shake", "smoothie", "buttermilk", "water")):
        return "ml", None

    # Check tags
    if "countable" in tag_set or "unit" in tag_set or "piece" in tag_set:
        return "nos", None
    if "liquid" in tag_set or "beverage" in tag_set:
        return "ml", None

    # Check serving description for hints
    if serving_description:
        sd = serving_description.lower()
        if any(h in sd for h in ("piece", "nos", "unit", "slice", "count")):
            return "nos", None

    # Default to grams
    return "grams", None


def get_display_unit(unit_type: UnitType) -> str:
    """Return user-facing unit label."""
    if unit_type == "nos":
        return "nos"
    if unit_type == "ml":
        return "ml"
    return "g"


def quantity_to_grams(quantity: float, unit_type: UnitType, weight_per_unit: float | None) -> float:
    """Convert user-entered quantity to grams for macro calculation."""
    if unit_type == "nos" and weight_per_unit:
        return quantity * weight_per_unit
    # For ml, treat as roughly equivalent to grams for nutrition
    return quantity


def grams_to_display_quantity(grams: float, unit_type: UnitType, weight_per_unit: float | None) -> float:
    """Convert stored grams back to display quantity."""
    if unit_type == "nos" and weight_per_unit:
        return round(grams / weight_per_unit, 1)
    return grams
