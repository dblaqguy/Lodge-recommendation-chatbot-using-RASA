import sys
import os
import json
import logging
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from lodge_data import LODGES

logger = logging.getLogger(__name__)

questions_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lodge_questions.json")
try:
    with open(questions_file, "r") as file:
        questions = json.load(file)
except FileNotFoundError:
    logger.error(f" Error: Questions file not found.")
except json.JSONDecodeError:
    logger.error(f" Error: Failed to parse questions file.")

def filter_lodges(location, lodge_type, price, amenities, preferences):
    matching_lodges = []
    for lodge in LODGES:
        if location and lodge["location"].lower() != location.lower():
            continue
        if lodge_type and lodge["type"].lower().replace("-", " ") != lodge_type.lower().replace("-", " "):
            continue
        if price:
            try:
                if int(lodge.get("price", 0)) > int(price):
                    continue
            except ValueError:
                continue
        if amenities:
            lodge_amenities = [a.lower() for a in lodge.get("amenities", [])]
            if not all(a in lodge_amenities for a in amenities):
                continue
        if preferences:
            lodge_preferences = [p.lower() for p in lodge.get("preferences", [])]
            if not all(p in lodge_preferences for p in preferences):
                continue

        matching_lodges.append(lodge)
    return matching_lodges

class ActionAskLodgeQuestion(Action):
    def name(self) -> Text:
        return "action_ask_lodge_question"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        total_questions = len(questions)
        question_index = int(tracker.get_slot("question_index") or 0)
        current_question = questions[question_index]
        slot_name = current_question["slot"]

        entities = tracker.latest_message.get("entities", [])
        slot_values = {"location": None, "lodge_type": None, "price": None, "amenities": [], "preferences": []}

        for entity in entities:
            entity_name = entity.get("entity")
            entity_value = entity.get("value").lower()

            if entity_name == "location":
                slot_values["location"] = entity_value
            elif entity_name == "lodge_type":
                slot_values["lodge_type"] = entity_value
            elif entity_name == "price":
                slot_values["price"] = entity_value.replace("₦", "").replace(",", "").strip()
            elif entity_name == "amenities":
                slot_values["amenities"].append(entity_value)
            elif entity_name == "preferences":
                slot_values["preferences"].append(entity_value)

        value = slot_values.get(slot_name)
        if value:
            logger.info(f"Extracted value for {slot_name}: {value}")
            # dispatcher.utter_message(text=f"✅ {slot_name.replace('_', ' ').title()} set to: {value}")
            events = [SlotSet(slot_name, value), SlotSet("question_index", question_index + 1)]
        else:
            logger.warning(f"Failed to extract value for {slot_name} from input: {tracker.latest_message.get('text', '')}")
            # dispatcher.utter_message(text=f"⚠️ I couldn't extract a valid value for {slot_name}. Please try again.")
            return []

        if question_index + 1 >= total_questions:
            location = tracker.get_slot("location")
            lodge_type = tracker.get_slot("lodge_type")
            price = tracker.get_slot("price")
            amenities = tracker.get_slot("amenities") or []
            preferences = tracker.get_slot("preferences") or []

            amenities = [a.lower() for a in amenities] if isinstance(amenities, list) else []
            preferences = [p.lower() for p in preferences] if isinstance(preferences, list) else []

            matching_lodges = filter_lodges(location, lodge_type, price, amenities, preferences)
            if matching_lodges:
                dispatcher.utter_message(text=f"🏡 Here are some lodges that match your preferences:")
                for lodge in matching_lodges:
                    info = (
                        f"📍 *{lodge['name']}* in {lodge['location']}\n"
                        f"🏷 Type: {lodge['type']}\n"
                        f"💰 Price: ₦{lodge['price']}\n"
                        f"✅ Amenities: {', '.join(lodge.get('amenities', []))}\n"
                        f"⭐ Preferences: {', '.join(lodge.get('preferences', []))}"
                    )
                    dispatcher.utter_message(text=info)
            else:
                dispatcher.utter_message(text="❌ Sorry, no lodges matched all your preferences.")

            return [SlotSet("question_index", None)]

        if question_index + 1 < total_questions:
            next_q = questions[question_index + 1]
            dispatcher.utter_message(text=next_q["question"])

        return events
  
