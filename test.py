import requests
import json

import os
from litellm import completion

os.environ["OPENROUTER_API_KEY"] = "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"
# os.environ["OPENROUTER_API_BASE"] = "" # [OPTIONAL] defaults to https://openrouter.ai/api/v1
# os.environ["OR_SITE_URL"] = "" # [OPTIONAL]
# os.environ["OR_APP_NAME"] = "" # [OPTIONAL]

import json
import litellm
from rich import print as rprint

# exit(0)
messages = [
      {
        "role": "user",
        "content": "Generate a product listing with name, price, and description. Respond in json."
      }
    ]

response = litellm.completion(
  model="openrouter/qwen/qwen3.5-27b",
  messages=messages,
  max_tokens=1024,
  reasoning={
    "effort": "none"
  },
  provider={
    "require_parameters": True,
    # "allow_fallbacks": False,
    # "quantizations": [
    #   "bf16"
    # ],
    # "order": [
    #   "alibaba",
    #   "phala", 
    #   "novita/bf16",
    # ],
  },
  response_format={
    "type": "json_schema",
    "json_schema": {
      "name": "Product",
      "schema": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string",
            "description": "Product name"
          },
          "price": {
            "type": "number",
            "description": "Price in USD"
          },
          "description": {
            "type": "string",
            "description": "Product description"
          }
        },
        "required": ["name", "price"]
      }
    }
  },
  plugins=[
    {"id": "response-healing"}
  ]
)
# rprint(response)

data = response.json()
print(data)
product = json.loads(data["choices"][0]["message"]["content"])
print(product)
# The plugin attempts to repair malformed JSON syntax
print(product["name"], product["price"])

exit(0)
completion_tokens = response.usage.completion_tokens
latency_sec = response._response_ms / 1000.0
throughput_tps = completion_tokens / latency_sec if latency_sec > 0 else None

print("completion_tokens:", completion_tokens)
print("latency_sec:", latency_sec)
print("throughput_tps:", throughput_tps)