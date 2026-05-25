# ComfyUI Workflows

Place ComfyUI API-format workflow JSON files in this directory.

## How to Export a Workflow from ComfyUI

1. Build your workflow in the ComfyUI UI (add nodes, connect them, configure defaults)
2. Click the **hamburger menu** (top-right) → **"Save (API Format)"**
3. Save the resulting JSON file into this directory
4. Run the inspect script to find node IDs:

```bash
python scripts/inspect_workflow.py plugins/builtin/comfyui/workflows/your_workflow.json
```

5. Update the `node_map` under `plugins.comfyui` in `config/settings.yaml`

## Node IDs

ComfyUI API-format JSON uses **string** node IDs (e.g. `"6"`, `"3"`). These are the
keys at the top level of the workflow dict. The `node_map` in settings must use
these same string IDs.

## Multiple Workflows

You can define multiple workflows in `settings.yaml`:

```yaml
plugins:
  comfyui:
    workflows:
      default: "plugins/builtin/comfyui/workflows/default_txt2img.json"
      portrait: "plugins/builtin/comfyui/workflows/portrait_xl.json"
```

The `comfyui_generate_image` tool accepts an optional `workflow_name` parameter that maps
to these keys. Omitting it uses the `default` workflow.