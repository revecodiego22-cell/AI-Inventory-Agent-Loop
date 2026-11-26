import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "mixtral-8x7b-32768")
INVENTORY_API_URL = os.getenv("INVENTORY_API_URL", "http://localhost:8000")
CONVERSATION_LOG = Path("conversation_log.csv")

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY,
)

SYSTEM_PROMPT = """Eres Carla, una asistente inteligente de inventario de cafetería. 
Tu objetivo es ayudar a gestionar el inventario de productos.

Reglas:
- Para actualizar stock por nombre, primero llama a list_inventory para obtener el ID del producto.
- Responde siempre en español, corto y directo.
- Nunca inventes productos ni IDs que no existan.
- Cuando no conozcas algo, consulta la API.
- Sé amable y profesional en tus respuestas."""


def init_conversation_log():
    """Initialize conversation log if it doesn't exist."""
    if CONVERSATION_LOG.exists() and CONVERSATION_LOG.stat().st_size > 0:
        return
    
    with open(CONVERSATION_LOG, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["actor", "message", "tool_call", "timestamp"])


def log_event(actor: str, message: str, tool_call: Optional[str] = None):
    """Log an event to conversation log."""
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(CONVERSATION_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([actor, message, tool_call or "", timestamp])


def call_api(method: str, endpoint: str, data: Optional[dict] = None) -> Any:
    """Call the inventory API."""
    url = f"{INVENTORY_API_URL}{endpoint}"
    try:
        if method == "GET":
            response = httpx.get(url, params=data)
        elif method == "POST":
            response = httpx.post(url, json=data)
        elif method == "PATCH":
            response = httpx.patch(url, json=data)
        else:
            raise ValueError(f"Método HTTP no soportado: {method}")
        
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        return f"Error en API: {str(e)}"
    except Exception as e:
        return f"Error en API: {str(e)}"


def list_inventory() -> dict[str, Any]:
    """Get all products from inventory."""
    result = call_api("GET", "/inventory")
    return {"inventory": result} if isinstance(result, list) else result


def add_product(name: str, quantity: int, unit: str) -> dict[str, Any]:
    """Add a new product to inventory."""
    result = call_api("POST", "/inventory", {"name": name, "quantity": quantity, "unit": unit})
    return result


def update_stock(product_id: int, delta: int) -> dict[str, Any]:
    """Update product stock by delta."""
    result = call_api("PATCH", f"/inventory/{product_id}", {"delta": delta})
    return result


def get_low_stock_alerts(threshold: Optional[int] = None) -> dict[str, Any]:
    """Get products with low stock."""
    params = {}
    if threshold is not None:
        params["threshold"] = threshold
    result = call_api("GET", "/inventory/alerts", params)
    return {"alerts": result} if isinstance(result, list) else result


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_inventory",
            "description": "Obtiene la lista completa de productos en el inventario con sus cantidades actuales.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_product",
            "description": "Agrega un nuevo producto al inventario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Nombre del producto",
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Cantidad inicial del producto (debe ser >= 0)",
                    },
                    "unit": {
                        "type": "string",
                        "description": "Unidad de medida (ej: kg, litros, unidades, paquetes)",
                    },
                },
                "required": ["name", "quantity", "unit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_stock",
            "description": "Actualiza la cantidad de stock de un producto (suma o resta).",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": "ID del producto a actualizar",
                    },
                    "delta": {
                        "type": "integer",
                        "description": "Cambio en la cantidad (positivo para agregar, negativo para restar)",
                    },
                },
                "required": ["product_id", "delta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_low_stock_alerts",
            "description": "Obtiene productos con stock por debajo del umbral especificado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "threshold": {
                        "type": "integer",
                        "description": "Umbral de cantidad (default 10). Devuelve productos con cantidad < threshold",
                    },
                },
                "required": [],
            },
        },
    },
]


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool and return the result as a string."""
    if tool_name == "list_inventory":
        result = list_inventory()
    elif tool_name == "add_product":
        result = add_product(
            tool_input["name"], tool_input["quantity"], tool_input["unit"]
        )
    elif tool_name == "update_stock":
        result = update_stock(tool_input["product_id"], tool_input["delta"])
    elif tool_name == "get_low_stock_alerts":
        threshold = tool_input.get("threshold")
        result = get_low_stock_alerts(threshold)
    else:
        result = f"Herramienta desconocida: {tool_name}"
    
    return json.dumps(result, ensure_ascii=False, indent=2)


def run_agent_loop(user_input: str, messages: list[dict]) -> tuple[str, list[dict]]:
    """
    Run the agent loop for a single turn.
    Returns (final_response, updated_messages).
    """
    max_iterations = 8
    iteration = 0
    
    messages.append({"role": "user", "content": user_input})
    log_event("user", user_input)
    
    while iteration < max_iterations:
        iteration += 1
        
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
        except Exception as e:
            print(f"\n⚠️  Error en Groq: {str(e)}")
            return f"Error al conectar con el servicio: {str(e)}", messages
        
        assistant_message = response.choices[0].message
        
        messages.append(
            {
                "role": "assistant",
                "content": assistant_message.content or "",
                "tool_calls": (
                    [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in assistant_message.tool_calls
                    ]
                    if assistant_message.tool_calls
                    else None
                ),
            }
        )
        
        if not assistant_message.tool_calls:
            final_response = assistant_message.content or "No hay respuesta disponible."
            log_event("agent", final_response)
            return final_response, messages
        
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            tool_input = json.loads(tool_call.function.arguments)
            
            log_event("agent", json.dumps(tool_input, ensure_ascii=False), tool_name)
            
            tool_result = execute_tool(tool_name, tool_input)
            
            log_event("tool", tool_result, tool_name)
            
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                }
            )
    
    return "Máximo de iteraciones alcanzado.", messages


def main():
    """Main CLI loop."""
    init_conversation_log()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    print("🤖 Asistente de Inventario Carla")
    print("Escribe 'salir' para terminar.\n")
    
    try:
        while True:
            user_input = input("Tú: ").strip()
            
            if user_input.lower() == "salir":
                print("👋 ¡Hasta luego!")
                break
            
            if not user_input:
                continue
            
            response, messages = run_agent_loop(user_input, messages)
            print(f"\nCarla: {response}\n")
    
    except KeyboardInterrupt:
        print("\n👋 Sesión terminada.")


if __name__ == "__main__":
    main()
