"""Minimal Anthropic-compatible async client used by StandardPilot.

The project historically called ``AsyncAnthropic.messages.create`` directly in
multiple modules.  This adapter preserves that stable internal interface while
allowing the runtime provider to be selected with environment variables.

Supported providers:
- ``zhipu``: OpenAI-compatible Chat Completions API
- ``anthropic``: native Anthropic Messages API
"""
