import sys
import os
import re
import json
import logging

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import SlotSet, ActiveLoop
from lodge_data import LODGES

logger = logging.getLogger(__name__)

def extract_slot_value(slot_name, user_input):
    value = None
    user_input = user_input.lower()

    if slot_name == "location":
        all_locations = {lodge["location"].lower() for lodge in LODGES}
        value = next((location for location in all_locations if location in user_input), None)

    elif slot_name == "lodge_type":
        # Normalize lodge types by removing hyphens
        all_types = {lodge["type"].lower().replace("-", " ") for lodge in LODGES}
        for typ in all_types:
            if typ in user_input.replace("-", " "):
                value = typ
                break

    elif slot_name == "price":
        price_match = re.search(r"(?:₦|naira)?\s?(\d{5,7})", user_input)
        if price_match:
            value = price_match.group(1).replace(",", "").strip()

    elif slot_name == "amenities":
        all_amenities = {amenity.lower() for lodge in LODGES for amenity in lodge.get("amenities", [])}
        value = [amenity for amenity in all_amenities if amenity in user_input]

    elif slot_name == "preferences":
        all_prefs = {pref.lower() for lodge in LODGES for pref in lodge.get("preferences", [])}
        value = [pref for pref in all_prefs if pref in user_input]

    return value

def filter_lodges(location, lodge_type, price, amenities, preferences):
    matching_lodges = []
    for lodge in LODGES:
        if location and lodge["location"].lower() != location.lower():
            continue

        # Normalize lodge type by removing hyphens for comparison
        if lodge_type and lodge["type"].lower().replace("-", " ") != lodge_type.lower().replace("-", " "):
            continue
        if price:
            try:
                if int(lodge.get("price", 0)) > int(price):
                    continue
            except ValueError:
                continue

        # Check amenities (case-insensitive and normalized)
        if amenities:
            lodge_amenities = [a.lower() for a in lodge.get("amenities", [])]
            if not all(a in lodge_amenities for a in amenities):
                continue

        # Check preferences (case-insensitive and normalized)
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

        questions_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lodge_questions.json")
        try:
            with open(questions_file, "r") as f:
                questions = json.load(f)
        except FileNotFoundError:
            dispatcher.utter_message(text="❌ Error: Questions file not found.")
            return []
        except json.JSONDecodeError:
            dispatcher.utter_message(text="❌ Error: Failed to parse questions file.")
            return []

        total_questions = len(questions)
        q_index = int(tracker.get_slot("question_index") or 0)

        # Get the current question and slot
        current_q = questions[q_index]
        slot_name = current_q["slot"]
        question_text = current_q["question"]

        # Extract user input
        user_input = tracker.latest_message.get("text", "").lower().strip()
        if not user_input:
            dispatcher.utter_message(text="⚠️ I didn't catch that. Could you please repeat?")
            return []

        # Extract value for the current slot
        value = extract_slot_value(slot_name, user_input)

        # If a valid value is extracted, set the slot and move to the next question
        if value:
            logger.info(f"Extracted value for {slot_name}: {value}")
            dispatcher.utter_message(text=f"✅ {slot_name.replace('_', ' ').title()} set to: {value}")
            events = [SlotSet(slot_name, value), SlotSet("question_index", q_index + 1)]
        else:
            # If no valid value is extracted, ask the same question again
            logger.warning(f"Failed to extract value for {slot_name} from input: {user_input}")
            dispatcher.utter_message(text=f"⚠️ I couldn't extract a valid value for {slot_name}. Please try again.")
            return []

        # If all questions are answered, proceed to lodge filtering
        if q_index + 1 >= total_questions:
            location = tracker.get_slot("location")
            lodge_type = tracker.get_slot("lodge_type")
            price = tracker.get_slot("price")
            amenities = tracker.get_slot("amenities") or []
            preferences = tracker.get_slot("preferences") or []

            # Normalize amenities and preferences
            amenities = [a.lower() for a in amenities] if isinstance(amenities, list) else []
            preferences = [p.lower() for p in preferences] if isinstance(preferences, list) else []

            # Filter lodges based on user input
            matching_lodges = filter_lodges(location, lodge_type, price, amenities, preferences)

            # Display matching lodges
            if matching_lodges:
                dispatcher.utter_message(text=f"🏡 Here are some lodges that match your preferences:")
                for lodge in matching_lodges[:5]:
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

            # Reset the question index and return
            return [SlotSet("question_index", None)]

        # Ask the next question if there are more questions
        if q_index + 1 < total_questions and value:
            next_q = questions[q_index + 1]
            dispatcher.utter_message(text=next_q["question"])

        return events

