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

   Ready to go. Run /screen-dams to start screening.
   ```
