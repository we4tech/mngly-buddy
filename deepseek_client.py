"""Custom OpenAI client with DeepSeek reasoning_content support."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from agent_framework import Content, Message
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework._types import ChatResponse
from openai.types.chat.chat_completion import ChatCompletion, Choice


class DeepSeekChatCompletionClient(OpenAIChatCompletionClient):
    """OpenAI Chat Completion client with DeepSeek reasoning_content support.
    
    DeepSeek's thinking models return a `reasoning_content` field that must be
    preserved and sent back in subsequent API calls. This client extends the
    standard OpenAIChatCompletionClient to handle this field properly.
    """

    def _parse_response_from_openai(self, response: ChatCompletion, options: Mapping[str, Any]) -> ChatResponse:
        """Parse response and preserve DeepSeek's reasoning_content field."""
        # Get the base response using parent's method
        chat_response = super()._parse_response_from_openai(response, options)
        
        # Check for reasoning_content in the original response and preserve it
        for i, choice in enumerate(response.choices):
            if hasattr(choice.message, "reasoning_content") and choice.message.reasoning_content:
                # Store reasoning_content in the message's additional_properties
                if i < len(chat_response.messages):
                    msg = chat_response.messages[i]
                    if msg.additional_properties is None:
                        msg.additional_properties = {}
                    msg.additional_properties["reasoning_content"] = choice.message.reasoning_content
                    
                    # Also add as protected content so it round-trips properly
                    reasoning_content = Content.from_text_reasoning(
                        protected_data=json.dumps({"reasoning_content": choice.message.reasoning_content})
                    )
                    msg.contents.append(reasoning_content)
        
        return chat_response

    def _prepare_message_for_openai(self, message: Message) -> list[dict[str, Any]]:
        """Prepare message and include DeepSeek's reasoning_content if present."""
        # Get base messages using parent's method
        all_messages = super()._prepare_message_for_openai(message)
        
        # If this message has reasoning_content in additional_properties, add it
        if message.additional_properties and "reasoning_content" in message.additional_properties:
            reasoning_content = message.additional_properties["reasoning_content"]
            # Add reasoning_content to the last message created
            if all_messages:
                all_messages[-1]["reasoning_content"] = reasoning_content
        
        # Also check if there's a text_reasoning content with reasoning_content
        for content in message.contents:
            if content.type == "text_reasoning" and content.protected_data:
                try:
                    protected = json.loads(content.protected_data)
                    if "reasoning_content" in protected and all_messages:
                        all_messages[-1]["reasoning_content"] = protected["reasoning_content"]
                except (json.JSONDecodeError, KeyError):
                    pass
        
        return all_messages
