# General Rules

## Preserve file history when editing
- When modifying an existing file, **do not delete and recreate it**, Always edit the file in place so its Git history is preserved.

## Layer documentation workflow is mandatory
- Every existing layer must have a markdown file with the **same name as that layer** in its related folder.
- Before making any change in a layer, you must first read that layer’s markdown file to understand the current context, constraints, and expected behavior.
- If creating a new layer, you must create it in the correct related folder based on the project structure.
- After any change in a layer’s code, you must update that layer’s markdown file so documentation remains fully aligned with the new codebase.
- This is a **general and important rule** and must be followed for all layer-level changes without exception.