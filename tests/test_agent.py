import csv
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def temp_conversation_log():
    """Fixture for temporary conversation log."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='') as f:
        temp_path = Path(f.name)
    
    yield temp_path
    
    temp_path.unlink(missing_ok=True)


def test_agent_tool_call_chain(temp_conversation_log):
    """Test agent making a chain of tool calls: list_inventory then update_stock."""
    
    with patch('agent.CONVERSATION_LOG', temp_conversation_log):
        with patch('agent.client') as mock_client:
            # Mock the inventory API responses
            with patch('agent.call_api') as mock_api:
                # First tool call response (list_inventory)
                list_response = {
                    "inventory": [
                        {"id": 1, "name": "Café", "quantity": 5, "unit": "kg"},
                        {"id": 2, "name": "Leche", "quantity": 20, "unit": "litros"},
                    ]
                }
                
                # Second tool call response (update_stock)
                update_response = {
                    "id": 1,
                    "name": "Café",
                    "quantity": 10,
                    "unit": "kg"
                }
                
                mock_api.side_effect = [list_response, update_response]
                
                # Import after mocking
                import agent
                agent.call_api = mock_api
                
                # Mock the LLM response with tool calls
                tool_call_1 = MagicMock()
                tool_call_1.id = "call_1"
                tool_call_1.function.name = "list_inventory"
                tool_call_1.function.arguments = "{}"
                
                tool_call_2 = MagicMock()
                tool_call_2.id = "call_2"
                tool_call_2.function.name = "update_stock"
                tool_call_2.function.arguments = json.dumps({"product_id": 1, "delta": 5})
                
                # First response from LLM: has tool calls
                first_response = MagicMock()
                first_response.choices = [MagicMock()]
                first_response.choices[0].message.content = ""
                first_response.choices[0].message.tool_calls = [tool_call_1, tool_call_2]
                
                # Second response from LLM: final answer, no tool calls
                second_response = MagicMock()
                second_response.choices = [MagicMock()]
                second_response.choices[0].message.content = "Stock de Café actualizado a 10 kg"
                second_response.choices[0].message.tool_calls = None
                
                mock_client.chat.completions.create.side_effect = [first_response, second_response]
                
                # Initialize log
                agent.init_conversation_log()
                
                # Run agent loop
                messages = [{"role": "system", "content": agent.SYSTEM_PROMPT}]
                response, updated_messages = agent.run_agent_loop(
                    "Actualiza el stock de Café en 5 kg", messages
                )
                
                assert response == "Stock de Café actualizado a 10 kg"
                
                # Verify tool results are in messages
                tool_messages = [m for m in updated_messages if m.get("role") == "tool"]
                assert len(tool_messages) == 2
                
                # Verify first tool result contains inventory
                first_tool_result = json.loads(tool_messages[0]["content"])
                assert "inventory" in first_tool_result
                
                # Verify second tool result contains updated product
                second_tool_result = json.loads(tool_messages[1]["content"])
                assert second_tool_result["id"] == 1
                assert second_tool_result["quantity"] == 10


def test_conversation_log_append_only(temp_conversation_log):
    """Test that conversation log is append-only across sessions."""
    
    with patch('agent.CONVERSATION_LOG', temp_conversation_log):
        import agent
        
        # First session
        agent.init_conversation_log()
        agent.log_event("user", "Hola")
        agent.log_event("agent", "¿Cómo estás?")
        
        # Read first session's log
        with open(temp_conversation_log, 'r') as f:
            reader = csv.DictReader(f)
            first_entries = list(reader)
        
        assert len(first_entries) == 2
        
        # Second session - append more
        agent.log_event("user", "¿Cuál es el stock?")
        agent.log_event("agent", "El stock es...")
        
        # Read both sessions
        with open(temp_conversation_log, 'r') as f:
            reader = csv.DictReader(f)
            all_entries = list(reader)
        
        assert len(all_entries) == 4
        assert all_entries[0]["message"] == "Hola"
        assert all_entries[2]["message"] == "¿Cuál es el stock?"


def test_tool_call_logging(temp_conversation_log):
    """Test that tool calls are logged correctly."""
    
    with patch('agent.CONVERSATION_LOG', temp_conversation_log):
        import agent
        
        agent.init_conversation_log()
        
        # Log a tool call
        agent.log_event(
            "agent",
            json.dumps({"product_id": 1, "delta": 5}),
            "update_stock"
        )
        
        # Read and verify
        with open(temp_conversation_log, 'r') as f:
            reader = csv.DictReader(f)
            entries = list(reader)
        
        assert len(entries) == 1
        assert entries[0]["actor"] == "agent"
        assert entries[0]["tool_call"] == "update_stock"
        assert "product_id" in entries[0]["message"]


def test_low_stock_alerts_tool():
    """Test get_low_stock_alerts tool function."""
    
    with patch('agent.call_api') as mock_api:
        mock_api.return_value = {
            "alerts": [
                {"id": 1, "name": "Café", "quantity": 5, "unit": "kg"},
                {"id": 2, "name": "Té", "quantity": 3, "unit": "paquetes"},
            ]
        }
        
        import agent
        agent.call_api = mock_api
        
        # Test with custom threshold
        result = agent.get_low_stock_alerts(threshold=10)
        
        assert "alerts" in result
        assert len(result["alerts"]) == 2
        mock_api.assert_called_once_with("GET", "/inventory/alerts", {"threshold": 10})
        
        # Test without threshold
        mock_api.reset_mock()
        mock_api.return_value = {"alerts": [{"id": 1, "name": "Café", "quantity": 5, "unit": "kg"}]}
        
        result = agent.get_low_stock_alerts()
        
        assert "alerts" in result
        mock_api.assert_called_once_with("GET", "/inventory/alerts", {})
