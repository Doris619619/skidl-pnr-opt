Title: Third-Party Tools

# Third-Party Tools

Tools and projects built by the SKiDL community.

---

## SKiDL IntelliSense VS Code Extension

**Repository:** [ashergarland/skidl-vscode](https://github.com/ashergarland/skidl-vscode)  
**VS Code Marketplace:** [skidl-lsp](https://marketplace.visualstudio.com/items?itemName=ashergarland.skidl-lsp)  
**Discussion:** [#292](https://github.com/devbisme/skidl/discussions/292)

A Visual Studio Code extension that provides intelligent development tools for SKiDL. Features include live fuzzy search across 21,000+ KiCad symbols and 15,000+ footprints, automatic bill-of-materials generation, design validation with pre-flight checks, and an MCP server that lets AI assistants (GitHub Copilot, Claude) browse KiCad libraries and validate SKiDL code.

---

## SKiDL Skills

**Repository:** [nickkraakman/skidl-skills](https://github.com/nickkraakman/skidl-skills)  
**Discussion:** [#291](https://github.com/devbisme/skidl/discussions/291)

A Claude Code plugin that converts plain-English circuit board descriptions into KiCad netlists using SKiDL. Nine specialized AI agents collaborate to handle orchestration, circuit architecture, requirements gathering, and datasheet research. Automatically sources real, in-stock components from KiCad libraries.

---

## Circuitron

**Repository:** [Shaurya-Sethi/circuitron](https://github.com/Shaurya-Sethi/circuitron)  
**Discussion:** [#263](https://github.com/devbisme/skidl/discussions/263)

An open-source, agent-driven PCB design accelerator that transforms natural language requirements into working PCB designs using SKiDL. Powered by OpenAI's Agents SDK with RAG via Model Context Protocol, it produces schematic files, netlists, SVG previews, and KiCad PCB files. Agents iteratively validate and correct designs until ERC checks pass.

---

## Galvano.ai

**Website:** [galvano.ai](https://galvano.ai/)  
**Discussion:** [#267](https://github.com/devbisme/skidl/discussions/267)

An AI-powered schematic review service that analyzes electronic circuit schematics and netlists before PCB manufacturing. Upload KiCad schematics or SPICE netlists along with relevant datasheets, and Galvano checks each node for common design errors, assigns risk scores, and provides an interactive chat interface for design recommendations.
