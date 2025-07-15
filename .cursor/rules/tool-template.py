# Tool Implementation Template
class ExampleTool(AgentBuilderBaseTool):
    @openapi_schema(
        {
            "type": "function",
            "function": {
                "name": "example_action",
                "description": "Perform an example action",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "First parameter"},
                        "param2": {
                            "type": "integer",
                            "description": "Second parameter",
                        },
                    },
                    "required": ["param1"],
                },
            },
        }
    )
    @xml_schema(
        tag_name="example-action",
        mappings=[
            {"param_name": "param1", "node_type": "attribute", "path": "."},
            {"param_name": "param2", "node_type": "attribute", "path": "."},
        ],
    )
    async def example_action(self, param1: str, param2: int = 0) -> ToolResult:
        try:
            # Implementation here
            result = await self.perform_action(param1, param2)
            return self.success_response(result)
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return self.fail_response(f"Failed to perform action: {str(e)}")
