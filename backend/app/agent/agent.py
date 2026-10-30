"""Gemini tool-calling loop. The model decides which tools to call; the tools do the math."""

from typing import Any

from google.genai import types
from pydantic import BaseModel

from ..store import Store
from .prompt import build_system_prompt
from .tools import Toolbox


class ToolCallTrace(BaseModel):
    name: str
    args: dict[str, Any]
    result: dict[str, Any]


class AgentReply(BaseModel):
    conversation_id: str
    reply: str
    tool_calls: list[ToolCallTrace]


class CarbonAgent:
    def __init__(self, client: Any, store: Store, model: str, max_steps: int = 8):
        """`client` is a `google.genai.Client` (or anything with the same `models.generate_content`)."""
        self.client = client
        self.store = store
        self.model = model
        self.max_steps = max_steps

    def chat(self, user_id: str, message: str, conversation_id: str | None = None) -> AgentReply:
        if conversation_id:
            self.store.check_conversation(user_id, conversation_id)
        else:
            conversation_id = self.store.create_conversation(user_id)

        toolbox = Toolbox(self.store, user_id)
        config = types.GenerateContentConfig(
            system_instruction=build_system_prompt(toolbox.user, self.store.factors),
            tools=[types.Tool(function_declarations=toolbox.declarations())],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        history = [types.Content.model_validate_json(j) for j in self.store.load_messages(conversation_id)]
        new: list[types.Content] = [types.Content(role="user", parts=[types.Part(text=message)])]
        traces: list[ToolCallTrace] = []
        reply: str | None = None

        for _ in range(self.max_steps):
            response = self.client.models.generate_content(model=self.model, contents=history + new, config=config)
            content = response.candidates[0].content if response.candidates else None
            if content is None or not content.parts:
                break
            new.append(content)  # keep as-is so Gemini's thought signatures survive
            calls = response.function_calls
            if not calls:
                reply = response.text or ""
                break
            parts = []
            for call in calls:
                args = dict(call.args or {})
                result = toolbox.execute(call.name, args)
                traces.append(ToolCallTrace(name=call.name, args=args, result=result))
                parts.append(types.Part(function_response=types.FunctionResponse(
                    id=call.id, name=call.name, response=result,
                )))
            new.append(types.Content(role="user", parts=parts))

        if reply is None:
            # Out of steps or an empty response: close the turn with a model message so history stays valid.
            reply = "Sorry, I couldn't finish that request. Could you rephrase or break it into smaller steps?"
            new.append(types.Content(role="model", parts=[types.Part(text=reply)]))

        self.store.append_messages(conversation_id, [c.model_dump_json(exclude_none=True) for c in new])
        return AgentReply(conversation_id=conversation_id, reply=reply, tool_calls=traces)
