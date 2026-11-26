# 🤖 AI Inventory Agent Loop - Asistente Inteligente de Inventario

Un asistente de IA para gestionar inventarios de cafetería usando un loop de agente manual en Python. Carla es tu asistente que mantiene el stock actualizado sin necesidad de frameworks de agentes complejos.

## ✨ Características

- **API REST** con FastAPI para gestión de inventario
- **Agente IA** con loop manual usando OpenAI SDK y Groq
- **Persistencia** en CSV con sincronización thread-safe
- **Herramientas LLM** para: listar, agregar, actualizar stock y alertas
- **Logs conversacionales** en CSV con historial completo
- **Validaciones** con Pydantic para datos consistentes

## 📋 Requisitos

- Python 3.14+
- `uv` como gestor de dependencias

## 🚀 Instalación

### 1. Clonar y navegar al proyecto

```bash
cd AI-Inventory-Agent-Loop
```

### 2. Instalar dependencias

```bash
uv sync
```

### 3. Configurar variables de entorno

Crear archivo `.env`:

```bash
cat > .env << 'ENDENV'
GROQ_API_KEY=tu_api_key_aqui
GROQ_MODEL=mixtral-8x7b-32768
INVENTORY_API_URL=http://localhost:8000
ENDENV
```

Obtén tu clave en [console.groq.com](https://console.groq.com).

## 📂 Estructura del Proyecto

```
.
├── api/
│   ├── __init__.py
│   └── app.py              # API FastAPI
├── tests/
│   ├── __init__.py
│   ├── test_api.py         # Tests de la API
│   └── test_agent.py       # Tests del agente
├── agent.py                # Agente con loop manual
├── products.csv            # Inventario (auto-generado)
├── conversation_log.csv    # Historial de conversaciones
├── .env                    # Variables de entorno (crear)
├── .gitignore
├── pyproject.toml
└── README.md               # Este archivo
```

## ▶️ Cómo Usar

### Terminal 1: Iniciar la API

```bash
uv run uvicorn api.app:app --reload
```

La API estará disponible en `http://localhost:8000`
- Documentación interactiva: `http://localhost:8000/docs`

### Terminal 2: Iniciar el Agente

```bash
uv run python agent.py
```

Escribe frases en español y Carla gestionará el inventario:

```
Tú: ¿Cuál es el stock actual?
Carla: Aquí está el inventario completo:
- Leche de Avena: 25 litros
- Café Arábica: 8 kg
- Vasos Desechables: 150 unidades
...

Tú: Recibimos 10 kg de café
Carla: He actualizado el stock de Café Arábica. Nuevo stock: 18 kg.

Tú: ¿Qué está bajo de stock?
Carla: Productos con stock bajo (< 10):
- Café Arábica: 8 kg
- Azúcar Moreno: 5 kg
...

Tú: salir
👋 ¡Hasta luego!
```

### Detener

1. **Agente**: Escribe `salir` o presiona `Ctrl+C`
2. **API**: En la terminal, presiona `Ctrl+C`

## 🧪 Pruebas

Ejecutar todos los tests:

```bash
uv run pytest -v
```

Ejecutar solo API tests:

```bash
uv run pytest tests/test_api.py -v
```

Ejecutar solo agent tests:

```bash
uv run pytest tests/test_agent.py -v
```

## 📡 Endpoints API

### GET /inventory
Lista todos los productos.

**Respuesta:**
```json
[
  {"id": 1, "name": "Leche de Avena", "quantity": 25, "unit": "litros"},
  {"id": 2, "name": "Café Arábica", "quantity": 8, "unit": "kg"}
]
```

### POST /inventory
Crea un nuevo producto.

**Body:**
```json
{"name": "Té Verde", "quantity": 15, "unit": "kg"}
```

**Respuesta (201):**
```json
{"id": 9, "name": "Té Verde", "quantity": 15, "unit": "kg"}
```

Errores:
- `409`: Producto ya existe (case-insensitive)
- `422`: Validación fallida

### PATCH /inventory/{product_id}
Actualiza el stock (suma/resta cantidad).

**Body:**
```json
{"delta": 5}
```

**Respuesta:**
```json
{"id": 1, "name": "Leche de Avena", "quantity": 30, "unit": "litros"}
```

Errores:
- `404`: Producto no encontrado
- `400`: Stock sería negativo

### GET /inventory/alerts?threshold=10
Productos con cantidad bajo el umbral (default: 10).

**Respuesta:**
```json
[
  {"id": 2, "name": "Café Arábica", "quantity": 8, "unit": "kg"},
  {"id": 4, "name": "Azúcar Moreno", "quantity": 5, "unit": "kg"}
]
```

## 🧠 Cómo Funciona el Agente

### Loop Manual: Observe → Think → Act → Update

1. **Observe**: Lee input del usuario desde terminal
2. **Think**: Envía mensaje + historial a Groq con herramientas disponibles
3. **Act**: Si LLM retorna tool_calls, ejecuta cada herramienta contra la API
4. **Update**: Agrega resultados al historial (mensajes role=tool)
5. **Repeat**: Vuelve a enviar al LLM hasta que responda sin tool_calls
6. **Return**: Imprime respuesta final y registra en log

Máximo 8 iteraciones por turno para evitar bucles infinitos.

### Herramientas del Agente

- `list_inventory()`: Obtiene lista completa de productos
- `add_product(name, quantity, unit)`: Agrega nuevo producto
- `update_stock(product_id, delta)`: Suma/resta cantidad a un producto
- `get_low_stock_alerts(threshold?)`: Productos bajo umbral (default 10)

### Logs Conversacionales

Archivo `conversation_log.csv` guarda:
- Columnas: `actor`, `message`, `tool_call`, `timestamp`
- Registra: inputs usuario, decisiones agent (tool_calls), resultados tools, respuestas
- Append-only: nunca borra, siempre agrega

## 📝 Ejemplos de Frases

```
# Consultas
"¿Cuál es el inventario?"
"¿Qué productos están bajos de stock?"
"Muéstrame los productos con menos de 5 unidades"

# Actualizaciones
"Recibimos 20 litros de leche de avena"
"Vendimos 3 kg de café"
"Registra 50 vasos nuevos"

# Crear productos
"Agrega agua embotellada, 100 botellas"
```

## 🔧 Detalles Técnicos

### Validaciones

- **Nombre**: No vacío, case-insensitive para duplicados
- **Cantidad**: >= 0, no puede ir negativa
- **Unit**: No vacía
- **Delta**: Puede ser negativo, pero stock final >= 0

### Thread Safety

- CSV acceso sincronizado con `threading.Lock`
- Lectura y escritura atómica de productos.csv

### Manejo de Errores

- **API**: HTTPException con mensajes en español
- **Groq**: Si falla, imprime mensaje y continúa
- **HTTP**: Reintentos automáticos con httpx

### Performance

- Productos en memoria durante la sesión (agent.py)
- CSV actualizado con cada cambio (api.app)
- Tests usan CSV temporal para aislamiento

## 🆘 Troubleshooting

**"Error: No `pyproject.toml` found"**
```bash
uv init --python 3.14
```

**"Connection refused" en agent**
- Verifica que API esté corriendo en Terminal 1
- Revisa `INVENTORY_API_URL` en `.env`

**"GROQ_API_KEY not found"**
- Crea `.env` con tu clave de Groq
- No commites `.env` (está en `.gitignore`)

**Tests fallan con "Module not found"**
```bash
uv sync
uv run pytest
```

## 📚 Recursos

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Pydantic](https://docs.pydantic.dev/)
- [OpenAI Python SDK](https://github.com/openai/openai-python)
- [Groq API](https://console.groq.com)
- [pytest Documentation](https://docs.pytest.org/)

---

Hecho con ❤️ para 4Geeks Academy
