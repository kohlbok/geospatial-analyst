# Setup

Install dependencies and configure MCP servers for the current platform.

## Steps

1. Detect the platform and run the appropriate install script from the repo root:
   - macOS/Linux: `bash install.sh`
   - Windows: `powershell -ExecutionPolicy Bypass -File install.ps1`

2. Verify `.mcp.json` was generated. Read it and confirm the python path looks correct for the platform.

3. Report:
   ```
   Setup complete.
     Python: [version]
     MCP server: geospatial configured

   Ready to go. Drop your data files into data/ and run:
     /collect-dams [country] - collect from global databases
     /normalize-dams - transform an existing file into the screening schema
     /screen-dams - find pairs between existing dams (Phase 1)
     /scan-terrain - find new reservoir sites for greenfield siting

   IMPORTANT: Start a new session to connect the MCP server.
     CLI: type /mcp to reload, or restart claude
     Desktop app: click "New session" in the sidebar
   ```
