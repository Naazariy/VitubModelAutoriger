## 2026-08-21T17:54:38Z
You are Explorer 2 (Live2D File Format & Ecosystem Specialist).
Your working directory is: d:\VitubModel\.agents\explorer_survey_2
You MUST read the authoritative user request at: d:\VitubModel\.agents\ORIGINAL_REQUEST.md

Task:
Conduct an in-depth survey of Live2D Cubism file formats and ecosystem compatibility (R2):
1. Investigate the exact specifications and structure of Live2D Cubism runtime and editor formats:
   - .moc3 file structure (binary header, sections, CanvasInfo, Parts, Deformers, WarpDeformers, Drawables, Parameters like ParamAngleX/Y/Z, Keyforms, Vertex Deformations, Texture indices, Blend modes).
   - .model3.json file specification (Version, FileReferences: Moc, Textures, Physics, DisplayInfo, Groups/HitAreas).
   - Texture atlas layout and packing (UV coordinates, texture dimensions, PNG generation).
   - .cdi3.json / display info format if applicable.
2. Investigate available Python/C/open-source tools and libraries for generating or compiling .moc3 / model3.json files (e.g. pyLive2D, live2d SDK, Inochi2D specs, custom moc3 binary writer / packers, or intermediate format compilers).
3. Determine the most realistic, reliable, and robust programmatic export path that outputs files directly loadable into Live2D Cubism Viewer, Live2D Cubism Editor, and VTube Studio.
4. Document the exact file schemas, binary structures, parameter mapping standards, and export pipeline in d:\VitubModel\.agents\explorer_survey_2\analysis.md and summarize in handoff.md.
5. Send a message to the orchestrator when finished.
