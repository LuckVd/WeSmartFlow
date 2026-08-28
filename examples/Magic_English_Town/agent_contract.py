"""Server-side allowlist for model-produced Magic English Town actions."""

from __future__ import annotations

from typing import Any

TOWN_LOCATIONS = {"town", "petshop", "bakery", "school", "park", "storyhouse"}
TOWN_INTENTS = {
    "travel",
    "help",
    "hide_coco",
    "greet_coco",
    "name_petshop_object",
    "place_object",
    "ask_baker",
    "order_food",
    "ask_teacher",
    "name_color",
    "inspect_clue",
    "inspect_town_clue",
    "town_observation",
    "find_coco",
    "clarify_tree",
    "care_coco",
    "open_story",
    "greet",
    "chat",
}
FESTIVAL_LOCATIONS = {"town", "bakery", "school", "park", "storyhouse"}
FESTIVAL_INTENTS = {
    "travel",
    "order_treats",
    "design_flag",
    "locate_firefly",
    "guide_fireflies",
    "invite_friend",
    "light_lantern",
    "greet",
    "chat",
}
SPEAKERS = {"Milo", "Coco", "Betty", "Ms. Maple"}


def _text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\x00", "").split()).strip()[:limit]


def _dialogue(raw: dict[str, Any], default_reply: str) -> dict[str, str]:
    speaker = raw.get("speaker")
    return {
        "speaker": speaker if speaker in SPEAKERS else "Milo",
        "reply": _text(raw.get("reply"), 240) or default_reply,
        "hint": _text(raw.get("hint"), 180),
        "recast": _text(raw.get("recast"), 160),
    }


def _town_action_allowed(intent: str, context: dict[str, Any], raw: dict[str, Any]) -> bool:
    location = context.get("location")
    stage = context.get("quest_stage")
    if intent in {"travel", "help", "greet", "chat"}:
        return True
    if intent == "greet_coco":
        return location in {"petshop", "park", "town"}
    if intent in {"hide_coco", "name_petshop_object", "place_object"}:
        return location == "petshop" and (intent != "hide_coco" or stage == "meet")
    if intent in {"ask_baker", "order_food"}:
        return location == "bakery"
    if intent in {"ask_teacher", "name_color"}:
        return location == "school"
    if intent in {"inspect_clue", "find_coco", "clarify_tree"}:
        return location == "park"
    if intent in {"inspect_town_clue", "town_observation"}:
        return location == "town"
    if intent == "open_story":
        return location == "storyhouse"
    if intent == "care_coco" and stage == "care":
        return (location, raw.get("care")) in {
            ("petshop", "towel"),
            ("bakery", "snack"),
            ("park", "snack"),
            ("school", "friends"),
        }
    return False


def normalize_town_response(raw: Any, context: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    intent = raw.get("intent")
    if intent not in TOWN_INTENTS or not _town_action_allowed(intent, context, raw):
        intent = "chat"

    result: dict[str, Any] = {"intent": intent}
    if intent == "travel" and raw.get("destination") in TOWN_LOCATIONS:
        result["destination"] = raw["destination"]
    elif intent == "travel":
        result["intent"] = "chat"
    elif intent == "hide_coco" and raw.get("destination") in {"box", "table"}:
        result["destination"] = raw["destination"]
    elif intent == "hide_coco":
        result["intent"] = "chat"
    elif intent == "name_petshop_object" and raw.get("object") in {"box", "table", "ball"}:
        result["object"] = raw["object"]
    elif intent == "name_petshop_object":
        result["intent"] = "chat"
    elif intent == "place_object":
        placement = (raw.get("object"), raw.get("relation"), raw.get("destination"))
        if placement in {
            ("ball", "on", "table"),
            ("ball", "in", "box"),
            ("ball", "under", "table"),
            ("ball", "on", "floor"),
        }:
            result.update(object=placement[0], relation=placement[1], destination=placement[2])
        else:
            result["intent"] = "chat"
    elif intent == "order_food" and raw.get("food") in {"bread", "cake", "cookie"}:
        result["food"] = raw["food"]
    elif intent == "order_food":
        result["intent"] = "chat"
    elif intent == "name_color" and raw.get("color") in {"blue", "red", "yellow", "green"}:
        result["color"] = raw["color"]
    elif intent == "name_color":
        result["intent"] = "chat"
    elif intent == "inspect_clue" and raw.get("clue") in {"tracks", "puddle", "bush"}:
        result["clue"] = raw["clue"]
    elif intent == "inspect_clue":
        result["intent"] = "chat"
    elif intent == "care_coco" and raw.get("care") in {"towel", "snack", "friends"}:
        result["care"] = raw["care"]
    elif intent == "care_coco":
        result["intent"] = "chat"

    if result["intent"] == "greet_coco" and raw.get("gesture") == "comfort":
        result["gesture"] = "comfort"
    result.update(
        _dialogue(
            raw,
            "I heard your idea. Try one short English sentence about the world around you.",
        )
    )
    return result


def _festival_action_allowed(intent: str, context: dict[str, Any]) -> bool:
    location = context.get("location")
    phase = context.get("phase")
    if intent in {"travel", "greet", "chat"}:
        return True
    if intent == "order_treats":
        return location == "bakery"
    if intent == "design_flag":
        return location == "school"
    if intent == "locate_firefly":
        return location == "park"
    if intent == "guide_fireflies":
        return location == "park" and len(context.get("fireflies_found") or []) >= 3
    if intent == "invite_friend":
        return location == "town" and phase == "finale"
    if intent == "light_lantern":
        completed = set(context.get("completed_tasks") or [])
        return (
            location == "town"
            and phase == "finale"
            and {"bakery", "school", "park"}.issubset(completed)
            and bool(context.get("invited"))
        )
    return False


def normalize_festival_response(raw: Any, context: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    intent = raw.get("intent")
    if intent not in FESTIVAL_INTENTS or not _festival_action_allowed(intent, context):
        intent = "chat"

    result: dict[str, Any] = {"intent": intent}
    if intent == "travel" and raw.get("destination") in FESTIVAL_LOCATIONS:
        result["destination"] = raw["destination"]
    elif intent == "travel":
        result["intent"] = "chat"
    elif intent == "order_treats":
        if raw.get("food") in {"cookie", "cake", "bread"}:
            result["food"] = raw["food"]
            try:
                result["quantity"] = max(1, min(3, int(raw.get("quantity", 1))))
            except (TypeError, ValueError):
                result["quantity"] = 1
        else:
            result["intent"] = "chat"
    elif intent == "design_flag":
        if raw.get("color") in {"blue", "yellow", "purple"} and raw.get("shape") in {
            "star",
            "moon",
            "circle",
        }:
            result.update(color=raw["color"], shape=raw["shape"])
        else:
            result["intent"] = "chat"
    elif intent == "invite_friend":
        invitee = raw.get("invitee") or context.get("selected_invitee")
        if invitee in {"Betty", "Ms. Maple", "Coco"}:
            result["invitee"] = invitee
        else:
            result["intent"] = "chat"

    result.update(
        _dialogue(
            raw,
            "That is a lovely idea. Try saying what you want to do in the festival.",
        )
    )
    return result
