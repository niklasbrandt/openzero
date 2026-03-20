import pytest
import tempfile
import json
import os
from unittest.mock import AsyncMock, patch
from app.services.dify import CrewRegistry

@pytest.mark.anyio
async def test_yaml_parser_graceful_failure():
    """
    Test that invalid YAML syntaxes trigger graceful warnings,
    not fatal Exceptions, allowing openZero to boot regardless.
    """
    # Create a temporary registry
    with tempfile.TemporaryDirectory() as td:
        map_path = os.path.join(td, ".dify_app_ids.json")
        crews_path = os.path.join(td, "crews.yaml")
        
        # Write invalid YAML
        with open(crews_path, "w") as f:
            f.write("invalid: [yaml: content:")
            
        registry = CrewRegistry(agent_dir=td, client=None)
        
        # Load should not raise an exception
        await registry.load()
        
        # State should be empty but initialized
        assert len(registry.list_active()) == 0

@pytest.mark.anyio
async def test_app_resolution_import_loop():
    """
    Test missing UUIDs correctly trigger an import loop when provisioning.
    """
    with tempfile.TemporaryDirectory() as td:
        map_path = os.path.join(td, ".dify_app_ids.json")
        crews_path = os.path.join(td, "crews.yaml")
        dify_agent_dir = os.path.join(td, "dify")
        os.makedirs(dify_agent_dir)
        
        # Write valid YAML for one crew that has no UUID yet
        with open(crews_path, "w") as f:
            f.write('''
dify_crews:
  - id: test_crew
    name: "Test Crew"
    description: "Mock crew for isolated UUID testing mapping"
    type: "workflow"
    dify_dsl_file: "test_crew.yml"
    enabled: true
            ''')
            
        # Write a dummy DSL file
        with open(os.path.join(dify_agent_dir, "test_crew.yml"), "w") as f:
            f.write("app: dummy")
            
        with patch("app.services.dify.DifyClient") as mock_dify_class:
            mock_client = mock_dify_class.return_value
            # Mock the import to return a valid app ID
            mock_client.import_dsl = AsyncMock(return_value="mock-uuid-1234")
            
            registry = CrewRegistry(agent_dir=td, client=mock_client)
            await registry.load()
            
            # The crew should initially not have a dify_app_id
            crew = registry.get("test_crew")
            assert crew.dify_app_id is None
            
            # Provision should trigger import_dsl
            await registry.provision()
            
            mock_client.import_dsl.assert_called_once()
            
            # After provisioning, the crew should have an ID
            crew_after = registry.get("test_crew")
            assert crew_after is not None
            assert crew_after.dify_app_id == "mock-uuid-1234"
