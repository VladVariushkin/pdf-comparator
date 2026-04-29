import json
import os


class LLMClient:
    def __init__(self):
        self.api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.endpoint,
                default_headers={"api-key": self.api_key},
            )
        return self._client

    def complete_json(self, system: str, user: str) -> dict:
        client = self._get_client()
        resp = client.chat.completions.create(
            model=self.deployment,
            temperature=0,
            seed=42,
            messages=[
                {"role": "system", "content": system + " Respond with raw JSON only — no markdown, no code fences."},
                {"role": "user", "content": user},
            ],
        )
        raw = resp.choices[0].message.content or ""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0]
        return json.loads(raw.strip())

    def complete_with_tool(self, system: str, user: str, tool: dict) -> dict:
        """Force a specific tool call and return the parsed arguments."""
        client = self._get_client()
        resp = client.chat.completions.create(
            model=self.deployment,
            temperature=0,
            seed=42,
            tools=[{"type": "function", "function": tool}],
            tool_choice={"type": "function", "function": {"name": tool["name"]}},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        call = resp.choices[0].message.tool_calls[0]
        return json.loads(call.function.arguments)
